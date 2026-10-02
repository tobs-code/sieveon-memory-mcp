"""Is the supported/implied gap lexical rather than semantic?

The NLI verifier is at chance on supported vs implied (pairwise AUC 0.527,
interval containing 0.5). Before building a second model, test the cheaper
hypothesis: most `implied` triples are not an entailment problem at all but
a predicate over-reach, and an over-reach should be visible in the surface
form. "Cooking helps Andrew be creative" does not contain `provides`.
"Deborah traveled to Bali" does not contain `work`.

Three signals, same 202 annotated triples, same two targets:

    nli_margin        the verifier score alone            (baseline)
    lexical           static lexicon match, graded 0/0.5/1
    margin x lexical  the composition under test

`lexical` is deliberately static and hand-written, not model-generated.
A synonym table chosen by an LLM would already be a semantic classifier,
which is the thing being tested for.

Known limits, stated up front:
  - Argument roles are not resolved. A sentence can contain `provide` for a
    different subject ("Susie provides comfort"), and the lexicon will still
    score it as a lexical match. Those cases are exactly what the
    right-vs-wrong column is there to expose.
  - Only the verbal part of the predicate is matched. Object-side
    over-reach ("leads veterans" for "supporting veterans") is not lexical.
  - Negation is handled by one narrow rule: a match within three tokens
    after a negator counts as no match.

Usage:
    python scripts/eval_strict_lexical.py
    python scripts/eval_strict_lexical.py --out docs/eval_strict_lexical.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
MODEL = "cross-encoder/nli-MiniLM2-L6-H768"

from scripts.eval_verifier import bootstrap_auc  # noqa: E402
from scripts.eval_verifier_strict import load_cases  # noqa: E402
from src.extraction.verbalise import verbalise  # noqa: E402

# Surface forms per predicate. First entry is the exact predicate surface
# (score 1.0); the rest are pre-agreed synonyms (score 0.5). Written by hand
# from the predicate inventory of both annotated sets, not generated.
LEXICON: Dict[str, List[str]] = {
    "created":   ["created", "made"],
    "provides":  ["provides", "offer", "give", "bring"],
    "works_at":  ["works", "employed", "job", "volunteer"],
    "discovered": ["discovered", "find"],
    "developed": ["developed", "develop"],
    "built":     ["built", "build"],
    "acquired":  ["acquired", "got", "bought", "purchased"],
    "wrote":     ["wrote", "written", "write", "authored"],
    "part_of":   ["part", "member", "family", "group"],
    "uses":      ["uses", "use", "using"],
    "founded":   ["founded", "establish", "start"],
    "designed":  ["designed", "design"],
    "located_in": ["in", "at"],
    "leads":     ["leads", "lead", "leading", "led"],
}

NEGATORS = {"not", "never", "no", "nor", "hardly", "without"}


def lexical_support(text: str, predicate: str) -> Tuple[float, str]:
    """0.0 no surface form, 0.5 synonym only, 1.0 exact predicate surface."""
    forms = LEXICON.get(predicate)
    if not forms:
        return 0.0, ""
    toks = [re.sub(r"[^a-z0-9']", "", t.lower()) for t in text.split()]
    toks = [t for t in toks if t]
    for i, tok in enumerate(toks):
        stem = _stem(tok)
        for rank, form in enumerate(forms):
            f = _stem(form)
            if stem != f:
                continue
            window = toks[max(0, i - 3):i]
            if any(w in NEGATORS for w in window):
                continue  # negated occurrence, does not count as support
            return (1.0 if rank == 0 else 0.5), form
    return 0.0, ""


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s", "d"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def pairwise(score: List[float], cases: List[Dict[str, Any]],
             a: str, b: str) -> Dict[str, Any]:
    sub = [(s, c) for s, c in zip(score, cases) if c["verdict"] in (a, b)]
    auc, lo, hi = bootstrap_auc([s for s, _ in sub],
                                [1 if c["verdict"] == a else 0 for _, c in sub])
    return {"n": len(sub), "auc": round(auc, 3),
            "auc_ci": [round(lo, 3), round(hi, 3)]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    from sentence_transformers import CrossEncoder

    cases = load_cases()
    model = CrossEncoder(args.model, max_length=512, device=args.device)
    i2l = {int(k): str(v).lower() for k, v in model.model.config.id2label.items()}
    ent = next(k for k, v in i2l.items() if "entail" in v)
    con = next(k for k, v in i2l.items() if "contradict" in v)
    logits = model.predict(
        [[c["text"], verbalise(c["s"], c["p"], c["o"])] for c in cases],
        convert_to_numpy=True)
    margins = [float(r[ent]) - float(r[con]) for r in logits]

    lex: List[float] = []
    hits: List[str] = []
    for c in cases:
        v, form = lexical_support(c["text"], c["p"])
        lex.append(v)
        hits.append(form)

    product = [m * x for m, x in zip(margins, lex)]
    boosted = [m * (1.0 + x) for m, x in zip(margins, lex)]

    signals = {"nli_margin": margins, "lexical": lex,
               "margin_x_lexical": product, "margin_x_(1+lexical)": boosted}

    print(f"{len(cases)} annotated triples\n")
    print("  supported vs implied (the target the NLI model failed on):")
    print(f"    {'signal':22} {'AUC':>6}  95% CI")
    out: Dict[str, Any] = {}
    for name, sc in signals.items():
        r = pairwise(sc, cases, "supported", "implied")
        out[name] = r
        print(f"    {name:22} {r['auc']:6.3f}  "
              f"[{r['auc_ci'][0]:.3f}, {r['auc_ci'][1]:.3f}]")

    print("\n  sanity check, same signals on the target NLI does handle:")
    print(f"    {'signal':22} {'AUC':>6}  95% CI")
    for name, sc in signals.items():
        si = pairwise(sc, cases, "supported", "wrong")
        out[name]["supported_vs_wrong"] = si
        print(f"    {name:22} {si['auc']:6.3f}  "
              f"[{si['auc_ci'][0]:.3f}, {si['auc_ci'][1]:.3f}]")

    # Contingency: how much of the supported/implied split does the lexicon
    # see at all? A binary signal cannot express more than this.
    print("\n  lexical hit rate by hand verdict:")
    from collections import Counter
    tab: Dict[str, Counter] = {}
    for c, x in zip(cases, lex):
        tab.setdefault(c["verdict"], Counter())[x] += 1
    print(f"    {'verdict':12} {'exact':>6} {'synonym':>8} {'none':>6}")
    for v in ("supported", "implied", "wrong"):
        t = tab[v]
        print(f"    {v:12} {t[1.0]:6} {t[0.5]:8} {t[0.0]:6}")

    print("\n  cases where the lexicon matched but the hand verdict is wrong "
          "(argument-role over-reach):")
    for c, x, h in zip(cases, lex, hits):
        if x > 0 and c["verdict"] == "wrong":
            print(f"    [{c['p']}~{h}] {c['s']} -> {c['o']}")
            print(f"        {c['text'][:96]}")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"model": args.model, "cases": len(cases), "pairwise": out},
            indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())