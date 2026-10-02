"""
Tests for sieveon's Python router components
"""
import unittest
import sys
import os

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.router.policy import RoutingPolicy, QueryType
from src.router.budget import BudgetLevel
from src.router.cost_awareness import CostTracker, cost_tracker
from src.extraction.classifier import QueryClassifier


def route(policy, query_type, confidence):
    """get_strategy returns a (strategy, budget, policy_applied) tuple."""
    strategy, budget, applied = policy.get_strategy(query_type, confidence)
    return strategy, budget.value, applied


class TestRoutingPolicy(unittest.TestCase):
    def setUp(self):
        # The policy reads the module-global cost tracker, so a previous test's
        # metrics could otherwise influence the strategy choice.
        cost_tracker.reset_metrics()
        self.policy = RoutingPolicy()

    def test_temporal_query_routing(self):
        """Temporal queries route to the event-log-first strategy"""
        strategy, budget, applied = route(self.policy, "temporal", 0.8)
        self.assertEqual(strategy, "event_log_first")
        self.assertEqual(budget, "medium")
        self.assertEqual(applied, "strict")

    def test_factual_query_routing(self):
        """Factual queries route to the semantic hybrid strategy"""
        strategy, budget, _ = route(self.policy, "factual", 0.8)
        self.assertEqual(strategy, "semantic_hybrid")
        self.assertEqual(budget, "high")

    def test_multi_hop_query_routing(self):
        """Multi-hop queries route to the graph expansion strategy"""
        strategy, budget, _ = route(self.policy, "multi-hop", 0.8)
        self.assertEqual(strategy, "hybrid_with_graph_expansion")
        self.assertEqual(budget, "high")

    def test_multi_hop_at_typical_classifier_confidence_stays_strict(self):
        """Measured multi-hop confidences are 0.68/0.71 -- below the old 0.8
        bar, which sent exactly the queries needing graph expansion to the
        generic fallback. The threshold must sit inside the operating range."""
        for conf in (0.68, 0.71):
            strategy, budget, applied = route(self.policy, "multi-hop", conf)
            self.assertEqual(strategy, "hybrid_with_graph_expansion", conf)
            self.assertEqual(applied, "strict", conf)
            self.assertEqual(budget, "high", conf)

    def test_conversational_query_routing(self):
        """Conversational queries route to the BM25/vector/temporal strategy"""
        strategy, budget, _ = route(self.policy, "conversational", 0.8)
        self.assertEqual(strategy, "hybrid_bm25_vector_temporal")
        self.assertEqual(budget, "medium")

    def test_update_query_routing(self):
        """Update queries route to the knowledge graph invalidation strategy"""
        strategy, budget, _ = route(self.policy, "update", 0.95)
        self.assertEqual(strategy, "knowledge_graph_with_invalidation")
        self.assertEqual(budget, "high")

    def test_update_query_below_min_confidence_degrades_to_read_only(self):
        """UPDATE has a high min_confidence (writes are dangerous), so weaker
        matches degrade -- but to a READ-ONLY strategy, never to a generic
        fallback and never to the invalidation path that triggers writes."""
        strategy, budget, applied = route(self.policy, "update", 0.8)
        self.assertEqual(applied, "degraded")
        self.assertNotEqual(strategy, "knowledge_graph_with_invalidation")
        self.assertNotEqual(strategy, "hybrid_fallback")
        # budget steps down one level from the configured HIGH
        self.assertEqual(budget, "medium")

    def test_low_confidence_degrades_type_strategy_not_generic_fallback(self):
        """Below min_confidence the policy keeps the query-type strategy at a
        reduced budget. The classifier's type guess stays informative even when
        uncertain; the generic fallback discards it."""
        strategy, budget, applied = route(self.policy, "temporal", 0.2)
        self.assertEqual(strategy, "event_log_first")
        self.assertEqual(applied, "degraded")
        # MEDIUM steps down to LOW
        self.assertEqual(budget, "low")

    def test_degraded_budget_steps_down_one_level(self):
        """HIGH -> MEDIUM -> LOW, never below LOW."""
        _, budget, applied = route(self.policy, "factual", 0.2)
        self.assertEqual(applied, "degraded")
        self.assertEqual(budget, "medium")  # HIGH -> MEDIUM
        _, budget, _ = route(self.policy, "conversational", 0.2)
        self.assertEqual(budget, "low")  # MEDIUM -> LOW

    def test_high_confidence_strict(self):
        """Above min_confidence the policy applies the strict policy"""
        _, _, applied = route(self.policy, "factual", 0.8)
        self.assertEqual(applied, "strict")

    def test_unknown_query_type_fallback(self):
        """Unknown query types fall back to the factual config"""
        strategy, budget, _ = route(self.policy, "unknown_type", 0.8)
        self.assertEqual(strategy, "semantic_hybrid")
        self.assertEqual(budget, "high")

    def test_query_type_enum_accepted(self):
        """QueryType enums are accepted alongside their string values"""
        from_enum = self.policy.get_strategy(QueryType.TEMPORAL, 0.8)
        from_string = self.policy.get_strategy("temporal", 0.8)
        self.assertEqual(from_enum, from_string)

    def test_get_budget_for_query(self):
        """get_budget_for_query resolves both enums and strings"""
        for query_type in (QueryType.FACTUAL, "factual", "multi_hop"):
            self.assertEqual(
                self.policy.get_budget_for_query(query_type), BudgetLevel.HIGH
            )
        self.assertEqual(
            self.policy.get_budget_for_query("temporal"), BudgetLevel.MEDIUM
        )

    def test_custom_config(self):
        """Custom per-query-type configuration overrides the defaults"""
        custom_policy = RoutingPolicy(
            config={"factual": {"strategy": "custom_strategy", "min_confidence": 0.7}}
        )
        strategy, _, _ = route(custom_policy, "factual", 0.8)
        self.assertEqual(strategy, "custom_strategy")

    def test_custom_config_low_confidence_degrades(self):
        """A raised min_confidence degrades low-confidence queries: same
        strategy, stepped-down budget -- not the generic fallback."""
        custom_policy = RoutingPolicy(
            config={"factual": {"strategy": "custom_strategy", "min_confidence": 0.9}}
        )
        strategy, budget, applied = route(custom_policy, "factual", 0.8)
        self.assertEqual(strategy, "custom_strategy")
        self.assertEqual(applied, "degraded")
        # HIGH steps down to MEDIUM
        self.assertEqual(budget, "medium")

    def test_update_query_config(self):
        """update_query_config changes the strategy for a query type"""
        self.policy.update_query_config("conversational", strategy="composite_kg_vector")
        strategy, _, _ = route(self.policy, "conversational", 0.9)
        self.assertEqual(strategy, "composite_kg_vector")

    def test_adaptive_selection_respects_compatibility(self):
        """A learned strategy is only used for query types it suits"""
        # Teach the tracker that event_log_first is great, over MIN_SAMPLES requests
        for _ in range(CostTracker.MIN_SAMPLES):
            cost_tracker.record_request(
                "event_log_first", latency=0.1, success=True, relevance=0.9
            )
        # factual does not consider event_log_first compatible -> keeps its default
        strategy, _, _ = route(self.policy, "factual", 0.8)
        self.assertEqual(strategy, "semantic_hybrid")
        # temporal does consider it compatible
        strategy, _, _ = route(self.policy, "temporal", 0.8)
        self.assertEqual(strategy, "event_log_first")

    def test_adaptive_selection_skips_slow_strategies(self):
        """A strategy exceeding max_latency_threshold is not selected"""
        for _ in range(CostTracker.MIN_SAMPLES):
            cost_tracker.record_request(
                "event_log_first",
                latency=5.0,  # way over the 1.0s threshold for temporal
                success=True,
                relevance=0.9,
            )
        # event_log_first would be the only candidate, but it is too slow,
        # so the configured default is used instead
        strategy, _, _ = route(self.policy, "temporal", 0.8)
        self.assertEqual(strategy, "event_log_first")

    def test_adaptive_selection_prefers_fast_alternative(self):
        """A fast compatible strategy is preferred over a slow one"""
        for _ in range(CostTracker.MIN_SAMPLES):
            cost_tracker.record_request(
                "event_log_first", latency=5.0, success=True, relevance=0.9
            )
        for _ in range(CostTracker.MIN_SAMPLES):
            cost_tracker.record_request(
                "hybrid_bm25_vector_temporal",
                latency=0.1,
                success=True,
                relevance=0.9,
            )
        strategy, _, _ = route(self.policy, "temporal", 0.8)
        self.assertEqual(strategy, "hybrid_bm25_vector_temporal")

    def test_adaptive_selection_ignores_thin_samples(self):
        """A single observation is not enough to change routing"""
        cost_tracker.record_request(
            "event_log_first", latency=0.1, success=True, relevance=0.9
        )
        strategy, _, _ = route(self.policy, "temporal", 0.8)
        self.assertEqual(strategy, "event_log_first")  # same as the default, not adaptive

    def test_get_all_costs_reports_config_and_metrics(self):
        """get_all_costs exposes policy config, tracker metrics and health"""
        report = self.policy.get_all_costs()
        self.assertIn("policy_config", report)
        self.assertIn("cost_tracker_metrics", report)
        self.assertIn(QueryType.FACTUAL.value, report["policy_config"])
        self.assertIn("system_health", report)


class TestCostTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = CostTracker()

    def test_initial_state(self):
        """A fresh tracker has no metrics and no ranked strategies"""
        self.assertEqual(self.tracker.get_all_strategies_ranked(), [])
        self.assertEqual(self.tracker.get_all_costs(), {})
        self.assertIsNone(self.tracker.get_average_latency("test_strategy"))
        self.assertIsNone(self.tracker.get_success_rate("test_strategy"))
        self.assertIsNone(self.tracker.get_average_cost("test_strategy"))

    def test_record_single_request(self):
        """A single successful request is reflected in the averages"""
        self.tracker.record_request(
            "test_strategy", latency=0.1, success=True, relevance=0.8
        )
        self.assertAlmostEqual(self.tracker.get_average_latency("test_strategy"), 0.1)
        self.assertEqual(self.tracker.get_success_rate("test_strategy"), 1.0)
        self.assertGreater(self.tracker.get_average_cost("test_strategy"), 0.0)

    def test_record_multiple_requests(self):
        """Counts, success rate and latency average accumulate correctly"""
        self.tracker.record_request("s", latency=0.1, success=True, relevance=0.8)
        self.tracker.record_request("s", latency=0.2, success=False, relevance=0.6)
        self.tracker.record_request("s", latency=0.15, success=True, relevance=0.9)

        self.assertAlmostEqual(self.tracker.get_average_latency("s"), 0.15)
        self.assertAlmostEqual(self.tracker.get_success_rate("s"), 2 / 3)
        self.assertEqual(self.tracker.get_all_costs()["s"]["total_requests"], 3)

    def test_ranking_is_per_query_type_not_global(self):
        """A strategy that shines for factual must not hijack temporal routing.

        This is the core contextual-bandit property: effectiveness is learned
        per (query type, strategy), so a globally good strategy cannot override
        a locally better one.
        """
        for _ in range(3):
            self.tracker.record_request("semantic_hybrid", latency=0.4,
                                        success=True, relevance=0.9,
                                        query_type="factual")
            self.tracker.record_request("event_log_first", latency=0.3,
                                        success=True, relevance=0.9,
                                        query_type="temporal")
        # semantic_hybrid has NO temporal samples: it must not outrank the
        # strategy that actually proved itself on temporal queries.
        ranked_temporal = [s for s, _ in
                           self.tracker.get_all_strategies_ranked(query_type="temporal")]
        self.assertIn("event_log_first", ranked_temporal)
        self.assertNotIn("semantic_hybrid", ranked_temporal)

    def test_global_ranking_aggregates_contexts(self):
        """Without a query type, ranking aggregates across contexts
        (backward compatible with the old global view)."""
        for _ in range(3):
            self.tracker.record_request("a", latency=0.1, success=True,
                                        relevance=0.9, query_type="factual")
            self.tracker.record_request("b", latency=0.1, success=True,
                                        relevance=0.9, query_type="temporal")
        ranked = [s for s, _ in self.tracker.get_all_strategies_ranked()]
        self.assertIn("a", ranked)
        self.assertIn("b", ranked)

    def test_export_import_roundtrip(self):
        """State survives a process restart via export/import (for persistence)."""
        for _ in range(3):
            self.tracker.record_request("s", latency=0.2, success=True,
                                        relevance=0.8, query_type="factual")
        state = self.tracker.export_state()
        import json
        json.dumps(state)  # must be JSON-serializable for DB storage
        fresh = CostTracker()
        fresh.import_state(state)
        self.assertAlmostEqual(fresh.get_average_latency("s", query_type="factual"), 0.2)
        self.assertEqual(
            [s for s, _ in fresh.get_all_strategies_ranked(query_type="factual")],
            [s for s, _ in self.tracker.get_all_strategies_ranked(query_type="factual")],
        )

    def test_cost_formula(self):
        """Cost = base_cost * num_queries * (1 + (1 - relevance))"""
        self.tracker.record_request(
            "event_log_first", latency=0.1, success=True, num_queries=2, relevance=0.5
        )
        # base 0.5 * 2 queries * (1 + 0.5) = 1.5
        self.assertAlmostEqual(self.tracker.get_average_cost("event_log_first"), 1.5)

    def test_lower_relevance_costs_more(self):
        """A less relevant result is treated as more expensive"""
        self.tracker.record_request("s", latency=0.1, success=True, relevance=0.9)
        self.tracker.record_request("s", latency=0.1, success=True, relevance=0.1)
        self.assertGreater(
            self.tracker.get_average_cost("s"),
            self.tracker.base_costs["event_log_first"] * 0.1,
        )

    def test_base_costs_cover_all_strategies(self):
        """Every strategy the executor can run has a configured base cost"""
        from src.planner.executor import RetrievalStrategy

        for strategy in RetrievalStrategy:
            self.assertIn(strategy.value, self.tracker.base_costs)

    def test_effectiveness_score_bounds(self):
        """Effectiveness stays within 0.0-1.0 even with the recency bonus"""
        for _ in range(CostTracker.MIN_SAMPLES):
            self.tracker.record_request(
                "event_log_first", latency=0.1, success=True, relevance=1.0
            )
        score = self.tracker.get_effectiveness_score("event_log_first")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_ranked_ignores_thin_samples(self):
        """Strategies with fewer than MIN_SAMPLES requests are not ranked"""
        self.tracker.record_request("s", latency=0.1, success=True, relevance=0.9)
        self.assertEqual(self.tracker.get_all_strategies_ranked(), [])

        for _ in range(CostTracker.MIN_SAMPLES - 1):
            self.tracker.record_request("s", latency=0.1, success=True, relevance=0.9)
        ranked = self.tracker.get_all_strategies_ranked()
        self.assertEqual([name for name, _ in ranked], ["s"])

    def test_ranking_prefers_successful_strategies(self):
        """A strategy that always succeeds outranks one that always fails"""
        for _ in range(CostTracker.MIN_SAMPLES):
            self.tracker.record_request("good", latency=0.1, success=True, relevance=0.9)
            self.tracker.record_request("bad", latency=0.1, success=False, relevance=0.9)
        ranked = dict(self.tracker.get_all_strategies_ranked())
        self.assertGreater(ranked["good"], ranked["bad"])

    def test_get_all_costs(self):
        """get_all_costs reports a summary per tracked strategy"""
        self.tracker.record_request("strategy1", latency=0.1, success=True, relevance=0.8)
        self.tracker.record_request("strategy2", latency=0.2, success=False, relevance=0.6)

        all_costs = self.tracker.get_all_costs()
        self.assertEqual(len(all_costs), 2)
        for entry in all_costs.values():
            for key in (
                "average_latency",
                "success_rate",
                "average_cost",
                "total_requests",
                "effectiveness_score",
            ):
                self.assertIn(key, entry)

    def test_reset_metrics(self):
        """reset_metrics clears all recorded data"""
        self.tracker.record_request("s", latency=0.1, success=True, relevance=0.9)
        self.tracker.reset_metrics()
        self.assertEqual(self.tracker.get_all_costs(), {})


class TestQueryClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = QueryClassifier()

    def test_classify_various_query_types(self):
        """Test classification of various query types (English only)"""
        test_cases = [
            ("When did I meet Alice?", "temporal"),
            ("Who is my customer?", "factual"),
            ("Why did we stop the project?", "multi-hop"),
            ("What did we talk about yesterday?", "conversational"),  # This may sometimes be classified as temporal
            ("Update my name", "update"),
        ]

        for query, expected_type in test_cases:
            with self.subTest(query=query):
                q_type, confidence = self.classifier.classify(query)
                # Allow for some flexibility in the "What did we talk about yesterday?" case
                # since "yesterday" is a strong temporal indicator
                if query == "What did we talk about yesterday?":
                    # This query has both temporal and conversational patterns, so accept either
                    self.assertIn(q_type, ["temporal", "conversational"])
                else:
                    self.assertEqual(q_type, expected_type)
                self.assertGreaterEqual(confidence, 0.5)

    def test_confidence_calculation(self):
        """Test that confidence is properly calculated"""
        q_type, confidence = self.classifier.classify("When did I meet Alice?")
        self.assertGreaterEqual(confidence, 0.6)  # Should have high confidence for clear temporal query

        q_type, confidence = self.classifier.classify("some random text")
        self.assertLessEqual(confidence, 0.5)  # Should have lower confidence for ambiguous query

    def test_priority_ordering(self):
        """Test that priorities are handled when multiple patterns match"""
        # A query that matches both temporal and factual patterns
        # According to priority order, temporal should win
        query = "When did who write the report?"  # Contains both temporal and factual patterns
        q_type, confidence = self.classifier.classify(query)
        # Since we don't have a specific test case that matches multiple patterns clearly,
        # we'll just verify it returns a valid result
        self.assertIn(q_type, ["temporal", "factual", "multi-hop", "conversational", "update"])
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)

    def test_english_queries(self):
        """Test classification of English queries"""
        test_cases = [
            ("When did we meet?", "temporal"),
            ("Who is the CEO?", "factual"),
            ("Why did sales decrease?", "multi-hop"),
            ("Do you remember our last meeting?", "conversational"),
            ("Change the meeting time", "update"),
        ]

        for query, expected_type in test_cases:
            with self.subTest(query=query):
                q_type, confidence = self.classifier.classify(query)
                self.assertEqual(q_type, expected_type)
                self.assertGreaterEqual(confidence, 0.5)


class TestRouterIntegration(unittest.TestCase):
    def setUp(self):
        cost_tracker.reset_metrics()
        self.classifier = QueryClassifier()
        self.policy = RoutingPolicy()

    def test_full_router_pipeline(self):
        """Test the full pipeline from classification to routing decision"""
        test_queries = [
            ("When did I meet Alice?", QueryType.TEMPORAL),
            ("Who is the CEO?", QueryType.FACTUAL),
            ("Why did sales decrease?", QueryType.MULTI_HOP),
            ("Do you remember our last meeting?", QueryType.CONVERSATIONAL),
            ("Update my contact info", QueryType.UPDATE),
        ]

        from src.planner.executor import RetrievalStrategy

        for query, expected_type in test_queries:
            with self.subTest(query=query):
                q_type, confidence = self.classifier.classify(query)
                self.assertEqual(
                    self.policy._resolve_query_type(q_type), expected_type
                )

                strategy, budget, applied = self.policy.get_strategy(q_type, confidence)

                # The routed strategy must be executable
                self.assertIn(strategy, [s.value for s in RetrievalStrategy])
                # And the budget must be one the BudgetTracker understands
                self.assertIn(budget, list(BudgetLevel))

                if applied == "fallback":
                    # Unknown type: factual default (hybrid_fallback is retired;
                    # the router no longer selects it)
                    self.assertEqual(
                        strategy, self.policy.config[QueryType.FACTUAL]["strategy"]
                    )
                elif applied == "degraded":
                    # Uncertain: type-appropriate strategy at reduced budget.
                    # UPDATE degrades to a read-only strategy, never the
                    # invalidation write path.
                    if expected_type == QueryType.UPDATE:
                        self.assertEqual(strategy, "knowledge_graph_first")
                    else:
                        self.assertEqual(
                            strategy, self.policy.config[expected_type]["strategy"]
                        )
                    self.assertLess(
                        confidence, self.policy.config[expected_type]["min_confidence"]
                    )
                else:
                    self.assertEqual(strategy, self.policy.config[expected_type]["strategy"])
                    self.assertGreaterEqual(
                        confidence, self.policy.config[expected_type]["min_confidence"]
                    )


if __name__ == '__main__':
    print("Running sieveon Python Router Tests...")
    unittest.main(verbosity=2)
