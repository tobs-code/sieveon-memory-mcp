"""Candidate theme-role probe run (T1 assist + T2 serve).

Candidate stage only (nu_candidates, local Ollama nuextract3): no validator,
no linking. T1 and T2 evaluated SEPARATELY, never pooled. T1 is confounded
(animacy covaries); T2 holds animacy constant. Material frozen.
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
        (ROOT / "docs" / "candidate_themerole_material_v1.json").read_text(
            encoding="utf-8"))
    out = {"version": "candidate_themerole_results_v1",
           "material": "docs/candidate_themerole_material_v1.json",
           "stage": "candidate_generation_only (nu_candidates, no validator, no linking)",
           "match_rule": "normalized span equality or containment, either direction; gold slots are provider+second-argument",
           "pairs": []}
    for p in mat["pairs"]:
        res = {"pair_id": p["pair_id"], "subprobe": p["subprobe"],
               "verb": p["verb"], "sides": {}}
        for side in ("concrete", "nonproto"):
            s = p[side]
            cands = nu_candidates(s["sentence"])
            pm = any(span_match(s["gold"][0], c[0]) for c in cands)
            sm = any(span_match(s["gold"][1], c[1]) for c in cands)
            if pm and sm:
                oc = "correct"
            elif not cands:
                oc = "absent"
            elif pm or sm:
                oc = "partial"
            else:
                oc = "wrong"
            res["sides"][side] = {
                "sentence_id": s["sentence_id"] if "sentence_id" in s else p["pair_id"] + side[0],
                "n_candidates": len(cands),
                "candidates": [list(c) for c in cands],
                "provider": pm, "second": sm, "outcome": oc}
        out["pairs"].append(res)
        a, b = res["sides"]["concrete"], res["sides"]["nonproto"]
        print(f"{p['pair_id']} {p['subprobe']:3s} concrete:{a['outcome']} "
              f"(n={a['n_candidates']}) nonproto:{b['outcome']} "
              f"(n={b['n_candidates']})", flush=True)
    (ROOT / "docs" / "candidate_themerole_results_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
