"""What would the unchanged extractor have produced if the chain could say it?

Read-only against frozen data. The counterfactual schema says these 53 facts
are expressible; the question here is whether the extractor that shipped
already produces them, or already produces something with the wrong
predicate. Nothing about the vocabulary, the gold or the matcher changes, and
the current-schema baseline keeps its own denominator.

A claim counts as found only when subject, predicate and object all match the
counterfactual predicate. A claim with the right entity pair but a different
predicate is counted as `discipline` and not as found, because that is the
defect the three-axis split exists to keep separate: letting it count here
would credit the schema for a discipline failure.

    current schema                26 / 44 = 0.591   unchanged, elsewhere
    counterfactual_scorable       53
    found                         claims the extractor already makes
    missed                        scorable in the counterfactual, absent
    discipline                    right entity pair, wrong predicate
    coverage of newly scorable    found / 53

That last number is the decision input. If the extractor already emits
`owns`, extending the schema is close to free. If it emits nothing, the
schema was never the binding constraint.

Usage:
    python scripts/eval_counterfactual_coverage.py
    python scripts/eval_counterfactual_coverage.py --out docs/eval_counterfactual.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
CF = ROOT / "docs" / "eval_recall_gold_counterfactual.jsonl"
CLAIMS = [
    ROOT / "docs" / "eval_triples_gold_locomo_uniform_model.jsonl",
    ROOT / "docs" / "eval_recall_claims_expanded.jsonl",
]


def load_claims() -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for f in CLAIMS:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out.setdefault(r["id"], []).extend(r.get("asserted", []))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    from scripts.eval_recall_harness import norm

    facts = [json.loads(l) for l in
             CF.read_text(encoding="utf-8").splitlines() if l.strip()]
    claims = load_claims()

    found: List[Dict[str, Any]] = []
    missed: List[Dict[str, Any]] = []
    discipline: List[Dict[str, Any]] = []

    for f in facts:
        cs = claims.get(f["id"], [])
        exact = any(norm(c["s"]) == norm(f["s"]) and norm(c["p"]) == norm(f["p"])
                    and norm(c["o"]) == norm(f["o"]) for c in cs)
        rec = {"id": f["id"], "s": f["s"], "p": f["p"], "o": f["o"],
               "family": f["counterfactual_family"],
               "status": f["original_status"]}
        if exact:
            found.append(rec)
            continue
        pair = [c for c in cs if norm(c["s"]) == norm(f["s"])
                and norm(c["o"]) == norm(f["o"])]
        if pair:
            rec["claimed_predicates"] = sorted({c["p"] for c in pair})
            discipline.append(rec)
        else:
            rec["claims_on_sentence"] = sorted(
                {c["p"] for c in cs})
            missed.append(rec)

    total = len(facts)
    print("=== counterfactual coverage: unchanged extractor, extended schema ===\n")
    print(f"  counterfactual_scorable        {total}")
    print(f"    schema_gap                   "
          f"{sum(1 for f in facts if f['original_status'] == 'schema_gap')}")
    print(f"    accepted gold outside vocab  "
          f"{sum(1 for f in facts if f['original_status'] != 'schema_gap')}")
    print()
    print(f"  {'bucket':14} {'n':>4}")
    for k, v in (("found", found), ("discipline", discipline),
                 ("missed", missed)):
        print(f"  {k:14} {len(v):4}")
    print()
    print(f"  coverage of newly scorable   {len(found) / total:.3f}   "
          f"({len(found)}/{total})")
    print()
    print("  A claim with the right entity pair but a different predicate is "
          "counted as\n  discipline, not found. Crediting the schema for it "
          "would conflate the two\n  defect classes this harness separates.")

    fam_tot: Dict[str, Counter] = defaultdict(Counter)
    for r in found:
        fam_tot[r["family"]]["found"] += 1
    for r in discipline:
        fam_tot[r["family"]]["discipline"] += 1
    for r in missed:
        fam_tot[r["family"]]["missed"] += 1

    print(f"\n  {'family':28} {'facts':>5} {'found':>6} {'disc':>5} "
          f"{'missed':>7} {'coverage':>9}")
    for fam in sorted(fam_tot, key=lambda k: -(sum(fam_tot[k].values()))):
        c = fam_tot[fam]
        n = sum(c.values())
        print(f"  {fam:28} {n:5} {c['found']:6} {c['discipline']:5} "
              f"{c['missed']:7} {c['found'] / n:9.3f}")

    pred_tot = Counter(f["p"] for f in facts)
    print(f"\n  {'predicate':22} {'facts':>5} {'found':>6} {'disc':>5} "
          f"{'missed':>7}")
    for p in sorted(pred_tot, key=lambda k: (-pred_tot[k], k)):
        sub = [r for r in found + discipline + missed if r["p"] == p]
        f_ = sum(1 for r in sub if r in found)
        d_ = sum(1 for r in sub if r in discipline)
        m_ = sum(1 for r in sub if r in missed)
        print(f"  {p:22} {len(sub):5} {f_:6} {d_:5} {m_:7}")

    if discipline:
        print("\n  discipline cases (right entity pair, wrong predicate):")
        for r in discipline:
            print(f"    {r['s']} -> {r['o']}: wanted {r['p']}, "
                  f"claimed {', '.join(r['claimed_predicates'])}")

    print("\n  Baseline for comparison, unchanged and in its own denominator:")
    print("    current schema  26 / 44 = 0.591")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "counterfactual_scorable": total,
            "found": len(found), "discipline": len(discipline),
            "missed": len(missed),
            "coverage_of_newly_scorable": round(len(found) / total, 4),
            "baseline_current_schema": {"found": 26, "scorable": 44,
                                       "recall": 0.591},
            "by_family": {k: dict(v) for k, v in fam_tot.items()},
            "detail": {"found": found, "discipline": discipline,
                       "missed": missed},
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())