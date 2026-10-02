"""Print the LoCoMo draft for hand annotation, grouped by stratum.

Reads the file the extractor already ran over, so each line shows the
asserted triples next to the sentence. Annotation is then: keep the triples
the sentence actually supports, and note the ones it does not. That gap is
the precision signal, and it is the only thing the gold is for.

Usage:
    python scripts/show_for_annotation.py --in docs/eval_triples_gold_locomo_draft_model.jsonl
    python scripts/show_for_annotation.py --in ... --stratum copular
    python scripts/show_for_annotation.py --in ... --only-contested
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--stratum", default="")
    ap.add_argument("--only-contested", action="store_true",
                    help="only sentences where several labels compete for the "
                         "same entity pair")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=0)
    args = ap.parse_args()

    p = Path(args.inp) if Path(args.inp).is_absolute() else ROOT / args.inp
    rows = [json.loads(l) for l in
            p.read_text(encoding="utf-8").splitlines() if l.strip()]

    if args.stratum:
        rows = [r for r in rows if r.get("stratum") == args.stratum]

    if args.only_contested:
        keep = []
        for r in rows:
            pairs = Counter(
                (t["s"].lower(), t["o"].lower()) for t in r.get("asserted", []))
            if any(n > 1 for n in pairs.values()):
                keep.append(r)
        rows = keep

    if args.start:
        rows = rows[args.start:]
    if args.count:
        rows = rows[: args.count]

    n_triples = sum(len(r.get("asserted", [])) for r in rows)
    print(f"{len(rows)} sentences, {n_triples} asserted triples "
          f"({n_triples / max(len(rows), 1):.2f} per sentence)\n")

    by_stratum: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_stratum.setdefault(r.get("stratum", "?"), []).append(r)

    for stratum in sorted(by_stratum):
        group = by_stratum[stratum]
        print(f"\n{'=' * 78}\n{stratum.upper()}  ({len(group)} sentences)\n"
              f"{'=' * 78}")
        for i, r in enumerate(group, 1):
            print(f"\n[{i:2}] {r['id']}")
            print(f"     {r['text']}")
            asserted = r.get("asserted", [])
            if not asserted:
                print("     -> no triples asserted")
                continue
            for t in asserted:
                flag = "" if t.get("label_ok", True) else "  !! LABEL UNREACHABLE"
                print(f"     -> {t['s']:26} -[{t['p']}]-> {t['o']:30} "
                      f"{t['c']:.3f}{flag}")
            # Surface competing labels on the same pair: those are the ones
            # where the annotation decision is genuinely hard.
            pairs: Dict[tuple, List[str]] = {}
            for t in asserted:
                pairs.setdefault((t["s"].lower(), t["o"].lower()), []).append(
                    t["p"])
            contested = {k: v for k, v in pairs.items() if len(v) > 1}
            if contested:
                for k, v in contested.items():
                    print(f"     ** same pair, competing labels: "
                          f"{'/'.join(sorted(set(v)))}")

    print(f"\n{'=' * 78}")
    print("Write the supported triples into triples[]. Anything asserted but")
    print("unsupported stays out -- that difference is the precision number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())