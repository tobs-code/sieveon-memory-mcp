# Interne Dokumentation: Agent-Native Memory System

## 📅 Datum: 29.06.2026

---

## 1. Über das Projekt

Dies ist ein **evidence-based Agent Memory System**, direkt abgeleitet aus den Erkenntnissen des Papers "Evaluating Memory Systems for LLM Agents" (Zhou et al., arXiv:2606.24775).

### Die wichtigsten Erkenntnisse aus dem Paper, die wir umgesetzt haben:
1. Kein einzelnes System dominiert alle Szenarien → Workload-adaptive Router
2. Immutables Raw Event Log ist wichtig für Temporal Reasoning
3. Temporal Knowledge Graph mit Logical Invalidation statt Löschen
4. Hybrid Index (Vector + BM25 + Temporal)
5. Coarse-grained Extraktion statt aggressiver Fine-grained (schützt Multi-hop Reasoning)
6. Conservative Maintenance statt globaler Reorganisation (Lazy Flushing)
7. Cost Awareness: Kein Overhead ohne Accuracy-Gewinn
8. Multi-dimensionale Evaluation: Nicht nur F1, sondern Fidelity, Robustness, Stability, Latency, Operationskosten

---

## 2. Projekt-Struktur

```
sms/
├── sdb/                                    # SurrealDB-Ordner
│   ├── schema.surql                        # SurrealDB-Schema (Event Log, KG, Hybrid Index, Gate Log)
│   ├── helper_functions.surql              # SurrealDB Helper Functions (active_fact, etc.)
│   ├── test_data.surql                     # Beispiel-Testdaten
│   ├── docker-compose.yml                  # Docker-Compose für SurrealDB
│   ├── README.md                           # SurrealDB spezifische Anleitung
│   ├── SURREALDB_PYTHON_SDK_DOCS.md        # Python-SDK Infos
│   └── example.py                          # SurrealDB Beispielcode
├── src/
│   ├── extraction/                         # Extraktions-Engine
│   │   ├── coarse_extractor.py             # Coarse-grained Extraktor mit Regex-Entitäten ✅ (fertig!)
│   │   ├── entropy_gate.py                 # Entropy-Gate nach LightMem (Composite Score)
│   │   └── extractor_integration.py        # Integration in SurrealDB (WIP)
│   ├── router/                             # Router & Planner
│   │   ├── policy.py                       # Routing Policy & Query Classifier
│   │   ├── cost_awareness.py               # Cost Tracker (Trackt Latency & Success)
│   ├── planner/
│   │   └── executor.py                     # Retrieval Executor (Strategien ausführen)
│   ├── maintenance/                        # Maintenance Engine
│   │   └── conservative_maintainer.py      # Conservative Maintenance mit Lazy Flushing
│   └── eval/                               # Evaluation
│       └── eval_harness.py                 # Multi-dimensionale Eval-Harness
├── scripts/
│   ├── debug_surrealdb.py                  # Debug-Skript für SurrealDB-Connection
│   ├── debug_surreal_response.py           # Debug-Skript für Response-Format
│   ├── load_schema.py                      # Altes Load-Skript (veraltet)
│   ├── load_schema_simple.py               # Einfaches Load-Skript (veraltet)
│   ├── load_schema_step_by_step.py         # Load-Skript Schritt-für-Schritt
│   ├── load_schema_optimized.py            # ✅ Aktuelles Load-Skript (optimiert)
│   ├── profile_surreal.py                  # Profiling-Skript für SurrealDB-Performance
│   ├── test_localhost_vs_127.py            # Test-Skript (localhost vs 127.0.0.1)
│   └── fix_localhost.py                    # Fix-Skript: Ersetzt localhost → 127.0.0.1
├── test_e2e.py                             # End-to-End Test-Skript ✅ (fertig!)
├── add_test_entities.py                    # Skript zum Hinzufügen von Test-Entitäten (manuell)
├── add_test_event.py                       # Skript zum Hinzufügen von Test-Events (manuell)
├── debug_surrealdb_queries.py              # Debug-Skript zum Testen von SurrealDB-Queries
├── test_regex.py                           # Test-Skript für die Coarse Extractor Regex-Muster
├── debug_classifier.py                     # Debug-Skript für den Query Classifier
├── test_classifier_english.py              # Test-Skript für englische Queries
├── requirements.txt                        # Python-Abhängigkeiten
├── plan.md                                 # Ursprünglicher Plan aus dem Paper
├── plan-router.md                          # Router-spezifischer Plan
├── IMPLEMENTATION_PLAN.md                  # Detaillierter Umsetzungsplan
├── QUICKSTART.md                           # Quickstart-Anleitung
└── INTERNES_README.md                      # ⬅️ Diese Datei!
```

---

## 3. SurrealDB-Schema (sdb/schema.surql)

### 3.1 Tables & Fields:
| Table       | Zweck                                                                 | Wichtigste Felder                          |
|-------------|-----------------------------------------------------------------------|-------------------------------------------|
| event       | Immutable Raw Event Log (Single Source of Truth für Temporal)        | id, timestamp, source, content, embedding |
| entity      | Entitäten im Knowledge Graph                                          | id, name, type, metadata                  |
| fact        | Relation zwischen Entitäten (mit Temporal Validity!)                 | id, valid_from, valid_until, source_event |
| gate_log    | Loggt alle Entropy-Gate-Entscheidungen (für spätere Kalibrierung!)   | id, content_hash, text_score, novelty, gate_score, decision, ts |

### 3.2 Indizes:
- **Event Log**: `event_timestamp`, `event_source`, `event_content_ft` (Full-Text)
- **Knowledge Graph**: `entity_name`, `entity_type`, `fact_valid`, `fact_subject`, `fact_object`
- **Gate Log**: `gate_log_ts`, `gate_log_decision`

---

## 4. Die wichtigsten Komponenten (mit Code-Links)

### 4.1 Embedding Service (src/extraction/embedding_service.py) ⭐⭐⭐
Modularer Embedding-Service, der leicht erweitert werden kann!
- Aktuell: Sentence-Transformers mit `nomic-ai/nomic-embed-text-v1.5`
- Einheitliches Interface für alle Backends (OpenAI, Mistral, etc. lassen sich später ergänzen)
- Singleton-Pattern (Model wird nur **einmal geladen**!)
- Unterstützt Batch-Embeddings

### 4.2 Entropy Gate (src/extraction/entropy_gate.py) ⭐⭐⭐
Nach **LightMem's Ansatz**:
- **Composite Score**: `α * text_score + β * novelty`
  - `text_score`: Normalisierte Shannon-Entropie auf Zeichenebene (0-1)
  - `novelty`: **Echte Embedding-Novelty**: `1 - max_similarity` (via In-Memory Vector DB!)
- **Threshold**: Standard: 0.55
- **min_length**: 10 Zeichen → kürzere Texte ("ja", "danke") werden direkt übersprungen
- **In-Memory Vector DB**: Für schnelle Cosine Similarity Suche (bis SurrealDB Vector Index stabil ist)
- **Pipeline**:
  1. **Immer**: Raw Event Log schreiben
  2. Embedding berechnen
  3. Vector DB aktualisieren
  4. Gate prüfen → decision: extract/skip
  5. Gate-Log schreiben (für spätere Kalibrierung!)
  6. Falls extract: Extraktion starten ✅ (fertig implementiert!)

#### Konfiguration (EntropyGateConfig):
```python
alpha: float = 0.35       # Gewicht Text-Entropy
beta: float = 0.65        # Gewicht Embedding-Novelty
threshold: float = 0.55   # Schwellwert für Gate-Entscheidung
min_length: int = 10      # Mindestlänge für Extraktion
```

---

### 4.3 Coarse-Grained Extractor (src/extraction/coarse_extractor.py) ⭐⭐
- Extrahiert Personen und Organisationen aus Events (keine aggressive Fine-Grained Extraktion!)
  - **Personen**: Vor- und Nachname mit Großbuchstabe am Anfang, optional mit Mittelname/Initial
  - **Organisationen**: Zwei Varianten:
    1. Namen mit Wörtern die großgeschrieben sind + bekannte Suffixe ("Inc", "Corp", "GmbH", "AG", "Ltd", "SA")
    2. Einwort-Namen wie "TechGmbH" ohne Leerzeichen
- **Extraktionsreihenfolge**: Erst Organisationen, dann Personen, um Doppelerkennung zu vermeiden!
- **Regeln aus dem Paper: Coarse-Grained statt Fine-Grained, um Multi-Hop Reasoning zu schonen!
- **Regex Muster aus Web-Suche (improved patterns for real-world data)!

---

### 4.4 Query Classifier & Routing Policy (src/extraction/classifier.py + src/router/policy.py)
- **Query Classifier**: Regel-basierte Klassifikation von Queries (Deutsch + Englisch!)
  - **Zweisprachig**: Unterstützt sowohl deutsche als auch englische Patterns!
  - **Patterns mit Word Boundaries**: Keine falschen Treffer mehr (z. B. "wer" passt nicht mehr "what"!)
  - **Prioritätsliste**: Bei gleicher Punktzahl gibt es eine festgelegte Priorität:
    1. `update`
    2. `multi-hop`
    3. `conversational`
    4. `temporal`
    5. `factual`
  - **Confidence-Berechnung**: Auf Margin umgestellt! (Abstand zwischen Besten und Zweitbesten, statt Relativscore!)
  - **Gewichtung**: Conversational & Update Patterns bekommen Score 2 statt 1!
- **Query Klassen**:
  - `temporal`: Enthält "wann", "heute", "gestern", "seit", "vor", "dann", "when", "yesterday", "today", etc.
  - `factual`: Enthält "wer", "was", "welche", "wo", "welcher", "who", "what", "which", "where", etc.
  - `multi-hop`: Enthält "warum", "wie", "weshalb", "wegen", "why", "because", etc.
  - `conversational`: Enthält "worüber", "gesprochen", "talk about", "remember", etc.
  - `update`: Enthält "aktualisiere", "update", "change", etc.
- **Routing Policy**: Wählt Retrieval-Strategie basierend auf Klasse:
  | Query Klasse | Strategy                     | Cost-Budget |
  |--------------|------------------------------|-------------|
  | temporal     | event_log_first              | low         |
  | factual      | knowledge_graph_first        | low         |
  | multi-hop    | hybrid_with_graph_expansion  | high        |
  | conversational | composite_kg_vector         | medium      |
  | update       | knowledge_graph_with_invalidation | high |
  | fallback     | hybrid_fallback              | medium      |

---

### 4.5 Conservative Maintenance Engine (src/maintenance/conservative_maintainer.py)
- Keine globalen Reorganisationen!
- Lazy Flushing mit Debounce
- Patch-Updates statt kompletter Neuschreibung
- Logical Invalidation (SET valid_until statt DELETE!)

---

### 4.6 Cost Awareness Layer (src/router/cost_awareness.py)
- Trackt pro Strategy:
  - Latency
  - Number of Queries
  - Success Rate
- Speichert Metriken in `cost_metrics.json`
- Bietet `get_cheaper_alternative()`

---

### 4.7 Eval Harness (src/eval/eval_harness.py)
- Misst die 5 Paper-Dimensionen: Fidelity, Robustness, Stability, Latency, Operationskosten
- Test-Cases definieren
- Trackt Metriken automatisch via Cost Awareness Layer

---

## 5. Wichtige Lessons Learned (Was wir heute herausgefunden haben!)

### 5.1 Performance-Problem: localhost vs. 127.0.0.1
- **Problem**: Jeder Request an SurrealDB dauerte **21 Sekunden**!
- **Ursache**: DNS-Lookup-Problem von `localhost` unter Windows!
- **Lösung**: Ersetze **`localhost` → `127.0.0.1`** in allen Skripten!
- **Ergebnis**: Jetzt dauert jeder Request nur **0.05 Sekunden**!

→ Alle relevanten Dateien sind bereits gefixt!

---

### 5.2 Regex-Muster & Extraktionsreihenfolge
- **Verbesserungen via Web-Suche**: Bessere Pattern für Personen- & Organisationserkennung!
- **Extraktionsreihenfolge**: ERST Organisationen, DANN Personen extrahieren!
  - Grund: Sonst könnten Organisationsteile als Personen erkannt werden!
- **Einwort-Organisationen**: Extrahiert auch Namen wie "TechGmbH" ohne Leerzeichen (aber mit Suffix im Namen!)

---

### 5.3 Query Classifier Verbesserungen
- **Zweisprachig**: Deutsch + Englisch support!
- **Word Boundaries**: Alle Patterns mit \b umschlossen → keine falschen Treffer!
- **Margin Confidence**: Kein Relativscore mehr, sondern Abstand zwischen Bestem und Zweitbestem!
- **Prioritätsliste**: Bei gleicher Punktzahl gewinnt die wichtigere Klasse!
- **Gewichtung**: Conversational & Update Patterns bekommen Score 2 statt 1!

---

## 6. Wie man es nutzt (Schritt-für-Schritt)

### 6.1 SurrealDB starten
```bash
cd sdb
docker-compose up -d
```

### 6.2 Schema & Testdaten laden
```bash
cd ..
python scripts/load_schema_optimized.py
```

### 6.3 Entropy Gate testen
```bash
python src/extraction/entropy_gate.py
```

### 6.4 End-to-End Test
```bash
python test_e2e.py
```

### 6.5 Evaluation Harness testen
```bash
python src/eval/eval_harness.py
```

### 6.6 SurrealDB manuell connecten (optional)
```bash
cd sdb
docker exec -it agent-memory-surrealdb /surreal sql --conn http://127.0.0.1:8000 --user root --pass root --ns agent_memory --db agent_memory
```

---

## 7. Was fehlt noch / Was ist WIP (Work in Progress)?

1. ✅ **Coarse-Grained Extraktion fertiggestellt**: Wenn das Gate "extract" sagt, extrahiert es jetzt Entitäten (Personen, Organisationen) und schreibt sie in den Knowledge Graph!
2. ✅ **Echte Embedding-Novelty**: Funktioniert jetzt über In-Memory Vector DB!
3. **Eval Harness MemoryData Integration**: Die Benchmark-Suite aus dem Paper anbinden!
4. **Router Feedback-Optimierung**: Eval-Metriken verwenden, um die Routing Policy automatisch zu verbessern!
5. **Rust-Implementierung**: Für Production-Use wäre ein Router in Rust besser (Performance!).

---

## 8. Datei-Referenz Cheat Sheet

| Aufgabe | Datei |
|---------|-------|
| SurrealDB-Schema | `sdb/schema.surql` |
| SurrealDB Helper Functions | `sdb/helper_functions.surql` |
| Entropy Gate | `src/extraction/entropy_gate.py` |
| Coarse Extractor (Entitäten) | `src/extraction/coarse_extractor.py` |
| Query Classifier (DE + EN) | `src/extraction/classifier.py` |
| Routing Policy | `src/router/policy.py` |
| Cost Tracker | `src/router/cost_awareness.py` |
| Maintenance Engine | `src/maintenance/conservative_maintainer.py` |
| Eval Harness | `src/eval/eval_harness.py` |
| Schema laden | `scripts/load_schema_optimized.py` |
| E2E Test | `test_e2e.py` |
| SurrealDB-Connection testen | `scripts/debug_surrealdb.py` |
| Regex-Extraktion testen | `test_regex.py` |
| Query Classifier debuggen | `debug_classifier.py` |
| Englische Queries testen | `test_classifier_english.py` |
| Test-Entities manuell hinzufügen | `add_test_entities.py` |
| Test-Events manuell hinzufügen | `add_test_event.py` |
| SurrealDB-Queries debuggen | `debug_surrealdb_queries.py` |

---

## 9. Kurze Erinnerung an die Architektur
```
USER / AGENT
     |
     ▼
┌─────────────────────┐
│  Router Service     │ ← Query Classifier, Cost-Awareness
└─────────────────────┘
     |
     ▼
┌─────────────────────┐
│ Retrieval Planner   │ ← Baut Plan, führt Strategien aus
└─────────────────────┘
     |
┌────┴────┬───────────┐
▼         ▼           ▼
Event Log KG       Hybrid Index
│         │           │
└─────────┴───────────┘
          |
          ▼
      SurrealDB
          |
┌─────────┴───────────┐
▼                     ▼
Extraktion (Coarse) Maintenance
```
