"""Entity typing must consult the embedding service, not fall back to concept.

Regression seam for the 2026-10-03 incident: `memory_update` created
"NovaCore Labs" with type `concept` because `_get_or_create_entity` calls
`infer_entity_type(name)` without an embedding service, and the suffix
heuristics do not cover "labs".

Unit seam: `infer_entity_type` with an injected stub service (no DB, no
models). The wiring fix in `_get_or_create_entity` is verified live
(memory_update on a fresh name must not yield `concept`).
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.extraction.embedding_service import BaseEmbeddingService
from src.extraction import entity_utils
from src.extraction.entity_utils import infer_entity_type


ORG_MARKERS = (
    "corp", "inc", "llc", "ltd", "labs", "acme", "microsoft", "google",
    "openai", "red cross", "united nations", "stanford", "university",
)


class StubEmbeddingService(BaseEmbeddingService):
    """Deterministic 2-D stub: org-like texts point at [1, 0], rest [0, 1]."""

    def __init__(self):
        super().__init__("stub")
        self.calls = 0

    def _vec(self, text):
        self.calls += 1
        t = text.lower()
        if any(m in t for m in ORG_MARKERS):
            return [1.0, 0.0]
        return [0.0, 1.0]

    def embed_for_storage(self, text):
        return self._vec(text)

    def embed_for_query(self, text):
        return self._vec(text)

    def embed_batch(self, texts, for_storage=True):
        return [self._vec(t) for t in texts]


class TestInferEntityTypeUsesService(unittest.TestCase):
    def setUp(self):
        entity_utils._INFER_TYPE_CACHE.clear()
        entity_utils._EMBEDDING_CACHE.clear()

    def test_labs_name_is_organization_with_service(self):
        svc = StubEmbeddingService()
        self.assertEqual(infer_entity_type("NovaCore Labs", svc), "organization")
        self.assertGreater(svc.calls, 0)

    def test_unknown_name_without_service_falls_back_to_concept(self):
        # Documents the fallback the incident hit; callers must pass a
        # service to avoid it.
        self.assertEqual(infer_entity_type("NovaCore Labs"), "concept")

    def test_suffix_fast_path_unaffected(self):
        svc = StubEmbeddingService()
        self.assertEqual(infer_entity_type("DataBridge Ltd", svc), "organization")
        self.assertEqual(svc.calls, 0)


if __name__ == "__main__":
    unittest.main()
