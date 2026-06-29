"""
Cost Awareness Module for Router
Tracks and manages resource consumption for different strategies
"""
import time
from collections import defaultdict
from typing import Dict, List, Tuple


class CostTracker:
    def __init__(self):
        # Strategy -> metrics mapping
        self.metrics = defaultdict(lambda: {
            'total_queries': 0,
            'total_latency': 0.0,
            'successful_queries': 0,
            'total_cost': 0.0,
            'latencies': [],
            'costs': []
        })

    def track_query(self, strategy: str, latency: float = 0.0, 
                   num_queries: int = 1, success: bool = False, 
                   relevance: float = 0.5) -> None:
        """
        Track metrics for a single query execution
        """
        self.metrics[strategy]['total_queries'] += 1
        self.metrics[strategy]['total_latency'] += latency
        self.metrics[strategy]['latencies'].append(latency)
        
        # Calculate cost based on strategy type and resource usage
        base_cost = self._calculate_base_cost(strategy)
        query_cost = base_cost * num_queries * (1.0 + (1.0 - relevance))  # Higher cost for low relevance
        self.metrics[strategy]['total_cost'] += query_cost
        self.metrics[strategy]['costs'].append(query_cost)
        
        if success:
            self.metrics[strategy]['successful_queries'] += 1

    def _calculate_base_cost(self, strategy: str) -> float:
        """
        Return base cost multiplier for different strategies
        """
        cost_map = {
            'event_log_first': 0.5,           # Low cost
            'knowledge_graph_first': 0.5,     # Low cost
            'hybrid_fallback': 1.0,           # Medium cost
            'composite_kg_vector': 1.0,       # Medium cost
            'hybrid_with_graph_expansion': 1.5, # Higher cost
            'knowledge_graph_with_invalidation': 2.0  # Highest cost
        }
        return cost_map.get(strategy, 1.0)

    def get_average_cost(self, strategy: str) -> Dict[str, float]:
        """
        Calculate average metrics for a strategy
        """
        if self.metrics[strategy]['total_queries'] == 0:
            return {'latency': 0.0, 'success_rate': 0.0, 'cost': 0.0}
            
        total_q = self.metrics[strategy]['total_queries']
        avg_latency = self.metrics[strategy]['total_latency'] / total_q
        success_rate = self.metrics[strategy]['successful_queries'] / total_q
        avg_cost = self.metrics[strategy]['total_cost'] / total_q
        
        return {
            'latency': avg_latency,
            'success_rate': success_rate,
            'cost': avg_cost
        }

    def get_all_costs(self) -> Dict[str, Dict[str, float]]:
        """
        Get cost metrics for all strategies
        """
        return {strategy: self.get_average_cost(strategy) 
                for strategy in self.metrics.keys()}


if __name__ == "__main__":
    tracker = CostTracker()
    
    # Simulate some queries
    strategies = ['event_log_first', 'knowledge_graph_first', 'hybrid_with_graph_expansion']
    
    for i in range(10):
        for strategy in strategies:
            success = i % 3 != 0  # ~66% success rate
            relevance = 0.5 + (i % 5) * 0.1  # Varying relevance
            latency = 0.05 + (i % 10) * 0.01  # Varying latency
            tracker.track_query(strategy, latency=latency, success=success, 
                              relevance=relevance)
    
    print("Cost Analysis:")
    for strategy, metrics in tracker.get_all_costs().items():
        print(f"  {strategy}:")
        print(f"    Avg Latency: {metrics['latency']:.3f}s")
        print(f"    Success Rate: {metrics['success_rate']:.1%}")
        print(f"    Avg Cost: {metrics['cost']:.3f}")
