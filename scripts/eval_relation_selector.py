"""Can a downstream selector pick the right relation from the model's own candidates?

The stage audit isolated 27 of 53 counterfactual facts where the target
relation was reachable under an extended label space and something else won.
Those 27 isolate exactly one defect: which relation gets selected. The entity
pair is already correct, the target relation is already among the model's own
candidates, so nothing here is about candidates or about capacity.

This is a new task and is evaluated as one. It is not the production
verifier's task and its numbers must never be reported as verifier numbers:
the verifier decides one claim, this ranks N competing claims for one entity
pair. Reusing the earlier metrics would compare two different questions.

Candidate sets come from the extended-label probe, not the production one.
Taking candidates from the shipped pass would be circular: the target
relation cannot appear in a set drawn from labels that exclude it.

Shadow only. No production code path, no database write, no change to
verbalise(), the vocabulary or the frozen gold. The 17 CLAIM templates cover
the production predicates; everything else falls back to the de-sugared name,
which yields awkward phrasing for compound labels such as `pitched_to` or
`sat_on`. Those fallbacks are reported separately rather than quietly mixed
in, because an awkward hypothesis is not evidence that the relation is wrong.

Usage:
    python scripts/eval_relation_selector.py
    python scripts/eval_relation_selector.py --out docs/eval_relation_selector.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
CF = ROOT / "docs" / "eval_recall_gold_counterfactual.jsonl"
STAGES = ROOT / "docs" / "eval_extractor_stages.json"
GOLD_FILES = [ROOT / "docs" / "eval_recall_gold_pilot.jsonl",
              ROOT / "docs" / "eval_recall_gold_batch2.jsonl",
              ROOT / "docs" / "eval_recall_gold_expanded.jsonl"]

SELECTION = "pair_present_cue_present_wrong_label"


def norm(s: str) -> str:
    toks = [t for t in str(s).strip().lower().split() if t not in
            {"the", "a", "an"}]
    return " ".join(toks)


def load_texts() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for f in GOLD_FILES:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out.setdefault(r["id"], r["text"])
    return out


def slug(label: str) -> str:
    return str(label).strip().lower().replace(" ", "_")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="")
    ap.add_argument("--ent-threshold", type=float, default=0.2)
    ap.add_argument("--rel-threshold", type=float, default=0.2)
    args = ap.parse_args()

    from src.extraction.entity_utils import (
        _SIEVEON_ENTITY_LABELS, _SIEVEON_RELATION_LABELS, _get_relex,
    )
    from src.extraction.verbalise import CLAIM, verbalise

    stages = json.loads(STAGES.read_text(encoding="utf-8"))
    cases = [r for r in stages["results"] if r["class"] == SELECTION]
    facts = {json.loads(l)["id"] + "|" + json.loads(l)["s"] + "|"
             + json.loads(l)["p"] + "|" + json.loads(l)["o"]: json.loads(l)
             for l in CF.read_text(encoding="utf-8").splitlines() if l.strip()}
    texts = load_texts()

    counter_labels = sorted({f["p"] for f in facts.values()})
    extended_labels = list(_SIEVEON_RELATION_LABELS) + [
        c.replace("_", " ") for c in counter_labels]

    model = _get_relex()

    prepared: List[Dict[str, Any]] = []
    for i, c in enumerate(cases, 1):
        key = f'{c["id"]}|{c["s"]}|{c["p"]}|{c["o"]}'
        f = facts.get(key)
        text = texts.get(c["id"])
        if f is None or text is None:
            continue
        _e, rels = model.predict_relations(
            text, _SIEVEON_ENTITY_LABELS, extended_labels,
            threshold=args.ent_threshold,
            relation_threshold=args.rel_threshold)
        pair = (norm(c["s"]), norm(c["o"]))
        cands = sorted({slug(r.get("relation", ""))
                        for r in (rels or [])
                        if norm(r["head"]["text"]) == pair[0]
                        and norm(r["tail"]["text"]) == pair[1]})
        if not cands:
            continue
        prepared.append({
            "id": c["id"], "s": c["s"], "o": c["o"], "text": text,
            "target": c["p"], "candidates": cands,
            "family": c["family"],
            "target_in_candidates": c["p"] in cands,
            "target_templated": c["p"] in CLAIM,
            "fallback_candidates": [x for x in cands if x not in CLAIM],
        })
        if i % 10 == 0:
            print(f"  prepared {i}/{len(cases)}")

    from src.extraction.verifier import _get_verifier
    vmodel, v_entail, v_contra = _get_verifier()

    def margins(pairs):
        """Same scoring path the production verifier uses, so the ranking
        rests on the same signal. Returns entail-minus-contradiction."""
        import numpy as np
        logits = vmodel.predict([[p, h] for p, h in pairs],
                                convert_to_numpy=True)
        return [float(row[v_entail]) - float(row[v_contra])
                for row in np.atleast_2d(logits)]

    scored: List[Dict[str, Any]] = []
    for r in prepared:
        hyps = [verbalise(r["s"], p, r["o"]) for p in r["candidates"]]
        prem = [r["text"]] * len(hyps)
        ms = margins(list(zip(prem, hyps)))
        rank = sorted(zip(r["candidates"], hyps, ms),
                      key=lambda t: -t[2])
        r["ranked"] = [{"predicate": p, "hypothesis": h,
                        "margin": round(m, 4)}
                       for p, h, m in rank]
        r["top1"] = rank[0][0]
        r["top1_margin"] = round(rank[0][2], 4)
        r["target_rank"] = next(
            (i + 1 for i, (p, _h, _m) in enumerate(rank) if p == r["target"]),
            None)
        r["top1_margin_gap"] = round(rank[0][2] - rank[1][2], 4) \
            if len(rank) > 1 else None
        scored.append(r)

    n = len(scored)
    top1 = sum(1 for r in scored if r["top1"] == r["target"])
    top3 = sum(1 for r in scored
               if r["target_rank"] and r["target_rank"] <= 3)
    reachable = sum(1 for r in scored if r["target_in_candidates"])

    print(f"\n=== relation selector: shadow ranking over the model's own "
          f"candidates ===\n")
    print(f"  selection-failure cases audited   {len(cases)}")
    print(f"  with a non-empty candidate set    {n}")
    print(f"  target present among candidates   {reachable}")
    print(f"  target on a hand-written template "
          f"{sum(1 for r in scored if r['target_templated'])}")
    print()
    print(f"  top-1 accuracy     {top1 / n:.3f}   ({top1}/{n})" if n else "")
    print(f"  top-3 accuracy     {top3 / n:.3f}   ({top3}/{n})" if n else "")
    if reachable:
        print(f"  ceiling (target reachable) {reachable}/{n} = "
              f"{reachable / n:.3f}")
    print()
    print("  Baseline for the same cases is 0/27: the shipped output chose the")
    print("  wrong relation for every one of them.")
    print()
    print("  Fallback verbalisation is reported apart. A candidate without a")
    print("  CLAIM template is de-sugared into 'X attended Y', which is an")
    print("  awkward hypothesis and not evidence that the relation is wrong.")

    if n:
        templ = [r for r in scored if r["target_templated"]]
        if templ:
            t1 = sum(1 for r in templ if r["top1"] == r["target"])
            print(f"\n  restricted to hand-templated targets: top-1 "
                  f"{t1}/{len(templ)} = {t1 / len(templ):.3f}")
        fam = defaultdict(lambda: [0, 0])
        for r in scored:
            fam[r["family"]][1] += 1
            if r["top1"] == r["target"]:
                fam[r["family"]][0] += 1
        print(f"\n  {'family':28} {'n':>3} {'top1':>5} {'acc':>7}")
        for k in sorted(fam, key=lambda k: -fam[k][1]):
            c, tot = fam[k]
            print(f"  {k:28} {tot:3} {c:5} {c / tot:7.3f}")
        print(f"\n  {'predicate':22} {'n':>3} {'top1':>5}")
        byp = defaultdict(lambda: [0, 0])
        for r in scored:
            byp[r["target"]][1] += 1
            if r["top1"] == r["target"]:
                byp[r["target"]][0] += 1
        for k in sorted(byp, key=lambda k: -byp[k][1]):
            c, tot = byp[k]
            print(f"  {k:22} {tot:3} {c:5}")
        print("\n  cases:")
        for r in scored:
            ok = "OK " if r["top1"] == r["target"] else "MISS"
            print(f"    {ok} {r['s']} -> {r['o']}: target {r['target']} "
                  f"(rank {r['target_rank']} of {len(r['candidates'])})")
            print(f"        top1: {r['ranked'][0]['predicate']} "
                  f"{r['top1_margin']:+.3f}")

    print("\n  These are shadow numbers for a new task. They are not verifier")
    print("  numbers and must not be reported alongside them.")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "task": "relation selection over the model's own candidates",
            "cases": n, "target_reachable": reachable,
            "top1": top1, "top3": top3,
            "top1_accuracy": round(top1 / n, 4) if n else None,
            "baseline_shipped": "0/27",
            "thresholds": {"ent": args.ent_threshold,
                           "rel": args.rel_threshold},
            "results": scored,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())