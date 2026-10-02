"""What can be said about a gold-free set: volume, confidence, agreement.

Precision needs labels. Without them the only honest statements are about
the distribution of what the extractor produces -- how many triples per
sentence, how confident, how often several backends or label variants
compete for the same entity pair.

That last one is the useful signal without labels: when the model emits
`Charles Babbage -created-> Analytical Engine` and
`Charles Babbage -developed-> Analytical Engine` for the same pair, the
competing labels tell you the relation decision was not confident, whatever
the individual scores say.

Usage:
    python scripts/eval_triples_unlabelled.py
    python scripts/eval_triples_unlabelled.py --in docs/eval_triples_gold_locomo_uniform.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]


async def collect(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from src.extraction.entity_utils import extract_triples_with_relex

    out = []
    for row in rows:
        out.append({
            "text": row["text"],
            "stratum": row.get("stratum", "?"),
            "triples": extract_triples_with_relex(row["text"]),
        })
    return out


def analyse(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    all_triples = [t for r in records for t in r["triples"]]
    confs = [float(t.get("confidence") or 0.0) for t in all_triples]

    # Competing labels on one entity pair: a pair the model cannot decide.
    by_pair: Dict[str, set] = {}
    for t in all_triples:
        key = (t["subject"].lower(), t["object"].lower())
        by_pair.setdefault(f"{key[0]}|{key[1]}", set()).add(t["predicate"])
    contested = {k: v for k, v in by_pair.items() if len(v) > 1}

    by_stratum: Dict[str, List[int]] = {}
    for r in records:
        by_stratum.setdefault(r["stratum"], []).append(len(r["triples"]))

    return {
        "sentences": len(records),
        "triples": len(all_triples),
        "per_sentence": len(all_triples) / max(len(records), 1),
        "silent_sentences": sum(1 for r in records if not r["triples"]),
        "confidence": {
            "min": min(confs) if confs else None,
            "median": statistics.median(confs) if confs else None,
            "mean": statistics.mean(confs) if confs else None,
            "max": max(confs) if confs else None,
        },
        "predicate_counts": Counter(t["predicate"] for t in all_triples).most_common(),
        "contested_pairs": len(contested),
        "contested_examples": [
            {"pair": k, "predicates": sorted(v)} for k, v in
            list(contested.items())[:12]
        ],
        "by_stratum": {
            k: {"n": len(v), "mean_triples": round(statistics.mean(v), 2)}
            for k, v in sorted(by_stratum.items())
        },
    }


def report(a: Dict[str, Any], label: str) -> None:
    print(f"\n=== {label} ===")
    print(f"  sentences            {a['sentences']}")
    print(f"  asserted triples     {a['triples']}  "
          f"({a['per_sentence']:.2f} per sentence)")
    print(f"  sentences with none  {a['silent_sentences']}")
    c = a["confidence"]
    if c["min"] is not None:
        print(f"  confidence           min {c['min']:.3f} "
              f"median {c['median']:.3f} mean {c['mean']:.3f} max {c['max']:.3f}")
    print(f"  contested pairs      {a['contested_pairs']}  "
          f"(same entities, several labels)")
    print("\n  predicate distribution:")
    for p, n in a["predicate_counts"]:
        print(f"    {p:14} {n:4}  {n / a['triples'] * 100:5.1f}%")
    print("\n  triples per stratum:")
    for k, v in a["by_stratum"].items():
        print(f"    {k:14} n={v['n']:3}  mean {v['mean_triples']:.2f}")
    if a["contested_examples"]:
        print("\n  contested pairs (the relation decision was not made):")
        for e in a["contested_examples"]:
            print(f"    {e['pair']:52} {'/'.join(e['predicates'])}")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", action="append", default=[],
                    help="jsonl with a 'text' field; repeatable")
    args = ap.parse_args()

    paths = [Path(p) if Path(p).is_absolute() else ROOT / p for p in args.inp]
    if not paths:
        paths = [ROOT / "docs" / "eval_triples_gold_locomo_draft.jsonl",
                 ROOT / "docs" / "eval_triples_gold_locomo_uniform.jsonl"]

    for p in paths:
        rows = [json.loads(l) for l in
                p.read_text(encoding="utf-8").splitlines() if l.strip()]
        records = await collect(rows)
        report(analyse(records), p.name)

    print("\nNone of this is precision. Volume, confidence spread and label")
    print("competition are measurable without labels; whether a triple is")
    print("right is not.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))