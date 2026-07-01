"""
Cost Awareness Module for Router
Empirically calibrated cost model, fed by BudgetTracker execution data.
"""
import time
from collections import defaultdict
from typing import Dict, Any, Optional


class CostTracker:
    """
    Tracks and calibrates strategy costs from real BudgetTracker execution metrics.
    Connects to BudgetTracker (policy.py) so cost data is empirical, not guessed.
    """

    def __init__(self):
        # Strategy → aggregated metrics from real BudgetTracker data
        self.metrics = defaultdict(lambda: {
            'total_queries': 0,
            'total_db_calls': 0,
            'total_tokens': 0,
            'total_latency': 0.0,
            'successful_queries': 0,
            'total_cost': 0.0,
            'db_calls_list': [],
            'tokens_list': [],
            'latencies': [],
            'costs': [],
        })

        # Default weights – werden durch calibrate() überschrieben
        self._db_call_weight = 1.0
        self._token_weight = 0.001
        self._latency_weight = 0.5

    # ── Primäre API: Gefüttert von BudgetTracker ──────────────────────

    def feed_budget_tracker(self, strategy: str, budget_data: Dict[str, Any], success: bool = True) -> float:
        """
        Nimmt echte Ausführungsdaten von BudgetTracker.to_dict() entgegen.
        Berechnet die Kosten aus tatsächlichen db_calls, tokens und Laufzeit.
        Gibt die berechneten Kosten zurück.
        """
        db_calls = budget_data.get('db_calls', 0)
        tokens = budget_data.get('estimated_tokens', 0)
        duration = budget_data.get('duration_seconds', 0.0)

        cost = self._calculate_empirical_cost(db_calls, tokens, duration)

        m = self.metrics[strategy]
        m['total_queries'] += 1
        m['total_db_calls'] += db_calls
        m['total_tokens'] += tokens
        m['total_latency'] += duration
        m['total_cost'] += cost
        m['db_calls_list'].append(db_calls)
        m['tokens_list'].append(tokens)
        m['latencies'].append(duration)
        m['costs'].append(cost)

        if success:
            m['successful_queries'] += 1

        return cost

    # ── Legacy-Kompatibilität ─────────────────────────────────────────

    def track_query(self, strategy: str, latency: float = 0.0,
                    num_queries: int = 1, success: bool = False,
                    relevance: float = 0.5) -> None:
        """
        Legacy-Methode – wird durch feed_budget_tracker() ersetzt.
        Wandelt die alten Parameter in einen BudgetTracker-ähnlichen Dict um.
        """
        budget_data = {
            'db_calls': num_queries,
            'estimated_tokens': int(max(1, latency * 1000)),
            'duration_seconds': latency,
        }
        self.feed_budget_tracker(strategy, budget_data, success)

    # ── Kostenberechnung ──────────────────────────────────────────────

    def _calculate_empirical_cost(self, db_calls: int, tokens: int, duration: float) -> float:
        """Kosten aus tatsächlichem Ressourcenverbrauch."""
        return (db_calls * self._db_call_weight
                + tokens * self._token_weight
                + duration * self._latency_weight)

    def get_empirical_base_cost(self, strategy: str) -> float:
        """
        Gibt den empirisch ermittelten Basiskostenfaktor pro Query für eine Strategie zurück.
        Liefert einen Fallback-Schätzwert, solange noch keine Echtzeit-Daten vorliegen.
        """
        m = self.metrics.get(strategy)
        if not m or m['total_queries'] == 0:
            return self._fallback_base_cost(strategy)

        avg_db = sum(m['db_calls_list']) / len(m['db_calls_list'])
        avg_tokens = sum(m['tokens_list']) / len(m['tokens_list'])
        avg_dur = sum(m['latencies']) / len(m['latencies'])
        return self._calculate_empirical_cost(int(avg_db), int(avg_tokens), avg_dur)

    @staticmethod
    def _fallback_base_cost(strategy: str) -> float:
        """Schätzwerte, bis echte Daten vorliegen (werden von calibrate überschrieben)."""
        return {
            'event_log_first': 1.0,
            'knowledge_graph_first': 1.0,
            'hybrid_fallback': 2.0,
            'composite_kg_vector': 3.0,
            'hybrid_with_graph_expansion': 4.0,
            'knowledge_graph_with_invalidation': 5.0,
        }.get(strategy, 2.0)

    # ── Selbstkalibrierung ────────────────────────────────────────────

    def calibrate(self) -> dict:
        """
        Kalibriert die Gewichte auf Basis der historischen Daten aller Strategien.
        Sollte periodisch aufgerufen werden (z. B. alle 100 Queries).
        """
        all_db = []
        all_tok = []
        all_dur = []
        for m in self.metrics.values():
            all_db.extend(m['db_calls_list'])
            all_tok.extend(m['tokens_list'])
            all_dur.extend(m['latencies'])

        if not all_db:
            return {'status': 'skipped', 'reason': 'no_data'}

        avg_db = sum(all_db) / len(all_db) if all_db else 1
        avg_tok = sum(all_tok) / len(all_tok) if all_tok else 1
        avg_dur = sum(all_dur) / len(all_dur) if all_dur else 0.1

        self._db_call_weight = 1.0
        self._token_weight = max(0.0001, 1.0 / max(avg_tok, 1))
        self._latency_weight = max(0.01, 1.0 / max(avg_dur, 0.01))

        return {
            'status': 'calibrated',
            'db_call_weight': round(self._db_call_weight, 4),
            'token_weight': round(self._token_weight, 6),
            'latency_weight': round(self._latency_weight, 4),
            'samples': len(all_db),
        }

    # ── Abfragen ──────────────────────────────────────────────────────

    def get_average_cost(self, strategy: str) -> Dict[str, float]:
        m = self.metrics.get(strategy)
        if not m or m['total_queries'] == 0:
            return {'latency': 0.0, 'success_rate': 0.0, 'cost': 0.0, 'avg_db_calls': 0.0, 'avg_tokens': 0.0}

        total_q = m['total_queries']
        return {
            'latency': m['total_latency'] / total_q,
            'success_rate': m['successful_queries'] / total_q,
            'cost': m['total_cost'] / total_q,
            'avg_db_calls': m['total_db_calls'] / total_q,
            'avg_tokens': m['total_tokens'] / total_q,
        }

    def get_all_costs(self) -> Dict[str, Dict[str, float]]:
        return {s: self.get_average_cost(s) for s in self.metrics.keys()}

    def get_calibration_state(self) -> dict:
        return {
            'db_call_weight': self._db_call_weight,
            'token_weight': self._token_weight,
            'latency_weight': self._latency_weight,
            'strategies': {
                s: {
                    'total_queries': m['total_queries'],
                    'successful_queries': m['successful_queries'],
                    'total_db_calls': m['total_db_calls'],
                    'total_tokens': m['total_tokens'],
                }
                for s, m in self.metrics.items()
            },
        }


if __name__ == "__main__":
    tracker = CostTracker()

    # Simuliere echte BudgetTracker-Daten statt Zufallszahlen
    scenarios = {
        'event_log_first': [
            {'db_calls': 1, 'estimated_tokens': 150, 'duration_seconds': 0.04},
            {'db_calls': 1, 'estimated_tokens': 200, 'duration_seconds': 0.06},
            {'db_calls': 1, 'estimated_tokens': 180, 'duration_seconds': 0.05},
        ],
        'hybrid_with_graph_expansion': [
            {'db_calls': 3, 'estimated_tokens': 450, 'duration_seconds': 0.15},
            {'db_calls': 4, 'estimated_tokens': 600, 'duration_seconds': 0.22},
            {'db_calls': 3, 'estimated_tokens': 500, 'duration_seconds': 0.18},
        ],
        'knowledge_graph_with_invalidation': [
            {'db_calls': 5, 'estimated_tokens': 800, 'duration_seconds': 0.35},
            {'db_calls': 6, 'estimated_tokens': 950, 'duration_seconds': 0.42},
        ],
    }

    for strategy, data_list in scenarios.items():
        for data in data_list:
            tracker.feed_budget_tracker(strategy, data, success=True)

    print("Vor Kalibrierung:")
    for s, m in tracker.get_all_costs().items():
        print(f"  {s}: cost={m['cost']:.3f}, latency={m['latency']:.3f}s, "
              f"db_calls={m['avg_db_calls']:.1f}, tokens={m['avg_tokens']:.0f}")

    cal = tracker.calibrate()
    print(f"\nKalibrierung: {cal}")

    print("\nEmpirische Basiskosten:")
    for s in scenarios:
        print(f"  {s}: {tracker.get_empirical_base_cost(s):.4f}")
