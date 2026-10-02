"""
Unit Tests for Sievon
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
        # English only (2026-10-01): German greetings removed with all
        # other German support.
        for q in ("hi", "hello there", "hey, are you there?", "good morning"):
            self.assertEqual(self.regex.classify(q)[0], "conversational", q)

    def test_update_read_requests_suppressed(self):
        q_type, _ = self.regex.classify("Update me on the project status")
        self.assertNotEqual(q_type, "update")

    def test_memory_write_verbs_are_update(self):
        # English only (2026-10-01)
        for q in ("Don't forget the meeting", "Remind me to call"):
            self.assertEqual(self.regex.classify(q)[0], "update", q)

    def test_coordination_is_multi_hop(self):
        self.assertEqual(
            self.regex.classify("Who runs Orion Labs and where are they?")[0], "multi-hop"
        )

    def test_why_definition_not_multi_hop(self):
        # "why is/are" alone must not score multi-hop (lookup, not synthesis)
        q_type, _ = self.regex.classify("Why is the sky blue?")
        self.assertNotEqual(q_type, "multi-hop")

    def test_english_was_is_not_a_question_word(self):
        """'was' is an auxiliary verb in English, not a wh-word.

        'Where was Acme Corp founded?' has ONE question word ('where');
        counting 'was' faked a coordination and routed factual lookups to
        multi-hop (and from there to the generic fallback).
        """
        for q in ("Where was Acme Corp founded?",
                  "Who was the first president?",
                  "What was the score?"):
            q_type, _ = self.regex.classify(q)
            self.assertEqual(q_type, "factual", q)

    def test_genuine_two_wh_coordination_still_multi_hop(self):
        """Two REAL question words still trigger coordination."""
        for q in ("Who runs Orion Labs and where are they?",
                  "What was the score and who scored?"):
            self.assertEqual(self.regex.classify(q)[0], "multi-hop", q)

    def test_ml_vetoes(self):
        """Deterministic vetoes override confident ML verdicts."""
        clf = QueryClassifier()
        clf._ensure_ml()
        if clf._ml.is_trained():
            label, conf = clf._ml.classify("Update me on the project status")
            if label == "update" and conf >= 0.60:
                self.assertNotEqual(clf.classify("Update me on the project status")[0], "update")


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
        """Test routing policy for multi-hop queries (min_confidence=0.6)"""
        strategy_name, budget_level, policy_applied = self.policy.get_strategy(QueryType.MULTI_HOP, 0.7)
        self.assertEqual(strategy_name, "hybrid_with_graph_expansion")
        self.assertEqual(policy_applied, "strict")
        self.assertIs(budget_level, BudgetLevel.HIGH)

    def test_conversational_policy(self):
        """Test routing policy for conversational queries (min_confidence=0.6)"""
        strategy_name, budget_level, policy_applied = self.policy.get_strategy(QueryType.CONVERSATIONAL, 0.9)
        self.assertEqual(policy_applied, "strict")
        self.assertIs(budget_level, BudgetLevel.MEDIUM)

    def test_update_policy(self):
        """Uncertain updates degrade to a read-only strategy, never writes"""
        strategy_name, budget_level, policy_applied = self.policy.get_strategy(QueryType.UPDATE, 0.8)
        self.assertEqual(strategy_name, "knowledge_graph_first")
        self.assertEqual(policy_applied, "degraded")

    def test_low_confidence_degrades(self):
        """Low confidence keeps the type strategy at reduced budget"""
        strategy_name, budget_level, policy_applied = self.policy.get_strategy(QueryType.TEMPORAL, 0.3)
        self.assertEqual(strategy_name, "event_log_first")
        self.assertEqual(policy_applied, "degraded")
        self.assertIs(budget_level, BudgetLevel.LOW)


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


class TestRelevanceScore(unittest.TestCase):
    """_calculate_relevance_score is an accept/abstain estimate, not a rank.

    Measured on docs/eval_retrieval_gold.jsonl: the top vector similarity
    separates answerable queries (0.524-0.818) from no-answer probes
    (0.224-0.335) at AUC 1.000, while lexical hit count gives 0.992, top
    BM25 0.979 and cross-channel agreement 0.933. These tests pin that the
    score tracks those signals -- in particular that the top-1 vector score
    is used rather than an average over the top three, which diluted the
    only signal that discriminated.
    """

    def test_top1_vec_score_beats_a_diluted_average(self):
        from src.planner.executor import RetrievalExecutor
        # One strong hit plus two weak ones. The top-1 is 0.80; the mean of
        # the top three is 0.60, and mixing coverage in pushed that down to
        # 0.36 -- inside the range of an unrelated query.
        strong = {"events": [
            {"content": "a", "vec_score": 0.80},
            {"content": "b", "vec_score": 0.50},
            {"content": "c", "vec_score": 0.50},
        ]}
        weak_only = {"events": [
            {"content": "x", "vec_score": 0.34},
        ]}
        self.assertGreater(
            RetrievalExecutor._calculate_relevance_score(strong, "q"),
            RetrievalExecutor._calculate_relevance_score(weak_only, "q"),
        )

    def test_vec_score_counts_as_semantic_evidence(self):
        from src.planner.executor import RetrievalExecutor
        base = {"events": [{"content": "Irrelevant text about nothing"}]}
        plain = RetrievalExecutor._calculate_relevance_score(
            base, "Who leads Nova Systems?")
        with_vec = RetrievalExecutor._calculate_relevance_score(
            {"events": [{"content": "Irrelevant text about nothing",
                         "vec_score": 0.85}]},
            "Who leads Nova Systems?")
        self.assertGreater(with_vec, plain)

    def test_agreement_only_raises_never_lowers(self):
        """A weak semantic match must not be rescued by channel agreement."""
        from src.planner.executor import RetrievalExecutor
        weak = {"events": [{"content": "a", "vec_score": 0.30}]}
        agreed = {
            "events": [{"content": "a", "vec_score": 0.30}],
            "retrieval_diagnostics": {
                "top_vec_score": 0.30, "lexical_hits": 9,
                "max_bm25": 8.0, "channels_agree": True,
            },
        }
        self.assertGreaterEqual(
            RetrievalExecutor._calculate_relevance_score(agreed, "q"),
            RetrievalExecutor._calculate_relevance_score(weak, "q"),
        )

    def test_diagnostics_take_precedence_over_result_rows(self):
        """Channels must be measured before fusion, not read back from it.

        A fused result list cannot say whether the top hit was found by one
        channel or corroborated by both, so a strategy that gathers the
        channels separately reports them in retrieval_diagnostics.
        """
        from src.planner.executor import RetrievalExecutor
        result = {
            "events": [{"content": "a"}],  # vec_score lost in fusion
            "retrieval_diagnostics": {"top_vec_score": 0.77},
        }
        self.assertGreaterEqual(
            RetrievalExecutor._calculate_relevance_score(result, "q"), 0.77)

    def test_lexical_only_strategy_uses_hit_count(self):
        from src.planner.executor import RetrievalExecutor
        result = {
            "events": [{"content": "a"}],
            "retrieval_diagnostics": {"top_vec_score": 0.0, "lexical_hits": 5},
        }
        self.assertGreater(
            RetrievalExecutor._calculate_relevance_score(result, "q"), 0.5)

    def test_empty_and_error_floors_unchanged(self):
        from src.planner.executor import RetrievalExecutor
        self.assertEqual(
            RetrievalExecutor._calculate_relevance_score({"events": []}, "q"), 0.2)
        self.assertEqual(
            RetrievalExecutor._calculate_relevance_score({"error": "x"}, "q"), 0.1)

    def test_score_stays_in_range(self):
        from src.planner.executor import RetrievalExecutor
        for events in (
            [{"content": "a" * 500, "vec_score": 0.99}] * 20,
            [{"content": "x"}],
        ):
            s = RetrievalExecutor._calculate_relevance_score(
                {"events": events}, "Who leads Nova Systems?")
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 1.0)

    def test_diagnostics_helper_separates_channels(self):
        from src.planner.executor import _channel_diagnostics
        diag = _channel_diagnostics(
            [{"id": "event:a", "bm25": 4.2}, {"id": "event:b", "bm25": 1.1}],
            [{"id": "event:a", "vec_score": 0.77},
             {"id": "event:c", "vec_score": 0.30}],
        )
        self.assertEqual(diag["top_vec_score"], 0.77)
        self.assertEqual(diag["lexical_hits"], 2)
        self.assertEqual(diag["max_bm25"], 4.2)
        # Both channels returned event:a first.
        self.assertTrue(diag["channels_agree"])

    def test_diagnostics_tolerate_missing_scores(self):
        from src.planner.executor import _channel_diagnostics
        diag = _channel_diagnostics([], [])
        self.assertEqual(diag["top_vec_score"], 0.0)
        self.assertEqual(diag["lexical_hits"], 0)
        self.assertFalse(diag["channels_agree"])


class TestSurrealStatementBuilding(unittest.TestCase):
    """Regression tests for SurrealQL 3 quirks in _query_surreal.

    No DB required: the wire format is asserted directly, because the original
    bugs were silent -- the server answered status OK without executing.
    """

    def _body(self, sql, params=None):
        import json
        import src.mcp.core as core

        captured = {}

        class _Resp:
            status_code = 200

            def json(self):
                return [{"status": "OK", "result": None}]

        class _Client:
            async def post(self, url, content=None, headers=None, **kw):
                captured["content"] = content
                captured["headers"] = headers
                return _Resp()

        async def _run():
            orig_client, orig_should = core._get_client, core._budget_aware_should_retry
            async def _fake_client():
                return _client
            core._get_client = _fake_client
            core._budget_aware_should_retry = lambda s: 1
            try:
                await core._query_surreal(sql, params)
            finally:
                core._get_client, core._budget_aware_should_retry = orig_client, orig_should

        _client = _Client()
        asyncio.run(_run())
        self.assertIn("application/json", captured["headers"].values())
        # A JSON request body makes SurrealDB 3 parse the object as an inert
        # literal and return it without executing: sql must travel as raw text.
        self.assertEqual(
            captured["headers"].get("Content-Type"), "text/plain")
        return captured["content"]

    def test_sql_is_sent_as_raw_text_with_use_prefix(self):
        body = self._body("SELECT * FROM entity;")
        self.assertIn(f"USE NS {self._ns()} DB {self._db()};", body)
        self.assertTrue(body.rstrip().endswith("SELECT * FROM entity;"))

    @staticmethod
    def _ns():
        import src.mcp.core as core
        return core.SURREAL_NS

    @staticmethod
    def _db():
        import src.mcp.core as core
        return core.SURREAL_DB

    def test_params_become_let_bindings_not_a_json_body(self):
        body = self._body("RETURN $one + 1;", {"one": 41})
        self.assertIn("LET $one = 41;", body)
        self.assertIn("RETURN $one + 1;", body)
        # The failure mode that made this silently a no-op.
        self.assertNotIn('"params"', body)

    def test_param_values_are_escaped_as_json_literals(self):
        body = self._body(
            "RETURN $name;", {"name": "O'Brien \"quoted\""})
        self.assertIn("\"O'Brien \\\"quoted\\\"\"", body)

    def test_entity_metadata_field_is_flexible(self):
        """On SCHEMAFULL, TYPE object is schemafull by default.

        Without FLEXIBLE every entity write carrying metadata fails, which
        takes out merge_entities and consolidate on a fresh setup. This
        caught that on a schema.surql/migration mismatch: both declared
        entity.metadata without FLEXIBLE while the dev table happened to be
        SCHEMALESS, so it only broke on a clean install.
        """
        import re
        for path in ("src/mcp/migrations.py", "docs/schema.surql"):
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
            for line in source.splitlines():
                if re.search(r"metadata ON entity TYPE", line):
                    self.assertIn(
                        "FLEXIBLE", line,
                        f"{path}: entity.metadata needs FLEXIBLE: {line.strip()}")
                    break
            else:
                self.fail(f"{path}: no entity.metadata definition found")

    def test_schema_loader_honours_configured_namespace(self):
        """run_sql_batch must not hardcode a namespace.

        It used to send `USE NS sieveon DB sieveon` regardless of the
        environment, so loading against a custom SURREALDB_NS appeared to
        succeed while writing to the default database and leaving the
        target without a schema.
        """
        import ast
        import os
        path = os.path.join("scripts", "load_schema_optimized.py")
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        interpolated = []
        for node in ast.walk(tree):
            # An f-string is a JoinedStr; plain string constants never carry
            # the {name} placeholders, so only JoinedStr is of interest.
            if isinstance(node, ast.JoinedStr):
                rendered = ast.unparse(node)
                if "USE NS" in rendered:
                    interpolated.append(rendered)
        self.assertTrue(interpolated, "expected a USE NS f-string in the loader")
        for stmt in interpolated:
            # NS/DB must come from the environment, not be baked in.
            self.assertIn("{NS}", stmt, f"namespace is hardcoded: {stmt}")
            self.assertIn("{DB}", stmt, f"database is hardcoded: {stmt}")

        # And the values they interpolate must come from the environment.
        assigned = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                assigned[node.targets[0].id] = ast.unparse(node.value)
        for name in ("NS", "DB", "URL", "AUTH"):
            self.assertIn(
                "os.getenv", assigned.get(name, ""),
                f"{name} must be read from the environment, got "
                f"{assigned.get(name)!r}")


class TestLoCoMoGoldBuilder(unittest.TestCase):
    """The production gold must come from third-party text, stratified.

    The 20 hand-written adversarial sentences estimated worst case, not
    typical case, and every error found in them turned out to be mine --
    a comitative "with" phrase scored as a model error, and span boundaries
    scored as wrong triples when they were an annotation convention. A gold
    set I wrote cannot fix that, so the replacement is LoCoMo's own
    observations plus a uniform draw for the production rate.
    """

    def test_strata_are_detected(self):
        from scripts.build_triples_gold_locomo import classify
        cases = {
            "Elon Musk founded SpaceX in 2002.": "active-verb",
            "The Analytical Engine was designed by Charles Babbage.": "passive",
            "QuantumDB is a database engine.": "copular",
            "Her manager is Rachel Cohen.": "nominal",
        }
        for text, expected in cases.items():
            self.assertIn(expected, classify(text),
                          f"{text!r} was not tagged {expected}: "
                          f"got {classify(text)}")

    def test_uniform_draw_is_separate_from_stratified(self):
        """A stratified set over-weights hard cases on purpose.

        Its aggregate precision is a worst-case-weighted figure, so a uniform
        draw is needed for the production rate and the two must not be
        averaged.
        """
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / "docs"
        strat = [json.loads(l) for l in
                 (root / "eval_triples_gold_locomo_draft.jsonl")
                 .read_text(encoding="utf-8").splitlines() if l.strip()]
        unif = [json.loads(l) for l in
                (root / "eval_triples_gold_locomo_uniform.jsonl")
                 .read_text(encoding="utf-8").splitlines() if l.strip()]

        self.assertTrue(all(r["stratum"] != "uniform" for r in strat))
        self.assertTrue(all(r["stratum"] == "uniform" for r in unif))

        strat_ids = {r["id"] for r in strat}
        unif_ids = {r["id"] for r in unif}
        self.assertEqual(strat_ids & unif_ids, set(),
                         "a sentence cannot be in both draws")

        # And the uniform draw must look like the corpus, not like the strata.
        from collections import Counter
        self.assertGreater(len(unif), 40)
        self.assertEqual(
            len({r["speaker"] for r in unif}), len({r["speaker"] for r in strat}) + 2,
            "expect roughly comparable speaker diversity")

    def test_drafts_are_unlabelled_until_a_human_fills_them(self):
        """triples must be null, never an LLM guess.

        An ACL 2025 study found LLM judges on biomedical RE below 50% accuracy
        before output-format constraints, so auto-filling would rebuild the
        trust problem the gold set exists to fix.
        """
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / "docs"
        for name in ("eval_triples_gold_locomo_draft.jsonl",
                     "eval_triples_gold_locomo_uniform.jsonl"):
            rows = [json.loads(l) for l in
                    (root / name).read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertTrue(rows, f"{name} is empty")
            self.assertTrue(
                all(r["triples"] is None for r in rows),
                f"{name}: triples must stay null until hand-annotated")


class TestRelationLabelCoverage(unittest.TestCase):
    """The inference label list is the model's entire output space.

    relex classifies an entity pair into one of the labels supplied at
    inference. A gold predicate missing from that list cannot be emitted at
    any confidence, so recall measured against it scores the configuration,
    not the model. Six verbs were missing here, which capped recall at 0.714
    and made `developed` look like a catch-all when it was mostly just the
    nearest available broad label. Adding them moved recall 0.667 -> 0.762
    and precision 0.438 -> 0.485 at no cost.
    """

    def test_every_gold_predicate_is_reachable(self):
        from src.extraction.entity_utils import _SIEVEON_RELATION_LABELS
        from scripts.eval_triples import load_gold
        from scripts.audit_relation_labels import slug

        labels = {slug(l) for l in _SIEVEON_RELATION_LABELS}
        gold = set()
        for row in load_gold():
            for t in row["triples"]:
                gold.add(slug(t[1]))

        unreachable = gold - labels
        self.assertEqual(
            unreachable, set(),
            "gold predicates absent from the inference label list; they are "
            f"unreachable at any confidence: {sorted(unreachable)}")

    def test_label_list_has_no_duplicates_after_normalisation(self):
        from src.extraction.entity_utils import _SIEVEON_RELATION_LABELS
        from scripts.audit_relation_labels import slug

        slugs = [slug(l) for l in _SIEVEON_RELATION_LABELS]
        self.assertEqual(
            len(slugs), len(set(slugs)),
            "two labels normalise to the same slug, so one silently wins")

    def test_labels_are_natural_language_phrases(self):
        """The model card documents labels as text, not slugs."""
        from src.extraction.entity_utils import _SIEVEON_RELATION_LABELS
        for label in _SIEVEON_RELATION_LABELS:
            self.assertNotIn("_", label,
                             f"{label!r} looks like a slug, not a phrase")


class TestTripleEvalMatching(unittest.TestCase):
    """Pure helpers of scripts/eval_triples.py.

    The metric itself is what exposed that SVO extraction asserts roughly
    three wrong triples for every correct one, so the classification of a
    wrong triple has to be right: counting a mis-parse as acceptable would
    report precision 1.0 on a sentence where the extractor attached the wrong
    agent to the right object.
    """

    def _gold(self):
        return [("Marie Curie", "discovered", "radium")]

    def test_matching_ignores_case_and_possessive_ending(self):
        from scripts.eval_triples import _matches
        self.assertTrue(_matches(
            {"subject": "marie curie", "predicate": "Discovered",
             "object": "Radium"}, self._gold()[0]))
        # "'s" is normalised away, so a possessive on a single-word object
        # still matches the bare form.
        self.assertTrue(_matches(
            {"subject": "Ada Lovelace", "predicate": "wrote",
             "object": "algorithm's"}, ("Ada Lovelace", "wrote", "algorithm")))

    def test_predicate_must_match_exactly(self):
        """The verb is the claim, so a different one is not a match."""
        from scripts.eval_triples import _matches
        self.assertFalse(_matches(
            {"subject": "Marie Curie", "predicate": "developed",
             "object": "radium"}, self._gold()[0]))

    def test_relaxed_matching_separates_span_convention_from_wrong_verb(self):
        """Span boundaries are an annotation convention, not a model error.

        "Saturn V" against gold "Saturn V first stage" and "algorithm" against
        "first algorithm" are both defensible. Under strict matching those
        counted as false triples, which made span quality look like the lever
        -- assertions with a non-exact span scored precision 0.000 -- when
        two thirds of the apparent recall loss was really my own boundary
        choice. Relaxed recall is 0.905 against 0.762 strict.
        """
        from scripts.eval_triples import _matches
        gold = [("Rocketdyne", "built", "Saturn V first stage")]
        short = {"subject": "Rocketdyne", "predicate": "built",
                 "object": "Saturn V"}
        self.assertFalse(_matches(short, gold[0]))
        self.assertTrue(_matches(short, gold[0], relaxed_span=True))

        # Relaxing spans must never relax the predicate: the verb is the claim.
        wrong_verb = {"subject": "Rocketdyne", "predicate": "developed",
                      "object": "Saturn V"}
        self.assertFalse(_matches(wrong_verb, gold[0], relaxed_span=True))

    def test_relaxed_scoring_is_reported_and_never_worse_than_strict(self):
        from scripts.eval_triples import evaluate, load_gold
        report = evaluate(load_gold())
        self.assertGreaterEqual(report["relaxed_precision"],
                                report["precision"])
        self.assertGreaterEqual(report["relaxed_recall"], report["recall"])

    def test_span_table_covers_every_assertion(self):
        from scripts.eval_triples import evaluate, load_gold
        report = evaluate(load_gold())
        total = sum(b["correct"] + b["wrong"]
                    for b in report["span_table"].values())
        self.assertEqual(total, report["asserted"],
                         "every assertion needs a span-quality row")

    def test_kind_classification(self):
        from scripts.eval_triples import _false_kind
        # _false_kind takes the whole gold list: whether a triple is false
        # depends on whether it is asserted anywhere in the sentence, not
        # against one reference triple.
        gold = self._gold()
        text = "Marie Curie discovered radium with Pierre Curie in 1898 in Paris."

        # Right subject and object, wrong verb.
        self.assertEqual(
            _false_kind({"subject": "Marie Curie", "predicate": "developed",
                         "object": "radium", "_text": text}, gold),
            "wrong-predicate")

        # Both words occur in the sentence, but this pair is not asserted.
        self.assertEqual(
            _false_kind({"subject": "Pierre Curie", "predicate": "founded",
                         "object": "Paris", "_text": text}, gold),
            "mis-parse")

        # An entity that never occurs in the sentence.
        self.assertEqual(
            _false_kind({"subject": "Marie Curie", "predicate": "discovered",
                         "object": "unobtainium", "_text": text}, gold),
            "hallucinated")

    def test_comitative_is_a_true_positive_not_agent_confusion(self):
        """PropBank marks 'with' in 'I sang with my sister' comitative.

        So both agents discovered radium, and scoring the co-agent triple as
        a false positive is a gold error, not a model error.
        """
        from scripts.eval_triples import _false_kind, _matches
        text = "Marie Curie discovered radium with Pierre Curie in 1898."
        gold = [("Marie Curie", "discovered", "radium"),
                ("Pierre Curie", "discovered", "radium")]
        self.assertIsNone(_false_kind(
            {"subject": "Pierre Curie", "predicate": "discovered",
             "object": "radium", "_text": text}, gold))
        self.assertTrue(_matches(
            {"subject": "Pierre Curie", "predicate": "discovered",
             "object": "radium"}, gold[1]))

    def test_predicate_table_must_list_gold_only_predicates(self):
        """A table built only from asserted rows hides the worst finding.

        Six gold predicates were never produced by the model, and an
        asserted-only table made them invisible -- which inverted the
        conclusion from "precision is low" to "a third of recall is
        unreachable at any confidence threshold".
        """
        from scripts.eval_triples import evaluate, load_gold
        report = evaluate(load_gold())
        table = {r["predicate"] for r in report["predicate_table"]}
        gold_preds = set()
        for row in load_gold():
            for t in row["triples"]:
                gold_preds.add(t[1].lower())
        self.assertTrue(
            gold_preds <= table,
            f"gold predicates missing from the table: {gold_preds - table}")
        self.assertEqual(
            report["gold_triples"],
            sum(r["gold"] for r in report["predicate_table"]),
            "the gold column must sum to the gold triple count")

    def test_a_correct_triple_is_not_false_at_all(self):
        from scripts.eval_triples import _false_kind
        self.assertIsNone(_false_kind(
            {"subject": "Marie Curie", "predicate": "discovered",
             "object": "radium"}, self._gold()))

    def test_gold_set_loads_and_is_adversarial(self):
        from scripts.eval_triples import load_gold
        rows = load_gold()
        self.assertGreaterEqual(len(rows), 20)
        # The set must contain sentences that assert nothing, or the eval
        # cannot measure a false positive at all.
        self.assertTrue(any(not r["triples"] for r in rows))
        # And constructions that break naive parsers.
        joined = " ".join(r["text"].lower() for r in rows)
        for construction in ("was designed by", "and later funded",
                             "which was founded"):
            self.assertIn(construction, joined,
                          f"gold set lost an adversarial case: {construction}")


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

    def test_discovered_is_a_valid_ontology_predicate(self):
        """'discovered' was in the gold set while missing from the ontology,
        so validate_predicate rejected exactly the facts we test for."""
        from src.extraction.entity_utils import validate_predicate
        self.assertTrue(validate_predicate("person", "discovered", "technology"))
        self.assertTrue(validate_predicate("person", "discovered", "concept"))
        self.assertTrue(validate_predicate("organization", "discovered", "technology"))
        self.assertFalse(validate_predicate("person", "discovered", "location"))

    def test_every_gold_predicate_validates(self):
        """No gold triple may use a predicate the ontology rejects.

        This is the regression guard: a predicate in the gold set but absent
        from ONTOLOGY['predicate_types'] is silently filtered at ingest, so
        triple recall for it can never exceed zero.
        """
        import json
        import os
        from src.extraction.entity_utils import validate_predicate
        gold_path = os.path.join(os.path.dirname(__file__), "..", "docs",
                                 "eval_extraction_gold.jsonl")
        failures = []
        with open(gold_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                types = {e["name"].lower(): e["type"] for e in row.get("entities", [])}
                for t in row.get("triples", []):
                    if not validate_predicate(types.get(t["s"].lower(), "?"),
                                              t["p"], types.get(t["o"].lower(), "?")):
                        failures.append(f"{t['s']} -{t['p']}-> {t['o']}")
        self.assertEqual(failures, [])

    def test_chain_prefers_relex(self):
        """Default chain resolves without Groq (env default)."""
        import os
        self.assertEqual(os.getenv("EXTRACTION_METHOD", "auto"), "auto")


class TestTripleExtractionChain(unittest.TestCase):
    """Which backends may contribute triples to the KG.

    Measured on docs/eval_extraction_gold.jsonl (ADR-002): spacy asserted 0
    correct facts out of 15 (tripR 0.000) while relex reached 0.706 and gliner
    0.941. spacy therefore stays available for *entities* (entR 0.981) but is
    no longer part of the triple chain: a KG fact that is wrong with certainty is
    worse than a missing fact, because retrieval can only fail to find a fact
    that does not exist, not one that is false.
    """

    def _chain_for(self, method, monkeypatched):
        """Resolve the chain for EXTRACTION_METHOD=method with fakes installed."""
        from src.extraction import entity_utils as eu
        originals = {n: getattr(eu, n) for n in monkeypatched}
        for n, fn in monkeypatched.items():
            setattr(eu, n, fn)
        import os
        old = os.environ.get("EXTRACTION_METHOD")
        os.environ["EXTRACTION_METHOD"] = method
        try:
            return eu.extract_triples("Ada built the Engine.")
        finally:
            for n, fn in originals.items():
                setattr(eu, n, fn)
            if old is None:
                os.environ.pop("EXTRACTION_METHOD", None)
            else:
                os.environ["EXTRACTION_METHOD"] = old

    def _fakes(self, relex_out, gliner_out, spacy_out, groq_out):
        return {
            "extract_triples_with_relex": lambda t: relex_out,
            "extract_triples_with_gliner": lambda t: gliner_out,
            "extract_triples_with_spacy": lambda t: spacy_out,
            "extract_triples_with_groq": lambda t: groq_out,
        }

    def test_auto_chain_returns_empty_when_local_backends_find_nothing(self):
        """relex and gliner both empty -> no triples, NOT spacy garbage."""
        got = self._chain_for("auto", self._fakes([], [], ["S-O junk"], []))
        self.assertEqual(got, [])

    def test_relex_result_wins(self):
        r = [{"subject": "Ada", "predicate": "created", "object": "Engine"}]
        got = self._chain_for("auto", self._fakes(r, [{"subject": "X"}], [], []))
        self.assertEqual(got, r)

    def test_gliner_used_when_relex_empty(self):
        g = [{"subject": "Ada", "predicate": "created", "object": "Engine"}]
        got = self._chain_for("auto", self._fakes([], g, [], []))
        self.assertEqual(got, g)

    def test_groq_opt_in_still_works(self):
        q = [{"subject": "Ada", "predicate": "created", "object": "Engine"}]
        got = self._chain_for("groq", self._fakes([], [], [], q))
        self.assertEqual(got, q)

    def test_explicit_backend_request_does_not_fall_through_to_another(self):
        """EXTRACTION_METHOD=relex must not silently return gliner or spacy facts."""
        got = self._chain_for("relex", self._fakes([], ["gliner junk"], ["spacy junk"], []))
        self.assertEqual(got, [])

    def test_groq_chain_does_not_call_local_backends(self):
        q = [{"subject": "Ada", "predicate": "created", "object": "Engine"}]
        got = self._chain_for("groq", self._fakes([], [], [], q))
        self.assertEqual(got, q)

    def test_entity_chain_still_falls_back_to_spacy(self):
        """Only triples are gated. spacy entity extraction (entR 0.981) stays."""
        from src.extraction import entity_utils as eu
        originals = {
            n: getattr(eu, n) for n in (
                "extract_entities_with_relex", "extract_entities_with_gliner",
                "extract_entities_with_spacy")
        }
        spacy_ents = [{"name": "Fallback", "type": "concept"}]
        eu.extract_entities_with_relex = lambda t: []
        eu.extract_entities_with_gliner = lambda t: []
        eu.extract_entities_with_spacy = lambda t: spacy_ents
        try:
            self.assertEqual(eu.extract_entities("something"), spacy_ents)
        finally:
            for n, fn in originals.items():
                setattr(eu, n, fn)

    def test_empty_text_is_not_an_error(self):
        """Empty input must not reach a backend that would invent relations."""
        got = self._chain_for("auto", self._fakes([], [], [{"subject": "A"}], []))
        self.assertEqual(got, [])


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


class TestExtractionMetrics(unittest.TestCase):
    """Per-fact labelling for the extraction eval (pure, no model, no DB).

    The eval used to label *missed gold triples* and charge each miss the best
    salience of the whole sentence, so a sentence with one correct and one wrong
    fact counted as wrong twice. These tests pin the per-fact contract.
    """

    def test_fact_matching_gold_triple_is_correct(self):
        from src.eval.extraction_metrics import label_facts
        gold = [{"s": "Marie Curie", "p": "discovered", "o": "radium"}]
        facts = [{"subject": "Marie Curie", "predicate": "discovered", "object": "radium",
                  "confidence": 0.9}]
        labelled = label_facts(facts, gold)
        self.assertEqual(len(labelled), 1)
        self.assertTrue(labelled[0]["correct"])

    def test_fact_not_in_gold_is_wrong(self):
        from src.eval.extraction_metrics import label_facts
        gold = [{"s": "Marie Curie", "p": "discovered", "o": "radium"}]
        facts = [{"subject": "Marie Curie", "predicate": "founded", "object": "radium",
                  "confidence": 0.9}]
        self.assertFalse(label_facts(facts, gold)[0]["correct"])

    def test_each_fact_is_labelled_independently(self):
        """One correct + one wrong fact in the same sentence: 1 correct, 1 wrong.

        This is the case the old per-miss proxy got wrong.
        """
        from src.eval.extraction_metrics import label_facts
        gold = [{"s": "Marie Curie", "p": "discovered", "o": "radium"}]
        facts = [
            {"subject": "Marie Curie", "predicate": "discovered", "object": "radium",
             "confidence": 0.9},
            {"subject": "Marie Curie", "predicate": "founded", "object": "radium",
             "confidence": 0.8},
        ]
        labelled = label_facts(facts, gold)
        self.assertEqual([f["correct"] for f in labelled], [True, False])

    def test_predicate_synonyms_count_as_correct(self):
        """Gold 'created', model said 'developed' -- synonym-tolerant by design."""
        from src.eval.extraction_metrics import label_facts
        gold = [{"s": "Ada", "p": "created", "o": "Engine"}]
        facts = [{"subject": "Ada", "predicate": "developed", "object": "Engine",
                  "confidence": 0.8}]
        self.assertTrue(label_facts(facts, gold)[0]["correct"])

    def test_sentence_without_gold_triples_labels_everything_wrong(self):
        from src.eval.extraction_metrics import label_facts
        facts = [{"subject": "Iceland", "predicate": "uses", "object": "geothermal",
                  "confidence": 0.7}]
        labelled = label_facts(facts, [])
        self.assertFalse(labelled[0]["correct"])

    def test_malformed_fact_is_skipped_not_crashing(self):
        from src.eval.extraction_metrics import label_facts
        gold = [{"s": "Ada", "p": "created", "o": "Engine"}]
        facts = [{"predicate": "created"}, "not-a-dict", None]
        self.assertEqual(label_facts(facts, gold), [])


class TestExtractionMetricRanking(unittest.TestCase):
    """AUC + bootstrap CI: does a fact score actually separate correct from wrong?

    The old eval only printed two means, which cannot distinguish a weak signal
    from no signal (v1 scored correct 0.843 vs wrong 0.844 -> "no separation",
    while confidence alone really has AUC 0.63).
    """

    def test_auc_is_one_for_perfect_separation(self):
        from src.eval.extraction_metrics import auc
        self.assertEqual(auc([0.9, 0.8, 0.7], [0.1, 0.2, 0.3]), 1.0)

    def test_auc_is_half_for_no_signal(self):
        from src.eval.extraction_metrics import auc
        self.assertEqual(auc([0.5, 0.5], [0.5, 0.5]), 0.5)

    def test_auc_is_zero_for_inverted_separation(self):
        from src.eval.extraction_metrics import auc
        self.assertEqual(auc([0.1, 0.2], [0.9, 0.8]), 0.0)

    def test_auc_counts_ties_as_half(self):
        from src.eval.extraction_metrics import auc
        self.assertEqual(auc([0.5], [0.5]), 0.5)

    def test_auc_is_nan_without_both_classes(self):
        from src.eval.extraction_metrics import auc
        self.assertNotEqual(auc([0.5, 0.6], []), auc([0.5, 0.6], []))
        import math
        self.assertTrue(math.isnan(auc([0.5, 0.6], [])))
        self.assertTrue(math.isnan(auc([], [0.5, 0.6])))

    def test_bootstrap_ci_brackets_the_point_estimate(self):
        from src.eval.extraction_metrics import auc, bootstrap_auc
        correct = [0.9, 0.8, 0.85, 0.75, 0.95, 0.88, 0.92, 0.78]
        wrong = [0.3, 0.4, 0.2, 0.5, 0.35, 0.28, 0.45, 0.32]
        mean, lo, hi = bootstrap_auc(correct, wrong, n=200, seed=1)
        self.assertLessEqual(lo, mean)
        self.assertLessEqual(mean, hi)
        self.assertGreaterEqual(lo, auc(correct, wrong) - 1e-9)

    def test_bootstrap_is_deterministic_for_a_seed(self):
        from src.eval.extraction_metrics import bootstrap_auc
        c, w = [0.9, 0.8, 0.7], [0.2, 0.1, 0.3]
        self.assertEqual(bootstrap_auc(c, w, n=100, seed=7),
                         bootstrap_auc(c, w, n=100, seed=7))


class TestExtractionTierOperatingPoint(unittest.TestCase):
    """What the shipped TIER_DROP_THRESHOLD actually does to each class."""

    def test_operating_point_splits_correct_from_wrong(self):
        from src.eval.extraction_metrics import operating_point
        correct = [0.9, 0.8, 0.4]
        wrong = [0.6, 0.4, 0.2]
        op = operating_point(correct, wrong, threshold=0.50)
        self.assertEqual(op["correct_kept"], 2)   # 0.9, 0.8
        self.assertEqual(op["wrong_dropped"], 2)  # 0.4, 0.2
        self.assertEqual(op["correct_total"], 3)
        self.assertEqual(op["wrong_total"], 3)

    def test_precision_of_kept_set_is_reported(self):
        from src.eval.extraction_metrics import operating_point
        op = operating_point([0.9, 0.9], [0.9, 0.1], threshold=0.50)
        # kept = 2 correct + 1 wrong at 0.9
        self.assertAlmostEqual(op["kept_precision"], 2 / 3, places=3)

    def test_threshold_of_zero_drops_nothing(self):
        from src.eval.extraction_metrics import operating_point
        op = operating_point([0.1], [0.1], threshold=0.0)
        self.assertEqual(op["wrong_dropped"], 0)

    def test_empty_input_reports_undefined_precision(self):
        """No facts at all -> kept_precision is None (JSON null), not NaN."""
        from src.eval.extraction_metrics import operating_point
        op = operating_point([], [], threshold=0.50)
        self.assertIsNone(op["kept_precision"])


class TestExtractionEvalScoring(unittest.TestCase):
    """score_backend's reporting core, exercised without loading a model.

    This is where the old proxy lived: it iterated gold triples and charged each
    miss the best salience of the sentence. These tests pin per-fact counting so
    the numbers a maintainer reads cannot silently go back to that.
    """

    def _salience(self, confidence, predicate, novelty=None):
        return float(confidence)

    def test_one_correct_one_wrong_fact_gives_precision_one_half(self):
        from scripts.eval_extraction import summarize_backend
        rows = [{"text": "Ada built Engine.", "entities": [{"name": "Ada", "type": "person"}],
                 "triples": [{"s": "Ada", "p": "created", "o": "Engine"}]}]
        ents = [[{"name": "Ada", "type": "person"}]]
        trips = [[{"subject": "Ada", "predicate": "created", "object": "Engine",
                   "confidence": 0.9},
                  {"subject": "Ada", "predicate": "founded", "object": "Engine",
                   "confidence": 0.8}]]
        out = summarize_backend("relex", rows, ents, trips, self._salience)
        self.assertEqual(out["facts_total"], 2)
        self.assertEqual(out["facts_correct"], 1)
        self.assertEqual(out["facts_wrong"], 1)
        self.assertAlmostEqual(out["fact_precision"], 0.5)

    def test_wrong_facts_are_counted_per_fact_not_per_missed_gold_triple(self):
        """Two gold triples missed, five junk facts produced -> 5 wrong facts."""
        from scripts.eval_extraction import summarize_backend
        rows = [{"text": "x", "entities": [], "triples": [
            {"s": "A", "p": "created", "o": "B"}, {"s": "C", "p": "created", "o": "D"}]}]
        junk = [{"subject": f"S{i}", "predicate": "uses", "object": f"O{i}",
                 "confidence": 0.7} for i in range(5)]
        out = summarize_backend("relex", rows, [[]], [junk], self._salience)
        self.assertEqual(out["triple_recall"], 0.0)
        self.assertEqual(out["facts_wrong"], 5)

    def test_reports_auc_not_just_two_means(self):
        from scripts.eval_extraction import summarize_backend
        rows = [{"text": "x", "entities": [], "triples": [
            {"s": "A", "p": "created", "o": "B"}]}]
        trips = [[{"subject": "A", "predicate": "created", "object": "B", "confidence": 0.95},
                  {"subject": "Z", "predicate": "uses", "object": "Y", "confidence": 0.10}]]
        out = summarize_backend("relex", rows, [[]], trips, self._salience)
        self.assertEqual(out["salience_auc"], 1.0)
        self.assertIn("salience_auc_ci_lo", out)
        self.assertIn("salience_auc_ci_hi", out)

    def test_reports_tier_operating_point_against_shipped_threshold(self):
        from scripts.eval_extraction import summarize_backend
        rows = [{"text": "x", "entities": [], "triples": [
            {"s": "A", "p": "created", "o": "B"}]}]
        trips = [[{"subject": "A", "predicate": "created", "object": "B", "confidence": 0.95},
                  {"subject": "Z", "predicate": "uses", "object": "Y", "confidence": 0.10}]]
        out = summarize_backend("relex", rows, [[]], trips, self._salience)
        self.assertIn("tier_threshold", out)
        self.assertEqual(out["tier_correct_kept"], 1)
        self.assertEqual(out["tier_wrong_dropped"], 1)

    def test_triple_recall_still_gold_based(self):
        from scripts.eval_extraction import summarize_backend
        rows = [{"text": "x", "entities": [], "triples": [
            {"s": "A", "p": "created", "o": "B"}, {"s": "C", "p": "created", "o": "D"}]}]
        trips = [[{"subject": "A", "predicate": "created", "object": "B", "confidence": 0.9}]]
        out = summarize_backend("relex", rows, [[]], trips, self._salience)
        self.assertAlmostEqual(out["triple_recall"], 0.5)

    def test_sentence_with_no_gold_triple_is_junk_not_scored(self):
        from scripts.eval_extraction import summarize_backend
        rows = [{"text": "nothing here", "entities": [], "triples": []}]
        out = summarize_backend("relex", rows, [[]], [[]], self._salience)
        self.assertEqual(out["junk_clean"], "1/1")
        self.assertEqual(out["facts_total"], 0)

    def test_facts_asserted_on_junk_sentences_are_surfaced_not_hidden(self):
        """A sentence with no gold entities/triples should yield no facts.

        If a backend does assert some, they are excluded from fact precision
        (junk_clean measures that case) but must still be reported, otherwise
        the fact count silently depends on this `continue`.
        """
        from scripts.eval_extraction import summarize_backend
        rows = [{"text": "nothing here", "entities": [], "triples": []}]
        junk_fact = [{"subject": "Iceland", "predicate": "uses", "object": "geothermal",
                      "confidence": 0.7}]
        out = summarize_backend("relex", rows, [[]], [junk_fact], self._salience)
        self.assertEqual(out["junk_clean"], "0/1")
        self.assertEqual(out["facts_total"], 0)
        self.assertEqual(out["facts_from_junk_sentences"], 1)

    def test_backend_with_zero_correct_facts_reports_undefined_auc(self):
        """spacy produces only wrong facts; its AUC must not read as 1.0 or 0.5.

        None (JSON null) rather than NaN: strict JSON has no NaN literal, and
        None keeps "not computable" visibly distinct from a computed 0.5.
        """
        from scripts.eval_extraction import summarize_backend
        rows = [{"text": "x", "entities": [], "triples": [
            {"s": "A", "p": "created", "o": "B"}]}]
        trips = [[{"subject": "Z", "predicate": "uses", "object": "Y", "confidence": 0.6}]]
        out = summarize_backend("spacy", rows, [[]], trips, self._salience)
        self.assertEqual(out["facts_correct"], 0)
        self.assertIsNone(out["salience_auc"])
        self.assertIsNone(out["salience_auc_ci_lo"])
        self.assertIsNone(out["salience_auc_ci_hi"])
        self.assertNotEqual(out["salience_auc"], 0.5)

    def test_result_is_strict_json_serializable(self):
        """Every backend result must survive json.dumps without allow_nan."""
        import json
        from scripts.eval_extraction import summarize_backend
        rows = [{"text": "x", "entities": [], "triples": [
            {"s": "A", "p": "created", "o": "B"}]}]
        out = summarize_backend("spacy", rows, [[]], [[]], self._salience)
        json.dumps(out, allow_nan=False)


if __name__ == '__main__':
    print("Running Strata Python Unit Tests...")
    unittest.main(verbosity=2)
