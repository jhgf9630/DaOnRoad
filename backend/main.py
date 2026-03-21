"""
DaOnRoad - FastAPI Backend
"""
import os
from pathlib import Path

# ── .env 로드 ───────────────────────────────────────────────────
# 우선순위: 시스템 환경변수(Docker) > .env 파일
# Docker Compose 실행 시 environment 블록이 우선 적용됨
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            # 시스템 환경변수가 이미 있으면 덮어쓰지 않음 (Docker 우선)
            if _k.strip() not in os.environ:
                os.environ[_k.strip()] = _v.strip()
    print(f"[main] .env 로드 완료")
else:
    print(f"[main] .env 없음 — 환경변수에서 API 키 사용")

# ── API 키 확인 로그 ─────────────────────────────────────────────
_kakao = os.environ.get("KAKAO_API_KEY", "")
_tmap  = os.environ.get("TMAP_API_KEY",  "")
_osrm  = os.environ.get("OSRM_BASE_URL", "")
print(f"[main] KAKAO_API_KEY: {'✅ 설정됨 (' + _kakao[:6] + '...)' if _kakao else '❌ 없음'}")
print(f"[main] TMAP_API_KEY:  {'✅ 설정됨' if _tmap else '❌ 없음'}")
print(f"[main] OSRM_BASE_URL: {'✅ 설정됨 (' + _osrm + ')' if _osrm else '❌ 없음 (직선 경로 사용)'}")

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
