#!/bin/bash
set -e

echo ""
echo "🚌 DaOnRoad — 버스 노선 최적화 시스템"
echo "================================================"

# Docker 확인
if ! docker info > /dev/null 2>&1; then
    echo ""
    echo "❌ Docker가 실행되지 않았습니다."
    echo ""
    echo "  1. Docker Desktop을 실행하세요."
    echo "  2. 트레이 아이콘이 초록색이 될 때까지 기다리세요."
    echo "  3. 이 스크립트를 다시 실행하세요."
    exit 1
fi

# .env 확인
if [ ! -f "backend/.env" ]; then
    echo ""
    echo "⚠️  backend/.env 파일이 없습니다."
    echo ""
    echo "  backend/.env.example 을 복사해서"
    echo "  backend/.env 로 만들고 API 키를 입력하세요."
    exit 1
fi

echo ""
echo "[1/3] Docker 컨테이너 빌드 및 시작 중..."
docker compose up -d --build

echo ""
echo "[2/3] 백엔드 준비 대기 중..."
until curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; do
    sleep 2
    printf "."
done
echo ""

echo ""
echo "[3/3] 준비 완료!"
echo ""
echo "================================================"
echo "  DaOnRoad 실행 중"
echo "  백엔드:   http://127.0.0.1:8000"
echo "  API 문서: http://127.0.0.1:8000/docs"
echo "================================================"
echo ""
echo "Electron 앱 실행:"
echo "  cd frontend && npm start"
