"""Candidate anaphora probe run (anaphora protocol v1, Phase D).

Candidate stage only (nu_candidates, local Ollama nuextract3): no validator,
no linking, no resolution of it/them required. Material is frozen
(docs/candidate_anaphora_material_v1.json); this script only measures.

Per-side outcome: explicit (gold surface span recovered), pronoun (role is
anaphoric and a candidate carries the pronoun in that slot), missing.
Sentence outcome: correct / anaphoric / partial / wrong_span / missing.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trackb_two_stage import nu_candidates
from trackb_production import normalize

ROOT = Path(__file__).resolve().parents[1]
PRONOUNS = {"it", "them"}


def span_match(gold: str, cand: str) -> bool:
    g, c = normalize(gold), normalize(cand)
    return bool(g) and bool(c) and (g == c or g in c or c in g)


def side_outcome(explicit_surface, referent_head, cands, slot):
    """explicit: surface span recovered. resolved: role anaphoric in surface
    but candidate carries the explicit referent head (mechanism undetermined:
    true coreference vs prominence pairing). pronoun: pronoun span in slot.
    """
    if explicit_surface is not None:
        if any(span_match(explicit_surface, c[slot]) for c in cands):
            return "explicit"
        return "missing"
    if any(span_match(referent_head, c[slot]) for c in cands):
        return "resolved"
    if any(normalize(c[slot]) in PRONOUNS for c in cands):
        return "pronoun"
    if any(c[slot].strip() for c in cands):
        return "wrong_span"
    return "missing"


def main() -> int:
    mat = json.loads(
        (ROOT / "docs" / "candidate_anaphora_material_v1.json").read_text(
            encoding="utf-8"))
    out = {"version": "candidate_anaphora_results_v1",
           "protocol": "docs/candidate_anaphora_probe_v1.json",
           "material": "docs/candidate_anaphora_material_v1.json",
           "stage": "candidate_generation_only (nu_candidates, no validator, no linking)",
           "match_rule": "normalized span equality or containment, either direction",
           "note": "D0 items share surface with C0/lex01 triplets (cross-probe calibration)",
           "pairs": []}
    for p in mat["pairs"]:
        res = {"pair_id": p["pair_id"], "condition": p["condition"],
               "subtype": p["subtype"], "sides": {}}
        for side in ("yes", "no"):
            s = p[side]
            cands = nu_candidates(s["sentence"])
            if side == "no":
                res["sides"][side] = {
                    "sentence_id": s["sentence_id"],
                    "n_candidates": len(cands),
                    "candidates": [list(c) for c in cands],
                    "false_candidate": bool(cands)}
                continue
            po = side_outcome(s["provider_surface"], s["provider"], cands, 0)
            ro = side_outcome(s["recipient_surface"], s["recipient"], cands, 1)
            good = {"explicit", "pronoun", "resolved"}
            if po == "explicit" and ro == "explicit":
                oc = "correct"
            elif not cands:
                oc = "missing"
            elif po in good and ro in good:
                oc = "anaphoric" if "pronoun" in (po, ro) else "resolved"
            elif po in good or ro in good:
                oc = "partial"
            else:
                oc = "wrong_span"
            res["sides"][side] = {
                "sentence_id": s["sentence_id"],
                "n_candidates": len(cands),
                "candidates": [list(c) for c in cands],
                "provider_outcome": po, "recipient_outcome": ro,
                "outcome": oc}
        out["pairs"].append(res)
        y, n = res["sides"]["yes"], res["sides"]["no"]
        print(f"{p['pair_id']} YES:{y['outcome']} (n={y['n_candidates']}) "
              f"NO-false:{int(n['false_candidate'])} (n={n['n_candidates']})",
              flush=True)
    (ROOT / "docs" / "candidate_anaphora_results_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
