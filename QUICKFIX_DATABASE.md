# 🔧 Szybka naprawa problemu z bazą danych

## Problem
```
unable to open database file
```

## Przyczyna
Katalog `data/` nie istnieje lub nie ma uprawnień do zapisu.

## Rozwiązanie 1: Utwórz katalog data
```bash
cd ~/mesh-scout
mkdir -p data
chmod 755 data
```

## Rozwiązanie 2: Użyj pełnej ścieżki
Edytuj `config.json`:
```json
{
  "database": {
    "enabled": true,
    "path": "data/mesh_scout.db"
  }
}
```

## Rozwiązanie 3: Użyj lokalnej ścieżki względnej
Edytuj `config.json`:
```json
{
  "database": {
    "enabled": true,
    "path": "./data/mesh_scout.db"
  }
}
```

## Test po naprawie
```bash
# Utwórz katalog
mkdir -p ~/mesh-scout/data

# Uruchom ponownie
cd ~/mesh-scout
./run.sh --config config.json
```

## Weryfikacja
Sprawdź czy baza się utworzyła:
```bash
ls -lh ~/mesh-scout/data/
# Powinien być plik: mesh_scout.db
```

---

## ✅ Co już działa:
- ✅ Połączenie z MQTT
- ✅ Deszyfrowanie pakietów
- ✅ Otrzymywanie komend rejestracji ("Registerme" zadziałało!)

## 📝 Po naprawie bazy:
System automatycznie zarejestruje gracza `0x9456a388` który wysłał "Registerme"!
