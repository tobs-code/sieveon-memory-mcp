"""Do three syntactic gates account for the false triples?

Claimed share: copular sentences produce no relation, a "to"-marked phrase is
a recipient rather than a location, and a "for"-marked phrase is a purpose
adjunct rather than an object. Those three were said to explain 31 of 66
false triples. That number was not checked. This checks it.

Gate 1 is measurable and unambiguous: a copular frame ("X is a ...") states
no relation. Gate 2 and gate 3 need a subject, so the module only tries them
when it can identify the surface verb, and says so rather than guessing.

Usage:
    python scripts/eval_structural_gates.py
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "docs" / "eval_triples_gold_locomo_draft_model.jsonl"

# Copular frame: the surface verb is a form of "be" and it is immediately
# followed by an article or a determiner, so the clause states what X is,
# not what X did.
COPULAR = re.compile(r"\b(is|are|was|were)\s+(a|an|the)\b", re.I)

# A "to"-marked PP follows a providing verb. The phrase is the recipient.
PROVIDE_TO = re.compile(
    r"\b(provides?|provided|supplies?|supplied|offers?|offered|"
    r"gives?|gave|sends?|sent|delivers?|delivered)\b[^.]{0,40}\bto\b",
    re.I)
# The object of such a verb is a recipient, not a place, so located_in and
# works_at cannot hold for it.
LOCATIONISH = {"located_in", "works_at"}

# Predicates that assert an event happened. A copular frame states what
# something IS, so it cannot license any of these -- "John is a member of a
# hiking club" licenses part_of and located_in, never founded.
EVENT_PREDICATES = {
    "built", "founded", "created", "developed", "acquired",
    "discovered", "designed", "funded", "integrated", "joined",
}

# A "for"-marked PP following the transitive verb. The phrase is a purpose
# or beneficiary adjunct.
PURPOSE_FOR = re.compile(
    r"\b(uses?|used|building|built|creates?|created|develops?|developed|"
    r"designs?|designed|writes?|wrote|started|started|joined)\b"
    r"[^.]{0,40}\bfor\b", re.I)


def subject_verb_spans(sentence: str) -> Tuple[Optional[str], Optional[str]]:
    """Crude subject and main-verb spans, or (None, None).

    Deliberately conservative: it only finds patterns it is sure about, and
    returns None otherwise so the caller can abstain rather than guess. A
    wrong verb span produces a wrong gate decision, which is worse than no
    gate.
    """
    # "X verb ..." / "X verb-ed ..."
    m = re.search(
        r"\b([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*)*)\s+"
        r"(is|are|was|were|has|have|had|wrote|built|founded|discovered|"
        r"acquired|uses|used|developed|created|provides|provided|funded|"
        r"integrated|leads|works|works_at|joined|joined|attended|painted|"
        r"planted|adopted|supports|bought|visited|moved|started|finished|"
        r"gave|got|sees|met|reads|says|explores|enjoys|wants|needs|keeps)\b",
        sentence)
    if m:
        return m.group(1).strip(), m.group(2).lower()

    # Lower-case subject: "his mother acquired ...", "the club provides ..."
    m = re.search(
        r"\b(?:his|her|their|the|a|an)\s+"
        r"([\w-]+(?:\s+[\w-]+)?)\s+"
        r"(is|are|was|were|has|have|had|wrote|built|founded|discovered|"
        r"acquired|uses|used|developed|created|provides|provided|funded|"
        r"integrated|leads|works|joined|attended|painted|planted|adopted|"
        r"supports|bought|visited|moved|started|finished|gave|got|sees|"
        r"met|reads|says|explores|enjoys|wants|needs|keeps)\b",
        sentence, re.I)
    if m:
        return m.group(1).strip(), m.group(2).lower()
    return None, None


def gate1_copular(sentence: str) -> bool:
    return bool(COPULAR.search(sentence))


def gate2_recipient_not_location(
    sentence: str, subject: Optional[str], verb: Optional[str],
    triple: Dict[str, Any],
) -> bool:
    """A "provides X to Y" object cannot be a location or a workplace."""
    if verb is None or triple.get("p") not in LOCATIONISH:
        return False
    if not PROVIDE_TO.search(sentence):
        return False
    obj = str(triple.get("o", ""))
    return bool(obj) and bool(re.search(rf"\b{re.escape(obj)}\b", sentence, re.I))


def gate3_purpose_not_object(
    sentence: str, subject: Optional[str], verb: Optional[str],
    triple: Dict[str, Any],
) -> bool:
    """A "X verb Y for Z" object is a purpose adjunct when it sits in the
    for-phrase rather than being the direct object."""
    if verb is None:
        return False
    if not PURPOSE_FOR.search(sentence):
        return False
    obj = str(triple.get("o", ""))
    if not obj:
        return False
    # The object is inside the "for ..." span, i.e. after the marker.
    for m in re.finditer(r"\bfor\b", sentence, re.I):
        tail = sentence[m.end():]
        if re.search(rf"\b{re.escape(obj)}\b", tail, re.I):
            return True
    return False


def apply_gates(sentence: str, triple: Dict[str, Any]) -> Optional[str]:
    """Return the gate that rejects this triple, or None if none applies.

    The copular gate is conjoined with the event-predicate set. Applied
    alone it is useless: a copular clause yields 34 asserted triples of
    which 18 are wrong, which is no worse than the 56% wrong rate overall,
    so it has almost no discriminative power, and it also rejects 16 correct
    triples -- "John is a member of a hiking club" does license part_of.
    Requiring the predicate to be an event as well makes it specific.
    """
    subject, verb = subject_verb_spans(sentence)
    if gate1_copular(sentence) and triple.get("p") in EVENT_PREDICATES:
        return "copular-event"
    if gate2_recipient_not_location(sentence, subject, verb, triple):
        return "recipient-not-location"
    if gate3_purpose_not_object(sentence, subject, verb, triple):
        return "purpose-not-object"
    return None


async def main() -> int:
    # Verdicts, keyed so the gates can be scored against them.
    from scripts.reconcile_triple_annotation import (
        ANNOTATION, IMPLIED, SUPPORTED, WRONG, load_gap,
    )

    rows = [json.loads(l) for l in
            DRAFT.read_text(encoding="utf-8").splitlines() if l.strip()]

    counters: Counter = Counter()
    indexed: Dict[Tuple[str, int], Dict[str, Any]] = {}
    per_stratum: Counter = Counter()
    for r in rows:
        per_stratum[r["stratum"]] += 1
        indexed[(r["stratum"], per_stratum[r["stratum"]])] = r

    verdicts = {(s, a, p, o): v for s, i, a, p, o, v in ANNOTATION}
    for g in load_gap():
        verdicts[(g["stratum"], g["s"], g["p"], g["o"])] = g["verdict"]

    caught_wrong = 0
    caught_right = 0
    examples: List[str] = []

    for (stratum, idx), row in indexed.items():
        for t in row.get("asserted", []):
            key = (stratum, t["s"], t["p"], t["o"])
            v = verdicts.get(key)
            if v is None:
                continue
            gate = apply_gates(row["text"], {
                "s": t["s"], "p": t["p"], "o": t["o"]})
            counters[v] += 1
            counters[f"gate:{gate}"] += 1
            if gate:
                if v == WRONG:
                    caught_wrong += 1
                    if len(examples) < 14:
                        examples.append(
                            f"[{gate}] {t['s']} -[{t['p']}]-> {t['o']}"
                            f"\n      {row['text'][:82]}")
                else:
                    caught_right += 1
                    counters[f"gate:{gate}:lost_a_good_one"] += 1

    total_wrong = counters[WRONG]
    total_right = counters[SUPPORTED] + counters[IMPLIED]
    total_annotated = sum(counters[v] for v in (SUPPORTED, IMPLIED, WRONG))
    print("=== structural gates vs the hand annotation ===")
    print(f"  annotated triples      {total_annotated}")
    print(f"  wrong triples          {total_wrong}")
    print()
    for gate in ("copular-event", "recipient-not-location", "purpose-not-object"):
        n = counters[f"gate:{gate}"]
        lost = counters[f"gate:{gate}:lost_a_good_one"]
        print(f"  {gate:24} rejects {n:3}   of which wrong {n - lost:3}, "
              f"good {lost}")
    any_gate = sum(counters[f"gate:{g}"] for g in
                   ("copular-event", "recipient-not-location",
                    "purpose-not-object"))
    baseline_precision = total_right / total_annotated if total_annotated else 0
    kept = total_annotated - any_gate
    kept_right = total_right - caught_right
    gated_precision = kept_right / kept if kept else 0.0

    print()
    print(f"  any gate rejects       {any_gate}")
    print(f"    wrong triples caught   {caught_wrong}")
    print(f"    good triples lost      {caught_right}")
    if total_wrong:
        print(f"  share of wrong caught  {caught_wrong / total_wrong:.1%}")
    print()
    print(f"  precision before gates {baseline_precision:.3f}")
    print(f"  precision after gates  {gated_precision:.3f}")
    if gated_precision > baseline_precision:
        print(f"    -> the gates pay for themselves: "
              f"{gated_precision - baseline_precision:+.3f}")
    else:
        print("    -> THE GATES COST MORE THAN THEY SAVE")
    if examples:
        print("\n  examples:")
        for e in examples:
            print(f"    {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))