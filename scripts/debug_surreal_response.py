#!/usr/bin/env python3
"""
Debug SurrealDB Response for Strata
Helps debug SurrealDB queries and responses
"""
import requests
import sys
import os
import json
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

def _query_surreal_with_debug(sql_query: str) -> tuple:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    full_sql = f"USE NS {SURREAL_NS} DB {SURREAL_DB};\n{sql_query}"
    try:
        response = requests.post(
            SURREAL_URL,
            headers=headers,
            auth=SURREAL_AUTH,
            data=full_sql,
            timeout=30
        )
        try:
            data = response.json()
            return data, response.status_code
        except json.JSONDecodeError:
            return response.text, response.status_code
    except requests.exceptions.RequestException as e:
        return f"Request failed: {e}", None
    except Exception as e:
        return f"Unexpected error: {e}", None


def debug_query(sql_query, verbose=True):
    """Debug a SurrealDB query and show detailed response information"""
    if verbose:
        print(f"Debugging query: {sql_query}")
        print("-" * 50)
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Format the query with namespace and database
    full_sql = f"USE NS {SURREAL_NS} DB {SURREAL_DB};\n{sql_query}"
    
    if verbose:
        print(f"Full SQL sent to SurrealDB:")
        print(full_sql)
        print("-" * 50)
    
    try:
        response = requests.post(
            SURREAL_URL,
            headers=headers,
            auth=(SURREAL_USER, SURREAL_PASS),
            data=full_sql,
            timeout=30
        )
        
        if verbose:
            print(f"HTTP Status Code: {response.status_code}")
            print(f"Response Headers: {dict(response.headers)}")
            print("-" * 50)
        
        # Try to parse JSON response
        try:
            data = response.json()
            if verbose:
                print("Parsed JSON Response:")
                print(json.dumps(data, indent=2))
            else:
                print(json.dumps(data, indent=2))
        except json.JSONDecodeError:
            if verbose:
                print("Raw Response (not JSON):")
                print(response.text)
            else:
                print(response.text)
            return None
        
        return data
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {e}"
        if verbose:
            print(error_msg)
        else:
            print(error_msg)
        return None
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        if verbose:
            print(error_msg)
        else:
            print(error_msg)
        return None


def main():
    """Main function to run debug checks"""
    if len(sys.argv) < 2:
        print("Usage: python debug_surreal_response.py '<SQL_QUERY>'")
        print("Example: python debug_surreal_response.py 'SELECT * FROM event LIMIT 5'")
        return 1
    
    query = sys.argv[1]
    
    print("Strata SurrealDB Response Debugger")
    print("="*50)
    
    result = debug_query(query)
    
    if result is not None:
        print("\n" + "="*50)
        print("DEBUG COMPLETE")
        return 0
    else:
        print("\n" + "="*50)
        print("DEBUG FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())