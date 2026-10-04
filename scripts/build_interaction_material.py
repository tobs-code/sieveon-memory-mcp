"""Build interaction probe material deterministically (protocol v1).

4 scenarios x 4 cells (A/B/C/D) x YES(supports)/NO(stop).
Pairs share everything except the verb (supports/stops).
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = {
    "rec": {"P": "foundation", "team": "teams", "part": "digitizing records",
            "nom": "the digitization of records"},
    "thea": {"P": "donors", "team": "staff", "part": "restoring the theater",
             "nom": "the restoration of the theater"},
    "hosp": {"P": "city", "team": "crews", "part": "rebuilding the bridge",
             "nom": "the rebuilding of the bridge"},
    "mus": {"P": "trust", "team": "artists", "part": "recording songs",
            "nom": "the recording of songs"},
}


def build(s, cell, verb):
    P = "The " + s["P"]
    if cell == "A":
        return f"{P} {verb} {s['team']} {s['part']}."
    if cell == "B":
        return f"{P} {verb} {s['nom']}."
    if cell == "C":
        return f"{s['team'].capitalize()} {s['part']} are {verb} by {P.lower()}."
    if cell == "D":
        return f"{s['nom'].capitalize()} is {verb} by {P.lower()}."
    raise ValueError(cell)


def main() -> int:
    pairs = []
    for sid, s in SCENARIOS.items():
        for cell in ("A", "B", "C", "D"):
            y = build(s, cell, "supports" if cell in ("A", "B") else "supported")
            n = build(s, cell, "stops" if cell in ("A", "B") else "stopped")
            pid = f"{cell.lower()}{sid}"
            target = s["team"] if cell in ("A", "C") else s["nom"]
            pairs.append({
                "pair_id": pid, "cell": cell, "scenario": sid,
                "yes": {"sentence_id": pid + "yes", "sentence": y,
                        "expected_provides": "YES",
                        "gold_provider": "The " + s["P"],
                        "gold_target": target,
                        "gold_relation": "provides",
                        "source_trigger": "supports",
                        "semantic_basis": "support/provision"},
                "no": {"sentence_id": pid + "no", "sentence": n,
                       "expected_provides": "NO",
                       "gold_provider": "The " + s["P"],
                       "gold_target": target,
                       "gold_relation": "none",
                       "source_trigger": "stop",
                       "semantic_basis": "control: cessation, no provision"}})
    out = {"version": "candidate_interaction_material_v1",
           "status": "built_by_script (validation + freeze are separate steps)",
           "date": "2026-10-04",
           "protocol": "docs/candidate_interaction_probe_v1.json",
           "builder": "scripts/build_interaction_material.py",
           "pairs": pairs}
    (ROOT / "docs" / "candidate_interaction_material_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"pairs: {len(pairs)}, sentences: {2 * len(pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
