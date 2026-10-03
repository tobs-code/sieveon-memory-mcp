"""Track B v1.2.1 operational release: baseline manifest + regression runner.

Checks (no model calls, FAIL on deviation, never retune):
- 16 accepted edges / 34 evidence records in SurrealDB
- Jon/John stays ABSTAIN (linker test)
- maria->tim distinct from tim->maria, john->community traceable
- 3 controlled FNs stay FNs (from frozen two-stage records)
- import idempotency: re-import yields identical graph state
"""

import json
import subprocess
import sys
import urllib.request
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NS, DB = "strata", "strata"
AUTH = base64.b64encode(b"root:root").decode()
EXPECTED_FNS = {"AA-1--01", "AA-1--02",
                "nominal_possessive:epistemic--02"}


def sql(s):
    req = urllib.request.Request(
        "http://127.0.0.1:8000/sql",
        data=("USE NS strata DB strata; " + s).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Authorization": "Basic " + AUTH})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def snapshot():
    res = sql("SELECT subject, object FROM trackb_provides "
              "WHERE pipeline_version = 'trackb_two_stage_v1';")[1]["result"]
    ev = sql("SELECT subject, object, source_key FROM trackb_evidence "
             "WHERE pipeline_version = 'trackb_two_stage_v1';")[1]["result"]
    import hashlib
    edges = sorted((r["subject"], r["object"]) for r in res)
    evs = sorted((r["subject"], r["object"], r["source_key"]) for r in ev)
    return {"edges": edges, "evidence": evs,
            "digest": hashlib.sha256(json.dumps([edges, evs]).encode()).hexdigest()}


def main() -> int:
    fails = []

    def check(name, cond, detail=""):
        print(("PASS " if cond else "FAIL ") + name, detail)
        if not cond:
            fails.append(name)

    snap1 = snapshot()
    check("16 edges", len(snap1["edges"]) == 16, str(len(snap1["edges"])))
    check("34 evidence", len(snap1["evidence"]) == 34, str(len(snap1["evidence"])))
    pairs = set(snap1["edges"])
    check("direction maria<->tim", ("entity:maria", "entity:tim") in pairs
          and ("entity:tim", "entity:maria") in pairs)
    check("blind-FP traceable", ("entity:john", "entity:community") in pairs)

    r = subprocess.run([sys.executable, "scripts/trackb_linker_test.py"],
                       capture_output=True, text=True, cwd=str(ROOT))
    check("linker test (Jon ABSTAIN)", r.returncode == 0)

    recs = {}
    for line in (ROOT / "docs" / "trackb_two_stage.jsonl").read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            recs[rec["key"]] = rec
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "scripts"))
    from trackb_full_run import norm
    fn_ok = True
    for pid in EXPECTED_FNS:
        hit = False
        for key, rec in recs.items():
            if pid in key and key.endswith("|clean"):
                for t in rec.get("triples", []):
                    for xp, yp in (("maria", "tim"), ("maria", "nonprofit"),
                                   ("team", "app"), ("coach", "club")):
                        if norm(t.get("subject", "")) == xp and norm(t.get("object", "")) == yp:
                            hit = True
        fn_ok &= not hit
    check("3 controlled FNs stay FN", fn_ok)

    subprocess.run([sys.executable, "scripts/trackb_surreal_import.py"],
                   capture_output=True, cwd=str(ROOT))
    snap2 = snapshot()
    check("idempotent re-import", snap1["digest"] == snap2["digest"],
          snap1["digest"][:16])
    check("no evidence duplication", len(snap2["evidence"]) == 34)

    manifest = {"version": "v1.2.1-operational", "graph_digest": snap2["digest"],
                "edges": len(snap2["edges"]), "evidence": len(snap2["evidence"]),
                "extraction": "trackb_two_stage_v1", "linking": "v1.2",
                "import_commit": "f514d19", "abstains": 1,
                "fails": fails}
    (ROOT / "docs" / "trackb_baseline_v121.json").write_text(json.dumps(manifest, indent=2))
    print("BASELINE:", "GREEN" if not fails else f"RED {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
