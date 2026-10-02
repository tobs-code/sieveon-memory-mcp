"""NLI verifier for candidate triples: extraction -> gates -> verify -> store.

A joint NER+RE model classifies an entity pair into a label. It does not ask
whether the sentence actually entails that relation, so the wrong verb on the
right entities survives with high confidence (supported 0.861 vs wrong 0.821
on 118 hand-annotated triples -- no threshold can separate them).

The verifier asks exactly that question. Given the source sentence and the
verbalised claim ("Andrew built the apartment."), an NLI cross-encoder
scores entailment vs contradiction, and the triple is kept only when the
margin clears the bar.

Scope, deliberately narrow:

* Only triples in the ambiguous band are judged (BAND_LO to BAND_HI in
  verbalise.py). Above it auto-accepts, below it drops. The base confidence
  already ranks well globally; only the band is undecided.
* verdict is a bool, but the margin is recorded on every kept fact as
  `verifier_margin`, so the threshold can be moved without re-ingesting.
* Lazy model load, CUDA when available. First use pays ~13s, every triple
  after that ~2ms on the reference hardware.
"""

from typing import Any, Dict, List, Optional, Tuple

from src.extraction.verbalise import BAND_HI, BAND_LO, verbalise

# MiniLM2 was selected over DeBERTa-xsmall on measured latency (p50 1.6ms,
# p95 1.9ms vs 5.9/66.2ms), with no significant AUC difference between them:
# in-band AUC 0.840 [0.754-0.915] vs 0.905 [0.842-0.958], overlapping.
# Full comparison in docs/eval_decision_gates_vs_verifier.md.
_VERIFIER_MODEL = "cross-encoder/nli-MiniLM2-L6-H768"

# Verifier margin (entailment minus contradiction logit) at or above which a
# candidate in the band is accepted. Set from the same measurement that
# adopted the verifier: at target recall 0.60 the accepting threshold was
# 6.26 with precision 0.844. Deliberately the measured value, not a rounded
# one, so a change is a conscious re-measurement rather than tidying.
_ACCEPT_MARGIN = 6.2617

_verifier = None


def _get_verifier():
    global _verifier
    if _verifier is None:
        from sentence_transformers import CrossEncoder

        model = CrossEncoder(_VERIFIER_MODEL, max_length=512, device="cuda")
        try:
            model.model = model.model.half()
        except Exception:
            pass
        id2label = {
            int(k): str(v).lower()
            for k, v in model.model.config.id2label.items()
        }
        entail_idx = next(k for k, v in id2label.items() if "entail" in v)
        contra_idx = next(k for k, v in id2label.items() if "contradict" in v)
        _verifier = (model, entail_idx, contra_idx)
    return _verifier


def verify_triples(
    sentence: str,
    triples: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Split candidate triples into accepted and verifier-rejected.

    Triples outside the band are not judged: above BAND_HI they pass through
    with margin None, below BAND_LO they are dropped. Only the band goes to
    the model. Returns (accepted, dropped_count).
    """
    model, entail_idx, contra_idx = _get_verifier()

    in_band: List[Dict[str, Any]] = []
    accepted: List[Dict[str, Any]] = []
    dropped = 0

    for t in triples:
        conf = float(t.get("confidence") or 0.0)
        if conf > BAND_HI:
            t["verifier_margin"] = None
            accepted.append(t)
        elif conf < BAND_LO:
            dropped += 1
        else:
            in_band.append(t)

    if not in_band:
        return accepted, dropped

    import numpy as np

    pairs = [(sentence, verbalise(t["subject"], t["predicate"], t["object"]))
             for t in in_band]
    logits = model.predict(
        [[p, h] for p, h in pairs], convert_to_numpy=True)
    for t, row in zip(in_band, np.atleast_2d(logits)):
        margin = float(row[entail_idx]) - float(row[contra_idx])
        t["verifier_margin"] = round(margin, 4)
        if margin >= _ACCEPT_MARGIN:
            accepted.append(t)
        else:
            dropped += 1

    return accepted, dropped


def verifier_status() -> Dict[str, Any]:
    """For health checks: is the model loaded, which one, what thresholds."""
    return {
        "model": _VERIFIER_MODEL,
        "loaded": _verifier is not None,
        "band": [BAND_LO, BAND_HI],
        "accept_margin": _ACCEPT_MARGIN,
    }
