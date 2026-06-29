# SurrealDB Python SDK Dokumentation (Stand Juni 2026)

## Quellen
- Offizielle Docs: https://surrealdb.com/docs/sdk/python
- GitHub: https://github.com/surrealdb/surrealdb.py

## Installation
```bash
pip install surrealdb
```
Erfordert Python 3.10+

## Quickstart
```python
# Import the Surreal class
from surrealdb import Surreal

# Using a context manager to automatically connect and disconnect
with Surreal("ws://localhost:8000/rpc") as db:
    db.signin({"username": 'root', "password": 'root'})
    db.use("namespace_test", "database_test")

    # Create a record in the person table
    db.create(
        "person",
        {
            "user": "me",
            "password": "safe",
            "marketing": True,
            "tags": ["python", "documentation"],
        },
    )

    # Read all the records in the table
    print(db.select("person"))
```

## Connection Methods
- .connect()
- .close()
- .use(namespace, database)
- .signin(credentials)
- .query(sql, **kwargs)
