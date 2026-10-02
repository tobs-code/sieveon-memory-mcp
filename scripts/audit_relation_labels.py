"""M1 audit: is every gold predicate reachable in the inference label set?

A joint NER+RE model classifies entity pairs into a label list supplied at
inference. Any predicate absent from that list cannot be emitted, no matter
what the confidence is -- so measuring recall against a gold set containing
such predicates scores the configuration, not the model.

This script answers that in one pass and is the cheapest possible check:
pure set arithmetic over the label list and the gold set, no model needed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.extraction.entity_utils import (  # noqa: E402
    _SIEVEON_RELATION_LABELS,
    _normalize_relation_label,
)

GOLD = Path(__file__).resolve().parents[1] / "docs" / "eval_triples_gold.jsonl"


def slug(label: str) -> str:
    return _normalize_relation_label(label)


def main() -> int:
    labels = {slug(l) for l in _SIEVEON_RELATION_LABELS}

    gold: dict = {}
    with GOLD.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            for t in row.get("triples", []):
                gold[slug(t[1])] = gold.get(slug(t[1]), 0) + 1

    missing = {p: n for p, n in gold.items() if p not in labels}
    extra = sorted(labels - set(gold))
    unreachable = sum(missing.values())
    total = sum(gold.values())

    print(f"inference labels ({len(labels)}): {sorted(labels)}")
    print(f"gold predicates    ({len(gold)}): {sorted(gold)}")
    print()
    if missing:
        print(f"UNREACHABLE: {unreachable} of {total} gold triples use a "
              f"predicate the model is never offered")
        for p, n in sorted(missing.items(), key=lambda kv: -kv[1]):
            print(f"    {p:14} gold={n}")
        print()
        print("  These are unreachable at ANY confidence threshold. Measuring")
        print("  recall against them scores the label list, not the model.")
        print()
        print(f"  ceiling on recall with this label set: "
              f"{(total - unreachable) / total:.3f}")
    else:
        print("every gold predicate is reachable in the label set")

    if extra:
        print()
        print(f"labels never used by gold ({len(extra)}): {extra}")
        print("  These may be noise sources. Each should justify itself:")
        print("  a label that gold never expects is a candidate for removal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())