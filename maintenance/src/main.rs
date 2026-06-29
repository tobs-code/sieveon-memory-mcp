mod maintainer;

use std::time::Duration;
use tokio::time::sleep;

#[tokio::main]
async fn main() {
    let engine = maintainer::Maintainer::new();

    println!("Strata Maintenance Service starting...");
    loop {
        sleep(Duration::from_secs(60)).await;
        let _ = engine.cleanup().await;
    }
}