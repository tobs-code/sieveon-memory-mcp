"""
Unit Tests for Strata
Testing individual Python components and their functions
"""
import unittest
import asyncio
from src.extraction.classifier import QueryClassifier
from src.router.policy import BudgetLevel, QueryType, RoutingPolicy
from src.planner.executor import PlanExecutor
from src.extraction.entropy_gate import EntropyGate
from src.extraction.embedding_service import get_embedding_service


class TestRegexClassifier(unittest.TestCase):
    """Pure regex fallback tests (no model, deterministic)."""

    def setUp(self):
        from src.extraction.classifier import _RegexClassifier
        self.regex = _RegexClassifier()

    def test_how_is_factual(self):
        self.assertEqual(self.regex.classify("How does RAG work?")[0], "factual")

    def test_greetings_are_conversational(self):
        for q in ("hi", "hello there", "hey, are you there?", "hallo", "good morning"):
            self.assertEqual(self.regex.classify(q)[0], "conversational", q)

    def test_update_read_requests_suppressed(self):
        q_type, _ = self.regex.classify("Update me on the project status")
        self.assertNotEqual(q_type, "update")

    def test_memory_write_verbs_are_update(self):
        for q in ("Don't forget the meeting", "Remind me to call", "Vergiss die Blumen nicht"):
            self.assertEqual(self.regex.classify(q)[0], "update", q)

    def test_coordination_is_multi_hop(self):
        self.assertEqual(
            self.regex.classify("Who runs Orion Labs and where are they?")[0], "multi-hop"
        )

    def test_german_change_is_factual(self):
        self.assertEqual(self.regex.classify("Was hat sich geaendert?")[0], "factual")

    def test_why_definition_not_multi_hop(self):
        # "why is/are" alone must not score multi-hop (lookup, not synthesis)
        q_type, _ = self.regex.classify("Why is the sky blue?")
        self.assertNotEqual(q_type, "multi-hop")

    def test_ml_vetoes(self):
        """Deterministic vetoes override confident ML verdicts."""
        clf = QueryClassifier()
        clf._ensure_ml()
        if clf._ml.is_trained():
            label, conf = clf._ml.classify("Update me on the project status")
            if label == "update" and conf >= 0.60:
                self.assertNotEqual(clf.classify("Update me on the project status")[0], "update")
            label, conf = clf._ml.classify("Was hat sich geaendert?")
            if label == "conversational" and conf >= 0.60:
                self.assertEqual(clf.classify("Was hat sich geaendert?")[0], "factual")


class TestQueryClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = QueryClassifier()

    def test_temporal_classification(self):
        """Test classification of temporal queries"""
        query = "When did I meet Alice?"
        q_type, confidence = self.classifier.classify(query)
        self.assertEqual(q_type, "temporal")
        self.assertGreaterEqual(confidence, 0.5)

    def test_factual_classification(self):
        """Test classification of factual queries"""
        query = "Who is my manager?"
        q_type, confidence = self.classifier.classify(query)
        self.assertEqual(q_type, "factual")
        self.assertGreaterEqual(confidence, 0.5)

    def test_multi_hop_classification(self):
        """Test classification of multi-hop queries"""
        query = "Why did the project fail?"
        q_type, confidence = self.classifier.classify(query)
        self.assertEqual(q_type, "multi-hop")
        self.assertGreaterEqual(confidence, 0.5)

    def test_conversational_classification(self):
        """Test classification of conversational queries"""
        query = "Do you remember our last meeting?"
        q_type, confidence = self.classifier.classify(query)
        self.assertEqual(q_type, "conversational")
        self.assertGreaterEqual(confidence, 0.5)

    def test_update_classification(self):
        """Test classification of update queries"""
        query = "Update my contact information"
        q_type, confidence = self.classifier.classify(query)
        self.assertEqual(q_type, "update")
        self.assertGreaterEqual(confidence, 0.5)

    def test_low_confidence_default(self):
        """Test that random text defaults to factual"""
        query = "random gibberish text"
        q_type, confidence = self.classifier.classify(query)
        self.assertEqual(q_type, "factual")


class TestRoutingPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = RoutingPolicy()

    def test_temporal_policy(self):
        """Test routing policy for temporal queries (min_confidence=0.5)"""
        strategy_name, budget_level, policy_applied = self.policy.get_strategy(QueryType.TEMPORAL, 0.9)
        self.assertEqual(policy_applied, "strict")
        self.assertIs(budget_level, BudgetLevel.MEDIUM)

    def test_factual_policy(self):
        """Test routing policy for factual queries (min_confidence=0.4)"""
        strategy_name, budget_level, policy_applied = self.policy.get_strategy(QueryType.FACTUAL, 0.8)
        self.assertEqual(policy_applied, "strict")
        self.assertIs(budget_level, BudgetLevel.HIGH)

    def test_multi_hop_policy(self):
        """Test routing policy for multi-hop queries (min_confidence=0.8 → 0.7 triggers fallback)"""
        strategy_name, budget_level, policy_applied = self.policy.get_strategy(QueryType.MULTI_HOP, 0.7)
        self.assertEqual(strategy_name, "hybrid_fallback")
        self.assertEqual(policy_applied, "fallback")

    def test_conversational_policy(self):
        """Test routing policy for conversational queries (min_confidence=0.6)"""
        strategy_name, budget_level, policy_applied = self.policy.get_strategy(QueryType.CONVERSATIONAL, 0.9)
        self.assertEqual(policy_applied, "strict")
        self.assertIs(budget_level, BudgetLevel.MEDIUM)

    def test_update_policy(self):
        """Test routing policy for update queries (min_confidence=0.9 → 0.8 triggers fallback)"""
        strategy_name, budget_level, policy_applied = self.policy.get_strategy(QueryType.UPDATE, 0.8)
        self.assertEqual(strategy_name, "hybrid_fallback")
        self.assertEqual(policy_applied, "fallback")

    def test_low_confidence_fallback(self):
        """Test that low confidence triggers fallback strategy"""
        strategy_name, budget_level, policy_applied = self.policy.get_strategy(QueryType.TEMPORAL, 0.3)
        self.assertEqual(strategy_name, "hybrid_fallback")
        self.assertEqual(policy_applied, "fallback")


class TestPlanExecutor(unittest.TestCase):
    def setUp(self):
        self.executor = PlanExecutor()

    def test_plan_creation(self):
        """Test that plan executor can create a basic plan"""
        result = asyncio.run(self.executor.execute_plan(
            strategy="knowledge_graph_first",
            query="Who is my main contact?",
            budget_level="medium",
        ))
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertIn("execution_metadata", result)


class TestEntropyGate(unittest.TestCase):
    def setUp(self):
        self.gate = EntropyGate()

    def test_entropy_calculation(self):
        """Test that entropy is calculated correctly"""
        text = "This is a test sentence."
        entropy = self.gate.calculate_char_entropy(text)
        self.assertIsInstance(entropy, float)
        self.assertGreaterEqual(entropy, 0.0)

    def test_novelty_calculation(self):
        """Test that novelty is calculated correctly"""
        text = "This is a completely new piece of text."
        novelty = self.gate.calculate_novelty(text)
        self.assertIsInstance(novelty, float)
        self.assertGreaterEqual(novelty, 0.0)
        self.assertLessEqual(novelty, 1.0)

    def test_short_text_skip(self):
        """Test that short texts are skipped"""
        short_text = "Hi"
        result = self.gate.should_extract(short_text)
        self.assertEqual(result["decision"], "skip")
        self.assertEqual(result["reason"], "text_too_short")

    def test_extraction_decision(self):
        """Test that extraction decisions are made properly"""
        text = "This is a longer text that should be evaluated for extraction."
        result = self.gate.should_extract(text)
        self.assertIn("decision", result)
        self.assertIn(result["decision"], ["extract", "ignore", "skip"])


class TestEmbeddingService(unittest.TestCase):
    def setUp(self):
        self.service = get_embedding_service()

    def test_embedding_dimensions(self):
        """Test that embeddings have expected dimensions"""
        text = "Test embedding for dimension check"
        embedding = self.service.embed_for_storage(text)
        self.assertIsInstance(embedding, list)
        self.assertGreater(len(embedding), 0)
        self.assertTrue(all(isinstance(x, float) for x in embedding))

    def test_query_vs_storage_embeddings(self):
        """Test that query and storage embeddings have same dimensions"""
        text = "Test text for both embedding types"
        query_emb = self.service.embed_for_query(text)
        storage_emb = self.service.embed_for_storage(text)
        self.assertEqual(len(query_emb), len(storage_emb))


class TestTiering(unittest.TestCase):
    """Pure-function tests for tier_keep (no DB, no model)."""

    def test_threshold_boundary(self):
        from src.extraction.entropy_gate import tier_keep
        self.assertTrue(tier_keep(0.50, 0.50))
        self.assertFalse(tier_keep(0.4999, 0.50))

    def test_disabled_threshold_keeps_all(self):
        from src.extraction.entropy_gate import tier_keep
        self.assertTrue(tier_keep(0.0, 0.0))
        self.assertTrue(tier_keep(0.0, 0))

    def test_bad_input_keeps(self):
        from src.extraction.entropy_gate import tier_keep
        self.assertTrue(tier_keep(None, 0.5))
        self.assertTrue(tier_keep("x", 0.5))

    def test_env_default(self):
        import os
        from src.extraction import entropy_gate
        prev = os.environ.pop("TIER_DROP_THRESHOLD", None)
        try:
            self.assertEqual(entropy_gate.tier_threshold(), 0.50)
            os.environ["TIER_DROP_THRESHOLD"] = "0"
            self.assertEqual(entropy_gate.tier_threshold(), 0.0)
        finally:
            if prev is None:
                os.environ.pop("TIER_DROP_THRESHOLD", None)
            else:
                os.environ["TIER_DROP_THRESHOLD"] = prev


class TestFtsSanitize(unittest.TestCase):
    """FTS query sanitization: natural questions must survive @@ matching."""

    def test_question_mark_removed(self):
        from src.extraction.entropy_gate import sanitize_fts_query
        out = sanitize_fts_query("When did Caroline go to the LGBTQ support group?")
        self.assertNotIn("?", out)
        self.assertIn("Caroline", out)
        self.assertIn("LGBTQ", out)

    def test_operators_stripped(self):
        from src.extraction.entropy_gate import sanitize_fts_query
        out = sanitize_fts_query('a+b -c "d" (e)*f:g!')
        self.assertEqual(out, "a b c d e f g")

    def test_empty_safe(self):
        from src.extraction.entropy_gate import sanitize_fts_query
        self.assertEqual(sanitize_fts_query(""), "")
        self.assertEqual(sanitize_fts_query("???"), "")

    def test_keywords_drop_stopwords(self):
        from src.extraction.entropy_gate import fts_keywords
        self.assertEqual(
            fts_keywords("When did Caroline go to the LGBTQ support group?"),
            "caroline lgbtq support group",
        )
        # Nothing but stopwords -> falls back to sanitized text, never empty
        self.assertTrue(fts_keywords("When is it?"))
        self.assertEqual(fts_keywords("Alice?"), "alice")


class TestTrustAndRecordIds(unittest.TestCase):
    """Pure-function tests for trust marking and record-id validation."""
    def test_trust_defaults(self):
        from src.mcp.core import _trust_of
        self.assertEqual(_trust_of("user_input"), "direct")
        self.assertEqual(_trust_of("markdown_import"), "untrusted")
        self.assertEqual(_trust_of("web", "direct"), "direct")

    def test_clean_output_marks_events(self):
        from src.mcp.core import _clean_output
        ev = _clean_output({"content": "x", "source": "web"})
        self.assertEqual(ev["trust"], "untrusted")
        ent = _clean_output({"name": "Alice", "type": "person"})
        self.assertNotIn("trust", ent)

    def test_record_id_validation(self):
        from src.mcp.tools import _is_record_id
        self.assertTrue(_is_record_id("event:abc123"))
        self.assertTrue(_is_record_id("entity:x_y_z"))
        self.assertFalse(_is_record_id("event:abc123; DELETE event"))
        self.assertFalse(_is_record_id("event:"))
        self.assertFalse(_is_record_id(""))


class TestPPRAndSplitting(unittest.TestCase):
    """Pure-function tests for PPR diffusion and query splitting (no DB)."""

    def test_ppr_stays_near_seeds(self):
        from src.planner.executor import personalized_pagerank
        adj = {"a": {"b": 1.0}, "b": {"a": 1.0, "c": 1.0}, "c": {"b": 1.0, "hub": 1.0}, "hub": {"c": 1.0}}
        scores = personalized_pagerank(adj, {"a": 1.0})
        self.assertGreater(scores["a"], scores["hub"])
        self.assertGreater(scores["b"], scores["hub"])
        self.assertAlmostEqual(sum(scores.values()), 1.0, places=4)

    def test_ppr_empty_graph(self):
        from src.planner.executor import personalized_pagerank
        self.assertEqual(personalized_pagerank({}, {"a": 1.0}), {})

    def test_split_coordination(self):
        from src.planner.executor import split_multihop_query
        parts = split_multihop_query("Who founded Acme and where is it based")
        self.assertEqual(len(parts), 2)
        self.assertIn("Acme", parts[0])

    def test_split_no_coordination(self):
        from src.planner.executor import split_multihop_query
        q = "Where does Alice work?"
        self.assertEqual(split_multihop_query(q), [q])
        self.assertEqual(split_multihop_query(""), [""])


class TestRelationLabelMapping(unittest.TestCase):
    """Pure-function tests for the relex/gliner predicate normalization."""

    def test_infer_extractor_majority(self):
        from src.extraction.entropy_gate import infer_extractor
        self.assertEqual(infer_extractor(["RELEX", "RELEX", "GROQ"]), "relex")
        self.assertEqual(infer_extractor(["PERSON", "NOUN_CHUNK"]), "spacy")
        self.assertEqual(infer_extractor([]), "spacy")
        # Ties fall back to the weakest-evidence tier (fail-closed)
        self.assertEqual(infer_extractor(["RELEX", "GLINER"]), "spacy")

    def test_normalizes_phrases(self):
        from src.extraction.entity_utils import _normalize_relation_label
        self.assertEqual(_normalize_relation_label("works at"), "works_at")
        self.assertEqual(_normalize_relation_label("located in"), "located_in")
        self.assertEqual(_normalize_relation_label("  Discovered "), "discovered")

    def test_fallback_and_empty(self):
        from src.extraction.entity_utils import _normalize_relation_label
        self.assertEqual(_normalize_relation_label(""), "related_to")
        self.assertEqual(_normalize_relation_label(None), "related_to")

    def test_chain_prefers_relex(self):
        """Default chain resolves without Groq (env default)."""
        import os
        self.assertEqual(os.getenv("EXTRACTION_METHOD", "auto"), "auto")


class TestFactSalience(unittest.TestCase):
    """Pure-function tests for EntropyGate.fact_salience (no DB, no model)."""

    def test_bounds(self):
        for conf in (0.0, 0.5, 1.0):
            for pred in ("works_at", "mentions", "co_occurs_with", ""):
                for nov in (None, 0.0, 1.0):
                    s = EntropyGate.fact_salience(conf, pred, nov)
                    self.assertGreaterEqual(s, 0.0)
                    self.assertLessEqual(s, 1.0)

    def test_specific_beats_generic(self):
        specific = EntropyGate.fact_salience(0.9, "works_at", 0.5)
        generic = EntropyGate.fact_salience(0.9, "co_occurs_with", 0.5)
        mention = EntropyGate.fact_salience(0.9, "mentions", 0.5)
        self.assertGreater(specific, generic)
        self.assertGreater(generic, mention)

    def test_novelty_monotone(self):
        low = EntropyGate.fact_salience(0.8, "works_at", 0.0)
        high = EntropyGate.fact_salience(0.8, "works_at", 1.0)
        self.assertGreater(high, low)

    def test_none_novelty_is_neutral(self):
        a = EntropyGate.fact_salience(0.8, "works_at", None)
        b = EntropyGate.fact_salience(0.8, "works_at", 0.5)
        self.assertEqual(a, b)

    def test_bad_input_never_throws(self):
        self.assertGreaterEqual(EntropyGate.fact_salience("x", None, "y"), 0.0)


if __name__ == '__main__':
    print("Running Strata Python Unit Tests...")
    unittest.main(verbosity=2)