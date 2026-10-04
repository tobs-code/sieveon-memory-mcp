"""Production corpus v1 run: frozen v1.2.1 pipeline, full provenance, no changes."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trackb_two_stage import nu_candidates, validate
from trackb_production import normalize, link
from postfilter import judge as postfilter_judge
from node_worthiness import node_worthy

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="docs/production_corpus_v1.json")
    ap.add_argument("--run", default="docs/production_run_v1.jsonl")
    ap.add_argument("--cache", default="docs/production_cands_v1.jsonl")
    args = ap.parse_args()
    corpus = json.loads((ROOT / args.corpus).read_text())
    rec_path = ROOT / args.run
    done = set()
    if rec_path.exists():
        for line in rec_path.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["sentence_id"])
    fh = open(rec_path, "a", encoding="utf-8")
    cache_path = ROOT / args.cache
    cached = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                cached[r["sentence_id"]] = r["candidates"]
    cands_by_id = {}
    with open(cache_path, "a", encoding="utf-8") as ch:
        for s in corpus["sentences"]:
            if s["sentence_id"] not in cached:
                c = nu_candidates(s["text"])
                ch.write(json.dumps({"sentence_id": s["sentence_id"],
                                     "candidates": c}) + "\n")
                ch.flush()
                cached[s["sentence_id"]] = c
            cands_by_id[s["sentence_id"]] = cached[s["sentence_id"]]
    norms = set()
    doc_norms = {}
    for s in corpus["sentences"]:
        bucket = doc_norms.setdefault(s["document_id"], set())
        sp = s["document_id"].split("/")[-1]
        if sp:
            bucket.add(normalize(sp))
        for x, y in cands_by_id.get(s["sentence_id"], []):
            norms.add(normalize(x))
            norms.add(normalize(y))
            bucket.add(normalize(x))
            bucket.add(normalize(y))
    n_new = 0
    for s in corpus["sentences"]:
        if s["sentence_id"] in done:
            continue
        cands = cands_by_id[s["sentence_id"]]
        doc_bucket = doc_norms.get(s["document_id"])
        for x, y in cands:
            sup, _ = validate(s["text"], x, y)
            nw_s, nw_o = node_worthy(x), node_worthy(y)
            sl, ol = link(x, norms, doc_bucket), link(y, norms, doc_bucket)
            if nw_s["verdict"] != "WORTHY" or nw_o["verdict"] != "WORTHY":
                final = "ABSTAIN"
                node_reason = f"{nw_s.get('reason', '')}/{nw_o.get('reason', '')}"
            else:
                node_reason = None
                final = "ACCEPT" if (sup and sl["status"] == "resolved"
                                     and ol["status"] == "resolved") else \
                    "ABSTAIN" if sup else "REJECT"
            pf = postfilter_judge(s["text"], x, y, norms)
            fh.write(json.dumps({
                "document_id": s["document_id"], "sentence_id": s["sentence_id"],
                "text": s["text"], "subject_mention": x, "object_mention": y,
                "candidate_status": "candidate", "assertion_status": "supported" if sup else "not_supported",
                "link_status": f"{sl['status']}/{ol['status']}", "final_status": final,
                "canonical_subject": sl.get("entity_id"), "canonical_object": ol.get("entity_id"),
                "pipeline_version": "trackb_two_stage_v1", "evidence": s["sentence_id"],
                "node_worthy": f"{nw_s['verdict']}/{nw_o['verdict']}",
                "node_reason": node_reason,
                "postfilter_v1": {"final": pf["final"], "by": pf.get("by"),
                                  "reason": pf.get("reason"),
                                  "trigger": (pf.get("trigger") or {}).get("lemma")},
            }, ensure_ascii=False) + "\n")
            fh.flush()
        if not cands:
            fh.write(json.dumps({"document_id": s["document_id"], "sentence_id": s["sentence_id"],
                                 "text": s["text"], "candidate_status": "no_candidate",
                                 "final_status": "REJECT",
                                 "pipeline_version": "trackb_two_stage_v1"},
                                ensure_ascii=False) + "\n")
            fh.flush()
        n_new += 1
        print(s["sentence_id"], "cands:", len(cands), flush=True)
    print("new sentences processed:", n_new)
    fh.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
