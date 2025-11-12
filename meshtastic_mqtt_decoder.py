#!/usr/bin/env python3
"""
Meshtastic MQTT Decoder
Dekoder wiadomości Meshtastic z MQTT z obsługą deszyfrowania i zapisu do bazy
"""

import paho.mqtt.client as mqtt
import json
import base64
import logging
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import argparse
import sys
import os
from typing import Optional, Dict, Any
import struct

# Importy lokalne
try:
    from database import MeshtasticDatabase
    from message_filter import MessageFilter
except ImportError:
    MeshtasticDatabase = None
    MessageFilter = None
    logger_early = logging.getLogger(__name__)
    logger_early.warning("Database/Filter modules not available")

# Importy dla protobuf z pakietu meshtastic
try:
    from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2
except ImportError:
    print("UWAGA: Nie znaleziono modułów protobuf Meshtastic.")
    print("Uruchom: ./setup.sh aby zainstalować pakiet meshtastic")
    print("Lub: pip install meshtastic")
    # Dla celów rozwojowych, kontynuujemy bez nich
    mesh_pb2 = None
    mqtt_pb2 = None
    portnums_pb2 = None
    telemetry_pb2 = None


# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MeshtasticDecoder:
    """Klasa do dekodowania i deszyfrowania wiadomości Meshtastic z MQTT"""

    def __init__(self, broker: str, port: int, topic: str,
                 channel_key: Optional[str] = None, mesh_scout_key: Optional[str] = None,
                 username: Optional[str] = None, password: Optional[str] = None,
                 db_path: Optional[str] = None, filter_config: Optional[Dict[str, Any]] = None):
        """
        Inicjalizacja dekodera

        Args:
            broker: Adres brokera MQTT
            port: Port MQTT (zazwyczaj 1883)
            topic: Temat MQTT do subskrypcji (np. 'msh/EU_868/2/e/#')
            channel_key: Klucz domyślny w base64 (opcjonalny, domyślnie "AQ==")
            mesh_scout_key: Klucz kanału mesh-scout w base64 (opcjonalny)
            username: Nazwa użytkownika MQTT (opcjonalne)
            password: Hasło MQTT (opcjonalne)
            db_path: Ścieżka do bazy danych SQLite (opcjonalne)
            filter_config: Konfiguracja filtra wiadomości (opcjonalne)
        """
        self.broker = broker
        self.port = port
        self.topic = topic

        # Klucz publiczny (zawsze próbujemy - dla traceroute i innych publicznych pakietów)
        # Domyślny klucz Meshtastic (AQ== rozszerzony do pełnej długości AES)
        self.public_key = self._decode_key("1PG7OiApB1nwvP+rz05pAQ==")  # Domyślny klucz publiczny Meshtastic

        # Klucz domyślny (jeśli podany w konfiguracji)
        self.channel_key = self._decode_key(channel_key) if channel_key else None

        # Klucz mesh-scout (opcjonalny - dla zaszyfrowanych pakietów mesh-scout)
        self.mesh_scout_key = self._decode_key(mesh_scout_key) if mesh_scout_key else None
        self.username = username
        self.password = password
        self.client = None

        # Inicjalizacja bazy danych
        self.database = None
        if db_path and MeshtasticDatabase:
            try:
                self.database = MeshtasticDatabase(db_path)
                logger.info(f"Baza danych włączona: {db_path}")
            except Exception as e:
                logger.error(f"Nie udało się zainicjalizować bazy danych: {e}")

        # Inicjalizacja filtra
        self.message_filter = None
        if filter_config and MessageFilter:
            self.message_filter = MessageFilter(filter_config)
            logger.info(f"Filtr wiadomości włączony: {self.message_filter.get_summary()}")

        # Statystyki
        self.stats = {
            "received": 0,
            "saved": 0,
            "filtered": 0,
            "registered": 0
        }

        # Cache ostatnich danych z urządzeń (dla rejestracji)
        # Format: {node_id: {"position": {...}, "user": {...}, "telemetry": {...}, "channel": "..."}}
        self.device_cache = {}

        logger.info(f"Inicjalizacja dekodera dla {broker}:{port}")
        logger.info(f"Temat: {topic}")

        # Pokaż informacje o dostępnych kluczach
        keys_info = ["Klucz publiczny (Meshtastic default)"]
        if self.channel_key:
            keys_info.append("Klucz domyślny (channel_key)")
        if self.mesh_scout_key:
            keys_info.append("Klucz mesh-scout")
        logger.info(f"Dostępne klucze deszyfrowania: {', '.join(keys_info)}")

    @staticmethod
    def _safe_id_to_hex(id_value: Any) -> Optional[str]:
        """Bezpiecznie konwertuje ID na format hex"""
        if id_value is None or id_value == 0:
            return None
        try:
            # Jeśli to string, sprawdź czy już jest w formacie hex
            if isinstance(id_value, str):
                if id_value.startswith('!'):
                    return id_value
                elif id_value.startswith('0x'):
                    return id_value
                else:
                    # Spróbuj sparsować jako int
                    return hex(int(id_value, 16) if len(id_value) == 8 else int(id_value))
            # Jeśli to int, konwertuj na hex
            elif isinstance(id_value, int):
                return hex(id_value)
            else:
                return str(id_value)
        except:
            return str(id_value) if id_value else None

    def _decode_key(self, key_base64: str) -> bytes:
        """Dekoduje klucz z base64"""
        try:
            # Obsługa różnych formatów kluczy
            key = base64.b64decode(key_base64)
            if len(key) not in [0, 16, 32]:
                raise ValueError(f"Nieprawidłowa długość klucza: {len(key)} (wymagane: 0, 16 lub 32 bajtów)")
            logger.info(f"Klucz zdekodowany: {len(key)} bajtów (AES{len(key)*8 if len(key) > 0 else 0})")
            return key
        except Exception as e:
            logger.error(f"Błąd dekodowania klucza: {e}")
            raise

    def _create_nonce(self, packet_id: int, from_node: int) -> bytes:
        """
        Tworzy nonce dla AES-CTR z packet_id i from_node
        Meshtastic używa packet_id (8 bajtów) + from_node (4 bajty) + padding
        """
        # Packet ID (64-bit little-endian)
        nonce = struct.pack('<Q', packet_id)
        # From node (32-bit little-endian)
        nonce += struct.pack('<I', from_node)
        # Padding do 16 bajtów (4 bajty zer)
        nonce += b'\x00' * 4
        return nonce

    def _decrypt_with_key(self, encrypted_payload: bytes, packet_id: int, from_node: int, key: bytes) -> Optional[bytes]:
        """
        Deszyfruje payload używając podanego klucza AES-256-CTR

        Args:
            encrypted_payload: Zaszyfrowany payload
            packet_id: ID pakietu (używane w nonce)
            from_node: ID nadawcy (używane w nonce)
            key: Klucz AES

        Returns:
            Odszyfrowany payload lub None w przypadku błędu
        """
        if not key or len(key) == 0:
            return None

        try:
            # Tworzenie nonce dla CTR mode
            nonce = self._create_nonce(packet_id, from_node)

            # Debug logging
            logger.debug(f"🔍 Próba deszyfrowania:")
            logger.debug(f"  Klucz: {key.hex()[:32]}... (len={len(key)} bajtów)")
            logger.debug(f"  Nonce: {nonce.hex()}")
            logger.debug(f"  Encrypted: {encrypted_payload.hex()[:64]}... (len={len(encrypted_payload)} bajtów)")

            # AES-CTR decryption
            cipher = Cipher(
                algorithms.AES(key),
                modes.CTR(nonce),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            decrypted = decryptor.update(encrypted_payload) + decryptor.finalize()

            logger.debug(f"  Decrypted: {decrypted.hex()[:64]}...")

            # Sprawdź czy deszyfrowanie się powiodło (podstawowa walidacja)
            # Próbujemy sparsować jako protobuf Data
            if mesh_pb2:
                try:
                    data = mesh_pb2.Data()
                    data.ParseFromString(decrypted)
                    # Jeśli się udało, deszyfrowanie prawidłowe
                    logger.debug(f"  ✅ Protobuf OK: portnum={data.portnum}")
                    return decrypted
                except Exception as pb_error:
                    # Deszyfrowanie nie powiodło się - loguj szczegóły
                    logger.debug(f"  ❌ Protobuf parsing failed: {pb_error}")
                    logger.debug(f"  Pierwszych 16 bajtów decrypted: {decrypted[:16].hex()}")
                    return None
            else:
                # Bez protobuf nie możemy zwalidować
                return decrypted

        except Exception as e:
            logger.debug(f"Błąd deszyfrowania: {e}")
            return None

    def _decrypt_payload(self, encrypted_payload: bytes, packet_id: int, from_node: int) -> Optional[bytes]:
        """
        Deszyfruje payload używając trzech kluczy w kolejności:
        1. Publiczny (Meshtastic default) - dla traceroute i innych publicznych pakietów
        2. Domyślny (channel_key) - jeśli podany w konfiguracji
        3. Mesh-scout (mesh_scout_key) - dla zaszyfrowanych pakietów mesh-scout

        Args:
            encrypted_payload: Zaszyfrowany payload
            packet_id: ID pakietu (używane w nonce)
            from_node: ID nadawcy (używane w nonce)

        Returns:
            Odszyfrowany payload lub None w przypadku błędu
        """
        # 1. Najpierw próbuj kluczem publicznym (Meshtastic default) - dla traceroute
        if self.public_key:
            decrypted = self._decrypt_with_key(encrypted_payload, packet_id, from_node, self.public_key)
            if decrypted:
                logger.debug("✅ Odszyfrowano kluczem publicznym (Meshtastic default)")
                return decrypted

        # 2. Spróbuj z kluczem domyślnym (jeśli podany)
        if self.channel_key:
            decrypted = self._decrypt_with_key(encrypted_payload, packet_id, from_node, self.channel_key)
            if decrypted:
                logger.debug("✅ Odszyfrowano kluczem domyślnym (channel_key)")
                return decrypted

        # 3. Na końcu spróbuj z kluczem mesh-scout (jeśli podany)
        if self.mesh_scout_key:
            decrypted = self._decrypt_with_key(encrypted_payload, packet_id, from_node, self.mesh_scout_key)
            if decrypted:
                logger.debug("✅ Odszyfrowano kluczem mesh-scout")
                return decrypted

        logger.warning("⚠️  Nie udało się odszyfrować wiadomości żadnym z dostępnych kluczy")
        return None

    def _decode_protobuf(self, payload: bytes) -> Optional[Dict[str, Any]]:
        """
        Dekoduje protobuf ServiceEnvelope i MeshPacket

        Args:
            payload: Surowy payload protobuf

        Returns:
            Słownik z zdekodowanymi danymi
        """
        if mqtt_pb2 is None or mesh_pb2 is None:
            logger.warning("Moduły protobuf nie są dostępne - zwracam surowe dane")
            return {"raw_payload": base64.b64encode(payload).decode()}

        try:
            # Dekodowanie ServiceEnvelope
            envelope = mqtt_pb2.ServiceEnvelope()
            envelope.ParseFromString(payload)

            result = {
                "channel_id": envelope.channel_id,
                "gateway_id": self._safe_id_to_hex(envelope.gateway_id),
            }

            # Dekodowanie MeshPacket
            if envelope.HasField("packet"):
                packet = envelope.packet

                # Obsługa różnych nazw pól (from_ to_ używa protobuf dla Python)
                # 'from' jest słowem zastrzeżonym w Python, więc protobuf używa 'from_'
                from_id = getattr(packet, 'from_', None) or getattr(packet, 'from', None) or getattr(packet, 'from_node', None)
                to_id = getattr(packet, 'to', None)

                result["packet"] = {
                    "from": self._safe_id_to_hex(from_id),
                    "to": self._safe_id_to_hex(to_id),
                    "packet_id": packet.id,
                    "rx_time": packet.rx_time if packet.rx_time else None,
                    "hop_limit": packet.hop_limit if packet.hop_limit else None,
                    "want_ack": packet.want_ack if hasattr(packet, 'want_ack') else None,
                }

                # Jeśli wiadomość jest zaszyfrowana, próbujemy ją odszyfrować
                if packet.HasField("encrypted") and len(packet.encrypted) > 0:
                    logger.info("Wykryto zaszyfrowaną wiadomość")
                    # Konwertuj from_id z powrotem na int dla deszyfrowania
                    from_node_int = from_id if isinstance(from_id, int) else int(str(from_id), 16) if from_id else 0
                    decrypted = self._decrypt_payload(
                        packet.encrypted,
                        packet.id,
                        from_node_int
                    )

                    if decrypted:
                        # Dekodowanie odszyfrowanego Data
                        try:
                            data = mesh_pb2.Data()
                            data.ParseFromString(decrypted)
                            result["packet"]["decrypted_data"] = self._decode_data(data)
                        except Exception as e:
                            logger.error(f"Błąd dekodowania odszyfrowanych danych: {e}")
                            result["packet"]["decrypted_raw"] = base64.b64encode(decrypted).decode()
                    else:
                        result["packet"]["encrypted"] = True
                        result["packet"]["encrypted_size"] = len(packet.encrypted)

                # Jeśli wiadomość jest niezaszyfrowana (decoded)
                elif packet.HasField("decoded"):
                    result["packet"]["decoded_data"] = self._decode_data(packet.decoded)

            return result

        except Exception as e:
            import traceback
            logger.error(f"Błąd dekodowania protobuf: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            return {"error": str(e), "raw_payload": base64.b64encode(payload).decode()}

    def _decode_data(self, data) -> Dict[str, Any]:
        """Dekoduje obiekt Data z protobuf"""
        result = {
            "portnum": data.portnum,
            "portnum_name": portnums_pb2.PortNum.Name(data.portnum) if portnums_pb2 else str(data.portnum),
        }

        # Dekodowanie payload w zależności od typu portu
        if data.portnum == 1:  # TEXT_MESSAGE_APP
            try:
                result["text"] = data.payload.decode('utf-8')
            except:
                result["payload_raw"] = base64.b64encode(data.payload).decode()

        elif data.portnum == 3:  # POSITION_APP
            try:
                position = mesh_pb2.Position()
                position.ParseFromString(data.payload)
                result["position"] = {
                    "latitude": position.latitude_i / 1e7 if position.latitude_i else None,
                    "longitude": position.longitude_i / 1e7 if position.longitude_i else None,
                    "altitude": position.altitude if position.altitude else None,
                    "time": position.time if position.time else None,
                    "precision_bits": position.precision_bits if position.precision_bits else None,
                }
                # Usuń None values
                result["position"] = {k: v for k, v in result["position"].items() if v is not None}
            except Exception as e:
                logger.debug(f"Błąd dekodowania pozycji: {e}")
                result["payload_raw"] = base64.b64encode(data.payload).decode()

        elif data.portnum == 4:  # NODEINFO_APP
            try:
                user = mesh_pb2.User()
                user.ParseFromString(data.payload)
                result["user"] = {
                    "id": user.id if user.id else None,
                    "longname": user.long_name if user.long_name else None,
                    "shortname": user.short_name if user.short_name else None,
                    "macaddr": base64.b64encode(user.macaddr).decode() if user.macaddr else None,
                    "hw_model": user.hw_model if user.hw_model else None,
                    "role": user.role if hasattr(user, 'role') else None,
                }
                # Usuń None values
                result["user"] = {k: v for k, v in result["user"].items() if v is not None}
            except Exception as e:
                logger.debug(f"Błąd dekodowania user info: {e}")
                result["payload_raw"] = base64.b64encode(data.payload).decode()

        elif data.portnum == 67:  # TELEMETRY_APP
            try:
                telemetry = telemetry_pb2.Telemetry()
                telemetry.ParseFromString(data.payload)
                result["telemetry"] = {}

                # Device metrics
                if telemetry.HasField("device_metrics"):
                    dm = telemetry.device_metrics
                    result["telemetry"]["device_metrics"] = {
                        "battery_level": dm.battery_level if dm.battery_level else None,
                        "voltage": dm.voltage if dm.voltage else None,
                        "channel_utilization": dm.channel_utilization if dm.channel_utilization else None,
                        "air_util_tx": dm.air_util_tx if dm.air_util_tx else None,
                    }
                    result["telemetry"]["device_metrics"] = {k: v for k, v in result["telemetry"]["device_metrics"].items() if v is not None}

                # Environment metrics
                if telemetry.HasField("environment_metrics"):
                    em = telemetry.environment_metrics
                    result["telemetry"]["environment_metrics"] = {
                        "temperature": em.temperature if em.temperature else None,
                        "relative_humidity": em.relative_humidity if em.relative_humidity else None,
                        "barometric_pressure": em.barometric_pressure if em.barometric_pressure else None,
                    }
                    result["telemetry"]["environment_metrics"] = {k: v for k, v in result["telemetry"]["environment_metrics"].items() if v is not None}

                # Power metrics
                if telemetry.HasField("power_metrics"):
                    pm = telemetry.power_metrics
                    result["telemetry"]["power_metrics"] = {
                        "ch1_voltage": pm.ch1_voltage if pm.ch1_voltage else None,
                        "ch1_current": pm.ch1_current if pm.ch1_current else None,
                        "ch2_voltage": pm.ch2_voltage if pm.ch2_voltage else None,
                        "ch2_current": pm.ch2_current if pm.ch2_current else None,
                    }
                    result["telemetry"]["power_metrics"] = {k: v for k, v in result["telemetry"]["power_metrics"].items() if v is not None}

                # Jeśli nie ma żadnych metryk, zwróć pusty dict
                if not result["telemetry"]:
                    result["telemetry"] = {"_note": "No telemetry data available"}

            except Exception as e:
                logger.debug(f"Błąd dekodowania telemetrii: {e}")
                result["payload_raw"] = base64.b64encode(data.payload).decode()

        elif data.portnum == 70:  # TRACEROUTE_APP
            try:
                route_discovery = mesh_pb2.RouteDiscovery()
                route_discovery.ParseFromString(data.payload)

                # Konwertuj route (repeated uint32) na lista hex string
                routes = [f"0x{node_id:08x}" for node_id in route_discovery.route]

                result["traceroute"] = {
                    "route": routes,
                    "snr_towards": list(route_discovery.snr_towards) if route_discovery.snr_towards else [],
                    "route_back": [f"0x{node_id:08x}" for node_id in route_discovery.route_back] if route_discovery.route_back else [],
                    "snr_back": list(route_discovery.snr_back) if route_discovery.snr_back else [],
                }

                logger.info(f"📍 TRACEROUTE: {len(routes)} hopów: {' -> '.join(routes)}")

            except Exception as e:
                logger.debug(f"Błąd dekodowania traceroute: {e}")
                result["payload_raw"] = base64.b64encode(data.payload).decode()

        else:
            result["payload_raw"] = base64.b64encode(data.payload).decode()

        return result

    def _update_device_cache_and_handle_registration(self, decoded: Dict[str, Any]):
        """
        Aktualizuje cache urządzenia i obsługuje komendy rejestracji

        Args:
            decoded: Zdekodowana wiadomość
        """
        if not self.database:
            return

        try:
            # Wyciągnij podstawowe dane
            channel_id = decoded.get('channel_id', '')
            packet = decoded.get('packet', {})
            from_node = packet.get('from', '')

            if not from_node:
                return

            # Inicjalizuj cache dla tego urządzenia jeśli nie istnieje
            if from_node not in self.device_cache:
                self.device_cache[from_node] = {
                    "position": None,
                    "user": None,
                    "telemetry": None,
                    "channel": channel_id
                }

            # Aktualizuj cache z danymi z tej wiadomości
            decoded_data = packet.get('decoded_data') or packet.get('decrypted_data', {})

            # Zaktualizuj pozycję
            if 'position' in decoded_data:
                self.device_cache[from_node]['position'] = decoded_data['position']
                logger.debug(f"Zaktualizowano pozycję dla {from_node}")

            # Zaktualizuj user info
            if 'user' in decoded_data:
                self.device_cache[from_node]['user'] = decoded_data['user']
                logger.debug(f"Zaktualizowano user info dla {from_node}")

            # Zaktualizuj telemetrię
            if 'telemetry' in decoded_data:
                self.device_cache[from_node]['telemetry'] = decoded_data['telemetry']
                logger.debug(f"Zaktualizowano telemetrię dla {from_node}")

            # Zaktualizuj kanał
            if channel_id:
                self.device_cache[from_node]['channel'] = channel_id

            # Sprawdź czy urządzenie jest już zarejestrowane
            # Jeśli tak, aktualizuj jego dane w bazie
            is_registered = self.database.is_device_registered(from_node)

            # Pobierz dane z cache dla tego urządzenia
            cached = self.device_cache.get(from_node, {})

            # Sprawdź czy w tej wiadomości są nowe dane do zaktualizowania
            has_new_data = (
                'position' in decoded_data or
                'user' in decoded_data or
                'telemetry' in decoded_data
            )

            if has_new_data:
                # Zarejestruj/zaktualizuj urządzenie (automatycznie jako zwykłe urządzenie, nie gracz)
                device_id = self.database.register_device(
                    node_id=from_node,
                    channel_id=cached.get('channel', channel_id),
                    position=cached.get('position'),
                    user_info=cached.get('user'),
                    telemetry=cached.get('telemetry'),
                    registration_message=None,
                    increment_messages=False if is_registered else True,  # Inkrementuj tylko przy pierwszym zapisie
                    is_player=False  # Domyślnie zwykłe urządzenie (nie gracz)
                )

                if device_id:
                    # Loguj tylko istotne aktualizacje
                    if not is_registered:
                        logger.info(f"📡 Nowe urządzenie: {from_node}")
                        user = cached.get('user', {})
                        if user.get('longname'):
                            logger.info(f"   👤 Nazwa: {user.get('longname')}")

                    if 'position' in decoded_data:
                        pos = cached.get('position', {})
                        if pos and pos.get('latitude') and pos.get('longitude'):
                            logger.info(f"📍 Pozycja {from_node}: {pos.get('latitude'):.6f}, {pos.get('longitude'):.6f}")

            # H3: Aktualizuj heksagon dla WSZYSTKICH urządzeń z pozycją GPS
            if 'position' in decoded_data:
                pos = decoded_data['position']
                if pos.get('latitude') and pos.get('longitude'):
                    is_player = self.database.is_player(from_node)
                    h3_index = self.database.update_device_hex(
                        from_node,
                        pos['latitude'],
                        pos['longitude'],
                        is_player=is_player
                    )
                    if h3_index:
                        device_type = "Gracz" if is_player else "Urządzenie"
                        logger.debug(f"H3: {device_type} {from_node} w heksagonie {h3_index}")

            # Sprawdź czy to komenda rejestracji
            message_text = decoded_data.get('text', '').strip().lower()
            if message_text == 'registerme':
                logger.info(f"🔔 Otrzymano komendę rejestracji od {from_node}")

                # Zarejestruj urządzenie jako GRACZA (cached już jest zdefiniowane powyżej)
                device_id = self.database.register_device(
                    node_id=from_node,
                    channel_id=cached.get('channel', channel_id),
                    position=cached.get('position'),
                    user_info=cached.get('user'),
                    telemetry=cached.get('telemetry'),
                    registration_message=message_text,
                    increment_messages=True,  # Inkrementuj przy jawnej rejestracji
                    is_player=True  # To jest gracz!
                )

                if device_id:
                    self.stats["registered"] += 1

                    # Informacje o rejestracji
                    pos = cached.get('position', {})
                    if pos and pos.get('latitude') and pos.get('longitude'):
                        lat = pos.get('latitude')
                        lon = pos.get('longitude')
                        alt = pos.get('altitude', 0)
                        logger.info(f"✅ Zarejestrowano GRACZA {from_node}")
                        logger.info(f"   📍 Pozycja: {lat:.6f}, {lon:.6f} (alt: {alt}m)")
                        logger.info(f"   📡 Kanał: {cached.get('channel', 'nieznany')}")

                        user = cached.get('user', {})
                        if user.get('longname'):
                            logger.info(f"   👤 Nazwa: {user.get('longname')}")
                        
                        # H3: Inicjalizuj pierwszy heksagon gracza (z is_player=True)
                        h3_index = self.database.update_device_hex(from_node, lat, lon, is_player=True)
                        if h3_index:
                            logger.info(f"   🔷 Pierwszy heksagon: {h3_index}")
                    else:
                        logger.info(f"✅ Zarejestrowano GRACZA {from_node} (brak pozycji GPS)")
                        logger.info(f"   📡 Kanał: {cached.get('channel', 'nieznany')}")
                else:
                    logger.error(f"❌ Nie udało się zarejestrować gracza {from_node}")

        except Exception as e:
            logger.error(f"Błąd w obsłudze cache/rejestracji: {e}")

    def _handle_traceroute(self, decoded: Dict[str, Any]):
        """
        Obsługuje pakiety traceroute od graczy - przyznaje punkty za każdy hop

        Args:
            decoded: Zdekodowana wiadomość
        """
        if not self.database:
            return

        try:
            # Wyciągnij podstawowe dane
            channel_id = decoded.get('channel_id', '')
            packet = decoded.get('packet', {})
            packet_id = packet.get('packet_id')
            from_node = packet.get('from', '')

            if not packet_id or not from_node:
                return

            # Sprawdź typ pakietu
            decoded_data = packet.get('decoded_data') or packet.get('decrypted_data', {})
            portnum = decoded_data.get('portnum', 0)
            portnum_name = decoded_data.get('portnum_name', '')

            # Traceroute to portnum 70 (TRACEROUTE_APP)
            if portnum != 70 and portnum_name != 'TRACEROUTE_APP':
                return

            # Sprawdź czy mamy zdekodowane traceroute (route)
            traceroute_data = decoded_data.get('traceroute', {})
            route = traceroute_data.get('route', [])
            route_back = traceroute_data.get('route_back', [])
            snr_towards = traceroute_data.get('snr_towards', [])
            to_node = packet.get('to', '')

            # Rozróżnij REQUEST vs RESPONSE:
            # REQUEST: from=gracz, route=[], snr_towards=[], route_back=[]
            # ACK/RESPONSE: from=cel, to=gracz, snr_towards=[...] (oznacza że dotarło!)
            # FULL RESPONSE: from=cel, to=gracz, route=[...], route_back=[...]

            # RESPONSE to każdy pakiet który ma snr_towards (oznacza odpowiedź) lub route_back
            is_response = bool(snr_towards) or (bool(route_back) and len(route_back) > 0)

            if is_response:
                # To jest RESPONSE - sprawdź czy TO jest graczem (odbiorca odpowiedzi)
                if not self.database.is_player(to_node):
                    logger.debug(f"Traceroute RESPONSE {packet_id} do {to_node} - nie jest graczem, pomijam")
                    return
                # W RESPONSE: gracz to TO (odbiorca), cel to FROM (nadawca odpowiedzi)
                player_node = to_node
                target_node = from_node

                # Rozróżnij ACK vs FULL RESPONSE
                if route_back and len(route_back) > 0:
                    logger.info(f"🔍 Traceroute FULL RESPONSE: gracz {player_node} ← {target_node}, route={len(route)} hopów, route_back={len(route_back)} hopów")
                else:
                    logger.info(f"🔍 Traceroute ACK: gracz {player_node} ← {target_node}, snr_towards={snr_towards}")
            else:
                # To jest REQUEST - sprawdź czy FROM jest graczem (nadawca zapytania)
                if not self.database.is_player(from_node):
                    logger.debug(f"Traceroute REQUEST {packet_id} od {from_node} - nie jest graczem, pomijam")
                    return
                # W REQUEST: gracz to FROM (nadawca), cel to TO (odbiorca)
                player_node = from_node
                target_node = to_node
                logger.info(f"🔍 Traceroute REQUEST: gracz {player_node} → {target_node}")

            # Przygotuj route do przetworzenia
            if is_response:
                # RESPONSE: route zawiera węzły pośrednie, dodajemy target na końcu
                if route and target_node not in route:
                    route = route + [target_node]
                elif not route:
                    route = [target_node]
            else:
                # REQUEST: jeśli route puste, użyj target_node (bezpośrednie połączenie)
                if not route and target_node:
                    route = [target_node]
                    logger.info(f"  → Bezpośrednie połączenie (direct) do {target_node}")
                elif not route:
                    logger.debug(f"Traceroute {packet_id} - brak route i brak target, pomijam")
                    return

            # Wykluczenie traceroute przez MQTT gateway (0xffffffff)
            # Takie traceroute idą przez serwery MQTT, nie przez mesh network
            if '0xffffffff' in route or (route_back and '0xffffffff' in route_back):
                logger.info(f"⚠️  Traceroute {player_node} → {target_node} przez MQTT gateway (0xffffffff), pomijam")
                return

            # Pobierz pozycję gracza
            player_pos = None
            if player_node in self.device_cache:
                pos_data = self.device_cache[player_node].get('position', {})
                if pos_data and pos_data.get('latitude') and pos_data.get('longitude'):
                    player_pos = (pos_data['latitude'], pos_data['longitude'])

            if not player_pos:
                device = self.database.get_device(player_node)
                if device and device.get('last_latitude') and device.get('last_longitude'):
                    player_pos = (device['last_latitude'], device['last_longitude'])

            if not player_pos:
                logger.warning(f"  ⚠️  Brak pozycji GPS dla gracza {player_node}, pomijam")
                return

            # H3: Zaktualizuj heksagon gracza PRZED zapisaniem traceroute
            # To zapewnia że gracz ma aktualne current_h3 w bazie
            player_h3 = None
            try:
                from h3_utils import lat_lon_to_h3
                player_h3 = lat_lon_to_h3(player_pos[0], player_pos[1])
                if player_h3:
                    # Aktualizuj H3 gracza (może przyznać bonus jeśli nowy hex)
                    self.database.update_device_hex(player_node, player_pos[0], player_pos[1], is_player=True)
                    logger.debug(f"H3: Zaktualizowano heksagon gracza {player_node}: {player_h3}")
            except Exception as e:
                logger.debug(f"Błąd aktualizacji H3 gracza: {e}")

            # Przetwórz każdy hop
            total_points = 0
            for hop_number, hop_node in enumerate(route, 1):
                # WAŻNE: Sprawdź czy hop_node to nie jest sam gracz!
                if hop_node == player_node:
                    logger.warning(f"⚠️  Pomijam hop {hop_node} - to sam gracz {player_node}!")
                    continue

                # WAŻNE: Pomiń MQTT gateway (0xffffffff) - to nie jest prawdziwy mesh hop
                if hop_node == '0xffffffff':
                    logger.warning(f"⚠️  Pomijam hop 0xffffffff - MQTT gateway!")
                    continue

                # Pobierz pozycję hopu
                hop_pos = None

                # Sprawdź cache
                if hop_node in self.device_cache:
                    pos_data = self.device_cache[hop_node].get('position', {})
                    if pos_data and pos_data.get('latitude') and pos_data.get('longitude'):
                        hop_pos = (pos_data['latitude'], pos_data['longitude'])

                # Sprawdź bazę
                if not hop_pos:
                    device = self.database.get_device(hop_node)
                    if device and device.get('last_latitude') and device.get('last_longitude'):
                        hop_pos = (device['last_latitude'], device['last_longitude'])

                # Zapisz traceroute dla tego hopu
                if hop_pos:
                    # Jeśli to RESPONSE (ACK lub FULL), usuń stary niepotwierdzony REQUEST (z ostatnich 30 sekund)
                    if is_response:
                        self.database.delete_unconfirmed_traceroutes(player_node, hop_node, seconds_old=30)

                    # H3: Oblicz heksagony dla gracza i hop'a
                    from h3_utils import lat_lon_to_h3
                    sender_h3 = lat_lon_to_h3(player_pos[0], player_pos[1]) if player_pos else None
                    hop_h3 = lat_lon_to_h3(hop_pos[0], hop_pos[1]) if hop_pos else None

                    logger.debug(f"  → Zapisuję: gracz={player_node}, hop={hop_node} (hop #{hop_number})")
                    result = self.database.record_traceroute(
                        packet_id=packet_id,
                        sender_node=player_node,  # WAŻNE: gracz który WYSŁAŁ traceroute
                        hop_node=hop_node,
                        sender_pos=player_pos,
                        hop_pos=hop_pos,
                        channel_id=channel_id,
                        hop_number=hop_number,
                        route_path=route,  # Pełna trasa tam (lista wszystkich hopów)
                        route_back=route_back,  # Pełna trasa z powrotem (tylko w FULL RESPONSE)
                        snr_towards=snr_towards,  # SNR - jeśli wypełnione, to ACK/potwierdzenie
                        sender_h3=sender_h3,  # H3 index gracza
                        hop_h3=hop_h3  # H3 index hop'a
                    )

                    if result and result.get('points', 0) > 0:
                        total_points += result['points']
                else:
                    logger.debug(f"  Hop #{hop_number} {hop_node} - brak pozycji GPS")

            if total_points > 0:
                logger.info(f"✅ Gracz {player_node} otrzymał {total_points} pkt za traceroute ({len(route)} hopów)")

        except Exception as e:
            logger.error(f"Błąd w obsłudze traceroute: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    def on_connect(self, client, userdata, flags, rc):
        """Callback wywoływany po połączeniu z brokerem"""
        if rc == 0:
            logger.info("Połączono z brokerem MQTT")
            client.subscribe(self.topic)
            logger.info(f"Subskrybowano temat: {self.topic}")
        else:
            logger.error(f"Błąd połączenia z brokerem: {rc}")

    def on_message(self, client, userdata, msg):
        """Callback wywoływany po otrzymaniu wiadomości"""
        logger.info(f"\n{'='*80}")
        logger.info(f"Nowa wiadomość na: {msg.topic}")

        try:
            self.stats["received"] += 1

            # Sprawdź czy to wiadomość JSON (topic zawiera /json/)
            if '/json/' in msg.topic:
                try:
                    # Dekoduj jako JSON
                    decoded = json.loads(msg.payload.decode('utf-8'))
                    decoded['_format'] = 'json'
                except json.JSONDecodeError:
                    logger.warning("Nie udało się zdekodować jako JSON, próbuję protobuf")
                    decoded = self._decode_protobuf(msg.payload)
            else:
                # Dekodowanie protobuf
                decoded = self._decode_protobuf(msg.payload)

            # Wyświetlenie zdekodowanych danych
            print(json.dumps(decoded, indent=2, ensure_ascii=False))

            # Aktualizacja cache urządzenia i obsługa rejestracji
            self._update_device_cache_and_handle_registration(decoded)

            # Obsługa traceroute - wykrywanie pakietów traceroute od graczy i przyznawanie punktów
            self._handle_traceroute(decoded)

            # Zapis do bazy danych (jeśli włączony)
            if self.database:
                # Jeśli jest filtr, sprawdź czy zapisać
                if self.message_filter:
                    should_save, reason = self.message_filter.should_save(decoded)

                    if should_save:
                        record_id = self.database.save_message(decoded, msg.topic)
                        if record_id:
                            self.stats["saved"] += 1
                            logger.info(f"✓ Zapisano do bazy (ID={record_id}): {reason}")
                        else:
                            logger.warning(f"Nie udało się zapisać do bazy")
                    else:
                        self.stats["filtered"] += 1
                        logger.debug(f"Odfiltrowano: {reason}")
                else:
                    # Brak filtra - zapisuj wszystko
                    record_id = self.database.save_message(decoded, msg.topic)
                    if record_id:
                        self.stats["saved"] += 1
                        logger.debug(f"✓ Zapisano do bazy (ID={record_id})")
                    else:
                        logger.warning(f"Nie udało się zapisać do bazy")

        except Exception as e:
            logger.error(f"Błąd przetwarzania wiadomości: {e}")
            logger.debug(f"Surowy payload (base64): {base64.b64encode(msg.payload).decode()}")

    def on_disconnect(self, client, userdata, rc):
        """Callback wywoływany po rozłączeniu"""
        if rc != 0:
            logger.warning(f"Nieoczekiwane rozłączenie: {rc}")

    def start(self):
        """Uruchamia klienta MQTT i nasłuchuje wiadomości"""
        try:
            # Tłumimy DeprecationWarning dla paho-mqtt
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning)

                # Użycie CallbackAPIVersion dla kompatybilności
                try:
                    import paho.mqtt.client as mqtt_module
                    if hasattr(mqtt_module, 'CallbackAPIVersion'):
                        # Nowa wersja paho-mqtt (2.0+) - użyj VERSION1 dla kompatybilności
                        self.client = mqtt.Client(callback_api_version=mqtt_module.CallbackAPIVersion.VERSION1)
                    else:
                        # Starsza wersja paho-mqtt
                        self.client = mqtt.Client()
                except (AttributeError, TypeError):
                    # Fallback dla starszych wersji
                    self.client = mqtt.Client()

            # Ustawienie callbacków
            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            self.client.on_disconnect = self.on_disconnect

            # Autoryzacja jeśli podano
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)
                logger.info("Skonfigurowano autoryzację MQTT")

            # Połączenie z brokerem
            logger.info(f"Łączenie z {self.broker}:{self.port}...")
            self.client.connect(self.broker, self.port, 60)

            # Rozpoczęcie nasłuchiwania (blokujące)
            logger.info("Nasłuchiwanie wiadomości... (Ctrl+C aby zatrzymać)")
            self.client.loop_forever()

        except KeyboardInterrupt:
            logger.info("\nZatrzymywanie...")
        except Exception as e:
            logger.error(f"Błąd: {e}")
        finally:
            if self.client:
                self.client.disconnect()

            # Wyświetl statystyki
            logger.info("\n" + "="*80)
            logger.info("STATYSTYKI:")
            logger.info(f"  Otrzymane wiadomości: {self.stats['received']}")
            logger.info(f"  Zapisane do bazy: {self.stats['saved']}")
            logger.info(f"  Odfiltrowane: {self.stats['filtered']}")
            logger.info(f"  Zarejestrowane urządzenia: {self.stats['registered']}")

            if self.database:
                db_stats = self.database.get_statistics()
                logger.info(f"\n  Łącznie w bazie: {db_stats.get('total_messages', 0)}")
                logger.info(f"  Unikalne węzły: {db_stats.get('unique_nodes', 0)}")

                # Pokaż statystyki zarejestrowanych urządzeń
                devices = self.database.get_all_devices(limit=2000)
                if devices:
                    logger.info(f"  Zarejestrowane urządzenia: {len(devices)}")

            # Zamknij bazę danych
            if self.database:
                self.database.close()


def main():
    """Główna funkcja programu"""
    parser = argparse.ArgumentParser(
        description='Dekoder wiadomości Meshtastic z MQTT',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady użycia:

  # Publiczny serwer MQTT Meshtastic (tylko niezaszyfrowane wiadomości)
  python3 meshtastic_mqtt_decoder.py --broker mqtt.meshtastic.org --topic "msh/EU_868/2/e/#"

  # Własny serwer z deszyfrowaniem
  python3 meshtastic_mqtt_decoder.py --broker 192.168.1.100 --topic "mesh/#" --key "1PG7OiApB1nwvP+rz05pAQ=="

  # Z konfiguracją z pliku
  python3 meshtastic_mqtt_decoder.py --config config.json

Uwagi:
  - Klucz kanału musi być w formacie base64 (16 lub 32 bajtów dla AES128/256)
  - Domyślny klucz "AQ==" to klucz publiczny (brak szyfrowania)
  - Temat może zawierać wildcardy MQTT: + (jeden poziom) lub # (wszystkie poziomy)
        """
    )

    parser.add_argument('--config', type=str, help='Plik konfiguracyjny JSON')
    parser.add_argument('--broker', type=str,
                        help='Adres brokera MQTT')
    parser.add_argument('--port', type=int,
                        help='Port MQTT')
    parser.add_argument('--topic', type=str,
                        help='Temat MQTT')
    parser.add_argument('--key', type=str,
                        help='Klucz kanału domyślny w base64 (domyślnie "AQ==")')
    parser.add_argument('--mesh-scout-key', type=str,
                        help='Klucz kanału mesh-scout w base64')
    parser.add_argument('--username', type=str,
                        help='Nazwa użytkownika MQTT')
    parser.add_argument('--password', type=str,
                        help='Hasło MQTT')
    parser.add_argument('--verbose', action='store_true',
                        help='Szczegółowe logowanie')

    args = parser.parse_args()

    # Ustawienie poziomu logowania
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Wczytanie konfiguracji z pliku jeśli podano
    config = {}
    if args.config:
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
            logger.info(f"Wczytano konfigurację z {args.config}")
        except Exception as e:
            logger.error(f"Błąd wczytywania konfiguracji: {e}")
            sys.exit(1)

    # Parametry: CLI ma priorytet, potem config.json, potem wartości domyślne
    broker = args.broker if args.broker is not None else config.get('broker', 'mqtt.meshtastic.org')
    port = args.port if args.port is not None else config.get('port', 1883)
    topic = args.topic if args.topic is not None else config.get('topic', 'msh/#')
    key = args.key if args.key is not None else config.get('channel_key')
    mesh_scout_key = getattr(args, 'mesh_scout_key', None) if hasattr(args, 'mesh_scout_key') else config.get('mesh_scout_key')
    username = args.username if args.username is not None else config.get('username')
    password = args.password if args.password is not None else config.get('password')

    # Baza danych i filtr z pliku konfiguracyjnego
    db_path = config.get('database', {}).get('path') if config.get('database', {}).get('enabled') else None
    filter_config = config.get('filter') if config.get('filter', {}).get('enabled') else None

    # Utworzenie i uruchomienie dekodera
    decoder = MeshtasticDecoder(
        broker=broker,
        port=port,
        topic=topic,
        channel_key=key,
        mesh_scout_key=mesh_scout_key,
        username=username,
        password=password,
        db_path=db_path,
        filter_config=filter_config
    )

    decoder.start()


if __name__ == "__main__":
    main()
