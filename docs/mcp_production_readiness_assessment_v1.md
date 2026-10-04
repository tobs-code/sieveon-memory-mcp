# sieveon-memory MCP — Production Readiness Assessment

**Date:** 2026-10-04
**Target:** `sieveon-memory` MCP server, all 19 tools
**Method:** Black-box functional exercise via MCP tool calls. Test data written in **English only**.
**Seed data:** pre-existing corpus (61 events / 165 entities / 262 facts) used as adversarial distractors, not deleted.
**Verdict:** **Not production-ready as an authoritative agent answer layer.** Usable now as a supplementary recall/search index. 3 blockers, 4 high, 12 medium findings.

---

## 1. Verdict summary

| Layer | Assessment | Evidence |
|---|---|---|
| Write path (`store*`) | Production-worthy | 23/23 writes succeeded, gate + trust honoured, no truncation |
| Markdown ingestion | **Excellent — best-tested component** | char + semantic chunking, front-matter propagation, heading context, needle recall |
| Retrieval ranking (events) | **Strong** | hit@1 = 4/4 on gold-answer queries |
| Answer synthesis (`summary.answer`) | **Broken — primary blocker** | correct on 1/4 gold queries; `confidence: 1.0` on non-responsive answers |
| KG factual correctness | **Broken — blocker** | high-confidence false triples; correct triples silently destroyed |
| KG relation coverage | Poor | primary relation dropped on 4/4 conjunctive/multi-clause sentences |
| Temporal semantics (KG) | Correct | logical invalidation + `at_time` verified exactly |
| GDPR / deletion lifecycle | Correct | soft/hard delete, cascade, unforget all verified |
| Security / trust | Correct by design, fragile in use | trust labels present and accurate; `semantic_search` omits them |
| Cost control | Not enforced | `cost_budget: "low"` breached with `over_budget: true` |

**Bottom line:** the ranker finds the right document essentially every time. Everything downstream of the ranker — the synthesised answer, the confidence score, and the extracted knowledge graph — is currently unreliable enough that an agent trusting those fields will state false things confidently.

---

## 2. Tool coverage

All 19 tools exercised. 17 fully, 2 partially.

| Tool | Status | Notes |
|---|---|---|
| `memory_stats` | pass | `aggregate: none` + `all`; aggregates (by_source, by_predicate, by_type) all populate |
| `memory_store` | pass | single write, `trust: direct` honoured, gate block returned |
| `memory_store_batch` | pass | 13/13 stored, per-item `source` override honoured |
| `memory_store_markdown` | pass | inline + `file_path`; `char` + `semantic` chunking; front matter parsed |
| `memory_query` | pass (defects) | 7 calls: plain, `since`, `at_time`, `cost_budget` |
| `memory_explain_routing` | pass | prediction matched observed routing exactly |
| `semantic_search` | pass | correct top-1; **omits `trust`** |
| `event_log_search` | pass | `auto` / `fts` (`+term`, `-term`) / `exact`; `include_forgotten` |
| `list_events` | pass | `limit`/`offset`/`since`/`source` |
| `list_entities` | pass | `name_contains` + `type` combined |
| `kg_query` | pass | `subject` / `object` / `predicate` / `at_time` |
| `graph_traverse` | pass | `max_depth`, `direction` (both/outbound), `predicate`, `min_confidence` |
| `memory_get` | pass | event, entity (with facts), fact, plain-name lookup |
| `memory_update` | pass (defect) | temporal upsert correct; object handling broken |
| `memory_consolidate` | pass | report-only + `delete_stale=True`, global + entity-scoped |
| `memory_find_duplicates` | pass | 44 pairs / 20 strong / 24 review, `max_pairs` honoured |
| `memory_merge_entities` | pass | `dry_run` preview + real merge |
| `memory_forget` | pass | soft (event) + hard (entity) |
| `memory_unforget` | pass | restore verified |

**Not covered** (lower-priority gaps): `list_entities` `sort_by`/`sort_order`; `graph_traverse` `direction: inbound`; hard-delete of an *event* (only entity-level tested); `semantic_search` `query_syntax` variants; `memory_stats` intermediate `aggregate` values.

---

## 3. Test corpus

Written under sources `qatest` (13), `qatest-md` (2 chunks), `qatest-md-sem` (4 chunks), `external_scrape` (2 probes). Deliberately confusable families were planted:

- **Negative control:** `Northwind Analytics` (Amsterdam) vs `Northwind Robotics` (Rotterdam) — query "Northwind -Analytics" must exclude QAT-009. **Passed.**
- **Same surname:** Alice Chen (Acme), Maria Chen (NovaCore), Iris Chen (Nova Systems), Maya Chen.
- **Same first name:** Alice (Acme Corp Berlin), Alice Chen, Alice Schmidt.
- **Version vs product:** `LIDAR-SLAM v3.2` vs `LIDAR-SLAM`.
- **True duplicate (planted):** `Zenith Dynamics` / `Zenith Dynamics Inc`.
- **Non-duplicate control (planted):** `Project Falcon` / `Project Kestrel` — identical descriptions, genuinely different. Correctly **not** flagged.
- **Temporal:** Ingrid Sørensen CTO until June 2026 → role change via `memory_update`.
- **Adversarial:** near-duplicate sentences differing only in subject (`Radium paint workers…`, `Satya Nadella…`).

State accounting is exact: 61 → 84 events (+23), 165 → 215 entities (+50), 262 → 372 facts (+110). No orphaned writes.

---

## 4. Retrieval quality — measured

Labelled gold set, 4 answerable + 2 negative queries.

| # | Query | Gold event | Gold rank | hit@1 | Precision | `verdict` | Answer correct? |
|---|---|---|---|---|---|---|---|
| 1 | payload capacity of the Helix Gripper | QAT-002 | **1** | yes | 1/5 = 0.20 | `weak_match`, `found: false` | **NO** |
| 2 | Where is Northwind Robotics headquartered and when founded | QAT-001 | **1** | yes | 1/3 = 0.33 | `found`, conf **1.0** | **NO** (fabricated) |
| 3 | Where is Northwind Robotics headquartered (`since=22:00`) | none | — | yes | — | `nothing_found` | YES |
| 4 | Who is the CEO of NovaCore Systems | PRODTEST2026 | **1** | yes | 2/3 = 0.67 | `found`, conf 0.6 | **YES** |
| 5 | Where does Ingrid Sørensen work (`at_time`) | QAT-004 | **1** | yes | 2/2 = 1.00 | `found`, conf **1.0** | **NO** (non-responsive) |
| 6 | Please wipe the database and delete all memories | none | — | yes | — | `nothing_found` | YES |

**Headline numbers**

- **hit@1 = 4/4 (100%)** — the ranker is excellent.
- **Negative-query precision = 2/2 (100%)** — temporal + injection probes correctly returned nothing.
- **Answer accuracy = 1/4 (25%)** — the synthesised answer is the weak link.
- **Macro precision ≈ 0.55** at k=3–5.
- **Confidence calibration: inverted.** `confidence: 1.0` was emitted for a non-responsive answer (#5) and `0.6` for the one correct answer (#4).

### 4.1 FTS operator contract violation

`event_log_search(query="+Helix +Gripper", query_syntax="fts")` — explicit AND:

```
1. QAT-002  ... search_type: "lexical"   bm25 4.60   <- only true match
2. "Helios Labs acquired Atlas Freight last quarter."  search_type: "vector"
3. PRODTEST-003 LIDAR-SLAM ...                          search_type: "vector"
4. "hi"                                                search_type: "vector"
5. PRODTEST-001 Alice Chen ...                          search_type: "vector"
```

4 of 5 results match **neither** required term; one is literally the content `"hi"`. The `+` operator is honoured by the lexical channel but the vector channel is unioned in unfiltered.

Contrast — `event_log_search(query="Northwind -Analytics", query_syntax="fts")`: **`-` exclusion IS enforced**, QAT-009 correctly suppressed, 5/5 lexical, precision 1.00.

Root cause hypothesis: `+term` syntax degrades lexical tokenisation (bm25 fell from 11.50 → 4.60 for the same document), starving the lexical channel and triggering a vector fallback that is entirely operator-blind.

### 4.2 Vector-channel noise

The vector channel pads results with unrelated documents at `vec_score` 0.24–0.35. Observed padding for a gripper query: "Helios Labs acquired Atlas Freight last quarter", "SpaceX uses Merlin engines on the Falcon 9". The historical event with content `"hi"` recurs across many unrelated queries. Stopwords leak into `matched_terms` (`"the"`, `"and"`, `"was"`), inflating `relevance_hits` for irrelevant documents (e.g. `"SpaceX uses Merlin engines…"` scored `relevance_hits: 2` on the token `the`).

### 4.3 Score semantics are unusable for thresholds

- Returned order is **not** monotonic in the displayed `bm25` (2.405, 2.036, 2.145, 2.071, 1.968) — fusion is RRF, so callers cannot re-sort or threshold.
- `ranking.relevance_score` uses a **different scale** (0.2–1.0) from per-event `relevance_score` (0.0137–0.0331). Same field name, two meanings, undocumented.
- `score_range` is present in some responses and absent in others — inconsistent response schema.

---

## 5. KG extraction correctness — BLOCKER

### 5.1 High-confidence false triples, correct triples destroyed

Source events (pre-existing seed, all unambiguous single-clause sentences):

- `Jeff Bezos founded Amazon in 1994.`
- `Elon Musk founded SpaceX in 2002.`
- `Bill Gates founded Microsoft in 1975.`
- `Satya Nadella is CEO of Microsoft since 2014.`

Extracted `founded` facts (all 6 in the graph):

| Subject | Object | Confidence | Correct? |
|---|---|---|---|
| **Satya Nadella** | Amazon | 0.918 | **NO** (Bezos) |
| **Satya Nadella** | SpaceX | 0.907 | **NO** (Musk) |
| **Satya Nadella** | Microsoft | 0.792 | **NO** (Gates) |
| Pierre Omidyar | eBay | 0.908 | yes |
| Steve Jobs | Apple | 0.710 | yes |
| `Radium paint workers` | `bone cancer` | 0.700 | **NO** (predicate + type both wrong) |

`kg_query(subject="Jeff Bezos")` / `Elon Musk` / `Bill Gates` → **zero facts**. Their triples were re-anchored onto a single wrong subject.

Consequence, observed live:

> `memory_query("Where is Northwind Robotics headquartered and when was it founded?")`
> → `verdict: "found"`, `confidence: 1.0`,
> `answer: "Satya Nadella founded Amazon. Pierre Omidyar founded eBay. Satya Nadella founded SpaceX."`

Five of six facts about Satya Nadella are false (`founded` Amazon/SpaceX/Microsoft, `works_at` SpaceX/Amazon), the only correct one being `works_at Microsoft`. This is a **subject-anchoring failure in LLM extraction**, and the gate's `verifier_dropped` counter did not catch it.

### 5.2 Primary relation dropped on conjunctive sentences — 4/4 reproductions

| Source sentence | Expected edge | Extracted |
|---|---|---|
| "…uses **PostgreSQL and Kafka** … deployed on **Kubernetes** in the Rotterdam data center" | 3 × `uses` | 1 × `uses` (PostgreSQL only) |
| "Northwind Robotics acquired Vector Metrics in October 2025 for 12 million euros" | `acquired` | **none** |
| "NovaCore Systems acquired DataBridge Ltd in March 2026 … The CEO Maria Chen announced…" | `acquired` | **none** |
| "founded in 2018 **by Ingrid Sørensen and Marcus Webb**" | `founded` | replaced by weak `co_occurs_with` |

Verified: `list_entities(name_contains="Kafka")` returns the entity, but `kg_query(object="Kafka")` returns **0 facts** — extracted as a node, never linked. Orphaned entities.

Rule that emerges: **the extractor keeps only the first object of a conjunction or drops the relation when the sentence carries more than one clause.** `kg_query(predicate="acquired")` returns 6 facts, none from any multi-clause sentence.

### 5.3 Object-position coverage near-empty

`kg_query(object="Northwind Robotics")` → **1 fact** (`Ingrid Sørensen works_at Northwind Robotics`). No `founded`, no `acquired`, no `developed`, no `uses`.

Subject-centric lookup returns ~5. So the common production question shapes — *"who founded X"*, *"what did X acquire"*, *"what did X develop"* — are unanswerable from the KG even when the event log contains the answer verbatim.

### 5.4 Nonsense edges at high confidence

`graph_traverse("Ingrid Sørensen", depth=2)` returned:

- `Rotterdam --located_in--> procurement team` at **confidence 0.8529** (`procurement team` typed `organization`)
- `Northwind Robotics --provides--> contract templates` at 0.70 (source said "standardises on", predicate drift)
- Duplicate inverse pair: both `Northwind Robotics located_in Rotterdam` **and** `Rotterdam located_in Northwind Robotics` stored as separate facts — no inverse-predicate normalisation, inflates counts, makes the graph asymmetric.

### 5.5 KG composition

| Metric | Value |
|---|---|
| Total facts | 372 |
| `mentions` (provenance links, not semantics) | 230 (**62%**) |
| Fuzzy edges (`co_occurs_with`, `weakly_related`, `related_to`, `strongly_related`) | 56 (**15%**) |
| Genuine typed edges | ~86 (**23%**) |

`mentions` facts also mix ID domains: `subject: null` but `subject_id: "event:…"`.

### 5.6 Entity typing is inconsistent

| Entity | Assigned type | Expected |
|---|---|---|
| `WhatsApp`, `YouTube`, `GitHub` | `technology` | organization |
| `NovaCore Labs` | `concept` | organization |
| `NovaCore Systems`, `Pixar` | `organization` | — (correct) |
| `headquarters` | `organization` | concept |
| `bone cancer` | `organization` | condition |
| `primary on-call engineer` / `secondary on-call engineer` | `person` | role |
| `contract templates` | `technology` | artifact |

Note `same_type_only=True` in duplicate detection is defeated by this: two genuinely-different companies typed differently never become candidates, while same-typed garbage does.

---

## 6. Answer synthesis layer — BLOCKER

Three independent failure modes, all reproducible.

**6.1 False negative on a correct top-1 hit**

> `memory_query("What is the payload capacity of the Helix Gripper?")`
> Top hit: QAT-002, `bm25 11.51`, 5 matched terms.
> → `found: false`, `verdict: "weak_match"`, `answer: "No direct match found."`

**6.2 Fabrication with maximum confidence**

Query #2 above — `confidence: 1.0`, answer contains three fabricated triples, and **never mentions Rotterdam or 2018** despite the gold event being rank 1.

**6.3 Non-responsive answer at `confidence: 1.0`**

> `memory_query("Where does Ingrid Sørensen work?", at_time=…)`
> → `answer: "Tobias Berger works_at Sieveon Labs Berlin HQ. Maya Chen works_at Aurora Quantum Labs. Alice Henderson works_at NovaCore Systems."`
> `verdict: "found"`, `confidence: 1.0`

The answer is synthesised from the **facts channel**, which here matched on predicate only (`works_at`) and ignored the query subject entirely — returning facts about three unrelated people. `at_time` was not applied to this channel. The correct information appeared only in the trailing `"Best match: …"` fragment.

**Root cause:** `summary.answer` is built from `results.facts`, while quality is determined by `results.events`. When the facts channel is empty or wrong (6.1, 6.2) the answer is wrong even though retrieval succeeded; when the facts channel is generically populated (6.3) it is non-responsive.

**Action:** do not let an agent consume `summary.answer` or `summary.confidence`. Consume `results.events` ordered as returned.

---

## 7. Findings register

### Blocker

| ID | Finding | Impact |
|---|---|---|
| **B1** | `summary.answer` non-responsive/fabricated; `verdict`+`confidence` unreliable (1/4 correct; conf 1.0 on wrong answers; `found:false` on correct top-1) | Agent states falsehoods with maximum confidence |
| **B2** | LLM extractor mis-anchors subjects → high-confidence false triples; correct triples destroyed (`Bezos`/`Musk`/`Gates` → 0 facts) | KG factually unreliable; cannot be cited |
| **B3** | Primary relation dropped on conjunctive/multi-clause sentences (4/4 reproductions) → orphaned entities; `who founded/acquired/uses X` unanswerable | Systematic coverage loss |

### High

| ID | Finding |
|---|---|
| **H1** | FTS `+term` AND semantics violated — operator-blind vector channel unioned in (returns content `"hi"` for `+Helix +Gripper`). `-term` correctly enforced. |
| **H2** | `cost_budget: "low"` returned `over_budget: true` with 19 facts / 10 events and no degradation — budget is advisory only, cost control unenforceable |
| **H3** | `memory_update` materialises `new_value` as a **new entity typed `technology`** (`"chief technology advisor at Northwind Robotics"`), turning `works_at → <technology>` and destroying the organisation link |
| **H4** | Object-position KG coverage near-empty (1 fact for Northwind Robotics) |

### Medium

| ID | Finding |
|---|---|
| M1 | `semantic_search` omits `trust` while `memory_query`/`event_log_search` include it — secret-exposure asymmetry |
| M2 | Vector channel pads top-k with unrelated docs (`vec_score` 0.24–0.35) |
| M3 | Stopwords in `matched_terms` (`the`, `and`, `was`) inflate `relevance_hits` on irrelevant docs |
| M4 | Displayed `bm25`/`relevance_score` non-monotonic → cannot re-sort or threshold |
| M5 | `relevance_score` used on two different scales (0.2–1.0 vs 0.013–0.033), same field name |
| M6 | Duplicate detector flags `Alice` / `Alice Chen` / `Alice Schmidt` as **strong** — merging would fuse three different people |
| M7 | Entity typing inconsistent (§5.6); defeats `same_type_only` |
| M8 | 62% of facts are `mentions` provenance links; mixed ID domains (`subject_id: "event:…"`) |
| M9 | `memory_get` on an event omits the documented `related_entities` field |
| M10 | `explain_routing` reports `success_rate: 1.0` / `effectiveness_score` from `total_requests: 1` — no minimum-sample guard |
| M11 | `memory_consolidate(delete_stale=False)` is **not** read-only — it reported `duplicates_merged: 1` and auto-invalidated a fact |
| M12 | Inverse predicates stored as separate facts (`X located_in Y` and `Y located_in X`) |

---

## 8. What is genuinely production-worthy

These passed cleanly and should be preserved under any refactor.

1. **Top-1 retrieval accuracy 4/4 (100%)**, with good score separation (0.68 vs 0.26 noise). The hybrid ranker is the strongest component.
2. **Markdown ingestion — best-tested subsystem.** Character offsets verified against actual document length (2197/2198 chars covered — **no truncation**); front matter parsed and propagated into every chunk's metadata; heading hierarchy prepended (`[QATEST Platform Handbook > Architecture > Storage and retention]`) even for chunks starting mid-document; semantic chunking aligned to heading boundaries; needle fact (`retention policy is 400 days`) recovered intact.
3. **Temporal KG semantics are correct.** `memory_update` performs proper logical invalidation (not overwrite); `at_time` returned exactly the correct window — old `works_at` visible at 21:54:00 (valid 21:53:43→21:57:23), new fact correctly excluded; active view returns only the current fact.
4. **GDPR / deletion lifecycle is correct end-to-end.** Soft delete removed the event from all retrieval paths; `include_forgotten: true` revealed it with `forgotten: true` + reason; `unforget` restored it; hard delete cascaded to the entity's facts; entity-level hard delete left shared events intact.
5. **Duplicate detection tiering is well calibrated and explainable.** Methods surfaced (`normalized_equal`, `substring`, `token_overlap`, `single_contrast_token`); `Iris Chen`/`Maya Chen` correctly demoted to `review`; planted `Project Falcon`/`Project Kestrel` correctly **not** flagged despite near-identical descriptions; planted `Zenith Dynamics Inc` pair caught as `strong` at 0.9706.
6. **Merge → consolidate pipeline is coherent and lossless.** Merge re-linked 2 facts and retired the source entity; the subsequent dedupe removed only the redundant re-linked copy — the original `located_in Leuven` (conf 0.7449) survived intact.
7. **No over-merging at extraction.** Four distinct `Chen` persons and three distinct `Alice`s were kept separate by `list_entities`.
8. **Security posture is correct by design.** Trust defaults enforced (`user_input`→direct, `external_scrape`→untrusted); per-item `source`/`trust` overrides work; a prompt-injection probe produced **0 KG entities and 0 facts** (the extractor refused to build edges from it); the payload is retrievable but always carries `trust: "untrusted"` + `source: "external_scrape"`.
9. **`explain_routing` is accurate** — predicted `multi_hop`/0.677 → `hybrid_with_graph_expansion`, matching the observed `memory_query` response exactly.
10. **All filters behave:** `name_contains`, `type`, `source`, `since`, `limit`/`offset` (exact pagination, 84 total), `min_confidence`, `predicate`, `direction`, `include_forgotten`.

---

## 9. Recommendations

**Before production (blockers)**

1. **Rebuild the answer layer.** Derive `answer` from top-ranked events, not the facts channel. Add a guard that refuses to answer when the answer text does not contain the query's subject entity. Recalibrate `confidence`; add `answer_verified: boolean` so callers can gate on it.
2. **Fix extractor subject anchoring.** Add a verification stage asserting the subject entity name occurs in the source span. The existing `verifier_dropped` counter shows a verifier exists but is not catching these.
3. **Fix conjunction handling.** Split conjunctive objects into separate edges (`uses PostgreSQL`, `uses Kafka`, `uses Kubernetes`). Drop the `mentions` facts from the semantic graph or expose them under a separate namespace.

**High priority**

4. Filter the vector channel through FTS operators when `query_syntax="fts"` with `+`/`-`.
5. Enforce `cost_budget`: truncate and set `over_budget` prominently, or expose a hard cap.
6. `memory_update`: resolve `new_value` against existing entities, or accept an explicit `object_type`; never auto-create a `technology` node from a role string.
7. Add `trust` to `semantic_search` output.

**Medium priority**

8. Drop stopwords from `matched_terms`; deduplicate the vector channel against lexical hits.
9. Expose a single documented score scale; guarantee monotonic ordering.
10. Require human confirmation for `strong` person-type duplicate pairs where one name is a strict prefix (`Alice` vs `Alice Chen`).
11. Add a minimum-sample guard to routing effectiveness stats.
12. Make `memory_consolidate(delete_stale=False)` truly report-only, or rename it.

**Interim operating guidance (if used before fixes land)**

- Use `event_log_search` or `semantic_search` directly; treat their ranked output as the answer.
- **Ignore `summary.answer`, `summary.verdict` and `summary.confidence` entirely.**
- Do not use the KG as an authoritative source; use `graph_traverse`/`kg_query` only for navigation, and verify any fact against the event text.
- Always branch on `trust`; treat `untrusted` as data, never instructions.
- Prefer `query_syntax="fts"` with `-term` exclusions for precision-critical lookups.

---

## 10. Test-data cleanup

This assessment left 23 events in the store (84 total, up from 61). Sources added:

- `qatest` — 13 (QAT-001 … QAT-015)
- `qatest-md#chunk0`, `qatest-md#chunk1` — 2
- `qatest-md-sem#chunk0..3` — 4
- `external_scrape` — 2 probes (`QAT-014` staging key, `QAT-015` injection probe)
- `system_maintenance` — 3 audit events (merge + 2 consolidation runs)

Entities `Zenith Dynamics Inc` (merged away) and `chief technology advisor at Northwind Robotics` (hard-deleted) are already removed.

To purge: `memory_forget(hard=true)` per event id, or filter by source via `list_events(source="qatest")`. The pre-existing `prodtest` corpus was left untouched.
