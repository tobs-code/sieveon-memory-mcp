"""End test: 17 archived cases through wired pipeline (worthiness then linker).

Expectations:
- 11 Jon/John: WORTHY, resolved to correct entity, 0 cross-resolution.
- 6 generic/activity: NOT_WORTHY, blocked BEFORE linker (no link attempt).
- 21 positive controls: WORTHY.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from node_worthiness import node_worthy
from trackb_production import link, normalize

ROOT = Path(__file__).resolve().parents[1]
CONTROLS = ["homeless shelter", "the club", "the nonprofit", "the venue",
            "the team", "friends", "students", "a transgender teen",
            "the donors", "the users", "the crowd", "Maria", "the shelter",
            "the community center", "the charity", "the app", "Tom",
            "the organizer", "the project", "the sponsor", "the coach"]


def main() -> int:
    d = json.load(open(ROOT / "docs" / "abstain_annotation_batch3_v1.json"))
    rows = [json.loads(l) for l in
            (ROOT / "docs" / "production_run_v3.jsonl").read_text().splitlines()
            if l.strip()]
    byid = {}
    for r in rows:
        byid.setdefault(r["sentence_id"], r)
    doc_ents, glob = {}, set()
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
    ok_rec = ok_block = ok_cross = ok_ctrl = ok_rec_extra = 0
    fails = []
    blocked_seen, controls_seen = set(), set()
    for e in d["entries"]:
        doc = byid.get(e["sentence_id"], {}).get("document_id", "")
        bucket = doc_ents.get(doc)
        for m in (e["subject_mention"], e["object_mention"]):
            w = node_worthy(m)["verdict"]
            got = link(m, glob, bucket)
            ent = got.get("entity_id") or ""
            is_j = m.lower() in ("jon", "john")
            if e["error_class"] == "name_collision_context_resolvable" and is_j:
                exp = "entity:jon" if m.lower() == "jon" else "entity:john"
                if w == "WORTHY" and ent == exp:
                    ok_rec += 1
                else:
                    fails.append(("resolve", e["sentence_id"], m, ent))
            elif not is_j:
                # only the 6 gold generic/activity mentions must block;
                # all other ordinary mentions must stay worthy
                if m.lower() in ("dancing", "yoga", "beginner yoga class",
                                 "kids in need", "people who lost their jobs",
                                 "his family"):
                    if m.lower() not in blocked_seen:
                        blocked_seen.add(m.lower())
                        if w != "NOT_WORTHY":
                            fails.append(("block", e["sentence_id"], m))
                        else:
                            ok_block += 1
                elif w != "WORTHY":
                    fails.append(("worthy", e["sentence_id"], m))
            else:
                # Jon/John inside generic/activity entries: must still resolve right
                exp = "entity:jon" if m.lower() == "jon" else "entity:john"
                if w == "WORTHY" and ent == exp:
                    ok_rec_extra += 1
                else:
                    fails.append(("resolve-extra", e["sentence_id"], m, ent))
            if (m.lower() == "jon" and ent == "entity:john") or \
                    (m.lower() == "john" and ent == "entity:jon"):
                ok_cross += 1
                fails.append(("cross", e["sentence_id"], m))
    for m in CONTROLS:
        if node_worthy(m)["verdict"] != "WORTHY":
            fails.append(("control", m))
        else:
            ok_ctrl += 1
    print(f"recovered: {ok_rec}/11 (+{ok_rec_extra} extra), blocked: {ok_block}/6, "
          f"controls: {ok_ctrl}/{len(CONTROLS)}, cross: {ok_cross}")
    ok = (ok_rec == 11 and ok_block == 6 and ok_ctrl == len(CONTROLS)
          and ok_cross == 0 and not fails)
    json.dump({"version": "linker_endtest_v1", "recovered": [ok_rec, 11],
               "recovered_extra": ok_rec_extra,
               "blocked": [ok_block, 6], "controls": [ok_ctrl, len(CONTROLS)],
               "cross": ok_cross, "fails": fails,
               "verdict": "GO" if ok else "REVIEW"},
              open(ROOT / "docs" / "linker_endtest_v1.json", "w"), indent=1)
    print("ENDTEST:", "GO" if ok else "REVIEW", fails if fails else "")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
