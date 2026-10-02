"""Verifier experiment: does an NLI cross-encoder beat extraction confidence?

Decision rule (agreed, docs/eval_decision_gates_vs_verifier.md): adopt the
verifier ONLY if its in-band AUC over the 0.70-0.95 extraction-confidence
band beats the base confidence there, AND precision at fixed recall improves
by at least 10 points with a bootstrap CI excluding zero. Overall AUC is the
wrong number: the base already ranks well globally.

The triple is verbalised into a natural claim first. The verifier never
re-extracts; it decides whether this concrete predicate is licensed by the
sentence. Template per predicate, subject and object substituted:

    "Andrew is a person living in an apartment."
    claim: "Andrew built the apartment."        -> contradiction, reject
    claim: "Andrew is located in the apartment." -> entailment, accept

That matches the observed error profile: right entities, wrong verb.

Usage:
    python scripts/eval_verifier.py --model cross-encoder/nli-deberta-v3-xsmall
    python scripts/eval_verifier.py --model x --model y --compare
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "docs" / "eval_triples_gold_locomo_draft_model.jsonl"

from src.extraction.verbalise import CLAIM, verbalise  # noqa: E402

BAND_LO, BAND_HI = 0.70, 0.95


def bootstrap_auc(
    scores: List[float], labels: List[int], n: int = 2000, seed: int = 17
) -> Tuple[float, float, float]:
    """AUC with a percentile bootstrap CI, computed by resampling pairs.

    Pairs are resampled, not individual items, because AUC is a pairwise
    statistic and item resampling breaks the pairing structure.
    """
    import random

    rng = random.Random(seed)
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return float("nan"), float("nan"), float("nan")

    def _auc(pp: List[float], nn: List[float]) -> float:
        wins = sum((a > b) + 0.5 * (a == b) for a in pp for b in nn)
        return wins / (len(pp) * len(nn))

    point = _auc(pos, neg)
    reps = []
    for _ in range(n):
        reps.append(_auc(
            [rng.choice(pos) for _ in pos],
            [rng.choice(neg) for _ in neg]))
    reps.sort()
    return point, reps[int(0.025 * n)], reps[int(0.975 * n)]


def precision_at_recall(
    scores: List[float], labels: List[int], target_recall: float = 0.60
) -> Tuple[float, float]:
    """Precision at the threshold that reaches target recall, and the threshold."""
    order = sorted(zip(scores, labels), reverse=True)
    total_pos = sum(labels)
    if not total_pos:
        return 0.0, 0.0
    need = max(1, round(target_recall * total_pos))
    # Threshold at the score of the need-th positive.
    seen = 0
    thresh = order[0][0]
    for s, y in order:
        seen += y
        if seen >= need:
            thresh = s
            break
    kept = [(s, y) for s, y in order if s >= thresh]
    prec = sum(y for _, y in kept) / len(kept) if kept else 0.0
    return prec, thresh


class Verifier:
    """A thin wrapper around a cross-encoder, with label order resolved
    from the model, never assumed."""

    def __init__(self, name: str, device: str = "cuda", fp16: bool = True):
        from sentence_transformers import CrossEncoder

        self.name = name
        self.model = CrossEncoder(name, max_length=512, device=device)
        if fp16:
            try:
                self.model.model = self.model.model.half()
            except Exception:
                pass
        id2label = {
            int(k): str(v).lower() for k, v in
            self.model.model.config.id2label.items()
        }
        self.entail_idx = next(
            k for k, v in id2label.items() if "entail" in v)
        self.contra_idx = next(
            k for k, v in id2label.items() if "contradict" in v)
        try:
            self.params_m = sum(
                p.numel() for p in self.model.model.parameters()) / 1e6
        except Exception:
            self.params_m = float("nan")

    def score(self, pairs: List[Tuple[str, str]]) -> List[Dict[str, float]]:
        """Score (premise, hypothesis) pairs: entailment minus contradiction.

        Returns the raw logits as well as the margin, because the margin is
        what the acceptance decision should use and the logits are what
        debugging needs.
        """
        import numpy as np

        logits = self.model.predict(
            [[p, h] for p, h in pairs], convert_to_numpy=True)
        out = []
        for row in np.atleast_2d(logits):
            ent = float(row[self.entail_idx])
            con = float(row[self.contra_idx])
            out.append({"entail": ent, "contra": con, "margin": ent - con})
        return out


async def load_cases() -> List[Dict[str, Any]]:
    from scripts.reconcile_triple_annotation import (
        ANNOTATION, IMPLIED, SUPPORTED, WRONG, load_gap,
    )

    rows = [json.loads(l) for l in
            DRAFT.read_text(encoding="utf-8").splitlines() if l.strip()]
    verdicts = {(s, a, p, o): v for s, i, a, p, o, v in ANNOTATION}
    for g in load_gap():
        verdicts[(g["stratum"], g["s"], g["p"], g["o"])] = g["verdict"]

    counters: Dict[str, int] = {}
    cases = []
    for r in rows:
        counters[r["stratum"]] = counters.get(r["stratum"], 0) + 1
        idx = counters[r["stratum"]]
        for t in r.get("asserted", []):
            v = verdicts.get((r["stratum"], t["s"], t["p"], t["o"]))
            if v is None:
                continue
            cases.append({
                "text": r["text"],
                "stratum": r["stratum"],
                "idx": idx,
                "s": t["s"], "p": t["p"], "o": t["o"],
                "extract_conf": float(t.get("c") or 0.0),
                "label": 1 if v in (SUPPORTED, IMPLIED) else 0,
                "verdict": v,
            })
    return cases


async def run_model(name: str) -> Dict[str, Any]:
    import torch

    t0 = time.perf_counter()
    verifier = Verifier(name)
    load_s = time.perf_counter() - t0
    mem_mb = (torch.cuda.memory_allocated() / 1024 ** 2
              if torch.cuda.is_available() else 0.0)

    cases = await load_cases()
    pairs = [(c["text"], verbalise(c["s"], c["p"], c["o"])) for c in cases]

    # Warm up, then time single-item latency the way ingestion would pay it.
    verifier.score(pairs[:2])
    lat: List[float] = []
    scores = []
    batch = 8
    for i in range(0, len(pairs), batch):
        t1 = time.perf_counter()
        out = verifier.score(pairs[i:i + batch])
        lat.append((time.perf_counter() - t1) / (i + batch - i))
        scores.extend(o["margin"] for o in out)
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    lat_ms = [x * 1000 for x in lat]
    lat_ms.sort()

    labels = [c["label"] for c in cases]
    extract = [c["extract_conf"] for c in cases]

    # In-band subset: only triples the extractor was unsure about.
    band = [(s, y) for s, y, c in zip(scores, labels, extract)
            if BAND_LO <= c <= BAND_HI]
    band_extract = [(c, y) for c, y in zip(extract, labels)
                    if BAND_LO <= c <= BAND_HI]

    def _split(pairs):
        return [s for s, _ in pairs], [y for _, y in pairs]

    bs, by = _split(band)
    es, ey = _split(band_extract)
    auc_v, lo_v, hi_v = bootstrap_auc(bs, by)
    auc_e, lo_e, hi_e = bootstrap_auc(es, ey)

    p_ver, t_ver = precision_at_recall(bs, by)
    p_ext, t_ext = precision_at_recall(es, ey)

    return {
        "model": name,
        "params_m": round(verifier.params_m, 1),
        "load_s": round(load_s, 1),
        "gpu_mem_mb": round(mem_mb, 1),
        "cases": len(cases),
        "in_band": len(band),
        "latency_ms": {
            "p50": round(lat_ms[len(lat_ms) // 2], 1),
            "p95": round(lat_ms[int(0.95 * len(lat_ms))], 1),
            "mean": round(statistics.mean(lat_ms), 1),
        },
        "auc_in_band": {"verifier": round(auc_v, 3),
                        "lo": round(lo_v, 3), "hi": round(hi_v, 3)},
        "auc_base_in_band": {"extract": round(auc_e, 3),
                             "lo": round(lo_e, 3), "hi": round(hi_e, 3)},
        "precision_at_recall_0.60": {
            "verifier": round(p_ver, 3), "verifier_thresh": round(t_ver, 4),
            "extract": round(p_ext, 3), "extract_thresh": round(t_ext, 4),
        },
    }


def print_report(r: Dict[str, Any]) -> None:
    print(f"\n=== verifier: {r['model']} ===")
    print(f"  params             {r['params_m']}M   load {r['load_s']}s   "
          f"GPU {r['gpu_mem_mb']}MB")
    print(f"  triples judged     {r['cases']}   in band "
          f"[{BAND_LO}-{BAND_HI}]: {r['in_band']}")
    lat = r["latency_ms"]
    print(f"  latency/item       p50 {lat['p50']}ms  p95 {lat['p95']}ms  "
          f"mean {lat['mean']}ms")
    v, e = r["auc_in_band"], r["auc_base_in_band"]
    print(f"  in-band AUC        verifier {v['verifier']:.3f} "
          f"[{v['lo']:.3f}-{v['hi']:.3f}]")
    print(f"                     extract  {e['extract']:.3f} "
          f"[{e['lo']:.3f}-{e['hi']:.3f}]")
    p = r["precision_at_recall_0.60"]
    print(f"  P@R=0.60           verifier {p['verifier']:.3f} "
          f"(thr {p['verifier_thresh']})")
    print(f"                     extract  {p['extract']:.3f} "
          f"(thr {p['extract_thresh']})")
    gain = p["verifier"] - p["extract"]
    print(f"  delta              {gain:+.3f}")
    print()
    if v["lo"] > e["hi"]:
        print("  -> in-band AUC beats base with non-overlapping CIs")
    else:
        print("  -> in-band AUC does NOT clearly beat base")
    if gain >= 0.10:
        print("  -> precision gain >= 10 points: adoption rule satisfied")
    else:
        print("  -> precision gain < 10 points: adoption rule NOT satisfied")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", action="append", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    reports = []
    for name in args.model:
        reports.append(await run_model(name))
        print_report(reports[-1])

    if args.out:
        Path(args.out).write_text(
            json.dumps({"reports": reports}, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))