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

## 🧪 테스트 실행

```powershell
pytest
```

---

## 📦 MVTec AD Bottle 데이터셋 배치

- Bottle 데이터셋은 `dataset/bottle/` 경로에 수동으로 배치해 주세요.
- 정상 배치 시 `dataset/bottle/train`, `dataset/bottle/test`, `dataset/bottle/ground_truth` 형태가 됩니다.
- 데이터셋 원본 파일들은 `.gitignore`에 등록되어 있어 Git 저장소에 커밋되지 않습니다.

---

## 📅 Day 1 작업 내역 (완료)

### 1. 목표 및 완료 기준
- **목표:** MVTec AD Bottle 이미지 1장을 FastAPI에서 읽고 `POST /inspections` 요청에 고유 `inspection_id`를 발급하는 최소 백엔드 파이프라인 구축.
- **완료 여부:** 100% 완료 및 테스트 16종 전원 통과.

### 2. 구현된 핵심 기능

| 구분 | 주요 내용 | 관련 모듈 |
| :--- | :--- | :--- |
| **기본 백엔드 구조** | - Miniconda `vision-insight` (Python 3.11) 환경 기반 구축<br>- `GET /health` (`{"status": "ok"}` 반환)<br>- `GET /test-image` (OpenCV 이미지 로드 및 메타데이터 반환) | `backend/main.py`<br>`backend/tools/image_loader.py` |
| **OpenCV 영상 분석** | - Grayscale 변환 후 평균(`mean`), 표준편차(`std`), 최솟값/최댓값 계산<br>- 정상 209장 기준 통계(`baseline`) 집계 (정상 평균 136.34)<br>- 영상 품질(`NORMAL`, `WARNING_LOW_BRIGHTNESS`)과 제품 판정(`UNINSPECTED`) 분리 | `backend/vision.py`<br>`GET /analyze-brightness`<br>`GET /baseline/brightness` |
| **0.6배 오류 주입** | - NumPy 기반 0.6배 밝기 감쇄 시뮬레이션 (`inject_brightness_fault`)<br>- 원본 데이터셋 보존 및 `data/outputs/injected/` 경로에 안전하게 분리 저장<br>- 전후 비교 API (`GET /test-image/compare-fault`) 제공 | `backend/vision.py`<br>`backend/main.py` |
| **검사 식별자 및 정답 은닉** | - `product_id`와 `inspection_id` 엄격한 분리 (`INSP-000001`, `INSP-000002`...)<br>- `broken_large`, `contamination` 등 정답 레이블 폴더 은닉을 위한 중립 `image_id` (`IMG-BOTTLE-0001` ~ `0292`) 매핑<br>- `POST /inspections` 구현 (임의 경로 주입 차단 및 `result="UNKNOWN"` 반환) | `backend/inspection.py`<br>`POST /inspections`<br>`GET /inspections/images` |
| **데이터 스키마 문서화** | - 식별자 설계, 정답 격리 원칙, ISO 8601 KST 타임스탬프, API 스키마 규격 정리 | `docs/inspection-data-schema.md` |

### 3. 검증 현황 (`pytest`)
- `pytest -v` 총 16개 테스트 전원 통과 (`16 passed in 3.60s`):
  - 헬스체크 및 OpenAPI 문서 접근성 검증
  - OpenCV 이미지 로드 및 404/422 예외 처리 검증
  - 밝기 계산 및 0.6배 오류 주입 전후 비교 검증
  - 변형 이미지 저장 시 원본 불변성 검증
  - 연속 검사 요청 시 서로 다른 고유 `inspection_id` 발급 검증
  - 허용되지 않은 경로 입력(Path Traversal) 차단 검증
- Git 보안 검증 완료 (비밀키, 대용량 데이터셋, 변형 이미지 커밋 차단 확인).

