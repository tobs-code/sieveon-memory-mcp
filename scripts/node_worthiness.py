"""Node-worthiness gate (isolated layer before linking).

WORTHY = mention denotes a graph entity of an allowed class, referential,
with identity info. Provisional operationalization (hypothesis, tested below):
  W1 activity: gerund-headed mention, or head in narrow ACTIVITY set
      (provisional seed: yoga/dance/meditation + X-class/lesson pattern).
  W2 open class: bare-plural head with restrictive relative clause
      (who/that/which + verb) -> NOT_WORTHY.
  W3 singular kinship noun without proper-name anchor -> NOT_WORTHY
      (provisional; tension noted: plural groups like friends stay WORTHY
      per production precedent).
Positive controls (must stay WORTHY): proper names + definite singulars
(homeless shelter, club, nonprofit, venue, team, friends, students...).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ACTIVITY_HEADS = {"yoga", "dance", "dancing", "meditation", "workout", "exercise"}
KINSHIP_SINGULAR = {"family", "mother", "father", "son", "daughter", "parent",
                    "brother", "sister", "husband", "wife"}


def _head(mention: str) -> str:
    words = re.findall(r"[a-z]+", mention.lower())
    return words[-1] if words else ""


def node_worthy(mention: str) -> dict:
    m = mention.strip()
    low = m.lower()
    head = _head(m)
    # W1: gerund-headed or narrow activity head
    if head.endswith("ing") and len(head) > 4:
        return {"verdict": "NOT_WORTHY", "reason": "W1 gerund activity head"}
    if head in ACTIVITY_HEADS or re.search(r"\b\w+\s+(class|lesson|practice)\b", low):
        return {"verdict": "NOT_WORTHY", "reason": "W1 activity pattern"}
    # W2: bare plural + restrictive postmodifier (relative clause or equivalent)
    if re.search(r"\b(kids|people|men|women|children)\b", low) and \
            re.search(r"\b(who|that|which|in need)\b", low):
        return {"verdict": "NOT_WORTHY", "reason": "W2 open-class relative"}
    # W3: singular kinship without proper-name anchor (provisional)
    if head in KINSHIP_SINGULAR and not re.search(r"\b[A-Z][a-z]+\b", m):
        # proper-name check on raw mention (capitalized token present?)
        if not re.search(r"\b[A-Z][a-z]{2,}\b", m):
            return {"verdict": "NOT_WORTHY", "reason": "W3 kinship singular"}
    return {"verdict": "WORTHY", "reason": None}
