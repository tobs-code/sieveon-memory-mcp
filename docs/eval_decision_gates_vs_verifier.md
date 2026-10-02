# Decision record: copular+event gate vs verifier

Measured on 118 hand-annotated production triples (LoCoMo, stratified).
Verifier trials ran on the same 118 triples, in the same harness, with the
same bootstrap procedure. The base P@R=0.60 of 0.482 is derived from both
reported deltas: 0.844 - 0.362 and 0.818 - 0.336.

| Measure              | Base               | Gates  | MiniLM2                 | DeBERTa-xsmall          |
|----------------------|-------------------:|-------:|------------------------:|------------------------:|
| Precision            | 0.441              | 0.479  | **0.698 (30/43)**       | —                       |
| Strict precision     | 0.297              | —      | **0.512 (22/43)**       | —                       |
| In-band AUC          | 0.578 [0.465-0.689]| —      | **0.840 [0.754-0.915]** | **0.905 [0.842-0.958]** |
| P@R=0.60             | **0.482**          | —      | **0.844 (+0.362)**      | **0.818 (+0.336)**      |
| Removed FPs          | —                  | **16** | **53 (of 75 total)**    | —                       |
| Lost TPs             | —                  | **6**  | **22 (of 75 total)**    | —                       |
| Latency p50 / p95    | —                  | —      | **1.6 / 1.9 ms**        | **5.9 / 66.2 ms**       |
| Adoption             | —                  | —      | **yes**                 | **yes**                 |

Pipeline end-to-end (gates + verifier, measured 2026-10-02 on the same 118):
every asserted triple ends in exactly one state (scripts/eval_pipeline_matrix.py,
docs/eval_pipeline_matrix.json):

| Path                | n  | right | wrong |
|---------------------|---:|------:|------:|
| structural_drop     | 22 |     6 |    16 |
| verifier_drop       | 53 |    16 |    37 |
| verifier_accept     | 28 |    23 |     5 |
| auto_accept         | 15 |     7 |     8 |
| floor_drop          |  0 |     0 |     0 |
| kept                | 43 |    30 |    13 |

Precision 0.698 (30/43) vs baseline 0.441 (+0.257), strict 0.512 (22/43) vs
0.297 (+0.215), retention 36.4%. The MiniLM2 column above is this pipeline
number: gates are already in the path, so a verifier-only column would
measure a configuration that never ships.

Two readings the matrix forces. The verifier is doing the work: it drops 53
of which 37 are wrong, and accepts 28 of which 23 are right. But auto-accept
is barely better than chance at 7 right of 15 -- that bucket holds the known
residual class (a very confident wrong triple, e.g. the Joanna `discovered`
at 0.97, auto-accepts by policy).

Per-path precision with Wilson 95% intervals:

| Path            |  n | right | wrong | precision | 95% CI      |
|-----------------|---:|------:|------:|----------:|:------------|
| structural_drop | 22 |     6 |    16 | —         | [0.132-0.482] |
| verifier_drop   | 53 |    16 |    37 | —         | [0.195-0.435] |
| verifier_accept | 28 |    23 |     5 | **0.821** | [0.644-0.921] |
| auto_accept     | 15 |     7 |     8 | **0.467** | [0.248-0.699] |
| kept            | 43 |    30 |    13 | **0.698** | —           |

The CIs are the point, not decoration: auto-accept at n=15 spans 0.248 to
0.699, which includes both "near chance" and "acceptable". Describing 7/15
as near chance is plausible; claiming it as established is not.

Shadow verifier on the auto-accepts (production path unchanged, measured
with --shadow):

| Band     | n | right | would-drop | would-keep | right lost |
|----------|---|------:|-----------:|-----------:|-----------:|
| 0.95-0.97| 6 |     2 |          4 |          2 | 0          |
| 0.97-0.99| 9 |     5 |          8 |          1 | 5          |

Extending the band downward would drop 12 to remove 7 wrong at the cost of
5 right -- and in the 0.97-0.99 band alone it would drop more right (5) than
wrong (3). That is not a recommendation to move the boundary; with n=6 and
n=9 it is evidence that the upper region needs more data before any move.
The production boundary stays at 0.95. These numbers are its baseline.

Coverage note: floor_drop is 0, which validates nothing about the <0.70
path. It means no asserted triple in this set scored below the floor, not
that the floor is correct. The implementation is tested
(tests/python_verifier_tests.py); its empirical effect is unobserved here.

Recall is still not measured. The precise claim is: the pipeline raises
precision substantially on the 118 annotated model assertions while
discarding most of them. Not: it improves extraction quality overall -- that
would need the triples the model never asserted.

The base rows are numbers, not estimates:
precision 52/118, strict 35/118, and the gate row is 36/96 after removing
22 rejected triples of which 16 were wrong.

Gate row details: the copular test alone rejects 34 triples of which 18 are
wrong, which is no better than the 56% wrong rate overall, and it also
rejects 16 correct triples. Alone it makes precision worse (0.441 -> 0.429).
Conjoined with event predicates it rejects 22 (16 wrong, 6 good). The
adjunct gates (recipient-not-location, purpose-not-object) fire zero times
against the annotation: identifying the surface verb and its direct object
is a dependency parse rather than a regex.

Decision rule for the verifier, agreed 2026-10-02: adopt it **only** if its
in-band AUC over the 0.70-0.95 confidence band beats the base confidence
there, **and** precision at fixed recall (e.g. 0.60) improves by at least 10
points with a bootstrap CI excluding zero. Overall AUC is the wrong number:
the base confidence already ranks well globally and only the band between
the floor and the accept threshold is undecided.

Both verifiers satisfy the rule, with room. Between them there is no
sufficient evidence of an AUC difference: their in-band AUC confidence
intervals overlap ([0.754-0.915] vs [0.842-0.958]). MiniLM2 was therefore
selected on measured latency, in particular its stable p95 of 1.9 ms against
66.2 ms for DeBERTa-xsmall. No selection was made on MNLI score and none on
overall AUC.

One point must not be lost: the base confidence reaches only AUC 0.578
[0.465-0.689] inside the relevant band. The verifiers improve discrimination
there substantially, so the verifier is not an optimisation of an existing
confidence signal -- it takes over the actual evidence check.

Conventions used throughout this file:

- Precision counts supported + implied. A right proposition on an imprecise
  predicate ("John works_at assistant manager" for a job title) is a fact
  the store can use and is not the same defect as a fabricated relation.
- Strict precision counts supported only. It is the lower bound and the one
  to cite when the claim is about fully correct facts.
- Recall is never reported from the annotation. It labels what the model
  asserted; it says nothing about triples it should have found.

Uniform sample, annotated 2026-10-02: the production-adjacent number
--------------------------------------------------------------------

Same semantics, same reconcile code (`--set uniform`), no merged headline
with the stratified set. The two samples answer different questions.

- 57 sentences, 84 asserted triples.
- Pre-pipeline: precision 0.310 (26/84), Wilson [0.221-0.415];
  strict 0.143 (12/84).
- Post-pipeline (`eval_pipeline_matrix.py --set uniform`):
  kept 29/84 (34.5%), precision 0.552 (16/29), Wilson [0.375-0.716];
  strict 0.207 (6/29).
- Partition: verifier_drop 55 (10 right / 45 wrong),
  verifier_accept 23 (13 / 10), auto_accept 6 (3 / 3),
  structural_drop 0, floor_drop 0.
- No copular+event frames and no sub-0.70 triples occurred in this sample,
  so those two paths contribute nothing here -- the 0.552 is the verifier's
  number alone.

Read against the stratified set (pre 0.441 -> post 0.698, retention 36.4%):
the uniform sample is worse both before and after the pipeline, and its
kept-precision CI ([0.375-0.716]) overlaps the stratified pre-pipeline
precision (0.441). The difference is the expected direction: the
stratified sample oversamples hard constructions, yet its baseline is
*higher*, not lower -- the extractor does comparatively well on its
targeted ambiguity classes and comparatively badly on ordinary sentences,
where creator overgeneration (`created` 1/12, `built` 0/6, `wrote` 0/6 on
this sample) dominates.

Strict precision on the uniform kept set (6/29 = 0.207) is the number to
cite when the claim is about fully correct facts in production-like text;
it is substantially below the stratified kept strict (0.512). This is the
cost of the pipeline keeping implied-but-imprecise triples: 10 of the 16
kept-right uniform triples are implied, not supported.

New error classes observed during uniform annotation (for the taxonomy,
not new labels):

- fabricated creator/agent relation: a mentioned concept becomes a
  `created`/`developed` relation of the subject even though no predicate
  substitution would fix it ([17], [18]).
- propositional-content-as-agent: content of a that-clause is attributed
  to the believer as an action ([29]).
- participation -> founder: `attended` entails `founded` ([43]).
- completion/achievement overgeneration: a purpose becomes a completed
  acquisition ([46] `acquired strategy skills`).
- requirement inverted as supply: `requires X` becomes `provides X`
  ([50] lilies/watering/sunlight).
- problem source as tool: `phone issues` becomes `uses phone` ([42]).

Strict entailment vs. broad precision, measured 2026-10-02
------------------------------------------------------------

Question: the uniform kept set shows strict 6/29 = 0.207 against broad
16/29 = 0.552. Is that a defect of the decision logic, or of the score?

`scripts/eval_verifier_strict.py`, same MiniLM2 scores over all 202
annotated triples from both sets, only the labelling swapped:

| Target                | n  | pos | AUC              | PR-AUC | P@R=0.60 |
| --------------------- | -- | --- | ---------------- | ------ | --------- |
| supported+implied vs wrong | 202 | 78 | 0.819 [0.763, 0.874] | 0.702 | 0.712 |
| supported vs rest         | 202 | 47 | 0.775 [0.707, 0.839] | 0.425 | 0.452 |

Those two overlap. The decisive numbers are the pairwise ones:

| Pair                   | n  | AUC              |
| ---------------------- | -- | ---------------- |
| supported vs wrong     | 171 | 0.837 [0.769, 0.897] |
| implied   vs wrong     | 155 | 0.792 [0.708, 0.870] |
| supported vs implied   | 78  | **0.527 [0.380, 0.666]** |

Mean margin by hand verdict: supported +5.930, implied +5.426,
wrong +2.459. The gap between not-wrong and wrong is about 3 margin
units; the gap between supported and implied is about half a unit.

So the verifier separates false from plausible well and is **at chance
on the supported/implied distinction** -- the interval contains 0.5. No
threshold on this score can substantially raise strict precision, because
the two classes are not separable in the score at all. `strict = 0.207`
is therefore not a threshold that was set wrong, and moving the accept
margin is not the fix.

What this rules out: a stricter accept margin, or a second, stricter
threshold on the same verifier margin. What it leaves open: a different
signal for strict entailment (a model or check that can read
"provides" as over-reading "bring"), which is a separate piece of work and
should be treated as such rather than as a threshold to tune.

**Decision, 2026-10-02: threshold tuning for strict entailment rejected.**
The verifier separates wrong from non-wrong claims but does not separate
supported from implied claims (pairwise AUC 0.527 [0.380, 0.666], interval
contains 0.5). Stricter thresholds on this signal therefore cannot
materially improve strict entailment precision. Do not revisit without a
different signal. Related: the auto-accept band is left unchanged because
n is too small (6 uniform, 15 stratified), not because it was tested to
insufficiency.

Extraction confidence is a weaker signal under both labellings
(0.570 / 0.625 AUC) and, notably, is *not* blind to the distinction --
which means it is not a candidate either, but it does not contradict the
verifier result: it is close to chance on both.
