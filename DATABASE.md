# 💾 Dokumentacja Bazy Danych MeshScout

## Przegląd

MeshScout używa **SQLite** jako bazy danych do przechowywania wiadomości, urządzeń i statystyk. Baza danych jest współdzielona między dekoderern MQTT a serwerem webowym.

## Lokalizacja bazy danych

Domyślna ścieżka: `data/mesh_scout.db`

```python
# W database.py
def __init__(self, db_path: str = "data/mesh_scout.db"):
    self.db_path = Path(db_path)
    self.conn = None
    self._init_database()
```

## Wymagane uprawnienia do plików

### 1. Katalog `data/`

```bash
# Uprawnienia: 755 (rwxr-xr-x)
mkdir -p data
chmod 755 data
```

**Uprawnienia 755 oznaczają:**
- Właściciel: odczyt (r), zapis (w), wykonywanie (x)
- Grupa: odczyt (r), wykonywanie (x)
- Inni: odczyt (r), wykonywanie (x)

### 2. Plik bazy danych `mesh_scout.db`

```bash
# Uprawnienia: 644 (rw-r--r--)
chmod 644 data/mesh_scout.db
```

**Uprawnienia 644 oznaczają:**
- Właściciel: odczyt (r), zapis (w)
- Grupa: odczyt (r)
- Inni: odczyt (r)

### 3. Pliki WAL (Write-Ahead Logging)

SQLite w trybie WAL tworzy dodatkowe pliki:
- `mesh_scout.db-wal` - log zapisu
- `mesh_scout.db-shm` - współdzielona pamięć

```bash
# Te pliki są tworzone automatycznie z uprawnieniami 644
chmod 644 data/mesh_scout.db-wal
chmod 644 data/mesh_scout.db-shm
```

## Tryb WAL (Write-Ahead Logging)

MeshScout używa trybu WAL dla SQLite, co umożliwia:
- ✅ Jednoczesne czytanie i pisanie do bazy
- ✅ Lepsza wydajność dla aplikacji wielowątkowych
- ✅ Bezpieczniejsze transakcje

```python
# W database.py
cursor.execute("PRAGMA journal_mode=WAL")
cursor.execute("PRAGMA synchronous=NORMAL")
cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
cursor.execute("PRAGMA temp_store=MEMORY")
cursor.execute("PRAGMA busy_timeout=30000")  # 30 sekund timeout
```

## Automatyczne tworzenie katalogu

Od najnowszej wersji, `database.py` automatycznie tworzy katalog `data/` jeśli nie istnieje:

```python
def _init_database(self):
    """Inicjalizuje bazę danych i tworzy tabele jeśli nie istnieją"""
    try:
        # Upewnij się, że katalog nadrzędny istnieje
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Połączenie z bazą danych z obsługą współbieżności
        self.conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30.0  # 30 sekund timeout dla locków
        )
```

## Struktura tabel

### Tabela `messages`
Przechowuje wszystkie odebrane wiadomości z sieci Meshtastic.

### Tabela `devices`
Przechowuje zarejestrowane urządzenia (gracze i zwykłe urządzenia).

### Tabela `traceroute_packets`
Przechowuje pakiety traceroute (tylko od graczy).

### Tabela `player_scores`
Przechowuje wyniki graczy (highscore).

### Tabela `device_hexagons`
Przechowuje odwiedzone heksagony H3 przez wszystkie urządzenia.

## Rozwiązywanie problemów

### Błąd: "Nie udało się zapisać do bazy"

**Przyczyny:**
1. Brak katalogu `data/`
2. Brak uprawnień do zapisu
3. Baza danych jest zablokowana przez inny proces
4. Brak miejsca na dysku

**Rozwiązanie:**

```bash
# 1. Sprawdź czy katalog istnieje
ls -la data/

# 2. Utwórz katalog jeśli nie istnieje
mkdir -p data

# 3. Ustaw odpowiednie uprawnienia
chmod 755 data

# 4. Sprawdź właściciela plików
ls -la data/
# Powinno wyświetlić: drwxr-xr-x  2 twoj_user twoj_grupa  4096 Nov 12 22:15 data

# 5. Zmień właściciela jeśli potrzeba
sudo chown -R $USER:$USER data/

# 6. Sprawdź uprawnienia bazy
ls -la data/mesh_scout.db
# Powinno wyświetlić: -rw-r--r--  1 twoj_user twoj_grupa  ... data/mesh_scout.db

# 7. Sprawdź miejsce na dysku
df -h .
```

### Błąd: "database is locked"

**Przyczyna:** Inny proces ma otwarty lock na bazie danych.

**Rozwiązanie:**

```bash
# 1. Sprawdź procesy używające bazy
lsof data/mesh_scout.db

# 2. Zatrzymaj procesy jeśli potrzeba
docker compose down  # jeśli używasz Docker
# lub
pkill -f meshtastic_mqtt_decoder

# 3. Usuń pliki lock jeśli istnieją (OSTROŻNIE!)
rm -f data/mesh_scout.db-wal
rm -f data/mesh_scout.db-shm

# 4. Uruchom ponownie
docker compose up -d
```

### Błąd: "unable to open database file"

**Przyczyna:** Brak uprawnień do odczytu/zapisu lub katalog nie istnieje.

**Rozwiązanie:**

```bash
# 1. Sprawdź uprawnienia katalogu
ls -ld data/
# Powinno być: drwxr-xr-x

# 2. Napraw uprawnienia
chmod 755 data/

# 3. Sprawdź uprawnienia pliku bazy
ls -l data/mesh_scout.db
# Powinno być: -rw-r--r--

# 4. Napraw uprawnienia pliku
chmod 644 data/mesh_scout.db
```

## Konfiguracja dla Docker

W `docker-compose.yml`:

```yaml
services:
  mqtt-decoder:
    volumes:
      - ./data:/data  # Współdzielony katalog danych
    environment:
      - DATABASE_PATH=/data/mesh_scout.db

  web-server:
    volumes:
      - ./data:/data  # Ten sam katalog danych
    environment:
      - DATABASE_PATH=/data/mesh_scout.db
```

**Ważne:** Oba kontenery muszą mieć dostęp do tego samego katalogu `data/`.

## Backup bazy danych

### Metoda 1: Prosty backup

```bash
# Zatrzymaj serwisy
docker compose down

# Skopiuj bazę
cp data/mesh_scout.db data/mesh_scout.db.backup

# Lub z datą
cp data/mesh_scout.db data/mesh_scout.db.$(date +%Y%m%d_%H%M%S)

# Uruchom serwisy
docker compose up -d
```

### Metoda 2: Backup online (bez zatrzymywania)

```bash
# Użyj sqlite3 do backupu online
sqlite3 data/mesh_scout.db ".backup data/mesh_scout.db.backup"
```

### Metoda 3: Export do SQL

```bash
# Export struktury i danych
sqlite3 data/mesh_scout.db .dump > backup.sql

# Restore z SQL
sqlite3 data/mesh_scout_new.db < backup.sql
```

## Optymalizacja

### Vacuum (defragmentacja)

```bash
# Zatrzymaj serwisy
docker compose down

# Vacuum bazy
sqlite3 data/mesh_scout.db "VACUUM;"

# Uruchom serwisy
docker compose up -d
```

### Analiza rozmiaru

```bash
# Sprawdź rozmiar bazy
du -h data/mesh_scout.db*

# Sprawdź liczbę rekordów
sqlite3 data/mesh_scout.db "SELECT COUNT(*) FROM messages;"
sqlite3 data/mesh_scout.db "SELECT COUNT(*) FROM devices;"
sqlite3 data/mesh_scout.db "SELECT COUNT(*) FROM traceroute_packets;"
```

## Monitoring

### Sprawdzanie statusu WAL

```bash
sqlite3 data/mesh_scout.db "PRAGMA journal_mode;"
# Powinno zwrócić: wal
```

### Sprawdzanie transakcji

```bash
sqlite3 data/mesh_scout.db "PRAGMA wal_checkpoint;"
# Wymusza checkpoint WAL do głównego pliku
```

### Statystyki

```bash
# Rozmiar stron
sqlite3 data/mesh_scout.db "PRAGMA page_size;"

# Liczba stron
sqlite3 data/mesh_scout.db "PRAGMA page_count;"

# Cache size
sqlite3 data/mesh_scout.db "PRAGMA cache_size;"
```

## Bezpieczeństwo

### Uprawnienia w produkcji

```bash
# Katalog data/ - tylko właściciel ma pełny dostęp
chmod 700 data/

# Baza danych - tylko właściciel ma odczyt/zapis
chmod 600 data/mesh_scout.db

# Pliki WAL
chmod 600 data/mesh_scout.db-*
```

### Dla środowiska wieloużytkownikowego

```bash
# Utwórz grupę dla użytkowników aplikacji
sudo groupadd meshscout

# Dodaj użytkowników do grupy
sudo usermod -a -G meshscout user1
sudo usermod -a -G meshscout user2

# Ustaw grupę dla katalogu
sudo chgrp meshscout data/

# Ustaw uprawnienia: właściciel i grupa mają dostęp
chmod 770 data/
chmod 660 data/mesh_scout.db*
```

## Migracje

Jeśli potrzebujesz zmienić schemat bazy, `database.py` automatycznie wykrywa brakujące kolumny i dodaje je:

```python
# Przykład migracji w database.py
try:
    cursor.execute("SELECT role FROM devices LIMIT 1")
except sqlite3.OperationalError:
    logger.info("Dodawanie kolumny 'role' do tabeli devices")
    cursor.execute("ALTER TABLE devices ADD COLUMN role INTEGER")
```

## Dodatkowe narzędzia

- `show_db.py` - Wyświetla statystyki bazy danych
- `view_database.py` - Przeglądarka bazy danych
- `view_devices.py` - Lista urządzeń
- `cleanup_database.py` - Czyszczenie starych danych

## Wsparcie

W razie problemów z bazą danych:
1. Sprawdź uprawnienia do plików
2. Sprawdź logi: `docker compose logs -f mqtt-decoder`
3. Uruchom w trybie verbose: `--verbose`
4. Otwórz issue na GitHub z szczegółami błędu
