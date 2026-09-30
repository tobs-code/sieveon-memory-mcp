"""
Multi-dimensional Evaluation Harness
Measures the 5 key metrics from the paper, plus a salience diagnostic:

1. Retrieval Fidelity    — expected terms present (recall) AND absent terms
                           avoided; rank of first hit logged as diagnostic.
2. Update Robustness     — does a logical invalidation leave exactly one active
                           fact, with the new value and not the old one?
3. Long-Horizon Stability— is state still consistent after a long write sequence
                           (chain insert + churn), incl. 2-hop chain probes?
4. Latency               — end-to-end p50/p95 of fidelity queries against an SLO
                           (warmup/stability phases reported separately).
5. Operation Cost        — DB calls / tokens per query against the allocated budget.
6. Fact Salience         — diagnostic distribution of v1 fact salience;
                           unscored, feeds the composite-vs-salience decision.

Quality metrics (1-3) report a normalized `score` in [0, 1] (higher is
better); `overall_score` is their mean. Latency/cost gate via
`operational_pass` instead of flattering the mean.

Design notes:
  * The harness drives the real pipeline (`_execute_query`, `memory_update`) instead
    of re-implementing retrieval in SQL, so it measures what actually ships. The
    previous version carried its own copy of the queries and had already drifted
    from the executor.
  * It runs in an isolated namespace/database (default `sieveon_eval`) and seeds a
    deterministic corpus, so a run neither depends on nor pollutes user data.
  * Seeding writes events/entities/facts directly via SurrealQL. Extraction quality
    is not what these metrics measure, and the LLM extraction path is neither
    deterministic nor available offline.

Usage:
    python -m src.eval.eval_harness
    python src/eval/eval_harness.py --limit 4 --latency-slo-ms 2000
    python src/eval/eval_harness.py --keep        # keep the eval namespace
    python src/eval/eval_harness.py --namespace my_ns --database my_db
"""

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.extraction.entropy_gate import SALIENCE_VERSION, EntropyGate, escape_surrealql
from src.mcp import core as mcp_core
from src.mcp.common_logic import _execute_query
from src.mcp.core import _extract_result, _query_surreal
from src.mcp.tools import memory_update
from src.planner.executor import PlanExecutor
from src.router.cost_awareness import cost_tracker

SCHEMA_FILE = os.path.join(_PROJECT_ROOT, "docs", "schema.surql")

# Expected embedding dimension of the HNSW index (see docs/schema.surql).
EMBEDDING_DIM = 1024


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic eval corpus
# ─────────────────────────────────────────────────────────────────────────────

EVAL_ENTITIES: List[Tuple[str, str]] = [
    ("Acme Corp", "organization"),
    ("Nova Systems", "organization"),
    ("Helios Labs", "organization"),
    ("Atlas Freight", "organization"),
    ("QuantumDB", "technology"),
    ("Iris Chen", "person"),
    ("Marco Ruiz", "person"),
    ("Munich", "location"),
    ("Barcelona", "location"),
]

EVAL_FACTS: List[Tuple[str, str, str, float]] = [
    ("Acme Corp", "founded", "Munich", 1.0),
    ("Iris Chen", "leads", "Nova Systems", 1.0),
    ("Marco Ruiz", "works_at", "Acme Corp", 1.0),
    ("Nova Systems", "uses", "QuantumDB", 1.0),
    ("QuantumDB", "developed", "Helios Labs", 1.0),
    ("Helios Labs", "acquired", "Atlas Freight", 1.0),
    ("Atlas Freight", "located_in", "Barcelona", 1.0),
    ("Acme Corp", "invested_in", "Helios Labs", 0.9),
]

EVAL_EVENTS: List[str] = [
    "Acme Corp was founded in Munich by a group of engineers.",
    "Iris Chen leads Nova Systems as chief executive officer.",
    "Marco Ruiz works at Acme Corp on the retrieval pipeline.",
    "Nova Systems uses the QuantumDB database for its event pipeline.",
    "Helios Labs developed the QuantumDB engine in 2024.",
    "Helios Labs acquired Atlas Freight last quarter.",
    "Atlas Freight operates a logistics hub in Barcelona.",
    "Acme Corp invested in Helios Labs to expand its data platform.",
]


@dataclass
class EvalCase:
    """A retrieval probe with the terms a correct answer must contain."""

    query: str
    expected: List[str]
    category: str = "factual"
    note: str = ""
    since: Optional[str] = None
    until: Optional[str] = None
    at_time: Optional[str] = None
    absent: List[str] = field(default_factory=list)


# Temporal demo (B1 regression): fixed validity windows, independent of
# wall-clock seeding. at_time=2021 must resolve to Vienna, unpinned to Graz.
TEMPORAL_SUBJECT = "Temporal Corp"
TEMPORAL_PREDICATE = "headquartered_in"
TEMPORAL_OLD_VALUE = "Vienna"
TEMPORAL_NEW_VALUE = "Graz"
TEMPORAL_CUTOFF = "2024-01-01T00:00:00Z"
TEMPORAL_PAST = "2021-06-01T00:00:00Z"


RETRIEVAL_CASES: List[EvalCase] = [
    EvalCase("Where was Acme Corp founded?", ["Munich"]),
    EvalCase("Who leads Nova Systems?", ["Iris Chen", "Nova Systems"]),
    EvalCase("Who works at Acme Corp?", ["Marco Ruiz", "Acme Corp"]),
    EvalCase("What database does Nova Systems use?", ["QuantumDB", "Nova Systems"]),
    EvalCase("Which company developed QuantumDB?", ["Helios Labs", "QuantumDB"]),
    EvalCase("Which company acquired Atlas Freight?", ["Helios Labs", "Atlas Freight"]),
    EvalCase("Where does Atlas Freight operate a logistics hub?", ["Barcelona", "Atlas Freight"]),
    EvalCase("What did Acme Corp invest in?", ["Helios Labs", "invested"]),
    EvalCase(
        "What is the connection between Nova Systems and Atlas Freight?",
        ["QuantumDB", "Helios Labs"],
        category="multi-hop",
        note="two hops: Nova Systems -> QuantumDB -> Helios Labs -> Atlas Freight",
    ),
    EvalCase(
        "Which company developed the database used by Nova Systems?",
        ["Helios Labs", "QuantumDB", "Nova Systems"],
        category="multi-hop",
        note="B2 regression: needs BFS depth 2 (Nova -> QuantumDB -> Helios); 1-hop returns only QuantumDB",
    ),
    EvalCase(
        "Where is the logistics hub connected to Helios Labs?",
        ["Atlas Freight", "Barcelona"],
        category="multi-hop",
        note="B2 regression: Helios -> Atlas -> Barcelona, 2 hops via acquired/located_in",
    ),
    EvalCase(
        f"Where was {TEMPORAL_SUBJECT} headquartered?",
        [TEMPORAL_OLD_VALUE],
        category="temporal",
        note=f"B1 regression: at_time={TEMPORAL_PAST} must pin validity to Vienna (Graz is current)",
        at_time=TEMPORAL_PAST,
    ),
    EvalCase(
        f"Where is {TEMPORAL_SUBJECT} headquartered?",
        [TEMPORAL_NEW_VALUE],
        category="temporal",
        note="B1 regression: unpinned query must resolve to current value Graz, not superseded Vienna",
    ),
    EvalCase(
        "Which protocol was ratified by a committee?",
        ["Oldtown"],
        category="temporal",
        note="since/until regression: until=2021 must find only the 2020 Oldtown event",
        until="2021-01-01T00:00:00Z",
        absent=["Newtown"],
    ),
    EvalCase(
        "Which protocol was ratified by a committee?",
        ["Newtown"],
        category="temporal",
        note="since/until regression: since=2024 must find only the 2025 Newtown event",
        since="2024-01-01T00:00:00Z",
        absent=["Oldtown"],
    ),
]

# Dedicated subjects: they must not overlap with the corpus above, otherwise the
# invalidation cycles would rewrite facts that retrieval fidelity asserts on.
UPDATE_CASES: List[Tuple[str, str, str, str]] = [
    ("Evalon Dynamics", "headquartered_in", "Lisbon", "Porto"),
    ("Kestrel Freight", "operates_in", "Riga", "Tallinn"),
    ("Lumen Optics", "supplies", "Brightwater", "Clearfield"),
]

CHAIN_LENGTH = 8
CHAIN_PREFIX = "Horizon Node"
CHAIN_PREDICATE = "leads_to"

# The churn subject is deliberately separate from the retrieval chain: rewriting
# chain links would destroy exactly the structure the probes assert on.
CHURN_SUBJECT = "Churn Node 0"
CHURN_PREDICATE = "supersedes"
CHURN_UPDATES = 6


def _chain_node(i: int) -> str:
    return f"{CHAIN_PREFIX} {i}"


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _vector_literal(vector: List[float]) -> str:
    """Serialize an embedding as a SurrealQL array literal."""
    return "[" + ", ".join(repr(float(v)) for v in vector) + "]"


def _flatten_items(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collect the result items of a query response, whatever its shape."""
    results = response.get("results") if isinstance(response.get("results"), dict) else response
    items: List[Dict[str, Any]] = []
    for group in ("events", "entities", "facts"):
        for item in (results.get(group) or []):
            if isinstance(item, dict):
                items.append(item)
    return items


def _item_text(item: Dict[str, Any]) -> str:
    parts: List[str] = [
        str(item.get("content") or ""),
        str(item.get("name") or ""),
        str(item.get("predicate") or ""),
        str(item.get("in_name") or ""),
        str(item.get("out_name") or ""),
    ]
    for edge in ("in", "out"):
        value = item.get(edge)
        if isinstance(value, dict):
            parts.append(str(value.get("name") or ""))
            parts.append(str(value.get("type") or ""))
        elif isinstance(value, str):
            parts.append(value)
    return " ".join(parts).lower()


def _result_blob(response: Dict[str, Any]) -> str:
    """Flatten a query response into one lowercase haystack for term matching."""
    return " ".join(_item_text(i) for i in _flatten_items(response))


def _fact_subjects(response: Dict[str, Any], subject: str, predicate: str) -> List[str]:
    """Object names of the returned facts for one (subject, predicate) pair."""
    out: List[str] = []
    for item in _flatten_items(response):
        if str(item.get("predicate") or "") != predicate:
            continue
        in_edge = item.get("in")
        in_name = (
            in_edge.get("name") if isinstance(in_edge, dict) else item.get("in_name") or in_edge
        )
        if str(in_name or "") != subject:
            continue
        out_edge = item.get("out")
        out_name = (
            out_edge.get("name")
            if isinstance(out_edge, dict)
            else item.get("out_name") or out_edge
        )
        if out_name:
            out.append(str(out_name))
    return out


def _mean(values: List[float]) -> float:
    return round(statistics.fmean(values), 4) if values else 0.0


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * len(ordered) + 0.5)) - 1))
    return round(ordered[idx], 2)


# ─────────────────────────────────────────────────────────────────────────────
# Harness
# ─────────────────────────────────────────────────────────────────────────────


# Two windowed events with fixed timestamps for since/until regression.
# Contents use distinctive terms (Oldtown vs Newtown) so the time filter --
# not term matching -- decides what is found.
WINDOW_OLD_TS = "2020-06-01T00:00:00Z"
WINDOW_NEW_TS = "2025-06-01T00:00:00Z"
WINDOW_OLD_TEXT = "Archive note: the Oldtown protocol was ratified by the harbor committee."
WINDOW_NEW_TEXT = "Fresh note: the Newtown protocol was ratified by the airport committee."


class SieveonEvalHarness:
    def __init__(
        self,
        namespace: Optional[str] = None,
        database: Optional[str] = None,
        latency_slo_ms: float = 1500.0,
        verbose: bool = True,
    ):
        self.namespace = namespace or os.getenv("SURREAL_EVAL_NS", "sieveon_eval")
        self.database = database or os.getenv("SURREAL_EVAL_DB", "sieveon_eval")
        self.latency_slo_ms = latency_slo_ms
        self.verbose = verbose

        # Point the shared core module at the eval namespace. SURREAL_NS/SURREAL_DB
        # are read as module globals on every call, so this redirects the whole
        # stack (executor, tools, common_logic) without touching their imports.
        mcp_core.SURREAL_NS = self.namespace
        mcp_core.SURREAL_DB = self.database

        self.metrics: Dict[str, float] = {}
        self._latencies_ms: List[Tuple[str, float]] = []
        self._budget_samples: List[Dict[str, Any]] = []
        self._failures: List[str] = []

    # ── infrastructure ────────────────────────────────────────────────

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message, flush=True)

    async def _sql(self, sql: str) -> List[Dict[str, Any]]:
        return _extract_result(await _query_surreal(sql), 1) or []

    async def _scalar(self, sql: str, key: str = "c") -> float:
        rows = await self._sql(f"SELECT count() AS {key} FROM ({sql}) GROUP ALL;")
        return float(rows[0].get(key, 0)) if rows else 0.0

    async def _ensure_schema(self) -> None:
        statements = [
            s
            for s in mcp_core.load_schema_file(SCHEMA_FILE)
            if not s.upper().lstrip().startswith("USE ")
        ]
        for stmt in statements:
            await _query_surreal(stmt)
        self._log(f"   schema ready ({len(statements)} statements)")

    async def _teardown(self) -> None:
        for table in ("event", "entity", "fact", "gate_log"):
            try:
                await _query_surreal(f"DELETE {table};")
            except Exception as exc:  # cleanup is best effort
                self._log(f"   [WARN] cleanup of '{table}' failed: {exc}")

    # ── seeding ───────────────────────────────────────────────────────

    async def _embed(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Embed the corpus so the vector retrieval channel is actually exercised."""
        try:
            from src.extraction.embedding_service import get_embedding_service

            vectors = get_embedding_service().embed_batch(texts, for_storage=True)
        except Exception as exc:
            self._log(f"   [WARN] embeddings unavailable ({exc}); vector channel skipped")
            return None
        if not vectors or len(vectors[0]) != EMBEDDING_DIM:
            dim = len(vectors[0]) if vectors else "?"
            self._log(
                f"   [WARN] embedding dim {dim} != index dim {EMBEDDING_DIM}; "
                "vector channel skipped"
            )
            return None
        return vectors

    async def _seed(self) -> Dict[str, Any]:
        self._log(f"   seeding {self.namespace}/{self.database}")
        await self._ensure_schema()
        await self._teardown()

        entity_ids: Dict[str, str] = {}
        for name, etype in EVAL_ENTITIES:
            rows = await self._sql(
                "CREATE entity SET "
                f"name = '{escape_surrealql(name)}', type = '{escape_surrealql(etype)}', "
                "forgotten = false, created_at = time::now(), updated_at = time::now() "
                "RETURN id;"
            )
            if rows:
                entity_ids[name] = rows[0]["id"]

        for subject, predicate, obj, confidence in EVAL_FACTS:
            if subject in entity_ids and obj in entity_ids:
                # Seed salience too (pure function): keeps the salience
                # diagnostic meaningful on the seeded corpus.
                sal = EntropyGate.fact_salience(confidence, predicate, None)
                await _query_surreal(
                    f"RELATE {entity_ids[subject]}->fact->{entity_ids[obj]} SET "
                    f"predicate = '{escape_surrealql(predicate)}', confidence = {confidence}, "
                    f"salience = {sal:.4f}, salience_version = '{SALIENCE_VERSION}';"
                )

        vectors = await self._embed(EVAL_EVENTS)
        for idx, content in enumerate(EVAL_EVENTS):
            emb = ""
            if vectors:
                emb = f", embedding = {_vector_literal(vectors[idx])}"
            await _query_surreal(
                "CREATE event SET "
                f"content = '{escape_surrealql(content)}', "
                f"content_hash = '{_content_hash(content)}', "
                "source = 'eval', forgotten = false, timestamp = time::now()"
                f"{emb};"
            )

        chain_links = await self._seed_chain()
        temporal = await self._seed_temporal()
        windowed = await self._seed_window_events()
        return {
            "entities": len(entity_ids),
            "facts": len(EVAL_FACTS),
            "events": len(EVAL_EVENTS),
            "chain_links": chain_links,
            "temporal": temporal,
            "windowed_events": windowed,
            "vector_channel": bool(vectors),
        }
    async def _seed_temporal(self) -> Dict[str, Any]:
        """Seed fixed-window validity demo (B1): Vienna valid until cutoff, Graz since cutoff."""
        ids: Dict[str, str] = {}
        for name, etype in [
            (TEMPORAL_SUBJECT, "organization"),
            (TEMPORAL_OLD_VALUE, "location"),
            (TEMPORAL_NEW_VALUE, "location"),
        ]:
            rows = await self._sql(
                "CREATE entity SET "
                f"name = '{escape_surrealql(name)}', type = '{escape_surrealql(etype)}', "
                "forgotten = false, created_at = time::now(), updated_at = time::now() "
                "RETURN id;"
            )
            if rows:
                ids[name] = rows[0]["id"]
        if len(ids) != 3:
            return {"seeded": False}
        subj, old, new = ids[TEMPORAL_SUBJECT], ids[TEMPORAL_OLD_VALUE], ids[TEMPORAL_NEW_VALUE]
        sal = EntropyGate.fact_salience(1.0, TEMPORAL_PREDICATE, None)
        await _query_surreal(
            f"RELATE {subj}->fact->{old} SET "
            f"predicate = '{escape_surrealql(TEMPORAL_PREDICATE)}', confidence = 1.0, "
            f"salience = {sal:.4f}, salience_version = '{SALIENCE_VERSION}', "
            f'valid_from = type::datetime("2020-01-01T00:00:00Z"), valid_until = type::datetime("{TEMPORAL_CUTOFF}");'
        )
        await _query_surreal(
            f"RELATE {subj}->fact->{new} SET "
            f"predicate = '{escape_surrealql(TEMPORAL_PREDICATE)}', confidence = 1.0, "
            f"salience = {sal:.4f}, salience_version = '{SALIENCE_VERSION}', "
            f'valid_from = type::datetime("{TEMPORAL_CUTOFF}");'
        )
        return {"seeded": True, "subject": TEMPORAL_SUBJECT, "cutoff": TEMPORAL_CUTOFF}

    async def _seed_window_events(self) -> Dict[str, Any]:
        """Seed Oldtown (2020) + Newtown (2025) events for since/until tests."""
        vectors = await self._embed([WINDOW_OLD_TEXT, WINDOW_NEW_TEXT])
        seeded = 0
        for idx, (text, ts) in enumerate(
            [(WINDOW_OLD_TEXT, WINDOW_OLD_TS), (WINDOW_NEW_TEXT, WINDOW_NEW_TS)]
        ):
            emb = ""
            if vectors:
                emb = f", embedding = {_vector_literal(vectors[idx])}"
            await _query_surreal(
                "CREATE event SET "
                f"content = '{escape_surrealql(text)}', "
                f"content_hash = '{_content_hash(text)}', "
                "source = 'eval-window', forgotten = false, "
                f'timestamp = type::datetime("{ts}")'
                f"{emb};"
            )
            seeded += 1
        return {"seeded": seeded}

    async def _seed_chain(self) -> int:
        """Seed the retrieval chain plus the (still empty) churn subject."""
        ids: List[str] = []
        names = [_chain_node(i) for i in range(CHAIN_LENGTH)] + [CHURN_SUBJECT]
        for name in names:
            rows = await self._sql(
                "CREATE entity SET "
                f"name = '{escape_surrealql(name)}', type = 'concept', "
                "forgotten = false, created_at = time::now(), updated_at = time::now() "
                "RETURN id;"
            )
            if rows:
                ids.append(rows[0]["id"])
        for i in range(CHAIN_LENGTH - 1):
            sal = EntropyGate.fact_salience(1.0, CHAIN_PREDICATE, None)
            await _query_surreal(
                f"RELATE {ids[i]}->fact->{ids[i + 1]} SET "
                f"predicate = '{CHAIN_PREDICATE}', confidence = 1.0, "
                f"salience = {sal:.4f}, salience_version = '{SALIENCE_VERSION}';"
            )
        return max(0, CHAIN_LENGTH - 1)

    # ── query driver ──────────────────────────────────────────────────

    async def _run_query(
        self,
        query: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        at_time: Optional[str] = None,
        phase: str = "retrieval",
    ) -> Tuple[Dict[str, Any], float]:
        """Run one query through the real pipeline, recording latency and cost.

        phase tags the sample ("retrieval" for fidelity cases, "stability"
        for long-horizon probes) so latency/cost metrics can slice cleanly
        instead of assuming the last N samples belong to fidelity.
        """
        start = time.perf_counter()
        response = await _execute_query(query, since=since, until=until, at_time=at_time)
        latency_ms = (time.perf_counter() - start) * 1000.0

        self._latencies_ms.append((phase, latency_ms))
        budget = response.get("budget") or {}
        self._budget_samples.append(
            {
                "query": query,
                "phase": phase,
                "latency_ms": round(latency_ms, 2),
                "strategy": response.get("strategy"),
                "level": budget.get("level"),
                "db_calls": budget.get("db_calls", 0),
                "estimated_tokens": budget.get("estimated_tokens", 0),
                "over_budget": bool(budget.get("over_budget")),
                "error": response.get("error"),
            }
        )
        if response.get("error"):
            self._failures.append(f"query error for '{query}': {response['error']}")
        return response, latency_ms

    async def _probe_pinned(self, query: str, strategy: str = "semantic_hybrid") -> Dict[str, Any]:
        """Run a verification probe with a fixed strategy.

        The adaptive router picks a different strategy as cost_tracker learns, so
        a check that depends on the routed strategy is not reproducible run to
        run. Verification probes therefore go through the planner entry point
        with a pinned strategy and are excluded from the latency/cost samples.
        """
        return await PlanExecutor().execute_plan(
            strategy=strategy, query=query, budget_level="high"
        )

    # ── metric 1: retrieval fidelity ──────────────────────────────────

    async def measure_retrieval_fidelity(self, cases: List[EvalCase]) -> Dict[str, Any]:
        self._log("  [1/6] retrieval fidelity")
        details = []
        recalls: List[float] = []

        for case in cases:
            response, _ = await self._run_query(
                case.query, since=case.since, until=case.until, at_time=case.at_time
            )
            blob = _result_blob(response)
            items = _flatten_items(response)
            found = [term for term in case.expected if term.lower() in blob]
            missing = [term for term in case.expected if term.lower() not in blob]
            recall = len(found) / len(case.expected) if case.expected else 0.0
            # Negative assertions: terms that must NOT appear (superseded values,
            # out-of-window events). Substring matching, same as expected.
            present_absent = [term for term in case.absent if term.lower() in blob]
            absent_score = (
                1.0 - len(present_absent) / len(case.absent) if case.absent else 1.0
            )
            case_score = round((recall + absent_score) / 2, 4) if case.absent else round(recall, 4)
            recalls.append(case_score)
            # Rank diagnostic (not scored): index of the first flattened item
            # containing any expected term. Lower is better.
            first_hit_at: Optional[int] = None
            for idx, item in enumerate(items):
                if any(term.lower() in _item_text(item) for term in case.expected):
                    first_hit_at = idx
                    break
            details.append(
                {
                    "query": case.query,
                    "category": case.category,
                    "strategy": response.get("strategy"),
                    "classified_as": response.get("classified_as"),
                    "relevance_score": (response.get("ranking") or {}).get("relevance_score"),
                    "expected": case.expected,
                    "found": found,
                    "missing": missing,
                    "recall": round(recall, 4),
                    "absent": case.absent,
                    "absent_violations": present_absent,
                    "absent_score": round(absent_score, 4),
                    "score": case_score,
                    "first_hit_at": first_hit_at,
                }
            )
            flag = "OK  " if not missing and not present_absent else "MISS"
            self._log(
                f"    {flag} [{case.category}] {case.query}"
                f" -> found={found or '[]'}{' missing=' + str(missing) if missing else ''}"
                f"{' absent_violation=' + str(present_absent) if present_absent else ''}"
                f"{' rank=' + str(first_hit_at) if first_hit_at is not None else ''}"
            )

        hit_rate = _mean(
            [1.0 if d["missing"] == [] and d["absent_violations"] == [] else 0.0 for d in details]
        )
        score = _mean(recalls)
        by_category: Dict[str, float] = {}
        for cat in sorted({d["category"] for d in details}):
            by_category[cat] = _mean([d["score"] for d in details if d["category"] == cat])

        return {
            "score": score,
            "definition": "mean case score: expected-term recall, averaged with "
            "absent-term avoidance where absent terms are defined "
            "(substring matching; first_hit_at is diagnostic only)",
            "hit_rate": hit_rate,
            "cases": len(details),
            "by_category": by_category,
            "details": details,
        }

    # ── metric 2: update robustness ───────────────────────────────────

    async def measure_update_robustness(
        self, cases: List[Tuple[str, str, str, str]]
    ) -> Dict[str, Any]:
        self._log("  [2/6] update robustness")
        details = []

        for subject, predicate, old_value, new_value in cases:
            # Establish the baseline, then supersede it: after the cycle exactly
            # one active fact must remain, pointing at the new value.
            await memory_update(subject, predicate, old_value)
            result = await memory_update(subject, predicate, new_value)

            active = await self._sql(
                "SELECT out.name AS out_name, valid_until FROM fact "
                f"WHERE in.name = '{escape_surrealql(subject)}' "
                f"AND predicate = '{escape_surrealql(predicate)}' "
                "AND (valid_until IS NONE OR valid_until = NONE);"
            )
            invalidated = await self._sql(
                "SELECT out.name AS out_name FROM fact "
                f"WHERE in.name = '{escape_surrealql(subject)}' "
                f"AND predicate = '{escape_surrealql(predicate)}' "
                "AND valid_until != NONE;"
            )
            probe = await self._probe_pinned(f"Where is {subject} {predicate}?")
            returned_objects = _fact_subjects(probe, subject, predicate)

            single_active = len(active) == 1
            points_at_new = bool(active) and active[0].get("out_name") == new_value
            old_invalidated = old_value in {f.get("out_name") for f in invalidated}
            new_retrievable = new_value in returned_objects
            # A superseded value must not be served as a current fact. All KG
            # read paths filter on the validity window (ACTIVE_FACT_FILTER),
            # so this is the check that catches read-side invalidation gaps.
            old_absent = old_value not in returned_objects

            passed = (
                single_active
                and points_at_new
                and old_invalidated
                and new_retrievable
                and old_absent
            )
            details.append(
                {
                    "subject": subject,
                    "predicate": predicate,
                    "old_value": old_value,
                    "new_value": new_value,
                    "active_fact_count": len(active),
                    "invalidated_count": len(invalidated),
                    "invalidated_fact": result.get("invalidated_fact"),
                    "returned_objects": returned_objects,
                    "single_active_fact": single_active,
                    "points_at_new_value": points_at_new,
                    "old_value_invalidated": old_invalidated,
                    "new_value_retrievable": new_retrievable,
                    "old_value_absent": old_absent,
                    "passed": passed,
                }
            )
            self._log(
                f"    {'OK  ' if passed else 'FAIL'} {subject} {predicate}: "
                f"{old_value} -> {new_value} (active={len(active)}, "
                f"invalidated={len(invalidated)}, returned={returned_objects})"
            )

        return {
            "score": _mean([1.0 if d["passed"] else 0.0 for d in details]),
            "definition": "share of update cycles leaving exactly one active fact "
            "with the new value, the old value invalidated, and a probe that "
            "returns the new value but not the superseded one",
            "probe_strategy": "semantic_hybrid",
            "cycles": len(details),
            "details": details,
        }

    # ── metric 3: long-horizon stability ──────────────────────────────

    async def measure_long_horizon_stability(self) -> Dict[str, Any]:
        self._log("  [3/6] long-horizon stability")

        # Baseline retrieval over the seeded chain. The executor expands two
        # hops (bounded BFS) from the entities named in the query, so the
        # 2-hop neighbourhood is the honest expectation.
        probes = [
            (_chain_node(0), _chain_node(3), [_chain_node(1), _chain_node(2)]),
            (_chain_node(0), _chain_node(4), [_chain_node(1), _chain_node(2), _chain_node(3)]),
            (_chain_node(5), _chain_node(6), [_chain_node(6)]),
        ]
        probe_details = []
        for src, dst, expected in probes:
            query = f"What is the connection between {src} and {dst}?"
            response, _ = await self._run_query(query, phase="stability")
            blob = _result_blob(response)
            found = [t for t in expected if t.lower() in blob]
            probe_details.append(
                {
                    "query": query,
                    "expected": expected,
                    "found": found,
                    "missing": [t for t in expected if t.lower() not in blob],
                    "hit": len(found) == len(expected),
                }
            )
            self._log(
                f"    {'OK  ' if probe_details[-1]['hit'] else 'MISS'} {query} -> {found or '[]'}"
            )
        probe_score = _mean([1.0 if p["hit"] else 0.0 for p in probe_details])

        # Churn: supersede the same subject CHURN_UPDATES times. The chain above
        # is untouched, so the probe result stays comparable across the churn.
        last_target = ""
        for i in range(CHURN_UPDATES):
            last_target = f"Waypoint {i}"
            await memory_update(CHURN_SUBJECT, CHURN_PREDICATE, last_target)

        # Invariants that must hold after the whole write sequence. The duplicate
        # check runs in Python: SurrealQL cannot GROUP BY an edge field without
        # escaping `in`, and a parse error there would take the whole run down.
        try:
            all_active = await self._sql(
                "SELECT in.name AS in_name, out.name AS out_name, predicate FROM fact "
                "WHERE valid_until IS NONE OR valid_until = NONE;"
            )
            chain_active = await self._scalar(
                "SELECT * FROM fact "
                "WHERE (valid_until IS NONE OR valid_until = NONE) "
                # SurrealDB 3 has no LIKE: CONTAINS is the supported form.
                f"AND in.name CONTAINS '{CHAIN_PREFIX}' "
                f"AND predicate = '{CHAIN_PREDICATE}'"
            )
            churn_invalidated = await self._scalar(
                f"SELECT * FROM fact WHERE valid_until != NONE "
                f"AND in.name = '{escape_surrealql(CHURN_SUBJECT)}'"
            )
            churn_active = await self._sql(
                "SELECT out.name AS out_name FROM fact "
                f"WHERE in.name = '{escape_surrealql(CHURN_SUBJECT)}' "
                "AND (valid_until IS NONE OR valid_until = NONE);"
            )
        except Exception as exc:
            self._log(f"   [ERROR] invariant query failed: {exc}")
            return {
                "score": 0.0,
                "definition": "0.5 * chain retrieval hit rate + 0.5 * share of state "
                "invariants holding after insert + churn",
                "error": f"{type(exc).__name__}: {exc}",
                "chain_length": CHAIN_LENGTH,
                "churn_updates": CHURN_UPDATES,
                "probe_score": probe_score,
                "probes": probe_details,
            }

        seen_keys: Dict[Tuple[str, str], int] = {}
        for row in all_active:
            key = (str(row.get("in_name")), str(row.get("predicate")))
            seen_keys[key] = seen_keys.get(key, 0) + 1
        duplicate_active = {f"{k[0]}|{k[1]}": v for k, v in seen_keys.items() if v > 1}
        dangling_active = [r for r in all_active if not r.get("out_name")]

        # N sequential upserts on one subject produce N facts: the first has
        # nothing to supersede, so N-1 end up invalidated and the last stays active.
        expected_churn_invalidated = CHURN_UPDATES - 1

        checks = {
            "no_duplicate_active_facts": not duplicate_active,
            "no_dangling_active_facts": not dangling_active,
            "chain_intact_after_churn": chain_active == CHAIN_LENGTH - 1,
            "churn_invalidated_count": churn_invalidated == expected_churn_invalidated,
            "churn_single_active_fact": len(churn_active) == 1,
            "churn_points_at_latest": bool(churn_active)
            and churn_active[0].get("out_name") == last_target,
        }
        for name, ok in checks.items():
            self._log(f"    {'OK  ' if ok else 'FAIL'} invariant: {name}")

        invariant_score = _mean([1.0 if ok else 0.0 for ok in checks.values()])

        return {
            "score": round(0.5 * probe_score + 0.5 * invariant_score, 4),
            "definition": "0.5 * chain retrieval hit rate + 0.5 * share of state "
            "invariants holding after insert + churn",
            "chain_length": CHAIN_LENGTH,
            "churn_updates": CHURN_UPDATES,
            "churn_subject": CHURN_SUBJECT,
            "churn_latest_target": last_target,
            "probe_score": probe_score,
            "invariant_score": invariant_score,
            "invariants": checks,
            "active_chain_facts": chain_active,
            "expected_active_chain_facts": CHAIN_LENGTH - 1,
            "invalidated_churn_facts": churn_invalidated,
            "expected_invalidated_churn_facts": expected_churn_invalidated,
            "duplicate_active_facts": duplicate_active,
            "dangling_active_facts": dangling_active,
            "probes": probe_details,
        }

    # ── metric 4: latency ─────────────────────────────────────────────

    async def measure_latency(self, cases: List[EvalCase]) -> Dict[str, Any]:
        self._log("  [4/6] latency")
        # Only fidelity-phase samples count toward the SLO score; the warmup
        # query (phase "warmup") and stability probes are reported separately.
        # Previously this sliced samples[-len(cases):], silently mixing in
        # long-horizon probes.
        retrieval = [ms for phase, ms in (self._latencies_ms or []) if phase == "retrieval"]
        other = {phase: [ms for ph, ms in (self._latencies_ms or []) if ph == phase] for phase in ("warmup", "stability")}
        if not retrieval:
            return {
                "score": 0.0,
                "definition": f"share of fidelity queries completing under {self.latency_slo_ms}ms",
                "samples": 0,
            }

        probe_samples = retrieval
        under_slo = [1.0 if s <= self.latency_slo_ms else 0.0 for s in probe_samples]
        by_strategy: Dict[str, List[float]] = {}
        for sample in self._budget_samples:
            if sample.get("phase", "retrieval") != "retrieval":
                continue
            by_strategy.setdefault(sample["strategy"] or "unknown", []).append(
                sample["latency_ms"]
            )

        return {
            "score": _mean(under_slo),
            "definition": f"share of fidelity queries completing under {self.latency_slo_ms}ms",
            "slo_ms": self.latency_slo_ms,
            "samples": len(probe_samples),
            "mean_ms": round(statistics.fmean(probe_samples), 2),
            "p50_ms": _percentile(probe_samples, 50),
            "p95_ms": _percentile(probe_samples, 95),
            "max_ms": round(max(probe_samples), 2),
            "by_strategy_mean_ms": {
                k: round(statistics.fmean(v), 2) for k, v in sorted(by_strategy.items())
            },
            "other_phases_mean_ms": {
                phase: round(statistics.fmean(vals), 2) for phase, vals in sorted(other.items()) if vals
            },
        }

    # ── metric 5: operation cost ──────────────────────────────────────

    async def measure_operation_cost(self) -> Dict[str, Any]:
        self._log("  [5/6] operation cost")
        samples = self._budget_samples or []
        if not samples:
            return {"score": 0.0, "definition": "share of queries staying within budget", "samples": 0}

        db_calls = [float(s["db_calls"]) for s in samples]
        tokens = [float(s["estimated_tokens"]) for s in samples]
        strategy_costs = cost_tracker.get_all_costs()

        return {
            "score": _mean([0.0 if s["over_budget"] else 1.0 for s in samples]),
            "definition": "share of queries staying within the allocated budget",
            "samples": len(samples),
            "mean_db_calls": round(statistics.fmean(db_calls), 2),
            "max_db_calls": max(db_calls),
            "mean_estimated_tokens": round(statistics.fmean(tokens), 2),
            "budget_levels": sorted({str(s["level"]) for s in samples}),
            "over_budget_queries": sum(1 for s in samples if s["over_budget"]),
            "failed_queries": sum(1 for s in samples if s["error"]),
            "strategy_metrics": strategy_costs,
        }

    # ── metric 6: fact salience distribution (diagnostic, unscored) ──

    async def measure_salience(self) -> Dict[str, Any]:
        """Histogram over per-fact salience (v1-heuristic) in the eval corpus.

        Diagnostic only: feeds the composite-vs-salience switchover decision.
        Compares avg fact salience against avg gate composite on extract rows.
        """
        self._log("  [6/6] fact salience (diagnostic)")
        facts = await self._sql(
            "SELECT predicate, confidence, salience FROM fact "
            "WHERE valid_until IS NONE OR valid_until = NONE LIMIT 500;"
        )
        scored = [f for f in facts if isinstance(f.get("salience"), (int, float))]
        buckets = {"<0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, ">=0.8": 0}
        for f in scored:
            s = float(f["salience"])
            buckets["<0.4" if s < 0.4 else "0.4-0.6" if s < 0.6 else "0.6-0.8" if s < 0.8 else ">=0.8"] += 1
        by_predicate: Dict[str, float] = {}
        for pred in sorted({str(f.get("predicate")) for f in scored}):
            vals = [float(f["salience"]) for f in scored if str(f.get("predicate")) == pred]
            by_predicate[pred] = round(statistics.fmean(vals), 4)
        gate = await self._sql(
            "SELECT gate_score, salience FROM gate_log WHERE decision = 'extract' LIMIT 500;"
        )
        pairs = [
            (float(g["gate_score"]), float(g["salience"]))
            for g in gate
            if isinstance(g.get("gate_score"), (int, float))
            and isinstance(g.get("salience"), (int, float))
        ]
        return {
            "score": None,
            "definition": "diagnostic distribution of v1 fact salience; unscored, "
            "does not affect overall_score",
            "facts_scored": len(scored),
            "facts_total": len(facts),
            "mean_salience": round(statistics.fmean([float(f["salience"]) for f in scored]), 4) if scored else 0.0,
            "histogram": buckets,
            "by_predicate": by_predicate,
            "composite_vs_salience_pairs": len(pairs),
            "mean_composite_on_extract": round(statistics.fmean([p[0] for p in pairs]), 4) if pairs else 0.0,
            "mean_salience_on_extract": round(statistics.fmean([p[1] for p in pairs]), 4) if pairs else 0.0,
        }

    # ── orchestration ─────────────────────────────────────────────────

    async def evaluate(
        self,
        test_cases: Optional[List[EvalCase]] = None,
        update_cases: Optional[List[Tuple[str, str, str, str]]] = None,
        keep_data: bool = False,
    ) -> Dict[str, Any]:
        cases = list(test_cases if test_cases is not None else RETRIEVAL_CASES)
        updates = list(update_cases if update_cases is not None else UPDATE_CASES)

        self._log(f"Running sieveon Evaluation Harness on {self.namespace}/{self.database}")
        # Cost metrics are only attributable to this run.
        cost_tracker.reset_metrics()
        self._latencies_ms = []
        self._budget_samples = []
        self._failures = []

        seeded = await self._seed()
        self._log(
            f"   corpus: {seeded['events']} events, {seeded['facts']} facts, "
            f"{seeded['entities']} entities, {seeded['chain_links']} chain links, "
            f"vector_channel={seeded['vector_channel']}"
        )

        try:
            # One warmup so the first measured query is not the cold one.
            # Phase "warmup" keeps it out of the latency SLO score.
            await self._run_query("warmup query for analyzer and index state", phase="warmup")

            results: Dict[str, Any] = {
                "timestamp": datetime.now().isoformat(),
                "namespace": self.namespace,
                "database": self.database,
                "corpus": seeded,
                "metrics": {},
                "overall_score": 0.0,
                "failures": self._failures,
            }
            results["metrics"]["retrieval_fidelity"] = (
                await self.measure_retrieval_fidelity(cases)
            )
            results["metrics"]["update_robustness"] = await self.measure_update_robustness(
                updates
            )
            results["metrics"]["long_horizon_stability"] = (
                await self.measure_long_horizon_stability()
            )
            results["metrics"]["latency"] = await self.measure_latency(cases)
            results["metrics"]["operation_cost"] = await self.measure_operation_cost()
            results["metrics"]["fact_salience"] = await self.measure_salience()

            # Overall = mean over quality metrics only (fidelity, update
            # robustness, stability). Latency/cost are near-constant 1.0 and
            # would flatter the score; they gate via operational_pass instead.
            quality = [
                results["metrics"][m].get("score", 0.0)
                for m in ("retrieval_fidelity", "update_robustness", "long_horizon_stability")
            ]
            results["overall_score"] = round(statistics.fmean(quality), 4) if quality else 0.0
            results["operational_pass"] = bool(
                results["metrics"]["latency"].get("score", 0.0) >= 1.0
                and results["metrics"]["operation_cost"].get("score", 0.0) >= 1.0
            )
            self.metrics = {k: v.get("score", 0.0) for k, v in results["metrics"].items() if v.get("score") is not None}
            return results
        finally:
            if not keep_data:
                self._log("   cleaning up eval namespace")
                await self._teardown()

    def print_summary(self, results: Dict[str, Any]) -> None:
        print("\n" + "=" * 62)
        print("sieveon EVALUATION RESULTS")
        print("=" * 62)
        print(
            f"namespace: {results.get('namespace')}/{results.get('database')}   "
            f"corpus: {results.get('corpus')}"
        )

        for metric, data in results.get("metrics", {}).items():
            print(f"\n{metric.upper()}")
            print(f"  score: {data.get('score', 'N/A') if data.get('score') is not None else 'N/A (diagnostic)'}")
            for key, value in data.items():
                if key in ("score", "definition", "details", "probes", "strategy_metrics"):
                    continue
                if isinstance(value, (dict, list)):
                    print(f"  {key}: {json.dumps(value, default=str)}")
                else:
                    print(f"  {key}: {value}")
            if data.get("definition"):
                print(f"  definition: {data['definition']}")

        failures = results.get("failures") or []
        if failures:
            print(f"\nFAILURES ({len(failures)}):")
            for failure in failures:
                print(f"  - {failure}")

        print(f"\nOVERALL SCORE (quality mean): {results.get('overall_score', 0.0):.3f}")
        print(f"OPERATIONAL PASS (latency+cost): {results.get('operational_pass', False)}")
        print("=" * 62)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="sieveon evaluation harness")
    parser.add_argument("--namespace", default=None, help="eval namespace (default sieveon_eval)")
    parser.add_argument("--database", default=None, help="eval database (default sieveon_eval)")
    parser.add_argument(
        "--limit", type=int, default=0, help="only run the first N retrieval cases"
    )
    parser.add_argument(
        "--latency-slo-ms", type=float, default=1500.0, help="latency SLO in milliseconds"
    )
    parser.add_argument("--keep", action="store_true", help="keep the eval data afterwards")
    parser.add_argument("--quiet", action="store_true", help="only print the summary")
    parser.add_argument(
        "--output", default="sieveon_eval_results.json", help="path for the JSON report"
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)

    cases = RETRIEVAL_CASES
    if args.limit and args.limit > 0:
        cases = RETRIEVAL_CASES[: args.limit]

    harness = SieveonEvalHarness(
        namespace=args.namespace,
        database=args.database,
        latency_slo_ms=args.latency_slo_ms,
        verbose=not args.quiet,
    )

    try:
        results = asyncio.run(harness.evaluate(test_cases=cases, keep_data=args.keep))
    except Exception as exc:
        print(f"[ERROR] evaluation failed: {type(exc).__name__}: {exc}")
        return 1

    harness.print_summary(results)

    out_path = args.output
    if not os.path.isabs(out_path):
        out_path = os.path.join(os.getcwd(), out_path)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, default=str)
    print(f"\nResults saved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
