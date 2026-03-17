"""
DaOnRoad - Distance Matrix Builder
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[전략]
  OSRM_BASE_URL 설정 여부에 따라 자동 선택:
    ✅ 설정됨 → OSRM Table API (실제 도로 기반 N×N 매트릭스)
    ❌ 없음   → Haversine (직선 × 우회계수 1.3, 40km/h)

  실패 시 자동 Haversine fallback.

[노드 인덱스 구조]
  [0 .. P-1]   : 승객 픽업 위치
  [P]          : 도착지
  [P+1 .. P+V] : 차량 출발지 (차량별 1개)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
from typing import List, Dict, Any
from routing.haversine import build_haversine_matrix, haversine_seconds
from routing.distance_cache import DistanceCache


def _osrm_enabled() -> bool:
    return bool(os.environ.get("OSRM_BASE_URL", "").strip())


class MatrixBuilder:

    # ── 노드 목록 구성 ──────────────────────────────────────────────
    def _build_nodes(self, passengers, vehicles, destination):
        nodes        = []
        node_indices = {"passengers": [], "destination": -1,
                        "vehicle_starts": [], "vehicle_ends": []}

        for i, p in enumerate(passengers):
            nodes.append({"lat": p['lat'], "lng": p['lng'], "label": p['name']})
            node_indices["passengers"].append(i)

        dest_idx = len(nodes)
        nodes.append({"lat": destination['lat'], "lng": destination['lng'],
                      "label": "도착지"})
        node_indices["destination"] = dest_idx

        vehicle_start_indices = []
        for v in vehicles:
            idx = len(nodes)
            nodes.append({
                "lat": v.get('start_lat', destination['lat']),
                "lng": v.get('start_lng', destination['lng']),
                "label": f"{v['bus_id']}_start"
            })
            vehicle_start_indices.append(idx)
        node_indices["vehicle_starts"] = vehicle_start_indices

        vehicle_end_indices = []
        for v in vehicles:
            el = v.get('end_lat') or v.get('start_lat', destination['lat'])
            en = v.get('end_lng') or v.get('start_lng', destination['lng'])
            idx = len(nodes)
            nodes.append({"lat": el, "lng": en, "label": f"{v['bus_id']}_end"})
            vehicle_end_indices.append(idx)
        node_indices["vehicle_ends"] = vehicle_end_indices

        return nodes, node_indices, dest_idx, vehicle_start_indices, vehicle_end_indices

    # ── 메인: Distance Matrix 빌드 ──────────────────────────────────
    def build(self, passengers: List[Dict], vehicles: List[Dict],
              destination: Dict) -> Dict[str, Any]:

        nodes, node_indices, dest_idx, v_start, v_end = \
            self._build_nodes(passengers, vehicles, destination)

        if _osrm_enabled():
            from routing.osrm_service import build_osrm_matrix
            matrix, source = build_osrm_matrix(nodes)
        else:
            print("[matrix] OSRM_BASE_URL 미설정 → Haversine 사용")
            matrix = build_haversine_matrix(nodes)
            source = "haversine"

        print(f"[matrix] 소스={source}, 크기={len(nodes)}×{len(nodes)}")

        return {
            "matrix":                matrix,
            "matrix_source":         source,
            "nodes":                 nodes,
            "node_indices":          node_indices,
            "destination_idx":       dest_idx,
            "vehicle_start_indices": v_start,
            "vehicle_end_indices":   v_end,
        }

    # ── VRP 결과 경로 → Polyline + 이동시간 갱신 ───────────────────
    def refine_with_road_api(self, routes: List[Dict], matrix_result: Dict):
        """
        VRP가 선택한 경로에 대해:
          OSRM 사용 중 → 구간별 실제 도로 Polyline 수집
          Haversine    → 직선 2점 Polyline (지도용)

        각 route에 'polylines' 키 추가:
          route['polylines'] = [
            [[lat,lng], [lat,lng], ...],   # 구간 0 (start→stop1)
            [[lat,lng], [lat,lng], ...],   # 구간 1 (stop1→stop2)
            ...
          ]
        """
        nodes  = matrix_result['nodes']
        matrix = matrix_result['matrix']
        source = matrix_result.get('matrix_source', 'haversine')
        use_osrm_poly = (source in ("osrm", "osrm_cached")) and _osrm_enabled()

        route_cache = None
        if use_osrm_poly:
            from routing.osrm_service import get_route_polyline
            route_cache = DistanceCache(cache_file="osrm_route_cache.json")

        for route in routes:
            stops = route.get('stops', [])
            polylines = []

            for i in range(len(stops) - 1):
                fs = stops[i]
                ts = stops[i + 1]
                fi = fs.get('node_idx', -1)
                ti = ts.get('node_idx', -1)

                # 이동시간 갱신 (이미 OSRM 기반이면 matrix 값 신뢰)
                if fi >= 0 and ti >= 0:
                    fs['travel_time_sec'] = matrix[fi][ti]

                # Polyline 수집
                if use_osrm_poly and fi >= 0 and ti >= 0:
                    from routing.osrm_service import get_route_polyline, _delay
                    _delay()
                    pl = get_route_polyline(nodes[fi], nodes[ti], route_cache)
                    if pl:
                        polylines.append(pl)
                        continue

                # fallback: 직선 2점
                from_lat = fs.get('lat') or (nodes[fi]['lat'] if fi >= 0 else None)
                from_lng = fs.get('lng') or (nodes[fi]['lng'] if fi >= 0 else None)
                to_lat   = ts.get('lat') or (nodes[ti]['lat'] if ti >= 0 else None)
                to_lng   = ts.get('lng') or (nodes[ti]['lng'] if ti >= 0 else None)

                if from_lat and from_lng and to_lat and to_lng:
                    polylines.append([[from_lat, from_lng], [to_lat, to_lng]])

            route['polylines'] = polylines
