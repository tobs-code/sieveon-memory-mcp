"""PostFilter v1: deterministic gates as functions. No pipeline wiring yet.

- Scope gate (CONDITIONAL/QUESTIONED/REPORTED/NEGATED/DESIDERATIVE/
  CONTRASTIVE_TARGET/INTENTIONAL/ATTRIBUTED): hard REJECT.
- Argument grounding: hard invariant.
- Entity gate: existing linker (resolved/ambiguous).
- Trigger licensing tri-state: LICENSED pass / UNKNOWN warn / NOT_PROVIDES reject.
- NLI: shadow only (not implemented here; see postfilter_shadow.py).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from postfilter_shadow import (LICENSED_TRIGGERS, SCOPE_CUES, NEG,
                               argument_grounding, trigger_licensing)
from trackb_production import link

NOT_PROVIDES_TRIGGERS = ["initiat"]

# PostFilter v1.1 DIRECT_SUPPORT licensing (constructions with bound roles).
# advises / roots-for / advice-transfer with resolved source.
# Everything else unchanged; UNKNOWN stays WARN.


def direct_support_licensing(sentence: str, subj: str, obj: str):
    low = sentence.lower()
    m = re.search(r"\b(advises|advised|advise|advising)\b", low)
    if m and low.find(subj.lower()) < m.start() < low.find(obj.lower()):
        return {"construction": "ACTIVE_advise"}
    m = re.search(r"\broots?\s+for\b", low)
    if m and low.find(subj.lower()) < m.start() < low.find(obj.lower()):
        return {"construction": "ACTIVE_roots_for"}
    m = re.search(r"\b(got|received|obtained)\b[^.]{0,40}\badvice\b", low)
    if m:
        # source explicit (from-phrase) or both candidate spans present;
        # bare "X got advice." with the partner absent never licenses.
        if re.search(r"\bfrom\s+[a-z]", low[m.start():]) or \
                (subj.lower() in low and obj.lower() in low):
            return {"construction": "NOMINAL_TRANSFER_advice"}
    return None


def scope_gate(sentence: str) -> dict:
    low = sentence.lower()
    for reason, cues in SCOPE_CUES.items():
        if any(c in low for c in cues):
            return {"verdict": "REJECT", "reason": reason}
    if any(re.search(r"\b" + n.strip() + r"\b", low) for n in NEG):
        # Batch-2 finding: bare negation cues hit complements
        # ("not to give up"), not the trigger. NEGATED stays OBSERVATION
        # until scope resolution (negation_scope(trigger)) exists.
        return {"verdict": "OBSERVE", "reason": "NEGATED_UNSCOPED"}
    return {"verdict": "PASS", "reason": None}


def trigger_gate(sentence: str, subj: str, obj: str) -> dict:
    low = sentence.lower()
    for lex in NOT_PROVIDES_TRIGGERS:
        if re.search(lex, low):
            return {"verdict": "REJECT", "reason": "NOT_PROVIDES",
                    "lemma": lex}
    trig = trigger_licensing(sentence, subj, obj)
    if trig["status"] == "pass":
        return {"verdict": "PASS", "reason": None, "lemma": trig["lemma"],
                "construction": trig.get("construction")}
    lic = direct_support_licensing(sentence, subj, obj)
    if lic is not None:
        return {"verdict": "PASS", "reason": "DIRECT_SUPPORT_V2", **lic}
    return {"verdict": "WARN", "reason": "UNKNOWN_TRIGGER"}


def judge(sentence: str, subj: str, obj: str, norms: set) -> dict:
    arg = argument_grounding(sentence, subj, obj)
    if arg["status"] != "pass":
        return {"final": "REJECT", "by": "ARGUMENT_GROUNDING"}
    sc = scope_gate(sentence)
    if sc["verdict"] == "REJECT":
        return {"final": "REJECT", "by": "SCOPE", "reason": sc["reason"]}
    ent = link(subj, norms)["status"] + "/" + link(obj, norms)["status"]
    if "ambiguous" in ent:
        return {"final": "ABSTAIN", "by": "ENTITY", "entity": ent}
    tg = trigger_gate(sentence, subj, obj)
    if tg["verdict"] == "REJECT":
        return {"final": "REJECT", "by": "TRIGGER", "reason": tg["reason"]}
    return {"final": "ACCEPT" if tg["verdict"] == "PASS" else "WARN_ACCEPT",
            "by": "TRIGGER", "trigger": tg}
