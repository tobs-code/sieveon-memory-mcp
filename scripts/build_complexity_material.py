"""Build Phase C complexity probe material deterministically (protocol v1).

4 subtypes x 6 conditions x YES/NO. Same triplets everywhere; pairs differ
only in the verb (provide/deny). Matrix tails use definite articles
(no possessive pronouns). C1 adjunct is identical across subtypes.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SUBTYPES = {
    "med": {"P": "clinic", "R": "patients", "T": "medication",
            "rel": "which", "c2": "that opened last year",
            "c3": "who need treatment", "tail": "expanded the pharmacy"},
    "fuel": {"P": "depot", "R": "units", "T": "fuel",
             "rel": "which", "c2": "that opened last year",
             "c3": "that need refills", "tail": "expanded the warehouse"},
    "badge": {"P": "clerk", "R": "visitors", "T": "badges",
              "rel": "who", "c2": "that started last month",
              "c3": "who need passes", "tail": "extended the desk hours"},
    "lesson": {"P": "tutor", "R": "students", "T": "lessons",
               "rel": "who", "c2": "that joined last term",
               "c3": "who need help", "tail": "extended the course catalog"},
}

C1_ADJUNCT = "struggling with long queues"


def build(sub, cond, verb):
    P, R, T = "The " + sub["P"], sub["R"], sub["T"]
    if cond == "C0":
        return f"{P} {verb} {R} {T}."
    if cond == "C1":
        return f"{P}, {C1_ADJUNCT}, {verb} {R} {T}."
    if cond == "C2":
        return f"{P} {sub['c2']} {verb} {R} {T}."
    if cond == "C3":
        return f"{P} {verb} {R} {sub['c3']} {T}."
    if cond == "C4":
        return f"{P}, {sub['rel']} {verb} {R} {T}, {sub['tail']}."
    if cond == "C5":
        part = {"provides": "Providing", "denies": "Denying"}[verb]
        return f"{part} {R} {T}, the {sub['P']} {sub['tail']}."
    raise ValueError(cond)


def main() -> int:
    pairs = []
    for sub_id, sub in SUBTYPES.items():
        for cond in ("C0", "C1", "C2", "C3", "C4", "C5"):
            y = build(sub, cond, "provides")
            n = build(sub, cond, "denies")
            pid = f"{cond.lower()}{sub_id}"
            pairs.append({
                "pair_id": pid, "condition": cond, "subtype": sub_id,
                "yes": {"sentence_id": pid + "yes", "sentence": y,
                        "expected_provides": "YES",
                        "provider": "The " + sub["P"],
                        "recipient": sub["R"],
                        "lexical_trigger": "provide",
                        "argument_frame": "participial" if cond == "C5" else "double-object"},
                "no": {"sentence_id": pid + "no", "sentence": n,
                       "expected_provides": "NO",
                       "provider": "The " + sub["P"],
                       "recipient": sub["R"],
                       "lexical_trigger": "deny",
                       "argument_frame": "participial" if cond == "C5" else "double-object"}})
    out = {"version": "candidate_complexity_material_v1",
           "status": "built_by_script (validation + freeze are separate steps)",
           "date": "2026-10-04",
           "protocol": "docs/candidate_complexity_probe_v1.json",
           "builder": "scripts/build_complexity_material.py",
           "c1_adjunct": C1_ADJUNCT,
           "pairs": pairs}
    (ROOT / "docs" / "candidate_complexity_material_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"pairs: {len(pairs)}, sentences: {2 * len(pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
