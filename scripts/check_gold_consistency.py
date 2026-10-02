"""Do the two gold files agree about severity on the sentences they share?

Two golds exist and they answer different questions:

  docs/eval_triples_gold_locomo_uniform_model.jsonl
      scores claims the extractor made. Its verdict classes (supported /
      implied / wrong) judge whether a specific predicate is licensed by the
      sentence. It is authoritative for precision.

  docs/eval_recall_gold_pilot.jsonl
      enumerates the facts the sentence carries, independent of what was
      claimed. Authoritative for coverage.

Both were written by hand and they share 20 sentences. On 14 of the shared
facts they agree; on 6 they do not, always in the same direction: they
disagree about severity, never about whether the fact exists. That is
reassuring for coverage and a trap for any number that mixes the two
severity scales.

This script recomputes the comparison so it can be rerun after each
annotation round. Divergences are NOT auto-fixed: some are deliberate and
fixing them silently would destroy the audit trail.

Usage:
    python scripts/check_gold_consistency.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
TRIPLE_VERDICTS = ROOT / "docs" / "eval_triples_annotation_uniform.jsonl"
RECALL_GOLD = [ROOT / "docs" / "eval_recall_gold_pilot.jsonl",
               ROOT / "docs" / "eval_recall_gold_batch2.jsonl"]

# Severity on the two scales. Recall gold has no `wrong`: a fact that is not
# gold is either held out as below threshold or absent, so `wrong` maps onto
# "not gold" rather than onto a severity.
RECALL_SEVERITY = {
    ("clean", "gold"): "supported",
    ("imprecise", "gold"): "implied",
}


def load() -> Tuple[Dict[Tuple[str, str, str], str], List[Dict[str, Any]]]:
    verdicts: Dict[Tuple[str, str, str], str] = {}
    for line in TRIPLE_VERDICTS.read_text(encoding="utf-8").splitlines():
        if line.strip():
            g = json.loads(line)
            verdicts[(g["s"], g["p"], g["o"])] = g["verdict"]
    rows = []
    seen = set()
    for f in RECALL_GOLD:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r["id"] not in seen:
                    seen.add(r["id"])
                    rows.append(r)
    return verdicts, rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()
    verdicts, rows = load()

    identical: List[str] = []
    severity: List[str] = []
    scope: List[str] = []
    gaps: List[str] = []
    unseen: List[str] = []

    for r in rows:
        entries: List[Tuple[Tuple[str, str, str], str]] = [
            ((t[0], t[1], t[2]), "gold") for t in (r.get("triples") or [])]
        entries += [((e["s"], e["p"], e["o"]), "excluded")
                    for e in (r.get("excluded") or [])]
        entries += [((g["s"], g["p"], g["o"]), "schema_gap")
                    for g in (r.get("schema_gap") or [])]
        for key, role in entries:
            v = verdicts.get(key)
            line = f"{key[0]} -{key[1]}-> {key[2]}"
            if role == "schema_gap":
                gaps.append(line)
                continue
            if v is None:
                unseen.append(f"{line}  ({role}, extractor never claimed it)")
                continue
            # An `excluded` fact that the triple file calls `wrong` or
            # `implied` agrees: both files decline to treat it as gold.
            if role == "excluded":
                (scope if v in ("wrong", "implied") else severity).append(
                    f"{line}  triple={v}, recall=below_threshold")
                continue
            flag = "imprecise" if len_of(r, key) else "clean"
            want = RECALL_SEVERITY[(flag, "gold")]
            (identical if v == want else severity).append(
                f"{line}  triple={v}, recall={flag}")

    print("=== gold consistency: shared sentences ===")
    print(f"  identical              {len(identical)}")
    print(f"  severity divergence    {len(severity)}")
    print(f"  scope agreement        {len(scope)}")
    print(f"  schema gap             {len(gaps)}")
    print(f"  never claimed          {len(unseen)}")
    print()
    print("  severity divergences (same fact, different strength):")
    for s in severity:
        print(f"    {s}")
    print()
    print("  scope agreements (held out of gold by the recall file, "
          "not called supported\n  by the triple file):")
    for s in scope:
        print(f"    {s}")
    print()
    print("  never claimed (absent from the extractor output, so no verdict):")
    for s in unseen:
        print(f"    {s}")
    print()
    print("  schema gap (annotator kept out of triples on scope grounds):")
    for s in gaps:
        print(f"    {s}")
    print()
    print("  Severity divergences are not auto-fixed. Where the recall file")
    print("  marks a fact clean that the triple file calls implied, the")
    print("  scorable-clean recall figure is the optimistic one; where it")
    print("  marks one imprecise that the triple file called supported, the")
    print("  figure is the pessimistic one. Both files answer different")
    print("  questions -- see docs/eval_recall_harness.md.")
    return 0


def len_of(row: Dict[str, Any], key: Tuple[str, str, str]) -> bool:
    for t in (row.get("triples") or []):
        if (t[0], t[1], t[2]) == key:
            return len(t) > 3
    return False


if __name__ == "__main__":
    raise SystemExit(main())