import requests


def run_sql_batch(statements):
    url = "http://127.0.0.1:8000/sql"
    auth = ("root", "root")
    sql = "USE NS strata DB strata;\n" + ";\n".join(statements) + ";"
    response = requests.post(url, data=sql, auth=auth, timeout=60)
    data = response.json()
    errors = []
    if isinstance(data, list):
        for i, item in enumerate(data):
            if item.get("status") == "ERR":
                errors.append(f"Statement {i}: {item.get('information') or item.get('result')}")
    return data, errors


def load_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("--") or stripped.startswith("//"):
            continue
        if "--" in stripped:
            stripped = stripped.split("--")[0].strip()
        if stripped:
            clean_lines.append(stripped)
    content_no_comments = " ".join(clean_lines)

    statements = []
    current = ""
    depth = 0
    for part in content_no_comments.split(";"):
        part = part.strip()
        if not part:
            continue
        current += part + ";"
        depth += part.count("{") - part.count("}")
        if depth <= 0:
            statements.append(current.strip())
            current = ""
    if current.strip():
        statements.append(current.strip())
    return statements


if __name__ == "__main__":
    print("=== Loading schema optimized...")
    
    # Load all statements
    all_statements = []
    for f in ["docs/schema.surql", "docs/helper_functions.surql", "docs/test_data.surql"]:
        stmts = load_file(f)
        all_statements.extend(stmts)
    
    # Execute in batches of 5
    batch_size = 5
    for i in range(0, len(all_statements), batch_size):
        batch = all_statements[i:i+batch_size]
        print(f"   Executing batch {i//batch_size +1}...", end=" ", flush=True)
        try:
            result, errors = run_sql_batch(batch)
            if errors:
                print(f"⚠️ Warnings: {errors}")
            else:
                print("✅ OK")
        except Exception as e:
            print(f"❌ Error: {e}")
            print(f"   Batch content: {batch}")
    
    print("\n✅ All loaded!")
    
    # Quick check
    check, errors = run_sql_batch(["SELECT count() FROM event", "SELECT count() FROM entity"])
    print(f"\n🔍 Quick check:")
    try:
        event_count = check[0]['result'][0]['count'] if check and check[0] and check[0].get('result') else 0
        entity_count = check[1]['result'][0]['count'] if check and len(check) > 1 and check[1] and check[1].get('result') else 0
        print(f"   Events: {event_count}")
        print(f"   Entities: {entity_count}")
    except Exception as e:
        print(f"   ⚠️ Could not retrieve counts: {e}")
