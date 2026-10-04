"""Build FN profiling set: 9 FNs x 3 matched successful controls (protocol: tree v3 next step).

Matching score (material features ONLY, never candidate outcomes):
  4 x predicate_family + 3 x argument_structure + 2 x entity_role_pattern
  + 2 x syntax + 1 x semantic_domain. Ties broken by pair_id (lexical).
Pool eligibility (successful = candidate present) comes from frozen results
files and is documented, not cherry-picked: scoring itself uses no outcomes.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

VERB_FAMILY = {
    "provide": "provision", "supply": "provision", "offer": "provision",
    "give": "provision", "supports": "support", "support": "support",
    "deliver": "transfer", "hand": "transfer", "pass": "transfer",
    "send": "transfer", "lend": "transfer", "transfer": "transfer",
    "do": "service", "pay": "service", "tip": "service", "buy": "service",
    "fetch": "service", "cook": "service", "spread": "service",
    "allocate": "allocation", "assign": "allocation", "grant": "allocation",
    "issue": "allocation", "allot": "allocation", "refund": "allocation",
    "teach": "instruction", "show": "instruction",
    "feed": "provisioning", "equip": "provisioning", "secure": "procurement",
    "give off": "emission", "leaven": "transformation", "assist": "assistance",
    "serve": "service", "fund": "finance", "build": "creation",
    "open": "opening", "bring": "transfer", "plant": "planting",
}

ANIMATE_HEADS = {"patients", "students", "visitors", "guests", "clients",
                 "pupils", "tribes", "teams", "crews", "readers", "artists",
                 "athletes", "residents", "families", "workers", "children",
                 "users", "neighbors", "schools", "units", "winners",
                 "applicants", "trains", "prisoners", "tenants", "players",
                 "trainees", "refugees", "nebhews", "pupils", "doctors"}

# FN side features (from frozen diagnosis/microprofile, documented)
FN_FEATURES = {
    "prodc6-012": {"verb": "give off", "arity": 2, "frame": "active-transitive",
                   "pat": (0, 0, 0), "syntax": "simple-active", "domain": "transformation"},
    "prodc6-027": {"verb": "leaven", "arity": 2, "frame": "passive-instrument",
                   "pat": (0, 0, 0), "syntax": "passive", "domain": "food"},
    "prodc6-030": {"verb": "assist", "arity": 2, "frame": "intransitive-PP",
                   "pat": (0, 0, 0), "syntax": "PP-complement", "domain": "service"},
    "prodc6-032": {"verb": "provide", "arity": 3, "frame": "participial-ditransitive",
                   "pat": (0, 1, 0), "syntax": "participial", "domain": "identification"},
    "prodc6-055": {"verb": "open", "arity": 3, "frame": "active-idiom-PP",
                   "pat": (0, 1, 1), "syntax": "idiom", "domain": "information"},
    "prodc6-112": {"verb": "serve", "arity": 3, "frame": "relative-serve-as-PP",
                   "pat": (0, 1, 0), "syntax": "relative", "domain": "artifact"},
    "prodc6-120": {"verb": "fund", "arity": 2, "frame": "passive-source",
                   "pat": (0, 1, 0), "syntax": "passive", "domain": "finance"},
    "prodc6-130": {"verb": "serve", "arity": 3, "frame": "biclausal-modal",
                   "pat": (0, 1, 1), "syntax": "biclausal", "domain": "service"},
    "prodc6-132": {"verb": "fund", "arity": 2, "frame": "passive-event-patient",
                   "pat": (0, 1, 0), "syntax": "passive", "domain": "finance"},
}

DOMAIN_MAP = {
    "medical_provision": "medical", "fuel_supply": "transfer",
    "food_supply": "food", "book_provision": "information",
    "training_provision": "service", "tutoring_provision": "service",
    "art_provision": "artifact", "parcel_transfer": "transfer",
    "badge_transfer": "transfer", "permission_transfer": "information",
    "budget_transfer": "finance", "award_transfer": "transfer",
    "favor_service": "service", "wage_service": "finance",
    "tip_service": "service", "gift_procurement": "transfer",
    "towel_service": "service", "meal_service": "food",
    "plot_resource": "transfer", "produce_resource": "food",
    "key_issuance": "transfer", "shift_function": "service",
    "skill_instruction": "information", "access_display": "information",
    "fee_refund": "finance", "parts_supply": "transfer",
    "housing_provision": "service", "grant_provision": "finance",
    "hospitality_provision": "service", "lesson_provision": "information",
    "museum_support": "service", "library_support": "service",
    "school_support": "service", "park_support": "service",
    "renovation_support": "construction", "digitization_support": "information",
    "restoration_support": "construction", "expansion_support": "construction",
    "museum_renovation_support": "construction",
    "records_digitization_support": "information",
    "theater_restoration_support": "construction",
    "hospital_expansion_support": "construction",
    "renovated_museum_support": "artifact",
    "digitized_records_support": "information",
    "restored_theater_support": "artifact",
    "expanded_hospital_support": "artifact",
    "medical": "medical", "fuel": "transfer", "badge": "transfer",
    "lesson": "information", "food": "food", "identification": "identification",
    "transformation": "transformation", "finance": "finance",
    "service": "service", "artifact": "artifact", "information": "information",
    "funding": "finance", "signature_identification": "identification",
    "community_program_service": "service", "artifact_service": "artifact",
    "assistance_function": "service", "information_knowledge": "information",
    "transformation_output": "transformation",
}


def head(s):
    import re
    toks = re.findall(r"[a-z]+", s.lower())
    return toks[-1] if toks else ""


def load_json(p):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def collect_pool():
    """(sentence_id, text, verb, arity, frame, pat, syntax, domain, source)."""
    pool = []

    def add(sid, text, verb, arity, frame, pat, syntax, domain, source):
        pool.append({"sentence_id": sid, "text": text, "verb": verb,
                     "arity": arity, "frame": frame, "pat": pat,
                     "syntax": syntax, "domain": domain, "source": source})

    # position probe: all 40 found, canonical/PP/passive/participial
    m = load_json("docs/candidate_probe_material_v1.json")
    r = {x["pair_id"]: x for x in
         load_json("docs/candidate_probe_results_v1.json")["pairs"]}
    for p in m["pairs"]:
        for v in ("a", "b"):
            s = p[v]
            rec = r[p["pair_id"]]["variants"][v]
            if not rec["full_match"]:
                continue
            frm = {"canonical_subject_object": "ditransitive"}.get(
                s["syntactic_class"], s["syntactic_class"])
            add(s["sentence_id"], s["text"], p.get("verb", "provide"), 3,
                frm, (0, 1, 1), "simple-active",
                DOMAIN_MAP.get(s.get("semantic_class", ""), "other"),
                "position:" + p["pair_id"])

    # lexical probe YES found
    m = load_json("docs/candidate_lexical_material_v1.json")
    r = {x["pair_id"]: x for x in
         load_json("docs/candidate_lexical_results_v1.json")["pairs"]}
    for p in m["pairs"]:
        s = p["yes"]
        rec = r[p["pair_id"]]["sides"]["yes"]
        if not rec["full_match"]:
            continue
        add(s["sentence_id"], s["sentence"], p["verb_yes"], 3, "ditransitive",
            (0, 1, 1), "simple-active",
            DOMAIN_MAP.get(p.get("semantic_subtype", ""), "other"),
            "lexical:" + p["pair_id"])

    # complexity YES found
    m = load_json("docs/candidate_complexity_material_v1.json")
    r = {x["pair_id"]: x for x in
         load_json("docs/candidate_complexity_results_v1.json")["pairs"]}
    for p in m["pairs"]:
        s = p["yes"]
        rec = r[p["pair_id"]]["sides"]["yes"]
        if not rec["full_match"]:
            continue
        add(s["sentence_id"], s["sentence"], "provide", 3, "ditransitive",
            (0, 1, 1), "complex-" + p["condition"].lower(), "transfer",
            "complexity:" + p["pair_id"])

    # anaphora: correct/resolved only (strict explicit spans)
    m = load_json("docs/candidate_anaphora_material_v1.json")
    r = {x["pair_id"]: x for x in
         load_json("docs/candidate_anaphora_results_v1.json")["pairs"]}
    for p in m["pairs"]:
        s = p["yes"]
        rec = r[p["pair_id"]]["sides"]["yes"]
        if rec["outcome"] not in ("correct", "resolved"):
            continue
        add(s["sentence_id"], s["sentence"], "provide", 3, "ditransitive",
            (0, 1, 1), "anaphoric-" + p["condition"].lower(), "transfer",
            "anaphora:" + p["pair_id"])

    # event nominal YES found
    m = load_json("docs/candidate_eventnominal_material_v1.json")
    r = {x["pair_id"]: x for x in
         load_json("docs/candidate_eventnominal_results_v1.json")["pairs"]}
    for p in m["pairs"]:
        s = p["yes"]
        rec = r[p["pair_id"]]["sides"]["yes"]
        if not rec["full_match"]:
            continue
        add(s["sentence_id"], s["sentence"], "supports", 2, "transitive",
            (0, 1, 0), "simple-active",
            DOMAIN_MAP.get(p.get("semantic_subtype", ""), "other"),
            "eventnominal:" + p["pair_id"])

    # benefactive YES present (provider+beneficiary)
    r = load_json("docs/candidate_benefactive_results_v1.json")
    m = load_json("docs/candidate_benefactive_material_v1.json")
    mm = {p["pair_id"]: p for p in m["pairs"]}
    for x in r["pairs"]:
        p = mm[x["pair_id"]]
        s = p["yes"]
        rec = x["sides"]["yes"]
        if rec["n_candidates"] == 0:
            continue
        add(s["sentence_id"], s["sentence"],
            p.get("verb_yes", "provides"), 3, "ditransitive", (0, 1, 1),
            "simple-active", "service", "benefactive:" + p["pair_id"])

    # metaphor literal + found figurative
    m = load_json("docs/candidate_metaphor_material_v1.json")
    r = {x["pair_id"]: x for x in
         load_json("docs/candidate_metaphor_results_v1.json")["pairs"]}
    for p in m["pairs"]:
        for side in ("literal", "figurative"):
            s = p[side]
            rec = r[p["pair_id"]]["sides"][side]
            if rec["outcome"] != "correct":
                continue
            add(s["sentence_id"], s["sentence"], p["verb"], 3, "ditransitive",
                (0, 1, 1), "simple-active",
                DOMAIN_MAP.get("transfer", "transfer"),
                "metaphor:" + p["pair_id"] + ":" + side)

    # interaction YES correct
    m = load_json("docs/candidate_interaction_material_v1.json")
    r = {x["pair_id"]: x for x in
         load_json("docs/candidate_interaction_results_v1.json")["pairs"]}
    for p in m["pairs"]:
        s = p["yes"]
        rec = r[p["pair_id"]]["sides"]["yes"]
        if rec["outcome"] != "correct":
            continue
        add(s["sentence_id"], s["sentence"], "supports", 3, "transitive",
            (0, 1, 0), "interaction-" + p["cell"].lower(), "service",
            "interaction:" + p["pair_id"])

    # agency YES correct
    m = load_json("docs/candidate_agency_material_v1.json")
    r = {x["pair_id"]: x for x in
         load_json("docs/candidate_agency_results_v1.json")["pairs"]}
    for p in m["pairs"]:
        s = p["yes"]
        rec = r[p["pair_id"]]["sides"]["yes"]
        if rec["outcome"] != "correct":
            continue
        add(s["sentence_id"], s["sentence"], "provides", 3, "ditransitive",
            (0, 1, 1), "simple-active", "transfer",
            "agency:" + p["pair_id"])

    # recipient R0/R2 correct + R1 correct
    m = load_json("docs/candidate_recipient_material_v1.json")
    r = {x["pair_id"]: x for x in
         load_json("docs/candidate_recipient_results_v1.json")["pairs"]}
    for p in m["pairs"]:
        s = p["yes"]
        rec = r[p["pair_id"]]["sides"]["yes"]
        if rec["outcome"] != "correct":
            continue
        add(s["sentence_id"], s["sentence"], "provides", 3, "ditransitive",
            (0, 1, 1), "simple-active", "transfer",
            "recipient:" + p["pair_id"])
    return pool


def family(v):
    if v in VERB_FAMILY:
        return VERB_FAMILY[v]
    if v.endswith("s") and v[:-1] in VERB_FAMILY:
        return VERB_FAMILY[v[:-1]]
    return None


def score(fn, c):
    s = 0.0
    if family(fn["verb"]) == family(c["verb"]) and family(fn["verb"]):
        s += 4
    if fn["frame"] == c["frame"]:
        s += 3
    elif fn["arity"] == c["arity"]:
        s += 1.5
    s += 2 * sum(a == b for a, b in zip(fn["pat"], c["pat"])) / 3
    if fn["syntax"] == c["syntax"]:
        s += 2
    if fn["domain"] == c["domain"]:
        s += 1
    return round(s, 3)


BLANK_AXES = ["predicate_lemma", "predicate_eventhood",
              "subject_role", "recipient_role", "theme_role",
              "subject_entity_type", "recipient_entity_type",
              "theme_entity_type", "argument_count", "explicit_argument_count",
              "implicit_argument_count", "syntax_pattern",
              "predicate_argument_compatibility", "proposition_completeness",
              "canonicality", "event_vs_state", "concreteness",
              "semantic_domain", "proposition_density"]

AXIS_ENUMS = {
    "predicate_eventhood": ["EVENT", "STATE", "PROCESS", "RELATION",
                            "AMBIGUOUS", "UNCLEAR"],
    "predicate_argument_compatibility": ["CANONICAL_FRAME",
        "ATTESTED_NONCANONICAL", "SEMANTICALLY_POSSIBLE", "UNLICENSED",
        "UNCLEAR"],
    "proposition_completeness": ["COMPLETE", "PARTIAL", "UNDER_SPECIFIED",
                                 "UNCLEAR"],
    "canonicality": ["P0", "P1", "P2", "P3", "UNCLEAR"],
    "event_vs_state": ["EVENTIVE", "STATIVE", "MIXED", "NOT_APPLICABLE",
                       "UNCLEAR"],
    "proposition_density": ["SINGLE", "MULTIPLE_COORDINATED",
                            "MULTIPLE_EMBEDDED", "MULTIPLE_MIXED",
                            "UNCLEAR"],
}

GUIDE = ("fill axes from sentence+gold ONLY, never from candidate outcomes, "
         "role labels, scores, or probe sources. "
         "proposition_completeness: are predicate and required arguments "
         "explicit or grammatically recoverable (COMPLETE/PARTIAL/"
         "UNDER_SPECIFIED/UNCLEAR). "
         "predicate_argument_compatibility: regular use of predicate with "
         "these roles (CANONICAL_FRAME/ATTESTED_NONCANONICAL/"
         "SEMANTICALLY_POSSIBLE/UNLICENSED/UNCLEAR). "
         "canonicality: descriptive syntactic-semantic category only "
         "(P0 canonical/P1 ordinary non-canonical/P2 indirect-embedded/"
         "P3 structurally unusual/UNCLEAR); P3 must NOT mean difficult "
         "for the generator. "
         "proposition_density counts structural propositions only, not "
         "worthiness. No worthiness variable. No embeddings. "
         "UNCLEAR allowed and stays UNCLEAR.")


def quality_band(score):
    return "HIGH" if score >= 6 else ("MEDIUM" if score >= 4 else "LOW")


def qc_sentence(text):
    """Mechanical only: agreement + termination. No semantic judgment."""
    import re
    toks = text.split()
    if not toks or not text.strip().endswith((".", "?", "!")):
        return "TRUNCATED"
    subj = re.sub(r"[^a-z]", "", toks[1].lower()) if len(toks) > 1 else ""
    verb = re.sub(r"[^a-z]", "", toks[2].lower()) if len(toks) > 2 else ""
    plural_subj = subj.endswith("s") and subj not in (
        "news", "species", "progress", "glass", "class", "this")
    if plural_subj and verb.endswith("s") and not verb.endswith("ss"):
        return "GRAMMAR_ERROR"
    return "OK"


def main() -> int:
    pool = collect_pool()
    print(f"control pool: {len(pool)} successful items")
    items = []
    corp = {s["sentence_id"]: s["text"] for s in
            load_json("docs/production_corpus_v6.json")["sentences"]}
    used = set()
    for fn_id, fn in FN_FEATURES.items():
        ranked = sorted(((score(fn, c), c["sentence_id"], c) for c in pool
                         if c["sentence_id"] not in used),
                        key=lambda t: (-t[0], t[1]))
        top = [(sc, c) for sc, _, c in ranked[:3]]
        used.update(c["sentence_id"] for _, c in top)
        print(fn_id, "verb=" + fn["verb"],
              [(round(sc, 2), c["source"]) for sc, c in top])
        fn_entry = {"item_id": fn_id, "role": "FN", "sentence_id": fn_id,
                    "data_quality": qc_sentence(
                        corp[fn_id]),
                    "axes": {k: "" for k in BLANK_AXES}}
        items.append(fn_entry)
        for sc, c in top:
            e = {"item_id": f"{fn_id}~{c['source']}",
                 "role": "CONTROL", "match_score": sc,
                 "match_quality": quality_band(sc),
                 "match_basis": "structural",
                 "sentence_id": c["sentence_id"], "sentence": c["text"],
                 "data_quality": qc_sentence(c["text"]),
                 "matched_on": {"verb": c["verb"], "frame": c["frame"],
                                "pat": list(c["pat"]), "syntax": c["syntax"],
                                "domain": c["domain"]},
                 "axes": {k: "" for k in BLANK_AXES}}
            items.append(e)
    for e in items:
        if e["role"] == "FN":
            e["sentence"] = corp[e["sentence_id"]]
    out = {"version": "fn_profiling_set_v1",
           "status": "matching_frozen (NOT analysis_ready); axes BLANK for blind annotation; scores are match quality only, never analysis weights",
           "date": "2026-10-04",
           "scoring": "4xpredicate_family + 3xargument_structure + 2xentity_role_pattern + 2xsyntax + 1xsemantic_domain; ties by sentence_id; scoring uses material features only",
           "annotation_guide": GUIDE,
           "axis_enums": AXIS_ENUMS,
           "items": items}
    (ROOT / "docs" / "fn_profiling_set_v1.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"items: {len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
