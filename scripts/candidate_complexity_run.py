"""Candidate complexity probe run (complexity protocol v1, Phase C).

Candidate stage only (nu_candidates, local Ollama nuextract3): no validator,
no postfilter, no linking, no pipeline change. Material is frozen
(docs/candidate_complexity_material_v1.json); this script only measures.
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
        (ROOT / "docs" / "candidate_complexity_material_v1.json").read_text(
            encoding="utf-8"))
    out = {"version": "candidate_complexity_results_v1",
           "protocol": "docs/candidate_complexity_probe_v1.json",
           "material": "docs/candidate_complexity_material_v1.json",
           "stage": "candidate_generation_only (nu_candidates, no validator)",
           "match_rule": "normalized span equality or containment, either direction",
           "note": "c0med YES/NO share surface with lex01 (cross-probe calibration, not independent evidence)",
           "pairs": []}
    for p in mat["pairs"]:
        res = {"pair_id": p["pair_id"], "condition": p["condition"],
               "subtype": p["subtype"], "sides": {}}
        for side in ("yes", "no"):
            s = p[side]
            cands = nu_candidates(s["sentence"])
            pm = any(span_match(s["provider"], c[0]) for c in cands)
            rm = any(span_match(s["recipient"], c[1]) for c in cands)
            full = any(span_match(s["provider"], c[0])
                       and span_match(s["recipient"], c[1]) for c in cands)
            res["sides"][side] = {
                "sentence_id": s["sentence_id"],
                "n_candidates": len(cands),
                "candidates": [list(c) for c in cands],
                "provider_recovered": pm, "recipient_recovered": rm,
                "full_match": full,
                "false_candidate": full and s["expected_provides"] == "NO"}
        out["pairs"].append(res)
        y, n = res["sides"]["yes"], res["sides"]["no"]
        print(f"{p['pair_id']} YES:{int(y['full_match'])} (n={y['n_candidates']}) "
              f"NO-false:{int(n['false_candidate'])} (n={n['n_candidates']})",
              flush=True)
    (ROOT / "docs" / "candidate_complexity_results_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
