"""
DaOnRoad - 주소/장소 검색 모듈
Kakao Local API (주소검색 + 키워드검색) 사용
Tmap fallback
★ fallback 하드코딩 좌표 완전 제거 → 신뢰성 확보
"""
import os
import requests
from typing import Optional, Dict, List
from routing.distance_cache import DistanceCache

KAKAO_API_KEY = os.environ.get("KAKAO_API_KEY", "")
TMAP_API_KEY  = os.environ.get("TMAP_API_KEY", "")


class Geocoder:
    def __init__(self):
        self.cache = DistanceCache(cache_file="geocode_cache.json")

    # ── 단일 좌표 변환 (내부용 / generate-route) ─────────────────
    def geocode(self, address: str) -> Optional[Dict]:
        """최상위 결과 1건만 반환. 없으면 None (하드코딩 fallback 없음)."""
        results = self.search(address, limit=1)
        return results[0] if results else None

    # ── 후보 목록 검색 (UI 자동완성용) ───────────────────────────
    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """
        query에 대해 후보 결과를 최대 limit건 반환.
        각 항목: {lat, lng, address, name, type}
        """
        if not query or not query.strip():
            return []

        cache_key = f"search:{query}:{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        results = []

        # 1순위: Kakao 주소 검색 (도로명/지번 정확도 높음)
        if KAKAO_API_KEY:
            addr_results = self._kakao_address_search(query, limit)
            results.extend(addr_results)

        # 2순위: Kakao 키워드 검색 (학교/시설명 등)
        if KAKAO_API_KEY and len(results) < limit:
            kw_results = self._kakao_keyword_search(query, limit)
            # 중복 제거 (위경도 기준 0.0001도 이내)
            for r in kw_results:
                if not any(abs(r['lat']-x['lat']) < 0.0001 and abs(r['lng']-x['lng']) < 0.0001
                           for x in results):
                    results.append(r)
                    if len(results) >= limit:
                        break

        # 3순위: Tmap 주소 검색
        if TMAP_API_KEY and len(results) < limit:
            tmap_results = self._tmap_search(query, limit - len(results))
            for r in tmap_results:
                if not any(abs(r['lat']-x['lat']) < 0.0001 and abs(r['lng']-x['lng']) < 0.0001
                           for x in results):
                    results.append(r)

        final = results[:limit]
        if final:
            self.cache.set(cache_key, final)
        return final

    # ── Kakao 주소 검색 API ──────────────────────────────────────
    def _kakao_address_search(self, query: str, limit: int) -> List[Dict]:
        try:
            url = "https://dapi.kakao.com/v2/local/search/address.json"
            resp = requests.get(
                url,
                headers={"Authorization": f"KakaoAK {KAKAO_API_KEY}"},
                params={"query": query, "size": limit},
                timeout=5
            )
            data = resp.json()
            out = []
            for doc in data.get("documents", []):
                # road_address 우선, 없으면 address
                ra = doc.get("road_address")
                a  = doc.get("address")
                addr_name = (ra["address_name"] if ra else None) or (a["address_name"] if a else "")
                out.append({
                    "lat":     float(doc["y"]),
                    "lng":     float(doc["x"]),
                    "address": addr_name,
                    "name":    addr_name,
                    "type":    "address"
                })
            return out
        except Exception as e:
            print(f"[geocoder] kakao address error: {e}")
            return []

    # ── Kakao 키워드 검색 API ────────────────────────────────────
    def _kakao_keyword_search(self, query: str, limit: int) -> List[Dict]:
        try:
            url = "https://dapi.kakao.com/v2/local/search/keyword.json"
            resp = requests.get(
                url,
                headers={"Authorization": f"KakaoAK {KAKAO_API_KEY}"},
                params={"query": query, "size": limit},
                timeout=5
            )
            data = resp.json()
            out = []
            for doc in data.get("documents", []):
                out.append({
                    "lat":     float(doc["y"]),
                    "lng":     float(doc["x"]),
                    "address": doc.get("road_address_name") or doc.get("address_name", ""),
                    "name":    doc.get("place_name", ""),
                    "type":    "place",
                    "category": doc.get("category_group_name", "")
                })
            return out
        except Exception as e:
            print(f"[geocoder] kakao keyword error: {e}")
            return []

    # ── Tmap 통합 검색 API ───────────────────────────────────────
    def _tmap_search(self, query: str, limit: int) -> List[Dict]:
        results = []
        # Tmap 주소 검색
        try:
            url = "https://apis.openapi.sk.com/tmap/geo/fullAddrGeo"
            resp = requests.get(url, params={
                "appKey": TMAP_API_KEY, "coordType": "WGS84GEO",
                "fullAddr": query, "format": "json"
            }, timeout=5)
            data = resp.json()
            coords = data.get("coordinateInfo", {}).get("coordinate", [])
            for c in coords[:limit]:
                results.append({
                    "lat":     float(c.get("lat") or c.get("newLat", 0)),
                    "lng":     float(c.get("lon") or c.get("newLon", 0)),
                    "address": c.get("fullAddress", query),
                    "name":    c.get("fullAddress", query),
                    "type":    "address"
                })
        except Exception as e:
            print(f"[geocoder] tmap error: {e}")

        # Tmap 키워드 POI 검색
        if len(results) < limit:
            try:
                url2 = "https://apis.openapi.sk.com/tmap/pois"
                resp2 = requests.get(url2, params={
                    "appKey": TMAP_API_KEY, "searchKeyword": query,
                    "count": limit, "version": 1, "format": "json"
                }, timeout=5)
                data2 = resp2.json()
                pois = data2.get("searchPoiInfo", {}).get("pois", {}).get("poi", [])
                for p in pois:
                    nlon = p.get("noorLon") or p.get("lon", "")
                    nlat = p.get("noorLat") or p.get("lat", "")
                    if nlon and nlat:
                        results.append({
                            "lat":     float(nlat),
                            "lng":     float(nlon),
                            "address": f"{p.get('upperAddrName','')} {p.get('middleAddrName','')} {p.get('roadName','')}".strip(),
                            "name":    p.get("name", ""),
                            "type":    "place"
                        })
                    if len(results) >= limit:
                        break
            except Exception as e:
                print(f"[geocoder] tmap poi error: {e}")

        return results[:limit]
