#!/usr/bin/env python3
"""
Web server dla Mesh Scout - wyświetla zarejestrowane urządzenia na mapie
"""

from flask import Flask, jsonify, render_template, send_from_directory, request, session
from flask_cors import CORS
from flask_caching import Cache
from flask_compress import Compress
import os
import sys
import json
from datetime import datetime
from database import MeshtasticDatabase
from version import VERSION

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
CORS(app)  # Enable CORS for API endpoints

# Configure Flask-Caching
cache = Cache(config={
    'CACHE_TYPE': 'SimpleCache',  # In-memory cache
    'CACHE_DEFAULT_TIMEOUT': 300  # 5 minutes default
})
cache.init_app(app)

# Configure Flask-Compress (gzip compression)
compress = Compress()
compress.init_app(app)

# Ścieżka do bazy danych
import os

DB_PATH = os.environ.get('DB_PATH', 'data/mesh_scout.db')

# Ensure the data directory exists if using the default path
if DB_PATH == 'data/mesh_scout.db':
    os.makedirs('data', exist_ok=True)

# Load translations
TRANSLATIONS = {}
TRANSLATIONS_DIR = os.path.join(os.path.dirname(__file__), 'translations')

def load_translations():
    """Load all translation files"""
    global TRANSLATIONS
    for lang in ['pl', 'en']:
        lang_file = os.path.join(TRANSLATIONS_DIR, f'{lang}.json')
        if os.path.exists(lang_file):
            with open(lang_file, 'r', encoding='utf-8') as f:
                TRANSLATIONS[lang] = json.load(f)
    print(f"Loaded translations: {list(TRANSLATIONS.keys())}")

load_translations()

def get_language():
    """Get current language from cookie or default to pl"""
    return request.cookies.get('language', 'pl')


def format_timestamp(ts_str):
    """Formatuje timestamp do ISO format z UTC timezone"""
    if not ts_str:
        return None
    try:
        # SQLite zapisuje w UTC bez tzinfo
        dt = datetime.fromisoformat(ts_str)
        # Oznacz jako UTC i zwróć w formacie ISO z 'Z'
        # JavaScript automatycznie skonwertuje na lokalny czas przeglądarki
        from datetime import timezone
        dt_utc = dt.replace(tzinfo=timezone.utc)
        return dt_utc.isoformat()
    except (ValueError, TypeError):
        return ts_str


# === TRANSLATION ENDPOINTS ===

@app.route('/api/translations/<lang>')
def get_translations(lang):
    """Get translations for specified language"""
    if lang not in TRANSLATIONS:
        return jsonify({'success': False, 'error': 'Language not found'}), 404
    return jsonify({
        'success': True,
        'language': lang,
        'translations': TRANSLATIONS[lang]
    })

@app.route('/api/set-language/<lang>')
def set_language(lang):
    """Set language preference"""
    if lang not in ['pl', 'en']:
        return jsonify({'success': False, 'error': 'Invalid language'}), 400

    response = jsonify({'success': True, 'language': lang})
    response.set_cookie('language', lang, max_age=31536000)  # 1 year
    return response

# === PAGE ROUTES ===

@app.route('/')
def index():
    """Strona główna z mapą"""
    lang = get_language()
    return render_template('index.html', version=VERSION, lang=lang)


@app.route('/player/<node_id>')
def player_page(node_id):
    """Strona dedykowana dla gracza z mapą traceroute"""
    lang = get_language()
    return render_template('player.html', node_id=node_id, version=VERSION, lang=lang)


@app.route('/api/player/<node_id>/details')
def get_player_details(node_id):
    """API endpoint - szczegółowe dane gracza"""
    try:
        db = MeshtasticDatabase(DB_PATH)

        # Pobierz dane urządzenia
        device = db.get_device(node_id)
        if not device:
            db.close()
            return jsonify({
                'success': False,
                'error': 'Player not found'
            }), 404

        # Pobierz wynik gracza
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT total_points, total_traceroutes_sent, total_hops_responded, last_traceroute
            FROM player_scores
            WHERE node_id = ?
        """, (node_id,))

        score = cursor.fetchone()

        # Pobierz najdłuższy traceroute
        longest_traceroute = db.get_longest_traceroute(node_id)

        # Formatuj dane
        player_data = {
            'node_id': device['node_id'],
            'is_player': bool(device.get('is_player', 0)),
            'user_longname': device.get('user_longname'),
            'user_shortname': device.get('user_shortname'),
            'channel_id': device.get('channel_id'),
            'hw_model': device.get('hw_model'),
            'role': device.get('role'),
            'last_latitude': device.get('last_latitude'),
            'last_longitude': device.get('last_longitude'),
            'last_altitude': device.get('last_altitude'),
            'last_battery_level': device.get('last_battery_level'),
            'last_voltage': device.get('last_voltage'),
            'total_messages': device.get('total_messages', 0),
            'registered_at': format_timestamp(device.get('registered_at')),
            'last_seen': format_timestamp(device.get('last_seen')),
            'total_points': score[0] if score else 0,
            'total_traceroutes': score[1] if score else 0,
            'total_hops_responded': score[2] if score else 0,
            'last_traceroute': format_timestamp(score[3]) if score and score[3] else None,
            'longest_traceroute': {
                'distance_km': longest_traceroute['distance_km'],
                'hop_node': longest_traceroute['hop_node'],
                'hop_name': longest_traceroute['hop_name'],
                'points': longest_traceroute['points'],
                'received_at': format_timestamp(longest_traceroute['received_at']),
                'hops_forward': longest_traceroute['hops_forward'],
                'hops_back': longest_traceroute['hops_back']
            } if longest_traceroute else None
        }

        db.close()

        return jsonify({
            'success': True,
            'player': player_data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/devices')
@cache.cached(timeout=600)  # 10 minut cache
def get_devices():
    """API endpoint - lista wszystkich zarejestrowanych urządzeń"""
    try:
        # Wysoki limit - praktycznie wszystkie urządzenia
        limit = int(request.args.get('limit', 10000))
        db = MeshtasticDatabase(DB_PATH)
        devices = db.get_all_devices(limit=limit)
        db.close()

        # Filtruj urządzenia z pozycją GPS
        devices_with_gps = []
        devices_without_gps = []

        for device in devices:
            # Formatuj dane
            device_data = {
                'node_id': device['node_id'],
                'is_player': bool(device.get('is_player', 0)),
                'channel_id': device.get('channel_id'),
                'user_longname': device.get('user_longname'),
                'user_shortname': device.get('user_shortname'),
                'hw_model': device.get('hw_model'),
                'role': device.get('role'),
                'last_latitude': device.get('last_latitude'),
                'last_longitude': device.get('last_longitude'),
                'last_altitude': device.get('last_altitude'),
                'last_battery_level': device.get('last_battery_level'),
                'last_voltage': device.get('last_voltage'),
                'total_messages': device.get('total_messages', 0),
                'registered_at': format_timestamp(device.get('registered_at')),
                'last_seen': format_timestamp(device.get('last_seen'))
            }

            # Sprawdź czy ma GPS
            if device_data['last_latitude'] and device_data['last_longitude']:
                devices_with_gps.append(device_data)
            else:
                devices_without_gps.append(device_data)

        return jsonify({
            'success': True,
            'total': len(devices),
            'with_gps': len(devices_with_gps),
            'without_gps': len(devices_without_gps),
            'devices': devices_with_gps + devices_without_gps
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/device/<node_id>')
def get_device(node_id):
    """API endpoint - szczegóły konkretnego urządzenia"""
    try:
        db = MeshtasticDatabase(DB_PATH)
        device = db.get_device(node_id)
        db.close()

        if not device:
            return jsonify({
                'success': False,
                'error': 'Device not found'
            }), 404

        # Formatuj dane
        device_data = {
            'node_id': device['node_id'],
            'is_player': bool(device.get('is_player', 0)),
            'channel_id': device.get('channel_id'),
            'user_longname': device.get('user_longname'),
            'user_shortname': device.get('user_shortname'),
            'hw_model': device.get('hw_model'),
            'role': device.get('role'),
            'last_latitude': device.get('last_latitude'),
            'last_longitude': device.get('last_longitude'),
            'last_altitude': device.get('last_altitude'),
            'last_battery_level': device.get('last_battery_level'),
            'last_voltage': device.get('last_voltage'),
            'registration_message': device.get('registration_message'),
            'total_messages': device.get('total_messages', 0),
            'registered_at': format_timestamp(device.get('registered_at')),
            'last_seen': format_timestamp(device.get('last_seen'))
        }

        return jsonify({
            'success': True,
            'device': device_data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stats')
@cache.cached(timeout=600)  # 10 minut cache
def get_stats():
    """API endpoint - statystyki"""
    try:
        db = MeshtasticDatabase(DB_PATH)

        # Pobierz wszystkie urządzenia
        devices = db.get_all_devices(limit=10000)

        # Statystyki wiadomości
        db_stats = db.get_statistics()

        db.close()

        # Policz statystyki
        total_devices = len(devices)
        devices_with_gps = sum(1 for d in devices if d.get('last_latitude') and d.get('last_longitude'))

        # Kanały
        channels = {}
        for device in devices:
            ch = device.get('channel_id', 'unknown')
            channels[ch] = channels.get(ch, 0) + 1

        # Ostatnio widziane
        recent_devices = sorted(
            devices,
            key=lambda x: x.get('last_seen', ''),
            reverse=True
        )[:10]

        recent_list = []
        for device in recent_devices:
            recent_list.append({
                'node_id': device['node_id'],
                'user_longname': device.get('user_longname'),
                'last_seen': format_timestamp(device.get('last_seen'))
            })

        return jsonify({
            'success': True,
            'stats': {
                'total_devices': total_devices,
                'devices_with_gps': devices_with_gps,
                'devices_without_gps': total_devices - devices_with_gps,
                'total_messages': db_stats.get('total_messages', 0),
                'unique_nodes': db_stats.get('unique_nodes', 0),
                'channels': channels,
                'recent_devices': recent_list
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/highscore')
def get_highscore():
    """API endpoint - ranking graczy (highscore)"""
    try:
        limit = int(request.args.get('limit', 20))
        db = MeshtasticDatabase(DB_PATH)
        highscore = db.get_highscore(limit=limit)
        db.close()

        # Formatuj dane
        results = []
        for idx, entry in enumerate(highscore, 1):
            results.append({
                'rank': idx,
                'node_id': entry['node_id'],
                'total_points': entry['total_points'],
                'total_traceroutes': entry.get('total_traceroutes_sent', 0),
                'last_traceroute': format_timestamp(entry.get('last_traceroute')),
                'user_longname': entry.get('user_longname'),
                'user_shortname': entry.get('user_shortname'),
                'channel_id': entry.get('channel_id'),
                'last_latitude': entry.get('last_latitude'),
                'last_longitude': entry.get('last_longitude')
            })

        return jsonify({
            'success': True,
            'total': len(results),
            'highscore': results
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/player/<node_id>/traceroutes')
def get_player_traceroutes(node_id):
    """API endpoint - traceroutes konkretnego gracza"""
    try:
        limit = int(request.args.get('limit', 50))
        db = MeshtasticDatabase(DB_PATH)

        # Pobierz traceroutes gracza z liczbą wykonanych dzisiaj
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT
                t.packet_id,
                t.hop_node,
                t.hop_number,
                t.distance_km,
                t.points,
                t.received_at,
                d.user_longname as hop_name,
                d.user_shortname as hop_short,
                t.route_path,
                t.route_back,
                t.is_confirmed,
                (SELECT COUNT(*) 
                 FROM traceroute_packets t2 
                 WHERE t2.sender_node = t.sender_node 
                   AND t2.hop_node = t.hop_node 
                   AND t2.is_confirmed = 1 
                   AND DATE(t2.received_at) = DATE(t.received_at)
                ) as today_count
            FROM traceroute_packets t
            LEFT JOIN devices d ON t.hop_node = d.node_id
            WHERE t.sender_node = ?
            ORDER BY t.received_at DESC
            LIMIT ?
        """, (node_id, limit))

        traceroutes = []
        for row in cursor.fetchall():
            hop_name = row[6] or row[1]  # longname lub node_id
            if row[7]:  # shortname
                hop_name = f"{hop_name} ({row[7]})"

            # Zdekoduj route_path i route_back z JSON
            route_path = None
            route_back = None
            if row[8]:  # route_path
                try:
                    import json
                    route_path = json.loads(row[8])
                except (json.JSONDecodeError, TypeError):
                    route_path = None
            if row[9]:  # route_back
                try:
                    import json
                    route_back = json.loads(row[9])
                except (json.JSONDecodeError, TypeError):
                    route_back = None

            is_confirmed = bool(row[10]) if row[10] is not None else False
            today_count = row[11] if len(row) > 11 else 1

            traceroutes.append({
                'packet_id': row[0],
                'hop_node': row[1],
                'hop_name': hop_name,
                'hop_number': row[2],
                'distance_km': round(row[3], 2) if row[3] else 0,
                'points': row[4],
                'received_at': format_timestamp(row[5]),
                'route_path': route_path,
                'route_back': route_back,
                'is_confirmed': is_confirmed,
                'is_direct': route_path and len(route_path) == 1,
                'hops_forward': len(route_path) if route_path else 0,
                'hops_back': len(route_back) if route_back else 0,
                'today_count': today_count
            })

        db.close()

        return jsonify({
            'success': True,
            'node_id': node_id,
            'total': len(traceroutes),
            'traceroutes': traceroutes
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/traceroute/<int:packet_id>/raw')
def get_traceroute_raw_packets(packet_id):
    """API endpoint - surowe pakiety dla danego traceroute"""
    try:
        db = MeshtasticDatabase(DB_PATH)
        cursor = db.conn.cursor()

        # Najpierw pobierz informacje o traceroute
        cursor.execute("""
            SELECT sender_node, hop_node, received_at
            FROM traceroute_packets
            WHERE packet_id = ?
            LIMIT 1
        """, (packet_id,))

        tr = cursor.fetchone()
        if not tr:
            return jsonify({
                'success': False,
                'error': 'Traceroute not found'
            }), 404

        sender_node, hop_node, received_at = tr

        # Pobierz wszystkie wiadomości traceroute między tymi węzłami
        # w oknie czasowym ±60 sekund od received_at
        # Szukamy wiadomości REQUEST (sender->hop) i RESPONSE (hop->sender)
        cursor.execute("""
            SELECT
                m.id,
                m.received_at,
                m.message_id,
                m.from_node,
                m.to_node,
                m.message_type,
                m.snr,
                m.rssi,
                m.hop_limit,
                m.raw_json,
                m.channel_id
            FROM messages m
            WHERE m.message_type = 'TRACEROUTE_APP'
              AND (
                  (m.from_node = ? AND m.to_node = ?)
                  OR (m.from_node = ? AND m.to_node = ?)
                  OR m.message_id = ?
              )
              AND datetime(m.received_at) >= datetime(?, '-60 seconds')
              AND datetime(m.received_at) <= datetime(?, '+60 seconds')
            ORDER BY m.received_at ASC
        """, (sender_node, hop_node, hop_node, sender_node, packet_id, received_at, received_at))

        packets = []
        for row in cursor.fetchall():
            # Parsuj raw_json
            raw_data = None
            if row[9]:  # raw_json
                try:
                    import json
                    raw_data = json.loads(row[9])
                except (json.JSONDecodeError, TypeError):
                    raw_data = row[9]

            packets.append({
                'id': row[0],
                'received_at': format_timestamp(row[1]),
                'message_id': row[2],
                'from_node': row[3],
                'to_node': row[4],
                'message_type': row[5],
                'snr': row[6],
                'rssi': row[7],
                'hop_limit': row[8],
                'raw_json': raw_data,
                'channel_id': row[10]
            })

        db.close()

        return jsonify({
            'success': True,
            'packet_id': packet_id,
            'sender_node': sender_node,
            'hop_node': hop_node,
            'total': len(packets),
            'packets': packets
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/highscore/<period>')
@cache.cached(timeout=300, query_string=True)  # 5 minut cache z parametrami
def get_highscore_period(period):
    """API endpoint - ranking graczy dla danego okresu (today, week, month, all)"""
    try:
        if period not in ['today', 'week', 'month', 'all']:
            return jsonify({
                'success': False,
                'error': 'Invalid period. Use: today, week, month, all'
            }), 400

        limit = int(request.args.get('limit', 20))
        db = MeshtasticDatabase(DB_PATH)
        highscore = db.get_highscore_period(period=period, limit=limit)
        db.close()

        # Formatuj dane
        results = []
        for idx, entry in enumerate(highscore, 1):
            results.append({
                'rank': idx,
                'node_id': entry['node_id'],
                'total_points': entry['total_points'],
                'total_traceroutes': entry.get('total_traceroutes', 0),
                'last_traceroute': format_timestamp(entry.get('last_traceroute')),
                'user_longname': entry.get('user_longname'),
                'user_shortname': entry.get('user_shortname'),
                'channel_id': entry.get('channel_id'),
                'last_latitude': entry.get('last_latitude'),
                'last_longitude': entry.get('last_longitude')
            })

        return jsonify({
            'success': True,
            'period': period,
            'total': len(results),
            'highscore': results
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/winners/<period_type>')
@cache.cached(timeout=300, query_string=True)  # 5 minut cache
def get_period_winners(period_type):
    """API endpoint - zwycięzcy z zakończonych okresów (day, week, month)"""
    try:
        if period_type not in ['day', 'week', 'month']:
            return jsonify({
                'success': False,
                'error': 'Invalid period_type. Use: day, week, month'
            }), 400

        limit = int(request.args.get('limit', 30))
        db = MeshtasticDatabase(DB_PATH)
        winners = db.get_period_winners(period_type=period_type, limit=limit)
        db.close()

        return jsonify({
            'success': True,
            'period_type': period_type,
            'total': len(winners),
            'winners': winners
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/winners')
def winners_page():
    """Strona ze zwycięzcami z różnych okresów"""
    lang = get_language()
    return render_template('winners.html', version=VERSION, lang=lang)


@app.route('/rules')
def rules_page():
    """Strona z zasadami gry"""
    lang = get_language()
    return render_template('rules.html', version=VERSION, lang=lang)


@app.route('/coverage')
def coverage_page():
    """Strona z mapą zasięgu sieci (H3 hexagons)"""
    lang = get_language()
    return render_template('coverage.html', version=VERSION, lang=lang)


# === H3 HEXAGON API ENDPOINTS ===

@app.route('/api/coverage')
@cache.cached(timeout=900, query_string=True)  # 15 minut cache
def get_coverage_map():
    """API endpoint - mapa zasięgu sieci (aktywne heksagony H3)

    Domyślnie zwraca 5000 najbardziej aktywnych hexów z min. 2 wizytami.
    Parametry query string:
    - limit: maksymalna liczba hexów do zwrócenia (domyślnie 5000)
    - min_activity: minimalna liczba wizyt w hexie (domyślnie 2)
    """
    try:
        # Ograniczone limity dla szybszego ładowania i renderowania mapy
        limit = int(request.args.get('limit', 5000))
        min_activity = int(request.args.get('min_activity', 2))
        
        db = MeshtasticDatabase(DB_PATH)
        coverage = db.get_coverage_map(limit=limit, min_activity=min_activity)
        db.close()

        if not coverage:
            return jsonify({
                'success': True,
                'total': 0,
                'hexagons': [],
                'message': 'No H3 data available. H3 features may be disabled or no players have visited any hexagons yet.'
            })

        # Konwertuj heksagony do GeoJSON dla Leaflet
        try:
            from h3_utils import hexagons_to_geojson_feature_collection
            geojson = hexagons_to_geojson_feature_collection(coverage, include_properties=True)
        except ImportError:
            # Fallback jeśli h3_utils nie jest dostępne
            geojson = None

        return jsonify({
            'success': True,
            'total': len(coverage),
            'hexagons': coverage,
            'geojson': geojson
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/player/<node_id>/hexagons')
def get_player_hexagons(node_id):
    """API endpoint - lista odwiedzonych heksagonów przez gracza"""
    try:
        limit = int(request.args.get('limit', 1000))
        days = int(request.args.get('days', 0))  # Filtr po dniach (0 = wszystkie)

        db = MeshtasticDatabase(DB_PATH)
        hexagons = db.get_device_hexagons(node_id, limit=limit, days=days)
        db.close()

        if not hexagons:
            return jsonify({
                'success': True,
                'node_id': node_id,
                'total': 0,
                'hexagons': [],
                'message': 'No hexagon data available for this player.'
            })

        # Konwertuj do GeoJSON
        try:
            from h3_utils import hexagons_to_geojson_feature_collection
            geojson = hexagons_to_geojson_feature_collection(hexagons, include_properties=True)
        except ImportError:
            geojson = None

        # Formatuj daty
        for hex_data in hexagons:
            hex_data['first_visit'] = format_timestamp(hex_data.get('first_visit'))
            hex_data['last_visit'] = format_timestamp(hex_data.get('last_visit'))

        return jsonify({
            'success': True,
            'node_id': node_id,
            'total': len(hexagons),
            'hexagons': hexagons,
            'geojson': geojson
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/hex/<h3_index>/stats')
def get_hex_stats(h3_index):
    """API endpoint - statystyki konkretnego heksagonu"""
    try:
        db = MeshtasticDatabase(DB_PATH)
        stats = db.get_hex_statistics(h3_index)
        db.close()

        if not stats:
            return jsonify({
                'success': False,
                'error': 'Hexagon not found or H3 features disabled'
            }), 404

        # Formatuj dane
        stats['last_activity'] = format_timestamp(stats.get('last_activity'))

        # Dodaj geometrię heksagonu
        try:
            from h3_utils import h3_to_geojson_polygon, h3_to_lat_lon
            stats['geometry'] = h3_to_geojson_polygon(h3_index)
            center = h3_to_lat_lon(h3_index)
            if center:
                stats['center'] = {'lat': center[0], 'lon': center[1]}
        except ImportError:
            pass

        return jsonify({
            'success': True,
            'hexagon': stats
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/hex/<h3_index>/details')
def get_hex_details(h3_index):
    """API endpoint - szczegółowe informacje o heksagonie (gracze, traceroutes)"""
    try:
        limit_traceroutes = int(request.args.get('limit_traceroutes', 50))
        limit_players = int(request.args.get('limit_players', 100))
        
        db = MeshtasticDatabase(DB_PATH)
        details = db.get_hex_details(h3_index, limit_traceroutes, limit_players)
        db.close()

        if not details:
            return jsonify({
                'success': False,
                'error': 'Hexagon not found or H3 features disabled'
            }), 404

        # Formatuj daty w statystykach
        if details.get('statistics'):
            details['statistics']['last_activity'] = format_timestamp(
                details['statistics'].get('last_activity')
            )

        # Formatuj daty dla graczy
        for player in details.get('players', []):
            player['first_visit'] = format_timestamp(player.get('first_visit'))
            player['last_visit'] = format_timestamp(player.get('last_visit'))

        # Formatuj daty dla traceroutes
        for tr in details.get('traceroutes', []):
            tr['received_at'] = format_timestamp(tr.get('received_at'))

        # Dodaj geometrię heksagonu
        try:
            from h3_utils import h3_to_geojson_polygon, h3_to_lat_lon
            details['geometry'] = h3_to_geojson_polygon(h3_index)
            center = h3_to_lat_lon(h3_index)
            if center:
                details['center'] = {'lat': center[0], 'lon': center[1]}
        except ImportError:
            pass

        return jsonify({
            'success': True,
            'hexagon': details
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/h3/resolution/<int:resolution>')
def get_h3_resolution_info(resolution):
    """API endpoint - informacje o rozdzielczości H3"""
    try:
        from h3_utils import get_resolution_info
        info = get_resolution_info(resolution)
        
        return jsonify({
            'success': True,
            'resolution_info': info
        })
    except ImportError:
        return jsonify({
            'success': False,
            'error': 'H3 utilities not available'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/hex/connections')
@cache.cached(timeout=1800, query_string=True)  # 30 minut cache
def get_hex_connections():
    """API endpoint - połączenia między heksagonami na podstawie traceroute"""
    try:
        days = int(request.args.get('days', 31))
        limit = int(request.args.get('limit', 10000))
        min_traceroutes = int(request.args.get('min_traceroutes', 1))
        
        db = MeshtasticDatabase(DB_PATH)
        connections = db.get_hex_connections(days=days, limit=limit, min_traceroutes=min_traceroutes)
        db.close()

        if not connections:
            return jsonify({
                'success': True,
                'total': 0,
                'connections': [],
                'message': 'No H3 connection data available. H3 features may be disabled or no traceroutes have been recorded yet.'
            })

        return jsonify({
            'success': True,
            'total': len(connections),
            'connections': connections,
            'filters': {
                'days': days,
                'min_traceroutes': min_traceroutes
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok'})


@app.route('/api/database/health')
def database_health():
    """Database health check endpoint - checks integrity and returns status"""
    try:
        db = MeshtasticDatabase(DB_PATH)

        # Verify database integrity
        is_healthy = db.verify_integrity()

        # Get database file size
        import os
        db_size = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        db_size_mb = round(db_size / (1024 * 1024), 2)

        # Get WAL file size if exists
        wal_path = DB_PATH.replace('.db', '.db-wal')
        wal_size = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
        wal_size_mb = round(wal_size / (1024 * 1024), 2)

        # Perform checkpoint to minimize WAL size
        if wal_size_mb > 10:  # If WAL is larger than 10MB
            db.checkpoint_wal()

        db.close()

        return jsonify({
            'success': True,
            'database_healthy': is_healthy,
            'database_size_mb': db_size_mb,
            'wal_size_mb': wal_size_mb,
            'status': 'healthy' if is_healthy else 'corrupted'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'database_healthy': False,
            'error': str(e),
            'status': 'error'
        }), 500


# === CACHE MANAGEMENT ENDPOINTS ===

@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """Clear all cache - useful after database updates"""
    try:
        cache.clear()
        return jsonify({
            'success': True,
            'message': 'Cache cleared successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/cache/info')
def cache_info():
    """Get cache configuration info"""
    return jsonify({
        'success': True,
        'cache_type': 'SimpleCache',
        'default_timeout': 300,
        'endpoints_cached': {
            '/api/devices': '600s (10 min)',
            '/api/stats': '600s (10 min)',
            '/api/highscore/<period>': '300s (5 min)',
            '/api/winners/<period_type>': '300s (5 min)',
            '/api/coverage': '900s (15 min)',
            '/api/hex/connections': '1800s (30 min)'
        }
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'

    print(f"Starting Mesh Scout Web Server on port {port}")
    print(f"Database: {DB_PATH}")

    app.run(host='0.0.0.0', port=port, debug=debug)
