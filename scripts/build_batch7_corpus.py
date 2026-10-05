"""Batch 7 corpus builder (source rule a2fcb33, fetch log batch7_fetch_log_v1).

Section-wise sampling: clean text, split into top-level sections, drop
structural sections, then apply the batch-6 stride formula PER SECTION.
No per-document sentence cap and no keyword criterion. Mechanical filters only.
Corpus digest is computed before any pipeline run.

Implementation defect corrected before any corpus was generated:
MIN_DOC_SENTENCES was 1200, which contradicted the frozen Batch 7
qualification criterion of >=300 usable sentences. Left unchanged it acted as
an unregistered second selection stage that would have silently discarded 15
of the 23 selected documents. The builder now implements the frozen
criterion instead; no qualification rule, threshold or selection changed.
See docs/batch7_builder_defect_v1.json.

Second correction round (explicitly decided, not inferred), after the single
first build produced 1316 sentences instead of 200:
- the minimum-two-per-section floor was removed entirely. It was never a
  frozen protocol rule; the protocol specifies only ratio r = 200 / total
  usable sentences with stride per section. A section that mathematically
  yields zero samples contributes zero; that is a rule outcome, not an
  error to repair with a minimum.
- the jina reader header strip (Title / URL Source / Published Time /
  Number of Pages) is taken over 1:1 from the qualification path in
  scripts/jina_fetch.py. No extension, no new heuristics.
See docs/batch7_corpus_verdict_v1.json.
"""

import hashlib
import json
import re
from pathlib import Path

from batch7_textclean import strip_links

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

HEADING_MAXLEN = 140
HEADING_NUMERIC = re.compile(r"^[\d\s.,:;]+$")
HEADING_TOC = re.compile(r"^\s*(table of )?contents\s*$", re.I)
HEADING_URLCOPY = re.compile(
    r"copyright|\u00a9|all rights reserved|https?://|www\.\S+")


def section_heading_artefact(t: str) -> bool:
    """Frozen artefact predicates: purely syntactic, no semantic judgement."""
    return bool(HEADING_NUMERIC.match(t) or HEADING_TOC.match(t)
                or HEADING_URLCOPY.search(t) or len(t) > HEADING_MAXLEN)

# NOTE: an earlier revision carried MIN_SENTENCES_PER_SECTION = 3 and
# MIN_SECTION_SENTENCES = 2 as a minimum-two-per-section floor. The floor was
# removed by explicit decision (it was never a frozen protocol rule); the
# constants are deleted rather than left to invite misreading.
# Implements the frozen Batch 7 qualification criterion (>=300 usable
# sentences). The previous value of 1200 was an unregistered second selection
# stage; it is recorded, not silently deleted.
MIN_DOC_SENTENCES = 300
QUALIFYING_SENTENCES = 300
EXPECTED_SELECTED_DOCUMENTS = 23


def clean(md: str) -> str:
    # Header strip, 1:1 from the qualification path (scripts/jina_fetch.py).
    # The builder must use the same text definition as qualification.
    md = re.sub(r"^(Title|URL Source|Published Time|Number of Pages):.*$",
                "", md, flags=re.M)
    md = CUT_SECTIONS.split(md)[0]
    md = strip_links(md)
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


CORPUS_TARGET_SENTENCES = 200


def frozen_sections(cut):
    """Partition the raw text per the frozen section rule. Returns (L, secs)
    where secs holds only surviving candidates at level L; rejected headings
    are plain text. L is None when nothing qualifies (DEGENERATE)."""
    heads = [(len(m.group(1)), m.group(2).strip())
             for m in re.finditer(r"^(#{1,6})\s+(\S.*)$", cut, flags=re.M)]
    kept = [(l, t) for l, t in heads if not section_heading_artefact(t)]
    per_level = {}
    for l, _ in kept:
        per_level[l] = per_level.get(l, 0) + 1
    eligible = [l for l, n in sorted(per_level.items()) if n >= 2]
    L = eligible[0] if eligible else None
    if L is None:
        return None, [cut]
    pat = re.compile(rf"^#{{{L}}}\s+\S.*$", flags=re.M)
    secs, buf = [], []
    for line in cut.split("\n"):
        m = pat.match(line)
        if m and not section_heading_artefact(
                re.sub(r"^#{1,6}\s+", "", line).strip()):
            secs.append("\n".join(buf))
            buf = []
            continue
        buf.append(line)
    secs.append("\n".join(buf))
    return L, [x for x in secs if x.strip()]


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


def stride_pick(cands, ratio):
    """Even stride within one section. Ratio keeps sections proportional to
    their own length (no per-document cap, no equalisation). No minimum: a
    section that mathematically yields zero samples contributes zero. That
    is a rule outcome, not an error; the removed minimum-two floor was never
    a frozen protocol rule (see module docstring)."""
    keep_n = int(len(cands) * ratio)
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


def audit_selection(sel):
    """Hard guard: the corpus must contain exactly the documents that were
    selected under the frozen qualification rule. Raises on any divergence so
    that a selection-to-build discrepancy can never pass silently."""
    if len(sel) != EXPECTED_SELECTED_DOCUMENTS:
        raise SystemExit(
            f"selection guard: expected {EXPECTED_SELECTED_DOCUMENTS} selected "
            f"documents, found {len(sel)}. Refusing to build: the corpus must "
            f"implement the frozen selection, not a subset of it.")
    problems = []
    for d in sel:
        name = d.get("snapshot") or d.get("url")
        usable = d.get("usable_sentences")
        if not isinstance(usable, int):
            problems.append(f"{name}: no usable_sentences recorded")
        elif usable < QUALIFYING_SENTENCES:
            problems.append(
                f"{name}: {usable} usable sentences is below the frozen "
                f"qualification criterion of {QUALIFYING_SENTENCES}")
    if problems:
        raise SystemExit("qualification guard failed:\n  " + "\n  ".join(problems))
    print(f"guards OK: {len(sel)} documents, all >= {QUALIFYING_SENTENCES} "
          f"usable sentences")


def main() -> int:
    log = json.loads(
        (ROOT / "docs" / "batch7_fetch_log_v1.json").read_text(encoding="utf-8"))
    sel = list(log.get("selected_documents", []))
    print("selected documents:", len(sel))
    if not sel:
        raise SystemExit("no documents selected yet")
    audit_selection(sel)

    # pass 1: usable sentences per document, total for the global ratio
    docs = []
    for d in sel:
        snap = ROOT / d["snapshot"]
        raw = snap.read_text(encoding="utf-8")
        assert hashlib.sha256(raw.encode()).hexdigest() == d["raw_sha256"], (
            f"snapshot bytes changed under pinning: {d['snapshot']}")
        cut = CUT_SECTIONS.split(raw)[0]
        L, secs = frozen_sections(cut)
        sec_usable = [dedup([s for s in split_sentences(clean(x)) if keep(s)])
                      for x in secs]
        docs.append({"record": d, "L": L, "secs": sec_usable,
                     "total": sum(len(c) for c in sec_usable)})
    grand = sum(x["total"] for x in docs)
    ratio = CORPUS_TARGET_SENTENCES / grand
    print(f"usable sentences total: {grand}  "
          f"global ratio: {CORPUS_TARGET_SENTENCES}/{grand} = {ratio:.6f}")

    # pass 2: stride per section, document-wide stride for DEGENERATE
    corpus, per_doc = [], []
    for x in docs:
        d = x["record"]
        tag = d["snapshot"].split("/")[-1].replace(".md", "")
        got, sec_report = [], []
        if x["L"] is None:
            cands = dedup([s for sec in x["secs"] for s in sec])
            picks = stride_pick(cands, ratio)
            got = [(s, -1, i) for i, s in enumerate(picks)]
            sec_report.append({"section": "DEGENERATE document-wide",
                               "candidates": len(cands),
                               "picked": len(picks)})
        else:
            for si, cands in enumerate(x["secs"]):
                picks = stride_pick(cands, ratio)
                got.extend((s, si, i) for i, s in enumerate(picks))
                sec_report.append({"section": si, "candidates": len(cands),
                                   "picked": len(picks)})
        per_doc.append({"tag": tag, "url": d["url"],
                        "usable_total": x["total"],
                        "sections": len(x["secs"]), "level": x["L"],
                        "picked": len(got), "detail": sec_report})
        for s, si, pi in got:
            corpus.append({"doc": tag, "url": d["url"],
                           "doc_sha256": d["raw_sha256"],
                           "section": si, "pick_index": pi,
                           "sentence": s})
    print(f"picked sentences: {len(corpus)} "
          f"(target {CORPUS_TARGET_SENTENCES})")

    # global dedup preserving first occurrence; every removal is recorded
    # global dedup preserving first occurrence. Removals are not silent:
    # each dropped duplicate records where it was kept and where it
    # reappeared, so it is visible whether the stride selected the same
    # sentence twice or whether repeated source boilerplate recurs.
    seen, clean_corpus, removed = {}, [], []
    for r in corpus:
        k = r["sentence"].strip().lower()
        if k in seen:
            kept = seen[k]
            removed.append({"sentence_head": r["sentence"][:90],
                            "kept_at": {"doc": kept["doc"],
                                        "section": kept["section"]},
                            "dropped_at": {"doc": r["doc"],
                                           "section": r["section"]},
                            "same_section_reselect": (
                                kept["doc"] == r["doc"]
                                and kept["section"] == r["section"])})
            continue
        seen[k] = r
        r["corpus_index"] = len(clean_corpus)
        clean_corpus.append(r)
    print(f"cross-document duplicates removed: {len(removed)}")

    digest = hashlib.sha256(
        json.dumps(clean_corpus, ensure_ascii=False,
                   sort_keys=True).encode()).hexdigest()
    out = {"corpus_id": "batch7_corpus_v1",
           "documents": 23, "target_sentences": CORPUS_TARGET_SENTENCES,
           "global_ratio": ratio,
           "usable_total": grand,
           "sentences": len(clean_corpus),
           "cross_doc_duplicates_removed": removed,
           "digest_sha256": digest,
           "rule": "v3 qualification, frozen section rule, "
                   "stride per section, document-wide stride for DEGENERATE",
           "records": clean_corpus}
    (ROOT / "docs" / "batch7_corpus_v1.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "docs" / "batch7_corpus_build_audit_v1.json").write_text(
        json.dumps({"ratio": ratio, "usable_total": grand,
                    "sentences": len(clean_corpus), "digest": digest,
                    "per_document": per_doc}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("digest:", digest)
    print("\nper-document contributions:")
    for p in per_doc:
        print(f"  {p['picked']:4d}  {p['tag']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())