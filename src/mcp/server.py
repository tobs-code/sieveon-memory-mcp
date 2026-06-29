"""
Control Plane Server implementing the Model Context Protocol (MCP)
Coordinates all components of the agent memory system

NOTE: This implements the Model Context Protocol (MCP) specification from Anthropic,
not to be confused with any other MCP acronym. This server serves as the system coordinator.
"""
import sys
import os
import json
import time
import requests
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timezone
import asyncio

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is not installed, skip loading .env file
    pass

# Standard imports
import uvicorn
from fastapi import FastAPI, Query, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Our components
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mcp.server.fastmcp import FastMCP  # This is the Model Context Protocol implementation
from src.extraction.classifier import QueryClassifier
from src.router.policy import RoutingPolicy
from src.planner.executor import RetrievalExecutor, PlanExecutor
from src.maintenance.conservative_maintainer import ConservativeMaintainer
from src.extraction.embedding_service import get_embedding_service

# Initialize FastMCP (Model Context Protocol) and FastAPI apps
mcp = FastMCP("strata")  # Model Context Protocol implementation

# FastAPI app
app = FastAPI(title="Strata Control Plane Server (MCP Implementation)", version="0.1.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SURREAL_URL = os.getenv("SURREALDB_URL", "http://127.0.0.1:8000/sql")
SURREAL_AUTH = (os.getenv("SURREALDB_USER", "root"), os.getenv("SURREALDB_PASS", "root"))
SURREAL_NS = os.getenv("SURREALDB_NS", "strata")  # Updated from agent_memory to strata
SURREAL_DB = os.getenv("SURREALDB_DB", "strata")  # Updated from agent_memory to strata


def _query_surreal(sql: str) -> Any:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    full_sql = f"USE NS {SURREAL_NS} DB {SURREAL_DB};\n{sql}"
    response = requests.post(SURREAL_URL, data=full_sql, headers=headers, auth=SURREAL_AUTH, timeout=30)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("status") == "ERR":
                raise RuntimeError(f"SurrealDB Error: {item.get('information') or item.get('result')} | SQL: {sql[:120]}")
    return data


def _extract_result(data: List[Dict], index: int = 1) -> List[Dict]:
    """Extract results from SurrealDB response."""
    if not isinstance(data, list):
        return []
    candidates = [
        item for item in data
        if isinstance(item, dict)
        and item.get("status") == "OK"
        and "result" in item
        and not (isinstance(item["result"], dict) and "database" in item["result"] and "namespace" in item["result"])
    ]
    if not candidates:
        return []
    if len(candidates) <= index:
        target = candidates[-1]
    else:
        target = candidates[index]
    result = target.get("result", [])
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return [result]
    return []


@app.get("/classify")
async def classify_endpoint(query: str = Query(..., description="The query to classify")):
    """Classify a query according to type and confidence"""
    classifier = QueryClassifier()
    query_type, confidence = classifier.classify(query)
    return {
        "query": query,
        "type": query_type,
        "confidence": confidence
    }


@app.get("/route")
async def route_endpoint(query: str = Query(..., description="The query to route")):
    """Route a query according to the routing policy"""
    classifier = QueryClassifier()
    policy = RoutingPolicy()
    
    query_type, confidence = classifier.classify(query)
    strategy = policy.get_strategy(query_type, confidence)
    
    return {
        "query": query,
        "classification": {
            "type": query_type,
            "confidence": confidence
        },
        "routing_strategy": strategy
    }


@app.post("/plan_and_execute")
async def plan_and_execute_endpoint(request_data: dict):
    """Create and execute a plan for the given query"""
    query = request_data.get("query", "")
    classifier = QueryClassifier()
    policy = RoutingPolicy()
    executor = PlanExecutor()
    
    # Classify and route the query
    query_type, confidence = classifier.classify(query)
    strategy_info = policy.get_strategy(query_type, confidence)
    
    # Create a plan
    plan = {
        "query": query,
        "strategy": strategy_info["strategy"],
        "classification": {
            "type": query_type,
            "confidence": confidence
        }
    }
    
    # Execute the plan
    result = await executor.execute_plan(plan)
    
    return result


@app.post("/maintain")
async def maintain_endpoint():
    """Perform maintenance operations"""
    maintainer = ConservativeMaintainer()
    result = await maintainer.perform_maintenance()
    
    return result


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "components": {
            "classifier": "ready",
            "router": "ready", 
            "planner": "ready",
            "executor": "ready",
            "maintainer": "ready"
        }
    }


# =============================================================================
# Schicht 1 — Core Memory Operations
# =============================================================================

# Expose memory operations as HTTP endpoints
@app.post("/memory/store")
async def memory_store_endpoint(request_data: dict):
    """Stores a new event in the raw event log. Always persists, entropy gate decides KG extraction."""
    content = request_data.get("content", "")
    source = request_data.get("source", "user_input")
    metadata = request_data.get("metadata", None)
    
    embedding_service = get_embedding_service()
    embedding_storage = embedding_service.embed_for_storage(content)

    content_escaped = content.replace("'", "''")
    sql = f"""
    CREATE event SET
        content = '{content_escaped}',
        source = '{source}',
        embedding = {embedding_storage};
    """
    if metadata:
        meta_escaped = json.dumps(metadata).replace("'", "''")
        sql = f"""
        CREATE event SET
            content = '{content_escaped}',
            source = '{source}',
            embedding = {embedding_storage},
            metadata = {{ content: '{meta_escaped}' }};
        """

    result = _query_surreal(sql)
    event_result = _extract_result(result)
    if event_result and isinstance(event_result, list) and len(event_result) > 0 and isinstance(event_result[0], dict):
        event_id = event_result[0]["id"]
    elif event_result and isinstance(event_result, dict):
        event_id = event_result.get("id")
    else:
        event_id = None
    return {"event_id": event_id, "status": "stored", "source": source}


@app.post("/memory/query")
async def memory_query_endpoint(request_data: dict):
    """Routes a natural language query through the full pipeline: classify → plan → retrieve."""
    query = request_data.get("query", "")
    cost_budget = request_data.get("cost_budget", "auto")
    
    classifier = QueryClassifier()
    q_type, confidence = classifier.classify(query)

    policy = RoutingPolicy()
    strategy = policy.get_strategy(q_type, confidence, cost_budget)

    executor = RetrievalExecutor()
    import asyncio
    results = asyncio.run(executor.execute_strategy(strategy, query))

    entities = []
    facts = []
    events = []
    for r in results:
        if isinstance(r, dict):
            rid = r.get("id", "")
            if rid.startswith("entity:"):
                entities.append(r)
            elif rid.startswith("fact:"):
                facts.append(r)
            elif rid.startswith("event:"):
                events.append(r)

    return {
        "query": query,
        "classified_as": q_type,
        "confidence": confidence,
        "strategy": strategy["strategy"],
        "cost_budget": strategy["cost_budget"],
        "results": {
            "entities": entities,
            "facts": facts,
            "events": events,
        },
        "total": len(entities) + len(facts) + len(events),
    }


@mcp.tool()
def memory_store(content: str, source: str = "user_input", metadata: Optional[Dict[str, Any]] = None) -> dict:
    """Stores a new event in the raw event log. Always persists, entropy gate decides KG extraction."""
    embedding_service = get_embedding_service()
    embedding_storage = embedding_service.embed_for_storage(content)

    content_escaped = content.replace("'", "''")
    sql = f"""
    CREATE event SET
        content = '{content_escaped}',
        source = '{source}',
        embedding = {embedding_storage};
    """
    if metadata:
        meta_escaped = json.dumps(metadata).replace("'", "''")
        sql = f"""
        CREATE event SET
            content = '{content_escaped}',
            source = '{source}',
            embedding = {embedding_storage},
            metadata = {{ content: '{meta_escaped}' }};
        """

    result = _query_surreal(sql)
    event_result = _extract_result(result)
    if event_result and isinstance(event_result, list) and len(event_result) > 0 and isinstance(event_result[0], dict):
        event_id = event_result[0]["id"]
    elif event_result and isinstance(event_result, dict):
        event_id = event_result.get("id")
    else:
        event_id = None
    return {"event_id": event_id, "status": "stored", "source": source}


@mcp.tool()
def memory_query(query: str, cost_budget: str = "auto") -> dict:
    """Routes a natural language query through the full pipeline: classify → plan → retrieve."""
    classifier = QueryClassifier()
    q_type, confidence = classifier.classify(query)

    policy = RoutingPolicy()
    strategy = policy.get_strategy(q_type, confidence, cost_budget)

    executor = RetrievalExecutor()
    import asyncio
    results = asyncio.run(executor.execute_strategy(strategy, query))

    entities = []
    facts = []
    events = []
    for r in results:
        if isinstance(r, dict):
            rid = r.get("id", "")
            if rid.startswith("entity:"):
                entities.append(r)
            elif rid.startswith("fact:"):
                facts.append(r)
            elif rid.startswith("event:"):
                events.append(r)

    return {
        "query": query,
        "classified_as": q_type,
        "confidence": confidence,
        "strategy": strategy["strategy"],
        "cost_budget": strategy["cost_budget"],
        "results": {
            "entities": entities,
            "facts": facts,
            "events": events,
        },
        "total": len(entities) + len(facts) + len(events),
    }


@mcp.tool()
def memory_update(subject: str, predicate: str, new_value: str) -> dict:
    """Updates a fact in the KG via logical invalidation. Old fact gets valid_until, new fact created."""
    subject_escaped = subject.replace("'", "''")
    predicate_escaped = predicate.replace("'", "''")
    new_value_escaped = new_value.replace("'", "''")

    find_sql = f"""
    SELECT * FROM fact
    WHERE in.name = '{subject_escaped}'
      AND predicate = '{predicate_escaped}'
      AND valid_until = NONE
    LIMIT 1;
    """
    find_result = _query_surreal(find_sql)
    facts = _extract_result(find_result, 1)

    invalidated = None
    if facts:
        old_fact_id = facts[0]["id"]
        invalidate_sql = f"UPDATE {old_fact_id} SET valid_until = time::now();"
        _query_surreal(invalidate_sql)
        invalidated = old_fact_id

    subject_escaped = subject.replace("'", "''")
    new_value_escaped = new_value.replace("'", "''")
    predicate_escaped = predicate.replace("'", "''")

    subject_sql = f"SELECT id FROM entity WHERE name = '{subject_escaped}' LIMIT 1;"
    subject_result = _query_surreal(subject_sql)
    subject_entities = _extract_result(subject_result, 1)

    object_sql = f"SELECT id FROM entity WHERE name = '{new_value_escaped}' LIMIT 1;"
    object_result = _query_surreal(object_sql)
    object_entities = _extract_result(object_result, 1)

    new_fact_id = None
    if subject_entities and object_entities:
        subject_id = subject_entities[0]["id"]
        object_id = object_entities[0]["id"]
        relate_sql = f"RELATE {subject_id}->fact->{object_id} SET predicate = '{predicate_escaped}', confidence = 1.0;"
        relate_result = _query_surreal(relate_sql)
        new_fact = _extract_result(relate_result, 1)
        if new_fact:
            new_fact_id = new_fact[0]["id"]

    return {
        "invalidated_fact": invalidated,
        "new_fact": new_fact_id,
        "subject": subject,
        "predicate": predicate,
        "new_value": new_value,
    }


# =============================================================================
# Schicht 2 — Retrieval Primitives
# =============================================================================

@app.get("/memory/event_log_search")
async def event_log_search_endpoint(query: str = Query(..., description="Search query"), 
                                   since: Optional[str] = Query(None, description="Start date"), 
                                   until: Optional[str] = Query(None, description="End date"), 
                                   limit: int = Query(10, description="Result limit")):
    """Direct timeline query without router: search raw event log."""
    query_escaped = query.replace("'", "''")
    sql = f"SELECT * FROM event WHERE content @@ '{query_escaped}'"

    if since:
        since_escaped = since.replace("'", "''")
        sql += f" AND timestamp >= '{since_escaped}'"
    if until:
        until_escaped = until.replace("'", "''")
        sql += f" AND timestamp <= '{until_escaped}'"

    sql += f" ORDER BY timestamp DESC LIMIT {limit};"
    result = _query_surreal(sql)
    events = _extract_result(result)
    return {"events": events, "count": len(events)}


@app.get("/memory/kg_query")
async def kg_query_endpoint(subject: Optional[str] = Query(None, description="Subject to search for"), 
                           predicate: Optional[str] = Query(None, description="Predicate to search for"), 
                           at_time: Optional[str] = Query(None, description="Time to query at")):
    """Direct graph traversal: query facts by subject/predicate/time."""
    sql = "SELECT * FROM fact WHERE valid_until = NONE"

    if subject:
        subject_escaped = subject.replace("'", "''")
        sql += f" AND in.name CONTAINS '{subject_escaped}'"
    if predicate:
        predicate_escaped = predicate.replace("'", "''")
        sql += f" AND predicate = '{predicate_escaped}'"
    if at_time:
        at_time_escaped = at_time.replace("'", "''")
        sql += f" AND valid_from <= '{at_time_escaped}'"

    sql += " LIMIT 20;"
    result = _query_surreal(sql)
    facts = _extract_result(result)

    entities = []
    seen_ids = set()
    for fact in facts:
        for key in ("in", "out"):
            eid = fact.get(key)
            if isinstance(eid, dict) and eid.get("id") not in seen_ids:
                entities.append(eid)
                seen_ids.add(eid.get("id"))

    return {"facts": facts, "entities": entities, "count": len(facts)}


@mcp.tool()
def event_log_search(query: str, since: Optional[str] = None, until: Optional[str] = None, limit: int = 10) -> dict:
    """Direct timeline query without router: search raw event log."""
    query_escaped = query.replace("'", "''")
    sql = f"SELECT * FROM event WHERE content @@ '{query_escaped}'"

    if since:
        since_escaped = since.replace("'", "''")
        sql += f" AND timestamp >= '{since_escaped}'"
    if until:
        until_escaped = until.replace("'", "''")
        sql += f" AND timestamp <= '{until_escaped}'"

    sql += f" ORDER BY timestamp DESC LIMIT {limit};"
    result = _query_surreal(sql)
    events = _extract_result(result)
    return {"events": events, "count": len(events)}


@mcp.tool()
def kg_query(subject: Optional[str] = None, predicate: Optional[str] = None, at_time: Optional[str] = None) -> dict:
    """Direct graph traversal: query facts by subject/predicate/time."""
    sql = "SELECT * FROM fact WHERE valid_until = NONE"

    if subject:
        subject_escaped = subject.replace("'", "''")
        sql += f" AND in.name CONTAINS '{subject_escaped}'"
    if predicate:
        predicate_escaped = predicate.replace("'", "''")
        sql += f" AND predicate = '{predicate_escaped}'"
    if at_time:
        at_time_escaped = at_time.replace("'", "''")
        sql += f" AND valid_from <= '{at_time_escaped}'"

    sql += " LIMIT 20;"
    result = _query_surreal(sql)
    facts = _extract_result(result)

    entities = []
    seen_ids = set()
    for fact in facts:
        for key in ("in", "out"):
            eid = fact.get(key)
            if isinstance(eid, dict) and eid.get("id") not in seen_ids:
                entities.append(eid)
                seen_ids.add(eid.get("id"))

    return {"facts": facts, "entities": entities, "count": len(facts)}


@mcp.tool()
def semantic_search(query: str, top_k: int = 5) -> dict:
    """Pure vector search without KG."""
    import numpy as np

    embedding_service = get_embedding_service()
    query_vector = np.array(embedding_service.embed_for_query(query), dtype=np.float32)

    sql = "SELECT id, content, embedding FROM event WHERE embedding IS NOT NONE;"
    result = _query_surreal(sql)
    events = _extract_result(result, 1)

    if not events:
        return {"events": [], "count": 0}

    scored = []
    for event in events:
        emb = event.get("embedding")
        if emb is None:
            continue
        emb_np = np.array(emb, dtype=np.float32)
        norm_q = np.linalg.norm(query_vector)
        norm_e = np.linalg.norm(emb_np)
        if norm_q == 0 or norm_e == 0:
            similarity = 0.0
        else:
            similarity = float(np.dot(query_vector, emb_np) / (norm_q * norm_e))
        scored.append((similarity, event))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_events = [e for _, e in scored[:top_k]]

    return {"events": top_events, "count": len(top_events)}


# =============================================================================
# Schicht 3 — Introspection Tools
# =============================================================================

@app.post("/memory/semantic_search")
async def semantic_search_endpoint(request_data: dict):
    """Pure vector search without KG."""
    query = request_data.get("query", "")
    top_k = request_data.get("top_k", 5)
    
    import numpy as np

    embedding_service = get_embedding_service()
    query_vector = np.array(embedding_service.embed_for_query(query), dtype=np.float32)

    sql = "SELECT id, content, embedding FROM event WHERE embedding IS NOT NONE;"
    result = _query_surreal(sql)
    events = _extract_result(result, 1)

    if not events:
        return {"events": [], "count": 0}

    scored = []
    for event in events:
        emb = event.get("embedding")
        if emb is None:
            continue
        emb_np = np.array(emb, dtype=np.float32)
        norm_q = np.linalg.norm(query_vector)
        norm_e = np.linalg.norm(emb_np)
        if norm_q == 0 or norm_e == 0:
            similarity = 0.0
        else:
            similarity = float(np.dot(query_vector, emb_np) / (norm_q * norm_e))
        scored.append((similarity, event))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_events = [e for _, e in scored[:top_k]]

    return {"events": top_events, "count": len(top_events)}


@mcp.tool()
def memory_stats() -> dict:
    """Returns statistics about the memory system."""
    event_count_sql = "SELECT count() AS event_count FROM event;"
    entity_count_sql = "SELECT count() AS entity_count FROM entity;"
    fact_count_sql = "SELECT count() AS fact_count FROM fact WHERE valid_until = NONE;"

    event_count = _extract_result(_query_surreal(event_count_sql), 1)
    entity_count = _extract_result(_query_surreal(entity_count_sql), 1)
    fact_count = _extract_result(_query_surreal(fact_count_sql), 1)

    stats = {
        "event_count": event_count[0]["event_count"] if event_count else 0,
        "entity_count": entity_count[0]["entity_count"] if entity_count else 0,
        "fact_count": fact_count[0]["fact_count"] if fact_count else 0,
    }

    oldest_sql = "SELECT timestamp FROM event ORDER BY timestamp ASC LIMIT 1;"
    newest_sql = "SELECT timestamp FROM event ORDER BY timestamp DESC LIMIT 1;"
    oldest_result = _extract_result(_query_surreal(oldest_sql), 1)
    newest_result = _extract_result(_query_surreal(newest_sql), 1)
    if oldest_result:
        stats["oldest_event"] = oldest_result[0].get("timestamp")
    if newest_result:
        stats["newest_event"] = newest_result[0].get("timestamp")

    total_sql = "SELECT count() AS total FROM gate_log;"
    extracted_sql = "SELECT count() AS extracted FROM gate_log WHERE decision = 'extract';"
    total_result = _extract_result(_query_surreal(total_sql), 1)
    extracted_result = _extract_result(_query_surreal(extracted_sql), 1)
    if total_result:
        total = total_result[0].get("total", 0)
        extracted = extracted_result[0].get("extracted", 0) if extracted_result else 0
        stats["gate_pass_rate"] = round(extracted / total, 3) if total > 0 else 0.0

    return stats


@mcp.tool()
def explain_routing(query: str) -> dict:
    """Explains why the router chose a specific strategy for a query."""
    classifier = QueryClassifier()
    q_type, confidence = classifier.classify(query)

    policy = RoutingPolicy()
    strategy = policy.get_strategy(q_type, confidence)

    reasons = {
        "temporal": "Query contains temporal indicators (when, date, time, since...). Event log prioritized.",
        "factual": "Query asks for specific facts (who, what, where). Knowledge graph prioritized.",
        "multi-hop": "Query implies multi-hop reasoning (why, relationship, and where...). Graph expansion enabled.",
        "conversational": "Query is conversational (remember, talked about). Composite KG+vector strategy used.",
        "update": "Query is an update instruction. Invalidation strategy selected.",
    }

    return {
        "query": query,
        "classified_as": q_type,
        "confidence": confidence,
        "strategy_selected": strategy["strategy"],
        "cost_budget": strategy["cost_budget"],
        "policy_applied": strategy["policy_applied"],
        "reason": reasons.get(q_type, "Default routing based on query type."),
    }


# =============================================================================
# Schicht 4 — Maintenance Tools
# =============================================================================

@app.post("/memory/stats")
async def memory_stats_endpoint():
    """Returns statistics about the memory system."""
    event_count_sql = "SELECT count() AS event_count FROM event;"
    entity_count_sql = "SELECT count() AS entity_count FROM entity;"
    fact_count_sql = "SELECT count() AS fact_count FROM fact WHERE valid_until = NONE;"

    event_count = _extract_result(_query_surreal(event_count_sql), 1)
    entity_count = _extract_result(_query_surreal(entity_count_sql), 1)
    fact_count = _extract_result(_query_surreal(fact_count_sql), 1)

    stats = {
        "event_count": event_count[0]["event_count"] if event_count else 0,
        "entity_count": entity_count[0]["entity_count"] if entity_count else 0,
        "fact_count": fact_count[0]["fact_count"] if fact_count else 0,
    }

    oldest_sql = "SELECT timestamp FROM event ORDER BY timestamp ASC LIMIT 1;"
    newest_sql = "SELECT timestamp FROM event ORDER BY timestamp DESC LIMIT 1;"
    oldest_result = _extract_result(_query_surreal(oldest_sql), 1)
    newest_result = _extract_result(_query_surreal(newest_sql), 1)
    if oldest_result:
        stats["oldest_event"] = oldest_result[0].get("timestamp")
    if newest_result:
        stats["newest_event"] = newest_result[0].get("timestamp")

    total_sql = "SELECT count() AS total FROM gate_log;"
    extracted_sql = "SELECT count() AS extracted FROM gate_log WHERE decision = 'extract';"
    total_result = _extract_result(_query_surreal(total_sql), 1)
    extracted_result = _extract_result(_query_surreal(extracted_sql), 1)
    if total_result:
        total = total_result[0].get("total", 0)
        extracted = extracted_result[0].get("extracted", 0) if extracted_result else 0
        stats["gate_pass_rate"] = round(extracted / total, 3) if total > 0 else 0.0

    return stats


@app.post("/memory/explain_routing")
async def explain_routing_endpoint(request_data: dict):
    """Explains why the router chose a specific strategy for a query."""
    query = request_data.get("query", "")
    classifier = QueryClassifier()
    q_type, confidence = classifier.classify(query)

    policy = RoutingPolicy()
    strategy = policy.get_strategy(q_type, confidence)

    reasons = {
        "temporal": "Query contains temporal indicators (when, date, time, since...). Event log prioritized.",
        "factual": "Query asks for specific facts (who, what, where). Knowledge graph prioritized.",
        "multi-hop": "Query implies multi-hop reasoning (why, relationship, and where...). Graph expansion enabled.",
        "conversational": "Query is conversational (remember, talked about). Composite KG+vector strategy used.",
        "update": "Query is an update instruction. Invalidation strategy selected.",
    }

    return {
        "query": query,
        "classified_as": q_type,
        "confidence": confidence,
        "strategy_selected": strategy["strategy"],
        "cost_budget": strategy["cost_budget"],
        "policy_applied": strategy["policy_applied"],
        "reason": reasons.get(q_type, "Default routing based on query type."),
    }


@app.post("/memory/forget")
async def memory_forget_endpoint(request_data: dict):
    """Marks an event or entity as forgotten (soft delete). Raw log stays immutable."""
    event_id = request_data.get("event_id")
    entity = request_data.get("entity")
    reason = request_data.get("reason", "")
    
    """Marks an event or entity as forgotten (soft delete). Raw log stays immutable."""
    if event_id:
        reason_escaped = reason.replace("'", "''")
        sql = f"UPDATE {event_id} SET forgotten = true, forgotten_at = time::now(), forgotten_reason = '{reason_escaped}';"
        _query_surreal(sql)
        return {"forgotten_id": event_id, "type": "event", "reason": reason}

    if entity:
        entity_escaped = entity.replace("'", "''")
        find_sql = f"SELECT id FROM entity WHERE name CONTAINS '{entity_escaped}' LIMIT 1;"
        find_result = _query_surreal(find_sql)
        entities = _extract_result(find_result)
        if entities:
            entity_id = entities[0]["id"]
            reason_escaped = reason.replace("'", "''")
            sql = f"UPDATE {entity_id} SET forgotten = true, forgotten_at = time::now(), forgotten_reason = '{reason_escaped}';"
            _query_surreal(sql)
            return {"forgotten_id": entity_id, "type": "entity", "reason": reason}

    return {"error": "No valid event_id or entity provided", "reason": reason}


@app.post("/memory/consolidate")
async def memory_consolidate_endpoint(request_data: dict):
    """Triggers conservative maintenance: local patches or entity-scoped consolidation."""
    scope = request_data.get("scope", "local")
    entity = request_data.get("entity")
    
    """Triggers conservative maintenance: local patches or entity-scoped consolidation."""
    maintainer = ConservativeMaintainer(debounce_seconds=0)

    if scope == "entity" and entity:
        entity_escaped = entity.replace("'", "''")
        find_sql = f"SELECT id FROM entity WHERE name CONTAINS '{entity_escaped}' LIMIT 1;"
        find_result = _query_surreal(find_sql)
        entities = _extract_result(find_result, 1)
        if entities:
            entity_id = entities[0]["id"]
            maintainer.queue_patch_update(entity_id, {"last_consolidated": datetime.now(timezone.utc).isoformat()})
            maintainer.flush_pending()
            return {"scope": scope, "entity": entity, "entity_id": entity_id, "status": "consolidated"}

    if scope == "local":
        stale = maintainer.get_stale_facts(max_age_seconds=86400)
        return {"scope": scope, "stale_facts_found": len(stale), "status": "reviewed"}

    return {"error": "Invalid scope. Use 'local' or 'entity' with entity name.", "scope": scope}


if __name__ == "__main__":
    # Run both MCP and FastAPI servers
    import threading
    
    # Run MCP server
    mcp_thread = threading.Thread(target=mcp.run)
    mcp_thread.start()
    
    # Run FastAPI server
    uvicorn.run(app, host="127.0.0.1", port=8082)
