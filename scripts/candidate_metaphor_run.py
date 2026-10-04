"""Candidate metaphor probe run (metaphor protocol v1).

Candidate stage only (nu_candidates, local Ollama nuextract3): no validator,
no linking. Outcome taxonomy: correct / partial_span / wrong_role vs absent
(TRUE SILENCE). Figurative-NO items (give-hope, bring-joy, build-confidence)
are ontology controls: a miss there is correct behavior, not generator failure.
Material is frozen; this script only measures.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trackb_two_stage import nu_candidates
from trackb_production import normalize

ROOT = Path(__file__).resolve().parents[1]


def head(s: str) -> str:
    toks = normalize(s).split()
    return toks[-1] if toks else ""


def span_match(gold: str, cand: str) -> bool:
    g, c = normalize(gold), normalize(cand)
    return bool(g) and bool(c) and (g == c or g in c or c in g)


def main() -> int:
    mat = json.loads(
        (ROOT / "docs" / "candidate_metaphor_material_v1.json").read_text(
            encoding="utf-8"))
    out = {"version": "candidate_metaphor_results_v1",
           "protocol": "docs/candidate_metaphor_probe_v1.json",
           "material": "docs/candidate_metaphor_material_v1.json",
           "stage": "candidate_generation_only (nu_candidates, no validator, no linking)",
           "match_rule": "rigid 5-token frame The-P-V-R-T: provider slot vs 'The P', recipient slot vs R (animate), theme slot vs theme head. Generator convention from all prior probes is provider->animate-recipient; theme recovery is secondary.",
           "convention_note": "v1 runner wrongly scored the theme slot as primary (everything partial). v2 scores recipient-convention primary; a miss there is absence, a theme-only hit would be selection.",
           "pairs": []}
    for p in mat["pairs"]:
        res = {"pair_id": p["pair_id"], "class": p["class"],
               "verb": p["verb"], "sides": {}}
        for side in ("literal", "figurative"):
            s = p[side]
            cands = nu_candidates(s["sentence"])
            exp = s["provides_relation"] in ("YES", "YES*")
            toks = s["sentence"].split()
            assert len(toks) == 5, s["sentence"]
            prov, recip, theme = " ".join(toks[:2]), toks[3], head(toks[4])
            pm = any(span_match(prov, c[0]) for c in cands)
            rm = any(span_match(recip, c[1]) for c in cands)
            tm = any(span_match(theme, c[1]) for c in cands)
            if pm and rm:
                oc = "correct"
            elif not cands:
                oc = "absent"
            elif pm or rm or tm:
                oc = "partial_span"
            else:
                oc = "wrong_role"
            if not exp:
                oc = "false_candidate" if cands else "absent"
            res["sides"][side] = {
                "sentence_id": s["sentence_id"],
                "gold": s["provides_relation"],
                "n_candidates": len(cands),
                "candidates": [list(c) for c in cands],
                "provider_recovered": pm, "recipient_recovered": rm,
                "theme_recovered": tm, "outcome": oc}
        out["pairs"].append(res)
        li, fi = res["sides"]["literal"], res["sides"]["figurative"]
        print(f"{p['pair_id']} {p['class']:3s} {p['verb']:8s} "
              f"LIT:{li['outcome']} (n={li['n_candidates']}) "
              f"FIG:{fi['outcome']} (n={fi['n_candidates']})", flush=True)
    (ROOT / "docs" / "candidate_metaphor_results_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
