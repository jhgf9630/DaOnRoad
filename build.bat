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
    echo  Current folder: %cd%
    pause
    exit /b 1
)

:: .env 파일 확인 (배포본에 포함되면 안 됨)
if exist "backend\.env" (
    echo [WARN] backend\.env exists - it will NOT be included in the package.
    echo        Users must create their own .env file.
    echo.
)

:: assets 폴더 확인
if not exist "frontend\assets\DaOnRoad.ico" (
    echo [WARN] frontend\assets\DaOnRoad.ico not found.
    echo        Build will continue without icon.
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
    echo [ERROR] Build failed.
    cd ..
    pause
    exit /b 1
)

cd ..

echo.
echo [3/3] Build complete!
echo.
echo  ========================
echo  Output: dist\
echo  ========================
echo.
dir dist\*.exe 2>nul || echo  (no .exe found - check dist\ folder)
echo.
echo  Deliver to users:
echo    1. dist\DaOnRoad Setup 1.0.0.exe
echo    2. osrm-data\ folder  (via USB or file server)
echo    3. backend\.env        (via secure channel)
echo.
pause
