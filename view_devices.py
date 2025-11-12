#!/usr/bin/env python3
"""
Narzędzie do przeglądania zarejestrowanych urządzeń Meshtastic
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Optional
from database import MeshtasticDatabase


def format_timestamp(ts_str: Optional[str]) -> str:
    """Formatuje timestamp do czytelnej formy"""
    if not ts_str:
        return "brak"
    try:
        dt = datetime.fromisoformat(ts_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return ts_str


def format_position(lat: Optional[float], lon: Optional[float], alt: Optional[int]) -> str:
    """Formatuje pozycję GPS"""
    if lat and lon:
        google_maps = f"https://www.google.com/maps?q={lat},{lon}"
        alt_str = f" (↕ {alt}m)" if alt else ""
        return f"{lat:.6f}, {lon:.6f}{alt_str}\n     🗺️  {google_maps}"
    return "brak danych GPS"


def display_device(device: dict, detailed: bool = False):
    """Wyświetla informacje o urządzeniu"""
    print(f"\n{'='*80}")
    print(f"🔹 Urządzenie: {device['node_id']}")
    print(f"   📡 Kanał: {device.get('channel_id', 'nieznany')}")

    if device.get('user_longname'):
        print(f"   👤 Nazwa: {device['user_longname']}", end="")
        if device.get('user_shortname'):
            print(f" ({device['user_shortname']})", end="")
        print()

    if device.get('hw_model'):
        print(f"   💻 Model: {device['hw_model']}")

    # Pozycja
    print(f"   📍 Pozycja: {format_position(device.get('last_latitude'), device.get('last_longitude'), device.get('last_altitude'))}")

    # Telemetria
    if device.get('last_battery_level') or device.get('last_voltage'):
        print(f"   🔋 Bateria: ", end="")
        if device.get('last_battery_level'):
            print(f"{device['last_battery_level']}%", end="")
        if device.get('last_voltage'):
            print(f" ({device['last_voltage']:.2f}V)", end="")
        print()

    # Statystyki
    print(f"   📊 Wiadomości: {device.get('total_messages', 0)}")
    print(f"   📅 Zarejestrowano: {format_timestamp(device.get('registered_at'))}")
    print(f"   🕐 Ostatnio widziany: {format_timestamp(device.get('last_seen'))}")

    if detailed and device.get('registration_message'):
        print(f"   💬 Wiadomość rejestracji: \"{device['registration_message']}\"")


def list_devices(db: MeshtasticDatabase, channel_id: Optional[str] = None,
                 detailed: bool = False, limit: int = 100):
    """Wyświetla listę zarejestrowanych urządzeń"""
    devices = db.get_all_devices(channel_id=channel_id, limit=limit)

    if not devices:
        print("Brak zarejestrowanych urządzeń w bazie danych.")
        return

    print(f"\n📱 Znaleziono {len(devices)} zarejestrowanych urządzeń:")

    for device in devices:
        display_device(device, detailed=detailed)

    print(f"\n{'='*80}")


def show_device_details(db: MeshtasticDatabase, node_id: str):
    """Wyświetla szczegóły konkretnego urządzenia"""
    device = db.get_device(node_id)

    if not device:
        print(f"❌ Nie znaleziono urządzenia: {node_id}")
        return

    display_device(device, detailed=True)
    print(f"{'='*80}\n")


def export_devices_to_json(db: MeshtasticDatabase, output_file: str,
                           channel_id: Optional[str] = None):
    """Eksportuje listę urządzeń do pliku JSON"""
    devices = db.get_all_devices(channel_id=channel_id, limit=10000)

    if not devices:
        print("Brak urządzeń do eksportu.")
        return

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(devices, f, indent=2, ensure_ascii=False, default=str)
        print(f"✅ Wyeksportowano {len(devices)} urządzeń do pliku: {output_file}")
    except Exception as e:
        print(f"❌ Błąd zapisu do pliku: {e}")


def show_statistics(db: MeshtasticDatabase):
    """Wyświetla statystyki urządzeń"""
    devices = db.get_all_devices(limit=10000)

    if not devices:
        print("Brak zarejestrowanych urządzeń.")
        return

    print(f"\n{'='*80}")
    print("📊 STATYSTYKI URZĄDZEŃ")
    print(f"{'='*80}")

    total = len(devices)
    with_gps = sum(1 for d in devices if d.get('last_latitude') and d.get('last_longitude'))
    with_user_info = sum(1 for d in devices if d.get('user_longname'))

    channels = {}
    for device in devices:
        ch = device.get('channel_id', 'nieznany')
        channels[ch] = channels.get(ch, 0) + 1

    total_messages = sum(d.get('total_messages', 0) for d in devices)

    print(f"Łączna liczba urządzeń: {total}")
    print(f"Urządzenia z GPS: {with_gps} ({with_gps/total*100:.1f}%)")
    print(f"Urządzenia z nazwą: {with_user_info} ({with_user_info/total*100:.1f}%)")
    print(f"Łączna liczba wiadomości: {total_messages}")

    print(f"\nUrządzenia według kanałów:")
    for channel, count in sorted(channels.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {channel}: {count}")

    # Ostatnio zarejestrowane
    recent = sorted(devices, key=lambda x: x.get('registered_at', ''), reverse=True)[:5]
    print(f"\n5 ostatnio zarejestrowanych urządzeń:")
    for device in recent:
        name = device.get('user_longname', device['node_id'])
        reg_at = format_timestamp(device.get('registered_at'))
        print(f"  - {name} ({device['node_id']}) - {reg_at}")

    print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Przeglądanie zarejestrowanych urządzeń Meshtastic',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady użycia:

  # Lista wszystkich urządzeń
  python3 view_devices.py

  # Lista urządzeń z konkretnego kanału
  python3 view_devices.py --channel mesh-scout

  # Szczegóły konkretnego urządzenia
  python3 view_devices.py --device 0x29b07f7e

  # Statystyki
  python3 view_devices.py --stats

  # Eksport do JSON
  python3 view_devices.py --export-json devices.json

  # Szczegółowa lista (z wiadomością rejestracyjną)
  python3 view_devices.py --detailed
        """
    )

    parser.add_argument('--db', type=str, default='mesh_scout.db',
                       help='Ścieżka do bazy danych (domyślnie: mesh_scout.db)')
    parser.add_argument('--channel', type=str,
                       help='Filtruj według channel_id')
    parser.add_argument('--device', type=str,
                       help='Pokaż szczegóły konkretnego urządzenia (node_id)')
    parser.add_argument('--stats', action='store_true',
                       help='Wyświetl statystyki urządzeń')
    parser.add_argument('--detailed', action='store_true',
                       help='Szczegółowe informacje o urządzeniach')
    parser.add_argument('--limit', type=int, default=100,
                       help='Limit wyników (domyślnie: 100)')
    parser.add_argument('--export-json', type=str,
                       help='Eksportuj urządzenia do pliku JSON')

    args = parser.parse_args()

    # Połącz z bazą danych
    try:
        db = MeshtasticDatabase(args.db)
    except Exception as e:
        print(f"❌ Błąd połączenia z bazą danych: {e}")
        sys.exit(1)

    try:
        if args.stats:
            show_statistics(db)
        elif args.device:
            show_device_details(db, args.device)
        elif args.export_json:
            export_devices_to_json(db, args.export_json, channel_id=args.channel)
        else:
            list_devices(db, channel_id=args.channel, detailed=args.detailed, limit=args.limit)
    finally:
        db.close()


if __name__ == "__main__":
    main()
