"""Build production corpus v6 from fresh Wikipedia snapshots (batch6_protocol_v1).

Source: 10 pre-registered heterogeneous Wikipedia articles, fetched
2026-10-04 via Firecrawl (raw markdown snapshots in tool-output dir).
Selection is purely mechanical: structural boilerplate cut, markdown
cleanup, deterministic sentence split, length/token filters, even stride
sampling (15 per article). No content/keyword criterion anywhere.
"""

import hashlib
import json
import re
from pathlib import Path

TOOL_DIR = Path("C:/Users/tobs/.local/share/opencode/tool-output")
ARTICLES = [
    "Photosynthesis", "Sourdough", "Lighthouse", "Silk_Road", "Jazz",
    "Coral_reef", "Bicycle", "Pottery", "Public_library", "Beekeeping",
]
PER_ARTICLE = 15
FETCH_DATE = "2026-10-04"
ROOT = Path(__file__).resolve().parents[1]

ABBREV = {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "vs", "etc",
          "fig", "no", "eg", "ie", "us", "uk", "usa", "jan", "feb",
          "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
          "nov", "dec", "prof", "rep", "sen", "gov", "gen", "col",
          "sgt", "capt", "cmdr", "ave", "blvd", "rd", "mt"}

CUT_SECTIONS = re.compile(
    r"^##\s+(References|External links|See also|Further reading|"
    r"Notes|Footnotes|Bibliography|Sources)\b.*", re.M | re.S)


def load_snapshots():
    snaps = {}
    for f in TOOL_DIR.glob("tool_1085*"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        url = (d.get("metadata") or {}).get("sourceURL", "")
        m = re.search(r"/wiki/([^/#?]+)", url)
        if m and "markdown" in d:
            snaps[m.group(1)] = (url, d["markdown"])
    missing = [a for a in ARTICLES if a not in snaps]
    assert not missing, f"missing snapshots: {missing}"
    return snaps


def clean(md: str) -> str:
    md = CUT_SECTIONS.split(md)[0]
    link = (r"!?\[((?:[^\[\]]|\([^()]*\))*)"  # anchor, parens-safe
            r"\]\s*\((?:[^()\"]|\([^()]*\)|\"[^\"]*\")*\)")
    for _ in range(3):  # fixpoint: nested thumb/link markup
        md = re.sub(link, r"\1", md)
    md = re.sub(r"\]\s*\([^)]*\)", "", md)  # leftover ](url) tails
    md = re.sub(r"!\s*\(\s*", "", md)  # stray image-marker remnants
    md = re.sub(r"\(\s*\)", "", md)  # empty paren remnants
    md = re.sub(r"\*\*+", "", md)  # bold markers
    md = re.sub(r"\[\d+(?:,\s*\d+)*\]", "", md)  # [12] ref markers
    md = re.sub(r"^#{1,6}\s+.*$", "", md, flags=re.M)  # headings
    md = re.sub(r"^\s*\|.*\|\s*$", "", md, flags=re.M)  # table rows
    md = re.sub(r"https?://\S+", "", md)
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


BOILER = re.compile(r"wikimedia|donor privacy|benefactors@|tax-deductible|"
                      r"jump to content|\\|for other uses|utm_|thumbnail|"
                      r"main article:|from wikipedia, the free encyclopedia|"
                      r"help fix the gap|^for .*?, see ",
                      re.I)


def title_glue(s: str, title: str) -> bool:
    """Structural: article title glued to short-desc/sentence without period."""
    tw = title.replace("_", " ").lower().split()
    toks = s.split()
    if [t.lower() for t in toks[:len(tw)]] != tw:
        return False
    rest = [t.lower() for t in toks[:8]]
    if sum(1 for t in rest if t in tw) > len(tw):
        return True  # title words repeat: "Sourdough bread Sourdough is"
    nxt = toks[len(tw)] if len(toks) > len(tw) else ""
    return bool(nxt) and nxt[0].isupper()  # "Coral reef Outcrop ..."


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


def main() -> int:
    snaps = load_snapshots()
    sentences, snapshot = [], {}
    for art in ARTICLES:
        url, md = snaps[art]
        snapshot[art] = {"url": url, "fetched": FETCH_DATE,
                         "raw_sha256": hashlib.sha256(
                             md.encode("utf-8")).hexdigest()}
        cands = dedup(
            [s for s in split_sentences(clean(md))
             if keep(s) and not title_glue(s, art)])
        assert len(cands) >= PER_ARTICLE, f"{art}: only {len(cands)}"
        step = len(cands) / PER_ARTICLE
        picked = [cands[int(i * step)] for i in range(PER_ARTICLE)]
        doc = f"wiki/{art}"
        for s in picked:
            sentences.append({"document_id": doc, "text": s})
    assert len(sentences) == 150
    for i, s in enumerate(sentences):
        s["sentence_id"] = f"prodc6-{i:03d}"
        sentences[i] = {"document_id": s["document_id"],
                        "sentence_id": s["sentence_id"], "text": s["text"]}
    digest = hashlib.sha256(
        "\n".join(s["text"] for s in sentences).encode("utf-8")).hexdigest()
    # disjointness: exact normalized-text overlap must be zero
    prior = set()
    for f in ROOT.glob("docs/production_corpus_v*.json"):
        if "v6" in f.name:
            continue
        d = json.loads((ROOT / f).read_text(encoding="utf-8"))
        for x in d["sentences"]:
            prior.add(x["text"].strip().lower())
    test = set()
    for f in list(ROOT.glob("docs/eval_*.jsonl")) + list(
            ROOT.glob("docs/trackb_*.jsonl")) + list(
            ROOT.glob("docs/eval_triples_*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            for k in ("text",):
                if isinstance(r.get(k), str):
                    test.add(r[k].strip().lower())
    norm = [s["text"].strip().lower() for s in sentences]
    ov_prior = sum(1 for t in norm if t in prior)
    ov_test = sum(1 for t in norm if t in test)
    ov_self = len(norm) - len(set(norm))
    print(f"prior-overlap: {ov_prior}, test-overlap: {ov_test}, "
          f"self-dupes: {ov_self}")
    assert ov_prior == 0 and ov_test == 0 and ov_self == 0
    docs_n = len(set(s["document_id"] for s in sentences))
    out = {"version": "production_corpus_v6", "n": 150, "digest": digest,
           "digest_method": "sha256 of newline-joined sentence texts in order",
           "snapshot": snapshot,
           "selection": {"articles": ARTICLES, "per_article": PER_ARTICLE,
                         "method": "even stride sampling; mechanical filters "
                         "only: 40-400 chars, >=6 tokens, terminal .!?, "
                         "markdown/chrome/boilerplate/hatnote removal, "
                         "title-glue removal, order-preserving dedup; "
                         "no content or keyword criterion",
                         "fetch": "firecrawl markdown, onlyMainContent",
                         "fetch_date": FETCH_DATE},
           "sentences": sentences}
    (ROOT / "docs" / "production_corpus_v6.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"docs: {docs_n}, digest: {digest[:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
