@echo off
echo [DaOnRoad] 백엔드 시작...
cd backend
if not exist venv (
    echo 가상환경 생성 중...
    python -m venv venv
)
call venv\Scripts\activate
pip install -r requirements.txt -q
echo.
echo [DaOnRoad] 백엔드: http://127.0.0.1:8000
python main.py
pause
