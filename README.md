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
                  │  19 tools + 6 resources │
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
| **MCP Server** | `src/mcp/server.py` | Control plane (Anthropic MCP protocol) — stdio mode. 19 tools + 6 MCP resources: `memory_store`, `memory_store_batch`, `memory_store_markdown`, `memory_query`, `memory_update`, `memory_get`, `event_log_search`, `kg_query`, `graph_traverse`, `semantic_search`, `list_entities`, `list_events`, `memory_stats`, `memory_explain_routing`, `memory_forget`, `memory_unforget`, `memory_consolidate`, `memory_merge_entities`, `memory_find_duplicates`; Resources: `sieveon://stats`, `sieveon://entity/{id}`, `sieveon://event/{id}`, `sieveon://kg/subject/{name}`, `sieveon://kg/predicate/{type}`, `sieveon://search/{query}` |
| **Extraction** | `src/extraction/` | Local-first entity extraction: relex (`knowledgator/gliner-relex-multi-v1.0`, joint NER+RE, ~60ms) → gliner2.5-multi (zero-shot, multilingual) → spaCy fallback. Groq API (`GROQ_MODEL`, default `openai/gpt-oss-20b`) explicit opt-in only via `EXTRACTION_METHOD=groq`. Thresholds via `RELEX_ENT/REL_THRESHOLD`, `GLINER_ENT/REL_THRESHOLD` |
| **Classifier** | `src/extraction/classifier.py` | Hybrid ML+Regex query classifier: sklearn LogisticRegression on Qwen3-Embedding-0.6B embeddings (1024d) + TF-IDF (500 unigrams+bigrams), with regex fallback when ML confidence < 0.6. Synthetic training data generator at `scripts/generate_synthetic_training_data.py`, manual labeling CLI at `scripts/label_queries.py` |
| **Migrations** | `src/mcp/migrations.py` | Versioned auto-migration engine for breaking schema changes |
| **Router** | `src/router/` | Query classification policy + budget tracking: `policy.py` (RoutingPolicy, strategy per QueryType), `budget.py` (BudgetTracker, BudgetLevel), `cost_awareness.py` (CostTracker effectiveness ranking) |
| **Planner** | `src/planner/executor.py` | No separate `Planner` class — retrieval execution only: `RetrievalExecutor.execute_strategy()` + `PlanExecutor.execute_plan()` run the strategy chosen by the Router |
| **Maintenance** | `src/maintenance/conservative_maintainer.py` | Internal conservative maintainer (debounced patch updates, stale-fact cleanup, duplicate consolidation). Only MCP entrypoint is `memory_consolidate` |
| **Chunking** | `src/mcp/chunking.py` | Overlapping `char`/`token`/`semantic` chunking engine with YAML front matter parsing, table/HTML fence protection, image stripping (alt-text preserved), heading context prepended to each chunk |

---

## Key Features

- **Query Classification** — 5 types: Temporal, Factual, Multi-Hop, Conversational, Update. Hybrid approach: sklearn LogisticRegression on Qwen3-Embedding-0.6B embeddings (1024d) **+ TF-IDF (500 unigrams+bigrams)** with regex fallback when ML confidence < 0.6, plus deterministic vetoes (update read-requests, DE factual frames). Trained on TREC + SQuAD (factual), HotpotQA (multi-hop), TimeQA + CLINC-time (temporal), CoQA + CLINC-greetings (conversational), CLINC-intents + synthetic (update); per-class cap 600, seed 42.
  - **5-fold CV F1-macro** (primary metric, n=1000, 200/class): **0.944 ± 0.006**
  - Holdout F1-macro (n=200, ~8.5% template leakage): 0.955 (clean: 0.949) — all residual errors below the 0.6 threshold, i.e. the regex fallback decides them in production
  - **0.6-threshold accuracy**: 100% (105/105 samples above threshold; coverage 52.5%)
  - **Boundary suite**: 25/25 adversarial queries (update-negatives, memory-writes, why-factuals, coordination, greetings, DE) — behaviors pinned as `TestRegexClassifier` unit tests in `tests/python_unit_tests.py`
  - **Caveats:** (1) TREC original 6 labels were heuristically mapped (ABBR/ENTY/HUM/LOC → factual, NUM/time → temporal, NUM/count → factual); the old DESC/why → multi-hop mapping was **removed 2026-09-30** (197 rows → factual: TREC why-questions are single-fact explanations). Original labels discarded. (2) CoQA mapped 100% → conversational. (3) Synthetic data uses templates → ~9% exact duplicates across any random train/test split. (4) Aggregate CV intentionally lower than the old 0.967 — the remapped training set is harder and honest (template memorization removed); robustness moved to the boundary suite. (5) Internal eval only — not yet validated on real agent traffic.
  - Run `python scripts/eval_classifier.py` to reproduce. Retrain via `python scripts/train_classifier.py --cap 600`.
- **Extraction Eval** — `docs/eval_extraction_gold.jsonl` (31 DE/EN sentences with expected entities/triples) + `python scripts/eval_extraction.py [--sweep]`: entity precision/recall, triple recall (synonym-tolerant predicates), latency per backend. Reference: relex entP 0.91/entR 0.98/tripR 0.71 @0.7 (~110ms), gliner tripR 0.94 (broader, noisier), spacy tripR 0.00 (dependency labels don't match KG predicates).
- **Adaptive Retrieval** — `memory_query` (classify → route → execute) selects per query type (event log, KG, hybrid BM25+vector+temporal). Direct tools (`event_log_search`, `semantic_search`, `kg_query`, `graph_traverse`) bypass the router for explicit lookups. Temporal pinning: `memory_query(..., since?, until?, at_time?)` bounds event timestamps (`fn::events_at` semantics) and pins KG validity (`fn::facts_at_time` semantics, `type::datetime`); graph expansion is bounded BFS (depth 2)
- **Entropy Gating** — Composite score: Shannon character entropy + gzip compression ratio (Kolmogorov complexity proxy) + embedding novelty. Raw Event Log is always append-only; the gate decides only whether to extract into the Knowledge Graph.
- **Entity Extraction** — Local-first: relex joint NER+RE → gliner2.5-multi → spaCy fallback (all on the RTX 2080, no API in the default chain). Groq API opt-in only (`EXTRACTION_METHOD=groq`). Type preservation (LLM classification preferred over heuristic).
  - **Fallback semantics:** the chain advances only on backend error or *empty* result — never on low scores. Every fact carries `extractor` (`relex`/`gliner`/`groq`/`spacy`/`manual`) so fallback evidence stays distinguishable in the KG; confidence is never rescaled, comparability comes from `salience` below.
  - **Thresholds:** `RELEX_REL_THRESHOLD` (default 0.7) is global across languages — measured DE/EN score medians differ slightly (0.23 vs 0.30) but kept-relation counts at 0.7 are near-identical (~4–5/text both), so no per-language split. Sweep via `python scripts/eval_extraction.py --sweep`.
- **Logical Invalidation** — `valid_until` timestamps instead of hard deletes. `memory_update` auto-creates target entities if they don't exist yet.
- **Forgetting & Consolidation** — `memory_forget` soft-deletes events or entities; `memory_consolidate` (sole MCP entrypoint) triggers `ConservativeMaintainer` runs (with optional physical stale-fact removal).
- **Cost Awareness** — Tracks & budgets resource consumption per strategy
- **Tool notes** — `memory_stats` accepts optional `aggregate` (`none`/`events_by_source`/`facts_by_predicate`/`entities_by_type`/`all`); the extra `random_string` param exists only for MCP no-required-args compatibility — call with no args.

---

## Quick Start

### Prerequisites

- Python 3.10+
- Docker + Docker Compose (for SurrealDB)
- ~4 GB disk for local models (downloaded lazily on first use into `~/.cache/huggingface`):
  `relex-multi` ~1.3 GB, `gliner2.5-multi` ~1.2 GB, `Qwen3-Embedding-0.6B` ~1.2 GB.
  GPU optional — everything runs on CPU too; on CUDA all three fit side by side
  in 8 GB VRAM (~5 GB used).

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

## Ingestion Gate — How It Works

The gate prevents the Knowledge Graph from being flooded with low-value entries.
Every input is always written to the immutable Raw Event Log; the gate only
controls whether content is additionally extracted into the temporal KG.

**Stage 1 — Guardrails (cheap, local, no model):** length (`min_length = 10`,
`max_length = 2000`), character diversity (< 0.15 for texts ≤ 150 chars) and
word diversity (< 0.20 above), exact-content dedup (same hash + source), and a
soft near-duplicate warning (embedding novelty vs adaptive `min_novelty`
ramp 0.05 → 0.20). Guardrail hits are logged with real entropy/compression
scores (`decision='skip'`).

**Stage 2 — Extraction + fact salience:** passed texts go through entity/triple
extraction; every created fact gets `salience = 0.6*confidence +
0.25*event_novelty + 0.15*predicate_specificity` (`salience_version`,
see `docs/adr/ADR-001-composite-deprecation.md` for why this replaced the old
composite score). Co-occurrence facts below `TIER_DROP_THRESHOLD` (default
0.50) are not created — mentions stay as provenance; SVO facts are never
tiered. Skipped counts surface as `tier_skipped` in `memory_store` responses.
Each fact also carries `extractor` (`relex`/`gliner`/`groq`/`spacy`/`manual`).

**Storage contract:** every input lands in the Raw Event Log, gate decisions
in `gate_log`, facts (with salience + extractor) in the KG.

**MCP path status:** `memory_store` calls `EntropyGate.ingest()` (log + extract
+ gate). Retrieval results carry `trust` markings — see Security below.

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
| `event` | SCHEMALESS | Raw event log (content, source, trust, embedding, timestamp) |
| `entity` | SCHEMAFULL | Knowledge graph entities (name, type, embedding) |
| `fact` | SCHEMALESS | Relations between entities (subject → predicate → object, salience, extractor) |
| `gate_log` | SCHEMAFULL | Gate decisions (composite score, threshold, salience, reason) |
| `_schema_migrations` | SCHEMAFULL | Applied migration versions (version, description, checksum) |

---

## Security

A memory server that returns stored text into LLM context is a
**prompt-injection channel**. Rules for consumers:

- **Trust levels:** every retrieved event carries `trust` — `"direct"`
  (entered via `memory_store` with `source="user_input"`) or `"untrusted"`
  (markdown imports, web content, batch sources; explicit `trust` param wins).
  Treat `untrusted` content strictly as DATA, never as instructions. This
  applies to KG fact strings as well (they are model-generated).
- **Deletion:** `memory_forget` soft-deletes by default (reversible via
  `memory_unforget`). `memory_forget(..., hard=True)` physically deletes the
  event (incl. embedding) plus derived facts (`source_event`), or the entity
  plus its facts. Hard deletes are irreversible — use them for
  privacy/data-removal requests. Shared entities are never cascade-deleted
  on event hard-delete.
- **Duplicates:** `memory_find_duplicates` lists merge candidates (read-only,
  fail-closed); `memory_merge_entities(dry_run=True)` previews merges.
  Nothing merges automatically.
- **Transport:** the MCP server itself has no auth layer (see Known
  Limitations) — bind stdio locally or put auth in front.

---

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
