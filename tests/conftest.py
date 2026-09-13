import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
# Tests never read/write the user's production address cache.
_cache = tempfile.TemporaryDirectory(prefix='daonroad-tests-')
os.environ['DAONROAD_CACHE_DIR'] = _cache.name
os.environ['KAKAO_API_KEY'] = ''
os.environ['TMAP_API_KEY'] = ''
os.environ['OSRM_BASE_URL'] = ''
