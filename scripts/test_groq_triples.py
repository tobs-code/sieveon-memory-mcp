"""Test Groq LLM triple extraction for sieveon — Modellvergleich."""
import os, sys, json, time, requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.extraction.entity_utils import (
    _GROQ_TRIPLE_PROMPT,
    _GROQ_TRIPLE_EXAMPLES,
    _GROQ_GENERIC_OBJECTS,
    _get_groq_key,
)
from dotenv import load_dotenv

load_dotenv()

GROQ_KEY = _get_groq_key()
if not GROQ_KEY:
    print("❌ GROQ_API_KEY not found in .env")
    sys.exit(1)
print(f"✓ GROQ_API_KEY: {GROQ_KEY[:8]}...{GROQ_KEY[-4:]}\n")

TEST_CASES = [
    ("Aktiv (einfach)", "Graydon Hoare created Rust at Mozilla Research."),
    ("Passiv (wichtig!)", "Rust was created by Graydon Hoare at Mozilla Research."),
    ("Passiv + follow-up Sätze",
     "Rust was created by Graydon Hoare at Mozilla Research. "
     "The first stable release was in May 2015. "
     "Rust is known for memory safety without garbage collection."),
    ("Person/Org/Tech gemischt",
     "Dr. Sarah Chen is a Nobel Prize winner in Physics 2023 from Stanford University. "
     "She discovered a new quantum algorithm called Chen's Algorithm."),
    ("Multiple Relationen",
     "Acme Corp is planning to open an office in Barcelona next year. "
     "John Doe leads the expansion team."),
    ("Sieveon-relevant",
     "Tobias built the Sieveon memory system. "
     "It uses SurrealDB as database and Qdrant for vector search. "
     "The Entity Extractor extracts entities and relationships from text."),
    ("Gemischte Tempora",
     "Apple held WWDC 2026 at Apple Park. "
     "Tim Cook introduced Apple Intelligence. "
     "Meta is planning to build a data center in Spain."),
    ("langer Text mit vielen Entitäten",
     "Satya Nadella is CEO of Microsoft. "
     "He met with Sundar Pichai at Davos. "
     "Microsoft acquired Activision Blizzard and invested in OpenAI. "
     "Sam Altman founded OpenAI and leads it as CEO. "
     "Elon Musk leads Tesla, SpaceX, and xAI."),
]

MODELS = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]


def call_groq(text: str, model: str) -> str:
    messages = [{"role": "system", "content": _GROQ_TRIPLE_PROMPT}]
    for user_text, asst_text in _GROQ_TRIPLE_EXAMPLES:
        messages.append({"role": "user", "content": user_text})
        messages.append({"role": "assistant", "content": asst_text})
    messages.append({"role": "user", "content": text})
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json={"model": model, "messages": messages,
                  "temperature": 0.0, "max_tokens": 2048},
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"


def parse_triples(raw: str) -> list[tuple]:
    triples = []
    seen = set()
    for line in raw.split("\n"):
        line = line.strip()
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            continue
        subj, pred, obj = parts[0], parts[1].lower(), parts[2]
        if len(subj) < 2 or len(obj) < 2:
            continue
        if subj.lower() == obj.lower():
            continue
        conf = 0.7
        if len(parts) >= 4:
            try:
                conf = min(1.0, max(0.0, float(parts[3])))
            except ValueError:
                pass
        key = f"{subj.lower()}|{pred}|{obj.lower()}"
        if key in seen:
            continue
        seen.add(key)
        triples.append((subj, pred, obj, conf))

    # Generic filter (selbe Logik wie entity_utils.py)
    generic_entities = {}
    for t in list(triples):
        sl, ol = t[0].lower(), t[2].lower()
        if ol in _GROQ_GENERIC_OBJECTS:
            generic_entities.setdefault(ol, []).append(t)
            triples.remove(t)
        elif sl in _GROQ_GENERIC_OBJECTS:
            generic_entities.setdefault(sl, []).append(t)
            triples.remove(t)

    generic_outgoing = {}
    for gen_name, gen_triples in generic_entities.items():
        for gt in gen_triples:
            if gt[1] == "located_in" and gt[2].lower() != gen_name:
                generic_outgoing.setdefault(gen_name, []).append(gt[2])
            elif gt[1] == "located_in" and gt[0].lower() != gen_name:
                generic_outgoing.setdefault(gen_name, []).append(gt[0])

    rewired = []
    for gen_name, gen_triples in generic_entities.items():
        targets = generic_outgoing.get(gen_name, [])
        if not targets:
            continue
        for gt in gen_triples:
            if gt[2].lower() == gen_name:
                for target_obj in targets:
                    chain_key = f"{gt[0].lower()}|{gt[1]}|{target_obj.lower()}"
                    if chain_key not in seen:
                        seen.add(chain_key)
                        rewired.append((gt[0], gt[1], target_obj, round(gt[3] * 0.9, 4)))

    triples.extend(rewired)

    final = []
    for t in triples:
        if t[2].lower() in _GROQ_GENERIC_OBJECTS:
            continue
        if t[0].lower() in _GROQ_GENERIC_OBJECTS:
            continue
        final.append(t)
    return final


# ---------- Haupttest ----------
results = {}

for model in MODELS:
    print(f"{'='*70}")
    print(f"  Modell: {model}")
    print(f"{'='*70}")
    total_found = 0
    total_expected_min = 0

    for desc, text in TEST_CASES:
        print(f"\n  ── {desc} ──")
        print(f"     Input: {text[:100]}{'...' if len(text)>100 else ''}")

        t0 = time.time()
        raw = call_groq(text, model)
        elapsed = time.time() - t0

        triples = parse_triples(raw)
        total_found += len(triples)
        print(f"     ⏱  {elapsed:.1f}s  |  Triples: {len(triples)}")
        if triples:
            for s, p, o, c in triples:
                print(f"     ✅  {s}  ─[{p} ({c:.2f})]→  {o}")
        else:
            print(f"     ⚠️  Keine Triples")
            if "ERROR" in raw:
                print(f"     ❌  API Error: {raw[:150]}")

    results[model] = {
        "total_triples": total_found,
        "test_count": len(TEST_CASES),
    }
    print()

# ---------- Vergleich ----------
print(f"{'='*70}")
print(f"  VERGLEICH")
print(f"{'='*70}")
m1, m2 = MODELS
r1 = results[m1]
r2 = results[m2]
print(f"  {m1:<35s}: {r1['total_triples']} Triples total")
print(f"  {m2:<35s}: {r2['total_triples']} Triples total")
diff = r2['total_triples'] - r1['total_triples']
pct = (diff / max(r1['total_triples'], 1)) * 100
print(f"  {'':>35s}  {'+' if diff>0 else ''}{diff} ({pct:+.0f}%)")
print(f"\n  Empfehlung: {'70B (bessere Qualität)' if diff > 0 else '8B reicht (schneller, billiger)'}")
