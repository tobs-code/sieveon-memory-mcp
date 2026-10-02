#!/usr/bin/env python
"""Retrieval eval against docs/eval_retrieval_gold.jsonl.

This measures what the memory actually retrieves, per query and per strategy,
and separates two failure modes that the aggregate score hides:

  * a wrong answer -- the expected fact is absent from the response;
  * no answer at all -- the no-answer probes return nothing, which is
    correct behaviour and must not be counted as a miss.

Per-strategy numbers matter because the router picks one of them
adaptively. A strategy that looks fine averaged over all queries can be
useless for factual lookups while carrying temporal ones, which is why the
adapter tracks effectiveness per (query_type, strategy) rather than
globally.

Gold indices are 1-based positions in docs/eval_extraction_gold.jsonl, the
sentence each query's answer must come from. They are resolved to the
sentence's entities here and matched by name, because matching the raw index
against result text can never succeed. Resolve them once at load time and
fail loudly if an index does not resolve, rather than reporting a hit rate
of zero against data that is actually present.

Usage:
    python scripts/eval_retrieval.py
    python scripts/eval_retrieval.py --strategies semantic_hybrid,kg_query
    python scripts/eval_retrieval.py --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

GOLD_PATH = Path(__file__).resolve().parents[1] / "docs" / "eval_retrieval_gold.jsonl"
EXTRACTION_GOLD_PATH = (
    Path(__file__).resolve().parents[1] / "docs" / "eval_extraction_gold.jsonl"
)

from src.extraction.classifier import QueryClassifier  # noqa: E402,F401


def mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _load_sentences(path: Path = EXTRACTION_GOLD_PATH) -> List[Dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _answer_terms(sentence: Dict[str, Any]) -> List[str]:
    """Terms a correct response must contain for one gold sentence.

    Entity names, not the whole sentence: a retriever that returns the right
    entity via the KG returns a name, not prose. Requiring sentence text
    would fail a correct KG-only answer.
    """
    names = [e.get("name") for e in sentence.get("entities") or [] if e.get("name")]
    return names or [sentence.get("text", "")]


def load_gold(
    path: Path = GOLD_PATH,
    sentences_path: Path = EXTRACTION_GOLD_PATH,
) -> List[Dict[str, Any]]:
    """Load the gold set, resolving indices to concrete answer terms."""
    sentences = _load_sentences(sentences_path)
    cases: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            indices = row.get("gold") or []

            terms: List[str] = []
            for idx in indices:
                # Gold indices are 0-based positions that happen to start at
                # 1, so the index is used as-is: gold[1] is sentences[1].
                # Verified against the data -- every referenced index lands
                # on the sentence its query asks about under this mapping
                # ("Who discovered radium?" -> Marie Curie, not the
                # SurrealDB release note at sentences[0]). The obvious
                # reading (1-based, sentences[idx-1]) lands on the wrong
                # sentence for every query.
                if not 0 <= idx < len(sentences):
                    raise ValueError(
                        f"{path.name}:{lineno}: gold index {idx} is outside the "
                        f"{len(sentences)} sentences in {sentences_path.name}"
                    )
                terms.extend(_answer_terms(sentences[idx]))

            cases.append(
                {
                    "query": row["query"],
                    # An empty gold list marks a no-answer probe: nothing in
                    # the store answers this, and a good system returns
                    # nothing rather than inventing a plausible answer.
                    "gold": indices,
                    "terms": terms,
                    "paraphrase": bool(row.get("paraphrase")),
                }
            )
    return cases


def _item_text(item: Dict[str, Any]) -> str:
    parts = [
        str(item.get("content") or ""),
        str(item.get("name") or ""),
        str(item.get("predicate") or ""),
        str(item.get("in_name") or ""),
        str(item.get("out_name") or ""),
        str(item.get("subject") or ""),
        str(item.get("object") or ""),
    ]
    for edge in ("in", "out"):
        value = item.get(edge)
        if isinstance(value, dict):
            parts.append(str(value.get("name") or ""))
            parts.append(str(value.get("type") or ""))
        elif isinstance(value, str):
            parts.append(value)
    return " ".join(p for p in parts if p)


def _flatten(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = response.get("results") if isinstance(response.get("results"), dict) else response
    items: List[Dict[str, Any]] = []
    for group in ("events", "entities", "facts"):
        for item in (results.get(group) or []):
            if isinstance(item, dict):
                items.append(item)
    return items


async def run_case(query: str, strategy: Optional[str]) -> Dict[str, Any]:
    """Run one query, optionally with a pinned strategy."""
    from src.mcp.common_logic import _execute_query

    if strategy is None:
        return await _execute_query(query)
    from src.planner.executor import PlanExecutor, RetrievalStrategy

    return await PlanExecutor().execute_plan(
        strategy=strategy, query=query, budget_level="high"
    )


async def evaluate(cases: List[Dict[str, Any]], strategy: Optional[str]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []

    for case in cases:
        response = await run_case(case["query"], strategy)
        items = _flatten(response)
        blob = " ".join(_item_text(i) for i in items).lower()

        if not case["gold"]:
            # No-answer probe. Returning nothing is correct. Returning
            # something is a false positive, which is the worse failure:
            # it looks like an answer.
            answered = len(items) > 0
            rows.append(
                {
                    "query": case["query"],
                    "kind": "no_answer",
                    "paraphrase": case["paraphrase"],
                    "false_positive": answered,
                    "items": len(items),
                    "rank": None,
                    "classified_as": response.get("classified_as"),
                    "strategy": response.get("strategy"),
                }
            )
            continue

        # The answer must mention every entity of every gold sentence.
        gold_terms = case["terms"]
        # A response carrying any one of the entities is partial progress;
        # a complete answer needs all of them. Tracking both separates "found
        # the right entity, wrong relation" from "found nothing relevant".
        hits = [t for t in gold_terms if t.lower() in blob]
        hit = len(hits) == len(gold_terms)
        rank = None
        for idx, item in enumerate(items):
            text = _item_text(item).lower()
            if all(t.lower() in text for t in gold_terms):
                rank = idx
                break
        rows.append(
            {
                "query": case["query"],
                "kind": "answerable",
                "paraphrase": case["paraphrase"],
                "hit": hit,
                "terms_found": hits,
                "terms_missing": [t for t in gold_terms if t not in hits],
                "rank": rank,
                "items": len(items),
                "classified_as": response.get("classified_as"),
                "strategy": response.get("strategy"),
                "relevance_score": (response.get("ranking") or {}).get(
                    "relevance_score"
                ),
            }
        )

    answerable = [r for r in rows if r["kind"] == "answerable"]
    no_answer = [r for r in rows if r["kind"] == "no_answer"]

    def _rate(subset, field):
        return mean([1.0 if r[field] else 0.0 for r in subset]) if subset else 0.0

    return {
        "strategy": strategy or "router",
        "answerable": len(answerable),
        "no_answer": len(no_answer),
        "hit_rate": _rate(answerable, "hit"),
        "literal_hit_rate": _rate(
            [r for r in answerable if not r["paraphrase"]], "hit"
        ),
        "paraphrase_hit_rate": _rate(
            [r for r in answerable if r["paraphrase"]], "hit"
        ),
        "false_positive_rate": _rate(no_answer, "false_positive"),
        "empty_rate": mean([1.0 if r["items"] == 0 else 0.0 for r in rows]),
        "mean_items": mean([float(r["items"]) for r in rows]) if rows else 0.0,
        "rows": rows,
    }


def print_report(report: Dict[str, Any]) -> None:
    strat = report["strategy"]
    print(f"\n=== strategy: {strat} ===")
    print(
        f"  hit rate           {report['hit_rate']:.3f}  "
        f"({report['answerable']} answerable)"
    )
    print(f"    literal          {report['literal_hit_rate']:.3f}")
    print(f"    paraphrase       {report['paraphrase_hit_rate']:.3f}")
    print(
        f"  false positives    {report['false_positive_rate']:.3f}  "
        f"({report['no_answer']} no-answer probes)"
    )
    print(f"  empty responses    {report['empty_rate']:.3f}")
    print(f"  mean items/answer  {report['mean_items']:.1f}")

    misses = [r for r in report["rows"] if r["kind"] == "answerable" and not r["hit"]]
    fps = [r for r in report["rows"] if r["kind"] == "no_answer" and r["false_positive"]]
    if misses:
        print("\n  misses:")
        for r in misses:
            tag = "paraphrase" if r["paraphrase"] else "literal"
            print(f"    [{tag}] {r['query']}")
            if r["terms_found"]:
                print(f"        partial: found {r['terms_found']}")
            print(
                f"        missing {r['terms_missing']}  "
                f"as={r['classified_as']} items={r['items']} "
                f"rel={r['relevance_score']}"
            )
    if fps:
        print("\n  false positives (should have returned nothing):")
        for r in fps:
            print(f"    {r['query']}  -> {r['items']} items")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--strategies",
        default="router",
        help="comma separated: 'router' for the adaptive path, or strategy "
        "names such as semantic_hybrid,kg_query,event_log_search",
    )
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    cases = load_gold()
    if args.limit:
        cases = cases[: args.limit]

    strategies: List[Optional[str]] = (
        [None] if args.strategies == "router" else args.strategies.split(",")
    )

    reports = []
    for strategy in strategies:
        report = await evaluate(cases, strategy)
        reports.append(report)
        print_report(report)

    if len(reports) > 1:
        print("\n=== comparison ===")
        print(f"{'strategy':22} {'hit':>6} {'lit':>6} {'para':>6} {'FP':>6} {'items':>7}")
        for r in reports:
            print(
                f"{r['strategy']:22} {r['hit_rate']:6.3f} "
                f"{r['literal_hit_rate']:6.3f} {r['paraphrase_hit_rate']:6.3f} "
                f"{r['false_positive_rate']:6.3f} {r['mean_items']:7.1f}"
            )

    if args.out:
        Path(args.out).write_text(
            json.dumps({"reports": reports}, indent=2), encoding="utf-8"
        )
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))