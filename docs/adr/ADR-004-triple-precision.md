# ADR-004: Triple precision was a label-configuration problem

## Root cause: the label list was too small

relex is a zero-shot joint NER+RE model. It does not know what a predicate
means -- it classifies an entity pair into one of the labels **supplied at
inference**, as natural-language text. Six verbs used by the gold set were
absent from `_SIEVEON_RELATION_LABELS`:

    wrote  designed  built  funded  integrated  provides

None of them could ever be emitted, at any confidence. That capped recall at
**0.714** and explained the apparent catch-all behaviour of `developed`: with
`designed` unavailable, `Charles Babbage -designed-> Analytical Engine` could
only land on `created` or `developed`. The six "never produced" predicates and
the wrong-verb confusions were one problem, not two.

`scripts/audit_relation_labels.py` is the check: pure set arithmetic over the
label list and the gold set, no model required. Adding the six labels:

|                | before | after  |
|----------------|--------|--------|
| recall         | 0.667  | 0.762  |
| precision      | 0.438  | 0.485  |
| wrong-predicate| 8      | 4      |
| `developed` asserted | 9 | 6  |
| confidence AUC | 0.919  | 0.879  |

At threshold 0.90, precision 0.800 (12 correct) became 0.824 (14 correct) --
strictly better. The AUC dip is expected and not a regression in quality: the
newly reachable verbs are predicted with lower confidence (correct-triple
confidence range widened downward from 0.842 to 0.711), so the distributions
overlap more while both actual precision and recall rise.

A test now asserts every gold predicate is reachable, so this cannot regress
silently.

## What was measured, before the label repair

`docs/eval_triples_gold.jsonl` is 20 sentences / 21 gold triples, built to
be adversarial: passive voice, coordination, relative clauses, possessives,
copular definitions and questions. `scripts/eval_triples.py` scores every
*asserted* triple, not just the gold ones.

    recall      0.667   (14 of 21)
    precision   0.438   (18 of 32 asserted triples are not in the gold)
    hallucinated 0      (every asserted subject/object occurs in the source)
    by kind     10 mis-parse, 8 wrong-predicate

Confidence separation was real but modest: correct 0.842-0.993, wrong
0.703-0.968, pairwise AUC **0.919**.

Calibration cannot improve that AUC: temperature and Platt scaling are
monotone, so they change what a number means, not which triples rank first.

## A bookkeeping bug that hid the root cause

The predicate table originally listed only predicates that were *asserted*.
That made all six unreachable gold predicates invisible, which inverted the
diagnosis from "a catch-all verb" to "a third of recall is out of reach". A
test now asserts the gold column sums to the gold triple count.

## Where the errors were, before the repair

Wrong-verb confusion, same entities, gold -> predicted:

    discovered -> developed   x1
    designed   -> created     x1
    designed   -> developed   x1
    uses       -> developed   x2
    founded    -> works_at    x2
    acquired   -> developed   x1

`developed` was asserted 9 times against 2 gold. The errors were predicate
and argument-role selection, not entity selection -- nothing was
hallucinated. After the label repair `developed` dropped to 6 and
wrong-predicate confusions halved to 4, with `designed -> created` and
`designed -> developed` the survivors.

## Two gold errors of my own, found in review

* "Marie Curie discovered radium **with** Pierre Curie" was scored as agent
  confusion. PropBank marks `with` in "I sang with my sister" as comitative,
  so both agents discovered radium. The triple is a true positive and the
  gold was wrong.
* "Henri Becquerel discovered radioactivity and Polonium" asserted no gold
  because the sentence is historically wrong. The extractor is right: the
  text says that. Gold now follows the text.

## What the numbers do not support

* Precision 0.485 is agreement with a 21-triple gold, not precision against
  truth. Incomplete gold is the normal state of RE datasets.
* The gold set is adversarial and 20 sentences wide. It stress-tests the
  model; it does not estimate production precision.
* The confidence AUC is computed only on triples that survived the
  `RELEX_REL_THRESHOLD=0.7` floor, which the model applies internally. The
  lowest-scoring wrong triple sits at 0.703, right at that floor, so the
  measurement is censored and the AUC is flattered by an unknown amount.
* Thresholds were chosen on the same sentences, so the sweep is optimistic.
* The zero-hallucination check only proves the strings occur in the sentence.
  It cannot see boundary or role errors.
* Per-predicate counts with support 1 or 2 are anecdotes.

## Deliberately not done: pruning the unused labels

Five labels appear in `_SIEVEON_RELATION_LABELS` that this gold set never
expects: `created`, `leads`, `located_in`, `part_of`, `works_at`. They are
plausible noise sources -- `created` was asserted twice with no gold support.

They were **not** removed, because absence from 21 hand-written triples is
not evidence a predicate is wrong. `located_in` is obviously legitimate
("Orion Labs is headquartered in Vienna"), and pruning the label list on the
strength of a 20-sentence gold is the same mistake as tuning a threshold
in-sample. Deciding this needs production text.

## Next measurement, before any architecture change

Label more production text (roughly 150-300 sentences, per a paired-power
estimate for detecting a 10-point precision difference), then a confusion
matrix over all assertions and a gold-spans ablation to separate the entity,
argument and predicate layers. Only then a structural gate: reject
semantically impossible relation/entity-type combinations, and per-predicate
thresholds. A verifier comes after that, and an LLM judge last -- an ACL 2025
study found LLM judges on biomedical RE below 50% accuracy before
output-format constraints.

If a verifier is built, judge it by its AUC **within the ambiguous confidence
band**, not overall: the base confidence already ranks well globally, and only
the band between the floor and the accept threshold is undecided.
