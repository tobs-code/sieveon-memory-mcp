from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import threading
from datetime import datetime, timedelta


class CostTracker:
    """
    Tracks performance metrics per strategy including latency, success rate, and cost.
    Implements adaptive cost awareness by adjusting strategy effectiveness based on relevance feedback.

    Metrics are keyed by (query_type, strategy): a strategy that shines for
    factual queries must not hijack temporal routing on the strength of its
    global average. Callers that do not know the query type use "unknown" and
    read the aggregated view, which behaves like the old global tracker.
    """

    def __init__(self):
        # Thread-safe storage for metrics
        self._metrics_lock = threading.RLock()
        
        # Track strategy performance per context:
        # {(query_type, strategy): {metric: value}}
        self._metrics = defaultdict(lambda: {
            'latency_sum': 0.0,
            'latency_count': 0,
            'success_count': 0,
            'total_count': 0,
            'cost_sum': 0.0,
            'cost_count': 0,
            'last_used': None
        })

        # Monotonic record counter for snapshot cadence (persist every N).
        self._total_records = 0
        
        # Base costs per strategy (reflects computational complexity)
        self.base_costs = {
            'event_log_first': 0.5,
            'knowledge_graph_first': 1.0,
            'hybrid_with_graph_expansion': 1.2,
            # 4 parallel searches including the embedding call for the vector side
            'composite_kg_vector': 1.5,
            # Read-only: no writes, just a validity-window filter on the results
            'knowledge_graph_with_invalidation': 1.1,
            'hybrid_bm25_vector_temporal': 1.1,
            'hybrid_fallback': 0.8,
            # Most expensive: 4 parallel searches plus bounded graph expansion
            'semantic_hybrid': 2.0,
            # Vector search + BFS traversal + in-memory personalized PageRank
            'graph_ppr_rerank': 1.5,
            # 2 searches per sub-query part plus entity lookups
            'decomposed_multihop': 1.7,
        }

    MIN_SAMPLES = 3

    @staticmethod
    def _key(query_type: Optional[str], strategy: str) -> tuple:
        return (str(query_type or "unknown"), str(strategy))

    def _aggregate(self, strategy: str) -> Dict:
        """Sum raw metrics for a strategy across all query-type contexts."""
        out = {'latency_sum': 0.0, 'latency_count': 0, 'success_count': 0,
               'total_count': 0, 'cost_sum': 0.0, 'cost_count': 0, 'last_used': None}
        for (qt, s), m in self._metrics.items():
            if s != str(strategy):
                continue
            for k in ('latency_sum', 'cost_sum'):
                out[k] += m[k]
            for k in ('latency_count', 'success_count', 'total_count', 'cost_count'):
                out[k] += m[k]
            if m['last_used'] and (out['last_used'] is None or m['last_used'] > out['last_used']):
                out['last_used'] = m['last_used']
        return out

    def _select(self, strategy: str, query_type: Optional[str]) -> Dict:
        if query_type is None:
            return self._aggregate(strategy)
        return self._metrics[self._key(query_type, strategy)]

    def record_request(self, strategy: str, latency: float, success: bool, num_queries: int = 1, relevance: float = 1.0, query_type: Optional[str] = None):
        """
        Records a request with its performance metrics.
        
        Args:
            strategy: The strategy used
            latency: Time taken in seconds
            success: Whether the request was successful
            num_queries: Number of database queries made
            relevance: Relevance score of results (0.0 to 1.0)
            query_type: QueryType value (e.g. "factual") or None. Recorded so
                effectiveness is learned per context, not globally.
        """
        with self._metrics_lock:
            metrics = self._metrics[self._key(query_type, strategy)]
            self._total_records += 1
            
            # Update basic metrics
            metrics['latency_sum'] += latency
            metrics['latency_count'] += 1
            
            if success:
                metrics['success_count'] += 1
            metrics['total_count'] += 1
            
            # Calculate cost using formula: base_cost * num_queries * (1.0 + (1.0 - relevance))
            base_cost = self.base_costs.get(strategy, 1.0)
            calculated_cost = base_cost * num_queries * (1.0 + (1.0 - relevance))
            
            metrics['cost_sum'] += calculated_cost
            metrics['cost_count'] += 1
            metrics['last_used'] = datetime.now()

    def get_average_latency(self, strategy: str, query_type: Optional[str] = None) -> Optional[float]:
        """Returns average latency for a strategy (optionally within one query-type context)."""
        with self._metrics_lock:
            metrics = self._select(strategy, query_type)
            if metrics['latency_count'] > 0:
                return metrics['latency_sum'] / metrics['latency_count']
            return None

    def get_success_rate(self, strategy: str, query_type: Optional[str] = None) -> Optional[float]:
        """Returns success rate for a strategy (optionally within one context)."""
        with self._metrics_lock:
            metrics = self._select(strategy, query_type)
            if metrics['total_count'] > 0:
                return metrics['success_count'] / metrics['total_count']
            return None

    def get_average_cost(self, strategy: str, query_type: Optional[str] = None) -> Optional[float]:
        """Returns average cost for a strategy (optionally within one context)."""
        with self._metrics_lock:
            metrics = self._select(strategy, query_type)
            if metrics['cost_count'] > 0:
                return metrics['cost_sum'] / metrics['cost_count']
            return None

    def _effectiveness_from(self, metrics: Dict) -> float:
        total = metrics['total_count']
        success_rate = (metrics['success_count'] / total) if total > 0 else 0.0
        if metrics['cost_count'] > 0:
            avg_cost = metrics['cost_sum'] / metrics['cost_count']
            cost_efficiency = max(0.0, min(1.0, (5.0 - avg_cost) / 5.0))
        else:
            cost_efficiency = 0.5
        recency_bonus = 1.0
        if metrics['last_used']:
            if datetime.now() - metrics['last_used'] < timedelta(hours=1):
                recency_bonus = 1.05
        return max(0.0, min(1.0, (success_rate * 0.6 + cost_efficiency * 0.4) * recency_bonus))

    def get_effectiveness_score(self, strategy: str, query_type: Optional[str] = None) -> float:
        """
        Returns a combined effectiveness score (0.0 to 1.0) based on:
        - Success rate (higher is better)
        - Average cost (lower is better)
        - Recency of usage (more recent is better)
        
        Higher score means more effective strategy.
        """
        with self._metrics_lock:
            return self._effectiveness_from(self._select(strategy, query_type))

    def get_all_strategies_ranked(self, query_type: Optional[str] = None) -> List[Tuple[str, float]]:
        """
        Returns all strategies ranked by effectiveness (best first).
        With a query_type, ranks within that context only -- a strategy with
        no samples in this context is invisible here, so it cannot hijack
        routing on the strength of another context. Without one, aggregates
        across contexts (the legacy global view).
        Strategies with fewer than MIN_SAMPLES observations are omitted so that
        adaptive routing does not flip on a single noisy request.
        """
        with self._metrics_lock:
            by_strategy: Dict[str, Dict] = {}
            for (qt, s), m in self._metrics.items():
                if query_type is not None and qt != str(query_type):
                    continue
                agg = by_strategy.setdefault(s, {'latency_sum': 0.0, 'latency_count': 0,
                    'success_count': 0, 'total_count': 0, 'cost_sum': 0.0,
                    'cost_count': 0, 'last_used': None})
                for k in ('latency_sum', 'cost_sum'):
                    agg[k] += m[k]
                for k in ('latency_count', 'success_count', 'total_count', 'cost_count'):
                    agg[k] += m[k]
                if m['last_used'] and (agg['last_used'] is None or m['last_used'] > agg['last_used']):
                    agg['last_used'] = m['last_used']
            ranked = []
            for strategy, agg in by_strategy.items():
                if agg['total_count'] < self.MIN_SAMPLES:
                    continue
                ranked.append((strategy, self._effectiveness_from(agg)))
            return sorted(ranked, key=lambda x: x[1], reverse=True)

    def get_all_costs(self) -> Dict[str, Dict]:
        """Returns all cost metrics, aggregated across contexts (legacy shape:
        {strategy: {...}} so existing consumers keep working)."""
        with self._metrics_lock:
            strategies = {s for (_, s) in self._metrics.keys()}
            result = {}
            for strategy in strategies:
                agg = self._aggregate(strategy)
                result[strategy] = {
                    'average_latency': (agg['latency_sum'] / agg['latency_count']
                                        if agg['latency_count'] else None),
                    'success_rate': (agg['success_count'] / agg['total_count']
                                     if agg['total_count'] else None),
                    'average_cost': (agg['cost_sum'] / agg['cost_count']
                                     if agg['cost_count'] else None),
                    'total_requests': agg['total_count'],
                    'effectiveness_score': self._effectiveness_from(agg),
                }
            return result

    def get_costs_by_context(self) -> Dict[str, Dict[str, Dict]]:
        """Per-context view: {query_type: {strategy: {...}}}. This is where
        learning actually lives; get_all_costs() is the flattened legacy view."""
        with self._metrics_lock:
            out: Dict[str, Dict[str, Dict]] = {}
            for (qt, s), m in self._metrics.items():
                out.setdefault(qt, {})[s] = {
                    'average_latency': (m['latency_sum'] / m['latency_count']
                                        if m['latency_count'] else None),
                    'success_rate': (m['success_count'] / m['total_count']
                                     if m['total_count'] else None),
                    'average_cost': (m['cost_sum'] / m['cost_count']
                                     if m['cost_count'] else None),
                    'total_requests': m['total_count'],
                    'effectiveness_score': self._effectiveness_from(m),
                }
            return out

    def export_state(self) -> Dict:
        """Plain-JSON snapshot for persistence (DB row, file, ...)."""
        with self._metrics_lock:
            out: Dict[str, Dict[str, Dict]] = {}
            for (qt, s), m in self._metrics.items():
                row = dict(m)
                lu = row.get('last_used')
                # datetimes are not JSON-serializable; ISO strings are
                row['last_used'] = lu.isoformat() if hasattr(lu, 'isoformat') else None
                out.setdefault(qt, {})[s] = row
            return {'version': 1, 'metrics': out}

    def import_state(self, state: Dict) -> None:
        """Restore a snapshot from export_state(). Unknown shapes are ignored
        (fail-open: bad persisted data must never break routing)."""
        try:
            metrics = (state or {}).get('metrics') or {}
            if not isinstance(metrics, dict):
                return
            with self._metrics_lock:
                for qt, by_strategy in metrics.items():
                    if not isinstance(by_strategy, dict):
                        continue
                    for s, m in by_strategy.items():
                        if not isinstance(m, dict):
                            continue
                        key = (str(qt), str(s))
                        slot = self._metrics[key]
                        for k in ('latency_sum', 'latency_count', 'success_count',
                                  'total_count', 'cost_sum', 'cost_count'):
                            v = m.get(k, 0)
                            slot[k] = v if isinstance(v, (int, float)) else 0
                        lu = m.get('last_used')
                        if isinstance(lu, str):
                            try:
                                lu = datetime.fromisoformat(lu)
                            except ValueError:
                                lu = None
                        slot['last_used'] = lu if isinstance(lu, datetime) else None
                    # Restore the snapshot cadence counter from the data so a
                    # restart does not snapshot on its very first request.
                    self._total_records = sum(
                        m.get('total_count', 0) if isinstance(m, dict) else 0
                        for by_strategy in metrics.values()
                        if isinstance(by_strategy, dict)
                        for m in by_strategy.values()
                    )
        except Exception:
            return

    def reset_metrics(self):
        """Resets all metrics."""
        with self._metrics_lock:
            self._metrics.clear()
            self._total_records = 0

    def total_records(self) -> int:
        """Monotonic count of recorded requests (for snapshot cadence)."""
        with self._metrics_lock:
            return self._total_records


# Global instance for cross-module access
cost_tracker = CostTracker()