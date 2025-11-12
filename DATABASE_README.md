# Database & Filtering - Mesh Scout

## Opis

System filtrowania i zapisu wiadomości Meshtastic do bazy danych SQLite.

## Funkcje

- ✅ Filtrowanie wiadomości po hashtagu (np. `#countme`)
- ✅ Filtrowanie po kanale (np. `mesh-scout`)
- ✅ Filtrowanie po typie wiadomości (TEXT, POSITION, TELEMETRY, etc.)
- ✅ Zapis do bazy danych SQLite
- ✅ Automatyczna ekstrakcja hashtagów
- ✅ Statystyki i eksport danych

## Konfiguracja

Edytuj `config.json`:

```json
{
  "broker": "mqtt.meshtastic.info.pl",
  "port": 11883,
  "username": "uplink",
  "password": "uplink",
  "topic": "msh/#",

  "database": {
    "enabled": true,
    "path": "mesh_scout.db"
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

## Użycie

### 1. Uruchomienie z filtrowaniem

```bash
# Skopiuj przykładową konfigurację
cp config.example.json config.json

# Edytuj sekcje database i filter
nano config.json

# Uruchom dekoder
./run.sh --config config.json
```

### 2. Przeglądanie bazy danych

```bash
# Statystyki
python3 view_database.py --db mesh_scout.db --stats

# Wiadomości z hashtagiem
python3 view_database.py --db mesh_scout.db --hashtag "#countme"

# Ostatnie 50 wiadomości
python3 view_database.py --db mesh_scout.db --limit 50

# Filtruj po kanale
python3 view_database.py --db mesh_scout.db --channel "mesh-scout"

# Pełne JSON
python3 view_database.py --db mesh_scout.db --hashtag "#countme" --full

# Eksport do JSON
python3 view_database.py --db mesh_scout.db --hashtag "#countme" --export-json export.json
```

## Struktura bazy danych

### Tabela `messages`

| Kolumna | Typ | Opis |
|---------|-----|------|
| `id` | INTEGER | ID wiadomości (auto) |
| `received_at` | TIMESTAMP | Kiedy otrzymano |
| `message_id` | INTEGER | ID pakietu Meshtastic |
| `channel_id` | TEXT | Nazwa kanału |
| `gateway_id` | TEXT | ID gateway |
| `from_node` | TEXT | ID nadawcy |
| `to_node` | TEXT | ID odbiorcy |
| `message_type` | TEXT | Typ wiadomości |
| `message_text` | TEXT | Treść tekstowa |
| `hashtags` | TEXT | Hashtagi (csv) |
| `latitude` | REAL | Szerokość geograficzna |
| `longitude` | REAL | Długość geograficzna |
| `altitude` | INTEGER | Wysokość (m) |
| `rssi` | INTEGER | RSSI |
| `snr` | REAL | SNR |
| `hop_limit` | INTEGER | Limit skoków |
| `rx_time` | INTEGER | Timestamp odbioru |
| `user_longname` | TEXT | Nazwa użytkownika |
| `user_shortname` | TEXT | Krótka nazwa |
| `hw_model` | INTEGER | Model sprzętu |
| `battery_level` | INTEGER | Poziom baterii (%) |
| `voltage` | REAL | Napięcie (V) |
| `temperature` | REAL | Temperatura (°C) |
| `raw_json` | TEXT | Pełne JSON |
| `topic` | TEXT | Temat MQTT |

## Filtr - opcje konfiguracji

### `channel_ids`
Lista dozwolonych kanałów. Jeśli pusta, wszystkie kanały są akceptowane.

```json
"channel_ids": ["mesh-scout", "emergency"]
```

### `hashtags`
Lista wymaganych hashtagów. Wiadomość musi zawierać PRZYNAJMNIEJ JEDEN z nich.

```json
"hashtags": ["#countme", "#help", "#sos"]
```

### `message_types`
Lista dozwolonych typów wiadomości:
- `TEXT_MESSAGE_APP` - wiadomości tekstowe
- `POSITION_APP` - pozycje GPS
- `NODEINFO_APP` - info o węzłach
- `TELEMETRY_APP` - telemetria
- `MAP_REPORT_APP` - raporty mapy

```json
"message_types": ["TEXT_MESSAGE_APP", "POSITION_APP"]
```

### `save_all`
Jeśli `true`, zapisuje wszystkie wiadomości ignorując inne filtry.

```json
"save_all": true
```

### `require_position`
Jeśli `true`, wymaga aby wiadomość miała współrzędne GPS.

```json
"require_position": true
```

## Przykłady użycia

### Przykład 1: Zbieranie wiadomości #countme

```json
{
  "database": {"enabled": true, "path": "countme.db"},
  "filter": {
    "enabled": true,
    "channel_ids": ["mesh-scout"],
    "hashtags": ["#countme"],
    "message_types": ["TEXT_MESSAGE_APP"]
  }
}
```

### Przykład 2: Mapa wszystkich węzłów

```json
{
  "database": {"enabled": true, "path": "positions.db"},
  "filter": {
    "enabled": true,
    "message_types": ["POSITION_APP"],
    "save_all": false
  }
}
```

### Przykład 3: Zbieranie telemetrii

```json
{
  "database": {"enabled": true, "path": "telemetry.db"},
  "filter": {
    "enabled": true,
    "message_types": ["TELEMETRY_APP"],
    "save_all": false
  }
}
```

### Przykład 4: Wszystko z jednego kanału

```json
{
  "database": {"enabled": true, "path": "my_channel.db"},
  "filter": {
    "enabled": true,
    "channel_ids": ["my-channel"],
    "save_all": true
  }
}
```

## Zapytania SQL

### Liczba wiadomości z #countme

```sql
SELECT COUNT(*) FROM messages WHERE hashtags LIKE '%#countme%';
```

### Unikalne węzły

```sql
SELECT DISTINCT from_node, user_longname, COUNT(*) as msg_count
FROM messages
WHERE hashtags LIKE '%#countme%'
GROUP BY from_node
ORDER BY msg_count DESC;
```

### Wiadomości z ostatniej godziny

```sql
SELECT * FROM messages
WHERE received_at > datetime('now', '-1 hour')
ORDER BY received_at DESC;
```

### Mapa węzłów

```sql
SELECT from_node, user_longname, latitude, longitude, altitude, received_at
FROM messages
WHERE latitude IS NOT NULL AND longitude IS NOT NULL
ORDER BY received_at DESC;
```

## Statystyki w czasie rzeczywistym

Podczas działania dekodera zobaczysz:

```
2025-10-23 11:00:00 - INFO - ✓ Zapisano do bazy (ID=123): Match: channel=mesh-scout, hashtags=#countme

Ctrl+C

STATYSTYKI:
  Otrzymane wiadomości: 1523
  Zapisane do bazy: 42
  Odfiltrowane: 1481

  Łącznie w bazie: 42
  Unikalne węzły: 8
```

## Eksport i integracja

### Eksport do CSV

```bash
sqlite3 mesh_scout.db -header -csv "SELECT * FROM messages WHERE hashtags LIKE '%#countme%'" > export.csv
```

### Eksport do JSON

```bash
python3 view_database.py --db mesh_scout.db --hashtag "#countme" --export-json countme.json
```

### Integracja z innymi narzędziami

- **Grafana**: użyj SQLite data source
- **Python**: `import sqlite3` lub pandas
- **Web app**: prosty backend z Flask/FastAPI
- **Map**: Leaflet.js + GeoJSON z pozycji

## Rozwiązywanie problemów

### Baza danych nie jest tworzona

Sprawdź:
```bash
# Czy filter.enabled = true?
# Czy database.enabled = true?
grep -A 5 '"database"' config.json
grep -A 10 '"filter"' config.json
```

### Wszystko jest filtrowane

- Sprawdź `channel_id` w wiadomościach
- Sprawdź hashtagi w wiadomościach tekstowych
- Użyj `"save_all": true` do testów

### Baza jest pusta

- Upewnij się że wiadomości pasują do filtra
- Sprawdź logi: `✓ Zapisano do bazy`
- Spróbuj z `"save_all": true`

## Bezpieczeństwo

⚠️ **Ważne:**
- Pliki `.db` są w `.gitignore` - nie będą commitowane
- Nie udostępniaj bazy publicznie bez filtrowania danych osobowych
- Regularnie rób backupy: `cp mesh_scout.db mesh_scout_backup_$(date +%Y%m%d).db`

## Wydajność

- Baza SQLite obsługuje tysiące wiadomości bez problemu
- Indeksy są już utworzone automatycznie
- Dla milionów wiadomości rozważ PostgreSQL

## Dalszy rozwój

Możliwe rozszerzenia:
- 📊 Real-time dashboard
- 🗺️ Interaktywna mapa
- 📈 Wykresy i analityka
- 🔔 Powiadomienia (email, Discord, Telegram)
- 🌐 REST API
- 📱 Aplikacja mobilna
