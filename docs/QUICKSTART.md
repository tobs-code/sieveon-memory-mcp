# Quickstart Guide

## Was haben wir bisher gebaut?

- ✅ SurrealDB-Schema mit Immutable Event Log, Temporal Knowledge Graph & Hybrid Index
- ✅ Helper Functions für SurrealDB
- ✅ Docker Compose Setup für SurrealDB
- ✅ Python-Prototypen für Query Classifier, Routing Policy & Retrieval Planner
- ✅ Load-Skripte für SurrealDB via HTTP-API
- ✅ End-to-End Test-Skript

## Schritt 1: SurrealDB starten

```bash
cd sdb
docker-compose up -d
```

## Schritt 2: Schema & Testdaten laden

Nutze das optimierte Load-Skript (benötigt `requests`):
```bash
cd ..
pip install requests
python scripts/load_schema_optimized.py
```

## Schritt 3: Komponenten testen

### Test Query Classifier & Routing Policy:
```bash
cd src/extraction && python classifier.py
cd ../router && python policy.py
```

### End-to-End Test ausführen:
```bash
cd ../..
python test_e2e.py
```

## Nächste Schritte

Siehe `IMPLEMENTATION_PLAN.md` für den vollständigen Plan!

## Nützliche Dateien

- `sdb/SURREALDB_PYTHON_SDK_DOCS.md`: Dokumentation zur Python-SDK
- `scripts/debug_surrealdb.py`: Debug-Skript für SurrealDB-Connection
- `scripts/load_schema_optimized.py`: Optimiertes Load-Skript

