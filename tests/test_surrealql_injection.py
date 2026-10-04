"""Regression tests for the SurrealQL injection fixes (R1, R2).

Two independent defects, both closed in this change:

R1 -- `escape_surrealql` escaped apostrophes but not double quotes, while
     event_log_search / list_events embedded `since`/`until` in a *double*
     quoted literal: type::datetime("..."). A `since` containing `"` closed
     the literal early and the remainder was parsed as SurrealQL. Verified
     against a live SurrealDB 3.x before the fix (parse error pointed at the
     early-terminated quote). Those values are now BOUND parameters.

R2 -- record ids are interpolated *unquoted* into FROM/WHERE/UPDATE/DELETE,
     so they cannot be escaped at all. `memory_get`, `memory_unforget`,
     `graph_traverse` and the sieveon:// MCP resources accepted them without
     validating their shape, while `memory_forget` already used `_is_record_id`.
     All five now share one guard.

Pure seams, no database required.
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.extraction.entropy_gate import escape_surrealql
from src.mcp.core import (
    _datetime_filters,
    _extract_result,
    _extract_statement_results,
    _is_record_id,
    _strip_angled,
    _validate_limit,
    get_entity_resource,
    get_event_resource,
)
from src.mcp.tools import (
    event_log_search,
    list_events,
    memory_get,
    memory_unforget,
)


# The payload that broke out of the double-quoted literal before the fix.
INJECTION = '2020-01-01" OR 1=1 OR timestamp >= type::datetime("'


def unescaped_quotes(value: str) -> int:
    """Count `"` characters that are not preceded by an escaping backslash.

    Checking for a bare '"' in the output is not a usable assertion: the correct
    escaping *is* `\"`, which of course still contains a quote character.
    """
    count = 0
    i = 0
    while i < len(value):
        if value[i] == '"':
            backslashes = 0
            j = i - 1
            while j >= 0 and value[j] == "\\":
                backslashes += 1
                j -= 1
            if backslashes % 2 == 0:
                count += 1
        i += 1
    return count


def unescaped_apostrophes(value: str) -> int:
    count = 0
    i = 0
    while i < len(value):
        if value[i] == "'":
            backslashes = 0
            j = i - 1
            while j >= 0 and value[j] == "\\":
                backslashes += 1
                j -= 1
            if backslashes % 2 == 0:
                count += 1
        i += 1
    return count


class TestEscapeSurrealQLQuotes(unittest.TestCase):
    """R1 root cause."""

    def test_double_quote_is_escaped(self):
        self.assertEqual(unescaped_quotes(escape_surrealql(INJECTION)), 0)

    def test_apostrophe_still_escaped(self):
        self.assertEqual(unescaped_apostrophes(escape_surrealql("it's")), 0)

    def test_backslash_escaped_before_quotes(self):
        # A literal backslash must be doubled first, otherwise the escape
        # introduced for the quote gets escaped instead.
        self.assertEqual(escape_surrealql('a"b'), 'a\\"b')

    def test_both_quotes_independently_covered(self):
        out = escape_surrealql("""it's a "test" """)
        self.assertEqual(unescaped_quotes(out), 0)
        self.assertEqual(unescaped_apostrophes(out), 0)

    def test_newline_and_control_stripped(self):
        out = escape_surrealql("a\nb\x00c")
        self.assertNotIn("\n", out)
        self.assertNotIn("\x00", out)


class TestDatetimeFiltersAreBound(unittest.TestCase):
    """R1 fix: since/until become bind parameters, never literals."""

    def test_values_are_bound_not_interpolated(self):
        clauses, params = _datetime_filters(INJECTION)
        joined = " ".join(clauses)
        self.assertNotIn("OR 1=1", joined)
        self.assertNotIn("2020-01-01\"", joined)
        self.assertIn("$t_since", joined)
        self.assertEqual(params["t_since"], INJECTION)

    def test_since_and_until_use_distinct_params(self):
        clauses, params = _datetime_filters("2020-01-01", "2021-01-01")
        self.assertEqual(len(clauses), 2)
        self.assertIn("$t_since", " ".join(clauses))
        self.assertIn("$t_until", " ".join(clauses))
        self.assertEqual(params, {"t_since": "2020-01-01", "t_until": "2021-01-01"})

    def test_no_filters_yields_no_clauses(self):
        clauses, params = _datetime_filters(None, None)
        self.assertEqual(clauses, [])
        self.assertEqual(params, {})

    def test_empty_string_is_treated_as_absent(self):
        clauses, params = _datetime_filters("", "")
        self.assertEqual(clauses, [])
        self.assertEqual(params, {})


class TestRecordIdGuard(unittest.TestCase):
    def test_accepts_shapes_surrealdb_generates(self):
        for good in ("event:abc123", "entity:x_y_z", "fact:a1b2c3"):
            self.assertTrue(_is_record_id(good), good)

    def test_rejects_statement_terminators(self):
        for bad in (
            "event:abc; DELETE event",
            "event:abc; REMOVE DATABASE x",
            "entity:a UNION SELECT * FROM event",
            "event:a--",
            "event:",
            "",
            "event:a\nCREATE b",
            "no_colon_here",
        ):
            self.assertFalse(_is_record_id(bad), bad)

    def test_strip_angled_handles_delimiters(self):
        self.assertEqual(_strip_angled("⟨event:abc⟩"), "event:abc")


class TestMemoryGetRejectsInjection(unittest.TestCase):
    """R2: memory_get interpolated id_stripped unquoted."""

    def _assert_rejected(self, bad_id):
        import asyncio
        result = asyncio.run(memory_get(bad_id))
        self.assertEqual(result.get("status"), "error", bad_id)
        self.assertIn("Invalid record id", result.get("message", ""))

    def test_semicolon_payload_rejected(self):
        self._assert_rejected("event:abc; DELETE event")

    def test_union_payload_rejected(self):
        self._assert_rejected("event:abc; REMOVE DATABASE sieveon")


class TestMemoryUnforgetRejectsInjection(unittest.TestCase):
    """R2: memory_unforget had no validation at all."""

    def test_semicolon_payload_rejected(self):
        import asyncio
        result = asyncio.run(memory_unforget("event:abc; UPDATE event SET forgotten=false"))
        self.assertEqual(result.get("status"), "error")
        self.assertIn("Invalid record id", result.get("message", ""))

    def test_unforget_does_not_reach_the_database(self):
        """The guard must run before any query, not merely clean up after."""
        import asyncio
        from src.mcp import tools as tools_mod

        async def _boom(*_a, **_kw):
            raise AssertionError("database was contacted with an invalid id")

        with patch.object(tools_mod, "_query_surreal", _boom):
            result = asyncio.run(memory_unforget("event:x; DELETE y"))
        self.assertEqual(result.get("status"), "error")


class TestGraphTraverseRejectsInjection(unittest.TestCase):
    """R2: graph_traverse interpolated `clean_id` with no shape check."""

    def test_semicolon_payload_rejected(self):
        import asyncio
        from src.mcp.tools import graph_traverse

        fn = getattr(graph_traverse, "fn", graph_traverse)
        result = asyncio.run(fn("entity:abc OR 1=1"))
        self.assertEqual(result.get("status"), "error")
        self.assertIn("Invalid record id", result.get("error", ""))

    def test_valid_record_id_is_accepted(self):
        """The guard must not reject the shape SurrealDB actually generates."""
        import asyncio
        from unittest.mock import patch
        from src.mcp import tools as tools_mod
        from src.mcp.tools import graph_traverse

        async def _capture(sql, params=None, ns=None, db=None):
            return [{"status": "OK", "result": [
                {"id": "entity:abc", "name": "Acme", "type": "organization"}
            ]}]

        async def _capture_facts(sql, params=None, ns=None, db=None):
            return [{"status": "OK", "result": []}]

        fn = getattr(graph_traverse, "fn", graph_traverse)
        with patch.object(tools_mod, "_query_surreal", _capture):
            result = asyncio.run(fn("entity:abc", max_depth=1))
        self.assertEqual(result.get("status"), "ok", result)


class TestMcpResourcesRejectInjection(unittest.TestCase):
    """R2: sieveon://entity/{id} and sieveon://event/{id}."""

    @staticmethod
    def _unwrap(resource):
        return getattr(resource, "fn", resource)

    def test_event_resource_rejects_injection(self):
        import asyncio
        payload = "event%3Aabc%3B%20REMOVE%20DATABASE%20sieveon"
        out = json.loads(asyncio.run(self._unwrap(get_event_resource)(payload)))
        self.assertIn("error", out)
        self.assertIn("Invalid record id", out["error"])

    def test_entity_resource_rejects_injection(self):
        import asyncio
        payload = "entity%3Aabc%3B%20DELETE%20event"
        out = json.loads(asyncio.run(self._unwrap(get_entity_resource)(payload)))
        self.assertIn("error", out)
        self.assertIn("Invalid record id", out["error"])


class TestListEventsBindsSinceUntil(unittest.TestCase):
    """R1 at the tool boundary: params must reach _query_surreal."""

    def test_injection_never_reaches_sql(self):
        import asyncio
        from src.mcp import tools as tools_mod

        seen = []

        async def _capture(sql, params=None, ns=None, db=None):
            seen.append((sql, params or {}))
            return []

        with patch.object(tools_mod, "_query_surreal", _capture):
            asyncio.run(list_events(since=INJECTION, until="2021-01-01"))

        self.assertTrue(seen, "no query was issued")
        for sql, params in seen:
            self.assertNotIn("OR 1=1", sql)
            self.assertNotIn('type::datetime("', sql)
            self.assertIn("$t_since", sql)
        self.assertEqual(seen[0][1].get("t_since"), INJECTION)


class TestEventLogSearchBindsSinceUntil(unittest.TestCase):
    def test_rejects_negative_limit(self):
        import asyncio
        with self.assertRaises(ValueError):
            asyncio.run(event_log_search("hello", limit=-1))

    def test_rejects_absurd_limit(self):
        import asyncio
        with self.assertRaises(ValueError):
            asyncio.run(event_log_search("hello", limit=10**9))

    def test_injection_never_reaches_sql(self):
        import asyncio
        from src.mcp import tools as tools_mod

        seen = []

        async def _capture(sql, params=None, ns=None, db=None):
            seen.append((sql, params or {}))
            return []

        async def _fake_embed(_q):
            return [0.0, 0.0]

        with patch.object(tools_mod, "_query_surreal", _capture), \
                patch.object(tools_mod, "_embed_query", _fake_embed):
            asyncio.run(event_log_search("", since=INJECTION))

        for sql, params in seen:
            self.assertNotIn("OR 1=1", sql)
            self.assertNotIn('type::datetime("', sql)


class TestValidateLimit(unittest.TestCase):
    """Y1/Y2: the previously-dead validator is now wired in."""

    def test_accepts_normal_values(self):
        self.assertEqual(_validate_limit(10, "limit", 100), 10)
        self.assertEqual(_validate_limit(0, "limit", 100), 0)

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            _validate_limit(-1, "limit", 100)

    def test_rejects_above_max(self):
        with self.assertRaises(ValueError):
            _validate_limit(101, "limit", 100)

    def test_rejects_bool_which_is_an_int_subclass(self):
        with self.assertRaises(ValueError):
            _validate_limit(True, "limit", 100)


class TestExtractStatementResults(unittest.TestCase):
    """R3 helper: skips USE and BEGIN/COMMIT rows, keeps real results."""

    def test_filters_use_and_transaction_markers(self):
        data = [
            {"status": "OK", "result": {"namespace": "sieveon", "database": "sieveon"}},
            {"status": "OK", "result": None},          # BEGIN
            {"status": "OK", "result": [{"id": "fact:1"}]},
            {"status": "OK", "result": [{"id": "fact:2"}]},
            {"status": "OK", "result": None},          # COMMIT
        ]
        self.assertEqual(
            _extract_statement_results(data),
            [[{"id": "fact:1"}], [{"id": "fact:2"}]],
        )

    def test_wraps_bare_dict_result(self):
        data = [{"status": "OK", "result": {"id": "x"}}]
        self.assertEqual(_extract_statement_results(data), [[{"id": "x"}]])

    def test_handles_empty_input(self):
        self.assertEqual(_extract_statement_results([]), [])
        self.assertEqual(_extract_statement_results(None), [])


class TestExtractResultIndexSemantics(unittest.TestCase):
    """Y5: the index==1 branch is now the only path for index 1."""

    def test_index_one_returns_first_candidate(self):
        data = [
            {"status": "OK", "result": {"namespace": "n", "database": "d"}},
            {"status": "OK", "result": [{"id": "a"}]},
            {"status": "OK", "result": [{"id": "b"}]},
        ]
        self.assertEqual(_extract_result(data, 1), [{"id": "a"}])

    def test_index_zero_returns_first_candidate(self):
        data = [
            {"status": "OK", "result": {"namespace": "n", "database": "d"}},
            {"status": "OK", "result": [{"id": "a"}]},
        ]
        self.assertEqual(_extract_result(data, 0), [{"id": "a"}])

    def test_non_list_input_is_empty(self):
        self.assertEqual(_extract_result(None, 1), [])


class TestExtractResultSkipsControlStatements(unittest.TestCase):
    """Bound parameters must not be mistaken for the query's result.

    `_query_surreal` prepends `LET $k = ...` per bound parameter. Those
    statements come back with `result: None` and passed the old candidate
    filter, so `candidates[0]` was the first LET rather than the SELECT and
    every parameterised query silently returned []. Verified live: a bound
    `WHERE name = $m` found nothing while the interpolated form found the row.
    """

    def test_let_statement_is_not_returned(self):
        data = [
            {"status": "OK", "result": {"namespace": "n", "database": "d"}},
            {"status": "OK", "result": None},            # LET $m = "x"
            {"status": "OK", "result": [{"name": "x"}]},  # the actual query
        ]
        self.assertEqual(_extract_result(data, 1), [{"name": "x"}])

    def test_multiple_lets_all_skipped(self):
        data = [
            {"status": "OK", "result": {"namespace": "n", "database": "d"}},
            {"status": "OK", "result": None},              # LET $a
            {"status": "OK", "result": None},              # LET $b
            {"status": "OK", "result": [{"c": 7}]},        # the query
        ]
        self.assertEqual(_extract_result(data, 1), [{"c": 7}])

    def test_all_control_statements_yields_empty(self):
        data = [
            {"status": "OK", "result": {"namespace": "n", "database": "d"}},
            {"status": "OK", "result": None},
            {"status": "OK", "result": None},
        ]
        self.assertEqual(_extract_result(data, 1), [])

    def test_transaction_markers_skipped(self):
        data = [
            {"status": "OK", "result": {"namespace": "n", "database": "d"}},
            {"status": "OK", "result": None},               # BEGIN
            {"status": "OK", "result": [{"id": "fact:x"}]}, # UPDATE
            {"status": "OK", "result": None},               # COMMIT
        ]
        self.assertEqual(_extract_result(data, 1), [{"id": "fact:x"}])


if __name__ == "__main__":
    unittest.main()