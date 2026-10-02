"""
Extraction eval: entity/triple recall + per-fact precision per backend on
docs/eval_extraction_gold.jsonl.

Compares relex vs gliner2.5-multi vs spacy (and optional --groq), including a
threshold sweep for RELEX_REL_THRESHOLD. Predicate matching is
synonym-tolerant (created/developed/authored/built/wrote/designed/published).

Fact-level quality is measured per *produced fact*, not per missed gold triple:
every triple a backend emits is labelled correct iff it matches a gold triple of
the same sentence. The per-fact metrics live in src/eval/extraction_metrics.py;
this script is the CLI around them.

Usage:
    python scripts/eval_extraction.py [--sweep] [--groq] [--limit 0]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
os.chdir(str(PROJ))
sys.path.insert(0, str(PROJ))

os.environ["TQDM_DISABLE"] = "1"

from src.eval.extraction_metrics import (  # noqa: E402
    auc,
    bootstrap_auc,
    label_facts,
    name_hit,
    operating_point,
    pred_match,
)

GOLD = PROJ / "docs" / "eval_extraction_gold.jsonl"


def load_gold(limit: int = 0):
    rows = []
    with open(GOLD, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows if not limit else rows[:limit]


def run_backend(name: str, texts: list):
    """Returns (entities_per_text, triples_per_text, avg_ms)."""
    import torch

    if name == "relex":
        from src.extraction.entity_utils import extract_entities_with_relex, extract_triples_with_relex as f
        ent_fn = extract_entities_with_relex
    elif name == "gliner":
        from src.extraction.entity_utils import extract_entities_with_gliner, extract_triples_with_gliner as f
        ent_fn = extract_entities_with_gliner
    elif name == "spacy":
        from src.extraction.entity_utils import extract_entities_with_spacy as ent_fn
        from src.extraction.entity_utils import extract_triples_with_spacy as f
    elif name == "groq":
        from src.extraction.entity_utils import extract_entities_with_groq as ent_fn
        from src.extraction.entity_utils import extract_triples_with_groq as f
    else:
        raise ValueError(name)
    ents_out, trips_out, total_ms = [], [], 0.0
    for t in texts:
        t0 = time.perf_counter()
        try:
            with torch.no_grad():
                ents = ent_fn(t) or []
        except TypeError:
            ents = ent_fn(t) or []
        try:
            with torch.no_grad():
                trips = f(t) or []
        except TypeError:
            trips = f(t) or []
        total_ms += (time.perf_counter() - t0) * 1000
        ents_out.append(ents)
        trips_out.append(trips)
    return ents_out, trips_out, total_ms / max(len(texts), 1)


def summarize_backend(name, rows, ents_out, trips_out, salience_fn) -> dict:
    """Score one backend's output. Pure -- no model, no DB.

    Split in two on purpose:
      * entity_precision / triple_recall stay gold-driven (recall questions:
        "did we find the gold facts?").
      * facts_total / fact_precision / salience_auc are fact-driven (precision
        questions: "of what we asserted, how much is real?"). A backend can
        recall everything and still assert mostly noise, and only the second
        group shows that.
    """
    ent_tp = ent_fp = ent_fn = 0
    trip_tp = trip_fn = trip_total = 0
    junk_ok = junk_total = 0

    correct_sal, wrong_sal = [], []
    facts_from_junk = 0

    for row, ents, trips in zip(rows, ents_out, trips_out):
        exp_ents = row.get("entities", [])
        exp_trips = row.get("triples", [])
        got_names = [e.get("name", "") for e in ents if isinstance(e, dict)]
        if not exp_ents and not exp_trips:
            junk_total += 1
            if not got_names and not trips:
                junk_ok += 1
            # Facts asserted on a sentence that should have produced none are
            # real wrong assertions. They stay out of fact precision (junk_clean
            # already measures this case) but are counted, so the fact total
            # does not silently depend on this `continue`.
            facts_from_junk += len(label_facts(trips, []))
            continue
        for exp in exp_ents:
            if name_hit(exp["name"], got_names):
                ent_tp += 1
            else:
                ent_fn += 1
        for e in got_names:
            if not any(name_hit(exp["name"], [e]) for exp in exp_ents):
                ent_fp += 1
        for exp in exp_trips:
            trip_total += 1
            ok = False
            for t in trips:
                if not isinstance(t, dict):
                    continue
                if (name_hit(exp["s"], [t.get("subject", "")])
                        and name_hit(exp["o"], [t.get("object", "")])
                        and pred_match(exp["p"], t.get("predicate", ""))):
                    ok = True
                    break
            if ok:
                trip_tp += 1
            else:
                trip_fn += 1

        # Per-fact labels for this sentence. novelty is unknown offline, so
        # salience_fn gets None (which the production function treats as neutral).
        for fact in label_facts(trips, exp_trips):
            sal = salience_fn(fact.get("confidence", 0.5), fact.get("predicate", ""), None)
            (correct_sal if fact["correct"] else wrong_sal).append(sal)

    ent_prec = ent_tp / max(ent_tp + ent_fp, 1)
    ent_rec = ent_tp / max(ent_tp + ent_fn, 1)
    trip_rec = trip_tp / max(trip_total, 1)
    n_correct, n_wrong = len(correct_sal), len(wrong_sal)
    a = auc(correct_sal, wrong_sal)
    _, ci_lo, ci_hi = bootstrap_auc(correct_sal, wrong_sal)
    op = operating_point(correct_sal, wrong_sal)

    return {
        "backend": name,
        "entity_precision": round(ent_prec, 3),
        "entity_recall": round(ent_rec, 3),
        "triple_recall": round(trip_rec, 3),
        "junk_clean": f"{junk_ok}/{junk_total}",
        "facts_total": n_correct + n_wrong,
        "facts_correct": n_correct,
        "facts_wrong": n_wrong,
        "facts_from_junk_sentences": facts_from_junk,
        "fact_precision": round(n_correct / max(n_correct + n_wrong, 1), 3),
        "salience_auc": round(a, 3) if a == a else None,
        "salience_auc_ci_lo": ci_lo if ci_lo == ci_lo else None,
        "salience_auc_ci_hi": ci_hi if ci_hi == ci_hi else None,
        "tier_threshold": op["threshold"],
        "tier_correct_kept": op["correct_kept"],
        "tier_wrong_dropped": op["wrong_dropped"],
        "tier_kept_precision": op["kept_precision"],
    }

def score_backend(name: str, rows: list, verbose: bool = True):
    from src.extraction.entropy_gate import EntropyGate

    texts = [r["text"] for r in rows]
    ents_out, trips_out, avg_ms = run_backend(name, texts)
    result = summarize_backend(name, rows, ents_out, trips_out, EntropyGate.fact_salience)
    result["avg_ms"] = round(avg_ms, 1)
    if verbose:
        junk_note = ""
        if result["facts_from_junk_sentences"]:
            junk_note = " +%d on junk" % result["facts_from_junk_sentences"]
        print(f"  {name:6} {avg_ms:7.1f}ms  entP={result['entity_precision']:.3f} "
              f"entR={result['entity_recall']:.3f} "
              f"tripR={result['triple_recall']:.3f} "
              f"factP={result['fact_precision']:.3f} "
              f"({result['facts_correct']}/{result['facts_total']}{junk_note}) "
              f"junk={result['junk_clean']}", flush=True)
        auc_txt = ("n/a" if result["salience_auc"] is None
                   else f"{result['salience_auc']:.3f} "
                        f"[{result['salience_auc_ci_lo']:.3f}, {result['salience_auc_ci_hi']:.3f}]")
        print(f"         salience AUC={auc_txt}   tier@{result['tier_threshold']:.2f}: "
              f"kept {result['tier_correct_kept']}/{result['facts_correct']} correct, "
              f"dropped {result['tier_wrong_dropped']}/{result['facts_wrong']} wrong "
              f"(kept precision {result['tier_kept_precision']})", flush=True)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate extraction backends on the gold set")
    ap.add_argument("--sweep", action="store_true", help="sweep RELEX_REL_THRESHOLD 0.3/0.5/0.7/0.9")
    ap.add_argument("--groq", action="store_true", help="include Groq backend (needs key)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--lang", default="", help="filter: de or en")
    args = ap.parse_args()

    rows = load_gold(args.limit)
    if args.lang:
        rows = [r for r in rows if r.get("lang") == args.lang]
    print(f"gold: {len(rows)} items", flush=True)
    backends = ["relex", "gliner", "spacy"] + (["groq"] if args.groq else [])
    results = {}
    if args.sweep:
        for thr in ("0.3", "0.5", "0.7", "0.9"):
            os.environ["RELEX_REL_THRESHOLD"] = thr
            print(f"RELEX_REL_THRESHOLD={thr}", flush=True)
            results[f"relex@{thr}"] = score_backend("relex", rows)
        os.environ.pop("RELEX_REL_THRESHOLD", None)
        for b in backends:
            if b != "relex":
                results[b] = score_backend(b, rows)
    else:
        for b in backends:
            results[b] = score_backend(b, rows)
    out = PROJ / "docs" / "eval_extraction_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"saved to {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
