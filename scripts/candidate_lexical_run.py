"""Candidate lexical probe run (lexical protocol v1, Phase L).

Candidate stage only (nu_candidates, local Ollama nuextract3): no validator,
no postfilter, no linking, no pipeline change. Material is frozen
(docs/candidate_lexical_material_v1.json); this script only measures.
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
        (ROOT / "docs" / "candidate_lexical_material_v1.json").read_text(
            encoding="utf-8"))
    out = {"version": "candidate_lexical_results_v1",
           "protocol": "docs/candidate_lexical_probe_v1.json",
           "material": "docs/candidate_lexical_material_v1.json",
           "stage": "candidate_generation_only (nu_candidates, no validator)",
           "match_rule": "normalized span equality or containment, either direction",
           "pairs": []}
    for p in mat["pairs"]:
        res = {"pair_id": p["pair_id"], "class": p["class"],
               "verb_yes": p["verb_yes"], "verb_no": p["verb_no"],
               "sides": {}}
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
        print(f"{p['pair_id']} {p['class']:3s} {p['verb_yes']:10s} "
              f"YES:{int(y['full_match'])} (n={y['n_candidates']})  "
              f"{p['verb_no']:8s} NO-false:{int(n['false_candidate'])} "
              f"(n={n['n_candidates']})", flush=True)
    (ROOT / "docs" / "candidate_lexical_results_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
