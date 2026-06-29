use strata_common::{QueryClassification, QueryType, Strategy, CostBudget};

#[derive(Default)]
pub struct Policy {
    pub thresholds: Thresholds,
}

#[derive(Debug, Clone)]
pub struct Thresholds {
    pub temporal_confidence: f64,
    pub factual_confidence: f64,
    pub multihop_confidence: f64,
    pub conversational_confidence: f64,
    pub update_confidence: f64,
}

impl Default for Thresholds {
    fn default() -> Self {
        Self {
            temporal_confidence: 0.7,
            factual_confidence: 0.7,
            multihop_confidence: 0.6,
            conversational_confidence: 0.7,
            update_confidence: 0.6,
        }
    }
}

impl Policy {
    pub fn decide(&self, classification: &QueryClassification) -> Strategy {
        if classification.confidence < 0.5 {
            return Strategy {
                name: "hybrid_fallback".to_string(),
                cost_budget: CostBudget::Medium,
            };
        }

        let strategy = match classification.query_type {
            QueryType::Temporal => Strategy {
                name: "hybrid_bm25_vector_temporal".to_string(), // Using full hybrid for temporal queries
                cost_budget: CostBudget::Medium,
            },
            QueryType::Factual => Strategy {
                name: "knowledge_graph_first".to_string(),
                cost_budget: CostBudget::Low,
            },
            QueryType::MultiHop => Strategy {
                name: "hybrid_with_graph_expansion".to_string(),
                cost_budget: CostBudget::High,
            },
            QueryType::Conversational => Strategy {
                name: "composite_kg_vector".to_string(),
                cost_budget: CostBudget::Medium,
            },
            QueryType::Update => Strategy {
                name: "knowledge_graph_with_invalidation".to_string(),
                cost_budget: CostBudget::High,
            },
        };

        strategy
    }
}