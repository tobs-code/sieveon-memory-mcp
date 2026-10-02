"""Build the counterfactual schema gold: what an extended vocabulary would score.

The production chain states 17 predicates, and 53 observed facts fall outside
it: 52 the annotators held out on scope grounds, plus `Deborah -received->
quote`, which was accepted as gold and is still unexpressible. Two questions
follow, and this script exists to keep them apart:

    schema gain     how many of those 53 become expressible at all
    extractor gain  how many of the newly expressible ones the unchanged
                    extractor actually produces

That second number is the one that decides whether extending the schema is
the intervention. Adding `owns` makes seven facts scorable; if the extractor
finds none of them, the schema was never the binding constraint.

Structure of the output file, per fact:

    original_status             schema_gap | accepted_gold_outside_vocab
    gap_predicate               the unexpressible relation as annotated
    counterfactual_family       analytical grouping, never a merge
    counterfactual_predicate    per-fact, explicit, usually identical
    current_scorable            false in this file, always
    counterfactual_scorable     true in this file, always

The current-schema baseline is not recomputed here and must not be
overwritten. It stays 26/44 in every downstream report, and this file is
read separately from the frozen gold.

Families are analytical groupings for reading the shape of the gap. They are
NOT vocabulary proposals and they do not merge relations: `near` does not
become `located_in`, `asked_for` does not become `asked_about`, `gifted`
does not become `acquired`. Every one of those distinctions was drawn during
annotation precisely because merging them would have inflated the gold.

Usage:
    python scripts/build_counterfactual_schema.py
    python scripts/build_counterfactual_schema.py --verify
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
GOLD_FILES = [
    ROOT / "docs" / "eval_recall_gold_pilot.jsonl",
    ROOT / "docs" / "eval_recall_gold_batch2.jsonl",
    ROOT / "docs" / "eval_recall_gold_expanded.jsonl",
]
OUT = ROOT / "docs" / "eval_recall_gold_counterfactual.jsonl"

# Analytical grouping of the observed gap relations. Membership is by
# observed gap predicate, never inferred from meaning: a relation is in this
# table only if an annotator wrote it into a schema_gap entry. Two
# consequences are deliberate. `near` sits in location rather than being
# folded into `located_in`, because an annotator ruled that normalisation
# out. `gifted` sits in interaction rather than acquisition, for the same
# reason.
FAMILY = {
    "possession": ["owns"],
    "event_participation": ["attended", "joined", "auditioned_for",
                            "performed_live_in", "toured_with", "pitched_to"],
    "conversation_interest": ["asked_about", "asked_for", "agrees_to",
                              "suggested_meeting_at", "suggests"],
    "location_motion": ["traveled_to", "visited", "near", "recommended"],
    "interaction_communication": ["sent", "shared", "gifted", "motivates",
                                  "took_on_trip"],
    "perception_media": ["watched"],
    "attribute_need": ["requires", "restored", "modified"],
    "social_role": ["parent_of", "noticed_by"],
    "achievement": ["earned", "drafted_by", "finished", "started"],
    "value_relation": ["alternative_to"],
    "acquisition_passive": ["received"],
    "body_position": ["sat_on"],
    "attempted": ["tried"],
}

FAMILY_NOTE = {
    "possession": "the corpus states possession constantly; the chain cannot",
    "event_participation": "events the person took part in, as distinct from "
                           "what they created",
    "conversation_interest": "asking and suggesting between people",
    "location_motion": "movement and spatial proximity. `near` is NOT "
                       "`located_in`: an annotator ruled that out explicitly",
    "interaction_communication": "transfers between people. `gifted` is NOT "
                                 "`acquired`: giving says nothing about "
                                 "prior acquisition",
    "perception_media": "media consumption as an event",
    "attribute_need": "properties and requirements of objects",
    "social_role": "family and professional roles",
    "achievement": "earned and drafted states",
    "value_relation": "comparative statements between entities",
    "acquisition_passive": "receiving. Kept in its own family because "
                           "`received` was accepted as gold and is not "
                           "interchangeable with `acquired`",
}


def load_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for f in GOLD_FILES:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r["id"] not in seen:
                    seen.add(r["id"])
                    rows.append(r)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true",
                    help="check that every observed gap predicate has a "
                         "family, and exit nonzero if one does not")
    args = ap.parse_args()

    from scripts.eval_recall_harness import production_vocabulary
    vocab = production_vocabulary()

    rows = [r for r in load_rows() if r.get("graphable") is not None]
    records: List[Dict[str, Any]] = []
    for r in rows:
        for g in (r.get("schema_gap") or []):
            records.append({
                "id": r["id"], "s": g["s"], "p": g["p"], "o": g["o"],
                "original_status": "schema_gap",
                "current_scorable": False,
                "counterfactual_scorable": True,
            })
        for t in (r.get("triples") or []):
            if t[1] not in vocab:
                records.append({
                    "id": r["id"], "s": t[0], "p": t[1], "o": t[2],
                    "original_status": "accepted_gold_outside_vocab",
                    "current_scorable": False,
                    "counterfactual_scorable": True,
                })

    by_pred = Counter(r["p"] for r in records)
    fam_of: Dict[str, str] = {}
    for fam, preds in FAMILY.items():
        for p in preds:
            if p in by_pred:
                fam_of[p] = fam
    unmapped = sorted(p for p in by_pred if p not in fam_of)

    print("=== counterfactual schema: observed facts outside the chain ===\n")
    print(f"  annotated rows                {len(rows)}")
    print(f"  facts outside the vocabulary   {len(records)}")
    print(f"    schema_gap                   "
          f"{sum(1 for r in records if r['original_status'] == 'schema_gap')}")
    print(f"    accepted gold outside vocab  "
          f"{sum(1 for r in records if r['original_status'] != 'schema_gap')}")
    print(f"  distinct gap predicates        {len(by_pred)}")

    print("\n=== by family ===\n")
    print(f"  {'family':28} {'facts':>5} {'predicates':>10}")
    grouped = defaultdict(list)
    for p, fam in fam_of.items():
        grouped[fam].append(p)
    total_facts = 0
    for fam, preds in sorted(grouped.items(),
                             key=lambda kv: -sum(by_pred[p] for p in kv[1])):
        n = sum(by_pred[p] for p in preds)
        total_facts += n
        print(f"  {fam:28} {n:5} {len(preds):10}")
    print(f"  {'total mapped':28} {total_facts:5}")
    if unmapped:
        print(f"  {'UNMAPPED':28} {sum(by_pred[p] for p in unmapped):5}  "
              f"{', '.join(unmapped)}")

    print("\n=== families in full ===\n")
    for fam in sorted(grouped):
        preds = sorted(grouped[fam])
        print(f"  {fam}  ({FAMILY_NOTE.get(fam, '')})")
        for p in preds:
            print(f"    {p:22} {by_pred[p]}")

    if unmapped:
        print(f"\n  {len(unmapped)} gap predicates have no family. Add them "
              f"before scoring the\n  counterfactual; an unmapped predicate "
              f"would be silently unscored.")
        if args.verify:
            return 1
    elif args.verify:
        print("\n  every observed gap predicate has a family")

    if args.verify:
        return 0

    for r in records:
        r["counterfactual_family"] = fam_of.get(r["p"], "")
        r["counterfactual_predicate"] = r["p"]

    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                             for r in records) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(records)} facts)")
    print("  The current-schema baseline 26/44 is untouched by this file and "
          "keeps its\n  own denominator. Reading this file never changes it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())