"""SurrealDB import: pure materialization of ACCEPTED extraction, no semantics.

Reads docs/trackb_production_v11.json (16 ACCEPTED edges + evidence).
Upserts entity nodes, provides edges, separate evidence records.
Post-import integrity checks. ABSTAIN triples are never imported.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv("SURREALDB_URL", "http://127.0.0.1:8000/sql")
NS = os.getenv("SURREALDB_NS", "strata")
DB = os.getenv("SURREALDB_DB", "strata")
AUTH = (os.getenv("SURREALDB_USER", "root"), os.getenv("SURREALDB_PASS", "root"))
VERSION = "trackb_two_stage_v1"


def sql(statements):
    import base64
    body = f"USE NS {NS} DB {DB};\n" + "\n".join(statements)
    body = body.encode()
    req = urllib.request.Request(
        URL, data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": "Basic " + base64.b64encode(
                     f"{AUTH[0]}:{AUTH[1]}".encode()).decode(),
                 "surreal-ns": NS, "surreal-db": DB})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main() -> int:
    prod = json.loads((ROOT / "docs" / "trackb_production_v11.json").read_text())
    edges = prod["edges"]

    def lit(v):
        return json.dumps(v, ensure_ascii=False)

    stmts = ["DEFINE TABLE IF NOT EXISTS trackb_entity SCHEMAFULL;",
             "DEFINE TABLE IF NOT EXISTS trackb_provides SCHEMAFULL;",
             "DEFINE TABLE IF NOT EXISTS trackb_evidence SCHEMAFULL;",
             "DELETE trackb_evidence WHERE pipeline_version = 'trackb_two_stage_v1';",
             "DELETE trackb_provides WHERE pipeline_version = 'trackb_two_stage_v1';"]
    def rid(eid):
        import re
        return "trackb_entity:" + re.sub(r"[^a-z0-9]+", "_", eid.lower()).strip("_")

    for e in edges:
        for eid in (e["subject_id"], e["object_id"]):
            stmts.append(
                f"UPDATE {rid(eid)} CONTENT "
                f"{{name: {lit(eid)}, pipeline_version: {lit(VERSION)}}};")
        stmts.append(
            f"CREATE trackb_provides CONTENT {{subject: {lit(e['subject_id'])}, "
            f"object: {lit(e['object_id'])}, relation: 'provides', "
            f"pipeline_version: {lit(VERSION)}}};")
        for ev in e["evidence"]:
            stmts.append(
                f"CREATE trackb_evidence CONTENT {{subject: {lit(e['subject_id'])}, "
                f"object: {lit(e['object_id'])}, source_key: {lit(ev['source_key'])}, "
                f"subject_mention: {lit(ev['subject_mention'])}, "
                f"object_mention: {lit(ev['object_mention'])}, "
                f"extractor: {lit(ev['extractor'])}, validator: {lit(ev['validator'])}, "
                f"pipeline_version: {lit(VERSION)}}};")
    sql(stmts)
    checks = sql([
        "SELECT count() AS n FROM trackb_provides WHERE pipeline_version = 'trackb_two_stage_v1' GROUP ALL;",
        "SELECT count() AS n FROM trackb_evidence WHERE pipeline_version = 'trackb_two_stage_v1' GROUP ALL;",
        "SELECT subject, object FROM trackb_provides WHERE pipeline_version = 'trackb_two_stage_v1';",
    ])
    n_edges = checks[1]["result"][0]["n"] if checks[1]["result"] else 0
    n_ev = checks[2]["result"][0]["n"] if checks[2]["result"] else 0
    pairs = {(r["subject"], r["object"]) for r in checks[3]["result"]}
    exp_ev = sum(len(e["evidence"]) for e in edges)
    ok = (n_edges == len(edges) and n_ev == exp_ev
          and ("entity:maria", "entity:tim") in pairs
          and ("entity:tim", "entity:maria") in pairs
          and ("entity:john", "entity:community") in pairs)
    print(f"edges: {n_edges}/{len(edges)}, evidence: {n_ev}/{exp_ev}")
    print("direction pair + blind-FP present:", ok)
    print("IMPORT:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
