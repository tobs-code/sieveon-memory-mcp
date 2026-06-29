import requests


def debug_step1_test_connection():
    print("Step 1: Testing basic HTTP connection to SurrealDB...")
    try:
        response = requests.get("http://127.0.0.1:8000/status")
        print(f"✅ Status: {response.status_code}")
        print(f"   Response: {response.text}")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False
    return True


def debug_step2_test_query():
    print("\nStep 2: Testing a simple SQL query...")
    url = "http://127.0.0.1:8000/sql"
    sql = "RETURN 123;"
    headers = {
        "Accept": "application/json",
        "NS": "test",
        "DB": "test",
    }
    auth = ("root", "root")
    try:
        response = requests.post(url, data=sql, headers=headers, auth=auth)
        print(f"✅ Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"❌ Query failed: {e}")
        return False
    return True


if __name__ == "__main__":
    print("=== SurrealDB Debug Script ===\n")
    if debug_step1_test_connection():
        debug_step2_test_query()
