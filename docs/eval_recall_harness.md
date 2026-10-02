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