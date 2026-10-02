"""Inference adapter: identical prediction interface for base and checkpoints.

Wraps the existing joint NER+RE inference (src/extraction/entity_utils)
without changing its semantics: no fold logic, no test logic, no threshold
optimisation, no family/pair/cue/provenance inputs.

    model = load_relex_model(source)   # 'base' or checkpoint dir
    out = predict(model, sentence, entities=None)

Output schema (both sources, by construction via _standardize):
    [{"head": str, "tail": str, "relation": str, "score": float,
      "source": "base" | <checkpoint digest>}]

Checkpoint dirs must carry training_manifest.json with base_model,
label_map, seed, contract_version, fold_id and training_data_digest.
Incompatible manifests fail hard; there is no silent fallback to base.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE_MODEL = "knowledgator/gliner-relex-multi-v1.0"
REQUIRED_MANIFEST_KEYS = ("base_model", "label_map", "seed",
                          "contract_version", "fold_id", "training_data_digest")


def load_relex_model(source: str):
    """Load base or a validated checkpoint. Returns (model, source_tag)."""
    if source == "base":
        from src.extraction.entity_utils import _get_relex
        return _get_relex(), "base"
    ckpt = Path(source)
    manifest_path = ckpt / "training_manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"checkpoint {source} has no training_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_MANIFEST_KEYS if k not in manifest]
    if missing:
        raise ValueError(f"checkpoint {source} manifest lacks {missing}")
    if manifest["base_model"] != BASE_MODEL:
        raise ValueError(f"checkpoint {source} base {manifest['base_model']!r} "
                         f"!= {BASE_MODEL!r}")
    from gliner import GLiNER
    model = GLiNER.from_pretrained(str(ckpt))
    model.eval()
    return model, manifest.get("checkpoint_digest", "checkpoint")


def _standardize(rels, source_tag: str) -> list[dict]:
    from src.extraction.entity_utils import _normalize_relation_label
    out = []
    for rel in rels or []:
        try:
            head = rel["head"]["text"].strip()
            tail = rel["tail"]["text"].strip()
            pred = _normalize_relation_label(rel.get("relation", ""))
            conf = float(rel.get("score", 0.7))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        out.append({"head": head, "tail": tail, "relation": pred,
                    "score": conf, "source": source_tag})
    return out


def predict(model_bundle, sentence: str, entities=None) -> list[dict]:
    """Predict relations. `entities`, if given, only filters head/tail pairs
    by exact text match; it never reaches the model as a feature."""
    from src.extraction.entity_utils import (_SIEVEON_ENTITY_LABELS,
                                             _SIEVEON_RELATION_LABELS,
                                             _env_float)
    model, source_tag = model_bundle
    ent_thr = _env_float("RELEX_ENT_THRESHOLD", 0.5)
    rel_thr = _env_float("RELEX_REL_THRESHOLD", 0.7)
    _ents, rels = model.predict_relations(
        sentence, _SIEVEON_ENTITY_LABELS, _SIEVEON_RELATION_LABELS,
        threshold=ent_thr, relation_threshold=rel_thr)
    out = _standardize(rels, source_tag)
    if entities:
        keep = {e.strip().lower() for e in entities}
        out = [r for r in out
               if r["head"].lower() in keep and r["tail"].lower() in keep]
    return out
