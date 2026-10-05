"""Fetch a candidate document through the local jina-reader (docker).

Saves the raw snapshot (for sha256 pinning) and reports the v3 mechanical
qualification: >=300 usable sentences + institutional document type from
URL/title metadata. No section gate (removed in v3).
"""
import hashlib
import json
import re
import sys

sys.path.insert(0, "C:/Users/tobs/AppData/Local/Temp/opencode")
sys.path.insert(0, "C:/Users/tobs/.cursor/workspace/sieveon/scripts")
from h2c_test import fetch_h2c
from batch7_qualify import clean

SNAP_DIR = ("C:/Users/tobs/.cursor/workspace/sieveon/docs/"
            "batch7_snapshots/")


def split_sentences(text):
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])", text)
    return [p.strip() for p in parts if p.strip()]


def keep(s):
    toks = s.split()
    return (40 <= len(s) <= 400 and len(toks) >= 6 and s[-1] in ".!?"
            and not re.search(r"[<>{}]", s))


def doc_type_from_metadata(url):
    u = url.lower()
    if any(x in u for x in ("wikipedia", "blog", "news", "facebook",
                            "linkedin", "marketing")):
        return "EXCLUDED_TYPE"
    if ".pdf" in u or "report" in u or "guidance" in u or "standard" in u:
        return "report/standard/guidance/manual"
    return "UNDETERMINED"


def main(url, tag):
    import os
    os.makedirs(SNAP_DIR, exist_ok=True)
    path = "/https://" + url.split("://", 1)[1] if "://" in url else url
    # jina reader OSS takes the target URL as the path
    target = url if url.startswith("http") else "https://" + url
    status, body = fetch_h2c("127.0.0.1", 18080, "/" + target, timeout=600)
    raw = body.decode("utf-8", errors="replace")
    fname = f"{tag}.md"
    with open(SNAP_DIR + fname, "w", encoding="utf-8") as f:
        f.write(raw)
    sha = hashlib.sha256(raw.encode()).hexdigest()
    # strip jina header lines for measurement (keep raw intact for pinning)
    text = re.sub(r"^(Title|URL Source|Published Time|Number of Pages):.*$",
                  "", raw, flags=re.M)
    sents = [s for s in split_sentences(clean(text)) if keep(s)]
    seen, uniq = set(), []
    for s in sents:
        k = s.strip().lower()
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    dt = doc_type_from_metadata(url)
    verdict = ("PASS" if len(uniq) >= 300 and dt != "EXCLUDED_TYPE"
               else "FAIL")
    print(f"{verdict} sents={len(uniq):5d} type={dt} status={status} "
          f"bytes={len(raw)} sha={sha[:16]}")
    print(f"  snapshot: docs/batch7_snapshots/{fname}")
    return {"url": url, "verdict": verdict,
            "usable_sentences": len(uniq), "doc_type": dt,
            "raw_sha256": sha, "snapshot": f"docs/batch7_snapshots/{fname}"}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=1))
