MCP-Server macht hier richtig Sinn weil du damit deinen Memory-Stack direkt als Tool-Layer für jeden LLM-Agent nutzbar machst — nicht nur für Claude.

lass mich die Tools nach Schichten aufteilen, damit's übersichtlich bleibt:

---

## Schicht 1 — Core Memory Operations

die muss jeder Agent haben:

**`memory_store`**
```json
{
  "name": "memory_store",
  "description": "Stores a new event in the raw event log. Always persists, entropy gate decides KG extraction.",
  "input": {
    "content": "string",
    "source": "string",
    "metadata": "object (optional)"
  }
}
```

**`memory_query`**
```json
{
  "name": "memory_query", 
  "description": "Routes a natural language query through the full pipeline: classify → plan → retrieve.",
  "input": {
    "query": "string",
    "cost_budget": "low | medium | high (optional, default: auto)"
  }
}
```

**`memory_update`**
```json
{
  "name": "memory_update",
  "description": "Updates a fact in the KG via logical invalidation. Old fact gets valid_until, new fact created.",
  "input": {
    "subject": "string",
    "predicate": "string", 
    "new_value": "string"
  }
}
```

das sind die drei die ein Agent im täglichen Betrieb 90% der Zeit braucht.

---

## Schicht 2 — Retrieval Primitives

für Agents die mehr Kontrolle wollen:

**`event_log_search`** — direkte Zeitstrahl-Abfrage ohne Router:
```json
{
  "input": {
    "query": "string",
    "since": "ISO timestamp (optional)",
    "until": "ISO timestamp (optional)",
    "limit": "int (default: 10)"
  }
}
```

**`kg_query`** — direkte Graph-Traversal:
```json
{
  "input": {
    "subject": "string (optional)",
    "predicate": "string (optional)",
    "at_time": "ISO timestamp (optional, default: now → active facts only)"
  }
}
```

**`semantic_search`** — reiner Vector-Pfad ohne KG:
```json
{
  "input": {
    "query": "string",
    "top_k": "int (default: 5)"
  }
}
```

der Trick: `memory_query` ist der High-Level-Einstieg, diese drei sind die Low-Level-Primitives. ein cleverer Agent kann bei Bedarf direkt auf die Primitives gehen wenn er weiß was er braucht.

---

## Schicht 3 — Introspection Tools

die sind für Debugging und Meta-Reasoning — und machen deinen Stack von anderen Systemen unterscheidbar:

**`memory_stats`** — was weiß das System überhaupt:
```json
{
  "returns": {
    "event_count": "int",
    "entity_count": "int", 
    "fact_count": "int",
    "oldest_event": "timestamp",
    "newest_event": "timestamp",
    "gate_pass_rate": "float (letzte 100 Events)"
  }
}
```

**`explain_routing`** — warum hat der Router so entschieden:
```json
{
  "input": { "query": "string" },
  "returns": {
    "classified_as": "string",
    "confidence": "float",
    "strategy_selected": "string",
    "reason": "string"
  }
}
```

das zweite Tool ist Gold wert für dein Eval-Setup — du kannst dem Agent sagen "erkläre mir warum du diese Strategie gewählt hast" und kriegst echte Routing-Transparenz.

---

## Schicht 4 — Maintenance Tools

die braucht der Agent seltener aber sie gehören dazu:

**`memory_forget`** — kein hard delete, nur Markierung:
```json
{
  "input": {
    "event_id": "string (optional)",
    "entity": "string (optional)",
    "reason": "string"
  }
}
```

implementierung intern: `SET forgotten = true, forgotten_at = time::now()` — raw log bleibt immutable, aber Retrieval filtert `WHERE forgotten != true`.

**`memory_consolidate`** — manueller Trigger für Conservative Maintenance:
```json
{
  "input": {
    "scope": "local | entity",
    "entity": "string (nur bei scope=entity)"
  }
}
```

kein globales Reindexieren — nur lokale Patches, genau wie dein `conservative_maintainer.py` es macht.

---

## die komplette Tool-Liste zusammengefasst

| Tool | Schicht | Häufigkeit |
|------|---------|------------|
| `memory_store` | Core | sehr hoch |
| `memory_query` | Core | sehr hoch |
| `memory_update` | Core | mittel |
| `event_log_search` | Primitives | mittel |
| `kg_query` | Primitives | mittel |
| `semantic_search` | Primitives | niedrig |
| `memory_stats` | Introspection | niedrig |
| `explain_routing` | Introspection | Debug |
| `memory_forget` | Maintenance | selten |
| `memory_consolidate` | Maintenance | selten |

---

## technisch: wie du den MCP-Server baust

du hast Python im Stack — dann ist FastMCP die naheliegendste Wahl. das ist die offizielle Python-Implementierung vom MCP-SDK:

```python
from mcp.server.fastmcp import FastMCP
from src.router.policy import RoutingPolicy
from src.router.classifier import QueryClassifier

mcp = FastMCP("agent-memory")

@mcp.tool()
async def memory_query(query: str, cost_budget: str = "auto") -> dict:
    """Routes a query through the full memory pipeline."""
    classifier = QueryClassifier()
    q_type, confidence = classifier.classify(query)
    
    policy = RoutingPolicy()
    strategy = policy.get_strategy(q_type, confidence, cost_budget)
    
    # → Planner aufrufen
    # → Ergebnis zurückgeben
    ...
```

die MCP-Spezifikation und das Python-SDK sind hier: **modelcontextprotocol.io** — Anthropic hat das im November 2024 open-source gestellt und es hat sich seitdem zum Standard entwickelt.

---

eine Sache noch: `explain_routing` würde ich von Anfang an einbauen, nicht als Afterthought. wenn dein Router später durch Eval-Feedback lernt, willst du nachvollziehbar haben warum er wie entschieden hat. das ist quasi dein Interpretability-Tool für den Router — du kennst das Konzept ja aus deiner mechanistic-interp Arbeit. ;)