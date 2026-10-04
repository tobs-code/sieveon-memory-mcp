"""Rare-term boost must match whole words, not substrings.

Regression seam for the 2026-10-03 incident: `semantic_search` for
"payment reconciliation service Rust PostgreSQL" ranked the irrelevant
"Netflix uses Amazon Web Services ..." first, partly because the rare-term
boost counted "service" as a hit inside "Services" (`in` substring check).

Tests the pure helper seam (no DB).
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.mcp.tools import _count_rare_term_hits


class TestRareTermWordBoundaries(unittest.TestCase):
    def test_substring_inside_longer_word_is_no_hit(self):
        self.assertEqual(
            _count_rare_term_hits(
                ["payment", "reconciliation", "service", "postgresql"],
                "netflix uses amazon web services for its infrastructure.",
            ),
            0,
        )

    def test_exact_words_hit(self):
        self.assertEqual(
            _count_rare_term_hits(
                ["payment", "reconciliation", "service", "postgresql"],
                "she designed the payment reconciliation service using rust.",
            ),
            3,
        )

    def test_case_insensitive(self):
        # Contract: the caller passes already-lowercased content.
        self.assertEqual(
            _count_rare_term_hits(["postgresql"], "runs on postgresql 16."),
            1,
        )


if __name__ == "__main__":
    unittest.main()
