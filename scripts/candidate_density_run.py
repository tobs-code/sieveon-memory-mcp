"""Candidate density probe run (density protocol v1, probe #11).

Candidate stage only (nu_candidates, local Ollama nuextract3): no validator,
no linking. Primary: target-frame candidate present per condition.
Material is frozen; this script only measures.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trackb_two_stage import nu_candidates
from trackb_production import normalize

ROOT = Path(__file__).resolve().parents[1]


def span_match(gold: str, cand: str) -> bool:
    g, c = normalize(gold), normalize(cand)
    return bool(g) and bool(c) and (g == c or g in c or c in g)


def main() -> int:
    mat = json.loads(
        (ROOT / "docs" / "candidate_density_material_v1.json").read_text(
            encoding="utf-8"))
    out = {"version": "candidate_density_results_v1",
           "protocol": "docs/candidate_density_probe_v1.json",
           "material": "docs/candidate_density_material_v1.json",
           "stage": "candidate_generation_only (nu_candidates, no validator, no linking)",
           "match_rule": "normalized span equality or containment, either direction",
           "pairs": []}
    for p in mat["pairs"]:
        res = {"pair_id": p["pair_id"], "condition": p["condition"],
               "set": p["set"], "sides": {}}
        for side in ("yes", "no"):
            s = p[side]
            cands = nu_candidates(s["sentence"])
            pm = any(span_match(s["gold_provider"], c[0]) for c in cands)
            rm = any(span_match(s["gold_recipient"], c[1]) for c in cands)
            if pm and rm:
                oc = "correct"
            elif not cands:
                oc = "absent"
            elif pm or rm:
                oc = "partial"
            else:
                oc = "wrong"
            if side == "no":
                oc = "false_candidate" if cands else "absent"
            res["sides"][side] = {
                "sentence_id": s["sentence_id"],
                "n_candidates": len(cands),
                "candidates": [list(c) for c in cands],
                "provider_recovered": pm, "recipient_recovered": rm,
                "outcome": oc}
        out["pairs"].append(res)
        y, n = res["sides"]["yes"], res["sides"]["no"]
        print(f"{p['pair_id']} YES:{y['outcome']} (n={y['n_candidates']}) "
              f"NO:{n['outcome']} (n={n['n_candidates']})", flush=True)
    (ROOT / "docs" / "candidate_density_results_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
