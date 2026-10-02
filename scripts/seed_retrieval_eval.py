"""Reset the retrieval-eval database and seed it from the extraction gold set.

The database and the gold set had drifted apart: the store held sourdough
bread and Wikipedia dumps while docs/eval_retrieval_gold.jsonl asked about
SpaceX and radium, so the hit rate measured a data mismatch rather than
retrieval quality. This rebuilds the store from the sentences the gold set
actually references.

The gold indices are 1-based positions in docs/eval_extraction_gold.jsonl.
Verified: with that interpretation all 29 referenced indices resolve to the
sentence the matching query asks about ("Who discovered radium?" -> Marie
Curie, not the SurrealDB release note that sits at 0-based position 1).

Storage goes through _store_content, the same path memory_store uses, so the
events and KG facts are built by the real extraction pipeline rather than
inserted directly. That matters: it is the extraction quality we want to
measure.

Usage:
    python scripts/seed_retrieval_eval.py --reset
    python scripts/seed_retrieval_eval.py --reset --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
EXTRACTION_GOLD = ROOT / "docs" / "eval_extraction_gold.jsonl"
RETRIEVAL_GOLD = ROOT / "docs" / "eval_retrieval_gold.jsonl"

# Sentences kept out of the retrieval store on purpose.
#
# The dog barked is a gate test fixture, "test test test" is an extractor
# fixture, and the ticket question is not a statement. Seeding them would add
# content that no query asks about and measure nothing. The sourdough and
# geothermal sentences stay: they are plausible memory content and give the
# retriever something to rank against, which is what makes a false positive
# detectable.
SKIP_TEXTS = {
    "test test test test test test test test",
    "The dog barks loudly in the garden.",
    "How much is the ticket to Munich?",
}


def load_sentences(path: Path = EXTRACTION_GOLD) -> List[Dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_gold(path: Path = RETRIEVAL_GOLD) -> List[Dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def referenced_indices(gold: List[Dict[str, Any]]) -> List[int]:
    return sorted({i for row in gold for i in (row.get("gold") or [])})


async def reset() -> None:
    """Drop the four content tables, leaving schema and migrations alone."""
    from src.mcp.core import _query_surreal

    print("resetting database...")
    for table in ("fact", "entity", "event", "gate_log", "router_costs"):
        await _query_surreal(f"DELETE {table};")
        print(f"  cleared {table}")


async def seed(sentences: List[Dict[str, Any]], dry_run: bool = False) -> Dict[str, Any]:
    from src.mcp.common_logic import _store_content

    stored, skipped = [], []
    for row in sentences:
        text = row["text"]
        if text in SKIP_TEXTS:
            skipped.append(text)
            continue
        if dry_run:
            stored.append({"text": text, "event_id": None})
            continue
        result = await _store_content(text, source="user_input")
        if result.get("status") == "stored":
            stored.append(
                {
                    "text": text,
                    "event_id": result.get("event_id"),
                    "gate": (result.get("gate") or {}).get("decision"),
                    "kg": (result.get("gate") or {}).get("kg"),
                }
            )
        else:
            skipped.append(f"{text} -> {result.get('message')}")

    return {"stored": stored, "skipped": skipped}


async def report() -> Dict[str, Any]:
    from src.mcp.core import _query_surreal

    counts = {}
    for table in ("event", "entity", "fact"):
        rows = await _query_surreal(f"SELECT count() AS c FROM {table} GROUP ALL;")
        for item in rows if isinstance(rows, list) else []:
            result = item.get("result") if isinstance(item, dict) else None
            if isinstance(result, list) and result:
                counts[table] = result[0].get("c", 0)
    return counts


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--reset", action="store_true",
        help="clear the content tables first (they currently hold unrelated data)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sentences = load_sentences()
    gold = load_gold()
    referenced = referenced_indices(gold)

    print(f"extraction gold sentences: {len(sentences)}")
    print(f"retrieval queries:         {len(gold)}")
    print(f"gold indices referenced:   {len(referenced)}")

    # Guard the off-by-one before touching the database: if the mapping breaks,
    # the eval would silently measure the wrong sentences.
    if referenced and max(referenced) >= len(sentences):
        print(
            f"ERROR: gold index {max(referenced)} exceeds the "
            f"{len(sentences)} available sentences",
            file=sys.stderr,
        )
        return 2

    if args.reset and not args.dry_run:
        await reset()

    result = await seed(sentences, dry_run=args.dry_run)

    print(f"\nstored: {len(result['stored'])}  skipped: {len(result['skipped'])}")
    for row in result["stored"]:
        if args.dry_run:
            print(f"  {row['text'][:78]}")
        else:
            kg = row.get("kg") or {}
            print(
                f"  [{row.get('gate', '?'):6}] facts={kg.get('facts_created', 0):3} "
                f"ents={kg.get('entities_created', 0):3}  {row['text'][:56]}"
            )
    for row in result["skipped"]:
        print(f"  SKIP {row[:78]}")

    if not args.dry_run:
        print("\n=== database contents ===")
        for table, count in (await report()).items():
            print(f"  {table:8} {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))