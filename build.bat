@echo off
chcp 65001 > nul 2>&1

echo.
echo  DaOnRoad - Build Script
echo  ========================
echo.

:: Node.js 확인
node --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found. Install from https://nodejs.org/
    pause
    exit /b 1
)

:: 루트 위치 확인
if not exist "frontend\package.json" (
    echo [ERROR] Run this script from the DaOnRoad root folder.
    echo  Current: %cd%
    pause
    exit /b 1
)

:: assets 폴더 및 아이콘 확인
if not exist "frontend\assets" mkdir "frontend\assets"
if not exist "frontend\assets\DaOnRoad.ico" (
    echo [WARN] frontend\assets\DaOnRoad.ico not found - building without icon.
    echo.
)

echo [1/3] Installing frontend dependencies...
cd frontend
call npm install
if %errorlevel% neq 0 (
    echo [ERROR] npm install failed.
    cd ..
    pause
    exit /b 1
)

echo.
echo [2/3] Building Electron package...
call npm run build:win
if %errorlevel% neq 0 (
    echo [ERROR] Build failed. See log above.
    cd ..
    pause
    exit /b 1
)

cd ..

echo.
echo [3/3] Build complete!
echo.
echo  Output: dist\
echo.
dir /b dist\*.exe 2>nul
echo.
echo  Ship to users:
echo    1. dist\DaOnRoad Setup 1.0.0.exe
echo    2. osrm-data\ folder  (USB or file server)
echo    3. backend\.env        (secure channel only)
echo.
pause
