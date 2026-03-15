"""
Distance Matrix 캐시 모듈
distance_cache.json에 저장/로드
"""
import json
import os
from typing import Any, Optional

CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'cache')


class DistanceCache:
    def __init__(self, cache_file: str = "distance_cache.json"):
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.cache_path = os.path.join(CACHE_DIR, cache_file)
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str) -> Optional[Any]:
        return self._data.get(key)

    def set(self, key: str, value: Any):
        self._data[key] = value
        self._save()

    def get_route_time(self, from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> Optional[int]:
        key = f"route:{from_lat:.5f},{from_lng:.5f}:{to_lat:.5f},{to_lng:.5f}"
        return self._data.get(key)

    def set_route_time(self, from_lat: float, from_lng: float, to_lat: float, to_lng: float, seconds: int):
        key = f"route:{from_lat:.5f},{from_lng:.5f}:{to_lat:.5f},{to_lng:.5f}"
        self._data[key] = seconds
        self._save()

    def clear(self):
        self._data = {}
        self._save()
