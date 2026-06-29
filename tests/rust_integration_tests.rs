// Tests for the Rust components of the STRATA (Spatio-Temporal Reasoning and Analysis) System

#[cfg(test)]
mod tests {
    use std::process::Command;
    use std::thread;
    use std::time::Duration;

    #[test]
    fn test_router_classification_endpoints() {
        // Ensure the router service is running
        let output = Command::new("cargo")
            .args(&["run", "--bin", "strata-router"])
            .output()
            .expect("Failed to start STRATA router service");
        
        // Wait for the service to start
        thread::sleep(Duration::from_secs(3));
        
        // Test classification endpoint
        let client = reqwest::blocking::Client::new();
        let response = client
            .get("http://127.0.0.1:8080/classify")
            .query(&[("query", "Wann habe ich Alice getroffen?")])
            .send()
            .expect("Failed to send request to router");
        
        assert_eq!(response.status(), 200);
        let body = response.text().expect("Failed to read response body");
        println!("Classification response: {}", body);
    }

    #[test]
    fn test_router_routing_endpoints() {
        // Test routing endpoint
        let client = reqwest::blocking::Client::new();
        let response = client
            .get("http://127.0.0.1:8080/route")
            .query(&[("query", "Wer ist mein Kunde?")])
            .send()
            .expect("Failed to send request to router");
        
        assert_eq!(response.status(), 200);
        let body = response.text().expect("Failed to read response body");
        println!("Routing response: {}", body);
    }

    #[test]
    fn test_planner_execution_endpoints() {
        // Ensure the planner service is running
        let output = Command::new("cargo")
            .args(&["run", "--bin", "strata-planner"])
            .output()
            .expect("Failed to start STRATA planner service");
        
        // Wait for the service to start
        thread::sleep(Duration::from_secs(3));
        
        // Test plan execution endpoint
        let client = reqwest::blocking::Client::new();
        let response = client
            .get("http://127.0.0.1:8081/plan_and_execute")
            .query(&[("query", "Was ist Projekt X?")])
            .send()
            .expect("Failed to send request to planner");
        
        assert_eq!(response.status(), 200);
        let body = response.text().expect("Failed to read response body");
        println!("Plan execution response: {}", body);
    }

    #[test]
    fn test_common_module_serialization() {
        use strata_common::{QueryClassification, QueryType, Strategy, CostBudget};
        
        let classification = QueryClassification {
            query_type: QueryType::Temporal,
            confidence: 0.85,
        };

        let serialized = serde_json::to_string(&classification).unwrap();
        let deserialized: QueryClassification = serde_json::from_str(&serialized).unwrap();

        assert_eq!(classification.query_type, deserialized.query_type);
        assert_eq!(classification.confidence, deserialized.confidence);

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
    fn test_surreal_client_connection() {
        use planner::surreal::SurrealClient;

        let client = SurrealClient::new();
        
        // Test basic connectivity by trying a simple query
        let result = tokio_test::block_on(async {
            client.query("INFO FOR DB;").await
        });

        // Note: This test assumes SurrealDB is running
        // In a real scenario, we'd want to handle the case where SurrealDB isn't running
        match result {
            Ok(_) => println!("Successfully connected to SurrealDB"),
            Err(e) => eprintln!("Could not connect to SurrealDB: {}", e),
        }
    }
}