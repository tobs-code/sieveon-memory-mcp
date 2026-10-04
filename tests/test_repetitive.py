"""Repetitive-content detection must not nuke normal technical prose.

Regression seam for the 2026-10-03 incident: `semantic_search` ranked an
irrelevant event above the true match because `_is_highly_repetitive`
flagged normal sentences (character diversity 0.16-0.20, an artifact of
text length: the charset is bounded, so the ratio sinks as text grows).
The x0.02 penalty then annihilated two-channel matches.

Character diversity alone cannot separate "test test test test test"
(0.167) from a normal sentence (0.164): only the word-repetition rate
tells them apart. Both signals are required.

Tests the pure helper seam (no DB).
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.mcp.tools import _is_highly_repetitive

ALICE = (
    "PRODTEST2026: Alice Henderson is the lead backend engineer at NovaCore "
    "Systems. She designed the payment reconciliation service using Rust and "
    "PostgreSQL, deployed in Frankfurt."
)
CAROL = (
    "PRODTEST2026: Carol White is a data scientist at NovaCore Systems who "
    "built the churn prediction model achieving 94 percent accuracy with XGBoost."
)


class TestRepetitiveDetection(unittest.TestCase):
    def test_normal_technical_prose_is_not_repetitive(self):
        self.assertFalse(_is_highly_repetitive(ALICE))
        self.assertFalse(_is_highly_repetitive(CAROL))
        self.assertFalse(
            _is_highly_repetitive("Netflix uses Amazon Web Services for its infrastructure.")
        )

    def test_word_salad_repetition_is_repetitive(self):
        self.assertTrue(_is_highly_repetitive("test test test test test"))
        self.assertTrue(_is_highly_repetitive("ab ab ab ab ab ab ab ab"))

    def test_short_and_empty_is_not_repetitive(self):
        self.assertFalse(_is_highly_repetitive(""))
        self.assertFalse(_is_highly_repetitive("hi"))


if __name__ == "__main__":
    unittest.main()
