
## Retrieval scoring and the accept decision (2026-10-02)

Separated two questions that were being answered with one number.

### Ranking is not confidence

`_calculate_relevance_score` used to average the top three `vec_score`
values and mix in a term-coverage ratio. Measured on
`docs/eval_retrieval_gold.jsonl` that scored a paraphrase **0.36** and an
unrelated query **0.31** — no separation at all. Averaging three scores and
adding coverage dilutes the one signal that discriminates.

The score is now the **top-1** vector similarity, with cross-channel
agreement and top BM25 able to raise it but never to rescue a weak semantic
match. Separately, each strategy now reports `retrieval_diagnostics`
(`_channel_diagnostics`) captured *before* fusion, because once channels are
fused it is no longer knowable whether a top hit was found by one channel or
corroborated by both.

### Measured separation (30 answerable, 4 no-answer)

| Signal                    | AUC   | answerable    | no-answer   |
|---------------------------|-------|---------------|-------------|
| top-1 vector similarity   | 1.000 | 0.524 – 0.818 | 0.224 – 0.335 |
| lexical hit count         | 0.992 | 1 – 11         | 0 – 1      |
| top BM25                  | 0.979 | 1.74 – 9.76    | 0 – 3.25   |
| cross-channel agreement   | 0.933 | —              | —          |

Accept threshold **0.43**, in the middle of the observed gap. It is not a
knife edge: every threshold from 0.35 to 0.50 yields 0 false positives and 0
missed answers on this set, and 0.30 admits 2 false positives while 0.55
starts dropping answers. Leave-one-out over the no-answer probes reproduces
the gap in 3 of 4 folds.

### The score-channel fusion was 98% vector

`_execute_semantic_hybrid` combined channels as
`0.5 * rrf_term + 0.5 * vec_score`. The RRF term spans 0.0132–0.0167 while
`vec_score` spans ~0.23–0.76, so the blend measured **2.1% RRF, 97.9% vector**
— the lexical channel contributed nothing while appearing to. Adding an
unbounded and a bounded score with equal weights is not sound; the fusion is
now rank-based only, which is scale-free by construction.

### What this is not

A cosine score is not comparable across queries in general: a ranking-trained
embedding optimises relative order *within* a query, not an absolute
probability of relevance. So 0.43 is an empirical constant for this embedding
model on this corpus, not a universal threshold. Re-measure with
`scripts/eval_retrieval.py` after changing the model or corpus.

Four no-answer queries is a thin basis for an operating point. The
principled long-term answer is a trained abstention model over
query-level features (QPP in the IR literature) compared against a
Chow-rule threshold, not a hand-placed constant.
