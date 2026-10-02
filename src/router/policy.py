"""
Routing Policy with cost awareness and adaptive enforcement.
Implements adaptive routing based on query type and learned strategy effectiveness.
"""

from typing import Dict, Optional, Any, Tuple
from enum import Enum
import re
import threading
from datetime import datetime, timedelta
import logging
from .cost_awareness import cost_tracker
from .budget import BudgetLevel, BudgetTracker


class OverBudget(Exception):
    """Raised when a request exceeds its allocated budget."""
    pass


class QueryType(Enum):
    TEMPORAL = "temporal"
    FACTUAL = "factual"
    MULTI_HOP = "multi_hop"
    CONVERSATIONAL = "conversational"
    UPDATE = "update"


# Budget step-down for degraded (low-confidence) queries: spend less when
# uncertain, but keep spending on the right strategy. Never below LOW.
_DEGRADED_BUDGET = {
    BudgetLevel.HIGH: BudgetLevel.MEDIUM,
    BudgetLevel.MEDIUM: BudgetLevel.LOW,
    BudgetLevel.LOW: BudgetLevel.LOW,
}

# Degraded UPDATE must be read-only. knowledge_graph_with_invalidation triggers
# writes (logical invalidation), so an uncertain update degrades to the plain
# KG read instead -- never to the write path, never to a generic fallback.
_UPDATE_DEGRADED_STRATEGY = "knowledge_graph_first"


_SEPARATOR_RE = re.compile(r"[\s\-]+")


def _is_known_query_type(value) -> bool:
    """True iff value denotes a real QueryType (enum member or exact string).

    resolve_query_type() silently maps garbage to FACTUAL; this distinguishes
    "caller said factual" from "caller said nonsense", so only the latter
    gets the generic fallback policy.
    """
    if isinstance(value, QueryType):
        return True
    if not isinstance(value, str):
        return False
    try:
        QueryType(_SEPARATOR_RE.sub("_", value.strip().lower()))
        return True
    except ValueError:
        return False


def resolve_query_type(query_type) -> QueryType:
    """Normalize a classifier/caller-supplied query type into a QueryType.

    The classifier emits "multi-hop" while the enum value is "multi_hop",
    so separators are normalized here. Unknown values fall back to FACTUAL
    instead of raising, so one odd label can never abort a query.
    """
    if isinstance(query_type, QueryType):
        return query_type
    try:
        normalized = _SEPARATOR_RE.sub("_", str(query_type).strip().lower())
        return QueryType(normalized)
    except ValueError:
        logging.warning("Unknown query type '%s', falling back to FACTUAL", query_type)
        return QueryType.FACTUAL


class RoutingPolicy:
    """
    Determines routing strategy based on query type and learned effectiveness.
    Now incorporates adaptive cost-awareness using CostTracker metrics.
    """
    
    def __init__(self, config: Optional[Dict[str, Dict[str, Any]]] = None):
        # Thread safety for concurrent access
        self._lock = threading.RLock()
        
        # Store usage patterns per query type (timestamp-based for cleanup)
        self._usage: Dict[str, Dict[str, Any]] = {}
        
        # Default configuration per query type
        self.config = {
            QueryType.TEMPORAL: {
                'strategy': 'event_log_first',
                'budget': BudgetLevel.MEDIUM,
                'min_confidence': 0.5,
                'max_latency_threshold': 1.0  # seconds
            },
            QueryType.FACTUAL: {
                'strategy': 'semantic_hybrid',
                'budget': BudgetLevel.HIGH,
                'min_confidence': 0.4,
                'max_latency_threshold': 1.5
            },
            QueryType.MULTI_HOP: {
                'strategy': 'hybrid_with_graph_expansion',
                'budget': BudgetLevel.HIGH,
                # Was 0.8, which sat above the classifier's operating range:
                # genuine multi-hop queries score 0.68/0.71 and were sent to
                # the generic fallback -- exactly the queries needing graph
                # expansion. Aligned with the 0.6 ML confidence gate: anything
                # the classifier calls multi-hop gets the multi-hop strategy.
                'min_confidence': 0.6,
                'max_latency_threshold': 2.0
            },
            QueryType.CONVERSATIONAL: {
                'strategy': 'hybrid_bm25_vector_temporal',
                'budget': BudgetLevel.MEDIUM,
                'min_confidence': 0.6,
                'max_latency_threshold': 1.2
            },
            QueryType.UPDATE: {
                'strategy': 'knowledge_graph_with_invalidation',
                'budget': BudgetLevel.HIGH,
                'min_confidence': 0.9,
                'max_latency_threshold': 1.5
            }
        }
        
        # Übernahme Custom-Konfiguration falls übergeben
        if config:
            for qt_key, cfg in config.items():
                try:
                    qt = QueryType(qt_key) if isinstance(qt_key, str) else qt_key
                    if qt in self.config:
                        self.config[qt].update(cfg)
                except (ValueError, KeyError):
                    logging.warning(f"Ignoring unknown query type in custom config: {qt_key}")

        # Cleanup interval for usage tracking (avoid memory leaks)
        self._cleanup_interval = timedelta(minutes=30)
        self._last_cleanup = datetime.now()

    def _cleanup_old_usage(self):
        """Remove old usage entries to prevent memory leaks."""
        now = datetime.now()
        if now - self._last_cleanup > self._cleanup_interval:
            with self._lock:
                # Remove entries older than 1 hour
                cutoff = now - timedelta(hours=1)
                keys_to_remove = [
                    k for k, v in self._usage.items()
                    if v.get('timestamp', datetime.min) < cutoff
                ]
                
                for key in keys_to_remove:
                    del self._usage[key]
                
                self._last_cleanup = now

    def _get_adapted_strategy(self, query_type: QueryType) -> str:
        """
        Get the most effective strategy for a query type based on learned metrics.
        Ranks within this query type's context first: a strategy that proved
        itself on factual queries must not hijack temporal routing on the
        strength of a global average. Falls back to the global ranking and
        then to the configured default when the context is still cold.
        """
        with self._lock:
            # Get base strategy from config
            base_config = self.config.get(query_type)
            if not base_config:
                # Fallback to factual if unknown query type
                base_config = self.config[QueryType.FACTUAL]
                logging.warning(f"Unknown query type {query_type}, falling back to factual config")
            
            base_strategy = base_config['strategy']
            max_latency = base_config.get('max_latency_threshold')

            # Context-first, then global, then default: a cold context must not
            # block learning, and no learning data must not block routing.
            for ranked_strategies in (
                cost_tracker.get_all_strategies_ranked(query_type=query_type.value),
                cost_tracker.get_all_strategies_ranked(),
            ):
                for strategy, score in ranked_strategies:
                    # Only consider strategies that are valid for this query type
                    if not self._is_strategy_appropriate_for_query_type(strategy, query_type):
                        continue
                    # Skip strategies that are too slow for this query type's SLO
                    if max_latency is not None:
                        latency = cost_tracker.get_average_latency(
                            strategy, query_type=query_type.value)
                        if latency is None:
                            latency = cost_tracker.get_average_latency(strategy)
                        if latency is not None and latency > max_latency:
                            continue
                    return strategy

            # Fall back to configured default
            return base_strategy

    def _is_strategy_appropriate_for_query_type(self, strategy: str, query_type: QueryType) -> bool:
        """Check if a strategy is appropriate for a specific query type."""
        # Define strategy-query type compatibility
        compatible_strategies = {
            QueryType.TEMPORAL: ['event_log_first', 'hybrid_bm25_vector_temporal', 'semantic_hybrid'],
            QueryType.FACTUAL: ['semantic_hybrid', 'knowledge_graph_first', 'hybrid_with_graph_expansion'],
            QueryType.MULTI_HOP: ['semantic_hybrid', 'hybrid_with_graph_expansion', 'knowledge_graph_with_invalidation', 'graph_ppr_rerank', 'decomposed_multihop'],
            QueryType.CONVERSATIONAL: ['semantic_hybrid', 'hybrid_bm25_vector_temporal', 'composite_kg_vector'],
            QueryType.UPDATE: ['knowledge_graph_with_invalidation', 'knowledge_graph_first']
        }
        
        compatible = compatible_strategies.get(query_type, [])
        return strategy in compatible

    def _resolve_query_type(self, query_type) -> QueryType:
        """Accept QueryType enums or their string values, defaulting to FACTUAL."""
        return resolve_query_type(query_type)

    def _config_for(self, query_type: QueryType) -> Dict[str, Any]:
        base_config = self.config.get(query_type)
        if not base_config:
            logging.warning(f"Unknown query type {query_type}, falling back to factual config")
            base_config = self.config[QueryType.FACTUAL]
        return base_config

    def get_strategy(self, query_type: QueryType, confidence: float) -> Tuple[str, BudgetLevel, str]:
        """
        Determine the optimal strategy based on query type, confidence, and learned effectiveness.
        Accepts both QueryType enums and their string values.
        
        Returns:
            Tuple of (strategy, budget_level, policy_applied) where
            policy_applied is "strict" (confident: full strategy, full budget),
            "degraded" (uncertain: type-appropriate strategy, stepped-down
            budget; UPDATE degrades to a read-only strategy), or "fallback"
            (unknown query type: factual default).
        """
        resolved = self._resolve_query_type(query_type)
        # An unresolvable type is the only true fallback: the classifier's
        # guess carries no information at all.
        known = _is_known_query_type(query_type)
        query_type = resolved

        with self._lock:
            # Perform periodic cleanup
            self._cleanup_old_usage()

            # Get base configuration
            base_config = self._config_for(query_type)

            if not known:
                strategy = self._get_adapted_strategy(QueryType.FACTUAL)
                policy_applied = "fallback"
                budget = self.config[QueryType.FACTUAL]['budget']
            elif confidence >= base_config['min_confidence']:
                strategy = self._get_adapted_strategy(query_type)
                policy_applied = "strict"
                budget = base_config['budget']
            else:
                # Graded fallback (RouteRAG "minimal sufficient retrieval"):
                # the type guess stays informative when uncertain, so keep the
                # type-appropriate strategy and spend less on it.
                if query_type == QueryType.UPDATE:
                    strategy = _UPDATE_DEGRADED_STRATEGY
                else:
                    strategy = self._get_adapted_strategy(query_type)
                policy_applied = "degraded"
                budget = _DEGRADED_BUDGET[base_config['budget']]

            # Record this usage pattern
            usage_key = f"{query_type.value}_{datetime.now().isoformat()}"
            self._usage[usage_key] = {
                'query_type': query_type.value,
                'strategy': strategy,
                'confidence': confidence,
                'budget': budget.value,
                'timestamp': datetime.now(),
                'policy_applied': policy_applied
            }
            
            return strategy, budget, policy_applied

    def get_budget_for_query(self, query_type: QueryType) -> BudgetLevel:
        """Get the appropriate budget level for a query type."""
        with self._lock:
            return self._config_for(self._resolve_query_type(query_type))['budget']

    def update_query_config(self, query_type: QueryType, **kwargs):
        """Update configuration for a specific query type."""
        with self._lock:
            query_type = self._resolve_query_type(query_type)
            if query_type in self.config:
                self.config[query_type].update(kwargs)
            else:
                raise ValueError(f"Unknown query type: {query_type}")

    def get_all_costs(self) -> Dict:
        """Get all cost information from both policy and cost tracker."""
        with self._lock:
            return {
                'policy_config': {
                    qt.value: config for qt, config in self.config.items()
                },
                'cost_tracker_metrics': cost_tracker.get_all_costs(),
                'system_health': BudgetTracker.get_system_health(),
                'usage_patterns_count': len(self._usage)
            }


_policy_lock = threading.Lock()
_shared_policy: Optional[RoutingPolicy] = None


def get_policy() -> RoutingPolicy:
    """Return the process-wide RoutingPolicy.

    Usage statistics and config updates only live on the instance, so building
    a fresh RoutingPolicy per request threw that state away on every call.
    Learned strategy effectiveness survives in the global cost_tracker, but the
    usage log and any update_query_config() changes did not.
    """
    global _shared_policy
    if _shared_policy is None:
        with _policy_lock:
            if _shared_policy is None:
                _shared_policy = RoutingPolicy()
    return _shared_policy
