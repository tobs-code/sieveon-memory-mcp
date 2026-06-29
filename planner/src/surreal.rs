use reqwest::Client;
use serde_json::Value;

const SURREALDB_URL: &str = "http://127.0.0.1:8000/sql";
const SURREALDB_USER: &str = "root";
const SURREALDB_PASS: &str = "root";
const SURREALDB_NS: &str = "agent_memory";
const SURREALDB_DB: &str = "agent_memory";

pub struct SurrealClient {
    client: Client,
}

impl SurrealClient {
    pub fn new() -> Self {
        Self {
            client: Client::new(),
        }
    }

    pub async fn query(&self, query: &str) -> Result<Value, reqwest::Error> {
        let payload = serde_json::json!({"query": query});
        
        let response = self
            .client
            .post(SURREALDB_URL)
            .header("NS", SURREALDB_NS)
            .header("DB", SURREALDB_DB)
            .basic_auth(SURREALDB_USER, Some(SURREALDB_PASS))
            .json(&payload)
            .send()
            .await?;

        let json: Value = response.json().await?;
        Ok(json)
    }
}