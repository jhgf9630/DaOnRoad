"""
주소 → 좌표 변환 모듈
Kakao Geocoding API 사용 (Tmap fallback)
"""
import os
import json
import requests
from typing import Optional, Dict
from routing.distance_cache import DistanceCache

KAKAO_API_KEY = os.environ.get("KAKAO_API_KEY", "")
TMAP_API_KEY = os.environ.get("TMAP_API_KEY", "")


class Geocoder:
    def __init__(self):
        self.cache = DistanceCache(cache_file="geocode_cache.json")

    def geocode(self, address: str) -> Optional[Dict[str, float]]:
        """주소를 위경도로 변환. 캐시 우선 조회."""
        cache_key = f"geo:{address}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        result = self._kakao_geocode(address)
        if not result:
            result = self._tmap_geocode(address)
        if not result:
            result = self._fallback_geocode(address)

        if result:
            self.cache.set(cache_key, result)
        return result

    def _kakao_geocode(self, address: str) -> Optional[Dict[str, float]]:
        if not KAKAO_API_KEY:
            return None
        try:
            url = "https://dapi.kakao.com/v2/local/search/address.json"
            headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
            resp = requests.get(url, headers=headers, params={"query": address}, timeout=5)
            data = resp.json()
            docs = data.get("documents", [])
            if docs:
                return {"lat": float(docs[0]["y"]), "lng": float(docs[0]["x"])}
        except Exception:
            pass
        return None

    def _tmap_geocode(self, address: str) -> Optional[Dict[str, float]]:
        if not TMAP_API_KEY:
            return None
        try:
            url = "https://apis.openapi.sk.com/tmap/geo/fullAddrGeo"
            params = {
                "appKey": TMAP_API_KEY,
                "coordType": "WGS84GEO",
                "fullAddr": address,
                "format": "json"
            }
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()
            coords = data.get("coordinateInfo", {}).get("coordinate", [])
            if coords:
                return {"lat": float(coords[0]["lat"]), "lng": float(coords[0]["lon"])}
        except Exception:
            pass
        return None

    def _fallback_geocode(self, address: str) -> Optional[Dict[str, float]]:
        """
        API 키 없을 때 주요 지역 좌표 하드코딩 Fallback (데모용)
        """
        KNOWN = {
            "서울": (37.5665, 126.9780),
            "강남": (37.5172, 127.0473),
            "강남구": (37.5172, 127.0473),
            "인천": (37.4563, 126.7052),
            "연수구": (37.4102, 126.6780),
            "부천": (37.5034, 126.7660),
            "수원": (37.2636, 127.0286),
            "성남": (37.4201, 127.1260),
            "분당": (37.3825, 127.1178),
            "용인": (37.2411, 127.1776),
            "안양": (37.3943, 126.9568),
            "고양": (37.6584, 126.8320),
            "일산": (37.6762, 126.7769),
            "의정부": (37.7382, 127.0338),
            "광명": (37.4784, 126.8665),
            "시흥": (37.3800, 126.8030),
            "안산": (37.3219, 126.8309),
            "김포": (37.6151, 126.7155),
            "하남": (37.5392, 127.2148),
            "광주": (35.1595, 126.8526),
            "대전": (36.3504, 127.3845),
            "대구": (35.8714, 128.6014),
            "부산": (35.1796, 129.0756),
        }
        for keyword, (lat, lng) in KNOWN.items():
            if keyword in address:
                import random
                # 약간의 랜덤 오프셋으로 같은 지역 내 다른 위치 표현
                return {
                    "lat": lat + random.uniform(-0.02, 0.02),
                    "lng": lng + random.uniform(-0.02, 0.02)
                }
        # 완전 알수없는 주소: 서울 기본값 + 랜덤
        import random
        return {
            "lat": 37.5665 + random.uniform(-0.1, 0.1),
            "lng": 126.9780 + random.uniform(-0.1, 0.1)
        }
