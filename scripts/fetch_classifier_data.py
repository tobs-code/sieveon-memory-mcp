"""
Fetch public training data for the Sieveon query classifier.

Sources (all verified 2026-09-30, see probes in Temp/opencode):
  multi-hop      HotpotQA distractor-train questions (CC BY-SA 4.0, crowdsourced)
  factual        SQuAD train questions (CC BY-SA 4.0)
  conversational CoQA story questions, flattened (check license before commercial use)
  update/...     CLINC150 'plus' mapped intents (check license before commercial use)
  temporal       TimeQA human_train.easy questions (BSD 3-Clause)

Writes docs/data/<name>.jsonl with {"text", "type", "source"} lines.
Exact-match dedup within each file. Existing files (trec/coqa/synthetic)
are left untouched; register new files in classifier._TRAINING_PATHS.

Usage:
    python scripts/fetch_classifier_data.py [--out docs/data] [--cap 600]
"""

import argparse
import gzip
import json
import os
import sys
import urllib.request
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ))

# Sieveon target classes: temporal, factual, multi-hop (hyphen!), conversational, update

CLINC_UPDATE = {
    "reminder", "reminder_update", "calendar_update", "todo_list_update",
    "shopping_list_update", "update_playlist", "alarm", "timer",
    "schedule_meeting", "cancel_reservation", "change_user_name",
    "reset_settings",
}
CLINC_CONV = {"greeting", "goodbye", "thank_you"}
CLINC_TEMPORAL = {"time", "date"}
CLINC_FACTUAL = {"definition", "weather"}


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _write(path: Path, rows: list) -> dict:
    seen, kept, dupes = set(), [], 0
    for text, typ, source in rows:
        text = _clean(text)
        if not text or len(text) < 5:
            continue
        key = text.lower()
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        kept.append({"text": text, "type": typ, "source": source})
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in kept:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"file": str(path), "kept": len(kept), "dupes": dupes}


def fetch_hotpot(out: Path, cap: int) -> dict:
    from datasets import load_dataset

    ds = load_dataset("hotpotqa/hotpot_qa", name="distractor", split="train", streaming=True)
    rows = []
    for ex in ds:
        q = _clean(ex.get("question", ""))
        if q:
            rows.append((q, "multi-hop", "hotpot_distractor"))
        if len(rows) >= cap:
            break
    return _write(out / "hotpot_multihop.jsonl", rows)


def fetch_squad(out: Path, cap: int) -> dict:
    from datasets import load_dataset

    ds = load_dataset("rajpurkar/squad", split="train", streaming=True)
    rows = []
    for ex in ds:
        q = _clean(ex.get("question", ""))
        if q:
            rows.append((q, "factual", "squad"))
        if len(rows) >= cap:
            break
    return _write(out / "squad_factual.jsonl", rows)


def fetch_coqa(out: Path, cap: int) -> dict:
    from datasets import load_dataset

    ds = load_dataset("stanfordnlp/coqa", split="train", streaming=True)
    rows = []
    for ex in ds:
        for q in ex.get("questions") or []:
            q = _clean(q if isinstance(q, str) else "")
            if q:
                rows.append((q, "conversational", "coqa_hf"))
            if len(rows) >= cap:
                break
        if len(rows) >= cap:
            break
    return _write(out / "coqa_conv.jsonl", rows)


def fetch_clinc(out: Path, caps: dict) -> dict:
    from datasets import load_dataset

    ds = load_dataset("clinc/clinc_oos", "plus", split="train")
    names = ds.features["intent"].names
    buckets: dict = {"update": [], "conversational": [], "temporal": [], "factual": []}
    skipped = 0
    for ex in ds:
        intent = names[ex["intent"]]
        text = _clean(ex["text"])
        if not text:
            continue
        if intent in CLINC_UPDATE:
            buckets["update"].append((text, "update", f"clinc:{intent}"))
        elif intent in CLINC_CONV:
            buckets["conversational"].append((text, "conversational", f"clinc:{intent}"))
        elif intent in CLINC_TEMPORAL:
            buckets["temporal"].append((text, "temporal", f"clinc:{intent}"))
        elif intent in CLINC_FACTUAL:
            buckets["factual"].append((text, "factual", f"clinc:{intent}"))
        else:
            skipped += 1
    rows = []
    for typ, items in buckets.items():
        rows.extend(items[: caps.get(typ, len(items))])
    stats = _write(out / "clinc_mapped.jsonl", rows)
    stats["skipped_intents"] = skipped
    stats["per_class"] = {k: min(len(v), caps.get(k, len(v))) for k, v in buckets.items()}
    return stats


def fetch_timeqa(out: Path, cap: int) -> dict:
    url = ("https://raw.githubusercontent.com/wenhuchen/Time-Sensitive-QA/"
           "master/dataset/human_train.easy.json.gzip")
    req = urllib.request.Request(url, headers={"User-Agent": "sieveon-fetch"})
    with urllib.request.urlopen(req, timeout=180) as r:
        blob = r.read()
    rows = []
    for line in gzip.decompress(blob).decode("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            q = _clean(json.loads(line).get("question", ""))
        except json.JSONDecodeError:
            continue
        if q:
            rows.append((q, "temporal", "timeqa_human_easy"))
        if len(rows) >= cap:
            break
    return _write(out / "timeqa_temporal.jsonl", rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch public classifier training data")
    ap.add_argument("--out", default=str(PROJ / "docs" / "data"))
    ap.add_argument("--cap", type=int, default=600)
    ap.add_argument("--only", default="", help="comma list: hotpot,squad,coqa,clinc,timeqa")
    args = ap.parse_args()

    out = Path(args.out)
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    jobs = {
        "hotpot": lambda: fetch_hotpot(out, args.cap),
        "squad": lambda: fetch_squad(out, 300),
        "coqa": lambda: fetch_coqa(out, 400),
        "clinc": lambda: fetch_clinc(out, {"update": 500, "conversational": 60, "temporal": 60, "factual": 60}),
        "timeqa": lambda: fetch_timeqa(out, 400),
    }
    failed = 0
    for name, fn in jobs.items():
        if only and name not in only:
            continue
        try:
            print(f"[{name}] fetching...", flush=True)
            print(f"[{name}]", fn(), flush=True)
        except Exception as e:
            failed += 1
            print(f"[{name}] FAILED: {type(e).__name__}: {str(e)[:300]}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
