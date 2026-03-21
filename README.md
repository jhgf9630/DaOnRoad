# 🚌 DaOnRoad — 버스 노선 최적화 시스템

승객 탑승지 정보를 입력하면 최적 버스 노선을 자동으로 생성합니다.

---

## 목차

- [👤 사용자 가이드](#-사용자-가이드)
- [👨‍💻 관리자 가이드](#-관리자-가이드)

---

# 👤 사용자 가이드

## 사전 준비 (최초 1회)

### 1. Docker Desktop 설치

[docker.com/get-started](https://www.docker.com/get-started) 에서 설치.  
설치 후 실행 → 트레이 아이콘이 **초록색**이 될 때까지 대기.

### 2. DaOnRoad.zip 압축 해제

관리자로부터 받은 `DaOnRoad.zip`을 원하는 폴더에 압축 해제합니다.

```
DaOnRoad\               ← 압축 해제된 폴더
├── DaOnRoad.exe        ← 실행 파일
├── resources\
│   ├── backend\        ← 백엔드 서버
│   ├── osrm-data\      ← 도로 지도 데이터
│   └── docker-compose.yml
└── ...
```

---

## 매일 실행

1. **Docker Desktop** 실행 → 트레이 아이콘 초록색 확인
2. **DaOnRoad.exe** 더블클릭
3. 앱 헤더에 **✅ 연결됨** 표시 확인 (첫 실행 시 1~2분 소요)

> 첫 실행은 Docker 이미지를 빌드하므로 수 분 소요됩니다.  
> 이후 실행부터는 30초 내외로 빠르게 시작됩니다.

---

## 앱 사용법

### STEP 1 — 승객 데이터 업로드

Excel 파일 형식:

| name | address | passenger_count |
|------|---------|----------------|
| 홍길동 | 서울 강남구 역삼동 | 1 |
| 김철수 | 인천 연수구 송도동 | 2 |

- 한글 컬럼명도 자동 인식 (이름/주소/인원)
- `.xlsx`, `.xls` 모두 지원

사이드바 **Step 1** 영역에 파일을 드래그하거나 클릭해서 업로드합니다.

---

### STEP 2 — 차량 설정

1. 버스 ID, 정원 입력
2. 출발지 입력 후 **✅ 확인** 클릭 → 검색 결과에서 정확한 위치 선택
3. 지도에서 위치 확인
4. **+ 차량 추가** 클릭

수정: 등록된 차량 우측 ✏️ → 출발지/정원 수정 → **저장**

---

### STEP 3 — 노선 생성

1. 도착지 입력 → **✅ 확인** → 위치 선택
2. 도착 목표시간 설정 (예: 10:00)
3. **🚀 최적 노선 생성** 클릭

결과 확인:

| 항목 | 위치 |
|------|------|
| 버스 수, 출발시간 요약 | 사이드바 결과 요약 |
| 버스별 탑승자/탑승시간 | 사이드바 노선 상세 |
| 지도 시각화 | 메인 화면 |
| 버스별 필터 | 지도 하단 탭 |

---

### STEP 4 — Excel 저장

**📥 Excel 저장** 클릭 → 저장 위치 선택

| 시트 | 내용 |
|------|------|
| Bus Summary | 버스별 출발/도착시간, 소요시간, 탑승인원 |
| Route Detail | 정류장 순서, 탑승지, 탑승시간 |
| Passenger | 승객별 배정 버스, 탑승지, 탑승시간 |

---

## 문제 해결

### "백엔드 연결 실패" 표시

→ Docker Desktop이 실행 중인지 확인 (트레이 아이콘 초록색)  
→ 앱 헤더의 **재연결** 버튼 클릭

### 주소 검색 결과 없음

→ 관리자에게 문의 (API 키 설정 문제)

### 노선이 직선으로 표시

→ 정상 동작입니다. 실제 도로 경로는 설정에 따라 다를 수 있습니다.

---

---

# 👨‍💻 관리자 가이드

## 시스템 구조

```
사용자
  │
  ▼
DaOnRoad.exe (Electron UI)
  │
  │  docker compose up
  ▼
┌──────────────────────────────┐
│  Docker                       │
│  ┌─────────────────┐         │
│  │ FastAPI 백엔드   │ :8000   │
│  │ - 노선 최적화    │         │
│  │ - Kakao 주소검색 │         │
│  │ - Excel 출력     │         │
│  └────────┬────────┘         │
│           │                   │
│  ┌────────▼────────┐         │
│  │ OSRM 서버        │ :5001   │
│  │ (실제 도로 경로)  │         │
│  └─────────────────┘         │
└──────────────────────────────┘
```

---

## 개발 환경 구성 (최초 1회)

### 사전 준비물

| 도구 | 설치 |
|------|------|
| Docker Desktop | [docker.com](https://www.docker.com/get-started) |
| Node.js 18+ | [nodejs.org](https://nodejs.org/) |
| Git | [git-scm.com](https://git-scm.com/) |

> Python은 불필요합니다. Docker 컨테이너 안에서 실행됩니다.

### 저장소 클론

```cmd
git clone https://github.com/jhgf9630/DaOnRoad.git
cd DaOnRoad
```

### Kakao API 키 발급

1. [developers.kakao.com](https://developers.kakao.com) → 로그인 → 애플리케이션 추가
2. **앱 키 → REST API 키** 복사
3. ⚠️ **제품 설정 → 카카오맵 → 사용 설정 ON** (필수)

### .env 파일 생성

```
backend\.env 내용:

KAKAO_API_KEY=발급받은_REST_API_키
```

### Node.js 패키지 설치

```cmd
cd frontend
npm install
cd ..
```

### OSRM 도로 데이터 구축 (최초 1회, 약 30분)

```cmd
mkdir osrm-data
cd osrm-data
curl -O https://download.geofabrik.de/asia/south-korea-latest.osm.pbf
```

전처리 (osrm-data 폴더 안에서 실행):

```cmd
docker run -t -v "%cd%:/data" osrm/osrm-backend:latest osrm-extract -p /opt/car.lua /data/south-korea-latest.osm.pbf
docker run -t -v "%cd%:/data" osrm/osrm-backend:latest osrm-partition /data/south-korea-latest.osrm
docker run -t -v "%cd%:/data" osrm/osrm-backend:latest osrm-customize /data/south-korea-latest.osrm
cd ..
```

---

## 개발 환경 실행

```cmd
rem Docker 백엔드 시작
start.bat

rem Electron UI 실행 (별도 터미널)
cd frontend
npm start
```

코드 수정 후 반영:
```cmd
rem backend 코드 변경 시
docker compose up -d --build

rem frontend 코드 변경 시
npm start 재실행
```

---

## 배포 (사용자에게 전달)

### build.bat 실행

```cmd
cd DaOnRoad
build.bat
```

빌드 스크립트가 자동으로:
1. Electron 앱 빌드
2. `osrm-data/` 포함
3. `backend/.env` 포함
4. `dist\DaOnRoad.zip` 생성

### 사용자에게 전달

```
dist\DaOnRoad.zip    ← 이것만 전달
```

ZIP 안에 모든 것이 포함되어 있습니다:
- 앱 실행파일 (`DaOnRoad.exe`)
- 백엔드 서버 코드
- 도로 지도 데이터 (`osrm-data/`)
- API 키 설정 (`.env`)

### 사용자 설치 방법 (전달용)

```
1. Docker Desktop 설치
   https://www.docker.com/get-started

2. DaOnRoad.zip 압축 해제

3. DaOnRoad.exe 실행
```

---

## Docker 관리 명령어

```cmd
rem 상태 확인
docker compose ps

rem 로그 확인
docker compose logs -f

rem 재시작
docker compose restart

rem 전체 재빌드 (코드 변경 후)
docker compose up -d --build

rem 종료
docker compose down
```

---

## 프로젝트 구조

```
DaOnRoad/
├── backend/                  Python FastAPI 서버
│   ├── .env                  API 키 (Git 미포함, 직접 생성)
│   ├── .env.example          .env 양식
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── api/                  라우터
│   ├── routing/              거리 계산, 지오코딩, OSRM
│   ├── solver/               VRP 최적화
│   ├── scheduler/            탑승시간 역산
│   └── export/               Excel 출력
├── frontend/                 Electron 앱
│   ├── index.html            메인 UI
│   ├── package.json
│   └── src/main.js           Electron 메인 프로세스
├── osrm-data/                OSRM 지도 데이터 (Git 미포함)
├── docker-compose.yml
├── start.bat                 개발 환경 시작 (Windows)
├── start.sh                  개발 환경 시작 (Mac/Linux)
├── build.bat                 배포 패키지 빌드
└── build.sh                  배포 패키지 빌드 (Mac/Linux)
```
