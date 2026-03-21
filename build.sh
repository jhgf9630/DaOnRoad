#!/bin/bash
set -e

echo ""
echo "DaOnRoad - Build Script"
echo "========================"
echo ""

# 루트 위치 확인
if [ ! -f "frontend/package.json" ]; then
    echo "[ERROR] Run from DaOnRoad root folder."
    exit 1
fi

# .env 경고
if [ -f "backend/.env" ]; then
    echo "[WARN] backend/.env exists - NOT included in package."
    echo "       Users must create their own .env file."
    echo ""
fi

echo "[1/3] Installing dependencies..."
cd frontend
npm install

echo ""
echo "[2/3] Building Electron package..."
npm run build:mac   # Mac용. Windows는 npm run build:win

cd ..

echo ""
echo "[3/3] Build complete!"
echo ""
echo "Output: dist/"
ls dist/*.dmg 2>/dev/null || ls dist/*.exe 2>/dev/null || echo "(check dist/ folder)"
echo ""
echo "Deliver to users:"
echo "  1. dist/DaOnRoad*.dmg or .exe"
echo "  2. osrm-data/ folder"
echo "  3. backend/.env (secure channel)"
