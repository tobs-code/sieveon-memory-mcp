use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PlanStep {
    SelectFromEventLog,
    SelectFromKnowledgeGraph,
    ExpandGraphRelations,
    SelectFromEventLogWithEmbedding,
    SimilaritySearch,
    CheckValidity,
    HybridSearch,  // New step for full hybrid search
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Plan {
    pub query: String,
    pub strategy: String,
    pub steps: Vec<PlanStep>,
}

pub struct PlanBuilder;

impl PlanBuilder {
    pub fn new() -> Self {
        Self
    }

    pub fn build_plan(&self, query: &str, strategy: &str) -> Plan {
        let steps = match strategy {
            "event_log_first" => vec![PlanStep::SelectFromEventLog],
            "knowledge_graph_first" => vec![PlanStep::SelectFromKnowledgeGraph],
            "hybrid_with_graph_expansion" => vec![
                PlanStep::SelectFromEventLog,
                PlanStep::SelectFromKnowledgeGraph,
                PlanStep::ExpandGraphRelations,
            ],
            "composite_kg_vector" => vec![
                PlanStep::SelectFromKnowledgeGraph,
                PlanStep::SimilaritySearch,
            ],
            "knowledge_graph_with_invalidation" => vec![
                PlanStep::SelectFromKnowledgeGraph,
                PlanStep::CheckValidity,
            ],
            "hybrid_bm25_vector_temporal" => vec![  // New strategy for full hybrid search
                PlanStep::HybridSearch,
            ],
            _ => vec![PlanStep::SelectFromEventLog], // Default fallback
        };

        Plan {
            query: query.to_string(),
            strategy: strategy.to_string(),
            steps,
        }
    }
}