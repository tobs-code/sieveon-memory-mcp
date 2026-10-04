"""Document-scoped shadow linking (no production change).

Compares global link() vs doc-scoped link_doc() on the 17 ABSTAIN cases.
Same similarity gate (0.85). Fallback without doc context = global link().
"""

import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from trackb_production import link, normalize

ROOT = Path(__file__).resolve().parents[1]
GATE = 0.85


def build_doc_entities():
    doc_ents = {}
    for line in (ROOT / "docs" / "production_run_v3.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        doc = r.get("document_id", "")
        sp = doc.split("/")[-1] if "/" in doc else ""
        bucket = doc_ents.setdefault(doc, set())
        if sp:
            bucket.add(normalize(sp))
        for k in ("subject_mention", "object_mention"):
            if r.get(k):
                bucket.add(normalize(r[k]))
    return doc_ents


def link_doc(mention, document_id, doc_entities, global_entities):
    n = normalize(mention)
    cands = set(doc_entities.get(document_id, set()))
    if not cands:
        return {"mode": "fallback-global", **link(mention, global_entities)}
    if n in cands:
        return {"mode": "doc", "status": "resolved", "entity_id": f"entity:{n}",
                "normalized": n}
    near = sorted(d for d in cands if d != n
                  and difflib.SequenceMatcher(None, n, d).ratio() > GATE)
    if near:
        return {"mode": "doc", "status": "ambiguous", "normalized": n,
                "collides_with": near}
    return {"mode": "doc", "status": "resolved", "entity_id": f"entity:{n}",
            "normalized": n}


def main() -> int:
    d = json.load(open(ROOT / "docs" / "abstain_annotation_batch3_v1.json"))
    rows = [json.loads(l) for l in
            (ROOT / "docs" / "production_run_v3.jsonl").read_text().splitlines()
            if l.strip()]
    byid = {}
    for r in rows:
        byid.setdefault(r["sentence_id"], r)
    doc_ents = build_doc_entities()
    global_ents = set()
    for ents in doc_ents.values():
        global_ents |= ents
    out = []
    for e in d["entries"]:
        doc = byid.get(e["sentence_id"], {}).get("document_id", "")
        for m in (e["subject_mention"], e["object_mention"]):
            g = link(m, global_ents)
            o = link_doc(m, doc, doc_ents, global_ents)
            out.append({"sentence_id": e["sentence_id"], "mention": m,
                        "document": doc.split("/")[-2] + "/" + doc.split("/")[-1]
                        if "/" in doc else doc,
                        "global": g["status"], "doc": o["status"],
                        "doc_mode": o["mode"],
                        "gold_class": e["error_class"]})
            print(e["sentence_id"], repr(m), "global:", g["status"],
                  "-> doc:", o["status"], "(" + o["mode"] + ")", flush=True)
    # gates
    jon = [o for o in out if o["gold_class"] == "name_collision_context_resolvable"]
    g1 = sum(1 for o in jon if o["doc"] == "resolved")
    bad_map = [o for o in out
               if (o["mention"].lower() == "jon" and "john" in str(o.get("doc", "")))
               or "entity:john" in str(o)]
    cross = [o for o in out if o["mention"].lower() == "jon"
             and o["doc"] == "resolved" and "john" in json.dumps(o).lower()]
    print(f"\ngate1 resolved: {g1}/{len(jon)}")
    print("gate2 (Jon never maps to John):", "CHECK in record")
    json.dump({"version": "linker_shadow_doc_v1", "gates": {"resolved": [g1, len(jon)]},
               "cases": out},
              open(ROOT / "docs" / "linker_shadow_doc_v1.json", "w"), indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
