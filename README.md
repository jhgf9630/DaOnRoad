# 🚌 DaOnRoad — 버스 노선 최적화 시스템

여행사 버스 배차 자동화 프로그램  
승객 탑승지 정보를 입력하면 최적 버스 노선을 자동으로 생성합니다.

---

## 📐 시스템 구조

```
사용자
  │
  ▼
Electron 앱 (.exe)          ← UI (지도, 결과 표시)
  │
  │  docker compose up
  ▼
┌─────────────────────────────────────────┐
│  Docker                                  │
│                                          │
│  ┌──────────────────┐                   │
│  │  FastAPI 백엔드   │ :8000             │
│  │  (Python)        │                   │
│  │  - 노선 최적화   │                   │
│  │  - Kakao 검색    │                   │
│  │  - Excel 출력    │                   │
│  └────────┬─────────┘                   │
│           │ HTTP                         │
│  ┌────────▼─────────┐                   │
│  │  OSRM 서버       │ :5001             │
│  │  (도로 경로 계산) │                   │
│  └──────────────────┘                   │
└─────────────────────────────────────────┘
```

**배포 구조 핵심:**
- **Electron** = UI 레이어 (지도, 버튼, 결과 표시)
- **Docker Compose** = 서버 레이어 (백엔드 + OSRM 통합 실행)
- 사용자는 **Docker Desktop** + **Electron 설치파일(.exe)** 만 있으면 됨

---

## 📑 목차

| 대상 | 섹션 |
|------|------|
| 관리자 (개발자) | [환경 구성](#관리자--환경-구성) → [OSRM 구축](#관리자--osrm-도로-데이터-구축) → [배포](#관리자--배포) |
| 사용자 | [사전 준비](#사용자--사전-준비) → [앱 사용법](#사용자--앱-사용법) |

---

# 👨‍💻 관리자 — 환경 구성

> 개발 및 배포 담당자가 최초 1회 수행합니다.

## 사전 준비물

| 도구 | 버전 | 다운로드 |
|------|------|---------|
| Docker Desktop | 최신 | [docker.com](https://www.docker.com/get-started) |
| Node.js | 18 이상 | [nodejs.org](https://nodejs.org/) |
| Git | 최신 | [git-scm.com](https://git-scm.com/) |

> Python은 **불필요**합니다. Docker 컨테이너 안에서 실행됩니다.

---

## 저장소 클론

```bash
git clone https://github.com/jhgf9630/DaOnRoad.git
cd DaOnRoad
```

---

## API 키 설정 (최초 1회)

### Kakao API 키 발급

1. [developers.kakao.com](https://developers.kakao.com) → 로그인
2. **내 애플리케이션 → 애플리케이션 추가**
3. **앱 키 탭 → REST API 키** 복사
4. ⚠️ **제품 설정 → 카카오맵 → 사용 설정 ON** (필수!)

### .env 파일 생성

```bash
# backend/.env.example 을 복사
cp backend/.env.example backend/.env
```

`backend/.env` 파일을 열어 편집:

```
KAKAO_API_KEY=여기에_REST_API_키_붙여넣기
```

> `OSRM_BASE_URL`은 **설정하지 않아도 됩니다.**  
> Docker Compose가 자동으로 `http://osrm:5000`으로 연결합니다.

---

## Node.js 패키지 설치

```bash
cd frontend
npm install
cd ..
```

---

# 👨‍💻 관리자 — OSRM 도로 데이터 구축

> 최초 1회 구축 후 재구축은 연 1~2회 정도면 충분합니다.

## OSRM이란?

실제 도로망 기반으로 경로와 이동시간을 계산하는 오픈소스 엔진입니다.  
설정하지 않으면 직선 경로로 표시됩니다.

## 데이터 다운로드

프로젝트 루트에서:

```bash
mkdir osrm-data
cd osrm-data
```

한국 지도 데이터 다운로드 (약 900MB):

```bash
# Windows
curl -O https://download.geofabrik.de/asia/south-korea-latest.osm.pbf

# Mac/Linux
wget https://download.geofabrik.de/asia/south-korea-latest.osm.pbf
```

## 전처리 (3단계, 총 15~30분)

`osrm-data` 폴더 안에서 실행:

```bash
# Windows
docker run -t -v "%cd%:/data" osrm/osrm-backend:latest osrm-extract -p /opt/car.lua /data/south-korea-latest.osm.pbf
docker run -t -v "%cd%:/data" osrm/osrm-backend:latest osrm-partition /data/south-korea-latest.osrm
docker run -t -v "%cd%:/data" osrm/osrm-backend:latest osrm-customize /data/south-korea-latest.osrm

# Mac/Linux
docker run -t -v "$(pwd):/data" osrm/osrm-backend:latest osrm-extract -p /opt/car.lua /data/south-korea-latest.osm.pbf
docker run -t -v "$(pwd):/data" osrm/osrm-backend:latest osrm-partition /data/south-korea-latest.osrm
docker run -t -v "$(pwd):/data" osrm/osrm-backend:latest osrm-customize /data/south-korea-latest.osrm
```

완료 후 `osrm-data/` 폴더에 `.osrm` 관련 파일들이 생성됩니다.

---

# 👨‍💻 관리자 — 개발 환경 실행

## 방법 A — 스크립트로 한 번에 실행

```bash
# Windows
start.bat

# Mac/Linux
./start.sh
```

스크립트가 자동으로:
1. Docker 실행 여부 확인
2. `backend/.env` 파일 존재 확인
3. `docker compose up -d --build` 실행
4. 백엔드 준비 완료 대기

## 방법 B — 수동 실행

```bash
# 백엔드 + OSRM 실행
docker compose up -d --build

# 상태 확인
docker compose ps

# 로그 확인
docker compose logs -f backend

# Electron UI 실행 (별도 터미널)
cd frontend
npm start
```

## 동작 확인

```bash
# 백엔드 헬스체크
curl http://127.0.0.1:8000/health

# OSRM 연결 확인
curl "http://127.0.0.1:5001/table/v1/driving/126.978,37.566;127.027,37.498"

# API 문서
브라우저: http://127.0.0.1:8000/docs
```

---

# 👨‍💻 관리자 — 배포

## 배포 대상 사용자가 준비할 것

| 항목 | 방법 |
|------|------|
| Docker Desktop | [docker.com](https://www.docker.com/get-started) 에서 설치 |
| DaOnRoad 설치파일 | 관리자가 제공하는 `.exe` 파일 실행 |

> **사용자는 Python, Node.js 등을 따로 설치할 필요가 없습니다.**

---

## Electron 설치 파일 빌드

```bash
cd frontend
npm run build:win    # Windows .exe 생성
npm run build:mac    # Mac .dmg 생성
```

빌드 완료 후:
```
frontend/dist/
└── DaOnRoad Setup 1.0.0.exe    ← 사용자에게 배포할 파일
```

빌드 시 `docker-compose.yml`과 `backend/` 폴더가 **자동으로 패키지에 포함**됩니다  
(`package.json`의 `extraResources` 설정).

---

## 사용자에게 전달할 것

```
1. DaOnRoad Setup 1.0.0.exe    (Electron 설치 파일)
2. osrm-data/ 폴더             (별도 전달 또는 공유 드라이브)
3. backend/.env                (API 키 포함, 보안 채널로 전달)
```

> `osrm-data/`는 용량이 크므로 USB 또는 내부 파일 서버로 전달하세요.  
> `.env` 파일은 이메일이 아닌 보안 채널(메신저 DM, 내부 시스템 등)로 전달하세요.

---

## 사용자 설치 가이드 (배포 시 함께 전달)

```
1. Docker Desktop 설치 및 실행
   https://www.docker.com/get-started

2. DaOnRoad Setup 1.0.0.exe 실행 → 설치

3. 관리자로부터 받은 파일 배치:
   - osrm-data/ 폴더 → C:\Users\사용자\DaOnRoad\osrm-data\
   - .env 파일     → C:\Users\사용자\DaOnRoad\backend\.env

4. DaOnRoad 앱 실행
   (첫 실행 시 Docker 이미지 빌드로 수 분 소요)
```

---

## Docker 이미지 관리 명령어

```bash
# 컨테이너 상태 확인
docker compose ps

# 컨테이너 재시작
docker compose restart backend

# 전체 재빌드 (코드 변경 후)
docker compose up -d --build

# 컨테이너 중지 (데이터 유지)
docker compose stop

# 컨테이너 완전 삭제
docker compose down

# 로그 실시간 확인
docker compose logs -f

# 백엔드 로그만 확인
docker compose logs -f backend
```

---

# 👤 사용자 — 사전 준비

## 최초 설치 (1회)

### 1. Docker Desktop 설치

[docker.com](https://www.docker.com/get-started) 에서 다운로드 후 설치.  
설치 후 실행 → 트레이 아이콘이 **초록색**이 될 때까지 대기.

### 2. DaOnRoad 앱 설치

관리자로부터 받은 `DaOnRoad Setup x.x.x.exe` 실행 → 설치.

### 3. 파일 배치

관리자로부터 받은 파일을 아래 위치에 배치:

```
DaOnRoad 설치 폴더/
├── osrm-data/              ← 관리자에게 받은 폴더
│   └── south-korea-latest.osrm  (및 기타 파일들)
└── backend/
    └── .env                ← 관리자에게 받은 파일
```

---

## 매일 실행

1. **Docker Desktop** 실행 → 초록색 아이콘 확인
2. **DaOnRoad** 앱 실행
3. 앱 헤더에 **✅ 연결됨** 표시 확인 (30초~1분 소요)

> 첫 실행 시 Docker 이미지를 빌드하므로 수 분 소요됩니다.  
> 이후 실행부터는 30초 내외로 빠르게 시작됩니다.

---

# 👤 사용자 — 앱 사용법

## STEP 1 — 승객 데이터 업로드

### Excel 파일 형식

| name (이름) | address (주소) | passenger_count (인원) |
|------------|--------------|----------------------|
| 홍길동 | 서울 강남구 역삼동 | 1 |
| 김철수 | 인천 연수구 송도동 | 2 |

- 한글 컬럼명도 자동 인식 (이름/주소/인원)
- `.xlsx`, `.xls` 모두 지원

### 업로드

1. **Step 1** 영역 클릭 또는 파일 드래그
2. 승객 목록 확인 — **좌표 ✗** 항목은 주소를 수정하세요

---

## STEP 2 — 차량 설정

1. 버스 ID, 정원 입력
2. 출발지 입력 후 **✅ 확인** 클릭 → 검색 결과에서 위치 선택
3. 지도에서 위치 확인
4. **+ 차량 추가** 클릭

**수정**: 등록된 차량 우측 ✏️ → 출발지/정원 수정 → **저장**

---

## STEP 3 — 노선 생성

1. **도착지** 입력 → **✅ 확인** → 위치 선택
2. **도착 목표시간** 설정 (예: 10:00)
3. **🚀 최적 노선 생성** 클릭

### 결과

| 항목 | 위치 |
|------|------|
| 요약 (버스 수, 출발시간) | 사이드바 결과 요약 |
| 노선 상세 (탑승자/시간) | 사이드바 노선 상세 |
| 지도 시각화 | 메인 화면 |
| 버스별 필터 | 지도 하단 탭 |

- **실선**: 실제 도로 경로
- **파선**: 직선 경로 (OSRM 미설정 시)

---

## STEP 4 — Excel 저장

1. **📥 Excel 저장** 클릭 → 저장 위치 선택

| 시트 | 내용 |
|------|------|
| Bus Summary | 버스별 출발/도착시간, 소요시간, 탑승인원 |
| Route Detail | 정류장 순서, 탑승지, 탑승시간 |
| Passenger | 승객별 배정 버스, 탑승지, 탑승시간 |

---

# 🔧 문제 해결

## "백엔드 연결 실패"

**Docker Desktop이 실행 중인지 확인:**
```bash
docker ps
```

**컨테이너 상태 확인:**
```bash
docker compose ps
docker compose logs backend
```

**수동으로 재시작:**
```bash
docker compose up -d
```

---

## 주소 검색 결과 없음

1. `backend/.env`에 `KAKAO_API_KEY` 설정 확인
2. Kakao Developers → **카카오맵 사용 설정 ON** 확인
3. **REST API 키** 인지 확인 (JavaScript 키 ❌)

진단:
```
http://127.0.0.1:8000/api/debug-key
```

---

## 노선이 직선으로 표시됨

OSRM 서버가 실행 중인지 확인:
```bash
docker compose ps
```
`daonroad-osrm` 컨테이너가 `Up` 상태인지 확인.

```
http://127.0.0.1:8000/api/osrm-status
```

---

## 캐시 초기화

```bash
docker compose exec backend rm -rf /app/cache/*
# 또는
curl -X DELETE http://127.0.0.1:8000/api/cache
```

---

## Docker 컨테이너 완전 재설치

```bash
docker compose down --volumes
docker compose up -d --build
```
