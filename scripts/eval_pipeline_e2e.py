"""End-to-end pipeline measurement on the 118 annotated triples.

Applies the production path in order -- copular+event gate, then the NLI
verifier on the band -- and scores the survivors against the hand
annotation. This is the number the decision table needs in its Verifier
column, measured rather than projected.

Usage:
    python scripts/eval_pipeline_e2e.py
    python scripts/eval_pipeline_e2e.py --out docs/eval_pipeline_e2e.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    from scripts.reconcile_triple_annotation import (
        ANNOTATION, IMPLIED, SUPPORTED, WRONG, load_gap,
    )
    from src.extraction.entropy_gate import _copular_event_rejected
    from src.extraction.verifier import BAND_HI, BAND_LO, verify_triples

    rows = [json.loads(l) for l in
            (ROOT / "docs" / "eval_triples_gold_locomo_draft_model.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()]
    verdicts = {(s, a, p, o): v for s, i, a, p, o, v in ANNOTATION}
    for g in load_gap():
        verdicts[(g["stratum"], g["s"], g["p"], g["o"])] = g["verdict"]

    counters = {"gate": 0, "verifier": 0, "auto": 0, "floor": 0}
    kept: List[Dict[str, Any]] = []

    for r in rows:
        text = r["text"]
        for t in r.get("asserted", []):
            key = (r["stratum"], t["s"], t["p"], t["o"])
            v = verdicts.get(key)
            if v is None:
                continue
            triple = {"subject": t["s"], "predicate": t["p"],
                      "object": t["o"], "confidence": t["c"]}

            # Stage 1: structural gate.
            if _copular_event_rejected(text, triple["predicate"]):
                counters["gate"] += 1
                continue

            # Stage 2: verifier on the band, passthrough outside it.
            conf = triple["confidence"]
            if conf > BAND_HI:
                counters["auto"] += 1
                kept.append({**triple, "stage": "auto-accept", "verdict": v})
            elif conf < BAND_LO:
                counters["floor"] += 1
            else:
                accepted, _ = verify_triples(text, [triple])
                if accepted:
                    counters["verifier"] += 1
                    kept.append({**triple, "stage": "verifier",
                                 "verdict": v,
                                 "margin": accepted[0].get("verifier_margin")})
                # else: verifier-dropped, counted implicitly

    total = sum(1 for _ in kept) + counters["gate"]
    # verifier-dropped and floor-dropped are not in `kept`; reconstruct:
    dropped = 118 - len(kept) - 0  # all 118 were annotated
    # Actually count directly:
    n_kept = len(kept)
    n_right = sum(1 for k in kept if k["verdict"] in (SUPPORTED, IMPLIED))
    n_strict = sum(1 for k in kept if k["verdict"] == SUPPORTED)

    print("=== pipeline end-to-end (gates + verifier) ===")
    print(f"  triples in              {counters}")
    print(f"  triples kept            {n_kept}")
    print(f"  precision               {n_right / n_kept:.3f}   ({n_right}/{n_kept})")
    print(f"  strict precision        {n_strict / n_kept:.3f}   ({n_strict}/{n_kept})")
    print()
    print("  baseline (no pipeline): precision 0.441, strict 0.297")
    print()
    print("  kept by stage:")
    from collections import Counter
    stages = Counter(k["stage"] for k in kept)
    for stage, n in stages.items():
        print(f"    {stage:12} {n}")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "kept": kept,
            "precision": round(n_right / n_kept, 4) if n_kept else 0,
            "strict_precision": round(n_strict / n_kept, 4) if n_kept else 0,
        }, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(__import__("asyncio").run(main()))
