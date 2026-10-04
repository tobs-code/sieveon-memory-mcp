"""Build density probe material deterministically (protocol v1).

4 sets x 3 conditions (SINGLE/REL/ADV) x YES/NO with deny.
Target frame constant; only propositional adjunct structure varies.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SETS = {
    "tut": {"P": "mentor", "R": "pupils", "T": "tutorials", "V": "gives",
            "rel": "that cover the syllabus",
            "adv": "before they start the exams"},
    "clk": {"P": "usher", "R": "guests", "T": "passes", "V": "provides",
            "rel": "that open the gates",
            "adv": "before they enter the hall"},
    "chf": {"P": "chef", "R": "patrons", "T": "suppers", "V": "cooked",
            "rel": "that includes the new menu",
            "adv": "while the staff prepared the tables"},
    "hrb": {"P": "harbor", "R": "pilots", "T": "charts", "V": "provides",
            "rel": "that show the new channel",
            "adv": "before they leave the dock"},
}

NO_VERB = {"gives": "denies", "provides": "denies", "cooked": "refused"}


def build(s, cond, verb):
    P, R, T = "The " + s["P"], s["R"], s["T"]
    if cond == "SINGLE":
        return f"{P} {verb} {R} {T}."
    if cond == "REL":
        return f"{P} {verb} {R} {T} {s['rel']}."
    if cond == "ADV":
        return f"{P} {verb} {R} {T} {s['adv']}."
    raise ValueError(cond)


def axes(cond):
    base = {"predicate_argument_compatibility": "CANONICAL_FRAME",
            "proposition_completeness": "COMPLETE",
            "event_vs_state": "EVENTIVE", "implicit_argument_count": 0}
    if cond == "SINGLE":
        return base | {"proposition_density": "SINGLE",
                       "canonicality": "P0",
                       "syntax_pattern": "DITRANSITIVE"}
    if cond == "REL":
        return base | {"proposition_density": "MULTIPLE_EMBEDDED",
                       "canonicality": "P1",
                       "syntax_pattern": "DITRANSITIVE_WITH_RELATIVE_CLAUSE"}
    return base | {"proposition_density": "MULTIPLE_EMBEDDED",
                   "canonicality": "P1",
                   "syntax_pattern": "DITRANSITIVE_WITH_ADVERBIAL_CLAUSE"}


def main() -> int:
    pairs = []
    for sid, s in SETS.items():
        for cond in ("SINGLE", "REL", "ADV"):
            y = build(s, cond, s["V"])
            n = build(s, cond, NO_VERB[s["V"]])
            pid = f"{cond.lower()}{sid}"
            pairs.append({
                "pair_id": pid, "condition": cond, "set": sid,
                "yes": {"sentence_id": pid + "yes", "sentence": y,
                        "expected_provides": "YES",
                        "gold_provider": "The " + s["P"],
                        "gold_recipient": s["R"], "gold_theme": s["T"],
                        "gold_relation": "provides",
                        "source_trigger": s["V"], **axes(cond)},
                "no": {"sentence_id": pid + "no", "sentence": n,
                       "expected_provides": "NO",
                       "gold_provider": "The " + s["P"],
                       "gold_recipient": s["R"], "gold_theme": s["T"],
                       "gold_relation": "none",
                       "source_trigger": NO_VERB[s["V"]],
                       **axes(cond)}})
    out = {"version": "candidate_density_material_v1",
           "status": "built_by_script (validation + freeze are separate steps)",
           "date": "2026-10-04",
           "protocol": "docs/candidate_density_probe_v1.json",
           "builder": "scripts/build_density_material.py",
           "pairs": pairs}
    (ROOT / "docs" / "candidate_density_material_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"pairs: {len(pairs)}, sentences: {2 * len(pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
