# Sieveon

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![SurrealDB](https://img.shields.io/badge/SurrealDB-3.1.5-8B5CF6)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![arXiv](https://img.shields.io/badge/arXiv-2606.24775-b31b1b)
![PRs](https://img.shields.io/badge/PRs-welcome-brightgreen)

> A workload-adaptive agent memory system combining event logs, knowledge graphs, and vector embeddings. Inspired from [Zhou et al. arXiv:2606.24775](https://arxiv.org/abs/2606.24775).

---

## Overview

Sieveon is an agent memory system that intelligently classifies, routes, plans, and executes queries across multiple storage and retrieval strategies. It consists of a **Python-based Control Plane** (MCP Server) that interfaces with SurrealDB for storage and retrieval operations.

### Architecture

```
                  ┌─────────────────────────┐
                  │  MCP Server             │  (Python, stdio)
                  │  18 tools + 6 resources │
                  │  Classifier → QueryType │
                  │  RoutingPolicy → Strategy + Budget
                  │  RetrievalExecutor → FTX / Vector / KG / Temporal
                  │  EntropyGate → KG Extraction
                  │  Maintenance → Forgetting / Consolidation
                  └──────┬──────────────────┘
                         │
                         ▼
        ┌─────────────────────────────┐
        │     SurrealDB Storage       │
        │  (NS:sieveon DB:sieveon)    │
        │  event / entity / fact /    │
        │  gate_log / _schema_migrations
        └─────────────────────────────┘
```

`memory_query` classifies via `QueryClassifier`, selects a strategy via
`RoutingPolicy` and executes it via `RetrievalExecutor`. Direct tools like
`event_log_search` and `semantic_search` bypass classification for explicit lookups.

### Python Components

| Component | Path | Description |
|-----------|------|-------------|
| **MCP Server** | `src/mcp/server.py` | Control plane (Anthropic MCP protocol) — stdio mode. 18 tools + 6 MCP resources: `memory_store`, `memory_store_batch`, `memory_store_markdown`, `memory_query`, `memory_update`, `memory_get`, `event_log_search`, `kg_query`, `graph_traverse`, `semantic_search`, `list_entities`, `list_events`, `memory_stats`, `memory_explain_routing`, `memory_forget`, `memory_unforget`, `memory_consolidate`, `memory_merge_entities`; Resources: `sieveon://stats`, `sieveon://entity/{id}`, `sieveon://event/{id}`, `sieveon://kg/subject/{name}`, `sieveon://kg/predicate/{type}`, `sieveon://search/{query}` |
| **Extraction** | `src/extraction/` | Entropy-gated entity extraction with Groq API (llama-3.1-8b-instant) or spaCy fallback. Pipe-separated LLM prompt, type preservation |
| **Classifier** | `src/extraction/classifier.py` | Hybrid ML+Regex query classifier: sklearn LogisticRegression on Qwen3-Embedding-0.6B embeddings (1024d) + TF-IDF (500 unigrams+bigrams), with regex fallback when ML confidence < 0.6. Synthetic training data generator at `scripts/generate_synthetic_training_data.py`, manual labeling CLI at `scripts/label_queries.py` |
| **Migrations** | `src/mcp/migrations.py` | Versioned auto-migration engine for breaking schema changes |
| **Router** | `src/router/` | Query classification policy + budget tracking: `policy.py` (RoutingPolicy, strategy per QueryType), `budget.py` (BudgetTracker, BudgetLevel), `cost_awareness.py` (CostTracker effectiveness ranking) |
| **Planner** | `src/planner/executor.py` | No separate `Planner` class — retrieval execution only: `RetrievalExecutor.execute_strategy()` + `PlanExecutor.execute_plan()` run the strategy chosen by the Router |
| **Maintenance** | `src/maintenance/conservative_maintainer.py` | Internal conservative maintainer (debounced patch updates, stale-fact cleanup, duplicate consolidation). Only MCP entrypoint is `memory_consolidate` |
| **Chunking** | `src/mcp/chunking.py` | Overlapping `char`/`token`/`semantic` chunking engine with YAML front matter parsing, table/HTML fence protection, image stripping (alt-text preserved), heading context prepended to each chunk |

---

## Key Features

- **Query Classification** — 5 types: Temporal, Factual, Multi-Hop, Conversational, Update. Hybrid approach: sklearn LogisticRegression on Qwen3-Embedding-0.6B embeddings (1024d) **+ TF-IDF (500 unigrams+bigrams)** with regex fallback when ML confidence < 0.6. Trained on synthetic (500), TREC (2000 capped), and CoQA (800) data.
  - **5-fold CV F1-macro** (primary metric, n=900, 200/class before split): **0.967 ± 0.010**
  - Clean holdout F1-macro (excl. ~9% synthetic template collisions): **~0.96**
  - Full holdout F1-macro (n=180, incl. ~9% leakage): 0.995 — but 5-fold CV is the reliable number
  - factual recall improved from 0.925 (embeddings only) to **0.975 (+TF-IDF)**
  - **0.6-threshold accuracy**: 100% (106/106 samples above threshold)
  - **Caveats:** (1) TREC original 6 labels were heuristically mapped to 3 Sieveon types (ABBR/ENTY/HUM/LOC → factual, NUM/time → temporal, DESC/why → multi-hop); original labels discarded. (2) CoQA mapped 100% → conversational. (3) Synthetic data uses templates → ~9% exact duplicates across any random train/test split. (4) Internal eval on synthetic + TREC + CoQA only — not yet validated on real agent traffic.
  - Run `python scripts/eval_classifier.py` to reproduce.
- **Adaptive Retrieval** — `memory_query` (classify → route → execute) selects per query type (event log, KG, hybrid BM25+vector+temporal). Direct tools (`event_log_search`, `semantic_search`, `kg_query`, `graph_traverse`) bypass the router for explicit lookups
- **Entropy Gating** — Composite score: Shannon character entropy + gzip compression ratio (Kolmogorov complexity proxy) + embedding novelty. Raw Event Log is always append-only; the gate decides only whether to extract into the Knowledge Graph.
- **Entity Extraction** — Groq API (`llama-3.1-8b-instant`) with spaCy fallback. Pipe-separated LLM prompt, type preservation (LLM classification preferred over heuristic).
- **Logical Invalidation** — `valid_until` timestamps instead of hard deletes. `memory_update` auto-creates target entities if they don't exist yet.
- **Forgetting & Consolidation** — `memory_forget` soft-deletes events or entities; `memory_consolidate` (sole MCP entrypoint) triggers `ConservativeMaintainer` runs (with optional physical stale-fact removal).
- **Cost Awareness** — Tracks & budgets resource consumption per strategy
- **Tool notes** — `memory_stats` accepts optional `aggregate` (`none`/`events_by_source`/`facts_by_predicate`/`entities_by_type`/`all`); the extra `random_string` param exists only for MCP no-required-args compatibility — call with no args.

---

## Quick Start

### Prerequisites

- Python 3.10+
- Docker + Docker Compose (for SurrealDB)

### One-command setup

```bash
# Everything: checks → Docker → schema → tests
python scripts/setup.py
```

### Or step by step

```bash
# 1. Copy environment config
cp .env.example .env

# 2. Start SurrealDB (Docker)
docker-compose up -d

# 3. Load schema & test data
python scripts/load_schema_optimized.py

# 4. Run all tests
python tests/run_all_tests.py
```

### Interactive demo

```bash
# After setup, explore the features interactively:
python scripts/quickstart.py
```

### Start Services

```bash
# Terminal 1 — MCP Server (Python)
python -m src.mcp.server
```

The server speaks MCP over stdin/stdout. Most MCP clients start the server as a subprocess and communicate via JSON-RPC.

#### Configuration in Claude Desktop (Example)

```json
{
  "mcpServers": {
    "Sieveon-memory": {
      "command": "python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "C:\\workspace\\Sieveon",
      "env": {
        "PYTHONPATH": "C:\\workspace\\Sieveon"
      }
    }
  }
}
```

#### Configuration in Cursor / VS Code

In `.cursor/mcp.json` or via the VS Code MCP extension:

```json
{
  "servers": {
    "Sieveon-memory": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

---

## Performance & Benchmarks

Sieveon has an integrated benchmark system to measure tool latency. Results are automatically logged to `benchmarks/benchmark_results.md`.

### Tool Performance (as of July 2026, warm SurrealDB, CPU-only embeddings)

| Tool | Average (ms) | P95 (ms) | Notes |
|------|-------------:|---------:|-------|
| `memory_stats` | ~165 | ~182 | COUNT indexes + parallel async queries |
| `memory_store` | ~842 | ~874 | SentenceTransformers (CPU) + Entropy Gate + Dedup |
| `memory_query` | ~405 | ~435 | Hybrid retrieval (classify → plan → execute) |
| `semantic_search` | ~155 | ~171 | HNSW vector index + `forgotten=false` |
| `event_log_search` | ~97 | ~107 | COUNT index + `forgotten=false` |
| `kg_query` | ~405 | ~437 | Indexed record lookups + `forgotten=false` |
| `memory_explain_routing` | ~0.20 | ~0.23 | Pure in-process logic |

### Run Benchmarks

```bash
python benchmarks/mcp_performance.py
```

---

## Testing

```bash
# All tests 
python tests/run_all_tests.py
python benchmarks/mcp_performance.py
```

---

## Entropy Gating — How It Works

The gate prevents the Knowledge Graph from being flooded with low-value entries.

**Formula:**

```
composite = alpha * normalized_text_entropy + gamma * compression_ratio + beta * embedding_novelty
```

- **Text entropy** = Shannon entropy on character level (alphanumeric + whitespace), normalized to `[0, 1]` using a max of ~4.5 bits.
- **Compression ratio** = `len(gzip.compress(text)) / len(text)` — a Kolmogorov complexity proxy via gzip. Higher values mean the text is less compressible, indicating higher informational content. Falls back to `0.5` for texts under 20 characters (unstable at very short lengths). This captures semantic density that pure character entropy misses (e.g. `"aaaaaaaaab"` and `"the cat sat"` can have similar Shannon entropy but very different compression ratios).
- **Embedding novelty** = `1 − avg cosine similarity` to the top-5 most similar previously stored embeddings (queried via SurrealDB native vector search).
- **Weights** (default): `alpha = 0.25` (Shannon), `gamma = 0.25` (compression ratio), `beta = 0.50` (embedding novelty).
- **Threshold** (adaptive): starts at `0.30` (cold start) and ramps linearly to `0.55` after ~150 events.

**Decision:** `extract` if `composite >= threshold`, otherwise `ignore`.

**Near-duplicate guardrail:** embedding novelty (`1 − avg similarity` to top-5 existing) is compared against an adaptive `min_novelty` ramping from `0.05` (cold start) to `0.20` (mature DB). A value below the ramp raises a `near_duplicate_warning` flag only — there is no hard skip; the composite score decides (`extract` vs `ignore`). Uses SurrealDB native vector search with event_id exclusion to prevent self-matches.

**Diversity guardrails (pre-filter):** Short texts (≤150 chars) are checked for `character_diversity < 0.15`; longer texts use `word_diversity < 0.20`. This blocks noise ("aaaa...", "test test...") while allowing normal English text of any length to pass through to the composite score.

**Length guardrails:** texts shorter than `min_length = 10` or longer than `max_length = 2000` characters are always skipped.

**Storage contract:** Every input is still written to the immutable Raw Event Log. The gate only controls whether the content is additionally extracted into the temporal Knowledge Graph.

**Logging:** Each decision is recorded in the `gate_log` table (including `compression_ratio`) for later calibration/evaluation.

**Calibration note:** `alpha`, `beta`, `gamma`, and `threshold` are currently **initial defaults**. Use the logged `gate_log` entries to tune them against real traffic and find the sweet spot for your workload.

**MCP path status:** The current MCP memory tools (`memory_store`, query endpoints) write to the raw event log **and invoke the entropy gate**. The `memory_store` tool calls `EntropyGate.ingest()` which logs decisions to `gate_log` for calibration.

---

## Resilience & Error Handling

**Implemented in `src/mcp/server.py`:**

- **Retry:** up to **3 attempts** by default; heavy queries (`RELATE`/`DEFINE`/`CREATE`) use **2 attempts**.
- **Jittered backoff:** full jitter (`uniform(0, min(8s, 0.5 * 2^level))`) to avoid thundering herd.
- **Circuit breaker:** opens after **5 failures**; half-open probe after **10s** quiet period.
- **Background Reconnect:** A dedicated async task periodically probes SurrealDB when the circuit is open, ensuring automatic recovery.
- **Thread safety:** circuit state protected by a lock; successful calls reset failure count and backoff level.
- **Timeouts:** `timeout=30` seconds per HTTP call to SurrealDB.

---

## Cost Model & Adaptive Enforcement

Budgets are measured and enforced per execution, and adaptively scaled based on global system health.

| Budget | Base limit | Strategy examples | Enforcement |
|--------|------------|-------------------|-------------|
| `low` | <= 10 DB calls / 1k tokens | KG-first | result truncation |
| `medium` | <= 25 DB calls / 3k tokens | Hybrid BM25+vector+temporal | result truncation |
| `high` | <= 50 DB calls / 8k tokens | Graph expansion + invalidation | best-effort truncation |

- **Adaptive Scaling:** Limits are automatically scaled down based on a **System Health Factor** (`BudgetTracker.get_system_health()`, range `0.1–1.0`). It is set to `1.0` on successful SurrealDB calls and lowered on failures (`src/mcp/core.py`); low health (< 0.5) also reduces retry attempts. Read it via `get_system_health()` — do not access the private `BudgetTracker._health_factor` directly.
- **Token counting:** uses `tiktoken` (`gpt-3.5-turbo` encoding) where available; otherwise falls back to `chars/4`.
- **BudgetTracker:** records `db_calls` and `estimated_tokens` and exposes `OverBudget` for aborts/throttling.

---

## Schema Evolution / Migration

Breaking schema changes (renaming fields, changing types) are rolled out **automatically** via the versioned migration system.

- **Engine:** `src/mcp/migrations.py` — `MigrationEngine` with registry pattern
- **Tracking:** The `_schema_migrations` table in SurrealDB stores applied versions (incl. checksum)
- **Auto-start:** `ensure_schema_loaded()` in `src/mcp/core.py` runs pending migrations on server startup
- **Adding a new migration:** register it in `_register_builtin()`:

```python
engine.register(Migration(
    version=2,
    description="Rename field X to Y on table Z",
    apply_fn=_m002_rename_x_to_y,
))
```

- `docs/schema.surql` is the canonical reference for fresh installs (baseline). Changes are documented there and versioned as migration steps.
- Non-breaking additive changes (new fields/tables): deploy via `docs/schema.surql` (`IF NOT EXISTS` prevents duplicates).

---

## Database Schema (SurrealDB)

| Table | Type | Purpose |
|-------|------|---------|
| `event` | SCHEMALESS | Raw event log (content, source, embedding, timestamp) |
| `entity` | SCHEMAFULL | Knowledge graph entities (name, type, embedding) |
| `fact` | SCHEMALESS | Relations between entities (subject → predicate → object) |
| `gate_log` | SCHEMAFULL | Entropy gate decisions (composite score, threshold, reason) |
| `_schema_migrations` | SCHEMAFULL | Applied migration versions (version, description, checksum) |

---

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
