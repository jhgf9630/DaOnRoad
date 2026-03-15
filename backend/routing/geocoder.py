"""
DaOnRoad - 주소/장소 검색 모듈
Kakao Local API (주소검색 + 키워드검색)
★ API 키를 모듈 로드 시점이 아닌 호출 시점에 읽음 → .env 반영 보장
"""
import os
import requests
from typing import Optional, Dict, List
from routing.distance_cache import DistanceCache


def _kakao_key() -> str:
    """호출 시점에 환경변수를 읽어 반환."""
    return os.environ.get("KAKAO_API_KEY", "").strip()


def _tmap_key() -> str:
    return os.environ.get("TMAP_API_KEY", "").strip()


class Geocoder:
    def __init__(self):
        self.cache = DistanceCache(cache_file="geocode_cache.json")

    def geocode(self, address: str) -> Optional[Dict]:
        """최상위 결과 1건. 없으면 None."""
        results = self.search(address, limit=1)
        return results[0] if results else None

    def search(self, query: str, limit: int = 6) -> List[Dict]:
        """
        주소/장소 후보 목록 반환.
        반환 형태: [{lat, lng, address, name, type, category?}, ...]
        """
        query = (query or "").strip()
        if not query:
            return []

        cache_key = f"search:{query}:{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        results: List[Dict] = []
        kakao = _kakao_key()
        tmap  = _tmap_key()

        # ── 1. Kakao 주소 검색 (도로명/지번) ─────────────────────
        if kakao:
            results.extend(self._kakao_addr(query, limit, kakao))

        # ── 2. Kakao 키워드 검색 (장소명/시설명) ─────────────────
        if kakao and len(results) < limit:
            for r in self._kakao_keyword(query, limit, kakao):
                if not self._dup(r, results):
                    results.append(r)
                    if len(results) >= limit:
                        break

        # ── 3. Tmap fallback ──────────────────────────────────────
        if tmap and len(results) < limit:
            for r in self._tmap(query, limit - len(results), tmap):
                if not self._dup(r, results):
                    results.append(r)

        # ── API 키 없음 안내 ──────────────────────────────────────
        if not kakao and not tmap:
            print("[geocoder] ⚠ API 키 없음 — KAKAO_API_KEY 또는 TMAP_API_KEY를 .env에 설정하세요")

        final = results[:limit]
        if final:
            self.cache.set(cache_key, final)
        return final

    # ─── 중복 판별 ────────────────────────────────────────────────
    @staticmethod
    def _dup(item: Dict, existing: List[Dict], tol: float = 0.0001) -> bool:
        return any(
            abs(item['lat'] - x['lat']) < tol and abs(item['lng'] - x['lng']) < tol
            for x in existing
        )

    # ─── Kakao 주소 검색 ─────────────────────────────────────────
    def _kakao_addr(self, query: str, limit: int, key: str) -> List[Dict]:
        try:
            resp = requests.get(
                "https://dapi.kakao.com/v2/local/search/address.json",
                headers={"Authorization": f"KakaoAK {key}"},
                params={"query": query, "size": limit},
                timeout=5
            )
            data = resp.json()

            # 인증 오류 체크
            if data.get("errorType"):
                print(f"[geocoder] Kakao 주소검색 오류: {data}")
                return []

            out = []
            for doc in data.get("documents", []):
                ra = doc.get("road_address")
                a  = doc.get("address")
                road = ra["address_name"] if ra else ""
                jibun= a["address_name"]  if a  else ""
                display = road or jibun
                if not display:
                    continue
                out.append({
                    "lat":     float(doc["y"]),
                    "lng":     float(doc["x"]),
                    "address": display,
                    "name":    display,
                    "road":    road,
                    "jibun":   jibun,
                    "type":    "address"
                })
            return out
        except Exception as e:
            print(f"[geocoder] kakao_addr error: {e}")
            return []

    # ─── Kakao 키워드 검색 ───────────────────────────────────────
    def _kakao_keyword(self, query: str, limit: int, key: str) -> List[Dict]:
        try:
            resp = requests.get(
                "https://dapi.kakao.com/v2/local/search/keyword.json",
                headers={"Authorization": f"KakaoAK {key}"},
                params={"query": query, "size": limit},
                timeout=5
            )
            data = resp.json()

            if data.get("errorType"):
                print(f"[geocoder] Kakao 키워드검색 오류: {data}")
                return []

            out = []
            for doc in data.get("documents", []):
                road  = doc.get("road_address_name", "")
                jibun = doc.get("address_name", "")
                name  = doc.get("place_name", "")
                addr  = road or jibun
                out.append({
                    "lat":      float(doc["y"]),
                    "lng":      float(doc["x"]),
                    "address":  addr,
                    "name":     name,
                    "road":     road,
                    "jibun":    jibun,
                    "type":     "place",
                    "category": doc.get("category_group_name", "")
                })
            return out
        except Exception as e:
            print(f"[geocoder] kakao_keyword error: {e}")
            return []

    # ─── Tmap 주소+POI 검색 ──────────────────────────────────────
    def _tmap(self, query: str, limit: int, key: str) -> List[Dict]:
        results = []
        try:
            resp = requests.get(
                "https://apis.openapi.sk.com/tmap/geo/fullAddrGeo",
                params={"appKey": key, "coordType": "WGS84GEO",
                        "fullAddr": query, "format": "json"},
                timeout=5
            )
            for c in resp.json().get("coordinateInfo", {}).get("coordinate", [])[:limit]:
                lat = float(c.get("lat") or c.get("newLat") or 0)
                lng = float(c.get("lon") or c.get("newLon") or 0)
                if lat and lng:
                    addr = c.get("fullAddress", query)
                    results.append({"lat": lat, "lng": lng, "address": addr,
                                    "name": addr, "type": "address"})
        except Exception as e:
            print(f"[geocoder] tmap_addr error: {e}")

        if len(results) < limit:
            try:
                resp2 = requests.get(
                    "https://apis.openapi.sk.com/tmap/pois",
                    params={"appKey": key, "searchKeyword": query,
                            "count": limit, "version": 1, "format": "json"},
                    timeout=5
                )
                for p in resp2.json().get("searchPoiInfo", {}).get("pois", {}).get("poi", []):
                    lat = float(p.get("noorLat") or p.get("lat") or 0)
                    lng = float(p.get("noorLon") or p.get("lon") or 0)
                    if lat and lng:
                        addr = " ".join(filter(None, [
                            p.get("upperAddrName"), p.get("middleAddrName"), p.get("roadName")
                        ]))
                        results.append({"lat": lat, "lng": lng,
                                        "address": addr, "name": p.get("name", ""),
                                        "type": "place"})
                    if len(results) >= limit:
                        break
            except Exception as e:
                print(f"[geocoder] tmap_poi error: {e}")

        return results[:limit]
