"""Candidate event-nominal probe run (event-nominal protocol v1).

Candidate stage only (nu_candidates, local Ollama nuextract3): no validator,
no linking. node_worthy(target) is recorded per produced target span as a
SEPARATE downstream metric and never influences the candidate primary metric.
Material is frozen; this script only measures.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trackb_two_stage import nu_candidates
from trackb_production import normalize
from node_worthiness import node_worthy

ROOT = Path(__file__).resolve().parents[1]


def span_match(gold: str, cand: str) -> bool:
    g, c = normalize(gold), normalize(cand)
    return bool(g) and bool(c) and (g == c or g in c or c in g)


def main() -> int:
    mat = json.loads(
        (ROOT / "docs" / "candidate_eventnominal_material_v1.json").read_text(
            encoding="utf-8"))
    out = {"version": "candidate_eventnominal_results_v1",
           "protocol": "docs/candidate_eventnominal_probe_v1.json",
           "material": "docs/candidate_eventnominal_material_v1.json",
           "stage": "candidate_generation_only + separate node_worthy(target) readout",
           "match_rule": "normalized span equality or containment, either direction",
           "pairs": []}
    for p in mat["pairs"]:
        res = {"pair_id": p["pair_id"], "class": p["class"],
               "target_type": p["target_type"], "sides": {}}
        for side in ("yes", "no"):
            s = p[side]
            cands = nu_candidates(s["sentence"])
            pm = any(span_match(s["provider"], c[0]) for c in cands)
            tm = [list(c) for c in cands
                  if span_match(s["recipient"], c[1])]
            full = any(span_match(s["provider"], c[0])
                       and span_match(s["recipient"], c[1]) for c in cands)
            worth = [ {"span": c[1], **node_worthy(c[1])} for c in cands ]
            res["sides"][side] = {
                "sentence_id": s["sentence_id"],
                "n_candidates": len(cands),
                "candidates": [list(c) for c in cands],
                "provider_recovered": pm,
                "target_recovered": bool(tm),
                "full_match": full,
                "target_worthiness": worth,
                "false_candidate": full and s["expected_provides"] == "NO"}
        out["pairs"].append(res)
        y, n = res["sides"]["yes"], res["sides"]["no"]
        w = ",".join(w_["verdict"] for w_ in y["target_worthiness"]) or "-"
        print(f"{p['pair_id']} {p['class']:3s} YES:{int(y['full_match'])} "
              f"(n={y['n_candidates']}, worthy=[{w}]) "
              f"NO-false:{int(n['false_candidate'])} (n={n['n_candidates']})",
              flush=True)
    (ROOT / "docs" / "candidate_eventnominal_results_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
