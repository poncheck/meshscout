#!/usr/bin/env python3
"""
Przeglądarka bazy danych Meshtastic
Wyświetla zapisane wiadomości i statystyki
"""

import argparse
import sys
from pathlib import Path
from database import MeshtasticDatabase
import json
from datetime import datetime


def print_message(msg, full=False):
    """Wyświetla pojedynczą wiadomość"""
    print(f"\n{'='*80}")
    print(f"ID: {msg['id']} | {msg['received_at']}")
    print(f"Kanał: {msg['channel_id']} | Od: {msg['from_node']} | Do: {msg['to_node']}")

    if msg['message_type']:
        print(f"Typ: {msg['message_type']}")

    if msg['message_text']:
        print(f"Tekst: {msg['message_text']}")

    if msg['hashtags']:
        print(f"Hashtagi: {msg['hashtags']}")

    if msg['latitude'] and msg['longitude']:
        print(f"Pozycja: {msg['latitude']}, {msg['longitude']} (alt: {msg['altitude']}m)")
        print(f"Google Maps: https://www.google.com/maps?q={msg['latitude']},{msg['longitude']}")

    if msg['user_longname']:
        print(f"Użytkownik: {msg['user_longname']} ({msg['user_shortname']})")

    if msg['battery_level']:
        print(f"Bateria: {msg['battery_level']}% | Napięcie: {msg['voltage']}V")

    if msg['temperature']:
        print(f"Temperatura: {msg['temperature']}°C")

    if msg['rssi'] or msg['snr']:
        print(f"RSSI: {msg['rssi']} | SNR: {msg['snr']}")

    if full and msg['raw_json']:
        print(f"\nSurowe JSON:")
        try:
            raw = json.loads(msg['raw_json'])
            print(json.dumps(raw, indent=2, ensure_ascii=False))
        except:
            print(msg['raw_json'])


def main():
    parser = argparse.ArgumentParser(description='Przeglądarka bazy danych Meshtastic')
    parser.add_argument('--db', default='meshtastic_messages.db', help='Ścieżka do bazy danych')
    parser.add_argument('--stats', action='store_true', help='Pokaż statystyki')
    parser.add_argument('--hashtag', help='Filtruj po hashtagu (np. #countme)')
    parser.add_argument('--channel', help='Filtruj po kanale')
    parser.add_argument('--limit', type=int, default=20, help='Limit wyników')
    parser.add_argument('--full', action='store_true', help='Pokaż pełne JSON')
    parser.add_argument('--export-json', help='Eksportuj do pliku JSON')

    args = parser.parse_args()

    # Sprawdź czy baza istnieje
    if not Path(args.db).exists():
        print(f"Błąd: Baza danych nie istnieje: {args.db}")
        sys.exit(1)

    # Otwórz bazę
    with MeshtasticDatabase(args.db) as db:
        # Statystyki
        if args.stats:
            stats = db.get_statistics(args.channel)
            print("\n" + "="*80)
            print("STATYSTYKI BAZY DANYCH")
            print("="*80)
            print(f"Łączna liczba wiadomości: {stats['total_messages']}")
            print(f"Unikalne węzły: {stats['unique_nodes']}")

            if stats['message_types']:
                print("\nTypy wiadomości:")
                for mt in stats['message_types']:
                    print(f"  {mt['type']}: {mt['count']}")

            if stats['top_hashtags']:
                print("\nNajpopularniejsze hashtagi:")
                for ht in stats['top_hashtags']:
                    print(f"  {ht['hashtag']}: {ht['count']}")
            print()

        # Lista wiadomości
        if args.hashtag:
            messages = db.get_messages_with_hashtag(args.hashtag, args.channel, args.limit)
            print(f"\nZnaleziono {len(messages)} wiadomości z hashtagiem {args.hashtag}")
        else:
            # Pobierz ostatnie wiadomości
            cursor = db.conn.cursor()
            where = f"WHERE channel_id = '{args.channel}'" if args.channel else ""
            cursor.execute(f"""
                SELECT * FROM messages
                {where}
                ORDER BY received_at DESC
                LIMIT {args.limit}
            """)
            messages = [dict(row) for row in cursor.fetchall()]
            print(f"\nOstatnie {len(messages)} wiadomości:")

        # Wyświetl wiadomości
        for msg in messages:
            print_message(msg, args.full)

        # Eksport do JSON
        if args.export_json:
            with open(args.export_json, 'w', encoding='utf-8') as f:
                json.dump(messages, f, indent=2, ensure_ascii=False, default=str)
            print(f"\n✓ Wyeksportowano {len(messages)} wiadomości do {args.export_json}")


if __name__ == '__main__':
    main()
