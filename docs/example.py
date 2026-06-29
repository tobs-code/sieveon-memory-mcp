"""
Beispiel: SurrealDB 3 mit Python
Voraussetzung: uv add surrealdb
"""

import asyncio
from surrealdb import AsyncSurreal


async def main():
    print("Verbinde mit SurrealDB...")
    
    # Verbindung herstellen
    db = AsyncSurreal()
    await db.connect("ws://127.0.0.1:8000/rpc")
    await db.signin({"user": "root", "pass": "root"})
    await db.use("myapp", "myapp")
    
    print("✅ Verbindung erfolgreich!")
    print()
    
    # ========================================
    # 1. Daten erstellen
    # ========================================
    print("1. Erstelle einen neuen Benutzer...")
    new_user = await db.create("person", {
        "name": "Dave Wilson",
        "email": "dave@example.com",
        "age": 25
    })
    print(f"   Erstellt: {new_user}")
    print()
    
    # ========================================
    # 2. Daten abfragen
    # ========================================
    print("2. Alle Benutzer abfragen...")
    users = await db.select("user")
    for user in users:
        print(f"   - {user['name']} ({user['email']})")
    print()
    
    # ========================================
    # 3. Spezifische Abfrage
    # ========================================
    print("3. Abfrage: Benutzer über 18...")
    result = await db.query("SELECT * FROM user WHERE age > 18")
    for user in result[0]["result"]:
        print(f"   - {user['name']} (Alter: {user['age']}, Kann fahren: {user['can_drive']})")
    print()
    
    # ========================================
    # 4. Daten aktualisieren
    # ========================================
    print("4. Aktualisiere einen Benutzer...")
    updated = await db.update("user:bob", {
        "age": 18
    })
    print(f"   Aktualisiert: {updated['name']} ist jetzt {updated['age']} Jahre alt")
    print()
    
    # ========================================
    # 5. Graph-Abfrage
    # ========================================
    print("5. Graph-Abfrage: Wen kennt Alice?")
    graph_result = await db.query("""
        SELECT ->knows->person.* AS friends FROM user:alice
    """)
    friends = graph_result[0]["result"][0]["friends"]
    for friend in friends:
        print(f"   - Alice kennt: {friend['name']}")
    print()
    
    # ========================================
    # 6. Komplexe Abfrage mit FETCH
    # ========================================
    print("6. Artikel mit Autoreninformationen...")
    articles = await db.query("""
        SELECT title, author.name AS author_name, tags 
        FROM article 
        FETCH author
    """)
    for article in articles[0]["result"]:
        print(f"   - {article['title']} von {article['author_name']}")
        print(f"     Tags: {', '.join(article['tags'])}")
    print()
    
    print("✅ Fertig!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Fehler: {e}")
        print()
        print("Stelle sicher, dass SurrealDB läuft:")
        print("  docker-compose up -d")
