**Extern.**
Der Router gehört **nicht** als Hauptlogik in SurrealDB, sondern als **eigener Decision-Layer** über dem Store. SurrealDB ist dann dein **Storage + Query Engine + Truth Layer**. Der Router ist die **Policy- und Orchestrierungs-Schicht**.

Warum das die bessere Wahl ist:

* **Der Router ändert sich am schnellsten.** Query-Klassifikation, Schwellenwerte, Kostenpolitik, A/B-Logik, Eval-getriebene Policy-Updates — das willst du unabhängig deployen können.
* **Du brauchst mehr als DB-Logik.** Routing basiert nicht nur auf Feldern, sondern oft auf Heuristiken, Modell-Scores, Budget, Latenz, History und Eval-Signalen.
* **Testing wird viel sauberer.** Extern kannst du Router-Entscheidungen isoliert unit-testen und gegen Benchmarks gegenprüfen.
* **SurrealDB bleibt schlank.** Die DB macht, was sie gut kann: speichern, versionieren, traversieren, indizieren, invalidieren.

Was ich stattdessen machen würde:

**SurrealDB-intern:**

* raw event log
* KG / valid_from / valid_until
* Retrieval primitives
* einfache, deterministische Helper-Funktionen

**Extern:**

* Query-Typ-Erkennung
* Routing-Policy
* Cost-Awareness
* Multi-stage retrieval orchestration
* Eval-Feedback → Policy-Update

**Sinnvolle Ausnahme:**
Ein paar **kleine, statische Router-Regeln** kannst du in SurrealDB als Function ablegen, etwa für harte Guards wie:

* „Wenn temporal_query und recorded_at vorhanden → Raw Log zuerst“
* „Wenn overwrite_detected → KG-Pfad bevorzugen“

Aber das ist dann nur **Fallback- oder Guard-Logik**, nicht der eigentliche Router.

Mein klares Urteil:
**Router extern, SurrealDB als Storage und strukturierte Retrieval-Basis.**
Das ist modularer, testbarer und viel näher an einem echten adaptive memory system.


Dann würde ich das ungefähr so schneiden:

```text
                 USER / AGENT
                       │
                       ▼
┌─────────────────────────────────┐
│        ROUTER SERVICE           │
│---------------------------------│
│ Query Classification            │
│ Cost Policy                     │
│ Temporal Detection              │
│ Multi-hop Detection             │
│ Strategy Selection              │
└─────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────┐
│      RETRIEVAL PLANNER          │
│---------------------------------│
│ Build Retrieval Plan            │
│ Fan-out Queries                 │
│ Merge Results                   │
│ Rerank                          │
│ Confidence Score                │
└─────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
┌────────────┐ ┌────────────┐ ┌────────────┐
│ Event Log  │ │ Knowledge  │ │ Hybrid     │
│            │ │ Graph      │ │ Index      │
└────────────┘ └────────────┘ └────────────┘
         │             │             │
         └─────────────┴─────────────┘
                       │
                       ▼
                 SURREALDB
```

---

# 1. Router Service

Der Router beantwortet nur eine Frage:

> "Welche Art Problem versucht der Nutzer gerade zu lösen?"

Beispielsweise:

| Query                                   | Klasse         |
| --------------------------------------- | -------------- |
| "Wann habe ich X gesagt?"               | temporal       |
| "Wer ist mein Kunde?"                   | factual        |
| "Warum haben wir Y gemacht?"            | multi-hop      |
| "Worüber haben wir gestern gesprochen?" | conversational |
| "Was hat sich geändert?"                | update         |

Der Router erzeugt beispielsweise:

```json
{
  "type": "temporal",
  "confidence": 0.91,
  "cost_budget": "low",
  "strategy": "event_log_first"
}
```

---

# 2. Retrieval Planner

Der Planner übersetzt die Strategie in echte Datenbankoperationen.

Beispiel:

```text
strategy:
    event_log_first

plan:
    1. search event log
    2. retrieve adjacent events
    3. fallback temporal index
    4. query KG if entities detected
```

Oder:

```text
strategy:
    multi_hop

plan:
    1. vector recall
    2. BM25 rerank
    3. graph expansion
    4. merge evidence
```

Der Planner ist der eigentliche "Execution Layer".

---

# 3. SurrealDB als Memory Kernel

Hier lebt alles Persistente.

## Event Log

```sql
DEFINE TABLE event SCHEMALESS;

{
    id,
    timestamp,
    source,
    content,
    embedding
}
```

Append-only.

Nie löschen.

Nie überschreiben.

---

## Knowledge Graph

```text
user
   └── likes
           └── coffee

user
   └── works_at
           └── company
```

Edge:

```json
{
    valid_from: "...",
    valid_until: null
}
```

Änderung:

```sql
UPDATE edge
SET valid_until = time::now();
```

Neue Edge erzeugen.

Historie bleibt erhalten.

---

## Hybrid Retrieval

* Vector Index
* Fulltext
* Zeitindex

Beispiel:

```sql
SELECT *
FROM event
WHERE timestamp > $t
ORDER BY timestamp;
```

oder:

```sql
SELECT *
FROM event
WHERE content @@ "SurrealDB";
```

---

# Warum zwei Services?

Der entscheidende Punkt aus dem Paper ist:

> Storage und Retrieval sind nicht dasselbe.

Viele Memory-Systeme vermischen:

* Speicherung
* Routing
* Reasoning
* Retrieval

in einem einzigen Monolithen.

Das führt dazu, dass jede Änderung alles beeinflusst.

---

# Was der Router zusätzlich lernen kann

Später kannst du den Router durch Evaluation verbessern:

```text
Query
 ↓
Router
 ↓
Result
 ↓
User Feedback
 ↓
Policy Update
```

Beispielsweise:

```text
Temporal queries:
  Event Log:
      93 %

  KG:
      61 %

→ Router erhöht Priorität.
```

Dann wird der Router praktisch ein kleines RL-System.

---

# Surreal-Funktionen würde ich nur für solche Dinge verwenden

```sql
DEFINE FUNCTION fn::active_fact($subject, $predicate) {

    RETURN (
        SELECT *
        FROM edge
        WHERE subject = $subject
          AND predicate = $predicate
          AND valid_until = NONE
    );

};
```

oder:

```sql
DEFINE FUNCTION fn::facts_at($time) {
    ...
};
```

Deterministische Hilfsfunktionen.

Nicht:

* Query Classification
* Policy Learning
* Cost Control
* Routing

---

# Mein persönlicher Architekturvorschlag

```text
Rust
│
├── Router
├── Planner
├── Evaluation
├── Policy Engine
│
└── SurrealDB
     ├── Event Log
     ├── KG
     ├── Vector Search
     └── Temporal Index
```

Warum Rust?

* extrem geringe Latenz
* guter Async-Stack
* leichtgewichtige Services
* hervorragende Parallelisierung
* sehr gute SurrealDB-Integration

Python funktioniert ebenfalls gut, insbesondere für Experimente und Evaluation. Für einen produktiven Agent-Memory-Stack würde ich den Router aber eher in Rust sehen.

Das Interessante ist: Das Paper beschreibt im Grunde genau diese Trennung, ohne sie explizit als Architekturdiagramm auszuformulieren. Die Findings führen fast zwangsläufig zu:

1. adaptive Entscheidungsschicht
2. Retrieval-Orchestrierung
3. mehrere spezialisierte Stores
4. konservative Persistenz

Das ist deutlich näher an einem Betriebssystem für Agent-Memory als an einer klassischen Vektor-Datenbank. 🚀
