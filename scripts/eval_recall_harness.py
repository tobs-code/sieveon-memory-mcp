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
          ) -> Dict[str, Any]:
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gold", type=Path, default=GOLD)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    gold_rows = [json.loads(l) for l in
                 args.gold.read_text(encoding="utf-8").splitlines() if l.strip()]
    claims_by_id: Dict[str, List[Dict[str, Any]]] = {}
    for line in CLAIMS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        claims_by_id[r["id"]] = r.get("asserted", [])

    # A gold row with no triples[] key at all is unannotated, not empty.
    unannotated = [r["id"] for r in gold_rows if r.get("triples") is None]
    if unannotated:
        print(f"  {len(unannotated)} of {len(gold_rows)} rows unannotated; "
              f"scoring would silently treat them as having no gold facts.")
        print(f"  first: {unannotated[0]}")
        return 2
    unlabelled = [r["id"] for r in gold_rows if r.get("graphable") is None]
    if unlabelled:
        print(f"  {len(unlabelled)} rows have no `graphable` verdict. Without "
              f"it an empty\n  triples[] list is ambiguous and the precision "
              f"denominator is meaningless.")
        print(f"  first: {unlabelled[0]}")
        return 2

    r = score(gold_rows, claims_by_id)
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

    if args.out:
        Path(args.out).write_text(json.dumps(
            dict(r, vocabulary_audit=audit,
                 scorable_recall=round(recall_scorable, 3),
                 scorable_recall_clean=round(recall_scorable_clean, 3)),
            indent=2, ensure_ascii=False),
            encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())