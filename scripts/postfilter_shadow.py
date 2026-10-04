"""PostFilter shadow v1: compute-only, never filters. See docs/postfilter_shadow_v1.md."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from trackb_production import normalize, link
# Trigger licensing: (lemma, construction) -> canonical relation.
# Only semantically vetted constructions, never a bare word list.
# "benefactive-for": X Ved NP for Y with performed action asserts assistance;
# note repair/carry/paint alone license nothing outside this construction.
LICENSED_TRIGGERS = [
    ("help", None), ("support", None), ("encourag", None), ("guid", None),
    ("mentor", None), ("advocat", None), ("assist", None), ("praise", None),
    ("acknowledg", None), ("cheer", None), ("urg", None),
    ("carr", "benefactive-for"), ("move", "benefactive-for"),
    ("paint", "benefactive-for"), ("repair", "benefactive-for"),
]
TRIGGER_LEXEMES = sorted({t[0] for t in LICENSED_TRIGGERS})
SCOPE_CUES = {
    "INTENTIONAL": ["offered to", "planned to", "meant to", "intended to",
                    "wants to", "wishes to", "going to"],
    "QUESTIONED": ["asked if", "asked whether", "?"],
    "REPORTED": ["said ", "reported", "rumored", "alleged", "claimed"],
    "ATTRIBUTED": ["talk of", "talk about", "described ", "spoke of"],
    "CONDITIONAL": ["would help", "would support", "would assist", " if "],
    "HYPOTHETICAL": ["would ", "could ", "might "],
    "CONTRASTIVE_TARGET": ["instead of", "rather than"],
    "DESIDERATIVE": ["hoped", "wished", "desired", "wanted"],
}


NEG = ["never", "not", "no ", "n't", "nobody", "nothing", "nowhere",
       "without", "hardly", "barely"]


def argument_grounding(sentence, subj, obj):
    low = sentence.lower()
    out = {}
    for role, m in (("subject", subj), ("object", obj)):
        idx = low.find(m.lower())
        out[role] = {"span": [idx, idx + len(m)]} if idx >= 0 else None
    out["status"] = "pass" if (out["subject"] and out["object"]) else "fail"
    return out


def trigger_licensing(sentence, subj, obj):
    """Licensed trigger: (lemma, construction) with span, never bare words."""
    low = sentence.lower()
    for lemma, construction in LICENSED_TRIGGERS:
        m = re.search(lemma, low)
        if not m:
            continue
        if construction == "benefactive-for":
            # X Ved NP for Y with performed action: require "for <object>"
            # after the trigger; otherwise the verb licenses nothing.
            tail = low[m.end():]
            if not re.search(r"\bfor\s+" + re.escape(obj.lower()), tail):
                continue
        return {"status": "pass", "lemma": lemma, "construction": construction,
                "span": [m.start(), m.start() + len(lemma)]}
    return {"status": "fail", "reason": "no_licensed_trigger"}


def anchor(sentence, subj, obj):
    low = sentence.lower()
    out = {}
    for role, m in (("subject", subj), ("object", obj)):
        idx = low.find(m.lower())
        out[role] = {"span": [idx, idx + len(m)]} if idx >= 0 else None
    trig = trigger_licensing(sentence, subj, obj)
    out["trigger"] = trig if trig["status"] == "pass" else None
    out["status"] = "pass" if (out["subject"] and out["object"]
                               and out["trigger"]) else "fail"
    return out


def role(sentence, subj, obj, anch):
    if anch["status"] != "pass":
        return {"status": "fail", "reason": "no_anchor"}
    order = anch["subject"]["span"][0] <= anch["trigger"]["span"][0] <= \
        anch["object"]["span"][0]
    return {"status": "pass" if order else "fail",
            "reason": None if order else "order_violation"}


def scope(sentence):
    low = sentence.lower()
    for reason, cues in SCOPE_CUES.items():
        if any(c in low for c in cues):
            return {"status": "fail", "reason": reason}
    if any(re.search(r"\b" + n.strip() + r"\b", low) for n in NEG):
        return {"status": "fail", "reason": "NEGATED"}
    return {"status": "pass", "reason": None}


def nli_shadow(sentence, subj, obj):
    from src.extraction.verifier import _get_verifier
    import numpy as np
    model, entail_idx, contra_idx = _get_verifier()
    hyp = f"{subj} provides support to {obj}."
    logits = model.predict([[sentence, hyp]], convert_to_numpy=True)
    row = np.atleast_2d(logits)[0]
    labels = ["contradiction", "neutral", "entailment"]
    order = sorted(range(3), key=lambda i: -row[i])
    best = order[0]
    id2label = {0: "contradiction", 1: "neutral", 2: "entailment"}
    try:
        from src.extraction.verifier import _VERIFIER_MODEL  # noqa
        id2 = {int(k): str(v).lower()
               for k, v in model.model.config.id2label.items()}
        label = id2label.get(best, id2.get(best, "?"))
    except Exception:
        label = ["contradiction", "neutral", "entailment"][best] \
            if len(row) == 3 else "entailment" if best == entail_idx else "other"
    return {"label": label,
            "margin": round(float(row[entail_idx]) - float(row[contra_idx]), 4)}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    recs = [json.loads(l) for l in
            (ROOT / "docs" / "trackb_two_stage.jsonl").read_text().splitlines() if l.strip()]
    norms = set()
    for r in recs:
        for t in r.get("triples", []):
            norms.add(normalize(t["subject"]))
            norms.add(normalize(t["object"]))
    out_path = ROOT / "docs" / "postfilter_shadow_v1.jsonl"
    index = build_sentence_index()
    n = 0
    seen_keys = set()
    with open(out_path, "w", encoding="utf-8") as fh:
        for r in recs:
            for t in r.get("triples", []):
                sent = index.get(r["key"])
                if sent is None:
                    continue
                seen_keys.add(r["key"])
                write_record(fh, r["key"], sent, t["subject"], t["object"],
                             norms, validated=True)
                n += 1
                if args.limit and n >= args.limit:
                    return 0
        # Raw NuExtract candidates on hard sentences (validator rejected them):
        # scope/anchor/role/entity only, marked validated=False.
        from trackb_two_stage import nu_candidates
        for key, sent in index.items():
            if not key.endswith("|hard") or key in seen_keys:
                continue
            try:
                cands = nu_candidates(sent)
            except Exception as e:
                print("candidate fail", key, str(e)[:80], flush=True)
                continue
            for x, y in cands:
                write_record(fh, key, sent, x, y, norms, validated=False)
                n += 1
                print(key, "raw-candidate", x, "->", y, flush=True)
                if args.limit and n >= args.limit:
                    return 0
    print("shadow records:", n)
    return 0


def write_record(fh, key, sent, subj, obj, norms, validated):
    a = anchor(sent, subj, obj)
    arg = argument_grounding(sent, subj, obj)
    trig = trigger_licensing(sent, subj, obj)
    rec = {"key": key, "subject": subj, "object": obj,
           "validated": validated,
           "anchor": a["status"], "anchor_detail": a,
           "argument_grounding": arg["status"],
           "trigger_licensing": trig,
           "role": role(sent, subj, obj, a),
           "scope": scope(sent),
           "entity": link(subj, norms)["status"] + "/" +
                     link(obj, norms)["status"],
           "nli": nli_shadow(sent, subj, obj)}
    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(key, subj, "->", obj, arg["status"], trig.get("lemma", "-"),
          rec["scope"], rec["nli"]["label"], flush=True)
    return rec


def build_sentence_index():
    """key -> sentence for controlled pairs and blind ids."""
    index = {}
    for rel in ["docs/eval_phase_a_expansion_scaled.json",
                "docs/eval_phase_a_expansion_ae1.json",
                "docs/eval_phase_a_expansion_ap2.json",
                "docs/eval_phase_a_expansion_np2.json"]:
        d = json.loads((ROOT / rel).read_text())
        fps = d["pairs"] if "pairs" in d else d.get("controlled_pairs", [])
        by = {}
        for e in fps:
            by.setdefault(e["pair_id"], {})[e["class"]] = e
        for pid, g in by.items():
            if "clean_positive" in g and "hard_negative" in g:
                pop = "expansion"
                index[f"{pop}|{pid}|clean"] = g["clean_positive"]["sentence"]
                index[f"{pop}|{pid}|hard"] = g["hard_negative"]["sentence"]
    v2 = json.loads((ROOT / "docs" / "eval_phase_a_manifest.json").read_text())
    by = {}
    for e in v2["controlled_pairs"]:
        if e.get("construction_family_id") == "nominal_possessive:epistemic":
            by.setdefault(e["pair_id"], {})[e["class"]] = e
    for pid, g in by.items():
        index[f"epistemic|{pid}|clean"] = g["clean_positive"]["sentence"]
        index[f"epistemic|{pid}|hard"] = g["hard_negative"]["sentence"]
    for line in (ROOT / "docs" / "eval_hard_negative_prevalence.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            index[f"blind|{r['id']}"] = r["text"]
    return index


if __name__ == "__main__":
    raise SystemExit(main())
