#!/usr/bin/env python3
"""
Message Filter dla Meshtastic MQTT Decoder
Filtruje wiadomości na podstawie kryteriów
"""

import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class MessageFilter:
    """Klasa do filtrowania wiadomości Meshtastic"""

    def __init__(self, filter_config: Optional[Dict[str, Any]] = None):
        """
        Inicjalizacja filtra

        Args:
            filter_config: Konfiguracja filtra
                {
                    "enabled": True/False,
                    "channel_ids": ["mesh-scout"],  # Lista dozwolonych kanałów
                    "hashtags": ["#countme"],        # Lista wymaganych hashtagów
                    "message_types": ["TEXT_MESSAGE_APP"],  # Typy wiadomości
                    "save_all": False,               # Zapisz wszystkie (ignoruj filtry)
                    "require_position": False        # Wymagaj współrzędnych GPS
                }
        """
        self.enabled = True
        self.channel_ids = []
        self.hashtags = []
        self.message_types = []
        self.save_all = False
        self.require_position = False

        if filter_config:
            self.enabled = filter_config.get('enabled', True)
            self.channel_ids = filter_config.get('channel_ids', [])
            self.hashtags = filter_config.get('hashtags', [])
            self.message_types = filter_config.get('message_types', [])
            self.save_all = filter_config.get('save_all', False)
            self.require_position = filter_config.get('require_position', False)

        logger.info(f"Filter initialized: enabled={self.enabled}, channels={self.channel_ids}, "
                   f"hashtags={self.hashtags}, save_all={self.save_all}")

    def should_save(self, decoded_message: Dict[str, Any]) -> tuple[bool, str]:
        """
        Sprawdza czy wiadomość powinna być zapisana

        Args:
            decoded_message: Zdekodowana wiadomość

        Returns:
            Tuple (should_save: bool, reason: str)
        """
        # Jeśli filtr wyłączony, nie zapisuj nic
        if not self.enabled:
            return False, "Filter disabled"

        # Jeśli save_all, zapisz wszystko
        if self.save_all:
            return True, "Save all enabled"

        # Sprawdź channel_id
        channel_id = decoded_message.get('channel_id', '')
        if self.channel_ids and channel_id not in self.channel_ids:
            return False, f"Channel '{channel_id}' not in filter list"

        # Sprawdź typ wiadomości
        packet = decoded_message.get('packet', {})
        # Obsługa zarówno decoded_data (niezaszyfrowane) jak i decrypted_data (zaszyfrowane)
        decoded_data = packet.get('decoded_data') or packet.get('decrypted_data', {})
        message_type = decoded_data.get('portnum_name', '')

        if self.message_types and message_type not in self.message_types:
            return False, f"Message type '{message_type}' not in filter list"

        # Sprawdź hashtagi (tylko dla wiadomości tekstowych)
        if self.hashtags:
            message_text = decoded_data.get('text', '')
            if not message_text:
                return False, "No text message (hashtag filter requires text)"

            # Wyciągnij hashtagi z tekstu
            found_hashtags = re.findall(r'#\w+', message_text.lower())

            # Sprawdź czy któryś z wymaganych hashtagów jest w wiadomości
            hashtags_lower = [h.lower() for h in self.hashtags]
            if not any(hashtag in found_hashtags for hashtag in hashtags_lower):
                return False, f"None of required hashtags {self.hashtags} found in message"

        # Sprawdź czy wymagana pozycja GPS
        if self.require_position:
            position = decoded_data.get('position', {})
            if not position or not position.get('latitude') or not position.get('longitude'):
                return False, "Position required but not present"

        # Wszystkie warunki spełnione
        reasons = []
        if self.channel_ids:
            reasons.append(f"channel={channel_id}")
        if self.hashtags:
            reasons.append(f"hashtags={','.join(found_hashtags)}")
        if self.message_types:
            reasons.append(f"type={message_type}")

        return True, f"Match: {', '.join(reasons)}"

    def get_summary(self) -> Dict[str, Any]:
        """Zwraca podsumowanie konfiguracji filtra"""
        return {
            "enabled": self.enabled,
            "channel_ids": self.channel_ids,
            "hashtags": self.hashtags,
            "message_types": self.message_types,
            "save_all": self.save_all,
            "require_position": self.require_position
        }
