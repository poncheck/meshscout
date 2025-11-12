#!/usr/bin/env python3
import sqlite3
import argparse
import sys
from pathlib import Path

# Lista typów wiadomości, które są generalnie bezpieczne do usunięcia bez wpływu na logikę gry.
# Możesz ją dostosować za pomocą argumentu --types.
DEFAULT_TYPES_TO_DELETE = [
    'UNKNOWN',
    'MAP_REPORT_APP',
    'ROUTING_APP',
    'NEIGHBORINFO_APP',
    'RANGE_TEST_APP',
    'ATAK_PLUGIN',
    'ADMIN_APP',
    'STORE_FORWARD_APP',
    'PAXCOUNTER_APP',
    'WAYPOINT_APP'
]

def get_db_stats(cursor):
    """Pobiera statystyki typów wiadomości z bazy danych."""
    cursor.execute("""
        SELECT message_type, COUNT(*) as count
        FROM messages
        GROUP BY message_type
        ORDER BY count DESC
    """)
    return cursor.fetchall()

def print_stats(stats, title):
    """Wyświetla statystyki w czytelnej formie."""
    print(f"\n--- {title} ---")
    if not stats:
        print("Brak wiadomości w bazie danych.")
        return
    for row in stats:
        print(f"  {row[0]}: {row[1]}")
    print("-" * (len(title) + 8))

def cleanup_database(db_path, types_to_delete, dry_run=False, yes=False):
    """
    Usuwa wiadomości o określonych typach z bazy danych.
    """
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"BŁĄD: Plik bazy danych nie istnieje: {db_path}")
        sys.exit(1)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print(f"Połączono z bazą danych: {db_path}")

        # Statystyki PRZED
        stats_before = get_db_stats(cursor)
        print_stats(stats_before, "Statystyki PRZED czyszczeniem")

        print("\nTypy wiadomości do usunięcia:")
        for msg_type in types_to_delete:
            print(f" - {msg_type}")

        if dry_run:
            print("\n[DRY RUN] Symulacja. Nie zostaną wprowadzone żadne zmiany.")
            for msg_type in types_to_delete:
                cursor.execute("SELECT COUNT(*) FROM messages WHERE message_type = ?", (msg_type,))
                count = cursor.fetchone()[0]
                print(f"[DRY RUN] Znaleziono {count} wiadomości typu '{msg_type}' do usunięcia.")
            conn.close()
            return

        if not yes:
            confirm = input("\nCzy na pewno chcesz trwale usunąć te wiadomości? (tak/nie): ")
            if confirm.lower() != 'tak':
                print("Anulowano operację.")
                conn.close()
                sys.exit(0)

        print("\nRozpoczynam usuwanie wiadomości...")
        total_deleted = 0
        for msg_type in types_to_delete:
            print(f"Usuwanie typu: {msg_type}...")
            cursor.execute("DELETE FROM messages WHERE message_type = ?", (msg_type,))
            deleted_count = cursor.rowcount
            total_deleted += deleted_count
            print(f"Usunięto {deleted_count} wiadomości.")
        
        print(f"\nŁącznie usunięto {total_deleted} wiadomości.")

        if total_deleted > 0:
            print("Optymalizacja bazy danych (VACUUM)...")
            conn.commit() # Commit before vacuum
            conn.execute("VACUUM")
            conn.commit()
            print("Optymalizacja zakończona.")

        # Statystyki PO
        stats_after = get_db_stats(cursor)
        print_stats(stats_after, "Statystyki PO czyszczeniu")

    except sqlite3.Error as e:
        print(f"Błąd bazy danych: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()
            print("\nPołączenie z bazą danych zamknięte.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Narzędzie do czyszczenia bazy danych Mesh Scout z niepotrzebnych typów wiadomości.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--db-path",
        default="data/mesh_scout.db",
        help="Ścieżka do pliku bazy danych SQLite. Domyślnie: 'data/mesh_scout.db'"
    )
    parser.add_argument(
        "--types",
        nargs='+',
        default=DEFAULT_TYPES_TO_DELETE,
        help=f"""Lista typów wiadomości do usunięcia, oddzielona spacjami.
Domyślnie: {' '.join(DEFAULT_TYPES_TO_DELETE)}"""
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Uruchom w trybie symulacji, bez faktycznego usuwania danych."
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Pomiń prośbę o potwierdzenie."
    )

    args = parser.parse_args()

    cleanup_database(args.db_path, args.types, args.dry_run, args.yes)
