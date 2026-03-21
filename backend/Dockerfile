# ── DaOnRoad Backend Dockerfile ──────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# 시스템 패키지 (pandas, openpyxl 의존)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 패키지 설치 (캐시 레이어 분리)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

# 캐시 디렉터리 생성
RUN mkdir -p /app/cache

EXPOSE 8000

CMD ["python", "main.py"]
