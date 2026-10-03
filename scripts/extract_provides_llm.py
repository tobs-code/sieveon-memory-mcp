"""Track B reality check: direct provides extraction via instruction model.

Frozen prompt: closed relation vocabulary (provides only), JSON-only output,
temperature 0. Scores model triples against gold clean/hard pairs.
No training. No threshold tuning.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = "stepfun/step-3.7-flash:free"
GATEWAY = "https://api.kilo.ai/api/gateway/chat/completions"

PROMPT = """Extract asserted support relations from the sentence.
Return ONLY a JSON list. Each item: {"subject": "...", "relation": "provides", "object": "..."}.
Rules:
- relation must always be exactly "provides".
- subject/object must be spans from the sentence.
- Only include a triple if the sentence asserts that the subject actually gave support, help, funding or encouragement to the object.
- Exclude: offers, plans, intentions, wishes, questions, reported/rumored/alleged support, encouragement of someone else.
- If nothing is asserted, return [].
Sentence: %s"""

CASES = [
    ("Maria helped Tim with the fundraiser.", True),
    ("Maria offered to help Tim with the fundraiser.", False),
    ("Maria's support for the nonprofit was substantial.", True),
    ("Maria's support for the nonprofit was rumored.", False),
    ("The coach encouraged the club to keep going.", True),
    ("The coach encouraged the crowd instead of the club.", False),
    ("The team asked if the app needed assistance with the forms.", False),
    ("Maria's support for the nonprofit was hoped for.", False),
]


def call(sentence: str) -> str:
    key = os.environ.get("KILO_API_KEY", "")
    if not key:
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("KILO_API_KEY="):
                key = line.split("=", 1)[1].strip()
    body = json.dumps({"model": MODEL, "stream": False, "temperature": 0,
                       "messages": [{"role": "user", "content": PROMPT % sentence}]}).encode()
    req = urllib.request.Request(GATEWAY, data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def main() -> int:
    tp = fp = tn = fn = 0
    for sent, gold in CASES:
        raw = call(sent)
        try:
            start, end = raw.index("["), raw.rindex("]") + 1
            triples = json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            triples = None
        pred = bool(triples)
        print(('TP' if pred and gold else 'TN' if not pred and not gold
               else 'FP' if pred else 'FN'), '|', sent[:50], '->', raw[:100].replace('\n', ' '))
        tp += pred and gold
        tn += (not pred) and (not gold)
        fp += pred and (not gold)
        fn += (not pred) and gold
    print(f'\naccuracy: {(tp + tn)}/{len(CASES)}  (tp={tp} tn={tn} fp={fp} fn={fn})')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
