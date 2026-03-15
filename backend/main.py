"""
DaOnRoad - FastAPI Backend
"""
import os
from pathlib import Path

# ── .env 로드 (모든 import보다 먼저) ────────────────────────────
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ[_k.strip()] = _v.strip()   # setdefault → 직접 set
    print(f"[main] .env 로드 완료")
else:
    print(f"[main] .env 없음 — 환경변수에서 API 키 사용")

# ── API 키 확인 로그 ─────────────────────────────────────────────
_kakao = os.environ.get("KAKAO_API_KEY", "")
_tmap  = os.environ.get("TMAP_API_KEY",  "")
print(f"[main] KAKAO_API_KEY: {'✅ 설정됨 (' + _kakao[:6] + '...)' if _kakao else '❌ 없음'}")
print(f"[main] TMAP_API_KEY:  {'✅ 설정됨' if _tmap else '❌ 없음'}")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.upload import router as upload_router
from api.routing import router as routing_router
from api.export import router as export_router

app = FastAPI(title="DaOnRoad API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api", tags=["upload"])
app.include_router(routing_router, prefix="/api", tags=["routing"])
app.include_router(export_router,  prefix="/api", tags=["export"])


@app.get("/")
async def root():
    return {"message": "DaOnRoad API", "version": "1.0.0"}


@app.get("/health")
async def health():
    kakao = bool(os.environ.get("KAKAO_API_KEY"))
    tmap  = bool(os.environ.get("TMAP_API_KEY"))
    return {
        "status": "ok",
        "service": "DaOnRoad",
        "kakao_key": kakao,
        "tmap_key": tmap
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
