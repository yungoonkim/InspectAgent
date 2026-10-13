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
