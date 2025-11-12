#!/usr/bin/env python3
"""
Skrypt do podglądu bazy danych Mesh Scout
"""

import sqlite3
import sys
from datetime import datetime

# Domyślna ścieżka - taka sama jak w view_devices.py
DB_PATH = 'data/mesh_scout.db'

# Jeśli podano argument, użyj go jako ścieżkę
if len(sys.argv) > 2 and sys.argv[1] not in ['players', 'highscore', 'traceroutes', 'trace', 'devices']:
    DB_PATH = sys.argv[1]
    sys.argv.pop(1)  # Usuń ścieżkę z argumentów

def show_devices():
    """Pokaż listę urządzeń"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Statystyki
        cursor.execute("SELECT COUNT(*) as total FROM devices")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) as players FROM devices WHERE is_player = 1")
        players = cursor.fetchone()[0]

        print(f"\n📊 Statystyki:")
        print(f"   Wszystkich urządzeń: {total}")
        print(f"   Graczy: {players}")
        print(f"   Zwykłych urządzeń: {total - players}")
        print()

        # Lista urządzeń
        cursor.execute("""
            SELECT node_id, is_player, user_longname, user_shortname,
                   last_latitude, last_longitude, total_messages, last_seen, role
            FROM devices
            ORDER BY last_seen DESC
            LIMIT 50
        """)

        print("📋 Lista urządzeń:")
        print("-" * 130)
        print(f"{'Node ID':<15} {'Typ':<10} {'Nazwa':<35} {'GPS':<20} {'Msg':<5} {'Ostatnio'}")
        print("-" * 130)

        for row in cursor.fetchall():
            node_id = row['node_id']
            typ = "🎮 GRACZ" if row['is_player'] else "📡 urządzenie"
            nazwa = row['user_longname'] or "(brak nazwy)"
            if row['user_shortname']:
                nazwa = f"{nazwa} ({row['user_shortname']})"
            nazwa = nazwa[:35]  # Przytnij do 35 znaków

            if row['last_latitude'] and row['last_longitude']:
                gps = f"{row['last_latitude']:.4f}, {row['last_longitude']:.4f}"
            else:
                gps = "(brak GPS)"

            msgs = str(row['total_messages'])
            last_seen = row['last_seen'][:19] if row['last_seen'] else "nigdy"

            print(f"{node_id:<15} {typ:<10} {nazwa:<35} {gps:<20} {msgs:<5} {last_seen}")

        conn.close()

    except Exception as e:
        print(f"❌ Błąd: {e}")
        sys.exit(1)

def show_players():
    """Pokaż listę graczy (highscore)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                s.node_id,
                s.total_points,
                s.total_traceroutes_sent,
                s.total_hops_responded,
                s.last_traceroute,
                d.user_longname,
                d.user_shortname
            FROM player_scores s
            LEFT JOIN devices d ON s.node_id = d.node_id
            WHERE s.total_points > 0
            ORDER BY s.total_points DESC
            LIMIT 20
        """)

        players = cursor.fetchall()

        print(f"\n🏆 Highscore - TOP {len(players)} graczy:")
        print("-" * 100)
        print(f"{'#':<4} {'Node ID':<15} {'Nazwa':<35} {'Punkty':<10} {'Traceroutes':<12} {'Ostatni'}")
        print("-" * 100)

        for idx, row in enumerate(players, 1):
            rank = f"#{idx}"
            if idx == 1:
                rank = "🥇"
            elif idx == 2:
                rank = "🥈"
            elif idx == 3:
                rank = "🥉"

            node_id = row['node_id']
            nazwa = row['user_longname'] or "(brak nazwy)"
            if row['user_shortname']:
                nazwa = f"{nazwa} ({row['user_shortname']})"
            nazwa = nazwa[:35]

            points = f"{row['total_points']} pkt"
            traceroutes = str(row['total_traceroutes_sent'])
            last = row['last_traceroute'][:19] if row['last_traceroute'] else "nigdy"

            print(f"{rank:<4} {node_id:<15} {nazwa:<35} {points:<10} {traceroutes:<12} {last}")

        conn.close()

    except Exception as e:
        print(f"❌ Błąd: {e}")
        sys.exit(1)

def show_traceroutes():
    """Pokaż ostatnie traceroutes"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                t.packet_id,
                t.sender_node,
                t.hop_node,
                t.hop_number,
                t.distance_km,
                t.points,
                t.received_at,
                d1.user_longname as sender_name,
                d2.user_longname as hop_name
            FROM traceroute_packets t
            LEFT JOIN devices d1 ON t.sender_node = d1.node_id
            LEFT JOIN devices d2 ON t.hop_node = d2.node_id
            ORDER BY t.received_at DESC
            LIMIT 30
        """)

        traceroutes = cursor.fetchall()

        print(f"\n📡 Ostatnie {len(traceroutes)} traceroutes:")
        print("-" * 120)
        print(f"{'Packet ID':<12} {'Gracz':<25} {'Hop':<25} {'#':<4} {'Odległość':<12} {'Punkty':<8} {'Czas'}")
        print("-" * 120)

        for row in traceroutes:
            packet_id = str(row['packet_id'])[:12]
            sender = row['sender_name'] or row['sender_node']
            sender = sender[:25]
            hop = row['hop_name'] or row['hop_node']
            hop = hop[:25]
            hop_num = f"#{row['hop_number']}" if row['hop_number'] else "-"
            distance = f"{row['distance_km']:.2f} km" if row['distance_km'] else "-"
            points = f"{row['points']} pkt" if row['points'] else "-"
            time = row['received_at'][:19] if row['received_at'] else "-"

            print(f"{packet_id:<12} {sender:<25} {hop:<25} {hop_num:<4} {distance:<12} {points:<8} {time}")

        conn.close()

    except Exception as e:
        print(f"❌ Błąd: {e}")
        sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == 'players' or cmd == 'highscore':
            show_players()
        elif cmd == 'traceroutes' or cmd == 'trace':
            show_traceroutes()
        else:
            print("Użycie: ./show_db.py [devices|players|traceroutes]")
            sys.exit(1)
    else:
        show_devices()
