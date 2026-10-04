"""PostFilter v1 ablation on frozen production annotation (no pipeline change)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from postfilter import judge
from trackb_production import normalize

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    d = json.load(open(ROOT / "docs" / "production_annotation_v1.json"))
    run = [json.loads(l) for l in
           open(ROOT / "docs" / "production_run_v1.jsonl") if l.strip()]
    norms = set()
    for r in run:
        for k in ("subject_mention", "object_mention"):
            if r.get(k):
                norms.add(normalize(r[k]))
    rows = []
    for e in d["entries"]:
        if e["stratum"] != "A_full" or not e["system"]:
            continue
        s = e["system"]
        j = judge(e["text"], s["subject"], s["object"], norms)
        rows.append({"id": e["sentence_id"], "gold": e["provides_relation_present"],
                     "system": s["final"], "filter": j})
        print(e["sentence_id"], s["subject"], "->", s["object"],
              "| gold", e["provides_relation_present"], "| filter", j["final"],
              j.get("by"), j.get("reason", ""), flush=True)
    tp_lost = sum(1 for r in rows if r["gold"] == "yes" and r["filter"]["final"] == "REJECT")
    fp_gone = sum(1 for r in rows if r["gold"] == "no" and r["filter"]["final"] == "REJECT")
    print(f"\nTP lost: {tp_lost}, FP removed: {fp_gone}")
    json.dump({"version": "postfilter_v1_ablation",
               "tp_lost": tp_lost, "fp_removed": fp_gone, "rows": rows},
              open(ROOT / "docs" / "postfilter_v1_ablation.json", "w"), indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
