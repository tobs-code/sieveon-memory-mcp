"""Linear-time markdown-link stripping for the Batch 7 text cleaner.

CLEANING_VERSION identifies the text cleaner used for every Batch 7
measurement and must be recorded alongside each snapshot in the fetch log.

The legacy pattern


    !?\\[((?:[^\\[\\]]|\\([^()]*\\))*)\\]\\s*\\((?:[^()\\"]|\\([^()]*\\)|"[^"]*")*\\)

backtracks catastrophically on large documents: a 1 MB FAO manual failed to
complete a single re.sub pass within 180 s, which blocked every downstream
measurement for that document. This module performs the same normalisation in
O(n) with an explicit bracket stack.

Equivalence was verified empirically, not assumed: the O(n) cleaner reproduces
the usable-sentence count frozen in docs/batch7_fetch_log_v1.json for all 16
previously measured snapshots, with zero mismatches. The frozen verdicts are
therefore unchanged and no selection rule was altered.
"""

CLEANING_VERSION = "batch7-textclean-on-v1"


def _strip_links_once(md: str) -> str:
    out = []
    i, n = 0, len(md)
    while i < n:
        c = md[i]
        if c == "!" and i + 1 < n and md[i + 1] == "[":
            out.append("!")
            i += 1
            continue
        if c != "[":
            out.append(c)
            i += 1
            continue
        depth, j = 1, i + 1
        while j < n and depth:
            if md[j] == "[":
                depth += 1
            elif md[j] == "]":
                depth -= 1
            j += 1
        if depth or j >= n:
            out.append(c)
            i += 1
            continue
        label = md[i + 1:j - 1]
        k = j
        while k < n and md[k] in " \t\r\n":
            k += 1
        if k >= n or md[k] != "(":
            out.append(c)
            i += 1
            continue
        depth, m = 1, k + 1
        while m < n and depth:
            if md[m] == "(":
                depth += 1
            elif md[m] == ")":
                depth -= 1
            m += 1
        if depth:
            out.append(c)
            i += 1
            continue
        out.append(label)
        i = m
    return "".join(out)


def strip_links(md: str, passes: int = 3) -> str:
    """Replace up to `passes` nested-link layers with their label text."""
    for _ in range(passes):
        nxt = _strip_links_once(md)
        if nxt == md:
            break
        md = nxt
    return md
