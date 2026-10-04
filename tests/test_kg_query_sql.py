"""kg_query temporal filtering: at_time must pin validity, not add to now().

Regression seam for the 2026-10-03 incident: kg_query(subject, at_time=<t>)
returned 0 facts for a fact valid at <t> but invalidated since, because the
query always ANDed `valid_until > time::now()` with the at_time condition.

Tests the pure SQL builder seam (no DB).
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.mcp.tools import _build_kg_query_sql


class TestKgQueryTemporalSql(unittest.TestCase):
    def test_no_at_time_keeps_current_filter(self):
        sql = _build_kg_query_sql("Alice Henderson", None, None, None, 10, 0)
        self.assertIn("time::now()", sql)
        self.assertIn("Alice Henderson", sql)

    def test_at_time_replaces_now_filter(self):
        sql = _build_kg_query_sql(
            "Alice Henderson", None, None, "2026-10-03T19:08:00Z", 10, 0
        )
        # The validity window is pinned to at_time; requiring valid_until >
        # now() would exclude every fact invalidated since (the incident).
        self.assertNotIn("time::now()", sql)
        self.assertIn("2026-10-03T19:08:00Z", sql)
        self.assertIn("valid_from", sql)
        self.assertIn("valid_until", sql)

    def test_at_time_without_subject(self):
        sql = _build_kg_query_sql(None, None, "acquired", "2026-10-02T12:00:00Z", 5, 0)
        self.assertNotIn("time::now()", sql)
        self.assertIn("acquired", sql)

    def test_limit_offset_honoured(self):
        sql = _build_kg_query_sql(None, None, None, None, 7, 3)
        self.assertIn("LIMIT 7", sql)
        self.assertIn("START 3", sql)


if __name__ == "__main__":
    unittest.main()
