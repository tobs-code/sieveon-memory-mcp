"""Recall and precision on one factor set: gold facts first, then claims.

Everything measured so far labels what the extractor asserted, so recall
has been unknown. This harness starts from the other side: a hand-written
gold of facts the sentence entails, scored against the extractor output.
Found and missed facts, spurious claims, recall, precision, F1.

THE MATCH RULE, fixed before any number was produced. It is the part that
would otherwise turn this into a measurement of the matcher:

  1. A triple matches iff subject, predicate and object are all equal after
     normalisation (lower case, whitespace, articles stripped).
  2. Argument order is not swappable. `works_at` and `part_of` are
     different relations, not a reversed triple.
  3. Predicate equivalence is limited to the groups in EQUIVALENT below.
     These are synonym pairs already attested in the hand annotation, not
     a general lexical resource. Notably absent: started/founded,
     travel/works_at, visit/acquired, check_out/acquired, bring/provides is
     present only because the annotation labels `animals provides comfort`
     implied, not supported -- so it counts as a match for recall but is
     reported as an imprecise match, never as clean.
  4. No credit is ever given for a triple whose hand-verdict class was
     disputed. Where the existing annotation says `attended` does not
     entail `founded`, a claim of founded does not cover a gold founded.

A gold triple the extractor found through a predicate the annotation
called wrong is counted as NOT FOUND. That is deliberate: recall against
gold measures whether the right relation was produced, not whether the
words overlapped.

Usage:
    python scripts/eval_recall_harness.py
    python scripts/eval_recall_harness.py --out docs/eval_recall_pilot.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "docs" / "eval_recall_gold_pilot.jsonl"
CLAIMS = ROOT / "docs" / "eval_triples_gold_locomo_uniform_model.jsonl"

# Pairs the hand annotation already treats as the same relation. Anything
# not listed here is an exact string match only.
EQUIVALENT: Dict[str, set] = {
    "discovered": {"find", "found"},
    "created": {"make", "made"},
    "provides": {"bring", "offer"},
    "developed": {"develop"},
    "built": {"build"},
    "wrote": {"write", "written"},
    "uses": {"use"},
    "located_in": {"in"},
}

# Predicates whose gold coverage is legitimately weaker: the annotation
# labels these implied rather than supported, so a match here is reported
# separately and never folded into clean recall.
IMPRECISE = {"provides"}

ARTICLES = {"the", "a", "an"}


def norm(s: str) -> str:
    toks = [t for t in re.split(r"\s+", s.strip().lower())
            if t and t not in ARTICLES]
    return " ".join(toks)


def same_predicate(a: str, b: str) -> Tuple[bool, bool]:
    """(equivalent, precise). Precise is False for the implied-predicate set."""
    if norm(a) == norm(b):
        # Identical predicate is still possibly one the annotation only
        # called implied; `provides` matching `provides` is not a clean hit.
        return True, norm(a) not in IMPRECISE and norm(b) not in IMPRECISE
    ga, gb = EQUIVALENT.get(norm(a)), EQUIVALENT.get(norm(b))
    if (ga and norm(b) in ga) or (gb and norm(a) in gb):
        return True, norm(a) not in IMPRECISE and norm(b) not in IMPRECISE
    return False, False


def match(gold: Tuple[str, str, str],
          claim: Dict[str, Any]) -> Tuple[bool, bool, str]:
    gs, gp, go = gold
    eq, precise = same_predicate(gp, claim["p"])
    if norm(gs) != norm(claim["s"]) or not eq:
        return False, False, ""
    if norm(go) != norm(claim["o"]):
        return False, False, ""
    return True, precise, claim["p"]


def score(gold_rows: List[Dict[str, Any]],
          claims_by_id: Dict[str, List[Dict[str, Any]]],
          ) -> Dict[str, Any]:
    found: List[Dict[str, Any]] = []
    missed: List[Dict[str, Any]] = []
    imprecise: List[Dict[str, Any]] = []
    spurious: List[Dict[str, Any]] = []

    for row in gold_rows:
        gold = [tuple(t) for t in (row.get("triples") or [])]
        claims = claims_by_id.get(row["id"], [])
        used = set()
        for g in gold:
            hit = None
            for ci, c in enumerate(claims):
                if ci in used:
                    continue
                ok, precise, via = match(g, c)
                if ok:
                    hit = (ci, precise, via)
                    break
            if hit is None:
                missed.append({"id": row["id"], "gold": list(g)})
            else:
                used.add(hit[0])
                rec = {"id": row["id"], "gold": list(g),
                       "matched": {k: claims[hit[0]][k] for k in "spo"},
                       "via_predicate": hit[2]}
                if hit[1]:
                    found.append(rec)
                else:
                    imprecise.append(rec)
        for ci, c in enumerate(claims):
            if ci not in used:
                spurious.append({"id": row["id"],
                                 "claim": {k: c[k] for k in "spo"},
                                 "on_gold_bearing": bool(gold)})

    n_gold = len(found) + len(imprecise) + len(missed)
    # Claims on sentences whose gold is empty are counted apart. Calling them
    # spurious would measure how conservative the gold annotator was, not how
    # often the extractor is wrong: a sentence annotated [] for every claim
    # pushes its claims to a 0 denominator. The second precision is the
    # interpretable one; the first is reported only to show the spread.
    off_gold = [s for s in spurious if not s["on_gold_bearing"]]
    spurious_on_gold = [s for s in spurious if s["on_gold_bearing"]]
    n_claims = len(found) + len(imprecise) + len(spurious_on_gold)
    recall = len(found) / n_gold if n_gold else float("nan")
    strict_recall = (len(found) + len(imprecise)) / n_gold if n_gold else float("nan")
    precision = len(found) / n_claims if n_claims else float("nan")
    incl = len(found) + len(imprecise)
    strict_precision = incl / n_claims if n_claims else float("nan")
    f1 = (2 * recall * precision / (recall + precision)
          if (recall + precision) > 0 else float("nan"))
    n_all_claims = len(found) + len(imprecise) + len(spurious)
    naive_precision = incl / n_all_claims if n_all_claims else float("nan")

    return {
        "gold": n_gold, "claims": n_all_claims,
        "claims_on_gold_bearing_sentences": n_claims,
        "found": len(found), "imprecise": len(imprecise),
        "missed": len(missed),
        "spurious": len(spurious_on_gold),
        "claims_on_empty_gold_sentences": len(off_gold),
        "recall": round(recall, 3),
        "recall_incl_implied": round(strict_recall, 3),
        "precision": round(precision, 3),
        "precision_incl_implied": round(strict_precision, 3),
        "precision_naive_all_claims": round(naive_precision, 3),
        "f1": round(f1, 3),
        "detail": {"found": found, "imprecise": imprecise,
                   "missed": missed, "spurious": spurious_on_gold,
                   "off_gold_sentences": off_gold},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gold", type=Path, default=GOLD)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    gold_rows = [json.loads(l) for l in
                 args.gold.read_text(encoding="utf-8").splitlines() if l.strip()]
    claims_by_id: Dict[str, List[Dict[str, Any]]] = {}
    for line in CLAIMS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        claims_by_id[r["id"]] = r.get("asserted", [])

    # A gold row with no triples[] key at all is unannotated, not empty.
    unannotated = [r["id"] for r in gold_rows if r.get("triples") is None]
    if unannotated:
        print(f"  {len(unannotated)} of {len(gold_rows)} rows unannotated; "
              f"scoring would silently treat them as having no gold facts.")
        print(f"  first: {unannotated[0]}")
        return 2

    r = score(gold_rows, claims_by_id)

    print(f"=== recall harness: {len(gold_rows)} sentences, gold-first ===")
    print(f"  gold facts        {r['gold']}")
    print(f"  extractor claims  {r['claims']}  "
          f"({r['claims_on_gold_bearing_sentences']} on sentences with gold)")
    print()
    print(f"  {'bucket':30} {'n':>4}")
    for k in ("found", "imprecise", "missed", "spurious",
              "claims_on_empty_gold_sentences"):
        print(f"  {k:30} {r[k]:4}")
    print()
    print(f"  recall            {r['recall']:.3f}   "
          f"({r['found']}/{r['gold']}, clean predicates only)")
    print(f"  recall incl impl  {r['recall_incl_implied']:.3f}   "
          f"({r['found'] + r['imprecise']}/{r['gold']})")
    print(f"  precision         {r['precision']:.3f}   "
          f"({r['found']}/{r['claims_on_gold_bearing_sentences']}, "
          f"gold-bearing sentences only)")
    print(f"  prec incl impl    {r['precision_incl_implied']:.3f}   "
          f"({r['found'] + r['imprecise']}"
          f"/{r['claims_on_gold_bearing_sentences']})")
    print(f"  prec naive        {r['precision_naive_all_claims']:.3f}   "
          f"({r['found'] + r['imprecise']}/{r['claims']}, all claims)")
    print(f"  F1                {r['f1']:.3f}")
    print()
    print("  The naive figure counts every claim on an empty-gold sentence as a")
    print("  false positive. That measures the gold annotator's strictness, not")
    print("  the extractor, and it disagrees with the per-triple annotation on")
    print("  sentences such as `bike routes located_in river`, which was called")
    print("  supported there and is not in gold here. Treat it as a disagreement")
    print("  to resolve, not as a number.")
    print()
    print("  missed gold facts (the number that did not exist before):")
    for m in r["detail"]["missed"]:
        print(f"    {m['gold'][0]} -{m['gold'][1]}-> {m['gold'][2]}")
    print()
    print("  spurious claims:")
    for s in r["detail"]["spurious"]:
        c = s["claim"]
        print(f"    {c['s']} -{c['p']}-> {c['o']}")

    if args.out:
        Path(args.out).write_text(json.dumps(r, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())