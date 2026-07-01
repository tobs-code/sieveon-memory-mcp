"""
Adaptive Routing Policy for Strata
Based on query type and confidence, decides which strategy to use
Includes historical performance tracking for dynamic threshold adjustment.
Integrated with CostTracker for empirical cost calibration.
"""
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from collections import defaultdict

try:
    import tiktoken
except ImportError:  # pragma: no cover
    tiktoken = None  # type: ignore

from src.router.cost_awareness import CostTracker


class OverBudget(Exception):
    """Raised when a query exceeds its configured cost budget."""
    pass


class BudgetTracker:
    """Tracks resource consumption against a cost budget with adaptive scaling."""
    
    _health_factor = 1.0
    
    @classmethod
    def update_system_health(cls, factor: float) -> None:
        cls._health_factor = max(0.1, min(1.0, factor))
    
    def __init__(self, budget: str):
        self.budget = budget
        self.db_calls = 0
        self.estimated_tokens = 0
        self.start_time = datetime.now(timezone.utc)
        self.end_time: Optional[datetime] = None
    
    def record_db_call(self, count: int = 1) -> None:
        self.db_calls += count
    
    def record_tokens(self, count: int) -> None:
        self.estimated_tokens += count
    
    def finish(self) -> None:
        self.end_time = datetime.now(timezone.utc)
    
    def is_over_budget(self) -> bool:
        limits = {
            "low": {"db_calls": 10, "tokens": 1000},
            "medium": {"db_calls": 25, "tokens": 3000},
            "high": {"db_calls": 50, "tokens": 8000},
        }
        limit_config = limits.get(self.budget, limits["medium"])
        max_db = int(limit_config["db_calls"] * self._health_factor)
        max_tokens = int(limit_config["tokens"] * self._health_factor)
        return self.db_calls > max_db or self.estimated_tokens > max_tokens
    
    def to_dict(self) -> Dict[str, Any]:
        duration = 0.0
        if self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
        return {
            "budget": self.budget,
            "db_calls": self.db_calls,
            "estimated_tokens": self.estimated_tokens,
            "duration_seconds": round(duration, 3),
            "over_budget": self.is_over_budget(),
        }


_DEFAULT_THRESHOLDS = {
    "temporal": 0.50,
    "factual": 0.60,
    "multi-hop": 0.70,
    "conversational": 0.55,
    "update": 0.75,
}


class RoutingPolicy:
    def __init__(self, config: Dict[str, Any] = None, thresholds: Optional[Dict[str, float]] = None,
                 cost_tracker: Optional[CostTracker] = None):
        self.config = config or {
            "temporal": {"strategy": "hybrid_bm25_vector_temporal", "cost_budget": "medium"},
            "factual": {"strategy": "hybrid_bm25_vector_temporal", "cost_budget": "medium"},
            "multi-hop": {"strategy": "hybrid_with_graph_expansion", "cost_budget": "high"},
            "conversational": {"strategy": "composite_kg_vector", "cost_budget": "medium"},
            "update": {"strategy": "knowledge_graph_with_invalidation", "cost_budget": "high"},
        }
        self._thresholds = dict(_DEFAULT_THRESHOLDS)
        for qt, cfg in self.config.items():
            legacy_conf = cfg.get("min_confidence")
            if legacy_conf is not None:
                self._thresholds[qt] = legacy_conf
        if thresholds:
            self._thresholds.update(thresholds)
        self._usage: Dict[str, BudgetTracker] = {}
        self._usage_strategies: Dict[str, str] = {}

        self._history: Dict[str, list[bool]] = defaultdict(list)
        self._history_max = 100

        self.cost_tracker = cost_tracker

    def get_strategy(self, query_type: str, confidence: float, query_hash: Optional[str] = None) -> Dict[str, Any]:
        base_config = self.config.get(query_type) or self.config.get("factual")
        min_confidence = self._get_dynamic_threshold(query_type)

        strategy: Dict[str, Any] = {
            "strategy": "hybrid_fallback",
            "cost_budget": "medium",
            "query_type": query_type,
            "confidence": confidence,
            "policy_applied": "fallback",
            "min_confidence": min_confidence,
        }
        if base_config and confidence >= min_confidence:
            strategy = {
                "strategy": base_config.get("strategy", strategy["strategy"]),
                "cost_budget": base_config.get("cost_budget", strategy["cost_budget"]),
                "query_type": query_type,
                "confidence": confidence,
                "policy_applied": "strict",
                "min_confidence": min_confidence,
            }

        budget = strategy.get("cost_budget", "medium")
        tracker = BudgetTracker(budget=budget)
        strategy_name = strategy.get("strategy", "hybrid_fallback")
        key = query_hash or f"{query_type}:{confidence}:{datetime.now(timezone.utc).timestamp()}"
        self._usage[key] = tracker
        self._usage_strategies[key] = strategy_name
        strategy["budget_tracker_key"] = key
        strategy["budget"] = budget

        return strategy

    def _get_dynamic_threshold(self, query_type: str) -> float:
        """Gibt den dynamischen Threshold zurück, basierend auf Baseline und historischer Performance."""
        baseline = self._thresholds.get(query_type, 0.6)
        outcomes = self._history.get(query_type, [])
        if len(outcomes) < 10:
            return baseline
        success_rate = sum(outcomes) / len(outcomes)
        if success_rate < 0.5:
            return min(baseline + 0.15, 0.9)
        elif success_rate > 0.85:
            return max(baseline - 0.1, 0.3)
        return baseline

    def record_outcome(self, query_type: str, success: bool) -> None:
        """Zeichnet Erfolg/Misserfolg für einen Query-Typ auf (für dynamische Thresholds)."""
        self._history[query_type].append(success)
        if len(self._history[query_type]) > self._history_max:
            self._history[query_type].pop(0)

    def get_thresholds(self) -> Dict[str, float]:
        """Gibt die aktuellen dynamischen Thresholds zurück."""
        return {qt: self._get_dynamic_threshold(qt) for qt in self._thresholds}

    def get_history(self) -> Dict[str, Dict[str, Any]]:
        """Gibt die historischen Statistiken pro Query-Typ zurück."""
        stats = {}
        for qt, outcomes in self._history.items():
            stats[qt] = {
                "total": len(outcomes),
                "successes": sum(outcomes),
                "success_rate": sum(outcomes) / len(outcomes) if outcomes else 0.0,
            }
        return stats

    def get_tracker(self, key: str) -> Optional[BudgetTracker]:
        return self._usage.get(key)
    
    def record_db_call(self, key: str, count: int = 1) -> None:
        tracker = self._usage.get(key)
        if tracker:
            tracker.record_db_call(count)
    
    def record_tokens(self, key: str, count: int) -> None:
        tracker = self._usage.get(key)
        if tracker:
            tracker.record_tokens(count)
    
    def finish_execution(self, key: str, success: bool = True) -> Optional[Dict[str, Any]]:
        tracker = self._usage.get(key)
        if tracker:
            tracker.finish()
            budget_data = tracker.to_dict()
            strategy_name = self._usage_strategies.get(key, "unknown")
            if self.cost_tracker is not None:
                self.cost_tracker.feed_budget_tracker(strategy_name, budget_data, success)
            return budget_data
        return None
    
    def is_over_budget(self, key: str) -> bool:
        tracker = self._usage.get(key)
        return bool(tracker and tracker.is_over_budget())


if __name__ == "__main__":
    # Test the routing policy
    policy = RoutingPolicy()
    
    test_cases = [
        ("temporal", 0.9),
        ("factual", 0.8),
        ("multi-hop", 0.7),
        ("conversational", 0.9),
        ("update", 0.8),
        ("temporal", 0.4),  # Low confidence should trigger fallback
    ]
    
    print("Strata Routing Policy Test:")
    for q_type, conf in test_cases:
        strategy = policy.get_strategy(q_type, conf)
        print(f"  {q_type} (conf={conf:.1f}): {strategy['strategy']} [{strategy['cost_budget']}]")