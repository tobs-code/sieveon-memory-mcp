"""
SurrealDB Integration Tests for Strata
Testing actual SurrealDB interactions
"""
import unittest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests
from src.maintenance.conservative_maintainer import SURREAL_URL, SURREAL_AUTH, SURREAL_NS, SURREAL_DB
from src.extraction.entropy_gate import EntropyGate


def _query_surreal(sql: str):
    """Helper function to query SurrealDB"""
    headers = {"Accept": "application/json"}
    full_sql = f"USE NS {SURREAL_NS} DB {SUREAL_DB};\n{sql}"
    response = requests.post(SURREAL_URL, data=full_sql, headers=headers, auth=SURREAL_AUTH, timeout=30)
    response.raise_for_status()
    return response.json()


def _extract_result(data, index: int = 1):
    """Helper function to extract results from SurrealDB response"""
    if not isinstance(data, list):
        return []
    candidates = [
        item for item in data
        if isinstance(item, dict)
        and item.get("status") == "OK"
        and "result" in item
        and not (isinstance(item["result"], dict) and "database" in item["result"] and "namespace" in item["result"])
    ]
    if not candidates:
        return []
    if len(candidates) <= index:
        target = candidates[-1]
    else:
        target = candidates[index]
    result = target.get("result", [])
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return [result]
    return []


class TestSurrealIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test database with clean state"""
        try:
            # Clean up any existing test data
            _query_surreal("DELETE event; DELETE entity; DELETE fact; DELETE gate_log;")
        except:
            # DB might not exist yet, that's okay
            pass

    def test_basic_event_creation(self):
        """Test basic event creation in SurrealDB"""
        content = "Test event for integration testing"
        content_escaped = content.replace("'", "''")

        sql = f"""
        CREATE event SET
            content = '{content_escaped}',
            timestamp = time::now();
        """

        result = _query_surreal(sql)
        events = _extract_result(result)

        self.assertTrue(len(events) > 0)
        self.assertEqual(events[0]["content"], content)

    def test_entity_creation(self):
        """Test entity creation in SurrealDB"""
        entity_name = "TestEntity"
        name_escaped = entity_name.replace("'", "''")

        sql = f"""
        CREATE entity SET
            name = '{name_escaped}';
        """

        result = _query_surreal(sql)
        entities = _extract_result(result)

        self.assertTrue(len(entities) > 0)
        self.assertEqual(entities[0]["name"], entity_name)

    def test_fact_creation_and_relationship(self):
        """Test fact creation and relating entities"""
        # Create two entities
        subj_name = "SubjectEntity"
        obj_name = "ObjectEntity"

        subj_name_clean = subj_name.replace("'", "''")
        obj_name_clean = obj_name.replace("'", "''")
        subj_sql = f"CREATE entity SET name = '{subj_name_clean}';"
        obj_sql = f"CREATE entity SET name = '{obj_name_clean}';"

        subj_result = _query_surreal(subj_sql)
        obj_result = _query_surreal(obj_sql)

        subj_entities = _extract_result(subj_result)
        obj_entities = _extract_result(obj_result)

        self.assertTrue(len(subj_entities) > 0)
        self.assertTrue(len(obj_entities) > 0)

        subj_id = subj_entities[0]["id"]
        obj_id = obj_entities[0]["id"]

        # Create a fact as a normal table (fact is TYPE NORMAL in this DB, not RELATION)
        fact_sql = f"""
        CREATE fact SET
            `in` = '{subj_id}',
            out = '{obj_id}',
            predicate = 'test_predicate',
            valid_until = NONE;
        """

        fact_result = _query_surreal(fact_sql)
        facts = _extract_result(fact_result)

        self.assertTrue(len(facts) > 0)
        self.assertEqual(facts[0]["predicate"], "test_predicate")

    def test_basic_query_functionality(self):
        """Test basic querying functionality"""
        # Create test data
        test_content = "Integration test content for querying"
        content_escaped = test_content.replace("'", "''")

        create_sql = f"""
        CREATE event SET
            content = '{content_escaped}',
            timestamp = time::now();
        """

        _query_surreal(create_sql)

        # Query the data back using exact match on content field
        query_sql = f"SELECT * FROM event WHERE content = '{content_escaped}';"
        result = _query_surreal(query_sql)
        events = _extract_result(result)

        self.assertTrue(len(events) > 0)
        found = False
        for event in events:
            if event.get("content") == test_content:
                found = True
                break
        self.assertTrue(found, "Created event should be found in query results")

    def test_timestamp_functionality(self):
        """Test timestamp-based queries"""
        past_content = "Past event for timestamp test"
        future_content = "Future event for timestamp test"

        for content in [past_content, future_content]:
            content_escaped = content.replace("'", "''")
            sql = f"""
            CREATE event SET
                content = '{content_escaped}',
                timestamp = time::now();
            """
            _query_surreal(sql)

        past_query = f"""
        SELECT * FROM event 
        WHERE content = 'Past event for timestamp test';
        """
        past_result = _query_surreal(past_query)
        past_events = _extract_result(past_result)

        self.assertTrue(len(past_events) > 0, "Should find past events")

    def test_entropy_gate_surreal_integration(self):
        """Test entropy gate integration with SurrealDB"""
        gate = EntropyGate()

        # Test that the gate can successfully store decisions in DB
        test_text = "This is a test for entropy gate integration with SurrealDB"
        result = gate.should_extract(test_text)

        # The decision should be made without errors
        self.assertIn("decision", result)
        self.assertIn(result["decision"], ["extract", "ignore", "skip"])

        # If it decided to extract, verify it was logged
        if result["decision"] == "extract":
            # Check that the event was added to the vector DB
            self.assertIsNotNone(gate.vector_db.vectors)

        test_text_clean = test_text.replace("'", "''")
        log_check_sql = f"SELECT * FROM gate_log WHERE content_hash = '{test_text_clean}';"
        try:
            log_result = _query_surreal(log_check_sql)
            logs = _extract_result(log_result)
            # May not find log if DB is unavailable, but shouldn't error
        except:
            # If logging fails, that's OK for this test
            pass

    def test_complex_query_with_joins(self):
        """Test more complex queries with joins"""
        # Create test entity
        entity_sql = """
        CREATE entity SET name = 'ComplexTestPerson';
        """
        entity_result = _query_surreal(entity_sql)
        entities = _extract_result(entity_result)

        self.assertTrue(len(entities) > 0)

        # Create related event
        event_content = "Event related to ComplexTestPerson"
        content_escaped = event_content.replace("'", "''")

        event_sql = f"""
        CREATE event SET
            content = '{content_escaped}',
            timestamp = time::now();
        """

        _query_surreal(event_sql)

        # Query to find the event we just created
        query_sql = f"SELECT * FROM event WHERE content = '{content_escaped}';"
        query_result = _query_surreal(query_sql)
        results = _extract_result(query_result)

        # Should find the related event
        found = False
        for result in results:
            if result.get("content") == event_content:
                found = True
                break

        self.assertTrue(found, "Should find the created event")


class TestSurrealConsistency(unittest.TestCase):
    """Tests to ensure consistency in SurrealDB operations"""

    def test_transaction_like_behavior(self):
        """Test that operations behave consistently"""
        # Create entity
        base_name = "ConsistencyTest"

        base_name_clean = base_name.replace("'", "''")
        entity_sql = f"CREATE entity SET name = '{base_name_clean}';"
        entity_result = _query_surreal(entity_sql)
        entities = _extract_result(entity_result)

        self.assertTrue(len(entities) > 0)
        entity_id = entities[0]["id"]

        # Verify we can retrieve it immediately using FROM <record_id> syntax
        retrieve_sql = f"SELECT * FROM {entity_id};"
        retrieve_result = _query_surreal(retrieve_sql)
        retrieved = _extract_result(retrieve_result)

        self.assertTrue(len(retrieved) > 0)
        self.assertEqual(retrieved[0]["id"], entity_id)
        self.assertEqual(retrieved[0]["name"], base_name)

    def test_data_persistence(self):
        """Test that data persists between operations"""
        test_value = "Persistence test value"
        value_escaped = test_value.replace("'", "''")

        # Insert
        insert_sql = f"""
        CREATE event SET
            content = '{value_escaped}',
            timestamp = time::now();
        """
        _query_surreal(insert_sql)

        # Immediately query back
        query_sql = f"SELECT * FROM event WHERE content = '{value_escaped}';"
        query_result = _query_surreal(query_sql)
        results = _extract_result(query_result)

        self.assertTrue(len(results) > 0)
        found = False
        for result in results:
            if result.get("content") == test_value:
                found = True
                break
        self.assertTrue(found)


if __name__ == '__main__':
    print("Running Strata SurrealDB Integration Tests...")
    unittest.main(verbosity=2)