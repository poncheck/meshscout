#!/usr/bin/env python3
"""
Test współbieżnego dostępu do bazy danych
Sprawdza czy WAL mode działa poprawnie
"""

import sqlite3
import time
import threading
from pathlib import Path
from database import MeshtasticDatabase

def test_wal_mode():
    """Sprawdza czy baza działa w trybie WAL"""
    print("🔍 Test 1: Sprawdzanie trybu WAL...")
    
    db = MeshtasticDatabase("test_concurrent.db")
    cursor = db.conn.cursor()
    
    # Sprawdź tryb journal
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    
    if mode.upper() == 'WAL':
        print("✅ Baza działa w trybie WAL")
        return True
    else:
        print(f"❌ Baza działa w trybie {mode} (powinno być WAL)")
        return False

def writer_thread(thread_id, num_writes):
    """Wątek zapisujący do bazy"""
    db = MeshtasticDatabase("test_concurrent.db")
    
    for i in range(num_writes):
        message = {
            'channel_id': f'test-channel-{thread_id}',
            'gateway_id': f'gateway-{thread_id}',
            'packet': {
                'from': f'0xtest{thread_id}',
                'to': '0xffffffff',
                'packet_id': thread_id * 1000 + i,
                'rx_time': int(time.time()),
                'hop_limit': 3,
                'decoded_data': {
                    'portnum_name': 'TEXT_MESSAGE_APP',
                    'text': f'Test message {i} from thread {thread_id}'
                }
            }
        }
        
        db.save_message(message, f'test/topic/{thread_id}')
        time.sleep(0.01)  # Krótkie opóźnienie między zapisami
    
    db.close()
    print(f"✅ Writer thread {thread_id} zakończył {num_writes} zapisów")

def reader_thread(thread_id, duration):
    """Wątek czytający z bazy"""
    db = MeshtasticDatabase("test_concurrent.db")
    start_time = time.time()
    read_count = 0
    
    while time.time() - start_time < duration:
        stats = db.get_statistics()
        read_count += 1
        time.sleep(0.05)
    
    db.close()
    print(f"✅ Reader thread {thread_id} wykonał {read_count} odczytów w {duration}s")

def test_concurrent_access():
    """Test równoczesnego zapisu i odczytu"""
    print("\n🔍 Test 2: Współbieżny zapis i odczyt...")
    
    # Usuń starą bazę testową
    test_db = Path("test_concurrent.db")
    if test_db.exists():
        test_db.unlink()
    for suffix in ['-wal', '-shm']:
        wal_file = Path(f"test_concurrent.db{suffix}")
        if wal_file.exists():
            wal_file.unlink()
    
    # Stwórz nową bazę (automatycznie włączy WAL)
    db = MeshtasticDatabase("test_concurrent.db")
    db.close()
    
    # Uruchom wiele wątków piszących i czytających jednocześnie
    threads = []
    
    # 3 wątki piszące
    for i in range(3):
        t = threading.Thread(target=writer_thread, args=(i, 50))
        threads.append(t)
        t.start()
    
    # 2 wątki czytające
    for i in range(2):
        t = threading.Thread(target=reader_thread, args=(i, 2))
        threads.append(t)
        t.start()
    
    # Poczekaj na wszystkie wątki
    for t in threads:
        t.join()
    
    # Sprawdź wyniki
    db = MeshtasticDatabase("test_concurrent.db")
    stats = db.get_statistics()
    db.close()
    
    print(f"\n📊 Statystyki po teście:")
    print(f"   Całkowita liczba wiadomości: {stats['total_messages']}")
    print(f"   Unikalne węzły: {stats['unique_nodes']}")
    
    if stats['total_messages'] == 150:  # 3 wątki × 50 wiadomości
        print("✅ Wszystkie wiadomości zostały zapisane poprawnie")
        return True
    else:
        print(f"❌ Oczekiwano 150 wiadomości, otrzymano {stats['total_messages']}")
        return False

def test_wal_files():
    """Sprawdza czy powstały pliki WAL"""
    print("\n🔍 Test 3: Sprawdzanie plików WAL...")
    
    db_file = Path("test_concurrent.db")
    wal_file = Path("test_concurrent.db-wal")
    shm_file = Path("test_concurrent.db-shm")
    
    files_exist = []
    
    if db_file.exists():
        print(f"✅ Plik bazy: {db_file.name} ({db_file.stat().st_size} bytes)")
        files_exist.append(True)
    else:
        print(f"❌ Brak pliku bazy: {db_file.name}")
        files_exist.append(False)
    
    if wal_file.exists():
        print(f"✅ Plik WAL: {wal_file.name} ({wal_file.stat().st_size} bytes)")
        files_exist.append(True)
    else:
        print(f"⚠️  Plik WAL nie istnieje (może być pusty po checkpoint)")
        files_exist.append(True)  # To jest OK
    
    if shm_file.exists():
        print(f"✅ Plik SHM: {shm_file.name} ({shm_file.stat().st_size} bytes)")
        files_exist.append(True)
    else:
        print(f"⚠️  Plik SHM nie istnieje (może być pusty po checkpoint)")
        files_exist.append(True)  # To jest OK
    
    return all(files_exist)

def test_no_locking_errors():
    """Sprawdza czy nie ma błędów blokowania"""
    print("\n🔍 Test 4: Test braku błędów blokowania...")
    
    try:
        # Otwórz 5 połączeń jednocześnie
        connections = []
        for i in range(5):
            db = MeshtasticDatabase("test_concurrent.db")
            connections.append(db)
        
        # Każde połączenie próbuje czytać
        for i, db in enumerate(connections):
            stats = db.get_statistics()
            print(f"   Połączenie {i+1}: {stats['total_messages']} wiadomości")
        
        # Zamknij wszystkie
        for db in connections:
            db.close()
        
        print("✅ Żadnych błędów blokowania przy wielu połączeniach")
        return True
        
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            print(f"❌ Błąd blokowania: {e}")
            return False
        raise

def cleanup():
    """Usuwa pliki testowe"""
    print("\n🧹 Czyszczenie plików testowych...")
    
    for suffix in ['', '-wal', '-shm']:
        test_file = Path(f"test_concurrent.db{suffix}")
        if test_file.exists():
            test_file.unlink()
            print(f"   Usunięto: {test_file.name}")

def main():
    """Uruchamia wszystkie testy"""
    print("=" * 60)
    print("Test współbieżnego dostępu do bazy danych - Mesh Scout")
    print("=" * 60)
    
    results = []
    
    # Test 1: Tryb WAL
    results.append(("Tryb WAL", test_wal_mode()))
    
    # Test 2: Współbieżny dostęp
    results.append(("Współbieżny dostęp", test_concurrent_access()))
    
    # Test 3: Pliki WAL
    results.append(("Pliki WAL", test_wal_files()))
    
    # Test 4: Brak blokowania
    results.append(("Brak blokowania", test_no_locking_errors()))
    
    # Wyniki
    print("\n" + "=" * 60)
    print("PODSUMOWANIE TESTÓW")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("🎉 Wszystkie testy przeszły pomyślnie!")
        print("✅ Baza danych obsługuje współbieżny zapis i odczyt")
    else:
        print("⚠️  Niektóre testy nie przeszły")
        print("❌ Sprawdź konfigurację bazy danych")
    
    # Czyszczenie
    cleanup()
    
    return all_passed

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
