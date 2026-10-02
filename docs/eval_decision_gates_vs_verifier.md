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
at 0.97, auto-accepts by policy). Widening the band upward would trade those
auto-accepts for verifier load and needs its own measurement; the current
numbers are the baseline for it.

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
