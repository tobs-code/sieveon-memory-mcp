import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

SURREAL_URL = os.getenv("SURREALDB_URL", "http://127.0.0.1:8000/sql")
SURREAL_AUTH = (os.getenv("SURREALDB_USER", "root"), os.getenv("SURREALDB_PASS", "root"))
SURREAL_NS = os.getenv("SURREALDB_NS", "strata")
SURREAL_DB = os.getenv("SURREALDB_DB", "strata")

def check_embeddings():
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    sql = f"USE NS {SURREAL_NS} DB {SURREAL_DB};\nSELECT id, content, count(embedding) as emb_len FROM event WHERE embedding IS NOT NONE;"
    
    response = requests.post(
        SURREAL_URL,
        data=sql,
        headers=headers,
        auth=SURREAL_AUTH,
        timeout=30,
    )
    results = response.json()
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    check_embeddings()
