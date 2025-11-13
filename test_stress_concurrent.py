#!/usr/bin/env python3
"""
Stres test współbieżnego dostępu do bazy danych
Symuluje bardzo intensywne obciążenie z wieloma wątkami
"""

import sqlite3
import threading
import time
import random
from pathlib import Path

def create_test_db(db_path):
    """Tworzy bazę testową z WAL mode"""
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
    cursor = conn.cursor()

    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
    cursor.execute("PRAGMA temp_store=MEMORY")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER,
            data TEXT,
            timestamp INTEGER
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_thread ON messages(thread_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp)
    """)

    conn.commit()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    conn.close()
    return mode

def aggressive_writer(db_path, thread_id, num_ops, results):
    """Wątek agresywnie zapisujący"""
    errors = []
    writes = 0
    lock_errors = 0

    try:
        conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
        cursor = conn.cursor()

        for i in range(num_ops):
            try:
                # Losowy zapis - czasem pojedynczy, czasem batch
                if random.random() < 0.3:  # 30% batch writes
                    batch_size = random.randint(5, 10)
                    for _ in range(batch_size):
                        cursor.execute(
                            "INSERT INTO messages (thread_id, data, timestamp) VALUES (?, ?, ?)",
                            (thread_id, f"Data-{i}-{writes}", int(time.time() * 1000))
                        )
                    conn.commit()
                    writes += batch_size
                else:
                    cursor.execute(
                        "INSERT INTO messages (thread_id, data, timestamp) VALUES (?, ?, ?)",
                        (thread_id, f"Data-{i}-{writes}", int(time.time() * 1000))
                    )
                    conn.commit()
                    writes += 1

                # Bez opóźnienia - maksymalne obciążenie
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower():
                    lock_errors += 1
                errors.append(str(e))

        conn.close()

    except Exception as e:
        errors.append(f"Fatal: {str(e)}")

    results[f'writer_{thread_id}'] = {
        'writes': writes,
        'errors': len(errors),
        'lock_errors': lock_errors
    }

def aggressive_reader(db_path, thread_id, duration, results):
    """Wątek agresywnie czytający"""
    errors = []
    reads = 0
    lock_errors = 0

    try:
        conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
        cursor = conn.cursor()

        start_time = time.time()
        while time.time() - start_time < duration:
            try:
                # Różne typy odczytów
                op = random.randint(1, 4)

                if op == 1:
                    cursor.execute("SELECT COUNT(*) FROM messages")
                    cursor.fetchone()
                elif op == 2:
                    cursor.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 10")
                    cursor.fetchall()
                elif op == 3:
                    cursor.execute("SELECT thread_id, COUNT(*) FROM messages GROUP BY thread_id")
                    cursor.fetchall()
                else:
                    cursor.execute("SELECT * FROM messages WHERE timestamp > ?", (int(time.time() * 1000) - 10000,))
                    cursor.fetchall()

                reads += 1
                # Bez opóźnienia - maksymalne obciążenie

            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower():
                    lock_errors += 1
                errors.append(str(e))

        conn.close()

    except Exception as e:
        errors.append(f"Fatal: {str(e)}")

    results[f'reader_{thread_id}'] = {
        'reads': reads,
        'errors': len(errors),
        'lock_errors': lock_errors
    }

def mixed_worker(db_path, thread_id, duration, results):
    """Wątek wykonujący mieszane operacje (zapis + odczyt)"""
    errors = []
    writes = 0
    reads = 0
    lock_errors = 0

    try:
        conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
        cursor = conn.cursor()

        start_time = time.time()
        op_count = 0

        while time.time() - start_time < duration:
            try:
                # 40% zapis, 60% odczyt
                if random.random() < 0.4:
                    cursor.execute(
                        "INSERT INTO messages (thread_id, data, timestamp) VALUES (?, ?, ?)",
                        (thread_id, f"Mixed-{op_count}", int(time.time() * 1000))
                    )
                    conn.commit()
                    writes += 1
                else:
                    cursor.execute("SELECT COUNT(*) FROM messages WHERE thread_id = ?", (thread_id,))
                    cursor.fetchone()
                    reads += 1

                op_count += 1

            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower():
                    lock_errors += 1
                errors.append(str(e))

        conn.close()

    except Exception as e:
        errors.append(f"Fatal: {str(e)}")

    results[f'mixed_{thread_id}'] = {
        'writes': writes,
        'reads': reads,
        'errors': len(errors),
        'lock_errors': lock_errors
    }

def stress_test():
    """Główny stres test"""
    print("=" * 70)
    print("STRES TEST: Intensywny współbieżny dostęp do bazy danych")
    print("=" * 70)

    db_path = "test_stress_concurrent.db"

    # Czyszczenie
    for suffix in ['', '-wal', '-shm']:
        test_file = Path(f"{db_path}{suffix}")
        if test_file.exists():
            test_file.unlink()

    # Stwórz bazę
    print("\n1. Tworzenie bazy danych...")
    mode = create_test_db(db_path)
    print(f"   ✅ Tryb: {mode}")

    # Konfiguracja testu
    NUM_WRITERS = 5
    NUM_READERS = 5
    NUM_MIXED = 3
    WRITES_PER_WRITER = 200
    TEST_DURATION = 10  # sekund

    print(f"\n2. Konfiguracja stres testu:")
    print(f"   - {NUM_WRITERS} wątków piszących (po {WRITES_PER_WRITER} operacji)")
    print(f"   - {NUM_READERS} wątków czytających ({TEST_DURATION}s)")
    print(f"   - {NUM_MIXED} wątków mieszanych ({TEST_DURATION}s)")
    print(f"   - Brak opóźnień między operacjami")
    print(f"   - Losowe batche zapisów")

    print("\n3. Uruchamianie testu...")
    start_time = time.time()

    results = {}
    threads = []

    # Uruchom wątki piszące
    for i in range(NUM_WRITERS):
        t = threading.Thread(target=aggressive_writer, args=(db_path, i, WRITES_PER_WRITER, results))
        threads.append(t)
        t.start()

    # Uruchom wątki czytające
    for i in range(NUM_READERS):
        t = threading.Thread(target=aggressive_reader, args=(db_path, i, TEST_DURATION, results))
        threads.append(t)
        t.start()

    # Uruchom wątki mieszane
    for i in range(NUM_MIXED):
        t = threading.Thread(target=mixed_worker, args=(db_path, i, TEST_DURATION, results))
        threads.append(t)
        t.start()

    # Czekaj
    for t in threads:
        t.join()

    elapsed = time.time() - start_time

    # Analiza
    print(f"\n4. Test zakończony w {elapsed:.2f}s")
    print("\n5. Wyniki szczegółowe:")

    total_writes = 0
    total_reads = 0
    total_errors = 0
    total_lock_errors = 0

    for key, data in sorted(results.items()):
        writes = data.get('writes', 0)
        reads = data.get('reads', 0)
        errors = data.get('errors', 0)
        lock_errors = data.get('lock_errors', 0)

        total_writes += writes
        total_reads += reads
        total_errors += errors
        total_lock_errors += lock_errors

        status = "✅" if errors == 0 else "⚠️"
        ops = f"{writes}w" if writes > 0 else ""
        ops += f"/{reads}r" if reads > 0 else ""
        ops += f" (ops: {ops})"

        print(f"   {status} {key:15} - zapisów: {writes:4}, odczytów: {reads:5}, błędów: {errors:2} (locked: {lock_errors})")

    # Finalna liczba rekordów
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM messages")
    final_count = cursor.fetchone()[0]
    conn.close()

    print(f"\n6. Podsumowanie globalne:")
    print(f"   Całkowita liczba zapisów:           {total_writes}")
    print(f"   Całkowita liczba odczytów:          {total_reads}")
    print(f"   Rekordów w bazie:                   {final_count}")
    print(f"   Błędy ogółem:                       {total_errors}")
    print(f"   Błędy blokowania (database locked): {total_lock_errors}")
    print(f"   Czas testu:                         {elapsed:.2f}s")
    print(f"   Operacje/sekundę:                   {(total_writes + total_reads) / elapsed:.1f}")

    # Weryfikacja
    print("\n" + "=" * 70)

    success = (
        total_lock_errors == 0 and
        final_count == total_writes and
        total_reads > 0
    )

    if success:
        print("✅✅✅ SUKCES: Baza przeszła stres test! ✅✅✅")
        print(f"\n   🎯 Wszystkie {total_writes} zapisów wykonane bez błędów")
        print(f"   🎯 Wykonano {total_reads} odczytów podczas intensywnego zapisu")
        print(f"   🎯 ZERO błędów blokowania bazy danych")
        print(f"   🎯 Wydajność: {(total_writes + total_reads) / elapsed:.1f} ops/s")
        print("\n   ✅ Baza danych MOŻE jednocześnie zapisywać i odczytywać dane")
        print("   ✅ Tryb WAL działa PERFEKCYJNIE")
    else:
        print("❌ BŁĄD: Test wykrył problemy")
        if total_lock_errors > 0:
            print(f"   ❌ Wykryto {total_lock_errors} błędów blokowania!")
        if final_count != total_writes:
            print(f"   ❌ Niezgodność rekordów: {final_count} != {total_writes}")

    print("=" * 70)

    # Czyszczenie
    print("\n7. Czyszczenie...")
    for suffix in ['', '-wal', '-shm']:
        test_file = Path(f"{db_path}{suffix}")
        if test_file.exists():
            size = test_file.stat().st_size
            test_file.unlink()
            print(f"   Usunięto: {test_file.name} ({size} bytes)")

    return success

if __name__ == "__main__":
    success = stress_test()
    exit(0 if success else 1)
