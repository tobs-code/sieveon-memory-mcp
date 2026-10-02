"""Blind annotation view for the recall harness.

This view deliberately does NOT print what the extractor asserted. A
gold-first annotation is the whole point: if the annotator sees the model
claims first they will quietly mark the model's output as the gold, and
the resulting recall number will be an artefact of that exposure. The
precision side of this evaluation already has its data; the missing half
is which facts should have been found at all.

Annotate the facts the sentence actually entails and that belong in a
knowledge graph, then canonicalise them to triples:

    Maria volunteers at a homeless shelter.
    -> ["Maria", "works_at", "homeless shelter"]

Not everything in a sentence is a fact worth storing. "Audrey is
thankful" is a state of mind, not a triple. If a sentence entails no
graphable fact, write [] -- an empty gold list is a real answer and is
what makes a spurious-claim count meaningful.

The predicate vocabulary is the same one the extractor emits. Using a
different, richer vocabulary would measure the matcher rather than the
extractor.

Output goes to a separate file. The extractor claims live in their own
file and are only joined at scoring time.

Usage:
    python scripts/show_for_recall_annotation.py
    python scripts/show_for_recall_annotation.py --count 18
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "eval_triples_gold_locomo_uniform_model.jsonl"
OUT = ROOT / "docs" / "eval_recall_gold_pilot.jsonl"
BATCH2 = ROOT / "docs" / "eval_recall_gold_batch2.jsonl"

# The pilot's 20 sentences. Frozen: these are annotated and confirmed, and
# scaling must not touch them.
PILOT_INDICES = [1, 2, 3, 5, 8, 9, 11, 12, 13, 15, 18, 20, 26, 28, 38, 47,
                 50, 53, 54, 57]


def remaining(rows: List[Dict[str, Any]]) -> List[int]:
    """Uniform-sample indices not yet in the pilot, in order."""
    return [i for i in range(1, len(rows) + 1) if i not in set(PILOT_INDICES)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=len(PILOT_INDICES))
    ap.add_argument("--all", action="store_true",
                    help="show the whole uniform sample instead of the pilot")
    ap.add_argument("--batch2", action="store_true",
                    help="show the sentences not yet in the pilot, i.e. the "
                         "scaling batch, and write the scaffold file")
    ap.add_argument("--offset", type=int, default=0,
                    help="skip the first N sentences of the selected batch")
    ap.add_argument("--from-scaffold", type=Path, default=None,
                    help="print these sentences in this file's order, so the "
                         "position numbers match the scaffold being filled in")
    args = ap.parse_args()

    if args.from_scaffold:
        picked = []
        for n, line in enumerate(args.from_scaffold.read_text(
                encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            r = json.loads(line)
            picked.append((n, {"id": r["id"], "text": r["text"]}))
        picked = picked[args.offset:args.offset + args.count]
        label = f"scaffold order: {args.from_scaffold.name}"
        picked_out = picked
    else:
        rows = [json.loads(l) for l in
                SOURCE.read_text(encoding="utf-8").splitlines() if l.strip()]
        if args.all:
            picked = list(enumerate(rows, start=1))
            label = "full uniform sample"
        elif args.batch2:
            rest = remaining(rows)
            picked = [(i, rows[i - 1]) for i in rest]
            label = f"scaling batch: {len(picked)} remaining sentences"
            BATCH2.write_text("\n".join(
                json.dumps({"id": r["id"], "text": r["text"],
                            "graphable": None, "triples": None,
                            "excluded": [], "schema_gap": [],
                            "by": "unannotated"},
                           ensure_ascii=False) for _, r in picked) + "\n",
                encoding="utf-8")
            print(f"wrote scaffold {BATCH2.relative_to(ROOT)} "
                  f"({len(picked)} rows, extractor output withheld)\n")
        else:
            picked = [(i, rows[i - 1]) for i in PILOT_INDICES[:args.count]]
            label = "frozen pilot"
        picked_out = picked[args.offset:args.offset + args.count]

    picked = picked_out

    print(f"{label}: showing {len(picked)}\n")
    print("Note the position number below is a position in this batch, not "
          "the sentence's index\nin the uniform sample. Quote the sentence "
          "text when reporting gold so the two\ncannot be confused again.\n")
    for n, (_, r) in enumerate(picked, start=1):
        print(f"[{n:2}] {r['id']}")
        print(f"     {r['text']}")
        print(f'     -> []')
        print()

    print("Fill triples by hand, then:")
    print(f"  python scripts/eval_recall_harness.py "
          f"--gold {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())