"""
LoCoMo spike: ablation BM25+vector (Arm A) vs full routed pipeline (Arm B).

Ingests LoCoMo dialog turns as events (isolated namespace, synthetic ordered
timestamps -- question dates live in the TEXT, e.g. "7 May 2023"), then runs
a capped set of QA pairs through both arms and scores word-F1 vs answers.

Category map (LoCoMo paper order, assumption -- verify against repo docs):
  1 single-hop, 2 multi-hop, 3 temporal, 4 commonsense, 5 adversarial.
Adversarial expects "unanswerable": reported separately (abstention rate),
both arms always answer, so F1 there is informative, not decisive.

Usage:
    python scripts/eval_locomo.py --data C:/path/locomo10.json --convos 2 --per-cat 12
"""

import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
os.chdir(str(PROJ))
sys.path.insert(0, str(PROJ))

CAT_NAMES = {1: "single-hop", 2: "multi-hop", 3: "temporal", 4: "commonsense", 5: "adversarial"}

BASE_TS = datetime(2023, 1, 1, tzinfo=timezone.utc)


def norm(text: str) -> list:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def f1(pred: str, gold: str) -> float:
    p, g = norm(pred), norm(gold)
    if not p or not g:
        return 0.0
    common = 0
    counts = {}
    for w in g:
        counts[w] = counts.get(w, 0) + 1
    for w in p:
        if counts.get(w, 0) > 0:
            counts[w] -= 1
            common += 1
    if common == 0:
        return 0.0
    prec, rec = common / len(p), common / len(g)
    return 2 * prec * rec / (prec + rec)


def answer_text(response: dict) -> str:
    s = response.get("summary") or {}
    return s.get("answer", "") if isinstance(s, dict) else ""


async def main() -> int:
    ap = argparse.ArgumentParser(description="LoCoMo ablation spike")
    ap.add_argument("--data", required=True)
    ap.add_argument("--convos", type=int, default=2)
    ap.add_argument("--per-cat", type=int, default=12)
    ap.add_argument("--namespace", default="sieveon_locom")
    ap.add_argument("--database", default="sieveon_locom")
    ap.add_argument("--out", default="locomo_spike_results.json")
    args = ap.parse_args()

    from src.mcp import core as mcp_core
    from src.mcp.common_logic import _execute_query, _store_content

    mcp_core.SURREAL_NS = args.namespace
    mcp_core.SURREAL_DB = args.database
    await mcp_core.ensure_schema_loaded()

    data = json.load(open(args.data, encoding="utf-8"))[: args.convos]
    # Cap questions per category for spike runtime
    qa_sets = []
    for conv in data:
        by_cat = defaultdict(list)
        for q in conv.get("qa", []):
            by_cat[q.get("category")].append(q)
        picked = []
        for cat in sorted(by_cat):
            picked.extend(by_cat[cat][: args.per_cat])
        qa_sets.append((conv, picked))

    total_turns = 0
    for ci, conv in enumerate(data):
        turns = [
            (skey, turn)
            for skey, sess in conv["conversation"].items()
            if skey.startswith("session_") and isinstance(sess, list)
            for turn in sess
        ]
        for si, (skey, turn) in enumerate(turns):
            ts = (BASE_TS + timedelta(days=si)).isoformat()
            text = f"{turn.get('speaker', '?')}: {turn.get('text', '')}"
            await _store_content(
                text, source="locomo",
                metadata={"convo": conv.get("sample_id"), "dia_id": turn.get("dia_id"), "session": skey},
            )
            # Stamp ordered timestamp (ingest uses time::now(); fix right after)
            total_turns += 1
        print(f"ingested convo {conv.get('sample_id')}: {len(turns)} turns", flush=True)
    print(f"total turns: {total_turns}", flush=True)

    from src.mcp.tools import event_log_search

    results = []
    for conv, picked in qa_sets:
        for q in picked:
            question = q["question"]
            gold = q.get("answer", "")
            cat = CAT_NAMES.get(q.get("category"), str(q.get("category")))
            # Arm A: pure hybrid BM25+vector, no KG
            try:
                a_res = await event_log_search(query=question, limit=5)
                a_blob = " ".join(e.get("content", "") for e in (a_res.get("events") or []))
            except Exception as e:
                a_blob = ""
                print(f"arm A error: {e}", flush=True)
            # Arm B: full routed pipeline
            try:
                b_res = await _execute_query(question)
                b_blob = answer_text(b_res)
            except Exception as e:
                b_blob = ""
                print(f"arm B error: {e}", flush=True)
            results.append({
                "convo": conv.get("sample_id"), "category": cat,
                "question": question, "answer": gold,
                "f1_a": round(f1(a_blob, gold), 4),
                "f1_b": round(f1(b_blob, gold), 4),
                "strategy_b": (b_res.get("strategy") if "b_res" in dir() else None),
            })
            print(f"[{cat:13s}] A={results[-1]['f1_a']:.2f} B={results[-1]['f1_b']:.2f} :: {question[:70]}", flush=True)

    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)
    summary = {}
    for cat, rows in sorted(by_cat.items()):
        summary[cat] = {
            "n": len(rows),
            "mean_f1_a": round(sum(r["f1_a"] for r in rows) / len(rows), 4),
            "mean_f1_b": round(sum(r["f1_b"] for r in rows) / len(rows), 4),
        }
    summary["_overall"] = {
        "n": len(results),
        "mean_f1_a": round(sum(r["f1_a"] for r in results) / len(results), 4),
        "mean_f1_b": round(sum(r["f1_b"] for r in results) / len(results), 4),
    }
    print(json.dumps(summary, indent=1), flush=True)
    out = args.out if os.path.isabs(args.out) else os.path.join(os.getcwd(), args.out)
    json.dump({"summary": summary, "results": results}, open(out, "w", encoding="utf-8"), indent=2)
    print(f"saved to {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
