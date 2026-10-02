"""Fill the expanded gold with the extractor assertions, for scoring.

The recall harness joins gold against a claims file. That file was the
uniform model output, which covers only the 57 uniform sentences. Every
expanded gold fact therefore looked missed -- not because the extractor
missed it, but because nobody had run the extractor on that sentence. The
harness cannot tell those apart: a sentence with no claims looks exactly
like a model that asserted nothing.

This runs the same extraction path the uniform file was built with
(extract_triples_with_relex plus the same label filter), writes claims to
their own file, and leaves every annotation field untouched. It has to run
before any expanded batch is scored, and re-running it is how the claim
side is refreshed when the extractor changes.

Usage:
    python scripts/annotate_recall_expanded.py --dry-run
    python scripts/annotate_recall_expanded.py
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
GOLD = ROOT / "docs" / "eval_recall_gold_expanded.jsonl"
CLAIMS = ROOT / "docs" / "eval_recall_claims_expanded.jsonl"


async def build(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from src.extraction.entity_utils import extract_triples_with_relex
    from src.extraction.entity_utils import _SIEVEON_RELATION_LABELS
    from scripts.audit_relation_labels import slug

    labels = {slug(l) for l in _SIEVEON_RELATION_LABELS}
    out: List[Dict[str, Any]] = []
    for i, row in enumerate(rows, 1):
        triples = extract_triples_with_relex(row["text"])
        asserted = [
            {
                "s": t.get("subject"),
                "p": t.get("predicate"),
                "o": t.get("object"),
                "c": round(float(t.get("confidence") or 0.0), 4),
                "label_ok": t.get("predicate") in labels,
            }
            for t in triples
        ]
        out.append({"id": row["id"], "text": row["text"],
                    "stratum": "expanded", "asserted": asserted})
        if i % 25 == 0:
            print(f"  {i}/{len(rows)}")
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = [json.loads(l) for l in
            GOLD.read_text(encoding="utf-8").splitlines() if l.strip()]
    claims = await build(rows)

    total = sum(len(c["asserted"]) for c in claims)
    empty = sum(1 for c in claims if not c["asserted"])
    print(f"  {len(claims)} sentences, {total} asserted triples, "
          f"{empty} with none")
    for c in claims[:8]:
        print(f"    {len(c['asserted'])} claims  {c['text'][:54]}")

    if args.dry_run:
        print("\n  dry run, nothing written")
        return 0

    CLAIMS.write_text("\n".join(json.dumps(c, ensure_ascii=False)
                                for c in claims) + "\n", encoding="utf-8")
    print(f"\nwrote {CLAIMS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
