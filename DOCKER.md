# 🐳 Docker - Dokumentacja MeshScout

## Szybki start

```bash
# 1. Skopiuj konfigurację dla Dockera
cp config.docker.json config.json

# 2. Edytuj konfigurację (broker, topic, klucz kanału)
nano config.json

# 3. Uruchom kontenery
docker compose up -d --build

# 4. Sprawdź logi
docker compose logs -f
```

## ⚙️ Konfiguracja

### Ważne różnice między lokalnym uruchomieniem a Docker

| Parametr | Lokalnie | Docker |
|----------|----------|--------|
| Baza danych | `data/mesh_scout.db` | `/data/mesh_scout.db` |
| Config | `config.example.json` | `config.docker.json` |
| Database enabled | opcjonalne | **MUSI być true** |
| Katalog data/ | relatywny `data/` | bezwzględny `/data` |

### Plik config.json dla Dockera

**Użyj `config.docker.json` jako bazy:**
```bash
cp config.docker.json config.json
```

**Kluczowe ustawienia:**
```json
{
  "database": {
    "enabled": true,                    // MUSI być true!
    "path": "/data/mesh_scout.db"       // MUSI być /data/ nie data/
  },
  "filter": {
    "enabled": true,                    // Zalecane
    "hashtags": ["#countme", "#registerme"],
    "save_all": false                   // true = zapisuj wszystko
  }
}
```

## 🔧 Dockerfile

Obraz bazowy: `python:3.11-slim`

Kluczowe elementy:
```dockerfile
# Katalog /data ma uprawnienia 777 (zapis dla wszystkich)
RUN mkdir -p /data && chmod 777 /data

# PYTHONUNBUFFERED dla natychmiastowych logów
ENV PYTHONUNBUFFERED=1
```

## 📦 docker-compose.yml

### Usługi

#### mqtt-decoder
- **Rola**: Odbiera i dekoduje wiadomości z MQTT, zapisuje do bazy
- **Port**: Brak (tylko internal)
- **Volume**: `./data:/data` (współdzielona baza)
- **Config**: `./config.json:/app/config.json:ro`

#### web-server
- **Rola**: Interfejs webowy z mapą urządzeń
- **Port**: `5000:5000` → http://localhost:5000
- **Volume**: `./data:/data` (ta sama baza)
- **Depends on**: mqtt-decoder

### Volumes

```yaml
volumes:
  - ./data:/data                      # Host ./data → Kontener /data
  - ./config.json:/app/config.json:ro # Config read-only
```

**Dlaczego używamy bind mount zamiast named volume?**
- Łatwy dostęp do bazy z hosta
- Łatwe backupy (`cp data/mesh_scout.db backup/`)
- Dane przetrwają usunięcie kontenerów

## 🚀 Komendy

### Podstawowe operacje

```bash
# Uruchom (build + start)
docker compose up -d --build

# Zatrzymaj (bez usuwania)
docker compose stop

# Uruchom ponownie
docker compose start

# Restart pojedynczej usługi
docker compose restart mqtt-decoder

# Usuń kontenery (dane w ./data/ zostają!)
docker compose down

# Usuń kontenery + images
docker compose down --rmi all
```

### Logi

```bash
# Wszystkie logi (follow)
docker compose logs -f

# Tylko mqtt-decoder
docker compose logs -f mqtt-decoder

# Tylko web-server
docker compose logs -f web-server

# Ostatnie 100 linii
docker compose logs --tail=100

# Od konkretnego czasu
docker compose logs --since="2025-11-12T22:00:00"
```

### Status i diagnostyka

```bash
# Status kontenerów
docker compose ps

# Zasoby (CPU, RAM)
docker stats mesh-scout-decoder mesh-scout-web

# Inspekcja kontenera
docker inspect mesh-scout-decoder

# Procesy w kontenerze
docker compose top mqtt-decoder
```

### Wejście do kontenera

```bash
# Shell interaktywny
docker compose exec mqtt-decoder bash

# Pojedyncza komenda
docker compose exec mqtt-decoder ls -la /data/

# Sprawdź Python
docker compose exec mqtt-decoder python3 --version

# Test bazy danych
docker compose exec mqtt-decoder python3 -c "
from database import MeshtasticDatabase
db = MeshtasticDatabase('/data/mesh_scout.db')
stats = db.get_statistics()
print(f'Wiadomości: {stats[\"total_messages\"]}')
db.close()
"
```

## 🐛 Rozwiązywanie problemów

### Problem: Kontener nie startuje

```bash
# 1. Sprawdź logi błędów
docker compose logs mqtt-decoder | grep -i error

# 2. Sprawdź czy config.json istnieje
ls -la config.json

# 3. Sprawdź składnię config.json
cat config.json | python3 -m json.tool

# 4. Zrestartuj z rebuildem
docker compose down
docker compose up -d --build
```

### Problem: "Nie udało się zapisać do bazy"

```bash
# 1. Sprawdź uprawnienia na hoście
ls -la data/
# Powinno być: drwxr-xr-x (755)

# 2. Napraw uprawnienia
chmod 755 data/

# 3. Sprawdź uprawnienia w kontenerze
docker compose exec mqtt-decoder ls -la /data/
# Powinno być: drwxrwxrwx (777)

# 4. Test zapisu
docker compose exec mqtt-decoder touch /data/test.txt
docker compose exec mqtt-decoder rm /data/test.txt

# 5. Restart
docker compose restart mqtt-decoder
```

### Problem: "database disk image is malformed"

```bash
# 1. Zatrzymaj kontenery
docker compose down

# 2. Backup uszkodzonej bazy
cp data/mesh_scout.db data/mesh_scout.db.corrupted

# 3. Usuń uszkodzoną bazę
rm -f data/mesh_scout.db data/mesh_scout.db-wal data/mesh_scout.db-shm

# 4. Uruchom ponownie - utworzy nową bazę
docker compose up -d
```

Więcej informacji: [DATABASE.md](DATABASE.md)

### Problem: Brak config.json

```bash
# 1. Utwórz config dla Dockera
cp config.docker.json config.json

# 2. Edytuj konfigurację
nano config.json

# 3. Sprawdź składnię JSON
cat config.json | python3 -m json.tool

# 4. Uruchom
docker compose up -d
```

### Problem: Port 5000 zajęty

```bash
# 1. Sprawdź co używa portu 5000
sudo lsof -i :5000
# lub
sudo netstat -tulpn | grep :5000

# 2. Opcja A: Zmień port w docker-compose.yml
#    ports: - "8080:5000"  # Host port 8080 → Container port 5000

# 3. Opcja B: Zatrzymaj konfliktującą usługę
sudo systemctl stop conflicting-service

# 4. Uruchom ponownie
docker compose up -d
```

### Problem: Kontenery działają, ale brak danych w bazie

```bash
# 1. Sprawdź czy database enabled w config.json
docker compose exec mqtt-decoder cat /app/config.json | grep -A2 "database"

# 2. Powinno być:
#    "enabled": true,
#    "path": "/data/mesh_scout.db"

# 3. Sprawdź rozmiar bazy
docker compose exec mqtt-decoder ls -lh /data/mesh_scout.db

# 4. Sprawdź statystyki bazy
docker compose exec mqtt-decoder python3 -c "
from database import MeshtasticDatabase
db = MeshtasticDatabase('/data/mesh_scout.db')
stats = db.get_statistics()
print(f'Total messages: {stats[\"total_messages\"]}')
print(f'Unique nodes: {stats[\"unique_nodes\"]}')
db.close()
"

# 5. Sprawdź czy MQTT działa (logi)
docker compose logs --tail=50 mqtt-decoder | grep -i "mqtt\|connected"
```

## 📊 Monitoring

### Metryki kontenerów

```bash
# Zużycie zasobów (real-time)
docker stats mesh-scout-decoder mesh-scout-web

# Historia logów
docker compose logs --since="1h" | wc -l

# Rozmiar bazy danych
docker compose exec mqtt-decoder du -h /data/mesh_scout.db
```

### Health checks

Dodaj do `docker-compose.yml`:
```yaml
services:
  mqtt-decoder:
    healthcheck:
      test: ["CMD", "python3", "-c", "import sqlite3; sqlite3.connect('/data/mesh_scout.db').execute('SELECT 1')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

Sprawdź:
```bash
docker compose ps
# Kolumna Status pokaże "healthy" lub "unhealthy"
```

## 🔄 Aktualizacje

### Aktualizacja kodu

```bash
# 1. Pobierz najnowszy kod
git pull

# 2. Przebuduj obrazy
docker compose build

# 3. Restart z nowymi obrazami
docker compose up -d

# 4. Sprawdź logi
docker compose logs -f
```

### Aktualizacja konfiguracji

```bash
# 1. Edytuj config.json
nano config.json

# 2. Restart kontenerów (bez rebuildu)
docker compose restart

# 3. Sprawdź czy zmiany zostały załadowane
docker compose exec mqtt-decoder cat /app/config.json
```

## 💾 Backupy

### Backup bazy danych

```bash
# Prosty backup (zatrzymaj kontenery)
docker compose stop
cp data/mesh_scout.db backups/mesh_scout.db.$(date +%Y%m%d_%H%M%S)
docker compose start

# Backup online (bez zatrzymywania)
docker compose exec mqtt-decoder python3 -c "
import sqlite3
conn = sqlite3.connect('/data/mesh_scout.db')
backup = sqlite3.connect('/data/mesh_scout.db.backup')
conn.backup(backup)
backup.close()
conn.close()
"
cp data/mesh_scout.db.backup backups/
```

### Automatyczny backup (cron)

```bash
# Dodaj do crontab (crontab -e)
0 3 * * * cd /path/to/meshscout && docker compose exec -T mqtt-decoder python3 -c "import sqlite3; conn = sqlite3.connect('/data/mesh_scout.db'); backup = sqlite3.connect('/data/mesh_scout.db.backup'); conn.backup(backup); backup.close(); conn.close()" && cp data/mesh_scout.db.backup backups/mesh_scout.db.$(date +\%Y\%m\%d)
```

## 🔐 Bezpieczeństwo

### Najlepsze praktyki

1. **Nie commituj config.json do git**
   ```bash
   # Dodaj do .gitignore
   echo "config.json" >> .gitignore
   ```

2. **Używaj secrets dla haseł MQTT**
   ```yaml
   services:
     mqtt-decoder:
       secrets:
         - mqtt_password
   secrets:
     mqtt_password:
       file: ./secrets/mqtt_password.txt
   ```

3. **Uruchom web-server za reverse proxy (nginx)**
   ```yaml
   # Nie expose'uj portu bezpośrednio
   # Zamiast ports: - "5000:5000"
   # Użyj nginx jako proxy
   ```

4. **Regularnie aktualizuj obrazy bazowe**
   ```bash
   docker compose pull
   docker compose up -d --build
   ```

## 📚 Dodatkowe zasoby

- [README.md](README.md) - Główna dokumentacja
- [DATABASE.md](DATABASE.md) - Dokumentacja bazy danych
- [WEB_README.md](WEB_README.md) - Dokumentacja interfejsu webowego
- [Docker Compose docs](https://docs.docker.com/compose/)
- [Meshtastic MQTT](https://meshtastic.org/docs/software/integrations/mqtt/)
