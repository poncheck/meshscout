#!/bin/bash

# Wrapper script dla Web Server
# Automatycznie aktywuje virtual environment i uruchamia web server

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$SCRIPT_DIR/venv"
WEB_SERVER="$SCRIPT_DIR/web_server.py"

# Sprawdzenie czy venv istnieje
if [ ! -d "$VENV_DIR" ]; then
    echo "BŁĄD: Virtual environment nie istnieje!"
    echo ""
    echo "Uruchom najpierw setup:"
    echo "  ./setup.sh"
    echo ""
    exit 1
fi

# Sprawdzenie czy web server istnieje
if [ ! -f "$WEB_SERVER" ]; then
    echo "BŁĄD: Nie znaleziono web_server.py!"
    exit 1
fi

# Aktywacja virtual environment i uruchomienie web servera
source "$VENV_DIR/bin/activate"

# Ustawienie domyślnej ścieżki do bazy (jeśli nie ustawiona)
# Zgodne z docker-compose.yml (./data/mesh_scout.db)
export DB_PATH="${DB_PATH:-$SCRIPT_DIR/data/mesh_scout.db}"

# Upewnij się, że katalog data istnieje
mkdir -p "$SCRIPT_DIR/data"

echo "=========================================="
echo "Mesh Scout Web Server"
echo "=========================================="
echo "Baza danych: $DB_PATH"
echo "URL: http://0.0.0.0:5000"
echo "=========================================="
echo ""

python3 "$WEB_SERVER" "$@"
