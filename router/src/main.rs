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

#[tokio::main]
async fn main() {
    let app = Router::new()
        .route("/classify", get(classify))
        .route("/route", get(route_query));

    let listener = tokio::net::TcpListener::bind("127.0.0.1:8080")
        .await
        .expect("Failed to bind Router to 127.0.0.1:8080");

    println!("Strata Router Service listening on http://127.0.0.1:8080");
    let _ = axum::serve(listener, app.into_make_service())
        .await
        .expect("Router server failed");
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
mod router_stability_tests {
    use super::*;
    use tokio_test;
    use strata_common::QueryType;

    #[test]
    fn test_classifier_logic_directly() {
        let classifier = classifier::Classifier::new();
        
        // Test temporal queries (based on actual implementation)
        let result = tokio_test::block_on(classifier.classify("Wann habe ich Alice getroffen?"));
        assert!(matches!(result.query_type, QueryType::Temporal));
        assert!(result.confidence >= 0.5);
        
        // Test factual queries
        let result = tokio_test::block_on(classifier.classify("Wer ist mein Kunde?"));
        assert!(matches!(result.query_type, QueryType::Factual));
        assert!(result.confidence >= 0.5);
        
        // Test multi-hop queries
        let result = tokio_test::block_on(classifier.classify("Warum haben wir das Projekt gestoppt?"));
        assert!(matches!(result.query_type, QueryType::MultiHop));
        assert!(result.confidence >= 0.5);
        
        // Test mixed temporal+conversational query
        let result = tokio_test::block_on(classifier.classify("Worüber haben wir gestern gesprochen?"));
        // "gestern" (temporal) and "gesprochen" + "worüber" (conversational) both match
        // Conversational patterns are weighted higher, so it is classified as Conversational
        assert!(matches!(result.query_type, QueryType::Conversational));
        assert!(result.confidence >= 0.5);
        
        // Test update queries
        let result = tokio_test::block_on(classifier.classify("Aktualisiere meinen Namen"));
        assert!(matches!(result.query_type, QueryType::Update));
        assert!(result.confidence >= 0.5);
        
        // Test default case
        let result = tokio_test::block_on(classifier.classify("blablabla"));
        assert!(matches!(result.query_type, QueryType::Factual));
        assert!((0.4..=0.6).contains(&result.confidence));
    }

    #[test]
    fn test_classifier_english_queries() {
        let classifier = classifier::Classifier::new();
        
        // Test English temporal queries
        let result = tokio_test::block_on(classifier.classify("When did I meet Alice?"));
        assert!(matches!(result.query_type, QueryType::Temporal));
        assert!(result.confidence >= 0.5);
        
        // Test English factual queries
        let result = tokio_test::block_on(classifier.classify("Who is my customer?"));
        assert!(matches!(result.query_type, QueryType::Factual));
        assert!(result.confidence >= 0.5);
        
        // Test English multi-hop queries
        let result = tokio_test::block_on(classifier.classify("Why did sales decrease?"));
        assert!(matches!(result.query_type, QueryType::MultiHop));
        assert!(result.confidence >= 0.5);
        
        // Test English conversational queries
        let result = tokio_test::block_on(classifier.classify("Do you remember our last meeting?"));
        assert!(matches!(result.query_type, QueryType::Conversational));
        assert!(result.confidence >= 0.5);
        
        // Test English update queries
        let result = tokio_test::block_on(classifier.classify("Update my contact info"));
        assert!(matches!(result.query_type, QueryType::Update));
        assert!(result.confidence >= 0.5);
    }

    #[test]
    fn test_classifier_edge_cases() {
        let classifier = classifier::Classifier::new();
        
        // Test empty query
        let result = tokio_test::block_on(classifier.classify(""));
        assert!(matches!(result.query_type, QueryType::Factual));
        assert!((0.4..=0.6).contains(&result.confidence));
        
        // Test whitespace-only query
        let result = tokio_test::block_on(classifier.classify("   \t\n  "));
        assert!(matches!(result.query_type, QueryType::Factual));
        assert!((0.4..=0.6).contains(&result.confidence));
        
        // Test query with special characters
        let result = tokio_test::block_on(classifier.classify("??? When did this happen ???"));
        assert!(matches!(result.query_type, QueryType::Temporal));
        assert!(result.confidence >= 0.5);
        
        // Test very long query
        let long_query = "When ".repeat(1000) + "did this happen?";
        let result = tokio_test::block_on(classifier.classify(&long_query));
        assert!(matches!(result.query_type, QueryType::Temporal));
        assert!(result.confidence >= 0.8);
    }

    #[test]
    fn test_policy_logic_directly() {
        use strata_common::{QueryClassification, CostBudget};

        let policy = policy::Policy::default();
        
        // Test high confidence temporal query
        let classification = QueryClassification {
            query_type: QueryType::Temporal,
            confidence: 0.9,
        };
        let strategy = policy.decide(&classification);
        assert_eq!(strategy.name, "hybrid_bm25_vector_temporal");
        assert_eq!(strategy.cost_budget, CostBudget::Medium);
        
        // Test high confidence factual query
        let classification = QueryClassification {
            query_type: QueryType::Factual,
            confidence: 0.9,
        };
        let strategy = policy.decide(&classification);
        assert_eq!(strategy.name, "hybrid_bm25_vector_temporal");
        assert_eq!(strategy.cost_budget, CostBudget::Medium);
        
        // Test high confidence multi-hop query
        let classification = QueryClassification {
            query_type: QueryType::MultiHop,
            confidence: 0.9,
        };
        let strategy = policy.decide(&classification);
        assert_eq!(strategy.name, "hybrid_with_graph_expansion");
        assert_eq!(strategy.cost_budget, CostBudget::High);
        
        // Test high confidence conversational query
        let classification = QueryClassification {
            query_type: QueryType::Conversational,
            confidence: 0.9,
        };
        let strategy = policy.decide(&classification);
        assert_eq!(strategy.name, "composite_kg_vector");
        assert_eq!(strategy.cost_budget, CostBudget::Medium);
        
        // Test high confidence update query
        let classification = QueryClassification {
            query_type: QueryType::Update,
            confidence: 0.9,
        };
        let strategy = policy.decide(&classification);
        assert_eq!(strategy.name, "knowledge_graph_with_invalidation");
        assert_eq!(strategy.cost_budget, CostBudget::High);
        
        // Test low confidence query (should fall back to hybrid)
        let classification = QueryClassification {
            query_type: QueryType::Temporal,
            confidence: 0.3,
        };
        let strategy = policy.decide(&classification);
        assert_eq!(strategy.name, "hybrid_fallback");
        assert_eq!(strategy.cost_budget, CostBudget::Medium);
    }

    #[test]
    fn test_combined_classification_and_policy() {
        let classifier = classifier::Classifier::new();
        let policy = policy::Policy::default();
        
        // Test a full flow for each query type with corrected expectations
        let test_cases = vec![
            ("Wann habe ich Alice getroffen?", "hybrid_bm25_vector_temporal"),
            ("Wer ist mein Kunde?", "hybrid_bm25_vector_temporal"),
            ("Warum haben wir das Projekt gestoppt?", "hybrid_fallback"), // Low confidence (0.5) triggers fallback
            ("Do you remember our last meeting?", "composite_kg_vector"),
            ("Update my contact info", "knowledge_graph_with_invalidation"),
            ("Worüber haben wir gestern gesprochen?", "composite_kg_vector"), // Conversational wins due to weighting
        ];
        
        for (query, expected_strategy) in test_cases {
            let classification = tokio_test::block_on(classifier.classify(query));
            let strategy = policy.decide(&classification);
            assert_eq!(strategy.name, expected_strategy, "Failed for query: {}", query);
        }
    }

    #[test]
    fn test_classifier_performance_under_load_simulation() {
        let classifier = classifier::Classifier::new();
        
        // Simulate many consecutive classifications to test stability
        for i in 0..100 {
            let query = format!("Test query number {}", i);
            let result = tokio_test::block_on(classifier.classify(&query));
            
            // Basic sanity checks
            assert!(result.confidence >= 0.0 && result.confidence <= 1.0);
            assert!(matches!(result.query_type, QueryType::Factual)); // Should default to factual
        }
    }

    #[test]
    fn test_cross_language_consistency() {
        use std::process::Command;

        let classifier = classifier::Classifier::new();
        let test_cases = vec![
            "Wann habe ich Alice getroffen?",
            "Wer ist mein Kunde?",
            "Warum haben wir das Projekt gestoppt?",
            "Worüber haben wir gestern gesprochen?",
            "Aktualisiere meinen Namen",
            "When did I meet Alice?",
            "Who is my customer?",
            "Why did sales decrease?",
            "Do you remember our last meeting?",
            "Update my contact info",
            "",
            "   ",
        ];

        for query in test_cases {
            let rust_result = tokio_test::block_on(classifier.classify(query));

            let script_path = std::env::var("CARGO_MANIFEST_DIR")
                .map(|d| format!("{}/../tests/classify_cli.py", d))
                .unwrap_or_else(|_| "tests/classify_cli.py".to_string());
            let output = Command::new("python")
                .arg(&script_path)
                .arg(query)
                .output()
                .unwrap_or_else(|_| panic!("Failed to run Python classifier CLI: {}", script_path));

            assert!(output.status.success(), "Python CLI failed for query: {}", query);

            let stdout = String::from_utf8(output.stdout).expect("Invalid UTF-8 from Python CLI");
            let py_parts: Vec<&str> = stdout.trim().split('|').collect();
            assert_eq!(py_parts.len(), 2, "Invalid Python output for query: {}: {}", query, stdout);

            let py_type = py_parts[0];
            let py_confidence: f64 = py_parts[1].parse().expect("Invalid Python confidence");

            assert_eq!(rust_result.query_type.to_string(), py_type,
                "Type mismatch for query '{}': Rust='{}', Python='{}'",
                query, rust_result.query_type, py_type);

            assert!((rust_result.confidence - py_confidence).abs() < 0.01,
                "Confidence mismatch for query '{}': Rust={}, Python={}",
                query, rust_result.confidence, py_confidence);
        }
    }

    #[tokio::test]
    async fn test_async_classification_stability() {
        // Test multiple async classifications to check for race conditions
        let mut handles = vec![];
        
        for i in 0..50 {
            let classifier_clone = classifier::Classifier::new();
            let query = format!("Async test query {}", i);
            
            let handle = tokio::spawn(async move {
                classifier_clone.classify(&query).await
            });
            handles.push(handle);
        }
        
        // Wait for all classifications to complete
        let results = futures::future::join_all(handles).await;
        
        for result in results {
            let classification = result.unwrap();
            assert!(classification.confidence >= 0.0 && classification.confidence <= 1.0);
        }
    }
}