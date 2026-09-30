# ADR-001: Composite Gate Score deprecated, Fact Salience v1 active

- Status: accepted (2026-09-30)
- Context: Ingestion Gate (`src/extraction/entropy_gate.py`)

## Former mechanism (retired from decision-making)

```
composite = alpha * normalized_text_entropy + gamma * compression_ratio + beta * embedding_novelty
```

- Text entropy: Shannon entropy on character level (alphanumeric + whitespace),
  normalized to `[0, 1]` with max ~4.5 bits. **Not LightMem** — LightMem
  (`_unused/LightMem/.../entropy_compress.py`) scores LM surprisal
  (`-log2 p(token|context)`) per word for compression; same word, different
  concept. The old "LightMem-style" code comment was wrong and has been removed.
- Compression ratio: `len(gzip.compress(text)) / len(text)`, a Kolmogorov
  complexity proxy. Falls back to `0.5` for texts under 20 characters.
- Embedding novelty: `1 - avg cosine similarity` to the top-5 most similar
  stored embeddings (SurrealDB native vector search, self-match excluded via
  record-literal `id != event:xxx` — the earlier quoted string form silently
  matched nothing, biasing every novelty down by up to 0.2; fixed).
- Weights: `alpha = 0.25`, `gamma = 0.25`, `beta = 0.50`. Threshold adaptive
  `0.30` (cold) → `0.55` (after ~150 events).

## Why deprecated

Calibration run 2026-09-30 (31 real web stores: Wikipedia RAG / sourdough /
Curie / geothermal + paraphrases + junk), `gate_log` analysis:

1. Entropy is ~constant (0.85–0.96) on all real prose — the alpha term is a
   constant offset, it discriminates nothing.
2. Compression is 1.0 (capped) for all short texts (gzip overhead) — short
   inputs get +0.25 for free and cannot fail.
3. The cold threshold (0.30) never binds (minimum observed composite 0.522);
   even at 0.55 only 1/23 would flip.
4. Weight sweep (entropy-heavy / novelty-only / no-novelty / balanced):
   **0 decision flips** — weights are irrelevant at these thresholds.
5. All real filtering came from the guardrails (length/diversity/dedup).

## Decision

- Composite stays **logged** (`gate_log.gate_score`) for comparability but no
  longer gates anything and will not be tuned.
- Active mechanism: guardrails → extraction → per-fact salience
  (`0.6*confidence + 0.25*event_novelty + 0.15*predicate_specificity`,
  `salience_version='v1-heuristic'`) with tiering of co-occurrence facts below
  `TIER_DROP_THRESHOLD` (default 0.50). Mentions stay as provenance; SVO facts
  are never tiered.
- Open follow-ups: salience threshold validation on a labeled triple set
  (see `scripts/eval_extraction.py`); LM-surprisal v2 as a possible later
  salience signal (the actual LightMem idea).
