
import asyncio
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.planner.executor import PlanExecutor

async def test_retrieval():
    executor = PlanExecutor()
    
    queries = ["Was ist PyTorch?", "Wer ist Tobias?"]
    
    for query in queries:
        print(f"\n--- Testing query: {query} ---")
        plan = {
            "strategy": "hybrid_bm25_vector_temporal",
            "query": query
        }
        result = executor.execute_plan(plan)
        
        # Check for entities and facts
        res_raw = result.get('result', {})
        if isinstance(res_raw, dict) and 'result' in res_raw:
            res_data = res_raw['result']
        elif isinstance(res_raw, list):
            res_data = res_raw
        else:
            res_data = []
            
        print(f"Result type: {type(res_data)}")
        if res_data and len(res_data) > 0:
            print(f"First item type: {type(res_data[0])}")
            # print(f"First item: {res_data[0]}")
            
        entities = []
        facts = []
        events = []
        
        for r in res_data:
            if isinstance(r, dict):
                rid = r.get('id', '')
                if rid.startswith('entity:'):
                    entities.append(r)
                elif rid.startswith('fact:'):
                    facts.append(r)
                else:
                    events.append(r)
            else:
                print(f"Warning: Non-dict item in results: {r}")
        
        print(f"Strategy: {result.get('strategy')}")
        print(f"Entities found: {len(entities)}")
        for e in entities:
            print(f"  - Entity: {e.get('name')} ({e.get('id')})")
            
        print(f"Facts found: {len(facts)}")
        for f in facts:
            print(f"  - Fact: {f.get('id')}")
            
        print(f"Top 3 Events:")
        for e in events[:3]:
            print(f"  - [{e.get('hybrid_score', 0):.4f}] {e.get('content')}")

if __name__ == "__main__":
    asyncio.run(test_retrieval())
