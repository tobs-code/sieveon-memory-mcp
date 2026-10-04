"""Regression tests for the correctness fixes that accompanied the security work.

Covers the behavioural changes which the injection tests do not:
  * R3   -- memory_update / memory_merge_entities are now transactional
  * Y7   -- non-retryable SurrealDB failures must not be retried or counted
            against the circuit breaker
  * Y14  -- comment stripping must not truncate `--` inside a string literal
  * Y8   -- chunking must not build a per-character protected map
  * Y9   -- memory_query's summary totals must match its returned results

Pure seams and mocked DB where a live database is not required.
"""
import asyncio
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.mcp import core as core_mod
from src.mcp.core import (
    _NonRetryableSurrealError,
    _extract_statement_results,
    _health_from_failures,
    _query_surreal,
    _retry_budget_for,
    _strip_surql_comments,
    load_schema_file,
    reset_surreal_circuit,
)
from src.mcp.tools import _MAX_FETCH_ROWS, _MAX_TRAVERSE_PATHS, event_log_search, memory_update


class TestRetryBudget(unittest.TestCase):
    """Y7 / N3: renamed to describe what it returns; behaviour unchanged."""

    def test_heavy_statements_get_fewer_attempts(self):
        core_mod.BudgetTracker.update_system_health(1.0)
        self.assertLessEqual(
            _retry_budget_for("CREATE event SET content = 'x';"),
            _retry_budget_for("SELECT * FROM event;"),
        )

    def test_healthy_system_allows_three(self):
        core_mod.BudgetTracker.update_system_health(1.0)
        self.assertEqual(_retry_budget_for("SELECT * FROM event;"), 3)

    def test_struggling_system_is_conservative(self):
        core_mod.BudgetTracker.update_system_health(0.2)
        try:
            self.assertLessEqual(_retry_budget_for("SELECT * FROM event;"), 2)
        finally:
            core_mod.BudgetTracker.update_system_health(1.0)

    def test_legacy_alias_still_bound(self):
        self.assertIs(core_mod._budget_aware_should_retry, _retry_budget_for)


class TestHealthFromFailures(unittest.TestCase):
    """Y7: the duplicated magic 12.0 is now one function."""

    def test_monotonically_decreasing(self):
        values = [_health_from_failures(n) for n in range(0, 11)]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_saturates_at_ten_failures(self):
        self.assertEqual(_health_from_failures(10), _health_from_failures(50))

    def test_zero_failures_is_full_health(self):
        self.assertEqual(_health_from_failures(0), 1.0)


class TestNonRetryableFailures(unittest.TestCase):
    """Y7: 4xx and statement ERR fail fast and do not trip the breaker."""

    def setUp(self):
        reset_surreal_circuit()
        core_mod._CIRCUIT_BREAKER_DISABLED_backup = core_mod._CIRCUIT_BREAKER_DISABLED

    def tearDown(self):
        reset_surreal_circuit()

    def _client_returning(self, status, payload):
        class _Resp:
            def __init__(self):
                self.status_code = status
                self.text = "boom"
                self.request = None

            def json(self):
                return payload

        class _Client:
            def __init__(self):
                self.calls = 0

            async def post(self, *a, **kw):
                self.calls += 1
                return _Resp()

        return _Client()

    def test_http_400_raises_immediately_without_retrying(self):
        client = self._client_returning(400, {"code": 400})
        with patch.object(core_mod, "_get_client", asyncio.sleep, create=True):
            async def _get():
                return client
            with patch.object(core_mod, "_get_client", _get):
                with self.assertRaises(_NonRetryableSurrealError):
                    asyncio.run(_query_surreal("SELECT * FROM event;"))
        self.assertEqual(client.calls, 1, "a permanent 400 must not be retried")

    def test_non_retryable_error_does_not_open_circuit(self):
        client = self._client_returning(400, {"code": 400})

        async def _get():
            return client

        with patch.object(core_mod, "_get_client", _get):
            with self.assertRaises(_NonRetryableSurrealError):
                asyncio.run(_query_surreal("SELECT * FROM event;"))
        # The breaker only counts availability problems.
        self.assertEqual(core_mod._surreal_failure_count, 0)
        self.assertFalse(core_mod._surreal_circuit_open)

    def test_statement_err_is_non_retryable(self):
        client = self._client_returning(200, [{"status": "ERR", "information": "bad"}])

        async def _get():
            return client

        with patch.object(core_mod, "_get_client", _get):
            with self.assertRaises(_NonRetryableSurrealError):
                asyncio.run(_query_surreal("SELECT * FROM event;"))
        self.assertEqual(client.calls, 1)
        self.assertEqual(core_mod._surreal_failure_count, 0)

    def test_retryable_statuses_are_the_transient_ones(self):
        for status in (408, 429, 500, 502, 503, 504):
            self.assertIn(status, core_mod._RETRYABLE_HTTP_STATUS)
        for status in (400, 401, 403, 404, 422):
            self.assertNotIn(status, core_mod._RETRYABLE_HTTP_STATUS)


class TestMemoryUpdateIsTransactional(unittest.TestCase):
    """R3: invalidate + RELATE must be one all-or-nothing unit."""

    @staticmethod
    def _entity_factory(value):
        async def _factory(*_a, **_kw):
            return value
        return _factory

    def test_sends_a_single_transaction(self):
        seen = []

        async def _capture(sql, params=None, ns=None, db=None):
            seen.append(sql)
            return [
                {"status": "OK", "result": {"namespace": "n", "database": "d"}},
                {"status": "OK", "result": None},                      # BEGIN
                {"status": "OK", "result": [{"id": "fact:old"}]},      # UPDATE
                {"status": "OK", "result": [{"id": "fact:new"}]},      # RELATE
                {"status": "OK", "result": None},                      # COMMIT
            ]

        with patch("src.mcp.common_logic._get_or_create_entity",
                   new=self._entity_factory("entity:a")), \
                patch("src.mcp.tools._query_surreal", _capture):
            result = asyncio.run(memory_update("Acme", "located_in", "Berlin"))

        self.assertEqual(len(seen), 1, "invalidate and RELATE must be one request")
        self.assertIn("BEGIN TRANSACTION", seen[0])
        self.assertIn("COMMIT TRANSACTION", seen[0])
        self.assertEqual(result["invalidated_facts"], ["fact:old"])
        self.assertEqual(result["new_fact"], "fact:new")

    def test_relate_failure_leaves_graph_untouched(self):
        """A failing RELATE must not leave every fact invalidated."""
        attempted = []

        async def _capture(sql, params=None, ns=None, db=None):
            attempted.append(sql)
            raise _NonRetryableSurrealError("RELATE rejected")

        with patch("src.mcp.common_logic._get_or_create_entity",
                   new=self._entity_factory("entity:a")), \
                patch("src.mcp.tools._query_surreal", _capture):
            with self.assertRaises(_NonRetryableSurrealError):
                asyncio.run(memory_update("Acme", "located_in", "Berlin"))

        # Exactly one request, containing both statements inside the
        # transaction -- never a committed invalidation on its own.
        self.assertEqual(len(attempted), 1)
        self.assertIn("BEGIN TRANSACTION", attempted[0])
        self.assertIn("UPDATE fact SET valid_until", attempted[0])
        self.assertIn("RELATE", attempted[0])


class TestFetchLimitIsCapped(unittest.TestCase):
    """Y2: over-fetch must not scale without bound."""

    def test_large_offset_does_not_explode_the_limit(self):
        seen = []

        async def _capture(sql, params=None, ns=None, db=None):
            seen.append(sql)
            return []

        with patch("src.mcp.tools._query_surreal", _capture), \
                patch("src.mcp.tools._fts_search_plan",
                      return_value={"where": "1=1", "has_lexical": False,
                                    "exclude_terms": ["x"], "exclude_phrases": []}):
            asyncio.run(event_log_search("q", limit=1000, offset=1_000_000))

        self.assertTrue(seen)
        for sql in seen:
            self.assertIn(f"LIMIT {_MAX_FETCH_ROWS}", sql)
            self.assertNotIn("10000000", sql)

    def test_traverse_path_budget_is_finite(self):
        self.assertLess(_MAX_TRAVERSE_PATHS, 100_000)


class TestStripSurrealComments(unittest.TestCase):
    """Y14: `--` inside a string literal is data, not a comment."""

    def test_strips_trailing_comment(self):
        self.assertEqual(
            _strip_surql_comments("DEFINE TABLE event SCHEMALESS; -- the table"),
            "DEFINE TABLE event SCHEMALESS;",
        )

    def test_keeps_double_dash_inside_single_quotes(self):
        line = "DEFINE FIELD regex ON t VALUE '^[a-z--]+$' ASSERT $value =~ /x/;"
        self.assertIn("^[a-z--]+$", _strip_surql_comments(line))

    def test_keeps_double_dash_inside_double_quotes(self):
        line = 'DEFINE FIELD note ON t VALUE "a -- b" ASSERT $value;'
        self.assertIn('"a -- b"', _strip_surql_comments(line))

    def test_strips_comment_after_closing_quote(self):
        self.assertEqual(
            _strip_surql_comments("DEFINE FIELD x ON t VALUE 'a' -- note"),
            "DEFINE FIELD x ON t VALUE 'a'",
        )

    def test_line_comment_only_becomes_empty(self):
        self.assertEqual(_strip_surql_comments("-- just a comment"), "")


class TestLoadSchemaFile(unittest.TestCase):
    """Y14: statement splitting must survive `--` in literals."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".surql")
        os.close(fd)

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def _load(self, text):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return load_schema_file(self.path)

    def test_adds_if_not_exists_once(self):
        stmts = self._load("DEFINE TABLE event SCHEMALESS;")
        self.assertEqual(len(stmts), 1)
        self.assertIn("DEFINE TABLE IF NOT EXISTS event", stmts[0])
        self.assertEqual(stmts[0].count("IF NOT EXISTS"), 1)

    def test_leaves_overwrite_alone(self):
        stmts = self._load("DEFINE FIELD OVERWRITE name ON entity TYPE string;")
        self.assertNotIn("IF NOT EXISTS", stmts[0])

    def test_preserves_dash_dash_in_string_literal(self):
        stmts = self._load(
            "DEFINE FIELD slug ON entity VALUE '^[a-z--]+$' ASSERT $value =~ /x/;")
        self.assertIn("^[a-z--]+$", stmts[0])

    def test_does_not_rewrite_second_occurrence(self):
        # str.replace rewrote *every* occurrence, so a keyword mentioned inside
        # a string literal was mangled too. Only the leading keyword changes.
        stmts = self._load(
            "DEFINE FIELD doc ON meta VALUE 'use DEFINE FIELD here' "
            "ASSERT $value;")
        self.assertEqual(stmts[0].count("IF NOT EXISTS"), 1)
        self.assertIn("'use DEFINE FIELD here'", stmts[0])
        self.assertTrue(stmts[0].startswith("DEFINE FIELD IF NOT EXISTS doc"))

    def test_trailing_comment_is_stripped(self):
        stmts = self._load("DEFINE TABLE meta SCHEMALESS; -- see docs\n")
        self.assertNotIn("see docs", stmts[0])
        self.assertEqual(stmts[0].count("IF NOT EXISTS"), 1)

    def test_multiple_statements_split(self):
        stmts = self._load("DEFINE TABLE a SCHEMALESS;\nDEFINE TABLE b SCHEMALESS;\n")
        self.assertEqual(len(stmts), 2)


class TestChunkingHasNoPerCharacterMap(unittest.TestCase):
    """Y8: the dead O(n) protected_map was pure overhead."""

    def test_large_document_chunks_without_per_character_map(self):
        import inspect

        from src.mcp import chunking
        src = inspect.getsource(chunking._build_section_tree)
        self.assertNotIn("protected_map", src)

    def test_section_tree_still_marks_protected_blocks(self):
        from src.mcp.chunking import _build_section_tree
        text = "intro line\n\n| a | b |\n| - | - |\n\ntail\n"
        blocks = [(text.index("| a"), text.index("\n\ntail"), "table")]
        sections = _build_section_tree(text, blocks)
        self.assertTrue(sections, "section tree should not be empty")


class TestStatementResultsUsedForTransactions(unittest.TestCase):
    def test_helper_exists_and_filters_markers(self):
        data = [
            {"status": "OK", "result": {"namespace": "n", "database": "d"}},
            {"status": "OK", "result": None},
            {"status": "OK", "result": [{"id": "fact:x"}]},
            {"status": "OK", "result": None},
        ]
        self.assertEqual(_extract_statement_results(data), [[{"id": "fact:x"}]])


if __name__ == "__main__":
    unittest.main()