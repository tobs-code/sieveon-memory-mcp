"""Locate where each of the 53 counterfactual facts is lost, without changing anything.

The counterfactual run established that extending the vocabulary alone buys
nothing: 0 of 53 facts appear as claims. 25 of them land on the right entity
pair under a different relation, 28 produce no pair at all. That splits into
two very different defects -- candidate generation and relation selection --
and they call for different interventions, so the split has to be measured
before any fix is chosen.

There is no intermediate representation to read. `extract_triples_with_relex`
is a single joint NER+RE forward pass: GLiNER scores entities and relations
together and returns only the surviving triples, so the stage at which a fact
was dropped is not recorded anywhere. This script recovers it with three
read-only calls against the same frozen model, none of which touches
production code, the vocabulary in use or the database:

    entities    entity-only pass. Answers "does the extractor see both
                endpoints at all", which is the candidate-generation side.
    current     the production relation label set, at a lowered threshold.
    extended    production labels plus the 53 observed counterfactual
                relations. This is a probe, not a proposal: it tells us
                whether the model *can* express the relation when the label
                exists, which separates "the label space lacks it" from "the
                model will not use it".

Every counterfactual fact lands in exactly one class:

    pair_missing                              endpoints not both detected
    pair_present_label_absent                 pair detected, no relation
                                              survives under current labels
    pair_present_cue_present_wrong_label      the target relation does survive
                                              under extended labels, but the
                                              current pass chose something else
    correct_relation_produced                 produced under current labels

The third class is the decisive one. It means the relation was reachable all
along and the defect is selection, not capacity.

Thresholds are lowered for all three passes so that a label losing near the
cut is not misread as a model failure. The numbers are therefore a lower bound
on what the extractor could do, not a measurement of the shipped cutoff.

Usage:
    python scripts/audit_extractor_stages.py --limit 53
    python scripts/audit_extractor_stages.py --out docs/eval_extractor_stages.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
CF = ROOT / "docs" / "eval_recall_gold_counterfactual.jsonl"
TEXT_SOURCE = ROOT / "docs" / "eval_recall_gold_pilot.jsonl"
TEXT_SOURCE2 = ROOT / "docs" / "eval_recall_gold_batch2.jsonl"
TEXT_SOURCE3 = ROOT / "docs" / "eval_recall_gold_expanded.jsonl"

CLASSES = ("correct_relation_produced",
           "pair_present_cue_present_wrong_label",
           "pair_present_label_absent",
           "pair_missing")


def norm(s: str) -> str:
    toks = [t for t in str(s).strip().lower().split() if t not in
            {"the", "a", "an"}]
    return " ".join(toks)


def load_texts() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for f in (TEXT_SOURCE, TEXT_SOURCE2, TEXT_SOURCE3):
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out.setdefault(r["id"], r["text"])
    return out


def pairs_of(rels: List[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    out = []
    for r in rels or []:
        try:
            head = r["head"]["text"].strip()
            tail = r["tail"]["text"].strip()
            pred = str(r.get("relation", "")).strip()
        except (KeyError, TypeError, AttributeError):
            continue
        out.append((norm(head), norm(pred), norm(tail)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="")
    ap.add_argument("--ent-threshold", type=float, default=0.2)
    ap.add_argument("--rel-threshold", type=float, default=0.2)
    args = ap.parse_args()

    from src.extraction.entity_utils import (
        _SIEVEON_ENTITY_LABELS, _SIEVEON_RELATION_LABELS, _get_relex,
        _normalize_relation_label,
    )

    facts = [json.loads(l) for l in
             CF.read_text(encoding="utf-8").splitlines() if l.strip()]
    texts = load_texts()
    missing_text = [f["id"] for f in facts if f["id"] not in texts]
    if missing_text:
        print(f"  {len(missing_text)} counterfactual facts have no sentence "
              f"text on file; first {missing_text[0]}")

    counter_labels = sorted({f["p"] for f in facts})
    extended_labels = list(_SIEVEON_RELATION_LABELS) + [
        c.replace("_", " ") for c in counter_labels]

    model = _get_relex()

    results: List[Dict[str, Any]] = []
    for i, f in enumerate(facts, 1):
        text = texts.get(f["id"])
        if text is None:
            continue
        try:
            ents, rels_cur = model.predict_relations(
                text, _SIEVEON_ENTITY_LABELS, _SIEVEON_RELATION_LABELS,
                threshold=args.ent_threshold,
                relation_threshold=args.rel_threshold)
            _e2, rels_ext = model.predict_relations(
                text, _SIEVEON_ENTITY_LABELS, extended_labels,
                threshold=args.ent_threshold,
                relation_threshold=args.rel_threshold)
        except Exception as exc:  # noqa: BLE001
            results.append({**f, "class": "probe_failed",
                            "error": str(exc)[:120]})
            continue

        cur = pairs_of(rels_cur)
        ext = pairs_of(rels_ext)
        target_pair = (norm(f["s"]), norm(f["o"]))
        target_rel = norm(f["p"])

        ent_names = {norm(e.get("text", "")) for e in (ents or [])}
        pair_in_ents = (norm(f["s"]) in ent_names
                        and norm(f["o"]) in ent_names)
        pair_in_cur = any(h == target_pair[0] and t == target_pair[1]
                          for h, _p, t in cur)
        exact_cur = any(h == target_pair[0] and p == target_rel
                        and t == target_pair[1] for h, p, t in cur)
        exact_ext = any(h == target_pair[0] and p == target_rel
                        and t == target_pair[1] for h, p, t in ext)
        # "cue present": the target relation survives somewhere in the
        # sentence under extended labels, on some pair.
        cue_present = any(p == target_rel for _h, p, _t in ext)

        if exact_cur:
            cls = "correct_relation_produced"
        elif pair_in_cur and cue_present:
            cls = "pair_present_cue_present_wrong_label"
        elif pair_in_cur or pair_in_ents:
            cls = "pair_present_label_absent"
        else:
            cls = "pair_missing"

        results.append({
            "id": f["id"], "s": f["s"], "p": f["p"], "o": f["o"],
            "family": f["counterfactual_family"],
            "class": cls,
            "pair_in_entities": pair_in_ents,
            "pair_in_current_relations": pair_in_cur,
            "exact_current": exact_cur,
            "exact_extended": exact_ext,
            "cue_present_extended": cue_present,
            "current_predicates": sorted({p for h, p, t in cur
                                         if h == target_pair[0]
                                         and t == target_pair[1]}),
        })
        if i % 10 == 0:
            print(f"  probed {i}/{len(facts)}")

    counts = Counter(r["class"] for r in results)
    print(f"\n=== extractor stage audit: {len(results)} counterfactual facts "
          f"===\n")
    print("  probes are read-only, thresholds lowered on all three passes, so "
          "these are a\n  lower bound on what the extractor could do, not a "
          "measurement of the\n  shipped cutoff.\n")
    print(f"  {'class':38} {'n':>4}")
    for c in CLASSES:
        if counts.get(c):
            print(f"  {c:38} {counts[c]:4}")
    other = [c for c in counts if c not in CLASSES]
    for c in other:
        print(f"  {c:38} {counts[c]:4}  (probe failure)")
    print()
    print(f"  probe_failed {counts.get('probe_failed', 0)}")
    print(f"  pair found as entities: "
          f"{sum(1 for r in results if r.get('pair_in_entities'))}")

    def share(key):
        n = sum(counts[c] for c in CLASSES)
        return n or 1

    print(f"\n  candidate generation side")
    print(f"    pair_missing                       "
          f"{counts.get('pair_missing', 0)}  "
          f"{counts.get('pair_missing', 0) / share(0):.0%}")
    print(f"  relation selection side")
    print(f"    label absent from the space        "
          f"{counts.get('pair_present_label_absent', 0)}  "
          f"{counts.get('pair_present_label_absent', 0) / share(0):.0%}")
    print(f"    label present, wrong one chosen    "
          f"{counts.get('pair_present_cue_present_wrong_label', 0)}  "
          f"{counts.get('pair_present_cue_present_wrong_label', 0) / share(0):.0%}")
    print(f"  already correct                      "
          f"{counts.get('correct_relation_produced', 0)}  "
          f"{counts.get('correct_relation_produced', 0) / share(0):.0%}")

    fam = defaultdict(Counter)
    for r in results:
        fam[r["family"]][r["class"]] += 1
    print(f"\n  {'family':28} {'n':>3} {'ok':>3} {'wrong':>6} {'absent':>7} "
          f"{'missing':>8}")
    for k in sorted(fam, key=lambda k: -sum(fam[k].values())):
        c = fam[k]
        print(f"  {k:28} {sum(c.values()):3} "
              f"{c.get('correct_relation_produced', 0):3} "
              f"{c.get('pair_present_cue_present_wrong_label', 0):6} "
              f"{c.get('pair_present_label_absent', 0):7} "
              f"{c.get('pair_missing', 0):8}")

    wrong = [r for r in results
             if r["class"] == "pair_present_cue_present_wrong_label"]
    if wrong:
        print("\n  selection failures: target relation was reachable, "
              "another one won")
        for r in wrong[:14]:
            print(f"    {r['s']} -> {r['o']}: wanted {r['p']}, "
                  f"chose {', '.join(r['current_predicates']) or 'none'}")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "probe": {"ent_threshold": args.ent_threshold,
                      "rel_threshold": args.rel_threshold,
                      "note": "read-only shadow passes against the frozen "
                              "relex model; lower bound on capability"},
            "counts": dict(counts),
            "results": results,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())