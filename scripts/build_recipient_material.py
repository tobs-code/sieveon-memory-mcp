"""Build recipient probe material deterministically (protocol v1).

8 sets x 3 conditions (R0/R1/R2) x YES(provides)/NO(denies).
R0 ditransitive, R1 bare transitive (recipient implicit), R2 to-PP recipient.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SETS = [
    ("stadium", "fans", "anthems"),
    ("kennel", "owners", "puppies"),
    ("observatory", "astronomers", "images"),
    ("garage", "drivers", "repairs"),
    ("hostel", "travelers", "bunks"),
    ("nursery", "parents", "seedlings"),
    ("arcade", "players", "tokens"),
    ("apiary", "beekeepers", "smokers"),
]


def build(P, R, T, cond, verb):
    if cond == "R0":
        return f"The {P} {verb} {R} {T}."
    if cond == "R1":
        return f"The {P} {verb} {T}."
    if cond == "R2":
        return f"The {P} {verb} {T} to {R}."
    raise ValueError(cond)


def main() -> int:
    pairs = []
    for i, (P, R, T) in enumerate(SETS, 1):
        for cond in ("R0", "R1", "R2"):
            y = build(P, R, T, cond, "provides")
            n = build(P, R, T, cond, "denies")
            pid = f"{cond.lower()}{i:02d}"
            pairs.append({
                "pair_id": pid, "condition": cond, "set": i,
                "yes": {"sentence_id": pid + "yes", "sentence": y,
                        "expected_provides": "YES",
                        "gold_provider": "The " + P,
                        "gold_recipient": R if cond in ("R0", "R2") else None,
                        "gold_theme": T, "gold_relation": "provides",
                        "source_trigger": "provides",
                        "expected_candidate": "CHECK" if cond == "R1" else True},
                "no": {"sentence_id": pid + "no", "sentence": n,
                       "expected_provides": "NO",
                       "gold_provider": "The " + P,
                       "gold_recipient": R if cond in ("R0", "R2") else None,
                       "gold_theme": T, "gold_relation": "none",
                       "source_trigger": "deny",
                       "expected_candidate": False}})
    out = {"version": "candidate_recipient_material_v1",
           "status": "built_by_script (validation + freeze are separate steps)",
           "date": "2026-10-04",
           "protocol": "docs/candidate_recipient_probe_v1.json",
           "builder": "scripts/build_recipient_material.py",
           "pairs": pairs}
    (ROOT / "docs" / "candidate_recipient_material_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"pairs: {len(pairs)}, sentences: {2 * len(pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
