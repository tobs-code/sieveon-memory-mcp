"""Natural claim templates for the counterfactual relations. Shadow use only.

The legacy selector run scored these relations through verbalise()'s
fallback, which de-sugars the label into text: "X pitched_to Y". Against
hand-written templates for other candidates that is a confound, because the
score may prefer whichever hypothesis reads more like natural English rather
than whichever states the right relation. To test that, every candidate in a
case needs a template of comparable quality -- target and distractor alike.

Two constraints on these templates, both enforced by check_templates():

  roles      the template must express s -p-> o in that order. An asymmetric
             relation written the other way round would bias the selector
             before it scored anything, which is exactly the failure this
             experiment is supposed to rule out.
  no smuggling   a template may not add completion that the relation does not
             contain. "earned" must not become "had earned", and nothing may
             acquire a negation.

Not production. verbalise() is untouched; nothing here is imported by the
ingest path. These templates exist so the measurement can separate relation
semantics from phrasing quality.

Usage:
    python scripts/counterfactual_templates.py          # validate and print
"""

from __future__ import annotations

from typing import Dict

# {s} is the subject of the triple, {o} the object. Order is part of the
# contract for asymmetric relations and check_templates() verifies it.
COUNTERFACTUAL_CLAIM: Dict[str, str] = {
    # participation / event
    "attended":       "{s} attended {o}.",
    "auditioned_for": "{s} auditioned for {o}.",
    "performed_live_in": "{s} performed live in {o}.",
    "toured_with":    "{s} toured with {o}.",
    "pitched_to":     "{s} pitched {o}.",
    # possession
    "owns":           "{s} owns {o}.",
    # conversation / interest
    "asked_about":    "{s} asked {o} about it.",
    "asked_for":      "{s} asked {o} for it.",
    "agrees_to":      "{s} agreed to {o}.",
    "suggested_meeting_at": "{s} suggested meeting at {o}.",
    "suggests":       "{s} suggests {o}.",
    # location / motion
    "traveled_to":    "{s} traveled to {o}.",
    "visited":        "{s} visited {o}.",
    "near":           "{s} is near {o}.",
    "recommended":    "{s} recommended {o}.",
    # interaction / communication
    "sent":           "{s} sent {o}.",
    "shared":         "{s} shared {o}.",
    "gifted":         "{s} gifted {o}.",
    "motivates":      "{s} motivates {o}.",
    "took_on_trip":   "{s} took {o} on a trip.",
    # perception
    "watched":        "{s} watched {o}.",
    # attribute / need
    "requires":       "{s} requires {o}.",
    "restored":       "{s} restored {o}.",
    "modified":       "{s} modified {o}.",
    # social role
    "parent_of":      "{s} is a parent of {o}.",
    "noticed_by":     "{s} was noticed by {o}.",
    # achievement
    "earned":         "{s} earned {o}.",
    "drafted_by":     "{s} was drafted by {o}.",
    "finished":       "{s} finished {o}.",
    "started":        "{s} started {o}.",
    # value
    "alternative_to": "{o} is an alternative to {s}.",
    # attempt
    "tried":          "{s} tried {o}.",
    # position / rest, deliberately left out: `sat_on` reads as a posture
    # instruction rather than an event, and no honest one-line claim exists.
    # It is reported as untemplated rather than given a clumsy template.
}

# Relations whose triple order is not subject-object order, so the template
# must place {o} first. Kept explicit because getting this wrong would
# silently swap the roles in the hypothesis.
OBJECT_FIRST = {"alternative_to"}

# Words that would smuggle in aspect the relation does not carry.
SMUGGLED_ASPECT = ("had ", "will ", "would ", "hadn't", "will have",
                   "was going to", "is going to")


def check_templates() -> Dict[str, list]:
    """Deterministic checks before any selector run.

    Each template must contain both placeholders exactly once, must not
    introduce negation or completion the relation does not state, and object
    -first relations must actually place {o} before {s}.
    """
    problems: Dict[str, list] = {}
    for rel, tpl in COUNTERFACTUAL_CLAIM.items():
        issues = []
        if tpl.count("{s}") != 1 or tpl.count("{o}") != 1:
            issues.append("placeholder count wrong")
        if " not " in tpl or " never " in tpl or "n't" in tpl:
            issues.append("template introduces negation")
        low = tpl.lower()
        for w in SMUGGLED_ASPECT:
            if w in low:
                issues.append(f"template adds aspect: {w.strip()}")
        if rel in OBJECT_FIRST and low.find("{o}") > low.find("{s}"):
            issues.append("object-first relation puts {s} first")
        if rel not in OBJECT_FIRST and low.find("{s}") > low.find("{o}"):
            issues.append("subject-first relation puts {o} first")
        if not tpl.rstrip().endswith("."):
            issues.append("missing sentence terminator")
        if issues:
            problems[rel] = issues
    return problems


def render(rel: str, subject: str, obj: str) -> str:
    """Render with the counterfactual set first, then verbalise()'s."""
    from src.extraction.verbalise import verbalise
    if rel in COUNTERFACTUAL_CLAIM:
        return COUNTERFACTUAL_CLAIM[rel].format(s=subject, o=obj)
    return verbalise(subject, rel, obj)


if __name__ == "__main__":
    probs = check_templates()
    print(f"templates: {len(COUNTERFACTUAL_CLAIM)}")
    for rel in sorted(COUNTERFACTUAL_CLAIM):
        flag = "  <-- " + "; ".join(probs[rel]) if rel in probs else ""
        print(f"  {rel:22} {COUNTERFACTUAL_CLAIM[rel]}{flag}")
    print()
    if probs:
        print(f"{len(probs)} template(s) failed validation")
        raise SystemExit(1)
    print("all templates pass: placeholders, order, negation, aspect")