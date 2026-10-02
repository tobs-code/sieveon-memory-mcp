# Recall harness: frozen reporting contract

Created 2026-10-02, after the 20-sentence pilot. The gold in
`docs/eval_recall_gold_pilot.jsonl` is frozen. This file fixes what may be
quoted and how, because the pilot produced three different numbers for
"recall" and only one of them is about the extractor.

## The three numbers, always together

    semantic gold coverage   every gold fact the annotator accepted,
                             including facts the schema cannot express
    scorable recall          gold facts the production vocabulary can
                             express, found by the extractor
    scorable clean recall    of those, found with a predicate the wording
                             actually licenses

The first is a property of the schema, the second and third of the
extractor. Reporting `scorable recall` alone invites the reading "recall
is perfect", which this pilot cannot support at n=13.

Pilot values, stated as pilot values:

    semantic gold coverage  13/14 = 0.929
    scorable recall         13/13 = 1.000
    scorable clean recall    4/13 = 0.308

Approved wording:

> Within the existing relation schema the pilot shows no observed recall
> loss: 13 of 13 scorable gold facts were found.

Not approved: "recall is 1.0" without that qualification, and any framing
of the 0.929 as a statement about the full relation vocabulary rather than
about the sentences in this pilot.

## Vocabulary gap: two different things, kept apart

They share a name and must not be merged, because they have different
causes and different owners.

  schema_gap in the gold file   facts the annotator kept out of `triples`
                               because they do not belong to the current KG
                               scope. 3 in the pilot: `requires watering`,
                               `requires sunlight`, `watched That`.
                               Nobody failed; the relation was never wanted.

  vocabulary audit              gold facts the annotator DID accept, which
                               the production chain cannot express. 1 in the
                               pilot: `Deborah -received-> quote`. The fact
                               is real and stays in the frozen gold; it is
                               unscorable, so it is not an extractor miss.

Both are reported. Neither substitutes for the other.

## Claim buckets, and what each one needs

    found / imprecise     the gold fact was extracted
    below_threshold       graphable, under the gold bar -- not an error
    discipline            right entity pair, wrong relation
    spurious              the sentence does not carry the fact
    non_graphable         sentence out of scope, out of the precision
                          denominator
    schema_gap_claims     vocabulary-gap sentence, reported apart unless the
                          row sets schema_gap_claims: "spurious"

`below_threshold` exists because the first pilot counted 16 of these as
false positives and produced a precision of 0.042 that measured the gold
annotator's strictness rather than the extractor. Corrected precision on
the same data is 0.333.

The vocabulary-gap judgement call is reported both ways on purpose:
0.333 with those claims held apart, 0.271 charged to precision. Neither
number is presented alone.

## Match rule

Subject, predicate and object equal after normalisation; argument order is
not swappable; predicate equivalence limited to the synonym groups in
`EQUIVALENT`, each attested in the earlier hand annotation. No credit for
started/founded, travel/works_at, attend/works_at, check_out/acquired. A
gold triple found through a predicate the annotation called wrong is not
counted as found.

## Not measured

Recall against facts nobody wrote down. A gold of 13 scorable facts across
20 sentences cannot bound what the extractor misses on unseen phrasings.

## Consistency audit across the two gold files, 2026-10-02

`scripts/check_gold_consistency.py` compares the recall gold against the
uniform triple annotation on the sentences they share. It is rerunnable,
because at ~100 facts a hand comparison stops being possible and a
convention drift would scale invisibly.

    identical              8
    severity divergence    6
    scope agreement       18
    schema gap             3
    never claimed          1

The 6 divergences, all severity, never facthood:

| Fact                                        | triple file | recall gold |
| ------------------------------------------- | ----------- | ----------- |
| `Melanie -developed-> environment`           | implied     | clean       |
| `Joanna -developed-> projects`               | implied     | clean       |
| `Jolene -uses-> bullet journal`              | supported   | imprecise   |
| `Susie -provides-> comfort`                  | supported   | imprecise   |
| `Susie -provides-> peace`                    | supported   | imprecise   |
| `bike routes -located_in-> river`            | supported   | below bar   |

Both files agree these facts exist and both decline two of them outright.
They disagree only on how strongly the wording supports them, and in both
directions: the recall gold is stricter in three cases and looser in two.

Consequence for reporting. `scorable clean recall` of 4/13 is the
pessimistic reading -- three of those four are called supported by the
triple file. The optimistic reading is 6/13. Neither is wrong; they answer
different questions, so the figure must always be quoted with which file
it came from.

### The disputed case: `bike routes located_in river`

The frozen rule says `near` does not entail `located_in`, and the recall
gold holds it below the bar. The triple file calls it supported. **This is
kept as a deliberate divergence and neither file is edited.** It is the
cleanest illustration of why the two files coexist: asked whether the
sentence licenses that claim, it does; asked whether the fact belongs in a
knowledge graph, it does not. Collapsing them would lose one of the two
questions.

### Which file answers which question

`docs/eval_triples_gold_locomo_*_model.jsonl`
: authoritative for precision. Its verdict classes judge a specific claim
  the extractor made. Use it for anything phrased as "is this claim right".

`docs/eval_recall_gold_pilot.jsonl`
: authoritative for coverage. Its `triples` list enumerates facts, and its
  severity flags are calibrated to coverage, not to claim adjudication. Use
  it for anything phrased as "should this fact be in the graph".

Never average a number from one file into a sentence about the other. Where
a figure could be read either way, quote both with their source.

## Batch 2 and the three axes, 2026-10-02

Ten further sentences annotated gold-first, selected by text features only
(`scripts/select_recall_batch.py`), then scored against the extractor.

    30 sentences, 21 gold facts (20 scorable, 1 vocabulary gap)

    found 6   imprecise 10   missed 5
    below_threshold 19   discipline 3   spurious 5

    scorable recall   0.800  (16/20)   pilot said 1.000 (13/13)
    scorable clean    0.300  (6/20)
    precision         0.372  (16/43)

The pilot's 1.000 was a small-sample effect and is now superseded. The four
new misses are one defect type, and a new one: the sentence is there, the
relation exists in the vocabulary, and nothing was asserted at all.

    Maria  -provides-> support         Audrey -provides-> support
    Maria  -provides-> encouragement   Audrey -provides-> assistance

This is an extraction dropout, not a predicate error and not a discipline
error. It cannot show up in any precision figure, because a missing claim
never appears as a wrong claim. `check_gold_consistency.py` counts these
five as `never claimed`, which is exactly the missed count -- an independent
confirmation that the harness detects the absence rather than filing it
under some other bucket.

### Expanded sample, batches 1 to 4 (40 of 100 annotated)

| | batch 1 | batch 2 | batch 3 | batch 4 |
| --- | --- | --- | --- | --- |
| graphable | 3/10 | 6/10 | 4/10 | 5/10 |
| gold facts | 1 | 6 | 1 | 3 |
| schema-gap facts | 3 | 3 | 3 | 5 |

Cumulative over all annotated rows (uniform and expanded together, 70 of130):

| | |
| --- | --- |
| scorable recall | 0.700 (21/30) |
| scorable clean | 0.267 (8/30) |
| precision | 0.368 (21/57) |
| vocabulary-gap facts | 25 |
| sentence-level dropout | 16 of 70, 2 carrying gold |

The numerator moved once in four batches. Batch 3 added three gold facts and
found none of them; batch 4 added three and found one. The estimate drifts
down because the denominator grows faster than the hits, not because the
extractor degrades.

### Two error classes, empirically separated in one population

| class | count | example |
| --- | ---: | --- |
| schema gap | 25 facts, 9 predicates | `Tim owns book collection` |
| extractor miss | 9 facts | `Nate acquired Max` |

`Nate -acquired-> Max` is the clearest proof they are not the same thing: the
predicate exists in the vocabulary, the object is named outright, the sentence
states the adoption, and no claim was produced. Extending the vocabulary would
not have prevented it.

Vocabulary gaps in the expanded sample, by predicate:

    owns 5   attended 4   noticed_by 1   joined 1   watched 1
    auditioned_for 1   pitched_to 1   earned 1   drafted_by 1

`owns` and `attended` account for 9 of the 16 annotated gaps. `owns` in
particular is a possession relation the corpus uses constantly -- "his
recipe", "has a recipe", "has a book collection" -- and the production chain
cannot state it. That is a dominant observed gap, not an exotic case.

### A rule that held, and what it prevented

"Possession says neither acquisition nor authorship." Applied unchanged
across batch 4, it blocked `Joanna created chocolate and raspberry cake
recipe` from `has a recipe`. Three of the four `created`/`acquired` errors in
the gold would otherwise have been annotation artefacts rather than extractor
defects, and the extractor would have been measured against facts it was
never asked for. The same rule blocked `Nate created cork board` (from
"his own") and `Nate created dairy-free dessert recipe` (from "his").

### Two limits on the current reading

The `provides` misses share a shape -- `support`, `encouragement`,
`assistance`, `creativity`, `mentoring`, all abstract or service-like
objects -- but that is a reproduced pattern, not a causal finding. Argument
structure, nominal complementation, verb form and candidate generation are
all still open explanations.

And the cumulative series mixes two populations: 30 annotated uniform
sentences and 40 annotated expanded ones. It is the right size for the
question "is coverage around 0.7", but it is not a time series over one
growing sample, and it should not be read as one.

| axis | measure | value |
| ---- | ------- | ----- |
| extractor coverage | scorable recall | 0.700 (21/30) |
| predicate quality | scorable clean recall | 0.267 (8/30) |
| schema expressiveness | gold facts outside the vocabulary | 25 |

Superseded interim values, kept for the trail: scorable recall was 0.800
(16/20) at 40 annotated rows and 0.762 (16/21) at 50; the schema count was
10 then. There is deliberately no combined quality number. A store can be perfectly
covered by a schema too poor to express what it read, and a good schema
cannot compensate for a model that asserts nothing.

### Schema gaps by family

`summarise_schema_gaps.py`. Note the count is 10, not 9: the harness's
`schema_gap_facts` counter covers only the 9 facts the annotator held out on
scope grounds. `Deborah -received-> quote` was accepted as gold and is also
outside the vocabulary, so the total of facts the chain cannot store is 10.

| family | facts | predicates |
| ------ | ----: | ---------- |
| event / interaction | 4 | attended, received, sent |
| attribute / requirement | 2 | requires |
| conversation / interest | 2 | asked_about |
| perception / media | 1 | watched |
| location / motion | 1 | traveled_to |

    requires          2   Peruvian Lilies -> watering, sunlight
    asked_about       2   John -> Tim's book collection, picture
    received          2   Joanna -> feedback, Deborah -> quote
    watched           1   John -> That
    attended          1   Caroline -> LGBTQ conference
    traveled_to       1   Deborah -> Bali
    sent              1   Tim -> picture

The inventory is heavy on creator and employment relations and thin on
relations describing events between people, movement and needs. Every fact
in that table is available to a reader and unavailable to the store.

## Scaling

Ten high-yield sentences yielded 7 gold facts, 6 of them scorable. Extrapolating over the 27 remaining uniform sentences gives roughly 40 to 50 facts in total, so ~100 gold facts needs roughly three to four times the corpus, not more annotation of what is there. The bottleneck is the corpus, and that is a finding rather than an obstacle.

## Expanded corpus, sampling rule fixed before any gold

`scripts/select_expanded_corpus.py`. The rule exists in the script header and
was written before a single expanded sentence was annotated.

    pool after exclusions   2397   (2541 LoCoMo observation sentences, minus
                                    the 57 uniform and the annotated draft set)
    conversations           10
    stride within each      12
    selected                100
    stratum                 expanded

| | |
| --- | --- |
| source | the same 10 LoCoMo conversations, observation sentences only |
| exclusion | every sentence id already present in any file under `docs/` |
| order | sorted by conversation, then session number, then id -- no reference to content |
| draw | every 12th sentence WITHIN each conversation |
| provenance | no randomness, so removing one sentence never reshuffles the rest |

The stride is within each conversation rather than across the pooled list.
Pooling first looks simpler and is wrong: ids sort by conversation name as a
string, so conv-26 supplies the first 15 slots and 100 slots run out inside
conv-44. Four conversations would have contributed nothing, and any recall
measured on that would have been a statement about two speakers. Striding
within each conversation keeps all ten present, 7 to 12 sentences each.

Two populations, reported side by side and never pooled:

    uniform recall     the 57-sentence population, 20 gold facts so far
    expanded recall    the 100-sentence stratum above, its own figures

They have different sampling rules and different sizes. A combined figure
would describe neither.

### The frozen sample, and a correction

The 100 ids are frozen in `docs/eval_recall_expanded_manifest.json` together
with the rule parameters and a sha256 over the ids. `--verify` re-derives the
rule and fails if it no longer reproduces the manifest. Later batches are
annotated against the manifest and never recomputed from the pool, so new
gold files appearing under `docs/` cannot retroactively change the
population.

This corrects an earlier claim in this file. It said the stride meant that
removing one sentence never reshuffles the rest of the sample. That was
wrong: with a stride over a list, removing one earlier sentence shifts every
later position, so a sentence can drop out while its successor takes the
slot. The rule is easy to re-derive; the id list is what is stable.

### Uncertainty, and why the interval is wide

    scorable recall   0.800  (16/20)
    approx 95% CI     [0.200, 0.692]

The interval is computed by resampling whole conversations and then
sentences within them, because several facts come from one sentence and
sentences come from ten conversations, so the effective sample size is well
below 20. It is labelled approximate: the draw is deterministic, so the
interval describes the variability of a comparable draw, not a population
this one represents.

**The interval does not contain the point estimate**, and after 60 annotated
expanded sentences the reason is visible in the per-conversation table below:
eight conversations carry between one and eleven scorable gold facts each,
and their rates run from 0.00 to 1.00. Resampling units that small and that
heterogeneous yields a percentile interval that excludes its own point
estimate. That is a property of this constellation -- few, unbalanced
clusters -- and not a verdict on the percentile bootstrap in general, which
is why the interval is retained as secondary rather than dropped.

Because of that, the primary uncertainty view is cluster sensitivity:

    pooled, fact-weighted      0.667  (24/36)
    delete-one-conversation    [0.636, 0.697]

The pooled rate stays fact-weighted. An unweighted mean of the per-cluster
rates would answer a different question -- how good is an average
conversation -- and would replace the estimand rather than describe it. No
minimum cluster size is imposed and no conversation is dropped: conv-26 at
1/1 and conv-47 at 0/1 are genuine parts of the defined population, and
censoring them would silently narrow the population after the fact.

| conversation | scorable | found | recall | pooled without it |
| --- | ---: | ---: | ---: | ---: |
| conv-26 | 1 | 1 | 1.00 | 0.657 |
| conv-30 | 7 | 5 | 0.71 | 0.655 |
| conv-41 | 11 | 8 | 0.73 | 0.640 |
| conv-42 | 6 | 4 | 0.67 | 0.667 |
| conv-43 | 3 | 1 | 0.33 | 0.697 |
| conv-44 | 4 | 2 | 0.50 | 0.688 |
| conv-47 | 1 | 0 | 0.00 | 0.686 |
| conv-48 | 3 | 3 | 1.00 | 0.636 |

The influence span is narrow -- removing any single conversation moves the
pooled rate by less than three points -- so no one conversation dominates.
The per-cluster rates are nonetheless spread from 0.00 to 1.00, which is the
actual finding: the uncertainty in this measurement comes from heterogeneous
clusters carrying few gold facts each, not from one conversation carrying the
result.

Approved wording for the estimate:

> Scorable recall: 24/36 = 0.667. The estimate is fact-weighted across the
> sampled sentences. Conversation-level recall varies substantially across
> the observed clusters, so uncertainty is reported separately via cluster
> sensitivity rather than as an ordinary binomial interval.

The pilot's `1.000` and the current `0.667` with its influence span are both
consistent with a true coverage somewhere around two thirds. The expanded
sample exists to narrow the cluster picture, not to move the point estimate.