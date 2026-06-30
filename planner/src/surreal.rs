use reqwest::Client;
use serde_json::Value;

pub struct SurrealClient {
    client: Client,
    url: String,
    user: String,
    pass: String,
    ns: String,
    db: String,
}

impl SurrealClient {
    pub fn new() -> Self {
        Self {
            client: Client::new(),
            url: std::env::var("SURREALDB_URL").unwrap_or_else(|_| "http://127.0.0.1:8000/sql".to_string()),
            user: std::env::var("SURREALDB_USER").unwrap_or_else(|_| "root".to_string()),
            pass: std::env::var("SURREALDB_PASS").unwrap_or_else(|_| "root".to_string()),
            ns: std::env::var("SURREALDB_NS").unwrap_or_else(|_| "strata".to_string()),
            db: std::env::var("SURREALDB_DB").unwrap_or_else(|_| "strata".to_string()),
        }
    }

    pub async fn query(&self, query: &str) -> Result<Value, reqwest::Error> {
        // Use the same header-based NS/DB selection as the Python version for consistency
        let response = self
            .client
            .post(&self.url)
            .header("NS", &self.ns)
            .header("DB", &self.db)
            .header("Accept", "application/json")
            .basic_auth(&self.user, Some(&self.pass))
            .body(query.to_string())
            .send()
            .await?;

        let json: Value = response.json().await?;
        Ok(json)
    }
}