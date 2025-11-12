# Przewodnik użytkowania - Meshtastic MQTT Decoder

## Szybki start

**Uwaga**: Przykłady poniżej używają `./run.sh` który automatycznie aktywuje virtual environment. Alternatywnie możesz użyć `source venv/bin/activate` i uruchamiać bezpośrednio `python3 meshtastic_mqtt_decoder.py`.

### 1. Podstawowe uruchomienie (publiczny serwer)

Najprostszy sposób - połączenie z publicznym serwerem Meshtastic bez deszyfrowania:

```bash
./run.sh
```

Domyślnie łączy się z `mqtt.meshtastic.org` i nasłuchuje wszystkie regiony.

### 2. Konkretny region

```bash
./run.sh --topic "msh/EU_868/2/e/#"
```

### 3. Z deszyfrowaniem

```bash
./run.sh --topic "msh/EU_868/2/e/LongFast/#" --key "1PG7OiApB1nwvP+rz05pAQ=="
```

## Scenariusze użycia

### Scenariusz 1: Monitoring publicznej sieci

Jeśli chcesz monitorować publiczne wiadomości w swojej okolicy:

```bash
./run.sh --broker mqtt.meshtastic.org --topic "msh/EU_868/2/e/#" --verbose
```

### Scenariusz 2: Własna prywatna sieć

Masz własną sieć Meshtastic z prywatnym kanałem:

1. Uzyskaj klucz z urządzenia Meshtastic
2. Utwórz config.json:

```json
{
  "broker": "mqtt.meshtastic.org",
  "topic": "msh/EU_868/2/e/MyPrivateChannel/!1234abcd",
  "channel_key": "TwojBase64KluczTutaj=="
}
```

3. Uruchom:

```bash
./run.sh --config config.json
```

### Scenariusz 3: Lokalny broker MQTT

Masz własny serwer MQTT w sieci lokalnej:

```bash
./run.sh --broker 192.168.1.100 --port 1883 --topic "mesh/#" \
  --username admin --password secretpassword --key "YourChannelKey=="
```

### Scenariusz 4: Wszystkie regiony jednocześnie

```bash
./run.sh \
  --topic "msh/+/2/e/#"
```

Znak `+` to wildcard dla jednego poziomu (zastępuje dowolny region).

## Zaawansowane użycie

### Uruchomienie jako usługa systemd

1. Utwórz plik `/etc/systemd/system/meshtastic-decoder.service`:

```ini
[Unit]
Description=Meshtastic MQTT Decoder
After=network.target

[Service]
Type=simple
User=meshuser
WorkingDirectory=/home/meshuser/mesh-scout
ExecStart=/usr/bin/python3 /home/meshuser/mesh-scout/meshtastic_mqtt_decoder.py --config /home/meshuser/mesh-scout/config.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

2. Aktywuj usługę:

```bash
sudo systemctl daemon-reload
sudo systemctl enable meshtastic-decoder
sudo systemctl start meshtastic-decoder
```

3. Sprawdź status:

```bash
sudo systemctl status meshtastic-decoder
sudo journalctl -u meshtastic-decoder -f
```

### Uruchomienie z Docker

#### Budowanie obrazu

```bash
docker build -t mesh-scout:latest .
```

#### Uruchomienie kontenera

Opcja 1 - z parametrami CLI:

```bash
docker run -d \
  --name meshtastic-decoder \
  --restart unless-stopped \
  mesh-scout:latest \
  --broker mqtt.meshtastic.org \
  --topic "msh/EU_868/2/e/#" \
  --key "YourKeyHere=="
```

Opcja 2 - z plikiem konfiguracyjnym:

```bash
docker run -d \
  --name meshtastic-decoder \
  --restart unless-stopped \
  -v $(pwd)/config.json:/app/config.json:ro \
  mesh-scout:latest \
  --config /app/config.json
```

#### Docker Compose

```bash
# Edytuj docker-compose.yml i config.json
nano docker-compose.yml
nano config.json

# Uruchom
docker compose up -d

# Logi
docker compose logs -f

# Zatrzymaj
docker compose down
```

### Przekierowanie wyjścia do pliku

```bash
./run.sh --config config.json > decoded_messages.json 2>&1
```

### Filtrowanie tylko wiadomości tekstowych (z jq)

```bash
./run.sh --config config.json 2>/dev/null | jq 'select(.packet.decrypted_data.portnum == 1)'
```

### Zapis do bazy danych (przykład z PostgreSQL)

```bash
# Stwórz prosty skrypt Python który używa biblioteki jako modułu
# i zapisuje zdekodowane dane do PostgreSQL
```

## Testowanie

### Test połączenia z brokerem

```bash
./quick-test.sh
```

Ten skrypt sprawdzi połączenie i wyświetli surowe wiadomości (bez dekodowania protobuf).

### Test dekodowania

```bash
# Terminal 1 - uruchom dekoder
./run.sh --topic "msh/EU_868/2/e/#" --verbose

# Poczekaj na wiadomości...
```

## Debugowanie

### Poziom verbose

```bash
./run.sh --config config.json --verbose
```

### Sprawdzenie dostępności brokera

```bash
# Ping
ping mqtt.meshtastic.org

# Test połączenia MQTT (jeśli masz mosquitto-clients)
mosquitto_sub -h mqtt.meshtastic.org -t "msh/#" -v -C 1
```

### Weryfikacja klucza

Upewnij się że klucz:
- Jest w formacie base64
- Ma długość 16 bajtów (AES-128) lub 32 bajty (AES-256) po dekodowaniu
- Nie zawiera białych znaków ani znaków nowej linii

```python
import base64
key_b64 = "1PG7OiApB1nwvP+rz05pAQ=="
key_bytes = base64.b64decode(key_b64)
print(f"Długość klucza: {len(key_bytes)} bajtów")  # Powinno być 16 lub 32
```

## Przykłady integracji

### Integration z Node-RED

1. Zainstaluj node-red-contrib-mqtt
2. Utwórz flow:
   - MQTT In node → Function node (dekodowanie) → Debug

### Integracja z Home Assistant

Dodaj do `configuration.yaml`:

```yaml
mqtt:
  sensor:
    - name: "Meshtastic Node"
      state_topic: "msh/EU_868/2/e/LongFast/!1234abcd"
      value_template: "{{ value_json.packet.from }}"
```

### Webhook do Discord/Slack

Rozbuduj skrypt o wysyłanie webhooków:

```python
import requests

def send_webhook(message):
    webhook_url = "https://discord.com/api/webhooks/..."
    data = {"content": message}
    requests.post(webhook_url, json=data)
```

## Najlepsze praktyki

1. **Bezpieczeństwo**:
   - Nie commituj config.json z kluczami do repozytorium
   - Używaj zmiennych środowiskowych dla wrażliwych danych
   - Rozważ TLS dla produkcji (port 8883)

2. **Wydajność**:
   - Filtruj tematy MQTT na brokerze (używaj konkretnych tematów)
   - Nie subskrybuj `#` jeśli nie potrzebujesz wszystkiego
   - Monitoruj użycie pamięci dla długotrwałych sesji

3. **Monitoring**:
   - Używaj `--verbose` podczas debugowania
   - Implementuj health checks dla produkcji
   - Loguj do pliku z rotacją logów

4. **Skalowanie**:
   - Jeden dekoder może obsłużyć tysiące wiadomości/min
   - Dla większych deploymentów użyj load balancingu MQTT
   - Rozważ message queue (RabbitMQ, Kafka) dla przetwarzania

## FAQ

**Q: Czy mogę używać tego z n8n?**
A: Tak! Użyj n8n MQTT node do subskrypcji, a następnie Function node z tym kodem do dekodowania.

**Q: Czy działa z MQTT over WebSocket?**
A: Nie bezpośrednio, ale możesz użyć proxy (np. mosquitto z WebSocket support).

**Q: Czy mogę odbierać wiadomości z wielu kanałów jednocześnie?**
A: Tak, użyj wildcards w topic, ale będziesz potrzebować różnych kluczy dla różnych kanałów.

**Q: Jak często należy aktualizować pliki protobuf?**
A: Sprawdzaj co kilka miesięcy lub gdy Meshtastic wydaje nową wersję firmware.

## Wsparcie

Problemy? Zobacz [README.md](README.md) sekcja "Rozwiązywanie problemów" lub otwórz issue na GitHub.
