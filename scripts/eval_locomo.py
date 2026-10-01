"""
LoCoMo spike: ablation BM25+vector (Arm A) vs full routed pipeline (Arm B).

Ingests LoCoMo dialog turns as events (isolated namespace, synthetic ordered
timestamps -- question dates live in the TEXT, e.g. "7 May 2023"), then runs
a capped set of QA pairs through both arms.

Primary metrics:
  evidence_hit   did we retrieve the session(s) the gold answer lives in
  containment    fraction of gold answer tokens present in the evidence

Containment, not F1: both arms return evidence chunks (~220 tokens) rather
than a generated short answer, so symmetric F1 is capped at
len(gold)/len(chunk) and a perfect hit scores ~0.02. Measured on the same
runs: f1=0.013 vs containment=0.54. Word-F1 is still reported (mean_f1_*)
for comparability with earlier runs only.

Category map (LoCoMo paper order, assumption -- verify against repo docs):
  1 single-hop, 2 multi-hop, 3 temporal, 4 commonsense, 5 adversarial.
Adversarial expects "unanswerable": reported separately (abstention rate),
both arms always answer, so containment there is informative, not decisive.

Usage:
    python scripts/eval_locomo.py --data C:/path/locomo10.json --convos 2 --per-cat 12
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
os.chdir(str(PROJ))
sys.path.insert(0, str(PROJ))

CAT_NAMES = {1: "single-hop", 2: "multi-hop", 3: "temporal", 4: "commonsense", 5: "adversarial"}

BASE_TS = datetime(2023, 1, 1, tzinfo=timezone.utc)


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def norm(text) -> list:
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def f1(pred: str, gold: str) -> float:
    """Symmetric word F1.

    NOT a valid retrieval metric here: the pipeline returns evidence chunks
    (~220 tokens) while gold answers are 1-5 tokens, so precision is capped at
    len(gold)/len(chunk) -- a perfect hit scores ~0.02. Kept only for
    comparability with earlier runs; use containment instead.
    """
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


def containment(unit: str, gold: str) -> float:
    """Fraction of distinct gold tokens present in the unit.

    Length-independent, so it measures the thing retrieval is actually
    responsible for: does the retrieved evidence actually contain the answer?
    Verified on LoCoMo-light: same runs score f1=0.013 vs containment=0.54.
    """
    g = set(norm(gold))
    if not g:
        return 0.0
    u = set(norm(unit))
    return sum(1 for w in g if w in u) / len(g)


def answer_text(response: dict) -> str:
    s = response.get("summary") or {}
    return s.get("answer", "") if isinstance(s, dict) else ""


def best_unit_f1(units: list, gold: str) -> float:
    """Max F1 of any single retrieved unit vs gold (see f1() for why this is
    only comparable across runs, not an absolute quality signal)."""
    best = 0.0
    for u in units:
        best = max(best, f1(u, gold))
    return best


def best_unit_containment(units: list, gold: str) -> float:
    """Max containment of any single retrieved unit vs gold.

    Primary quality metric: retrieval returns evidence, not a generated short
    answer, so "does the evidence contain the answer" is the meaningful
    question. Combined with evidence_hit (did we get the right session) this
    separates retrieval failure from metric artefact.
    """
    best = 0.0
    for u in units:
        best = max(best, containment(u, gold))
    return best


def evidence_sessions(q: dict) -> set:
    """Session numbers from evidence ids like D1:3 (session 1, turn 3)."""
    out = set()
    for ev in q.get("evidence") or []:
        m = re.match(r"D(\d+):", str(ev))
        if m:
            out.add(int(m.group(1)))
    return out


def session_of(meta: dict) -> object:
    """Session number from chunk metadata session_N, else None."""
    if not isinstance(meta, dict):
        return None
    m = re.match(r"session_(\d+)", str(meta.get("session", "")))
    return int(m.group(1)) if m else None


def item_text(item: dict) -> str:
    parts = [str(item.get("content") or ""), str(item.get("name") or ""),
             str(item.get("predicate") or "")]
    for edge in ("in", "out"):
        v = item.get(edge)
        if isinstance(v, dict):
            parts.append(str(v.get("name") or ""))
    return " ".join(p for p in parts if p)


async def main() -> int:
    ap = argparse.ArgumentParser(description="LoCoMo ablation spike")
    ap.add_argument("--data", required=True)
    ap.add_argument("--convos", type=int, default=2)
    ap.add_argument("--per-cat", type=int, default=12)
    ap.add_argument("--namespace", default="sieveon_locom")
    ap.add_argument("--database", default="sieveon_locom")
    ap.add_argument("--out", default="locomo_spike_results.json")
    ap.add_argument("--skip-ingest", action="store_true",
                    help="reuse events already in the namespace (no wipe, no ingest)")
    ap.add_argument("--arm-b", default="routed",
                    help="Arm B strategy: routed (default, full pipeline) or a pinned "
                    "strategy name (e.g. graph_ppr_rerank, decomposed_multihop, "
                    "hybrid_with_graph_expansion, semantic_hybrid)")
    args = ap.parse_args()

    from src.mcp import core as mcp_core
    from src.mcp.common_logic import _execute_query, _store_content

    mcp_core.SURREAL_NS = args.namespace
    mcp_core.SURREAL_DB = args.database
    # Load schema + helper functions DIRECTLY into this namespace (the loader
    # script targets the default NS; ensure_schema_loaded would too).
    for surql in ("docs/schema.surql", "docs/helper_functions.surql"):
        for stmt in mcp_core.load_schema_file(str(PROJ / surql)):
            if stmt.upper().lstrip().startswith("USE "):
                continue
            await mcp_core._query_surreal(stmt)
    print("schema ready", flush=True)
    if not args.skip_ingest:
        for tbl in ("fact", "event", "entity", "gate_log"):
            try:
                await mcp_core._query_surreal(f"DELETE {tbl};")
            except Exception:
                pass
        print("namespace wiped", flush=True)
    else:
        print("ingest skipped (--skip-ingest)", flush=True)

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
    from src.mcp.chunking import chunk_markdown

    t_ingest0 = time.perf_counter()
    if not args.skip_ingest:
        for ci, conv in enumerate(data):
            sessions = [
                (skey, sess) for skey, sess in conv["conversation"].items()
                if skey.startswith("session_") and isinstance(sess, list)
            ]
            for skey, sess in sessions:
                # Session-level episodes, chunked to gate limits (~1500 chars):
                # keeps QA evidence inside while cutting stores ~7x vs per-turn.
                date = conv["conversation"].get(f"{skey}_date_time", "")
                body = "\n".join(
                    f"{t.get('speaker', '?')}: {t.get('text', '')}" for t in sess
                )
                header = f"[{conv.get('sample_id')} {skey} {date}]"
                chunks = chunk_markdown(
                    body, chunk_size=1200, overlap=150,
                    include_heading_context=False,
                )["chunks"] or [{"text": body}]
                for chi, ch in enumerate(chunks):
                    content = ch["text"] if isinstance(ch, dict) else str(ch)
                    await _store_content(
                        f"{header}\n{content}", source="locomo",
                        metadata={"convo": conv.get("sample_id"), "session": skey,
                                  "date": date, "turns": len(sess), "chunk": chi},
                    )
                total_turns += len(sess)
            print(f"[{ts()}] ingested convo {conv.get('sample_id')}: {len(sessions)} sessions", flush=True)
    ingest_ms = (time.perf_counter() - t_ingest0) * 1000 if not args.skip_ingest else 0.0
    print(f"[{ts()}] total turns: {total_turns} ingest_ms={ingest_ms:.0f}", flush=True)

    from src.mcp.tools import event_log_search

    results = []
    for conv, picked in qa_sets:
        for q in picked:
            question = q["question"]
            gold = q.get("answer", "")
            cat = CAT_NAMES.get(q.get("category"), str(q.get("category")))
            # Arm A: pure hybrid BM25+vector, no KG
            t0 = time.perf_counter()
            try:
                a_res = await event_log_search(query=question, limit=5)
                a_events = a_res.get("events") or []
                a_units = [(e.get("content", "") or "") for e in a_events]
                a_f1 = best_unit_f1(a_units, gold)
                a_sess = {s for s in (session_of(e.get("metadata")) for e in a_events) if s is not None}
                a_cont = best_unit_containment(a_units, gold)
            except Exception as e:
                a_f1 = 0.0
                a_cont = 0.0
                a_sess = set()
                print(f"arm A error: {e}", flush=True)
            ms_a = (time.perf_counter() - t0) * 1000
            # Arm B: full routed pipeline, or a pinned strategy for A/B
            t0 = time.perf_counter()
            try:
                if args.arm_b == "routed":
                    b_res = await _execute_query(question)
                else:
                    from src.planner.executor import PlanExecutor
                    b_res = await PlanExecutor().execute_plan(
                        strategy=args.arm_b, query=question, budget_level="high"
                    )
                    # Normalize planner shape to the _execute_query shape
                    b_res = {
                        "strategy": b_res.get("strategy", args.arm_b),
                        "results": {
                            "events": b_res.get("events", []),
                            "entities": b_res.get("entities", []),
                            "facts": b_res.get("facts", []),
                        },
                    }
                res = b_res.get("results") or {}
                b_evs = res.get("events") or []
                b_units = []
                for grp in ("events", "entities", "facts"):
                    for it in (res.get(grp) or []):
                        if isinstance(it, dict):
                            b_units.append(item_text(it))
                b_f1 = best_unit_f1(b_units, gold)
                b_cont = best_unit_containment(b_units, gold)
                b_sess = {s for s in (session_of(e.get("metadata")) for e in b_evs) if s is not None}
            except Exception as e:
                b_f1 = 0.0
                b_cont = 0.0
                b_sess = set()
                print(f"arm B error: {e}", flush=True)
            ms_b = (time.perf_counter() - t0) * 1000
            ev_sess = evidence_sessions(q)
            results.append({
                "convo": conv.get("sample_id"), "category": cat,
                "question": question, "answer": gold,
                "f1_a": round(a_f1, 4),
                "f1_b": round(b_f1, 4),
                "containment_a": round(a_cont, 4),
                "containment_b": round(b_cont, 4),
                "ms_a": round(ms_a, 1),
                "ms_b": round(ms_b, 1),
                "hit_a": bool(ev_sess and (ev_sess & a_sess)),
                "hit_b": bool(ev_sess and (ev_sess & b_sess)),
                "strategy_b": (b_res.get("strategy") if "b_res" in dir() else None),
            })
            print(f"[{ts()}] [{cat:13s}] A: hit={int(bool(ev_sess and (ev_sess & a_sess)))} "
                  f"cont={a_cont:.2f}/{ms_a:.0f}ms  B: hit={int(bool(ev_sess and (ev_sess & b_sess)))} "
                  f"cont={b_cont:.2f}/{ms_b:.0f}ms :: {question[:52]}", flush=True)

    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)
    summary = {}
    for cat, rows in sorted(by_cat.items()):
        summary[cat] = {
            "n": len(rows),
            "mean_containment_a": round(sum(r["containment_a"] for r in rows) / len(rows), 4),
            "mean_containment_b": round(sum(r["containment_b"] for r in rows) / len(rows), 4),
            "mean_f1_a": round(sum(r["f1_a"] for r in rows) / len(rows), 4),
            "mean_f1_b": round(sum(r["f1_b"] for r in rows) / len(rows), 4),
            "mean_ms_a": round(sum(r["ms_a"] for r in rows) / len(rows), 1),
            "mean_ms_b": round(sum(r["ms_b"] for r in rows) / len(rows), 1),
            "evidence_hit_a": round(sum(1 for r in rows if r.get("hit_a")) / len(rows), 4),
            "evidence_hit_b": round(sum(1 for r in rows if r.get("hit_b")) / len(rows), 4),
        }
    summary["_overall"] = {
        "n": len(results),
        "mean_containment_a": round(sum(r["containment_a"] for r in results) / len(results), 4),
        "mean_containment_b": round(sum(r["containment_b"] for r in results) / len(results), 4),
        "mean_f1_a": round(sum(r["f1_a"] for r in results) / len(results), 4),
        "mean_f1_b": round(sum(r["f1_b"] for r in results) / len(results), 4),
        "mean_ms_a": round(sum(r["ms_a"] for r in results) / len(results), 1),
        "mean_ms_b": round(sum(r["ms_b"] for r in results) / len(results), 1),
        "evidence_hit_a": round(sum(1 for r in results if r.get("hit_a")) / len(results), 4),
        "evidence_hit_b": round(sum(1 for r in results if r.get("hit_b")) / len(results), 4),
        "ingest_ms": round(ingest_ms, 0),
    }
    print(json.dumps(summary, indent=1), flush=True)
    out = args.out if os.path.isabs(args.out) else os.path.join(os.getcwd(), args.out)
    json.dump({"summary": summary, "results": results}, open(out, "w", encoding="utf-8"), indent=2)
    print(f"saved to {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
