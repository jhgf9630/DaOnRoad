#!/bin/bash
echo "🚌 DaOnRoad - 백엔드 시작..."
cd "$(dirname "$0")/backend"
if [ ! -d "venv" ]; then
    echo "가상환경 생성 중..."
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt -q
echo "✅ DaOnRoad 백엔드: http://127.0.0.1:8000"
python main.py
