"""Track B production hardening v1.1: normalization, linking, dedup, gates.

Layers text-level extraction (from frozen two-stage records) from canonical
graph edges. No new model calls. Same frozen prompts by construction.
"""

import difflib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STOP = {"the", "a", "an"}


def normalize(mention: str) -> str:
    s = mention.strip().lower()
    s = re.sub(r"^(the|a|an)\s+", "", s)
    s = re.sub(r"['\u2019]s$", "", s)
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def load_triples():
    recs = {}
    for line in (ROOT / "docs" / "trackb_two_stage.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            recs[r["key"]] = r
    return recs


def link(mention: str, all_norms: set, doc_norms: set | None = None):
    """Link a mention. v1.3: optional document-scoped candidate set.

    Document scope restricts the candidate pool; the similarity mechanism
    (0.85 gate) is unchanged. Without doc context (doc_norms None) the
    behavior is exactly the legacy global link. Document scope never
    auto-resolves: exact match or same gate, never looser.
    """
    n = normalize(mention)
    pool = set(doc_norms) if doc_norms else set(all_norms)
    if n in pool:
        return {"entity_id": f"entity:{n}", "status": "resolved",
                "normalized": n, "scope": "doc" if doc_norms else "global"}
    near = sorted({m for m in pool if m != n
                   and difflib.SequenceMatcher(None, n, m).ratio() > 0.85})
    if near:
        return {"entity_id": None, "status": "ambiguous",
                "collides_with": near, "normalized": n,
                "scope": "doc" if doc_norms else "global"}
    return {"entity_id": f"entity:{n}", "status": "resolved", "normalized": n,
            "scope": "doc" if doc_norms else "global"}


def main() -> int:
    recs = load_triples()
    with_norms = set()
    items = []
    for key, r in recs.items():
        for t in r.get("triples", []):
            with_norms.add(normalize(t["subject"]))
            with_norms.add(normalize(t["object"]))
            items.append((key, t))
    edges, abstains = {}, []
    for key, t in items:
        s_link = link(t["subject"], with_norms)
        o_link = link(t["object"], with_norms)
        status = "ACCEPT" if (s_link["status"] == "resolved"
                              and o_link["status"] == "resolved") else "ABSTAIN"
        sent = key
        if status == "ACCEPT":
            ek = (s_link["entity_id"], "provides", o_link["entity_id"])
            edges.setdefault(ek, {"subject_id": ek[0], "relation": "provides",
                                  "object_id": ek[2], "evidence": []})
            edges[ek]["evidence"].append({"source_key": key,
                                         "subject_mention": t["subject"],
                                         "object_mention": t["object"],
                                         "extractor": t["candidate_source"],
                                         "validator": t["validator"],
                                         "status": t["assertion"],
                                         "pipeline_version": "trackb_two_stage_v1"})
        else:
            abstains.append({"key": key, "subject": t["subject"], "object": t["object"],
                             "reason": "ambiguous_link",
                             "subject_link": s_link, "object_link": o_link})
    out = {"version": "production_hardening_v1.1",
           "n_edges": len(edges), "n_abstains": len(abstains),
           "edges": list(edges.values()), "abstains": abstains}
    (ROOT / "docs" / "trackb_production_v11.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False))
    print(f"edges: {len(edges)}, abstains: {len(abstains)}")
    amb = [a for a in abstains if a["reason"] == "ambiguous_link"]
    print("ambiguous samples:", [(a["subject"], a["object"]) for a in amb[:5]])
    # semantic baseline check: controlled pair consistency from records
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
