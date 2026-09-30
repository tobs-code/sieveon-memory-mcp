
import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.planner.executor import PlanExecutor


async def run_retrieval_demo():
    executor = PlanExecutor()

    queries = ["Was ist PyTorch?", "Wer ist Tobias?"]

    for query in queries:
        print(f"\n--- Testing query: {query} ---")
        result = await executor.execute_plan(
            "hybrid_bm25_vector_temporal", query, "medium"
        )

        if result.get("error"):
            print(f"Error: {result['error']} ({result.get('error_type')})")

        entities = result.get("entities", [])
        facts = result.get("facts", [])
        events = result.get("events", [])

        print(f"Strategy: {result.get('strategy')}")
        print(f"Metadata: {result.get('execution_metadata')}")

        print(f"Entities found: {len(entities)}")
        for e in entities:
            print(f"  - Entity: {e.get('name')} ({e.get('id')})")

        print(f"Facts found: {len(facts)}")
        for f in facts:
            print(f"  - Fact: {f.get('id')}")

        print("Top 3 Events:")
        for e in events[:3]:
            print(f"  - [{e.get('relevance_score', 0):.4f}] {e.get('content')}")


if __name__ == "__main__":
    asyncio.run(run_retrieval_demo())
