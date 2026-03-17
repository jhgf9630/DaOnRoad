"""
DaOnRoad - OSRM Service (통합 모듈)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OSRM(Open Source Routing Machine)을 사용하여:
  1. N×N 실제 도로 이동시간 매트릭스 생성 (VRP 입력용)
  2. 구간별 실제 도로 경로 Geometry 수집 (지도 Polyline용)

[서버 옵션]
  공용 데모: http://router.project-osrm.org  (무료, 초당 요청 제한)
  로컬 Docker (권장): docker run -p 5000:5000 -v $(pwd)/maps:/data \
      osrm/osrm-backend:latest osrm-routed --algorithm mld /data/korea.osrm
  → .env에 OSRM_BASE_URL=http://localhost:5000 설정

[API 스펙]
  Table API: GET /table/v1/driving/{lng1,lat1;lng2,lat2;...}
    → durations: N×N 이동시간(초)
  Route API: GET /route/v1/driving/{lng1,lat1;lng2,lat2}?geometries=geojson
    → routes[0].geometry.coordinates: 도로 좌표 배열
    → routes[0].duration: 초, routes[0].distance: 미터
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
import time
import requests
from typing import List, Dict, Optional, Tuple
from routing.haversine import haversine_seconds, build_haversine_matrix
from routing.distance_cache import DistanceCache

# ── 환경 설정 ────────────────────────────────────────────────────
PUBLIC_OSRM = "http://router.project-osrm.org"
TIMEOUT     = 12      # 초
RETRY       = 2
RETRY_DELAY = 0.8     # 초 (공용 서버 rate-limit 방지)
PUBLIC_CHUNK = 100    # 공용 서버 1회 최대 노드 수
LOCAL_CHUNK  = 5000   # 로컬 서버 제한 없음


def _base_url() -> str:
    return os.environ.get("OSRM_BASE_URL", PUBLIC_OSRM).rstrip("/")

def _is_local() -> bool:
    u = _base_url()
    return any(k in u for k in ["localhost", "127.0.0.1", "192.168.", "10."])

def _chunk_limit() -> int:
    return LOCAL_CHUNK if _is_local() else PUBLIC_CHUNK

def _delay():
    """공용 서버 사용 시 rate-limit 방지 딜레이"""
    if not _is_local():
        time.sleep(RETRY_DELAY)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Table API: N×N 이동시간 매트릭스
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _table_request(nodes: List[Dict],
                   sources: Optional[List[int]] = None,
                   destinations: Optional[List[int]] = None
                   ) -> Optional[List[List[float]]]:
    """
    OSRM /table/v1/driving 단일 요청.
    반환: durations 행렬 (초, float) | None
    """
    coords = ";".join(f"{n['lng']},{n['lat']}" for n in nodes)
    url    = f"{_base_url()}/table/v1/driving/{coords}"
    params: Dict = {"annotations": "duration"}
    if sources:
        params["sources"]      = ";".join(str(i) for i in sources)
    if destinations:
        params["destinations"] = ";".join(str(i) for i in destinations)

    for attempt in range(RETRY):
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)
            if resp.status_code == 429:
                print("[osrm] Rate-limit (429) → 2초 대기")
                time.sleep(2.0)
                resp = requests.get(url, params=params, timeout=TIMEOUT)
            if resp.status_code != 200:
                print(f"[osrm] Table HTTP {resp.status_code}")
                return None
            data = resp.json()
            if data.get("code") != "Ok":
                print(f"[osrm] Table 오류: {data.get('code')} {data.get('message','')}")
                return None
            return data.get("durations")
        except requests.Timeout:
            print(f"[osrm] Table 타임아웃 (시도 {attempt+1}/{RETRY})")
        except Exception as e:
            print(f"[osrm] Table 예외: {e}")
        if attempt < RETRY - 1:
            time.sleep(RETRY_DELAY)
    return None


def _build_matrix_chunked(nodes: List[Dict]) -> Optional[List[List[float]]]:
    """
    노드 수 > chunk_limit 시 행(row) 단위로 분할 호출 후 재조합.

    예: 노드 150개, 청크 100
      호출1: sources=[0..99]   → 100×150
      호출2: sources=[100..149] → 50×150
      병합 → 150×150
    """
    n     = len(nodes)
    chunk = _chunk_limit()
    if n <= chunk:
        return _table_request(nodes)

    print(f"[osrm] 청크 분할: {n}개 노드 → {chunk}개씩")
    full = [[None] * n for _ in range(n)]
    i = 0
    while i < n:
        j       = min(i + chunk, n)
        sources = list(range(i, j))
        _delay()
        rows = _table_request(nodes, sources=sources)
        if rows is None:
            print(f"[osrm] 청크 {i}~{j} 실패")
            return None
        for k, src in enumerate(sources):
            full[src] = rows[k]
        i = j
    return full


def build_osrm_matrix(nodes: List[Dict],
                      use_cache: bool = True
                      ) -> Tuple[List[List[int]], str]:
    """
    ★ 공개 함수: VRP용 N×N 이동시간 매트릭스(초, int) 생성.

    반환: (matrix, source)
      source: "osrm" | "osrm_cached" | "haversine"
    """
    n   = len(nodes)
    url = _base_url()

    # 캐시 확인
    cache     = DistanceCache(cache_file="osrm_matrix_cache.json") if use_cache else None
    cache_key = None
    if cache:
        sig       = "_".join(f"{nd['lat']:.4f},{nd['lng']:.4f}" for nd in nodes)
        cache_key = f"matrix:{hash(sig)}"
        hit       = cache.get(cache_key)
        if hit:
            print(f"[osrm] 캐시 히트 ({n}×{n})")
            return hit["matrix"], "osrm_cached"

    print(f"[osrm] 서버={url}, 노드={n}개")

    durations = _build_matrix_chunked(nodes)
    if durations is None:
        print("[osrm] ⚠ 실패 → Haversine fallback")
        return build_haversine_matrix(nodes), "haversine"

    # None 셀 보완 (도달 불가 구간)
    matrix     = [[0] * n for _ in range(n)]
    null_cells = 0
    for i in range(n):
        for j in range(n):
            v = durations[i][j] if durations[i] else None
            if v is None or (v == 0 and i != j):
                null_cells += 1
                matrix[i][j] = haversine_seconds(
                    nodes[i]['lat'], nodes[i]['lng'],
                    nodes[j]['lat'], nodes[j]['lng']
                )
            else:
                matrix[i][j] = max(int(v), 0)

    if null_cells:
        print(f"[osrm] null 셀 {null_cells}개 → Haversine 보완")

    avg = sum(matrix[i][j] for i in range(n) for j in range(n) if i != j) // max(n*(n-1), 1)
    print(f"[osrm] ✅ {n}×{n} 완성 (평균 {avg}초/구간)")

    if cache and cache_key:
        cache.set(cache_key, {"matrix": matrix})

    return matrix, "osrm"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Route API: 실제 도로 경로 Geometry
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_route_polyline(from_node: Dict, to_node: Dict,
                       cache: Optional[DistanceCache] = None
                       ) -> Optional[List[List[float]]]:
    """
    두 지점 간 실제 도로 경로 좌표 반환.

    반환: [[lat,lng], ...] Leaflet 직접 사용 가능
          None = 실패 (호출자가 직선으로 fallback)
    """
    if cache:
        ck  = (f"poly:{from_node['lat']:.5f},{from_node['lng']:.5f}:"
               f"{to_node['lat']:.5f},{to_node['lng']:.5f}")
        hit = cache.get(ck)
        if hit:
            return hit

    coords = (f"{from_node['lng']},{from_node['lat']};"
              f"{to_node['lng']},{to_node['lat']}")
    url    = f"{_base_url()}/route/v1/driving/{coords}"
    params = {"overview": "full", "geometries": "geojson", "steps": "false"}

    for attempt in range(RETRY):
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                return None
            # GeoJSON: [lng,lat] → Leaflet: [lat,lng]
            raw    = data["routes"][0]["geometry"]["coordinates"]
            result = [[c[1], c[0]] for c in raw]
            if cache:
                cache.set(ck, result)
            return result
        except requests.Timeout:
            print(f"[osrm] Route 타임아웃 (시도 {attempt+1})")
        except Exception as e:
            print(f"[osrm] Route 예외: {e}")
        if attempt < RETRY - 1:
            time.sleep(RETRY_DELAY)
    return None


def get_routes_polylines(stops: List[Dict]) -> List[List[List[float]]]:
    """
    정류장 순서대로 구간별 Polyline 일괄 조회.
    stops: [{"lat","lng"}, ...]
    반환: [[[lat,lng],...], ...]  (len = len(stops)-1)
    """
    cache     = DistanceCache(cache_file="osrm_route_cache.json")
    polylines = []
    for i in range(len(stops) - 1):
        _delay()
        pl = get_route_polyline(stops[i], stops[i+1], cache)
        if pl:
            polylines.append(pl)
        else:
            # fallback: 직선 2점
            polylines.append([
                [stops[i]['lat'],   stops[i]['lng']],
                [stops[i+1]['lat'], stops[i+1]['lng']]
            ])
    return polylines


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 상태 확인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def check_osrm_health() -> Dict:
    """서울시청 → 강남역 샘플 쿼리로 연결 상태 확인."""
    samples = [
        {"lat": 37.5665, "lng": 126.9780},  # 서울시청
        {"lat": 37.4979, "lng": 127.0276},  # 강남역
    ]
    coords = ";".join(f"{n['lng']},{n['lat']}" for n in samples)
    url    = f"{_base_url()}/table/v1/driving/{coords}"
    info   = {
        "base_url":  _base_url(),
        "is_local":  _is_local(),
        "env_set":   bool(os.environ.get("OSRM_BASE_URL")),
        "status":    "unknown",
        "sample_duration_sec": None,
        "error": None,
    }
    try:
        resp = requests.get(url, params={"annotations": "duration"}, timeout=5)
        data = resp.json()
        if resp.status_code == 200 and data.get("code") == "Ok":
            info["status"] = "ok"
            d = data.get("durations", [[None]])
            info["sample_duration_sec"] = d[0][1] if d and d[0] else None
        else:
            info["status"] = "error"
            info["error"]  = f"HTTP {resp.status_code}: {data.get('message','')}"
    except Exception as e:
        info["status"] = "unreachable"
        info["error"]  = str(e)
    return info
