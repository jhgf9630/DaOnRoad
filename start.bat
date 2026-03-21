@echo off
chcp 65001 >nul
echo.
echo  ██████╗  █████╗  ██████╗ ███╗  ██╗██████╗  ██████╗  █████╗ ██████╗
echo  ██╔══██╗██╔══██╗██╔═══██╗████╗ ██║██╔══██╗██╔═══██╗██╔══██╗██╔══██╗
echo  ██║  ██║███████║██║   ██║██╔██╗██║██████╔╝██║   ██║███████║██║  ██║
echo  ██║  ██║██╔══██║██║   ██║██║╚████║██╔══██╗██║   ██║██╔══██║██║  ██║
echo  ██████╔╝██║  ██║╚██████╔╝██║ ╚███║██║  ██║╚██████╔╝██║  ██║██████╔╝
echo  ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚══╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═════╝
echo.
echo  버스 노선 최적화 시스템
echo ================================================================

:: Docker 설치 확인
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [오류] Docker Desktop이 실행되지 않았습니다.
    echo.
    echo  1. Docker Desktop을 실행하세요.
    echo  2. 트레이 아이콘이 초록색이 될 때까지 기다리세요.
    echo  3. 이 파일을 다시 실행하세요.
    echo.
    pause
    exit /b 1
)

:: .env 파일 확인
if not exist "backend\.env" (
    echo.
    echo [경고] backend\.env 파일이 없습니다.
    echo.
    echo  backend\.env.example 을 복사해서
    echo  backend\.env 로 만들고 API 키를 입력하세요.
    echo.
    pause
    exit /b 1
)

echo.
echo [1/3] Docker 컨테이너 빌드 및 시작 중...
echo       (최초 실행 시 수 분 소요될 수 있습니다)
echo.
docker compose up -d --build

if %errorlevel% neq 0 (
    echo.
    echo [오류] Docker Compose 실행 실패
    echo  docker compose up --build 를 직접 실행해서 오류를 확인하세요.
    pause
    exit /b 1
)

echo.
echo [2/3] 백엔드 준비 대기 중...
:wait_loop
timeout /t 2 /nobreak >nul
curl -s http://127.0.0.1:8000/health >nul 2>&1
if %errorlevel% neq 0 goto wait_loop

echo.
echo [3/3] 백엔드 준비 완료!
echo.
echo ================================================================
echo  DaOnRoad 실행 중
echo  백엔드:  http://127.0.0.1:8000
echo  API 문서: http://127.0.0.1:8000/docs
echo ================================================================
echo.
echo  Electron 앱을 실행하려면:
echo    cd frontend
echo    npm start
echo.
echo  종료하려면 이 창을 닫거나 Ctrl+C 를 누르세요.
echo  (컨테이너는 유지됩니다. 완전 종료: docker compose down)
echo.
pause
