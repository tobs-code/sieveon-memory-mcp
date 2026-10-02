"""Recall and precision on one factor set: gold facts first, then claims.

Everything measured so far labels what the extractor asserted, so recall
has been unknown. This harness starts from the other side: a hand-written
gold of facts the sentence entails, scored against the extractor output.
Found and missed facts, spurious claims, recall, precision, F1.

THE THIRD LABEL, added after the first pilot. A gold of `[]` was doing two
incompatible jobs: "this sentence carries no knowledge-graph fact" and
"this sentence carries a graphable fact that I judged below the bar". Both
were scored as empty, so every claim on such a sentence counted as a false
positive, and the precision denominator ended up measuring the gold
annotator's strictness. The two are now separated:

    graphable = "no"     sentence carries no graphable KG fact
                         -> its claims are excluded from precision entirely
    graphable = "yes"    at least one graphable fact exists
                         -> triples[] holds the gold facts,
                            excluded[] holds graphable relations deliberately
                            left out, each with a reason,
                            schema_gap[] holds facts that are real but have
                            no relation in the current vocabulary

A gold triple may carry a fourth element, "imprecise", when the sentence
supports the fact but the predicate is stronger than the wording licenses:
`Jolene uses bullet journal` from "cross tasks off her list in the bullet
journal", `Susie provides comfort` from "brings her comfort". This replaced
a global predicate list, because the same predicate is clean in one
sentence and imprecise in another -- `provides` is nearly literal for "the
studio offers kickboxing" and an over-reading for "brings her comfort".

A vocabulary gap is not a mistake by either side. `Peruvian Lilies require
watering` is a fact the sentence carries, but `requires` is not a relation
the schema has, so no extractor could have produced it. Those facts go in
schema_gap[], and by default the claims on such a sentence are reported
separately instead of being charged to precision. Set
`schema_gap_claims: "spurious"` on a row to count them anyway; the report
always shows both, because the honest reading is a judgement call and
hiding one side of it would be the same error as the one this harness
exists to catch.

The pilot proved this is not a theoretical concern: `bike routes located_in
river` was marked supported in the per-triple annotation and omitted from
gold here. Same sentence, same relation, two verdicts.

THE MATCH RULE, fixed before any number was produced. It is the part that
would otherwise turn this into a measurement of the matcher:

  1. A triple matches iff subject, predicate and object are all equal after
     normalisation (lower case, whitespace, articles stripped).
  2. Argument order is not swappable. `works_at` and `part_of` are
     different relations, not a reversed triple.
  3. Predicate equivalence is limited to the groups in EQUIVALENT below.
     These are synonym pairs already attested in the hand annotation, not
     a general lexical resource. Notably absent: started/founded,
     travel/works_at, visit/acquired, check_out/acquired. `bring` and
     `provides` are equivalent only because the annotation labels the pair
     implied rather than wrong, so such a match is reported as imprecise,
     never as clean.
  4. A claim on a non-graphable sentence is not evidence of anything and
     is reported apart from the precision computation.
  5. Predicate discipline is scored separately from fact coverage: a claim
     whose subject and object match a gold triple but whose predicate does
     not is a discipline failure, not a missed fact and not a fabricated
     relation. The extractor produces these constantly -- for `Melanie
     developed environment` it also emitted `created` and `built`.

Usage:
    python scripts/eval_recall_harness.py
    python scripts/eval_recall_harness.py --out docs/eval_recall_pilot.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "docs" / "eval_recall_gold_pilot.jsonl"
CLAIMS = ROOT / "docs" / "eval_triples_gold_locomo_uniform_model.jsonl"

# Pairs the hand annotation already treats as the same relation. Anything
# not listed here is an exact string match only.
EQUIVALENT: Dict[str, set] = {
    "discovered": {"find", "found"},
    "created": {"make", "made"},
    "provides": {"bring", "offer"},
    "developed": {"develop"},
    "built": {"build"},
    "wrote": {"write", "written"},
    "uses": {"use"},
    "located_in": {"in"},
}

# Predicates whose gold coverage is legitimately weaker: the annotation
# labels these implied rather than supported, so a match here is reported
# separately and never folded into clean recall.
IMPRECISE = {"provides"}

ARTICLES = {"the", "a", "an"}


def norm(s: str) -> str:
    toks = [t for t in re.split(r"\s+", s.strip().lower())
            if t and t not in ARTICLES]
    return " ".join(toks)


def same_predicate(a: str, b: str) -> Tuple[bool, bool]:
    """(equivalent, precise). Precise is False for the implied-predicate set."""
    if norm(a) == norm(b):
        # Identical predicate is still possibly one the annotation only
        # called implied; `provides` matching `provides` is not a clean hit.
        return True, norm(a) not in IMPRECISE and norm(b) not in IMPRECISE
    ga, gb = EQUIVALENT.get(norm(a)), EQUIVALENT.get(norm(b))
    if (ga and norm(b) in ga) or (gb and norm(a) in gb):
        return True, norm(a) not in IMPRECISE and norm(b) not in IMPRECISE
    return False, False


def match(gold: Tuple[str, str, str],
          claim: Dict[str, Any]) -> Tuple[bool, bool, str]:
    gs, gp, go = gold
    eq, precise = same_predicate(gp, claim["p"])
    if norm(gs) != norm(claim["s"]) or not eq:
        return False, False, ""
    if norm(go) != norm(claim["o"]):
        return False, False, ""
    return True, precise, claim["p"]


def score(gold_rows: List[Dict[str, Any]],
          claims_by_id: Dict[str, List[Dict[str, Any]]],
          rows_by_id: Dict[str, Dict[str, Any]] | None = None,
          ) -> Dict[str, Any]:
    rows_by_id = rows_by_id or {r["id"]: r for r in gold_rows}
    found: List[Dict[str, Any]] = []
    missed: List[Dict[str, Any]] = []
    imprecise: List[Dict[str, Any]] = []
    spurious: List[Dict[str, Any]] = []
    discipline: List[Dict[str, Any]] = []
    non_graphable: List[Dict[str, Any]] = []
    below: List[Dict[str, Any]] = []
    gap_claims: List[Dict[str, Any]] = []

    for row in gold_rows:
        raw = [list(t) for t in (row.get("triples") or [])]
        # An optional fourth element marks a gold fact whose predicate is an
        # over-reading of the wording. Absent means clean.
        gold = [(t[0], t[1], t[2], t[3] if len(t) > 3 else "clean")
                for t in raw]
        claims = claims_by_id.get(row["id"], [])
        used = set()
        for g in gold:
            hit = None
            for ci, c in enumerate(claims):
                if ci in used:
                    continue
                ok, precise, via = match(g[:3], c)
                if ok:
                    hit = (ci, g[3] == "clean" and precise, via)
                    break
            if hit is None:
                missed.append({"id": row["id"], "gold": list(g[:3])})
            else:
                used.add(hit[0])
                rec = {"id": row["id"], "gold": list(g[:3]),
                       "matched": {k: claims[hit[0]][k] for k in "spo"},
                       "via_predicate": hit[2]}
                if hit[1]:
                    found.append(rec)
                else:
                    imprecise.append(rec)
        # Every claim the gold did not absorb. If its entity pair matches a
        # graphable fact of this sentence, the extractor addressed the right
        # thing and attached the wrong relation -- a discipline failure,
        # which is not a missed fact and not a fabricated relation. Order of
        # operations matters: a gold triple that was itself found still has
        # its pair watched here, because `Melanie developed environment` was
        # found *and* `created`/`built` were emitted alongside it.
        graphable_pairs = {(norm(g[0]), norm(g[2])) for g in gold}
        graphable_pairs |= {(norm(e["s"]), norm(e["o"]))
                            for e in (row.get("excluded") or [])}
        gap_pairs = {(norm(e["s"]), norm(e["o"]))
                     for e in (row.get("schema_gap") or [])}
        excluded_triples = [(e["s"], e["p"], e["o"])
                            for e in (row.get("excluded") or [])]
        # Default: claims on a sentence whose only graphable content is a
        # vocabulary gap are reported apart, not charged to precision.
        gap_counts_as = row.get("schema_gap_claims", "excluded")
        for ci, c in enumerate(claims):
            if ci in used:
                continue
            entry = {"id": row["id"], "claim": {k: c[k] for k in "spo"}}
            if row.get("graphable") == "no":
                non_graphable.append(entry)
                continue
            if (not gold and gap_pairs and gap_counts_as == "excluded"
                    and (norm(c["s"]), norm(c["o"])) not in graphable_pairs):
                gap_claims.append(entry)
                continue
            # Three distinct failures, kept apart because they call for
            # different fixes. A claim that restates an excluded relation is
            # not wrong, it is below the bar we set. A claim on the right
            # entity pair with a different relation is a discipline failure.
            # Anything else asserts something the sentence does not carry.
            if any(match(t, c)[:1] == (True,) for t in excluded_triples):
                below.append(entry)
            elif (norm(c["s"]), norm(c["o"])) in graphable_pairs:
                discipline.append(entry)
            else:
                spurious.append(dict(entry, on_gold_bearing=bool(gold)))

    n_gold = len(found) + len(imprecise) + len(missed)
    # Every claim lands in exactly one bucket. Claims on non-graphable
    # sentences are excluded from precision: they say nothing about the
    # extractor, only about what the annotator considered graphable.
    n_all_claims = (len(found) + len(imprecise) + len(below)
                    + len(discipline) + len(spurious)
                    + len(non_graphable) + len(gap_claims))
    scored_claims = n_all_claims - len(non_graphable) - len(gap_claims)
    recall = len(found) / n_gold if n_gold else float("nan")
    strict_recall = (len(found) + len(imprecise)) / n_gold if n_gold else float("nan")
    incl = len(found) + len(imprecise)
    precision = incl / scored_claims if scored_claims else float("nan")
    clean_precision = len(found) / scored_claims if scored_claims else float("nan")
    f1 = (2 * recall * precision / (recall + precision)
          if (recall + precision) > 0 else float("nan"))
    naive_precision = (incl / n_all_claims
                       if n_all_claims else float("nan"))
    discipline_rate = (len(discipline) / scored_claims
                       if scored_claims else None)
    # Same numbers with the vocabulary-gap claims charged to precision, so the
    # effect of that judgement call is visible instead of assumed.
    alt_denom = scored_claims + len(gap_claims)
    alt_precision = (incl / alt_denom if alt_denom else float("nan"))

    n_schema_gap = sum(len(r.get("schema_gap") or []) for r in gold_rows)

    # Sentence-level dropout and fact-level recall are different quantities.
    # A claimless sentence costs recall only if it carries gold facts; a
    # claimless `graphable: no` sentence is neutral for recall and only
    # inflates the sentence-level rate. Reporting them together invites
    # reading one as evidence for the other.
    claimless = [r["id"] for r in gold_rows if not claims_by_id.get(r["id"])]
    claimless_with_gold = [i for i in claimless
                           if any(
                               norm(t[0]) for t in
                               (rows_by_id[i].get("triples") or []))]

    return {
        "gold": n_gold, "claims": n_all_claims,
        "claims_on_graphable_sentences": scored_claims,
        "found": len(found), "imprecise": len(imprecise),
        "missed": len(missed),
        "below_threshold": len(below),
        "predicate_discipline": len(discipline),
        "predicate_discipline_rate": (
            round(discipline_rate, 3) if discipline_rate is not None else None),
        "spurious": len(spurious),
        "non_graphable_sentences": sum(
            1 for r in gold_rows if r.get("graphable") == "no"),
        "non_graphable_claims": len(non_graphable),
        "schema_gap_facts": n_schema_gap,
        "schema_gap_claims": len(gap_claims),
        "sentence_dropout": len(claimless),
        "sentence_dropout_carrying_gold": len(claimless_with_gold),
        "precision_if_gap_counted": round(alt_precision, 3),
        "recall": round(recall, 3),
        "recall_incl_implied": round(strict_recall, 3),
        "precision": round(precision, 3),
        "precision_strict": round(clean_precision, 3),
        "precision_incl_implied": round(precision, 3),
        "precision_naive_all_claims": round(naive_precision, 3),
        "f1": round(f1, 3),
        "detail": {"found": found, "imprecise": imprecise,
                   "missed": missed, "spurious": spurious,
                   "below_threshold": below,
                   "predicate_discipline": discipline,
                   "non_graphable": non_graphable,
                   "schema_gap_claims": gap_claims},
    }


def production_vocabulary() -> set:
    """Predicate names the production chain can actually produce.

    Read live from `verbalise.CLAIM` rather than copied into a list here.
    That dict is the verbaliser of the extractor's own output, so it is the
    one place that answers "can this predicate exist in the store at all". A
    gold fact whose predicate is missing from it is a vocabulary gap: no
    claim could ever match it, so charging the extractor for missing it would
    be measuring the schema.
    """
    from src.extraction.verbalise import CLAIM
    return set(CLAIM)


VOCAB = production_vocabulary()


def audit_vocabulary(gold_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Which gold facts are expressible in the production vocabulary.

    Purely derived: the gold file is not rewritten. Semantic gold stays the
    ground truth; this only decides what the extractor could be scored on.
    """
    vocab = production_vocabulary()
    preds: Dict[str, List[str]] = {}
    for r in gold_rows:
        for t in (r.get("triples") or []):
            preds.setdefault(t[1], []).append(r["id"])
    in_vocab = sorted(p for p in preds if p in vocab)
    out_vocab = sorted(p for p in preds if p not in vocab)
    scorable = [r for r in gold_rows for t in (r.get("triples") or [])
                if t[1] in vocab]
    unscorable = [r for r in gold_rows for t in (r.get("triples") or [])
                  if t[1] not in vocab]
    return {
        "vocabulary_size": len(vocab),
        "vocabulary": sorted(vocab),
        "distinct_gold_predicates": sorted(preds),
        "gold_predicate_counts": {k: len(v) for k, v in sorted(preds.items())},
        "scorable_predicates": in_vocab,
        "unscorable_predicates": out_vocab,
        "scorable_gold_facts": len(scorable),
        "unscorable_gold_facts": len(unscorable),
        "scorable_ids": sorted({r["id"] for r in scorable}),
    }


def clustered_recall_ci(rows: List[Dict[str, Any]],
                        ids_per_fact: Dict[Tuple[str, str, str], str],
                        found: List[Dict[str, Any]],
                        imprecise: List[Dict[str, Any]],
                        reps: int = 2000, seed: int = 23) -> Tuple[float, float]:
    """Approximate CI that resamples whole conversations, then sentences.

    A binomial CI over gold facts would treat every fact as independent.
    They are not: several facts come from one sentence, and sentences come
    from ten conversations, so the effective sample size is far below the
    fact count. Resampling the highest level of clustering first widens the
    interval to reflect that.

    This is still approximate. The draw is deterministic rather than random,
    so the interval describes the sampling variability of a comparable draw,
    not a confidence statement about a population the draw does not
    represent. It is labelled as approximate everywhere it is printed.
    """
    import random

    by_conv: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_conv.setdefault(r["id"].split("/")[0], []).append(r)
    convs = sorted(by_conv)
    if len(convs) < 2:
        return float("nan"), float("nan")

    rng = random.Random(seed)
    vals: List[float] = []
    for _ in range(reps):
        hit = tot = 0
        for _ in range(len(convs)):
            r = rng.choice(convs)
            take = by_conv[r]
            if len(take) > 1 and rng.random() < 0.5:
                take = [rng.choice(take)]
            for row in take:
                gold = [(t[0], t[1], t[2]) for t in (row.get("triples") or [])]
                gold += [(e["s"], e["p"], e["o"])
                         for e in (row.get("excluded") or [])]
                got = {tuple(d["gold"]) for d in found + imprecise
                       if d["id"] == row["id"]}
                for g in gold:
                    if g[1] not in VOCAB:
                        continue  # unscorable, excluded from the denominator
                    tot += 1
                    if g in got:
                        hit += 1
        if tot:
            vals.append(hit / tot)
    vals.sort()
    return vals[int(0.025 * reps)], vals[int(0.975 * reps)]


def cluster_sensitivity(rows: List[Dict[str, Any]],
                        claims_by_id: Dict[str, List[Dict[str, Any]]],
                        ) -> Dict[str, Any]:
    """Per-conversation recall, plus leave-one-cluster-out influence.

    The percentile bootstrap is kept but demoted. With eight observed
    conversations carrying between one and eleven scorable gold facts each,
    cluster rates run from 0.00 to 1.00, and resampling whole conversations
    from units that small produces a percentile interval that excludes its
    own point estimate. That is a property of the current constellation, not
    a verdict on the bootstrap in general, so the interval is reported as
    secondary and the influence report carries the uncertainty story.

    The delete-one-cluster values need no distributional assumption at all:
    each is simply the pooled rate with one conversation removed. No minimum
    cluster size is imposed and no conversation is dropped from the estimate,
    because conv-26 at 1/1 and conv-47 at 0/1 are genuine parts of the
    defined population.

    The pooled rate stays fact-weighted. An unweighted mean of cluster rates
    would answer a different question -- how good is an average conversation
    -- and would quietly replace the estimand.
    """
    by_conv: Dict[str, List[Tuple[Tuple[str, str, str], bool]]] = {}
    for r in rows:
        conv = r["id"].split("/")[0]
        claims = claims_by_id.get(r["id"], [])
        got = {(norm(c["s"]), norm(c["p"]), norm(c["o"]))
               for c in claims}
        for t in (r.get("triples") or []):
            g = (norm(t[0]), norm(t[1]), norm(t[2]))
            if t[1] not in VOCAB:
                continue
            by_conv.setdefault(conv, []).append(
                (g, any(norm(c["s"]) == g[0] and norm(c["o"]) == g[2]
                        and norm(c["p"]) == g[1] for c in claims)))

    per: Dict[str, Dict[str, Any]] = {}
    for conv, items in sorted(by_conv.items()):
        n = len(items)
        f = sum(1 for _, hit in items if hit)
        per[conv] = {"scorable": n, "found": f,
                     "recall": round(f / n, 3) if n else None}

    tot = sum(v["scorable"] for v in per.values())
    fnd = sum(v["found"] for v in per.values())
    pooled = fnd / tot if tot else float("nan")

    jack: Dict[str, float] = {}
    for conv in per:
        rest_t = tot - per[conv]["scorable"]
        rest_f = fnd - per[conv]["found"]
        jack[conv] = round(rest_f / rest_t, 3) if rest_t else float("nan")

    return {"pooled": round(pooled, 3), "total_scorable": tot,
            "total_found": fnd, "per_conversation": per,
            "delete_one_conversation": jack,
            "influence_span": [min(jack.values()), max(jack.values())]
            if jack else None,
            "conversations": len(per)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gold", type=Path, action="append", default=None,
                    help="gold file; repeat to score the frozen pilot "
                         "together with later batches")
    ap.add_argument("--out", default="")
    ap.add_argument("--annotated-only", action="store_true",
                    help="score only the rows that are annotated, and report "
                         "how many were skipped. Batch-wise annotation makes "
                         "this necessary, and it changes the denominator, so "
                         "the skipped count is printed on every run.")
    ap.add_argument("--claims", type=Path, action="append", default=None,
                    help="claims file; repeat alongside repeated --gold. "
                         "Required for every gold file that the matching "
                         "claims file does not cover, otherwise the sentences "
                         "look like a model that asserted nothing rather than "
                         "an extraction that was never run.")
    args = ap.parse_args()
    gold_files = args.gold or [GOLD]
    claim_files = args.claims or [CLAIMS]

    rows_by_id: Dict[str, Dict[str, Any]] = {}
    for gf in gold_files:
        for line in gf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            prev = rows_by_id.get(r["id"])
            if prev is not None and prev.get("triples") != r.get("triples"):
                # Two files disagreeing about the same sentence would
                # silently change the denominator, so refuse instead.
                print(f"  conflicting gold for {r['id']} between files")
                return 2
            rows_by_id[r["id"]] = r
    gold_rows = list(rows_by_id.values())
    claims_by_id: Dict[str, List[Dict[str, Any]]] = {}
    for cf in claim_files:
        if not cf.exists():
            print(f"  claims file missing: {cf}")
            return 2
        for line in cf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                claims_by_id[r["id"]] = r.get("asserted", [])

    # A gold sentence with no claims entry was never extracted. Reporting it
    # as a miss would blame the model for our omission.
    uncovered = [r["id"] for r in gold_rows if r["id"] not in claims_by_id]
    if uncovered:
        print(f"  {len(uncovered)} gold sentences have no entry in any claims "
              f"file, so their facts cannot be\n  scored. They are counted as "
              f"missed by default, which is wrong: the extractor was never "
              f"run on them.")
        print(f"  first: {uncovered[0]}")
        print(f"  run scripts/annotate_recall_expanded.py, or pass --claims")
        return 2

    # A gold row with no triples[] key at all is unannotated, not empty.
    unannotated = [r["id"] for r in gold_rows if r.get("triples") is None]
    if unannotated:
        if not args.annotated_only:
            print(f"  {len(unannotated)} of {len(gold_rows)} rows unannotated; "
                  f"scoring would silently treat them as having no gold facts.")
            print(f"  first: {unannotated[0]}")
            return 2
        gold_rows = [r for r in gold_rows if r.get("triples") is not None]
        print(f"  {len(unannotated)} unannotated rows skipped by "
              f"--annotated-only.\n  This figure describes the annotated "
              f"subset, not the frozen sample: {len(gold_rows)} of "
              f"{len(gold_rows) + len(unannotated)} rows.")
    unlabelled = [r["id"] for r in gold_rows if r.get("graphable") is None]
    if unlabelled and not args.annotated_only:
        print(f"  {len(unlabelled)} rows have no `graphable` verdict. Without "
              f"it an empty\n  triples[] list is ambiguous and the precision "
              f"denominator is meaningless.")
        print(f"  first: {unlabelled[0]}")
        return 2
    if unlabelled:
        gold_rows = [r for r in gold_rows if r.get("graphable") is not None]
        print(f"  {len(unlabelled)} unannotated rows skipped by "
              f"--annotated-only. This figure therefore\n  describes the "
              f"annotated subset, not the frozen sample: {len(gold_rows)} of "
              f"{len(gold_rows) + len(unlabelled)} rows.")

    r = score(gold_rows, claims_by_id, rows_by_id)
    audit = audit_vocabulary(gold_rows)

    # Two denominators, both reported. Semantic coverage counts every gold
    # fact, including the ones the schema cannot express. Scorable recall
    # counts only what an extractor claim could ever have matched. Quoting
    # either alone is how a schema gap gets mistaken for a model defect.
    n_gold = r["gold"]
    n_unscorable = audit["unscorable_gold_facts"]
    n_scorable = n_gold - n_unscorable
    recall_scorable = ((r["found"] + r["imprecise"]) / n_scorable
                       if n_scorable else float("nan"))
    recall_scorable_clean = (r["found"] / n_scorable
                             if n_scorable else float("nan"))

    print("=== vocabulary audit ===")
    print(f"  production vocabulary  {audit['vocabulary_size']} predicates "
          f"(src/extraction/verbalise.py CLAIM)")
    print(f"  distinct gold preds    "
          f"{len(audit['distinct_gold_predicates'])}: "
          f"{audit['distinct_gold_predicates']}")
    print(f"  scorable predicates    {audit['scorable_predicates']}")
    print(f"  NOT in vocabulary      {audit['unscorable_predicates'] or 'none'}")
    print(f"  gold facts             {n_gold} total, {n_scorable} scorable, "
          f"{n_unscorable} vocabulary gap")
    print()

    print(f"=== recall harness: {len(gold_rows)} sentences, gold-first ===")
    print(f"  gold facts        {r['gold']}")
    print(f"  extractor claims  {r['claims']}  "
          f"({r['claims_on_graphable_sentences']} on graphable sentences)")
    print()
    print(f"  {'bucket':30} {'n':>4}")
    for k in ("found", "imprecise", "missed", "below_threshold",
              "predicate_discipline", "spurious", "non_graphable_claims",
              "schema_gap_claims"):
        print(f"  {k:30} {r[k]:4}")
    print(f"  {'discipline rate':30} "
          f"{r['predicate_discipline_rate']:>4}")
    print()
    print(f"  recall            {r['recall']:.3f}   "
          f"({r['found']}/{r['gold']}, semantic gold, clean predicates)")
    print(f"  recall incl impl  {r['recall_incl_implied']:.3f}   "
          f"({r['found'] + r['imprecise']}/{r['gold']}, semantic gold)")
    print(f"  scorable recall   {recall_scorable:.3f}   "
          f"({r['found'] + r['imprecise']}/{n_scorable}, vocabulary gap excluded)")
    lo, hi = clustered_recall_ci(gold_rows, {}, r["detail"]["found"],
                                 r["detail"]["imprecise"])
    if lo == lo:  # not NaN
        print(f"    approx 95% CI [{lo:.3f}, {hi:.3f}]  "
              f"(clustered: {len({x['id'].split('/')[0] for x in gold_rows})} "
              f"conversations resampled, then sentences)")
        print(f"    approximate only -- the draw is deterministic, so this "
              f"describes sampling\n    variability of a comparable draw, "
              f"not a population this draw represents")
        if not (lo <= recall_scorable <= hi):
            print(f"    NOTE the interval does not contain the point estimate "
                  f"{recall_scorable:.3f}. That is a real\n    symptom, not a "
                  f"rounding artefact: at this sample size the result moves "
                  f"more when\n    whole conversations change than the fact "
                  f"count suggests. Treat the point estimate as\n    unstable "
                  f"until more conversations carry annotated gold facts.")
    print(f"  scorable clean    {recall_scorable_clean:.3f}   "
          f"({r['found']}/{n_scorable})")
    print(f"  precision         {r['precision']:.3f}   "
          f"({r['found'] + r['imprecise']}"
          f"/{r['claims_on_graphable_sentences']})")
    print(f"  precision strict  {r['precision_strict']:.3f}   "
          f"({r['found']}/{r['claims_on_graphable_sentences']})")
    print(f"  prec naive        {r['precision_naive_all_claims']:.3f}   "
          f"({r['found'] + r['imprecise']}/{r['claims']}, all claims)")
    print(f"  prec if gap count {r['precision_if_gap_counted']:.3f}   "
          f"(vocabulary-gap claims charged to precision instead of held apart)")
    print(f"  F1                {r['f1']:.3f}")
    print()
    print(f"  vocabulary-gap facts in gold: {r['schema_gap_facts']} "
          f"(no relation exists, so no claim could match)")
    print()
    print(f"  sentence-level dropout    {r['sentence_dropout']} of "
          f"{len(gold_rows)} annotated sentences produced no claim")
    print(f"    of which carrying gold  {r['sentence_dropout_carrying_gold']}")
    print(f"    A claimless sentence lowers recall only if it carries gold "
          f"facts. The\n    rest is a sentence-level extraction rate, not "
          f"evidence about recall, and\n    the two must not be added or "
          f"quoted as one number.")
    print()
    print("  Buckets, and what each one would need:")
    print("    found/imprecise  the gold fact was extracted")
    print("    below_threshold  graphable but under the gold bar; not an error")
    print("    discipline       right entity pair, wrong relation")
    print("    spurious         the sentence does not carry the fact at all")
    print("    non_graphable    sentence out of scope; excluded from precision")
    print()
    print("  missed gold facts (the number that did not exist before):")
    for m in r["detail"]["missed"]:
        print(f"    {m['gold'][0]} -{m['gold'][1]}-> {m['gold'][2]}")
    print()
    print("  spurious claims (on graphable sentences):")
    for s in r["detail"]["spurious"]:
        c = s["claim"]
        print(f"    {c['s']} -{c['p']}-> {c['o']}")
    print("  predicate-discipline failures (right entity pair, wrong relation):")
    for d in r["detail"]["predicate_discipline"]:
        c = d["claim"]
        print(f"    {c['s']} -{c['p']}-> {c['o']}")

    cs = cluster_sensitivity(gold_rows, claims_by_id)
    print()
    print("=== cluster sensitivity (primary uncertainty view) ===")
    print(f"  pooled, fact-weighted   {cs['pooled']:.3f} "
          f"({cs['total_found']}/{cs['total_scorable']})")
    print(f"  conversations observed  {cs['conversations']}")
    print()
    print(f"  {'conversation':14} {'scorable':>8} {'found':>6} {'recall':>7} "
          f"{'without it':>11}")
    for conv, v in cs["per_conversation"].items():
        print(f"  {conv:14} {v['scorable']:8} {v['found']:6} "
              f"{v['recall']:7.2f} {cs['delete_one_conversation'][conv]:11.3f}")
    if cs["influence_span"]:
        lo, hi = cs["influence_span"]
        print()
        print(f"  delete-one-conversation span [{lo:.3f}, {hi:.3f}] "
              f"(pooled {cs['pooled']:.3f})")
        print("  No conversation is excluded from the estimate. The spread "
              "shows how much the\n  pooled rate depends on single "
              "conversations, which is where the uncertainty\n  currently "
              "comes from: heterogeneous clusters with few gold facts each, "
              "not one\n  dominant conversation.")

    if args.out:
        Path(args.out).write_text(json.dumps(
            dict(r, vocabulary_audit=audit, cluster_sensitivity=cs,
                 scorable_recall=round(recall_scorable, 3),
                 scorable_recall_clean=round(recall_scorable_clean, 3)),
            indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())