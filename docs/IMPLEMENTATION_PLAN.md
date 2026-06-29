# Detaillierter Umsetzungsplan: Agent-Native Memory System

## Überblick

Dieser Plan beschreibt die schrittweise Implementierung eines **evidence-basierten Memory-Systems**, direkt abgeleitet aus den 6 Paper-Findings (Zhou et al. 2026). Die Architektur folgt dem Prinzip: **"Router extern, SurrealDB als Kernel"**.

---

## Technologie-Stack

| Layer               | Technologie                                                                 |
|---------------------|-----------------------------------------------------------------------------|
| Storage & Query     | SurrealDB 3                                                                 |
| Router & Planner    | Rust (für Performance) + Python (für Experimente/Eval)                      |
| Embeddings          | OpenAI / Sentence-Transformers (flexibel)                                    |
| Eval-Benchmarks     | MemoryData (github.com/OpenDataBox/MemoryData)                              |
| Deployment          | Docker + Docker Compose                                                      |

---

## Projekt-Struktur

```
sms/
├── sdb/                           # SurrealDB Konfiguration & Schema
│   ├── docker-compose.yml
│   ├── schema.surql
│   └── helper_functions.surql
├── src/
│   ├── router/                    # Rust: Router Service
│   │   ├── classifier.rs          # Query-Klassifikation
│   │   ├── policy.rs              # Routing-Policy
│   │   └── main.rs
│   ├── planner/                   # Rust: Retrieval Planner
│   │   ├── plan_builder.rs
│   │   ├── executor.rs
│   │   └── main.rs
│   ├── extraction/                # Python/Rust: Coarse-grained Extraction
│   │   └── extractor.py
│   ├── maintenance/               # Rust: Conservative Maintenance Engine
│   │   └── maintainer.rs
│   └── eval/                      # Python: Multi-dim Eval Harness
│       ├── harness.py
│       └── benchmarks/
├── scripts/
│   ├── start_surreal.sh
│   ├── load_schema.sh
│   └── run_benchmarks.sh
└── docs/
    └── api.md
```

---

## Phase 1: SurrealDB Schema & Kernel (Hohe Priorität)

**Ziel**: Die "Truth Layer"-Infrastruktur in SurrealDB aufbauen.

### Tasks

1. **Projekt-Struktur erstellen**
   - Ordner `sms/sdb/` finalisieren
   - Ordner `sms/src/` und Unterordner anlegen

2. **Event Log Tabelle definieren**
   - Append-only, immutable by convention
   - Felder: `id`, `timestamp`, `source`, `content`, `embedding`, `metadata`
   - Indizes: `timestamp`, `source`, Fulltext auf `content`, Vector auf `embedding`

3. **Knowledge Graph mit Temporal Validity definieren**
   - Knotentabellen: `entity`, `fact`
   - Kanten: `RELATE` mit `valid_from`, `valid_until`
   - Logische Invalidierung statt physischem Löschen

4. **Hybrid Index Struktur aufbauen**
   - Vector Index für semantische Suche
   - BM25 Fulltext Index für Keyword-Präzision
   - Temporal Index für Zeitreihen-Retrieval

5. **SurrealDB Helper Functions definieren**
   - `fn::active_fact($subject, $predicate)`: Holt aktive Facts
   - `fn::facts_at($time)`: Facts zu bestimmtem Zeitpunkt
   - `fn::temporal_context($entity, $window)`: Temporaler Kontext

### Deliverables

- `sms/sdb/schema.surql`: Komplettes Schema
- `sms/sdb/helper_functions.surql`: Helper-Funktionen
- `sms/sdb/docker-compose.yml`: Finalisierte Docker-Konfiguration
- `sms/scripts/start_surreal.sh`: Start-Skript
- `sms/scripts/load_schema.sh`: Schema-Load-Skript

---

## Phase 2: Query Classifier & Workload-adaptive Router (Hohe Priorität)

**Ziel**: Der externe Decision-Layer, der Query-Typen erkennt und Strategien wählt.

### Tasks

1. **Query Classifier implementieren (Python für schnelle Experimente)**
   - Trainingsdaten: Beispiele für temporal/factual/multi-hop/conversational/update
   - Initial: Rule-based + einfache Embedding-basierte Klassifikation
   - Später: LLM-basiert (gpt-4o-mini / llama-3.1)

2. **Router Policy Engine (Rust für Performance)**
   - Input: Klassifizierter Query, Cost-Budget, History
   - Output: Retrieval-Strategy (z.B. `event_log_first`, `multi_hop_hybrid`)
   - Config-Datei für Schwellwerte & Prioritäten

3. **Router Service API (Rust)**
   - gRPC oder REST-API Endpunkt: `/classify`, `/route`
   - Async, low-latency

### Deliverables

- `sms/src/router/classifier.rs/py`: Query-Klassifikator
- `sms/src/router/policy.rs`: Routing-Policy
- `sms/src/router/main.rs`: Router Service
- `sms/src/router/config.toml`: Policy-Konfiguration

---

## Phase 3: Retrieval Planner (Hohe Priorität)

**Ziel**: Übersetzt die Strategie in echte SurrealDB-Operationen.

### Tasks

1. **Plan Builder (Rust)**
   - Nimmt Strategy-Entscheidung des Routers
   - Baut einen schrittweisen Retrieval-Plan (z.B. "1. Vector Recall, 2. BM25 Rerank, 3. Graph Expansion")

2. **Executor (Rust)**
   - Führt den Plan gegen SurrealDB aus
   - Fan-out Queries, Merge Results, Reranking, Confidence-Scoring

3. **Planner Service API**
   - Endpunkt: `/plan_and_execute`
   - Nimmt Query & Strategy, gibt Final-Result zurück

### Deliverables

- `sms/src/planner/plan_builder.rs`: Plan-Logik
- `sms/src/planner/executor.rs`: Ausführungs-Engine
- `sms/src/planner/main.rs`: Planner Service

---

## Phase 4: Multi-dim Eval Harness & MemoryData Integration (Hohe Priorität)

**Ziel**: Evaluiert das System gegen die gleichen Benchmarks wie das Paper.

### Tasks

1. **MemoryData Repository klonen & untersuchen**
   - github.com/OpenDataBox/MemoryData
   - 11 Datasets & Workloads verstehen

2. **Eval Harness implementieren (Python)**
   - Misst die 5 Paper-Dimensionen:
     1. Retrieval-Fidelity
     2. Update-Robustness
     3. Long-Horizon-Stability
     4. Latenz
     5. Operationskosten

3. **SurrealDB-System an MemoryData andocken**
   - Adapter für die Benchmark-Schnittstelle
   - Automatisierte Benchmark-Läufe

### Deliverables

- `sms/src/eval/harness.py`: Eval-Harness
- `sms/src/eval/benchmarks/`: MemoryData-Adapter
- `sms/scripts/run_benchmarks.sh`: Benchmark-Skript

---

## Phase 5: Coarse-grained Extraction Engine (Mittlere Priorität)

**Ziel**: Konservative Extraktion ohne Multi-Hop-Zerstörung.

### Tasks

1. **Extraction Logic (Python/Rust)**
   - Schema-free Extraction mit Entropy-Gating (LightMem-Ansatz)
   - Kein aggressives Fine-Grain-Parsing
   - Extrahiert nur, wenn Kontext es eindeutig rechtfertigt

2. **Integration mit Router/Planner**
   - Extraktion als optional Step im Retrieval-Plan
   - Cost-Awareness: Extraktion nur, wenn Nutzen > Kosten

### Deliverables

- `sms/src/extraction/extractor.py/rs`: Extraktions-Engine
- Integration in den Planner

---

## Phase 6: Conservative Maintenance Engine (Mittlere Priorität)

**Ziel**: Lokale, kosteneffiziente Maintenance ohne globale Reorganisation.

### Tasks

1. **Maintenance Logic (Rust)**
   - Lazy Flushing mit Debounce
   - Patch-Updates auf dem KG statt kompletter Neuschreibung
   - Keine globalen Reindexierungen

2. **Maintenance Service**
   - Hintergrund-Service, der periodisch (oder bei Bedarf) läuft
   - Logging & Monitoring der Maintenance-Operationen

### Deliverables

- `sms/src/maintenance/maintainer.rs`: Maintenance-Engine
- `sms/src/maintenance/main.rs`: Maintenance Service

---

## Phase 7: Cost-Awareness Layer (Mittlere Priorität)

**Ziel**: Dynamische Entscheidung zwischen leichtgewichtig & strukturiert.

### Tasks

1. **Cost-Tracking implementieren**
   - Misst Latenz & Kosten pro Query-Typ & Store
   - Sammelt Metriken in SurrealDB oder Prometheus

2. **Cost-Policy im Router integrieren**
   - Wenn teurerer Layer keinen Accuracy-Gewinn → Fallback auf günstigeren
   - Feedback-Loop: Eval-Ergebnisse updaten die Cost-Policy

### Deliverables

- Erweiterungen am Router & Policy-Engine
- Cost-Tracking-Modul

---

## Phase 8: End-to-End Integration & Test (Hohe Priorität)

**Ziel**: Alles zusammenführen & testen.

### Tasks

1. **E2E-Test-Suite schreiben**
   - Unit-Tests für jede Komponente
   - Integration-Tests für den vollen Flow
   - Benchmark-Tests gegen MemoryData

2. **Docker Compose Stack für alles**
   - SurrealDB + Router + Planner + Maintenance + Eval
   - Ein-Klick-Start

3. **Dokumentation finalisieren**
   - API-Dokumentation
   - Setup-Guide
   - Benchmark-Resultate

### Deliverables

- `sms/docker-compose.full.yml`: Kompletter Stack
- Test-Suite
- Finalisierte Dokumentation

---

## Meilensteine

| Meilenstein | Beschreibung | Deadline-Vorschlag |
|-------------|--------------|--------------------|
| M1          | SurrealDB Schema & Kernel fertig | 1 Woche |
| M2          | Router + Planner funktionsfähig | 2 Wochen |
| M3          | Eval Harness & MemoryData Integration | 3 Wochen |
| M4          | Extraction + Maintenance + Cost-Awareness | 5 Wochen |
| M5          | E2E fertig & Benchmarks gelaufen | 6 Wochen |

---

## Nächster Schritt (SOFORT)

Lass uns direkt mit **Phase 1** anfangen! Ich erstelle dir jetzt die finalisierten SurrealDB-Schema-Dateien und Projekt-Struktur.
