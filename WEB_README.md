# 🗺️ Mesh Scout Web Interface

Interfejs webowy z mapą do wizualizacji zarejestrowanych urządzeń Meshtastic.

## Funkcje

- 🗺️ **Interaktywna mapa** z wszystkimi zarejestrowanymi urządzeniami
- 📍 **Automatyczne pozycjonowanie** - mapa dopasowuje się do lokalizacji urządzeń
- 🔄 **Auto-refresh** - dane aktualizują się co 30 sekund
- 📋 **Lista urządzeń** - sidebar z możliwością przejścia do konkretnego urządzenia
- 📊 **Statystyki** - liczba urządzeń, wiadomości, urządzenia z GPS
- 🔋 **Telemetria** - bateria, napięcie, wysokość n.p.m.
- ⏰ **Aktywność** - ostatnio widziane urządzenia

## Szybki start z Docker Compose

### 1. Przygotowanie

Upewnij się, że masz plik `config.json` z konfiguracją MQTT:

```json
{
  "broker": "mqtt.meshtastic.info.pl",
  "port": 11883,
  "username": "uplink",
  "password": "uplink",
  "topic": "msh/#",
  "channel_key": "Z8kcxmN7VFYJIf86M3Nj6Q==",

  "database": {
    "enabled": true,
    "path": "/data/mesh_scout.db"
  },

  "filter": {
    "enabled": true,
    "channel_ids": ["mesh-scout"],
    "hashtags": ["#countme"],
    "message_types": ["TEXT_MESSAGE_APP"],
    "save_all": false,
    "require_position": false
  }
}
```

**WAŻNE:** W konfiguracji ustaw `"path": "/data/mesh_scout.db"` aby baza była współdzielona między kontenerami.

### 2. Uruchomienie

```bash
# Utwórz katalog na dane (jeśli nie istnieje)
mkdir -p data

# Zbuduj i uruchom kontenery
docker compose up -d

# Sprawdź logi
docker compose logs -f
```

### 3. Dostęp do interfejsu

Otwórz przeglądarkę i wejdź na:

```
http://localhost:5000
```

## Ręczne uruchomienie (bez Dockera)

### Instalacja zależności

```bash
# Zainstaluj pakiety
pip install -r requirements.txt
```

### Uruchomienie dekodera MQTT

W jednym terminalu:

```bash
./run.sh --config config.json
```

### Uruchomienie web servera

W drugim terminalu:

```bash
python3 web_server.py
```

Lub z niestandardową konfiguracją:

```bash
# Zmień port
PORT=8080 python3 web_server.py

# Użyj innej bazy danych
DB_PATH=/path/to/custom.db python3 web_server.py

# Tryb debug
DEBUG=True python3 web_server.py
```

## API Endpoints

Web server udostępnia REST API:

### GET `/api/devices`

Pobiera listę wszystkich zarejestrowanych urządzeń.

**Odpowiedź:**
```json
{
  "success": true,
  "total": 15,
  "with_gps": 12,
  "without_gps": 3,
  "devices": [
    {
      "node_id": "0x29b07f7e",
      "channel_id": "mesh-scout",
      "user_longname": "Wio Tracker L1 PRO",
      "user_shortname": "WIOT",
      "last_latitude": 51.123456,
      "last_longitude": 17.234567,
      "last_altitude": 120,
      "last_battery_level": 95,
      "last_voltage": 4.15,
      "total_messages": 42,
      "registered_at": "2025-01-15T10:30:00",
      "last_seen": "2025-01-15T14:25:30"
    }
  ]
}
```

### GET `/api/device/<node_id>`

Pobiera szczegóły konkretnego urządzenia.

**Przykład:**
```bash
curl http://localhost:5000/api/device/0x29b07f7e
```

### GET `/api/stats`

Pobiera statystyki ogólne.

**Odpowiedź:**
```json
{
  "success": true,
  "stats": {
    "total_devices": 15,
    "devices_with_gps": 12,
    "devices_without_gps": 3,
    "total_messages": 1234,
    "unique_nodes": 25,
    "channels": {
      "mesh-scout": 10,
      "LongFast": 5
    },
    "recent_devices": [...]
  }
}
```

### GET `/health`

Health check endpoint dla monitoringu.

```bash
curl http://localhost:5000/health
# {"status": "ok"}
```

## Docker Compose - zarządzanie

### Podstawowe komendy

```bash
# Uruchom w tle
docker compose up -d

# Zatrzymaj
docker compose down

# Restart
docker compose restart

# Logi wszystkich serwisów
docker compose logs -f

# Logi tylko web servera
docker compose logs -f web-server

# Logi tylko dekodera
docker compose logs -f mqtt-decoder

# Status kontenerów
docker compose ps

# Przebuduj obrazy
docker compose build --no-cache

# Usuń kontenery i volumes
docker compose down -v
```

### Aktualizacja aplikacji

```bash
# 1. Zatrzymaj kontenery
docker compose down

# 2. Pobierz nową wersję
git pull

# 3. Przebuduj obrazy
docker compose build

# 4. Uruchom ponownie
docker compose up -d
```

## Technologie

- **Backend:** Flask + Python 3.11
- **Frontend:** HTML5 + JavaScript (Vanilla)
- **Mapa:** Leaflet.js + OpenStreetMap
- **Baza danych:** SQLite (współdzielona między kontenerami)
- **Konteneryzacja:** Docker + Docker Compose

## Architektura

```
┌─────────────────┐     ┌─────────────────┐
│  MQTT Broker    │────▶│  mqtt-decoder   │
│                 │     │  (Container 1)  │
└─────────────────┘     └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  mesh_scout.db  │◀────┐
                        │  (Volume /data) │     │
                        └─────────────────┘     │
                                 │              │
                                 ▼              │
                        ┌─────────────────┐     │
                        │   web-server    │─────┘
                        │  (Container 2)  │
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   Browser       │
                        │  localhost:5000 │
                        └─────────────────┘
```

## Porty

- **5000** - Web interface (domyślnie)
- Można zmienić w `docker-compose.yml`:
  ```yaml
  ports:
    - "8080:5000"  # Dostępny na localhost:8080
  ```

## Zmienne środowiskowe

| Zmienna | Opis | Domyślna wartość |
|---------|------|------------------|
| `DB_PATH` | Ścieżka do bazy SQLite | `mesh_scout.db` |
| `PORT` | Port web servera | `5000` |
| `DEBUG` | Tryb debug Flask | `False` |
| `TZ` | Strefa czasowa | `Europe/Warsaw` |

## Troubleshooting

### Brak danych na mapie

1. Sprawdź czy dekoder MQTT działa:
   ```bash
   docker compose logs mqtt-decoder
   ```

2. Sprawdź czy są zarejestrowane urządzenia:
   ```bash
   python3 view_devices.py --db data/mesh_scout.db
   ```

3. Sprawdź czy urządzenia mają GPS:
   ```bash
   python3 view_devices.py --db data/mesh_scout.db --stats
   ```

### Web server nie startuje

```bash
# Sprawdź logi
docker compose logs web-server

# Sprawdź czy port jest zajęty
netstat -tlnp | grep 5000

# Zmień port w docker-compose.yml
```

### Baza danych nie jest współdzielona

Upewnij się, że oba kontenery używają tej samej ścieżki:

```yaml
# W docker-compose.yml
volumes:
  - ./data:/data  # To musi być takie samo dla obu serwisów

environment:
  - DB_PATH=/data/mesh_scout.db  # To też
```

## Integracja z reverse proxy

### Nginx

```nginx
server {
    listen 80;
    server_name mesh-scout.example.com;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### Traefik

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.mesh-scout.rule=Host(`mesh-scout.example.com`)"
  - "traefik.http.services.mesh-scout.loadbalancer.server.port=5000"
```

## Bezpieczeństwo

⚠️ **UWAGA:** Web server nie ma wbudowanej autoryzacji!

Zalecenia:
1. Użyj reverse proxy z HTTP Basic Auth
2. Uruchom w sieci prywatnej / VPN
3. Użyj firewall do ograniczenia dostępu
4. Dodaj HTTPS (Let's Encrypt + Nginx/Traefik)

## Przyszłe funkcje (TODO)

- [ ] Autoryzacja użytkowników
- [ ] WebSocket do live updates
- [ ] Historia pozycji urządzeń (tracking)
- [ ] Eksport danych do KML/GPX
- [ ] Dashboard z wykresami
- [ ] Alerty/powiadomienia
- [ ] Dark mode toggle
- [ ] Filtrowanie po kanałach/regionach
- [ ] Clustering markerów

## Licencja

MIT License - zobacz plik `LICENSE`
