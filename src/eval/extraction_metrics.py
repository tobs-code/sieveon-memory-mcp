"""
Evaluation metrics for extraction quality (pure functions, no model, no DB).

These live here rather than in `scripts/eval_extraction.py` so they can be unit
tested without loading a 1.3 GB relex model, and so the script stays a thin CLI.

Why per-fact labels: the previous eval iterated over *gold* triples and, for
every miss, charged the miss with `max(salience)` over all triples the model
produced for that sentence. That is not a measurement of any fact. A sentence
holding one correct and one wrong fact was counted as correct once and wrong
twice, and a confidently-wrong fact in a mostly-correct sentence was invisible.
The resulting "correct mean 0.843 vs wrong mean 0.844, no separation" was an
artefact of that proxy: extraction confidence alone really does separate the two
classes (AUC ~0.63 on the current gold set).
"""

import math
import random
from typing import Any, Dict, Iterable, List, Optional, Sequence

# Predicate synonyms, keyed by the gold predicate. Symmetric enough for the gold
# vocabulary; an unmatched predicate only matches itself.
PRED_SYNONYMS = {
    "created": {"created", "developed", "authored", "built", "wrote", "designed", "published", "made"},
    "developed": {"created", "developed", "built", "made"},
    "discovered": {"discovered", "found", "identified"},
    "works_at": {"works_at", "employed_by", "works_for"},
    "located_in": {"located_in", "based_in", "headquartered_in", "situated_in"},
    "uses": {"uses", "used", "utilizes"},
    "leads": {"leads", "heads", "leaded_by", "ceo_of", "leads_to"},
    "acquired": {"acquired", "bought", "purchased"},
    "founded": {"founded", "established", "started"},
}


def pred_match(expected: str, got: str) -> bool:
    """Is `got` an acceptable realization of the gold predicate `expected`?"""
    e, g = (expected or "").lower(), (got or "").lower()
    if e == g:
        return True
    return g in PRED_SYNONYMS.get(e, {e})


def name_hit(expected: str, names: Iterable[str]) -> bool:
    """Substring-tolerant entity-name match (token boundaries ignored).

    Deliberately loose: "Corvus" must hit "Corvus Software". The cost of the
    looseness is counted as fact precision, not hidden.
    """
    e = (expected or "").lower()
    if not e:
        return False
    return any(e == n.lower() or e in n.lower() or n.lower() in e for n in names if n)


def label_facts(facts: Sequence[Any], gold_triples: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Label every produced fact correct/wrong against the sentence's gold triples.

    A fact is correct iff it matches at least one gold triple of the same
    sentence. Facts that are not dicts, or that carry no subject/predicate/object,
    are skipped rather than guessed at. The original fact dict is returned with
    an added `correct` key, so downstream callers keep the extractor output.
    """
    labelled: List[Dict[str, Any]] = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        s, p, o = fact.get("subject"), fact.get("predicate"), fact.get("object")
        if not (s and p and o):
            continue
        correct = any(
            name_hit(g.get("s", ""), [str(s)])
            and name_hit(g.get("o", ""), [str(o)])
            and pred_match(g.get("p", ""), str(p))
            for g in gold_triples
            if isinstance(g, dict)
        )
        labelled.append({**fact, "correct": correct})
    return labelled


def auc(positive: Sequence[float], negative: Sequence[float]) -> float:
    """Mann-Whitney AUC: P(pos > neg) + 0.5 * P(pos == neg).

    0.5 = no separation, 1.0 = perfect. Returns nan if either class is empty --
    a single-class AUC is not a number, and silently returning 0.5 or 1.0 there
    would let a backend with zero correct facts look either harmless or perfect.
    """
    pos = [float(x) for x in positive]
    neg = [float(x) for x in negative]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def bootstrap_auc(
    positive: Sequence[float],
    negative: Sequence[float],
    n: int = 2000,
    seed: int = 0,
) -> tuple:
    """Resampling CI for auc(). Returns (mean, lo95, hi95).

    The gold set is small (17 triples), so a bare AUC overstates what the number
    supports. Deterministic for a given seed.
    """
    pos = [float(x) for x in positive]
    neg = [float(x) for x in negative]
    if not pos or not neg:
        return (float("nan"), float("nan"), float("nan"))
    rnd = random.Random(seed)
    vals: List[float] = []
    for _ in range(n):
        sp = [rnd.choice(pos) for _ in pos]
        sn = [rnd.choice(neg) for _ in neg]
        a = auc(sp, sn)
        if not math.isnan(a):
            vals.append(a)
    if not vals:
        return (float("nan"), float("nan"), float("nan"))
    vals.sort()
    lo = vals[max(0, int(0.025 * len(vals)))]
    hi = vals[min(len(vals) - 1, int(0.975 * len(vals)))]
    return (round(sum(vals) / len(vals), 3), round(lo, 3), round(hi, 3))


def operating_point(
    correct: Sequence[float],
    wrong: Sequence[float],
    threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """What a keep-if->= threshold does to each class.

    `threshold=None` means "whatever the shipped TIER_DROP_THRESHOLD is", which
    is read lazily so this stays pure and the caller cannot get the tiering
    policy and the measurement out of sync.
    """
    if threshold is None:
        from src.extraction.entropy_gate import tier_threshold
        threshold = tier_threshold()
    thr = float(threshold)

    def kept(scores):
        return [s for s in scores if s >= thr]

    k_correct = len(kept(correct))
    k_wrong = len(kept(wrong))
    kept_total = k_correct + k_wrong
    return {
        "threshold": round(thr, 4),
        "correct_total": len(correct),
        "wrong_total": len(wrong),
        "correct_kept": k_correct,
        "wrong_kept": k_wrong,
        "wrong_dropped": len(wrong) - k_wrong,
        # None, not nan: callers write this to strict JSON.
        "kept_precision": round(k_correct / kept_total, 4) if kept_total else None,
    }
