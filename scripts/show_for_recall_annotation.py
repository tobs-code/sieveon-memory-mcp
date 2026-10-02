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

# The pilot spread across the uniform sample on purpose: sentences where the
# extractor claimed a lot, where it claimed one over-reaching creator triple,
# and where it claimed nothing. A pilot drawn only from claimed sentences
# would measure recall on the easy cases and precision on nothing.
PILOT_INDICES = [1, 2, 3, 5, 8, 9, 11, 12, 13, 15, 18, 20, 26, 28, 38, 47,
                 50, 53, 54, 57]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=len(PILOT_INDICES))
    ap.add_argument("--all", action="store_true",
                    help="show the whole uniform sample instead of the pilot")
    args = ap.parse_args()

    rows = [json.loads(l) for l in
            SOURCE.read_text(encoding="utf-8").splitlines() if l.strip()]

    if args.all:
        picked: List[Dict[str, Any]] = list(enumerate(rows, start=1))
    else:
        picked = [(i, rows[i - 1]) for i in PILOT_INDICES[:args.count]]

    print(f"{len(picked)} sentences for gold annotation "
          f"(extractor output withheld)")
    print("Note the position number below is a PILOT position, not the "
          "sentence's index\nin the uniform sample. They coincide only for "
          "the first entries. Quote the sentence\ntext when reporting gold "
          "so the two cannot be confused again.\n")
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