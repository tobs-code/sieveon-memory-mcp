"""Fill in the draft gold by running the extractor, for manual verification.

Writes the model's assertions alongside each sentence so they can be
checked. Nothing here is a label: the triples column stays the source of
truth and must be filled by a human. The point is to make labelling cheap --
reviewing the model's output is faster than extracting triples from scratch,
and it surfaces exactly the cases where the model's reading is questionable.

Usage:
    python scripts/annotate_triples_locomo.py --in docs/eval_triples_gold_locomo_draft.jsonl
    python scripts/annotate_triples_locomo.py --limit 10 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]


async def build(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from src.extraction.entity_utils import extract_triples_with_relex
    from scripts.audit_relation_labels import slug
    from src.extraction.entity_utils import _SIEVEON_RELATION_LABELS

    labels = {slug(l) for l in _SIEVEON_RELATION_LABELS}

    for i, row in enumerate(rows, 1):
        triples = extract_triples_with_relex(row["text"])
        row["asserted"] = [
            {
                "s": t.get("subject"),
                "p": t.get("predicate"),
                "o": t.get("object"),
                "c": round(float(t.get("confidence") or 0.0), 4),
                # Every asserted predicate must come from the inference label
                # list by construction, so this is a tripwire for a future
                # change that normalises labels after extraction.
                "label_ok": slug(str(t.get("predicate", ""))) in labels,
            }
            for t in triples
        ]
        print(f"  {i:3}/{len(rows)} {row['stratum']:12} "
              f"{len(row['asserted']):2} triples  {row['text'][:58]}")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = Path(args.inp)
    if not src.is_absolute():
        src = ROOT / src
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        rows = rows[: args.limit]

    rows = asyncio.run(build(rows))

    total = sum(len(r["asserted"]) for r in rows)
    print(f"\n{total} asserted triples over {len(rows)} sentences "
          f"({total / max(len(rows), 1):.2f} per sentence)")
    print(f"sentences with no assertion: "
          f"{sum(1 for r in rows if not r['asserted'])}")

    if args.dry_run:
        return 0

    out = Path(args.out) if args.out else src.with_name(src.stem + "_model.jsonl")
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {out}")
    print("triples[] is still null. Compare each asserted triple against the")
    print("sentence and write the ones that are actually supported, then move")
    print("them into triples[]. Anything asserted but unsupported stays out --")
    print("that gap is the precision signal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())