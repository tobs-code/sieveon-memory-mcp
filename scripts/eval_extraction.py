"""
Extraction eval: entity/triple recall per backend on docs/eval_extraction_gold.jsonl.

Compares relex vs gliner2.5-multi vs spacy (and optional --groq), including a
threshold sweep for RELEX_REL_THRESHOLD. Predicate matching is
synonym-tolerant (created/developed/authored/built/wrote/designed/published).

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

GOLD = PROJ / "docs" / "eval_extraction_gold.jsonl"

PRED_SYNONYMS = {
    "created": {"created", "developed", "authored", "built", "wrote", "designed", "published", "made"},
    "developed": {"created", "developed", "built", "made"},
    "discovered": {"discovered", "found", "identified"},
    "works_at": {"works_at", "employed_by", "works for"},
    "located_in": {"located_in", "based_in", "headquartered_in", "situated_in"},
    "uses": {"uses", "used", "utilizes"},
    "leads": {"leads", "heads", "leaded_by", "ceo_of", "leads_to"},
    "acquired": {"acquired", "bought", "purchased"},
    "founded": {"founded", "established", "started"},
}


def pred_match(expected: str, got: str) -> bool:
    e, g = expected.lower(), got.lower()
    if e == g:
        return True
    return g in PRED_SYNONYMS.get(e, {e})


def name_hit(expected: str, names: list) -> bool:
    e = expected.lower()
    return any(e == n.lower() or e in n.lower() or n.lower() in e for n in names)


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


def score_backend(name: str, rows: list, verbose: bool = True):
    from src.extraction.entropy_gate import EntropyGate

    texts = [r["text"] for r in rows]
    ents_out, trips_out, avg_ms = run_backend(name, texts)
    ent_tp = ent_fp = ent_fn = 0
    trip_tp = trip_fn = 0
    trip_total = 0
    junk_ok = junk_total = 0
    # Salience validation: per produced triple, is it gold-correct, and what
    # salience (novelty unknown offline -> neutral 0.5) did it get?
    sal_correct, sal_wrong = [], []
    for row, ents, trips in zip(rows, ents_out, trips_out):
        exp_ents = row.get("entities", [])
        exp_trips = row.get("triples", [])
        got_names = [e.get("name", "") for e in ents if isinstance(e, dict)]
        if not exp_ents and not exp_trips:
            junk_total += 1
            if not got_names and not trips:
                junk_ok += 1
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
            match_sal = None
            for t in trips:
                if not isinstance(t, dict):
                    continue
                s = t.get("subject", "")
                o = t.get("object", "")
                p = t.get("predicate", "")
                if name_hit(exp["s"], [s]) and name_hit(exp["o"], [o]) and pred_match(exp["p"], p):
                    ok = True
                    sal = EntropyGate.fact_salience(t.get("confidence", 0.5), p, None)
                    match_sal = sal if match_sal is None else max(match_sal, sal)
            # Salience of the matching produced triple; misses contribute
            # their best produced salience as "wrong" (a confident miss).
            if ok and match_sal is not None:
                sal_correct.append(match_sal)
            else:
                cands = [
                    EntropyGate.fact_salience(t.get("confidence", 0.5), t.get("predicate", ""), None)
                    for t in trips if isinstance(t, dict)
                ]
                if cands:
                    sal_wrong.append(max(cands))
            if ok:
                trip_tp += 1
            else:
                trip_fn += 1
    ent_prec = ent_tp / max(ent_tp + ent_fp, 1)
    ent_rec = ent_tp / max(ent_tp + ent_fn, 1)
    trip_rec = trip_tp / max(trip_total, 1)
    import statistics as _stats

    def _mean(xs):
        return round(_stats.fmean(xs), 3) if xs else 0.0

    # Does salience >= 0.50 separate correct from wrong triples?
    keep_correct = sum(1 for s in sal_correct if s >= 0.50)
    keep_wrong = sum(1 for s in sal_wrong if s >= 0.50)
    result = {
        "backend": name,
        "avg_ms": round(avg_ms, 1),
        "entity_precision": round(ent_prec, 3),
        "entity_recall": round(ent_rec, 3),
        "triple_recall": round(trip_rec, 3),
        "junk_clean": f"{junk_ok}/{junk_total}",
        "salience_correct_n": len(sal_correct),
        "salience_wrong_n": len(sal_wrong),
        "salience_correct_mean": _mean(sal_correct),
        "salience_wrong_mean": _mean(sal_wrong),
        "salience_keep_correct_at_050": f"{keep_correct}/{len(sal_correct)}",
        "salience_keep_wrong_at_050": f"{keep_wrong}/{len(sal_wrong)}",
    }
    if verbose:
        print(f"  {name:6s} {avg_ms:7.1f}ms  entP={ent_prec:.3f} entR={ent_rec:.3f} "
              f"tripR={trip_rec:.3f} junk={junk_ok}/{junk_total}", flush=True)
        print(f"         salience: correct mean={_mean(sal_correct)} (n={len(sal_correct)}) "
              f"wrong mean={_mean(sal_wrong)} (n={len(sal_wrong)}) "
              f"kept@0.50: {keep_correct}/{len(sal_correct)} correct, {keep_wrong}/{len(sal_wrong)} wrong", flush=True)
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
