"""Build implicit-agent/theme probe materials deterministically.

Probe A: 4 sets x (A1 active+agent / A2 passive+agent / A3 passive-agentless)
  x YES(provides)/NO(denies). Primary contrast A2 vs A3.
Probe B: 4 verbs x 2 triples x (overt theme / dropped theme)
  x YES/NO with deny. Per-predicate blocks + aggregate.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

A_SETS = {
    "inf": {"P": "infirmary", "R": "patients", "T": "doses"},
    "ldg": {"P": "lodge", "R": "hikers", "T": "maps"},
    "std": {"P": "studio", "R": "members", "T": "manuals"},
    "gal": {"P": "gallery", "R": "visitors", "T": "catalogs"},
}

B_ITEMS = [
    ("pay", "The company", "the workers", "their wages"),
    ("pay", "The firm", "contractors", "bonuses"),
    ("teach", "The instructor", "the students", "the procedure"),
    ("teach", "The tutor", "pupils", "grammar"),
    ("serve", "The chef", "the guests", "soup"),
    ("serve", "The host", "diners", "courses"),
    ("feed", "The farmer", "the horses", "grain"),
    ("feed", "The groom", "horses", "oats"),
]


PASSIVE = {"provides": "provided", "denies": "denied"}


def build_a(s, cond, verb):
    P, R, T = "The " + s["P"], s["R"], s["T"]
    if cond == "A1":
        return f"{P} {verb} {R} {T}."
    pv = PASSIVE[verb]
    if cond == "A2":
        return f"{T.capitalize()} are {pv} to {R} by {P.lower()}."
    if cond == "A3":
        return f"{T.capitalize()} are {pv} to {R}."
    raise ValueError(cond)


def main() -> int:
    a_pairs = []
    for sid, s in A_SETS.items():
        for cond in ("A1", "A2", "A3"):
            y = build_a(s, cond, "provides")
            n = build_a(s, cond, "denies")
            pid = f"{cond.lower()}{sid}"
            a_pairs.append({
                "pair_id": pid, "condition": cond, "set": sid,
                "yes": {"sentence_id": pid + "yes", "sentence": y,
                        "expected_provides": "YES",
                        "gold_provider": "The " + s["P"],
                        "gold_recipient": s["R"], "gold_theme": s["T"],
                        "gold_relation": "provides",
                        "expected_candidate": True},
                "no": {"sentence_id": pid + "no", "sentence": n,
                       "expected_provides": "NO",
                       "gold_provider": "The " + s["P"],
                       "gold_recipient": s["R"], "gold_theme": s["T"],
                       "gold_relation": "none",
                       "expected_candidate": False}})
    b_pairs = []
    for i, (verb, P, R, T) in enumerate(B_ITEMS, 1):
        past = {"pay": "paid", "teach": "taught", "serve": "served",
                "feed": "fed"}[verb]
        nopast = "denied"
        y = f"{P} {past} {R} {T}."
        y2 = f"{P} {past} {R}."
        n = f"{P} {nopast} {R} {T}."
        n2 = f"{P} {nopast} {R}."
        pid = f"b{i:02d}"
        b_pairs.append({
            "pair_id": pid, "verb": verb,
            "overt": {"sentence_id": pid + "overt_yes", "sentence": y,
                      "expected_provides": "YES",
                      "gold_provider": P, "gold_recipient": R,
                      "gold_theme": T, "gold_relation": "provides",
                      "expected_candidate": True,
                      "theme_status": "overt"},
            "overt_no": {"sentence_id": pid + "overt_no", "sentence": n,
                         "expected_provides": "NO",
                         "gold_relation": "none",
                         "expected_candidate": False},
            "dropped": {"sentence_id": pid + "dropped_yes", "sentence": y2,
                        "expected_provides": "YES",
                        "gold_provider": P, "gold_recipient": R,
                        "gold_theme": None, "gold_relation": "provides",
                        "expected_candidate": "CHECK",
                        "theme_status": "dropped"},
            "dropped_no": {"sentence_id": pid + "dropped_no", "sentence": n2,
                           "expected_provides": "NO",
                           "gold_relation": "none",
                           "expected_candidate": False}})
    a_out = {"version": "candidate_implicit_agent_material_v1",
             "status": "built_by_script (validation + freeze are separate steps)",
             "date": "2026-10-04",
             "protocol": "docs/candidate_implicit_agent_probe_v1.json",
             "builder": "scripts/build_implicit_material.py",
             "pairs": a_pairs}
    b_out = {"version": "candidate_implicit_theme_material_v1",
             "status": "built_by_script (validation + freeze are separate steps)",
             "date": "2026-10-04",
             "protocol": "docs/candidate_implicit_theme_probe_v1.json",
             "builder": "scripts/build_implicit_material.py",
             "pairs": b_pairs}
    (ROOT / "docs" / "candidate_implicit_agent_material_v1.json").write_text(
        json.dumps(a_out, indent=1, ensure_ascii=False), encoding="utf-8")
    (ROOT / "docs" / "candidate_implicit_theme_material_v1.json").write_text(
        json.dumps(b_out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"A pairs: {len(a_pairs)}, B pairs: {len(b_pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
