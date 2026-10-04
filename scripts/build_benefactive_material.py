"""Build benefactive probe material deterministically (protocol v1).

4 sets x 4 conditions (T0-T3) x YES/NO with deny-family controls.
Same provider/beneficiary/benefit within set; only construction/role model
(and the YES verb where the construction requires it) varies.
T3-NO keeps the positive purpose clause by design (documented oddness:
negated provision retaining positive purpose); the candidate stage is
assertion-blind so measurement is unaffected.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SETS = {
    "med": {"P": "clinic", "B": "patients", "T": "medication",
            "purpose": "so that patients recover"},
    "fuel": {"P": "depot", "B": "units", "T": "fuel",
             "purpose": "so that units operate"},
    "badge": {"P": "clerk", "B": "visitors", "T": "badges",
              "purpose": "so that visitors enter"},
    "lesson": {"P": "tutor", "B": "students", "T": "lessons",
               "purpose": "so that students learn"},
}

CONDITIONS = {
    "T0": {"verb_yes": "provides", "verb_no": "denies",
           "basis_yes": "direct transfer provision",
           "tpl": "The {P} {v} {T} to {B}."},
    "T1": {"verb_yes": "provides", "verb_no": "refuses",
           "basis_yes": "benefactive-for provision",
           "tpl": "The {P} {v} {T} for {B}."},
    "T2": {"verb_yes": "secures", "verb_no": "withholds",
           "basis_yes": "procurement-for provision",
           "tpl": "The {P} {v} {T} for {B}."},
    "T3": {"verb_yes": "provides", "verb_no": "denies",
           "basis_yes": "purpose-oriented provision",
           "tpl": "The {P} {v} {T} {purpose}."},
}


def main() -> int:
    pairs = []
    for set_id, s in SETS.items():
        for cond, c in CONDITIONS.items():
            y = c["tpl"].format(P=s["P"], v=c["verb_yes"], T=s["T"],
                                B=s["B"], purpose=s["purpose"])
            n = c["tpl"].format(P=s["P"], v=c["verb_no"], T=s["T"],
                                B=s["B"], purpose=s["purpose"])
            pid = f"{cond.lower()}{set_id}"
            pairs.append({
                "pair_id": pid, "construction": cond, "set": set_id,
                "yes": {"sentence_id": pid + "yes", "sentence": y,
                        "expected_provides": "YES",
                        "gold_provider": "The " + s["P"],
                        "gold_target": s["T"],
                        "gold_relation": "provides",
                        "source_trigger": c["verb_yes"],
                        "semantic_basis": c["basis_yes"],
                        "construction": cond,
                        "gold_candidate_expected": True,
                        "expected_outcome": "CANDIDATE_PRESENT"},
                "no": {"sentence_id": pid + "no", "sentence": n,
                       "expected_provides": "NO",
                       "gold_provider": "The " + s["P"],
                       "gold_target": s["T"],
                       "gold_relation": "none",
                       "source_trigger": c["verb_no"],
                       "semantic_basis": "control: denial, no provision",
                       "construction": cond,
                       "gold_candidate_expected": False,
                       "expected_outcome": "NO_CANDIDATE"}})
    out = {"version": "candidate_benefactive_material_v1",
           "status": "frozen_for_probe (validated; t0med YES shares surface with probe01b: cross-probe calibration, not independent evidence)",
           "calibration_note": "t0med YES 'The clinic provides medication to patients.' duplicates probe01b surface; report T0 with and without med",
           "date": "2026-10-04",
           "protocol": "docs/candidate_benefactive_probe_v1.json",
           "builder": "scripts/build_benefactive_material.py",
           "pairs": pairs}
    (ROOT / "docs" / "candidate_benefactive_material_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"pairs: {len(pairs)}, sentences: {2 * len(pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
