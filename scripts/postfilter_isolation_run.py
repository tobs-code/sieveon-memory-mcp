"""PostFilter isolation replay (protocol postfilter_isolation_v1).

Pure deterministic replay: no model call. L1 is fixed (all material items are
extractor gold matches), L2 is frozen from the assertion-isolation run, L3 is
measured here with the shipped PostFilter v1.1.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from postfilter import judge
from trackb_production import normalize

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    mat = json.loads(
        (ROOT / "docs" / "assertion_isolation_material_v1.json").read_text(
            encoding="utf-8"))
    rows = [json.loads(l) for l in
            (ROOT / "docs" / "assertion_isolation_results_v1.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()]
    verdict = {r["item_id"]: r["validator_result"] for r in rows}
    assert len(rows) == 79 and len(verdict) == 79

    # global normalized pool from the frozen gold triples (documented
    # approximation of the production document-scoped pool)
    pool = set()
    for it in mat["items"]:
        x, _, y = it["gold_triple"]
        if not y:
            continue
        pool.add(normalize(x))
        pool.add(normalize(y))

    out = {"version": "postfilter_isolation_results_v1",
           "protocol": "docs/postfilter_isolation_v1.json",
           "material": "docs/assertion_isolation_material_v1.json",
           "validator_input": "docs/assertion_isolation_results_v1.jsonl",
           "stage": "postfilter v1.1 replay, no model call, shipped rules",
           "linker_pool": "global normalized gold-triple pool (%d spans)" % len(pool),
           "excluded_null_recipient": [
               it["item_id"] for it in mat["items"] if not it["gold_triple"][2]],
           "exclusion_reason": "NULL gold recipient in the frozen material "
               "(validator was asked '... to None'); these are validator-REJECT "
               "and never reach PostFilter in production",
           "items": []}
    for it in mat["items"]:
        x, _, y = it["gold_triple"]
        if not y:
            continue
        pf = judge(it["sentence"], x, y, pool)
        rec = {"item_id": it["item_id"],
               "source_probe": it["source_probe"],
               "condition": it["condition"],
               "semantic_subtype": it["semantic_subtype"],
               "gold_triple": it["gold_triple"],
               "validator_result": verdict[it["item_id"]],
               "postfilter_final": pf["final"],
               "postfilter_by": pf.get("by"),
               "postfilter_reason": pf.get("reason"),
               "postfilter_trigger": (pf.get("trigger") or {}).get("lemma"),
               "reaches_postfilter_in_production":
                   verdict[it["item_id"]] == "ACCEPT"}
        out["items"].append(rec)

    acc = [r for r in out["items"] if r["validator_result"] == "ACCEPT"]
    import collections
    print("validator ACCEPT items:", len(acc))
    print("postfilter outcome:", dict(collections.Counter(
        r["postfilter_final"] for r in acc)))
    print("drop reasons:", dict(collections.Counter(
        (r["postfilter_by"], r["postfilter_reason"])
        for r in acc if r["postfilter_final"] not in ("ACCEPT", "WARN_ACCEPT"))))
    print()
    for r in acc:
        if r["postfilter_final"] not in ("ACCEPT", "WARN_ACCEPT"):
            print("  DROP", r["item_id"], r["postfilter_final"],
                  r["postfilter_by"], r["postfilter_reason"])
    (ROOT / "docs" / "postfilter_isolation_results_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())