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


async def build_matrix() -> List[Dict[str, Any]]:
    from scripts.reconcile_triple_annotation import (
        ANNOTATION, IMPLIED, SUPPORTED, WRONG, load_gap,
    )
    from src.extraction.entropy_gate import _copular_event_rejected
    from src.extraction.verifier import BAND_HI, BAND_LO, verify_triples

    rows = [json.loads(l) for l in
            DRAFT.read_text(encoding="utf-8").splitlines() if l.strip()]
    verdicts = {(s, a, p, o): v for s, i, a, p, o, v in ANNOTATION}
    for g in load_gap():
        verdicts[(g["stratum"], g["s"], g["p"], g["o"])] = g["verdict"]

    counters: Dict[str, int] = {}
    for r in rows:
        counters[r["stratum"]] = counters.get(r["stratum"], 0) + 1
    indexed = {}
    seen: Counter = Counter()
    for r in rows:
        seen[r["stratum"]] += 1
        indexed[(r["stratum"], seen[r["stratum"]])] = r

    matrix = []
    for (stratum, idx), row in sorted(indexed.items()):
        text = row["text"]
        for t in row.get("asserted", []):
            key = (stratum, t["s"], t["p"], t["o"])
            v = verdicts.get(key)
            if v is None:
                state = "UNANNOTATED"
            elif _copular_event_rejected(
                    text, t["p"]):
                state = "structural_drop"
            else:
                conf = float(t.get("c") or 0.0)
                if conf > BAND_HI:
                    state = "auto_accept"
                elif conf < BAND_LO:
                    state = "floor_drop"
                else:
                    accepted, _ = verify_triples(text, [{
                        "subject": t["s"], "predicate": t["p"],
                        "object": t["o"], "confidence": conf}])
                    state = ("verifier_accept" if accepted
                             else "verifier_drop")
            matrix.append({
                "stratum": stratum, "idx": idx,
                "s": t["s"], "p": t["p"], "o": t["o"],
                "confidence": t.get("c"),
                "verdict": v, "state": state,
                "text": text[:90],
            })
    return matrix


def report(matrix: List[Dict[str, Any]]) -> Dict[str, Any]:
    from scripts.reconcile_triple_annotation import IMPLIED, SUPPORTED

    def _right(m):
        return m["verdict"] in (SUPPORTED, IMPLIED)

    states = Counter(m["state"] for m in matrix)
    assert sum(states.values()) == len(matrix) == 118, (
        f"matrix must partition all 118 triples, got {dict(states)}")

    kept_states = ("verifier_accept", "auto_accept")
    kept = [m for m in matrix if m["state"] in kept_states]
    n_right = sum(1 for m in kept if _right(m))
    n_strict = sum(1 for m in kept
                   if m["verdict"] == SUPPORTED)

    print("=== pipeline matrix: 118 triples, one state each ===")
    print(f"\n  {'state':18} {'n':>4} {'right':>6} {'wrong':>6}")
    for state in list(STATES) + ["UNANNOTATED"]:
        n = states.get(state, 0)
        if not n:
            continue
        rows = [m for m in matrix if m["state"] == state]
        r = sum(1 for m in rows if m["verdict"] in (SUPPORTED, IMPLIED))
        # UNANNOTATED rows have verdict None and are excluded from both.
        r = sum(1 for m in rows
                if m["verdict"] in (SUPPORTED, IMPLIED))
        w = sum(1 for m in rows if m["verdict"] == "wrong")
        print(f"  {state:18} {n:4} {r:6} {w:6}")
    print(f"  {'kept':18} {len(kept):4} {n_right:6} {len(kept) - n_right:6}")
    print()
    print(f"  precision        {n_right / len(kept):.3f}   ({n_right}/{len(kept)})")
    print(f"  strict precision {n_strict / len(kept):.3f}   ({n_strict}/{len(kept)})")
    print(f"  retention        {len(kept) / len(matrix):.1%}   "
          f"({len(kept)}/{len(matrix)})")
    print()
    print("  baseline (no pipeline): precision 0.441, strict 0.297")
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
    args = ap.parse_args()

    matrix = await build_matrix()
    summary = report(matrix)
    if args.out:
        Path(args.out).write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(__import__("asyncio").run(main()))
