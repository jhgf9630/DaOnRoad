# 🚌 DaOnRoad — 버스 노선 최적화 시스템

여행사 버스 배차 자동화 프로그램

---

## ⚡ 처음 설치하기 (최초 1회)

### Step 1 — Python 패키지 설치

```bash
cd backend
python -m venv venv
```

**Windows:**
```bash
venv\Scripts\activate
pip install -r requirements.txt
```

**Mac / Linux:**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

> ✅ 설치가 끝나면 `backend/venv/` 폴더가 생깁니다.

---

### Step 2 — Kakao API 키 설정

주소 검색 기능에 Kakao REST API 키가 **필수**입니다.

**1. 키 발급**
- [developers.kakao.com](https://developers.kakao.com) 접속 → 로그인
- **내 애플리케이션** → **애플리케이션 추가하기**
- 앱 이름 입력 후 생성
- **앱 키** 탭 → **REST API 키** 복사

**2. Kakao 맵 API 활성화** ← ⚠️ 이 단계를 빠뜨리면 검색이 동작하지 않습니다

- [developers.kakao.com](https://developers.kakao.com) → 내 애플리케이션 → 앱 선택
- 왼쪽 메뉴 **앱 설정 → 카카오 로그인** → 활성화 (선택사항)
- 왼쪽 메뉴 **제품 설정 → 카카오맵** → **사용 설정 ON**

> ✅ 카카오맵 사용 설정을 ON으로 해야 주소/장소 검색 API가 활성화됩니다.

**3. .env 파일 생성**

`backend/` 폴더 안에 `.env` 파일을 새로 만들고 아래 내용을 입력:

```
KAKAO_API_KEY=여기에_REST_API_키_붙여넣기
```

> ⚠️ `.env` 파일은 `backend/` 폴더 안에 있어야 합니다.
> `.env.example` 파일을 복사해서 이름을 `.env`로 바꿔도 됩니다.

**3. 설정 확인**

백엔드 실행 시 터미널에 아래처럼 나오면 성공:
```
[main] KAKAO_API_KEY: ✅ 설정됨 (abcdef12...)
```

---

### Step 3 — Node.js 패키지 설치

```bash
cd frontend
npm install
```

> ✅ 설치가 끝나면 `frontend/node_modules/` 폴더가 생깁니다.

---

## 🚀 매일 실행하기

### 방법 A — Electron 앱 실행 (백엔드 자동 시작)

> ⚠️ 반드시 **venv 설치가 완료된 상태**여야 자동 시작됩니다.

```bash
cd frontend
npm start
```

앱이 열리고 몇 초 후 헤더에 **✅ 연결됨** 이 뜨면 정상입니다.

---

### 방법 B — 수동 실행 (백엔드 자동 시작이 안 될 때)

터미널 2개를 열어서 각각 실행합니다.

**터미널 1 — 백엔드:**
```bash
cd backend

# Windows
venv\Scripts\activate
python main.py

# Mac / Linux
source venv/bin/activate
python main.py
```

백엔드가 뜨면 터미널에 아래가 보입니다:
```
[main] KAKAO_API_KEY: ✅ 설정됨 (abcdef12...)
INFO:     Uvicorn running on http://127.0.0.1:8000
```

**터미널 2 — Electron:**
```bash
cd frontend
npm start
```

---

## ❓ 문제 해결

### "백엔드 연결 실패" 배너가 뜸

→ 백엔드를 **방법 B**로 수동 실행하세요.

---

### 주소 검색 결과가 안 나옴

백엔드가 실행 중인 상태에서 브라우저로 아래 주소를 열어 확인하세요:

```
http://127.0.0.1:8000/api/debug-key
```

결과 예시:

| 결과 | 의미 | 해결 |
|------|------|------|
| `kakao_key_set: true` + `kakao_test_ok: true` | ✅ 정상 | — |
| `kakao_key_set: false` | .env 파일 미설정 | Step 2 참고 |
| `kakao_test_ok: false` + `kakao_test_error: "..." ` | 키 오류 | REST API 키인지 확인 |

> ⚠️ Kakao 앱 키 종류 주의: **REST API 키**를 사용해야 합니다 (JavaScript 키 ❌)

---

### 캐시 초기화

이전 검색 결과가 잘못 캐시된 경우:
```bash
# 백엔드 실행 중에 아래 실행
curl -X DELETE http://127.0.0.1:8000/api/cache
```

또는 `backend/cache/` 폴더를 통째로 삭제하세요.

---

## 📁 프로젝트 구조

```
DaOnRoad/
├── backend/                   Python FastAPI 백엔드
│   ├── .env                   ← API 키 설정 (직접 만들어야 함)
│   ├── .env.example           ← .env 양식 예시
│   ├── main.py                진입점
│   ├── requirements.txt       Python 패키지 목록
│   ├── venv/                  ← 가상환경 (pip install 후 생성됨)
│   ├── api/                   FastAPI 라우터
│   ├── routing/               거리 계산, 지오코딩
│   ├── solver/                VRP 최적화 (OR-Tools)
│   ├── scheduler/             탑승시간 역산
│   └── export/                Excel 출력
│
└── frontend/                  Electron 프론트엔드
    ├── index.html             메인 UI
    ├── package.json
    ├── node_modules/          ← npm install 후 생성됨
    └── src/
        └── main.js            Electron 메인 프로세스
```

---

## 📊 Excel 입력 형식

| name | address | passenger_count |
|------|---------|----------------|
| 홍길동 | 서울 강남구 역삼동 | 1 |
| 김철수 | 인천 연수구 송도동 | 2 |

`backend/create_sample_excel.py` 를 실행하면 샘플 파일이 생성됩니다:
```bash
cd backend
python create_sample_excel.py
```

---

## 🛠 기술 스택

| 분류 | 기술 |
|------|------|
| Backend | Python, FastAPI, OR-Tools |
| 주소 검색 | Kakao Local API (검색에만 사용) |
| 이동시간 계산 | Haversine 공식 (도로 우회계수 적용) |
| Frontend | Electron, Leaflet.js, MarkerCluster |
| 지도 | OpenStreetMap |
| Excel | openpyxl |

> Kakao API는 **주소/장소 검색에만** 사용합니다.
> 경로 계산, 이동시간 등은 API를 사용하지 않아 사용량 걱정 없습니다.
