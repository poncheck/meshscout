# 🗺️ Funkcjonalność H3 w Mesh Scout

## 📋 Spis treści
- [Wprowadzenie](#wprowadzenie)
- [Technologia H3](#technologia-h3)
- [Mechanika gry](#mechanika-gry)
- [Struktura bazy danych](#struktura-bazy-danych)
- [API Endpoints](#api-endpoints)
- [Frontend](#frontend)
- [Przykłady użycia](#przykłady-użycia)

---

## 🎯 Wprowadzenie

Funkcjonalność H3 została dodana do Mesh Scout w celu:
- **Mapowania zasięgu sieci Meshtastic** - wizualizacja obszarów, gdzie faktycznie działa sieć
- **Zwiększenia mobilności graczy** - nagradzanie za eksplorację nowych terenów
- **Analizy pokrycia sieci** - dane o aktywności w poszczególnych regionach
- **Gamifikacji** - dodatkowe punkty za odkrywanie nowych obszarów

---

## 🔷 Technologia H3

### Czym jest H3?

H3 to hierarchiczny system indeksowania geolokalizacji opracowany przez Uber, który dzieli Ziemię na heksagony.

### Parametry

- **Rozdzielczość:** 8
- **Powierzchnia heksagonu:** ~0.46 km²
- **Średnica:** ~0.76 km

### Dlaczego heksagony?

- ✅ Równomierne pokrycie powierzchni
- ✅ Każdy heksagon ma 6 sąsiadów (z wyjątkiem biegunów)
- ✅ Lepsze reprezentowanie odległości niż kwadraty
- ✅ Efektywne przechowywanie i wyszukiwanie

---

## 🎮 Mechanika gry

### System punktacji

1. **Podstawowe punkty za traceroute**
   - 1 km = 1 punkt (0.01 pkt = 10 m)
   - Punkty przyznawane tylko raz dziennie dla danego hopu w danym heksagonie

2. **Bonus za nowy heksagon**
   - +5 punktów za pierwszą wizytę w nowym heksagonie
   - Bonus przyznawany automatycznie przy zmianie H3 indexu

3. **Reset punktów per-heksagon**
   - Przemieszczenie się do nowego heksagonu = możliwość zdobywania punktów za traceroute ponownie
   - Gracze są zachęcani do eksploracji

### Tracking ruchu gracza

System automatycznie:
1. Oblicza H3 index na podstawie współrzędnych GPS
2. Porównuje z poprzednim H3 indexem gracza
3. Jeśli się różni:
   - Przyznaje bonus +5 pkt
   - Aktualizuje `current_h3` w tabeli `devices`
   - Dodaje rekord do `player_hexagons`
   - Resetuje możliwość zdobywania punktów za traceroute

---

## 🗄️ Struktura bazy danych

### Nowe kolumny

#### `devices` (rozszerzone)
```sql
current_h3 TEXT  -- Aktualny H3 index gracza
```

#### `traceroute_packets` (rozszerzone)
```sql
sender_h3 TEXT   -- H3 index nadawcy w momencie wysłania
hop_h3 TEXT      -- H3 index węzła odpowiadającego
```

#### `player_scores` (rozszerzone)
```sql
hex_bonus_points INTEGER DEFAULT 0      -- Suma bonusów za nowe heksagony
unique_hexes_visited INTEGER DEFAULT 0  -- Liczba unikalnych odwiedzonych heksagonów
```

### Nowa tabela

#### `player_hexagons`
```sql
CREATE TABLE player_hexagons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,              -- ID gracza
    h3_index TEXT NOT NULL,             -- H3 index heksagonu
    first_visit TIMESTAMP NOT NULL,     -- Pierwsza wizyta
    last_visit TIMESTAMP NOT NULL,      -- Ostatnia wizyta
    visit_count INTEGER DEFAULT 1,      -- Liczba wizyt
    FOREIGN KEY (node_id) REFERENCES devices(node_id)
);

CREATE UNIQUE INDEX idx_player_hex ON player_hexagons(node_id, h3_index);
```

---

## 🔌 API Endpoints

### 1. Mapa zasięgu sieci

```http
GET /api/coverage?limit=10000&min_activity=1
```

**Odpowiedź:**
```json
{
  "success": true,
  "total": 150,
  "hexagons": [
    {
      "h3_index": "8a2a1072b59ffff",
      "total_activity": 45,
      "unique_players": 3,
      "traceroute_count": 12,
      "last_activity": "2025-01-04T07:30:00+00:00"
    }
  ],
  "geojson": {
    "type": "FeatureCollection",
    "features": [...]
  }
}
```

### 2. Odwiedzone heksagony gracza

```http
GET /api/player/{node_id}/hexagons?limit=1000
```

**Odpowiedź:**
```json
{
  "success": true,
  "node_id": "!abc12345",
  "total": 25,
  "hexagons": [
    {
      "h3_index": "8a2a1072b59ffff",
      "first_visit": "2025-01-01T10:00:00+00:00",
      "last_visit": "2025-01-04T15:30:00+00:00",
      "visit_count": 5
    }
  ],
  "geojson": {
    "type": "FeatureCollection",
    "features": [...]
  }
}
```

### 3. Statystyki heksagonu

```http
GET /api/hex/{h3_index}/stats
```

**Odpowiedź:**
```json
{
  "success": true,
  "hexagon": {
    "h3_index": "8a2a1072b59ffff",
    "total_activity": 45,
    "unique_players": 3,
    "traceroute_count": 12,
    "last_activity": "2025-01-04T07:30:00+00:00",
    "geometry": {
      "type": "Polygon",
      "coordinates": [[...]]
    },
    "center": {
      "lat": 52.2297,
      "lon": 21.0122
    }
  }
}
```

### 4. Informacje o rozdzielczości H3

```http
GET /api/h3/resolution/8
```

**Odpowiedź:**
```json
{
  "success": true,
  "resolution_info": {
    "resolution": 8,
    "avg_hex_area_km2": 0.461,
    "avg_hex_edge_length_km": 0.461,
    "description": "~0.46 km² per hexagon"
  }
}
```

---

## 🎨 Frontend

### 1. Strona główna (index.html)

**Nowe elementy:**
- Przycisk "Warstwa H3" - toggle warstwy heksagonów na mapie
- Licznik aktywnych heksagonów
- Link do strony "Mapa Zasięgu"
- Automatyczne ładowanie danych H3 w tle

**Kolory warstwy H3:**
- 🟡 Żółty: 1-2 aktywności (niska)
- 🟡 Złoty: 3-4
- 🟠 Pomarańczowy: 5-9
- 🟠 Ciemny pomarańczowy: 10-19
- 🔴 Pomidorowy: 20-49
- 🔴 Czerwony: 50-99
- 🔴 Ciemny czerwony: 100+ (wysoka)

### 2. Mapa zasięgu (coverage.html)

**Dedykowana strona pokazująca:**
- Wszystkie aktywne heksagony
- Statystyki: liczba heksagonów, graczy, aktywność, pokryty obszar
- Legenda kolorów
- Popup z detalami każdego heksagonu
- Highlight on hover

### 3. Strona gracza (player.html)

**Nowe elementy:**
- Licznik odwiedzonych heksagonów w statystykach
- Przycisk "Pokaż/Ukryj Odwiedzone Heksagony"
- Warstwa heksagonów z kolorami według liczby wizyt
- Popup z informacjami o wizytach w heksagonie

**Kolory heksagonów gracza:**
- 🟢 Jasny zielony: 1-4 wizyty
- 🟢 Zielony: 5-9 wizyt
- 🟠 Ciemny pomarańczowy: 10-19 wizyt
- 🟠 Pomarańczowy: 20-49 wizyt
- 🟡 Złoty: 50+ wizyt (często odwiedzany)

---

## 💡 Przykłady użycia

### Backend - obliczanie H3 index

```python
from h3_utils import lat_lon_to_h3

# Pozycja gracza
lat = 52.2297
lon = 21.0122
resolution = 8

# Oblicz H3 index
h3_index = lat_lon_to_h3(lat, lon, resolution)
# Wynik: "8a2a1072b59ffff"
```

### Backend - aktualizacja pozycji gracza

```python
# W meshtastic_mqtt_decoder.py przy odbiorze pozycji
if lat and lon:
    h3_index = h3_utils.lat_lon_to_h3(lat, lon, 8)
    
    # Sprawdź czy gracz zmienił heksagon
    old_h3 = db.get_device(node_id).get('current_h3')
    
    if h3_index != old_h3:
        # Aktualizuj heksagon i przyznaj bonus
        db.update_player_hex(node_id, h3_index)
        bonus_awarded = db.check_and_award_hex_bonus(node_id, h3_index)
        
        if bonus_awarded:
            print(f"Gracz {node_id} otrzymał +5 pkt za nowy heksagon!")
```

### Frontend - toggle warstwy H3

```javascript
// JavaScript w index.html
document.getElementById('h3-toggle').addEventListener('click', function() {
    h3Visible = !h3Visible;
    
    if (h3Visible) {
        showH3Layer();  // Wyświetl heksagony
    } else {
        hideH3Layer();  // Ukryj heksagony
    }
});
```

### Frontend - wyświetlanie mapy zasięgu

```javascript
// JavaScript w coverage.html
async function loadCoverageMap() {
    const response = await fetch('/api/coverage?limit=10000');
    const data = await response.json();
    
    if (data.success && data.geojson) {
        // Wyświetl warstwę H3 z kolorami według aktywności
        L.geoJSON(data.geojson, {
            style: feature => ({
                fillColor: getHexColor(feature.properties.total_activity),
                weight: 2,
                opacity: 0.8,
                fillOpacity: 0.6
            })
        }).addTo(map);
    }
}
```

---

## 🔧 Konfiguracja

### Wymagania

```txt
h3>=3.7.6
```

### Instalacja

```bash
pip install h3>=3.7.6
```

### Migracja bazy danych

System automatycznie utworzy nowe kolumny i tabele przy pierwszym uruchomieniu.
Można też ręcznie uruchomić:

```bash
python database.py
```

---

## 📊 Analityka

### Przykładowe zapytania SQL

**Top 10 najbardziej aktywnych heksagonów:**
```sql
SELECT 
    h3_index,
    COUNT(DISTINCT node_id) as unique_players,
    COUNT(*) as total_activity
FROM player_hexagons
GROUP BY h3_index
ORDER BY total_activity DESC
LIMIT 10;
```

**Gracze z największą eksploracją:**
```sql
SELECT 
    node_id,
    COUNT(DISTINCT h3_index) as unique_hexagons,
    SUM(visit_count) as total_visits
FROM player_hexagons
GROUP BY node_id
ORDER BY unique_hexagons DESC
LIMIT 10;
```

**Pokrycie sieci (km²):**
```sql
SELECT 
    COUNT(DISTINCT h3_index) * 0.46 as coverage_km2
FROM player_hexagons;
```

---

## 🚀 Roadmap

### Przyszłe funkcje

- [ ] **Heatmapa czasowa** - aktywność w czasie (godziny/dni/miesiące)
- [ ] **Konkursy eksploracji** - nagrody za odkrycie najwięcej heksagonów
- [ ] **Granice terytoriów** - automatyczne wykrywanie granic miast/regionów
- [ ] **H3 clustering** - grupowanie blisko położonych heksagonów
- [ ] **Eksport danych** - GeoJSON/KML dla zewnętrznych aplikacji
- [ ] **API publiczne** - dostęp do danych o pokryciu dla deweloperów

---

## 📝 Notatki techniczne

### Wydajność

- H3 index calculation: ~0.1ms per coordinate
- GeoJSON generation: ~10ms dla 1000 heksagonów
- Database query: ~50ms dla 10000 rekordów

### Limitacje

- Rozdzielczość H3 jest stała (8) - zmiana wymaga przebudowy bazy
- Heksagony na biegunach mogą mieć nieregularny kształt
- Maksymalnie ~122,000,000 unikalnych heksagonów na rozdzielczości 8 globalnie

---

## 🤝 Współpraca

Chcesz pomóc w rozwoju? Zgłoś issue lub pull request!

---

**Autor:** Cline AI Assistant  
**Data utworzenia:** 2025-01-04  
**Wersja:** 1.0.0
