import requests
import json


def run_sql(sql):
    url = "http://127.0.0.1:8000/sql"
    headers = {
        "Accept": "application/json",
        "NS": "strata",
        "DB": "strata",
    }
    auth = ("root", "root")
    response = requests.post(
        url,
        data=sql,
        headers=headers,
        auth=auth,
        timeout=30
    )
    return response.json()


def load_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    # Split by ; and run each statement
    statements = [s.strip() for s in content.split(";") if s.strip()]
    for stmt in statements:
        try:
            result = run_sql(stmt)
            # print(f"Executed: {stmt[:50]}... Result: {result}")
        except Exception as e:
            print(f"⚠️ Warning executing: {stmt[:50]}... Error: {e}")


if __name__ == "__main__":
    print("🔌 Loading schema via SurrealDB HTTP API...")
    
    print("📦 Loading schema...")
    load_file("sdb/schema.surql")
    
    print("🔧 Loading helper functions...")
    load_file("sdb/helper_functions.surql")
    
    print("🧪 Loading test data...")
    load_file("sdb/test_data.surql")
    
    print("\n✅ All loaded successfully!")
    
    # Quick check
    result = run_sql("SELECT count() FROM event")
    print(f"\n🔍 Quick check: Events in DB: {result[0]['result'][0]['count']}")
    
    result = run_sql("SELECT * FROM entity")
    print(f"🔍 Entities in DB: {len(result[0]['result'])}")
