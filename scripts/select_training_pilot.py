"""Pick the 50 sentences for the training-corpus pilot. Frozen before annotation.

The open question is no longer whether the model can be trained but how
dense the training signal for the 35 new predicates actually is in the
unused corpus, and how many examples carry several relations on one entity
pair. That needs sentences nobody has looked at yet.

Selection is deterministic and reads the sentence text only. No extractor
output, no confidence, no claim counts: choosing sentences by how promising
they look for the extractor would rebuild the training set around the
patterns the current model already produces, which is the failure mode the
recall sampling was built to avoid.

The population is the 2429 observation sentences not used by any gold file
under docs/. On top of that the 50 slots are stratified by structural
features computed from the text, because multi-relation training examples
are needed and they cannot be assumed to appear at the corpus base rate:

    multi_entity     several named entities, so several relations can attach
                     to the same pair
    multi_verb       several relation-bearing verbs, often coordinated
    possessive       possessive or "of" structures, which is how possession
                     and part-of relations are phrased
    plain            none of the above -- the control stratum, kept so the
                     pilot measures the corpus base rate rather than only
                     its densest corner

Every stratum is drawn with the same stride logic as before, so the selection
can be re-derived and re-checked, and the resulting ids are frozen to a
manifest before any annotation. Annotation follows the same gold-first rules
as the recall gold: `excluded`, `schema_gap` and `graphable: no` are all
recorded, because the pilot has to distinguish no training signal from wrong
family from non-graphable material from a genuinely missing label.

Usage:
    python scripts/select_training_pilot.py --count 50 --freeze
    python scripts/select_training_pilot.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
LOCOMO = ROOT / "_unused" / "locomo" / "data" / "locomo10.json"
MANIFEST = ROOT / "docs" / "eval_training_pilot_manifest.json"
SCAFFOLD = ROOT / "docs" / "eval_training_pilot.jsonl"

EXCLUDE = [
    "docs/eval_triples_gold_locomo_uniform.jsonl",
    "docs/eval_triples_gold_locomo_draft.jsonl",
    "docs/eval_recall_gold_pilot.jsonl",
    "docs/eval_recall_gold_batch2.jsonl",
    "docs/eval_recall_gold_expanded.jsonl",
]

REL_VERB = {
    "has", "have", "had", "is", "was", "were", "are", "owns", "acquired",
    "got", "joined", "attended", "went", "visited", "met", "made", "built",
    "founded", "created", "wrote", "designed", "started", "finished",
    "sent", "shared", "gifted", "earned", "drafted", "performed", "toured",
    "received", "watched", "listened", "read", "played", "practised",
    "practiced", "volunteered", "works", "worked", "supports", "led",
    "provides", "offered", "tried", "bought", "purchased", "took",
    "brought", "gave", "told", "asked", "recommended", "suggested",
    "restored", "modified", "signed", "moved", "live", "lives", "taught",
    "studied", "graduated", "married", "hired", "trained", "coached",
    "supported", "celebrated", "hosted", "organized", "joined",
}

STRATA = ("multi_entity", "multi_verb", "possessive", "plain")
DEFAULT_SHARE = {"multi_entity": 16, "multi_verb": 14,
                 "possessive": 12, "plain": 8}


def build_pool() -> List[Dict[str, str]]:
    data = json.loads(LOCOMO.read_text(encoding="utf-8"))
    used = set()
    for rel in EXCLUDE:
        p = ROOT / rel
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                used.add(json.loads(line)["id"])

    pool: List[Dict[str, str]] = []
    for s in data:
        for k, per in (s.get("observation") or {}).items():
            if not k.endswith("_observation"):
                continue
            for sp, items in per.items():
                for text, dia in items:
                    sid = "%s/%s/%s/%s" % (s["sample_id"], k, sp, dia)
                    if sid in used:
                        continue
                    pool.append({"id": sid, "text": text,
                                 "sample_id": s["sample_id"], "speaker": sp})
    pool.sort(key=lambda r: (r["sample_id"], r["id"]))
    return pool


def features(text: str) -> Dict[str, int]:
    toks = [t for t in re.split(r"[^\w']+", text.lower()) if t]
    caps = set(re.findall(r"\b[A-Z][a-z]+\b", text))
    poss = len(re.findall(r"\b[A-Z][a-z]+'s\b", text))
    of = sum(1 for t in toks if t == "of")
    verbs = sum(1 for t in toks if t in REL_VERB)
    return {"entities": len(caps), "possessive": poss + of,
            "rel_verbs": verbs}


def assign(f: Dict[str, int]) -> str:
    """One stratum per sentence, most specific first.

    Strata are exclusive so the shares mean what they say. A sentence with
    several entities and several relation verbs counts as multi_entity; the
    control stratum has to stay genuinely control.
    """
    if f["entities"] >= 3:
        return "multi_entity"
    if f["rel_verbs"] >= 2:
        return "multi_verb"
    if f["possessive"] >= 1:
        return "possessive"
    return "plain"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--scaffold", action="store_true")
    args = ap.parse_args()

    pool = build_pool()
    buckets: Dict[str, List[Dict[str, str]]] = {k: [] for k in STRATA}
    for r in pool:
        buckets[assign(features(r["text"]))].append(r)

    share = dict(DEFAULT_SHARE)
    scale = args.count / sum(DEFAULT_SHARE.values())
    quota = {k: max(1, round(v * scale)) for k, v in DEFAULT_SHARE.items()}

    picked: List[Dict[str, Any]] = []
    for k in STRATA:
        avail = buckets[k]
        n = min(quota[k], len(avail))
        # Even stride inside the stratum: no randomness, and removing one
        # sentence does not reshuffle the rest.
        step = max(1, len(avail) // n) if n else 1
        chosen = [avail[i * step] for i in range(n) if i * step < len(avail)]
        for c in chosen:
            f = features(c["text"])
            picked.append({**c, "stratum": k, "features": f})
    picked.sort(key=lambda r: (r["sample_id"], r["id"]))

    print("=== training-corpus pilot: selection ===\n")
    print(f"  pool (observation sentences, unused)   {len(pool)}")
    print(f"  requested                              {args.count}")
    print()
    print(f"  {'stratum':16} {'available':>9} {'selected':>8}")
    for k in STRATA:
        n = sum(1 for r in picked if r["stratum"] == k)
        print(f"  {k:16} {len(buckets[k]):9} {n:8}")
    print(f"  {'total':16} {len(pool):9} {len(picked):8}")
    print()
    agg = Counter()
    for r in picked:
        for k2, v in r["features"].items():
            agg[k2] += v
    print("  mean features of the selected sentences: "
          + ", ".join(f"{k} {agg[k] / max(1, len(picked)):.2f}" for k in agg))
    print("  the plain stratum is a control and is not representative of the")
    print("  rest of the pool by construction; the pilot reports each stratum")
    print("  separately so the training rate is not read off the biased half.")

    ids = [r["id"] for r in picked]
    if args.verify:
        if not MANIFEST.exists():
            print("\n  no manifest; run --freeze first")
            return 2
        man = json.loads(MANIFEST.read_text(encoding="utf-8"))
        print(f"\n  manifest {len(man['ids'])} ids, re-derived {len(ids)} ids")
        if man["ids"] != ids:
            print("  MISMATCH: the pool moved. The manifest is authoritative.")
            return 1
        print("  OK: the rule still reproduces the frozen sample")
        return 0

    if args.freeze:
        MANIFEST.write_text(json.dumps({
            "population": "observation sentences of the 10 LoCoMo conversations, "
                          "excluding every id present under docs/",
            "pool_size": len(pool),
            "strata": {k: quota[k] for k in STRATA},
            "rule": "text features only: entities>=3 -> multi_entity; "
                    "else >=2 relation verbs -> multi_verb; else >=1 possessive "
                    "or 'of' -> possessive; else plain. Even stride inside "
                    "each stratum.",
            "count": len(ids),
            "sha256_of_ids": hashlib.sha256(
                "\n".join(ids).encode("utf-8")).hexdigest(),
            "ids": ids,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nfroze {len(ids)} ids -> {MANIFEST.relative_to(ROOT)}")
        return 0

    if args.scaffold:
        rows = []
        man = json.loads(MANIFEST.read_text(encoding="utf-8")) \
            if MANIFEST.exists() else {}
        frozen = man.get("ids", ids)
        by_id = {r["id"]: r for r in picked}
        for sid in frozen:
            src = by_id.get(sid) or next(
                (r for r in pool if r["id"] == sid), None)
            rows.append({
                "id": sid, "text": src["text"] if src else "",
                "stratum": src["stratum"] if src else "",
                "graphable": None, "entities": None, "triples": None,
                "excluded": [], "schema_gap": [], "by": "unannotated",
            })
        SCAFFOLD.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                      for r in rows) + "\n", encoding="utf-8")
        print(f"\nwrote {SCAFFOLD.relative_to(ROOT)} ({len(rows)} rows)")

    print("\n  first 10 sentences, extractor output withheld:")
    for n, r in enumerate(picked[:10], 1):
        print(f"    [{n:2}] {r['id']}  [{r['stratum']}]")
        print(f"         {r['text'][:88]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())