"""Test Groq LLM triple extraction for sieveon."""
import os, sys, json, requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.extraction.entity_utils import (
    _GROQ_TRIPLE_PROMPT,
    _GROQ_TRIPLE_EXAMPLES,
    _GROQ_GENERIC_OBJECTS,
    _get_groq_key,
)

# load .env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

GROQ_KEY = _get_groq_key()
if not GROQ_KEY:
    print("❌ GROQ_API_KEY not found in .env")
    sys.exit(1)
print(f"✓ GROQ_API_KEY found: {GROQ_KEY[:8]}...{GROQ_KEY[-4:]}")

TEST_SENTENCES = [
    # (description, text)
    ("Active voice (should work perfectly)",
     "Graydon Hoare created Rust programming language at Mozilla Research."),
    ("Passive voice (failed before)",
     "Rust programming language was created by Graydon Hoare at Mozilla Research."),
    ("Original text from our test",
     "Rust programming language was created by Graydon Hoare at Mozilla Research. "
     "The first stable release was in May 2015. It is known for memory safety "
     "without garbage collection and is used in systems programming, web assembly, "
     "and blockchain development."),
    ("NERD focus — person/org/tech mix",
     "Dr. Sarah Chen is a Nobel Prize winner in Physics 2023 from Stanford University. "
     "She discovered a new quantum computing algorithm called Chen's Algorithm."),
    ("Multiple relationships",
     "Acme Corp is planning to open an office in Barcelona next year."),
]


def call_groq(text):
    messages = [{"role": "system", "content": _GROQ_TRIPLE_PROMPT}]
    for user_text, asst_text in _GROQ_TRIPLE_EXAMPLES:
        messages.append({"role": "user", "content": user_text})
        messages.append({"role": "assistant", "content": asst_text})
    messages.append({"role": "user", "content": text})

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json={"model": "llama-3.1-8b-instant", "messages": messages,
                  "temperature": 0.0, "max_tokens": 1024},
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"


def parse_triples(raw):
    from src.extraction.entity_utils import _GROQ_GENERIC_OBJECTS
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

    # Remove generic AND chain (same logic as entity_utils.py)
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

    # Final filter
    final = []
    for t in triples:
        if t[2].lower() in _GROQ_GENERIC_OBJECTS:
            continue
        if t[0].lower() in _GROQ_GENERIC_OBJECTS:
            continue
        final.append(t)
    return final


# --- run tests ---
all_ok = True
for desc, text in TEST_SENTENCES:
    print(f"\n{'='*60}")
    print(f"📝 {desc}")
    print(f"   Text: {text[:100]}{'...' if len(text)>100 else ''}")
    raw = call_groq(text)
    print(f"   Raw response: {raw[:200] if raw else '(empty)'}")
    triples = parse_triples(raw)
    if triples:
        for s, p, o, c in triples:
            print(f"   ✅  {s}  ─[{p} ({c:.2f})]→  {o}")
    else:
        print("   ⚠️  No triples extracted")
        all_ok = False
    print()

print(f"{'='*60}")
print(f"{'✅ ALL TESTS PASSED' if all_ok else '⚠️  SOME TESTS FAILED'}")
