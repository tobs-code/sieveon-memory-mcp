
## Benchmark Run: 2026-06-30 18:56:02

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 774.55 | 798.30 | 757.14 | 798.30 | 0 |
| `memory_store` | 790.20 | 814.75 | 762.20 | 814.75 | 0 |
| `memory_query` | 368.40 | 412.81 | 330.69 | 412.81 | 0 |
| `semantic_search` | 854.12 | 900.21 | 821.50 | 900.21 | 0 |
| `event_log_search` | 770.59 | 811.56 | 749.43 | 811.56 | 0 |
| `kg_query` | 766.28 | 787.76 | 749.55 | 787.76 | 0 |
| `explain_routing` | 0.20 | 0.22 | 0.19 | 0.22 | 0 |

---

## Benchmark Run: 2026-06-30 19:42:32

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 851.77 | 1122.77 | 760.13 | 1122.77 | 0 |
| `memory_store` | 786.93 | 823.22 | 756.19 | 823.22 | 0 |
| `memory_query` | 362.01 | 400.54 | 323.91 | 400.54 | 0 |
| `semantic_search` | 806.62 | 870.25 | 782.46 | 870.25 | 0 |
| `event_log_search` | 783.67 | 822.17 | 761.45 | 822.17 | 0 |
| `kg_query` | 765.23 | 798.41 | 747.11 | 798.41 | 0 |
| `explain_routing` | 0.20 | 0.21 | 0.18 | 0.21 | 0 |

---

## Benchmark Run: 2026-06-30 19:44:02

### Summary

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 784.86 | 831.33 | 761.31 | 831.33 | 0 |
| `memory_store` | 792.60 | 828.55 | 767.54 | 828.55 | 0 |
| `memory_query` | 391.88 | 429.05 | 334.11 | 429.05 | 0 |
| `semantic_search` | 809.22 | 892.39 | 781.75 | 892.39 | 0 |
| `event_log_search` | 795.02 | 828.39 | 770.72 | 828.39 | 0 |
| `kg_query` | 878.98 | 1028.94 | 787.49 | 1028.94 | 0 |
| `explain_routing` | 0.24 | 0.37 | 0.19 | 0.37 | 0 |

### Full Execution Logs

```text
STRATA MCP Performance Benchmark - 2026-06-30 19:44:02
============================================================
System: Windows 10 (AMD64)
Python: 3.11.9
============================================================

--- Benchmarking 'memory_stats' (10 iterations) ---
  Avg: 784.86ms
  P95: 831.33ms
  Min/Max: 761.31ms / 831.33ms
  Errors: 0

--- Benchmarking 'memory_store' (10 iterations) ---
[INFO] Initializing Embedding Service with model: sentence-transformers/all-MiniLM-L6-v2...
[OK] Embedding Service initialized
  Avg: 792.60ms
  P95: 828.55ms
  Min/Max: 767.54ms / 828.55ms
  Errors: 0

--- Benchmarking 'memory_query' (10 iterations) ---
  Avg: 391.88ms
  P95: 429.05ms
  Min/Max: 334.11ms / 429.05ms
  Errors: 0

--- Benchmarking 'semantic_search' (10 iterations) ---
  Avg: 809.22ms
  P95: 892.39ms
  Min/Max: 781.75ms / 892.39ms
  Errors: 0

--- Benchmarking 'event_log_search' (10 iterations) ---
  Avg: 795.02ms
  P95: 828.39ms
  Min/Max: 770.72ms / 828.39ms
  Errors: 0

--- Benchmarking 'kg_query' (10 iterations) ---
  Avg: 878.98ms
  P95: 1028.94ms
  Min/Max: 787.49ms / 1028.94ms
  Errors: 0

--- Benchmarking 'explain_routing' (10 iterations) ---
  Avg: 0.24ms
  P95: 0.37ms
  Min/Max: 0.19ms / 0.37ms
  Errors: 0

============================================================
Tool                 |   Avg (ms) |   P95 (ms) | Errors
------------------------------------------------------------
memory_stats         |     784.86 |     831.33 |      0
memory_store         |     792.60 |     828.55 |      0
memory_query         |     391.88 |     429.05 |      0
semantic_search      |     809.22 |     892.39 |      0
event_log_search     |     795.02 |     828.39 |      0
kg_query             |     878.98 |    1028.94 |      0
explain_routing      |       0.24 |       0.37 |      0
============================================================
```

---

## Benchmark Run: 2026-06-30 19:50:03

### Summary

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 790.87 | 863.10 | 762.12 | 863.10 | 0 |
| `memory_store` | 796.96 | 818.69 | 785.12 | 818.69 | 0 |
| `memory_query` | 355.10 | 399.04 | 319.16 | 399.04 | 0 |
| `semantic_search` | 807.81 | 844.35 | 786.09 | 844.35 | 0 |
| `event_log_search` | 775.61 | 799.04 | 764.14 | 799.04 | 0 |
| `kg_query` | 772.53 | 813.60 | 752.64 | 813.60 | 0 |
| `explain_routing` | 0.20 | 0.32 | 0.18 | 0.32 | 0 |

### Full Execution Logs

```text
STRATA MCP Performance Benchmark - 2026-06-30 19:50:03
============================================================
System: Windows 10 (AMD64)
Python: 3.11.9
============================================================

--- Benchmarking 'memory_stats' (10 iterations) ---
  Avg: 790.87ms
  P95: 863.10ms
  Min/Max: 762.12ms / 863.10ms
  Errors: 0

--- Benchmarking 'memory_store' (10 iterations) ---
[INFO] Initializing Embedding Service with model: sentence-transformers/all-MiniLM-L6-v2...
[OK] Embedding Service initialized
  Avg: 796.96ms
  P95: 818.69ms
  Min/Max: 785.12ms / 818.69ms
  Errors: 0

--- Benchmarking 'memory_query' (10 iterations) ---
  Avg: 355.10ms
  P95: 399.04ms
  Min/Max: 319.16ms / 399.04ms
  Errors: 0

--- Benchmarking 'semantic_search' (10 iterations) ---
  Avg: 807.81ms
  P95: 844.35ms
  Min/Max: 786.09ms / 844.35ms
  Errors: 0

--- Benchmarking 'event_log_search' (10 iterations) ---
  Avg: 775.61ms
  P95: 799.04ms
  Min/Max: 764.14ms / 799.04ms
  Errors: 0

--- Benchmarking 'kg_query' (10 iterations) ---
  Avg: 772.53ms
  P95: 813.60ms
  Min/Max: 752.64ms / 813.60ms
  Errors: 0

--- Benchmarking 'explain_routing' (10 iterations) ---
  Avg: 0.20ms
  P95: 0.32ms
  Min/Max: 0.18ms / 0.32ms
  Errors: 0

============================================================
Tool                 |   Avg (ms) |   P95 (ms) | Errors
------------------------------------------------------------
memory_stats         |     790.87 |     863.10 |      0
memory_store         |     796.96 |     818.69 |      0
memory_query         |     355.10 |     399.04 |      0
semantic_search      |     807.81 |     844.35 |      0
event_log_search     |     775.61 |     799.04 |      0
kg_query             |     772.53 |     813.60 |      0
explain_routing      |       0.20 |       0.32 |      0
============================================================
```

---

## Benchmark Run: 2026-06-30 20:59:24

### Summary

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 787.03 | 857.40 | 763.76 | 857.40 | 0 |
| `memory_store` | 768.65 | 789.28 | 753.44 | 789.28 | 0 |
| `memory_query` | 363.10 | 422.31 | 339.50 | 422.31 | 0 |
| `semantic_search` | 789.75 | 835.28 | 769.87 | 835.28 | 0 |
| `event_log_search` | 766.15 | 807.32 | 749.67 | 807.32 | 0 |
| `kg_query` | 759.73 | 799.96 | 740.39 | 799.96 | 0 |
| `explain_routing` | 0.20 | 0.35 | 0.18 | 0.35 | 0 |

### Full Execution Logs

```text
STRATA MCP Performance Benchmark - 2026-06-30 20:59:24
============================================================
System: Windows 10 (AMD64)
Python: 3.11.9
============================================================

--- Benchmarking 'memory_stats' (10 iterations) ---
[INFO] Starting background SurrealDB reconnect task
  Avg: 787.03ms
  P95: 857.40ms
  Min/Max: 763.76ms / 857.40ms
  Errors: 0

--- Benchmarking 'memory_store' (10 iterations) ---
[INFO] Initializing Embedding Service with model: sentence-transformers/all-MiniLM-L6-v2...
[OK] Embedding Service initialized
  Avg: 768.65ms
  P95: 789.28ms
  Min/Max: 753.44ms / 789.28ms
  Errors: 0

--- Benchmarking 'memory_query' (10 iterations) ---
  Avg: 363.10ms
  P95: 422.31ms
  Min/Max: 339.50ms / 422.31ms
  Errors: 0

--- Benchmarking 'semantic_search' (10 iterations) ---
  Avg: 789.75ms
  P95: 835.28ms
  Min/Max: 769.87ms / 835.28ms
  Errors: 0

--- Benchmarking 'event_log_search' (10 iterations) ---
  Avg: 766.15ms
  P95: 807.32ms
  Min/Max: 749.67ms / 807.32ms
  Errors: 0

--- Benchmarking 'kg_query' (10 iterations) ---
  Avg: 759.73ms
  P95: 799.96ms
  Min/Max: 740.39ms / 799.96ms
  Errors: 0

--- Benchmarking 'explain_routing' (10 iterations) ---
  Avg: 0.20ms
  P95: 0.35ms
  Min/Max: 0.18ms / 0.35ms
  Errors: 0

============================================================
Tool                 |   Avg (ms) |   P95 (ms) | Errors
------------------------------------------------------------
memory_stats         |     787.03 |     857.40 |      0
memory_store         |     768.65 |     789.28 |      0
memory_query         |     363.10 |     422.31 |      0
semantic_search      |     789.75 |     835.28 |      0
event_log_search     |     766.15 |     807.32 |      0
kg_query             |     759.73 |     799.96 |      0
explain_routing      |       0.20 |       0.35 |      0
============================================================
```

---

## Benchmark Run: 2026-06-30 22:48:03

### Summary

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 5176.22 | 5211.56 | 5147.74 | 5211.56 | 0 |
| `memory_store` | 777.24 | 823.54 | 751.76 | 823.54 | 0 |
| `memory_query` | 408.88 | 431.88 | 389.47 | 431.88 | 0 |
| `semantic_search` | 778.73 | 797.05 | 761.54 | 797.05 | 0 |
| `event_log_search` | 757.38 | 783.20 | 742.97 | 783.20 | 0 |
| `kg_query` | 742.65 | 756.70 | 727.85 | 756.70 | 0 |
| `explain_routing` | 0.21 | 0.36 | 0.18 | 0.36 | 0 |

### Full Execution Logs

```text
STRATA MCP Performance Benchmark - 2026-06-30 22:48:03
============================================================
System: Windows 10 (AMD64)
Python: 3.11.9
============================================================

--- Benchmarking 'memory_stats' (10 iterations) ---
[INFO] Starting background SurrealDB reconnect task
  Avg: 5176.22ms
  P95: 5211.56ms
  Min/Max: 5147.74ms / 5211.56ms
  Errors: 0

--- Benchmarking 'memory_store' (10 iterations) ---
[INFO] Initializing Embedding Service with model: sentence-transformers/all-MiniLM-L6-v2...
[OK] Embedding Service initialized
  Avg: 777.24ms
  P95: 823.54ms
  Min/Max: 751.76ms / 823.54ms
  Errors: 0

--- Benchmarking 'memory_query' (10 iterations) ---
  Avg: 408.88ms
  P95: 431.88ms
  Min/Max: 389.47ms / 431.88ms
  Errors: 0

--- Benchmarking 'semantic_search' (10 iterations) ---
  Avg: 778.73ms
  P95: 797.05ms
  Min/Max: 761.54ms / 797.05ms
  Errors: 0

--- Benchmarking 'event_log_search' (10 iterations) ---
  Avg: 757.38ms
  P95: 783.20ms
  Min/Max: 742.97ms / 783.20ms
  Errors: 0

--- Benchmarking 'kg_query' (10 iterations) ---
  Avg: 742.65ms
  P95: 756.70ms
  Min/Max: 727.85ms / 756.70ms
  Errors: 0

--- Benchmarking 'explain_routing' (10 iterations) ---
  Avg: 0.21ms
  P95: 0.36ms
  Min/Max: 0.18ms / 0.36ms
  Errors: 0

============================================================
Tool                 |   Avg (ms) |   P95 (ms) | Errors
------------------------------------------------------------
memory_stats         |    5176.22 |    5211.56 |      0
memory_store         |     777.24 |     823.54 |      0
memory_query         |     408.88 |     431.88 |      0
semantic_search      |     778.73 |     797.05 |      0
event_log_search     |     757.38 |     783.20 |      0
kg_query             |     742.65 |     756.70 |      0
explain_routing      |       0.21 |       0.36 |      0
============================================================
```

---

## Benchmark Run: 2026-07-01 02:20:05

### Summary

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 5300.05 | 5464.49 | 5207.94 | 5464.49 | 0 |
| `memory_store` | 235.94 | 251.79 | 225.91 | 251.79 | 0 |
| `memory_query` | 410.61 | 434.83 | 384.51 | 434.83 | 0 |
| `semantic_search` | 779.93 | 804.02 | 767.22 | 804.02 | 0 |
| `event_log_search` | 747.99 | 758.49 | 742.59 | 758.49 | 0 |
| `kg_query` | 779.16 | 809.69 | 743.16 | 809.69 | 0 |
| `explain_routing` | 0.27 | 0.53 | 0.18 | 0.53 | 0 |

### Full Execution Logs

```text
STRATA MCP Performance Benchmark - 2026-07-01 02:20:05
============================================================
System: Windows 10 (AMD64)
Python: 3.11.9
============================================================

--- Benchmarking 'memory_stats' (10 iterations) ---
[INFO] Starting background SurrealDB reconnect task
  Avg: 5300.05ms
  P95: 5464.49ms
  Min/Max: 5207.94ms / 5464.49ms
  Errors: 0

--- Benchmarking 'memory_store' (10 iterations) ---
[INFO] Initializing Embedding Service with model: sentence-transformers/all-MiniLM-L6-v2...
[OK] Embedding Service initialized
Entropy Gate Decision: {'decision': 'extract', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 0.5076565639736005, 'composite_score': 0.6209543003777901, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.621 meets threshold 0.550'}
  [KG] Found candidate entities: ['Benchmark']
  [KG] Entity: Benchmark -> entity:4zkz17t86sd2in1bvpfh
  [KG] Extraction complete: {'entities_created': 1, 'facts_created': 1}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 0.3716276607543306, 'composite_score': 0.5325355132852647, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.533 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 0.24168867224708868, 'composite_score': 0.4480751707555574, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.448 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 0.11385437377834506, 'composite_score': 0.3649828767508741, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.365 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
  Avg: 235.94ms
  P95: 251.79ms
  Min/Max: 225.91ms / 251.79ms
  Errors: 0

--- Benchmarking 'memory_query' (10 iterations) ---
  Avg: 410.61ms
  P95: 434.83ms
  Min/Max: 384.51ms / 434.83ms
  Errors: 0

--- Benchmarking 'semantic_search' (10 iterations) ---
  Avg: 779.93ms
  P95: 804.02ms
  Min/Max: 767.22ms / 804.02ms
  Errors: 0

--- Benchmarking 'event_log_search' (10 iterations) ---
  Avg: 747.99ms
  P95: 758.49ms
  Min/Max: 742.59ms / 758.49ms
  Errors: 0

--- Benchmarking 'kg_query' (10 iterations) ---
  Avg: 779.16ms
  P95: 809.69ms
  Min/Max: 743.16ms / 809.69ms
  Errors: 0

--- Benchmarking 'explain_routing' (10 iterations) ---
  Avg: 0.27ms
  P95: 0.53ms
  Min/Max: 0.18ms / 0.53ms
  Errors: 0

============================================================
Tool                 |   Avg (ms) |   P95 (ms) | Errors
------------------------------------------------------------
memory_stats         |    5300.05 |    5464.49 |      0
memory_store         |     235.94 |     251.79 |      0
memory_query         |     410.61 |     434.83 |      0
semantic_search      |     779.93 |     804.02 |      0
event_log_search     |     747.99 |     758.49 |      0
kg_query             |     779.16 |     809.69 |      0
explain_routing      |       0.27 |       0.53 |      0
============================================================
```

---

## Benchmark Run: 2026-07-01 02:45:01

### Summary

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 5135.50 | 5262.68 | 5007.17 | 5262.68 | 0 |
| `memory_store` | 224.70 | 253.05 | 209.86 | 253.05 | 0 |
| `memory_query` | 415.76 | 455.63 | 378.07 | 455.63 | 0 |
| `semantic_search` | 782.41 | 821.84 | 773.44 | 821.84 | 0 |
| `event_log_search` | 752.16 | 774.10 | 739.15 | 774.10 | 0 |
| `kg_query` | 747.56 | 767.69 | 737.38 | 767.69 | 0 |
| `explain_routing` | 0.20 | 0.23 | 0.18 | 0.23 | 0 |

### Full Execution Logs

```text
STRATA MCP Performance Benchmark - 2026-07-01 02:45:01
============================================================
System: Windows 10 (AMD64)
Python: 3.11.9
============================================================

--- Benchmarking 'memory_stats' (10 iterations) ---
[INFO] Starting background SurrealDB reconnect task
  Avg: 5135.50ms
  P95: 5262.68ms
  Min/Max: 5007.17ms / 5262.68ms
  Errors: 0

--- Benchmarking 'memory_store' (10 iterations) ---
[INFO] Initializing Embedding Service with model: sentence-transformers/all-MiniLM-L6-v2...
[OK] Embedding Service initialized
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
  Avg: 224.70ms
  P95: 253.05ms
  Min/Max: 209.86ms / 253.05ms
  Errors: 0

--- Benchmarking 'memory_query' (10 iterations) ---
  Avg: 415.76ms
  P95: 455.63ms
  Min/Max: 378.07ms / 455.63ms
  Errors: 0

--- Benchmarking 'semantic_search' (10 iterations) ---
  Avg: 782.41ms
  P95: 821.84ms
  Min/Max: 773.44ms / 821.84ms
  Errors: 0

--- Benchmarking 'event_log_search' (10 iterations) ---
  Avg: 752.16ms
  P95: 774.10ms
  Min/Max: 739.15ms / 774.10ms
  Errors: 0

--- Benchmarking 'kg_query' (10 iterations) ---
  Avg: 747.56ms
  P95: 767.69ms
  Min/Max: 737.38ms / 767.69ms
  Errors: 0

--- Benchmarking 'explain_routing' (10 iterations) ---
  Avg: 0.20ms
  P95: 0.23ms
  Min/Max: 0.18ms / 0.23ms
  Errors: 0

============================================================
Tool                 |   Avg (ms) |   P95 (ms) | Errors
------------------------------------------------------------
memory_stats         |    5135.50 |    5262.68 |      0
memory_store         |     224.70 |     253.05 |      0
memory_query         |     415.76 |     455.63 |      0
semantic_search      |     782.41 |     821.84 |      0
event_log_search     |     752.16 |     774.10 |      0
kg_query             |     747.56 |     767.69 |      0
explain_routing      |       0.20 |       0.23 |      0
============================================================
```

---

## Benchmark Run: 2026-07-01 03:29:48

### Summary

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 5143.42 | 5250.86 | 5045.51 | 5250.86 | 0 |
| `memory_store` | 226.81 | 256.07 | 191.51 | 256.07 | 0 |
| `memory_query` | 403.11 | 424.83 | 393.38 | 424.83 | 0 |
| `semantic_search` | 816.28 | 873.67 | 781.91 | 873.67 | 0 |
| `event_log_search` | 760.35 | 785.13 | 746.04 | 785.13 | 0 |
| `kg_query` | 761.93 | 798.46 | 746.03 | 798.46 | 0 |
| `explain_routing` | 0.19 | 0.22 | 0.18 | 0.22 | 0 |

### Full Execution Logs

```text
STRATA MCP Performance Benchmark - 2026-07-01 03:29:48
============================================================
System: Windows 10 (AMD64)
Python: 3.11.9
============================================================

--- Benchmarking 'memory_stats' (10 iterations) ---
[INFO] Starting background SurrealDB reconnect task
  Avg: 5143.42ms
  P95: 5250.86ms
  Min/Max: 5045.51ms / 5250.86ms
  Errors: 0

--- Benchmarking 'memory_store' (10 iterations) ---
[INFO] Initializing Embedding Service with model: sentence-transformers/all-MiniLM-L6-v2...
[OK] Embedding Service initialized
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
  Avg: 226.81ms
  P95: 256.07ms
  Min/Max: 191.51ms / 256.07ms
  Errors: 0

--- Benchmarking 'memory_query' (10 iterations) ---
  Avg: 403.11ms
  P95: 424.83ms
  Min/Max: 393.38ms / 424.83ms
  Errors: 0

--- Benchmarking 'semantic_search' (10 iterations) ---
  Avg: 816.28ms
  P95: 873.67ms
  Min/Max: 781.91ms / 873.67ms
  Errors: 0

--- Benchmarking 'event_log_search' (10 iterations) ---
  Avg: 760.35ms
  P95: 785.13ms
  Min/Max: 746.04ms / 785.13ms
  Errors: 0

--- Benchmarking 'kg_query' (10 iterations) ---
  Avg: 761.93ms
  P95: 798.46ms
  Min/Max: 746.03ms / 798.46ms
  Errors: 0

--- Benchmarking 'explain_routing' (10 iterations) ---
  Avg: 0.19ms
  P95: 0.22ms
  Min/Max: 0.18ms / 0.22ms
  Errors: 0

============================================================
Tool                 |   Avg (ms) |   P95 (ms) | Errors
------------------------------------------------------------
memory_stats         |    5143.42 |    5250.86 |      0
memory_store         |     226.81 |     256.07 |      0
memory_query         |     403.11 |     424.83 |      0
semantic_search      |     816.28 |     873.67 |      0
event_log_search     |     760.35 |     785.13 |      0
kg_query             |     761.93 |     798.46 |      0
explain_routing      |       0.19 |       0.22 |      0
============================================================
```

---

## Benchmark Run: 2026-07-01 05:29:13

### Summary

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 789.47 | 814.95 | 775.18 | 814.95 | 0 |
| `memory_store` | 230.05 | 247.09 | 204.92 | 247.09 | 0 |
| `memory_query` | 403.30 | 416.38 | 356.05 | 416.38 | 0 |
| `semantic_search` | 818.95 | 936.97 | 782.16 | 936.97 | 0 |
| `event_log_search` | 1590.20 | 1704.88 | 1507.08 | 1704.88 | 0 |
| `kg_query` | 755.11 | 785.17 | 737.53 | 785.17 | 0 |
| `explain_routing` | 0.19 | 0.23 | 0.18 | 0.23 | 0 |

### Full Execution Logs

```text
STRATA MCP Performance Benchmark - 2026-07-01 05:29:13
============================================================
System: Windows 10 (AMD64)
Python: 3.11.9
============================================================

--- Benchmarking 'memory_stats' (10 iterations) ---
[INFO] Starting background SurrealDB reconnect task
  Avg: 789.47ms
  P95: 814.95ms
  Min/Max: 775.18ms / 814.95ms
  Errors: 0

--- Benchmarking 'memory_store' (10 iterations) ---
[INFO] Initializing Embedding Service with model: sentence-transformers/all-MiniLM-L6-v2...
[OK] Embedding Service initialized
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
  Avg: 230.05ms
  P95: 247.09ms
  Min/Max: 204.92ms / 247.09ms
  Errors: 0

--- Benchmarking 'memory_query' (10 iterations) ---
  Avg: 403.30ms
  P95: 416.38ms
  Min/Max: 356.05ms / 416.38ms
  Errors: 0

--- Benchmarking 'semantic_search' (10 iterations) ---
  Avg: 818.95ms
  P95: 936.97ms
  Min/Max: 782.16ms / 936.97ms
  Errors: 0

--- Benchmarking 'event_log_search' (10 iterations) ---
  Avg: 1590.20ms
  P95: 1704.88ms
  Min/Max: 1507.08ms / 1704.88ms
  Errors: 0

--- Benchmarking 'kg_query' (10 iterations) ---
  Avg: 755.11ms
  P95: 785.17ms
  Min/Max: 737.53ms / 785.17ms
  Errors: 0

--- Benchmarking 'explain_routing' (10 iterations) ---
  Avg: 0.19ms
  P95: 0.23ms
  Min/Max: 0.18ms / 0.23ms
  Errors: 0

============================================================
Tool                 |   Avg (ms) |   P95 (ms) | Errors
------------------------------------------------------------
memory_stats         |     789.47 |     814.95 |      0
memory_store         |     230.05 |     247.09 |      0
memory_query         |     403.30 |     416.38 |      0
semantic_search      |     818.95 |     936.97 |      0
event_log_search     |    1590.20 |    1704.88 |      0
kg_query             |     755.11 |     785.17 |      0
explain_routing      |       0.19 |       0.23 |      0
============================================================
```

---

## Benchmark Run: 2026-07-01 05:36:28

### Summary

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 859.40 | 915.23 | 814.88 | 915.23 | 0 |
| `memory_store` | 212.60 | 226.21 | 203.59 | 226.21 | 0 |
| `memory_query` | 403.02 | 429.38 | 362.04 | 429.38 | 0 |
| `semantic_search` | 803.35 | 828.70 | 791.74 | 828.70 | 0 |
| `event_log_search` | 1552.82 | 1591.52 | 1499.36 | 1591.52 | 0 |
| `kg_query` | 765.94 | 792.75 | 748.48 | 792.75 | 0 |
| `explain_routing` | 0.20 | 0.28 | 0.18 | 0.28 | 0 |

### Full Execution Logs

```text
STRATA MCP Performance Benchmark - 2026-07-01 05:36:28
============================================================
System: Windows 10 (AMD64)
Python: 3.11.9
============================================================

--- Benchmarking 'memory_stats' (10 iterations) ---
[INFO] Starting background SurrealDB reconnect task
  Avg: 859.40ms
  P95: 915.23ms
  Min/Max: 814.88ms / 915.23ms
  Errors: 0

--- Benchmarking 'memory_store' (10 iterations) ---
[INFO] Initializing Embedding Service with model: sentence-transformers/all-MiniLM-L6-v2...
[OK] Embedding Service initialized
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
  Avg: 212.60ms
  P95: 226.21ms
  Min/Max: 203.59ms / 226.21ms
  Errors: 0

--- Benchmarking 'memory_query' (10 iterations) ---
  Avg: 403.02ms
  P95: 429.38ms
  Min/Max: 362.04ms / 429.38ms
  Errors: 0

--- Benchmarking 'semantic_search' (10 iterations) ---
  Avg: 803.35ms
  P95: 828.70ms
  Min/Max: 791.74ms / 828.70ms
  Errors: 0

--- Benchmarking 'event_log_search' (10 iterations) ---
  Avg: 1552.82ms
  P95: 1591.52ms
  Min/Max: 1499.36ms / 1591.52ms
  Errors: 0

--- Benchmarking 'kg_query' (10 iterations) ---
  Avg: 765.94ms
  P95: 792.75ms
  Min/Max: 748.48ms / 792.75ms
  Errors: 0

--- Benchmarking 'explain_routing' (10 iterations) ---
  Avg: 0.20ms
  P95: 0.28ms
  Min/Max: 0.18ms / 0.28ms
  Errors: 0

============================================================
Tool                 |   Avg (ms) |   P95 (ms) | Errors
------------------------------------------------------------
memory_stats         |     859.40 |     915.23 |      0
memory_store         |     212.60 |     226.21 |      0
memory_query         |     403.02 |     429.38 |      0
semantic_search      |     803.35 |     828.70 |      0
event_log_search     |    1552.82 |    1591.52 |      0
kg_query             |     765.94 |     792.75 |      0
explain_routing      |       0.20 |       0.28 |      0
============================================================
```

---

## Benchmark Run: 2026-07-01 05:45:00

### Summary

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 91.14 | 101.47 | 83.44 | 101.47 | 0 |
| `memory_store` | 227.87 | 251.02 | 209.15 | 251.02 | 0 |
| `memory_query` | 401.48 | 431.50 | 377.12 | 431.50 | 0 |
| `semantic_search` | 73.22 | 76.46 | 71.29 | 76.46 | 0 |
| `event_log_search` | 95.75 | 107.44 | 92.07 | 107.44 | 0 |
| `kg_query` | 49.01 | 57.19 | 46.74 | 57.19 | 0 |
| `explain_routing` | 0.19 | 0.23 | 0.18 | 0.23 | 0 |

### Full Execution Logs

```text
STRATA MCP Performance Benchmark - 2026-07-01 05:45:00
============================================================
System: Windows 10 (AMD64)
Python: 3.11.9
============================================================

--- Benchmarking 'memory_stats' (10 iterations) ---
[INFO] Starting background SurrealDB reconnect task
  Avg: 91.14ms
  P95: 101.47ms
  Min/Max: 83.44ms / 101.47ms
  Errors: 0

--- Benchmarking 'memory_store' (10 iterations) ---
[INFO] Initializing Embedding Service with model: sentence-transformers/all-MiniLM-L6-v2...
[OK] Embedding Service initialized
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
  Avg: 227.87ms
  P95: 251.02ms
  Min/Max: 209.15ms / 251.02ms
  Errors: 0

--- Benchmarking 'memory_query' (10 iterations) ---
  Avg: 401.48ms
  P95: 431.50ms
  Min/Max: 377.12ms / 431.50ms
  Errors: 0

--- Benchmarking 'semantic_search' (10 iterations) ---
  Avg: 73.22ms
  P95: 76.46ms
  Min/Max: 71.29ms / 76.46ms
  Errors: 0

--- Benchmarking 'event_log_search' (10 iterations) ---
  Avg: 95.75ms
  P95: 107.44ms
  Min/Max: 92.07ms / 107.44ms
  Errors: 0

--- Benchmarking 'kg_query' (10 iterations) ---
  Avg: 49.01ms
  P95: 57.19ms
  Min/Max: 46.74ms / 57.19ms
  Errors: 0

--- Benchmarking 'explain_routing' (10 iterations) ---
  Avg: 0.19ms
  P95: 0.23ms
  Min/Max: 0.18ms / 0.23ms
  Errors: 0

============================================================
Tool                 |   Avg (ms) |   P95 (ms) | Errors
------------------------------------------------------------
memory_stats         |      91.14 |     101.47 |      0
memory_store         |     227.87 |     251.02 |      0
memory_query         |     401.48 |     431.50 |      0
semantic_search      |      73.22 |      76.46 |      0
event_log_search     |      95.75 |     107.44 |      0
kg_query             |      49.01 |      57.19 |      0
explain_routing      |       0.19 |       0.23 |      0
============================================================
```

---

## Benchmark Run: 2026-07-01 05:47:02

### Summary

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 85.25 | 89.82 | 80.49 | 89.82 | 0 |
| `memory_store` | 222.25 | 255.21 | 198.04 | 255.21 | 0 |
| `memory_query` | 411.34 | 443.04 | 363.80 | 443.04 | 0 |
| `semantic_search` | 70.60 | 73.95 | 68.34 | 73.95 | 0 |
| `event_log_search` | 88.63 | 92.10 | 87.26 | 92.10 | 0 |
| `kg_query` | 45.63 | 48.33 | 43.97 | 48.33 | 0 |
| `explain_routing` | 0.19 | 0.20 | 0.18 | 0.20 | 0 |

### Full Execution Logs

```text
STRATA MCP Performance Benchmark - 2026-07-01 05:47:02
============================================================
System: Windows 10 (AMD64)
Python: 3.11.9
============================================================

--- Benchmarking 'memory_stats' (10 iterations) ---
[INFO] Starting background SurrealDB reconnect task
  Avg: 85.25ms
  P95: 89.82ms
  Min/Max: 80.49ms / 89.82ms
  Errors: 0

--- Benchmarking 'memory_store' (10 iterations) ---
[INFO] Initializing Embedding Service with model: sentence-transformers/all-MiniLM-L6-v2...
[OK] Embedding Service initialized
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
Entropy Gate Decision: {'decision': 'ignore', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'novelty': 2.220446049250313e-16, 'composite_score': 0.29097753379494995, 'threshold': 0.55, 'alpha': 0.35, 'beta': 0.65, 'reason': 'Composite score 0.291 does not meet threshold 0.550'}
  Avg: 222.25ms
  P95: 255.21ms
  Min/Max: 198.04ms / 255.21ms
  Errors: 0

--- Benchmarking 'memory_query' (10 iterations) ---
  Avg: 411.34ms
  P95: 443.04ms
  Min/Max: 363.80ms / 443.04ms
  Errors: 0

--- Benchmarking 'semantic_search' (10 iterations) ---
  Avg: 70.60ms
  P95: 73.95ms
  Min/Max: 68.34ms / 73.95ms
  Errors: 0

--- Benchmarking 'event_log_search' (10 iterations) ---
  Avg: 88.63ms
  P95: 92.10ms
  Min/Max: 87.26ms / 92.10ms
  Errors: 0

--- Benchmarking 'kg_query' (10 iterations) ---
  Avg: 45.63ms
  P95: 48.33ms
  Min/Max: 43.97ms / 48.33ms
  Errors: 0

--- Benchmarking 'explain_routing' (10 iterations) ---
  Avg: 0.19ms
  P95: 0.20ms
  Min/Max: 0.18ms / 0.20ms
  Errors: 0

============================================================
Tool                 |   Avg (ms) |   P95 (ms) | Errors
------------------------------------------------------------
memory_stats         |      85.25 |      89.82 |      0
memory_store         |     222.25 |     255.21 |      0
memory_query         |     411.34 |     443.04 |      0
semantic_search      |      70.60 |      73.95 |      0
event_log_search     |      88.63 |      92.10 |      0
kg_query             |      45.63 |      48.33 |      0
explain_routing      |       0.19 |       0.20 |      0
============================================================
```

---

## Benchmark Run: 2026-07-05 05:12:52

### Summary

| Tool | Avg (ms) | P95 (ms) | Min (ms) | Max (ms) | Errors |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `memory_stats` | 164.72 | 182.28 | 155.67 | 182.28 | 0 |
| `memory_store` | 2311.50 | 2394.48 | 2226.41 | 2394.48 | 0 |
| `memory_query` | 1015.79 | 1052.01 | 999.64 | 1052.01 | 0 |
| `semantic_search` | 154.94 | 170.90 | 147.58 | 170.90 | 0 |
| `event_log_search` | 96.65 | 107.44 | 91.75 | 107.44 | 0 |
| `kg_query` | 51.81 | 58.82 | 48.75 | 58.82 | 0 |

### Full Execution Logs

```text
STRATA MCP Performance Benchmark - 2026-07-05 05:12:52
============================================================
System: Windows 10 (AMD64)
Python: 3.11.9
============================================================

--- Benchmarking 'memory_stats' (10 iterations) ---
[INFO] Starting background SurrealDB reconnect task
  Avg: 164.72ms
  P95: 182.28ms
  Min/Max: 155.67ms / 182.28ms
  Errors: 0

--- Benchmarking 'memory_store' (10 iterations) ---
[INFO] Initializing Embedding Service with model: nomic-ai/nomic-embed-text-v1.5...
[OK] Embedding Service initialized
Entropy Gate Decision: {'decision': 'extract', 'text_entropy': 3.7411397202207834, 'normalized_entropy': 0.8313643822712852, 'compression_ratio': 1.0, 'novelty': 0.3364373728926706, 'composite_score': 0.6260597820141566, 'threshold': 0.30166666666666664, 'alpha': 0.25, 'beta': 0.5, 'gamma': 0.25, 'near_duplicate_warning': False, 'adaptive_min_novelty': 0.051000000000000004, 'reason': 'Composite score 0.626 meets threshold 0.302'}
  [KG] Found candidate entities: ['Benchmark test event']
  [KG] Entity: Benchmark test event (concept) -> entity:yx1v4a6se9ge0lbjbmqm
  [KG] Extraction complete: {'entities_created': 1, 'facts_created': 1}
  [Dedup] Found existing event event:59fbsf1tmiicpcit9e4s for identical content and source
  [KG] Found candidate entities: ['Benchmark test event']
  [KG] Entity: Benchmark test event (concept) -> entity:yx1v4a6se9ge0lbjbmqm
  [Dedup] Found existing event event:59fbsf1tmiicpcit9e4s for identical content and source
  [KG] Found candidate entities: ['Benchmark test event']
  [KG] Entity: Benchmark test event (concept) -> entity:yx1v4a6se9ge0lbjbmqm
  [Dedup] Found existing event event:59fbsf1tmiicpcit9e4s for identical content and source
  [KG] Found candidate entities: ['Benchmark test event']
  [KG] Entity: Benchmark test event (concept) -> entity:yx1v4a6se9ge0lbjbmqm
  [Dedup] Found existing event event:59fbsf1tmiicpcit9e4s for identical content and source
  [KG] Found candidate entities: ['Benchmark test event']
  [KG] Entity: Benchmark test event (concept) -> entity:yx1v4a6se9ge0lbjbmqm
  [Dedup] Found existing event event:59fbsf1tmiicpcit9e4s for identical content and source
  [KG] Found candidate entities: ['Benchmark test event']
  [KG] Entity: Benchmark test event (concept) -> entity:yx1v4a6se9ge0lbjbmqm
  [Dedup] Found existing event event:59fbsf1tmiicpcit9e4s for identical content and source
  [KG] Found candidate entities: ['Benchmark test event']
  [KG] Entity: Benchmark test event (concept) -> entity:yx1v4a6se9ge0lbjbmqm
  [Dedup] Found existing event event:59fbsf1tmiicpcit9e4s for identical content and source
  [KG] Found candidate entities: ['Benchmark test event']
  [KG] Entity: Benchmark test event (concept) -> entity:yx1v4a6se9ge0lbjbmqm
  [Dedup] Found existing event event:59fbsf1tmiicpcit9e4s for identical content and source
  [KG] Found candidate entities: ['Benchmark test event']
  [KG] Entity: Benchmark test event (concept) -> entity:yx1v4a6se9ge0lbjbmqm
  [Dedup] Found existing event event:59fbsf1tmiicpcit9e4s for identical content and source
  [KG] Found candidate entities: ['Benchmark test event']
  [KG] Entity: Benchmark test event (concept) -> entity:yx1v4a6se9ge0lbjbmqm
  [Dedup] Found existing event event:59fbsf1tmiicpcit9e4s for identical content and source
  [KG] Found candidate entities: ['Benchmark test event']
  [KG] Entity: Benchmark test event (concept) -> entity:yx1v4a6se9ge0lbjbmqm
  Avg: 2311.50ms
  P95: 2394.48ms
  Min/Max: 2226.41ms / 2394.48ms
  Errors: 0

--- Benchmarking 'memory_query' (10 iterations) ---
  Avg: 1015.79ms
  P95: 1052.01ms
  Min/Max: 999.64ms / 1052.01ms
  Errors: 0

--- Benchmarking 'semantic_search' (10 iterations) ---
  Avg: 154.94ms
  P95: 170.90ms
  Min/Max: 147.58ms / 170.90ms
  Errors: 0

--- Benchmarking 'event_log_search' (10 iterations) ---
  Avg: 96.65ms
  P95: 107.44ms
  Min/Max: 91.75ms / 107.44ms
  Errors: 0

--- Benchmarking 'kg_query' (10 iterations) ---
  Avg: 51.81ms
  P95: 58.82ms
  Min/Max: 48.75ms / 58.82ms
  Errors: 0

--- Benchmarking 'explain_routing' (10 iterations) ---
Warmup failed for explain_routing: Unknown tool: explain_routing
============================================================
Tool                 |   Avg (ms) |   P95 (ms) | Errors
------------------------------------------------------------
memory_stats         |     164.72 |     182.28 |      0
memory_store         |    2311.50 |    2394.48 |      0
memory_query         |    1015.79 |    1052.01 |      0
semantic_search      |     154.94 |     170.90 |      0
event_log_search     |      96.65 |     107.44 |      0
kg_query             |      51.81 |      58.82 |      0
============================================================
```

---
