"""Assertion-isolation probe run (frozen protocol 23846d4).

Unchanged validator (trackb_two_stage.validate: same prompt, same retries,
same timeout). No extractor call, no prompt/rule/threshold change. Conditions
and analysis hierarchy come from the frozen material; the pooled/primary/
descriptive contrasts are applied AFTER the full run only.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trackb_two_stage import validate

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    mat = json.loads(
        (ROOT / "docs" / "assertion_isolation_material_v1.json").read_text(
            encoding="utf-8"))
    out = {"version": "assertion_isolation_results_v1",
           "protocol": "docs/assertion_isolation_probe_v1.json",
           "material": "docs/assertion_isolation_material_v1.json",
           "stage": "assertion only (unchanged validate(); extractor not re-run)",
           "analysis_rule": "no intermediate interpretation; full run first",
           "items": []}
    rec_path = ROOT / "docs" / "assertion_isolation_results_v1.jsonl"
    done = set()
    if rec_path.exists():
        for line in rec_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["item_id"])
    fh = open(rec_path, "a", encoding="utf-8")
    for n, it in enumerate(mat["items"], 1):
        if it["item_id"] in done:
            continue
        x, _, y = it["gold_triple"]
        supported, raw = validate(it["sentence"], x, y)
        rec = {"item_id": it["item_id"], "sentence": it["sentence"],
               "gold_triple": it["gold_triple"],
               "condition": it["condition"],
               "semantic_subtype": it["semantic_subtype"],
               "source_probe": it["source_probe"],
               "extractor_gold_match": it["extractor_gold_match"],
               "is_boundary_case": it["is_boundary_case"],
               "subtype_rationale": it["subtype_rationale"],
               "validator_result": "ACCEPT" if supported else "REJECT",
               "validator_reason": raw[:200]}
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        out["items"].append(rec)
        print(f"[{n}/{len(mat['items'])}] {it['item_id']:22s} "
              f"{it['condition']:20s} {rec['validator_result']}", flush=True)
    fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())