"""Candidate implicit-agent/theme probe runs (protocols v1).

Candidate stage only (nu_candidates, local Ollama nuextract3): no validator,
no linking. Probe A: A1/A2/A3, primary contrast A2 vs A3. Probe B: overt vs
dropped theme per predicate block + aggregate. Materials frozen.
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


def run_file(material, version, sides):
    mat = json.loads((ROOT / "docs" / material).read_text(encoding="utf-8"))
    out = {"version": version,
           "material": "docs/" + material,
           "stage": "candidate_generation_only (nu_candidates, no validator, no linking)",
           "match_rule": "normalized span equality or containment, either direction",
           "pairs": []}
    for p in mat["pairs"]:
        res = {"pair_id": p["pair_id"], "sides": {}}
        for side in sides:
            s = p[side]
            cands = nu_candidates(s["sentence"])
            pm = any(span_match(s.get("gold_provider", ""), c[0])
                     for c in cands) if s.get("gold_provider") else None
            # recipient convention (established across probes): the generator
            # puts the animate recipient in slot 2, never the theme
            rm = any(span_match(s.get("gold_recipient", ""), c[1])
                     for c in cands) if s.get("gold_recipient") else False
            tm = any(span_match(s.get("gold_theme") or "", c[1])
                     for c in cands)
            if pm and (rm or tm):
                oc = "correct"
            elif not cands:
                oc = "absent"
            elif pm or rm or tm:
                oc = "partial"
            else:
                oc = "wrong"
            if s.get("expected_provides") == "NO":
                oc = "false_candidate" if cands else "absent"
            res["sides"][side] = {
                "sentence_id": s["sentence_id"],
                "n_candidates": len(cands),
                "candidates": [list(c) for c in cands],
                "provider": pm, "recipient": rm, "theme": tm,
                "outcome": oc}
        out["pairs"].append(res)
        print(" | ".join(
            f"{side}:{res['sides'][side]['outcome']} "
            f"(n={res['sides'][side]['n_candidates']})" for side in sides),
            flush=True)
    (ROOT / "docs" / (version + ".json")).write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "agent"
    if mode == "agent":
        raise SystemExit(run_file("candidate_implicit_agent_material_v1.json",
                                  "candidate_implicit_agent_results_v1",
                                  ("yes", "no")))
    raise SystemExit(run_file("candidate_implicit_theme_material_v1.json",
                              "candidate_implicit_theme_results_v1",
                              ("overt", "overt_no", "dropped",
                               "dropped_no")))
