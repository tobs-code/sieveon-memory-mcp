"""Answer synthesis: facts without query overlap must not outrank a covering event.

Regression seam for the 2026-10-03 production incident: the query
"Which company did NovaCore acquire and for how much?" returned
"Facebook acquired WhatsApp. ..." with verdict=found and confidence 0.8,
even though the correct event (NovaCore/DataBridge, $45M) was retrieved.
Generic KG facts shared no word with the query; they were trusted via the
confident-retrieval path and carried the verdict on their own.

Tests call the pure seam `src.mcp.common_logic._synthesize_answer`
(no DB, no models).
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.mcp.common_logic import _synthesize_answer


def _fact(subj, pred, obj, conf=0.9):
    return {
        "id": "fact:test",
        "predicate": pred,
        "confidence": conf,
        "in": {"id": "entity:s", "name": subj, "type": "organization"},
        "out": {"id": "entity:o", "name": obj, "type": "organization"},
    }


ACQUIRE_QUERY = "Which company did NovaCore acquire and for how much?"
DATABRIDGE_EVENT = (
    "PRODTEST2026: NovaCore Systems acquired DataBridge Ltd in March 2026 "
    "for 45 million dollars to expand its analytics platform. "
    "The CEO Maria Chen announced the deal in Berlin."
)


class TestZeroOverlapFactsDoNotCarryVerdict(unittest.TestCase):
    """Facts that share no vocabulary with the query are weak evidence."""

    def test_acquisition_incident_leads_with_event(self):
        facts = [
            _fact("Facebook", "acquired", "WhatsApp", 0.95),
            _fact("Google", "acquired", "YouTube", 0.94),
            _fact("Apple", "acquired", "Beats Electronics", 0.94),
            # Live noise: shares "novacore" with the query but states no
            # relation -- must not confirm the answer either.
            {
                "id": "fact:co",
                "predicate": "co_occurs_with",
                "confidence": 0.71,
                "in": {"id": "entity:n", "name": "NovaCore Systems", "type": "organization"},
                "out": {"id": "entity:d", "name": "David Kim", "type": "person"},
            },
        ]
        entities = [{"id": "entity:n", "name": "NovaCore Systems", "type": "organization"}]
        events = [{"id": "event:d", "content": DATABRIDGE_EVENT, "source": "prodtest"}]

        summary = _synthesize_answer(
            ACQUIRE_QUERY, entities, facts, events, retrieval_relevance=1.0
        )

        # Must not claim a confirmed answer built on vocabulary-free facts.
        self.assertNotEqual(summary["verdict"], "found")
        self.assertFalse(summary["found"])
        # The covering event answers the question: it leads the answer text.
        self.assertIn("DataBridge", summary["answer"])
        self.assertLess(
            summary["answer"].index("DataBridge"),
            summary["answer"].index("Facebook"),
        )

    def test_paraphrase_fact_without_event_is_weak_not_found(self):
        # Zero-overlap fact, confident retrieval, no covering event:
        # may be quoted as a near miss, but never a confirmed answer.
        facts = [_fact("Netflix", "uses", "Amazon Web Services", 0.9)]
        summary = _synthesize_answer(
            "Which cloud provider hosts the streaming platform?",
            [],
            facts,
            [],
            retrieval_relevance=0.9,
        )
        self.assertNotEqual(summary["verdict"], "found")
        self.assertIn("Netflix", summary["answer"])

    def test_strong_fact_still_found(self):
        # Guard against overcorrection: a fact sharing query vocabulary
        # keeps the old confident behaviour.
        facts = [
            {
                "id": "fact:w",
                "predicate": "works_at",
                "confidence": 0.99,
                "in": {"id": "entity:a", "name": "Alice Henderson", "type": "person"},
                "out": {"id": "entity:n", "name": "NovaCore Systems", "type": "organization"},
            }
        ]
        entities = [{"id": "entity:n", "name": "NovaCore Systems", "type": "organization"}]
        events = [
            {
                "id": "event:a",
                "content": "Alice Henderson is the lead backend engineer at NovaCore Systems.",
                "source": "prodtest",
            }
        ]
        summary = _synthesize_answer(
            "Who is the lead backend engineer at NovaCore Systems?",
            entities,
            facts,
            events,
            retrieval_relevance=0.78,
        )
        self.assertEqual(summary["verdict"], "found")
        self.assertTrue(summary["found"])
        self.assertIn("Alice Henderson works_at NovaCore Systems", summary["answer"])


class TestMorphologyAwareOverlap(unittest.TestCase):
    """Inflections must count as overlap: 'acquire' == 'acquired'."""

    def test_inflected_verb_covers_event(self):
        events = [{"id": "event:d", "content": DATABRIDGE_EVENT, "source": "prodtest"}]
        summary = _synthesize_answer(
            ACQUIRE_QUERY, [], [], events, retrieval_relevance=1.0
        )
        snippets = summary["parts"]
        self.assertTrue(
            any(p.get("type") == "relevant_events" for p in snippets),
            "inflected 'acquired' must match query word 'acquire'",
        )


if __name__ == "__main__":
    unittest.main()
