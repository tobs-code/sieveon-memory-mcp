"""
Benchmark: memory_store pipeline
Measures:
  1. Embedding model loading time
  2. Embedding generation time (per round)
  3. SurrealDB store time (per round, raw CREATE)
"""

import hashlib
import json
import os
import statistics
import time
import sys

import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

SURREAL_URL = os.getenv("SURREALDB_URL", "http://127.0.0.1:8000/sql")
SURREAL_AUTH = (os.getenv("SURREALDB_USER", "root"), os.getenv("SURREALDB_PASS", "root"))
SURREAL_NS = os.getenv("SURREALDB_NS", "sieveon")
SURREAL_DB = os.getenv("SURREALDB_DB", "sieveon")

ROUNDS = 10
TEXTS = [
    "Ergonomic Bamboo Desk Organizer with USB Charging Station for Home Office Workspace Setup and Cable Management",
    "Premium Turkish Cotton Bath Towel Set 6 Piece 700GSM Quick Dry Absorbent Heavy Duty Luxury Towels for Bathroom",
    "Professional Stainless Steel Cocktail Shaker Set 18oz Boston Shaker with Jigger Strainer Muddler for Bartending",
    "Organic Matcha Green Tea Powder Ceremonial Grade Premium Stone Ground Japanese Matcha 100g Resealable Pouch",
    "Adjustable Laptop Stand for Desk Ergonomic Aluminum Ventilated Notebook Riser Compatible with MacBook Dell HP",
    "Wireless Bluetooth Earbuds Sport IPX7 Waterproof 48H Playtime Premium Sound Noise Cancelling Earphones for Gym",
    "Memory Foam Bed Pillow Queen Size 2 Pack Cooling Bamboo Shredded Twin Pack CertiPUR Certified Adjustable Loft",
    "Cast Iron Dutch Oven 6 Quart Enameled Heavy Duty Pot with Lid Self Basting Slow Cooker Bread Pot for Kitchen",
    "Plant Protein Powder Vanilla 2lb Vegan Gluten Free Non GMO 25g Plant Based Protein Shake with Greens Probiotics",
    "Fleece Throw Blanket Super Soft Cozy Lightweight Microfiber Travel Blanket for Couch Sofa Bed Airplane 50x70",
]


def _query_surreal(sql: str) -> dict:
    client = httpx.Client(timeout=30.0)
    headers = {"Accept": "application/json", "Content-Type": "text/plain"}
    body = f"USE NS {SURREAL_NS} DB {SURREAL_DB};\n{sql}"
    response = client.post(SURREAL_URL, content=body, headers=headers, auth=SURREAL_AUTH)
    client.close()
    return response.json()


def _escape_surrealql(value: str) -> str:
    value = value.replace("\\", "\\\\")
    value = value.replace("'", "\\'")
    value = value.replace("}", "\\}")
    value = value.replace("\n", "\\n")
    value = value.replace("\r", "\\r")
    value = value.replace("\t", "\\t")
    return value


def _hash_content(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cleanup_events(event_ids: list[str]):
    for eid in event_ids:
        try:
            _query_surreal(f"DELETE {eid};")
        except Exception:
            pass


def main():
    print("=" * 65)
    print("  Benchmark: Memory Store Pipeline")
    print("=" * 65)

    # ── Phase 1: Model Loading ──────────────────────────────────────
    print(f"\n{'─' * 65}")
    print("  Phase 1: Embedding Model Loading")
    print(f"{'─' * 65}")

    t0 = time.time()
    from src.extraction.embedding_service import get_embedding_service
    service = get_embedding_service()
    model_load_time = time.time() - t0
    print(f"  Model         : {service.model_name}")
    print(f"  Dimension     : {service.dimension}")
    print(f"  Load time     : {model_load_time:.3f}s")

    # Warm-up embed (first call may compile graph)
    print(f"\n  Warming up model (first embed)...")
    t0 = time.time()
    service.embed_for_storage("warm up sentence.")
    warmup_time = time.time() - t0
    print(f"  Warm-up embed : {warmup_time:.3f}s")

    # ── Phase 2: Per-Round Benchmark ─────────────────────────────────
    embed_times = []
    store_times = []
    total_times = []
    created_ids = []

    print(f"\n{'─' * 65}")
    print(f"  Phase 2: Benchmarking ({ROUNDS} rounds)")
    print(f"{'─' * 65}")

    for i in range(ROUNDS):
        # Unique content to avoid dedup
        uid = f"BENCH-{i}-{time.time_ns()}"
        text = TEXTS[i % len(TEXTS)] + f" [uid:{uid}]"
        print(f"\n  Round {i+1:2d}/{ROUNDS} | content_len={len(text)}")

        # 2a. Embedding generation
        t0 = time.time()
        embedding = service.embed_for_storage(text)
        te = time.time() - t0
        embed_times.append(te)

        # 2b. SurrealDB store
        content_hash = _hash_content(text)
        text_escaped = _escape_surrealql(text)
        emb_str = "[" + ",".join(str(v) for v in embedding) + "]"
        sql = f"""
        CREATE event SET
            content = '{text_escaped}',
            content_hash = '{content_hash}',
            source = 'benchmark',
            embedding = {emb_str};
        """

        t0 = time.time()
        result = _query_surreal(sql)
        ts = time.time() - t0
        store_times.append(ts)

        # Extract event ID
        event_id = None
        if isinstance(result, list):
            for item in result:
                if isinstance(item, dict) and item.get("status") == "OK":
                    r = item.get("result", [])
                    if isinstance(r, list) and len(r) > 0 and isinstance(r[0], dict):
                        event_id = r[0].get("id")
                        break
        if event_id:
            created_ids.append(event_id)

        total = te + ts
        total_times.append(total)

        print(f"    Embedding   : {te:.4f}s")
        print(f"    Store       : {ts:.4f}s")
        print(f"    Total       : {total:.4f}s")
        print(f"    Event ID    : {event_id or 'ERROR'}")

        # Brief pause between rounds to avoid overwhelming SurrealDB
        if i < ROUNDS - 1:
            time.sleep(0.5)

    # ── Phase 3: Statistics ──────────────────────────────────────────
    print(f"\n{'═' * 65}")
    print("  Results Summary")
    print(f"{'═' * 65}")
    print(f"  Model load time         : {model_load_time:.3f}s")
    print(f"  Model warm-up embed     : {warmup_time:.3f}s")
    print(f"  Embedding dimension     : {service.dimension}")
    print()
    print(f"  Embedding Generation:")
    print(f"    Rounds                : {len(embed_times)}")
    print(f"    Total time            : {sum(embed_times):.3f}s")
    print(f"    Min                   : {min(embed_times):.4f}s")
    print(f"    Max                   : {max(embed_times):.4f}s")
    print(f"    Avg                   : {statistics.mean(embed_times):.4f}s")
    if len(embed_times) > 1:
        print(f"    Stddev                : {statistics.stdev(embed_times):.4f}s")
    print()
    print(f"  SurrealDB Store:")
    print(f"    Rounds                : {len(store_times)}")
    print(f"    Total time            : {sum(store_times):.3f}s")
    print(f"    Min                   : {min(store_times):.4f}s")
    print(f"    Max                   : {max(store_times):.4f}s")
    print(f"    Avg                   : {statistics.mean(store_times):.4f}s")
    if len(store_times) > 1:
        print(f"    Stddev                : {statistics.stdev(store_times):.4f}s")
    print()
    print(f"  Combined (Embed + Store):")
    print(f"    Total time            : {sum(total_times):.3f}s")
    print(f"    Min                   : {min(total_times):.4f}s")
    print(f"    Max                   : {max(total_times):.4f}s")
    print(f"    Avg                   : {statistics.mean(total_times):.4f}s")
    if len(total_times) > 1:
        print(f"    Stddev                : {statistics.stdev(total_times):.4f}s")

    # ── Cleanup ──────────────────────────────────────────────────────
    if created_ids:
        print(f"\n  Cleaning up {len(created_ids)} benchmark events...")
        _cleanup_events(created_ids)
        print("  Done.")

    print(f"\n{'═' * 65}")
    print("  Benchmark complete.")
    print(f"{'═' * 65}")


if __name__ == "__main__":
    main()
