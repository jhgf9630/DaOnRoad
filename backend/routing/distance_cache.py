"""Thread-safe shared JSON caches with expiry and atomic writes (single worker process)."""
import json
import os
import tempfile
import threading
import time
from pathlib import Path

CACHE_DIR = os.environ.get('DAONROAD_CACHE_DIR', str(Path(__file__).resolve().parent.parent / 'cache'))
_registry = {}
_registry_lock = threading.Lock()


class DistanceCache:
    def __init__(self, cache_file='distance_cache.json'):
        self.cache_path = str(Path(CACHE_DIR).resolve() / cache_file)
        Path(self.cache_path).parent.mkdir(parents=True, exist_ok=True)
        with _registry_lock:
            if self.cache_path not in _registry:
                try:
                    raw = json.loads(Path(self.cache_path).read_text(encoding='utf-8'))
                    data = raw.get('entries', {}) if raw.get('version') == 2 else {}
                except (OSError, ValueError, AttributeError):
                    data = {}
                _registry[self.cache_path] = (threading.RLock(), data)
            self._lock, self._data = _registry[self.cache_path]

    def _save(self):
        now = time.time()
        for key in list(self._data):
            if self._data[key]['expires'] <= now:
                del self._data[key]
        fd, temporary = tempfile.mkstemp(dir=str(Path(self.cache_path).parent), suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'version': 2, 'entries': self._data}, stream, ensure_ascii=False)
            os.replace(temporary, self.cache_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def get(self, key):
        with self._lock:
            entry = self._data.get(key)
            if entry and entry['expires'] > time.time():
                return entry['value']
            return None

    def set(self, key, value, ttl=7 * 86400):
        with self._lock:
            self._data[key] = {'value': value, 'expires': time.time() + ttl}
            self._save()

    def clear(self):
        with self._lock:
            self._data.clear()
            self._save()
