import requests
import time


def run_single_sql(stmt):
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


def load_file_step_by_step(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    # Split by ;
    statements = [s.strip() for s in content.split(";") if s.strip()]
    for i, stmt in enumerate(statements):
        print(f"   [{i+1}/{len(statements)}: {stmt[:100]}...", end=" ", flush=True)
        try:
            start = time.time()
            result = run_single_sql(stmt)
            elapsed = time.time() - start
            print(f"✅ OK ({elapsed:.2f}s)")
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("=== Loading schema step by step...")
    print("\n📦 schema.surql:")
    load_file_step_by_step("sdb/schema.surql")
    print("\n🔧 helper_functions.surql:")
    load_file_step_by_step("sdb/helper_functions.surql")
    print("\n🧪 test_data.surql:")
    load_file_step_by_step("sdb/test_data.surql")
    print("\n✅ Done!")
