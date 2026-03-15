"""
실제 도로 기반 이동시간 조회 엔진
Kakao Mobility API / Tmap Route API 사용
"""
import os
import requests
from typing import Optional
from routing.distance_cache import DistanceCache

KAKAO_API_KEY = os.environ.get("KAKAO_API_KEY", "")
TMAP_API_KEY = os.environ.get("TMAP_API_KEY", "")


class DistanceEngine:
    def __init__(self):
        self.cache = DistanceCache()

    def get_road_duration(self, from_lat: float, from_lng: float,
                          to_lat: float, to_lng: float) -> int:
        """
        두 지점 간 실제 도로 이동시간(초) 반환.
        캐시 → Kakao → Tmap → Haversine 순으로 fallback
        """
        cached = self.cache.get_route_time(from_lat, from_lng, to_lat, to_lng)
        if cached is not None:
            return cached

        duration = self._kakao_road_duration(from_lat, from_lng, to_lat, to_lng)
        if duration is None:
            duration = self._tmap_road_duration(from_lat, from_lng, to_lat, to_lng)
        if duration is None:
            from routing.haversine import haversine_seconds
            duration = haversine_seconds(from_lat, from_lng, to_lat, to_lng)

        self.cache.set_route_time(from_lat, from_lng, to_lat, to_lng, duration)
        return duration

    def _kakao_road_duration(self, from_lat, from_lng, to_lat, to_lng) -> Optional[int]:
        if not KAKAO_API_KEY:
            return None
        try:
            url = "https://apis-navi.kakaomobility.com/v1/directions"
            headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
            params = {
                "origin": f"{from_lng},{from_lat}",
                "destination": f"{to_lng},{to_lat}",
                "priority": "TIME"
            }
            resp = requests.get(url, headers=headers, params=params, timeout=5)
            data = resp.json()
            routes = data.get("routes", [])
            if routes and routes[0].get("result_code") == 0:
                duration = routes[0]["summary"]["duration"]  # 초
                return duration
        except Exception:
            pass
        return None

    def _tmap_road_duration(self, from_lat, from_lng, to_lat, to_lng) -> Optional[int]:
        if not TMAP_API_KEY:
            return None
        try:
            url = "https://apis.openapi.sk.com/tmap/routes"
            params = {
                "appKey": TMAP_API_KEY,
                "startX": from_lng, "startY": from_lat,
                "endX": to_lng, "endY": to_lat,
                "reqCoordType": "WGS84GEO",
                "resCoordType": "WGS84GEO",
                "trafficInfo": "Y"
            }
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()
            features = data.get("features", [])
            if features:
                props = features[0].get("properties", {})
                total_time = props.get("totalTime", 0)  # 초
                return total_time
        except Exception:
            pass
        return None
