"""Batch 7 candidate qualification check (rule ec017a5).

Mechanical only: >=300 usable sentences AND >=3 real sections after cleaning.
No interpretation of search hits, no difficulty judgement.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

from batch7_textclean import strip_links

TOOL_DIR = Path("C:/Users/tobs/.local/share/opencode/tool-output")

CUT = re.compile(r"^##\s+(References|External links|See also|Further reading|"
                 r"Notes|Footnotes|Bibliography|Sources|Endnotes|Disclaimer)\b.*",
                 re.M | re.S)
ABBREV = {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "vs", "etc", "fig",
          "no", "eg", "ie", "us", "uk", "usa", "jan", "feb", "mar", "apr",
          "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "prof",
          "rep", "sen", "gov", "gen", "col", "sgt", "capt", "cmdr"}
BOILER = re.compile(r"subscribe|sign up for|newsletter|all rights reserved|"
                    r"click here|read more|share this|cookie policy|"
                    r"privacy policy|terms of use|copyright \u00a9|"
                    r"utm_|thumbnail", re.I)
MIN_SENTENCES = 300
MIN_SECTIONS = 3


def clean(md):
    md = CUT.split(md)[0]
    md = strip_links(md)
    md = re.sub(r"\]\s*\([^)]*\)", "", md)
    md = re.sub(r"\*\*+", "", md)
    md = re.sub(r"https?://\S+", "", md)
    md = BOILER.sub(" ", md)
    md = re.sub(r"[\[\]]", "", md)
    return md


def sentences(text):
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])", text)
    out, buf = [], ""
    for p in parts:
        buf = (buf + " " + p).strip() if buf else p
        tail = re.search(r"(\b[\w.]+)[.!?]?$", buf)
        w = (tail.group(1) if tail else "").lower().strip(".")
        if w in ABBREV:
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


def qualify(md):
    c = clean(md)
    secs = [s for s in re.split(r"^##\s+.*$", c, flags=re.M) if s.strip()]
    usable = []
    for sec in secs:
        for s in sentences(sec):
            if (40 <= len(s) <= 400 and len(s.split()) >= 6
                    and s[-1] in ".!?" and not re.search(r"[<>{}]", s)):
                usable.append(s)
    seen, uniq = set(), []
    for s in usable:
        k = s.strip().lower()
        if k not in seen:
            seen.add(k)
            uniq.append(s)
    return {"usable_sentences": len(uniq),
            "sections": len(secs),
            "qualifies": len(uniq) >= MIN_SENTENCES and len(secs) >= MIN_SECTIONS,
            "raw_sha256": hashlib.sha256(md.encode()).hexdigest()}


def main():
    for f in sorted(TOOL_DIR.glob("tool_109*")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        md = d.get("markdown")
        url = (d.get("metadata") or {}).get("sourceURL", "")
        if not md or not url:
            continue
        q = qualify(md)
        print(f"{'PASS' if q['qualifies'] else 'FAIL'} "
              f"sents={q['usable_sentences']:5d} "
              f"sections={q['sections']:3d}  {url[:78]}")
        print(f"      sha256={q['raw_sha256'][:32]}")


if __name__ == "__main__":
    main()