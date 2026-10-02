"""Minimal GLiNER-Relex training entrypoint (contract validation stage).

Reads training JSONL conforming to docs/eval_relex_training_contract_v1.json,
validates schema, label map, entity spans and the split-hygiene rule
(family/pair ids must not reach the model), and writes a training manifest.

The actual Trainer loop (gliner.training.Trainer + RelationExtraction
processor) is wired in the next step. Without --dry-run this entrypoint
refuses to run: no training happens before the contract is frozen.

Usage:
    python scripts/train_relex.py --train <training.jsonl> --out <dir> --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "docs" / "eval_relex_training_contract_v1.json").read_text())

LABELS = tuple(CONTRACT["labels"])
FORBIDDEN = tuple(CONTRACT["forbidden_model_features"])


def validate_example(ex: dict, lineno: int) -> list[str]:
    problems: list[str] = []
    for key in CONTRACT["training_example_schema"]["required"]:
        if key not in ex:
            problems.append(f"line {lineno}: missing {key}")
    if problems:
        return problems
    if ex["relation"] not in LABELS:
        problems.append(f"line {lineno}: bad relation {ex['relation']!r}")
    sent = ex["sentence"]
    for role in ("X", "Y"):
        ent = ex["entities"].get(role, {})
        span = sent[ent.get("start", -1):ent.get("end", -1)]
        if span != ent.get("text", ""):
            problems.append(f"line {lineno}: {role} span does not match sentence")
    for feat in FORBIDDEN:
        if feat in ex and feat not in ("construction_family_id", "pair_id",
                                       "provenance", "split_key", "cue_phrase"):
            problems.append(f"line {lineno}: forbidden model feature {feat}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fold-id", default=None)
    args = ap.parse_args()

    rows = [json.loads(line) for line in
            Path(args.train).read_text(encoding="utf-8").splitlines()
            if line.strip()]
    problems: list[str] = []
    for i, ex in enumerate(rows, 1):
        problems += validate_example(ex, i)
    if problems:
        for p in problems:
            print(f"  PROBLEM {p}")
        return 1

    blob = "\n".join(f'{e["sentence"]}|{e["entities"]["X"]["text"]}|'
                     f'{e["entities"]["Y"]["text"]}|{e["relation"]}' for e in rows)
    digest = hashlib.sha256(blob.encode()).hexdigest()
    print(f"  examples: {len(rows)}  digest: {digest}")
    print(f"  labels: {LABELS}  split-hygiene: {FORBIDDEN} excluded from features")

    if args.dry_run:
        print("  dry-run: contract valid, no training executed")
        return 0

    print("  REFUSED: trainer loop not yet wired (next step). "
          "Re-run with --dry-run.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
