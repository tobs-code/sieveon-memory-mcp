"""Full pipeline matrix: every asserted triple, one final state, one verdict.

Each of the 118 annotated triples ends in exactly one pipeline state:

    structural_drop   copular frame + event predicate
    verifier_drop     in the band, margin below the bar (or model dead)
    verifier_accept   in the band, margin clears the bar
    auto_accept       above the band, never judged
    floor_drop        below the band, model never sees it

and carries its hand verdict:

    supported / implied / wrong

The cross-tabulation is the audit trail for the +0.257 precision gain: it
shows which stage removed which error, and which correct triples each stage
cost. A stage that cannot be audited this way cannot be trusted, because its
contribution to the headline number is then unverifiable.

Usage:
    python scripts/eval_pipeline_matrix.py
    python scripts/eval_pipeline_matrix.py --out docs/eval_pipeline_matrix.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "docs" / "eval_triples_gold_locomo_draft_model.jsonl"

STATES = ("structural_drop", "verifier_drop", "verifier_accept",
          "auto_accept", "floor_drop")


async def build_matrix(shadow: bool = False,
                       draft: Path | None = None,
                       gaps: List[Path] | None = None) -> List[Dict[str, Any]]:
    from scripts.reconcile_triple_annotation import (
        ANNOTATION, IMPLIED, SUPPORTED, WRONG, load_gap,
    )
    from src.extraction.entropy_gate import _copular_event_rejected
    from src.extraction.verifier import BAND_HI, BAND_LO, verify_triples
    from src.extraction.verbalise import verbalise
    from src.extraction.verifier import _get_verifier

    from scripts.reconcile_triple_annotation import GAP as _GAP, UNIFORM_GAP
    if draft is None:
        draft = DRAFT
    if gaps is None:
        gaps = [_GAP]
    rows = [json.loads(l) for l in
            draft.read_text(encoding="utf-8").splitlines() if l.strip()]
    verdicts = {(s, a, p, o): v for s, i, a, p, o, v in ANNOTATION}
    for g in load_gap(gaps):
        verdicts[(g["stratum"], g["s"], g["p"], g["o"])] = g["verdict"]

    counters: Dict[str, int] = {}
    for r in rows:
        counters[r["stratum"]] = counters.get(r["stratum"], 0) + 1
    indexed = {}
    seen: Counter = Counter()
    for r in rows:
        seen[r["stratum"]] += 1
        indexed[(r["stratum"], seen[r["stratum"]])] = r

    # Shadow model, loaded once. Only used when --shadow is passed; the
    # production path never consults it for auto-accepts.
    shadow_model = None
    if shadow:
        import numpy as np
        model, entail_idx, contra_idx = _get_verifier()
        shadow_model = (model, entail_idx, contra_idx)

    matrix = []
    for (stratum, idx), row in sorted(indexed.items()):
        text = row["text"]
        for t in row.get("asserted", []):
            key = (stratum, t["s"], t["p"], t["o"])
            v = verdicts.get(key)
            if v is None:
                state = "UNANNOTATED"
                shadow_margin = None
            elif _copular_event_rejected(
                    text, t["p"]):
                state = "structural_drop"
                shadow_margin = None
            else:
                conf = float(t.get("c") or 0.0)
                if conf > BAND_HI:
                    state = "auto_accept"
                    shadow_margin = None
                    if shadow_model is not None:
                        # Shadow only: what WOULD the verifier have said?
                        # Never changes the accept decision.
                        model, entail_idx, contra_idx = shadow_model
                        claim = verbalise(t["s"], t["p"], t["o"])
                        import numpy as np
                        logits = model.predict(
                            [[text, claim]], convert_to_numpy=True)
                        row_logits = np.atleast_2d(logits)[0]
                        shadow_margin = round(
                            float(row_logits[entail_idx])
                            - float(row_logits[contra_idx]), 4)
                elif conf < BAND_LO:
                    state = "floor_drop"
                    shadow_margin = None
                else:
                    accepted, _ = verify_triples(text, [{
                        "subject": t["s"], "predicate": t["p"],
                        "object": t["o"], "confidence": conf}])
                    state = ("verifier_accept" if accepted
                             else "verifier_drop")
                    shadow_margin = None
                    if accepted:
                        shadow_margin = accepted[0].get("verifier_margin")
            matrix.append({
                "stratum": stratum, "idx": idx,
                "s": t["s"], "p": t["p"], "o": t["o"],
                "confidence": t.get("c"),
                "verdict": v, "state": state,
                "shadow_margin": shadow_margin,
                "text": text[:90],
            })
    return matrix


def report(matrix: List[Dict[str, Any]]) -> Dict[str, Any]:
    from scripts.reconcile_triple_annotation import IMPLIED, SUPPORTED

    def _right(m):
        return m["verdict"] in (SUPPORTED, IMPLIED)

    states = Counter(m["state"] for m in matrix)
    assert sum(states.values()) == len(matrix), (
        f"matrix must partition all triples, got {dict(states)}")

    kept_states = ("verifier_accept", "auto_accept")
    kept = [m for m in matrix if m["state"] in kept_states]
    n_right = sum(1 for m in kept if _right(m))
    n_strict = sum(1 for m in kept
                   if m["verdict"] == SUPPORTED)

    print(f"=== pipeline matrix: {len(matrix)} triples, one state each ===")
    print(f"\n  {'state':18} {'n':>4} {'right':>6} {'wrong':>6}  95% CI")
    for state in list(STATES) + ["UNANNOTATED"]:
        n = states.get(state, 0)
        if not n:
            continue
        rows = [m for m in matrix if m["state"] == state]
        r = sum(1 for m in rows if _right(m))
        w = n - r - sum(1 for m in rows if m["verdict"] is None)
        # Wilson score interval for the precision of this path.
        import math
        z = 1.96
        p = r / n if n else 0.0
        denom = 1 + z * z / n if n else 1
        centre = (p + z * z / (2 * n)) / denom if n else 0.0
        half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
                if n else 0.0)
        print(f"  {state:18} {n:4} {r:6} {w:6}  "
              f"[{max(0.0, centre - half):.3f}-{min(1.0, centre + half):.3f}]")
    print(f"  {'kept':18} {len(kept):4} {n_right:6} {len(kept) - n_right:6}")
    print()
    print(f"  precision        {n_right / len(kept):.3f}   ({n_right}/{len(kept)})")
    print(f"  strict precision {n_strict / len(kept):.3f}   ({n_strict}/{len(kept)})")
    print(f"  retention        {len(kept) / len(matrix):.1%}   "
          f"({len(kept)}/{len(matrix)})")
    print()
    print("  baseline (no pipeline): stratified 0.441 / 0.297, "
          "uniform computed per draft -- see reconcile --set uniform")
    return {
        "total": len(matrix),
        "kept": len(kept),
        "precision": round(n_right / len(kept), 4) if kept else 0,
        "strict_precision": round(n_strict / len(kept), 4) if kept else 0,
        "by_state": {s: states.get(s, 0) for s in STATES},
        "matrix": matrix,
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="")
    ap.add_argument("--set", choices=["stratified", "uniform"], default="stratified")
    ap.add_argument("--shadow", action="store_true",
                    help="also run the verifier over auto-accepts and record "
                         "what it would have decided, without changing any "
                         "accept decision")
    args = ap.parse_args()

    if args.set == "uniform":
        from scripts.reconcile_triple_annotation import UNIFORM_GAP
        draft = ROOT / "docs" / "eval_triples_gold_locomo_uniform_model.jsonl"
        gaps = [UNIFORM_GAP]
        default_out = "docs/eval_pipeline_matrix_uniform.json"
    else:
        draft = DRAFT
        gaps = None
        default_out = ""

    matrix = await build_matrix(shadow=args.shadow, draft=draft, gaps=gaps)
    summary = report(matrix)

    if args.shadow:
        _report_shadow(matrix)

    if args.out:
        Path(args.out).write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


def _report_shadow(matrix: List[Dict[str, Any]]) -> None:
    """What the verifier would have done with the auto-accepts.

    Production path unchanged: every auto_accept stays accepted. This only
    records the counterfactual, broken down by confidence sub-band, so the
    next decision -- where to move the upper edge -- has evidence instead
    of a guess.
    """
    from scripts.reconcile_triple_annotation import IMPLIED, SUPPORTED
    from src.extraction.verifier import _ACCEPT_MARGIN

    autos = [m for m in matrix if m["state"] == "auto_accept"
             and m.get("shadow_margin") is not None]
    if not autos:
        print("\n  shadow: no auto-accepts scored (run with --shadow)")
        return

    print("\n  shadow verifier on auto-accepts (production unchanged):")
    print(f"    {'band':14} {'n':>3} {'verdict-right':>13} "
          f"{'would-drop':>11} {'would-keep':>11}  of dropped, right")
    for lo, hi, label in ((0.95, 0.97, "0.95-0.97"),
                          (0.97, 0.99, "0.97-0.99"),
                          (0.99, 1.01, "0.99-1.00")):
        sub = [m for m in autos if lo < float(m["confidence"]) <= hi]
        if not sub:
            continue
        right = sum(1 for m in sub
                    if m["verdict"] in (SUPPORTED, IMPLIED))
        drop = [m for m in sub
                if m["shadow_margin"] < _ACCEPT_MARGIN]
        keep = [m for m in sub
                if m["shadow_margin"] >= _ACCEPT_MARGIN]
        drop_right = sum(1 for m in drop
                         if m["verdict"] in (SUPPORTED, IMPLIED))
        print(f"    {label:14} {len(sub):3} {right:13} {len(drop):11} "
              f"{len(keep):11}  {drop_right} right would be lost")
    print("    (would-drop = margin below the accept bar; "
          "would-keep = at or above it)")


if __name__ == "__main__":
    raise SystemExit(__import__("asyncio").run(main()))
