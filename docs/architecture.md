# InspectAgent: Architecture & Setup Guide

## 1. 프로젝트 개요
**InspectAgent**는 MVTec AD Bottle 데이터셋 기반의 산업용 Vision 검사 이상 진단 AI Agent 서비스입니다.
FastAPI를 백엔드 웹 프레임워크로 사용하며, OpenCV를 통한 이미지 전처리/특징 추출, 향후 **`gemini-3.8-flash`** 모델 기반의 AI Agent 진단 및 Google Cloud Run 배포를 목표로 합니다.

---

## 2. 디렉토리 구조 및 역할

```text
InspectAgent/
├── .env.example              # 환경 변수 설정 템플릿
├── .gitignore                # Git 제외 파일 목록 (가상환경, 데이터셋 원본, 로그, 산출물, 비밀키)
├── README.md                 # 프로젝트 개요 및 빠른 시작 가이드
├── requirements.txt          # 프로젝트 핵심 의존성 목록
├── backend/
│   ├── __init__.py
│   ├── config.py             # 로컬 / Cloud Run 환경 설정 및 경로 통합 관리
│   ├── main.py               # FastAPI 엔트리포인트 (Health Check 및 라우터)
│   └── tools/                # Vision 검사 및 AI Agent 도구 모듈 (향후 구현)
│       └── __init__.py
├── data/
│   ├── logs/                 # 실행 및 진단 로그 보관 디렉토리 (.gitkeep)
│   └── outputs/              # 검사 생성 이미지 및 시각화 결과물 보관 (.gitkeep)
├── dataset/
│   └── bottle/               # MVTec AD Bottle 데이터셋 수동 배치 경로 (.gitkeep)
├── docs/                     # 프로젝트 문서화
│   └── architecture.md       # 시스템 아키텍처 및 설정 가이드
└── tests/
    ├── __init__.py
    └── test_main.py          # 기본 API 엔드포인트 및 설정 단위 테스트
```

---

## 3. MVTec AD Bottle 데이터셋 가이드
MVTec AD Bottle 데이터셋은 수동으로 `dataset/bottle/` 폴더 아래에 배치합니다.

표준 MVTec AD Bottle 폴더 구조:
```text
dataset/bottle/
├── ground_truth/
│   ├── broken_large/
│   ├── broken_small/
│   └── contamination/
├── test/
│   ├── good/
│   ├── broken_large/
│   ├── broken_small/
│   └── contamination/
└── train/
    └── good/
```

> [!NOTE]
> 데이터셋 원본 파일들은 `.gitignore`에 의해 Git 추적 대상에서 제외되므로, 저장소 용량 및 보안에 영향을 주지 않습니다.

---

## 4. 환경 설정 및 Google Cloud Run 배포 고려사항

1. **포트(PORT) 바인딩**:
   - Google Cloud Run은 환경 변수 `PORT`를 컨테이너에 주입합니다(기본값: 8080).
   - `backend/config.py`에서 `os.getenv("PORT", "8000")`을 조회하여 동적으로 포트를 바인딩합니다.
2. **무상태(Stateless) 컨테이너**:
   - Cloud Run 인스턴스는 일시적이므로 로컬 파일 시스템(`data/outputs`, `data/logs`) 저장은 영속성을 갖지 않습니다.
   - 추후 클라우드 환경에서는 Google Cloud Storage(GCS) 또는 BigQuery/Cloud Logging과 연동할 수 있도록 `config.py`의 경로 추상화를 유지합니다.
3. **Gemini 모델**:
   - 프로젝트 요구사항에 따라 `gemini-3.8-flash` 모델을 기본값으로 사용합니다.

---

## 5. 저장소 동시성 제약 및 배포 영구 저장 제약사항 (MVP 기준)

### 5.1 로컬 JSONL 저장소 동시성 제약
1. **단일 프로세스 다중 스레드 (Thread Safety)**:
   - `JsonlInspectionStorage`는 Python의 `threading.Lock`을 통해 파일 쓰기 연산의 원자성을 보장합니다.
   - 단일 프로세스 내에서 복수의 동시 요청이 발생하더라도 JSONL 라인이 섞이거나(interleaving) 손상되지 않습니다.
2. **다중 프로세스 환경 제약 (Process Safety)**:
   - 현재 구현은 OS 레벨의 파일 잠금(file lock, 예: `portalocker` 또는 `fcntl`)을 사용하지 않으므로, Uvicorn 다중 워커(`--workers N`)나 Gunicorn 다중 프로세스 환경에서는 파일 경합에 따른 데이터 손상이 발생할 수 있습니다.
   - MVP 개발 단계에서는 **단일 프로세스(Worker 1개)** 환경으로 제한하여 운영합니다.

### 5.2 Google Cloud Run 배포 시 영구 저장 제약
1. **로컬 파일시스템의 휘발성 (Ephemeral Filesystem)**:
   - Cloud Run 인스턴스는 무상태(stateless)로 동작하며 인스턴스 스케일 인(축소), 교체, 재시작 시 컨테이너 로컬 디스크(`data/inspections.jsonl`, `data/inspection_logs.jsonl`)의 모든 파일이 즉시 초기화/소실됩니다.
   - 따라서 로컬 JSONL 저장은 개발 및 PoC 테스트 전용이며, 배포 환경에서 검사 이력을 영구 보존하려면 **Google Cloud Storage (GCS)** 버킷 객체 저장 또는 Cloud SQL 연동이 필수적입니다.
2. **저장소 인터페이스(`InspectionStorageBase`) 분리 이유**:
   - `backend/storage.py`에 추상 인터페이스를 선제적으로 설계한 이유는 향후 Cloud Run 배포 시 비즈니스 및 Agent API 코드 수정 없이 GCS 기반 스토리지 어댑터로 즉시 교체하기 위함입니다.

---

## 6. 알려진 개발 및 테스트 환경 이슈

### 6.1 pytest 실행 시 StarletteDeprecationWarning
- **경고 메시지**: `StarletteDeprecationWarning: Using 'httpx' with 'starlette.testclient' is deprecated; install 'httpx2' instead.`
- **환경 버전**: `fastapi==0.143.0`, `starlette==1.8.0`, `httpx==0.28.1`
- **발생 원인**: Starlette 1.8.0 내부의 `starlette.testclient`가 향후 라이브러리 전환 계획을 알리기 위해 출력하는 비파괴적 안내성 경고입니다.
- **영향도 및 조치 방침**:
  - **영향 없음**: 실제 FastAPI 서버 서빙(런타임 프로덕션 코드)에는 `TestClient`가 호출되지 않으므로 영향이 전혀 없습니다.
  - **테스트 정상성**: pytest 실행 시 단순 안내 경고로만 출력되며, 전체 44개 테스트가 정상 통과(100% PASS)합니다.
  - **유지 결정**: 임의 패키지 변경으로 인한 부작용을 방지하기 위해 불필요한 업그레이드나 패키지 교체 없이 현재 환경을 안정적으로 유지합니다.


