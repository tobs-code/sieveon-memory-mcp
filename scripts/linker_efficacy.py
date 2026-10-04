"""Linker efficacy test: 17 archived ABSTAIN cases, v1.2 global vs v1.3 doc-scoped.

Same inputs, document context from production_run_v3 document_ids.
Expected: 11 Jon/John resolved under v1.3, 6 stay ABSTAIN, 0 cross-maps.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from trackb_production import link, normalize

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    d = json.load(open(ROOT / "docs" / "abstain_annotation_batch3_v1.json"))
    rows = [json.loads(l) for l in
            (ROOT / "docs" / "production_run_v3.jsonl").read_text().splitlines()
            if l.strip()]
    byid = {}
    for r in rows:
        byid.setdefault(r["sentence_id"], r)
    doc_ents = {}
    glob = set()
    for r in rows:
        doc = r.get("document_id", "")
        bucket = doc_ents.setdefault(doc, set())
        sp = doc.split("/")[-1]
        if sp:
            bucket.add(normalize(sp))
        for k in ("subject_mention", "object_mention"):
            if r.get(k):
                bucket.add(normalize(r[k]))
                glob.add(normalize(r[k]))
    res = {"v12_abstain": 0, "v13_resolved_collision": 0, "v13_abstain": 0,
           "cross": 0, "cases": []}
    for e in d["entries"]:
        doc = byid.get(e["sentence_id"], {}).get("document_id", "")
        for m in (e["subject_mention"], e["object_mention"]):
            old = link(m, glob)
            new = link(m, glob, doc_ents.get(doc))
            ent = new.get("entity_id") or ""
            rec = {"id": e["sentence_id"], "mention": m, "doc": doc.split("/")[-1],
                   "v12": old["status"],
                   "v13": ent if new["status"] == "resolved" else "ABSTAIN",
                   "gold": e["error_class"]}
            res["cases"].append(rec)
            if old["status"] == "ambiguous":
                res["v12_abstain"] += 1
            if e["error_class"] == "name_collision_context_resolvable" and (
                    (m.lower() == "jon" and ent == "entity:jon")
                    or (m.lower() == "john" and ent == "entity:john")):
                res["v13_ok"] = res.get("v13_ok", 0) + 1
            if new["status"] != "resolved":
                res["v13_abstain"] += 1
            ent = (new.get("entity_id") or "")
            if (m.lower() == "jon" and ent == "entity:john") or \
                    (m.lower() == "john" and ent == "entity:jon"):
                res["cross"] += 1
                rec["CROSS"] = True
    print("v12 abstains:", res["v12_abstain"])
    print("v13 resolved collisions:", res["v13_resolved_collision"], "/ 11")
    print("v13 abstains:", res["v13_abstain"])
    print("cross-maps:", res["cross"])
    for c in res["cases"]:
        if c["v12"] == "ambiguous" or "CROSS" in c:
            print(" ", c["id"], repr(c["mention"]), c["v12"], "->",
                  c["v13"] if isinstance(c.get("v13"), str) else c["v13"],
                  c.get("CROSS", ""))
    json.dump({"version": "linker_efficacy_v1", **res},
              open(ROOT / "docs" / "linker_efficacy_v1.json", "w"), indent=1)
    ok = (res.get("v13_ok", 0) == 11 and res["cross"] == 0)
    print("EFFICACY:", "PASS" if ok else "REVIEW")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
