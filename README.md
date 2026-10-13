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
├── README.md                 # 본 문서
├── requirements.txt          # 기본 의존성 패키지 목록
├── backend/
│   ├── __init__.py
│   ├── config.py             # 로컬 및 Cloud Run 환경 설정 모듈
│   ├── main.py               # FastAPI 엔트리포인트 (기본 헬스체크 구현)
│   └── tools/                # Vision 검사 및 AI Agent 도구 패키지 (향후 구현)
│       └── __init__.py
├── data/
│   ├── logs/                 # 실행 및 진단 로그 디렉토리 (.gitkeep)
│   └── outputs/              # 검사 생성 이미지/결과물 디렉토리 (.gitkeep)
├── dataset/
│   └── bottle/               # MVTec AD Bottle 데이터셋 수동 배치 경로 (.gitkeep)
├── docs/
│   └── architecture.md       # 아키텍처 및 상세 가이드
└── tests/
    ├── __init__.py
    └── test_main.py          # 기본 엔드포인트 테스트
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
