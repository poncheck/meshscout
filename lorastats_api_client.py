#!/usr/bin/env python3
"""
Klient API dla lorastats.pl
Pobiera pakiety Meshtastic z API i przekazuje do dekodera
"""

import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import base64
import requests

try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False

logger = logging.getLogger(__name__)


class LoraStatsAPIClient:
    """Klient API dla lorastats.pl"""

    def __init__(self, region: str = "Warszawa"):
        """
        Inicjalizacja klienta API

        Args:
            region: Region do pobierania danych (domyślnie "Warszawa")
        """
        self.base_url = "https://lorastats.pl/API"
        self.region = region

        # Użyj cloudscraper jeśli dostępny (omija Cloudflare), w przeciwnym razie requests
        if CLOUDSCRAPER_AVAILABLE:
            self.session = cloudscraper.create_scraper()
            logger.info("🔓 Używam cloudscraper (omija Cloudflare)")
        else:
            self.session = requests.Session()
            logger.warning("⚠️  cloudscraper niedostępny, używam requests (może nie działać z Cloudflare)")

        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://lorastats.pl/',
            'DNT': '1'
        })
        self.last_packet_time = None

        logger.info(f"🌐 Zainicjalizowano klienta API lorastats.pl (region: {region})")

    def fetch_packets(self) -> List[Dict[str, Any]]:
        """
        Pobiera pakiety z API

        Returns:
            Lista pakietów w formacie API
        """
        url = f"{self.base_url}/{self.region}/PacketsRaw/JSON"

        try:
            logger.debug(f"📡 Pobieranie danych z {url}")
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()

            # API może zwracać różne formaty, dostosuj według rzeczywistego API
            if isinstance(data, list):
                packets = data
            elif isinstance(data, dict) and 'packets' in data:
                packets = data['packets']
            else:
                logger.warning(f"⚠️  Nieoczekiwany format odpowiedzi API: {type(data)}")
                packets = []

            logger.info(f"✅ Pobrano {len(packets)} pakietów z API")
            return packets

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Błąd pobierania danych z API: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Nieoczekiwany błąd: {e}")
            return []

    def convert_to_mqtt_format(self, api_packet: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Konwertuje pakiet z formatu API na format MQTT

        Args:
            api_packet: Pakiet w formacie API

        Returns:
            Pakiet w formacie MQTT lub None
        """
        try:
            # To jest przykładowa konwersja - dostosuj według rzeczywistego formatu API
            # API lorastats.pl może mieć inną strukturę

            mqtt_packet = {
                'packet': api_packet.get('packet', {}),
                'gateway_id': api_packet.get('gateway_id', ''),
                'channel_id': api_packet.get('channel_id', ''),
                'timestamp': api_packet.get('timestamp', datetime.utcnow().isoformat()),
            }

            return mqtt_packet

        except Exception as e:
            logger.error(f"❌ Błąd konwersji pakietu: {e}")
            return None

    def start_polling(self, callback, interval: int = 60):
        """
        Rozpoczyna cykliczne pobieranie pakietów

        Args:
            callback: Funkcja wywoływana dla każdego pakietu
            interval: Interwał pobierania w sekundach (domyślnie 60)
        """
        logger.info(f"🔄 Rozpoczynam pobieranie pakietów co {interval} sekund")

        while True:
            try:
                packets = self.fetch_packets()

                for api_packet in packets:
                    mqtt_packet = self.convert_to_mqtt_format(api_packet)
                    if mqtt_packet:
                        callback(mqtt_packet)

                time.sleep(interval)

            except KeyboardInterrupt:
                logger.info("⏹️  Zatrzymano pobieranie pakietów")
                break
            except Exception as e:
                logger.error(f"❌ Błąd w pętli pobierania: {e}")
                time.sleep(interval)


if __name__ == '__main__':
    # Test klienta API
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    def test_callback(packet):
        print(f"Otrzymano pakiet: {packet}")

    client = LoraStatsAPIClient(region="Warszawa")

    # Pojedyncze pobranie
    packets = client.fetch_packets()
    print(f"Pobrano {len(packets)} pakietów")

    # Lub ciągłe pobieranie (odkomentuj aby przetestować)
    # client.start_polling(test_callback, interval=60)
