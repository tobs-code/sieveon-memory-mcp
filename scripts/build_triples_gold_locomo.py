"""Build a production-text triple gold set from LoCoMo observations.

Why LoCoMo and not the chat log: LoCoMo ships hand-written observations with
provenance ids, so the sentences are real third-party text and independent of
the model being evaluated. A gold built from my own writing inherits my blind
spots -- which is exactly how the comitative "with" case and the span-boundary
disagreement both got into the previous gold.

Why not the dialogues: a memory system stores asserted content, and
observation sentences are that form. Dialogue turns are questions,
acknowledgements and partial utterances, which would skew precision
estimates toward a case the system is not built for.

Selection is stratified by construction rather than at random, because the
previous 20-sentence set was 100% adversarial and therefore estimated worst
case rather than typical case:

  active-verb    a finite verb states the relation
  coordination   several verbs or objects in one sentence
  passive        the agent is introduced by a preposition
  nominal        the relation is a noun phrase, not a verb
  copular        "is a" / "was a" states no relation at all

Usage:
    python scripts/build_triples_gold_locomo.py --per-stratum 14
    python scripts/build_triples_gold_locomo.py --per-stratum 14 --dry-run
"""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
LOCOMO = ROOT / "_unused" / "locomo" / "data" / "locomo10.json"

FINITE_VERB = re.compile(
    r"\b(is|are|was|were|am|has|have|had|does|did|"
    r"wrote|written|writes|built|builds|founded|founds|"
    r"discovered|discovers|acquired|acquires|"
    r"uses|used|developed|develops|created|creates|"
    r"provides|provided|funded|funds|integrated|integrates|"
    r"leads|led|works|worked|met|meets|bought|buys|"
    r"visited|visits|joined|joins|attended|attends|"
    r"moved|moves|started|starts|finished|finishes|"
    r"painted|paints|planted|plants|adopted|adopts|"
    r"supports|supported|attends|attending)\b", re.I)

COPULAR = re.compile(r"\b(is|are|was|were)\s+(a|an|the)\b", re.I)
PASSIVE = re.compile(r"\b(was|were|is|are|been|being)\s+\w+(ed|en)\b", re.I)
NOMINAL = re.compile(
    # Possessive role noun as the subject: "Her manager is Rachel.",
    # "My sister lives in Berlin", "Tim's coach retired".
    r"\b(?:my|her|his|their|our)\s+"
    r"(?:new\s+|old\s+|former\s+)?\w*(?:friend|partner|manager|teacher|"
    r"student|mentor|neighbou?r|colleague|roommate|mother|father|"
    r"brother|sister|aunt|uncle|cousin|grand(?:ma|pa|mother|father)|"
    r"boss|coordinator|volunteer|doctor|dentist|therapist|nurse|"
    r"co-?worker|supervisor|intern|landlord|flatmate)\b|"
    # Copular with a role/collective noun on either side.
    r"\b(?:is|was|are|were)\s+(?:a|an|the|my|her|his|their|our)?\s*"
    r"\w*\s*(?:friend|partner|manager|teacher|student|mentor|"
    r"neighbou?r|colleague|roommate|mother|father|brother|sister|"
    r"member|supporter|owner|fan|resident|volunteer|coordinator|"
    r"doctor|dentist|therapist|nurse|co-?worker|supervisor|intern|"
    r"album|book|novel|band|project|job|role|position|routine|"
    r"diet|garden|club|group|team|forum|conference|class|course|"
    r"collection|series|game|app|software|device)\b", re.I)
COORDINATION = re.compile(r",\s+\w+\s+(and|but)\s|,\s+and\s+\w+|\band\b.+", re.I)


def classify(sentence: str) -> List[str]:
    """Which construction strata this sentence exercises. May be empty."""
    tags = []
    if FINITE_VERB.search(sentence):
        tags.append("active-verb")
    if PASSIVE.search(sentence):
        tags.append("passive")
    if NOMINAL.search(sentence):
        tags.append("nominal")
    if COPULAR.search(sentence):
        tags.append("copular")
    if len(COORDINATION.findall(sentence)) >= 1 and "," in sentence:
        tags.append("coordination")
    return tags


def iter_sentences(path: Path = LOCOMO) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for entry in data:
        sid = entry.get("sample_id", "?")
        obs = entry.get("observation") or {}
        for key, speakers in obs.items():
            if not isinstance(speakers, dict):
                continue
            for speaker, items in speakers.items():
                if not isinstance(items, list):
                    continue
                for it in items:
                    if isinstance(it, list) and it and isinstance(it[0], str):
                        sent = it[0].strip()
                        prov = it[1] if len(it) > 1 else ""
                        if 6 <= len(sent.split()) <= 42:
                            out.append({
                                "text": sent,
                                "speaker": speaker,
                                "session": key,
                                "provenance": f"{sid}/{key}/{speaker}/{prov}",
                            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--per-stratum", type=int, default=14)
    ap.add_argument("--random", type=int, default=0,
                    help="also draw N sentences uniformly at random, for a "
                         "production-rate estimate")
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="")
    ap.add_argument("--random-out", default="")
    args = ap.parse_args()

    pool = iter_sentences()
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for s in pool:
        for tag in classify(s["text"]):
            buckets.setdefault(tag, []).append(s)

    print(f"candidate sentences: {len(pool)}")
    for tag in sorted(buckets):
        print(f"  {tag:14} {len(buckets[tag])}")

    rng = random.Random(args.seed)
    # Stratified draw, no sentence used twice, so the strata stay comparable
    # and the total is predictable.
    chosen: List[Dict[str, Any]] = []
    seen = set()
    for tag in sorted(buckets):
        picks = sorted(buckets[tag], key=lambda s: s["provenance"])
        rng.shuffle(picks)
        taken = 0
        for s in picks:
            if s["provenance"] in seen:
                continue
            if taken >= args.per_stratum:
                break
            seen.add(s["provenance"])
            chosen.append({**s, "stratum": tag})
            taken += 1
        print(f"  drew {taken:2} from {tag}")

    print(f"\ntotal selected: {len(chosen)}")

    # A stratified set deliberately over-weights hard constructions, so its
    # aggregate precision is a worst-case-weighted figure, not a production
    # rate. The uniform draw is what estimates production. Both are written
    # out because they answer different questions and must not be averaged.
    random_set: List[Dict[str, Any]] = []
    if args.random:
        pool_sorted = sorted(pool, key=lambda s: s["provenance"])
        rng2 = random.Random(args.seed + 1)
        picks = list(pool_sorted)
        rng2.shuffle(picks)
        for s in picks[: args.random]:
            if s["provenance"] in seen:
                continue
            random_set.append({**s, "stratum": "uniform"})
        print(f"uniform draw: {len(random_set)} "
              f"(excludes sentences already in the stratified set)")

    if args.dry_run:
        for s in chosen[:12]:
            print(f"  [{s['stratum']:12}] {s['text'][:88]}")
        for s in random_set[:5]:
            print(f"  [uniform     ] {s['text'][:88]}")
        return 0

    def _write(path: Path, rows: List[Dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as fh:
            for s in rows:
                fh.write(json.dumps({
                    "id": s["provenance"],
                    "text": s["text"],
                    "stratum": s["stratum"],
                    "speaker": s["speaker"],
                    "session": s["session"],
                    "triples": None,
                    "note": "UNLABELLED. Fill triples by hand, or no model will.",
                }, ensure_ascii=False) + "\n")
        print(f"wrote {path}  ({len(rows)} rows, triples=null)")

    out_path = Path(args.out) if args.out else (
        ROOT / "docs" / "eval_triples_gold_locomo_draft.jsonl")
    _write(out_path, chosen)

    if random_set:
        rp = Path(args.random_out) if args.random_out else (
            ROOT / "docs" / "eval_triples_gold_locomo_uniform.jsonl")
        _write(rp, random_set)

    print("\ntriples are null: annotate them yourself, or no model will.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())