# -*- coding: utf-8 -*-
import asyncio
import time
import os
import sys
import platform
from datetime import datetime
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import the MCP server tools
from src.mcp.server import mcp

async def call_tool_safe(tool_name: str, args: dict):
    """Call a tool and return success/failure and duration."""
    start = time.perf_counter()
    try:
        await mcp.call_tool(tool_name, args)
        duration = (time.perf_counter() - start) * 1000
        return True, duration
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000
        return False, duration

async def run_concurrency_test(tool_name: str, args: dict, concurrency: int, total_requests: int):
    """Run a batch of requests in parallel."""
    print(f"Testing '{tool_name}' with concurrency={concurrency} (total={total_requests})...")
    
    start_total = time.perf_counter()
    
    tasks = []
    # We distribute total_requests into batches of 'concurrency' size
    results = []
    
    for i in range(0, total_requests, concurrency):
        batch_size = min(concurrency, total_requests - i)
        batch_tasks = [call_tool_safe(tool_name, args) for _ in range(batch_size)]
        batch_results = await asyncio.gather(*batch_tasks)
        results.extend(batch_results)
        
    end_total = time.perf_counter()
    total_duration_ms = (end_total - start_total) * 1000
    
    successes = [r for r in results if r[0]]
    failures = [r for r in results if not r[0]]
    latencies = [r[1] for r in successes]
    
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    throughput = len(results) / (total_duration_ms / 1000)
    
    print(f"  Done in {total_duration_ms:.2f}ms")
    print(f"  Success: {len(successes)} | Failures: {len(failures)}")
    print(f"  Throughput: {throughput:.2f} req/s")
    print(f"  Avg Latency: {avg_latency:.2f}ms")
    print()
    
    return {
        "tool": tool_name,
        "concurrency": concurrency,
        "total": total_requests,
        "success": len(successes),
        "failure": len(failures),
        "throughput": throughput,
        "avg_latency": avg_latency,
        "total_time_ms": total_duration_ms
    }

async def run_suite():
    timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"STRATA MCP Concurrency Test - {timestamp_str}")
    print("=" * 60)
    print(f"System: {platform.system()} {platform.release()}")
    print("=" * 60)
    
    # Warmup
    print("Warming up...")
    await mcp.call_tool("memory_stats", {})
    print("Ready.\n")

    concurrency_levels = [1, 5, 10, 25, 50]
    total_per_level = 50 # Total requests to run for each concurrency level
    
    all_results = []
    
    test_configs = [
        ("memory_query", {"query": "test query", "cost_budget": "low"}),
        ("memory_stats", {})
    ]
    
    for tool_name, args in test_configs:
        print(f"### Benchmarking Tool: {tool_name} ###")
        for c in concurrency_levels:
            res = await run_concurrency_test(tool_name, args, c, total_per_level)
            all_results.append(res)

    # Save to Markdown
    benchmark_dir = os.path.dirname(__file__)
    log_file = os.path.join(benchmark_dir, "concurrency_results.md")
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n## Concurrency Test Run: {timestamp_str}\n\n")
        f.write("| Tool | Concurrency | Total Req | Success | Failure | Throughput (req/s) | Avg Latency (ms) |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for r in all_results:
            f.write(f"| `{r['tool']}` | {r['concurrency']} | {r['total']} | {r['success']} | {r['failure']} | {r['throughput']:.2f} | {r['avg_latency']:.2f} |\n")
        f.write("\n---\n")
    
    print(f"[OK] Results logged to {log_file}")

if __name__ == "__main__":
    asyncio.run(run_suite())
