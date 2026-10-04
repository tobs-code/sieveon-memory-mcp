"""Trigger-Licensing v2 hypothesis (shadow only, no pipeline change).

Three constructions with bound roles:
- ACTIVE advise: advis* + direct object Y, subject X agentive.
- ACTIVE roots_for: roots for + object Y.
- NOMINAL_TRANSFER advice: got/received/obtained + advice (+ from X);
  recipient = clause subject, source = explicit or resolved entity.
NOT included: built-website-for (separate artifact_provision family).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from trackb_production import normalize

ROOT = Path(__file__).resolve().parents[1]


def match_advise(sent, subj, obj):
    low = sent.lower()
    m = re.search(r"\b(advises|advised|advise|advising)\b", low)
    if not m:
        return None
    if low.find(subj.lower()) < m.start() < low.find(obj.lower()):
        return {"construction": "ACTIVE_advise", "lemma": m.group(1)}
    return None


def match_roots_for(sent, subj, obj):
    low = sent.lower()
    m = re.search(r"\broots?\s+for\b", low)
    if not m:
        return None
    if low.find(subj.lower()) < m.start() < low.find(obj.lower()):
        return {"construction": "ACTIVE_roots_for", "lemma": "roots for"}
    return None


def match_advice_transfer(sent, subj, obj):
    low = sent.lower()
    m = re.search(r"\b(got|received|obtained)\b[^.]{0,40}\badvice\b", low)
    if not m:
        return None
    fm = re.search(r"\bfrom\s+([a-z][a-z\s]*?)(?:,|\.| and |$)", low[m.start():])
    source = fm.group(1).strip() if fm else None
    return {"construction": "NOMINAL_TRANSFER_advice",
            "source": source, "recipient": obj}


def classify(sent, subj, obj):
    for fn in (match_advise, match_roots_for, match_advice_transfer):
        hit = fn(sent, subj, obj)
        if hit:
            return {"v2": "LICENSED", **hit}
    return {"v2": "UNKNOWN"}


def main() -> int:
    tested = [
        ("Gina advises Jon to stay passionate, focused, resilient, and open to learning fo",
         "Gina", "Jon"),
        ("Gina roots for Jon to keep going and make his dreams a reality, even when facing",
         "Gina", "Jon"),
        ("Gina met some investors and got good advice at a recent networking event.",
         "investors", "Gina"),
    ]
    # full warn set from batch 2
    rows = [json.loads(l) for l in open(ROOT / "docs" / "production_run_v2.jsonl")
            if l.strip()]
    cases = [(r["text"], r["subject_mention"], r["object_mention"])
             for r in rows if (r.get("postfilter_v1") or {}).get("final") == "WARN_ACCEPT"]
    for prefix in ("TEST", "WARN"):
        pass
    print("== hypothesis cases ==")
    for sent, x, y in tested:
        print(classify(sent, x, y), "|", sent[:50])
    print("== all batch2 warns ==")
    licensed, unknown = [], []
    for sent, x, y in cases:
        c = classify(sent, x, y)
        (licensed if c["v2"] == "LICENSED" else unknown).append((sent[:60], x, y, c))
    print(f"LICENSED: {len(licensed)}, UNKNOWN: {len(unknown)}")
    for s, x, y, c in licensed:
        print("  L", c.get("construction"), "|", x, "->", y, "|", s)
    json.dump({"version": "trigger_licensing_v2_shadow",
               "licensed": [{"s": s, "x": x, "y": y, "c": c} for s, x, y, c in licensed],
               "unknown_n": len(unknown)},
              open(ROOT / "docs" / "trigger_licensing_v2_shadow.json", "w"), indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
