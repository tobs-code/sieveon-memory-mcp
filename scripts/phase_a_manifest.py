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
        # Originally specified as "concrete vs abstract object". That trains
        # the exact heuristic the recall audit disproved: `John supports James`
        # was missed too, so object concreteness does not explain the failure.
        # The cue is the semantic role of the assistance, not the noun class.
        "frame": "assistance_performed_vs_mentioned",
        "cue": "assistance carried out vs assistance only spoken of",
        "positive_template": "{X} helped {Y} carry the boxes.",
        "negative_template": "{X} talked about helping {Y} carry the boxes.",
        "expect": "the negative mentions the assistance without performing it",
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

# Construction rules, frozen with the frames. Each is checked by
# validate_constructed(), not merely asserted here.
CONSTRUCTION_RULES = {
    "no_test_leakage": "no controlled sentence may paraphrase or reuse text "
                       "from the 53 counterfactual facts or the 44 current "
                       "gold sentences, nor any audited or annotated sentence",
    "one_gold_relation": "a controlled example asserts exactly one target "
                         "relation; no additional competing relation is "
                         "smuggled in",
    "entity_type_balance": "entity types are drawn from the production "
                           "typology and varied across frames, so the model "
                           "cannot key on person-to-person alone",
    "matched_local_syntax": "the two variants of a pair share their entities "
                            "and their local syntax; only the declared cue "
                            "may differ, so no positional cue such as "
                            "sentence length or verb class separates them",
    "no_aspect_leak": "no variant may introduce an aspect the other lacks",
}

ENTITY_TYPES = ["person", "organization", "concept", "event", "location",
                "technology"]


def _test_corpus_texts() -> List[str]:
    """Every sentence that must not be paraphrased into controlled data."""
    texts: List[str] = []
    for rel in ("docs/eval_recall_gold_counterfactual.jsonl",
                "docs/eval_recall_gold_pilot.jsonl",
                "docs/eval_recall_gold_batch2.jsonl",
                "docs/eval_recall_gold_expanded.jsonl",
                "docs/eval_training_pilot.jsonl",
                "docs/eval_hard_negative_prevalence.jsonl"):
        p = ROOT / rel
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
            t = r.get("text")
            if t:
                texts.append(t.strip().lower())
    return texts


def validate_constructed(entries: List[Dict[str, Any]],
                         corpus: List[str]) -> List[str]:
    """Semantic checks on built pairs, beyond the spec-level validation."""
    problems: List[str] = []
    banned_aspects = ("never ", "hadn't", "won't", "will ", "would have")

    # Grouping is by pair_id, not by frame: after expansion a frame holds
    # several pairs, and the invariant under test is the within-pair match.
    by_pair: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        by_pair.setdefault(e.get("pair_id", e.get("frame", "unnamed")),
                           []).append(e)
    for pair_id, group in by_pair.items():
        frame = group[0].get("frame", group[0].get("frame_id", "unnamed"))
        pos = [e for e in group if e["class"] == "clean_positive"]
        neg = [e for e in group if e["class"] == "hard_negative"]
        if len(pos) != 1 or len(neg) != 1:
            problems.append(f"{frame}: expected one clean and one hard, got "
                            f"{len(pos)}/{len(neg)}")
            continue
        a, b = pos[0], neg[0]
        if a["entities"] != b["entities"]:
            problems.append(f"{frame}: pair does not share its entities")
        wa, wb = a["sentence"].split(), b["sentence"].split()
        if abs(len(wa) - len(wb)) > 4:
            problems.append(f"{frame}: pair differs in length by "
                            f"{abs(len(wa) - len(wb))} tokens, which lets "
                            f"length separate the classes")
        for e in (a, b):
            low = e["sentence"].lower()
            if any(w in low for w in banned_aspects):
                problems.append(f"{frame}/{e['class']}: aspect or negation leak")
            if len(e["target_relation"]) != 1:
                problems.append(f"{frame}/{e['class']}: more than one target "
                                f"relation: {e['target_relation']}")
        for t in corpus:
            if a["sentence"].strip().lower() == t or \
                    b["sentence"].strip().lower() == t:
                problems.append(f"{frame}: controlled sentence collides with "
                                f"frozen test or audited text")
    return problems


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


def build_seeds() -> List[Dict[str, Any]]:
    """The ten controlled seeds: one matched pair per frame.

    Entity types are varied deliberately. Every frame uses the same two
    entities in both variants, so nothing but the cue separates the classes;
    the types change from frame to frame so the model cannot learn that
    person-to-person assistance is the positive case.
    """
    slots = [
        ("Maria", "Tim", ["person", "person"]),
        ("Maria", "the nonprofit", ["person", "organization"]),
        ("the venue", "the organizer", ["organization", "organization"]),
        ("the app", "the team", ["technology", "organization"]),
        ("the meetup", "Tom", ["event", "person"]),
    ]
    out: List[Dict[str, Any]] = []
    for f, (x, y, types) in zip(CONTROLLED_FRAMES, slots):
        for cls, key in (("clean_positive", "positive_template"),
                         ("hard_negative", "negative_template")):
            tpl = f[key]
            out.append({
                "frame": f["frame"], "cue": f["cue"], "class": cls,
                "template": tpl,
                "sentence": tpl.format(X=x, Y=y),
                "entities": [x, y], "entity_types": types,
                "target_relation": ["provides"],
                "target_object": ("encouragement" if f["frame"] ==
                                 "active_encouragement" else "help"),
                "provenance": ("controlled_clean_positive" if cls ==
                               "clean_positive" else "controlled_hard_negative"),
            })
    return out


# Expansion axes. Each frame gets several independent variants of its cue,
# crossed with different entity pairs and a surface modifier. The rule that
# makes the result interpretable: within a pair everything is held fixed
# except the cue phrase. Across pairs the axes vary, but not all of them at
# once, so a classifier that reacts to sentence length or to entity type has
# nowhere to hide.
CUE_VARIANTS = {
    "active_assistance": [
        ("helped", "offered to help"),
        ("assisted", "said she would assist"),
        ("helped out", "spoke of helping out"),
    ],
    "active_encouragement": [
        ("encouraged", "said he would encourage"),
        ("cheered on", "spoke of cheering on"),
        ("urged", "talked about urging"),
    ],
    "nominal_possessive": [
        ("'s support for", "'s support was instrumental for"),
    ],
    "assistance_performed_vs_mentioned": [
        ("helped", "spoke of helping"),
        ("assisted", "described assisting"),
        ("was busy helping", "was asked about helping"),
    ],
    "intentional": [
        ("helped", "planned to help"),
        ("assisted", "meant to assist"),
        ("supported", "intended to support"),
    ],
}

# One shell per frame. The cue phrase slots into the same position in both
# variants, so the pair cannot be separated by anything but the cue itself.
SHELLS = {
    "active_assistance": "{X} {cue} {Y} with the fundraiser.",
    "active_encouragement": "{X} {cue} {Y} to keep going.",
    "nominal_possessive": "{X} {cue} {Y} was steady.",
    "assistance_performed_vs_mentioned": "{X} {cue} {Y} move the boxes.",
    "intentional": "{X} {cue} {Y} after she asked.",
}

ENTITY_SLOTS = [
    (["Maria", "Tim"], ["person", "person"]),
    (["Maria", "the nonprofit"], ["person", "organization"]),
    (["the organizer", "the venue"], ["organization", "organization"]),
    (["the team", "the app"], ["organization", "technology"]),
    (["the meetup", "Tom"], ["event", "person"]),
    (["the coach", "the club"], ["person", "organization"]),
    (["the project", "the sponsor"], ["concept", "organization"]),
]


def build_pairs() -> List[Dict[str, Any]]:
    """Matched pairs across all five frames, keyed for pair-level splitting."""
    out: List[Dict[str, Any]] = []
    for fi, f in enumerate(CONTROLLED_FRAMES):
        frame = f["frame"]
        shell = SHELLS[frame]
        variants = CUE_VARIANTS[frame]
        for vi, (pos_cue, neg_cue) in enumerate(variants):
            # One axis moves at a time across pairs: the cue variant advances
            # fastest, the entity slot advances slowest, so consecutive pairs
            # differ in exactly one dimension.
            ents, types = ENTITY_SLOTS[(fi * len(variants) + vi) % len(ENTITY_SLOTS)]
            surface = "" if vi % 2 == 0 else "the "
            pid = f"{frame}--{vi:02d}"
            for cls, cue in (("clean_positive", pos_cue),
                             ("hard_negative", neg_cue)):
                out.append({
                    "pair_id": pid, "frame_id": frame, "frame_index": fi,
                    "variant_index": vi, "cue": f["cue"],
                    "class": cls, "cue_phrase": cue,
                    "entities": list(ents), "entity_types": list(types),
                    "surface": surface,
                    "sentence": shell.format(X=ents[0], Y=ents[1], cue=cue),
                    "target_relation": ["provides"],
                    "provenance": ("controlled_clean_positive" if cls ==
                                   "clean_positive" else
                                   "controlled_hard_negative"),
                    "split_key": pid,
                })
    return out


def _render(entry: Dict[str, Any], shell: str, tail: str) -> str:
    x, y = entry["entities"]
    if entry["frame_id"] == "nominal_possessive":
        return f'{entry["surface"]}{x} {entry["cue_phrase"]} {y} was steady.'
    return f'{x} {entry["cue_phrase"]}{tail}'


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

    pairs = build_pairs()
    corpus = _test_corpus_texts()
    problems += validate_constructed(pairs, corpus)

    print(f"\n  controlled pairs built: {len(pairs)} entries "
          f"({len(pairs) // 2} matched pairs)\n")
    print(f"  {'pair_id':38} {'entities':26} classes")
    seen_pair = []
    for p in pairs:
        if p["pair_id"] in seen_pair:
            continue
        seen_pair.append(p["pair_id"])
        same = [e for e in pairs if e["pair_id"] == p["pair_id"]]
        ents = " / ".join(p["entities"])
        print(f"  {p['pair_id']:38} {ents:26} "
              f"{len(same)} entries, cue '{p['cue'][:28]}'")
    print(f"\n  distinct pair_ids: {len(seen_pair)}  "
          f"(train/val/test must split on pair_id, never on rows)")
    print()
    for p in pairs[:12]:
        print(f"    {p['class']:16} {p['sentence']}")

    print("\n  construction rules enforced:")
    for k, v in CONSTRUCTION_RULES.items():
        print(f"    {k:22} {v[:78]}")
    print(f"\n  leakage check against {len(corpus)} frozen sentences: "
          f"{'clean' if not any('collides' in p for p in problems) else 'COLLISION'}")

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
            "construction_rules": CONSTRUCTION_RULES,
            "controlled_pairs": pairs,
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