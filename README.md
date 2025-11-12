# 📡 Mesh Scout - Meshtastic MQTT Tracker

System do śledzenia i wizualizacji urządzeń Meshtastic z MQTT z pełnym wsparciem dla deszyfrowania protokołu AES-256-CTR oraz interfejsem webowym z mapą.

## 🎯 Główne funkcje

### 📊 Interfejs Webowy
- 🗺️ **Interaktywna mapa** - wizualizacja wszystkich zarejestrowanych urządzeń
- 📍 **Śledzenie pozycji GPS** - automatyczna aktualizacja lokalizacji urządzeń
- 🔋 **Telemetria** - bateria, napięcie, wysokość, statystyki
- 🔄 **Auto-refresh** - dane odświeżają się co 30 sekund
- 📋 **Lista urządzeń** - szybki dostęp do szczegółów każdego urządzenia

### 🔐 Dekoder MQTT
- ✅ Dekodowanie pakietów Protobuf (ServiceEnvelope, MeshPacket)
- ✅ Deszyfrowanie wiadomości z użyciem klucza kanału (AES-128/256-CTR)
- ✅ Obsługa wielu typów wiadomości (tekstowe, pozycja, telemetria, info o nodach)
- ✅ Filtrowanie wiadomości (hashtagi, kanały, typy)
- ✅ Rejestracja urządzeń przez komendę "registerme"

### 💾 Baza danych
- 📝 Zapis wszystkich wiadomości do SQLite
- 👥 Rejestr urządzeń z ostatnimi znanymi pozycjami
- 📈 Statystyki i historia aktywności
- 🔍 Narzędzia do przeglądania i eksportu danych

## Wymagania

- Python 3.7+ (z modułem venv)
- pip3 (zazwyczaj wbudowany w Python)
- git (tylko do klonowania repozytorium)

**Nie potrzebujesz**: protoc, kompilatorów, dodatkowych narzędzi!

### Systemy operacyjne

Testowane na:
- Ubuntu/Debian Linux (18.04+, 20.04, 22.04, 24.04)
- CentOS/RHEL/Fedora
- macOS

## Instalacja

### Szybki start

```bash
# Sklonuj repozytorium
git clone https://github.com/poncheck/mesh-scout.git
cd mesh-scout

# Uruchom setup (utworzy venv i zainstaluje zależności)
chmod +x setup.sh
./setup.sh

# Gotowe! Możesz teraz uruchomić dekoder
./run.sh --help
```

**Uwaga**:
- Setup automatycznie tworzy virtual environment (venv)
- Instaluje pakiet `meshtastic` który zawiera wszystkie potrzebne protobuf
- Nie wymaga protoc ani kompilacji - wszystko działa od razu!

### Instalacja manualna

Jeśli wolisz zainstalować komponenty ręcznie:

```bash
# 1. Zainstaluj zależności systemowe
sudo apt-get install python3 python3-venv  # Ubuntu/Debian
# lub
sudo yum install python3                   # CentOS/RHEL

# 2. Utwórz i aktywuj virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Zainstaluj pakiety Python (zawierają protobuf)
pip install -r requirements.txt

# 4. Gotowe! Uruchom dekoder
python3 meshtastic_mqtt_decoder.py --help
```

**Zalecane**: Użyj `./setup.sh` i `./run.sh` - automatyzują wszystko powyżej!

## 🚀 Szybki start z Docker Compose (ZALECANE)

Najprostszy sposób na uruchomienie całego systemu (dekoder MQTT + web interface):

```bash
# 1. Sklonuj repozytorium
git clone https://github.com/poncheck/mesh-scout.git
cd mesh-scout

# 2. Skopiuj i dostosuj konfigurację
cp config.example.json config.json
nano config.json  # edytuj parametry MQTT i klucz kanału

# 3. WAŻNE: W config.json ustaw ścieżkę bazy danych na:
#    "path": "/data/mesh_scout.db"

# 4. Utwórz katalog na dane
mkdir -p data

# 5. Uruchom wszystkie serwisy
docker compose up -d

# 6. Sprawdź logi
docker compose logs -f

# 7. Otwórz interfejs webowy
# http://localhost:5000
```

**Co się uruchomi:**
- 🔧 `mqtt-decoder` - odbiera i dekoduje wiadomości z MQTT
- 🌐 `web-server` - interfejs webowy z mapą urządzeń
- 💾 Współdzielona baza SQLite w katalogu `./data/`

Więcej informacji: [WEB_README.md](WEB_README.md)

## Użycie

### Metoda 1: Używając wrapper script (ZALECANE)

```bash
# Publiczny serwer Meshtastic (tylko niezaszyfrowane wiadomości)
./run.sh --broker mqtt.meshtastic.org --topic "msh/EU_868/2/e/#"

# Z deszyfrowaniem (prywatny kanał)
./run.sh --topic "msh/EU_868/2/e/LongFast/!abc12345" --key "1PG7OiApB1nwvP+rz05pAQ=="

# Lokalny broker z autoryzacją
./run.sh --broker 192.168.1.100 --topic "mesh/#" --key "YourKey==" --username user --password pass

# Z pliku konfiguracyjnego
cp config.example.json config.json
nano config.json  # edytuj konfigurację
./run.sh --config config.json
```

### Metoda 2: Aktywując venv ręcznie

```bash
source venv/bin/activate
python3 meshtastic_mqtt_decoder.py --help
python3 meshtastic_mqtt_decoder.py --config config.json
deactivate  # gdy skończysz
```

## Konfiguracja

### Format pliku config.json

```json
{
  "broker": "mqtt.meshtastic.org",
  "port": 1883,
  "topic": "msh/EU_868/2/e/#",
  "channel_key": "1PG7OiApB1nwvP+rz05pAQ==",
  "username": null,
  "password": null
}
```

### Parametry

| Parametr | Opis | Domyślnie |
|----------|------|-----------|
| `--broker` | Adres brokera MQTT | `mqtt.meshtastic.org` |
| `--port` | Port MQTT | `1883` |
| `--topic` | Temat MQTT (obsługuje wildcards: `#`, `+`) | `msh/#` |
| `--key` | Klucz kanału w base64 (16 lub 32 bajty) | `null` |
| `--username` | Nazwa użytkownika MQTT | `null` |
| `--password` | Hasło MQTT | `null` |
| `--config` | Ścieżka do pliku konfiguracyjnego JSON | - |
| `--verbose` | Szczegółowe logowanie | `false` |

## Jak uzyskać klucz kanału?

### Z aplikacji Meshtastic

1. **Aplikacja mobilna** (Android/iOS):
   - Otwórz ustawienia kanału
   - Kliknij "Share" lub "QR Code"
   - Skopiuj URL (np. `https://meshtastic.org/e/#CgUYAyIBAQ`)
   - Klucz to część `CgUYAyIBAQ` (to przykład, użyj swojego!)

2. **Meshtastic CLI**:
   ```bash
   meshtastic --info
   # Sprawdź sekcję "Channels" -> "Primary PSK"
   ```

3. **Z linku QR**:
   - Dekoduj QR code do URL
   - Wyciągnij fragment z base64 po `#`

### Uwagi o kluczach

- **Domyślny klucz** `AQ==` = brak szyfrowania (publiczny)
- **AES-128**: 16 bajtów (np. `1PG7OiApB1nwvP+rz05pAQ==`)
- **AES-256**: 32 bajty (mocniejsze szyfrowanie)
- Klucz musi być w formacie **base64**

## Tematy MQTT (Topics)

### Format

```
msh/<region>/<version>/e/<channel>/<node_id>
```

### Przykłady

- `msh/EU_868/2/e/#` - Wszystkie wiadomości z regionu EU_868
- `msh/US/2/e/LongFast/#` - Kanał "LongFast" w regionie US
- `msh/+/2/e/#` - Wszystkie regiony (wildcard `+`)
- `msh/#` - Wszystko (wildcard `#`)

### Dostępne regiony

`US`, `EU_433`, `EU_868`, `CN`, `JP`, `ANZ`, `KR`, `TW`, `RU`, `IN`, `NZ_865`, `TH`, `UA_433`, `UA_868`, `MY_433`, `MY_919`, `SG_923`, `LORA_24`

## Przykłady wyjścia

### Wiadomość tekstowa (odszyfrowana)

```json
{
  "channel_id": "LongFast",
  "gateway_id": "0x1234abcd",
  "packet": {
    "from": "0xabcd1234",
    "to": "0xffffffff",
    "packet_id": 123456789,
    "rx_time": 1698765432,
    "hop_limit": 3,
    "decrypted_data": {
      "portnum": 1,
      "portnum_name": "TEXT_MESSAGE_APP",
      "text": "Witaj świecie!"
    }
  }
}
```

### Wiadomość zaszyfrowana (bez klucza)

```json
{
  "channel_id": "LongFast",
  "gateway_id": "0x1234abcd",
  "packet": {
    "from": "0xabcd1234",
    "to": "0xffffffff",
    "packet_id": 123456789,
    "encrypted": true,
    "encrypted_size": 64
  }
}
```

## Rozwiązywanie problemów

### Błąd: "externally-managed-environment"

Ten błąd występuje na nowszych wersjach Debiana/Ubuntu. Setup automatycznie używa virtual environment - po prostu uruchom:
```bash
./setup.sh
```

Jeśli nadal masz problem:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Błąd: "Virtual environment nie istnieje"

Uruchom setup aby utworzyć venv:
```bash
./setup.sh
```

### Błąd: "Nie znaleziono modułów protobuf Meshtastic"

Pakiet meshtastic nie został zainstalowany. Uruchom ponownie:
```bash
./setup.sh
```

Lub zainstaluj manualnie:
```bash
source venv/bin/activate
pip install meshtastic
```

### Błąd połączenia z MQTT

Sprawdź:
- Czy broker jest dostępny: `ping mqtt.meshtastic.org`
- Czy port 1883 nie jest blokowany przez firewall
- Czy wymagane jest uwierzytelnienie (username/password)

### Nie udaje się odszyfrować wiadomości

Sprawdź:
- Czy klucz jest poprawny (base64)
- Czy klucz ma odpowiednią długość (16 lub 32 bajty)
- Czy wiadomość rzeczywiście jest zaszyfrowana tym kluczem
- Czy kanał używa tego samego klucza co twój dekoder

## Struktura projektu

```
mesh-scout/
├── meshtastic_mqtt_decoder.py   # Główny skrypt dekodera
├── run.sh                        # Wrapper script (uruchamia dekoder w venv)
├── setup.sh                      # Skrypt instalacyjny
├── quick-test.sh                 # Szybki test połączenia MQTT
├── requirements.txt              # Zależności Python
├── config.example.json           # Przykładowa konfiguracja
├── Dockerfile                    # Obraz Docker
├── docker-compose.yml            # Docker Compose config
├── meshtastic-decoder.service    # Systemd service
├── README.md                     # Ten plik
├── USAGE.md                      # Szczegółowy przewodnik użycia
├── LICENSE                       # Licencja MIT
├── .gitignore                    # Pliki ignorowane przez git
├── venv/                         # Virtual environment (tworzone przez setup.sh)
└── meshtastic/                   # Wygenerowane pliki protobuf (po setup.sh)
    ├── __init__.py
    ├── mesh_pb2.py
    ├── mqtt_pb2.py
    ├── portnums_pb2.py
    └── ...
```

## Rozwój projektu

Ten projekt to fundament dla dalszej aplikacji. Możliwe rozszerzenia:

- 🔄 Zapis danych do bazy danych (InfluxDB, PostgreSQL)
- 📊 Dashboard wizualizacyjny (Grafana, własny web UI)
- 🗺️ Mapa węzłów Meshtastic w czasie rzeczywistym
- 📡 Analiza zasięgu i routing
- 🔔 Powiadomienia o wydarzeniach
- 🌐 API REST/WebSocket
- 🐳 Konteneryzacja (Docker)

## Bezpieczeństwo

⚠️ **Ważne uwagi bezpieczeństwa:**

- NIE udostępniaj publicznie swoich kluczy kanałów
- Używaj silnych haseł dla brokerów MQTT
- Rozważ TLS/SSL dla produkcji (port 8883)
- Nie commituj `config.json` z wrażliwymi danymi do git
- Klucz domyślny `AQ==` to **brak szyfrowania** - zmień go!

## Licencja

MIT License - możesz swobodnie używać i modyfikować ten kod.

## Autor

Stworzony dla projektu mesh-scout

## Linki

- [Dokumentacja Meshtastic](https://meshtastic.org/docs/)
- [Meshtastic MQTT](https://meshtastic.org/docs/software/integrations/mqtt/)
- [Meshtastic Protobufs](https://github.com/meshtastic/protobufs)
- [Paho MQTT](https://pypi.org/project/paho-mqtt/)

## Wsparcie

Jeśli napotkasz problemy:
1. Sprawdź sekcję "Rozwiązywanie problemów" powyżej
2. Uruchom z flagą `--verbose` dla szczegółowych logów
3. Otwórz issue na GitHub

---

**Uwaga**: Ten dekoder jest przeznaczony do użytku z własnymi sieciami Meshtastic lub publicznymi kanałami. Respektuj prywatność innych użytkowników i nie próbuj deszyfrować wiadomości bez posiadania odpowiedniego klucza kanału.
