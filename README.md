# InspectAgent
Vision 검사 이상 진단 AI Agent

MVTec AD Bottle 데이터셋 기반 산업용 Vision 검사 이상 진단 AI Agent 백엔드 서비스입니다.
FastAPI, OpenCV를 기반으로 동작하며, 향후 Gemini AI Agent (`gemini-3.8-flash`) 및 Google Cloud Run 배포를 연동할 예정입니다.

---

## 📁 프로젝트 구조

```text
InspectAgent/
├── .env.example              # 환경 변수 템플릿 파일
├── .gitignore                # Git 제외 파일 목록 (가상환경, 데이터셋 원본, 로그, 비밀키 등)
├── AGENTS.md                 # Agent 개발 지침 및 일정 규약
├── README.md                 # 본 문서
├── requirements.txt          # 기본 의존성 패키지 목록
├── backend/
│   ├── __init__.py
│   ├── config.py             # 로컬 및 Cloud Run 환경 설정 모듈
│   ├── inspection.py         # 검사 ID 발급 및 중립 이미지 레지스트리 (Day 1)
│   ├── main.py               # FastAPI 엔트리포인트 (Health Check, 검사, 비전 엔드포인트)
│   ├── vision.py             # 밝기 분석, 정상 기준 통계, 0.6배 오류 주입 (Day 1)
│   └── tools/                # Vision 검사 도구 모듈
│       ├── __init__.py
│       └── image_loader.py   # 안전한 OpenCV 이미지 로더
├── data/
│   ├── logs/                 # 실행 및 진단 로그 디렉토리 (.gitkeep)
│   └── outputs/              # 검사 생성 이미지/결과물 디렉토리 (.gitkeep)
│       └── injected/         # 0.6배 오류 주입 저장 경로 (원본 보존)
├── dataset/
│   └── bottle/               # MVTec AD Bottle 데이터셋 수동 배치 경로 (.gitkeep)
│       ├── train/good/
│       └── test/{good, broken_large, broken_small, contamination}/
├── docs/
│   ├── architecture.md       # 아키텍처 및 상세 가이드
│   ├── inspection-data-schema.md              # 검사 데이터 스키마 및 식별자 명세 (Day 1)
│   └── vision_inspection_data_naming_schema.md # 데이터 네이밍 규약
└── tests/
    ├── __init__.py
    ├── test_inspections.py   # 검사 ID 발급 및 경로 차단 테스트 (Day 1)
    ├── test_main.py          # 기본 엔드포인트 테스트
    └── test_vision.py        # 영상 지표 및 오류 주입 테스트 (Day 1)
```

---

## 🛠️ 개발 환경 설정 및 가상환경 가이드 (Conda 기준)

### 1. Conda 가상환경 생성

OpenCV 및 의존성 패키지 호환성을 위해 Python 3.10 또는 3.11 환경을 권장합니다.

```powershell
# 가상환경 생성 (이름: inspect-agent, Python 3.11)
conda create -n inspect-agent python=3.11 -y
```

### 2. 가상환경 활성화

```powershell
conda activate inspect-agent
```

<details>
<summary>💡 Python 기본 venv 사용 시 (참고용)</summary>

```powershell
# 생성
python -m venv .venv
# 활성화 (PowerShell)
.venv\Scripts\Activate.ps1
# 활성화 (CMD)
.venv\Scripts\activate.bat
```
</details>

> [!TIP]
> PowerShell에서 스크립트 실행 권한 오류(`ExecutionPolicy`)가 발생할 경우:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` 를 실행해 주세요.

### 3. 패키지 설치

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 환경 변수 설정

`.env.example` 파일을 복사하여 `.env` 파일을 생성합니다.

```powershell
# Windows PowerShell
Copy-Item .env.example .env

# Windows CMD
copy .env.example .env
```

`.env` 파일 내에서 필요에 따라 설정을 조정할 수 있습니다.
- `GEMINI_MODEL`: `gemini-3.8-flash` (기본 지정)
- `DATASET_PATH`: `dataset/bottle` (기본값)
- `PORT`: `8000` (Cloud Run 환경에서는 플랫폼이 `PORT` 환경 변수를 자동 주입)

---

## 🚀 실행 명령어

프로젝트 루트에서 다음 명령어로 FastAPI 개발 서버를 실행할 수 있습니다.

```powershell
uvicorn backend.main:app --reload
```

- 로컬 서버 접속: [http://localhost:8000](http://localhost:8000)
- 대화형 API 문서(Swagger UI): [http://localhost:8000/docs](http://localhost:8000/docs)
- 헬스체크 엔드포인트: [http://localhost:8000/health](http://localhost:8000/health)
- 검사 등록 엔드포인트: `POST /inspections` (Body: `{"product_id": "ABCD1541", "image_id": "IMG-BOTTLE-0001"}`)
- 등록 가능 이미지 목록: `GET /inspections/images`
- 데이터 스키마 명세: [docs/inspection-data-schema.md](docs/inspection-data-schema.md)

---

## 🧪 테스트 및 시나리오 검증 실행

```powershell
# 1. 전체 pytest 테스트 스위트 (총 57개 테스트)
pytest -v

# 2. T03 오류 주입 이미지 생성 및 원본 SHA-256 검증
python scripts/generate_t03_fault.py

# 3. T01, T03, T05, T06 시나리오 2회 반복 자동 검증 러너
python scripts/verify_day3_scenarios.py
```

---

## 📦 MVTec AD Bottle 데이터셋 배치

- Bottle 데이터셋은 `dataset/bottle/` 경로에 수동으로 배치해 주세요.
- 정상 배치 시 `dataset/bottle/train`, `dataset/bottle/test`, `dataset/bottle/ground_truth` 형태가 됩니다.
- 데이터셋 원본 파일들은 `.gitignore`에 등록되어 있어 Git 저장소에 커밋되지 않습니다.

---

## 📅 마일스톤 및 작업 내역

### Day 1: 기반 인프라 및 최초 검사 API (완료)
- FastAPI 백엔드 구축 (`GET /health`, `GET /test-image`)
- OpenCV 영상 품질 분석 및 0.6배 오류 주입 (`backend/vision.py`)
- 중립 `image_id` 매핑 및 순차 고유 `inspection_id` 발급 (`POST /inspections`)

### Day 2: 밝기 통계 완성 및 JSONL 영구 저장 (완료)
- 정상 209장 기준 통계 계산 및 임계값(`BRIGHTNESS_LOW_THRESHOLD = 125.0`) 반영
- `data/inspections.jsonl` 및 `data/inspection_logs.jsonl` 스레드 세이프 저장소 구축
- `POST /inspections` 요청 시 이미지 로드 -> 분석 -> 로그 -> 결과 저장 원스톱 파이프라인 완성

### Day 3: 오류 주입 시나리오 4종 및 평가 정답 물리적 격리 (완료)
- **T01 (정상 검사)**: 정상 Bottle 원본 검사 (`IMG-BOTTLE-0084`), 품질 `NORMAL`, 결과 `UNKNOWN`
- **T03 (조도 저하)**: 0.6배 밝기 감쇄 사본 검사 (`IMG-BOTTLE-INJ-0001`), 품질 `WARNING_LOW_BRIGHTNESS` (하드코딩 배제, 임계값 기반 동적 판정)
- **T05 (로드 실패)**: 비프로덕션 테스트 stub 부재 경로 참조 (`IMG-BOTTLE-NONEXISTENT`), 404 Not Found 및 `IMAGE_LOAD_FAILED` / `INSPECTION_FAILED` 로깅 (`ANALYSIS_COMPLETED` 미발생 보장)
- **T06 (불량 원본)**: MVTec `broken_large` 불량 원본 정상 흐름 처리 (`IMG-BOTTLE-0001`), 품질 `NORMAL`, 결과 `UNKNOWN` (제품 불량과 프로그램 오류의 엄격한 분리)
- **정답 격리**: `Project/evaluation_private/`로 물리적 분리 및 운영 코드 무참조(Zero Reference) 달성
- **통합 검증**: 57개 pytest 전체 통과 (`57 passed, 1 warning in 5.09s`), 2-Pass 재현 완수

