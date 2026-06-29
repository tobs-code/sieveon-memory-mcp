mod plan_builder;
mod executor;
mod surreal;

use axum::{
    routing::post,
    Json, Router,
};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct PlanRequest {
    pub query: String,
}

#[tokio::main]
async fn main() {
    let app = Router::new()
        .route("/plan_and_execute", post(plan_and_execute));

    let listener = tokio::net::TcpListener::bind("127.0.0.1:8081")
        .await
        .expect("Failed to bind Planner to 127.0.0.1:8081");

    println!("Strata Planner Service listening on http://127.0.0.1:8081");
    let _ = axum::serve(listener, app.into_make_service())
        .await
        .expect("Planner server failed");
}

async fn plan_and_execute(
    Json(payload): Json<PlanRequest>,
) -> Json<serde_json::Value> {
    let builder = plan_builder::PlanBuilder::new();
    let default_strategy = "hybrid_fallback"; // Changed to string
    let plan = builder.build_plan(&payload.query, &default_strategy); // Fixed method name
    let executor = executor::Executor::new();
    let result = executor.execute(plan).await;
    Json(result)
}