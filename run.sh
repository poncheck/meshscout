#!/bin/bash

# Wrapper script dla Meshtastic MQTT Decoder
# Automatycznie aktywuje virtual environment i uruchamia dekoder

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$SCRIPT_DIR/venv"
DECODER_SCRIPT="$SCRIPT_DIR/meshtastic_mqtt_decoder.py"

# Sprawdzenie czy venv istnieje
if [ ! -d "$VENV_DIR" ]; then
    echo "BŁĄD: Virtual environment nie istnieje!"
    echo ""
    echo "Uruchom najpierw setup:"
    echo "  ./setup.sh"
    echo ""
    exit 1
fi

# Sprawdzenie czy decoder istnieje
if [ ! -f "$DECODER_SCRIPT" ]; then
    echo "BŁĄD: Nie znaleziono meshtastic_mqtt_decoder.py!"
    exit 1
fi

# Aktywacja virtual environment i uruchomienie dekodera
# Przekieruj stdout (JSON z pakietami) do /dev/null, pokaż tylko stderr (błędy)
source "$VENV_DIR/bin/activate"

echo "🔍 Uruchomiono dekoder - wyświetlane są tylko BŁĘDY dekodowania"
echo "   (poprawnie zdekodowane pakiety są ukryte)"
echo ""

python3 "$DECODER_SCRIPT" "$@" > /dev/null
