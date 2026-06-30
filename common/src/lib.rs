use serde::{Deserialize, Serialize};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryClassification {
    pub query_type: QueryType,
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum QueryType {
    #[serde(rename = "temporal")]
    Temporal,
    #[serde(rename = "factual")]
    Factual,
    #[serde(rename = "multi-hop")]
    MultiHop,
    #[serde(rename = "conversational")]
    Conversational,
    #[serde(rename = "update")]
    Update,
}

impl std::fmt::Display for QueryType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            QueryType::Temporal => write!(f, "temporal"),
            QueryType::Factual => write!(f, "factual"),
            QueryType::MultiHop => write!(f, "multi-hop"),
            QueryType::Conversational => write!(f, "conversational"),
            QueryType::Update => write!(f, "update"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Strategy {
    pub name: String,
    pub cost_budget: CostBudget,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Copy)]
pub enum CostBudget {
    #[serde(rename = "low")]
    Low,
    #[serde(rename = "medium")]
    Medium,
    #[serde(rename = "high")]
    High,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BudgetTracker {
    pub budget: CostBudget,
    pub db_calls: u32,
    pub estimated_tokens: u32,
    pub start_time: f64,
    pub end_time: Option<f64>,
}

impl BudgetTracker {
    pub fn new(budget: CostBudget) -> Self {
        let start = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or(Duration::from_secs(0))
            .as_secs_f64();
            
        Self {
            budget,
            db_calls: 0,
            estimated_tokens: 0,
            start_time: start,
            end_time: None,
        }
    }

    pub fn record_db_call(&mut self, count: u32) {
        self.db_calls += count;
    }

    pub fn record_tokens(&mut self, count: u32) {
        self.estimated_tokens += count;
    }

    pub fn finish(&mut self) {
        self.end_time = Some(
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or(Duration::from_secs(0))
                .as_secs_f64()
        );
    }

    pub fn is_over_budget(&self) -> bool {
        let (max_db, max_tokens) = match self.budget {
            CostBudget::Low => (10, 1000),
            CostBudget::Medium => (25, 3000),
            CostBudget::High => (50, 8000),
        };
        
        self.db_calls > max_db || self.estimated_tokens > max_tokens
    }

    pub fn duration_seconds(&self) -> f64 {
        match self.end_time {
            Some(end) => end - self.start_time,
            None => SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or(Duration::from_secs(0))
                .as_secs_f64() - self.start_time,
        }
    }
}