"""
Conservative Maintainer for sieveon — MANUAL trigger only (C2).

There is deliberately no background/auto-flush loop: the only production
entrypoint is the `memory_consolidate` MCP tool. `queue_patch_update` +
`debounce_seconds` batch patch-updates between explicit `flush_pending` /
`perform_maintenance` calls. Physical stale-fact deletion only happens
with `delete_stale=true`. Do not add auto-scheduling without updating
README + docs/mcp-server.md.
"""

import asyncio
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import httpx

from src.extraction.entropy_gate import escape_surrealql

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv is not installed, skip loading .env file
    pass

# Standard imports
import json

SURREAL_URL = os.getenv("SURREALDB_URL", "http://127.0.0.1:8000/sql")
SURREAL_AUTH = (
    os.getenv("SURREALDB_USER", "root"),
    os.getenv("SURREALDB_PASS", "root"),
)
SURREAL_NS = os.getenv("SURREALDB_NS", "sieveon")
SURREAL_DB = os.getenv("SURREALDB_DB", "sieveon")

_shared_async_client = None
_async_client_lock = asyncio.Lock()


async def _get_async_client() -> httpx.AsyncClient:
    global _shared_async_client
    if _shared_async_client is None:
        async with _async_client_lock:
            if _shared_async_client is None:
                _shared_async_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    return _shared_async_client


async def _query_surreal(sql: str) -> Any:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    full_sql = f"USE NS {SURREAL_NS} DB {SURREAL_DB};\n{sql}"
    client = await _get_async_client()
    try:
        response = await client.post(
            SURREAL_URL,
            content=full_sql,
            headers=headers,
            auth=SURREAL_AUTH,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("status") == "ERR":
                    raise RuntimeError(
                        f"SurrealDB Error: {item.get('information') or item.get('result')} | SQL: {sql[:120]}"
                    )
        return data
    except httpx.TimeoutException:
        raise RuntimeError(f"SurrealDB timeout: {sql[:120]}")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"SurrealDB HTTP {e.response.status_code}: {sql[:120]}")


def _extract_result(data: List[Dict], index: int = 1) -> List[Dict]:
    """Extract results from SurrealDB response.

    Delegates to src.mcp.core._extract_result so both modules share one
    index semantic (index=1 -> first data-carrying statement, LET/BEGIN/
    COMMIT and USE responses are skipped). Falls back to a local copy with
    the same semantic when the core import is unavailable.
    """
    try:
        from src.mcp.core import _extract_result as _core_extract

        return _core_extract(data, index)
    except Exception:
        pass
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


_RECORD_ID_RE = re.compile(r"^(entity|fact|event|fact_history):[A-Za-z0-9_]+$")

# Field names are interpolated unquoted into UPDATE ... SET, so they must be
# strict identifiers -- escaping cannot make them safe (same reason record ids
# need _RECORD_ID_RE instead of escape_surrealql).
_FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_record_id(value: Any) -> bool:
    """Strict record-id check, canonical with src.mcp.core._is_record_id.

    Local copy to avoid importing the MCP stack (httpx/FastMCP) from the
    maintenance module; keep the two patterns in sync.
    """
    try:
        from src.mcp.core import _is_record_id as _core_check

        return bool(_core_check(value))
    except Exception:
        return bool(_RECORD_ID_RE.match(str(value or "")))


def _archive_fact_sqls(fact: Dict[str, Any]) -> Tuple[str, str]:
    """Build (CREATE fact_history, DELETE original) for one stale fact.

    Pure (no IO), so the no-loss guarantee is unit-testable. The archived
    copy keeps the original id suffix (fact_history:<suffix>), the record
    links (in/out stay real links, not strings, so graph reads keep
    working), validity window, confidence, plus archived_at. Raises
    ValueError when the row cannot be archived losslessly.
    """
    fid = str(fact.get("id") or "")
    if not _RECORD_ID_RE.match(fid):
        raise ValueError(f"cannot archive fact without valid id: {fid!r}")
    suffix = fid.split(":", 1)[1]

    def _link(value: Any, role: str) -> str:
        if isinstance(value, dict):
            value = value.get("id")
        link = str(value or "")
        if not _RECORD_ID_RE.match(link):
            raise ValueError(f"cannot archive {fid}: invalid {role} link {link!r}")
        return link

    in_id = _link(fact.get("in"), "in")
    out_id = _link(fact.get("out"), "out")

    try:
        conf = float(fact.get("confidence") or 0.0)
    except (TypeError, ValueError):
        raise ValueError(f"cannot archive {fid}: invalid confidence")

    def _dt(value: Any) -> str:
        if value is None or value == "NONE":
            return "NONE"
        return f"type::datetime('{escape_surrealql(str(value))}')"

    predicate = escape_surrealql(str(fact.get("predicate") or ""))
    archived_id = escape_surrealql(fid)
    create_sql = (
        f"CREATE fact_history:{suffix} SET archived_id = '{archived_id}', "
        f"predicate = '{predicate}', in = {in_id}, out = {out_id}, "
        f"confidence = {conf}, valid_from = {_dt(fact.get('valid_from'))}, "
        f"valid_until = {_dt(fact.get('valid_until'))}, "
        f"archived_at = time::now();"
    )
    delete_sql = f"DELETE {fid};"
    return create_sql, delete_sql


class ConservativeMaintainer:
    def __init__(self, debounce_seconds: int = 300):  # 5 minutes default
        self.debounce_seconds = debounce_seconds
        self.pending_updates = {}
        self.last_flush_time = time.time()

    async def perform_maintenance(self) -> Dict[str, Any]:
        """Perform conservative maintenance operations"""
        # First, flush any pending updates
        await self.flush_pending()

        # Then perform cleanup operations
        result = {
            "timestamp": datetime.now().isoformat(),
            "operations_performed": [],
            "stats": {},
        }

        # Clean up stale facts (those marked with valid_until)
        stale_facts_cleaned = await self._clean_stale_facts()
        result["operations_performed"].append(
            {"type": "stale_fact_cleanup", "count": stale_facts_cleaned}
        )

        # Consolidate similar events
        consolidated_events = await self._consolidate_events()
        result["operations_performed"].append(
            {"type": "event_consolidation", "count": consolidated_events}
        )

        # Update statistics
        result["stats"] = await self._get_memory_stats()

        return result

    async def queue_patch_update(self, entity_id: str, updates: Dict[str, Any]):
        """Queue a patch update to be applied later"""
        if not _is_record_id(entity_id):
            print(f"Refusing to queue patch update with invalid record id: {entity_id!r}")
            return
        if entity_id not in self.pending_updates:
            self.pending_updates[entity_id] = {}
        self.pending_updates[entity_id].update(updates)

        # Schedule flush if debounce period has passed
        if time.time() - self.last_flush_time > self.debounce_seconds:
            await self.flush_pending()

    async def flush_pending(self):
        """Apply all pending updates"""
        if not self.pending_updates:
            return

        for entity_id, updates in self.pending_updates.items():
            try:
                # entity_id is interpolated unquoted into UPDATE -- escaping
                # cannot make an identifier safe, so fail closed on shape.
                if not _is_record_id(entity_id):
                    print(f"Refusing patch update with invalid record id: {entity_id!r}")
                    continue
                # Build update query
                set_clauses = []
                for key, value in updates.items():
                    if not isinstance(key, str) or not _FIELD_NAME_RE.match(key):
                        print(f"Refusing patch update with invalid field name: {key!r}")
                        continue
                    if isinstance(value, str):
                        escaped_value = escape_surrealql(value)
                        set_clauses.append(f"{key} = '{escaped_value}'")
                    else:
                        set_clauses.append(f"{key} = {json.dumps(value)}")

                if not set_clauses:
                    continue
                update_sql = f"UPDATE {entity_id} SET {', '.join(set_clauses)};"
                await _query_surreal(update_sql)
            except Exception as e:
                print(f"Error applying pending update to {entity_id}: {e}")

        # Clear pending updates
        self.pending_updates.clear()
        self.last_flush_time = time.time()

    async def _clean_stale_facts(self) -> int:
        """Archive stale facts to fact_history, then remove the originals.

        Invalidated facts (valid_until in the past) are moved, never
        silently dropped: at_time queries and audits keep working against
        fact_history. Returns the archived count.
        """
        try:
            # Find facts that are marked as invalid/stale
            sql = """
            SELECT * FROM fact
            WHERE valid_until != NONE
              AND valid_until < time::now()
            LIMIT 50;
            """
            result = await _query_surreal(sql)
            stale_facts = _extract_result(result)

            # Archive each fact before removal (no-loss guarantee)
            removed_count = 0
            for fact in stale_facts:
                fact_id = fact.get("id")
                if not fact_id:
                    continue
                try:
                    create_sql, delete_sql = _archive_fact_sqls(fact)
                    await _query_surreal(create_sql)
                    await _query_surreal(delete_sql)
                    removed_count += 1
                except Exception as e:
                    print(f"Could not archive stale fact {fact_id}: {e}")

            return removed_count
        except Exception as e:
            print(f"Error cleaning stale facts: {e}")
            return 0

    async def _consolidate_events(self) -> int:
        """Deduplicate events with identical content_hash within 1-hour windows."""
        try:
            sql = """
            SELECT id, content_hash, timestamp, source
            FROM event
            WHERE forgotten = false
            ORDER BY timestamp DESC
            LIMIT 500;
            """
            result = await _query_surreal(sql)
            events = _extract_result(result)
            if not events:
                return 0

            from collections import defaultdict
            buckets = defaultdict(list)
            for ev in events:
                key = ev.get("content_hash") or ev.get("content", "")[:50]
                buckets[key].append(ev)

            consolidated_count = 0
            for key, group in buckets.items():
                if len(group) < 2:
                    continue
                group.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
                # group[0] is the newest event and is kept; the rest are forgotten
                for dup in group[1:]:
                    dup_id = dup.get("id")
                    if not dup_id:
                        continue
                    if not _is_record_id(dup_id):
                        print(f"Refusing to consolidate invalid record id: {dup_id!r}")
                        continue
                    try:
                        forget_sql = f"UPDATE {dup_id} SET forgotten = true, forgotten_reason = 'consolidated_duplicate';"
                        await _query_surreal(forget_sql)
                        consolidated_count += 1
                    except Exception as e:
                        print(f"Could not consolidate event {dup_id}: {e}")

            return consolidated_count

        except Exception as e:
            print(f"Error consolidating events: {e}")
            return 0

    async def _get_memory_stats(self) -> Dict[str, Any]:
        """Get statistics about the memory system"""
        try:
            # Get event count
            result = await _query_surreal(
                "SELECT count() AS count FROM event GROUP ALL;"
            )
            extracted = _extract_result(result)
            event_count = extracted[0].get("count", 0) if extracted else 0

            # Get entity count
            result = await _query_surreal(
                "SELECT count() AS count FROM entity GROUP ALL;"
            )
            extracted = _extract_result(result)
            entity_count = extracted[0].get("count", 0) if extracted else 0

            # Get fact count
            result = await _query_surreal(
                "SELECT count() AS count FROM fact WHERE valid_until = NONE GROUP ALL;"
            )
            extracted = _extract_result(result)
            fact_count = extracted[0].get("count", 0) if extracted else 0

            return {
                "event_count": event_count,
                "entity_count": entity_count,
                "fact_count": fact_count,
            }
        except Exception as e:
            print(f"Error getting memory stats: {e}")
            return {}

    async def get_stale_facts(
        self, max_age_seconds: int = 86400
    ) -> List[Dict[str, Any]]:
        """Get facts that haven't been accessed in a while"""
        try:
            cutoff_time = datetime.now() - timedelta(seconds=max_age_seconds)
            sql = f"""
            SELECT * FROM fact
            WHERE last_accessed < '{cutoff_time.isoformat()}'
               OR last_accessed = NONE
            LIMIT 20;
            """
            result = await _query_surreal(sql)
            return _extract_result(result)
        except Exception as e:
            print(f"Error getting stale facts: {e}")
            return []


# Example usage
if __name__ == "__main__":

    async def test_maintainer():
        maintainer = ConservativeMaintainer()
        result = await maintainer.perform_maintenance()
        print("Maintenance completed:", result)

    asyncio.run(test_maintainer())
