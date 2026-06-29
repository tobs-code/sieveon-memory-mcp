// Load and stress tests for the router component
// These tests simulate various load conditions to ensure stability

#[cfg(test)]
mod router_load_tests {
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;
    use tokio::time::{timeout, Duration};

    #[tokio::test]
    async fn test_router_single_thread_stress() {
        // Test the router logic directly without HTTP overhead
        use strata::classifier::Classifier;
        use strata::policy::Policy;

        let classifier = Classifier::new();
        let policy = Policy::default();
        
        // Process many requests sequentially to test stability
        for i in 0..1000 {
            let query = format!("Test query number {}", i % 5); // Cycle through a few queries
            
            let classification = classifier.classify(&query).await;
            let strategy = policy.decide(&classification);
            
            // Basic assertions to ensure the components are working
            assert!(!strategy.name.is_empty());
        }
    }

    #[tokio::test]
    async fn test_router_concurrent_load() {
        use strata::classifier::Classifier;
        use strata::policy::Policy;

        let classifier = Arc::new(Classifier::new());
        let policy = Arc::new(Policy::default());
        let counter = Arc::new(AtomicUsize::new(0));

        let mut handles = vec![];

        // Spawn multiple concurrent tasks
        for _ in 0..50 {
            let classifier_clone = classifier.clone();
            let policy_clone = policy.clone();
            let counter_clone = counter.clone();

            let handle = tokio::spawn(async move {
                for i in 0..20 {
                    let query = format!("Concurrent test query {}", i);
                    
                    let classification = classifier_clone.classify(&query).await;
                    let strategy = policy_clone.decide(&classification);
                    
                    // Increment counter on successful completion
                    counter_clone.fetch_add(1, Ordering::SeqCst);
                    
                    // Basic validation
                    assert!(!strategy.name.is_empty());
                }
            });
            handles.push(handle);
        }

        // Wait for all tasks to complete
        for handle in handles {
            handle.await.unwrap();
        }

        // Verify that all operations completed
        let total_ops = counter.load(Ordering::SeqCst);
        assert_eq!(total_ops, 1000); // 50 threads * 20 ops each
    }

    #[tokio::test]
    async fn test_router_variable_query_types_under_load() {
        use strata::classifier::Classifier;
        use strata::policy::Policy;

        let classifier = Arc::new(Classifier::new());
        let policy = Arc::new(Policy::default());

        let query_types = vec![
            "Wann habe ich Alice getroffen?",      // Temporal
            "Wer ist mein Kunde?",                 // Factual
            "Warum haben wir das Projekt gestoppt?", // Multi-hop
            "Worüber haben wir gesprochen?",       // Conversational
            "Aktualisiere meinen Namen",          // Update
            "Random non-matching query",          // Default
        ];

        let mut handles = vec![];

        // Multiple concurrent workers processing different query types
        for worker_id in 0..10 {
            let classifier_clone = classifier.clone();
            let policy_clone = policy.clone();
            let queries = query_types.clone();

            let handle = tokio::spawn(async move {
                for i in 0..100 {
                    let query_idx = (worker_id + i) % queries.len();
                    let query = queries[query_idx];

                    let classification = classifier_clone.classify(query).await;
                    let strategy = policy_clone.decide(&classification);
                    
                    // Validate that we get reasonable results
                    assert!(!strategy.name.is_empty());
                    assert!(classification.confidence >= 0.0 && classification.confidence <= 1.0);
                }
            });
            handles.push(handle);
        }

        // Wait for all workers to finish
        for handle in handles {
            handle.await.unwrap();
        }
    }

    #[tokio::test]
    async fn test_router_long_running_stability() {
        use router::classifier::Classifier;
        use router::policy::Policy;

        let classifier = Classifier::new();
        let policy = Policy::default();
        
        // Run continuously for a period to test long-term stability
        let start_time = std::time::Instant::now();
        let duration = std::time::Duration::from_secs(5); // Run for 5 seconds

        let mut processed_count = 0;
        let queries = [
            "Wann habe ich Alice getroffen?",
            "Wer ist mein Kunde?",
            "Warum haben wir das Projekt gestoppt?",
            "Worüber haben wir gesprochen?",
            "Aktualisiere meinen Namen",
        ];

        while start_time.elapsed() < duration {
            for query in &queries {
                let classification = classifier.classify(query).await;
                let strategy = policy.decide(&classification);
                
                // Basic validation
                assert!(!strategy.name.is_empty());
                assert!(classification.confidence >= 0.0 && classification.confidence <= 1.0);
                
                processed_count += 1;
                
                // Small delay to prevent excessive CPU usage
                tokio::time::sleep(tokio::time::Duration::from_micros(100)).await;
            }
        }

        println!("Processed {} queries in {:?}", processed_count, duration);
        assert!(processed_count > 0); // Ensure we actually processed some queries
    }

    #[tokio::test]
    async fn test_router_timeout_resilience() {
        use router::classifier::Classifier;
        use router::policy::Policy;

        let classifier = Arc::new(Classifier::new());
        let policy = Arc::new(Policy::default());

        let mut handles = vec![];

        // Test with timeout to ensure operations don't hang
        for i in 0..20 {
            let classifier_clone = classifier.clone();
            let policy_clone = policy.clone();

            let handle = tokio::spawn(async move {
                let query = format!("Timeout test query {}", i);
                
                // Wrap the operation in a timeout
                let result = timeout(Duration::from_secs(1), async {
                    let classification = classifier_clone.classify(&query).await;
                    let strategy = policy_clone.decide(&classification);
                    (classification, strategy)
                }).await;

                match result {
                    Ok((classification, strategy)) => {
                        // Success path
                        assert!(!strategy.name.is_empty());
                        assert!(classification.confidence >= 0.0 && classification.confidence <= 1.0);
                        true
                    },
                    Err(_) => {
                        // Timeout occurred
                        eprintln!("Operation timed out for query: {}", query);
                        false
                    }
                }
            });
            handles.push(handle);
        }

        // Collect results and ensure most operations succeeded
        let results: Vec<bool> = futures::future::join_all(handles)
            .await
            .into_iter()
            .map(|r| r.unwrap_or(false))
            .collect();

        let success_count: usize = results.iter().map(|&x| x as usize).sum();
        let total_count = results.len();
        
        // At least 80% should succeed
        assert!(success_count as f64 / total_count as f64 >= 0.8, 
                "Only {}/{} operations succeeded", success_count, total_count);
    }

    #[tokio::test]
    async fn test_router_memory_usage_stability() {
        use router::classifier::Classifier;
        use router::policy::Policy;

        let classifier = Classifier::new();
        let policy = Policy::default();
        
        // Monitor memory usage by running many operations and checking for leaks
        // (In a real test, we'd measure actual memory, but here we just ensure no crashes)
        
        for batch in 0..10 {
            // Process a batch of queries
            for i in 0..100 {
                let query = format!("Memory test query batch {} item {}", batch, i);
                
                let classification = classifier.classify(&query).await;
                let strategy = policy.decide(&classification);
                
                // Basic validation
                assert!(!strategy.name.is_empty());
                assert!(classification.confidence >= 0.0 && classification.confidence <= 1.0);
            }
            
            // Yield control to allow cleanup
            tokio::task::yield_now().await;
        }
    }

    #[tokio::test]
    async fn test_router_error_recovery() {
        use router::classifier::Classifier;
        use router::policy::Policy;

        let classifier = Classifier::new();
        let policy = Policy::default();
        
        // Test with potentially problematic inputs to ensure graceful handling
        let problematic_queries = vec![
            "", // Empty
            "   ", // Whitespace
            &"a".repeat(10000), // Very long
            "Special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?", // Special chars
            "Mixed émojis 🚀 and 📊 symbols", // Unicode
        ];

        for query in &problematic_queries {
            // These should not crash the system
            let classification = classifier.classify(query).await;
            let strategy = policy.decide(&classification);
            
            // Should still return valid results
            assert!(!strategy.name.is_empty());
            assert!(classification.confidence >= 0.0 && classification.confidence <= 1.0);
        }
    }
}