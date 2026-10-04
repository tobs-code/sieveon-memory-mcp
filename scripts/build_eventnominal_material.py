"""Build event-nominal probe material deterministically (protocol v1).

16 pairs (4 per class E0-E3) x YES(supports)/NO(deny). Same provider and
frame within pair; only the verb changes. Target types vary by class.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ITEMS = [
    ("E0", "entity", "The foundation", "the museum", "museum_support"),
    ("E0", "entity", "The city", "the library", "library_support"),
    ("E0", "entity", "The company", "the school", "school_support"),
    ("E0", "entity", "The club", "the park", "park_support"),
    ("E1", "event_nominal", "The foundation", "the renovation", "renovation_support"),
    ("E1", "event_nominal", "The archive", "the digitization", "digitization_support"),
    ("E1", "event_nominal", "The trust", "the restoration", "restoration_support"),
    ("E1", "event_nominal", "The board", "the expansion", "expansion_support"),
    ("E2", "event_nominal_of", "The foundation", "the renovation of the museum", "museum_renovation_support"),
    ("E2", "event_nominal_of", "The donors", "the digitization of the records", "records_digitization_support"),
    ("E2", "event_nominal_of", "The trust", "the restoration of the theater", "theater_restoration_support"),
    ("E2", "event_nominal_of", "The council", "the expansion of the hospital", "hospital_expansion_support"),
    ("E3", "result_nominal", "The foundation", "the renovated museum", "renovated_museum_support"),
    ("E3", "result_nominal", "The donors", "the digitized records", "digitized_records_support"),
    ("E3", "result_nominal", "The trust", "the restored theater", "restored_theater_support"),
    ("E3", "result_nominal", "The council", "the expanded hospital", "expanded_hospital_support"),
]


def main() -> int:
    pairs = []
    for i, (cls, ttype, prov, targ, sem) in enumerate(ITEMS, 1):
        pid = f"en{i:02d}"
        pairs.append({
            "pair_id": pid, "class": cls, "target_type": ttype,
            "semantic_subtype": sem,
            "yes": {"sentence_id": pid + "yes",
                    "sentence": f"{prov} supports {targ}.",
                    "expected_provides": "YES",
                    "provider": prov, "recipient": targ,
                    "lexical_trigger": "supports",
                    "argument_frame": "transitive"},
            "no": {"sentence_id": pid + "no",
                   "sentence": f"{prov} denies {targ}.",
                   "expected_provides": "NO",
                   "provider": prov, "recipient": targ,
                   "lexical_trigger": "deny",
                   "argument_frame": "transitive"}})
    out = {"version": "candidate_eventnominal_material_v1",
           "status": "draft_for_review (NOT frozen, NO generator run)",
           "date": "2026-10-04",
           "protocol": "docs/candidate_eventnominal_probe_v1.json",
           "builder": "scripts/build_eventnominal_material.py",
           "pairs": pairs}
    (ROOT / "docs" / "candidate_eventnominal_material_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"pairs: {len(pairs)}, sentences: {2 * len(pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
