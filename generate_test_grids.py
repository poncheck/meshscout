#!/usr/bin/env python3
"""
Skrypt do generowania przykładowych danych grid dla testów
"""

import sqlite3
from datetime import datetime, timedelta
import random

# Siatka dla Polski - kilka przykładowych lokalizacji
TEST_LOCATIONS = [
    {"lat": 52.2297, "lon": 21.0122, "name": "Warszawa"},
    {"lat": 50.0647, "lon": 19.9450, "name": "Kraków"},
    {"lat": 51.1079, "lon": 17.0385, "name": "Wrocław"},
    {"lat": 54.3520, "lon": 18.6466, "name": "Gdańsk"},
    {"lat": 51.7592, "lon": 19.4560, "name": "Łódź"},
    {"lat": 53.4285, "lon": 14.5528, "name": "Szczecin"},
    {"lat": 50.2929, "lon": 18.6714, "name": "Katowice"},
    {"lat": 53.1235, "lon": 23.1458, "name": "Białystok"},
]

def calculate_grid_id(latitude: float, longitude: float) -> str:
    """Oblicz ID kwadratu siatki 2km x 2km"""
    GRID_SIZE_KM = 2.0
    lat_idx = int(latitude * 111.32 / GRID_SIZE_KM)
    lon_idx = int(longitude * 111.32 * abs(cos(latitude * 3.14159 / 180)) / GRID_SIZE_KM)
    return f"grid_{lat_idx}_{lon_idx}"

def cos(x):
    """Przybliżenie funkcji cosinus"""
    import math
    return math.cos(x)

def calculate_grid_center(grid_id: str) -> tuple:
    """Oblicz współrzędne środka kwadratu"""
    GRID_SIZE_KM = 2.0
    parts = grid_id.split('_')
    lat_idx = int(parts[1])
    lon_idx = int(parts[2])
    
    center_lat = (lat_idx + 0.5) * GRID_SIZE_KM / 111.32
    center_lon = (lon_idx + 0.5) * GRID_SIZE_KM / (111.32 * abs(cos(center_lat * 3.14159 / 180)))
    
    return center_lat, center_lon

def generate_test_grids(db_path='meshtastic.db'):
    """Generuj przykładowe dane grid"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"Generowanie przykładowych danych grid dla {len(TEST_LOCATIONS)} lokalizacji...")
    
    grids_created = 0
    
    for loc in TEST_LOCATIONS:
        # Wygeneruj kilka gridów wokół każdej lokalizacji
        for dlat in [-0.02, -0.01, 0, 0.01, 0.02]:
            for dlon in [-0.02, -0.01, 0, 0.01, 0.02]:
                lat = loc["lat"] + dlat
                lon = loc["lon"] + dlon
                
                grid_id = calculate_grid_id(lat, lon)
                center_lat, center_lon = calculate_grid_center(grid_id)
                
                # Losowe dane
                unique_nodes = random.randint(1, 10)
                total_visits = random.randint(unique_nodes, unique_nodes * 20)
                first_discovered = datetime.now() - timedelta(days=random.randint(1, 90))
                last_activity = datetime.now() - timedelta(hours=random.randint(0, 48))
                
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO grid_coverage (
                            grid_id, center_latitude, center_longitude,
                            first_discovered, last_activity,
                            total_visits, unique_nodes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        grid_id, center_lat, center_lon,
                        first_discovered.isoformat(),
                        last_activity.isoformat(),
                        total_visits, unique_nodes
                    ))
                    grids_created += 1
                except sqlite3.IntegrityError:
                    pass  # Grid już istnieje
    
    conn.commit()
    conn.close()
    
    print(f"✓ Utworzono {grids_created} przykładowych gridów")
    print(f"✓ Możesz teraz otworzyć mapę i zobaczyć siatkę")

if __name__ == '__main__':
    generate_test_grids()
