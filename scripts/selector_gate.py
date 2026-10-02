"""Abstraction levels and comparability for the production relations.

The unrestricted selector lost more than it gained on the full gold set:
26/44 fell to 21/44, one claim corrected and four correct claims broken. The
four regressions were not noise. They were all the same shape -- the
selector swapped a semantically right abstract relation for a lexically
closer concrete one: founded for started, created for finished, works_at
for owns, developed for works_at.

Gating needs a notion of "same level of abstraction", and that notion must
not be reverse-engineered from the four regressions, or the gate becomes a
description of the failures it was built to prevent. So the levels below are
a classification of the 17 production relations on their own terms:

    0  position / structure   part_of, located_in
    1  use / affiliation      uses, works_at, joined, leads, provides, acquired
    2  conception            created, developed, designed, founded, wrote,
                              built, funded, integrated, discovered

Within a level, two relations compete for the same kind of statement about a
pair, and a ranker is choosing between two reasonable readings. Across
levels, one relation is an abstraction of the other, and no score should be
allowed to demote the abstraction to its instance: "founded the store" and
"started the store" are not two readings of one fact, they are different
claims about how the store came to be.

Comparability is symmetric and reflexive within a level, and never across.
The gate abstains on the rest.

Nothing here is derived from the counterfactual. The counterfactual
describes relations the chain cannot state; this table is about the
relations it can, and the two questions do not meet.

Usage:
    python scripts/selector_gate.py
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

# Abstraction level per production predicate. Written before the gated run.
ABSTRACTION_LEVEL: Dict[str, int] = {
    # 0: where something sits in a structure
    "part_of": 0,
    "located_in": 0,
    # 1: what someone does with or for something
    "uses": 1,
    "works_at": 1,
    "joined": 1,
    "leads": 1,
    "provides": 1,
    "acquired": 1,
    # 2: something brought into being or brought to light
    "created": 2,
    "developed": 2,
    "designed": 2,
    "founded": 2,
    "wrote": 2,
    "built": 2,
    "funded": 2,
    "integrated": 2,
    "discovered": 2,
}

LEVEL_NAME = {0: "structural", 1: "affiliation/use", 2: "conception"}


def level(relation: str) -> Optional[int]:
    return ABSTRACTION_LEVEL.get(relation)


def comparable(a: str, b: str) -> bool:
    """May a ranker choose between these two, or must it abstain?

    Same relation: yes, trivially. Different relations in the same level:
    yes, they compete for the same statement. Different levels: no, because
    demoting an abstraction to its instance is the exact failure the
    unrestricted selector produced.
    """
    la, lb = level(a), level(b)
    if la is None or lb is None:
        # Outside the production set: the gate has no opinion, and the safe
        # reading is to abstain rather than to guess.
        return False
    return la == lb


def verdict(a: str, b: str) -> str:
    if a == b:
        return "same"
    return "rank" if comparable(a, b) else "abstain"


def explain(a: str, b: str) -> str:
    la, lb = level(a), level(b)
    v = verdict(a, b)
    if v == "same":
        return f"{a} == {b}"
    if v == "abstain":
        return (f"{a} [{LEVEL_NAME.get(la, 'outside')}] vs "
                f"{b} [{LEVEL_NAME.get(lb, 'outside')}] -- not comparable, "
                f"keep the original relation")
    return (f"{a} vs {b} [{LEVEL_NAME.get(la)}] -- rankable, both "
            f"{LEVEL_NAME.get(la)}")


if __name__ == "__main__":
    print(f"production relations classified: {len(ABSTRACTION_LEVEL)}\n")
    for lv in sorted(LEVEL_NAME):
        members = sorted(k for k, v in ABSTRACTION_LEVEL.items() if v == lv)
        print(f"  {lv}  {LEVEL_NAME[lv]:16} {', '.join(members)}\n")
    print("  the four observed regressions under this classification:")
    for a, b in (("founded", "started"), ("created", "finished"),
                 ("developed", "works_at"), ("works_at", "owns")):
        print(f"    {explain(a, b)}")
    print("\n  representative rankable pairs:")
    for a, b in (("created", "developed"), ("uses", "works_at"),
                 ("acquired", "provides"), ("created", "wrote")):
        print(f"    {explain(a, b)}")