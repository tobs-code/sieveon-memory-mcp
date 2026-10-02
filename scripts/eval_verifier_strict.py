"""Does the verifier separate `supported` from the rest, or only right from wrong?

The production pipeline maximises broad precision: anything the verifier
does not reject as wrong counts as kept, including triples that are only
`implied` rather than `supported`. On the uniform sample that shows up as
strict precision 6/29 = 0.207 against broad 16/29 = 0.552. Whether strict
entailment is worth optimising separately depends on one thing, and it is
not a matter of taste: does the same cross-encoder already separate
`supported` from `implied`+`wrong`, or does it not?

Two targets, identical claims, identical scores, only the labelling differs:

    A  right     = supported + implied  vs  wrong
    B  strict    = supported            vs  implied + wrong

Target A is what the current decision rule optimises. Target B is the
question. Because `supported` is a small class (47 of 202), ROC-AUC alone
can flatter it, so PR-AUC and precision at fixed recall are reported too,
plus the extraction confidence as a baseline under both labellings.

Nothing here changes the production threshold. Measure first.

Usage:
    python scripts/eval_verifier_strict.py
    python scripts/eval_verifier_strict.py --out docs/eval_verifier_strict.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
MODEL = "cross-encoder/nli-MiniLM2-L6-H768"

from scripts.eval_verifier import bootstrap_auc, precision_at_recall  # noqa: E402
from src.extraction.verbalise import verbalise  # noqa: E402

TARGETS = {
    "right_vs_wrong": {  # target A: what the pipeline optimises today
        "pos": {"supported", "implied"},
        "neg": {"wrong"},
    },
    "supported_vs_rest": {  # target B: strict entailment
        "pos": {"supported"},
        "neg": {"implied", "wrong"},
    },
}


def average_precision(scores: List[float], labels: List[int]) -> float:
    """PR-AUC via the step-wise average-precision estimator."""
    order = sorted(zip(scores, labels), key=lambda kv: -kv[0])
    total_pos = sum(labels)
    if not total_pos:
        return float("nan")
    hits = 0
    ap = 0.0
    for rank, (_, y) in enumerate(order, start=1):
        if y == 1:
            hits += 1
            ap += hits / rank
    return ap / total_pos


def load_cases() -> List[Dict[str, Any]]:
    """All annotated triples from both sets, verdicts attached."""
    from scripts.reconcile_triple_annotation import (
        ANNOTATION, GAP, UNIFORM_GAP, load_gap,
    )

    drafts = [
        ROOT / "docs" / "eval_triples_gold_locomo_draft_model.jsonl",
        ROOT / "docs" / "eval_triples_gold_locomo_uniform_model.jsonl",
    ]
    verdicts: Dict[Tuple[str, str, str], str] = {}
    # The stratified verdicts live in the script's ANNOTATION table, the
    # uniform ones in a file. Both must be merged or one set silently
    # contributes nothing -- an empty class looks exactly like a low score.
    for stratum, _idx, s, p, o, v in ANNOTATION:
        verdicts[(stratum, s, p, o)] = v
    for g in load_gap([GAP, UNIFORM_GAP]):
        verdicts[(g["stratum"], g["s"], g["p"], g["o"])] = g["verdict"]

    cases: List[Dict[str, Any]] = []
    for draft in drafts:
        for line in draft.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            for t in r.get("asserted", []):
                v = verdicts.get((r["stratum"], t["s"], t["p"], t["o"]))
                if v is None:
                    continue
                cases.append({
                    "set": r["stratum"],
                    "text": r["text"],
                    "s": t["s"], "p": t["p"], "o": t["o"],
                    "extract_conf": float(t.get("c") or 0.0),
                    "verdict": v,
                })
    return cases


def evaluate(scores: List[float], cases: List[Dict[str, Any]],
             spec: Dict[str, set]) -> Dict[str, Any]:
    labels = [1 if c["verdict"] in spec["pos"] else 0 for c in cases]
    extract = [c["extract_conf"] for c in cases]

    auc, lo, hi = bootstrap_auc(scores, labels)
    e_auc, e_lo, e_hi = bootstrap_auc(extract, labels)
    p_v, t_v = precision_at_recall(scores, labels, 0.60)
    p_e, t_e = precision_at_recall(extract, labels, 0.60)

    return {
        "n": len(labels),
        "n_pos": sum(labels),
        "base_rate": round(sum(labels) / len(labels), 3),
        "verifier": {
            "auc": round(auc, 3),
            "auc_ci": [round(lo, 3), round(hi, 3)],
            "pr_auc": round(average_precision(scores, labels), 3),
            "p_at_recall_0.60": round(p_v, 3),
            "threshold_at_0.60": round(t_v, 4),
        },
        "extract_confidence": {
            "auc": round(e_auc, 3),
            "auc_ci": [round(e_lo, 3), round(e_hi, 3)],
            "pr_auc": round(average_precision(extract, labels), 3),
            "p_at_recall_0.60": round(p_e, 3),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    from sentence_transformers import CrossEncoder

    cases = load_cases()
    pairs = [(c["text"], verbalise(c["s"], c["p"], c["o"])) for c in cases]
    print(f"{len(cases)} annotated triples, model {args.model} "
          f"on {args.device}")

    model = CrossEncoder(args.model, max_length=512, device=args.device)
    id2label = {int(k): str(v).lower()
                for k, v in model.model.config.id2label.items()}
    ent = next(k for k, v in id2label.items() if "entail" in v)
    con = next(k for k, v in id2label.items() if "contradict" in v)

    logits = model.predict([[p, h] for p, h in pairs], convert_to_numpy=True)
    scores = [float(r[ent]) - float(r[con]) for r in logits]

    results = {name: evaluate(scores, cases, spec)
               for name, spec in TARGETS.items()}

    print(f"\n  {'target':22} {'n':>4} {'pos':>4} {'base':>6} "
          f"{'AUC':>6} {'95% CI':>16} {'PR-AUC':>7} {'P@R.6':>6}")
    for name, r in results.items():
        v = r["verifier"]
        print(f"  {name:22} {r['n']:4} {r['n_pos']:4} {r['base_rate']:6.3f} "
              f"{v['auc']:6.3f} [{v['auc_ci'][0]:.3f}, {v['auc_ci'][1]:.3f}] "
              f"{v['pr_auc']:7.3f} {v['p_at_recall_0.60']:6.3f}")

    print(f"\n  extraction confidence as baseline:")
    print(f"  {'target':22} {'AUC':>6} {'95% CI':>16} {'PR-AUC':>7} "
          f"{'P@R.6':>6}")
    for name, r in results.items():
        e = r["extract_confidence"]
        print(f"  {name:22} {e['auc']:6.3f} "
              f"[{e['auc_ci'][0]:.3f}, {e['auc_ci'][1]:.3f}] "
              f"{e['pr_auc']:7.3f} {e['p_at_recall_0.60']:6.3f}")

    # How separable is the implied class itself? If implied sits on the
    # wrong side of supported, no single threshold can separate them.
    by_verdict: Dict[str, List[float]] = {}
    for v, s in zip([c["verdict"] for c in cases], scores):
        by_verdict.setdefault(v, []).append(s)
    print(f"\n  mean verifier margin by hand verdict:")
    for v in ("supported", "implied", "wrong"):
        vals = by_verdict.get(v, [])
        print(f"    {v:12} {statistics.mean(vals):+.3f}  (n={len(vals)})")

    # The two-target AUCs above can hide the decisive fact: the verifier
    # separates wrong from not-wrong well while being blind to the
    # supported/implied distinction. The pairwise numbers state that
    # directly, and they are what decides whether any threshold on this
    # score can move strict precision at all.
    pairwise = {}
    for a, b in (("supported", "implied"), ("supported", "wrong"),
                 ("implied", "wrong")):
        sub = [(s, c["verdict"]) for s, c in zip(scores, cases)
               if c["verdict"] in (a, b)]
        pauc, plo, phi = bootstrap_auc(
            [s for s, _ in sub], [1 if v == a else 0 for _, v in sub])
        pairwise[f"{a}_vs_{b}"] = {
            "n": len(sub),
            "auc": round(pauc, 3),
            "auc_ci": [round(plo, 3), round(phi, 3)],
        }
    print(f"\n  pairwise AUC (the decisive number):")
    for k, v in pairwise.items():
        print(f"    {k:22} {v['auc']:6.3f} "
              f"[{v['auc_ci'][0]:.3f}, {v['auc_ci'][1]:.3f}]  n={v['n']}")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"model": args.model, "device": args.device,
             "cases": len(cases), "targets": results,
             "pairwise": pairwise},
            indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())