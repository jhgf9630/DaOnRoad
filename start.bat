@echo off
chcp 65001 > nul 2>&1

echo.
echo  DaOnRoad - Bus Route Optimizer
echo  ================================
echo.

:: Docker 실행 확인
docker info > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker Desktop is not running.
    echo.
    echo  Please:
    echo  1. Start Docker Desktop
    echo  2. Wait until the tray icon turns green
    echo  3. Run this file again
    echo.
    pause
    exit /b 1
)

:: .env 파일 확인
if not exist "backend\.env" (
    echo [ERROR] backend\.env file not found.
    echo.
    echo  Please copy backend\.env.example to backend\.env
    echo  and fill in your API keys.
    echo.
    pause
    exit /b 1
)

:: docker compose 명령어 자동 감지 (신버전: "docker compose", 구버전: "docker-compose")
docker compose version > nul 2>&1
if %errorlevel% equ 0 (
    set COMPOSE_CMD=docker compose
) else (
    docker-compose version > nul 2>&1
    if %errorlevel% equ 0 (
        set COMPOSE_CMD=docker-compose
    ) else (
        echo [ERROR] docker compose command not found.
        echo  Please update Docker Desktop to the latest version.
        pause
        exit /b 1
    )
)

echo [1/3] Starting containers (first run may take a few minutes)...
echo.
%COMPOSE_CMD% up -d --build

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] docker compose failed.
    echo  Run manually to see details:
    echo    %COMPOSE_CMD% up --build
    pause
    exit /b 1
)

echo.
echo [2/3] Waiting for backend to be ready...
:wait_loop
timeout /t 2 /nobreak > nul
curl -s http://127.0.0.1:8000/health > nul 2>&1
if %errorlevel% neq 0 goto wait_loop

echo.
echo [3/3] Backend is ready!
echo.
echo  ================================
echo  DaOnRoad is running
echo  Backend : http://127.0.0.1:8000
echo  API Docs: http://127.0.0.1:8000/docs
echo  ================================
echo.
echo  To start the UI:
echo    cd frontend
echo    npm start
echo.
echo  To stop: docker compose stop
echo  To view logs: docker compose logs -f
echo.
pause
