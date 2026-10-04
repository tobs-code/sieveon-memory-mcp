"""Batch 7 corpus builder (source rule a2fcb33, fetch log batch7_fetch_log_v1).

Section-wise sampling: clean text, split into top-level sections, drop
structural sections, then apply the batch-6 stride formula PER SECTION.
No per-document sentence cap and no keyword criterion. Mechanical filters only.
Corpus digest is computed before any pipeline run.
"""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAP_DIR = Path("C:/Users/tobs/.local/share/opencode/tool-output")

CUT_SECTIONS = re.compile(
    r"^##\s+(References|External links|See also|Further reading|Notes|"
    r"Footnotes|Bibliography|Sources|Endnotes|Citations|Contributors|"
    r"Acknowledgements|Disclaimer|References and further reading)\b.*",
    re.M | re.S)
BOILER = re.compile(
    r"wikimedia|donor privacy|benefactors@|tax-deductible|jump to content|"
    r"\\|for other uses|utm_|thumbnail|main article:|from wikipedia, the free "
    r"encyclopedia|help fix the gap|for .*?, see |^\s*cookie|"
    r"subscribe|sign up for|newsletter|all rights reserved|"
    r"click here|read more|share this|cookie policy|privacy policy|"
    r"terms of (use|service)|copyright \u00a9", re.I | re.M)

ABBREV = {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "vs", "etc",
          "fig", "no", "eg", "ie", "us", "uk", "usa", "jan", "feb",
          "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
          "nov", "dec", "prof", "rep", "sen", "gov", "gen", "col",
          "sgt", "capt", "cmdr", "ave", "blvd", "rd", "mt"}

MIN_SENTENCES_PER_SECTION = 3
MIN_SECTION_SENTENCES = 2
MIN_DOC_SENTENCES = 1200


def clean(md: str) -> str:
    md = CUT_SECTIONS.split(md)[0]
    link = (r"!?\[((?:[^\[\]]|\([^()]*\))*)"
            r"\]\s*\((?:[^()\"]|\([^()]*\)|\"[^\"]*\")*\)")
    for _ in range(3):
        md = re.sub(link, r"\1", md)
    md = re.sub(r"\]\s*\([^)]*\)", "", md)
    md = re.sub(r"!\s*\(\s*", "", md)
    md = re.sub(r"\(\s*\)", "", md)
    md = re.sub(r"\*\*+", "", md)
    md = re.sub(r"^\s*\|.*\|\s*$", "", md, flags=re.M)
    md = re.sub(r"^#{1,6}\s+.*$", "", md, flags=re.M)
    md = re.sub(r"https?://\S+", "", md)
    md = BOILER.sub(" ", md)
    md = re.sub(r"[\[\]]", "", md)
    return md


def split_sentences(text: str):
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])", text)
    out, buf = [], ""
    for p in parts:
        buf = (buf + " " + p).strip() if buf else p
        tail = re.search(r"(\b[\w.]+)[.!?]?$", buf)
        word = (tail.group(1) if tail else "").lower().strip(".")
        if word in ABBREV:
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return [s.strip() for s in out if s.strip()]


def sections(md: str):
    """Split on top-level headings, preserving document order."""
    md = CUT_SECTIONS.split(md)[0]
    parts = re.split(r"^##\s+.*$", md, flags=re.M)
    return [p for p in parts if p.strip()]


def keep(s: str) -> bool:
    toks = s.split()
    return (40 <= len(s) <= 400 and len(toks) >= 6
            and s[-1] in ".!?" and not re.search(r"[<>{}]", s)
            and not BOILER.search(s))


def dedup(seq):
    seen, out = set(), []
    for s in seq:
        k = s.strip().lower()
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def stride_pick(cands, per_section_ratio=0.18):
    """Even stride within one section. Ratio keeps sections proportional to
    their own length (no per-document cap, no equalisation)."""
    keep_n = int(len(cands) * per_section_ratio)
    if keep_n < MIN_SECTION_SENTENCES and len(cands) >= MIN_SENTENCES_PER_SECTION:
        keep_n = MIN_SECTION_SENTENCES
    if keep_n <= 0:
        return []
    step = len(cands) / keep_n
    return [cands[int(i * step)] for i in range(keep_n)]


def dedup(seq):
    seen, out = set(), []
    for s in seq:
        k = s.strip().lower()
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def main() -> int:
    log = json.loads(
        (ROOT / "docs" / "batch7_fetch_log_v1.json").read_text(encoding="utf-8"))
    sel = [d for d in log["domains"] if d.get("selected")]
    print("selected documents:", len(sel))
    if not sel:
        raise SystemExit("no documents selected yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())