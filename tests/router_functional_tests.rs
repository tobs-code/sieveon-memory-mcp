mod classifier;
mod policy;

use axum::{
    extract::Query,
    routing::get,
    Json, Router,
};
use strata_common::{QueryClassification, Strategy};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct ClassifyRequest {
    query: String,
}

#[derive(Debug, Deserialize)]
pub struct RouteRequest {
    query: String,
}

async fn classify(
    Query(params): Query<ClassifyRequest>,
) -> Json<QueryClassification> {
    let classifier = classifier::Classifier::new();
    let result = classifier.classify(&params.query).await;
    Json(result)
}

async fn route_query(
    Query(params): Query<RouteRequest>,
) -> Json<Strategy> {
    let classifier = classifier::Classifier::new();
    let classification = classifier.classify(&params.query).await;
    let policy = policy::Policy::default();
    let strategy = policy.decide(&classification);
    Json(strategy)
}

#[cfg(test)]
mod router_functional_tests {
    use super::*;
    use tokio_test;

    #[test]
    fn test_classification_accuracy() {
        let classifier = classifier::Classifier::new();
        
        // Test that temporal keywords trigger temporal classification
        let temporal_keywords = ["when", "yesterday", "today", "wann", "gestern", "heute"];
        for keyword in temporal_keywords {
            let query = format!("{} did this happen?", keyword);
            let result = tokio_test::block_on(classifier.classify(&query));
            assert!(matches!(result.query_type, common::QueryType::Temporal));
            assert!(result.confidence >= 0.8);
        }
        
        // Test that factual keywords trigger factual classification
        let factual_keywords = ["who", "what", "where", "wer", "was", "wo"];
        for keyword in factual_keywords {
            let query = format!("{} is this?", keyword);
            let result = tokio_test::block_on(classifier.classify(&query));
            assert!(matches!(result.query_type, common::QueryType::Factual));
            assert!(result.confidence >= 0.8);
        }
        
        // Test that multi-hop keywords trigger multi-hop classification
        let multihop_keywords = ["why", "because", "warum", "wegen"];
        for keyword in multihop_keywords {
            let query = format!("{} did this happen?", keyword);
            let result = tokio_test::block_on(classifier.classify(&query));
            assert!(matches!(result.query_type, common::QueryType::MultiHop));
            assert!(result.confidence >= 0.8);
        }
    }

    #[test]
    fn test_routing_decision_consistency() {
        let classifier = classifier::Classifier::new();
        let policy = policy::Policy::default();
        
        // Test that temporal queries get routed to temporal strategy
        let temporal_query = "When did I meet Alice?";
        let classification = tokio_test::block_on(classifier.classify(temporal_query));
        let strategy = policy.decide(&classification);
        assert_eq!(strategy.name, "hybrid_bm25_vector_temporal");
        assert!(matches!(strategy.cost_budget, common::CostBudget::Medium));
        
        // Test that factual queries get routed to factual strategy
        let factual_query = "Who is my contact?";
        let classification = tokio_test::block_on(classifier.classify(factual_query));
        let strategy = policy.decide(&classification);
        assert_eq!(strategy.name, "knowledge_graph_first");
        assert!(matches!(strategy.cost_budget, common::CostBudget::Low));
        
        // Test that multi-hop queries get routed to expansion strategy
        let multihop_query = "Why did the project fail?";
        let classification = tokio_test::block_on(classifier.classify(multihop_query));
        let strategy = policy.decide(&classification);
        assert_eq!(strategy.name, "hybrid_with_graph_expansion");
        assert!(matches!(strategy.cost_budget, common::CostBudget::High));
    }

    #[test]
    fn test_confidence_based_routing() {
        let classifier = classifier::Classifier::new();
        let policy = policy::Policy::default();
        
        // Test high confidence temporal query
        let classification = common::QueryClassification {
            query_type: common::QueryType::Temporal,
            confidence: 0.9,
        };
        let strategy = policy.decide(&classification);
        assert_eq!(strategy.name, "hybrid_bm25_vector_temporal");
        
        // Test medium confidence temporal query (should still get temporal strategy)
        let classification = common::QueryClassification {
            query_type: common::QueryType::Temporal,
            confidence: 0.6,
        };
        let strategy = policy.decide(&classification);
        assert_eq!(strategy.name, "hybrid_bm25_vector_temporal");
        
        // Test low confidence query (should go to fallback)
        let classification = common::QueryClassification {
            query_type: common::QueryType::Temporal,
            confidence: 0.3,
        };
        let strategy = policy.decide(&classification);
        assert_eq!(strategy.name, "hybrid_fallback");
    }

    #[test]
    fn test_pattern_matching_priority() {
        let classifier = classifier::Classifier::new();
        
        // Test that earlier patterns in the chain take priority
        // "when" appears before "what" in the temporal check, so "when" should win
        let query = "When what is the answer?";
        let result = tokio_test::block_on(classifier.classify(query));
        assert!(matches!(result.query_type, common::QueryType::Temporal));
        assert!(result.confidence >= 0.8);
        
        // Test a query with both temporal and factual patterns
        // The first matching pattern should win
        let query = "Yesterday who attended the meeting?";
        let result = tokio_test::block_on(classifier.classify(query));
        assert!(matches!(result.query_type, common::QueryType::Temporal));
    }

    #[test]
    fn test_cross_language_consistency_scenarios() {
        let classifier = classifier::Classifier::new();
        let policy = policy::Policy::default();
        
        // Test scenarios that should match Python implementation
        let test_cases = vec![
            ("When did I receive the email?", "hybrid_bm25_vector_temporal"),
            ("Who sent me the message?", "knowledge_graph_first"),
            ("Why was the meeting cancelled?", "hybrid_with_graph_expansion"),
            ("Do you remember our conversation?", "composite_kg_vector"),
            ("Update my preferences", "knowledge_graph_with_invalidation"),
        ];
        
        for (query, expected_strategy) in test_cases {
            let classification = tokio_test::block_on(classifier.classify(query));
            let strategy = policy.decide(&classification);
            assert_eq!(strategy.name, expected_strategy, "Failed for query: {}", query);
        }
    }

    #[test]
    fn test_edge_case_handling() {
        let classifier = classifier::Classifier::new();
        
        // Test empty string
        let result = tokio_test::block_on(classifier.classify(""));
        assert!(matches!(result.query_type, common::QueryType::Factual));
        assert!((0.4..=0.6).contains(&result.confidence));
        
        // Test very short string
        let result = tokio_test::block_on(classifier.classify("Hi"));
        assert!(matches!(result.query_type, common::QueryType::Factual));
        assert!((0.4..=0.6).contains(&result.confidence));
        
        // Test string with only punctuation
        let result = tokio_test::block_on(classifier.classify("?!@#$"));
        assert!(matches!(result.query_type, common::QueryType::Factual));
        assert!((0.4..=0.6).contains(&result.confidence));
    }

    #[tokio::test]
    async fn test_async_functional_flow() {
        let classifier = classifier::Classifier::new();
        let policy = policy::Policy::default();
        
        // Test the full async flow
        let query = "When is the next appointment?";
        let classification = classifier.classify(query).await;
        let strategy = policy.decide(&classification);
        
        assert!(matches!(classification.query_type, common::QueryType::Temporal));
        assert!(classification.confidence >= 0.8);
        assert_eq!(strategy.name, "hybrid_bm25_vector_temporal");
        assert!(matches!(strategy.cost_budget, common::CostBudget::Medium));
    }

    #[test]
    fn test_classification_boundary_conditions() {
        let classifier = classifier::Classifier::new();
        
        // Test queries that barely match patterns
        let weak_temporal = "sometime in the past";
        let result = tokio_test::block_on(classifier.classify(weak_temporal));
        // This might not match temporal patterns if they're not strong enough
        // It should default to factual if no strong pattern matches
        
        let weak_factual = "something about things";
        let result = tokio_test::block_on(classifier.classify(weak_factual));
        // Should default to factual if no strong pattern matches
        assert!(matches!(result.query_type, common::QueryType::Factual));
    }
}