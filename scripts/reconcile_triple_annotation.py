"""Reconcile the hand annotation against what the extractor asserted.

Three things this does that a plain counter cannot:

  1. Every asserted triple must carry a verdict. A missing one is reported
     rather than silently dropped, because an unlabelled triple that is not
     counted is an unlabelled triple that is not wrong either -- it would
     inflate precision by simply not existing.
  2. "implied" counts as correct but is reported separately from "supported",
     because a right proposition attached to a slightly wrong predicate is a
     different problem from a wrong fact, and they call for different fixes.
  3. Recall is not measurable from this annotation. It labels triples the
     model asserted; it says nothing about triples it should have found and
     did not. Reporting a recall here would be a fabrication.

Usage:
    python scripts/reconcile_triple_annotation.py
    python scripts/reconcile_triple_annotation.py --out docs/eval_triples_gold_locomo.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "docs" / "eval_triples_gold_locomo_draft_model.jsonl"
GAP = ROOT / "docs" / "eval_triples_annotation_gap.jsonl"
UNIFORM_GAP = ROOT / "docs" / "eval_triples_annotation_uniform.jsonl"

SUPPORTED = "supported"
IMPLIED = "implied"
WRONG = "wrong"

# (stratum, index, subject, predicate, object, verdict) -- index is 1-based
# within the stratum, matching show_for_annotation.py output.
A = "supported"
I = "implied"
W = "wrong"

ANNOTATION: List[Tuple[str, int, str, str, str, str]] = [
    # ── active-verb ────────────────────────────────────────────────────
    ("active-verb", 1, "Joanna", "wrote", "new script", A),
    ("active-verb", 3, "John", "works_at", "firefighting brigade", A),
    ("active-verb", 3, "John", "founded", "firefighting brigade", W),
    ("active-verb", 3, "John", "part_of", "firefighting brigade", A),
    ("active-verb", 6, "Audrey", "discovered", "awesome spot", W),
    ("active-verb", 7, "Sam", "created", "new diet", W),
    ("active-verb", 7, "Sam", "developed", "new diet", W),
    ("active-verb", 7, "Sam", "developed", "exercise routine", W),
    ("active-verb", 9, "John", "works_at", "hiking club", W),
    ("active-verb", 9, "John", "founded", "hiking club", W),
    ("active-verb", 9, "John", "part_of", "hiking club", A),
    ("active-verb", 11, "Tim", "founded", "fantasy literature forum", W),
    ("active-verb", 11, "Tim", "created", "favorite books", W),
    ("active-verb", 11, "Tim", "wrote", "favorite books", W),
    ("active-verb", 12, "Audrey", "works_at", "small garden", I),
    ("active-verb", 12, "Audrey", "built", "small garden", W),
    ("active-verb", 12, "Audrey", "discovered", "peace", A),
    ("active-verb", 12, "Audrey", "discovered", "relaxation", A),
    ("active-verb", 13, "Andrew", "acquired", "plants", W),
    ("active-verb", 13, "Andrew", "designed", "plants", W),
    ("active-verb", 13, "Andrew", "built", "house", W),
    # ── coordination ────────────────────────────────────────────────────
    ("coordination", 1, "Jon", "works_at", "dance studio", A),
    ("coordination", 2, "John", "developed", "new perspectives", W),
    ("coordination", 2, "John", "developed", "tackling challenges", W),
    ("coordination", 2, "John", "uses", "energy", I),
    ("coordination", 4, "Joanna", "created", "stories", W),
    ("coordination", 4, "Joanna", "wrote", "stories", W),
    ("coordination", 4, "Joanna", "created", "personal experiences", W),
    ("coordination", 4, "Joanna", "created", "feelings", W),
    ("coordination", 5, "Caroline", "created", "hand-painted bowl", W),
    ("coordination", 5, "Caroline", "acquired", "hand-painted bowl", A),
    ("coordination", 5, "Caroline", "designed", "hand-painted bowl", W),
    ("coordination", 6, "John", "provides", "encouragement", W),
    ("coordination", 8, "Audrey", "discovered", "bond", W),
    ("coordination", 8, "Audrey", "provides", "petting", A),
    ("coordination", 8, "Audrey", "uses", "hugs", I),
    ("coordination", 8, "Audrey", "provides", "hugs", A),
    ("coordination", 8, "Audrey", "provides", "calmness", A),
    ("coordination", 11, "Deborah", "created", "workshops", I),
    ("coordination", 11, "yoga", "part_of", "workshops", A),
    ("coordination", 11, "meditation", "part_of", "workshops", A),
    ("coordination", 11, "self-reflection", "part_of", "workshops", A),
    ("coordination", 13, "Melanie", "acquired", "running shoes", A),
    ("coordination", 13, "Melanie", "designed", "running shoes", W),
    ("coordination", 13, "running shoes", "provides", "destressing", A),
    # ── copular ─────────────────────────────────────────────────────────
    ("copular", 2, "Melanie", "created", "Painting", W),
    ("copular", 2, "Melanie", "created", "feelings", W),
    ("copular", 3, "Deborah", "developed", "mindfulness", W),
    ("copular", 4, "Jon", "works_at", "dance studio", A),
    ("copular", 5, "Andrew", "built", "apartment", W),
    ("copular", 6, "Tim", "created", "presentation", A),
    ("copular", 6, "Tim", "part_of", "class", A),
    ("copular", 6, "presentation", "part_of", "class", A),
    ("copular", 7, "Audrey", "located_in", "neighborhood", A),
    ("copular", 7, "Max", "located_in", "neighborhood", A),
    ("copular", 9, "Joanna", "created", "Tilly", W),
    ("copular", 9, "Joanna", "acquired", "Tilly", A),
    ("copular", 10, "Jon", "works_at", "dance studio", A),
    ("copular", 10, "Jon", "acquired", "dance studio", I),
    ("copular", 10, "Jon", "built", "dance studio", W),
    ("copular", 11, "John", "created", "mobile game", A),
    ("copular", 11, "John", "developed", "mobile game", A),
    ("copular", 11, "John", "wrote", "mobile game", I),
    ("copular", 11, "John", "designed", "mobile game", I),
    ("copular", 11, "mobile game", "provides", "puzzles", A),
    ("copular", 11, "mobile game", "provides", "exploration", A),
    ("copular", 12, "Joanna", "created", "story", W),
    ("copular", 12, "Joanna", "discovered", "story", W),
    ("copular", 12, "Joanna", "wrote", "story", W),
    ("copular", 12, "Joanna", "created", "powers", W),
    ("copular", 12, "Joanna", "discovered", "powers", W),
    ("copular", 13, "John", "acquired", "game", W),
    ("copular", 13, "John", "acquired", "next level", W),
    ("copular", 14, "Tim", "created", "fantasy", W),
    ("copular", 14, "Tim", "developed", "fantasy", W),
    ("copular", 14, "Tim", "created", "epic adventures", W),
    # ── nominal ─────────────────────────────────────────────────────────
    ("nominal", 1, "Deborah", "developed", "new perspective", A),
    ("nominal", 1, "Deborah", "acquired", "new perspective", I),
    ("nominal", 2, "Deborah", "acquired", "old house", W),
    ("nominal", 2, "Deborah", "built", "old house", W),
    ("nominal", 2, "mother", "acquired", "old house", I),
    ("nominal", 2, "mother", "built", "old house", W),
    ("nominal", 3, "Jolene", "discovered", "waterfall oasis", A),
    ("nominal", 3, "Jolene", "built", "waterfall oasis", W),
    ("nominal", 3, "partner", "discovered", "waterfall oasis", A),
    ("nominal", 3, "partner", "built", "waterfall oasis", W),
    ("nominal", 4, "Audrey", "created", "Chicken Pot Pie", W),
    ("nominal", 5, "Jolene", "located_in", "Rio de Janeiro", A),
    ("nominal", 6, "Jolene", "acquired", "console", A),
    ("nominal", 6, "Jolene", "built", "console", W),
    ("nominal", 7, "Andrew", "works_at", "pet shelter", I),
    ("nominal", 7, "girlfriend", "works_at", "pet shelter", I),
    ("nominal", 9, "Jolene", "uses", "video games", A),
    ("nominal", 12, "Jolene", "acquired", "room", I),
    ("nominal", 12, "Jolene", "built", "house", W),
    ("nominal", 12, "Jolene", "created", "memories", I),
    ("nominal", 12, "room", "located_in", "house", A),
    ("nominal", 13, "Deborah", "created", "pendant", W),
    ("nominal", 13, "Deborah", "designed", "pendant", W),
    # ── passive ─────────────────────────────────────────────────────────
    ("passive", 1, "John", "works_at", "assistant manager", I),
    ("passive", 2, "Joanna", "discovered", "nature", W),
    ("passive", 2, "Joanna", "discovered", "reset", W),
    ("passive", 2, "Joanna", "discovered", "worries", W),
    ("passive", 2, "Joanna", "discovered", "stress", W),
    ("passive", 2, "Joanna", "discovered", "beauty", W),
    ("passive", 4, "John", "developed", "gaming", W),
    ("passive", 4, "John", "developed", "coding", W),
    ("passive", 4, "John", "developed", "projects", W),
    ("passive", 5, "John", "built", "The Cliffs of Moher", W),
    ("passive", 6, "Maria", "works_at", "homeless shelter", W),
    ("passive", 8, "John", "works_at", "food drive events", I),
    ("passive", 9, "John", "works_at", "brainstorming projects", W),
    ("passive", 9, "John", "provides", "mentorship", I),
    ("passive", 9, "John", "provides", "job training", I),
    ("passive", 10, "Tim", "created", "fantasy TV series", W),
    ("passive", 10, "Tim", "created", "The Wheel of Time", W),
    ("passive", 10, "Tim", "wrote", "book series", W),
]


def load_gap(paths) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in paths:
        if not Path(p).exists():
            continue
        out.extend(json.loads(l) for l in
                   Path(p).read_text(encoding="utf-8").splitlines() if l.strip())
    return out


def reconcile(draft: Path = DRAFT, gaps=None) -> Dict[str, Any]:
    if gaps is None:
        gaps = [GAP]
    rows = [json.loads(l) for l in
            draft.read_text(encoding="utf-8").splitlines() if l.strip()]

    # (stratum, index) -> row
    indexed: Dict[Tuple[str, int], Dict[str, Any]] = {}
    counters: Counter = Counter()
    for r in rows:
        counters[r["stratum"]] += 1
        indexed[(r["stratum"], counters[r["stratum"]])] = r

    verdicts: Dict[Tuple[str, str, str, str], str] = {}
    for stratum, idx, s, p, o, v in ANNOTATION:
        verdicts[(stratum, s, p, o)] = v

    for g in load_gap(gaps):
        verdicts[(g["stratum"], g["s"], g["p"], g["o"])] = g["verdict"]

    annotated = 0
    judged: List[Dict[str, Any]] = []
    unannotated: List[str] = []
    per_stratum: Dict[str, Counter] = defaultdict(Counter)
    confidence_by_verdict: Dict[str, List[float]] = defaultdict(list)
    predicate_verdict: Dict[str, Counter] = defaultdict(Counter)

    for (stratum, idx), row in indexed.items():
        for t in row.get("asserted", []):
            key = (stratum, t["s"], t["p"], t["o"])
            v = verdicts.get(key)
            if v is None:
                unannotated.append(
                    f'[{stratum} {idx:2}] {t["s"]} -[{t["p"]}]-> {t["o"]}')
                continue
            annotated += 1
            judged.append({"s": t["s"], "p": t["p"], "o": t["o"],
                           "c": float(t.get("c") or 0.0), "verdict": v})
            per_stratum[stratum][v] += 1
            predicate_verdict[t["p"]][v] += 1
            confidence_by_verdict[v].append(float(t.get("c") or 0.0))

    total = sum(sum(c.values()) for c in per_stratum.values()) + len(unannotated)
    supported = sum(c[SUPPORTED] for c in per_stratum.values())
    implied = sum(c[IMPLIED] for c in per_stratum.values())
    wrong = sum(c[WRONG] for c in per_stratum.values())

    def _share(v: str) -> str:
        vals = confidence_by_verdict.get(v) or []
        if not vals:
            return "n/a"
        return f"{sum(vals) / len(vals):.3f} (n={len(vals)})"

    return {
        "asserted": total,
        "annotated": annotated,
        "judged": judged,
        "unannotated": unannotated,
        "supported": supported,
        "implied": implied,
        "wrong": wrong,
        # A right proposition on a slightly wrong predicate is still a fact the
        # store can use, so it counts as correct -- but it is a different defect
        # from a false fact and is never merged with it in the report.
        "precision_strict": supported / total if total else 0.0,
        "precision_incl_implied": (supported + implied) / total if total else 0.0,
        "per_stratum": {k: dict(v) for k, v in sorted(per_stratum.items())},
        "mean_confidence_by_verdict": {
            v: _share(v) for v in (SUPPORTED, IMPLIED, WRONG)},
        "predicate_verdict": {k: dict(v) for k, v in sorted(predicate_verdict.items())},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", choices=["stratified", "uniform"], default="stratified",
                    help="which annotated set to reconcile. Both run through "
                         "this same code; only the draft file and the extra "
                         "verdict file differ.")
    ap.add_argument("--out", type=Path, default=None,
                    help="write the judged gold jsonl here")
    args = ap.parse_args()

    if args.set == "uniform":
        draft = ROOT / "docs" / "eval_triples_gold_locomo_uniform_model.jsonl"
        gaps = [UNIFORM_GAP]
        title = "LoCoMo triple annotation (uniform sample)"
    else:
        draft = DRAFT
        gaps = [GAP]
        title = "LoCoMo triple annotation (production text, stratified)"

    r = reconcile(draft=draft, gaps=gaps)

    if args.out is not None:
        args.out.write_text("\n".join(
            json.dumps(t, ensure_ascii=False) for t in r["judged"]
        ) + "\n", encoding="utf-8")
        print(f"  wrote {len(r['judged'])} judged triples -> {args.out}")

    print(f"=== {title} ===")
    print(f"  asserted              {r['asserted']}")
    print(f"  annotated             {r['annotated']}")
    if r["unannotated"]:
        print(f"  UNANNOTATED           {len(r['unannotated'])}")
        for u in r["unannotated"]:
            print(f"      {u}")
    print()
    print(f"  supported             {r['supported']}")
    print(f"  implied               {r['implied']}")
    print(f"  wrong                 {r['wrong']}")
    print()
    print(f"  precision (strict)          {r['precision_strict']:.3f}   "
          f"supported only")
    print(f"  precision (incl implied)    {r['precision_incl_implied']:.3f}   "
          f"supported + implied")
    print()
    print("  per stratum:")
    print(f"    {'stratum':16} {'n':>4} {'sup':>5} {'imp':>5} {'wrong':>6} {'P':>7}")
    for stratum, c in r["per_stratum"].items():
        n = sum(c.values())
        p = (c.get(SUPPORTED, 0) + c.get(IMPLIED, 0)) / n if n else 0
        print(f"    {stratum:16} {n:4} {c.get(SUPPORTED, 0):5} "
              f"{c.get(IMPLIED, 0):5} {c.get(WRONG, 0):6} {p:7.3f}")
    print()
    print("  mean confidence by verdict:")
    for v in (SUPPORTED, IMPLIED, WRONG):
        print(f"    {v:12} {r['mean_confidence_by_verdict'][v]}")
    print()
    print("  predicate -> verdict (wrong count is the noise signal):")
    print(f"    {'predicate':16} {'sup':>5} {'imp':>5} {'wrong':>6} {'P':>7}")
    for p, c in sorted(r["predicate_verdict"].items(),
                       key=lambda kv: -kv[1].get(WRONG, 0)):
        n = sum(c.values())
        pr = (c.get(SUPPORTED, 0) + c.get(IMPLIED, 0)) / n if n else 0
        print(f"    {p:16} {c.get(SUPPORTED, 0):5} {c.get(IMPLIED, 0):5} "
              f"{c.get(WRONG, 0):6} {pr:7.3f}")
    print()
    print("  Recall is NOT measured here. This annotation labels what the model")
    print("  asserted; it says nothing about triples it should have found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
