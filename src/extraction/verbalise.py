"""Single source for turning a (subject, predicate, object) triple into the
natural-language claim a verifier judges.

Evaluation and production must check exactly the same claims. If the eval
script said "Andrew built the apartment" and production said "Andrew
constructed an apartment", a verifier measured on the first would be
deployed on the second, and the measurement would be worthless. So both
import from here, and any template change re-runs the whole comparison.

The template must preserve the semantic claim. "Andrew -built-> apartment"
is wrong only if the claim reads as a building event, so the wording is the
verbatim relation, not a paraphrase that softens the decision.
"""

from typing import Dict

# Predicate -> claim template.
CLAIM: Dict[str, str] = {
    "acquired": "{s} acquired {o}.",
    "built": "{s} built {o}.",
    "created": "{s} created {o}.",
    "designed": "{s} designed {o}.",
    "developed": "{s} developed {o}.",
    "discovered": "{s} discovered {o}.",
    "founded": "{s} founded {o}.",
    "funded": "{s} funded {o}.",
    "integrated": "{s} integrated {o}.",
    "joined": "{s} joined {o}.",
    "leads": "{s} leads {o}.",
    "located_in": "{s} is located in {o}.",
    "part_of": "{s} is part of {o}.",
    "provides": "{s} provides {o}.",
    "uses": "{s} uses {o}.",
    "works_at": "{s} works at {o}.",
    "wrote": "{s} wrote {o}.",
}

# The extraction-confidence band the verifier is allowed to decide. Triples
# above it auto-accept, below it are dropped. Matches BAND_HI/BAND_LO in
# scripts/eval_verifier.py; both exist so a change in one without the other
# is visible in review.
BAND_LO = 0.70
BAND_HI = 0.95


def verbalise(subject: str, predicate: str, obj: str) -> str:
    """Turn (s, p, o) into the natural-language claim the verifier judges.

    Unknown predicates fall back to the de-sugged name. That keeps a new
    label from crashing the pipeline, at the cost of a less natural claim --
    which is acceptable, because an unnatural claim is evidence *against*
    acceptance, the safe direction.
    """
    template = CLAIM.get(predicate)
    if template is None:
        template = "{s} " + predicate.replace("_", " ") + " {o}."
    return template.format(s=subject, o=obj)
