#!/usr/bin/env python3
"""
Load Schema for Strata
Creates the required database schema in SurrealDB
"""
import requests
import sys
import os
import json
import logging
from urllib.parse import urljoin

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv is not installed, skip loading .env file
    pass

# Get configuration from environment variables or use defaults
SURREAL_URL = os.getenv("SURREALDB_URL", "http://127.0.0.1:8000/sql")
SURREAL_USER = os.getenv("SURREALDB_USER", "root")
SURREAL_PASS = os.getenv("SURREALDB_PASS", "root")
SURREAL_NS = os.getenv("SURREALDB_NS", "strata")  # Updated from agent_memory to strata
SURREAL_DB = os.getenv("SURREALDB_DB", "strata")  # Updated from agent_memory to strata
SURREAL_AUTH = (SURREAL_USER, SURREAL_PASS)

print(f"Connecting to SurrealDB at {SURREAL_URL}")


def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def create_namespace_and_database(logger):
    """Create the namespace and database if they don't exist"""
    logger.info(f"Creating namespace '{SURREAL_NS}' and database '{SURREAL_DB}'...")
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Commands to create namespace and database
    commands = [
        f"DEFINE NAMESPACE {SURREAL_NS};",
        f"USE NS {SURREAL_NS}; DEFINE DATABASE {SURREAL_DB};",
    ]
    
    full_sql = "\n".join(commands)
    
    try:
        response = requests.post(
            SURREAL_URL,
            headers=headers,
            auth=(SURREAL_USER, SURREAL_PASS),
            data=full_sql,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✓ Namespace and database created (or already existed)")
            return True
        else:
            print(f"✗ Failed to create namespace/database: {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ Error creating namespace/database: {e}")
        return False


def create_tables_and_indexes(logger):
    """Create the required tables and indexes for Strata"""
    logger.info("Creating tables and indexes for Strata...")
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Schema definition for Strata
    schema_commands = [
        f"USE NS {SURREAL_NS} DB {SURREAL_DB};",
        
        # Event table - for raw event log
        "DEFINE TABLE event SCHEMAFUL;",
        "DEFINE FIELD content ON TABLE event TYPE string;",
        "DEFINE FIELD source ON TABLE event TYPE string;",
        "DEFINE FIELD timestamp ON TABLE event TYPE datetime DEFAULT time::now();",
        "DEFINE FIELD embedding ON TABLE event TYPE array<float>;",
        "DEFINE FIELD forgotten ON TABLE event TYPE bool DEFAULT false;",
        "DEFINE FIELD forgotten_at ON TABLE event TYPE datetime;",
        "DEFINE FIELD forgotten_reason ON TABLE event TYPE string;",
        
        # Entity table - for knowledge graph entities
        "DEFINE TABLE entity SCHEMAFUL;",
        "DEFINE FIELD name ON TABLE entity TYPE string;",
        "DEFINE FIELD type ON TABLE entity TYPE string;",
        "DEFINE FIELD created_at ON TABLE entity TYPE datetime DEFAULT time::now();",
        "DEFINE FIELD updated_at ON TABLE entity TYPE datetime DEFAULT time::now();",
        "DEFINE FIELD forgotten ON TABLE entity TYPE bool DEFAULT false;",
        
        # Fact table - for knowledge graph relationships
        "DEFINE TABLE fact SCHEMAFUL;",
        "DEFINE FIELD in ON TABLE fact TYPE record<entity>;",  # Subject entity
        "DEFINE FIELD out ON TABLE fact TYPE record<entity>;",  # Object entity
        "DEFINE FIELD predicate ON TABLE fact TYPE string;",    # Relationship type
        "DEFINE FIELD confidence ON TABLE fact TYPE float DEFAULT 1.0;",
        "DEFINE FIELD valid_from ON TABLE fact TYPE datetime DEFAULT time::now();",
        "DEFINE FIELD valid_until ON TABLE fact TYPE option<datetime>;",  # For logical invalidation
        "DEFINE FIELD source_event ON TABLE fact TYPE option<record<event>>;",  # Link to source event
        "DEFINE FIELD created_at ON TABLE fact TYPE datetime DEFAULT time::now();",
        
        # Gate log table - for entropy gate decisions
        "DEFINE TABLE gate_log SCHEMAFUL;",
        "DEFINE FIELD text ON TABLE gate_log TYPE string;",
        "DEFINE FIELD entropy ON TABLE gate_log TYPE float;",
        "DEFINE FIELD novelty ON TABLE gate_log TYPE float;",
        "DEFINE FIELD composite_score ON TABLE gate_log TYPE float;",
        "DEFINE FIELD threshold ON TABLE gate_log TYPE float;",
        "DEFINE FIELD decision ON TABLE gate_log TYPE string;",  # 'extract' or 'ignore'
        "DEFINE FIELD reason ON TABLE gate_log TYPE string;",
        "DEFINE FIELD timestamp ON TABLE gate_log TYPE datetime DEFAULT time::now();",
        
        # Indexes for performance
        "DEFINE INDEX event_timestamp ON TABLE event COLUMNS timestamp;",
        "DEFINE INDEX event_source ON TABLE event COLUMNS source;",
        "DEFINE ANALYZER event_analyzer TOKENIZERS class FILTERS lowercase, ascii, snowball(english);",
        "DEFINE INDEX event_content_ft ON TABLE event FIELDS content SEARCH ANALYZER event_analyzer HIGHLIGHTS;",
        "DEFINE INDEX event_embedding_vec ON TABLE event FIELDS embedding MTREE DIMENSION 768 DIST COSINE;",
        "DEFINE INDEX entity_name ON TABLE entity COLUMNS name;",
        "DEFINE INDEX fact_subject ON TABLE fact COLUMNS in;",
        "DEFINE INDEX fact_object ON TABLE fact COLUMNS out;",
    ]
    
    full_sql = "\n".join(schema_commands)
    
    try:
        response = requests.post(
            SURREAL_URL,
            headers=headers,
            auth=(SURREAL_USER, SURREAL_PASS),
            data=full_sql,
            timeout=60  # Longer timeout for schema creation
        )
        
        if response.status_code == 200:
            data = response.json()
            print("✓ Tables and indexes created successfully")
            
            # Check if any commands failed
            for i, result in enumerate(data):
                if result.get("status") == "ERR":
                    print(f"⚠️  Command {i} failed: {result.get('result', 'Unknown error')}")
            
            return True
        else:
            print(f"✗ Failed to create tables/indexes: {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ Error creating tables/indexes: {e}")
        return False


def verify_schema(logger):
    """Verify that the schema was created correctly"""
    logger.info("Verifying schema...")
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Check what tables exist
    verify_command = [
        f"USE NS {SURREAL_NS} DB {SURREAL_DB};",
        "INFO FOR DB;"
    ]
    full_sql = "\n".join(verify_command)
    
    try:
        response = requests.post(
            SURREAL_URL,
            headers=headers,
            auth=(SURREAL_USER, SURREAL_PASS),
            data=full_sql,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                db_info = data[0].get("result", {})
                tables = db_info.get("tb", {})
                
                required_tables = ["event", "entity", "fact", "gate_log"]
                found_tables = list(tables.keys())
                
                print(f"Found tables: {found_tables}")
                
                missing_tables = [t for t in required_tables if t not in found_tables]
                if missing_tables:
                    print(f"✗ Missing required tables: {missing_tables}")
                    return False
                else:
                    print("✓ All required tables exist")
                    return True
            else:
                print("✗ Could not retrieve database info")
                return False
        else:
            print(f"✗ Verification failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ Verification error: {e}")
        return False


def main():
    """Main function to run schema loading"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Strata Schema Loader")
    logger.info("="*50)
    
    success = True
    
    # Create namespace and database
    if not create_namespace_and_database(logger):
        success = False
        # Continue anyway since DB might already exist
    
    # Create tables and indexes
    if not create_tables_and_indexes(logger):
        success = False
    
    # Verify schema
    if not verify_schema(logger):
        success = False
    
    logger.info("\n" + "="*50)
    if success:
        logger.info("✓ Strata schema loaded successfully!")
        logger.info("The database is now ready for Strata to use.")
        return 0
    else:
        logger.error("✗ Some schema operations failed.")
        logger.error("Check the errors above and try again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())