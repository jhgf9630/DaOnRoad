@echo off

echo DaOnRoad Build Script

if not exist "frontend\package.json" (
  echo ERROR: Run from DaOnRoad root folder
  pause
  exit /b 1
)

if not exist "frontend\assets" mkdir "frontend\assets"

set CSC_IDENTITY_AUTO_DISCOVERY=false
set CSC_LINK=
set WIN_CSC_LINK=

cd frontend

echo Step 1: npm install
call npm install
if %errorlevel% neq 0 (
  echo ERROR: npm install failed
  cd ..
  pause
  exit /b 1
)

echo Step 2: Building...
call npm run buildwin
if %errorlevel% neq 0 (
  echo ERROR: Build failed
  cd ..
  pause
  exit /b 1
)

cd ..

echo Done! Check dist folder.
dir /b dist\*.exe 2>nul
pause