# Decision record: copular+event gate vs verifier

Measured on 118 hand-annotated production triples (LoCoMo, stratified).
Verifier trials ran on the same 118 triples, in the same harness, with the
same bootstrap procedure. The base P@R=0.60 of 0.482 is derived from both
reported deltas: 0.844 - 0.362 and 0.818 - 0.336.

| Measure              | Base               | Gates  | MiniLM2                 | DeBERTa-xsmall          |
|----------------------|-------------------:|-------:|------------------------:|------------------------:|
| Precision            | 0.441              | 0.479  | —                       | —                       |
| Strict precision     | 0.297              | —      | —                       | —                       |
| In-band AUC          | 0.578 [0.465-0.689]| —      | **0.840 [0.754-0.915]** | **0.905 [0.842-0.958]** |
| P@R=0.60             | **0.482**          | —      | **0.844 (+0.362)**      | **0.818 (+0.336)**      |
| Removed FPs          | —                  | **16** | —                       | —                       |
| Latency p50 / p95    | —                  | —      | **1.6 / 1.9 ms**        | **5.9 / 66.2 ms**       |
| Adoption             | —                  | —      | **yes**                 | **yes**                 |

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
