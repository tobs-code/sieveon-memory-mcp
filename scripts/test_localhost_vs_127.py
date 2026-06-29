import time
import requests

def test_url(label, url):
    headers = {"Accept": "application/json"}
    sql = "USE NS agent_memory DB agent_memory;\nRETURN 1;"
    auth = ("root", "root")
    t0 = time.time()
    try:
        response = requests.post(url, data=sql, headers=headers, auth=auth, timeout=30)
        t1 = time.time()
        print(f"✅ {label:15} | {t1-t0:.3f}s | Status: {response.status_code}")
    except Exception as e:
        t1 = time.time()
        print(f"❌ {label:15} | {t1-t0:.3f}s | Error: {e}")


def test_connection():
    sql = "USE NS strata DB strata;\nRETURN 1;"  # Updated from agent_memory to strata
    response = requests.post(
        "http://127.0.0.1:8000/sql",
        data=sql,
        headers={
            "NS": "strata",  # Updated from agent_memory to strata
            "DB": "strata",  # Updated from agent_memory to strata
            "Accept": "application/json"
        },
        auth=("root", "root"),
        timeout=5
    )
    t0 = time.time()
    try:
        t1 = time.time()
        print(f"✅ Connection | {t1-t0:.3f}s | Status: {response.status_code}")
    except Exception as e:
        t1 = time.time()
        print(f"❌ Connection | {t1-t0:.3f}s | Error: {e}")


print("=== Testing localhost vs 127.0.0.1 ===\n")
test_url("localhost", "http://localhost:8000/sql")
test_url("127.0.0.1", "http://127.0.0.1:8000/sql")
