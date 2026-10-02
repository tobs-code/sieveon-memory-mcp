"""Full-set evaluation: does the selector help where it is not already failing?

The failure-set run showed the ranking signal works, 20 of 26 selection
failures corrected, and the template control ruled out phrasing as the
explanation. That set is selected by the very failure it fixes, so it cannot
answer whether a selector would help in general or would break what already
works. This script does.

The guard is the 44 current-scorable gold facts, all of them, including the
26 the shipped pipeline already finds. A selector is only worth shipping if
it keeps those. Everything is shadow: the same 17-label production model,
the same frozen MiniLM2 scorer, the same frozen gold, no database write.

Four numbers decide it:

    recall                 found / 44, against the 0.591 baseline
    clean recall           clean predicates only, against 0.205
    corrected              previously-wrong claims the selector gets right
    regressions            previously-right claims the selector breaks

Regressions are the one that can kill the idea on its own. Correcting a
wrong relation is worth nothing if it costs two correct ones, and a metric
that reports only corrected would hide exactly that.

Usage:
    python scripts/eval_selector_full_set.py
    python scripts/eval_selector_full_set.py --out docs/eval_selector_full.json
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
GOLD_FILES = [ROOT / "docs" / "eval_recall_gold_pilot.jsonl",
              ROOT / "docs" / "eval_recall_gold_batch2.jsonl",
              ROOT / "docs" / "eval_recall_gold_expanded.jsonl"]
CLAIM_FILES = [ROOT / "docs" / "eval_triples_gold_locomo_uniform_model.jsonl",
               ROOT / "docs" / "eval_recall_claims_expanded.jsonl"]


def norm(s: str) -> str:
    toks = [t for t in str(s).strip().lower().split() if t not in
            {"the", "a", "an"}]
    return " ".join(toks)


def slug(label: str) -> str:
    return str(label).strip().lower().replace(" ", "_")


def _frozen_baseline():
    """Baseline read from the frozen harness output, never recomputed here.

    An earlier version counted gold facts per claim and reported 11 clean
    where the harness reports 9: the harness consumes one claim per gold
    fact, a fact-keyed counter does not. Reimplementing a frozen metric is
    how two numbers for the same thing end up in circulation, so the
    authority stays eval_recall_pilot.json, produced by
    scripts/eval_recall_harness.py.
    """
    d = json.loads((ROOT / "docs" / "eval_recall_pilot.json")
                   .read_text(encoding="utf-8"))
    # In the harness output `found` is the CLEAN count and `imprecise` is
    # separate, so the broad recall numerator is found + imprecise. Its
    # `gold` figure is the total including the one fact outside the
    # vocabulary, so the scorable denominator has that removed.
    from scripts.eval_recall_harness import production_vocabulary
    V = production_vocabulary()
    unscorable = sum(
        1 for f in GOLD_FILES if f.exists() for line in
        f.read_text(encoding="utf-8").splitlines() if line.strip()
        for t in (json.loads(line).get("triples") or [])
        if t[1] not in V)
    return {"found": d["found"] + d["imprecise"], "clean": d["found"],
            "gold": d["gold"] - unscorable}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="")
    ap.add_argument("--ent-threshold", type=float, default=0.2)
    ap.add_argument("--rel-threshold", type=float, default=0.2)
    args = ap.parse_args()

    from scripts.counterfactual_templates import (
        COUNTERFACTUAL_CLAIM, check_templates,
    )
    bad = check_templates()
    if bad:
        print(f"  {len(bad)} templates failed validation")
        return 2

    from src.extraction.entity_utils import (
        _SIEVEON_ENTITY_LABELS, _SIEVEON_RELATION_LABELS, _get_relex,
    )
    from src.extraction.verbalise import CLAIM
    from src.extraction.verifier import _get_verifier
    import numpy as np

    vocab = set(CLAIM)

    texts: Dict[str, str] = {}
    gold_rows: Dict[str, Dict[str, Any]] = {}
    for f in GOLD_FILES:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                texts.setdefault(r["id"], r["text"])
                gold_rows.setdefault(r["id"], r)

    shipped: Dict[str, List[Dict[str, Any]]] = {}
    for f in CLAIM_FILES:
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                shipped.setdefault(r["id"], []).extend(r.get("asserted", []))

    model = _get_relex()
    vmodel, v_entail, v_contra = _get_verifier()

    def claim(rel: str, s: str, o: str) -> str:
        if rel in COUNTERFACTUAL_CLAIM:
            return COUNTERFACTUAL_CLAIM[rel].format(s=s, o=o)
        from src.extraction.verbalise import verbalise
        return verbalise(s, rel, o)

    # Every sentence with scorable gold facts, plus every sentence with
    # shipped claims, so regressions on claims without gold are visible too.
    targets = [i for i in gold_rows if any(
        t[1] in vocab for t in (gold_rows[i].get("triples") or []))]
    probe_ids = sorted(set(targets) | set(shipped))

    recs: List[Dict[str, Any]] = []
    for n, sid in enumerate(probe_ids, 1):
        text = texts.get(sid)
        if text is None:
            continue
        gold = [t for t in (gold_rows.get(sid, {}).get("triples") or [])
                if t[1] in vocab]
        ship = shipped.get(sid, [])
        gold_keys = {(norm(t[0]), norm(t[1]), norm(t[2])) for t in gold}

        ship_found = [c for c in ship
                      if (norm(c["s"]), norm(c["p"]), norm(c["o"]))
                      in gold_keys]
        ship_wrong = [c for c in ship
                      if (norm(c["s"]), norm(c["p"]), norm(c["o"]))
                      not in gold_keys]

        try:
            _e, rels = model.predict_relations(
                text, _SIEVEON_ENTITY_LABELS,
                list(_SIEVEON_RELATION_LABELS)
                + [c.replace("_", " ") for c in COUNTERFACTUAL_CLAIM],
                threshold=args.ent_threshold,
                relation_threshold=args.rel_threshold)
        except Exception:  # noqa: BLE001
            continue

        by_pair: Dict[Tuple[str, str], List[str]] = defaultdict(list)
        # Keep the original surface strings for the hypothesis. Ranking keys
        # are normalised, but the text the verifier sees must be the same
        # text the pipeline would verbalise, or the comparison against the
        # baseline is quietly comparing two different inputs.
        surface: Dict[Tuple[str, str], Tuple[str, str]] = {}
        for r in rels or []:
            try:
                h_raw = str(r["head"]["text"]).strip()
                t_raw = str(r["tail"]["text"]).strip()
                h = norm(h_raw)
                t = norm(t_raw)
                p = slug(r.get("relation", ""))
            except (KeyError, TypeError, AttributeError):
                continue
            by_pair[(h, t)].append(p)
            surface.setdefault((h, t), (h_raw, t_raw))

        sel_found = 0
        sel_clean = 0
        regressed = 0
        corrected = 0
        details = []
        for (h, t), cands in by_pair.items():
            # Only rank pairs that the pipeline actually asserts something
            # for. A selector that also fires on pairs the extractor never
            # claimed would be doing candidate generation, which is a
            # separate defect and is measured separately.
            base = [c for c in ship
                    if norm(c["s"]) == h and norm(c["o"]) == t]
            if not base:
                continue
            cands = sorted(set(cands))
            h_raw, t_raw = surface[(h, t)]
            hyps = [claim(p, h_raw, t_raw) for p in cands]
            logits = vmodel.predict([[text, h_] for h_ in hyps],
                                    convert_to_numpy=True)
            ms = [float(row[v_entail]) - float(row[v_contra])
                  for row in np.atleast_2d(logits)]
            top = cands[max(range(len(cands)), key=lambda i: ms[i])]
            top_key = (h, top, t)
            if top_key in gold_keys:
                sel_found += 1
                if any(k[1] == top and top in CLAIM for k in gold_keys):
                    pass
                for g in gold:
                    if (norm(g[0]), norm(g[1]), norm(g[2])) == top_key:
                        if len(g) > 3 and g[3] == "imprecise":
                            pass
                        else:
                            sel_clean += 1
            had_correct = any((norm(c["s"]), norm(c["p"]), norm(c["o"]))
                              in gold_keys for c in base)
            if had_correct and top_key not in gold_keys:
                regressed += 1
                details.append({"kind": "regression", "pair": [h, t],
                                "was": sorted({c["p"] for c in base
                                               if (norm(c["s"]), norm(c["p"]),
                                                   norm(c["o"])) in gold_keys}),
                                "now": top})
            if not had_correct and top_key in gold_keys:
                corrected += 1
                details.append({"kind": "correction", "pair": [h, t],
                                "was": sorted({c["p"] for c in base}),
                                "now": top})
        recs.append({"id": sid, "gold": len(gold),
                     "shipped_found": len(ship_found),
                     "shipped_wrong": len(ship_wrong),
                     "selected_found": sel_found, "selected_clean": sel_clean,
                     "corrected": corrected, "regressed": regressed,
                     "details": details})
        if n % 20 == 0:
            print(f"  probed {n}/{len(probe_ids)}")

    ship_found_keys = set()
    ship_clean_keys = set()
    # The baseline is read from the frozen harness rather than recomputed
    # here. An earlier version counted gold facts per claim and reported
    # 11 clean where the harness reports 9, because the harness consumes one
    # claim per gold fact while a fact-keyed counter does not. Reimplementing
    # a frozen metric is how two different numbers for the same thing get
    # reported, so the authority stays the harness.
    hb = _frozen_baseline()
    ship_found = hb["found"]
    ship_clean = hb["clean"]
    n_gold = hb["gold"]
    sel_found = sum(r["selected_found"] for r in recs)
    sel_clean = sum(r["selected_clean"] for r in recs)
    corrected = sum(r["corrected"] for r in recs)
    regressed = sum(r["regressed"] for r in recs)

    print(f"\n=== selector on the full set ===\n")
    print(f"  sentences probed        {len(recs)}   "
          f"(gold-bearing and claim-bearing)")
    print(f"  scorable gold facts     {n_gold}")
    print()
    print(f"  {'measure':32} {'baseline':>10} {'selector':>10}")
    print(f"  {'scorable recall':32} "
          f"{ship_found / n_gold:10.3f} {sel_found / n_gold:10.3f}")
    print(f"  {'  absolute':32} {ship_found:>10} {sel_found:>10}")
    print(f"  {'clean recall':32} "
          f"{ship_clean / n_gold:10.3f} {sel_clean / n_gold:10.3f}")
    print(f"  {'  absolute':32} {ship_clean:>10} {sel_clean:>10}")
    print()
    print(f"  corrected wrong-label claims   {corrected}")
    print(f"  regressions on correct claims   {regressed}")
    print()
    print("  Baseline is 26/44 = 0.591 recall and 9/44 = 0.205 clean. A selector")
    print("  that corrects but also regresses has not helped.")

    if regressed or corrected:
        print("\n  detail:")
        for r in recs:
            for d in r["details"]:
                print(f"    {d['kind']:11} {d['pair'][0]} -> {d['pair'][1]}: "
                      f"{', '.join(d['was'])} -> {d['now']}")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "scorable_gold": n_gold,
            "baseline": {"recall": round(ship_found / n_gold, 4),
                         "found": ship_found, "clean": ship_clean},
            "selector": {"recall": round(sel_found / n_gold, 4),
                         "found": sel_found, "clean": sel_clean},
            "corrected": corrected, "regressed": regressed,
            "thresholds": {"ent": args.ent_threshold,
                           "rel": args.rel_threshold},
            "records": recs,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())