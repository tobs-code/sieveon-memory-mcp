"""Generate synthetic labeled training data for the query classifier."""

import json
import random
import hashlib

random.seed(42)

TYPES = ["temporal", "factual", "multi-hop", "conversational", "update"]

# ── Entity / Topic pools ──────────────────────────────────────────────
PEOPLE = [
    "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace",
    "Hans", "Iris", "Max", "Lena", "Tom", "Sarah", "David", "Emma",
]
COMPANIES = [
    "Acme Corp", "TechNova", "DataFlow Inc", "BuildRight GmbH",
    "GreenLeaf Analytics", "CloudPeak Systems", "QuantumSoft",
    "Strata Labs", "NexGen AI", "Pyramid AG",
]
PROJECTS = [
    "Project Phoenix", "Project Atlas", "Project Nova", "the migration",
    "the restructuring", "the Q4 rollout", "the dashboard redesign",
]
TOPICS = [
    "pricing", "the roadmap", "the strategy", "the deadline",
    "the partnership", "the acquisition", "layoffs", "the merger",
    "budget planning", "market expansion", "compliance", "security audit",
]
LOCATIONS = [
    "Berlin", "Munich", "New York", "London", "Zurich", "San Francisco",
    "Amsterdam", "Singapore", "Tokyo", "Paris",
]
TEMPORAL_TERMS = [
    "yesterday", "today", "last week", "last month", "last year",
    "this morning", "this quarter", "since Monday", "until Friday",
    "gestern", "heute", "letzte Woche", "letzten Monat", "seit Januar",
]
CHANGE_TERMS = [
    "changed", "updated", "modified", "created", "deleted",
    "geändert", "aktualisiert", "erstellt", "gelöscht",
]
RELATIONS = [
    "works at", "leads", "reports to", "partners with",
    "invested in", "acquired", "collaborates with", "competes with",
]


# ── Template pools per type ───────────────────────────────────────────

TEMPLATES = {
    "temporal": [
        # English
        "When did {person} {change}?",
        "What time did {person} {change}?",
        "Show me the timestamp for {topic}",
        "What happened {term} at {company}?",
        "List all changes {term}",
        "When was the last change to {project}?",
        "Find events {term}",
        "What {change} {term}?",
        "Since when is {person} at {company}?",
        "Until when does {project} run?",
        "Give me the timeline for {project}",
        "Show history for {topic}",
        # German
        "Wann wurde {project} {change_ge}?",
        "Wann hat {person} {change_ge}?",
        "Zeige alle Änderungen {term}",
        "Was ist {term} passiert?",
        "Seit wann arbeitet {person} bei {company}?",
        "Bis wann läuft {project}?",
        "Zeitstempel von {topic}",
        "Wann wurde {company} {change_ge}?",
    ],
    "factual": [
        # English
        "Who is {person}?",
        "What is {company}?",
        "Where is {company} located?",
        "Show me all people at {company}",
        "List the projects {person} is working on",
        "Tell me about {company}",
        "What does {person} do at {company}?",
        "Find information about {project}",
        "Who works at {company}?",
        "Which projects is {person} involved in?",
        "Show details for {project}",
        "What is the status of {project}?",
        # German
        "Wer ist {person}?",
        "Was ist {company}?",
        "Wo befindet sich {company}?",
        "Liste alle Personen bei {company}",
        "Was macht {person} bei {company}?",
        "Zeige Infos zu {project}",
        "Finde Fakten über {topic}",
        "Hat {person} an {project} gearbeitet?",
    ],
    "multi-hop": [
        # English
        "Why did {person} {change}?",
        "What is the relationship between {person} and {person2}?",
        "How is {company} connected to {company2}?",
        "What is the reason for {topic}?",
        "Explain the connection between {person} and {project}",
        "Why was {project} {change_ge}?",
        "How does {person} relate to {company}?",
        "Find the cause of {topic} at {company}",
        "Tell me why {company} {change} {company2}",
        "What impact does {project} have on {company}?",
        # German
        "Warum hat {person} {change_ge}?",
        "Weshalb wurde {project} {change_ge}?",
        "Zeige die Verbindung zwischen {person} und {company}",
        "In welchem Zusammenhang stehen {company} und {project}?",
        "Wie hängen {person} und {person2} zusammen?",
        "Erkläre die Beziehung zwischen {company} und {company2}",
    ],
    "conversational": [
        # English
        "What about {topic}?",
        "Remember when we discussed {topic}?",
        "Did we talk about {project} before?",
        "Can you recall what {person} said about {topic}?",
        "What did we discuss regarding {company}?",
        "Following up on our conversation about {topic}",
        "As we discussed, what about {project}?",
        "Earlier we talked about {company}, any updates?",
        "You mentioned {person} — what's new?",
        "Going back to {project}",
        # German
        "Worüber haben wir bezüglich {project} gesprochen?",
        "Erinnerst du dich an {topic}?",
        "Hatten wir nicht über {company} gesprochen?",
        "Weißt du noch, was {person} über {topic} gesagt hat?",
        "Was war nochmal mit {project}?",
        "Wie besprochen, was ist mit {company}?",
        "Du hast {person} erwähnt — gibt's was Neues?",
    ],
    "update": [
        # English
        "Update {person}'s role to {role}",
        "Change {project}'s status to {status}",
        "Set the deadline for {project} to {deadline}",
        "Modify {person}'s company to {company}",
        "Correct the name of {project}",
        "Set {topic} to {value}",
        "Update {company}'s details",
        "Change {person}'s task to {task}",
        "Overwrite the budget for {project} to {budget}",
        "Modify the status of {company} to active",
        # German
        "Aktualisiere {person}s Rolle auf {role}",
        "Ändere den Status von {project} auf {status}",
        "Setze das Datum für {project} auf {deadline}",
        "Korrigiere {person}s Firma zu {company}",
        "Überschreibe das Budget von {project} auf {budget}",
        "Update {company}s Adresse",
    ],
}

VALUES_POOL = [
    "lead", "manager", "director", "VP", "CTO", "engineer", "consultant",
]
STATUS_POOL = [
    "active", "completed", "on hold", "cancelled", "in progress",
]
DEADLINE_POOL = [
    "next Monday", "Friday", "end of Q3", "December 31st",
]
TASK_POOL = [
    "review the proposal", "sign the contract", "finish the migration",
]
BUDGET_POOL = [
    "$50k", "100k EUR", "200k USD",
]


def _get_change_ge() -> str:
    verb = random.choice(CHANGE_TERMS)
    if verb.endswith("ed"):
        return verb[:-1] if random.random() > 0.5 else verb[:-2] + "et"
    return verb


def _fill(template: str, label: str) -> dict:
    """Render a template with random entities and return a labeled example."""
    kwargs = {
        "person": random.choice(PEOPLE),
        "person2": random.choice(PEOPLE),
        "company": random.choice(COMPANIES),
        "company2": random.choice(COMPANIES),
        "project": random.choice(PROJECTS),
        "topic": random.choice(TOPICS),
        "location": random.choice(LOCATIONS),
        "term": random.choice(TEMPORAL_TERMS),
        "change": random.choice(CHANGE_TERMS),
        "change_ge": _get_change_ge(),
        "role": random.choice(VALUES_POOL),
        "status": random.choice(STATUS_POOL),
        "deadline": random.choice(DEADLINE_POOL),
        "task": random.choice(TASK_POOL),
        "budget": random.choice(BUDGET_POOL),
        "value": f"{random.randint(1, 100)} {random.choice(['days', 'percent', 'EUR', 'USD'])}",
    }
    text = template.format(**kwargs)
    return {"text": text, "type": label, "source": "synthetic"}


def generate(count_per_type: int = 100) -> list[dict]:
    examples = []
    for label in TYPES:
        templates_for_label = TEMPLATES[label]
        for _ in range(count_per_type):
            template = random.choice(templates_for_label)
            examples.append(_fill(template, label))
    random.shuffle(examples)
    return examples


def export_jsonl(examples: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print(f"Wrote {len(examples)} examples to {path}")


def export_stats(examples: list[dict]):
    from collections import Counter
    counts = Counter(ex["type"] for ex in examples)
    print(f"\n{'─' * 50}")
    print("  Generated dataset stats:")
    print(f"{'─' * 50}")
    for t in TYPES:
        print(f"    {t:16s} → {counts[t]:3d}")
    print(f"{'─' * 50}")
    print(f"    {'Total':16s} → {len(examples):3d}")
    print(f"{'─' * 50}")


if __name__ == "__main__":
    data = generate(count_per_type=100)
    export_stats(data)
    export_jsonl(data, "data/training_queries.jsonl")
