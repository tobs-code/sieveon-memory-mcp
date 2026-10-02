"""Classify the vocabulary gaps: which relations the schema cannot express.

A vocabulary gap is a fact the sentence genuinely carries, which the
annotator accepted or identified as real, and which no extractor claim could
ever have matched because the production chain has no such relation. It is
a property of the schema, not of the extractor, so it must not be counted as
a model defect. It also must not be confused with the `schema_gap` entries
in the gold files: those are facts the annotator deliberately kept out of
`triples` because they do not belong to the current KG scope. Both are real
facts the chain cannot store; the annotation one is a choice about scope, the
audit one is a gap in the relations themselves.

The useful question is not how many gaps there are but where the relation
inventory is thin. This groups the gaps into semantic families so the
pattern is visible. The families are hand-assigned and deliberately coarse:
they are for reading the shape of the gap, not for proposing a schema.

Usage:
    python scripts/summarise_schema_gaps.py
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

from src.extraction.verbalise import CLAIM  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLD_FILES = [ROOT / "docs" / "eval_recall_gold_pilot.jsonl",
              ROOT / "docs" / "eval_recall_gold_batch2.jsonl"]

# Hand-assigned semantic families for relations the inventory lacks. The
# name is the family, not a proposal for what the relation should be called.
FAMILY = {
    "event_interaction": ["received", "sent", "attended", "gave", "offered"],
    "location_motion":   ["traveled_to", "lives_in", "moved_to", "visited"],
    "perception_media":  ["watched", "listened_to", "read"],
    "attribute_need":    ["requires", "needs", "consists_of", "has_property"],
    "conversation_interest": ["asked_about", "discussed", "inquired_about"],
    "assistance":        ["helped", "assisted", "supported_person"],
    "possession_use":    ["owns", "has", "uses_equipment"],
    "participation":     ["participated_in", "joined", "attended_event"],
}

FAMILY_LABEL = {
    "event_interaction": "event / interaction",
    "location_motion": "location / motion",
    "perception_media": "perception / media",
    "attribute_need": "attribute / requirement",
    "conversation_interest": "conversation / interest",
    "assistance": "assistance",
    "possession_use": "possession / use",
    "participation": "participation",
}


def load_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for f in GOLD_FILES:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["id"] not in seen:
                seen.add(r["id"])
                rows.append(r)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    rows = load_rows()
    vocab = set(CLAIM)

    # Two distinct populations, kept apart on purpose.
    annotator_scope: List[Dict[str, Any]] = []
    unexpressible: List[Dict[str, Any]] = []
    for r in rows:
        for g in (r.get("schema_gap") or []):
            annotator_scope.append(g)
        for t in (r.get("triples") or []):
            if t[1] not in vocab:
                unexpressible.append({"s": t[0], "p": t[1], "o": t[2],
                                      "source": "accepted as gold"})

    print("=== schema gaps: two populations ===\n")
    print(f"  annotator scope gaps   {len(annotator_scope)}  facts kept out "
          f"of triples on scope grounds")
    print(f"  unexpressible gold     {len(unexpressible)}  facts accepted as "
          f"gold, no relation exists")
    print(f"  total facts outside the production vocabulary: "
          f"{len(annotator_scope) + len(unexpressible)}")

    all_gaps = annotator_scope + unexpressible
    preds = Counter(g["p"] for g in all_gaps)

    print("\n=== axis 1: which relations are missing ===\n")
    print(f"  {'predicate':18} {'n':>3}  facts")
    for p, n in preds.most_common():
        facts = [g for g in all_gaps if g["p"] == p]
        ex = ", ".join(f'{g["s"]}->{g["o"]}' for g in facts)
        print(f"  {p:18} {n:3}  {ex[:64]}")

    print("\n=== axis 2: what kind of relation is missing ===\n")
    by_family: Dict[str, List[str]] = defaultdict(list)
    unmapped: List[str] = []
    for p in preds:
        fam = next((f for f, members in FAMILY.items() if p in members), None)
        if fam:
            by_family[fam].append(p)
        else:
            unmapped.append(p)
    print(f"  {'family':28} {'facts':>6}  predicates")
    total_facts = 0
    for fam, members in sorted(by_family.items(),
                               key=lambda kv: -sum(preds[m] for m in kv[1])):
        n = sum(preds[m] for m in members)
        total_facts += n
        print(f"  {FAMILY_LABEL[fam]:28} {n:6}  {', '.join(sorted(members))}")
    print(f"  {'unmapped':28} "
          f"{sum(preds[p] for p in unmapped):6}  "
          f"{', '.join(sorted(unmapped)) or 'none'}")
    print(f"  {'total':28} {total_facts:6}")

    print("\n=== the shape of the gap ===")
    fams = sorted(by_family, key=lambda f: -sum(preds[m] for m in by_family[f]))
    top = fams[0] if fams else None
    if top:
        n = sum(preds[m] for m in by_family[top])
        print(f"  Largest family: {FAMILY_LABEL[top]} ({n} facts). The "
              f"inventory is heavy on\n  creator and employment relations and "
              f"thin on relations that describe\n  events between people, "
              f"movement and needs. Every one of those\n  facts is available "
              f"to a reader and unavailable to the store.")
    print()
    print("  This is a schema finding. It is not evidence about the "
          "extractor, and\n  it must not be folded into a single quality "
          "number: extractor coverage\n  (scorable recall), predicate quality "
          "(clean vs imprecise) and schema\n  expressiveness (these gaps) are "
          "three separate axes.")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "annotator_scope_gaps": annotator_scope,
            "unexpressible_gold": unexpressible,
            "predicate_counts": dict(preds),
            "families": {FAMILY_LABEL[f]: sorted(m)
                         for f, m in by_family.items()},
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())