"""Rank the remaining sentences for gold annotation by text alone.

The goal is ~100 gold facts, and annotating all 37 remaining sentences in
order would spend most of the budget on sentences that carry none. That is
wasteful but harmless. The dangerous alternative -- picking the sentences
where the extractor already claimed something -- is not harmless: it biases
the recall measurement toward facts the model finds, which is exactly the
population where recall losses would be invisible.

So the ranking here uses the sentence text and nothing else. No claim
count, no confidence, no predicate from the extractor output is read. The
author of this script had seen the claims while writing the pilot, which is
why the rule is a static lexicon applied mechanically rather than a
judgement call: the ranking can be re-derived and checked, and its inputs
are visible.

Two populations matter and must not be conflated. High-density sentences
yield gold facts and answer "which facts get missed". Sentences that carry
no graphable fact, or only facts the schema cannot express, answer a
different question -- whether the precision denominator is being inflated
by gold-annotator strictness. Both are needed; this script only prioritises
the first, and reports how many of the remainder fall into the second.

Usage:
    python scripts/select_recall_batch.py
    python scripts/select_recall_batch.py --count 10 --scaffold
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "eval_triples_gold_locomo_uniform.jsonl"

# Verbs that tend to state a durable relation between named entities.
RELATION_BEARING = {
    "acquired", "bought", "purchased", "owns", "owned", "founded", "started",
    "works", "worked", "volunteers", "attends", "attended", "wrote", "written",
    "created", "made", "built", "opened", "runs", "ran", "joined", "led",
    "leads", "managed", "moved", "lives", "lived", "visited", "traveled",
    "provides", "provided", "gave", "given", "received", "offered", "met",
    "played", "plays", "teaches", "taught", "studies", "graduated",
    "married", "born", "hired", "served", "supported", "introduced",
}

# Verbs that describe a state, a preference or a plan. Real sentences, but
# they rarely yield a durable graph edge.
NON_RELATIONAL = {
    "feels", "find", "finds", "enjoys", "appreciates", "believes", "thinks",
    "wants", "plans", "hopes", "likes", "loves", "prefers", "regrets",
    "struggles", "overwhelming", "supportive", "encouraging", "grateful",
    "excited", "trying", "wondering", "considering", "declined",
}

NEGATION = {"not", "never", "no", "nor", "without", "hardly", "neither"}


def analyse(text: str) -> Dict[str, Any]:
    toks = [t for t in re.split(r"[^\w']+", text.lower()) if t]
    counts = {"RELATION_BEARING": 0, "NON_RELATIONAL": 0}
    hits: List[str] = []
    for t in toks:
        if t in RELATION_BEARING:
            counts["RELATION_BEARING"] += 1
            hits.append(t)
        elif t in NON_RELATIONAL:
            counts["NON_RELATIONAL"] += 1
    # Proper nouns and possessives, as a proxy for how many entities are
    # named. Extracted from the raw text, not from any extractor output.
    caps = re.findall(r"\b[A-Z][a-z]+\b", text)
    poss = len(re.findall(r"\b[A-Z][a-z]+'s\b", text))
    neg = sum(1 for t in toks if t in NEGATION)
    score = (2 * counts["RELATION_BEARING"] + min(len(caps), 4)
             + min(poss, 2) - 2 * counts["NON_RELATIONAL"] - 2 * neg)
    return {"score": score, "relation_hits": sorted(set(hits)),
            "nonrelational": counts["NON_RELATIONAL"],
            "entities": len(caps), "negations": neg}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--scaffold", action="store_true",
                    help="write the scaffold file for the selected batch")
    args = ap.parse_args()

    from scripts.show_for_recall_annotation import PILOT_INDICES, remaining

    rows = [json.loads(l) for l in
            SOURCE.read_text(encoding="utf-8").splitlines() if l.strip()]
    rest = remaining(rows)

    ranked: List[Tuple[int, Dict[str, Any]]] = []
    for i in rest:
        a = analyse(rows[i - 1]["text"])
        ranked.append((i, a))
    ranked.sort(key=lambda kv: (-kv[1]["score"], kv[0]))

    print(f"=== extractor-blind ranking of {len(rest)} remaining sentences ===")
    print("    (no claim, confidence or extractor predicate is read here)\n")
    print(f"  {'#':>3} {'idx':>4} {'score':>6} {'ent':>4} {'hit':>4}  "
          f"relation verbs")
    for n, (i, a) in enumerate(ranked[:args.count], start=1):
        print(f"  {n:3} {i:4} {a['score']:6} {a['entities']:4} "
              f"{len(a['relation_hits']):4}  {','.join(a['relation_hits'])}")

    print(f"\n  selected {min(args.count, len(ranked))} of {len(rest)}")
    zero = sum(1 for _, a in ranked if a["score"] <= 0)
    print(f"  {zero} remaining sentences score 0 or below: no relation verb, "
          f"or state and plan language only.\n  Those are the scope and "
          f"vocabulary-gap population and still need annotating, but they "
          f"yield few gold facts.")

    if args.scaffold:
        out = ROOT / "docs" / "eval_recall_gold_batch2.jsonl"
        picked = [i for i, _ in ranked[:args.count]]
        out.write_text("\n".join(
            json.dumps({"id": rows[i - 1]["id"], "text": rows[i - 1]["text"],
                        "graphable": None, "triples": None,
                        "excluded": [], "schema_gap": [], "by": "unannotated"},
                       ensure_ascii=False) for i in picked) + "\n",
            encoding="utf-8")
        print(f"\nwrote {out.relative_to(ROOT)} ({len(picked)} rows)")

    print("\n  For annotation, print the sentences with the extractor output")
    print("  withheld:  python scripts/show_for_recall_annotation.py "
          "--batch2 --count 10")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())