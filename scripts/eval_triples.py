#!/usr/bin/env python
"""Per-triple evaluation of SVO extraction.

The existing eval_extraction.py measures recall against a gold set, which
hid the actual problem: recall was fine, precision was not. It reported how
many gold triples were found and never asked what else came back. In the
live store that showed up as 'Henri Becquerel acquired Chemistry' sitting in
the knowledge graph with confidence 0.84, produced from a sentence with no
acquisition in it.

This measures precision directly, per asserted triple, which is the only way
to see a hallucinated relation. Three numbers per backend:

  recall      gold triples found
  precision   asserted triples that were actually in the sentence
  false       the asserted triples that were not -- listed, not just counted

The gold set in docs/eval_triples_gold.jsonl is adversarial on purpose:
passive voice, coordination, relative clauses, possessives, copular
definitions and questions, because those are the constructions that
produced the bad facts.

Usage:
    python scripts/eval_triples.py
    python scripts/eval_triples.py --show-all
    python scripts/eval_triples.py --threshold-sweep
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

GOLD = Path(__file__).resolve().parents[1] / "docs" / "eval_triples_gold.jsonl"

# Predicates that carry no relational claim. A triple using one of these is
# the same noise as 'X acquired Y' on a sentence with no acquisition.
NON_RELATIONAL = {
    "is", "was", "are", "were", "be", "been",
    "has", "have", "had",
    "mentions", "related_to", "co_occurs_with",
    "strongly_related", "weakly_related", "knows", "works_at",
}


def load_gold(path: Path = GOLD) -> List[Dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _norm(value: str) -> str:
    return " ".join(str(value).lower().replace("'s", " ").split())


def _triple_key(t: Any) -> Tuple[str, str, str]:
    """Normalise a gold triple given as a sequence, or an asserted one as a dict."""
    if isinstance(t, dict):
        parts = (t.get("subject", ""), t.get("predicate", ""), t.get("object", ""))
    else:
        parts = tuple(t)[:3]
    while len(parts) < 3:
        parts = parts + ("",)
    return (_norm(parts[0]), _norm(parts[1]), _norm(parts[2]))


def _matches(asserted: Dict[str, Any], gold: Any) -> bool:
    """Whether an asserted triple matches a gold one.

    Exact on all three slots, with articles and possessives stripped. Kept
    strict on purpose: a predicate is the claim, and accepting a different
    verb would hide the failure this eval exists to find.
    """
    return _triple_key(asserted) == _triple_key(gold)


def _false_kind(asserted: Dict[str, Any], gold: List[Sequence[str]]) -> Optional[str]:
    """Classify an asserted triple that matched no gold triple.

    Both kinds count against precision -- an asserted triple that the gold
    does not contain is wrong either way, and excluding mis-parses would
    report precision 1.0 on a sentence where the extractor attached the
    wrong agent to the right object.

      hallucinated  subject or object does not occur in the sentence at all
      mis-parse     both occur, but the asserted relation is not asserted
      wrong-predicate both occur and the pair is right, but the verb is not
    """
    if any(_matches(asserted, g) for g in gold):
        return None
    text = _norm(asserted.get("_text", ""))
    subject = _norm(asserted.get("subject", ""))
    obj = _norm(asserted.get("object", ""))
    if subject in text and obj in text:
        # Both ends are real words from the sentence. If some gold triple
        # pairs the same two entities, only the verb is wrong.
        for g in gold:
            if _norm(g[0]) == subject and _norm(g[2]) == obj:
                return "wrong-predicate"
        return "mis-parse"
    return "hallucinated"


def evaluate(
    sentences: List[Dict[str, Any]],
    show_all: bool = False,
    threshold_sweep: bool = False,
) -> Dict[str, Any]:
    from src.extraction.entity_utils import extract_triples_with_relex

    gold_total = 0
    gold_found = 0
    asserted_total = 0
    false_triples: List[Dict[str, Any]] = []
    missed: List[Dict[str, Any]] = []
    per_sentence = []

    for row in sentences:
        text = row["text"]
        gold = [tuple(t) for t in row.get("triples", [])]
        gold_total += len(gold)

        asserted = extract_triples_with_relex(text)
        for t in asserted:
            t["_text"] = text
        asserted_total += len(asserted)

        found_gold = []
        for g in gold:
            hit = next((a for a in asserted if _matches(a, g)), None)
            if hit:
                gold_found += 1
                found_gold.append(g)
            else:
                missed.append({"text": text, "gold": list(g)})

        fp = []
        for a in asserted:
            kind = _false_kind(a, gold)
            if kind:
                fp.append((a, kind))
        for a, kind in fp:
            false_triples.append({
                "text": text,
                "subject": a.get("subject"),
                "predicate": a.get("predicate"),
                "object": a.get("object"),
                "confidence": a.get("confidence"),
                "kind": kind,
            })

        per_sentence.append({
            "id": row.get("id"),
            "text": text,
            "gold": [list(g) for g in gold],
            "asserted": [
                {k: v for k, v in a.items() if k != "_text"} for a in asserted
            ],
            "found": len(found_gold),
            "false": len(fp),
            "note": row.get("note", ""),
        })

        if show_all:
            flag = "OK  " if not fp and len(found_gold) == len(gold) else "PROB"
            asserted_txt = [
                "-".join([str(a.get("subject")), str(a.get("predicate")),
                          str(a.get("object"))]) for a in asserted
            ]
            false_txt = [
                "-".join([str(a.get("subject")), str(a.get("predicate")),
                          str(a.get("object"))]) + f" ({kind})" for a, kind in fp
            ]
            print(f"  {flag} {row.get('id', '')}")
            print(f"       {text[:96]}")
            print(f"       gold     ({len(gold)}): "
                  f"{['-'.join(g) for g in gold]}")
            print(f"       asserted ({len(asserted)}): {asserted_txt}")
            if fp:
                print(f"       FALSE    ({len(fp)}): {false_txt}")
            if row.get("note"):
                print(f"       note: {row['note'][:88]}")

    recall = gold_found / gold_total if gold_total else 0.0
    precision = (
        (asserted_total - len(false_triples)) / asserted_total
        if asserted_total else 0.0
    )

    # Predicate distribution: the dominant failure mode is verb selection,
    # not entity selection, and that is only visible in aggregate.
    #
    # Both sides must be listed. Reporting only predicates that were
    # ASSERTED hides every predicate the model never emits -- and that class
    # turned out to be the largest single recall loss: six gold predicates
    # (wrote, designed, built, funded, integrated, provides) had zero
    # output and were simply absent from an asserted-only table.
    gold_preds: Dict[str, int] = {}
    for row in sentences:
        for t in row.get("triples", []):
            p = _norm(t[1])
            gold_preds[p] = gold_preds.get(p, 0) + 1
    got_preds: Dict[str, int] = {}
    for ps in per_sentence:
        for a in ps["asserted"]:
            p = _norm(a.get("predicate", ""))
            got_preds[p] = got_preds.get(p, 0) + 1

    predicate_table = []
    for p in sorted(set(gold_preds) | set(got_preds)):
        g = gold_preds.get(p, 0)
        a = got_preds.get(p, 0)
        predicate_table.append({
            "predicate": p,
            "gold": g,
            "asserted": a,
            "delta": a - g,
            # 0 recall on a predicate the gold actually uses means the model
            # cannot produce it at all -- a label-coverage gap, not a
            # threshold problem, since raising the threshold cannot help.
            "never_produced": bool(g > 0 and a == 0),
        })
    predicate_table.sort(key=lambda r: (-r["delta"], r["predicate"]))

    never_produced = [r["predicate"] for r in predicate_table
                      if r["never_produced"]]

    # Confusion matrix: gold predicate x predicted predicate for every
    # asserted triple whose subject/object pair matches a gold pair. This is
    # what separates "wrong verb" from "wrong entities" without guessing.
    confusion: Dict[str, Dict[str, int]] = {}
    gold_by_text = {r["text"]: [tuple(g) for g in r["gold"]]
                    for r in per_sentence}
    for ps in per_sentence:
        gold = gold_by_text[ps["text"]]
        for a in ps["asserted"]:
            if any(_matches(a, g) for g in gold):
                continue
            subject = _norm(a.get("subject", ""))
            obj = _norm(a.get("object", ""))
            pair_golds = [g for g in gold
                          if _norm(g[0]) == subject and _norm(g[2]) == obj]
            for g in pair_golds:
                row = confusion.setdefault(_norm(g[1]), {})
                row[_norm(a.get("predicate", ""))] = (
                    row.get(_norm(a.get("predicate", "")), 0) + 1
                )

    return {
        "backend": "relex",
        "sentences": len(sentences),
        "gold_triples": gold_total,
        "gold_found": gold_found,
        "asserted": asserted_total,
        "false_triples": len(false_triples),
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "hallucinated": sum(1 for f in false_triples
                            if f["kind"] == "hallucinated"),
        "mis_parse": sum(1 for f in false_triples
                         if f["kind"] == "mis-parse"),
        "wrong_predicate": sum(1 for f in false_triples
                               if f["kind"] == "wrong-predicate"),
        "predicate_table": predicate_table,
        "never_produced": never_produced,
        "confusion": confusion,
        "false_detail": false_triples,
        "missed_detail": missed,
        "per_sentence": per_sentence,
    }


def threshold_sweep(report: Dict[str, Any]) -> None:
    """Does the confidence score separate correct triples from wrong ones?

    If it did, precision would be recoverable by raising the threshold. If
    the distributions overlap, no threshold helps and the fix has to be
    structural -- gate the predicates that are systematically over-produced,
    or verify each candidate against the sentence. This decides which.
    """
    pairs: List[Tuple[float, bool]] = []
    gold_by_text = {r["text"]: [tuple(g) for g in r["gold"]]
                    for r in report["per_sentence"]}
    for ps in report["per_sentence"]:
        gold = gold_by_text[ps["text"]]
        for a in ps["asserted"]:
            correct = any(_matches(a, g) for g in gold)
            pairs.append((float(a.get("confidence") or 0.0), correct))
    if not pairs:
        return

    pos = [c for c, ok in pairs if ok]
    neg = [c for c, ok in pairs if not ok]
    print(f"\n  confidence: correct n={len(pos)} "
          f"range {min(pos):.3f}-{max(pos):.3f}" if pos else "")
    print(f"  confidence: wrong   n={len(neg)} "
          f"range {min(neg):.3f}-{max(neg):.3f}" if neg else "")

    print(f"\n  {'threshold':>10} {'kept':>5} {'correct':>8} "
          f"{'wrong':>6} {'precision':>10}")
    for t in (0.0, 0.5, 0.7, 0.8, 0.85, 0.9, 0.95, 0.97, 0.99):
        kept = [(c, ok) for c, ok in pairs if c >= t]
        if not kept:
            continue
        ok_n = sum(1 for _, ok in kept if ok)
        bad = len(kept) - ok_n
        print(f"  {t:10.2f} {len(kept):5} {ok_n:8} {bad:6} "
              f"{ok_n / len(kept):10.3f}")

    # Ranking quality: how often is a correct triple scored above a wrong one?
    wins = sum(1 for c1, ok1 in pairs if ok1
               for c2, ok2 in pairs if not ok2 and c1 > c2)
    total = len(pos) * len(neg)
    print(f"\n  pairwise separation (AUC of confidence): "
          f"{wins / total:.3f}" if total else "  AUC n/a")


def print_report(report: Dict[str, Any]) -> None:
    print("\n=== SVO triple extraction (relex) ===")
    print(f"  sentences          {report['sentences']}")
    print(f"  gold triples       {report['gold_triples']}")
    print(f"  found              {report['gold_found']}  "
          f"(recall {report['recall']:.3f})")
    print(f"  asserted           {report['asserted']}")
    print(f"  false              {report['false_triples']}  "
          f"(precision {report['precision']:.3f})")
    print(f"  by kind            hallucinated {report['hallucinated']}, "
          f"mis-parse {report['mis_parse']}, "
          f"wrong-predicate {report['wrong_predicate']}")

    print("\n  predicate distribution (both sides; delta = over- or "
          "under-production):")
    print(f"    {'predicate':16} {'gold':>5} {'asserted':>9} {'delta':>6}  note")
    for row in report["predicate_table"]:
        note = "NEVER PRODUCED" if row["never_produced"] else ""
        if row["asserted"] and not row["gold"]:
            note = "never in gold"
        print(f"    {row['predicate']:16} {row['gold']:5} {row['asserted']:9} "
              f"{row['delta']:+6}  {note}")

    if report["never_produced"]:
        print(f"\n  {len(report['never_produced'])} gold predicates the model "
              f"never emits: {report['never_produced']}")
        print("    These are a label-coverage gap, not a threshold problem: "
              "no confidence cut")
        print("    can recover a predicate the model does not produce.")

    if report["confusion"]:
        print("\n  wrong-verb confusion (same entities, gold -> predicted):")
        for gold_p, preds in report["confusion"].items():
            for pred_p, n in preds.items():
                print(f"    {gold_p:14} -> {pred_p:14} x{n}")

    if report["missed_detail"]:
        print("\n  missed gold triples:")
        for m in report["missed_detail"]:
            print(f"    {'-'.join(m['gold']):50} <- {m['text'][:50]}")

    if report["false_detail"]:
        print("\n  false triples:")
        for f in report["false_detail"]:
            print(f"    [{f['kind']:15}] {f['subject']} -[{f['predicate']}]-> "
                  f"{f['object']}  (conf {f['confidence']})")
            print(f"                      src={f['text'][:66]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--show-all", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    sentences = load_gold()
    report = evaluate(sentences, show_all=args.show_all)
    print_report(report)
    threshold_sweep(report)

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())