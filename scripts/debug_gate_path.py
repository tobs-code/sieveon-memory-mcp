"""Single-case trace: why did `created -> finished` survive an abstain?

Reconstructs the whole decision chain for one entity pair, so the gate's
actual path can be read instead of inferred. The declared rule is that an
abstention between two relations must leave the shipped relation in place,
and `verdict('finished', 'created')` does return `abstain`. Yet the full-set
run still recorded that regression, which means the gate was not applied to
the candidate it was supposed to judge. Either the override candidate came
from a different list than the one the gate compared against, or the
comparison used a different pair of relations than the ones actually
emitted.

This prints, for one sentence and one entity pair:

    shipped relation(s)
    every candidate the probe produced
    which of those are shipped
    the selector's winning candidate and its score
    both abstraction levels
    the comparability verdict for (winner, shipped rival)
    the relation actually emitted after gating

Run it with `--pair "joanna|presentation"`.

Usage:
    python scripts/debug_gate_path.py --pair "joanna|presentation"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
GOLD_FILES = [ROOT / "docs" / "eval_recall_gold_pilot.jsonl",
              ROOT / "docs" / "eval_recall_gold_batch2.jsonl",
              ROOT / "docs" / "eval_recall_gold_expanded.jsonl"]
CLAIM_FILES = [ROOT / "docs" / "eval_triples_gold_locomo_uniform_model.jsonl",
               ROOT / "docs" / "eval_recall_claims_expanded.jsonl"]


def norm(s: str) -> str:
    toks = [t for t in str(s).strip().lower().split() if t not in
            {"the", "a", "an"}]
    return " ".join(toks)


def slug(x: str) -> str:
    return str(x).strip().lower().replace(" ", "_")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pair", required=True,
                    help="normalised subject|object, e.g. joanna|presentation")
    ap.add_argument("--rel-threshold", type=float, default=0.2)
    args = ap.parse_args()

    from scripts.counterfactual_templates import COUNTERFACTUAL_CLAIM
    from scripts.selector_gate import (
        LEVEL_NAME, level, verdict, explain,
    )
    from src.extraction.entity_utils import (
        _SIEVEON_ENTITY_LABELS, _SIEVEON_RELATION_LABELS, _get_relex,
    )
    from src.extraction.verifier import _get_verifier
    from src.extraction.verbalise import CLAIM, verbalise
    import numpy as np

    subj, obj = (p.strip() for p in args.pair.split("|"))

    texts: Dict[str, str] = {}
    for f in GOLD_FILES:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                texts.setdefault(r["id"], r["text"])
    shipped: Dict[str, List[Dict[str, Any]]] = {}
    for f in CLAIM_FILES:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                shipped.setdefault(r["id"], []).extend(r.get("asserted", []))

    hits = [(sid, t) for sid, t in texts.items()
            if any(norm(c["s"]) == subj and norm(c["o"]) == obj
                   for c in shipped.get(sid, []))]
    if not hits:
        print(f"  no shipped claim for {subj} -> {obj}")
        return 2

    model = _get_relex()
    vmodel, v_entail, v_contra = _get_verifier()

    extended = list(_SIEVEON_RELATION_LABELS) + [
        c.replace("_", " ") for c in sorted(COUNTERFACTUAL_CLAIM)]

    for sid, text in hits:
        print("=" * 72)
        print(f"  {sid}")
        print(f"  {text}\n")

        base = [c for c in shipped[sid]
                if norm(c["s"]) == subj and norm(c["o"]) == obj]
        print("  shipped relation(s):")
        for c in base:
            print(f"    {c['p']:14} (confidence {c.get('c')})")
        shipped_rels = {c["p"] for c in base}

        _e, rels = model.predict_relations(
            text, _SIEVEON_ENTITY_LABELS, extended,
            threshold=0.2, relation_threshold=args.rel_threshold)
        cands = sorted({slug(r.get("relation", "")) for r in (rels or [])
                        if norm(r["head"]["text"]) == subj
                        and norm(r["tail"]["text"]) == obj})
        print(f"\n  all candidates from the extended probe: {cands}")
        print(f"  candidates that are also shipped: "
              f"{sorted(set(cands) & shipped_rels)}")

        surface = next((str(r["head"]["text"]).strip(), str(r["tail"]["text"]).strip())
                       for r in (rels or [])
                       if norm(r["head"]["text"]) == subj
                       and norm(r["tail"]["text"]) == obj)

        def claim(rel: str) -> str:
            if rel in COUNTERFACTUAL_CLAIM:
                return COUNTERFACTUAL_CLAIM[rel].format(s=surface[0], o=surface[1])
            return verbalise(surface[0], rel, surface[1])

        hyps = [claim(c) for c in cands]
        logits = vmodel.predict([[text, h] for h in hyps], convert_to_numpy=True)
        scores = [float(r[v_entail]) - float(r[v_contra])
                  for r in np.atleast_2d(logits)]
        ranked = sorted(zip(cands, scores), key=lambda t: -t[1])
        print("\n  selector scores (entail - contradict):")
        for c, s in ranked:
            mark = " <- shipped" if c in shipped_rels else ""
            print(f"    {c:14} {s:+8.3f}{mark}   \"{claim(c)}\"")

        top = ranked[0][0]
        rivals = [c for c in cands if c in shipped_rels]
        print(f"\n  winner: {top}")
        print(f"  rivals (the gate's comparison list): {rivals}")
        if not rivals:
            print("  gate: no shipped rival -> nothing to protect")
            continue
        rival = sorted(rivals)[0]
        print(f"\n  level({top})        = {level(top)} "
              f"[{LEVEL_NAME.get(level(top), 'outside')}]")
        print(f"  level({rival})      = {level(rival)} "
              f"[{LEVEL_NAME.get(level(rival), 'outside')}]")
        v = verdict(top, rival)
        print(f"  verdict({top!r}, {rival!r}) = {v!r}")
        print(f"  {explain(top, rival)}")
        emitted = rival if v == "abstain" else top
        print(f"\n  relation emitted after gating: {emitted}")
        expected = rival if v == "abstain" else top
        print(f"  INVARIANT: abstain implies the shipped relation survives -- "
              f"{'holds' if emitted == expected else 'VIOLATED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())