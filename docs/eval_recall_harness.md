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

### Three axes that must not be summed

| axis | measure | value |
| ---- | ------- | ----- |
| extractor coverage | scorable recall | 16/20 = 0.800 |
| predicate quality | scorable clean recall | 6/20 = 0.300 |
| schema expressiveness | gold facts outside the vocabulary | 10 |

There is deliberately no combined quality number. A store can be perfectly
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