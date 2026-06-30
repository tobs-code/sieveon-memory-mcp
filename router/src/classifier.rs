use strata_common::{QueryClassification, QueryType};
use regex::Regex;

pub struct Classifier {
    temporal_patterns: Vec<Regex>,
    factual_patterns: Vec<Regex>,
    multi_hop_patterns: Vec<Regex>,
    conversational_patterns: Vec<Regex>,
    update_patterns: Vec<Regex>,
}

impl Classifier {
    pub fn new() -> Self {
        let compile_patterns = |pats: &[&str]| -> Vec<Regex> {
            pats.iter().map(|p| Regex::new(p).unwrap()).collect()
        };

        Self {
            temporal_patterns: compile_patterns(&[
                r"\bwann\b", r"\bgestern\b", r"\bheute\b", r"\bmorgen\b", r"\bletzt\b", r"\bnächste\b",
                r"\btimestamp\b", r"\bzeit\b", r"\bdatum\b", r"\bseit\b", r"\bbis\b", r"\bänderung\b", r"\bgeändert\b",
                r"\bwhen\b", r"\byesterday\b", r"\btoday\b", r"\btomorrow\b", r"\blast\b", r"\bnext\b",
                r"\btime\b", r"\bdate\b", r"\bsince\b", r"\buntil\b", r"\bchange\b", r"\bchanged\b",
            ]),
            factual_patterns: compile_patterns(&[
                r"\bwer\b", r"\bwas\b", r"\bwelche\b", r"\bwo\b", r"\bhat\b", r"\bhaben\b",
                r"\bwho\b", r"\bwhat\b", r"\bwhich\b", r"\bwhere\b", r"\bhas\b", r"\bhave\b",
            ]),
            multi_hop_patterns: compile_patterns(&[
                r"\bwarum\b", r"\bweshalb\b", r"\bwieso\b", r"\bwegen\b", r"\bdaher\b", r"\bdeshalb\b",
                r"\bbeziehung\b", r"\bverbunden\b", r"\bzusammenhang\b",
                r"\bund wo\b", r"\bund was\b", r"\bund welche\b",
                r"\bwhy\b", r"\bbecause\b", r"\breason\b", r"\brelation\b", r"\bconnected\b", r"\brelationship\b",
                r"\band where\b", r"\band what\b", r"\band which\b",
            ]),
            conversational_patterns: compile_patterns(&[
                r"\bworüber\b", r"\büber was\b", r"\bgesprochen\b", r"\bredeten\b", r"\bunterhielt\b",
                r"\berinnerst du dich\b", r"\bweißt du noch\b",
                r"\bwhat about\b", r"\btalked about\b", r"\bspoke about\b", r"\btalking about\b",
                r"\bremember\b", r"\bdo you recall\b",
            ]),
            update_patterns: compile_patterns(&[
                r"\baktualisiere\b", r"\bupdate\b", r"\bändere\b", r"\bkorrigiere\b", r"\bsetze\b", r"\büberschreibe\b",
                r"\bupdate\b", r"\bchange\b", r"\bmodify\b", r"\bcorrect\b", r"\bset\b", r"\boverwrite\b",
            ]),
        }
    }

    pub async fn classify(&self, query: &str) -> QueryClassification {
        let query_lower = query.to_lowercase();

        let mut scores: Vec<(QueryType, i32)> = vec![
            (QueryType::Temporal, self.count_matches(&query_lower, &self.temporal_patterns)),
            (QueryType::Factual, self.count_matches(&query_lower, &self.factual_patterns)),
            (QueryType::MultiHop, self.count_matches(&query_lower, &self.multi_hop_patterns)),
            (QueryType::Conversational, self.count_matches(&query_lower, &self.conversational_patterns) * 2),
            (QueryType::Update, self.count_matches(&query_lower, &self.update_patterns) * 2),
        ];

        // Sort by score descending, then by priority as tiebreaker
        let priority_order = vec![
            QueryType::Update,
            QueryType::MultiHop,
            QueryType::Temporal,
            QueryType::Conversational,
            QueryType::Factual,
        ];

        scores.sort_by(|a, b| {
            let score_cmp = b.1.cmp(&a.1);
            if score_cmp == std::cmp::Ordering::Equal {
                let a_prio = priority_order.iter().position(|t| t == &a.0).unwrap_or(99);
                let b_prio = priority_order.iter().position(|t| t == &b.0).unwrap_or(99);
                a_prio.cmp(&b_prio)
            } else {
                score_cmp
            }
        });

        let best = &scores[0];
        let best_type = best.0.clone();
        let best_score = best.1;
        let second_best_score = scores[1].1;

        if best_score == 0 {
            return QueryClassification {
                query_type: QueryType::Factual,
                confidence: 0.5,
            };
        }

        let margin = (best_score - second_best_score) as f64 / best_score as f64;
        let confidence = 0.5 + (margin * 0.5);

        QueryClassification {
            query_type: best_type,
            confidence: confidence.clamp(0.5, 1.0) as f64,
        }
    }

    fn count_matches(&self, text: &str, patterns: &[Regex]) -> i32 {
        patterns.iter().filter(|re| re.is_match(text)).count() as i32
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rust_classifier_with_regex() {
        let classifier = Classifier::new();

        // This would need to be run in an async context or we test synchronously
        tokio_test::block_on(async {
            let result = classifier.classify("Wann habe ich Alice getroffen?").await;
            assert!(matches!(result.query_type, QueryType::Temporal));
            assert!(result.confidence >= 0.8);
        });
    }
}
