"""Build agency probe material deterministically (protocol v1).

16 pairs (4 per class R0-R3) x YES(provides)/NO(deny). Same frame within
pair; only the verb changes. Provider agency varies by class; theme domains
vary within class and are documented per item.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ITEMS = [
    ("R0", "The mentor", "pupils", "novels", "reading_material"),
    ("R0", "The doctor", "clients", "treatment", "medical_resource"),
    ("R0", "The usher", "guests", "leaflets", "information"),
    ("R0", "The baker", "neighbors", "bread", "food_resource"),
    ("R1", "The school", "pupils", "records", "information"),
    ("R1", "The clinic", "patients", "vaccines", "medical_resource"),
    ("R1", "The depot", "crews", "fuel", "physical_resource"),
    ("R1", "The center", "guests", "tours", "tour_service"),
    ("R2", "The server", "clients", "data", "information"),
    ("R2", "The dispenser", "patients", "pills", "medical_resource"),
    ("R2", "The pump", "fields", "water", "physical_resource"),
    ("R2", "The generator", "homes", "power", "energy_output"),
    ("R3", "The spring", "village", "water", "physical_resource"),
    ("R3", "The forest", "mill", "timber", "physical_resource"),
    ("R3", "The reef", "divers", "shelter", "protection_service"),
    ("R3", "The garden", "families", "herbs", "remedy_resource"),
]


def main() -> int:
    pairs = []
    for i, (cls, prov, rec, theme, dom) in enumerate(ITEMS, 1):
        pid = f"g{i:02d}"
        pairs.append({
            "pair_id": pid, "class": cls, "theme_domain": dom,
            "yes": {"sentence_id": pid + "yes",
                    "sentence": f"{prov} provides {rec} {theme}.",
                    "expected_provides": "YES",
                    "gold_provider": prov, "gold_recipient": rec,
                    "gold_theme": theme, "gold_relation": "provides",
                    "source_trigger": "provides",
                    "semantic_basis": "provision with varied provider agency",
                    "gold_candidate_expected": True},
            "no": {"sentence_id": pid + "no",
                   "sentence": f"{prov} denies {rec} {theme}.",
                   "expected_provides": "NO",
                   "gold_provider": prov, "gold_recipient": rec,
                   "gold_theme": theme, "gold_relation": "none",
                   "source_trigger": "deny",
                   "semantic_basis": "control: denial, no provision",
                   "gold_candidate_expected": False}})
    out = {"version": "candidate_agency_material_v1",
           "status": "built_by_script (validation + freeze are separate steps)",
           "date": "2026-10-04",
           "protocol": "docs/candidate_agency_probe_v1.json",
           "builder": "scripts/build_agency_material.py",
           "pairs": pairs}
    (ROOT / "docs" / "candidate_agency_material_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"pairs: {len(pairs)}, sentences: {2 * len(pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
