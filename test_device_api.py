#!/usr/bin/env python3
"""Test wydajności endpointu /api/device/<node_id>"""

import time
import sqlite3
from database import MeshtasticDatabase

# Test dla node_id 0x1327eb80
NODE_ID = "0x1327eb80"
DB_PATH = "data/mesh_scout.db"

def test_query_performance():
    """Testuje wydajność zapytania SQL"""
    print(f"\n=== Test wydajności dla {NODE_ID} ===\n")

    # Test 1: Bezpośrednie zapytanie SQL
    print("1. Bezpośrednie zapytanie SQL:")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    start = time.time()
    cursor.execute("SELECT * FROM devices WHERE node_id = ?", (NODE_ID,))
    row = cursor.fetchone()
    end = time.time()

    print(f"   Czas: {(end-start)*1000:.2f} ms")
    if row:
        print(f"   Znaleziono urządzenie: {dict(row).get('user_longname', 'N/A')}")
    else:
        print(f"   Urządzenie nie znalezione!")

    conn.close()

    # Test 2: Przez klasę MeshtasticDatabase
    print("\n2. Przez klasę MeshtasticDatabase:")
    db = MeshtasticDatabase(DB_PATH)

    start = time.time()
    device = db.get_device(NODE_ID)
    end = time.time()

    print(f"   Czas: {(end-start)*1000:.2f} ms")
    if device:
        print(f"   Znaleziono urządzenie: {device.get('user_longname', 'N/A')}")
    else:
        print(f"   Urządzenie nie znalezione!")

    db.close()

    # Test 3: Plan zapytania (EXPLAIN QUERY PLAN)
    print("\n3. Plan wykonania zapytania:")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("EXPLAIN QUERY PLAN SELECT * FROM devices WHERE node_id = ?", (NODE_ID,))
    for row in cursor.fetchall():
        print(f"   {row}")

    conn.close()

    # Test 4: Statystyki bazy
    print("\n4. Statystyki bazy danych:")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM devices")
    total_devices = cursor.fetchone()[0]
    print(f"   Łączna liczba urządzeń: {total_devices}")

    cursor.execute("SELECT COUNT(*) as indexed FROM sqlite_master WHERE type='index' AND tbl_name='devices'")
    total_indexes = cursor.fetchone()[0]
    print(f"   Liczba indeksów na tabeli devices: {total_indexes}")

    # Sprawdź rozmiar bazy
    cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
    db_size = cursor.fetchone()[0]
    print(f"   Rozmiar bazy danych: {db_size / (1024*1024):.2f} MB")

    conn.close()

    print("\n" + "="*50)

if __name__ == "__main__":
    test_query_performance()
