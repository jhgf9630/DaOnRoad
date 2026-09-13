"""OSRM matrices use bounded 2D tiles; unreachable arcs remain forbidden."""
import hashlib
import ipaddress
import json
import math
import os
import time
from urllib.parse import urlparse
import requests
from routing.distance_cache import DistanceCache
from routing.haversine import build_haversine_matrix

UNREACHABLE = 10 ** 8


def _base_url():
    return os.environ.get('OSRM_BASE_URL', '').strip().rstrip('/')


def _is_local():
    host = urlparse(_base_url()).hostname or ''
    if host in ('localhost', 'osrm'):
        return True
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback
    except ValueError:
        return False


def _delay():
    if not _is_local():
        time.sleep(.8)


def _chunk_limit():
    return min(200, max(2, int(os.environ.get('OSRM_TABLE_COORD_LIMIT', '100'))))


def _signature(nodes):
    payload = [_base_url(), os.environ.get('OSRM_DATA_VERSION', 'korea-v1'), nodes]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _table_request(nodes, sources=None, destinations=None):
    coords = ';'.join(f"{n['lng']},{n['lat']}" for n in nodes)
    params = {'annotations': 'duration'}
    if sources is not None:
        params['sources'] = ';'.join(map(str, sources))
    if destinations is not None:
        params['destinations'] = ';'.join(map(str, destinations))
    for attempt in range(2):
        try:
            _delay()
            response = requests.get(f'{_base_url()}/table/v1/driving/{coords}', params=params, timeout=12)
            response.raise_for_status()
            data = response.json()
            if data.get('code') == 'Ok':
                return data.get('durations')
            return None
        except (requests.RequestException, ValueError):
            if attempt == 0:
                time.sleep(.5)
    return None


def _build_matrix_chunked(nodes, progress=None):
    n, block = len(nodes), max(1, _chunk_limit() // 2)
    full = [[None] * n for _ in range(n)]
    total = math.ceil(n / block) ** 2
    done = 0
    for a in range(0, n, block):
        sources = list(range(a, min(n, a + block)))
        for b in range(0, n, block):
            targets = list(range(b, min(n, b + block)))
            union = list(dict.fromkeys(sources + targets))
            remap = {node: i for i, node in enumerate(union)}
            rows = _table_request([nodes[i] for i in union],
                [remap[i] for i in sources], [remap[i] for i in targets])
            if rows is None or len(rows) != len(sources) or any(not isinstance(row,list) or len(row) != len(targets) for row in rows):
                return None
            for i, src in enumerate(sources):
                for j, dst in enumerate(targets):
                    full[src][dst] = rows[i][j]
            done += 1
            if progress:
                progress(done, total)
    return full


def build_osrm_matrix(nodes, use_cache=True, progress=None):
    # Node labels are excluded: the same coordinates share a matrix.
    coordinates = [{'lat': n['lat'], 'lng': n['lng']} for n in nodes]
    cache = DistanceCache('osrm_matrix_cache.json') if use_cache else None
    key = 'matrix:' + _signature(coordinates)
    hit = cache.get(key) if cache else None
    if hit:
        return hit['matrix'], 'osrm_cached'
    rows = _build_matrix_chunked(coordinates, progress) if _base_url() else None
    if rows is None:
        return build_haversine_matrix(nodes), 'haversine'
    matrix = []
    for i, row in enumerate(rows):
        converted = []
        for j, value in enumerate(row):
            if i == j:
                converted.append(0)
            elif value is None:
                converted.append(UNREACHABLE)
            elif not isinstance(value, (int,float)) or not math.isfinite(value) or value < 0:
                return build_haversine_matrix(nodes), 'haversine'
            else:
                converted.append(math.ceil(value))
        matrix.append(converted)
    if cache:
        cache.set(key, {'matrix': matrix})
    return matrix, 'osrm'


def get_route_polyline(from_node, to_node, cache=None):
    nodes = [{'lat': n['lat'], 'lng': n['lng']} for n in (from_node, to_node)]
    key = 'poly:' + _signature(nodes)
    hit = cache.get(key) if cache else None
    if hit:
        return hit
    coords = ';'.join(f"{n['lng']},{n['lat']}" for n in nodes)
    try:
        _delay()
        r = requests.get(f'{_base_url()}/route/v1/driving/{coords}',
                         params={'overview': 'full', 'geometries': 'geojson', 'steps': 'false'}, timeout=8)
        r.raise_for_status()
        data = r.json()
        if data.get('code') != 'Ok' or not data.get('routes'):
            return None
        points = [[c[1],c[0]] for c in data['routes'][0]['geometry']['coordinates']]
        if cache:
            cache.set(key, points)
        return points
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None


def check_osrm_health():
    info = dict(env_set=bool(_base_url()), is_local=_is_local(), status='unconfigured')
    if not _base_url():
        return info
    try:
        r = requests.get(f'{_base_url()}/nearest/v1/driving/126.9780,37.5665', timeout=3)
        info['status'] = 'ok' if r.ok and r.json().get('code') == 'Ok' else 'error'
    except (requests.RequestException, ValueError):
        info['status'] = 'unreachable'
    return info
