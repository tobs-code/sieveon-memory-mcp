"""
Plan Executor for Strata
Executes different retrieval strategies based on the plan
"""
import asyncio
import time
import requests
import json
import os
from typing import Dict, List, Any, Optional
import numpy as np
from urllib.parse import quote

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is not installed, skip loading .env file
    pass

# Import embedding service
try:
    from src.extraction.embedding_service import get_embedding_service
except ImportError:
    # Handle relative import when module is not installed
    from extraction.embedding_service import get_embedding_service


class RetrievalExecutor:
    """Retrieval executor that wraps PlanExecutor functionality for backward compatibility"""
    def __init__(self):
        self.plan_executor = PlanExecutor()
    
    async def execute(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Async execute method that matches the expected interface"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self.plan_executor.execute_plan, plan)
        return result


class PlanExecutor:
    def __init__(self):
        self.surreal_url = os.getenv("SURREALDB_URL", "http://127.0.0.1:8000/sql")
        self.auth = (os.getenv("SURREALDB_USER", "root"), os.getenv("SURREALDB_PASS", "root"))
        self.ns = os.getenv("SURREALDB_NS", "strata")  # Updated to match the database we created
        self.db = os.getenv("SURREALDB_DB", "strata")  # Updated to match the database we created
        self.temporal_weight = 0.3  # Weight for temporal relevance
        self.semantic_weight = 0.5  # Weight for semantic similarity
        self.keyword_weight = 0.2   # Weight for keyword matching (BM25)
        self.embedding_service = get_embedding_service()

    def execute_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a query plan based on the strategy
        """
        strategy = plan.get('strategy', 'hybrid_fallback')
        query = plan.get('query', '')
        
        start_time = time.time()
        
        if strategy == "event_log_first":
            result = self._execute_event_log_first(query)
        elif strategy == "knowledge_graph_first":
            result = self._execute_knowledge_graph_first(query)
        elif strategy == "hybrid_with_graph_expansion":
            result = self._execute_hybrid_with_graph_expansion(query)
        elif strategy == "composite_kg_vector":
            result = self._execute_composite_kg_vector(query)
        elif strategy == "knowledge_graph_with_invalidation":
            result = self._execute_knowledge_graph_with_invalidation(query)
        elif strategy == "hybrid_bm25_vector_temporal":
            result = self._execute_hybrid_bm25_vector_temporal(query)
        else:
            result = self._execute_hybrid_fallback(query)
        
        execution_time = time.time() - start_time
        
        return {
            'strategy': strategy,
            'query': query,
            'result': result,
            'execution_time': execution_time,
            'timestamp': time.time()
        }

    def _execute_event_log_first(self, query: str) -> Dict[str, Any]:
        """Execute event log first strategy"""
        try:
            escaped_query = query.replace("'", "''")
            sql = f"SELECT * FROM event WHERE content @@ '{escaped_query}' ORDER BY timestamp DESC LIMIT 10;"
            return self._query_surreal(sql)
        except Exception as e:
            return {'error': str(e), 'strategy': 'event_log_first'}

    def _execute_knowledge_graph_first(self, query: str) -> Dict[str, Any]:
        """Execute knowledge graph first strategy"""
        try:
            escaped_query = query.replace("'", "''")
            sql = f"SELECT * FROM entity WHERE name @@ '{escaped_query}' LIMIT 10;"
            return self._query_surreal(sql)
        except Exception as e:
            return {'error': str(e), 'strategy': 'knowledge_graph_first'}

    def _execute_hybrid_with_graph_expansion(self, query: str) -> Dict[str, Any]:
        """Execute hybrid strategy with graph expansion"""
        try:
            escaped_query = query.replace("'", "''")
            events_sql = f"SELECT * FROM event WHERE content @@ '{escaped_query}' ORDER BY timestamp DESC LIMIT 5;"
            entities_sql = f"SELECT * FROM entity WHERE name @@ '{escaped_query}' LIMIT 5;"
            
            events_result = self._query_surreal(events_sql)
            entities_result = self._query_surreal(entities_sql)
            
            return {
                'events': events_result,
                'entities': entities_result,
                'strategy': 'hybrid_with_graph_expansion'
            }
        except Exception as e:
            return {'error': str(e), 'strategy': 'hybrid_with_graph_expansion'}

    def _execute_composite_kg_vector(self, query: str) -> Dict[str, Any]:
        """Execute composite knowledge graph and vector strategy"""
        try:
            escaped_query = query.replace("'", "''")
            sql = f"SELECT * FROM event WHERE content @@ '{escaped_query}' ORDER BY timestamp DESC LIMIT 10;"
            return self._query_surreal(sql)
        except Exception as e:
            return {'error': str(e), 'strategy': 'composite_kg_vector'}

    def _execute_knowledge_graph_with_invalidation(self, query: str) -> Dict[str, Any]:
        """Execute knowledge graph with invalidation strategy"""
        try:
            escaped_query = query.replace("'", "''")
            sql = f"SELECT * FROM entity WHERE name @@ '{escaped_query}' AND (valid_until IS NULL OR valid_until > time::now()) LIMIT 10;"
            return self._query_surreal(sql)
        except Exception as e:
            return {'error': str(e), 'strategy': 'knowledge_graph_with_invalidation'}

    def _execute_hybrid_fallback(self, query: str) -> Dict[str, Any]:
        """Execute hybrid fallback strategy"""
        try:
            escaped_query = query.replace("'", "''")
            sql = f"SELECT * FROM event WHERE content @@ '{escaped_query}' ORDER BY timestamp DESC LIMIT 5;"
            return self._query_surreal(sql)
        except Exception as e:
            return {'error': str(e), 'strategy': 'hybrid_fallback'}

    def _execute_hybrid_bm25_vector_temporal(self, query: str) -> Dict[str, Any]:
        """Execute full hybrid search combining BM25, vector similarity, and temporal relevance"""
        try:
            # Step 1: Get keyword-based results (BM25-like)
            keyword_results = self._execute_bm25_search(query)
            
            # Step 2: Get vector similarity results
            vector_results = self._execute_vector_search(query)
            
            # Step 3: Get temporal relevance results
            temporal_results = self._execute_temporal_search(query)
            
            # Step 4: Combine results with weighted scoring
            combined_results = self._combine_hybrid_results(keyword_results, vector_results, temporal_results)
            
            return {
                'keyword_results': keyword_results,
                'vector_results': vector_results,
                'temporal_results': temporal_results,
                'combined_results': combined_results,
                'strategy': 'hybrid_bm25_vector_temporal'
            }
        except Exception as e:
            return {'error': str(e), 'strategy': 'hybrid_bm25_vector_temporal'}

    def _execute_bm25_search(self, query: str) -> List[Dict[str, Any]]:
        """Execute keyword-based search using SurrealDB's full-text search (BM25 equivalent)"""
        try:
            escaped_query = query.replace("'", "''")
            sql = f"SELECT *, search::score(1.0) AS relevance_score FROM event WHERE content @@ '{escaped_query}' ORDER BY relevance_score DESC LIMIT 10;"
            result = self._query_surreal(sql)
            
            # Extract results array from SurrealDB response
            if isinstance(result, list) and len(result) > 1 and 'result' in result[1]:
                return result[1]['result']
            else:
                return []
        except Exception as e:
            print(f"BM25 search error: {e}")
            return []

    def _execute_vector_search(self, query: str) -> List[Dict[str, Any]]:
        """Execute vector similarity search using embedding similarity"""
        try:
            # In a real implementation, this would use SurrealDB's vector search capabilities
            # For now, we'll use a simplified approach with a stored procedure or function call
            escaped_query = query.replace("'", "''")
            # This would typically use a vector search function in SurrealDB like: search::knn(...)
            # For now, we'll use the basic full-text search as a placeholder
            sql = f"SELECT * FROM event WHERE content @@ '{escaped_query}' ORDER BY timestamp DESC LIMIT 10;"
            result = self._query_surreal(sql)
            
            if isinstance(result, list) and len(result) > 1 and 'result' in result[1]:
                # Add a similarity score for ranking purposes
                events = result[1]['result']
                for event in events:
                    event['similarity_score'] = self._calculate_similarity_score(query, event.get('content', ''))
                return events
            else:
                return []
        except Exception as e:
            print(f"Vector search error: {e}")
            return []

    def _execute_temporal_search(self, query: str) -> List[Dict[str, Any]]:
        """Execute temporal relevance search based on time proximity"""
        try:
            escaped_query = query.replace("'", "''")
            sql = f"SELECT *, time::now() - timestamp AS time_diff FROM event WHERE content @@ '{escaped_query}' ORDER BY timestamp DESC LIMIT 10;"
            result = self._query_surreal(sql)
            
            if isinstance(result, list) and len(result) > 1 and 'result' in result[1]:
                # Add temporal score based on recency
                events = result[1]['result']
                for event in events:
                    time_diff = event.get('time_diff', 0)
                    # Calculate temporal score (more recent = higher score)
                    event['temporal_score'] = 1.0 / (1.0 + time_diff)  # Simplified temporal scoring
                return events
            else:
                return []
        except Exception as e:
            print(f"Temporal search error: {e}")
            return []

    def _calculate_similarity_score(self, query: str, content: str) -> float:
        """Calculate a basic similarity score between query and content"""
        query_words = set(query.lower().split())
        content_words = set(content.lower().split())
        intersection = query_words.intersection(content_words)
        union = query_words.union(content_words)
        if len(union) == 0:
            return 0.0
        return len(intersection) / len(union)  # Jaccard similarity

    def _combine_hybrid_results(self, keyword_results: List[Dict], vector_results: List[Dict], temporal_results: List[Dict]) -> List[Dict]:
        """Combine results from different search modalities with weighted scoring"""
        # Create a map of event IDs to their scores from different modalities
        combined_scores = {}
        result_map = {}
        
        # Add keyword scores (BM25)
        for i, result in enumerate(keyword_results):
            event_id = result.get('id', f'kw_{i}')
            combined_scores[event_id] = {
                'keyword_score': result.get('relevance_score', 0.0),
                'vector_score': 0.0,
                'temporal_score': 0.0
            }
            result_map[event_id] = result
        
        # Add vector scores
        for i, result in enumerate(vector_results):
            event_id = result.get('id', f'vec_{i}')
            if event_id not in combined_scores:
                combined_scores[event_id] = {
                    'keyword_score': 0.0,
                    'vector_score': 0.0,
                    'temporal_score': 0.0
                }
                result_map[event_id] = result
            combined_scores[event_id]['vector_score'] = result.get('similarity_score', 0.0)
            # Update result_map if not already present
            if event_id not in result_map:
                result_map[event_id] = result
        
        # Add temporal scores
        for i, result in enumerate(temporal_results):
            event_id = result.get('id', f'temp_{i}')
            if event_id not in combined_scores:
                combined_scores[event_id] = {
                    'keyword_score': 0.0,
                    'vector_score': 0.0,
                    'temporal_score': 0.0
                }
                result_map[event_id] = result
            combined_scores[event_id]['temporal_score'] = result.get('temporal_score', 0.0)
            # Update result_map if not already present
            if event_id not in result_map:
                result_map[event_id] = result

        # Calculate final hybrid score for each result
        final_results = []
        for event_id, scores in combined_scores.items():
            hybrid_score = (
                self.keyword_weight * scores['keyword_score'] +
                self.semantic_weight * scores['vector_score'] +
                self.temporal_weight * scores['temporal_score']
            )
            final_result = result_map[event_id].copy()
            final_result['hybrid_score'] = hybrid_score
            final_results.append(final_result)

        # Sort by hybrid score in descending order
        final_results.sort(key=lambda x: x.get('hybrid_score', 0.0), reverse=True)
        return final_results

    def _query_surreal(self, sql: str) -> List[Dict[str, Any]]:
        """Execute a SurrealDB query"""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        full_sql = f"USE NS {self.ns} DB {self.db};\n{sql}"
        
        response = requests.post(
            self.surreal_url,
            data=full_sql,
            headers=headers,
            auth=self.auth,
            timeout=30
        )
        
        result = response.json()
        return result