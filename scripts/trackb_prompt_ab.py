"""Prompt A/B mirror caller (Ast D).

Experiment-local caller that mirrors frozen validate() from
scripts/trackb_two_stage.py byte-identically EXCEPT the prompt question
string. The frozen file is imported (constants) but never modified.

Use: arm A runs frozen validate() itself; arm B runs mirror_validate()
with the preregistered B prompt text. See
docs/batch7_prompt_ab_design_v1.json.
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trackb_two_stage as _F


def mirror_validate(sentence, x, y, prompt_text,
                    max_tokens=None, temperature=0, timeout=None):
    """Same transport/parsing/retry contract as frozen validate().

    Only differences allowed: prompt_text (preregistered B text) and
    optional overrides, which default to the frozen constants.
    Returns (supported_bool, raw_prefix_200) like frozen validate().
    """
    mt = _F.KILO_MAX_TOKENS if max_tokens is None else max_tokens
    to = _F.KILO_TIMEOUT if timeout is None else timeout
    body = json.dumps({"model": _F.KILO_MODEL, "stream": False,
                       "temperature": temperature,
                       "max_tokens": mt,
                       "messages": [{"role": "user",
                                     "content": prompt_text % (sentence, x,
                                                               y)}]}).encode()
    headers = {"Content-Type": "application/json"}
    key = _F.kilo_key()
    if key:
        headers["Authorization"] = "Bearer %s" % key
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(_F.KILO_URL, data=body,
                                         headers=headers)
            with urllib.request.urlopen(req, timeout=to) as r:
                payload = json.loads(r.read())
                raw = payload["choices"][0]["message"]["content"] or ""
            start, end = raw.index("{"), raw.rindex("}") + 1
            return bool(json.loads(raw[start:end]).get("supported")), \
                raw[:200]
        except Exception as exc:
            last = exc
    raise RuntimeError("validator failed 3x: %s" % (last,))
