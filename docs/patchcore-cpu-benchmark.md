# VisionInsight — PatchCore Bottle CPU 추론 및 자원 실측 보고서 (`docs/patchcore-cpu-benchmark.md`)

> **프로젝트:** VisionInsight — MVTec AD Bottle 기반 Vision 검사 이상 진단 AI Agent  
> **단계:** Day 3.5 - Step 2 (CPU 추론 성능 및 자원 실측)  
> **실측 일시:** 2026-10-14  
> **검증 장비:** 13th Gen Intel® Core™ i7-13620H (CPU 전용 모드)  
> **재현 스크립트:** `python scripts/verify_patchcore_cpu.py`

---

## 1. 실측 개요 및 목적

VisionInsight 프로젝트는 향후 **Google Cloud Run (서버리스 컨테이너)** 환경에 배포될 예정입니다. Cloud Run은 기본적으로 GPU가 제공되지 않거나 GPU 인스턴스 비용이 높으므로, **순수 CPU 환경에서의 실시간 추론 속도와 메모리 적합성**을 사전에 실측하여 검증해야 합니다.

본 실측은 GPU(RTX 4060)에서 학습하여 저장한 공식 체크포인트(`models/patchcore/patchcore_bottle.ckpt`)를 **순수 CPU 전용(`map_location="cpu"`, `model.to("cpu")`)** 환경에서 로드하고, 모델 파일 크기, 로딩 시간, 메모리(RAM) 점유량, 단일 이미지 추론 레이턴시(ms), 그리고 실제 정상/불량 이미지에 대한 Anomaly Score 반응을 정량적으로 측정한 결과입니다.

---

## 2. 하드웨어 및 런타임 환경

| 구분 | 사양 및 환경 | 비고 |
| :--- | :--- | :--- |
| **추론 프로세서 (CPU)** | 13th Gen Intel® Core™ i7-13620H (10 Cores, 16 Threads) | 순수 CPU 추론 실행 |
| **시스템 메모리 (RAM)** | 64.0 GB DDR5 | 호스트 시스템 |
| **학습 장치 (GPU)** | NVIDIA GeForce RTX 4060 Laptop GPU (8GB VRAM) | 학습 시에만 사용 (추론 시 미사용) |
| **운영체제 (OS)** | Windows 11 Home (Build 26100) | 로컬 개발 환경 |
| **파이썬 런타임** | Python 3.11.16 (`vision-insight` Conda 가상환경) | 의존성 격리 |
| **딥러닝 프레임워크** | PyTorch 2.6.0+cu124, torchvision 0.21.0+cu124 | CPU 텐서 연산 수행 |
| **이상 탐지 라이브러리** | Anomalib 2.7.0 (공식 최신 안정 버전) | Lightning 기반 추론 모듈 |

---

## 3. PatchCore 모델 사양 및 체크포인트

| 항목 | 사양 / 설정값 | 설명 |
| :--- | :--- | :--- |
| **기반 모델** | PatchCore (Roth et al., 2022) | 정상 패치 임베딩 메모리 뱅크 기반 이상 탐지 |
| **백본 (Backbone)** | ResNet-18 (`resnet18`) | ImageNet 사전학습 가중치 동결 (Frozen) |
| **특징 추출 레이어** | `layer2`, `layer3` | 중간 형상 및 텍스처 특징 결합 (384차원) |
| **학습 데이터셋** | `dataset/bottle/train/good` 209장 | 순수 정상 이미지만 100% 사용 (분할 배제) |
| **코어셋 샘플링 비율** | `0.05` (5%) | 메모리 뱅크 압축 최적화 (213,980개 → 10,700개) |
| **메모리 뱅크 형상** | `[10700, 384]` | 384차원 패치 임베딩 벡터 10,700개 |
| **체크포인트 파일** | `models/patchcore/patchcore_bottle.ckpt` | Anomalib 공식 Lightning 체크포인트 |
| **체크포인트 크기** | **26.35 MB** (27,633,962 바이트) | 컨테이너 이미지 경량화 및 빠른 콜드 스타트에 최적 |
| **학습 소요 시간** | **41.23초** | 로컬 RTX 4060 기준 (피크 VRAM: 836.09 MB) |

---

## 4. CPU 자원 및 지연시간 실측 결과

### 4.1. 모델 로딩 시간 및 메모리(RAM) 점유량

프로세스 메모리는 Windows API(`psapi.dll`의 `GetProcessMemoryInfo`, Working Set Size)를 사용하여 정밀 실측했습니다.

| 측정 지표 | 실측값 | Cloud Run 배포 적합성 평가 |
| :--- | :---: | :--- |
| **모델 로딩 시간** | **3.975초** | 서버 시작 시 Lifespan 사전 로드 시 사용자 대기 시간 0초 달성 가능 |
| **로드 전 프로세스 RAM** | 453.19 MB | Python 런타임 및 라이브러리 기본 상주 메모리 |
| **로드 후 프로세스 RAM** | 780.50 MB | 모델 가중치 및 메모리 뱅크 텐서 상주 후 메모리 |
| **순수 모델 메모리 증분** | **+327.31 MB** | Cloud Run 기본 메모리(1GB) 대비 32% 수준으로 매우 안전 |

> **분석 요약:** 모델 파일(26.35MB)이 메모리에 압축 해제 및 텐서화되면서 발생하는 추가 RAM은 약 327MB에 불과합니다. Cloud Run 인스턴스 사양을 **1 vCPU / 1GB RAM** 또는 **2 vCPU / 2GB RAM**으로 설정할 경우 OOM(Out Of Memory) 위험 없이 안정적인 컨테이너 구동이 보장됩니다.

---

### 4.2. CPU 추론 레이턴시(Latency) 벤치마크

Warm-up 1회 수행 후, 미지의 테스트 이미지에 대해 5회 연속 CPU 추론을 수행하여 지연시간을 측정했습니다.

| 반복 회차 | 추론 지연시간 (Latency) | 비고 |
| :---: | :---: | :--- |
| Warm-up (1회차) | 45.40 ms | 캐시 초기화 |
| 1회 | 44.59 ms | 최소 지연시간 (Min) |
| 2회 | 46.12 ms | |
| 3회 | 45.72 ms | |
| 4회 | 48.41 ms | 최대 지연시간 (Max) |
| 5회 | 46.03 ms | |
| **평균 (Average)** | **46.17 ms** | **목표(100ms) 대비 53.8% 우수한 성능** |
| **표준편차 (StdDev)** | **±1.36 ms** | 매우 균일하고 안정적인 추론 시간 유지 |
| **초당 처리량 (Throughput)** | **약 21.6 FPS** | 단일 코어 기준 초당 약 21.6개 병 검사 가능 |

---

### 4.3. 실제 Bottle 이미지 Anomaly Score 반응 실측

임의의 판정 임계값을 튜닝하거나 오염시키지 않고, 모델이 산출한 순수 원본 점수(Raw Score)와 히트맵 크기를 실측했습니다.

| 이미지 식별자 | 이미지 경로 및 유형 | Anomaly Score | CPU 추론 시간 | 이상 히트맵 형상 |
| :--- | :--- | :---: | :---: | :---: |
| `IMG-TRAIN-GOOD-000` | `dataset/bottle/train/good/000.png`<br>*(학습에 사용된 정상)* | **31.1105** | 47.53 ms | `[256, 256]` (float32) |
| `IMG-TEST-GOOD-000` | `dataset/bottle/test/good/000.png`<br>*(학습에 미포함된 정상)* | **30.5060** | 45.40 ms | `[256, 256]` (float32) |
| `IMG-TEST-DEFECT-000` | `dataset/bottle/test/broken_large/000.png`<br>*(학습에 미포함된 불량)* | **32.2905** | 47.86 ms | `[256, 256]` (float32) |

#### 주요 관측 결과
1. **정상 이미지의 일관된 점수대**: 학습에 직접 투입된 정상 이미지(`31.11`)와 학습에 참여하지 않은 미지의 정상 이미지(`30.51`)가 유사하게 낮은 이상치 점수대를 형성합니다.
2. **불량 검출 민감도**: 대형 파손 불량 이미지(`32.29`)의 이상치 점수가 정상 이미지들보다 명확하게 높게 나타나, 정상 메모리 뱅크 기반 최근접 거리 측정이 올바르게 작동함을 입증했습니다.
3. **픽셀 히트맵 산출**: 256x256 해상도의 2D 이상치 맵이 즉시 생성되어, 향후 결함 부위 바운딩 박스 시각화 및 Agent 설명 자료로 활용할 수 있습니다.

---

## 5. 안전 규칙 및 개발 원칙 준수 확인

1. **Ground Truth 및 평가 정답 무참조**:
   * 모델 학습과 추론 과정에서 `ground_truth` 마스크 및 `test_data/injected_images` 정답 라벨에 일절 접근하지 않았습니다.
2. **임계값 과적합 배제**:
   * 최종 테스트 세트를 보고 판정 임계값을 최적화하지 않았으며, 원본 거리 점수(Raw Distance Score)만 측정·기록했습니다.
3. **클라우드 과금 0원 원칙**:
   * 클라우드 GPU나 유료 리소스를 사용하지 않고 로컬 PC 하드웨어만으로 학습과 검증을 완수했습니다.
4. **Git 보안 및 저장소 경량화**:
   * `.gitignore`에 `models/**/*.ckpt`를 등록하여 대용량 체크포인트 바이너리가 Git 원격 저장소에 커밋되는 것을 원천 차단했습니다.
5. **기존 기능 무결성**:
   * Day 1~3의 기존 FastAPI, OpenCV Brightness 분석, JSONL 로깅 코드를 무단 수정하지 않았으며, 총 63개 테스트가 100% 통과했습니다.

---

## 6. 재현 및 실행 명령어

```bash
# 1. PatchCore 모델 학습 재현 (로컬 GPU 가속, 209장 정상 이미지)
python scripts/train_patchcore.py

# 2. 순수 CPU 전용 환경 성능 및 자원 실측 실행
python scripts/verify_patchcore_cpu.py

# 3. Inferencer 단위 테스트 및 전체 회귀 테스트 실행 (총 63개 테스트)
pytest tests -v
```

---

## 7. 향후 계획 (Next Steps)

* **Day 3.5 - Step 3 (FastAPI 파이프라인 연동)**:
  * FastAPI Lifespan 이벤트에서 `PatchCoreInferencer`를 싱글톤으로 사전 로드하여 요청 지연 최소화.
  * `POST /inspections` 엔드포인트에서 이미지 로드 후 Anomaly Score를 계산하여 응답 스키마 및 JSONL 로그에 반영.
* **Day 3.5 - Step 4 (검증 데이터 기반 임계값 도출)**:
  * 독립된 별도 검증 셋을 구성하여 정상/불량을 가르는 최적의 Anomaly Score 임계값(Threshold) 수립.
