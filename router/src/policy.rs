use strata_common::{QueryClassification, QueryType, Strategy, CostBudget, BudgetTracker};
use std::collections::HashMap;
use std::sync::{Arc, Mutex};

#[allow(dead_code)]
pub struct Policy {
    pub thresholds: Thresholds,
    pub usage: Arc<Mutex<HashMap<String, BudgetTracker>>>,
}

#[derive(Debug, Clone)]
pub struct Thresholds {
    pub default_min_confidence: f64,
}

impl Default for Thresholds {
    fn default() -> Self {
        Self {
            default_min_confidence: 0.6,
        }
    }
}

impl Default for Policy {
    fn default() -> Self {
        Self {
            thresholds: Thresholds::default(),
            usage: Arc::new(Mutex::new(HashMap::new())),
        }
    }
}

#[allow(dead_code)]
impl Policy {
    pub fn decide(&self, classification: &QueryClassification) -> Strategy {
        if classification.confidence < self.thresholds.default_min_confidence {
            return Strategy {
                name: "hybrid_fallback".to_string(),
                cost_budget: CostBudget::Medium,
            };
        }

        match classification.query_type {
            QueryType::Temporal => Strategy {
                name: "hybrid_bm25_vector_temporal".to_string(),
                cost_budget: CostBudget::Medium,
            },
            QueryType::Factual => Strategy {
                name: "hybrid_bm25_vector_temporal".to_string(), // Updated to match Python
                cost_budget: CostBudget::Medium,
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
        }
    }

    pub fn create_tracker(&self, key: String, budget: CostBudget) -> String {
        let tracker = BudgetTracker::new(budget);
        let mut usage = self.usage.lock().unwrap();
        usage.insert(key.clone(), tracker);
        key
    }

    pub fn record_db_call(&self, key: &str, count: u32) {
        let mut usage = self.usage.lock().unwrap();
        if let Some(tracker) = usage.get_mut(key) {
            tracker.record_db_call(count);
        }
    }

    pub fn record_tokens(&self, key: &str, count: u32) {
        let mut usage = self.usage.lock().unwrap();
        if let Some(tracker) = usage.get_mut(key) {
            tracker.record_tokens(count);
        }
    }

    pub fn is_over_budget(&self, key: &str) -> bool {
        let usage = self.usage.lock().unwrap();
        usage.get(key).map(|t| t.is_over_budget()).unwrap_or(false)
    }
}