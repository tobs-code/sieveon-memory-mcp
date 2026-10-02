# Decision record: copular+event gate vs verifier

Measured on 118 hand-annotated production triples (LoCoMo, stratified).

| Measure                        | Base   | Gates  | Verifier |
|--------------------------------|-------:|-------:|---------:|
| Precision (supported+implied)  |  0.441 |  0.479 | ?        |
| Strict precision (supported)   |  0.297 |      ? | ?        |
| In-band AUC (0.70-0.95)        |  base  |      - | must be > base |
| Removed false positives        |      - |     16 | ?        |
| Lost true positives            |      - |      6 | ?        |

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

Conventions used throughout this file:

- Precision counts supported + implied. A right proposition on an imprecise
  predicate ("John works_at assistant manager" for a job title) is a fact
  the store can use and is not the same defect as a fabricated relation.
- Strict precision counts supported only. It is the lower bound and the one
  to cite when the claim is about fully correct facts.
- Recall is never reported from the annotation. It labels what the model
  asserted; it says nothing about triples it should have found.
