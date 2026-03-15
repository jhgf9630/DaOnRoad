# 🚌 DaOnRoad

버스 노선 최적화 시스템 — 여행사 버스 배차 자동화

---

## ⚡ 빠른 시작

### 1. 백엔드 (Python)

```bash
cd backend

# 가상환경 생성 (권장, 최초 1회)
python -m venv venv

# 가상환경 활성화
source venv/bin/activate        # Mac / Linux
venv\Scripts\activate           # Windows

# 패키지 설치 (최초 1회)
pip install -r requirements.txt

# 백엔드 실행
python main.py
# → http://127.0.0.1:8000
```

### 2. 프론트엔드 (Electron)

```bash
cd frontend
npm install    # 최초 1회
npm start
```

> ✅ Electron 앱이 시작되면 **백엔드를 자동으로 실행**합니다.
> 단, Python 가상환경이 `backend/venv`에 설치되어 있어야 합니다.

---

## 🖼 아이콘 적용 방법

`DaOnRoad.ico` 파일을 아래 위치에 복사하세요:

```
frontend/
└── assets/
    └── DaOnRoad.ico   ← 여기에 넣기
```

---

## 🔑 API 키 설정 (선택)

`backend/.env` 파일 생성:

```
KAKAO_API_KEY=your_kakao_rest_api_key
TMAP_API_KEY=your_tmap_app_key
```

API 키 없이도 동작합니다 (한국 주요 지역 Fallback 내장).

---

## 📊 Excel 입력 형식

| name | address | passenger_count |
|------|---------|----------------|
| 홍길동 | 서울 강남구 역삼동 | 1 |
| 김철수 | 인천 연수구 | 2 |

---

## 🛠 기술 스택

| 분류 | 기술 |
|------|------|
| Backend | Python, FastAPI, OR-Tools |
| Frontend | Electron, Leaflet.js |
| 지도 | OpenStreetMap |
| Excel | openpyxl |
