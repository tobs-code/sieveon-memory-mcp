#!/usr/bin/env python3
"""
SurrealDB Connection Checker for Strata
Verifies that SurrealDB is accessible and responding correctly
"""
import requests
import sys
import os
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
SURREAL_AUTH = (os.getenv("SURREALDB_USER", "root"), os.getenv("SURREALDB_PASS", "root"))
SURREAL_NS = os.getenv("SURREALDB_NS", "strata")  # Updated from agent_memory to strata
SURREAL_DB = os.getenv("SURREALDB_DB", "strata")  # Updated from agent_memory to strata


def _query_surreal(sql: str) -> Any:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    full_sql = f"USE NS {SURREAL_NS} DB {SURREAL_DB};\n{sql}"
    try:
        response = requests.post(
            SURREAL_URL,
            headers=headers,
            auth=SURREAL_AUTH,
            data=full_sql,
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        else:
            print(f"✗ Query failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return None
    except Exception as e:
        print(f"✗ Query execution error: {e}")
        return None


def check_surreal_connection():
    """Check if we can connect to SurrealDB and authenticate"""
    print(f"Checking connection to SurrealDB at {SURREAL_URL}")
    
    try:
        # Test basic connectivity
        response = requests.get(
            SURREAL_URL.replace('/sql', '/status'),
            timeout=10
        )
        print(f"✓ HTTP connection: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"✗ Cannot connect to {SURREAL_URL}")
        return False
    except Exception as e:
        print(f"✗ Connection error: {e}")
        return False
    
    # Test authentication and basic operations
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Try to switch namespace/database and run a simple query
    sql_commands = [
        f"USE NS {SURREAL_NS} DB {SURREAL_DB};",
        "INFO FOR DB;"
    ]
    full_sql = "\n".join(sql_commands)
    
    try:
        response = requests.post(
            SURREAL_URL,
            headers=headers,
            auth=SURREAL_AUTH,
            data=full_sql,
            timeout=10
        )
        
        if response.status_code == 200:
            print("✓ Authentication successful")
            print("✓ Can access namespace and database")
            
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                print("✓ Successfully executed query")
                return True
            else:
                print("? Query executed but no data returned")
                return True
        else:
            print(f"✗ Query failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ Query execution error: {e}")
        return False


def check_required_tables():
    """Check if the required tables for Strata exist"""
    print("\nChecking for required tables...")
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Switch to our namespace/database and check for tables
    sql_commands = [
        f"USE NS {SURREAL_NS} DB {SURREAL_DB};",
        "INFO FOR DB;"
    ]
    full_sql = "\n".join(sql_commands)
    
    try:
        response = requests.post(
            SURREAL_URL,
            headers=headers,
            auth=SURREAL_AUTH,
            data=full_sql,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                db_info = data[0].get("result", {})
                
                if isinstance(db_info, dict):
                    tables = db_info.get("tb", {})  # Tables are usually under 'tb' key
                    required_tables = ["event", "entity", "fact", "gate_log"]
                    
                    print("Found tables:", list(tables.keys()) if tables else "None")
                    
                    missing_tables = []
                    for req_table in required_tables:
                        if req_table not in tables:
                            missing_tables.append(req_table)
                    
                    if missing_tables:
                        print(f"⚠️  Missing required tables: {missing_tables}")
                        print("   These will be created when Strata initializes")
                    else:
                        print("✓ All required tables exist")
                    
                    return True
                else:
                    print("? Could not parse database info")
                    return True
            else:
                print("? Could not retrieve database info")
                return True
        else:
            print(f"✗ Table check failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"✗ Table check error: {e}")
        return False


def main():
    """Main function to run all checks"""
    print("Strata SurrealDB Connection Checker")
    print("="*40)
    
    success = True
    
    # Check connection
    if not check_surreal_connection():
        success = False
    
    # Check tables
    if not check_required_tables():
        success = False
    
    print("\n" + "="*40)
    if success:
        print("✓ All checks passed! SurrealDB is ready for Strata.")
        return 0
    else:
        print("✗ Some checks failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())