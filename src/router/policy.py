"""
Adaptive Routing Policy for Strata
Based on query type and confidence, decides which strategy to use
"""
from typing import Dict, Any, Optional
from datetime import datetime, timezone

try:
    import tiktoken
except ImportError:  # pragma: no cover
    tiktoken = None  # type: ignore


class OverBudget(Exception):
    """Raised when a query exceeds its configured cost budget."""
    pass


class BudgetTracker:
    """Tracks resource consumption against a cost budget."""
    
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
        # Simple budget enforcement: high budget gets more resources
        limits = {
            "low": {"db_calls": 10, "tokens": 1000},
            "medium": {"db_calls": 25, "tokens": 3000},
            "high": {"db_calls": 50, "tokens": 8000},
        }
        limit = limits.get(self.budget, limits["medium"])
        return self.db_calls > limit["db_calls"] or self.estimated_tokens > limit["tokens"]
    
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


class RoutingPolicy:
    def __init__(self, config: Dict[str, Any] = None):
        # Default configuration
        self.config = config or {
            "temporal": {
                "strategy": "hybrid_bm25_vector_temporal",  # Updated to use full hybrid
                "cost_budget": "medium",
                "min_confidence": 0.6
            },
            "factual": {
                "strategy": "hybrid_bm25_vector_temporal",
                "cost_budget": "medium",
                "min_confidence": 0.6
            },
            "multi-hop": {
                "strategy": "hybrid_with_graph_expansion",
                "cost_budget": "high",
                "min_confidence": 0.6
            },
            "conversational": {
                "strategy": "composite_kg_vector",
                "cost_budget": "medium",
                "min_confidence": 0.6
            },
            "update": {
                "strategy": "knowledge_graph_with_invalidation",
                "cost_budget": "high",
                "min_confidence": 0.6
            }
        }
        self._usage: Dict[str, BudgetTracker] = {}

    def get_strategy(self, query_type: str, confidence: float, query_hash: Optional[str] = None) -> Dict[str, Any]:
        """Get the routing strategy based on query type and confidence"""
        # Get base configuration for this query type
        base_config = self.config.get(query_type) or self.config.get("factual")
        strategy: Dict[str, Any] = {
            "strategy": "hybrid_fallback",
            "cost_budget": "medium",
            "query_type": query_type,
            "confidence": confidence,
            "policy_applied": "fallback",
        }
        if base_config:
            min_confidence = base_config.get("min_confidence", 0.6)
            if confidence >= min_confidence:
                strategy = {
                    "strategy": base_config.get("strategy", strategy["strategy"]),
                    "cost_budget": base_config.get("cost_budget", strategy["cost_budget"]),
                    "query_type": query_type,
                    "confidence": confidence,
                    "policy_applied": "strict",
                }
        # Ensure base_config is never None downstream if needed
        if base_config is None:
            base_config = {}
        
        # Attach a fresh budget tracker for this execution
        budget = strategy.get("cost_budget", "medium")
        tracker = BudgetTracker(budget=budget)
        key = query_hash or f"{query_type}:{confidence}:{datetime.now(timezone.utc).timestamp()}"
        self._usage[key] = tracker
        strategy["budget_tracker_key"] = key
        strategy["budget"] = budget
        
        return strategy
    
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
    
    def finish_execution(self, key: str) -> Optional[Dict[str, Any]]:
        tracker = self._usage.get(key)
        if tracker:
            tracker.finish()
            return tracker.to_dict()
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