"""Stale facts must be archived, never silently deleted.

Regression seam: the maintainer physically DELETEd invalidated facts, which
destroyed the history that at_time queries promise. Stale facts are now
moved to `fact_history` (full copy + archived_at) before deletion.

Tests the pure seams (no DB):
- `_archive_fact_sqls` builds a fact_history CREATE preserving the fact,
  plus the DELETE of the original.
- `_build_kg_query_sql` accepts a table parameter for the history read path.
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.maintenance.conservative_maintainer import _archive_fact_sqls
from src.mcp.tools import _build_kg_query_sql

STALE_FACT = {
    "id": "fact:abc123",
    "predicate": "works_at",
    "in": "entity:sub1",
    "out": "entity:obj1",
    "confidence": 0.99,
    "valid_from": "2026-10-03T19:07:21.203429345Z",
    "valid_until": "2026-10-03T19:09:51.409152783Z",
}


class TestArchiveSqls(unittest.TestCase):
    def test_create_targets_history_and_preserves_fact(self):
        create_sql, delete_sql = _archive_fact_sqls(STALE_FACT)
        self.assertIn("fact_history", create_sql)
        self.assertIn("fact:abc123", create_sql)  # original id retained
        self.assertIn("works_at", create_sql)
        self.assertIn("archived_at", create_sql)
        for token in ("19:07:21", "19:09:51", "0.99"):
            self.assertIn(token, create_sql)

    def test_delete_targets_original_only(self):
        _, delete_sql = _archive_fact_sqls(STALE_FACT)
        self.assertIn("DELETE fact:abc123", delete_sql)
        self.assertNotIn("fact_history", delete_sql)

    def test_missing_id_raises(self):
        with self.assertRaises(ValueError):
            _archive_fact_sqls({"predicate": "works_at"})


class TestKgHistoryTable(unittest.TestCase):
    def test_table_param_switches_source(self):
        sql = _build_kg_query_sql(
            "Alice Henderson", None, None, "2026-10-03T19:08:00Z", 10, 0,
            table="fact_history",
        )
        self.assertIn("FROM fact_history", sql)
        self.assertNotIn("FROM fact\n", sql)
        self.assertNotIn("time::now()", sql)

    def test_default_table_unchanged(self):
        sql = _build_kg_query_sql("Alice Henderson", None, None, None, 10, 0)
        self.assertIn("FROM fact", sql)


if __name__ == "__main__":
    unittest.main()
