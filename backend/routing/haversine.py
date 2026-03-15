"""
Haversine 거리 계산 모듈
두 좌표 간 직선거리(km) 및 예상 이동시간(분) 계산
"""
import math
from typing import Tuple

EARTH_RADIUS_KM = 6371.0
AVG_SPEED_KMH = 40.0  # 도심 평균 속도


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 간 Haversine 거리(km)"""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def haversine_seconds(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """두 좌표 간 예상 이동시간(초) - 평균 40km/h 기준"""
    km = haversine_km(lat1, lng1, lat2, lng2)
    # 도로 우회 계수 1.3 적용
    road_km = km * 1.3
    hours = road_km / AVG_SPEED_KMH
    seconds = int(hours * 3600)
    # 최소 60초 (정차/탑승 시간)
    return max(seconds, 60)


def build_haversine_matrix(locations: list) -> list:
    """
    locations: [{"lat": float, "lng": float}, ...]
    return: n x n 초 단위 거리 행렬
    """
    n = len(locations)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i][j] = haversine_seconds(
                    locations[i]['lat'], locations[i]['lng'],
                    locations[j]['lat'], locations[j]['lng']
                )
    return matrix
