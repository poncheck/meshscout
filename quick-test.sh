#!/bin/bash

# Quick test script - test dekodera bez pełnej instalacji protobuf
# Łączy się z publicznym serwerem Meshtastic i wyświetla surowe wiadomości

echo "=========================================="
echo "Meshtastic MQTT Decoder - Quick Test"
echo "=========================================="
echo ""
echo "Ten skrypt sprawdzi połączenie z publicznym"
echo "serwerem MQTT Meshtastic i wyświetli surowe"
echo "wiadomości (bez dekodowania protobuf)."
echo ""
echo "Naciśnij Ctrl+C aby zatrzymać."
echo ""
echo "Łączenie z mqtt.meshtastic.org..."
echo ""

# Test prostego połączenia MQTT bez dekodowania
if command -v mosquitto_sub &> /dev/null; then
    # Użyj mosquitto_sub jeśli dostępny
    mosquitto_sub -h mqtt.meshtastic.org -t "msh/EU_868/2/e/#" -v
else
    # Fallback do Pythona z podstawowym klientem MQTT
    python3 << 'EOF'
import paho.mqtt.client as mqtt
import sys

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✓ Połączono z brokerem MQTT")
        client.subscribe("msh/EU_868/2/e/#")
        print("✓ Subskrybowano msh/EU_868/2/e/#")
        print("\nOczekiwanie na wiadomości...\n")
    else:
        print(f"✗ Błąd połączenia: {rc}")
        sys.exit(1)

def on_message(client, userdata, msg):
    print(f"{'='*60}")
    print(f"Temat: {msg.topic}")
    print(f"Rozmiar: {len(msg.payload)} bajtów")
    print(f"Payload (hex): {msg.payload.hex()[:100]}...")
    print()

try:
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("mqtt.meshtastic.org", 1883, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print("\n\nZatrzymano.")
except Exception as e:
    print(f"\n✗ Błąd: {e}")
    print("\nSprawdź połączenie internetowe i upewnij się, że:")
    print("  - Port 1883 nie jest zablokowany")
    print("  - Masz zainstalowane: pip3 install paho-mqtt")
    sys.exit(1)
EOF
fi
