#!/usr/bin/env python3
"""
Prosty test współbieżnego dostępu do bazy danych SQLite z WAL mode
"""

import sqlite3
import threading
import time
from pathlib import Path

def create_test_db(db_path):
    """Tworzy prostą bazę testową z WAL mode"""
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
    cursor = conn.cursor()

    # Włącz WAL mode
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")

    # Prosta tabela testowa
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER,
            message TEXT,
            timestamp INTEGER
        )
    """)

    conn.commit()

    # Sprawdź tryb WAL
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]

    conn.close()
    return mode

def writer_worker(db_path, thread_id, num_writes, results):
    """Wątek zapisujący do bazy"""
    errors = []
    writes = 0

    try:
        conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
        cursor = conn.cursor()

        for i in range(num_writes):
            try:
                cursor.execute(
                    "INSERT INTO test_messages (thread_id, message, timestamp) VALUES (?, ?, ?)",
                    (thread_id, f"Message {i} from thread {thread_id}", int(time.time()))
                )
                conn.commit()
                writes += 1
                time.sleep(0.001)  # Małe opóźnienie
            except sqlite3.OperationalError as e:
                errors.append(str(e))

        conn.close()

    except Exception as e:
        errors.append(f"Fatal error: {str(e)}")

    results[thread_id] = {
        'writes': writes,
        'errors': errors
    }

def reader_worker(db_path, thread_id, duration, results):
    """Wątek czytający z bazy"""
    errors = []
    reads = 0

    try:
        conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
        cursor = conn.cursor()

        start_time = time.time()
        while time.time() - start_time < duration:
            try:
                cursor.execute("SELECT COUNT(*) FROM test_messages")
                count = cursor.fetchone()[0]
                reads += 1
                time.sleep(0.005)  # Małe opóźnienie
            except sqlite3.OperationalError as e:
                errors.append(str(e))

        conn.close()

    except Exception as e:
        errors.append(f"Fatal error: {str(e)}")

    results[f'reader_{thread_id}'] = {
        'reads': reads,
        'errors': errors
    }

def test_concurrent_access():
    """Test współbieżnego dostępu"""
    print("=" * 70)
    print("Test współbieżnego dostępu do bazy danych SQLite z WAL mode")
    print("=" * 70)

    db_path = "test_simple_concurrent.db"

    # Usuń starą bazę
    for suffix in ['', '-wal', '-shm']:
        test_file = Path(f"{db_path}{suffix}")
        if test_file.exists():
            test_file.unlink()

    # Stwórz bazę z WAL mode
    print("\n1. Tworzenie bazy danych z WAL mode...")
    mode = create_test_db(db_path)
    print(f"   ✅ Baza utworzona, tryb: {mode}")

    if mode.upper() != 'WAL':
        print(f"   ❌ BŁĄD: Oczekiwano WAL, otrzymano {mode}")
        return False

    # Sprawdź pliki WAL
    print("\n2. Sprawdzanie plików WAL...")
    for suffix in ['-wal', '-shm']:
        wal_file = Path(f"{db_path}{suffix}")
        if wal_file.exists():
            print(f"   ✅ Plik {wal_file.name} istnieje ({wal_file.stat().st_size} bytes)")
        else:
            print(f"   ⚠️  Plik {wal_file.name} nie istnieje (może być pusty)")

    # Test współbieżności
    print("\n3. Test współbieżnego zapisu i odczytu...")
    print("   Uruchamiam 3 wątki piszące (po 100 wpisów) i 2 wątki czytające (5s)...")

    results = {}
    threads = []

    # 3 wątki piszące
    for i in range(3):
        t = threading.Thread(target=writer_worker, args=(db_path, i, 100, results))
        threads.append(t)
        t.start()

    # 2 wątki czytające
    for i in range(2):
        t = threading.Thread(target=reader_worker, args=(db_path, i, 5, results))
        threads.append(t)
        t.start()

    # Czekaj na wszystkie wątki
    for t in threads:
        t.join()

    # Analiza wyników
    print("\n4. Analiza wyników...")

    total_writes = 0
    total_reads = 0
    all_errors = []

    for key, data in results.items():
        if 'writes' in data:
            writes = data['writes']
            total_writes += writes
            errors = len(data['errors'])
            status = "✅" if errors == 0 else "❌"
            print(f"   {status} Writer thread {key}: {writes} zapisów, {errors} błędów")
            all_errors.extend(data['errors'])
        else:
            reads = data['reads']
            total_reads += reads
            errors = len(data['errors'])
            status = "✅" if errors == 0 else "❌"
            print(f"   {status} Reader thread {key}: {reads} odczytów, {errors} błędów")
            all_errors.extend(data['errors'])

    # Sprawdź końcową liczbę rekordów
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM test_messages")
    final_count = cursor.fetchone()[0]
    conn.close()

    print(f"\n5. Podsumowanie:")
    print(f"   Całkowita liczba zapisów wykonanych: {total_writes}")
    print(f"   Całkowita liczba odczytów wykonanych: {total_reads}")
    print(f"   Końcowa liczba rekordów w bazie: {final_count}")
    print(f"   Liczba błędów: {len(all_errors)}")

    if all_errors:
        print("\n   ⚠️  Wykryte błędy:")
        for error in set(all_errors)[:5]:  # Pokaż tylko unikalne błędy
            print(f"      - {error}")

    # Wynik testu
    print("\n" + "=" * 70)

    expected_writes = 300  # 3 threads × 100 writes
    success = (
        final_count == expected_writes and
        len(all_errors) == 0 and
        total_reads > 0
    )

    if success:
        print("✅ SUKCES: Baza danych obsługuje współbieżny zapis i odczyt!")
        print(f"   - Wszystkie {expected_writes} wiadomości zostały zapisane")
        print(f"   - Wykonano {total_reads} odczytów podczas zapisu")
        print("   - Żadnych błędów blokowania (database locked)")
        print("   - Tryb WAL działa poprawnie")
    else:
        print("❌ BŁĄD: Test nie przeszedł")
        if final_count != expected_writes:
            print(f"   - Oczekiwano {expected_writes} rekordów, znaleziono {final_count}")
        if len(all_errors) > 0:
            print(f"   - Wystąpiły błędy: {len(all_errors)}")
        if total_reads == 0:
            print("   - Nie wykonano żadnych odczytów")

    print("=" * 70)

    # Czyszczenie
    print("\n6. Czyszczenie...")
    for suffix in ['', '-wal', '-shm']:
        test_file = Path(f"{db_path}{suffix}")
        if test_file.exists():
            test_file.unlink()
            print(f"   Usunięto: {test_file.name}")

    return success

if __name__ == "__main__":
    success = test_concurrent_access()
    exit(0 if success else 1)
