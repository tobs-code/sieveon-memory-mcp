"""Prevalence of hard negatives for `provides`, before any training manifest.

The positive data for `provides` exists and is entirely imprecise: 18 gold
facts, 0 clean, 8 of them the single object `support`. Training on that set
alone would teach exactly the rule the annotation deliberately refused --
possessive noun phrase implies `provides`. So the set needs hard negatives,
sentences that carry a support or assistance frame and still do not license
`X provides support`:

    with James's support            instrumental framing
    support attributed to someone else
    desire or intention involving support
    a genuine but different relation about support

The quota 25/40/35 in the phase-A spec is a design target, not an observed
distribution. This measures whether the corpus can supply it. Sampling is
deterministic and blind: an even stride over the whole remaining pool, with
no relation claim, no confidence and no provides-specific filter deciding
what gets annotated. The `support_frame` flag below is computed for
reporting, and never used to select. Filtering on it would answer a
different question -- how many support frames exist among sentences already
chosen because they have one.

Only eligibility is annotated here, not triples. This run is a prevalence
measurement, not gold.

Usage:
    python scripts/audit_hard_negative_prevalence.py --count 60
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
LOCOMO = ROOT / "_unused" / "locomo" / "data" / "locomo10.json"
MANIFEST = ROOT / "docs" / "eval_hard_negative_manifest.json"
SCAFFOLD = ROOT / "docs" / "eval_hard_negative_prevalence.jsonl"

EXCLUDE = [
    "docs/eval_triples_gold_locomo_uniform.jsonl",
    "docs/eval_triples_gold_locomo_draft.jsonl",
    "docs/eval_recall_gold_pilot.jsonl",
    "docs/eval_recall_gold_batch2.jsonl",
    "docs/eval_recall_gold_expanded.jsonl",
    "docs/eval_training_pilot.jsonl",
]

# Text-only. Used to report how many sampled sentences contain a support
# frame at all, never to choose which sentences are annotated.
SUPPORT_NOUNS = {
    "support", "encouragement", "assistance", "help", "advice", "mentoring",
    "backing", "sustenance", "comfort", "care", "guidance", "hand",
    "backing", "affirmation", "boost", "welcome",
}
FRAME_CUES = {
    "instrumental", "intention", "attribution", "evaluation",
}


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
                                 "sample_id": s["sample_id"]})
    pool.sort(key=lambda r: (r["sample_id"], r["id"]))
    return pool


def support_frame(text: str) -> Dict[str, Any]:
    """Text-only indicators. Reported, never used for selection."""
    toks = [t for t in re.split(r"[^\w']+", text.lower()) if t]
    nouns = sorted({t for t in toks if t in SUPPORT_NOUNS})
    possessive = bool(re.search(r"\b[A-Z][a-z]+'s\s+\w*"
                                r"(support|encouragement|assistance|help|"
                                r"advice|comfort|care)\b", text))
    instrumental = bool(re.search(r"\b(with|thanks to|owing to)\b", text.lower()))
    return {"support_nouns": nouns, "possessive_frame": possessive,
            "instrumental_cue": instrumental,
            "has_support_frame": bool(nouns)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--scaffold", action="store_true")
    args = ap.parse_args()

    pool = build_pool()
    step = max(1, len(pool) // args.count)
    picked = pool[::step][:args.count]

    print("=== hard-negative prevalence: sampling ===\n")
    print(f"  remaining pool (unused observation sentences) {len(pool)}")
    print(f"  sampled (even stride, blind to claims)       {len(picked)}")
    frames = [p for p in picked if support_frame(p["text"])["has_support_frame"]]
    print(f"  of which carry a support frame (reported, not filtered) "
          f"{len(frames)}  ({len(frames) / len(picked):.0%})")
    print()
    print("  The sample is NOT restricted to support frames. The prevalence")
    print("  that matters is hard negatives among all sampled sentences,")
    print("  and a frame-only sample would report the wrong denominator.")

    if args.freeze:
        ids = [p["id"] for p in picked]
        MANIFEST.write_text(json.dumps({
            "purpose": "hard-negative prevalence for provides, not a training set",
            "pool_size": len(pool),
            "rule": "even stride over the sorted remaining pool; no claim, "
                    "confidence or support-frame filter participates in selection",
            "count": len(ids),
            "sha256_of_ids": hashlib.sha256(
                "\n".join(ids).encode("utf-8")).hexdigest(),
            "ids": ids,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nfroze {len(ids)} ids -> {MANIFEST.relative_to(ROOT)}")
        return 0

    if args.scaffold:
        rows = []
        for p in picked:
            f = support_frame(p["text"])
            rows.append({"id": p["id"], "text": p["text"],
                         "support_frame": f["has_support_frame"],
                         "support_nouns": f["support_nouns"],
                         "possessive_frame": f["possessive_frame"],
                         "instrumental_cue": f["instrumental_cue"],
                         "hard_negative": None, "reason": None, "by": None})
        SCAFFOLD.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                                       for r in rows) + "\n", encoding="utf-8")
        print(f"\nwrote {SCAFFOLD.relative_to(ROOT)} ({len(rows)} rows)")
        print("  annotate `hard_negative` yes/no and `reason` for each")

    print("\n  sentences carrying a support frame (candidates worth reading):")
    for n, p in enumerate(frames, 1):
        f = support_frame(p["text"])
        print(f"    [{n:2}] {p['text'][:104]}")
        print(f"         nouns={','.join(f['support_nouns'])}"
              f" possessive={f['possessive_frame']}"
              f" instrumental={f['instrumental_cue']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())