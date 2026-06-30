import asyncio
import os
import httpx
import json

SURREAL_URL = os.getenv("SURREALDB_URL", "http://127.0.0.1:8000/sql")
SURREAL_AUTH = (os.getenv("SURREALDB_USER", "root"), os.getenv("SURREALDB_PASS", "root"))
SURREAL_NS = os.getenv("SURREALDB_NS", "strata")
SURREAL_DB = os.getenv("SURREALDB_DB", "strata")

async def _query_surreal(sql: str):
    headers = {
        "Accept": "application/json",
        "Content-Type": "text/plain",
    }
    full_sql = f"USE NS {SURREAL_NS} DB {SURREAL_DB};\n{sql}"
    
    async with httpx.AsyncClient() as client:
        print(f"Executing SQL: {sql[:50]}...")
        response = await client.post(
            SURREAL_URL,
            content=full_sql,
            headers=headers,
            auth=SURREAL_AUTH,
            timeout=10.0,
        )
        print(f"Status Code: {response.status_code}")
        if response.status_code >= 400:
            print(f"Error Response: {response.text}")
            return None
        return response.json()

async def test_schema_check():
    print("Testing INFO FOR DB...")
    result = await _query_surreal("INFO FOR DB;")
    if not result:
        print("Failed to get response")
        return
    
    # In SurrealDB, index 0 is USE NS/DB, index 1 is INFO FOR DB
    if len(result) < 2:
        print(f"Unexpected result length: {len(result)}")
        return
    
    info_item = result[1]
    if info_item.get("status") == "OK":
        db_info = info_item.get("result", {})
        print(f"Tables found: {list(db_info.get('tables', {}).keys())}")
    else:
        print(f"INFO FOR DB failed: {info_item}")

if __name__ == "__main__":
    asyncio.run(test_schema_check())
