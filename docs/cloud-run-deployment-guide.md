# VisionInsight — Google Cloud Run CPU 추론 배포 준비 및 리소스 점검 보고서

> **작성일:** 2026-10-14  
> **단계:** Day 3.5 / 프롬프트 7  
> **상태:** 배포 준비 완료 (실제 클라우드 리소스 생성 및 배포는 수행하지 않음)  

---

## 1. 개요 및 목표

본 문서는 VisionInsight의 PatchCore ResNet-18 이상 진단 모델을 **GPU 없이 CPU 환경에서 안정적으로 서비스하기 위한 Google Cloud Run 배포 구성 및 리소스 실측 결과**를 정리합니다.

- **목표:**
  1. PyTorch CPU 전용 의존성 분리 및 경량 컨테이너 환경 준비
  2. Cloud Run 환경 표준(PORT 환경변수, 0.0.0.0 바인딩, 무중단 lifespan) 준수
  3. 모델 파일(24.18MB) 배포 전략 비교 및 최적안 선정
  4. 로컬 CPU 추론 지연시간 및 프로세스 메모리 실측을 통한 Cloud Run 사양 추천
  5. JSONL 파일시스템 제약 분석 및 영구 저장소 전환 로드맵 수립

---

## 2. 운영용 Docker 및 환경 구성

### 2.1 의존성 분리 (`requirements-prod.txt`)
- 로컬 개발 환경의 CUDA 의존성(`cu124` 등 수 GB)을 배제하고, 공식 PyTorch CPU 휠(`torch==2.6.0+cpu`, `torchvision==0.21.0+cpu`)을 채택하여 컨테이너 이미지 크기를 대폭 감축했습니다.
- 학습 전용/평가 전용 패키지를 배제하고 추론 및 웹 서비스 구동 필수 라이브러리(`fastapi`, `uvicorn`, `anomalib`, `timm`, `opencv-python-headless`)만 포함했습니다.

### 2.2 운영 보안 및 이미지 최적화 (`.dockerignore`)
- `dataset/` (MVTec 원본 데이터셋)
- `data/splits/` (학습/검증 분할 목록)
- `tests/` 및 `scripts/` (테스트 및 학습 스크립트)
- `.git/`, `.env`, 캐시 디렉터리(`__pycache__`)
- 위 경로를 빌드 컨텍스트에서 완전히 배제하여 민감 데이터 누출 방지 및 빌드 속도를 최적화했습니다.

### 2.3 Cloud Run 전용 `Dockerfile`
- **Base Image:** `python:3.11-slim`
- **시스템 패키지:** `libgl1`, `libglib2.0-0`, `libgomp1` (OpenCV 및 PyTorch CPU 런타임 필수 의존성)
- **환경 변수:**
  - `HF_HUB_OFFLINE=1`: 네트워크 격리 환경에서 Hugging Face Hub 요청 원천 차단
  - `ENABLE_PATCHCORE=true`: PatchCore 추론 활성화
  - `PATCHCORE_DEVICE=cpu`: CPU 추론 명시
  - `PORT=8080`: Cloud Run 기본 포트
- **실행 명령:**
  ```bash
  CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --workers 1
  ```
  *(운영 컨테이너에서는 `--reload`를 사용하지 않으며 단일 워커 프로세스로 메모리 효율을 극대화합니다)*

---

## 3. 모델 파일 배포 방식 비교 및 추천

| 구분 | 방식 A: Docker 이미지 내 모델 포함 (선택) | 방식 B: Cloud Storage 다운로드 로드 |
| :--- | :--- | :--- |
| **개념** | `models/patchcore/` 디렉터리를 이미지 빌드 시 복사 | 컨테이너 시작 시 GCS 버킷에서 다운로드 |
| **장점** | • 외부 네트워크/인증 종속성 전무<br>• Cold Start 즉시 메모리 로드(추가 다운로드 0초)<br>• 배포 재현성 100% 보장 | • 애플리케이션 코드와 모델 가중치 분리<br>• 모델 교체 시 컨테이너 재빌드 불필요 |
| **단점** | • 모델 변경 시 Docker 이미지 재빌드 필요 | • GCS 다운로드 시간으로 인한 Cold Start 지연<br>• IAM 권한 설정 및 장애 처리 로직 추가 필요 |
| **적합성** | **초기 포트폴리오 MVP에 최적 (강력 추천)** | 대용량(수 GB 이상) 멀티 모델 운영 시 적합 |

> **추천 사유:**  
> 현재 PatchCore 체크포인트(`patchcore_bottle.ckpt`) 크기는 **24.18MB**로 매우 작습니다.  
> 24MB 수준의 모델은 Docker 이미지 크기에 거의 영향을 미치지 않으며, GCS 인증 실패나 네트워크 타임아웃 위험을 원천 제거하여 Cloud Run 인스턴스 스케일아웃 시 신속한 기동이 가능합니다.

---

## 4. CPU 리소스 및 지연시간 실측 결과

*측정 환경: Intel/AMD x86_64 CPU, Windows 11, Python 3.11 (`vision-insight`)*

| 측정 항목 | 실측값 | 비고 |
| :--- | :--- | :--- |
| **모델 최초 로딩 시간** | **3,813.08 ms** (~3.8초) | 서버 프로세스 시작 시 lifespan에서 1회 수행 |
| **모델 로딩 전 프로세스 메모리** | 474.13 MB | 기본 FastAPI 및 패키지 임포트 상태 |
| **모델 로딩 후 프로세스 메모리** | 798.31 MB | 메모리 뱅크 `[9216, 384]` 복원 |
| **순수 모델 점유 메모리 (Delta)** | **+324.18 MB** | ResNet-18 가중치 및 Coreset 메모리 뱅크 |
| **단일 이미지 첫 추론 (Warm-up)** | 51.79 ms | 순수 PyTorch 추론 시간 44.11 ms |
| **정상 이미지(T01) 반복 추론 (n=20)** | **평균 41.04 ms** (최소 39.58 / 최대 46.08 ms) | 표준편차 1.54 ms |
| **불량 이미지(T06) 반복 추론 (n=20)** | **평균 41.49 ms** (최소 38.62 / 최대 51.31 ms) | 표준편차 2.62 ms |
| **정상 vs 불량 추론 지연시간 차이** | **0.45 ms** | 결함 유무에 따른 연산 부하 차이 없음 |
| **추론 반복 후 프로세스 메모리** | 842.69 MB | 안정적인 메모리 유지 (메모리 누수 없음) |
| **첫 번째 E2E API 요청 (`POST /inspections`)**| 69.01 ms | 상태 201, 결과 OK, score: 32.2679 |
| **반복 E2E API 요청 (`POST /inspections`, n=10)** | **평균 77.35 ms** | HTTP 통신 + 전처리 + 추론 + JSONL 저장 |
| **서버 전체 최종 RSS 메모리** | **869.11 MB** | 1GB 이하에서 안정적 구동 |

---

## 5. Cloud Run 권장 사양 및 비용 분석

### 5.1 초기 권장 사양
- **CPU:** **1 vCPU** (동시 요청 처리 및 추론 연산에 충분)
- **Memory:** **2 GiB** (프로세스 RSS 약 870MB + 버퍼 여유 공간 확보)
- **Min Instances:** **0** (비용 최적화를 위해 요청 없을 시 0으로 축소)
- **Max Instances:** **1** (초기 MVP 단계에서의 예기치 않은 과금 방지)
- **Concurrency:** **10 ~ 20** (FastAPI 비동기 I/O 기반 단일 워커 기준)
- **Timeout:** **60초** (Cold Start 4초 + 추론 0.1초를 충분히 커버)

### 5.2 Cold Start 고려사항
- 인스턴스가 0에서 1로 기동될 때 컨테이너 부팅 + Python 임포트 + lifespan 모델 로딩에 **약 4~5초**가 소요됩니다.
- 초기 로딩 이후의 개별 요청은 싱글톤 캐시를 통해 **~75ms 내외**로 즉각 응답합니다.

### 5.3 비용 요소 구분
1. **로컬 개발/학습:** 클라우드 비용 **0원**
2. **Cloud Run CPU/메모리:** 요청 처리 시간 동안만 초 단위 과금 (무료 할당량 내 활용 가능)
3. **Artifact Registry (컨테이너 이미지 저장):** 저장 용량(약 1~2GB)에 따른 미미한 스토리지 요금 발생 가능
4. **Cloud Storage (향후 Day 7 영구 저장소 도입 시):** 수 MB 단위 로그 저장은 매우 저렴
5. **Gemini API (Day 4 에이전트 도입 시):** 토큰 사용량에 따라 별도 과금 발생

---

## 6. JSONL 파일시스템 제약 및 영구 저장소 로드맵

### 6.1 Cloud Run 파일시스템의 특성
- Cloud Run 컨테이너 인스턴스는 **Stateless(무상태)** 환경입니다.
- 인스턴스가 스케일 다운되거나 새 리비전으로 교체되면 로컬 디스크(`data/inspections.jsonl`, `data/inspection_logs.jsonl`)의 기록은 소멸됩니다.

### 6.2 저장 계층 분리 및 향후 전환 계획
- 현재 백엔드는 `InspectionStorageBase` 인터페이스를 통해 비즈니스 로직과 저장 구현이 분리되어 있습니다.
- **Day 4:** 개발 환경 로컬 JSONL 저장을 유지하며 Gemini Agent와의 구조화 질의 인터페이스 구축
- **Day 7:** Cloud Run 배포 시 `Google Cloud Storage (GCS)` 기반의 버킷 저장소 어댑터(`GCSInspectionStorage`)를 선택적으로 주입하여 영구 보존 및 감사 로그를 영구화할 수 있도록 설계

### 6.3 Day 7 검사 이미지 제공 방식 계획 및 배포 전 체크리스트
현재 Docker 구성(`Dockerfile`, `.dockerignore`)은 보안 및 이미지 경량화를 위해 **원본 MVTec 데이터셋 전체(`dataset/`)를 빌드에서 완전히 제외**하고 있습니다.  
따라서 운영 컨테이너에 검사 대상 이미지가 제공되지 않으면 `POST /inspections` 호출 시 `ImageRegistry`가 이미지를 찾지 못해 검사 파이프라인이 실패(`final_result=ERROR`)하게 됩니다.

Day 7 실제 배포 전 아래 두 가지 방식 중 하나를 확정해야 합니다:
1. **방안 A (최소 데모 검사 이미지 번들링 - MVP 권장):**
   - 중립 식별자로 명명된 소수의 데모 이미지(예: 5~10장)만 `demo_images/` 디렉터리에 포함하여 컨테이너 이미지와 함께 배포.
   - 외부 스토리지 의존성 없이 즉시 작동하며 포트폴리오 데모에 최적.
2. **방안 B (Cloud Storage 이미지 스트리밍 연동):**
   - 검사 이미지를 GCS 버킷에 업로드하고, 검사 요청 시 스트리밍 다운로드 또는 사전 서명된 URL(Signed URL)로 취득.
   - 대규모 산업 환경에 적합하나 버킷 생성, IAM 인증 설정, 다운로드 지연시간 발생.

> **Day 7 배포 전 필수 체크리스트:**
> - [ ] 검사 대상 이미지 제공 경로 확정 (방안 A 데모 이미지 번들링 vs 방안 B GCS 스토리지 연동)
> - [ ] 컨테이너 내 이미지 경로 환경변수(`DATASET_PATH`) 또는 스토리지 어댑터 정합성 확인
> - [ ] 배포 후 `GET /inspections/images`가 유효한 이미지 식별자를 반환하는지 확인
> - *(※ 본 Day 3.5 단계에서는 실제 Cloud Storage 버킷을 생성하거나 연결하지 않음)*

---

## 7. 향후 Day 7 배포 절차 안내 (참고용)

*(※ 본 단계에서는 실행하지 마세요)*

```bash
# 1. Google Cloud 로그인 및 프로젝트 설정
gcloud auth login
gcloud config set project <PROJECT_ID>

# 2. Artifact Registry 저장소 생성
gcloud artifacts repositories create inspectagent-repo \
    --repository-format=docker \
    --location=asia-northeast3

# 3. Docker 이미지 빌드 및 푸시
docker build -t asia-northeast3-docker.pkg.dev/<PROJECT_ID>/inspectagent-repo/vision-insight:latest .
docker push asia-northeast3-docker.pkg.dev/<PROJECT_ID>/inspectagent-repo/vision-insight:latest

# 4. Cloud Run 서비스 배포
gcloud run deploy vision-insight-api \
    --image=asia-northeast3-docker.pkg.dev/<PROJECT_ID>/inspectagent-repo/vision-insight:latest \
    --platform=managed \
    --region=asia-northeast3 \
    --allow-unauthenticated \
    --cpu=1 \
    --memory=2Gi \
    --min-instances=0 \
    --max-instances=1 \
    --port=8080
```
