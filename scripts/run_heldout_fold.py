"""Fold runner: deterministic orchestration only, no decisions of its own.

Resolves each protocol fold from frozen files (never constructs or alters
folds), converts pairs to training-contract examples, validates them with
train_relex, and prints digests. Without --dry-run it refuses: the trainer
loop is not wired yet, so no checkpoint, prediction or metric is produced.

Fold rule: test = held-out family's pairs; train = all other pairs among
the 6 expansion families plus the v2 epistemic reference. Boundary fold:
train = 4 epistemic pairs, test = 3 entity-disjoint NP-2 pairs (the
overlapping NP-2--00 pilot stays out, per d560641).

Usage:
    python scripts/run_heldout_fold.py --fold <id> --dry-run
    python scripts/run_heldout_fold.py --all --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]

FAMILY_FILES = {
    "active_assistance:delegated_causative": "docs/eval_phase_a_expansion_scaled.json",
    "assistance_mentioned:nominalized_commentary": "docs/eval_phase_a_expansion_scaled.json",
    "intentional:conditional_hypothetical": "docs/eval_phase_a_expansion_scaled.json",
    "active_encouragement:recipient_switch": "docs/eval_phase_a_expansion_ae1.json",
    "assistance_mentioned:interrogative_need": "docs/eval_phase_a_expansion_ap2.json",
    "nominal_possessive:desiderative_embedding": "docs/eval_phase_a_expansion_np2.json",
}

FOLDS = {
    "aa1": "active_assistance:delegated_causative",
    "ap1": "assistance_mentioned:nominalized_commentary",
    "in1": "intentional:conditional_hypothetical",
    "ae1": "active_encouragement:recipient_switch",
    "ap2": "assistance_mentioned:interrogative_need",
    "np2": "nominal_possessive:desiderative_embedding",
    "boundary": "nominal_possessive:desiderative_embedding",
}


def _load_all() -> list[dict]:
    pairs: list[dict] = []
    seen_files: dict[str, list[dict]] = {}
    for fam, rel in FAMILY_FILES.items():
        if rel not in seen_files:
            seen_files[rel] = json.loads((ROOT / rel).read_text())["pairs"]
        pairs += [e for e in seen_files[rel]
                  if e.get("construction_family_id") == fam]
    v2 = json.loads((ROOT / "docs" / "eval_phase_a_manifest.json").read_text())
    pairs += [e for e in v2["controlled_pairs"]
              if e.get("construction_family_id") == "nominal_possessive:epistemic"]
    for e in pairs:
        e.setdefault("frame", e.get("frame_id", ""))
    return pairs


def _span(sentence: str, mention: str) -> tuple[int, int, str]:
    idx = sentence.lower().find(mention.lower())
    if idx < 0:
        raise ValueError(f"entity {mention!r} not in {sentence!r}")
    return idx, idx + len(mention), sentence[idx:idx + len(mention)]


def to_example(entry: dict) -> dict:
    sent = entry["sentence"]
    x, y = entry["entities"]
    sx, ex, tx = _span(sent, x)
    sy, ey, ty = _span(sent, y)
    return {
        "sentence": sent,
        "entities": {"X": {"start": sx, "end": ex, "text": tx},
                     "Y": {"start": sy, "end": ey, "text": ty}},
        "relation": ("provides" if entry["class"] == "clean_positive"
                     else "no_relation"),
        "metadata": {
            "provenance": entry.get("provenance", entry.get("source", "expansion")),
            "pair_id": entry["pair_id"],
            "construction_family_id": entry["construction_family_id"],
        },
    }


def resolve_fold(fold_id: str, pairs: list[dict]):
    held = FOLDS[fold_id]
    if fold_id == "boundary":
        test = [e for e in pairs
                if e.get("construction_family_id") == held
                and e["pair_id"] in ("NP-2--01", "NP-2--02", "NP-2--03")]
        train = [e for e in pairs
                 if e.get("construction_family_id") == "nominal_possessive:epistemic"]
    else:
        test = [e for e in pairs if e.get("construction_family_id") == held]
        train = [e for e in pairs if e.get("construction_family_id") != held]
    return train, test


def digest_examples(examples: list[dict]) -> str:
    blob = "\n".join(f'{e["sentence"]}|{e["entities"]["X"]["text"]}|'
                     f'{e["entities"]["Y"]["text"]}|{e["relation"]}'
                     for e in examples)
    return hashlib.sha256(blob.encode()).hexdigest()


def dry_run_fold(fold_id: str, pairs: list[dict]) -> int:
    from train_relex import validate_example
    train, test = resolve_fold(fold_id, pairs)
    problems: list[str] = []
    train_ex, test_ex = [], []
    for e in train:
        try:
            train_ex.append(to_example(e))
        except ValueError as exc:
            problems.append(str(exc))
    for e in test:
        try:
            test_ex.append(to_example(e))
        except ValueError as exc:
            problems.append(str(exc))
    for i, ex in enumerate(train_ex + test_ex, 1):
        problems += validate_example(ex, i)
    train_pids = {e["pair_id"] for e in train}
    test_pids = {e["pair_id"] for e in test}
    if train_pids & test_pids:
        problems.append(f"pair overlap train/test: {train_pids & test_pids}")
    train_fams = {e.get("construction_family_id") for e in train}
    if fold_id != "boundary" and FOLDS[fold_id] in train_fams:
        problems.append("held-out family present in train")
    print(f"fold {fold_id}: held={FOLDS[fold_id]} "
          f"train={len(train_ex)} test={len(test_ex)}")
    print(f"  train_digest={digest_examples(train_ex)[:16]} "
          f"test_digest={digest_examples(test_ex)[:16]}")
    if problems:
        for p in problems:
            print(f"  PROBLEM {p}")
        return 1
    print("  dry-run clean: fold resolved, contract valid, nothing trained")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fold", default=None, choices=list(FOLDS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.dry_run:
        print("  REFUSED: trainer loop not wired; re-run with --dry-run.",
              file=sys.stderr)
        return 2
    pairs = _load_all()
    folds = list(FOLDS) if args.all else [args.fold or "aa1"]
    rc = 0
    for f in folds:
        rc |= dry_run_fold(f, pairs)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
