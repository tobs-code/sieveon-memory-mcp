"""v1.2 linker ambiguity test: real corpus mentions, no model calls.

Cases from existing records and blind sentences:
- Jon vs john (0.86): distinct names, must ABSTAIN, never auto-merge.
- Maria's vs maria: possessive rule resolves exactly.
- John's team vs John's basketball team: distinct entities, no merge.
- Tim vs tom (0.67): below gate, distinct.
- Maria/Tim/club: exact matches resolve.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trackb_production import link, normalize

GRAPH = {"maria", "tim", "john", "club", "team", "nonprofit", "coach",
         "crowd", "donors", "users", "project", "sponsor", "app",
         "organizer", "venue", "meetup", "tom", "shelter", "community",
         "friends", "each other", "james", "nate", "homeless shelter"}

CASES = [
    ("Jon", "ambiguous"),
    ("Maria's", "resolved:maria"),
    ("Tim's", "resolved:tim"),
    ("John's team", "resolved:johns team"),
    ("John's basketball team", "resolved:johns basketball team"),
    ("Maria", "resolved:maria"),
    ("the club", "resolved:club"),
    ("Tim", "resolved:tim"),
]


def main() -> int:
    fails = 0
    for mention, expected in CASES:
        got = link(mention, GRAPH)
        actual = got["status"] if got["status"] == "ambiguous" \
            else f"resolved:{got['normalized']}"
        ok = actual == expected
        fails += not ok
        print(("PASS" if ok else "FAIL"), repr(mention), "->", actual,
              "" if ok else f"(expected {expected})")
    print("linker ambiguity v1.2:", "PASS" if not fails else f"{fails} FAILURES")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
