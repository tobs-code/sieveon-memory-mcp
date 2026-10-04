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
