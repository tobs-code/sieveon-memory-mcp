import time
import requests

def profile_query(label: str, sql: str, ns: str = "strata", db: str = "strata"):
    url = "http://127.0.0.1:8000/sql"
    auth = ("root", "root")
    headers = {
        "Accept": "application/json",
        "NS": ns,
        "DB": db,
    }
    full_sql = f"USE NS {ns} DB {db};\n{sql}"

    t0 = time.time()
    try:
        response = requests.post(url, data=full_sql, headers=headers, auth=auth, timeout=60)
        t1 = time.time()
        status = response.status_code
        print(f"✅ {label:30} | {t1-t0:6.3f}s | Status: {status}")
        return t1-t0, response
    except Exception as e:
        t1 = time.time()
        print(f"❌ {label:30} | {t1-t0:6.3f}s | Error: {e}")
        return t1-t0, None

print("=== SurrealDB Performance Profiling ===\n")

total_time = 0.0

# 1. Basic Connection Test
label = "Basic connection (no query)"
t, _ = profile_query(label, "RETURN 1;")
total_time += t

# 2. Small SELECT
label = "SELECT * FROM event LIMIT 1"
t, _ = profile_query(label, "SELECT * FROM event LIMIT 1;")
total_time += t

# 3. CREATE Event
label = "CREATE 1 event"
t, _ = profile_query(label, "CREATE event SET content = 'test', source = 'profile';")
total_time += t

# 4. CREATE Gate Log
label = "CREATE 1 gate_log"
t, _ = profile_query(label, "CREATE gate_log SET content_hash = 'test', text_score = 0.5, novelty = 0.5, gate_score = 0.5, decision = 'test';")
total_time += t

print(f"\n{'='*60}")
print(f"Total profiling time: {total_time:.3f}s")
