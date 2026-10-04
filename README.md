# Sieveon

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![SurrealDB](https://img.shields.io/badge/SurrealDB-3.3.0-8B5CF6)
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
                  │  MCP Server             │  (Python, stdio + HTTP)
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
        │  fact_history / gate_log /  │
        │  router_costs / retrieval_cache /
        │  _schema_migrations
        └─────────────────────────────┘
```

`stdio` is the primary MCP transport. Additionally `src/mcp/server.py`
starts an **unauthenticated HTTP control plane on `0.0.0.0:8082`**
(same tools via `POST /memory/...`, see Security). Do not expose it
without auth in front.

`memory_query` classifies via `QueryClassifier`, selects a strategy via
`RoutingPolicy` and executes it via `RetrievalExecutor`. Direct tools like
`event_log_search` and `semantic_search` bypass classification for explicit lookups.

### Python Components

| Component | Path | Description |
|-----------|------|-------------|
| **MCP Server** | `src/mcp/server.py` | Control plane (Anthropic MCP protocol) — stdio mode. 19 tools + 6 MCP resources: `memory_store`, `memory_store_batch`, `memory_store_markdown`, `memory_query`, `memory_update`, `memory_get`, `event_log_search`, `kg_query`, `graph_traverse`, `semantic_search`, `list_entities`, `list_events`, `memory_stats`, `memory_explain_routing`, `memory_forget`, `memory_unforget`, `memory_consolidate`, `memory_merge_entities`, `memory_find_duplicates`; Resources: `sieveon://stats`, `sieveon://entity/{id}`, `sieveon://event/{id}`, `sieveon://kg/subject/{name}`, `sieveon://kg/predicate/{type}`, `sieveon://search/{query}` |
| **Extraction** | `src/extraction/` | Local-first entity extraction: relex (`knowledgator/gliner-relex-multi-v1.0`, joint NER+RE, ~60ms) → gliner2.5-multi (zero-shot, multilingual) → spaCy fallback. Groq API (`GROQ_MODEL`, default `openai/gpt-oss-20b`) explicit opt-in only via `EXTRACTION_METHOD=groq`. Thresholds via `RELEX_ENT/REL_THRESHOLD`, `GLINER_ENT/REL_THRESHOLD`. **Triple** chain has no spaCy fallback (see below). |
| **Classifier** | `src/extraction/classifier.py` | Hybrid ML+Regex query classifier: sklearn LogisticRegression on Qwen3-Embedding-0.6B embeddings (1024d) + TF-IDF (500 unigrams+bigrams), with regex fallback when ML confidence < 0.6. Synthetic training data generator at `scripts/generate_synthetic_training_data.py`, manual labeling CLI at `scripts/label_queries.py` |
| **Migrations** | `src/mcp/migrations.py` | Versioned auto-migration engine for breaking schema changes |
| **Router** | `src/router/` | Query classification policy + budget tracking: `policy.py` (RoutingPolicy, strategy per QueryType), `budget.py` (BudgetTracker, BudgetLevel), `cost_awareness.py` (CostTracker effectiveness ranking) |
| **Planner** | `src/planner/executor.py` | No separate `Planner` class — retrieval execution only: `RetrievalExecutor.execute_strategy()` + `PlanExecutor.execute_plan()` run the strategy chosen by the Router |
| **Maintenance** | `src/maintenance/conservative_maintainer.py` | Internal conservative maintainer (debounced patch updates, stale-fact cleanup, duplicate consolidation). Only MCP entrypoint is `memory_consolidate` |
| **Chunking** | `src/mcp/chunking.py` | Overlapping `char`/`token`/`semantic` chunking engine with YAML front matter parsing, table/HTML fence protection, image stripping (alt-text preserved), heading context prepended to each chunk. Hardened import path (see `memory_store_markdown` below): `.md`/`.markdown` only, no symlinks, 2 MiB / 200k-chars cap, `chunk_size` 100–10000, `0 <= overlap < chunk_size`, `max_concurrent` 1–5, optional jail via `SIEVEON_MARKDOWN_ROOT` |

---

## Key Features

- **Query Classification** — 5 types: Temporal, Factual, Multi-Hop, Conversational, Update. Hybrid approach: sklearn LogisticRegression on Qwen3-Embedding-0.6B embeddings (1024d) **+ TF-IDF (500 unigrams+bigrams)** with regex fallback when ML confidence < 0.6, plus deterministic vetoes (update read-requests). **English only** (2026-10-01): German/Denglish template rows removed from training, German regex patterns and vetoes deleted. Trained on TREC + SQuAD (factual), HotpotQA (multi-hop), TimeQA + CLINC-time (temporal), CoQA + CLINC-greetings (conversational), CLINC-intents + synthetic (update); per-class cap 600, seed 42.
  - **5-fold CV F1-macro** (primary metric, n=1000, 200/class): **0.924 ± 0.015**
  - Holdout F1-macro (n=200): 0.920 — residual errors below the 0.6 threshold, i.e. the regex fallback decides them in production
  - **0.6-threshold accuracy**: 99.2% (117/118 samples above threshold; coverage 59.0%)
  - **Boundary suite**: adversarial queries (update-negatives, memory-writes, why-factuals, coordination, greetings) — behaviors pinned as `TestRegexClassifier` unit tests in `tests/python_unit_tests.py`. English only since 2026-10-01.
  - **Caveats:** (1) TREC original 6 labels were heuristically mapped (ABBR/ENTY/HUM/LOC → factual, NUM/time → temporal, NUM/count → factual); the old DESC/why → multi-hop mapping was **removed 2026-09-30** (197 rows → factual: TREC why-questions are single-fact explanations). Original labels discarded. (2) CoQA mapped 100% → conversational. (3) Synthetic data uses templates → ~9% exact duplicates across any random train/test split. (4) Aggregate CV intentionally lower than the old 0.967 — the remapped training set is harder and honest (template memorization removed); robustness moved to the boundary suite. (5) Internal eval only — not yet validated on real agent traffic.
  - Run `python scripts/eval_classifier.py` to reproduce. Retrain via `python scripts/train_classifier.py --cap 600`.
- **Extraction Eval** — `docs/eval_extraction_gold.jsonl` (39 **English-only** sentences, 32 triples) + `python scripts/eval_extraction.py [--sweep]`: entity precision/recall, triple recall, **per-fact precision**, latency per backend, and the AUC of fact salience as a correct-vs-wrong discriminator. Predicate matching is synonym-tolerant. Reference: relex entP 0.92/entR 0.97/tripR 0.84 / factP 0.51 (~620ms), gliner tripR 0.88 but factP 0.24, spacy tripR 0.00 (excluded from the triple chain, see below). Details in [ADR-002](docs/adr/ADR-002-extraction-measurement-correction.md).
- **English only** — deliberate, measured decision. Splitting the gold set by language: relex per-fact precision was **0.188 on English** vs **0.028 on German** (1 correct fact of 36 on FewRel-mapped data; 0.400 on the 20-sentence English project set before the canonical expansion, 0.509 after). The embedding model is English-only as well. German was dropped from the gold set rather than tuned; non-English input is expected to degrade extraction and search.
- **Adaptive Retrieval** — `memory_query` (classify → route → execute) selects per query type (event log, KG, hybrid BM25+vector+temporal). Direct tools (`event_log_search`, `semantic_search`, `kg_query`, `graph_traverse`) bypass the router for explicit lookups. Temporal pinning: `memory_query(..., since?, until?, at_time?)` bounds event timestamps (`fn::events_at` semantics) and pins KG validity (`fn::facts_at_time` semantics, `type::datetime`); graph expansion is bounded BFS (depth 2)
- **Entropy Gating** — Composite score: Shannon character entropy + gzip compression ratio (Kolmogorov complexity proxy) + embedding novelty. Raw Event Log is always append-only; the gate decides only whether to extract into the Knowledge Graph.
- **Entity Extraction** — Local-first: relex joint NER+RE → gliner2.5-multi → spaCy fallback (all on the RTX 2080, no API in the default chain). Groq API opt-in only (`EXTRACTION_METHOD=groq`). Type preservation (LLM classification preferred over heuristic).
  - **Triple chain has no spaCy fallback** (ADR-002): spaCy asserted 0 correct triples of 15 because it scores a relation by the cosine similarity of the subject and object *names* — a measure of string similarity, not of there being a relation. Returning no triple beats returning a false one: retrieval can fail to find a fact that does not exist, but it will happily surface a false one. spaCy still backs *entity* extraction (entR 0.98). An explicit `EXTRACTION_METHOD` is honoured strictly — `relex` never silently falls back to a weaker backend.
  - **Fallback semantics:** the chain advances only on backend error or *empty* result — never on low scores. Every fact carries `extractor` (`relex`/`gliner`/`groq`/`spacy`/`manual`) so fallback evidence stays distinguishable in the KG; confidence is never rescaled, comparability comes from `salience` below. Caveat: `extractor` is inferred from entity labels by majority vote, so it can misattribute a triple (known limitation).
  - **Thresholds:** `RELEX_REL_THRESHOLD` (default 0.7). Sweep via `python scripts/eval_extraction.py --sweep`. Note the sweep is not a precision/recall trade you can win outright — raising it from 0.7 to 0.9 lifts per-fact precision 0.12→0.18 but drops triple recall 0.29→0.22, because the model's score distributions for correct and wrong facts overlap almost completely.
- **Logical Invalidation** — `valid_until` timestamps instead of hard deletes. `memory_update` auto-creates target entities if they don't exist yet.
- **Forgetting & Consolidation** — `memory_forget` soft-deletes events or entities; `memory_consolidate` (sole MCP entrypoint) triggers `ConservativeMaintainer` runs (with optional physical stale-fact removal).
- **Markdown import (`memory_store_markdown`)** — `content` or `file_path` (mutually exclusive). `file_path` is untrusted input: only `.md`/`.markdown` regular files, no symlinks, max 2 MiB on disk / 200k chars, optionally jailed to `SIEVEON_MARKDOWN_ROOT` (when set, the resolved path must lie inside it). Chunking params are fail-closed: `chunk_size` 100–10000, `0 <= overlap < chunk_size`, `chunking_method ∈ {char, token, semantic}`, `encoding_name ∈ {cl100k_base, p50k_base, r50k_base, o200k_base}`, `max_concurrent` 1–5, `content` ≤ 200k chars. Violations return `{"status": "error"}` before any chunking/DB work.
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

The SurrealDB image is pinned to `surrealdb/surrealdb:v3.3.0`. This matters:
SurrealDB 3 changed query semantics that this codebase depends on — `UPDATE`
no longer creates a missing record (so the router-cost snapshot is an
`UPSERT`), and on a `SCHEMAFULL` table `TYPE object` is schemafull by default
(so `entity.metadata` is `FLEXIBLE`). Running `latest` could invalidate both
with no code change to point at. Bump the tag deliberately and re-run
`tests/python_schema_tests.py`.

**Debug stack.** The published image is distroless, so it has no shell and
there is no way to look inside. `docker-compose.debug.yml` builds the same
server version on Debian with the usual tools:

```bash
# Starts on port 8001 with in-memory storage, leaving the real one alone
docker compose -f docker-compose.yml -f docker-compose.debug.yml up -d

# Shell in
docker exec -it sieveon-surrealdb-debug bash

# Or query it directly
echo "USE DB x; SELECT * FROM event;" | docker exec -i sieveon-surrealdb-debug \
  surreal sql --endpoint http://localhost:8000 --user root --pass root --pretty

docker compose -f docker-compose.yml -f docker-compose.debug.yml down
```

It runs in its own Compose project (`name: sieveon-debug`), on its own port,
and with `SURREAL_PATH=mem://`. Note that Alpine is not used: SurrealDB
publishes no musl build, only glibc.

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

**Implemented in `src/mcp/core.py`** (`server.py` only starts the transports):

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

- **Adaptive Scaling:** Limits are automatically scaled down based on a **System Health Factor** (`BudgetTracker.get_system_health()`, range `~0.17–1.0` per `_health_from_failures`: `1.0 - min(failures,10)/12.0`). It is set to `1.0` on successful SurrealDB calls and lowered on failures (`src/mcp/core.py`); low health (< 0.5) also reduces retry attempts. Read it via `get_system_health()` — do not access the private `BudgetTracker._health_factor` directly.
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
| `fact_history` | SCHEMALESS | Invalidated fact versions (logical-delete history) |
| `gate_log` | SCHEMAFULL | Gate decisions (composite score, threshold, salience, reason) |
| `router_costs` | SCHEMAFULL | Persisted router cost-tracker state |
| `retrieval_cache` | SCHEMALESS | Cached retrieval results (query_hash, TTL) |
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
  Limitations) — bind stdio locally or put auth in front. This explicitly
  includes the HTTP control plane (`0.0.0.0:8082`, e.g.
  `POST /memory/store/markdown`): it accepts the same untrusted tool inputs
  (notably `file_path`, `content`, `chunk_size`/`overlap`) as stdio with no
  authentication. Never expose the port without auth/reverse-proxy.

---

## Known Limitations

- **KG fact precision is low.** On the gold set relex asserts 45 facts to get 13
  right (fact precision 0.29); gliner 18/75. Retrieval can only be as trustworthy
  as what was written. A background fact with no verb — "The VectorDB engine OR
  (query) was rated 5/5" — yields `VectorDB developed engine` at confidence 0.84.
  See [ADR-002](docs/adr/ADR-002-extraction-measurement-correction.md).
- **`extractor` is inferred, not recorded.** `infer_extractor` votes on entity
  labels to guess which backend produced a fact, so a relex triple can be stored
  as `extractor=spacy`. Do not treat it as provenance.
- **`TIER_DROP_THRESHOLD` (0.50) is inert.** Fact salience ranks relex output
  usefully (AUC 0.817) but the whole distribution sits above 0.50, so tiering
  drops nothing; it also only applies to co-occurrence predicates, while 86% of
  wrong facts are SVO.
- **`fact.salience` is not read by retrieval.** It is written at ingest and
  surfaces in `memory_explain_routing`/diagnostics only; no retrieval strategy
  ranks on it.

## provides Extraction Program (Tracks A/B)

Separate from the MCP extraction chain above, a dedicated program builds
reliable `(X, provides, Y)` graph edges. Status: Track B v1.2.1 is the
frozen production baseline; Track A is archived research.

- **Track A (frozen):** controlled provides training data
  (`docs/eval_phase_a_manifest.json`, `controlled_seed_expanded_v2`),
  counterfactual schema tests, pre-registered held-out protocol
  (`docs/eval_phase_a_heldout_protocol_v1*.json`). GLiNER relation-learning
  experiments ended inconclusive at the entity stage; records kept, no
  further runs.
- **Track B (production v1.2.1):** NuExtract3 candidate extraction +
  stepfun assertion validation → pair-scoped acceptance → normalization /
  entity linking (ACCEPT/ABSTAIN) → SurrealDB materialization into
  `trackb_entity` / `trackb_provides` / `trackb_evidence` (NS/DB `strata`).
  Current state: 16 edges, 34 evidence records, 1 real ABSTAIN.
- **Baseline manifest:** `docs/trackb_baseline_v121.json` (graph digest).
- **Regression:** `python scripts/trackb_regression.py` — 8/8 GREEN required
  before any new run (edges, evidence, direction pair, blind-FP provenance,
  linker ABSTAIN, controlled FNs, import idempotency).
- **Scope freeze:** benefit/effect relations are explicitly out of `provides`
  scope (`docs/scope_taxonomy_freeze_v1.json`); new relations ship as
  separate tracks, never as silent `provides` extensions.
- **Production corpus:** `docs/production_corpus_v1.json` (150 sentences,
  digest-pinned) with annotated error matrix
  (`docs/production_error_matrix_v1.json`).
- **MCP integration:** Track B is an opt-in backend (`EXTRACTION_METHOD=trackb`;
  `TRACKB_IN_AUTO=1` merges it into the `auto` chain). Needs local Ollama +
  `KILO_API_KEY`; triples carry `extractor="trackb"` plus candidate/validator
  provenance. Default chain unchanged.

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
