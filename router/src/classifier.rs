use strata_common::{QueryClassification, QueryType};

pub struct Classifier;

impl Classifier {
    pub fn new() -> Self {
        Self
    }

    pub async fn classify(&self, query: &str) -> QueryClassification {
        let text = query.to_lowercase();

        let (query_type, confidence) = if text.contains("wann")
            || text.contains("heute")
            || text.contains("gestern")
            || text.contains("wann")
            || text.contains("seit")
            || text.contains("vor")
            || text.contains("when")
            || text.contains("yesterday")
            || text.contains("today")
        {
            (QueryType::Temporal, 0.9)
        } else if text.contains("wer")
            || text.contains("was")
            || text.contains("welche")
            || text.contains("wo")
            || text.contains("who")
            || text.contains("what")
            || text.contains("which")
            || text.contains("where")
        {
            (QueryType::Factual, 0.9)
        } else if text.contains("warum")
            || text.contains("wie")
            || text.contains("weshalb")
            || text.contains("wegen")
            || text.contains("why")
            || text.contains("because")
        {
            (QueryType::MultiHop, 0.9)
        } else if text.contains("worüber")
            || text.contains("gesprochen")
            || text.contains("talk about")
            || text.contains("remember")
            || text.contains("remember")
        {
            (QueryType::Conversational, 0.9)
        } else if text.contains("aktualisiere")
            || text.contains("update")
            || text.contains("change")
        {
            (QueryType::Update, 0.9)
        } else {
            (QueryType::Factual, 0.5)
        };

        QueryClassification {
            query_type,
            confidence,
        }
    }
}
