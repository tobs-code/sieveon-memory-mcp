"""Node-worthiness gates A/B/C (no pipeline change)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from node_worthiness import node_worthy

GATE_A = [  # (mention, expected)
    ("Jon", "WORTHY"), ("John", "WORTHY"),
    ("Maria", "WORTHY"), ("Tim", "WORTHY"), ("Gina", "WORTHY"),
    ("Dancing", "NOT_WORTHY"), ("Yoga", "NOT_WORTHY"),
    ("beginner yoga class", "NOT_WORTHY"),
    ("kids in need", "NOT_WORTHY"), ("people who lost their jobs", "NOT_WORTHY"),
    ("his family", "NOT_WORTHY"),
]
GATE_B = ["homeless shelter", "the club", "the nonprofit", "the venue",
          "the team", "friends", "students", "a transgender teen",
          "the donors", "the users", "the crowd", "Maria", "the shelter",
          "the community center", "the charity", "the app", "Tom",
          "the organizer", "the project", "the sponsor", "the coach"]
GATE_C = ["Dancing", "Yoga", "beginner yoga class"]


def main() -> int:
    fails = 0
    for m, exp in GATE_A:
        got = node_worthy(m)["verdict"]
        expv = "WORTHY" if exp == "WORTHY" else "NOT_WORTHY"
        ok = got == expv
        fails += not ok
        print(("PASS" if ok else "FAIL"), "A", repr(m), "->", got, "" if ok else f"(exp {expv})")
    for m in GATE_B:
        got = node_worthy(m)["verdict"]
        ok = got == "WORTHY"
        fails += not ok
        print(("PASS" if ok else "FAIL"), "B", repr(m), "->", got)
    for m in GATE_C:
        got = node_worthy(m)["verdict"]
        ok = got == "NOT_WORTHY"
        fails += not ok
        print(("PASS" if ok else "FAIL"), "C", repr(m), "->", got)
    print("GATES:", "GREEN" if not fails else f"{fails} FAILURES")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
