"""
Adaptive Routing Policy for Strata
Based on query type and confidence, decides which strategy to use
"""
from typing import Dict, Any


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
                "strategy": "knowledge_graph_first",
                "cost_budget": "low",
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

    def get_strategy(self, query_type: str, confidence: float) -> Dict[str, Any]:
        """Get the routing strategy based on query type and confidence"""
        # Get base configuration for this query type
        base_config = self.config.get(query_type, self.config.get("factual"))  # Default to factual
        
        # Check if confidence is above minimum threshold
        min_confidence = base_config.get("min_confidence", 0.6)
        
        if confidence < min_confidence:
            # Fall back to hybrid strategy if confidence is too low
            return {
                "strategy": "hybrid_fallback",
                "cost_budget": "medium",
                "query_type": query_type,
                "confidence": confidence,
                "policy_applied": "fallback"
            }
        else:
            return {
                "strategy": base_config["strategy"],
                "cost_budget": base_config["cost_budget"],
                "query_type": query_type,
                "confidence": confidence,
                "policy_applied": "strict"
            }


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