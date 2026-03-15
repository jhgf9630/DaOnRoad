"""
DaOnRoad - 버스 노선 최적화 시스템
FastAPI Backend
"""
import os
from pathlib import Path

# .env 파일 자동 로드
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.upload import router as upload_router
from api.routing import router as routing_router
from api.export import router as export_router

app = FastAPI(
    title="DaOnRoad API",
    description="DaOnRoad - 버스 노선 최적화 시스템",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router, prefix="/api", tags=["upload"])
app.include_router(routing_router, prefix="/api", tags=["routing"])
app.include_router(export_router, prefix="/api", tags=["export"])


@app.get("/")
async def root():
    return {"message": "DaOnRoad API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "DaOnRoad"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
