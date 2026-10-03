"""Track B NuExtract-v1 run: same populations, same pair-scoped scoring.

Documented v1 format: ### Template / ### Example / ### Text in user message.
Mapping: provider->subject, receiver->object, relation fixed to provides.
Resume-capable via docs/trackb_nuextract.jsonl.
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trackb_full_run import load_pairs, norm, edge_present, any_edge

MODEL = "numind/nuextract3:q4_k_m"
URL = "http://localhost:11434/api/chat"
TEMPLATE = {"support_relations": [{"provider": "verbatim-string",
                                   "receiver": "verbatim-string"}]}
EXAMPLE_IN = "Maria helped Tim with the fundraiser."
EXAMPLE_OUT = '{"support_relations": [{"provider": "Maria", "receiver": "Tim"}]}'
EXAMPLE_NEG_IN = "Maria offered to help Tim with the fundraiser."
EXAMPLE_NEG_OUT = '{"support_relations": []}'


def call(sentence: str) -> str:
    body = json.dumps({
        "model": MODEL, "stream": False, "think": False,
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 256},
        "messages": [
            {"role": "template", "content": json.dumps(TEMPLATE, indent=4)},
            {"role": "examples.input", "content": EXAMPLE_IN},
            {"role": "examples.output", "content": EXAMPLE_OUT},
            {"role": "examples.input", "content": EXAMPLE_NEG_IN},
            {"role": "examples.output", "content": EXAMPLE_NEG_OUT},
            {"role": "user", "content": sentence},
        ]}).encode()
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(URL, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read())["message"]["content"]
        except Exception as e:
            last = e
    raise RuntimeError(f"nuextract call failed 3x: {last}")


def to_triples(raw: str):
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        obj = json.loads(raw[start:end])
        rels = obj.get("support_relations", []) or []
        return [{"subject": r.get("provider", ""), "relation": "provides",
                 "object": r.get("receiver", "")} for r in rels
                if isinstance(r, dict) and r.get("provider") and r.get("receiver")]
    except (ValueError, json.JSONDecodeError, AttributeError):
        return None


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--blind-only", action="store_true")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    rec_path = root / "docs" / "trackb_nuextract3.jsonl"
    done = {}
    if rec_path.exists():
        for line in rec_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["key"]] = r
    fh = open(rec_path, "a", encoding="utf-8")

    def run_case(key, sentence):
        if key in done:
            return done[key]
        raw = call(sentence)
        rec = {"key": key, "raw": raw[:500]}
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        done[key] = rec
        return rec

    if not args.blind_only:
        pairs = load_pairs()
        cons = clean_ok = hard_ok = 0
        cats = {}
        for pop, clean, hard in pairs:
            xe, ye = clean["entities"]
            res = {}
            for variant, entry in (("clean", clean), ("hard", hard)):
                rec = run_case(f"{pop}|{clean['pair_id']}|{variant}", entry["sentence"])
                tr = to_triples(rec["raw"])
                res[variant] = (edge_present(tr, xe, ye) if tr is not None else None,
                                any_edge(tr) if tr is not None else None, tr)
            ch, oh, th = res["hard"]
            cc, oc, tc = res["clean"]
            c_ok, h_ok = cc is True, ch is False
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
            flag = " [other_valid_relation]" if (oh and not ch) else ""
            print(f"{cat:24} {pop:9} {clean['pair_id']}{flag}", flush=True)
        print(f"\ncontrolled: consistent {cons}/{len(pairs)}, clean {clean_ok}, hard {hard_ok}")
        print("categories:", cats)

    print("\n--- blind 60 ---")
    btp = btn = bfp = bfn = 0
    for line in (root / "docs" / "eval_hard_negative_prevalence.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        key = f"blind|{r['id']}"
        if key in done and "mark" in done[key]:
            mark = done[key]["mark"]
        else:
            rec = run_case(key, r["text"])
            tr = to_triples(rec["raw"])
            pred = any_edge(tr) if tr is not None else None
            gold_pos = r.get("provides_class") in ("clean_positive", "ambiguous_positive")
            mark = "TP" if pred and gold_pos else "TN" if pred is False and not gold_pos \
                else "FP" if pred else "FN" if pred is False else "?"
            rec.update({"mark": mark, "cls": r.get("provides_class")})
            fh.write(json.dumps({"key": key + "|scored", "mark": mark}, ensure_ascii=False) + "\n")
        print(mark, r.get("provides_class"), '|', r["text"][:60], flush=True)
        btp += mark == "TP"
        btn += mark == "TN"
        bfp += mark == "FP"
        bfn += mark == "FN"
    print(f"\nblind: tp={btp} tn={btn} fp={bfp} fn={bfn}")
    fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
