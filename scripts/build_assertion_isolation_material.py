"""Select assertion-isolation items from FROZEN probe materials (no new sentences).

Every item is an extractor-confirmed gold pair (L1 known-good from a previous
probe run). Conditions are assigned from the frozen material's documented
semantic_subtype/target_type BEFORE any validator call. No surface authorin.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# semantic frame of the provision, derived from the frozen label only
SUPPORT_FRAMING = {
    "hospitality_provision", "favor_service", "wage_service", "tip_service",
    "hospital_support", "museum_support", "library_support", "school_support",
    "park_support", "digitization_support", "restoration_support",
    "expansion_support", "museum_renovation_support",
    "records_digitization_support", "theater_restoration_support",
    "hospital_expansion_support", "renovated_museum_support",
    "digitized_records_support", "restored_theater_support",
    "expanded_hospital_support", "skill_instruction", "access_display",
    "grant_provision", "housing_provision",
}
NON_SUPPORT_FRAMING = {
    "medical_provision", "fuel_supply", "book_provision",
    "training_provision", "tutoring_provision", "art_provision",
    "parcel_transfer", "badge_transfer", "permission_transfer",
    "budget_transfer", "award_transfer", "gift_procurement",
    "towel_service", "meal_service", "plot_resource", "produce_resource",
    "key_issuance", "shift_function", "fee_refund", "parts_supply",
    "lesson_provision",
}


def gold_of(s):
    for pk, rk in (("provider", "recipient"), ("gold_provider", "gold_recipient")):
        if pk in s:
            return s[pk], s.get(rk, "")
    toks = s["sentence"].split()
    return " ".join(toks[:2]), toks[3]


def condition(subtype):
    if subtype in SUPPORT_FRAMING:
        return "SUPPORT_FRAMING"
    if subtype in NON_SUPPORT_FRAMING:
        return "NON_SUPPORT_FRAMING"
    return None


def add(items, sid, sentence, subtype, prov, rec, source, is_no=False):
    cond = condition(subtype)
    if cond is None and not is_no:
        return
    items.append({
        "item_id": f"{sid}" + ("_no" if is_no else ""),
        "sentence": sentence,
        "gold_triple": [prov, "provides", rec],
        "condition": "NEGATIVE_DENY" if is_no else cond,
        "semantic_subtype": subtype,
        "source_probe": source,
        "extractor_gold_match": not is_no,
    })


def main() -> int:
    items = []

    def load(f):
        return json.load(open(ROOT / "docs" / f, encoding="utf-8"))

    # lexical probe (NO mirrors use deny)
    for p in load("candidate_lexical_material_v1.json")["pairs"]:
        y = p["yes"]
        add(items, y["sentence_id"], y["sentence"], p["semantic_subtype"],
            *gold_of(y), "lexical:" + p["pair_id"])
        n = p["no"]
        add(items, n["sentence_id"], n["sentence"], p["semantic_subtype"],
            *gold_of(n), "lexical:" + p["pair_id"], is_no=True)

    # event-nominal probe
    for p in load("candidate_eventnominal_material_v1.json")["pairs"]:
        y = p["yes"]
        add(items, y["sentence_id"], y["sentence"], p["semantic_subtype"],
            *gold_of(y), "eventnominal:" + p["pair_id"])

    # recipient probe (OVERT variants)
    for p in load("candidate_recipient_material_v1.json")["pairs"]:
        y = p["yes"]
        add(items, y["sentence_id"], y["sentence"], "access_display",
            *gold_of(y), "recipient:" + p["pair_id"])

    # batch6 known gold matches (the motivating cases)
    run = [json.loads(l) for l in open(
        ROOT / "docs" / "production_run_v6.jsonl", encoding="utf-8")
        if l.strip()]
    for r in run:
        if r.get("candidate_status") != "candidate":
            continue
        if r["sentence_id"] in ("prodc6-005", "prodc6-033", "prodc6-149",
                                "prodc6-129"):
            items.append({
                "item_id": r["sentence_id"],
                "sentence": r["text"],
                "gold_triple": [r["subject_mention"], "provides",
                                r["object_mention"]],
                "condition": ("NON_SUPPORT_FRAMING"
                              if r["sentence_id"] in ("prodc6-005",
                                                      "prodc6-033")
                              else ("MODAL" if r["sentence_id"] == "prodc6-149"
                                    else "SUPPORT_FRAMING")),
                "semantic_subtype": "batch6_known_gold_match",
                "source_probe": "batch6:" + r["sentence_id"],
                "extractor_gold_match": True,
                "prior_assertion_status": r["assertion_status"],
            })

    out = {"version": "assertion_isolation_material_v1",
           "status": "built_by_script (validation + freeze are separate steps)",
           "date": "2026-10-04",
           "protocol": "docs/assertion_isolation_probe_v1.json",
           "builder": "scripts/build_assertion_isolation_material.py",
           "note": "conditions assigned from frozen labels only; L1 known-good; "
                   "no new sentences",
           "items": items}
    (ROOT / "docs" / "assertion_isolation_material_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    import collections
    print("items:", len(items), dict(collections.Counter(
        i["condition"] for i in items)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())