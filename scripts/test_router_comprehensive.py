# -*- coding: utf-8 -*-
"""
Comprehensive Router Test Script for STRATA
Tests routing logic, fallback mechanisms, and budget tracking including edge cases.
"""
import sys
import os
import unittest
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.router.policy import RoutingPolicy, BudgetTracker, OverBudget

class TestRouterComprehensive(unittest.TestCase):
    def setUp(self):
        self.policy = RoutingPolicy()

    def test_standard_routing(self):
        """Test if standard query types route to expected strategies."""
        scenarios = [
            ("temporal", 0.9, "hybrid_bm25_vector_temporal", "medium"),
            ("factual", 0.8, "hybrid_bm25_vector_temporal", "medium"),
            ("multi-hop", 0.7, "hybrid_with_graph_expansion", "high"),
            ("conversational", 0.95, "composite_kg_vector", "medium"),
            ("update", 0.85, "knowledge_graph_with_invalidation", "high"),
        ]
        
        print("\n[INFO] Testing Standard Routing Scenarios:")
        for q_type, conf, expected_strat, expected_budget in scenarios:
            strategy = self.policy.get_strategy(q_type, conf)
            print(f"  Input: {q_type} (conf={conf}) -> Result: {strategy['strategy']} ({strategy['cost_budget']})")
            self.assertEqual(strategy["strategy"], expected_strat)
            self.assertEqual(strategy["cost_budget"], expected_budget)
            self.assertEqual(strategy["policy_applied"], "strict")

    def test_fallback_mechanisms(self):
        """Test if low confidence triggers fallback strategy."""
        print("\n[INFO] Testing Fallback Mechanisms (Low Confidence):")
        # Confidence 0.4 is below default threshold 0.6
        strategy = self.policy.get_strategy("factual", 0.4)
        print(f"  Input: factual (conf=0.4) -> Result: {strategy['strategy']} ({strategy['policy_applied']})")
        self.assertEqual(strategy["strategy"], "hybrid_fallback")
        self.assertEqual(strategy["policy_applied"], "fallback")

    def test_unknown_query_type_edge_case(self):
        """Test how the router handles unknown query types."""
        print("\n[INFO] Testing Edge Case: Unknown Query Type:")
        # Should fallback to 'factual' or a general default
        strategy = self.policy.get_strategy("completely_unknown_type", 0.9)
        print(f"  Input: unknown_type -> Result: {strategy['strategy']} ({strategy['cost_budget']})")
        # According to code, it defaults to factual config if not found
        self.assertEqual(strategy["strategy"], "hybrid_bm25_vector_temporal")

    def test_budget_tracking_logic(self):
        """Test if the budget tracker correctly identifies over-budget situations."""
        print("\n[INFO] Testing Budget Tracking Logic:")
        
        # Test Low Budget
        tracker_low = BudgetTracker("low")
        tracker_low.record_db_call(5)
        tracker_low.record_tokens(500)
        self.assertFalse(tracker_low.is_over_budget(), "Should be under budget (low)")
        
        tracker_low.record_db_call(6) # Total 11, limit is 10
        self.assertTrue(tracker_low.is_over_budget(), "Should be over budget (low - db_calls)")
        
        # Test High Budget
        tracker_high = BudgetTracker("high")
        tracker_high.record_tokens(7000)
        self.assertFalse(tracker_high.is_over_budget(), "Should be under budget (high)")
        
        tracker_high.record_tokens(1001) # Total 8001, limit is 8000
        self.assertTrue(tracker_high.is_over_budget(), "Should be over budget (high - tokens)")

    def test_concurrent_trackers(self):
        """Test if multiple trackers can exist independently."""
        print("\n[INFO] Testing Concurrent Trackers:")
        s1 = self.policy.get_strategy("factual", 0.9)
        s2 = self.policy.get_strategy("multi-hop", 0.9)
        
        k1 = s1["budget_tracker_key"]
        k2 = s2["budget_tracker_key"]
        
        self.policy.record_db_call(k1, 5)
        self.policy.record_db_call(k2, 40)
        
        self.assertFalse(self.policy.is_over_budget(k1), "Tracker 1 should be under budget")
        self.assertFalse(self.policy.is_over_budget(k2), "Tracker 2 should be under budget (high budget)")
        
        self.policy.record_db_call(k2, 11) # 51 calls total
        self.assertTrue(self.policy.is_over_budget(k2), "Tracker 2 should be over budget now")
        self.assertFalse(self.policy.is_over_budget(k1), "Tracker 1 should still be under budget")

    def test_extreme_confidence_values(self):
        """Test edge cases for confidence (0.0 and 1.0)."""
        print("\n[INFO] Testing Edge Case: Extreme Confidence Values:")
        
        s_zero = self.policy.get_strategy("factual", 0.0)
        self.assertEqual(s_zero["policy_applied"], "fallback")
        
        s_one = self.policy.get_strategy("factual", 1.0)
        self.assertEqual(s_one["policy_applied"], "strict")

def run_tests():
    print("=" * 60)
    print("STRATA COMPREHENSIVE ROUTER TEST SUITE")
    print("=" * 60)
    
    suite = unittest.TestLoader().loadTestsFromTestCase(TestRouterComprehensive)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        print("\n[SUCCESS] All router logic tests passed!")
    else:
        print("\n[FAILURE] Some router tests failed. Check logs.")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
