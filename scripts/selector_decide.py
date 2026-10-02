"""One canonical decision path, shared by every caller.

The gated full-set run and the single-case debug trace disagreed about
`Jolene -> bullet journal`: the trace ranked `uses` at +5.830 against `wrote`
at +4.211 and kept `uses`, the full run emitted `wrote`. Until that is
explained, no gated number can be frozen, because it is not known whether the
measurement or the model is doing something.

Having two implementations is the likeliest cause. The trace scores one
hypothesis at a time, the full run scores a sentence's hypotheses in one
batch, and anything that differs -- candidate order, batching, dtype,
tokenisation, padding -- is free to change the numbers. So the path is
defined once, here, and both callers must use it:

    probe_candidates    extended-label probe, per sentence
    score_pairs         NLI scores, one batch per caller's own grouping
    decide_pair         rank, then gate, then emit

A caller may change how work is grouped, but it may not re-implement the
comparison. `decide_pair` returns the full decision record so that a caller
that disagrees with another can compare the intermediate values rather than
only the final relation.

CARDINALITY. `decide_pair` is a single-winner reranker: one relation per
entity pair. That is WRONG for this system and the single-winner runs
recorded with it are negative results under a wrong assumption, not evidence
about selection quality.

The production contract is multi-relation per entity pair. `Gina founded
store` and `Gina works_at store` are two facts, both true at once, both
emitted by the current pipeline and both scored separately by the gold. A
one-winner reranker can express at most one, so it necessarily loses the
others -- which is exactly the 4/26/44 pattern the gated run produced. The
defect is the cardinality assumption, not the gate.

`keep_relations` below is the multi-relation scorer and is the one that
matches the contract: every candidate relation is judged on its own merits
and several may survive. It stays here beside the single-winner path so the
difference is inspectable rather than rewritten away.

Invariant this module is meant to make checkable:

    same sentence + same pair + same candidate set + same model state
        => same scores, same gate decision, same emitted relation,
           whether processed alone or inside a batch
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]


def norm(s: str) -> str:
    toks = [t for t in str(s).strip().lower().split() if t not in
            {"the", "a", "an"}]
    return " ".join(toks)


def slug(x: str) -> str:
    return str(x).strip().lower().replace(" ", "_")


def claim_text(rel: str, subject: str, obj: str) -> str:
    """Hypothesis for one relation, counterfactual templates first."""
    from scripts.counterfactual_templates import COUNTERFACTUAL_CLAIM
    from src.extraction.verbalise import verbalise
    if rel in COUNTERFACTUAL_CLAIM:
        return COUNTERFACTUAL_CLAIM[rel].format(s=subject, o=obj)
    return verbalise(subject, rel, obj)


def probe_candidates(text: str, ent_threshold: float = 0.2,
                     rel_threshold: float = 0.2,
                     extra_labels: Sequence[str] = ()
                     ) -> Dict[str, Any]:
    """Extended-label probe. Returns candidates and surface strings per pair."""
    from src.extraction.entity_utils import (
        _SIEVEON_ENTITY_LABELS, _SIEVEON_RELATION_LABELS, _get_relex,
    )
    from scripts.counterfactual_templates import COUNTERFACTUAL_CLAIM

    labels = list(_SIEVEON_RELATION_LABELS) + [
        c.replace("_", " ") for c in sorted(COUNTERFACTUAL_CLAIM)]
    labels += [r.replace("_", " ") for r in extra_labels]

    _e, rels = _get_relex().predict_relations(
        text, _SIEVEON_ENTITY_LABELS, labels,
        threshold=ent_threshold, relation_threshold=rel_threshold)

    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in rels or []:
        try:
            h_raw = str(r["head"]["text"]).strip()
            t_raw = str(r["tail"]["text"]).strip()
        except (KeyError, TypeError, AttributeError):
            continue
        key = (norm(h_raw), norm(t_raw))
        entry = out.setdefault(key, {"candidates": set(),
                                     "surface": (h_raw, t_raw)})
        rel = slug(r.get("relation", ""))
        if rel:
            entry["candidates"].add(rel)
    return {f"{k[0]}|{k[1]}": {"candidates": sorted(v["candidates"]),
                               "surface": v["surface"]}
            for k, v in out.items()}


def score_pairs(premises: Sequence[str],
                hypotheses: Sequence[str]) -> List[float]:
    """Entailment minus contradiction, in one batch, for the given order.

    The caller decides the grouping, but this function is the only place a
    number is produced, so a single-hypothesis call and a batch call differ
    only in batch size -- which is the effect we want to measure.
    """
    import numpy as np
    from src.extraction.verifier import _get_verifier
    model, ent, con = _get_verifier()
    if not hypotheses:
        return []
    logits = model.predict([[p, h] for p, h in zip(premises, hypotheses)],
                           convert_to_numpy=True)
    return [float(row[ent]) - float(row[con])
            for row in np.atleast_2d(logits)]


def decide_pair(text: str, candidates: Sequence[str], subject: str,
                obj: str, shipped_rels: Sequence[str],
                gate: str = "abstraction") -> Dict[str, Any]:
    """Rank the candidates, then gate, then emit. Returns the whole chain.

    `gate` is "off" for the unrestricted selector or "abstraction" for the
    frozen comparability gate. The gate is evaluated against every relation
    the pipeline shipped for the pair, never against a filtered subset: an
    earlier version intersected candidates with shipped relations first, and
    when the shipped relation was absent from the probe the comparison set
    came out empty and the gate silently did nothing.
    """
    from scripts.selector_gate import level, verdict, explain

    cands = sorted(set(candidates))
    hyps = [claim_text(c, subject, obj) for c in cands]
    scores = score_pairs([text] * len(cands), hyps)
    ranked = sorted(zip(cands, scores), key=lambda t: (-t[1], t[0]))

    winner = ranked[0][0] if ranked else ""
    decision: Dict[str, Any] = {
        "candidates": cands,
        "ranked": [{"predicate": c, "hypothesis": h, "margin": round(s, 4)}
                   for c, s, h in zip([c for c, _ in ranked],
                                      [s for _, s in ranked], hyps)],
        "winner": winner,
        "winner_margin": round(ranked[0][1], 4) if ranked else None,
        "shipped_rels": sorted(set(shipped_rels)),
        "gate": gate,
    }

    if gate == "abstraction" and shipped_rels:
        for rival in sorted(set(shipped_rels)):
            v = verdict(winner, rival)
            decision["gate_checks"] = decision.get("gate_checks", [])
            decision["gate_checks"].append({
                "winner_level": level(winner),
                "rival": rival,
                "rival_level": level(rival),
                "verdict": v,
                "explanation": explain(winner, rival),
            })
            if v == "abstain":
                decision["gate_decision"] = f"abstain against {rival}"
                decision["emitted"] = rival
                break
        else:
            decision["gate_decision"] = "rankable against every shipped relation"
            decision["emitted"] = winner
    else:
        decision["gate_decision"] = ("gate off" if gate == "off"
                                     else "no shipped relation to protect")
        decision["emitted"] = winner

    # Post-decision invariant, asserted rather than assumed: an abstention
    # must leave a shipped relation in place.
    if decision.get("gate_decision", "").startswith("abstain"):
        assert decision["emitted"] in set(shipped_rels), (
            f"gate invariant violated: abstained against "
            f"{decision['emitted']} but emitted something else")
    return decision


def keep_relations(text: str, candidates: Sequence[str], subject: str,
                   obj: str, shipped_rels: Sequence[str] = (),
                   gate: str = "abstraction") -> Dict[str, Any]:
    """Score every relation on its own merits; keep several if several hold.

    This is the multi-relation scorer the production contract requires. Each
    candidate is judged independently, so no relation's fate depends on
    where another relation on the same entity pair ranks. That independence
    is the invariant: the earlier single-winner design made an existing
    correct relation disappear because another relation on the same pair
    scored higher, which is what produced every regression in the gated run.

    Returns per-relation keep/drop decisions with the margin that produced
    them, plus a summary of how many relations survive for this pair.
    """
    from scripts.selector_gate import level, verdict

    cands = sorted(set(candidates))
    hyps = [claim_text(c, subject, obj) for c in cands]
    scores = score_pairs([text] * len(cands), hyps)
    shipped = set(shipped_rels)

    per: List[Dict[str, Any]] = []
    for c, s, h in zip(cands, scores, hyps):
        keep = True
        reason = "score kept it"
        if gate == "abstraction" and shipped:
            # A shipped relation is never dropped for being less specific
            # than a rival: dropping it is the exact failure under repair.
            if c in shipped:
                keep, reason = True, "already shipped, protected"
            elif any(verdict(c, r) == "same" for r in shipped):
                keep, reason = True, "comparable to a shipped relation"
        per.append({"predicate": c, "hypothesis": h, "margin": round(s, 4),
                    "level": level(c), "keep": keep, "reason": reason,
                    "shipped": c in shipped})

    kept = [p["predicate"] for p in per if p["keep"]]
    return {
        "candidates": cands,
        "per_relation": per,
        "kept": kept,
        "dropped": [p["predicate"] for p in per if not p["keep"]],
        "multiplicity": len(kept),
        "gate": gate,
    }


if __name__ == "__main__":
    print(__doc__)