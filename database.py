#!/usr/bin/env python3
"""
Database handler dla Meshtastic MQTT Decoder
Obsługuje zapis wiadomości do SQLite
"""

import sqlite3
import json
import logging
import math
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

# Setup logger first
logger = logging.getLogger(__name__)

# Import H3 utilities
try:
    from h3_utils import lat_lon_to_h3, DEFAULT_H3_RESOLUTION
    H3_AVAILABLE = True
except ImportError:
    H3_AVAILABLE = False
    DEFAULT_H3_RESOLUTION = 8  # Fallback value
    logger.warning("H3 utilities not available - H3 features disabled")


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Oblicza odległość między dwoma punktami GPS używając formuły Haversine

    Args:
        lat1, lon1: Współrzędne punktu 1
        lat2, lon2: Współrzędne punktu 2

    Returns:
        Odległość w kilometrach
    """
    # Promień Ziemi w km
    R = 6371.0

    # Konwersja na radiany
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Różnice
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    # Formuła Haversine
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c
    return distance


class MeshtasticDatabase:
    """Klasa do zarządzania bazą danych SQLite dla wiadomości Meshtastic"""

    def __init__(self, db_path: str = "data/mesh_scout.db"):
        """
        Inicjalizacja połączenia z bazą danych

        Args:
            db_path: Ścieżka do pliku bazy danych SQLite
        """
        self.db_path = Path(db_path)
        self.conn = None
        self._init_database()

    def _init_database(self):
        """Inicjalizuje bazę danych i tworzy tabele jeśli nie istnieją"""
        try:
            # Upewnij się, że katalog nadrzędny istnieje
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Połączenie z bazą danych z obsługą współbieżności
            self.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0  # 30 sekund timeout dla locków
            )
            self.conn.row_factory = sqlite3.Row  # Zwraca wyniki jako dict

            cursor = self.conn.cursor()

            # Sprawdź integralność bazy danych (tylko jeśli plik już istnieje i ma rozmiar > 0)
            if self.db_path.exists() and self.db_path.stat().st_size > 0:
                try:
                    result = cursor.execute("PRAGMA integrity_check").fetchone()
                    if result and result[0] != "ok":
                        logger.error(f"Baza danych jest uszkodzona: {result[0]}")
                        logger.warning("Rozpoczynam odzyskiwanie danych z uszkodzonej bazy...")
                        self._recover_corrupted_database()
                        # Po odzyskaniu, ponownie połącz się z nową bazą
                        self.conn = sqlite3.connect(
                            self.db_path,
                            check_same_thread=False,
                            timeout=30.0
                        )
                        self.conn.row_factory = sqlite3.Row
                        cursor = self.conn.cursor()
                        logger.info("Baza danych odzyskana pomyślnie")
                    else:
                        logger.debug("Integralność bazy danych: OK")
                except sqlite3.DatabaseError as e:
                    logger.error(f"Błąd sprawdzania integralności bazy: {e}")
                    # Jeśli nie można sprawdzić integralności, utwórz backup i nową bazę
                    if "malformed" in str(e).lower() or "corrupt" in str(e).lower() or "database disk image is malformed" in str(e).lower():
                        logger.warning("Wykryto uszkodzoną bazę danych, rozpoczynam odzyskiwanie...")
                        try:
                            self.conn.close()
                            self._recover_corrupted_database()
                            # Ponownie połącz się z nową bazą
                            self.conn = sqlite3.connect(
                                self.db_path,
                                check_same_thread=False,
                                timeout=30.0
                            )
                            self.conn.row_factory = sqlite3.Row
                            cursor = self.conn.cursor()
                            logger.info("Baza danych odzyskana pomyślnie")
                        except Exception as recovery_error:
                            logger.error(f"Błąd odzyskiwania bazy danych: {recovery_error}")
                            raise

            # Włącz WAL (Write-Ahead Logging) dla pełnej współbieżności
            # WAL pozwala na jednoczesne czytanie i pisanie do bazy
            cursor.execute("PRAGMA journal_mode=WAL")

            # Optymalizacje dla współbieżności i zapobiegania korupcji
            cursor.execute("PRAGMA synchronous=NORMAL")   # NORMAL jest bezpieczny z WAL i 10-20x szybszy niż FULL
            cursor.execute("PRAGMA cache_size=-64000")    # 64MB cache
            cursor.execute("PRAGMA temp_store=MEMORY")    # Tymczasowe dane w pamięci
            cursor.execute("PRAGMA busy_timeout=30000")   # 30 sekund timeout
            cursor.execute("PRAGMA wal_autocheckpoint=1000")  # Checkpoint co 1000 stron
            cursor.execute("PRAGMA page_size=4096")       # Standardowy rozmiar strony
            cursor.execute("PRAGMA auto_vacuum=INCREMENTAL")  # Automatyczne czyszczenie

            logger.info("Włączono tryb WAL z normalną synchronizacją dla szybkiego i bezpiecznego dostępu do bazy danych")

            # Tabela główna dla wiadomości
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    message_id INTEGER,
                    channel_id TEXT,
                    gateway_id TEXT,
                    from_node TEXT,
                    to_node TEXT,
                    message_type TEXT,
                    message_text TEXT,
                    hashtags TEXT,
                    latitude REAL,
                    longitude REAL,
                    altitude INTEGER,
                    rssi INTEGER,
                    snr REAL,
                    hop_limit INTEGER,
                    rx_time INTEGER,
                    user_longname TEXT,
                    user_shortname TEXT,
                    hw_model INTEGER,
                    battery_level INTEGER,
                    voltage REAL,
                    temperature REAL,
                    raw_json TEXT,
                    topic TEXT
                )
            """)

            # Tabela urządzeń (wszyscy - gracze i zwykłe urządzenia)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT UNIQUE NOT NULL,
                    is_player BOOLEAN DEFAULT 0,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    channel_id TEXT,
                    user_longname TEXT,
                    user_shortname TEXT,
                    hw_model INTEGER,
                    last_latitude REAL,
                    last_longitude REAL,
                    last_altitude INTEGER,
                    last_battery_level INTEGER,
                    last_voltage REAL,
                    registration_message TEXT,
                    total_messages INTEGER DEFAULT 0
                )
            """)

            # Tabela pakietów traceroute (tylko od graczy)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS traceroute_packets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    packet_id INTEGER NOT NULL,
                    sender_node TEXT NOT NULL,
                    hop_node TEXT NOT NULL,
                    hop_number INTEGER,
                    sender_latitude REAL,
                    sender_longitude REAL,
                    hop_latitude REAL,
                    hop_longitude REAL,
                    distance_km REAL,
                    points INTEGER DEFAULT 0,
                    channel_id TEXT,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(packet_id, hop_node)
                )
            """)

            # Tabela wyników graczy (highscore)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS player_scores (
                    node_id TEXT PRIMARY KEY,
                    total_points INTEGER DEFAULT 0,
                    total_traceroutes_sent INTEGER DEFAULT 0,
                    total_hops_responded INTEGER DEFAULT 0,
                    last_traceroute TIMESTAMP,
                    FOREIGN KEY (node_id) REFERENCES devices(node_id)
                )
            """)

            # Indeksy dla szybszego wyszukiwania - messages
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_channel_id ON messages(channel_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_from_node ON messages(from_node)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_hashtags ON messages(hashtags)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_received_at ON messages(received_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_message_type ON messages(message_type)
            """)

            # Indeksy dla devices
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_device_node_id ON devices(node_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_device_channel ON devices(channel_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_device_last_seen ON devices(last_seen)
            """)

            # Indeksy dla traceroute_packets
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_traceroute_packet_id ON traceroute_packets(packet_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_traceroute_sender ON traceroute_packets(sender_node)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_traceroute_hop ON traceroute_packets(hop_node)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_traceroute_channel ON traceroute_packets(channel_id)
            """)

            # Indeksy dla player_scores
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_player_score_points ON player_scores(total_points DESC)
            """)

            # Indeks dla is_player w devices
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_device_is_player ON devices(is_player)
            """)

            # Migracja: Dodaj kolumnę role jeśli nie istnieje
            try:
                cursor.execute("SELECT role FROM devices LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("Dodawanie kolumny 'role' do tabeli devices")
                cursor.execute("ALTER TABLE devices ADD COLUMN role INTEGER")

            # Migracja: Dodaj kolumnę route_path do traceroute_packets
            try:
                cursor.execute("SELECT route_path FROM traceroute_packets LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("Dodawanie kolumny 'route_path' do tabeli traceroute_packets")
                cursor.execute("ALTER TABLE traceroute_packets ADD COLUMN route_path TEXT")

            # Migracja: Dodaj kolumnę route_back do traceroute_packets
            try:
                cursor.execute("SELECT route_back FROM traceroute_packets LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("Dodawanie kolumny 'route_back' do tabeli traceroute_packets")
                cursor.execute("ALTER TABLE traceroute_packets ADD COLUMN route_back TEXT")

            # Migracja: Dodaj kolumnę is_confirmed do traceroute_packets
            try:
                cursor.execute("SELECT is_confirmed FROM traceroute_packets LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("Dodawanie kolumny 'is_confirmed' do tabeli traceroute_packets")
                cursor.execute("ALTER TABLE traceroute_packets ADD COLUMN is_confirmed BOOLEAN DEFAULT 0")

            # === H3 MIGRATIONS ===
            if H3_AVAILABLE:
                logger.info("H3 dostępne - inicjalizacja struktur H3")
                
                # Migracja: Dodaj kolumnę current_h3 do devices
                try:
                    cursor.execute("SELECT current_h3 FROM devices LIMIT 1")
                except sqlite3.OperationalError:
                    logger.info("Dodawanie kolumny 'current_h3' do tabeli devices")
                    cursor.execute("ALTER TABLE devices ADD COLUMN current_h3 TEXT")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_device_current_h3 ON devices(current_h3)")
                
                # Migracja: Dodaj kolumny H3 do traceroute_packets
                try:
                    cursor.execute("SELECT sender_h3 FROM traceroute_packets LIMIT 1")
                except sqlite3.OperationalError:
                    logger.info("Dodawanie kolumny 'sender_h3' do tabeli traceroute_packets")
                    cursor.execute("ALTER TABLE traceroute_packets ADD COLUMN sender_h3 TEXT")

                try:
                    cursor.execute("SELECT hop_h3 FROM traceroute_packets LIMIT 1")
                except sqlite3.OperationalError:
                    logger.info("Dodawanie kolumny 'hop_h3' do tabeli traceroute_packets")
                    cursor.execute("ALTER TABLE traceroute_packets ADD COLUMN hop_h3 TEXT")

                # Twórz indeksy dla kolumn H3 po ich dodaniu
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_traceroute_sender_h3 ON traceroute_packets(sender_h3)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_traceroute_hop_h3 ON traceroute_packets(hop_h3)
                """)
                
                # Tabela odwiedzonych heksagonów przez WSZYSTKIE urządzenia (graczy i zwykłe)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS device_hexagons (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        node_id TEXT NOT NULL,
                        h3_index TEXT NOT NULL,
                        is_player BOOLEAN DEFAULT 0,
                        first_visit TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_visit TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        visit_count INTEGER DEFAULT 1,
                        points_earned REAL DEFAULT 0,
                        traceroutes_here INTEGER DEFAULT 0,
                        UNIQUE(node_id, h3_index),
                        FOREIGN KEY (node_id) REFERENCES devices(node_id)
                    )
                """)
                
                # Indeksy dla device_hexagons
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_device_hex_node ON device_hexagons(node_id)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_device_hex_h3 ON device_hexagons(h3_index)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_device_hex_visits ON device_hexagons(last_visit DESC)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_device_hex_is_player ON device_hexagons(is_player)
                """)
                
                # Migracja: Dodaj kolumny H3 do player_scores
                try:
                    cursor.execute("SELECT hex_bonus_points FROM player_scores LIMIT 1")
                except sqlite3.OperationalError:
                    logger.info("Dodawanie kolumny 'hex_bonus_points' do tabeli player_scores")
                    cursor.execute("ALTER TABLE player_scores ADD COLUMN hex_bonus_points INTEGER DEFAULT 0")
                
                try:
                    cursor.execute("SELECT unique_hexes_visited FROM player_scores LIMIT 1")
                except sqlite3.OperationalError:
                    logger.info("Dodawanie kolumny 'unique_hexes_visited' do tabeli player_scores")
                    cursor.execute("ALTER TABLE player_scores ADD COLUMN unique_hexes_visited INTEGER DEFAULT 0")
                
                # Migracja: Zmień nazwę tabeli player_hexagons na device_hexagons jeśli istnieje
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='player_hexagons'
                """)
                if cursor.fetchone():
                    logger.info("Migracja: Znaleziono starą tabelę player_hexagons")
                    # Sprawdź czy device_hexagons już istnieje
                    cursor.execute("""
                        SELECT name FROM sqlite_master 
                        WHERE type='table' AND name='device_hexagons'
                    """)
                    if not cursor.fetchone():
                        # Kopiuj dane ze starej tabeli do nowej
                        logger.info("Migracja: Tworzenie device_hexagons z danych player_hexagons")
                        cursor.execute("""
                            INSERT INTO device_hexagons 
                            (node_id, h3_index, is_player, first_visit, last_visit, visit_count, points_earned, traceroutes_here)
                            SELECT node_id, h3_index, 1, first_visit, last_visit, visit_count, points_earned, traceroutes_here
                            FROM player_hexagons
                        """)
                        logger.info("Migracja: Skopiowano dane z player_hexagons (is_player=1)")
                        # Można opcjonalnie usunąć starą tabelę (zakomentowane dla bezpieczeństwa)
                        # cursor.execute("DROP TABLE player_hexagons")
                        
                logger.info("Struktury H3 zainicjalizowane pomyślnie")
            else:
                logger.warning("H3 nie dostępne - pominięto inicjalizację struktur H3")

            self.conn.commit()
            logger.info(f"Baza danych zainicjalizowana: {self.db_path}")

        except sqlite3.Error as e:
            logger.error(f"Błąd inicjalizacji bazy danych: {e}")
            raise

    def _recover_corrupted_database(self):
        """
        Odzyskuje dane z uszkodzonej bazy danych używając SQLite .recover
        Tworzy backup uszkodzonej bazy i nową czystą bazę danych
        """
        import shutil
        import subprocess
        import tempfile
        from datetime import datetime

        try:
            # Zamknij obecne połączenie jeśli jest otwarte
            if self.conn:
                try:
                    self.conn.close()
                except:
                    pass

            # Utwórz backup uszkodzonej bazy z timestampem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.db_path.with_suffix(f'.corrupted.{timestamp}.db')
            shutil.copy2(self.db_path, backup_path)
            logger.warning(f"✓ Uszkodzona baza zapisana jako: {backup_path}")

            # Spróbuj odzyskać dane używając sqlite3 .recover lub .dump
            recovered_data_path = self.db_path.with_suffix('.recovered.sql')

            # Metoda 1: Spróbuj użyć .recover (wymaga SQLite 3.37.0+)
            logger.info("Próba odzyskania danych używając .recover...")
            try:
                result = subprocess.run(
                    ['sqlite3', str(self.db_path), '.recover'],
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode == 0 and result.stdout:
                    with open(recovered_data_path, 'w', encoding='utf-8') as f:
                        f.write(result.stdout)
                    logger.info(f"✓ Odzyskano dane używając .recover ({len(result.stdout)} bajtów)")
                    recovery_method = 'recover'
                else:
                    raise Exception("Recover failed or returned no data")

            except Exception as recover_error:
                logger.warning(f".recover nie powiodło się: {recover_error}, próbuję .dump...")

                # Metoda 2: Fallback do .dump (może odzyskać częściowe dane)
                try:
                    result = subprocess.run(
                        ['sqlite3', str(self.db_path), '.dump'],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )

                    if result.returncode == 0 and result.stdout:
                        with open(recovered_data_path, 'w', encoding='utf-8') as f:
                            f.write(result.stdout)
                        logger.info(f"✓ Odzyskano dane używając .dump ({len(result.stdout)} bajtów)")
                        recovery_method = 'dump'
                    else:
                        raise Exception("Dump failed or returned no data")

                except Exception as dump_error:
                    logger.error(f".dump nie powiodło się: {dump_error}")
                    logger.warning("Nie udało się odzyskać danych, tworzę pustą bazę")
                    recovery_method = None

            # Usuń uszkodzoną bazę i pliki WAL
            logger.info("Usuwam uszkodzoną bazę danych...")
            if self.db_path.exists():
                self.db_path.unlink()

            # Usuń też pliki WAL i SHM jeśli istnieją
            wal_path = self.db_path.with_suffix('.db-wal')
            shm_path = self.db_path.with_suffix('.db-shm')
            if wal_path.exists():
                wal_path.unlink()
                logger.info("✓ Usunięto plik WAL")
            if shm_path.exists():
                shm_path.unlink()
                logger.info("✓ Usunięto plik SHM")

            # Jeśli udało się odzyskać dane, importuj je do nowej bazy
            if recovery_method and recovered_data_path.exists():
                logger.info("Importuję odzyskane dane do nowej bazy...")
                try:
                    result = subprocess.run(
                        ['sqlite3', str(self.db_path)],
                        input=open(recovered_data_path, 'r', encoding='utf-8').read(),
                        capture_output=True,
                        text=True,
                        timeout=120
                    )

                    if result.returncode == 0:
                        logger.info(f"✓ Pomyślnie zaimportowano odzyskane dane (metoda: {recovery_method})")
                        # Usuń plik SQL po udanym imporcie
                        recovered_data_path.unlink()
                    else:
                        logger.error(f"Błąd importu: {result.stderr}")
                        logger.warning("Tworzę pustą bazę zamiast tego")
                        if self.db_path.exists():
                            self.db_path.unlink()

                except Exception as import_error:
                    logger.error(f"Błąd podczas importu: {import_error}")
                    logger.warning("Tworzę pustą bazę zamiast tego")
                    if self.db_path.exists():
                        self.db_path.unlink()

            logger.info(f"✓ Odzyskiwanie zakończone. Backup: {backup_path}")

        except Exception as e:
            logger.error(f"Błąd krytyczny podczas odzyskiwania bazy: {e}")
            # Ostateczna próba - po prostu usuń bazę i zacznij od nowa
            try:
                if self.db_path.exists():
                    backup_path = self.db_path.with_suffix('.corrupted.emergency.db')
                    shutil.copy2(self.db_path, backup_path)
                    self.db_path.unlink()
                    logger.warning(f"Awaryjny backup zapisany jako: {backup_path}")
            except Exception as emergency_error:
                logger.error(f"Nie udało się utworzyć awaryjnego backupu: {emergency_error}")

    # Typy wiadomości, których nie zapisujemy w bazie (możesz edytować tę listę)
    IGNORED_MESSAGE_TYPES = {
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
    }

    def save_message(self, decoded_message: Dict[str, Any], topic: str) -> Optional[int]:
        """
        Zapisuje wiadomość do bazy danych

        Args:
            decoded_message: Zdekodowana wiadomość (dict z JSON)
            topic: Temat MQTT z którego przyszła wiadomość

        Returns:
            ID zapisanego rekordu lub None w przypadku błędu
        """
        try:
            cursor = self.conn.cursor()

            # Wyciągnij dane z wiadomości
            channel_id = decoded_message.get('channel_id', '')
            gateway_id = decoded_message.get('gateway_id', '')

            packet = decoded_message.get('packet', {})
            from_node = packet.get('from', '')
            to_node = packet.get('to', '')
            message_id = packet.get('packet_id', 0)
            rx_time = packet.get('rx_time', 0)
            hop_limit = packet.get('hop_limit', 0)

            # Dane specyficzne dla typu wiadomości
            decoded_data = packet.get('decoded_data', {})
            message_type = decoded_data.get('portnum_name', 'UNKNOWN')

            # Jeśli typ wiadomości jest na liście ignorowanych, nie zapisuj jej w bazie
            if message_type in self.IGNORED_MESSAGE_TYPES:
                logger.debug(f"Ignoruję wiadomość typu {message_type} - nie zostanie zapisana w bazie.")
                return None

            # Teksty
            message_text = decoded_data.get('text', None)
            hashtags = None
            if message_text:
                # Wyciągnij hashtagi
                import re
                found_hashtags = re.findall(r'#\w+', message_text)
                if found_hashtags:
                    hashtags = ','.join(found_hashtags)

            # Pozycja
            position = decoded_data.get('position', {})
            latitude = position.get('latitude', None)
            longitude = position.get('longitude', None)
            altitude = position.get('altitude', None)

            # User info
            user = decoded_data.get('user', {})
            user_longname = user.get('longname', None)
            user_shortname = user.get('shortname', None)
            hw_model = user.get('hw_model', None)

            # Telemetria
            telemetry = decoded_data.get('telemetry', {})
            device_metrics = telemetry.get('device_metrics', {})
            battery_level = device_metrics.get('battery_level', None)
            voltage = device_metrics.get('voltage', None)

            env_metrics = telemetry.get('environment_metrics', {})
            temperature = env_metrics.get('temperature', None)

            # RSSI/SNR (zazwyczaj w wiadomościach JSON)
            rssi = decoded_message.get('rssi', None)
            snr = decoded_message.get('snr', None)

            # Surowe JSON do późniejszej analizy
            raw_json = json.dumps(decoded_message, ensure_ascii=False)

            # INSERT
            cursor.execute("""
                INSERT INTO messages (
                    message_id, channel_id, gateway_id, from_node, to_node,
                    message_type, message_text, hashtags,
                    latitude, longitude, altitude,
                    rssi, snr, hop_limit, rx_time,
                    user_longname, user_shortname, hw_model,
                    battery_level, voltage, temperature,
                    raw_json, topic
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message_id, channel_id, gateway_id, from_node, to_node,
                message_type, message_text, hashtags,
                latitude, longitude, altitude,
                rssi, snr, hop_limit, rx_time,
                user_longname, user_shortname, hw_model,
                battery_level, voltage, temperature,
                raw_json, topic
            ))

            self.conn.commit()
            record_id = cursor.lastrowid
            logger.debug(f"Zapisano wiadomość do bazy: ID={record_id}, channel={channel_id}, from={from_node}")
            return record_id

        except sqlite3.Error as e:
            logger.error(f"Błąd zapisu do bazy danych: {e}")
            return None

    def get_messages_with_hashtag(self, hashtag: str, channel_id: Optional[str] = None,
                                   limit: int = 100) -> List[Dict[str, Any]]:
        """
        Pobiera wiadomości zawierające dany hashtag

        Args:
            hashtag: Hashtag do wyszukania (np. "#countme")
            channel_id: Opcjonalnie filtruj po kanale
            limit: Maksymalna liczba wyników

        Returns:
            Lista wiadomości jako dict
        """
        try:
            cursor = self.conn.cursor()

            if channel_id:
                cursor.execute("""
                    SELECT * FROM messages
                    WHERE hashtags LIKE ? AND channel_id = ?
                    ORDER BY received_at DESC
                    LIMIT ?
                """, (f'%{hashtag}%', channel_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM messages
                    WHERE hashtags LIKE ?
                    ORDER BY received_at DESC
                    LIMIT ?
                """, (f'%{hashtag}%', limit))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Błąd odczytu z bazy danych: {e}")
            return []

    def get_statistics(self, channel_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Zwraca statystyki bazy danych

        Args:
            channel_id: Opcjonalnie filtruj po kanale

        Returns:
            Dict ze statystykami
        """
        try:
            cursor = self.conn.cursor()

            where_clause = f"WHERE channel_id = '{channel_id}'" if channel_id else ""

            # Zoptymalizowane: Pobierz liczby w jednym zapytaniu
            cursor.execute(f"""
                SELECT
                    COUNT(*) as total_messages,
                    COUNT(DISTINCT from_node) as unique_nodes
                FROM messages {where_clause}
            """)
            row = cursor.fetchone()
            total_messages = row[0]
            unique_nodes = row[1]

            # Najpopularniejsze hashtagi
            cursor.execute(f"""
                SELECT hashtags, COUNT(*) as count
                FROM messages
                {where_clause}
                {'AND' if where_clause else 'WHERE'} hashtags IS NOT NULL
                GROUP BY hashtags
                ORDER BY count DESC
                LIMIT 10
            """)
            top_hashtags = [{"hashtag": row[0], "count": row[1]} for row in cursor.fetchall()]

            # Typy wiadomości
            cursor.execute(f"""
                SELECT message_type, COUNT(*) as count
                FROM messages
                {where_clause}
                GROUP BY message_type
                ORDER BY count DESC
            """)
            message_types = [{"type": row[0], "count": row[1]} for row in cursor.fetchall()]

            return {
                "total_messages": total_messages,
                "unique_nodes": unique_nodes,
                "top_hashtags": top_hashtags,
                "message_types": message_types,
                "channel_id": channel_id
            }

        except sqlite3.Error as e:
            logger.error(f"Błąd pobierania statystyk: {e}")
            return {}

    def register_device(self, node_id: str, channel_id: str,
                       position: Optional[Dict[str, Any]] = None,
                       user_info: Optional[Dict[str, Any]] = None,
                       telemetry: Optional[Dict[str, Any]] = None,
                       registration_message: Optional[str] = None,
                       increment_messages: bool = False,
                       is_player: bool = False) -> Optional[int]:
        """
        Rejestruje nowe urządzenie lub aktualizuje istniejące

        Args:
            node_id: ID węzła (np. "0x29b07f7e")
            channel_id: ID kanału na którym się zarejestrował
            position: Słownik z danymi pozycji (latitude, longitude, altitude)
            user_info: Słownik z informacjami o użytkowniku (longname, shortname, hw_model)
            telemetry: Słownik z danymi telemetrycznymi (battery_level, voltage)
            registration_message: Treść wiadomości rejestracyjnej
            increment_messages: Czy inkrementować licznik wiadomości (False dla automatycznych aktualizacji)
            is_player: Czy to gracz (True) czy zwykłe urządzenie (False)

        Returns:
            ID rekordu urządzenia lub None w przypadku błędu
        """
        try:
            cursor = self.conn.cursor()

            # Sprawdź czy urządzenie już istnieje
            cursor.execute("SELECT id, total_messages FROM devices WHERE node_id = ?", (node_id,))
            existing = cursor.fetchone()

            if existing:
                # Aktualizuj istniejące urządzenie
                device_id = existing[0]
                total_messages = existing[1]

                update_fields = ["last_seen = CURRENT_TIMESTAMP"]
                update_values = []

                # Inkrementuj licznik tylko jeśli increment_messages=True
                if increment_messages:
                    total_messages += 1
                    update_fields.append("total_messages = ?")
                    update_values.append(total_messages)

                # Aktualizuj status gracza (raz gracz, zawsze gracz)
                if is_player:
                    update_fields.append("is_player = ?")
                    update_values.append(1)

                if channel_id:
                    update_fields.append("channel_id = ?")
                    update_values.append(channel_id)

                if position:
                    if position.get('latitude'):
                        update_fields.append("last_latitude = ?")
                        update_values.append(position['latitude'])
                    if position.get('longitude'):
                        update_fields.append("last_longitude = ?")
                        update_values.append(position['longitude'])
                    if position.get('altitude'):
                        update_fields.append("last_altitude = ?")
                        update_values.append(position['altitude'])

                if user_info:
                    if user_info.get('longname'):
                        update_fields.append("user_longname = ?")
                        update_values.append(user_info['longname'])
                    if user_info.get('shortname'):
                        update_fields.append("user_shortname = ?")
                        update_values.append(user_info['shortname'])
                    if user_info.get('hw_model'):
                        update_fields.append("hw_model = ?")
                        update_values.append(user_info['hw_model'])
                    if user_info.get('role') is not None:
                        update_fields.append("role = ?")
                        update_values.append(user_info['role'])

                if telemetry:
                    device_metrics = telemetry.get('device_metrics', {})
                    if device_metrics.get('battery_level'):
                        update_fields.append("last_battery_level = ?")
                        update_values.append(device_metrics['battery_level'])
                    if device_metrics.get('voltage'):
                        update_fields.append("last_voltage = ?")
                        update_values.append(device_metrics['voltage'])

                update_values.append(node_id)
                cursor.execute(f"""
                    UPDATE devices
                    SET {', '.join(update_fields)}
                    WHERE node_id = ?
                """, update_values)

                logger.info(f"Zaktualizowano urządzenie: {node_id}")

            else:
                # Nowe urządzenie
                latitude = position.get('latitude') if position else None
                longitude = position.get('longitude') if position else None
                altitude = position.get('altitude') if position else None

                longname = user_info.get('longname') if user_info else None
                shortname = user_info.get('shortname') if user_info else None
                hw_model = user_info.get('hw_model') if user_info else None
                role = user_info.get('role') if user_info else None

                battery_level = None
                voltage = None
                if telemetry:
                    device_metrics = telemetry.get('device_metrics', {})
                    battery_level = device_metrics.get('battery_level')
                    voltage = device_metrics.get('voltage')

                cursor.execute("""
                    INSERT INTO devices (
                        node_id, is_player, channel_id,
                        user_longname, user_shortname, hw_model, role,
                        last_latitude, last_longitude, last_altitude,
                        last_battery_level, last_voltage,
                        registration_message, total_messages
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    node_id, 1 if is_player else 0, channel_id,
                    longname, shortname, hw_model, role,
                    latitude, longitude, altitude,
                    battery_level, voltage,
                    registration_message
                ))

                device_id = cursor.lastrowid
                logger.info(f"Zarejestrowano nowe urządzenie: {node_id} (ID={device_id})")

            self.conn.commit()
            return device_id

        except sqlite3.Error as e:
            logger.error(f"Błąd rejestracji urządzenia: {e}")
            return None

    def get_device(self, node_id: str) -> Optional[Dict[str, Any]]:
        """
        Pobiera informacje o zarejestrowanym urządzeniu

        Args:
            node_id: ID węzła

        Returns:
            Dict z informacjami o urządzeniu lub None
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM devices WHERE node_id = ?", (node_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Błąd pobierania urządzenia: {e}")
            return None

    def get_all_devices(self, channel_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Pobiera wszystkie zarejestrowane urządzenia

        Args:
            channel_id: Opcjonalnie filtruj po kanale
            limit: Maksymalna liczba wyników

        Returns:
            Lista urządzeń jako dict
        """
        try:
            cursor = self.conn.cursor()

            if channel_id:
                cursor.execute("""
                    SELECT * FROM devices
                    WHERE channel_id = ?
                    ORDER BY last_seen DESC
                    LIMIT ?
                """, (channel_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM devices
                    ORDER BY last_seen DESC
                    LIMIT ?
                """, (limit,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Błąd pobierania urządzeń: {e}")
            return []

    def is_device_registered(self, node_id: str) -> bool:
        """
        Sprawdza czy urządzenie jest zarejestrowane

        Args:
            node_id: ID węzła

        Returns:
            True jeśli urządzenie jest zarejestrowane
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1 FROM devices WHERE node_id = ? LIMIT 1", (node_id,))
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Błąd sprawdzania rejestracji: {e}")
            return False

    def is_player(self, node_id: str) -> bool:
        """
        Sprawdza czy urządzenie jest graczem (zarejestrowanym przez 'registerme')

        Args:
            node_id: ID węzła

        Returns:
            True jeśli urządzenie jest graczem
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT is_player FROM devices WHERE node_id = ? LIMIT 1", (node_id,))
            row = cursor.fetchone()
            return row[0] == 1 if row else False
        except sqlite3.Error as e:
            logger.error(f"Błąd sprawdzania statusu gracza: {e}")
            return False

    def delete_unconfirmed_traceroutes(self, sender_node: str, hop_node: str, seconds_old: int = 30) -> int:
        """
        Usuwa niepotwierdzony traceroute między podanymi węzłami (REQUEST bez RESPONSE/ACK)

        Args:
            sender_node: Gracz który wysłał traceroute
            hop_node: Węzeł docelowy
            seconds_old: Usuń tylko te z ostatnich X sekund (domyślnie 30)

        Returns:
            Liczba usuniętych rekordów
        """
        try:
            cursor = self.conn.cursor()

            cursor.execute("""
                DELETE FROM traceroute_packets
                WHERE sender_node = ?
                  AND hop_node = ?
                  AND is_confirmed = 0
                  AND received_at > datetime('now', '-' || ? || ' seconds')
            """, (sender_node, hop_node, seconds_old))

            deleted = cursor.rowcount
            self.conn.commit()

            if deleted > 0:
                logger.debug(f"Usunięto {deleted} niepotwierdzonych traceroute {sender_node}→{hop_node}")

            return deleted

        except sqlite3.Error as e:
            logger.error(f"Błąd usuwania niepotwierdzonych traceroute: {e}")
            return 0

    def record_traceroute(self, packet_id: int, sender_node: str, hop_node: str,
                         sender_pos: Optional[Tuple[float, float]] = None,
                         hop_pos: Optional[Tuple[float, float]] = None,
                         channel_id: Optional[str] = None,
                         hop_number: Optional[int] = None,
                         route_path: Optional[List[str]] = None,
                         route_back: Optional[List[str]] = None,
                         snr_towards: Optional[List] = None,
                         sender_h3: Optional[str] = None,
                         hop_h3: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Zapisuje hop z traceroute i oblicza punkty dla gracza

        Args:
            packet_id: ID pakietu traceroute
            sender_node: Gracz który wysłał traceroute
            hop_node: Urządzenie które odpowiedziało (może być graczem lub zwykłym urządzeniem)
            sender_pos: (latitude, longitude) gracza
            hop_pos: (latitude, longitude) hop'a
            channel_id: Kanał
            hop_number: Numer hopu w traceroute
            route_path: Pełna trasa tam jako lista node_id (opcjonalne)
            route_back: Pełna trasa z powrotem jako lista node_id (opcjonalne)
            snr_towards: SNR w kierunku celu - jeśli wypełnione, oznacza ACK/potwierdzenie
            sender_h3: H3 index gracza (opcjonalne)
            hop_h3: H3 index hop'a (opcjonalne)

        Returns:
            Dict z informacjami o traceroute lub None jeśli już istnieje
        """
        try:
            cursor = self.conn.cursor()

            # Sprawdź czy sender jest graczem
            if not self.is_player(sender_node):
                logger.debug(f"Pakiet {packet_id} od {sender_node} - nie jest graczem, pomijam")
                return None

            # Sprawdź czy to duplikat (ten sam packet_id i hop)
            cursor.execute("""
                SELECT id FROM traceroute_packets
                WHERE packet_id = ? AND hop_node = ?
            """, (packet_id, hop_node))

            if cursor.fetchone():
                logger.debug(f"Traceroute {packet_id} hop {hop_node} już zapisany")
                return None

            # Sprawdź czy traceroute jest potwierdzony:
            # - FULL RESPONSE: ma route_back (pełna trasa z powrotem)
            # - ACK: ma snr_towards (oznacza że węzeł otrzymał i odpowiedział)
            is_confirmed = (route_back is not None and len(route_back) > 0) or (snr_towards is not None and len(snr_towards) > 0)

            # Oblicz odległość i POTENCJALNE punkty
            distance_km = None
            potential_points = 0
            points = 0

            if sender_pos and hop_pos and sender_pos != hop_pos:
                sender_lat, sender_lon = sender_pos
                hop_lat, hop_lon = hop_pos
                distance_km = calculate_distance(sender_lat, sender_lon, hop_lat, hop_lon)
                # 1 punkt = 1 km (0.01 punkta = 10 metrów)
                potential_points = round(distance_km, 2)  # Zaokrąglenie do 2 miejsc po przecinku

            # Punkty przyznawane TYLKO dla potwierdzonych traceroute (z route_back)
            if not is_confirmed:
                points = 0
                logger.debug(f"Traceroute {sender_node}→{hop_node} NIEPOTWIERDZONY (brak route_back), 0 pkt")
            else:
                # H3: Sprawdź czy już dzisiaj był POTWIERDZONY traceroute od tego gracza do tego hopu W TYM HEKSAGONIE
                # Punkty przyznawane tylko raz dziennie na unikalne połączenie PER HEKSAGON
                if H3_AVAILABLE and sender_h3:
                    # Z H3: sprawdź per-hex
                    cursor.execute("""
                        SELECT id FROM traceroute_packets
                        WHERE sender_node = ?
                          AND hop_node = ?
                          AND sender_h3 = ?
                          AND is_confirmed = 1
                          AND DATE(received_at) = DATE('now')
                        LIMIT 1
                    """, (sender_node, hop_node, sender_h3))
                else:
                    # Bez H3: stara logika (globalnie per-hop)
                    cursor.execute("""
                        SELECT id FROM traceroute_packets
                        WHERE sender_node = ?
                          AND hop_node = ?
                          AND is_confirmed = 1
                          AND DATE(received_at) = DATE('now')
                        LIMIT 1
                    """, (sender_node, hop_node))

                already_today = cursor.fetchone()

                # Jeśli już dzisiaj był potwierdzony traceroute do tego hopu (w tym hex) - brak punktów
                if already_today:
                    points = 0
                    hex_info = f" w hex {sender_h3}" if sender_h3 else ""
                    logger.debug(f"Traceroute {sender_node}→{hop_node} już dziś był{hex_info} (potwierdzony), 0 pkt")
                else:
                    points = potential_points
                    hex_info = f" w hex {sender_h3}" if sender_h3 else ""
                    logger.debug(f"Pierwszy potwierdzony traceroute dzisiaj {sender_node}→{hop_node}{hex_info}, {points} pkt")

            # Przygotuj route_path i route_back jako JSON
            route_path_json = None
            route_back_json = None
            if route_path:
                route_path_json = json.dumps(route_path)
            if route_back:
                route_back_json = json.dumps(route_back)

            # Zapisz traceroute (z H3 indices)
            cursor.execute("""
                INSERT INTO traceroute_packets (
                    packet_id, sender_node, hop_node, hop_number,
                    sender_latitude, sender_longitude,
                    hop_latitude, hop_longitude,
                    distance_km, points, channel_id, route_path, route_back, is_confirmed,
                    sender_h3, hop_h3
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                packet_id, sender_node, hop_node, hop_number,
                sender_pos[0] if sender_pos else None,
                sender_pos[1] if sender_pos else None,
                hop_pos[0] if hop_pos else None,
                hop_pos[1] if hop_pos else None,
                distance_km, points, channel_id, route_path_json, route_back_json, 1 if is_confirmed else 0,
                sender_h3, hop_h3
            ))

            traceroute_id = cursor.lastrowid

            # Aktualizuj wynik gracza (sender dostaje punkty!)
            if points > 0:
                self._update_player_score(sender_node, points)

                # Aktualizuj punkty w heksagonie gracza (jeśli H3 dostępne)
                if sender_h3:
                    cursor.execute("""
                        UPDATE device_hexagons
                        SET points_earned = points_earned + ?,
                            traceroutes_here = traceroutes_here + 1
                        WHERE node_id = ? AND h3_index = ?
                    """, (points, sender_node, sender_h3))

            self.conn.commit()

            # Logowanie z uwzględnieniem statusu potwierdzenia
            status_emoji = "✅" if is_confirmed else "⏳"
            status_text = "potwierdzony" if is_confirmed else "oczekuje"

            if distance_km:
                if points > 0:
                    logger.info(f"{status_emoji} Gracz {sender_node} traceroute do {hop_node}: {distance_km:.2f}km = {points} pkt ({status_text})")
                else:
                    logger.info(f"{status_emoji} Gracz {sender_node} traceroute do {hop_node}: {distance_km:.2f}km (bez punktów, {status_text})")
            else:
                if points > 0:
                    logger.info(f"{status_emoji} Gracz {sender_node} traceroute do {hop_node} (brak GPS) = {points} pkt ({status_text})")
                else:
                    logger.info(f"{status_emoji} Gracz {sender_node} traceroute do {hop_node} (brak GPS, bez punktów, {status_text})")

            return {
                'id': traceroute_id,
                'packet_id': packet_id,
                'sender_node': sender_node,
                'hop_node': hop_node,
                'distance_km': distance_km,
                'points': points
            }

        except sqlite3.Error as e:
            logger.error(f"Błąd zapisu traceroute: {e}")
            return None

    def _update_player_score(self, node_id: str, points: float):
        """
        Aktualizuje wynik gracza (wewnętrzna metoda)

        Args:
            node_id: ID gracza
            points: Liczba punktów do dodania
        """
        try:
            cursor = self.conn.cursor()

            # INSERT or UPDATE
            cursor.execute("""
                INSERT INTO player_scores (node_id, total_points, total_traceroutes_sent, last_traceroute)
                VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(node_id) DO UPDATE SET
                    total_points = total_points + ?,
                    total_traceroutes_sent = total_traceroutes_sent + 1,
                    last_traceroute = CURRENT_TIMESTAMP
            """, (node_id, points, points))

        except sqlite3.Error as e:
            logger.error(f"Błąd aktualizacji wyniku gracza: {e}")

    def get_highscore(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Pobiera ranking graczy

        Args:
            limit: Maksymalna liczba wyników

        Returns:
            Lista graczy z wynikami, posortowana malejąco
        """
        try:
            cursor = self.conn.cursor()

            cursor.execute("""
                SELECT
                    s.node_id,
                    s.total_points,
                    s.total_traceroutes_sent,
                    s.last_traceroute,
                    d.user_longname,
                    d.user_shortname,
                    d.channel_id,
                    d.last_latitude,
                    d.last_longitude
                FROM player_scores s
                LEFT JOIN devices d ON s.node_id = d.node_id
                WHERE s.total_points > 0 AND d.is_player = 1
                ORDER BY s.total_points DESC, s.total_traceroutes_sent DESC
                LIMIT ?
            """, (limit,))

            rows = cursor.fetchall()
            results = []

            for row in rows:
                results.append({
                    'node_id': row[0],
                    'total_points': row[1],
                    'total_traceroutes_sent': row[2],
                    'last_traceroute': row[3],
                    'user_longname': row[4],
                    'user_shortname': row[5],
                    'channel_id': row[6],
                    'last_latitude': row[7],
                    'last_longitude': row[8]
                })

            return results

        except sqlite3.Error as e:
            logger.error(f"Błąd pobierania highscore: {e}")
            return []

    def get_highscore_period(self, period: str = 'all', limit: int = 100) -> List[Dict[str, Any]]:
        """
        Pobiera ranking graczy dla danego okresu

        Args:
            period: Okres - 'today', 'week', 'month', 'all'
            limit: Maksymalna liczba wyników

        Returns:
            Lista graczy z wynikami dla danego okresu, posortowana malejąco
        """
        try:
            cursor = self.conn.cursor()

            # Określ warunek WHERE dla okresu
            if period == 'today':
                date_condition = "DATE(t.received_at) = DATE('now')"
            elif period == 'week':
                # Bieżący tydzień (rok-numer tygodnia)
                date_condition = "strftime('%Y-%W', t.received_at) = strftime('%Y-%W', 'now')"
            elif period == 'month':
                # Bieżący miesiąc
                date_condition = "strftime('%Y-%m', t.received_at) = strftime('%Y-%m', 'now')"
            else:
                # 'all' - wszystkie czasy
                date_condition = "1=1"

            # Sumuj punkty z traceroute_packets dla danego okresu
            cursor.execute(f"""
                SELECT
                    t.sender_node as node_id,
                    SUM(t.points) as total_points,
                    COUNT(*) as total_traceroutes,
                    MAX(t.received_at) as last_traceroute,
                    d.user_longname,
                    d.user_shortname,
                    d.channel_id,
                    d.last_latitude,
                    d.last_longitude
                FROM traceroute_packets t
                LEFT JOIN devices d ON t.sender_node = d.node_id
                WHERE {date_condition}
                  AND d.is_player = 1
                  AND t.points > 0
                GROUP BY t.sender_node
                HAVING total_points > 0
                ORDER BY total_points DESC, total_traceroutes DESC
                LIMIT ?
            """, (limit,))

            rows = cursor.fetchall()
            results = []

            for row in rows:
                results.append({
                    'node_id': row[0],
                    'total_points': row[1],
                    'total_traceroutes': row[2],
                    'last_traceroute': row[3],
                    'user_longname': row[4],
                    'user_shortname': row[5],
                    'channel_id': row[6],
                    'last_latitude': row[7],
                    'last_longitude': row[8]
                })

            return results

        except sqlite3.Error as e:
            logger.error(f"Błąd pobierania highscore dla okresu {period}: {e}")
            return []

    def get_period_winners(self, period_type: str = 'day', limit: int = 50) -> List[Dict[str, Any]]:
        """
        Pobiera zwycięzców z zakończonych okresów (dni, tygodni, miesięcy)

        Args:
            period_type: Typ okresu - 'day', 'week', 'month'
            limit: Maksymalna liczba okresów do pobrania

        Returns:
            Lista zwycięzców z każdego okresu
        """
        try:
            cursor = self.conn.cursor()

            # Określ format daty dla grupowania
            if period_type == 'day':
                date_format = "%Y-%m-%d"
                date_condition = "DATE(t.received_at) < DATE('now')"  # Tylko zakończone dni
                period_label = "Dzień"
            elif period_type == 'week':
                date_format = "%Y-%W"  # Rok-tydzień
                date_condition = "strftime('%Y-%W', t.received_at) < strftime('%Y-%W', 'now')"
                period_label = "Tydzień"
            elif period_type == 'month':
                date_format = "%Y-%m"  # Rok-miesiąc
                date_condition = "strftime('%Y-%m', t.received_at) < strftime('%Y-%m', 'now')"
                period_label = "Miesiąc"
            else:
                return []

            # Dla każdego okresu znajdź gracza z największą liczbą punktów
            cursor.execute(f"""
                WITH period_scores AS (
                    SELECT
                        strftime('{date_format}', t.received_at) as period,
                        t.sender_node,
                        SUM(t.points) as points,
                        COUNT(*) as traceroutes,
                        d.user_longname,
                        d.user_shortname
                    FROM traceroute_packets t
                    LEFT JOIN devices d ON t.sender_node = d.node_id
                    WHERE {date_condition}
                      AND d.is_player = 1
                      AND t.points > 0
                    GROUP BY period, t.sender_node
                ),
                ranked AS (
                    SELECT
                        period,
                        sender_node,
                        points,
                        traceroutes,
                        user_longname,
                        user_shortname,
                        ROW_NUMBER() OVER (PARTITION BY period ORDER BY points DESC, traceroutes DESC) as rank
                    FROM period_scores
                )
                SELECT
                    period,
                    sender_node as node_id,
                    points as total_points,
                    traceroutes as total_traceroutes,
                    user_longname,
                    user_shortname
                FROM ranked
                WHERE rank = 1
                ORDER BY period DESC
                LIMIT ?
            """, (limit,))

            rows = cursor.fetchall()
            results = []

            for row in rows:
                results.append({
                    'period': row[0],
                    'period_type': period_type,
                    'period_label': period_label,
                    'node_id': row[1],
                    'total_points': row[2],
                    'total_traceroutes': row[3],
                    'user_longname': row[4],
                    'user_shortname': row[5]
                })

            return results

        except sqlite3.Error as e:
            logger.error(f"Błąd pobierania zwycięzców dla {period_type}: {e}")
            return []

    def get_traceroutes(self, sender_node: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Pobiera historię traceroute'ów

        Args:
            sender_node: Opcjonalnie filtruj po graczu (nadawca traceroute)
            limit: Maksymalna liczba wyników

        Returns:
            Lista traceroute'ów
        """
        try:
            cursor = self.conn.cursor()

            if sender_node:
                cursor.execute("""
                    SELECT * FROM traceroute_packets
                    WHERE sender_node = ?
                    ORDER BY received_at DESC
                    LIMIT ?
                """, (sender_node, limit))
            else:
                cursor.execute("""
                    SELECT * FROM traceroute_packets
                    ORDER BY received_at DESC
                    LIMIT ?
                """, (limit,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Błąd pobierania traceroute: {e}")
            return []

    def get_players(self, channel_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Pobiera wszystkich zarejestrowanych graczy

        Args:
            channel_id: Opcjonalnie filtruj po kanale
            limit: Maksymalna liczba wyników

        Returns:
            Lista graczy jako dict
        """
        try:
            cursor = self.conn.cursor()

            if channel_id:
                cursor.execute("""
                    SELECT * FROM devices
                    WHERE is_player = 1 AND channel_id = ?
                    ORDER BY last_seen DESC
                    LIMIT ?
                """, (channel_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM devices
                    WHERE is_player = 1
                    ORDER BY last_seen DESC
                    LIMIT ?
                """, (limit,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Błąd pobierania graczy: {e}")
            return []

    def get_longest_traceroute(self, node_id: str) -> Optional[Dict[str, Any]]:
        """
        Pobiera informacje o najdłuższym traceroute gracza

        Args:
            node_id: ID gracza

        Returns:
            Dict z informacjami o najdłuższym traceroute lub None
        """
        try:
            cursor = self.conn.cursor()

            cursor.execute("""
                SELECT
                    t.distance_km,
                    t.hop_node,
                    t.points,
                    t.received_at,
                    d.user_longname,
                    d.user_shortname,
                    t.route_path,
                    t.route_back
                FROM traceroute_packets t
                LEFT JOIN devices d ON t.hop_node = d.node_id
                WHERE t.sender_node = ?
                  AND t.distance_km IS NOT NULL
                  AND t.is_confirmed = 1
                ORDER BY t.distance_km DESC
                LIMIT 1
            """, (node_id,))

            row = cursor.fetchone()
            if not row:
                return None

            # Zdekoduj route_path i route_back z JSON
            route_path = None
            route_back = None
            if row[6]:  # route_path
                try:
                    route_path = json.loads(row[6])
                except (json.JSONDecodeError, TypeError):
                    route_path = None
            if row[7]:  # route_back
                try:
                    route_back = json.loads(row[7])
                except (json.JSONDecodeError, TypeError):
                    route_back = None

            hop_name = row[4] or row[1]  # longname lub node_id
            if row[5]:  # shortname
                hop_name = f"{hop_name} ({row[5]})"

            return {
                'distance_km': round(row[0], 2),
                'hop_node': row[1],
                'hop_name': hop_name,
                'points': row[2],
                'received_at': row[3],
                'route_path': route_path,
                'route_back': route_back,
                'hops_forward': len(route_path) if route_path else 0,
                'hops_back': len(route_back) if route_back else 0
            }

        except sqlite3.Error as e:
            logger.error(f"Błąd pobierania najdłuższego traceroute: {e}")
            return None

    # === H3 HEXAGON METHODS ===
    
    def update_device_hex(self, node_id: str, lat: float, lon: float, is_player: bool = False, resolution: int = DEFAULT_H3_RESOLUTION) -> Optional[str]:
        """
        Aktualizuje heksagon urządzenia (gracza lub zwykłego) na podstawie pozycji GPS
        
        Args:
            node_id: ID urządzenia
            lat: Latitude
            lon: Longitude
            is_player: Czy to gracz (True) czy zwykłe urządzenie (False)
            resolution: Rozdzielczość H3 (domyślnie 8)
            
        Returns:
            H3 index lub None jeśli H3 niedostępne lub błąd
        """
        if not H3_AVAILABLE:
            return None
            
        try:
            # Oblicz H3 index
            h3_index = lat_lon_to_h3(lat, lon, resolution)
            if not h3_index:
                return None
            
            cursor = self.conn.cursor()
            
            # Pobierz obecny H3 index gracza
            cursor.execute("SELECT current_h3 FROM devices WHERE node_id = ?", (node_id,))
            row = cursor.fetchone()
            
            if not row:
                logger.warning(f"Urządzenie {node_id} nie istnieje w bazie")
                return None
            
            old_h3 = row[0]
            
            # Jeśli hex się zmienił
            if old_h3 != h3_index:
                # Aktualizuj current_h3 w devices
                cursor.execute("""
                    UPDATE devices
                    SET current_h3 = ?
                    WHERE node_id = ?
                """, (h3_index, node_id))
                
                # Sprawdź czy urządzenie już było w tym heksagonie
                cursor.execute("""
                    SELECT id FROM device_hexagons
                    WHERE node_id = ? AND h3_index = ?
                """, (node_id, h3_index))
                
                if cursor.fetchone():
                    # Już było - tylko aktualizuj last_visit i visit_count
                    cursor.execute("""
                        UPDATE device_hexagons
                        SET last_visit = CURRENT_TIMESTAMP,
                            visit_count = visit_count + 1
                        WHERE node_id = ? AND h3_index = ?
                    """, (node_id, h3_index))
                    
                    device_type = "Gracz" if is_player else "Urządzenie"
                    logger.info(f"🔄 {device_type} {node_id} wrócił do heksagonu {h3_index}")
                else:
                    # Nowy heksagon - dodaj rekord
                    cursor.execute("""
                        INSERT INTO device_hexagons (node_id, h3_index, is_player)
                        VALUES (?, ?, ?)
                    """, (node_id, h3_index, 1 if is_player else 0))
                    
                    device_type = "Gracz" if is_player else "Urządzenie"
                    logger.info(f"🆕 {device_type} {node_id} odwiedził NOWY heksagon {h3_index}")
                
                self.conn.commit()
                
                # Jeśli to nowy heksagon i GRACZ, przyznaj bonus (TYLKO dla graczy!)
                if is_player and old_h3 is not None:  # Nie przy pierwszej rejestracji
                    self.check_and_award_hex_bonus(node_id, h3_index, old_h3)
            
            return h3_index
            
        except Exception as e:
            logger.error(f"Błąd aktualizacji heksagonu: {e}")
            return None
    
    def check_and_award_hex_bonus(self, node_id: str, new_h3: str, old_h3: Optional[str] = None) -> bool:
        """
        Sprawdza czy gracz odwiedził nowy heksagon i przyznaje bonus +5 pkt
        
        Args:
            node_id: ID gracza
            new_h3: Nowy H3 index
            old_h3: Poprzedni H3 index (opcjonalny)
            
        Returns:
            True jeśli bonus został przyznany, False w przeciwnym razie
        """
        if not H3_AVAILABLE:
            return False
            
        try:
            cursor = self.conn.cursor()
            
            # Sprawdź czy to pierwszy raz w tym heksagonie (visit_count = 1)
            cursor.execute("""
                SELECT visit_count FROM device_hexagons
                WHERE node_id = ? AND h3_index = ?
            """, (node_id, new_h3))
            
            row = cursor.fetchone()
            if not row or row[0] != 1:
                # Nie pierwszy raz lub błąd
                return False
            
            # To pierwszy raz! Przyznaj bonus +50 pkt
            HEX_BONUS = 50
            
            # Aktualizuj player_scores
            cursor.execute("""
                INSERT INTO player_scores (node_id, total_points, hex_bonus_points, unique_hexes_visited, last_traceroute)
                VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(node_id) DO UPDATE SET
                    total_points = total_points + ?,
                    hex_bonus_points = hex_bonus_points + ?,
                    unique_hexes_visited = unique_hexes_visited + 1
            """, (node_id, HEX_BONUS, HEX_BONUS, HEX_BONUS, HEX_BONUS))
            
            # Zapisz informację o bonusie w device_hexagons
            cursor.execute("""
                UPDATE device_hexagons
                SET points_earned = ?
                WHERE node_id = ? AND h3_index = ?
            """, (HEX_BONUS, node_id, new_h3))
            
            self.conn.commit()
            
            logger.info(f"🎁 Gracz {node_id} otrzymał BONUS +{HEX_BONUS} pkt za nowy heksagon {new_h3}")
            
            return True
            
        except Exception as e:
            logger.error(f"Błąd przyznawania bonusu hex: {e}")
            return False
    
    def can_earn_traceroute_points_in_hex(self, node_id: str, h3_index: str, hop_node: str) -> bool:
        """
        Sprawdza czy gracz może zdobyć punkty za traceroute w danym heksagonie
        
        Zasada: Pierwszy traceroute DZISIAJ do danego hop'a W TYM HEKSAGONIE
        
        Args:
            node_id: ID gracza
            h3_index: H3 index gracza
            hop_node: Węzeł docelowy traceroute
            
        Returns:
            True jeśli może zdobyć punkty, False w przeciwnym razie
        """
        if not H3_AVAILABLE:
            # Jeśli H3 niedostępne, używamy starej logiki (bez hex)
            return True
            
        try:
            cursor = self.conn.cursor()
            
            # Sprawdź czy dzisiaj był już traceroute do tego hop'a W TYM HEKSAGONIE
            cursor.execute("""
                SELECT id FROM traceroute_packets
                WHERE sender_node = ?
                  AND hop_node = ?
                  AND sender_h3 = ?
                  AND is_confirmed = 1
                  AND points > 0
                  AND DATE(received_at) = DATE('now')
                LIMIT 1
            """, (node_id, hop_node, h3_index))
            
            already_today = cursor.fetchone()
            
            if already_today:
                logger.debug(f"Traceroute {node_id}→{hop_node} już dzisiaj w hex {h3_index}, 0 pkt")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Błąd sprawdzania możliwości punktów w hex: {e}")
            return False
    
    def get_device_hexagons(self, node_id: str, limit: int = 1000, days: int = 0) -> List[Dict[str, Any]]:
        """
        Pobiera listę odwiedzonych heksagonów przez urządzenie (gracza lub zwykłe)

        Args:
            node_id: ID urządzenia
            limit: Maksymalna liczba wyników
            days: Filtr po liczbie dni wstecz (0 = wszystkie)

        Returns:
            Lista heksagonów jako dict
        """
        if not H3_AVAILABLE:
            return []

        try:
            cursor = self.conn.cursor()

            if days > 0:
                cursor.execute("""
                    SELECT
                        h3_index,
                        is_player,
                        first_visit,
                        last_visit,
                        visit_count,
                        points_earned,
                        traceroutes_here
                    FROM device_hexagons
                    WHERE node_id = ?
                      AND last_visit >= datetime('now', '-' || ? || ' days')
                    ORDER BY last_visit DESC
                    LIMIT ?
                """, (node_id, days, limit))
            else:
                cursor.execute("""
                    SELECT
                        h3_index,
                        is_player,
                        first_visit,
                        last_visit,
                        visit_count,
                        points_earned,
                        traceroutes_here
                    FROM device_hexagons
                    WHERE node_id = ?
                    ORDER BY last_visit DESC
                    LIMIT ?
                """, (node_id, limit))
            
            rows = cursor.fetchall()
            results = []
            
            for row in rows:
                results.append({
                    'h3_index': row[0],
                    'is_player': bool(row[1]),
                    'first_visit': row[2],
                    'last_visit': row[3],
                    'visit_count': row[4],
                    'points_earned': row[5],
                    'traceroutes_here': row[6]
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Błąd pobierania heksagonów gracza: {e}")
            return []
    
    def get_hex_statistics(self, h3_index: str) -> Optional[Dict[str, Any]]:
        """
        Pobiera statystyki dla danego heksagonu
        
        Args:
            h3_index: H3 index
            
        Returns:
            Dict ze statystykami lub None
        """
        if not H3_AVAILABLE:
            return None
            
        try:
            cursor = self.conn.cursor()
            
            # Liczba graczy którzy odwiedzili ten heksagon
            cursor.execute("""
                SELECT COUNT(DISTINCT node_id) FROM device_hexagons
                WHERE h3_index = ? AND is_player = 1
            """, (h3_index,))
            unique_players = cursor.fetchone()[0]
            
            # Liczba zwykłych urządzeń
            cursor.execute("""
                SELECT COUNT(DISTINCT node_id) FROM device_hexagons
                WHERE h3_index = ? AND is_player = 0
            """, (h3_index,))
            unique_devices = cursor.fetchone()[0]
            
            # Całkowita liczba wizyt
            cursor.execute("""
                SELECT SUM(visit_count) FROM device_hexagons
                WHERE h3_index = ?
            """, (h3_index,))
            total_visits = cursor.fetchone()[0] or 0
            
            # Liczba traceroute z tego heksagonu
            cursor.execute("""
                SELECT COUNT(*) FROM traceroute_packets
                WHERE sender_h3 = ? AND is_confirmed = 1
            """, (h3_index,))
            traceroutes_from_hex = cursor.fetchone()[0]
            
            # Całkowite punkty zdobyte w tym heksagonie
            cursor.execute("""
                SELECT SUM(points) FROM traceroute_packets
                WHERE sender_h3 = ?
            """, (h3_index,))
            total_points = cursor.fetchone()[0] or 0
            
            # Ostatnia aktywność
            cursor.execute("""
                SELECT MAX(last_visit) FROM device_hexagons
                WHERE h3_index = ?
            """, (h3_index,))
            last_activity = cursor.fetchone()[0]
            
            return {
                'h3_index': h3_index,
                'unique_players': unique_players,
                'unique_devices': unique_devices,
                'total_visits': total_visits,
                'traceroutes_from_hex': traceroutes_from_hex,
                'total_points': total_points,
                'last_activity': last_activity
            }
            
        except Exception as e:
            logger.error(f"Błąd pobierania statystyk heksagonu: {e}")
            return None
    
    def get_hex_details(self, h3_index: str, limit_traceroutes: int = 50, limit_players: int = 100) -> Optional[Dict[str, Any]]:
        """
        Pobiera szczegółowe informacje o heksagonie włącznie z listą graczy i traceroutes
        
        Args:
            h3_index: H3 index
            limit_traceroutes: Maksymalna liczba traceroutes do zwrócenia
            limit_players: Maksymalna liczba graczy do zwrócenia
            
        Returns:
            Dict ze szczegółowymi danymi lub None
        """
        if not H3_AVAILABLE:
            return None
            
        try:
            cursor = self.conn.cursor()
            
            # Pobierz podstawowe statystyki
            stats = self.get_hex_statistics(h3_index)
            if not stats:
                return None
            
            # Lista urządzeń które odwiedziły ten heksagon
            cursor.execute("""
                SELECT 
                    dh.node_id,
                    d.user_longname,
                    d.user_shortname,
                    dh.is_player,
                    dh.first_visit,
                    dh.last_visit,
                    dh.visit_count,
                    dh.points_earned,
                    dh.traceroutes_here
                FROM device_hexagons dh
                LEFT JOIN devices d ON dh.node_id = d.node_id
                WHERE dh.h3_index = ?
                ORDER BY dh.last_visit DESC
                LIMIT ?
            """, (h3_index, limit_players))
            
            devices_list = []
            for row in cursor.fetchall():
                device_name = row[1] or row[0]  # longname lub node_id
                if row[2]:  # shortname
                    device_name = f"{device_name} ({row[2]})"
                
                devices_list.append({
                    'node_id': row[0],
                    'user_longname': row[1],
                    'user_shortname': row[2],
                    'is_player': bool(row[3]),
                    'display_name': device_name,
                    'first_visit': row[4],
                    'last_visit': row[5],
                    'visit_count': row[6],
                    'points_earned': row[7],
                    'traceroutes_here': row[8]
                })
            
            # Lista traceroutes wykonanych z tego heksagonu
            cursor.execute("""
                SELECT 
                    t.packet_id,
                    t.sender_node,
                    t.hop_node,
                    t.distance_km,
                    t.points,
                    t.received_at,
                    t.is_confirmed,
                    t.route_path,
                    t.route_back,
                    t.hop_number,
                    ds.user_longname as sender_name,
                    ds.user_shortname as sender_short,
                    dh.user_longname as hop_name,
                    dh.user_shortname as hop_short
                FROM traceroute_packets t
                LEFT JOIN devices ds ON t.sender_node = ds.node_id
                LEFT JOIN devices dh ON t.hop_node = dh.node_id
                WHERE t.sender_h3 = ?
                ORDER BY t.received_at DESC
                LIMIT ?
            """, (h3_index, limit_traceroutes))
            
            traceroutes = []
            for row in cursor.fetchall():
                sender_display = row[10] or row[1]  # sender_name lub sender_node
                if row[11]:  # sender_short
                    sender_display = f"{sender_display} ({row[11]})"
                
                hop_display = row[12] or row[2]  # hop_name lub hop_node
                if row[13]:  # hop_short
                    hop_display = f"{hop_display} ({row[13]})"
                
                # Zdekoduj route_path i route_back z JSON
                route_path = None
                route_back = None
                if row[7]:  # route_path
                    try:
                        route_path = json.loads(row[7])
                    except (json.JSONDecodeError, TypeError):
                        route_path = None
                if row[8]:  # route_back
                    try:
                        route_back = json.loads(row[8])
                    except (json.JSONDecodeError, TypeError):
                        route_back = None
                
                traceroutes.append({
                    'packet_id': row[0],
                    'sender_node': row[1],
                    'sender_display': sender_display,
                    'hop_node': row[2],
                    'hop_display': hop_display,
                    'distance_km': round(row[3], 2) if row[3] else 0,
                    'points': row[4],
                    'received_at': row[5],
                    'is_confirmed': bool(row[6]),
                    'route_path': route_path,
                    'route_back': route_back,
                    'hop_number': row[9],
                    'hops_forward': len(route_path) if route_path else 0,
                    'hops_back': len(route_back) if route_back else 0
                })
            
            # Zwróć wszystkie dane
            return {
                'h3_index': h3_index,
                'statistics': stats,
                'devices': devices_list,
                'traceroutes': traceroutes,
                'device_count': len(devices_list),
                'traceroute_count': len(traceroutes)
            }
            
        except Exception as e:
            logger.error(f"Błąd pobierania szczegółów heksagonu: {e}")
            return None
    
    def get_coverage_map(self, limit: int = 10000, min_activity: int = 1) -> List[Dict[str, Any]]:
        """
        Pobiera mapę zasięgu sieci - wszystkie aktywne heksagony

        Args:
            limit: Maksymalna liczba heksagonów
            min_activity: Minimalna liczba wizyt/punktów dla heksagonu

        Returns:
            Lista heksagonów z aktywnością jako dict
        """
        if not H3_AVAILABLE:
            return []

        try:
            cursor = self.conn.cursor()

            # Zoptymalizowane zapytanie - używamy podzapytania zamiast LEFT JOIN dla lepszej wydajności
            cursor.execute("""
                SELECT
                    dh.h3_index,
                    COUNT(DISTINCT CASE WHEN dh.is_player = 1 THEN dh.node_id END) as unique_players,
                    COUNT(DISTINCT CASE WHEN dh.is_player = 0 THEN dh.node_id END) as unique_devices,
                    SUM(dh.visit_count) as total_visits,
                    SUM(dh.points_earned) as hex_bonus_points,
                    (SELECT COUNT(*) FROM traceroute_packets t WHERE t.sender_h3 = dh.h3_index) as traceroutes_count,
                    (SELECT COALESCE(SUM(points), 0) FROM traceroute_packets t WHERE t.sender_h3 = dh.h3_index) as traceroute_points,
                    MAX(dh.last_visit) as last_activity
                FROM device_hexagons dh
                GROUP BY dh.h3_index
                HAVING total_visits >= ?
                ORDER BY total_visits DESC, last_activity DESC
                LIMIT ?
            """, (min_activity, limit))
            
            rows = cursor.fetchall()
            results = []
            
            for row in rows:
                # Określ typ heksagonu: player, device, mixed
                unique_players = row[1]
                unique_devices = row[2]
                if unique_players > 0 and unique_devices > 0:
                    hex_type = "mixed"
                elif unique_players > 0:
                    hex_type = "player"
                else:
                    hex_type = "device"
                
                results.append({
                    'h3_index': row[0],
                    'unique_players': unique_players,
                    'unique_devices': unique_devices,
                    'hex_type': hex_type,
                    'total_visits': row[3],
                    'total_activity': row[3],  # Dodano dla kompatybilności z frontendem
                    'hex_bonus_points': row[4],
                    'traceroutes_count': row[5],
                    'traceroute_points': row[6],
                    'total_points': row[4] + row[6],  # bonus + traceroute points
                    'last_activity': row[7],
                    'activity_level': 'high' if row[3] >= 10 else ('medium' if row[3] >= 5 else 'low')
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Błąd pobierania mapy zasięgu: {e}")
            return []
    
    def get_hex_connections(self, days: int = 31, limit: int = 10000, min_traceroutes: int = 1) -> List[Dict[str, Any]]:
        """
        Pobiera połączenia między heksagonami na podstawie traceroute
        
        Args:
            days: Liczba dni wstecz do filtrowania (domyślnie 31, 0 = wszystkie)
            limit: Maksymalna liczba połączeń
            min_traceroutes: Minimalna liczba traceroute dla połączenia
            
        Returns:
            Lista połączeń jako dict z danymi source/target hex
        """
        if not H3_AVAILABLE:
            return []
            
        try:
            cursor = self.conn.cursor()
            
            # Warunek czasowy
            if days > 0:
                date_condition = f"AND t.received_at >= datetime('now', '-{days} days')"
            else:
                date_condition = ""
            
            # Pobierz unikalne połączenia między hexami
            query = f"""
                SELECT
                    t.sender_h3,
                    t.hop_h3,
                    COUNT(*) as traceroute_count,
                    SUM(t.points) as total_points,
                    AVG(t.distance_km) as avg_distance,
                    MAX(t.received_at) as last_traceroute,
                    COUNT(DISTINCT t.sender_node) as unique_senders
                FROM traceroute_packets t
                WHERE t.sender_h3 IS NOT NULL
                  AND t.hop_h3 IS NOT NULL
                  AND t.is_confirmed = 1
                  {date_condition}
                GROUP BY t.sender_h3, t.hop_h3
                HAVING traceroute_count >= ?
                ORDER BY traceroute_count DESC, last_traceroute DESC
                LIMIT ?
            """
            
            cursor.execute(query, (min_traceroutes, limit))
            
            rows = cursor.fetchall()
            results = []
            
            # Import h3_utils dla konwersji H3 -> GPS
            try:
                from h3_utils import h3_to_lat_lon
            except ImportError:
                logger.error("Brak h3_utils - nie można pobrać współrzędnych hexów")
                return []
            
            for row in rows:
                sender_h3 = row[0]
                hop_h3 = row[1]
                
                # Pobierz współrzędne centrów hexów
                sender_coords = h3_to_lat_lon(sender_h3)
                hop_coords = h3_to_lat_lon(hop_h3)
                
                if not sender_coords or not hop_coords:
                    continue
                
                results.append({
                    'sender_h3': sender_h3,
                    'hop_h3': hop_h3,
                    'sender_lat': sender_coords[0],
                    'sender_lon': sender_coords[1],
                    'hop_lat': hop_coords[0],
                    'hop_lon': hop_coords[1],
                    'traceroute_count': row[2],
                    'total_points': row[3] or 0,
                    'avg_distance': round(row[4], 2) if row[4] else 0,
                    'last_traceroute': row[5],
                    'unique_senders': row[6]
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Błąd pobierania połączeń hexów: {e}")
            return []

    def checkpoint_wal(self):
        """Wykonuje checkpoint WAL dla zapewnienia spójności danych"""
        try:
            if self.conn:
                cursor = self.conn.cursor()
                cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                logger.debug("WAL checkpoint wykonany pomyślnie")
                return True
        except sqlite3.Error as e:
            logger.error(f"Błąd podczas WAL checkpoint: {e}")
            return False

    def verify_integrity(self) -> bool:
        """
        Sprawdza integralność bazy danych

        Returns:
            True jeśli baza jest OK, False jeśli jest uszkodzona
        """
        try:
            if self.conn:
                cursor = self.conn.cursor()
                result = cursor.execute("PRAGMA integrity_check").fetchone()
                if result and result[0] == "ok":
                    logger.debug("Integralność bazy danych: OK")
                    return True
                else:
                    logger.error(f"Integralność bazy danych: BŁĄD - {result[0] if result else 'brak odpowiedzi'}")
                    return False
        except sqlite3.Error as e:
            logger.error(f"Błąd sprawdzania integralności: {e}")
            return False

    def close(self):
        """Zamyka połączenie z bazą danych po wykonaniu checkpoint"""
        if self.conn:
            try:
                # Wykonaj checkpoint przed zamknięciem
                self.checkpoint_wal()
                self.conn.close()
                logger.info("Połączenie z bazą danych zamknięte bezpiecznie")
            except Exception as e:
                logger.error(f"Błąd podczas zamykania bazy danych: {e}")
                try:
                    self.conn.close()
                except:
                    pass

    def __enter__(self):
        """Context manager support"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support"""
        self.close()
