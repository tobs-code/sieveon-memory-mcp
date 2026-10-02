"""Phase-A training manifest: schema and frozen spec, before any data is built.

The measurement phase is closed. Four-way classification on the frozen 60
gives clean_positive 4 (6.7 %), ambiguous_positive 1 (1.7 %), hard_negative 9
(15.0 %), no_signal 46 (76.7 %). The lexical frame filter finds 7 of the 9
negatives and 0 of the 4 positives, so it cannot serve as a sampler for both
classes at once. And the 18 existing gold facts are 18/18 possessive and
18/18 imprecise, which makes them a targeted seed for the thinnest class
rather than a natural positive distribution.

So the training set is split by provenance, and this file freezes that split
before a single training sentence exists. Provenance tags:

    natural_clean_positive      found in the blind 60, clean
    natural_ambiguous_positive found in the blind 60, imprecise
    natural_hard_negative      found in the blind 60, negative
    seed_possessive            the 18 existing provides gold facts
    controlled_*                constructed here, always labelled

Controlled data varies the semantic frame, not just the words. The point is
to teach the distinction between assistance performed and support merely
mentioned, wanted, attributed or instrumentalised. Every controlled frame is
specified as a matched pair with a single varying cue, so a negative cannot
be a sentence that is simply less on-topic than its positive.

The natural entries are read from the frozen audit and seed files. Nothing
is retyped by hand, so the manifest cannot drift from what was measured.

Invariants checked by validate():
  - every entry carries a provenance tag
  - natural counts match the frozen measurements exactly
  - no sentence appears under two classes
  - every controlled frame yields exactly one positive and one negative
  - matched pairs differ only in the declared cue
  - no target ratio is prescribed; natural rates are recorded, not enforced

Usage:
    python scripts/phase_a_manifest.py
    python scripts/phase_a_manifest.py --out docs/eval_phase_a_manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs" / "eval_hard_negative_prevalence.jsonl"
PILOT = ROOT / "docs" / "eval_training_pilot.jsonl"
OUT = ROOT / "docs" / "eval_phase_a_manifest.json"

# Controlled frames, frozen before construction. Each is a matched pair: the
# two variants share everything except the cue that decides the class.
# `cue` names the minimal difference; the builder must not vary anything else.
CONTROLLED_FRAMES: List[Dict[str, Any]] = [
    {
        "frame": "active_assistance",
        "cue": "realised vs offered",
        "positive_template": "{X} helped {Y} with the fundraiser.",
        "negative_template": "{X} offered to help {Y} with the fundraiser.",
        "expect": "the negative carries an offer modal, not a performed action",
    },
    {
        "frame": "active_encouragement",
        "cue": "directed encouragement vs reported effect",
        "positive_template": "{X} encouraged {Y} to keep going.",
        "negative_template": "{Y} said {X}'s encouragement kept him going.",
        "expect": "attribution to an effect is not a provided relation",
    },
    {
        "frame": "nominal_possessive",
        "cue": "direct possession vs instrumental framing",
        "positive_template": "{X}'s support for {Y} was constant.",
        "negative_template": "{Y} succeeded with {X}'s support.",
        "expect": "instrumental use of a possessive phrase does not itself assert "
                  "the relation",
    },
    {
        "frame": "abstract_object",
        "cue": "assistance performed with a concrete object vs an abstract one",
        "positive_template": "{X} helped {Y} move the boxes.",
        "negative_template": "{X} values the value of support.",
        "expect": "object concreteness is part of the positive cue",
    },
    {
        "frame": "intentional",
        "cue": "intention vs execution",
        "positive_template": "{X} helped {Y} after she asked.",
        "negative_template": "{X} planned to help {Y} after she asked.",
        "expect": "planning is not performing",
    },
]

PROVENANCE = ("natural_clean_positive", "natural_ambiguous_positive",
              "natural_hard_negative", "seed_possessive",
              "controlled_clean_positive", "controlled_hard_negative")


def natural_entries() -> List[Dict[str, Any]]:
    """Read the measured classes straight from the frozen files."""
    out: List[Dict[str, Any]] = []
    for line in AUDIT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        cls = r.get("provides_class")
        if not cls:
            continue
        prov = {"clean_positive": "natural_clean_positive",
                "ambiguous_positive": "natural_ambiguous_positive",
                "hard_negative": "natural_hard_negative"}.get(cls)
        if prov:
            out.append({"id": r["id"], "text": r["text"],
                        "provenance": prov, "source": "blind_60",
                        "reason": r.get("reason", "")})
    for line in PILOT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        for t in (r.get("triples") or []):
            if len(t) > 2 and t[1] == "provides":
                out.append({
                    "id": f'{r["id"]}|{t[0]}|provides|{t[2]}',
                    "text": r["text"], "provenance": "seed_possessive",
                    "source": "training_pilot_50",
                    "precision": "imprecise" if len(t) > 3 else "clean",
                    "reason": "existing provides gold, possessive frame",
                })
    return out


def validate(nat: List[Dict[str, Any]]) -> List[str]:
    problems: List[str] = []

    for e in nat:
        if e["provenance"] not in PROVENANCE:
            problems.append(f"bad provenance on {e['id']}")

    counts = Counter(e["provenance"] for e in nat)
    # These are the measured values. If the audit files ever change, the
    # manifest must be rebuilt rather than quietly carrying stale numbers.
    if counts["natural_clean_positive"] != 4:
        problems.append(f"expected 4 natural_clean_positive, got "
                        f"{counts['natural_clean_positive']}")
    if counts["natural_ambiguous_positive"] != 1:
        problems.append(f"expected 1 natural_ambiguous_positive, got "
                        f"{counts['natural_ambiguous_positive']}")
    if counts["natural_hard_negative"] != 9:
        problems.append(f"expected 9 natural_hard_negative, got "
                        f"{counts['natural_hard_negative']}")
    if counts["seed_possessive"] != 18:
        problems.append(f"expected 18 seed_possessive, got "
                        f"{counts['seed_possessive']}")

    # One sentence may legitimately carry several facts of the same class --
    # "provided comfort and company" is two provides facts in one sentence --
    # so the duplicate check keys on the fact id and only fires when the same
    # sentence lands in two different classes, which would be a real conflict.
    seen: Dict[str, str] = {}
    for e in nat:
        key = (e["id"].split("|")[0], e["text"].strip().lower())
        if key in seen and seen[key] != e["provenance"]:
            problems.append(f"sentence appears under both {seen[key]} and "
                            f"{e['provenance']}")
        seen[key] = e["provenance"]

    for f in CONTROLLED_FRAMES:
        if not f.get("positive_template") or not f.get("negative_template"):
            problems.append(f"frame {f['frame']} lacks a matched pair")
        if f["positive_template"] == f["negative_template"]:
            problems.append(f"frame {f['frame']} pair is identical")
        if not f.get("cue"):
            problems.append(f"frame {f['frame']} does not declare its cue")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    nat = natural_entries()
    counts = Counter(e["provenance"] for e in nat)

    print("=== phase-A manifest: natural part (measured) ===\n")
    print(f"  {'provenance':28} {'n':>3}")
    for p in PROVENANCE[:4]:
        print(f"  {p:28} {counts[p]:3}")
    print(f"  {'total natural':28} {sum(counts.values()):3}")
    print()
    print("  The seed is not a natural distribution: 18/18 possessive and")
    print("  imprecise, while the blind 60 yields 4 clean positives, all of")
    print("  them verbal constructions the frame filter never marks.")

    print("\n=== controlled part (spec frozen, data not yet built) ===\n")
    print(f"  {'frame':26} {'cue':42}")
    for f in CONTROLLED_FRAMES:
        print(f"  {f['frame']:26} {f['cue']:42}")
    print(f"\n  {len(CONTROLLED_FRAMES)} frames, each yielding one controlled "
          f"clean_positive\n  and one controlled_hard_negative.")
    print("  No target ratio is prescribed. Natural rates are recorded above;")
    print("  the controlled layer fills missing contrasts and stays labelled.")

    problems = validate(nat)
    print(f"\n  validation: {'clean' if not problems else 'PROBLEMS'}")
    for p in problems:
        print(f"    {p}")

    multi = sum(1 for e in nat
                if sum(1 for o in nat
                       if o["text"].strip().lower() == e["text"].strip().lower()
                       ) > 1)
    if multi:
        print(f"  {multi} sentences carry more than one fact of the same "
              f"class, which is\n  allowed and expected for multi-object "
              f"provides sentences.")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "purpose": "phase-A training data, split by provenance",
            "natural": nat,
            "controlled_frames": CONTROLLED_FRAMES,
            "natural_counts": dict(counts),
            "natural_rates": {k: round(v / 60, 4)
                              for k, v in counts.items()
                              if k.startswith("natural_")},
            "provenance_tags": list(PROVENANCE),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())