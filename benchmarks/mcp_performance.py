# -*- coding: utf-8 -*-
import asyncio
import time
import statistics
import json
import os
import sys
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import the MCP server tools
from src.mcp.server import mcp

async def benchmark_tool(tool_name: str, args: dict, iterations: int = 10):
    """Benchmark a specific tool for a number of iterations."""
    print(f"--- Benchmarking '{tool_name}' ({iterations} iterations) ---")
    
    latencies = []
    errors = 0
    
    # Warmup
    try:
        await mcp.call_tool(tool_name, args)
    except Exception as e:
        print(f"Warmup failed for {tool_name}: {e}")
        return None

    for i in range(iterations):
        start_time = time.perf_counter()
        try:
            await mcp.call_tool(tool_name, args)
            end_time = time.perf_counter()
            latencies.append((end_time - start_time) * 1000) # ms
        except Exception as e:
            errors += 1
            print(f"Error in iteration {i}: {e}")
        
    if not latencies:
        return None
        
    avg = sum(latencies) / len(latencies)
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    min_lat = min(latencies)
    max_lat = max(latencies)
    
    print(f"  Avg: {avg:.2f}ms")
    print(f"  P95: {p95:.2f}ms")
    print(f"  Min/Max: {min_lat:.2f}ms / {max_lat:.2f}ms")
    print(f"  Errors: {errors}")
    print()
    
    return {
        "tool": tool_name,
        "avg": avg,
        "p95": p95,
        "min": min_lat,
        "max": max_lat,
        "errors": errors
    }

import io
import sys
import platform

async def run_suite():
    timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Capture stdout
    stdout_capture = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = stdout_capture
    
    try:
        print(f"STRATA MCP Performance Benchmark - {timestamp_str}")
        print("=" * 60)
        print(f"System: {platform.system()} {platform.release()} ({platform.machine()})")
        print(f"Python: {platform.python_version()}")
        print("=" * 60)
        print()
        
        results = []
        
        # Core Tools
        results.append(await benchmark_tool("memory_stats", {}))
        
        results.append(await benchmark_tool("memory_store", {
            "content": "Benchmark test event for performance measurement.",
            "source": "benchmark",
            "metadata": {"type": "test"}
        }))
        
        results.append(await benchmark_tool("memory_query", {
            "query": "What is the benchmark testing?",
            "cost_budget": "low"
        }))
        
        # Search Tools
        results.append(await benchmark_tool("semantic_search", {
            "query": "performance benchmark",
            "top_k": 5
        }))
        
        results.append(await benchmark_tool("event_log_search", {
            "query": "benchmark",
            "limit": 10
        }))
        
        # Graph Tools
        results.append(await benchmark_tool("kg_query", {
            "limit": 5
        }))
        
        # Introspection
        results.append(await benchmark_tool("explain_routing", {
            "query": "How is the performance?"
        }))

        # Summary table in console
        print("=" * 60)
        print(f"{'Tool':<20} | {'Avg (ms)':>10} | {'P95 (ms)':>10} | {'Errors':>6}")
        print("-" * 60)
        for r in results:
            if r:
                print(f"{r['tool']:<20} | {r['avg']:>10.2f} | {r['p95']:>10.2f} | {r['errors']:>6}")
        print("=" * 60)

    finally:
        # Restore stdout
        sys.stdout = original_stdout
        
    # Get the captured output
    full_output = stdout_capture.getvalue()
    print(full_output) # Still print to console

    # Save to Markdown
    benchmark_dir = os.path.dirname(__file__)
    log_file = os.path.join(benchmark_dir, "benchmark_results.md")
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n## Benchmark Run: {timestamp_str}\n\n")
        
        f.write("### Summary\n\n")
        f.write("| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: |\n")
        for r in results:
            if r:
                f.write(f"| `{r['tool']}` | {r['avg']:.2f} | {r['p95']:.2f} | {r['min']:.2f} | {r['max']:.2f} | {r['errors']} |\n")
        
        f.write("\n### Full Execution Logs\n\n")
        f.write("```text\n")
        f.write(full_output)
        f.write("```\n")
        f.write("\n---\n")
    
    print(f"[OK] Results and full logs appended to {log_file}")

if __name__ == "__main__":
    asyncio.run(run_suite())
