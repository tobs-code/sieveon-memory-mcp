"""Multi-relation selector: does it hold the baseline instead of losing it?

The single-winner reranker scored 21/44 unrestricted and 23/44 gated, against
a 26/44 baseline. Both numbers were negative, and the reason turned out not
to be selection quality. The production contract is multi-relation per entity
pair: `Gina founded store` and `Gina works_at store` are two facts, both
emitted, both scored separately by the gold. A one-winner reranker can
express at most one of them, so it dropped correct facts by construction.
That is the cardinality assumption, not a gate defect.

This scorer judges each relation independently. No relation's fate depends
on where another relation on the same pair ranks, which is the invariant that
removes the single-winner failure mode.

The bar is not "beats the baseline". It is "does not lose anything". A
scorer that keeps what is already correct and adds a little is progress; one
that trades a correct relation for another correct relation is not.

Guard: shipped relations are protected. The gate may not drop a relation the
pipeline already produced on the strength of a rival's rank, because that is
the failure being repaired.

Shadow only: same frozen model, same frozen gold, no database write.

Usage:
    python scripts/eval_multi_relation_selector.py
    python scripts/eval_multi_relation_selector.py --out docs/eval_multi_selector.json
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="")
    ap.add_argument("--rel-threshold", type=float, default=0.2)
    args = ap.parse_args()

    from scripts.selector_decide import keep_relations, probe_candidates
    from scripts.eval_selector_full_set import _frozen_baseline

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

    hb = _frozen_baseline()
    n_gold = hb["gold"]
    base_found, base_clean = hb["found"], hb["clean"]

    kept_keys: set = set()
    kept_clean: set = set()
    kept_all: List[Tuple[str, str, str, str]] = []
    dropped_shipped: List[Dict[str, Any]] = []
    multiplicity: Counter = Counter()
    per_family: Dict[str, Counter] = defaultdict(Counter)

    for n, (sid, text) in enumerate(texts.items(), 1):
        gold = [t for t in (gold_rows.get(sid, {}).get("triples") or [])]
        ship = shipped.get(sid, [])
        if not gold and not ship:
            continue
        try:
            cands = probe_candidates(text, rel_threshold=args.rel_threshold)
        except Exception:  # noqa: BLE001
            continue
        pairs: Dict[Tuple[str, str], List[str]] = defaultdict(list)
        for k, v in cands.items():
            h, t = k.split("|", 1)
            for p in v["candidates"]:
                pairs[(h, t)].append(p)

        for (h, t), rels in pairs.items():
            base = [c for c in ship if norm(c["s"]) == h and norm(c["o"]) == t]
            if not base:
                continue  # no shipped claim on this pair: nothing to protect
            surface = cands[f"{h}|{t}"]["surface"]
            d = keep_relations(text, rels, surface[0], surface[1],
                               [c["p"] for c in base], gate="abstraction")
            multiplicity[d["multiplicity"]] += 1
            for p in d["per_relation"]:
                per_family[p["predicate"]]["kept" if p["keep"] else "dropped"] += 1
                if p["shipped"] and not p["keep"]:
                    dropped_shipped.append({"id": sid, "s": surface[0],
                                            "o": surface[1], "p": p["predicate"]})
            for p in d["kept"]:
                key = (sid, h, p, t)
                kept_all.append(key)
                for g in gold:
                    if (norm(g[0]), norm(g[1]), norm(g[2])) == (h, p, t):
                        kept_keys.add(key)
                        if len(g) <= 3:
                            kept_clean.add(key)
                        break
        if n % 30 == 0:
            print(f"  probed {n}/{len(texts)}")

    # Baseline facts are counted as gold facts; the selector side must use
    # the same unit or the two numbers are not comparable.
    sel_found = len(kept_keys)
    sel_clean = len(kept_clean)

    print(f"\n=== multi-relation selector on the full set ===\n")
    print(f"  {'measure':30} {'baseline':>9} {'selector':>9}")
    print(f"  {'scorable recall':30} "
          f"{base_found / n_gold:9.3f} {sel_found / n_gold:9.3f}")
    print(f"  {'  absolute':30} {base_found:>9} {sel_found:>9}")
    print(f"  {'clean recall':30} "
          f"{base_clean / n_gold:9.3f} {sel_clean / n_gold:9.3f}")
    print(f"  {'  absolute':30} {base_clean:>9} {sel_clean:>9}")
    print()
    print(f"  shipped relations dropped        {len(dropped_shipped)}")
    print(f"  relations kept per entity pair   "
          f"{dict(sorted(multiplicity.items()))}")
    kept_pairs = sum(v for k, v in multiplicity.items() if k >= 1)
    multi = sum(v for k, v in multiplicity.items() if k >= 2)
    if kept_pairs:
        print(f"    pairs with 2+ relations kept  {multi}/{kept_pairs} = "
              f"{multi / kept_pairs:.0%}")
    print()
    print("  The bar is losing nothing. Lower recall than the baseline means")
    print("  the scorer still discarded facts it was supposed to protect.")

    if dropped_shipped:
        print("\n  shipped relations dropped (must be empty):")
        for d in dropped_shipped[:12]:
            print(f"    {d['s']} -{d['p']}-> {d['o']}")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "scorable_gold": n_gold,
            "baseline": {"recall": round(base_found / n_gold, 4),
                         "found": base_found, "clean": base_clean},
            "selector": {"recall": round(sel_found / n_gold, 4),
                         "found": sel_found, "clean": sel_clean},
            "shipped_dropped": len(dropped_shipped),
            "kept_per_pair": dict(multiplicity),
            "per_predicate": {k: dict(v) for k, v in per_family.items()},
            "dropped_shipped_detail": dropped_shipped,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())