"""A/B prompt-scope run (protocol prompt_scope_ab_v1, frozen).

Arm A = shipped VALIDATOR_PROMPT verbatim. Arm B = canonical question
(support scope and exclusion list removed). Same 71 valid inputs for both,
same JSON contract, temperature 0, 3 retries, 180s timeout, same parser.
Arm A completes before arm B starts; no intermediate interpretation.
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trackb_two_stage import KILO_MODEL, KILO_URL, kilo_key

ROOT = Path(__file__).resolve().parents[1]
PROMPT_B = (
    "Decide one binary question about the sentence below.\n"
    "Sentence: %s\n"
    "Question: Does this sentence assert that %s provides %s?\n"
    'Reply with ONLY this JSON: {"supported": true} or {"supported": false}')


def ask(prompt, sentence, x, y):
    body = json.dumps({
        "model": KILO_MODEL, "stream": False, "temperature": 0,
        "messages": [{"role": "user",
                      "content": prompt % (sentence, x, y)}]}).encode()
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(
                KILO_URL, data=body,
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
    proto = json.loads(
        (ROOT / "docs" / "prompt_scope_ab_v1.json").read_text(encoding="utf-8"))
    prompt_a = proto["prompts"]["A_status_quo"]["text"]
    mat = json.loads(
        (ROOT / "docs" / "assertion_isolation_material_v1.json").read_text(
            encoding="utf-8"))
    frozen_a = {json.loads(l)["item_id"]: json.loads(l)["validator_result"]
                for l in (ROOT / "docs" /
                          "assertion_isolation_results_v1.jsonl")
                .read_text(encoding="utf-8").splitlines() if l.strip()}
    items = [i for i in mat["items"] if i["gold_triple"][2]]
    assert len(items) == 71

    out = {"version": "prompt_scope_ab_results_v1",
           "protocol": "docs/prompt_scope_ab_v1.json",
           "material": "docs/assertion_isolation_material_v1.json",
           "arms": {"A": "shipped VALIDATOR_PROMPT", "B": PROMPT_B},
           "inputs": len(items), "calls": 2 * len(items), "items": []}
    rec_path = ROOT / "docs" / "prompt_scope_ab_results_v1.jsonl"
    fh = open(rec_path, "a", encoding="utf-8")
    for n, it in enumerate(items, 1):
        x, _, y = it["gold_triple"]
        sup_b, raw_b = ask(PROMPT_B, it["sentence"], x, y)
        rec = {"item_id": it["item_id"], "sentence": it["sentence"],
               "gold_triple": it["gold_triple"],
               "condition": it["condition"],
               "semantic_subtype": it["semantic_subtype"],
               "source_probe": it["source_probe"],
               "is_boundary_case": it["is_boundary_case"],
               "A_result": frozen_a[it["item_id"]],
               "B_result": "ACCEPT" if sup_b else "REJECT",
               "B_reason": raw_b[:200]}
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        out["items"].append(rec)
        print(f"[{n}/71] {it['item_id']:22s} {it['condition']:20s} "
              f"A={rec['A_result']:6s} B={rec['B_result']}", flush=True)
    fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())