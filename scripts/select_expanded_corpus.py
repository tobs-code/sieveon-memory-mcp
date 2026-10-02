"""Draw the expanded-corpus sample for the recall gold.

The uniform population is 57 sentences and yields, so far, 20 gold facts.
Reaching ~100 needs about three to four times the corpus, and the sampling
rule has to exist before any gold is written. If sentences were drawn while
we already knew which ones look fact-dense, the resulting recall would no
longer describe the uniform population it is quoted next to.

So the rule here is mechanical and stated in full:

  1. Source: the same 10 LoCoMo conversations, observation sentences only.
     The 57 uniform sentences are excluded, and so is anything already
     annotated anywhere in docs/.
  2. Order: sort the pool by sentence id. The ids are
     conversation/session_observation/speaker/Dn:m, so sorting walks
     conversations in a fixed order and sessions in numeric order, with no
     reference to content.
  3. Take a contiguous window: every k-th sentence from the ordered pool,
     with k fixed here and not adjusted afterwards.

A regular stride rather than a random draw, so that adding or removing one
sentence never reshuffles the rest of the sample. It is reproducible from
this file alone: re-running it yields the same 100 sentences.

The stride is applied WITHIN each conversation, not across the pooled list.
Pooling and then taking every k-th looks simpler but is wrong here: ids sort
by conversation name as a string, so conv-26 comes first and its 179
sentences supply the first 15 slots, and 100 slots run out before the
eighth conversation is reached. Four conversations would have contributed
nothing, and any recall measured on that would be a statement about
Caroline and Melanie only. Striding within each conversation keeps all ten
present in proportion to their size.

The stratum is `expanded` and never merged into `uniform`. The two are
reported side by side and never pooled into a single recall figure.

Usage:
    python scripts/select_expanded_corpus.py
    python scripts/select_expanded_corpus.py --stride 20 --count 100
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
LOCOMO = ROOT / "_unused" / "locomo" / "data" / "locomo10.json"
OUT = ROOT / "docs" / "eval_recall_gold_expanded.jsonl"

DEFAULT_STRIDE = 12
DEFAULT_COUNT = 100

# Any sentence already present in these files is excluded, whatever file it
# lives in, so the expansion cannot quietly reuse pilot material.
EXCLUDE_SOURCES = [
    "docs/eval_triples_gold_locomo_uniform.jsonl",
    "docs/eval_triples_gold_locomo_draft.jsonl",
    "docs/eval_recall_gold_pilot.jsonl",
    "docs/eval_recall_gold_batch2.jsonl",
]


def session_key(k: str) -> Tuple[int, int]:
    m = re.search(r"session_(\d+)", k)
    return (int(m.group(1)) if m else 0, 0)


def build_pool() -> List[Dict[str, str]]:
    data = json.loads(LOCOMO.read_text(encoding="utf-8"))
    used = set()
    for rel in EXCLUDE_SOURCES:
        p = ROOT / rel
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                used.add(json.loads(line)["id"])

    pool: List[Dict[str, str]] = []
    for sample in data:
        for key, per_speaker in (sample.get("observation") or {}).items():
            if not key.endswith("_observation"):
                continue
            for speaker, items in per_speaker.items():
                for text, dia in items:
                    sid = "%s/%s/%s/%s" % (sample["sample_id"], key,
                                           speaker, dia)
                    if sid in used:
                        continue
                    pool.append({"id": sid, "text": text,
                                 "speaker": speaker,
                                 "sample_id": sample["sample_id"]})
    pool.sort(key=lambda r: (r["sample_id"], session_key(r["id"]), r["id"]))
    return pool


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    ap.add_argument("--count", type=int, default=DEFAULT_COUNT)
    ap.add_argument("--write", action="store_true",
                    help="write the annotation scaffold")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    pool = build_pool()

    # Stride within each conversation, not across the pooled list: a global
    # stride drains the alphabetically first conversation into the sample
    # and leaves the later ones empty.
    by_conv: Dict[str, List[Dict[str, str]]] = {}
    for r in pool:
        by_conv.setdefault(r["sample_id"], []).append(r)

    picked: List[Dict[str, str]] = []
    for conv in sorted(by_conv):
        picked.extend(by_conv[conv][::args.stride])

    # If the stride overshoots the requested size, thin evenly rather than
    # truncating, which would drop whole conversations again.
    if len(picked) > args.count:
        step = len(picked) / args.count
        picked = [picked[int(i * step)] for i in range(args.count)]

    from collections import Counter
    print(f"=== expanded corpus ===")
    print(f"  pool after exclusions   {len(pool)}")
    print(f"  conversations           {len(by_conv)}")
    print(f"  stride within each      {args.stride}")
    print(f"  selected                {len(picked)}")
    print(f"  stratum                 expanded (never pooled with uniform)")
    print()
    print("  per conversation:")
    share = Counter(r["sample_id"] for r in picked)
    for k, n in sorted(share.items()):
        avail = len(by_conv[k])
        print(f"    {k:10} {n:4}  (of {avail} available, "
              f"{n / len(picked):.0%} of the sample)")
    print()
    print("  The first 10 sentences, extractor output withheld:")
    for n, r in enumerate(picked[:10], start=1):
        print(f"    [{n:2}] {r['id']}")
        print(f"         {r['text'][:92]}")

    if args.write:
        out = Path(args.out) if args.out else OUT
        out.write_text("\n".join(
            json.dumps({"id": r["id"], "text": r["text"],
                        "graphable": None, "triples": None,
                        "excluded": [], "schema_gap": [],
                        "stratum": "expanded",
                        "sampling": {"stride": args.stride,
                                     "source": "locomo10 observation sentences",
                                     "position": n},
                        "by": "unannotated"}, ensure_ascii=False)
            for n, r in enumerate(picked)) + "\n", encoding="utf-8")
        print(f"\nwrote {out.relative_to(ROOT)} ({len(picked)} rows)")
    else:
        print("\n  To write the scaffold: add --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())