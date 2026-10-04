"""Build Phase D anaphora probe material deterministically (protocol v1).

7 conditions x 4 subtypes x YES/NO. Triplets reused from Phase C.
D4-D6 inputs are multi-sentence contexts fed to the generator as one string.
Pairs differ only in provide/deny. No other pronouns besides it/them.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SUBTYPES = {
    "med": {"P": "clinic", "R": "patients", "T": "medication",
            "ctx_p": "The clinic opened a new pharmacy.",
            "ctx_r": "The patients arrived at the clinic.",
            "ctx_both2": "The patients arrived later."},
    "fuel": {"P": "depot", "R": "units", "T": "fuel",
             "ctx_p": "The depot opened a new terminal.",
             "ctx_r": "The units arrived at the depot.",
             "ctx_both2": "The units arrived later."},
    "badge": {"P": "clerk", "R": "visitors", "T": "badges",
              "ctx_p": "The clerk opened a new desk.",
              "ctx_r": "The visitors arrived at the desk.",
              "ctx_both2": "The visitors arrived later."},
    "lesson": {"P": "tutor", "R": "students", "T": "lessons",
               "ctx_p": "The tutor opened a new course.",
               "ctx_r": "The students arrived at the hall.",
               "ctx_both2": "The students arrived later."},
}


def target(sub, cond, verb):
    P, R, T = f"The {sub['P']}", sub["R"], sub["T"]
    if cond == "D0":
        return f"{P} {verb} {R} {T}."
    if cond == "D1":
        return f"{P} {verb} them {T}."
    if cond == "D2":
        return f"It {verb} {R} {T}."
    if cond == "D3":
        return f"It {verb} them {T}."
    if cond == "D4":
        return f"{sub['ctx_p']} It {verb} {R} {T}."
    if cond == "D5":
        return f"{sub['ctx_r']} {P} {verb} them {T}."
    if cond == "D6":
        return f"{sub['ctx_p']} {sub['ctx_both2']} It {verb} them {T}."
    raise ValueError(cond)


def main() -> int:
    pairs = []
    for sub_id, sub in SUBTYPES.items():
        for cond in ("D0", "D1", "D2", "D3", "D4", "D5", "D6"):
            y = target(sub, cond, "provides")
            n = target(sub, cond, "denies")
            pid = f"{cond.lower()}{sub_id}"
            pairs.append({
                "pair_id": pid, "condition": cond, "subtype": sub_id,
                "yes": {"sentence_id": pid + "yes", "sentence": y,
                        "expected_provides": "YES",
                        "provider_surface": None if cond in ("D2", "D3", "D6")
                        else "The " + sub["P"],
                        "recipient_surface": None if cond in ("D1", "D3", "D5", "D6")
                        else sub["R"],
                        "provider": "The " + sub["P"], "recipient": sub["R"],
                        "lexical_trigger": "provide"},
                "no": {"sentence_id": pid + "no", "sentence": n,
                       "expected_provides": "NO",
                       "provider": "The " + sub["P"], "recipient": sub["R"],
                       "lexical_trigger": "deny"}})
    out = {"version": "candidate_anaphora_material_v1",
           "status": "built_by_script (validation + freeze are separate steps)",
           "date": "2026-10-04",
           "protocol": "docs/candidate_anaphora_probe_v1.json",
           "builder": "scripts/build_anaphora_material.py",
           "surface_note": "provider_surface/recipient_surface hold the explicit surface span or null when anaphoric; provider/recipient hold the discourse referents for evaluation",
           "pairs": pairs}
    (ROOT / "docs" / "candidate_anaphora_material_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"pairs: {len(pairs)}, inputs: {2 * len(pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
