#!/usr/bin/env python3
"""
H3 Utilities dla Mesh Scout
Funkcje pomocnicze do pracy z H3 Hexagonal Hierarchical Geospatial Indexing System
"""

import h3
import logging
from typing import Optional, List, Tuple, Dict, Any

logger = logging.getLogger(__name__)

# Domyślna rozdzielczość H3 dla Mesh Scout
DEFAULT_H3_RESOLUTION = 8  # ~0.46 km² per hexagon


def lat_lon_to_h3(lat: float, lon: float, resolution: int = DEFAULT_H3_RESOLUTION) -> Optional[str]:
    """
    Konwertuje współrzędne GPS na H3 index
    
    Args:
        lat: Latitude (szerokość geograficzna)
        lon: Longitude (długość geograficzna)
        resolution: Rozdzielczość H3 (0-15, domyślnie 8)
        
    Returns:
        H3 index jako string lub None w przypadku błędu
    """
    try:
        if lat is None or lon is None:
            return None
            
        # Walidacja współrzędnych
        if not (-90 <= lat <= 90):
            logger.warning(f"Nieprawidłowa latitude: {lat}")
            return None
        if not (-180 <= lon <= 180):
            logger.warning(f"Nieprawidłowa longitude: {lon}")
            return None
            
        # Konwersja na H3 index - wspieraj obie wersje API
        try:
            # Nowa wersja h3 (v4+)
            h3_index = h3.latlng_to_cell(lat, lon, resolution)
        except AttributeError:
            # Stara wersja h3 (v3)
            h3_index = h3.geo_to_h3(lat, lon, resolution)
        
        return h3_index
        
    except Exception as e:
        logger.error(f"Błąd konwersji GPS->H3: {e}")
        return None


def h3_to_lat_lon(h3_index: str) -> Optional[Tuple[float, float]]:
    """
    Konwertuje H3 index na współrzędne GPS (centrum heksagonu)
    
    Args:
        h3_index: H3 index jako string
        
    Returns:
        Tuple (latitude, longitude) lub None w przypadku błędu
    """
    try:
        if not h3_index:
            return None
            
        # Walidacja H3 index - wspieraj obie wersje API
        try:
            is_valid = h3.is_valid_cell(h3_index)  # h3 v4+
        except AttributeError:
            is_valid = h3.h3_is_valid(h3_index)  # h3 v3
            
        if not is_valid:
            logger.warning(f"Nieprawidłowy H3 index: {h3_index}")
            return None
            
        # Konwersja na GPS - wspieraj obie wersje API
        try:
            lat, lon = h3.cell_to_latlng(h3_index)  # h3 v4+
        except AttributeError:
            lat, lon = h3.h3_to_geo(h3_index)  # h3 v3
            
        return (lat, lon)
        
    except Exception as e:
        logger.error(f"Błąd konwersji H3->GPS: {e}")
        return None


def h3_to_boundary(h3_index: str) -> Optional[List[Tuple[float, float]]]:
    """
    Zwraca granicę (boundary) heksagonu jako listę współrzędnych
    
    Args:
        h3_index: H3 index jako string
        
    Returns:
        Lista tuple (latitude, longitude) dla granic heksagonu lub None
    """
    try:
        # Walidacja H3 index - wspieraj obie wersje API
        try:
            is_valid = h3.is_valid_cell(h3_index)  # h3 v4+
        except AttributeError:
            is_valid = h3.h3_is_valid(h3_index)  # h3 v3
            
        if not h3_index or not is_valid:
            return None
            
        # Pobierz granice heksagonu - wspieraj obie wersje API
        try:
            boundary = h3.cell_to_boundary(h3_index)  # h3 v4+
        except AttributeError:
            boundary = h3.h3_to_geo_boundary(h3_index, geo_json=False)  # h3 v3
            
        return boundary
        
    except Exception as e:
        logger.error(f"Błąd pobierania granic H3: {e}")
        return None


def h3_to_geojson_polygon(h3_index: str) -> Optional[Dict[str, Any]]:
    """
    Konwertuje H3 index na GeoJSON polygon (dla Leaflet)
    
    Args:
        h3_index: H3 index jako string
        
    Returns:
        GeoJSON polygon lub None w przypadku błędu
    """
    try:
        # Walidacja H3 index - wspieraj obie wersje API
        try:
            is_valid = h3.is_valid_cell(h3_index)  # h3 v4+
        except AttributeError:
            is_valid = h3.h3_is_valid(h3_index)  # h3 v3
            
        if not h3_index or not is_valid:
            return None
            
        # Pobierz granice - wspieraj obie wersje API
        try:
            # h3 v4+ zwraca listę (lat, lon) tuple
            boundary = h3.cell_to_boundary(h3_index)
        except AttributeError:
            # h3 v3
            boundary = h3.h3_to_geo_boundary(h3_index, geo_json=True)
        
        # GeoJSON wymaga formatu [lon, lat], a h3 zwraca [lat, lon]
        # Musimy zamienić kolejność
        coords = [[lon, lat] for lat, lon in boundary]
        # Zamknij polygon (pierwszy punkt = ostatni punkt)
        coords.append(coords[0])
        
        geojson = {
            "type": "Polygon",
            "coordinates": [coords]
        }
        
        return geojson
        
    except Exception as e:
        logger.error(f"Błąd konwersji H3->GeoJSON: {e}")
        return None


def get_h3_neighbors(h3_index: str, ring: int = 1) -> List[str]:
    """
    Zwraca sąsiednie heksagony (k-ring)
    
    Args:
        h3_index: H3 index jako string
        ring: Odległość pierścienia (1 = bezpośredni sąsiedzi, 2 = sąsiedzi sąsiadów, etc.)
        
    Returns:
        Lista H3 indices sąsiednich heksagonów
    """
    try:
        # Walidacja H3 index - wspieraj obie wersje API
        try:
            is_valid = h3.is_valid_cell(h3_index)  # h3 v4+
        except AttributeError:
            is_valid = h3.h3_is_valid(h3_index)  # h3 v3
            
        if not h3_index or not is_valid:
            return []
            
        # Pobierz k-ring (wszystkie heksagony w promieniu ring) - wspieraj obie wersje API
        try:
            neighbors = h3.grid_ring(h3_index, ring)  # h3 v4+
        except AttributeError:
            neighbors = h3.k_ring(h3_index, ring)  # h3 v3
            neighbors.discard(h3_index)  # Usuń sam heksagon z listy (tylko w v3)
        
        return list(neighbors)
        
    except Exception as e:
        logger.error(f"Błąd pobierania sąsiadów H3: {e}")
        return []


def get_h3_resolution(h3_index: str) -> Optional[int]:
    """
    Zwraca rozdzielczość H3 index
    
    Args:
        h3_index: H3 index jako string
        
    Returns:
        Rozdzielczość (0-15) lub None w przypadku błędu
    """
    try:
        # Walidacja H3 index - wspieraj obie wersje API
        try:
            is_valid = h3.is_valid_cell(h3_index)  # h3 v4+
        except AttributeError:
            is_valid = h3.h3_is_valid(h3_index)  # h3 v3
            
        if not h3_index or not is_valid:
            return None
            
        # Pobierz rozdzielczość - wspieraj obie wersje API
        try:
            return h3.get_resolution(h3_index)  # h3 v4+
        except AttributeError:
            return h3.h3_get_resolution(h3_index)  # h3 v3
        
    except Exception as e:
        logger.error(f"Błąd pobierania rozdzielczości H3: {e}")
        return None


def h3_distance(h3_index1: str, h3_index2: str) -> Optional[int]:
    """
    Oblicza odległość między dwoma heksagonami (liczba hopów)
    
    Args:
        h3_index1: Pierwszy H3 index
        h3_index2: Drugi H3 index
        
    Returns:
        Liczba hopów między heksagonami lub None w przypadku błędu
    """
    try:
        if not h3_index1 or not h3_index2:
            return None
            
        # Walidacja H3 indices - wspieraj obie wersje API
        try:
            is_valid1 = h3.is_valid_cell(h3_index1)  # h3 v4+
            is_valid2 = h3.is_valid_cell(h3_index2)
        except AttributeError:
            is_valid1 = h3.h3_is_valid(h3_index1)  # h3 v3
            is_valid2 = h3.h3_is_valid(h3_index2)
            
        if not is_valid1 or not is_valid2:
            return None
            
        # Sprawdź czy mają tę samą rozdzielczość
        res1 = get_h3_resolution(h3_index1)
        res2 = get_h3_resolution(h3_index2)
        if res1 != res2:
            logger.warning("H3 indices mają różne rozdzielczości")
            return None
            
        # Oblicz odległość - wspieraj obie wersje API
        try:
            return h3.grid_distance(h3_index1, h3_index2)  # h3 v4+
        except AttributeError:
            return h3.h3_distance(h3_index1, h3_index2)  # h3 v3
        
    except Exception as e:
        logger.error(f"Błąd obliczania odległości H3: {e}")
        return None


def get_h3_area_km2(resolution: int = DEFAULT_H3_RESOLUTION) -> float:
    """
    Zwraca przybliżoną powierzchnię heksagonu dla danej rozdzielczości
    
    Args:
        resolution: Rozdzielczość H3 (0-15)
        
    Returns:
        Powierzchnia w km²
    """
    try:
        # Średnia powierzchnia heksagonu w km² dla każdej rozdzielczości
        # Źródło: https://h3geo.org/docs/core-library/restable
        areas = {
            0: 4250546.848,
            1: 607220.9782,
            2: 86745.85403,
            3: 12392.26486,
            4: 1770.323552,
            5: 252.9033645,
            6: 36.1290521,
            7: 5.1612932,
            8: 0.7373276,
            9: 0.1053325,
            10: 0.0150475,
            11: 0.0021496,
            12: 0.0003071,
            13: 0.0000439,
            14: 0.0000063,
            15: 0.0000009
        }
        
        return areas.get(resolution, 0.7373276)  # Domyślnie dla res 8
        
    except Exception as e:
        logger.error(f"Błąd pobierania powierzchni H3: {e}")
        return 0.7373276


def get_h3_edge_length_km(resolution: int = DEFAULT_H3_RESOLUTION) -> float:
    """
    Zwraca przybliżoną długość krawędzi heksagonu dla danej rozdzielczości
    
    Args:
        resolution: Rozdzielczość H3 (0-15)
        
    Returns:
        Długość krawędzi w km
    """
    try:
        # Średnia długość krawędzi w km dla każdej rozdzielczości
        edge_lengths = {
            0: 1107.712591,
            1: 418.6760055,
            2: 158.2446558,
            3: 59.81085794,
            4: 22.6063794,
            5: 8.544408276,
            6: 3.229482772,
            7: 1.220629759,
            8: 0.461354684,
            9: 0.174375668,
            10: 0.065907807,
            11: 0.024910561,
            12: 0.009415526,
            13: 0.003559893,
            14: 0.001348575,
            15: 0.000509713
        }
        
        return edge_lengths.get(resolution, 0.461354684)  # Domyślnie dla res 8
        
    except Exception as e:
        logger.error(f"Błąd pobierania długości krawędzi H3: {e}")
        return 0.461354684


def validate_h3_index(h3_index: str) -> bool:
    """
    Waliduje H3 index
    
    Args:
        h3_index: H3 index jako string
        
    Returns:
        True jeśli prawidłowy, False w przeciwnym razie
    """
    try:
        if not h3_index:
            return False
        # Wspieraj obie wersje API
        try:
            return h3.is_valid_cell(h3_index)  # h3 v4+
        except AttributeError:
            return h3.h3_is_valid(h3_index)  # h3 v3
    except:
        return False


def hexagons_to_geojson_feature_collection(
    hexagons: List[Dict[str, Any]],
    include_properties: bool = True
) -> Dict[str, Any]:
    """
    Konwertuje listę heksagonów na GeoJSON FeatureCollection
    
    Args:
        hexagons: Lista dict z polami 'h3_index' i opcjonalnie innymi właściwościami
        include_properties: Czy dołączyć dodatkowe właściwości do feature
        
    Returns:
        GeoJSON FeatureCollection
    """
    features = []
    
    for hex_data in hexagons:
        h3_index = hex_data.get('h3_index')
        if not h3_index or not validate_h3_index(h3_index):
            continue
            
        # Pobierz geometrię
        geometry = h3_to_geojson_polygon(h3_index)
        if not geometry:
            continue
            
        # Przygotuj właściwości
        properties = {'h3_index': h3_index}
        
        if include_properties:
            # Dodaj wszystkie dodatkowe właściwości oprócz h3_index
            for key, value in hex_data.items():
                if key != 'h3_index':
                    properties[key] = value
        
        # Utwórz feature
        feature = {
            "type": "Feature",
            "geometry": geometry,
            "properties": properties
        }
        
        features.append(feature)
    
    # Utwórz FeatureCollection
    feature_collection = {
        "type": "FeatureCollection",
        "features": features
    }
    
    return feature_collection


def get_resolution_info(resolution: int = DEFAULT_H3_RESOLUTION) -> Dict[str, Any]:
    """
    Zwraca informacje o danej rozdzielczości H3
    
    Args:
        resolution: Rozdzielczość H3 (0-15)
        
    Returns:
        Dict z informacjami o rozdzielczości
    """
    return {
        "resolution": resolution,
        "area_km2": get_h3_area_km2(resolution),
        "edge_length_km": get_h3_edge_length_km(resolution),
        "description": f"Rozdzielczość {resolution} (~{get_h3_area_km2(resolution):.2f} km² per hexagon)"
    }
