# Skrypty MeshScout

## Sprawdzanie bazy danych

### Sposób 1: Skrypt bash (wymaga psql)

```bash
# Z głównego katalogu projektu
./check-db.sh
```

Ten skrypt:
- Sprawdza ostatnie pozycje z SNR/RSSI
- Wyświetla telemetrię
- Pokazuje traceroutes
- Statystyki węzłów

### Sposób 2: Bezpośrednie zapytanie SQL

```bash
# Jeśli masz plik .env z DATABASE_URL
source .env
psql "$DATABASE_URL" -f scripts/check-db.sql
```

### Sposób 3: Ręczne zapytania

```bash
# Połącz się z bazą
source .env
psql "$DATABASE_URL"

# Sprawdź statystyki
SELECT COUNT(*) FROM "Position";
SELECT COUNT(*) FROM "Telemetry";
SELECT COUNT(*) FROM "Traceroute";

# Ostatnie pozycje z SNR/RSSI
SELECT "nodeId", latitude, longitude, snr, rssi, timestamp
FROM "Position"
WHERE snr IS NOT NULL
ORDER BY timestamp DESC
LIMIT 10;

# Ostatnia telemetria
SELECT "nodeId", variant, "batteryLevel", voltage, temperature, timestamp
FROM "Telemetry"
ORDER BY timestamp DESC
LIMIT 10;
```

## Wymagania

- PostgreSQL client (psql)
- Plik `.env` z poprawnym `DATABASE_URL`

## Troubleshooting

### Brak psql
```bash
# Ubuntu/Debian
sudo apt-get install postgresql-client

# macOS
brew install postgresql
```

### Brak .env
```bash
cp .env.example .env
# Edytuj .env i ustaw DATABASE_URL
```
