# -*- coding: utf-8 -*-
"""
Core infrastructure for the Sieveon Memory Control Plane
Handles connection management, resilience patterns, and basic utilities
"""

import asyncio
import json
import logging
import os
import random
import re
import sys
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple

import httpx

# Standard imports
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Our components
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mcp.server.fastmcp import FastMCP
from src.extraction.entropy_gate import escape_surrealql
from src.router.cost_awareness import CostTracker
from src.router.budget import BudgetTracker

# Shared CostTracker – wird von RoutingPolicy automatisch gefüttert
cost_tracker = CostTracker()

log = logging.getLogger(__name__)

# Initialize FastMCP (Model Context Protocol) and FastAPI apps
mcp = FastMCP("sieveon")  # Model Context Protocol implementation


# ── MCP Resources ──────────────────────────────────────────────────────
@mcp.resource("sieveon://stats", description="Memory system statistics")
async def get_stats_resource() -> str:
    """Aggregate statistics about the memory system."""
    stats = {}
    try:
        f = "forgotten = false"

        async def _q(sql):
            return _extract_result(await _query_surreal(sql), 1) or []

        task1 = asyncio.create_task(_q(f"SELECT count() FROM event WHERE {f} GROUP ALL;"))
        task2 = asyncio.create_task(_q(f"SELECT count() FROM entity WHERE {f} GROUP ALL;"))
        task3 = asyncio.create_task(_q("SELECT count() FROM fact WHERE (valid_until IS NONE OR valid_until = NONE) GROUP ALL;"))
        task4 = asyncio.create_task(_q(f"SELECT timestamp FROM event WHERE {f} ORDER BY timestamp ASC LIMIT 1;"))
        task5 = asyncio.create_task(_q(f"SELECT timestamp FROM event WHERE {f} ORDER BY timestamp DESC LIMIT 1;"))

        results = await asyncio.gather(task1, task2, task3, task4, task5)

        stats["event_count"] = results[0][0].get("count", 0) if results[0] else 0
        stats["entity_count"] = results[1][0].get("count", 0) if results[1] else 0
        stats["fact_count"] = results[2][0].get("count", 0) if results[2] else 0
        stats["oldest_event"] = results[3][0].get("timestamp") if results[3] else None
        stats["newest_event"] = results[4][0].get("timestamp") if results[4] else None
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)
    return json.dumps(stats, indent=2, default=str)


from urllib.parse import unquote as _unquote


@mcp.resource("sieveon://entity/{entity_id}", description="Entity details with active facts")
async def get_entity_resource(entity_id: str) -> str:
    """Get detailed information about a specific entity, including its active KG facts."""
    entity_id = _unquote(entity_id)
    # Interpolated unquoted into FROM/WHERE below, so it must be a strict
    # record id -- escaping cannot make an identifier safe.
    if not _is_record_id(entity_id):
        return json.dumps(
            {"error": f"Invalid record id '{entity_id}': expected 'table:id'"}, indent=2)
    try:
        result = await _query_surreal(f"SELECT * FROM {entity_id};")
        data = _extract_result(result, 1)
        if not data:
            return json.dumps({"error": f"Entity {entity_id} not found"}, indent=2)
        entity = _clean_output(data[0])

        facts_result = await _query_surreal(
            "SELECT id, predicate, in.name AS subject, out.name AS object, confidence, valid_from, valid_until "
            f"FROM fact WHERE (in = {entity_id} OR out = {entity_id}) "
            "AND (valid_until IS NONE OR valid_until > time::now()) "
            "ORDER BY confidence DESC LIMIT 50;"
        )
        facts = _extract_result(facts_result, 1) or []
        entity["facts"] = _clean_output(facts)
        return json.dumps(entity, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Failed to read entity {entity_id}: {str(e)}"}, indent=2)


@mcp.resource("sieveon://event/{event_id}", description="Event details")
async def get_event_resource(event_id: str) -> str:
    """Get details about a specific event."""
    event_id = _unquote(event_id)
    if not _is_record_id(event_id):
        return json.dumps(
            {"error": f"Invalid record id '{event_id}': expected 'table:id'"}, indent=2)
    try:
        sql = f"SELECT id, content, timestamp, source, metadata, forgotten, forgotten_reason FROM {event_id};"
        result = await _query_surreal(sql)
        data = _extract_result(result, 1)
        if not data:
            return json.dumps({"error": f"Event {event_id} not found"}, indent=2)
        return json.dumps(_clean_output(data[0]), indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Failed to read event {event_id}: {str(e)}"}, indent=2)


@mcp.resource("sieveon://kg/subject/{subject_name}", description="Knowledge graph facts where the named entity is the subject")
async def kg_subject_resource(subject_name: str) -> str:
    """Get KG facts where the named entity appears as the subject (in.position)."""
    # FastMCP passes the raw path segment URL-encoded ("Sieveon%20Labs").
    # Without decoding, the name never matches and the resource always
    # returns 0 facts -- decode before querying.
    subject_name = _unquote(subject_name)
    try:
        escaped = escape_surrealql(subject_name)
        sql = f"""
        SELECT id, predicate, in.name AS subject, out.name AS object,
               confidence, valid_from, valid_until
        FROM fact
        WHERE in.name = '{escaped}'
          AND (valid_until IS NONE OR valid_until > time::now())
          AND predicate NOT IN ['weakly_related', 'mentions']
        ORDER BY confidence DESC
        LIMIT 50;
        """
        result = await _query_surreal(sql)
        facts = _extract_result(result, 1) or []
        output = {
            "subject": subject_name,
            "facts": _clean_output(facts),
            "count": len(facts),
        }
        return json.dumps(output, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Failed to query KG for subject '{subject_name}': {str(e)}"}, indent=2)


@mcp.resource("sieveon://kg/predicate/{predicate}", description="Knowledge graph facts filtered by predicate/relation type")
async def kg_predicate_resource(predicate: str) -> str:
    """Get KG facts filtered by a specific predicate/relation type."""
    predicate = _unquote(predicate)
    try:
        escaped = escape_surrealql(predicate)
        sql = f"""
        SELECT id, predicate, in.name AS subject, out.name AS object,
               confidence, valid_from, valid_until
        FROM fact
        WHERE predicate = '{escaped}'
          AND (valid_until IS NONE OR valid_until > time::now())
        ORDER BY confidence DESC
        LIMIT 50;
        """
        result = await _query_surreal(sql)
        facts = _extract_result(result, 1) or []
        output = {
            "predicate": predicate,
            "facts": _clean_output(facts),
            "count": len(facts),
        }
        return json.dumps(output, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Failed to query KG for predicate '{predicate}': {str(e)}"}, indent=2)


@mcp.resource("sieveon://search/{query}", description="Hybrid search results (semantic + lexical) for a query string")
async def search_resource(query: str) -> str:
    """Search events by query text using hybrid search (vector + FTX) with RRF fusion."""
    query = _unquote(query)
    try:
        if not query.strip():
            return json.dumps({"events": [], "count": 0, "message": "Query cannot be empty"}, indent=2)

        from .tools import _prepare_fts_query

        query_escaped = _prepare_fts_query(query, "auto")
        query_vector = await _embed_query(query)
        query_vector_str = "[" + ", ".join(map(str, query_vector)) + "]"

        fetch_k = 30
        forgotten_filter = "forgotten = false"

        vec_sql = f"""
        SELECT id, content, timestamp, source, metadata,
               vector::similarity::cosine(embedding, {query_vector_str}) AS vec_score
        FROM event
        WHERE embedding IS NOT NONE
          AND {forgotten_filter}
          AND array::len(embedding) = {len(query_vector)}
        ORDER BY vec_score DESC
        LIMIT {fetch_k};
        """
        ftx_sql = f"""
        SELECT id, content, timestamp, source, metadata, search::score(0) AS bm25
        FROM event
        WHERE content @OR@ '{query_escaped}'
          AND {forgotten_filter}
        ORDER BY bm25 DESC
        LIMIT {fetch_k};
        """

        vec_task = asyncio.create_task(_query_surreal(vec_sql))
        ftx_task = asyncio.create_task(_query_surreal(ftx_sql))

        vec_result = await vec_task
        vec_events = _extract_result(vec_result, 1) or []
        ftx_events = []
        try:
            ftx_result = await ftx_task
            ftx_events = _extract_result(ftx_result, 1) or []
        except Exception:
            # Vector results alone still answer the query; say why the lexical
            # half is missing instead of returning a silently poorer result.
            log.warning("search_resource: FTX query failed, vector-only results",
                        exc_info=True)

        k = 60
        fused = {}
        seen_ids = set()

        for rank, ev in enumerate(vec_events):
            eid = ev.get("id")
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            vs = ev.get("vec_score", 0.0)
            if not isinstance(vs, (int, float)):
                vs = 0.0
            fused[eid] = {"event": ev, "rrf": 1.0 / (k + rank), "vec_score": vs}

        for rank, ev in enumerate(ftx_events):
            eid = ev.get("id")
            if eid not in seen_ids:
                seen_ids.add(eid)
                fused[eid] = {"event": ev, "rrf": 1.0 / (k + rank), "vec_score": 0.0}
            elif eid in fused:
                fused[eid]["rrf"] += 1.0 / (k + rank)

        scored = sorted(fused.values(), key=lambda x: x["rrf"], reverse=True)

        top_events = []
        for entry in scored[:10]:
            ev = _clean_output(entry["event"])
            ev["score"] = round(entry["rrf"], 4)
            ev["vec_score"] = round(entry["vec_score"], 4)
            top_events.append(ev)

        output = {"query": query, "events": top_events, "count": len(top_events)}
        return json.dumps(output, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": f"Search failed for query '{query}': {str(e)}"}, indent=2)


# ── FastAPI app ────────────────────────────────────────────────────────
# CORS: the origin allowlist is explicit. `allow_origins=["*"]` combined with
# `allow_credentials=True` is not merely permissive, it is incoherent -- the
# spec forbids echoing a wildcard origin on a credentialed response, so the
# browser rejects it and the intended capability (credentialed cross-origin
# requests) is unreachable while looking configured. Set CORS_ORIGINS to a
# comma-separated list to widen it deliberately.
_DEFAULT_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def _cors_origins() -> List[str]:
    raw = os.getenv("CORS_ORIGINS")
    if raw is None:
        return list(_DEFAULT_CORS_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start/stop module-level background work with the application.

    The reconnect task is started lazily by _query_surreal, so shutdown is what
    has to guarantee it does not outlive the process.
    """
    _reconnect_stop.clear()
    try:
        yield
    finally:
        _reconnect_stop.set()
        global _shared_client
        # Hold the client lock so the background reconnect task cannot grab
        # a client that is being closed (client.post on a closed AsyncClient
        # raises RuntimeError).
        async with _client_lock:
            if _shared_client is not None:
                await _shared_client.aclose()
                _shared_client = None


app = FastAPI(
    title="Sieveon Control Plane Server (MCP Implementation)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

SURREAL_URL = os.getenv("SURREALDB_URL", "http://127.0.0.1:8000/sql")
# Local SurrealDB defaults to root/root, so these match a stock `surreal start`.
# Set SURREALDB_USER/SURREALDB_PASS for anything reachable off localhost --
# shipping root/root to a shared instance would hand over the whole database.
SURREAL_AUTH = (
    os.getenv("SURREALDB_USER", "root"),
    os.getenv("SURREALDB_PASS", "root"),
)
SURREAL_NS = os.getenv("SURREALDB_NS", "sieveon")
SURREAL_DB = os.getenv("SURREALDB_DB", "sieveon")

# Maximum content length constant
MAX_CONTENT_LENGTH = 100_000

# Resilience state for SurrealDB connectivity
_surreal_failure_count = 0
_surreal_circuit_open = False
_surreal_last_failure = 0.0
_surreal_backoff_level = 0
_surreal_lock = asyncio.Lock()
_reconnect_task_started = False
# Set on shutdown to end the reconnect loop. Without it the `while True` task
# outlives the application (and every test process that imported the module).
_reconnect_stop = asyncio.Event()

# Shared HTTP client (reused across requests to avoid connection overhead)
_shared_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()

# Query embedding cache. Bounded FIFO: eviction takes the oldest *inserted*
# entry, which is not a true LRU (a hot key can still be evicted). At this
# size (128 vectors) the difference does not matter; the important property is
# that the cache cannot grow without bound.
_embedding_cache: "OrderedDict[str, List[float]]" = OrderedDict()
_EMBEDDING_CACHE_MAX = 128

# Circuit-breaker thresholds (budget-aware)
_CIRCUIT_OPEN_THRESHOLD = 5  # failures before opening
_CIRCUIT_RESET_AFTER = 10.0  # seconds before half-open retry
_MAX_BACKOFF = 8.0  # cap jittered backoff
_RECONNECT_INTERVAL = 30.0  # background check every 30s

# HTTP statuses worth retrying. Everything else in 4xx is a permanent client
# error (bad SurrealQL, bad credentials, missing table) and must fail fast.
_RETRYABLE_HTTP_STATUS = frozenset({408, 429, 500, 502, 503, 504})


class _NonRetryableSurrealError(RuntimeError):
    """A SurrealDB failure that will not improve on retry.

    Raised for 4xx responses and statement-level ``status: ERR``. Distinguishing
    it from a transport failure matters twice over: the query is not retried,
    and the circuit breaker is not advanced -- otherwise one malformed statement
    could open the breaker and take every later query down with it.
    """

# Test escape hatch. The breaker is module-global, so a test that expects a
# query to fail -- or a suite that runs against an unavailable server -- leaves
# it open and makes every later DB test fail with "circuit open" for 10s,
# regardless of the database being perfectly healthy. Set
# SURREALDB_DISABLE_CIRCUIT_BREAKER=1 to short-circuit both the open check and
# the failure accounting.
_CIRCUIT_BREAKER_DISABLED = os.getenv(
    "SURREALDB_DISABLE_CIRCUIT_BREAKER", "").strip().lower() in (
        "1", "true", "yes", "on")


def reset_surreal_circuit() -> None:
    """Clear the SurrealDB circuit breaker.

    For tests that exercise failure handling and then need a working
    database again in the same process.
    """
    global _surreal_failure_count, _surreal_circuit_open
    global _surreal_last_failure, _surreal_backoff_level
    _surreal_failure_count = 0
    _surreal_circuit_open = False
    _surreal_last_failure = 0.0
    _surreal_backoff_level = 0


async def _get_client() -> httpx.AsyncClient:
    global _shared_client
    # A closed client (lifespan shutdown / event-loop change) must never be
    # reused: httpx raises "Cannot send a request, as the client has been
    # closed" and every query then feeds the circuit breaker until it opens.
    if _shared_client is None or _shared_client.is_closed:
        async with _client_lock:
            if _shared_client is None or _shared_client.is_closed:
                _shared_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    return _shared_client


def _get_cached_embedding(query: str) -> Optional[List[float]]:
    cached = _embedding_cache.get(query)
    if cached is not None:
        _embedding_cache.move_to_end(query)
    return cached


def _store_embedding_cache(query: str, vector: List[float]):
    _embedding_cache[query] = vector
    _embedding_cache.move_to_end(query)
    while len(_embedding_cache) > _EMBEDDING_CACHE_MAX:
        _embedding_cache.popitem(last=False)


async def _embed_query(query: str) -> List[float]:
    cached = _get_cached_embedding(query)
    if cached is not None:
        return cached
    from src.extraction.embedding_service import get_embedding_service
    service = get_embedding_service()
    vector = await asyncio.to_thread(service.embed_for_query, query)
    _store_embedding_cache(query, vector)
    return vector


def _jittered_backoff(level: int) -> float:
    # Full jitter: uniform random in [0, min(cap, base * 2^level)]
    base = 0.5
    ceiling = min(_MAX_BACKOFF, base * (2**level))
    return random.uniform(0.0, ceiling)


def _health_from_failures(failure_count: int) -> float:
    """System-health factor for a consecutive-failure count (0..1).

    Single source of truth: _query_surreal and _background_reconnect_task used
    to carry the same `1.0 - min(failures, 10) / 12.0` expression inline, so
    the two could drift apart.
    """
    return 1.0 - (min(failure_count, 10) / 12.0)


def _retry_budget_for(sql: str) -> int:
    """How many attempts _query_surreal may make for this statement.

    Named for what it returns (an attempt count, not a boolean). Write-heavy
    statements get fewer attempts, and a struggling system gets fewer still.
    """
    health = BudgetTracker.get_system_health()
    heavy = sql.strip().upper().startswith(("RELATE", "DEFINE", "CREATE"))
    if health < 0.5:
        return 1 if heavy else 2
    return 2 if heavy else 3


# Backwards-compatible alias for the original (misleading) name.
_budget_aware_should_retry = _retry_budget_for


async def _query_surreal(
    sql: str,
    params: Optional[Dict[str, Any]] = None,
    ns: Optional[str] = None,
    db: Optional[str] = None,
) -> Any:
    """Execute SurrealQL — with optional bind parameters.

    Parameters are bound with SurrealQL LET declarations prepended to the
    statement, NOT via a JSON request body:
        sql = "CREATE entity SET name = $name"
        params = {"name": "Tobias"}

    A JSON body ({"sql": ..., "params": ...}) does NOT work against
    SurrealDB 3.3: POST /sql is documented to expect the raw body to be
    "a set of SurrealQL statements", so a JSON object is parsed as an inert
    object literal. The server then returns that literal as the result --
    status OK, but nothing was executed. Verified against 3.3.0.

    Values are serialised as JSON literals, which are valid SurrealQL values,
    so no SurrealQL string escaping is needed. json.dumps emits only
    double-quoted strings; SurrealQL accepts both quote styles.

    ns/db override the configured namespace for this call. SURREAL_NS and
    SURREAL_DB are bound at import time, so a caller that needs a different
    database cannot set the environment variable afterwards -- it has to
    pass them explicitly.
    """
    global \
        _surreal_failure_count, \
        _surreal_circuit_open, \
        _surreal_last_failure, \
        _surreal_backoff_level, \
        _reconnect_task_started

    # Start background reconnect task if not already started
    if not _reconnect_task_started:
        async with _surreal_lock:
            if not _reconnect_task_started:
                asyncio.create_task(_background_reconnect_task())
                _reconnect_task_started = True

    headers = {
        "Accept": "application/json",
        "Content-Type": "text/plain",
    }
    statements = [f"USE NS {ns or SURREAL_NS} DB {db or SURREAL_DB};"]
    if params:
        for key, value in params.items():
            statements.append(f"LET ${key} = {json.dumps(value)};")
    statements.append(sql)
    body = "\n".join(statements)

    # Read circuit state without holding lock while query runs
    async with _surreal_lock:
        circuit_open = _surreal_circuit_open
        failure_count = _surreal_failure_count
        last_failure = _surreal_last_failure

    if circuit_open and not _CIRCUIT_BREAKER_DISABLED:
        # Half-open probe after quiet period
        if (time.time() - last_failure) >= _CIRCUIT_RESET_AFTER:
            async with _surreal_lock:
                _surreal_circuit_open = False
                _surreal_backoff_level = 0
        else:
            raise RuntimeError(
                f"SurrealDB circuit open (failures={failure_count}); next probe in {_CIRCUIT_RESET_AFTER:.1f}s"
            )

    max_retries = _budget_aware_should_retry(sql)
    last_exception = None

    client = await _get_client()
    for attempt in range(max_retries):
        try:
            response = await client.post(
                SURREAL_URL,
                content=body,
                headers=headers,
                auth=SURREAL_AUTH,
                timeout=30.0,
            )
            if response.status_code >= 400:
                error_msg = response.text
                log.error(
                    "SurrealDB HTTP %s: %s", response.status_code, error_msg[:500])
                if response.status_code not in _RETRYABLE_HTTP_STATUS:
                    # 4xx (except 408/429) means the request itself is wrong --
                    # malformed SurrealQL, bad auth, missing table. Retrying it
                    # cannot succeed and just spends 3 roundtrips plus backoff
                    # on a permanent failure. Surface it immediately and do NOT
                    # count it against the circuit breaker.
                    raise _NonRetryableSurrealError(
                        f"SurrealDB rejected the query (HTTP {response.status_code}): "
                        f"{error_msg[:300]} | SQL: {sql[:120]}"
                    )
                raise httpx.HTTPStatusError(
                    f"SurrealDB error {response.status_code}: {error_msg}",
                    request=response.request,
                    response=response,
                )
            data = response.json()
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("status") == "ERR":
                        # A statement-level ERR is a query problem, not an
                        # availability problem: same reasoning as the 4xx case
                        # above, so it must not open the circuit either.
                        raise _NonRetryableSurrealError(
                            f"SurrealDB Error: {item.get('information') or item.get('result')} | SQL: {sql[:120]}"
                        )
            # success -> reset circuit state (only lock for this update)
            async with _surreal_lock:
                _surreal_failure_count = 0
                _surreal_circuit_open = False
                _surreal_backoff_level = 0
                # Success: reset health factor
                BudgetTracker.update_system_health(1.0)
            return data
        except _NonRetryableSurrealError:
            # Permanent by definition -- no retry, no backoff, no breaker.
            raise
        except Exception as exc:
            last_exception = exc
            async with _surreal_lock:
                _surreal_failure_count += 1
                _surreal_last_failure = time.time()
                level = _surreal_backoff_level
                _surreal_backoff_level = min(level + 1, 10)

                # Update health factor based on failure count
                health = _health_from_failures(_surreal_failure_count)
                BudgetTracker.update_system_health(health)

            if attempt < max_retries - 1:
                delay = _jittered_backoff(level)
                await asyncio.sleep(delay)

    # All retries failed -> possibly open circuit
    async with _surreal_lock:
        _surreal_circuit_open = (
            _surreal_failure_count >= _CIRCUIT_OPEN_THRESHOLD
            and not _CIRCUIT_BREAKER_DISABLED)
        opened = _surreal_circuit_open
        current_failures = _surreal_failure_count

    raise RuntimeError(
        f"SurrealDB unreachable after {max_retries} attempts (failures={current_failures}, circuit={'open' if opened else 'closed'}): {last_exception}"
    )


def _extract_result(data: List[Dict], index: int = 1) -> List[Dict]:
    """Extract results from SurrealDB response.

    `index` addresses the *filtered* candidate list, not the raw response.
    Callers overwhelmingly want the first meaningful statement, which is why
    `index=1` is the default and why `index == 1` short-circuits to
    `candidates[0]`: with the USE statement already filtered out, index 1 of the
    raw response IS candidates[0]. The explicit branches below only apply to
    other indices.

    Statements whose result is `None` are skipped. Those are the control
    statements `_query_surreal` and the transaction wrappers emit -- `USE`,
    `LET` (parameter declarations), `BEGIN`/`COMMIT` -- none of which return
    rows. Without this filter a request carrying bound parameters returned the
    `LET`'s None and every caller saw an empty result: the parameters resolved
    correctly, the extraction just pointed at the wrong statement.
    """
    if not isinstance(data, list):
        return []

    candidates = [
        item
        for item in data
        if isinstance(item, dict)
        and item.get("status") == "OK"
        and item.get("result") is not None
        and not (
            isinstance(item["result"], dict)
            and "database" in item["result"]
            and "namespace" in item["result"]
        )
    ]

    if not candidates:
        return []

    if index == 1:
        target = candidates[0]
    elif len(candidates) <= index:
        target = candidates[-1]
    else:
        target = candidates[index]

    result = target.get("result", [])
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return [result]
    return []


def _extract_result_batch(data: List[Dict]) -> List[Any]:
    """Extract results from a multi-statement SurrealDB response.
    Skips the USE NS response (index 0), returns results for each subsequent statement."""
    if not isinstance(data, list) or len(data) < 2:
        return []
    return [
        item.get("result", []) if isinstance(item, dict) else [] for item in data[1:]
    ]


def _extract_statement_results(data: List[Dict]) -> List[List[Any]]:
    """Per-statement results of a multi-statement SurrealDB response.

    Filters out the two statement kinds that never carry rows:
      * ``USE NS/DB``               -> result is a {namespace, database} dict
      * ``BEGIN``/``COMMIT``/``CANCEL`` -> result is None

    Returns a list whose element *i* is the rows produced by the i-th
    data-carrying statement, in order. Callers that wrap work in a transaction
    use this instead of `_extract_result`, because hard-coded offsets shift
    every time a BEGIN/COMMIT pair is added or removed.

    Verified against SurrealDB 3.x: a 4-statement request
    (USE, UPDATE, RELATE, COMMIT) yields exactly [update_rows, relate_rows].
    """
    out: List[List[Any]] = []
    for item in (data or []):
        if not isinstance(item, dict):
            continue
        res = item.get("result")
        if res is None:
            continue
        if isinstance(res, dict) and "namespace" in res and "database" in res:
            continue
        out.append(res if isinstance(res, list) else [res])
    return out


def _validate_limit(value: int, name: str = "limit", max_val: int = 1_000_000) -> int:
    """Validate that a limit/value is non-negative and within bounds. Raises ValueError if not."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative (got {value})")
    if value > max_val:
        raise ValueError(f"{name} exceeds maximum of {max_val} (got {value})")
    return value


_ALLOWED_RECORD_TABLES = frozenset({"entity", "fact", "event", "fact_history"})


def _is_record_id(value: Any) -> bool:
    """Strict record-id check (`table:id`) against SurrealQL injection.

    Record ids are interpolated *unquoted* into FROM/WHERE/UPDATE/DELETE
    statements throughout the tool layer, so they cannot be escaped as string
    literals -- a semicolon in the input terminates the statement and whatever
    follows is executed as further SurrealQL. Only the narrow shape SurrealDB
    itself generates is accepted, restricted to the tables this codebase
    reads/writes (arbitrary table names would allow probing unrelated tables).

    Canonical definition lives here (not in tools.py) because src.mcp.core is the
    module every consumer already imports; tools.py re-exports it for
    backwards compatibility.
    """
    text = str(value or "")
    m = re.fullmatch(r"([A-Za-z0-9_]+):([A-Za-z0-9_]+)", text)
    return bool(m) and m.group(1) in _ALLOWED_RECORD_TABLES


_ANGLED_ID_DELIMITERS = "⟨⟩<>"


def _strip_angled(value: Any) -> str:
    """Drop the record-id delimiters SurrealDB may wrap ids in.

    SurrealDB renders record ids as U+27E8/U+27E9 (ANGLE BRACKET) in some
    serialisations; ASCII <> is accepted too so callers can pass either form.
    """
    return str(value or "").strip(_ANGLED_ID_DELIMITERS).strip()


def _datetime_filters(
    since: Optional[str] = None,
    until: Optional[str] = None,
    column: str = "timestamp",
    param_prefix: str = "t",
) -> Tuple[List[str], Dict[str, Any]]:
    """Build timestamp bounds as *bound parameters*, never as a literal.

    Returns ``(clauses, params)``: a list of ready-to-join SQL predicates
    (empty when there is nothing to filter) and the params mapping
    ``$<param_prefix>_since`` / ``$<param_prefix>_until`` to the raw values.
    Join the clauses with ``" AND "``; the caller decides placement.

    Binding is not optional here: these values used to be interpolated into
    ``type::datetime("...")`` -- a *double*-quoted literal -- while
    escape_surrealql only escaped apostrophes, so a `since` containing `"`
    terminated the literal early and injected SQL. Bound parameters remove the
    quote-style question entirely.
    """
    clauses: List[str] = []
    params: Dict[str, Any] = {}
    if since:
        params[f"{param_prefix}_since"] = since
        clauses.append(f"{column} >= type::datetime(${param_prefix}_since)")
    if until:
        params[f"{param_prefix}_until"] = until
        clauses.append(f"{column} <= type::datetime(${param_prefix}_until)")
    return clauses, params


def _trust_of(source: str, explicit: Any = None) -> str:
    """Trust level for a stored event.

    Explicit per-event `trust` wins. Otherwise: direct tool input
    (`user_input`) is "direct", everything else (markdown imports, web
    content, batch sources) is "untrusted". Consumers MUST treat untrusted
    content as data, never as instructions (prompt-injection channel).
    """
    if isinstance(explicit, str) and explicit:
        return explicit
    # Chunk sources carry a "#chunkN" suffix ("user_input#chunk0"); the base
    # source decides trust, otherwise every markdown chunk imported with
    # source="user_input" silently degrades to untrusted.
    base_source = (source or "").split("#")[0]
    return "direct" if base_source == "user_input" else "untrusted"


def _clean_output(obj: Any) -> Any:
    """Recursively removes large fields like 'embedding' from output objects."""
    if isinstance(obj, list):
        return [_clean_output(i) for i in obj]
    if isinstance(obj, dict):
        # Create a copy to avoid modifying the original if it's cached or reused
        new_dict = {k: _clean_output(v) for k, v in obj.items() if k != "embedding"}
        # Trust marking: event-shaped dicts (content + source) always carry
        # a trust level so LLM consumers can distinguish direct input from
        # untrusted imports. Explicit stored trust wins, else derived.
        # See README Security section.
        if "content" in new_dict and "source" in new_dict:
            if not new_dict.get("trust"):
                new_dict["trust"] = _trust_of(new_dict.get("source", ""))
        return new_dict
    return obj


async def _background_reconnect_task():
    """Background task to actively check connection and reset circuit breaker.

    Runs until `_reconnect_stop` is set, so it terminates on application
    shutdown instead of leaking for the lifetime of the process.
    """
    global _surreal_failure_count, _surreal_circuit_open, _surreal_backoff_level

    log.info("Starting background SurrealDB reconnect task")
    while not _reconnect_stop.is_set():
        try:
            # Only probe if we've had failures or circuit is open
            should_probe = False
            async with _surreal_lock:
                if _surreal_circuit_open or _surreal_failure_count > 0:
                    should_probe = True

            if should_probe:
                # Lightweight probe: INFO FOR DB
                headers = {"Accept": "application/json", "Content-Type": "text/plain"}
                full_sql = f"USE NS {SURREAL_NS} DB {SURREAL_DB};\nINFO FOR DB;"

                client = await _get_client()
                response = await client.post(
                    SURREAL_URL,
                    content=full_sql,
                    headers=headers,
                    auth=SURREAL_AUTH,
                    timeout=httpx.Timeout(5.0),
                )

                if response.status_code < 400:
                    # Success! Reset everything
                    async with _surreal_lock:
                        if _surreal_circuit_open:
                            log.info(
                                "SurrealDB connection restored. Closing circuit.")
                        _surreal_failure_count = 0
                        _surreal_circuit_open = False
                        _surreal_backoff_level = 0
                        # Reset health factor to healthy
                        BudgetTracker.update_system_health(1.0)
                else:
                    # Still failing, update health factor based on failure count
                    async with _surreal_lock:
                        health = _health_from_failures(_surreal_failure_count)
                        BudgetTracker.update_system_health(health)

        except Exception as e:
            # Log the exception instead of silent fail
            log.warning("Background reconnect task error: %s", e)

        try:
            await asyncio.wait_for(
                _reconnect_stop.wait(), timeout=_RECONNECT_INTERVAL)
        except asyncio.TimeoutError:
            pass


async def check_schema_exists() -> bool:
    """Check if the Sieveon schema is already loaded in SurrealDB."""
    try:
        # Check if key tables exist - INFO FOR DB is more standard in SurrealDB 2.x+
        result = await _query_surreal("INFO FOR DB;")
        # Extract the result from the second item (index 1) since index 0 is the USE statement
        db_info = _extract_result(result, 1)

        if not db_info or not isinstance(db_info, list) or len(db_info) == 0:
            return False

        # INFO FOR DB returns a dictionary where keys are things like 'tables', 'functions', etc.
        # But _extract_result might have already wrapped it in a list.
        info_dict = db_info[0] if isinstance(db_info, list) else db_info

        if not isinstance(info_dict, dict) or "tables" not in info_dict:
            return False

        table_names = list(info_dict["tables"].keys())

        required_tables = ["event", "entity", "fact"]
        exists = all(table in table_names for table in required_tables)
        if exists:
            log.debug("Tables found: %s", table_names)
        return exists
    except Exception as e:
        log.warning("Schema check failed: %s", e)
        return False


def _strip_surql_comments(line: str) -> str:
    """Remove a trailing `--` / `//` comment from one line.

    Naive `line.split("--")[0]` truncated any statement containing `--` inside
    a string literal -- e.g. a regex default `'^[a-z--]+$'` -- silently
    producing a different statement than the file declared. Scan for the marker
    only while outside quotes; the trailing part is kept.
    """
    out = []
    quote = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(line[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        else:
            if ch in ("'", '"', "`"):
                quote = ch
                out.append(ch)
            elif line.startswith("--", i) or line.startswith("//", i):
                break
            else:
                out.append(ch)
        i += 1
    return "".join(out).strip()


def load_schema_file(file_path: str) -> List[str]:
    """Load and parse a .surql file, removing comments and splitting statements."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    clean_lines = []
    for line in content.split("\n"):
        stripped = _strip_surql_comments(line)
        if stripped:
            clean_lines.append(stripped)
    content_no_comments = " ".join(clean_lines)

    statements = []
    current = ""
    depth = 0
    for part in content_no_comments.split(";"):
        part = part.strip()
        if not part:
            continue
        current += part + ";"
        depth += part.count("{") - part.count("}")
        if depth <= 0:
            statements.append(current.strip())
            current = ""
    if current.strip():
        statements.append(current.strip())

    # Add IF NOT EXISTS to table/index definitions to handle existing schema.
    # Statements already carrying OVERWRITE are idempotent by themselves and
    # must be left alone (IF NOT EXISTS + OVERWRITE is a syntax error).
    safe_statements = []
    for stmt in statements:
        upper = stmt.upper()
        if "OVERWRITE" in upper:
            safe_statements.append(stmt)
            continue
        for keyword in ("DEFINE TABLE", "DEFINE INDEX", "DEFINE FUNCTION",
                        "DEFINE FIELD"):
            # `upper.startswith` rather than `in`: a stray "DEFINE TABLE"
            # mention later in the statement body must not be rewritten too,
            # and str.replace would substitute every occurrence.
            if upper.startswith(keyword) and "IF NOT EXISTS" not in upper:
                stmt = stmt[:len(keyword)] + " IF NOT EXISTS" + stmt[len(keyword):]
                break
        safe_statements.append(stmt)

    return safe_statements


async def ensure_schema_loaded():
    """Ensure the Sieveon schema is loaded. If not, load it automatically."""
    if not await check_schema_exists():
        log.info("Sieveon schema not found. Loading automatically...")

        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        load_script = os.path.join(project_root, "scripts", "load_schema_optimized.py")

        if os.path.exists(load_script):
            log.info("Using existing load script: %s", load_script)
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, load_script,
                    cwd=project_root,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
                if stdout:
                    log.info("Schema loader stdout: %s",
                          stdout.decode("utf-8", errors="replace"))
                if stderr:
                    log.warning("Schema loader stderr: %s",
                                stderr.decode("utf-8", errors="replace"))
                log.info("Schema loading complete")
            except asyncio.TimeoutError:
                log.error("Schema loading timed out after 60s")
                if proc:
                    proc.kill()
            except Exception as e:
                log.error("Failed to run load script: %s", e)
        else:
            log.warning("Load script not found: %s", load_script)
            log.warning("Skipping automatic schema load")
    else:
        log.info("Sieveon schema already loaded")

    # Ensure entity table has all required fields (in case schema was loaded without them).
    # Every DEFAULT must match docs/schema.surql: these are OVERWRITE statements, so a
    # missing DEFAULT silently strips the schema default and later CREATEs that omit
    # the field fail with "Couldn't coerce value for field `type`".
    try:
        required_fields = [
            "DEFINE FIELD OVERWRITE name ON entity TYPE string;",
            "DEFINE FIELD OVERWRITE type ON entity TYPE string DEFAULT 'unknown';",
            "DEFINE FIELD OVERWRITE embedding ON entity TYPE option<array>;",
            "DEFINE FIELD OVERWRITE metadata ON entity TYPE option<object> FLEXIBLE;",
            "DEFINE FIELD OVERWRITE forgotten ON entity TYPE bool DEFAULT false;",
            "DEFINE FIELD OVERWRITE forget_reason ON entity TYPE option<string>;",
            "DEFINE FIELD OVERWRITE created_at ON entity TYPE option<datetime> DEFAULT time::now();",
            "DEFINE FIELD OVERWRITE updated_at ON entity TYPE option<datetime> DEFAULT time::now();",
        ]
        for field_def in required_fields:
            await _query_surreal(field_def)
    except Exception as e:
        log.warning("Entity field sync failed (non-fatal): %s", e)

    # Backfill missing timestamps on existing entities
    try:
        await _query_surreal(
            "UPDATE entity SET created_at = time::now() WHERE created_at IS NONE;"
        )
        await _query_surreal(
            "UPDATE entity SET updated_at = time::now() WHERE updated_at IS NONE;"
        )
        backfilled = _extract_result(
            await _query_surreal(
                "SELECT count() AS c FROM (SELECT * FROM entity WHERE created_at = time::now()) GROUP ALL;"
            ), 1
        )
        count = backfilled[0].get("c", 0) if backfilled else 0
        if count > 0:
            log.info("Backfilled timestamps for %d entities", count)
    except Exception as e:
        log.warning("Timestamp backfill failed (non-fatal): %s", e)

    # ── Automatic data migration ──────────────────────────────────────
    # Apply pending schema/data migrations in version order.
    try:
        from src.mcp.migrations import MigrationEngine, _register_builtin
        engine = MigrationEngine(_query_surreal)
        _register_builtin(engine)
        logs = await engine.apply_all()
        for line in logs:
            log.info("[MIGRATION] %s", line)
    except Exception as e:
        log.warning("Migration check failed (non-fatal): %s", e)

    # ── Router learned costs ──────────────────────────────────────────
    # Restore per-context strategy effectiveness from the last run.
    # Fail-open: a missing row or an unreachable DB starts unlearned.
    await load_router_costs()


async def load_router_costs() -> bool:
    """Restore CostTracker state from the router_costs table.

    Returns True when state was restored, False otherwise. Never raises:
    routing must work with empty metrics.
    """
    try:
        from src.router.cost_awareness import cost_tracker
        rows = _extract_result(await _query_surreal(
            "SELECT state FROM router_costs:state;"
        ), 1)
        if not rows:
            return False
        state = rows[0].get("state") if isinstance(rows[0], dict) else None
        if not isinstance(state, dict):
            return False
        cost_tracker.import_state(state)
        return True
    except Exception as e:
        log.warning("Router cost restore failed (non-fatal): %s", e)
        return False


async def save_router_costs() -> bool:
    """Snapshot CostTracker state to the router_costs table (single row).

    Fail-open: a failed save only loses learning since the last snapshot.
    """
    try:
        from src.router.cost_awareness import cost_tracker
        # UPSERT, not UPDATE. Since SurrealDB 2.0 an UPDATE against a record ID
        # that does not exist is a no-op: it will not create the row, so the
        # very first snapshot would be silently dropped. UPSERT is documented
        # as "insert, otherwise update" and is the only single-statement
        # create-or-replace primitive (INSERT ... ON DUPLICATE KEY UPDATE is
        # the other). State goes in as a bound parameter, not interpolated
        # JSON, so SurrealQL never has to parse it.
        await _query_surreal(
            "UPSERT router_costs:state CONTENT { state: $state, "
            "updated_at: time::now() } RETURN NONE;",
            {"state": cost_tracker.export_state()},
        )
        return True
    except Exception as e:
        log.warning("Router cost snapshot failed (non-fatal): %s", e)
        return False