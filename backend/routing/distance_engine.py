"""
DaOnRoad - 이동시간 계산 엔진
★ Kakao Mobility API 사용 안 함 (API 횟수 절약)
★ Haversine 기반 계산만 사용 (캐시 적용)
"""
from routing.haversine import haversine_seconds
from routing.distance_cache import DistanceCache


class DistanceEngine:
    def __init__(self):
        self.cache = DistanceCache()

    def get_road_duration(self, from_lat: float, from_lng: float,
                          to_lat: float, to_lng: float) -> int:
        """
        두 지점 간 이동시간(초) 반환.
        캐시 우선 → Haversine(도로 우회계수 적용)
        """
        cached = self.cache.get_route_time(from_lat, from_lng, to_lat, to_lng)
        if cached is not None:
            return cached

        duration = haversine_seconds(from_lat, from_lng, to_lat, to_lng)
        self.cache.set_route_time(from_lat, from_lng, to_lat, to_lng, duration)
        return duration
