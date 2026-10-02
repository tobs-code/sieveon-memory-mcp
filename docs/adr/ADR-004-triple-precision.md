# ADR-004: Triple precision is a label-coverage problem, not a confidence problem

## What was measured

`docs/eval_triples_gold.jsonl` is 20 sentences / 21 gold triples, built to
be adversarial: passive voice, coordination, relative clauses, possessives,
copular definitions and questions. `scripts/eval_triples.py` scores every
*asserted* triple, not just the gold ones.

    recall      0.667   (14 of 21)
    precision   0.438   (18 of 32 asserted triples are not in the gold)
    hallucinated 0      (every asserted subject/object occurs in the source)
    by kind     10 mis-parse, 8 wrong-predicate

Confidence separation is real but modest: correct 0.842-0.993, wrong
0.703-0.968, pairwise AUC **0.919**. Threshold sweep:

| threshold | kept | correct | wrong | precision |
|-----------|-----:|--------:|------:|----------:|
| 0.70      |   32 |      13 |    19 |   0.406   |
| 0.90      |   15 |      12 |     3 |   0.800   |
| 0.95      |    8 |       7 |     1 |   0.875   |

Calibration cannot improve the AUC: temperature and Platt scaling are
monotone, so they change what a number means, not which triples rank first.

## The finding that changed the diagnosis

The first version of the predicate table listed only predicates that were
*asserted*. That hid six gold predicates the model never emits at all:

    wrote  designed  built  funded  integrated  provides

Six of 21 gold triples, unreachable at **any** confidence threshold because
the model does not produce those labels. The reported table made the problem
look like over-production of `developed`; it was in part a label-coverage
gap. A test now asserts the gold column sums to the gold triple count, so
the table cannot silently drop gold-only predicates again.

## Where the errors actually are

Wrong-verb confusion, same entities, gold -> predicted:

    discovered -> developed   x1
    designed   -> created     x1
    designed   -> developed   x1
    uses       -> developed   x2
    founded    -> works_at    x2
    acquired   -> developed   x1

`developed` behaves as a catch-all: 9 asserted against 2 gold. The errors
are predicate and argument-role selection, not entity selection -- nothing is
hallucinated.

## Two gold errors of my own, found in review

* "Marie Curie discovered radium **with** Pierre Curie" was scored as agent
  confusion. PropBank marks `with` in "I sang with my sister" as comitative,
  so both agents discovered radium. The triple is a true positive and the
  gold was wrong.
* "Henri Becquerel discovered radioactivity and Polonium" asserted no gold
  because the sentence is historically wrong. The extractor is right: the
  text says that. Gold now follows the text.

## What the numbers do not support

* Precision 0.438 is agreement with a 21-triple gold, not precision against
  truth. Incomplete gold is the normal state of RE datasets.
* Clopper-Pearson 95% CI: precision at 0.70 is 0.24-0.59, at 0.90 is
  0.52-0.96. Indistinguishable at this size.
* The thresholds were chosen on the same 20 sentences, so the sweep is
  optimistic by construction.
* The zero-hallucination check only proves the strings occur in the sentence.
  It cannot see boundary or role errors.
* Per-predicate counts with support 1 or 2 are anecdotes.

## Next measurement, before any architecture change

A confusion matrix over all assertions (done above, now in the script), then
a gold-spans ablation to separate the entity, argument and predicate layers.
Only then a structural gate: reject semantically impossible relation/entity
type combinations, and per-predicate thresholds. A verifier comes after that,
and an LLM judge last -- an ACL 2025 study found LLM judges on biomedical RE
below 50% accuracy before output-format constraints.
