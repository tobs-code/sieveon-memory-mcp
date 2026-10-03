"""Track B two-stage v1: NuExtract3 candidates + stepfun assertion validator.

Stage 1 asks only WHICH pairs are candidates (no assertion question).
Stage 2 asks per candidate: does the sentence assert X provides Y?
Output: {"supported": true/false}. Provenance recorded per triple.
No thresholds. Resume-capable via docs/trackb_two_stage.jsonl.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trackb_full_run import load_pairs, norm

ROOT = Path(__file__).resolve().parents[1]
NU_MODEL = "numind/nuextract3:q4_k_m"
NU_URL = "http://localhost:11434/api/chat"
NU_TEMPLATE = {"support_relations": [{"provider": "verbatim-string",
                                      "receiver": "verbatim-string"}]}
KILO_URL = "https://api.kilo.ai/api/gateway/chat/completions"
KILO_MODEL = "stepfun/step-3.7-flash:free"

VALIDATOR_PROMPT = """Decide one binary question about the sentence below.
Sentence: %s
Question: Does this sentence assert that %s provides support, help, funding or encouragement to %s?
Consider assertions only: offers, plans, intentions, wishes, questions, rumored/reported/alleged support, or encouragement directed at someone else do NOT count.
Reply with ONLY this JSON: {"supported": true} or {"supported": false}"""


def kilo_key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("KILO_API_KEY="):
            return line.split("=", 1)[1].strip()
    return os.environ.get("KILO_API_KEY", "")


def nu_candidates(sentence: str):
    body = json.dumps({
        "model": NU_MODEL, "stream": False, "think": False,
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 256},
        "messages": [
            {"role": "template", "content": json.dumps(NU_TEMPLATE)},
            {"role": "user", "content": sentence},
        ]}).encode()
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(NU_URL, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                raw = json.loads(r.read())["message"]["content"]
            start, end = raw.index("{"), raw.rindex("}") + 1
            obj = json.loads(raw[start:end])
            out = []
            for rel in obj.get("support_relations", []) or []:
                if isinstance(rel, dict) and rel.get("provider") and rel.get("receiver"):
                    out.append((rel["provider"], rel["receiver"]))
            return out
        except Exception as e:
            last = e
    raise RuntimeError(f"nuextract failed 3x: {last}")


def validate(sentence: str, x: str, y: str):
    body = json.dumps({"model": KILO_MODEL, "stream": False, "temperature": 0,
                       "messages": [{"role": "user",
                                     "content": VALIDATOR_PROMPT % (sentence, x, y)}]}).encode()
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(KILO_URL, data=body,
                                         headers={"Authorization": f"Bearer {kilo_key()}",
                                                  "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = json.loads(r.read())["choices"][0]["message"]["content"]
            start, end = raw.index("{"), raw.rindex("}") + 1
            return bool(json.loads(raw[start:end]).get("supported")), raw[:200]
        except Exception as e:
            last = e
    raise RuntimeError(f"validator failed 3x: {last}")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--blind-only", action="store_true")
    args = ap.parse_args()
    rec_path = ROOT / "docs" / "trackb_two_stage.jsonl"
    done = {}
    if rec_path.exists():
        for line in rec_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["key"]] = r
    fh = open(rec_path, "a", encoding="utf-8")

    def validated_triples(key, sentence):
        if key in done:
            return done[key]["triples"]
        cands = nu_candidates(sentence)
        triples = []
        for x, y in cands:
            sup, _raw = validate(sentence, x, y)
            if sup:
                triples.append({"subject": x, "relation": "provides", "object": y,
                                "candidate_source": "nuextract3",
                                "validator": "stepfun",
                                "assertion": "supported"})
        rec = {"key": key, "n_candidates": len(cands), "triples": triples}
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        done[key] = rec
        return triples

    def edge(tr, x, y):
        return any(norm(t["subject"]) == norm(x) and norm(t["object"]) == norm(y) for t in tr)

    if not args.blind_only:
        pairs = load_pairs()
        cons = tp = fp = fn = 0
        cats = {}
        for pop, clean, hard in pairs:
            xe, ye = clean["entities"]
            tc = validated_triples(f"{pop}|{clean['pair_id']}|clean", clean["sentence"])
            th = validated_triples(f"{pop}|{clean['pair_id']}|hard", hard["sentence"])
            c_ok, h_ok = edge(tc, xe, ye), not edge(th, xe, ye)
            tp += c_ok
            fn += not c_ok
            fp += edge(th, xe, ye)
            if c_ok and h_ok:
                cat, cons = "CONSISTENT", cons + 1
            elif not h_ok:
                cat = "HARD_FP"
            elif not c_ok:
                cat = "CLEAN_MISS"
            else:
                cat = "MIXED"
            cats[cat] = cats.get(cat, 0) + 1
            print(f"{cat:12} {pop:9} {clean['pair_id']}", flush=True)
        print(f"\ncontrolled: consistent {cons}/{len(pairs)} tp={tp} fp={fp} fn={fn}")
        print("categories:", cats)

    print("\n--- blind 60 ---")
    btp = btn = bfp = bfn = 0
    for line in (ROOT / "docs" / "eval_hard_negative_prevalence.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        tr = validated_triples(f"blind|{r['id']}", r["text"])
        pred = bool(tr)
        gold_pos = r.get("provides_class") in ("clean_positive", "ambiguous_positive")
        mark = "TP" if pred and gold_pos else "TN" if not pred and not gold_pos \
            else "FP" if pred else "FN"
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
