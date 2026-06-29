# Strata — A Workload-Adaptive Agent Memory System

Strata — a workload-adaptive agent memory system.
Evidence-based architecture derived from Zhou et al. arXiv:2606.24775.

A sophisticated agent memory system that combines event logs, knowledge graphs, and vector embeddings for intelligent information retrieval and storage. This system implements a workload-adaptive architecture that intelligently routes queries to the most appropriate storage and retrieval strategy. Evidence-based architecture derived from Zhou et al. arXiv:2606.24775.

## Architecture Overview

The system is composed of interconnected Rust and Python components that work together to provide intelligent query processing:

### Rust Components
- **Router** ([router](file:///c:/Users/tobs/.cursor/workspace/sms/router)): Classifies incoming queries and routes them to appropriate strategies using pattern-based classification
- **Planner** ([planner](file:///c:/Users/tobs/.cursor\workspace/sms\planner)): Builds and executes execution plans based on routing decisions with support for multiple retrieval strategies
- **Maintenance** ([maintenance](file:///c:/Users/tobs/.cursor/workspace/sms/maintenance)): Performs conservative maintenance operations with lazy flushing and logical invalidation
- **Common** ([common](file:///c:/Users/tobs/.cursor/workspace/sms/common)): Shared data structures and utilities across Rust components

### Python Components
- **Extraction** ([src/extraction](file:///c:/Users/tobs/.cursor/workspace/sms/src/extraction)): Text processing, entity extraction, and entropy-based filtering
- **Router** ([src/router](file:///c:/Users/tobs/.cursor/workspace/sms/src/router)): Policy engine for routing decisions
- **Planner** ([src/planner](file:///c:/Users/tobs/.cursor/workspace/sms/src/planner)): Execution engine for query plans
- **Control Plane** ([src/mcp](file:///c:/Users/tobs/.cursor/workspace/sms/src/mcp)): System coordinator implementing the Model Context Protocol (MCP) specification from Anthropic

## Key Features

### 1. Query Classification
The system classifies queries into five types using pattern-matching rules in both Rust and Python implementations:
- **Temporal**: Questions about time/dates (patterns: "when", "wann", "yesterday", "gestern", "since", "seit")
- **Factual**: Direct factual questions (patterns: "who", "what", "who", "was", "where", "wo")
- **Multi-Hop**: Complex questions requiring reasoning (patterns: "why", "warum", "because", "wegen", "relationship")
- **Conversational**: Context-dependent queries (patterns: "remember", "erinnerst", "talked about", "gesprochen")
- **Update**: Requests to modify stored information (patterns: "update", "aktualisiere", "change", "modify")

### 2. Adaptive Retrieval Strategies
Based on query classification, the system selects optimal retrieval strategies:

- **Event Log First**: For temporal queries (`event_log_first`)
- **Knowledge Graph First**: For factual queries (`knowledge_graph_first`)
- **Hybrid with Graph Expansion**: For multi-hop queries (`hybrid_with_graph_expansion`)
- **Composite KG-Vector**: For conversational queries (`composite_kg_vector`)
- **KG with Invalidation**: For update queries (`knowledge_graph_with_invalidation`)
- **Hybrid BM25-Vector-Temporal**: Advanced hybrid search combining keyword, vector, and temporal modalities (`hybrid_bm25_vector_temporal`)
- **Hybrid Fallback**: Default strategy for low-confidence queries

### 3. Cross-Language Consistency
The system maintains strict consistency between Rust and Python implementations:
- Both languages use identical SurrealDB connection parameters and authentication
- Shared query syntax and database schema understanding
- Consistent data structures through the common crate
- Equivalent routing policies and classification algorithms

### 4. Hybrid Indexing Approach
The system implements a sophisticated hybrid indexing strategy combining:
- **BM25 keyword search** using SurrealDB's full-text search capabilities with scoring
- **Vector similarity** via embedding-based retrieval
- **Temporal relevance** via time-based scoring and chronological ordering
- **Weighted scoring** to combine all three modalities effectively

### 5. Conservative Maintenance
The system implements conservative maintenance policies:
- Lazy flushing with debounce mechanisms
- Patch updates on knowledge graph instead of full rewrites
- Logical invalidation using `valid_until` timestamps
- Preservation of chronological integrity

### 6. Entropy-Based Filtering
An entropy gate decides whether to extract information to the knowledge graph based on:
- Text entropy (Shannon entropy on character level)
- Embedding novelty (vector similarity)
- Composite score combining both metrics

## Components Deep Dive

### Router
The router is implemented in both Rust and Python with equivalent functionality:
- **Rust**: Runs on port 8080, performs pattern-based classification and policy-driven routing
- **Python**: Provides policy engine with cost budget management

**Endpoints:**
- `GET /classify?query=text`: Classify a query
- `GET /route?query=text`: Route a query to strategy

### Planner
The planner creates execution plans based on routing decisions:
- **Rust**: Runs on port 8081, builds and executes query plans with support for multiple retrieval steps
- **Python**: Execution engine for complex retrieval strategies

**Endpoints:**
- `POST /plan_and_execute` (body: `{"query": "text"}`): Execute a query plan

### Maintenance
Performs background maintenance operations:
- **Rust**: Continuous service performing cleanup operations every 60 seconds
- Lazy flushing with debounce
- Patch updates to knowledge graph
- Logical invalidation of stale facts

**Endpoints:**
- `POST /maintain`: Perform maintenance operations

### Control Plane (MCP Implementation)
The Control Plane coordinates all system components and implements the Model Context Protocol (MCP) specification from Anthropic:
- **Python**: Runs on port 8082, integrates all system components
- Implements the official Model Context Protocol (MCP) specification from Anthropic
- Acts as the system coordinator for all memory operations
- Provides comprehensive toolset for memory operations

**NAMING CLARIFICATION**: This system implements the Model Context Protocol (MCP) specification developed by Anthropic. While we previously used "MCP" to mean "Memory Control Plane," we now clarify that our control plane server implements Anthropic's official MCP protocol specification.

**MCP Protocol Endpoints:**
- `GET /classify?query=text`: Query classification
- `GET /route?query=text`: Routing decision
- `POST /plan_and_execute` (body: `{"query": "text"}`): Plan and execute query
- `POST /maintain`: Perform maintenance
- `GET /health`: Health check

**Memory Operations Endpoints:**
- `POST /memory/store` (body: `{"content": "text", "source": "optional_source", "metadata": "optional_object"}`): Store new events in the raw event log
- `POST /memory/query` (body: `{"query": "text", "cost_budget": "auto"}`): Full pipeline query processing
- `POST /memory/update` (body: `{"subject": "text", "predicate": "text", "new_value": "text"}`): Update facts via logical invalidation
- `POST /memory/forget` (body: `{"event_id": "optional_id", "entity": "optional_entity_name", "reason": "text"}`): Soft delete operations
- `POST /memory/consolidate` (body: `{"scope": "local", "entity": "optional_entity_name"}`): Trigger maintenance operations

**Retrieval Primitives:**
- `GET /memory/event_log_search?query=text&since=timestamp&until=timestamp&limit=10`: Direct timeline query
- `GET /memory/kg_query?subject=text&predicate=text&at_time=timestamp`: Direct graph traversal
- `POST /memory/semantic_search` (body: `{"query": "text", "top_k": 5}`): Pure vector search

**Introspection Tools:**
- `GET /memory/stats`: System statistics
- `POST /memory/explain_routing` (body: `{"query": "text"}`): Explain routing decisions

## Database Schema

The system uses SurrealDB with the following key tables:

- `event`: Raw event log with content, embeddings, and timestamps
- `entity`: Knowledge graph entities
- `fact`: Relations between entities with validity periods
- `gate_log`: Entropy gate decisions

## Prerequisites

- Rust 1.75+
- Python 3.8+
- SurrealDB running on `http://127.0.0.1:8000`
- Namespace: `agent_memory`, Database: `agent_memory`
- Credentials: see [.env.example](file:///c:/Users/tobs/.cursor/workspace/sms/.env.example)

## Running the System

### Docker Compose Setup
The system includes a [docker-compose.yml](file:///c:/Users/tobs/.cursor/workspace/sms/docker-compose.yml) file for easy setup:

```bash
docker-compose up -d
```

This will start SurrealDB and all necessary services.

### Manual Setup

1. Start SurrealDB:
```bash
# Using the provided script
./scripts/start_surreal.sh
# Or manually
surreal start --user root --pass root
```

2. Start the router service:
```bash
cd router && cargo run
```

3. Start the planner service:
```bash
cd planner && cargo run
```

4. Start the maintenance service:
```bash
cd maintenance && cargo run
```

5. Start the control plane (Python) implementing the Model Context Protocol (MCP):
```bash
cd src/mcp && python server.py
```

### Control Plane Server Startup (MCP Implementation)
To start the Control Plane server that implements the Model Context Protocol (MCP) specification from Anthropic:
```bash
cd src/mcp && python server.py
```

## Testing

The system includes comprehensive tests covering all components:

### Rust Tests
```bash
cargo test --workspace
```

### Python Tests
```bash
cd tests
python run_all_tests.py
```

### Individual Test Categories
```bash
# Rust unit tests
cargo test -p router && cargo test -p planner && cargo test -p maintenance

# Python unit tests
python -m pytest tests/python_unit_tests.py -v

# Integration tests (requires running SurrealDB)
python -m pytest tests/surreal_integration_tests.py -v

# Router-specific tests
python -m pytest tests/python_router_tests.py -v
```

## Scripts

The system includes various utility scripts in the [scripts](file:///c:/Users/tobs/.cursor/workspace/sms/scripts) directory:
- `check_surreal.py`: Verify SurrealDB connection
- `load_schema.py`: Load database schema
- `debug_surreal_response.py`: Debug SurrealDB responses
- `profile_surreal.py`: Profile database queries
- `start_surreal.sh`: Start SurrealDB instance

## Evaluation

Run the evaluation harness to test system performance:
```bash
cd src/eval && python eval_harness.py
```

This measures the five key metrics from the research paper:
1. Retrieval Fidelity
2. Update Robustness
3. Long-Horizon Stability
4. Latency
5. Operation Cost

## Implementation Status

All planned components are **FULLY IMPLEMENTED**:
- ✅ Workload-adaptive Router
- ✅ Raw Event Log
- ✅ Knowledge Graph with logical invalidation
- ✅ Hybrid Index (BM25 + Vector + Temporal)
- ✅ Coarse-grained Extraction Engine
- ✅ Conservative Maintenance Engine
- ✅ Cost-awareness Layer
- ✅ Multi-dimensional Eval Harness

## Cross-Language Consistency

The system ensures strict consistency between Rust and Python implementations:
- Identical SurrealDB query syntax and connection parameters
- Equivalent data structures through the common crate
- Consistent classification and routing algorithms
- Proper trait implementations (PartialEq, etc.) for testing

## Contributing

When developing new features:
1. Ensure cross-language consistency between Rust and Python implementations
2. Update both language-specific tests when changing core logic
3. Maintain the same database schema understanding across components
4. Follow the conservative maintenance principles
5. Preserve chronological integrity in all operations

## License

This project is licensed under the terms specified in the repository.