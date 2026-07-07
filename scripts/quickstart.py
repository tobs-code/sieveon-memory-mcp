"""
Sieveon — Interactive quickstart demo.

Usage:
    python scripts/quickstart.py

Walks through the core features of Sieveon:
  • memory_store  – store an event
  • memory_stats  – inspect the system
  • memory_query  – ask questions
  • graph_traverse – explore the knowledge graph

Prerequisites: SurrealDB running (via `python scripts/setup.py` or manually).
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("TQDM_DISABLE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

# ── helpers ──────────────────────────────────────────────────────────────

def banner(text):
    n = len(text) + 4
    print(f"\n  {'=' * n}")
    print(f"  {text}")
    print(f"  {'=' * n}\n")


def step(n, label):
    print(f"\n  ── Step {n}: {label} ──\n")


def ok(msg):
    print(f"  ✅ {msg}")


def info(msg):
    print(f"  ℹ️  {msg}")


def show_json(obj):
    print(json.dumps(obj, indent=2, default=str))


# ── demo ─────────────────────────────────────────────────────────────────

async def check_surreal():
    """Quick connectivity check via HTTP + docker ps fallback."""
    import urllib.request, urllib.error, base64
    url = "http://127.0.0.1:8000/sql"
    payload = "USE NS sieveon DB sieveon; SELECT 1 AS ping;"
    token = base64.b64encode(b"root:root").decode()
    headers = {
        "Accept": "application/json",
        "Content-Type": "text/plain",
        "Authorization": f"Basic {token}",
    }
    try:
        req = urllib.request.Request(url, data=payload.encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        pass
    # Fallback: check docker container
    import subprocess
    try:
        r = subprocess.run(
            ["docker", "ps", "--filter", "name=sieveon-surrealdb", "--format", "{{.Status}}"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0 and "healthy" in r.stdout.lower()
    except Exception:
        return False


async def step_1_store():
    """Store sample events."""
    from src.mcp.common_logic import _store_content

    banner("Step 1 — Storing Events")

    items = [
        "Alice is a software engineer at Acme Corp in Berlin.",
        "Alice worked on the quantum ledger project with Bob.",
        "Bob is a data scientist at Beta Corp in Munich.",
        "The quantum ledger project uses PostgresML for vector search.",
        "Acme Corp is planning to open an office in Barcelona next year.",
    ]

    for text in items:
        info(f"Storing: \"{text}\"")
        result = await _store_content(text, source="quickstart_demo")
        decision = result.get("gate", {}).get("decision", "n/a")
        eid = result.get("event_id", "?")[:20]
        ok(f"event={eid}… | gate={decision}")
        await asyncio.sleep(0.3)

    print()


async def step_2_stats():
    """Show system stats."""
    from src.mcp.tools import memory_stats

    banner("Step 2 — System Statistics")
    stats = await memory_stats()
    show_json(stats)
    print()


async def step_3_query(query: str):
    """Run a memory query."""
    from src.mcp.tools import memory_query

    banner(f"Step 3 — Query: \"{query}\"")
    result = await memory_query(query, limit=5)
    info(f"Classified as: {result['classified_as']}  (confidence: {result['confidence']})")
    info(f"Strategy: {result['strategy']}  |  Budget: {result['cost_budget']}")
    print()

    summary = result.get("summary", {})
    if summary.get("found"):
        ok(summary["answer"])
    else:
        info("No results found.")
    print()


async def step_4_graph():
    """Graph traversal demo."""
    from src.mcp.tools import graph_traverse

    banner("Step 4 — Graph Traversal")
    info("Starting from 'Alice', walking 2 hops …")
    result = await graph_traverse("Alice", max_depth=2)

    if result.get("status") == "ok":
        ok(f"Found {result['node_count']} nodes, {result['edge_count']} edges, {result['path_count']} paths")
        print()
        for path in result.get("paths", [])[:5]:
            labels = [f"{seg['from']} ──{seg['predicate']}──▶ {seg['to']}" for seg in path]
            print(f"    {'  ➡  '.join(labels)}")
    else:
        info(f"Graph traversal: {result}")
    print()


async def step_5_list():
    """List entities and events."""
    from src.mcp.tools import list_entities, list_events

    banner("Step 5 — Browse the Knowledge Graph")

    info("Entities:")
    ents = await list_entities(limit=10)
    for e in ents.get("entities", []):
        print(f"    • {e['name']}  ({e.get('type', '?')})")

    print()
    info("Recent events:")
    evts = await list_events(limit=5)
    for ev in evts.get("events", []):
        content = ev.get("content", "")[:80]
        print(f"    • {content}…")


async def main():
    print()
    print("  ╔════════════════════════════════════════════╗")
    print("  ║     Sieveon — Interactive Quickstart      ║")
    print("  ║     Agent Memory System Demo              ║")
    print("  ╚════════════════════════════════════════════╝")
    print()

    if not await check_surreal():
        print("  ❌ SurrealDB is not reachable at http://127.0.0.1:8000.")
        print()
        print("  Start it with:")
        print("     python scripts/setup.py")
        print("  or manually:")
        print("     docker-compose up -d")
        print("     python scripts/load_schema_optimized.py")
        sys.exit(1)

    ok("SurrealDB is running")
    print()

    await step_1_store()
    await asyncio.sleep(0.5)

    await step_2_stats()
    await asyncio.sleep(0.3)

    await step_3_query("Where does Alice work?")
    await asyncio.sleep(0.3)

    await step_3_query("What projects is Alice working on?")
    await asyncio.sleep(0.3)

    await step_3_query("Tell me about the quantum ledger project")
    await asyncio.sleep(0.3)

    await step_4_graph()
    await asyncio.sleep(0.3)

    await step_5_list()

    print()
    print("  ╔════════════════════════════════════════════╗")
    print("  ║  Demo complete!                           ║")
    print("  ║                                           ║")
    print("  ║  Next: start the MCP server               ║")
    print("  ║    python -m src.mcp.server               ║")
    print("  ║                                           ║")
    print("  ║  Or dive into the docs:                   ║")
    print("  ║    docs/mcp-server.md                     ║")
    print("  ╚════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    asyncio.run(main())
