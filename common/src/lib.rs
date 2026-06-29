use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryClassification {
    pub query_type: QueryType,
    pub confidence: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum QueryType {
    Temporal,
    Factual,
    MultiHop,
    Conversational,
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum CostBudget {
    Low,
    Medium,
    High,
}