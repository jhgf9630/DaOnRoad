@echo off
chcp 65001 > nul 2>&1

echo.
echo  DaOnRoad - Build Script
echo  ========================
echo.

:: Node.js check
node --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found. Install from https://nodejs.org/
    pause
    exit /b 1
)

:: Must run from project root
if not exist "frontend\package.json" (
    echo [ERROR] Run this script from the DaOnRoad root folder.
    pause
    exit /b 1
)

:: .env check
if not exist "backend\.env" (
    echo [ERROR] backend\.env not found.
    echo  Create backend\.env and add KAKAO_API_KEY before building.
    pause
    exit /b 1
)

:: osrm-data check
if not exist "osrm-data\south-korea-latest.osrm" (
    echo [ERROR] osrm-data\south-korea-latest.osrm not found.
    echo  Run OSRM preprocessing first. See README.md STEP 6.
    pause
    exit /b 1
)

if not exist "frontend\assets" mkdir "frontend\assets"

set CSC_IDENTITY_AUTO_DISCOVERY=false
set CSC_LINK=
set WIN_CSC_LINK=

echo [1/4] Installing frontend dependencies...
cd frontend
call npm install
if %errorlevel% neq 0 (
    echo [ERROR] npm install failed.
    cd ..
    pause
    exit /b 1
)

echo.
echo [2/4] Building Electron package...
call npm run buildwin
if %errorlevel% neq 0 (
    echo [ERROR] Build failed.
    echo  Try running this script as Administrator (right-click - Run as administrator)
    cd ..
    pause
    exit /b 1
)
cd ..

echo.
echo [3/4] Adding osrm-data and .env to package...

:: osrm-data 복사
if exist "dist\win-unpacked\resources\osrm-data" rmdir /s /q "dist\win-unpacked\resources\osrm-data"
xcopy /e /i /q "osrm-data" "dist\win-unpacked\resources\osrm-data"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to copy osrm-data.
    pause
    exit /b 1
)

:: .env 복사
copy /y "backend\.env" "dist\win-unpacked\resources\backend\.env" > nul
if %errorlevel% neq 0 (
    echo [ERROR] Failed to copy .env.
    pause
    exit /b 1
)

echo.
echo [4/4] Creating DaOnRoad.zip...
if exist "dist\DaOnRoad.zip" del "dist\DaOnRoad.zip"

:: PowerShell로 ZIP 생성
powershell -NoProfile -Command "Compress-Archive -Path 'dist\win-unpacked\*' -DestinationPath 'dist\DaOnRoad.zip' -Force"
if %errorlevel% neq 0 (
    echo [WARN] ZIP creation failed - distribute win-unpacked\ folder directly.
) else (
    echo.
    echo  ZIP created: dist\DaOnRoad.zip
)

echo.
echo  ================================
echo  Build complete!
echo  ================================
echo.
echo  Distribute to users:
echo    dist\DaOnRoad.zip
echo.
echo  Users just need to:
echo    1. Install Docker Desktop
echo    2. Unzip DaOnRoad.zip
echo    3. Run DaOnRoad.exe
echo.
pause
