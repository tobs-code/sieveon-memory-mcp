# ADR-002: Extraction measurement corrected — per-fact labels, and what salience actually does

- Status: proposed (2026-10-01)
- Context: `scripts/eval_extraction.py`, `EntropyGate.fact_salience`,
  `EntropyGate.tier_keep`
- No production behaviour changed by this ADR. It fixes the measurement and
  records the resulting open decisions.

## The measurement was wrong

`scripts/eval_extraction.py` iterated over **gold** triples. For every gold triple
the backend missed, it charged the miss with `max(salience)` over *all* triples
the backend produced for that sentence:

```python
# removed
cands = [EntropyGate.fact_salience(t.get("confidence", 0.5), t.get("predicate", ""), None)
         for t in trips if isinstance(t, dict)]
sal_wrong.append(max(cands))
```

That is not a measurement of any fact. A sentence holding one correct and one
wrong fact was counted once correct and twice wrong; a confidently wrong fact in a
mostly-correct sentence was invisible; and the score charged to a miss depended
on unrelated facts in the same sentence.

Its headline output was `correct mean=0.843 / wrong mean=0.844` for relex — read
as "salience does not separate correct from wrong". The overlap was an artefact of
the proxy, not of the scoring function.

## What the corrected measurement says

Facts are now labelled per produced fact: correct iff it matches a gold triple of
the same sentence (`src/eval/extraction_metrics.label_facts`). Gold set:
`docs/eval_extraction_gold.jsonl`, 31 sentences / 17 triples (20 English sentences /
13 triples after German was dropped, see "Language scope" below).

| backend | tripR (gold recall) | facts correct/asserted | fact precision | salience AUC [95% CI] |
|---|---:|---:|---:|---|
| relex | 0.706 | 13/45 | 0.29 | **0.817** [0.663, 0.933] |
| gliner | 0.941 | 18/75 | 0.24 | **0.500** [0.500, 0.500] |
| spacy | 0.000 | 0/15 | 0.00 | n/a (no positive class) |

(Fact precision excludes facts asserted on junk sentences; those are counted
separately as `facts_from_junk_sentences`: relex 8, gliner 14, spacy 3.)

Three findings, in order of how much they change decisions:

1. **Two thirds of what the KG is told is wrong.** relex asserts 45 facts to get 13
   right. `tripR=0.706` (a recall number) had been the headline and reads far
   healthier than the precision reality.

2. **Salience *does* rank relex facts — it just cannot threshold them.**
   AUC 0.817 is real and its CI excludes 0.5. But relex salience occupies
   [0.697, 0.873] for wrong facts and [0.774, 0.873] for correct ones: the
   distributions overlap almost completely, and *every* relex fact sits far above
   `TIER_DROP_THRESHOLD=0.50`. At 0.50 the tier drops **0 of 24** wrong facts.

   `TIER_DROP_THRESHOLD=0.50` is calibrated in the wrong units for the current
   formula. Sweep on relex:

   | threshold | correct kept | wrong dropped | kept precision |
   |---:|---:|---:|---:|
   | 0.50 (shipped) | 13/13 (100%) | 0/32 (0%) | 0.29 |
   | 0.78 | 12/13 (92%) | 12/32 (38%) | 0.38 |
   | 0.80 | 11/13 (85%) | 18/32 (56%) | 0.44 |
   | 0.84 | 7/13 (54%) | 25/32 (78%) | 0.50 |

3. **gliner's salience is a constant.** Its confidence is always 0.70 and its
   predicates are all SVO (specificity 1.0), so every fact it emits scores
   exactly 0.695. AUC is 0.500 by construction — the score carries no information
   for that backend, so no threshold can help it either.

## Also found: spacy asserts nothing correct

spacy produced 0 correct facts out of 15. This is consistent with its
`tripR=0.000` and the README note that spaCy dependency labels do not match KG
predicates. It is not a threshold problem — it is a backend that should not be in
the triple chain.

## Open decisions (not decided here)

**A — Tiering scope.** 86% of wrong relex facts (89/104 pooled across backends) are
SVO predicates. ADR-001 decided "SVO facts are never tiered", so the tiering
mechanism structurally cannot touch the dominant failure mode. Extending tiering
to SVO trades recall for precision per the sweep above.

**B — Threshold units.** `TIER_DROP_THRESHOLD=0.50` is inert against the current
formula. Either recalibrate it into the observed range, or rescale the formula.

**C — Backend policy.** spacy contributes 0 correct facts. Removing
`extract_triples_with_spacy` from the chain would delete ~100% of its facts at
zero recall cost; its entity extraction is a separate question (entR 0.981).

**D — Gold set size.** 17 gold triples is small. The CIs above are wide and any
weight tuning done on this set would be overfitting. `bootstrap_auc` reports the
interval so this stays visible; expanding the gold set is a prerequisite for
tuning, not an optional extra.

**E — Consumer.** `fact.salience` is written but never read: no retrieval strategy
or ranking path in `src/planner/executor.py` references it. Its only effect today
is the create-time tier decision. If salience is meant to influence retrieval
ranking, that consumer does not exist yet.

## Consequence for ADR-001

ADR-001 named "salience threshold validation on a labeled triple set" as an open
follow-up and assumed a labeled set would confirm or refute the mechanism. It
refutes the threshold (finding 2) while leaving the ranking signal intact
(finding 2, positive half). The v1 formula is not useless — it is misapplied.

## Language scope: English only (decided 2026-10-01)

Splitting the gold set by language showed where a large share of the noise came
from:

| language | gold triples | triple recall | facts asserted | correct | fact precision |
|---|---:|---:|---:|---:|---:|
| English | 13 | 0.462 | 48 | 9 | **0.188** |
| German | 4 | 0.250 | 36 | 1 | **0.028** |

German produced one correct fact out of 36 — consistent with the entity
fragmentation seen in live runs (`Applied Cognition Lab` split into
`Elena works_at Cognition` and `Elena works_at Lab`). The embedding model is
English-only by the project's own documentation, so multilingual support was
already half-claimed.

The German sentences were removed from the gold set rather than tuned. Caveat:
n=4 gold triples, so the direction is well supported but the exact ratio is not
precise.

Going English-only does not solve relation precision — English alone is still
0.188. It removes the worst tail, not the problem.

## Root cause: the relation head has no negative class

arXiv:2605.10108 (GLiNER-Relex), §3.5/§3.6/§3.9, plus A/B measurements on the
gold set:

* **All-pairs enumeration** over recognized entities, and
* relation scoring as `MLP([head;tail]) · relation_label_embedding`, with
* **no "no relation" class** in the label set.

So the model must name a relation for every ordered entity pair;
`relation_threshold` is its only way to decline. This is what produces
`VectorDB developed engine` at 0.836 from a sentence containing no such verb.

Four mitigations were tested and rejected:

| mitigation | result |
|---|---|
| `adjacency_threshold=0.6` | **no-op** — the released checkpoint uses all-pairs and ships no adjacency decoder (λ_A=0, Table 1 "Adjacency decoder: none"). Identical output at 0.6. |
| `flat_ner=False` (the model card's examples) | **worse** — overlapping entities ("VectorDB" *and* "VectorDB engine") create extra pairs and extra relations |
| negative relation label ("no relation", "unrelated", "mentioned together") | **refused** — assigned 0 times at `relation_threshold >= 0.7` (0 of 122). Never trained on such a label. |
| `relation_threshold` 0.7 → 0.9 | factP 0.122 → 0.176 but tripR 0.293 → 0.220. Wrong trade. |

The one documented feature the code does not use is **label descriptions**
(`labels` as `{name: description}` instead of bare strings). Measured as the only
intervention that helped: at `relation_threshold` 0.9, factP 0.176 → 0.304.

Relation loss uses focal loss with α=0.75, **γ=0** — no focusing — under the
severe positive/negative imbalance the paper describes, which matches the observed
overconfidence (max score on a wrong fact: 0.996; on a correct one: 0.987).

## Reproduction attempt: GLiREL's published numbers are not obtainable

GLiREL (arXiv:2501.03172, Boylan et al., NAACL 2025) was the leading candidate to
replace GLiNER-Relex, for three reasons: it operates on pre-identified entities
(our NER is entR 1.000 on English gold), it has a **trained** `no relation` label,
and it can be followed by an ontology type filter.

Measured on the English gold set with our relex NER, GLiREL looked decisive:

| system | facts | correct | fact precision | triple recall |
|---|---:|---:|---:|---:|
| GLiNER-Relex joint (current) | 30 | 6 | 0.200 | 0.385 |
| + GLiREL, threshold 0.3, ontology filter | 12 | 9 | **0.750** | 0.692 |
| + GLiREL, threshold 0.5, ontology filter | 9 | 8 | **0.889** | 0.615 |

**That number is not corroborated and must not be relied on.**

Reproduction against the paper's own protocol (FewRel 1.0, human-annotated,
44 800 instances, m=15 held-out relations, gold entity spans, §4.2):

| path | best micro-F1 |
|---|---|
| `glirel` 1.2.1 + `jackboyla/glirel-large-v0` | 0.238 |
| `glirel` 0.1.4 + `jackboyla/glirel_beta` (the path every README example uses) | 0.281 |
| paper, Table 1, m=15, FewRel | 70.40 (plain) / 84.48 (+synthetic) |

A plateau at ~0.25-0.28 across 21 threshold x top_k combinations, two checkpoints
and two library versions. The cause is structural: both public checkpoints carry
`dataset_name=zero_rel`, `train_data=[zero_rel_all.jsonl]`, `prev_path=none` — they
were trained only on the synthetic ZeroRel corpus. The paper trains a separate
model per experiment "from scratch on the given dataset", i.e. on FewRel/WikiZSL
themselves. **Neither evaluated model is published, so the published numbers
cannot be reproduced from any available artifact.**

The "kaputtes Encoding in FewRel" hypothesis raised during this work was wrong:
the file is valid UTF-8 and `Miloš` is intact. It was an artifact of my own
log-display pipeline.

### Integration facts worth keeping

* `predict_relations()` requires a **plain list** of labels. The README's
  `{"glirel_labels": {label: {"allowed_head": [...], "allowed_tail": [...]}}}`
  form is only consumed by `constrain_relations_by_entity_type()`
  (`glirel/modules/utils.py`), which runs *after* prediction and needs spaCy Doc
  entities. Passing the dict in makes `collate_fn` iterate the dict and take the
  top-level key, so every relation returns labelled `glirel_labels` at ~0.005
  (`glirel/modules/base.py:321`).
* Type constraints must therefore be applied as a post-filter. `validate_predicate()`
  in `src/extraction/entity_utils.py` does the same job against our ontology, and
  on the English gold set it removed mostly relation inverses.
* Tokenisation must match `glirel/model.py:523` (`\w+(?:[-_]\w+)*|\S`), not
  `\S+`. Misaligned entity indices silently produce garbage.
* GLiREL returns its own normalised spans (`[16,17]` for a gold `[16]`, absorbing
  the adjacent quote token), so compare extracted text, not positions.

### Conclusion

The GLiREL path stays **open but unproven**. Deciding it requires an eval set we
trust, which is the actual blocker -- not the model choice.

### Update (2026-10-01): GLiREL is closed, for a measured reason

The fair pipeline test — same 375 human-annotated FewRel sentences, same label
vocabulary, but GLiREL fed with **relex-predicted** entities instead of human
spans — reverses the earlier result:

| system | facts | correct | fact precision | triple recall |
|---|---:|---:|---:|---:|
| GLiNER-Relex joint (current production path) | 926 | 119 | **0.129** | 0.288 |
| relex-NER + GLiREL, thr=0.3 | 1938 | 73 | 0.038 | 0.189 |
| relex-NER + GLiREL, thr=0.5 | 622 | 50 | 0.080 | 0.128 |
| relex-NER + GLiREL, thr=0.7 | 147 | 23 | 0.156 | 0.059 |

The earlier 0.750–0.889 was entirely an artefact of feeding GLiREL human NER on
13 triples. With the entities it would actually receive, GLiREL asserts 1 938
facts to get 73 right — worse than doing nothing. relex's NER errors feed
GLiREL's forced all-pairs classification, exactly the error propagation the
joint architecture was built to avoid. **Do not integrate GLiREL.**

That leaves the unsatisfying but honest fact: on human-annotated Wikipedia prose,
relex asserts 926 facts to get 119 right. The project set (see below) reads much
healthier because its sentences are canonical (active voice, named founder,
single relation). Both are true: the model handles canonical phrasing and fails
on real prose. The gap between 0.509 (project) and 0.129 (FewRel) *is* the
measurement of how far production text is from canonical text.

## Gold set, second version (2026-10-01)

- 39 sentences / 32 triples, all English, every extraction predicate covered.
- 16 new sentences are well-known, checkable real-world facts
  (`Microsoft acquired GitHub in 2018`, `Fleming discovered penicillin in 1928`)
  rather than invented prose, so the labels are true by reference, not by my
  judgement.
- The first v2 attempt (nominalised, passive, multi-triple adversarial sentences
  authored by hand) was discarded: it contained real labelling errors
  (`is behind` as `acquired`, `founded -> Hamburg` with the wrong target) and is
  not a substitute for a protocol. Adversarial cases return once the basics
  hold and are labelled with a review step, not from memory.
- A consistency test (`test_every_gold_predicate_validates`) asserts every gold
  triple passes `validate_predicate()`. It immediately caught five real defects:
  `discovered` missing from the ontology entirely; `developed` and `published`
  rejecting organisations as subjects; `part_of` restricted to concepts; and one
  inherited v1 mislabel (`Acme Corp founded Munich`, corrected to `located_in`).

## Embedding shootout (2026-10-01): the embedder is not the bottleneck

Same 39-sentence corpus, same 34 queries (30 answerable + 4 no-answer probes),
only the encoder changes. Each model under its own documented convention.

| model | MRR | recall@1 | paraphrase MRR | no-answer floor | dim | serving |
|---|---:|---:|---:|---:|---:|---|
| Qwen3-Embedding-0.6B, torch (current) | 0.983 | 0.967 | 1.000 | 0.285 | 1024 | in-process |
| qwen3-embedding:0.6b | 0.983 | 0.967 | 1.000 | 0.402 | 1024 | ollama |
| qwen3-embedding:4b @1024d (Matryoshka) | **1.000** | 1.000 | 1.000 | 0.422 | 1024 | ollama |
| nomic-embed-text-v2-moe | 0.983 | 0.967 | 1.000 | **0.261** | 768 | ollama |
| nomic-embed-text v1 | 0.654 | 0.500 | 0.368 | 0.578 | 768 | ollama |

Three conclusions:

1. **Ranking is at ceiling.** 0.983 → 1.000 is one query. The embedder is not
   the retrieval bottleneck, so no swap is justified on ranking quality. The
   remaining retrieval headroom is in routing and extraction, not vectors.
2. **The Ollama path costs separation.** Identical 0.6B weights score the
   no-answer floor at 0.285 (torch, with the documented query prompt) vs 0.402
   (Ollama, no per-request instruction). Whatever Ollama's Modelfile does, it
   is not the Qwen query instruction.
3. **nomic v1 is out** (worse on everything). nomic v2-moe has the best floor
   but needs a 768d index migration for a 0.024 gain — not worth it.

Consequences: keep torch Qwen3-Embedding-0.6B. Do not download stella's 6.2 GB
fp32 weights — even a perfect encoder cannot beat MRR 1.0, and the measured
headroom is one query. Do not move embeddings to Ollama: same ranking, worse
separation, plus an extra service and the version fragility already observed
(upstream issue: 0.12.6 broke Qwen3-Embedding serving). The Matryoshka finding
(qwen3-embedding:4b emitting exactly 1024 dims) stays on record for the day the
corpus outgrows the ceiling — it is the only upgrade path that needs no index
migration.

Caveat: 39 clean sentences cannot separate good encoders. If a harder corpus
with near-duplicate distractors ever shows ranking headroom, revisit.

## Correction (2026-10-02): the "overlap almost completely" claim was wrong

An earlier version of this document concluded that the score distributions
for correct and wrong facts "overlap almost completely", based on a
threshold sweep that moved fact precision only 0.12 -> 0.18 between 0.7 and
0.9. That sweep used `fact_salience`, a heuristic computed **per source
text**, so every triple extracted from one sentence shares the same value.
A per-text score structurally cannot separate correct from incorrect
triples *within* a sentence, which makes the overlap an artefact of the
measurement rather than a property of the model.

Measuring the raw relex confidence per triple against per-triple
correctness gives AUC 0.919 instead — see
[ADR-004](ADR-004-triple-precision.md). The two numbers do not contradict
each other; they are two different predictors, and the raw confidence is
the relevant one for filtering triples. Do not use the old claim as
counter-evidence.

The 95% CI on that AUC is roughly 0.81-1.0 at 13 correct vs 19 wrong, so it
is directionally useful and nowhere near settled. It is also computed only on
triples that survived the model's internal `RELEX_REL_THRESHOLD=0.7` floor,
with the lowest-scoring wrong triple sitting at 0.703 — right at that floor.
The measurement is therefore censored and the AUC flattered by an unknown
amount.

## Reproducing

    python scripts/eval_extraction.py          # per-fact metrics, AUC, tier operating point
    python scripts/eval_extraction.py --sweep  # RELEX_REL_THRESHOLD sweep
    python -m pytest tests/python_unit_tests.py -k "Extraction"
