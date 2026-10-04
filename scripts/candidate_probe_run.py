"""Candidate argument-realization probe run (probe protocol v1).

Candidate stage only (nu_candidates, local Ollama nuextract3): no validator,
no postfilter, no linking, no pipeline change. Material is frozen
(docs/candidate_probe_material_v1.json); this script only measures.
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
        (ROOT / "docs" / "candidate_probe_material_v1.json").read_text(
            encoding="utf-8"))
    out = {"version": "candidate_probe_results_v1",
           "protocol": "docs/candidate_argument_realization_probe_v1.json",
           "material": "docs/candidate_probe_material_v1.json",
           "stage": "candidate_generation_only (nu_candidates, no validator)",
           "match_rule": "normalized span equality or containment, either direction",
           "pairs": []}
    for p in mat["pairs"]:
        res = {"pair_id": p["pair_id"], "class": p["class"],
               "verb": p["verb"], "variants": {}}
        for v in ("a", "b"):
            s = p[v]
            cands = nu_candidates(s["text"])
            pm = [list(c) for c in cands
                  if span_match(p["provider_gold"], c[0])]
            rm = [list(c) for c in cands
                  if span_match(p["recipient_gold"], c[1])]
            full = [list(c) for c in cands
                    if span_match(p["provider_gold"], c[0])
                    and span_match(p["recipient_gold"], c[1])]
            res["variants"][v] = {
                "sentence_id": s["sentence_id"],
                "n_candidates": len(cands),
                "candidates": [list(c) for c in cands],
                "provider_recovered": bool(pm),
                "recipient_recovered": bool(rm),
                "full_match": bool(full)}
        out["pairs"].append(res)
        fa = res["variants"]["a"]["full_match"]
        fb = res["variants"]["b"]["full_match"]
        print(f"{p['pair_id']} {p['class']:12s} A:{int(fa)} B:{int(fb)} "
              f"(A-cands:{res['variants']['a']['n_candidates']} "
              f"B-cands:{res['variants']['b']['n_candidates']})", flush=True)
    (ROOT / "docs" / "candidate_probe_results_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
