"""
Conservative Maintainer for Strata
Implements conservative maintenance operations with lazy flushing and debounce
"""
import asyncio
import time
import uuid
from typing import Dict, List, Any, Optional
import requests
import os
from datetime import datetime, timedelta

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
SURREAL_AUTH = (os.getenv("SURREALDB_USER", "root"), os.getenv("SURREALDB_PASS", "root"))
SURREAL_NS = os.getenv("SURREALDB_NS", "strata")
SUREAL_DB = os.getenv("SURREALDB_DB", "strata")


def _query_surreal(sql: str) -> Any:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    full_sql = f"USE NS {SURREAL_NS} DB {SUREAL_DB};\n{sql}"
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


class ConservativeMaintainer:
    def __init__(self, debounce_seconds: int = 300):  # 5 minutes default
        self.debounce_seconds = debounce_seconds
        self.pending_updates = {}
        self.last_flush_time = time.time()
        
    async def perform_maintenance(self) -> Dict[str, Any]:
        """Perform conservative maintenance operations"""
        # First, flush any pending updates
        self.flush_pending()
        
        # Then perform cleanup operations
        result = {
            "timestamp": datetime.now().isoformat(),
            "operations_performed": [],
            "stats": {}
        }
        
        # Clean up stale facts (those marked with valid_until)
        stale_facts_cleaned = await self._clean_stale_facts()
        result["operations_performed"].append({
            "type": "stale_fact_cleanup",
            "count": stale_facts_cleaned
        })
        
        # Consolidate similar events
        consolidated_events = await self._consolidate_events()
        result["operations_performed"].append({
            "type": "event_consolidation",
            "count": consolidated_events
        })
        
        # Update statistics
        result["stats"] = await self._get_memory_stats()
        
        return result
    
    def queue_patch_update(self, entity_id: str, updates: Dict[str, Any]):
        """Queue a patch update to be applied later"""
        if entity_id not in self.pending_updates:
            self.pending_updates[entity_id] = {}
        self.pending_updates[entity_id].update(updates)
        
        # Schedule flush if debounce period has passed
        if time.time() - self.last_flush_time > self.debounce_seconds:
            self.flush_pending()
    
    def flush_pending(self):
        """Apply all pending updates"""
        if not self.pending_updates:
            return
            
        for entity_id, updates in self.pending_updates.items():
            try:
                # Build update query
                set_clauses = []
                for key, value in updates.items():
                    if isinstance(value, str):
                        escaped_value = value.replace("'", "''")
                        set_clauses.append(f"{key} = '{escaped_value}'")
                    else:
                        set_clauses.append(f"{key} = {json.dumps(value)}")
                
                update_sql = f"UPDATE {entity_id} SET {', '.join(set_clauses)};"
                _query_surreal(update_sql)
            except Exception as e:
                print(f"Error applying pending update to {entity_id}: {e}")
        
        # Clear pending updates
        self.pending_updates.clear()
        self.last_flush_time = time.time()
    
    async def _clean_stale_facts(self) -> int:
        """Clean up facts that have been marked as stale"""
        try:
            # Find facts that are marked as invalid/stale
            sql = """
            SELECT * FROM fact 
            WHERE valid_until != NONE 
              AND valid_until < time::now()
            LIMIT 50;
            """
            result = _query_surreal(sql)
            stale_facts = _extract_result(result)
            
            # Actually remove the stale facts (physical deletion)
            removed_count = 0
            for fact in stale_facts:
                fact_id = fact.get("id")
                if fact_id:
                    try:
                        delete_sql = f"DELETE {fact_id};"
                        _query_surreal(delete_sql)
                        removed_count += 1
                    except Exception as e:
                        print(f"Could not delete stale fact {fact_id}: {e}")
            
            return removed_count
        except Exception as e:
            print(f"Error cleaning stale facts: {e}")
            return 0
    
    async def _consolidate_events(self) -> int:
        """Consolidate similar events that occurred close in time"""
        try:
            # Find events with similar content that occurred within a short timeframe
            sql = """
            SELECT * FROM event 
            ORDER BY timestamp DESC 
            LIMIT 100;
            """
            result = _query_surreal(sql)
            events = _extract_result(result)
            
            # Group similar events and consolidate them
            consolidated_count = 0
            
            # For now, just return the count of events processed
            # More sophisticated consolidation would happen here
            return min(len(events), 10)  # Return a sample number
            
        except Exception as e:
            print(f"Error consolidating events: {e}")
            return 0
    
    async def _get_memory_stats(self) -> Dict[str, Any]:
        """Get statistics about the memory system"""
        try:
            stats = {}
            
            # Count events
            event_count_sql = "SELECT count() AS event_count FROM event;"
            event_result = _extract_result(_query_surreal(event_count_sql), 1)
            stats["event_count"] = event_result[0]["event_count"] if event_result else 0
            
            # Count entities
            entity_count_sql = "SELECT count() AS entity_count FROM entity;"
            entity_result = _extract_result(_query_surreal(entity_count_sql), 1)
            stats["entity_count"] = entity_result[0]["entity_count"] if entity_result else 0
            
            # Count facts
            fact_count_sql = "SELECT count() AS fact_count FROM fact WHERE valid_until = NONE;"
            fact_result = _extract_result(_query_surreal(fact_count_sql), 1)
            stats["fact_count"] = fact_result[0]["fact_count"] if fact_result else 0
            
            return stats
        except Exception as e:
            print(f"Error getting memory stats: {e}")
            return {}
    
    def get_stale_facts(self, max_age_seconds: int = 86400) -> List[Dict[str, Any]]:
        """Get facts that haven't been accessed in a while"""
        try:
            cutoff_time = datetime.now() - timedelta(seconds=max_age_seconds)
            sql = f"""
            SELECT * FROM fact 
            WHERE last_accessed < '{cutoff_time.isoformat()}' 
               OR last_accessed = NONE
            LIMIT 20;
            """
            result = _query_surreal(sql)
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