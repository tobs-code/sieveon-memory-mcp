# SurrealDB 3 - Projekt Setup Guide

## Übersicht

SurrealDB ist eine multi-model Datenbank, die verschiedene Datenmodelle in einem einzigen System vereint. SurrealDB 3 bringt bedeutende Verbesserungen in Stabilität, Leistung und Entwicklererfahrung.

## Hauptmerkmale von SurrealDB 3

### Stabilität & Leistung
- Trennung von Werten und Ausdrücken für weniger redundante Arbeit
- Computed Fields (berechnete Felder) ersetzen die alten "future"-Typen
- ID-basierte Speicherung für Katalogeinträge (Namespaces, Datenbanken, Indizes)
- Synchrone Schreibvorgänge als Standard
- Über 150 geschlossene Issues

### Multi-Modell Unterstützung
- **Dokument-Datenbank**
- **Graph-Datenbank**
- **Relationale Datenbank**
- **Zeitreihen-Datenbank**
- **Geodatenbank**
- **Vektor-Datenbank** (für AI/ML)
- **Full-Text-Suche**

### AI-Agent Speicher
- First-Class-Unterstützung für AI-Agenten
- Einheitlicher Speicher für strukturierte, vektor- und Graph-Daten
- Context Memory für Langzeitgedächtnis von Agenten
- Reduzierung von Glue-Code und beweglichen Teilen

### Surrealism (Erweiterungen)
- Open-Source-Erweiterungssystem
- WASM-Plugins direkt in SurrealQL
- Einbettung von KI- und Geschäftslogik nah an den Daten

### Dateispeicherung
- Einfache Buckets und Dateizeiger
- Speichern, Zugreifen und Transformieren von Dateidaten direkt in SurrealQL

### Verbessertes In-Memory-Engine
- Ultraniedrige Latenz und hoher Durchsatz
- Volle ACID-Transaktionen
- Lock-freies, MVCC-basiertes Design
- Optionale Hintergrundpersistenz

### Verbesserte Indizierung
- Schnellere Abfragen und höherer Durchsatz
- Intelligentere Query-Planer
- Gleichzeitige Index-Updates
- Reichere Index-Funktionen

### Client-seitige Transaktionen
- Transaktionsfluss direkt im Anwendungscode steuern
- Operationen über mehrere Anfragen gruppieren
- Commit bei Bedarf mit vollen ACID-Garantien

### Benutzerdefinierte API-Endpoints
- HTTP-Routen und Middleware direkt in der Datenbank definieren
- Entfernen der Notwendigkeit für externe Middleware
- Vereinfachung der Anwendungsarchitektur

### Record References
- Bidirektionale Record-Links auf Schema-Ebene
- Einfachere Abfragen
- Schnellere, natürlichere Navigation durch verwandte Daten

### GraphQL (Stabil)
- Offizielle Unterstützung für GraphQL
- Volle Unterstützung für Mutations
- Native Authentifizierung
- Schutz vor Missbrauch durch konfigurierbare Komplexitätsgrenzen
- Optimierungen zur Vermeidung des N+1-Problems

### Java & Go SDKs (v1.0)
- Produktionsreife SDKs für Java und Go

## Installation

### Docker (empfohlen)
```bash
docker run --pull always -p 8000:8000 surrealdb/surrealdb:latest start
```

### Windows
```powershell
iwr https://install.surrealdb.com | iex
```

### macOS (Homebrew)
```bash
brew install surrealdb/tap/surreal
```

### Linux
```bash
curl --proto '=https' --tlsv1.2 -sSf https://install.surrealdb.com | sh
```

## Starten von SurrealDB

### In-Memory
```bash
surreal start memory
```

### Single Node mit SurrealKV (ohne Versionierung)
```bash
surreal start -u root -p root surrealkv://mydb
```

### Single Node mit SurrealKV (mit Versionierung)
```bash
surreal start -u root -p root surrealkv+versioned://mydb
```

### Single Node mit RocksDB
```bash
surreal start -u root -p root rocksdb://mydb
```

### Multi-Node Cluster mit TiKV
```bash
surreal start tikv://127.0.0.1:2379
```

## SurrealQL Grundlagen

### CREATE - Daten erstellen
```surrealql
-- Automatisch generierte ID
CREATE category SET name = 'Technology', created_at = time::now();

-- Explizit festgelegte ID
CREATE person:john SET name = 'John Doe', age = 30, admin = true;

-- Mit Subquery
CREATE article SET 
    title = 'SurrealDB Guide',
    author = (SELECT id FROM person WHERE name = 'John Doe'),
    category = (SELECT id FROM category WHERE name = 'Technology');
```

### SELECT - Daten abfragen
```surrealql
-- Alle Datensätze aus einer Tabelle
SELECT * FROM person;

-- Spezifische Felder
SELECT name, age FROM person;

-- Mit Filter
SELECT * FROM person WHERE age < 30;

-- Mit FETCH (Record-IDs auflösen)
SELECT title, author.name FROM article FETCH author;

-- Direkter Zugriff auf verknüpfte Daten
SELECT title, author.name.full FROM article;
```

### UPDATE - Daten aktualisieren
```surrealql
-- Einzelnen Datensatz aktualisieren
UPDATE person:john SET age = 31;

-- Mehrere Datensätze mit Bedingung
UPDATE person SET admin = false WHERE age < 30;

-- Merge (Teilupdate)
UPDATE person:john MERGE { last_login: time::now() };
```

### UPSERT - Aktualisieren oder Erstellen
```surrealql
UPSERT person:jane SET name = 'Jane Smith', age = 25;
```

### DELETE - Daten löschen
```surrealql
-- Einzelnen Datensatz löschen
DELETE person:john;

-- Mit Bedingung
DELETE person WHERE age < 18;

-- Mit RETURN (gelöschte Datensätze zurückgeben)
DELETE person WHERE age < 18 RETURN BEFORE;
```

### Computed Fields (Neu in 3.0)
```surrealql
DEFINE FIELD can_drive ON person COMPUTED age > 18;
```

### Graph-Relationen
```surrealql
-- Personen erstellen
CREATE person:alice SET name = 'Alice';
CREATE person:bob SET name = 'Bob';

-- Beziehung erstellen
RELATE person:alice->knows->person:bob SET since = time::now();

-- Graph traversieren
SELECT ->knows->person.* FROM person:alice;
```

### Vektoren (für AI/ML)
```surrealql
-- Vektor-Feld definieren
DEFINE FIELD embedding ON article TYPE vector(f32, 1536);

-- Datensatz mit Vektor erstellen
CREATE article SET 
    title = 'Machine Learning Basics',
    embedding = [0.1, 0.2, 0.3, /* ... */];

-- Ähnlichkeitsuche
SELECT * FROM article 
WHERE vector::cosine_distance(embedding, $query_vector) < 0.5
ORDER BY vector::cosine_distance(embedding, $query_vector)
LIMIT 10;
```

## SDK Integration

### Python
```bash
uv add surrealdb
```

```python
import asyncio
from surrealdb import AsyncSurreal

async def main():
    db = AsyncSurreal()
    await db.connect("ws://localhost:8000/rpc")
    await db.signin({"user": "root", "pass": "root"})
    await db.use("test", "test")
    
    # Daten erstellen
    await db.create("person", {
        "name": "John",
        "age": 30
    })
    
    # Daten abfragen
    result = await db.select("person")
    print(result)

asyncio.run(main())
```

### Rust
```bash
cargo add surrealdb
cargo add tokio --features macros,rt-multi-thread
cargo add serde --features derive
```

```rust
use surrealdb::engine::remote::ws::Ws;
use surrealdb::opt::auth::Root;
use surrealdb::Surreal;

#[tokio::main]
async fn main() -> surrealdb::Result<()> {
    let db = Surreal::new::<Ws>("127.0.0.1:8000").await?;
    
    db.signin(Root {
        username: "root",
        password: "root",
    }).await?;
    
    db.use_ns("test").use_db("test").await?;
    
    db.create("person")
        .content(serde_json::json!({
            "name": "John",
            "age": 30
        }))
        .await?;
    
    Ok(())
}
```

### Go
```bash
go get github.com/surrealdb/surrealdb.go
```

```go
package main

import (
    surrealdb "github.com/surrealdb/surrealdb.go"
)

func main() {
    db, err := surrealdb.New("ws://localhost:8000/rpc")
    if err != nil {
        panic(err)
    }
    defer db.Close()
    
    _, err = db.Signin(map[string]any{
        "user": "root",
        "pass": "root",
    })
    if err != nil {
        panic(err)
    }
    
    _, err = db.Use("test", "test")
    if err != nil {
        panic(err)
    }
}
```

## Projekt-Struktur Vorschlag

```
mein-projekt/
├── surrealdb/
│   ├── docker-compose.yml
│   └── migrations/
│       └── 001_initial_schema.surql
├── src/
│   └── (Ihr Anwendungscode)
└── README.md
```

### docker-compose.yml Beispiel
```yaml
version: '3.8'
services:
  surrealdb:
    image: surrealdb/surrealdb:latest
    container_name: surrealdb
    ports:
      - "8000:8000"
    command: start --user root --pass root memory
    restart: unless-stopped
```

### Migration-Datei Beispiel (001_initial_schema.surql)
```surrealql
-- Namespace und Datenbank definieren
USE NS myapp DB myapp;

-- Tabellen und Felder definieren
DEFINE TABLE user SCHEMAFULL;
DEFINE FIELD name ON user TYPE string;
DEFINE FIELD email ON user TYPE string;
DEFINE FIELD age ON user TYPE int;
DEFINE FIELD can_drive ON user COMPUTED age > 18;

DEFINE TABLE article SCHEMAFULL;
DEFINE FIELD title ON article TYPE string;
DEFINE FIELD content ON article TYPE string;
DEFINE FIELD author ON article TYPE record(user);
DEFINE FIELD embedding ON article TYPE vector(f32, 1536);

-- Indizes erstellen
DEFINE INDEX user_email ON user COLUMNS email UNIQUE;
DEFINE INDEX article_title ON article COLUMNS title;
DEFINE INDEX article_embedding ON article FIELDS embedding;
```

## Nützliche Ressourcen

- **Offizielle Dokumentation**: https://surrealdb.com/docs
- **SurrealDB University**: https://surrealdb.com/learn
- **GitHub**: https://github.com/surrealdb/surrealdb
- **Blog Post zur 3.0**: https://surrealdb.com/blog/introducing-surrealdb-3-0-the-future-of-ai-agent-memory
- **SurrealDB Cloud**: https://app.surrealdb.com/overview
