// Unit tests for STRATA - the Scalable Temporal Relational Analysis and Tracking Architecture

#[cfg(test)]
mod common_tests {
    use strata_common::{QueryClassification, QueryType, Strategy, CostBudget};

    #[test]
    fn test_query_classification_serialization() {
        let classification = QueryClassification {
            query_type: QueryType::Temporal,
            confidence: 0.85,
        };

        let serialized = serde_json::to_string(&classification).unwrap();
        let deserialized: QueryClassification = serde_json::from_str(&serialized).unwrap();

        assert_eq!(classification.query_type, deserialized.query_type);
        assert_eq!(classification.confidence, deserialized.confidence);
    }

    #[test]
    fn test_strategy_serialization() {
        let strategy = Strategy {
            name: "test_strategy".to_string(),
            cost_budget: CostBudget::High,
        };

        let serialized = serde_json::to_string(&strategy).unwrap();
        let deserialized: Strategy = serde_json::from_str(&serialized).unwrap();

        assert_eq!(strategy.name, deserialized.name);
        assert_eq!(strategy.cost_budget, deserialized.cost_budget);
    }

    #[test]
    fn test_query_type_display() {
        assert_eq!(format!("{}", QueryType::Temporal), "temporal");
        assert_eq!(format!("{}", QueryType::Factual), "factual");
        assert_eq!(format!("{}", QueryType::MultiHop), "multi-hop");
        assert_eq!(format!("{}", QueryType::Conversational), "conversational");
        assert_eq!(format!("{}", QueryType::Update), "update");
    }
}

#[cfg(test)]
mod plan_builder_tests {
    use strata_common::{Strategy, CostBudget};
    use planner::plan_builder::{PlanBuilder, PlanStep};

    #[test]
    fn test_plan_building_event_log_first() {
        let builder = PlanBuilder::new();
        let strategy = Strategy {
            name: "event_log_first".to_string(),
            cost_budget: CostBudget::Low,
        };
        
        let plan = tokio_test::block_on(builder.build("test query", &strategy));
        
        assert_eq!(plan.strategy, "event_log_first");
        assert_eq!(plan.steps.len(), 1);
        assert!(matches!(plan.steps[0], PlanStep::SelectFromEventLog));
    }

    #[test]
    fn test_plan_building_knowledge_graph_first() {
        let builder = PlanBuilder::new();
        let strategy = Strategy {
            name: "knowledge_graph_first".to_string(),
            cost_budget: CostBudget::Low,
        };
        
        let plan = tokio_test::block_on(builder.build("test query", &strategy));
        
        assert_eq!(plan.strategy, "knowledge_graph_first");
        assert_eq!(plan.steps.len(), 1);
        assert!(matches!(plan.steps[0], PlanStep::KnowledgeGraphTraversal));
    }

    #[test]
    fn test_plan_building_hybrid_with_graph_expansion() {
        let builder = PlanBuilder::new();
        let strategy = Strategy {
            name: "hybrid_with_graph_expansion".to_string(),
            cost_budget: CostBudget::High,
        };
        
        let plan = tokio_test::block_on(builder.build("test query", &strategy));
        
        assert_eq!(plan.strategy, "hybrid_with_graph_expansion");
        assert!(plan.steps.contains(&PlanStep::TemporalFilter));
        assert!(plan.steps.contains(&PlanStep::KnowledgeGraphTraversal));
        assert!(plan.steps.contains(&PlanStep::GraphExpansion));
    }
}

#[cfg(test)]
mod classifier_tests {
    use router::classifier::Classifier;

    #[test]
    fn test_classifier_temporal_query() {
        let classifier = Classifier::new();
        let result = tokio_test::block_on(classifier.classify("Wann habe ich Alice getroffen?"));
        
        assert!(matches!(result.query_type, router::classifier::QueryType::Temporal));
        assert!(result.confidence > 0.8);
    }

    #[test]
    fn test_classifier_factual_query() {
        let classifier = Classifier::new();
        let result = tokio_test::block_on(classifier.classify("Wer ist mein Kunde?"));
        
        assert!(matches!(result.query_type, router::classifier::QueryType::Factual));
        assert!(result.confidence > 0.8);
    }

    #[test]
    fn test_classifier_multi_hop_query() {
        let classifier = Classifier::new();
        let result = tokio_test::block_on(classifier.classify("Warum haben wir das Projekt gestoppt?"));
        
        assert!(matches!(result.query_type, router::classifier::QueryType::MultiHop));
        assert!(result.confidence > 0.8);
    }

    #[test]
    fn test_classifier_conversational_query() {
        let classifier = Classifier::new();
        let result = tokio_test::block_on(classifier.classify("Worüber haben wir gestern gesprochen?"));
        
        assert!(matches!(result.query_type, router::classifier::QueryType::Conversational));
        assert!(result.confidence > 0.8);
    }

    #[test]
    fn test_classifier_update_query() {
        let classifier = Classifier::new();
        let result = tokio_test::block_on(classifier.classify("Aktualisiere meinen Namen"));
        
        assert!(matches!(result.query_type, router::classifier::QueryType::Update));
        assert!(result.confidence > 0.8);
    }
}

#[cfg(test)]
mod policy_tests {
    use strata_common::{QueryClassification, QueryType, CostBudget};
    use router::policy::{Policy, Thresholds};

    #[test]
    fn test_policy_decision_high_confidence() {
        let policy = Policy::default();
        let classification = QueryClassification {
            query_type: QueryType::Temporal,
            confidence: 0.9,
        };
        
        let strategy = policy.decide(&classification);
        
        assert_eq!(strategy.name, "event_log_first");
        assert_eq!(strategy.cost_budget, CostBudget::Low);
    }

    #[test]
    fn test_policy_decision_low_confidence() {
        let policy = Policy::default();
        let classification = QueryClassification {
            query_type: QueryType::Temporal,
            confidence: 0.3,
        };
        
        let strategy = policy.decide(&classification);
        
        assert_eq!(strategy.name, "hybrid_fallback");
        assert_eq!(strategy.cost_budget, CostBudget::Medium);
    }

    #[test]
    fn test_strata_specific_policy() {
        let policy = Policy::default();
        let classification = QueryClassification {
            query_type: QueryType::Temporal,
            confidence: 0.85,
        };
        
        let strategy = policy.decide(&classification);
        
        // STRATA uses hybrid approach for temporal queries
        assert_eq!(strategy.name, "hybrid_bm25_vector_temporal");
        assert_eq!(strategy.cost_budget, CostBudget::Medium);
        
        // Verify strategy includes both temporal and vector components
        assert!(strategy.name.contains("bm25"));
        assert!(strategy.name.contains("vector"));
        assert!(strategy.name.contains("temporal"));
    }
}