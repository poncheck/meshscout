#!/bin/bash

# Skrypt do migracji lokalnej bazy danych i naprawy jej uprawnień dla środowiska Docker.
# Uruchom ten skrypt z głównego katalogu projektu (np. ./migrate_db.sh).

set -e

DB_SOURCE="mesh_scout.db"
DB_DEST_DIR="data"
DB_DEST_FILE="$DB_DEST_DIR/$DB_SOURCE"

echo "--- Skrypt migracji i naprawy bazy danych Mesh Scout ---"

# Sprawdź, czy plik docker-compose.yml istnieje, aby potwierdzić, że jesteśmy w dobrym katalogu
if [ ! -f "docker-compose.yml" ]; then
  echo "BŁĄD: Nie znaleziono pliku docker-compose.yml. Uruchom ten skrypt z głównego katalogu projektu mesh-scout."
  exit 1
fi

# Sprawdź, czy stara baza danych istnieje w głównym katalogu
if [ -f "$DB_SOURCE" ]; then
  echo "1. Znaleziono istniejącą bazę danych w głównym katalogu projektu."
  
  echo "2. Zatrzymywanie kontenerów Docker, aby uniknąć problemów z plikami..."
  docker compose down
  
  echo "3. Tworzenie katalogu '$DB_DEST_DIR' (jeśli nie istnieje)."
  mkdir -p "$DB_DEST_DIR"
  
  echo "4. Przenoszenie bazy danych z '$DB_SOURCE' do '$DB_DEST_FILE' (może wymagać hasła sudo)."
  sudo mv "$DB_SOURCE" "$DB_DEST_FILE"
  
  echo "Baza danych została przeniesiona."
else
  echo "INFO: Nie znaleziono bazy danych '$DB_SOURCE' w głównym katalogu. Przechodzę do naprawy uprawnień."
fi

# Sprawdź, czy katalog 'data' istnieje przed próbą zmiany uprawnień
if [ ! -d "$DB_DEST_DIR" ]; then
    echo "INFO: Katalog '$DB_DEST_DIR' nie istnieje. Nie ma czego naprawiać. Kończę pracę."
    exit 0
fi

echo "5. Naprawianie uprawnień do katalogu '$DB_DEST_DIR' i jego zawartości."
echo "    Zostaniesz poproszony o hasło, aby zmienić właściciela plików (sudo)."

# Zmień właściciela katalogu 'data' i wszystkich plików wewnątrz na bieżącego użytkownika i grupę.
# To rozwiązuje problemy z uprawnieniami, gdy Docker tworzy pliki jako 'root'.
sudo chown -R $(id -u):$(id -g) "$DB_DEST_DIR"

echo "Uprawnienia zostały pomyślnie zaktualizowane."
echo "--- Zakończono ---"
echo "Teraz możesz bezpiecznie uruchomić aplikację za pomocą: docker compose up --build -d"
