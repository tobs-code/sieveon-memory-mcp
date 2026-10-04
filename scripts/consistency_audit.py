"""Consistency audit: reproduce every headline number from frozen artifacts.

Contract (20 invariants, fixed expectations, not self-comparison):
 batch6: records=156, ACCEPT=6, gold YES/UNCLEAR/NO=17/7/126
 position: 40/40 full matches
 lexical: 22/22 YES full matches
 complexity: 23/24 YES full matches
 anaphora: 27/28 relation-present
 event-nominal: 16/16 YES full matches
 benefactive: 16/16 YES with candidates
 metaphor: M0 8/8 correct, M1-YES* figurative present 2/3, M3 figurative 5/6
 interaction: 16/16 YES correct
 agency: 16/16 YES correct
 recipient: R0/R2/R1 correct = 8/8/5
 density: 12/12 YES correct
 implicit-agent: 12/12 YES present
 implicit-theme: overt 7/8 and dropped 7/8 correct
 theme-role: T1 8/8 correct, T2 concrete 1/4 and nonproto 3/4 correct

Exit 0 iff all invariants hold, nonzero otherwise (CI-usable).
New probes MUST extend this contract when they add headline numbers.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "docs"
fails = []


def check(name, got, exp):
    ok = got == exp
    print(("OK  " if ok else "FAIL"), name, "=", got,
          "" if ok else f"(expected {exp})")
    if not ok:
        fails.append(name)


def load(f):
    return json.load(open(ROOT / f, encoding="utf-8"))


def main() -> int:
    import collections
    run = [json.loads(line) for line in
           open(ROOT / "production_run_v6.jsonl", encoding="utf-8")
           if line.strip()]
    check("b6 records", len(run), 156)
    check("b6 accept",
          sum(1 for r in run if r.get("final_status") == "ACCEPT"), 6)
    gold = load("batch6_gold_v1.json")
    c1 = collections.Counter(e["provides_gold"] for e in gold["step1"])
    check("b6 gold", (c1["YES"], c1["UNCLEAR"], c1["NO"]), (17, 7, 126))

    r = load("candidate_probe_results_v1.json")["pairs"]
    check("position full", sum(1 for p in r for v in ("a", "b")
                                if p["variants"][v]["full_match"]), 40)

    r = load("candidate_lexical_results_v1.json")["pairs"]
    check("lexical YES full",
          sum(1 for p in r if p["sides"]["yes"]["full_match"]), 22)

    r = load("candidate_complexity_results_v1.json")["pairs"]
    check("complexity YES full",
          sum(1 for p in r if p["sides"]["yes"]["full_match"]), 23)

    r = load("candidate_anaphora_results_v1.json")["pairs"]
    present = sum(1 for p in r if p["sides"]["yes"]["outcome"] in
                  ("correct", "anaphoric", "resolved"))
    check("anaphora present", present, 27)

    r = load("candidate_eventnominal_results_v1.json")["pairs"]
    check("eventnom YES full",
          sum(1 for p in r if p["sides"]["yes"]["full_match"]), 16)

    r = load("candidate_benefactive_results_v1.json")["pairs"]
    check("benefactive YES n_cands>0",
          sum(1 for p in r if p["sides"]["yes"]["n_candidates"] > 0), 16)

    r = load("candidate_metaphor_results_v1.json")["pairs"]
    m0 = [p for p in r if p["class"] == "M0"]
    m1 = [p for p in r if p["class"] == "M1"]
    m3 = [p for p in r if p["class"] == "M3"]
    check("metaphor M0 correct",
          sum(1 for p in m0 for s in ("literal", "figurative")
              if p["sides"][s]["outcome"] == "correct"), 8)
    m1fig = [p["sides"]["figurative"] for p in m1]
    check("metaphor M1fig YES* present",
          sum(1 for d in m1fig[:3] if d["n_candidates"] > 0), 2)
    check("metaphor M3 fig correct",
          sum(1 for p in m3
              if p["sides"]["figurative"]["outcome"] == "correct"), 5)

    r = load("candidate_interaction_results_v1.json")["pairs"]
    check("interaction YES correct",
          sum(1 for p in r if p["sides"]["yes"]["outcome"] == "correct"), 16)

    r = load("candidate_agency_results_v1.json")["pairs"]
    check("agency YES correct",
          sum(1 for p in r if p["sides"]["yes"]["outcome"] == "correct"), 16)

    r = load("candidate_recipient_results_v1.json")["pairs"]
    by = collections.defaultdict(int)
    for p in r:
        if p["sides"]["yes"]["outcome"] == "correct":
            by[p["condition"]] += 1
    check("recipient R0/R2/R1", (by["R0"], by["R2"], by["R1"]), (8, 8, 5))

    r = load("candidate_density_results_v1.json")["pairs"]
    check("density YES correct",
          sum(1 for p in r if p["sides"]["yes"]["outcome"] == "correct"), 12)

    r = load("candidate_implicit_agent_results_v1.json")["pairs"]
    check("implicit-agent YES present",
          sum(1 for p in r if p["sides"]["yes"]["n_candidates"] > 0), 12)

    r = load("candidate_implicit_theme_results_v1.json")["pairs"]
    ov = [p for p in r if p["sides"]["overt"]["outcome"] == "correct"]
    dr = [p for p in r if p["sides"]["dropped"]["outcome"] == "correct"]
    check("implicit-theme overt/dropped", (len(ov), len(dr)), (7, 7))

    r = load("candidate_themerole_results_v1.json")["pairs"]
    t1 = [p for p in r if p["subprobe"] == "T1"]
    t2 = [p for p in r if p["subprobe"] == "T2"]
    check("themerole T1 correct",
          sum(1 for p in t1 for s in ("concrete", "nonproto")
              if p["sides"][s]["outcome"] == "correct"), 8)
    t2c = sum(1 for p in t2
              if p["sides"]["concrete"]["outcome"] == "correct")
    t2n = sum(1 for p in t2
              if p["sides"]["nonproto"]["outcome"] == "correct")
    check("themerole T2 concrete/nonproto", (t2c, t2n), (1, 3))

    print("FAILURES:", fails if fails else "NONE")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
