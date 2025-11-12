#!/bin/bash

# Setup script dla Meshtastic MQTT Decoder
# Tworzy virtual environment i instaluje zależności

set -e

echo "=========================================="
echo "Meshtastic MQTT Decoder - Setup"
echo "=========================================="
echo ""

# Sprawdzenie wymaganych narzędzi
echo "[1/3] Sprawdzanie wymaganych narzędzi..."

if ! command -v python3 &> /dev/null; then
    echo "BŁĄD: Python3 nie jest zainstalowany"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python3 zainstalowany (wersja: $PYTHON_VERSION)"

if ! python3 -m venv --help &> /dev/null; then
    echo "BŁĄD: python3-venv nie jest zainstalowany"
    echo "Zainstaluj przez: sudo apt-get install python3-venv"
    exit 1
fi

echo "✓ Wszystkie narzędzia dostępne"
echo ""

# Utworzenie i konfiguracja virtual environment
echo "[2/3] Tworzenie virtual environment..."
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [ -d "$SCRIPT_DIR/venv" ]; then
    echo "Virtual environment już istnieje - aktualizacja..."
    source "$SCRIPT_DIR/venv/bin/activate"
    pip install --upgrade pip
else
    echo "Tworzenie nowego virtual environment..."
    python3 -m venv "$SCRIPT_DIR/venv"
    source "$SCRIPT_DIR/venv/bin/activate"
    pip install --upgrade pip
    echo "✓ Virtual environment utworzone"
fi
echo ""

# Instalacja zależności Python
echo "[3/3] Instalacja zależności Python..."
echo "To może potrwać kilka minut przy pierwszym uruchomieniu..."
pip install -r requirements.txt

echo ""
echo "✓ Zależności zainstalowane w venv"

# Weryfikacja instalacji h3
echo ""
echo "Weryfikacja instalacji h3 (geospatial library)..."
if python3 -c "import h3" 2>/dev/null; then
    echo "✓ Moduł h3 zainstalowany poprawnie"
else
    echo "⚠ Moduł h3 nie został zainstalowany - próba ponownej instalacji..."
    pip install h3>=3.7.0
    if python3 -c "import h3" 2>/dev/null; then
        echo "✓ Moduł h3 zainstalowany poprawnie (druga próba)"
    else
        echo "⚠ Nie udało się zainstalować h3 - funkcje geospatial będą wyłączone"
    fi
fi
echo ""

echo "=========================================="
echo "✓ Setup zakończony pomyślnie!"
echo "=========================================="
echo ""
echo "Virtual environment utworzone w: $SCRIPT_DIR/venv"
echo ""
echo "Możesz teraz uruchomić dekoder na 2 sposoby:"
echo ""
echo "1. Używając wrapper script (ZALECANE):"
echo "   ./run.sh --help"
echo "   ./run.sh --broker mqtt.meshtastic.org --topic \"msh/EU_868/2/e/#\""
echo ""
echo "2. Aktywując venv ręcznie:"
echo "   source venv/bin/activate"
echo "   python3 meshtastic_mqtt_decoder.py --help"
echo ""
echo "Aby użyć własnej konfiguracji:"
echo "   cp config.example.json config.json"
echo "   nano config.json"
echo "   ./run.sh --config config.json"
echo ""
echo "Uwaga: Pakiet meshtastic zawiera wbudowane protobuf - nie musisz"
echo "       instalować protoc ani kompilować plików .proto!"
echo ""
