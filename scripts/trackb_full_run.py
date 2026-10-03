"""Track B v1.0 full-population reality check. Frozen prompt from dbeb935.

Populations (never pooled): 24 expansion pairs, 4 epistemic pairs,
60 blind sentences. Pair-scoped scoring: only the gold X->Y edge counts.
No prompt changes, no few-shot, no threshold tuning.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_provides_llm import call as llm_call

ROOT = Path(__file__).resolve().parents[1]


def norm(s: str) -> str:
    s = s.strip().lower()
    if s.startswith("the "):
        s = s[4:]
    return s


def load_pairs():
    pairs = []
    spec = [("docs/eval_phase_a_expansion_scaled.json", None),
            ("docs/eval_phase_a_expansion_ae1.json", None),
            ("docs/eval_phase_a_expansion_ap2.json", None),
            ("docs/eval_phase_a_expansion_np2.json", None)]
    for rel, _ in spec:
        d = json.loads((ROOT / rel).read_text())
        fps = d["pairs"] if "pairs" in d else d.get("controlled_pairs", [])
        by = {}
        for e in fps:
            by.setdefault(e["pair_id"], {})[e["class"]] = e
        for pid, g in by.items():
            if "clean_positive" in g and "hard_negative" in g:
                pairs.append(("expansion", g["clean_positive"], g["hard_negative"]))
    v2 = json.loads((ROOT / "docs" / "eval_phase_a_manifest.json").read_text())
    by = {}
    for e in v2["controlled_pairs"]:
        if e.get("construction_family_id") == "nominal_possessive:epistemic":
            by.setdefault(e["pair_id"], {})[e["class"]] = e
    for pid, g in by.items():
        pairs.append(("epistemic", g["clean_positive"], g["hard_negative"]))
    return pairs


def parse_triples(raw: str):
    try:
        return json.loads(raw[raw.index("["):raw.rindex("]") + 1])
    except (ValueError, json.JSONDecodeError):
        return None


def edge_present(triples, x, y):
    for t in triples or []:
        if not isinstance(t, dict):
            continue
        if norm(str(t.get("subject", ""))) == norm(x) and \
                norm(str(t.get("object", ""))) == norm(y):
            return True
    return False


def any_edge(triples):
    return bool([t for t in triples or [] if isinstance(t, dict) and t.get("subject")])


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--blind-only", action="store_true")
    args = ap.parse_args()
    if not args.blind_only:
        pairs = load_pairs()
        print(f"controlled pairs: {len(pairs)}")
        cons = clean_ok = hard_ok = 0
        cats = {}
        for pop, clean, hard in pairs:
            xe, ye = clean["entities"]
            results = {}
            for variant, entry in (("clean", clean), ("hard", hard)):
                raw = llm_call(entry["sentence"])
                tr = parse_triples(raw)
                hit = edge_present(tr, xe, ye) if tr is not None else None
                other = any_edge(tr) if tr is not None else None
                results[variant] = (hit, other, tr)
            ch, oh, th = results["hard"]
            cc, oc, tc = results["clean"]
            c_ok = cc is True
            h_ok = ch is False
            if c_ok and h_ok:
                cat = "CONSISTENT"
                cons += 1
            elif ch is True:
                cat = "HARD_FP"
            elif c_ok and oh:
                cat = "PAIR_MISS_WRONG_OBJECT" if any_edge(th) else "CLEAN_OK_HARD_OTHER"
            elif not c_ok:
                cat = "CLEAN_MISS"
            else:
                cat = "UNPARSEABLE" if (tc is None or th is None) else "MIXED"
            clean_ok += c_ok
            hard_ok += h_ok
            cats[cat] = cats.get(cat, 0) + 1
            flag = ""
            if oh and not ch:
                flag = " [sentence_asserts_other_valid_relation=true gold_pair_supported=false]"
            print(f"{cat:24} {pop:9} {clean['pair_id']}{flag}")
        print(f"\ncontrolled: consistent {cons}/{len(pairs)}, clean_ok {clean_ok}, hard_ok {hard_ok}")
        print("categories:", cats)

    print("\n--- blind 60 ---")
    resume_path = ROOT / "docs" / "trackb_blind60.jsonl"
    done = {}
    if resume_path.exists():
        for line in resume_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["id"]] = r
    btp = btn = bfp = bfn = 0
    with open(resume_path, "a", encoding="utf-8") as fh:
        for line in (ROOT / "docs" / "eval_hard_negative_prevalence.jsonl").read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r["id"] in done:
                rec = done[r["id"]]
                mark = rec["mark"]
                print(mark, rec["cls"], '|', r["text"][:60], '(cached)')
            else:
                cls = r.get("provides_class")
                raw = llm_call(r["text"])
                tr = parse_triples(raw)
                pred = any_edge(tr) if tr is not None else None
                gold_pos = cls in ("clean_positive", "ambiguous_positive")
                mark = "TP" if pred and gold_pos else "TN" if pred is False and not gold_pos \
                    else "FP" if pred else "FN" if pred is False else "?"
                rec = {"id": r["id"], "cls": cls, "mark": mark,
                       "triples": tr if tr is not None else raw[:300]}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                print(mark, cls, '|', r["text"][:60])
            btp += mark == "TP"
            btn += mark == "TN"
            bfp += mark == "FP"
            bfn += mark == "FN"
    print(f"\nblind: tp={btp} tn={btn} fp={bfp} fn={bfn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
