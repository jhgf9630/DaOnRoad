# 🚌 DaOnRoad — 버스 노선 최적화 시스템

여행사 버스 배차 자동화 프로그램  
승객 탑승지 정보를 입력하면 최적 버스 노선을 자동으로 생성합니다.

---

## 📑 목차

- [시스템 구조](#시스템-구조)
- [관리자 가이드 — 최초 설치](#관리자-가이드--최초-설치)
- [관리자 가이드 — 배포 및 배포 후 관리](#관리자-가이드--배포-및-배포-후-관리)
- [사용자 가이드 — 앱 사용법](#사용자-가이드--앱-사용법)
- [문제 해결](#문제-해결)

---

## 시스템 구조

```
DaOnRoad/
├── backend/              Python FastAPI 서버
│   ├── .env              ★ API 키 설정 (직접 생성)
│   ├── .env.example      API 키 양식 예시
│   ├── requirements.txt  Python 패키지 목록
│   ├── main.py           서버 진입점
│   ├── api/              라우터 (upload, routing, export)
│   ├── routing/          거리 계산, 지오코딩, OSRM 연동
│   ├── solver/           VRP 최적화 알고리즘
│   ├── scheduler/        탑승시간 역산
│   └── export/           Excel 출력
│
├── frontend/             Electron 데스크톱 앱
│   ├── index.html        메인 UI
│   ├── package.json
│   └── src/main.js       Electron 메인 프로세스
│
├── osrm-data/            ★ OSRM 지도 데이터 (직접 생성)
│   └── south-korea-latest.osrm  (전처리 후 생성)
│
└── .gitignore
```

**기술 스택:**

| 분류 | 기술 |
|------|------|
| 백엔드 | Python 3.10+, FastAPI, OR-Tools |
| 프론트엔드 | Electron, Leaflet.js |
| 주소 검색 | Kakao Local API (검색만 사용) |
| 경로 계산 | OSRM (실제 도로망) |
| 지도 | OpenStreetMap |
| Excel | openpyxl |

---

# 관리자 가이드 — 최초 설치

> 개발자 또는 배포 담당자가 최초 1회 수행하는 작업입니다.

---

## STEP 1 — 사전 준비물 설치

아래 3가지가 모두 설치되어 있어야 합니다.

### Python 3.10 이상
```
https://www.python.org/downloads/
```
설치 시 **"Add Python to PATH"** 반드시 체크.

설치 확인:
```cmd
python --version
```

### Node.js 18 이상
```
https://nodejs.org/
```

설치 확인:
```cmd
node --version
npm --version
```

### Docker Desktop
```
https://www.docker.com/get-started
```

설치 후 Docker Desktop 실행 → 트레이 아이콘이 초록색이 될 때까지 대기.

설치 확인:
```cmd
docker --version
```

---

## STEP 2 — 저장소 클론

```cmd
git clone https://github.com/본인계정/DaOnRoad.git
cd DaOnRoad
```

---

## STEP 3 — Kakao API 키 발급 및 설정

주소/장소 검색에 사용합니다. **최초 1회만** 설정하면 됩니다.

### 키 발급 방법

1. [developers.kakao.com](https://developers.kakao.com) 접속 → 로그인
2. **내 애플리케이션 → 애플리케이션 추가하기**
3. 앱 이름 입력 후 생성
4. **앱 키 탭 → REST API 키** 복사

5. ⚠️ **필수 설정** — 왼쪽 메뉴 **제품 설정 → 카카오맵 → 사용 설정 ON**
   (이 설정을 빠뜨리면 검색이 동작하지 않습니다)

### .env 파일 생성

`backend/` 폴더 안에 `.env` 파일을 새로 만듭니다.  
`.env.example` 파일을 복사해서 이름을 `.env` 로 변경해도 됩니다.

```
backend/.env 내용:

KAKAO_API_KEY=여기에_REST_API_키_붙여넣기
OSRM_BASE_URL=http://127.0.0.1:5001
```

> ⚠️ `.env` 파일은 Git에 올라가지 않습니다 (`.gitignore`에 포함).  
> 배포할 때마다 서버에서 직접 생성해야 합니다.

---

## STEP 4 — Python 가상환경 및 패키지 설치

```cmd
cd backend

python -m venv venv

venv\Scripts\activate

pip install -r requirements.txt
```

설치 완료 확인:
```cmd
python -c "import fastapi, ortools; print('OK')"
```

---

## STEP 5 — Node.js 패키지 설치

```cmd
cd frontend
npm install
```

---

## STEP 6 — OSRM 실제 도로 경로 서버 구축

OSRM은 직선 경로 대신 **실제 도로망 기반 경로**를 제공합니다.  
한 번만 구축하면 이후에는 `docker start` 명령어 하나로 실행됩니다.

### 6-1. 지도 데이터 다운로드

프로젝트 루트에서 실행:

```cmd
mkdir osrm-data
cd osrm-data
```

한국 지도 데이터 다운로드 (약 900MB, 10~20분 소요):

```cmd
curl -O https://download.geofabrik.de/asia/south-korea-latest.osm.pbf
```

### 6-2. OSRM 전처리 (3단계, 총 15~25분)

`osrm-data` 폴더 안에서 실행:

```cmd
rem 1단계: 도로 데이터 추출 (5~10분)
docker run -t -v "%cd%:/data" osrm/osrm-backend:latest osrm-extract -p /opt/car.lua /data/south-korea-latest.osm.pbf

rem 2단계: 파티션 (5~8분)
docker run -t -v "%cd%:/data" osrm/osrm-backend:latest osrm-partition /data/south-korea-latest.osrm

rem 3단계: 최적화 (3~5분)
docker run -t -v "%cd%:/data" osrm/osrm-backend:latest osrm-customize /data/south-korea-latest.osrm
```

완료 후 `osrm-data/` 폴더에 `.osrm` 관련 파일이 여러 개 생성됩니다.

### 6-3. OSRM 서버 실행

```cmd
cd osrm-data
docker run -d --name osrm-korea -p 5001:5000 -v "%cd%:/data" osrm/osrm-backend:latest osrm-routed --algorithm mld /data/south-korea-latest.osrm
```

30초 대기 후 연결 확인:
```cmd
curl "http://127.0.0.1:5001/table/v1/driving/126.978,37.566;127.027,37.498"
```

`{"code":"Ok",...}` 가 나오면 성공.

---

## STEP 7 — 전체 동작 확인

### 백엔드 실행
```cmd
cd backend
venv\Scripts\activate
python main.py
```

정상 출력:
```
[main] KAKAO_API_KEY: ✅ 설정됨 (xxxxxx...)
[main] OSRM_BASE_URL: ✅ 설정됨 (http://127.0.0.1:5001)
INFO: Uvicorn running on http://127.0.0.1:8000
```

### 상태 확인 (브라우저)
```
http://127.0.0.1:8000/api/osrm-status
```

```json
{ "status": "ok", "is_local": true, "sample_duration_sec": 597 }
```

### 프론트엔드 실행 (별도 터미널)
```cmd
cd frontend
npm start
```

앱이 열리고 헤더에 **✅ 연결됨** 이 표시되면 완료.

---

# 관리자 가이드 — 배포 및 배포 후 관리

---

## 사용자에게 배포하는 방법

DaOnRoad는 **데스크톱 앱(Electron)** 형태로 배포합니다.  
사용자는 설치 파일(.exe)을 실행하기만 하면 됩니다.

### 배포 파일 빌드

```cmd
cd frontend
npm run build
```

`frontend/dist/` 폴더에 설치 파일이 생성됩니다:
- Windows: `DaOnRoad Setup 1.0.0.exe`

### 배포 시 포함해야 할 것

사용자 PC에는 아래가 필요합니다:

| 항목 | 방법 |
|------|------|
| Python + 패키지 | 설치 파일에 포함하거나 별도 안내 |
| backend 폴더 전체 | 배포 패키지에 포함 |
| `.env` 파일 | 배포 시 별도 제공 또는 사용자가 생성 |
| Docker + OSRM | 사용자 PC에서 별도 설치 (선택사항) |

> 💡 **권장 배포 방식**: backend 폴더와 Electron 설치 파일을 ZIP으로 묶어서 제공.  
> 사용자는 ZIP 해제 → `.exe` 실행 → 백엔드는 앱이 자동 실행.

---

## 매일 실행 방법 (배포 후 운영)

### 방법 A — Electron 앱 실행 (백엔드 자동 시작)

> `backend/venv` 가상환경이 설치된 상태여야 합니다.

```cmd
cd frontend
npm start
```

앱이 열리면서 백엔드 자동 실행. 헤더에 ✅ 연결됨 확인.

---

### 방법 B — 수동 실행 (자동 시작 실패 시)

**터미널 1 — OSRM 서버:**
```cmd
docker start osrm-korea
```

**터미널 2 — 백엔드:**
```cmd
cd backend
venv\Scripts\activate
python main.py
```

**터미널 3 — 프론트엔드:**
```cmd
cd frontend
npm start
```

---

## OSRM 서버 관리 명령어

```cmd
rem 시작 (재부팅 후)
docker start osrm-korea

rem 중지
docker stop osrm-korea

rem 상태 확인
docker ps | findstr osrm

rem 로그 확인
docker logs osrm-korea

rem 자동 시작 설정 (Windows 부팅 시 자동 실행)
docker update --restart=always osrm-korea
```

---

## 지도 데이터 업데이트 (연 1~2회 권장)

한국 OSM 지도 데이터는 매월 업데이트됩니다.  
도로 변경이 많을 경우 아래 절차로 갱신합니다.

```cmd
rem 기존 컨테이너 중지 및 삭제
docker stop osrm-korea
docker rm osrm-korea

rem osrm-data 폴더의 기존 파일 삭제 후
rem STEP 6 전체 재실행 (다운로드 → 전처리 → 실행)
```

---

# 사용자 가이드 — 앱 사용법

---

## 앱 실행

관리자가 제공한 방법으로 앱을 실행합니다.  
헤더 우측에 **✅ 연결됨** 이 표시되면 사용 준비 완료입니다.

---

## STEP 1 — 승객 데이터 업로드

### Excel 파일 형식

아래 3개 열이 필요합니다:

| name (이름) | address (주소) | passenger_count (인원) |
|------------|--------------|----------------------|
| 홍길동 | 서울 강남구 역삼동 | 1 |
| 김철수 | 인천 연수구 송도동 | 2 |
| 박영희 | 경기 부천시 중동 | 3 |

- 열 이름은 한글(이름/주소/인원)도 자동 인식합니다.
- 주소는 도로명 또는 지번 모두 가능합니다.

### 업로드 방법

1. 사이드바 **Step 1** 영역 클릭 또는 Excel 파일을 드래그
2. 업로드 완료 후 승객 목록과 지도 마커 확인
3. **좌표 ✗** 표시된 항목은 주소를 수정해야 합니다

---

## STEP 2 — 차량 설정

### 차량 추가

1. **버스 ID** 입력 (예: Bus1, 인천버스1)
2. **정원** 입력 (예: 45)
3. **출발지** 입력 후 **✅ 확인** 버튼 클릭
4. 검색 결과 드롭다운에서 정확한 위치 선택
5. 지도에서 위치 확인 후 **+ 차량 추가** 클릭

### 차량 수정

등록된 차량 우측 ✏️ 버튼 클릭 → 출발지/정원 수정 → **저장**

### 주의사항

- 모든 차량에 최소 1명 이상이 배정됩니다
- 총 차량 정원 ≥ 총 승객 수 이어야 합니다
- 좌표가 확인(✓)된 차량만 노선 생성에 사용됩니다

---

## STEP 3 — 노선 생성

1. **도착지** 입력 후 **✅ 확인** → 드롭다운에서 선택
2. **도착 목표시간** 설정 (예: 10:00)
3. **🚀 최적 노선 생성** 클릭

### 결과 확인

| 항목 | 위치 |
|------|------|
| 운행 버스 수, 총 탑승객 | 사이드바 결과 요약 |
| 버스별 노선 상세 (탑승자/탑승시간) | 사이드바 노선 상세 |
| 지도 시각화 | 메인 지도 영역 |
| 버스별 필터 | 지도 하단 탭 |

- **실선**: 실제 도로 경로 (OSRM 활성화 시)
- **파선**: 직선 경로 (OSRM 미설정 시)

---

## STEP 4 — Excel 저장

1. **📥 Excel 저장** 버튼 클릭
2. 저장 위치 선택
3. 생성된 파일 구성:

| 시트 | 내용 |
|------|------|
| Bus Summary | 버스별 출발시간, 도착시간, 소요시간, 탑승인원 |
| Route Detail | 정류장 순서, 탑승지, 탑승시간 |
| Passenger | 승객별 버스 배정, 탑승지, 탑승시간 |

---

# 문제 해결

## "백엔드 연결 실패" 배너가 표시될 때

**원인**: Python 백엔드가 실행되지 않음

**해결**:
```cmd
cd backend
venv\Scripts\activate
python main.py
```

실행 후 앱 헤더의 **재연결** 버튼 클릭.

---

## 주소 검색 결과가 나오지 않을 때

**체크리스트:**

1. `backend/.env` 파일에 `KAKAO_API_KEY` 설정 여부 확인
2. Kakao Developers → 제품 설정 → **카카오맵 사용 설정 ON** 확인
3. REST API 키인지 확인 (JavaScript 키 ❌)

**진단 URL** (백엔드 실행 중):
```
http://127.0.0.1:8000/api/debug-key
```

---

## 노선이 직선으로 표시될 때

**원인**: OSRM 서버 미설정 또는 미실행

**해결**:
```cmd
docker start osrm-korea
```

상태 확인:
```
http://127.0.0.1:8000/api/osrm-status
```
`"status": "ok"` 확인 후 노선 재생성.

---

## OSRM 서버가 연결되지 않을 때

```cmd
rem 컨테이너 상태 확인
docker ps -a | findstr osrm

rem 로그 확인
docker logs osrm-korea

rem 직접 연결 테스트
curl "http://127.0.0.1:5001/table/v1/driving/126.978,37.566;127.027,37.498"
```

---

## 노선 생성 후 빈 버스가 있을 때

**원인**: 승객 수가 차량 수보다 적은 경우

모든 차량에 최소 1명이 강제 배정되므로, 승객 수 ≥ 차량 수인지 확인하세요.

---

## 캐시 초기화가 필요할 때

주소 검색 결과가 오래된 데이터를 반환하면:

```cmd
rem cache 폴더 삭제 (백엔드 종료 후)
rmdir /s /q backend\cache
```

또는 실행 중 초기화:
```
curl -X DELETE http://127.0.0.1:8000/api/cache
```
