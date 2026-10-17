# VisionInsight — Day4 최종 완료 및 Day5~7 개발 현황 요약 보고서

> **문서 식별자:** `docs/day4-completion-and-day5-roadmap-summary.md`  
> **작성일:** 2026-10-17  
> **문서 목적:** Day4 백엔드 Agent PoC의 공식 완료 상태와 대표 실측 데이터, 핵심 기술 난제 해결 과정(T06 이력 포함), 시스템 아키텍처 역할 분리, 그리고 향후 Day5~Day7 개발 계획을 독립적으로 정리한 기술 요약 보고서입니다.  
> **원칙 준수:** 실제 구현하지 않은 기능은 완료로 표시하지 않으며, Day5~Day7은 실증 증거 확보 전까지 '계획/준비 중'으로 엄격히 관리합니다.

---

## 1. Day4 마일스톤 공식 완료 현황

VisionInsight 프로젝트의 **Day 4 백엔드 Agent PoC 마일스톤(Step 1~5)**이 공식 완료되었습니다 (`DAY4_DONE`).

### 1.1 최신 회귀 테스트 결과
- **테스트 스위트:** 전체 pytest 1,093건 전수 검증
- **검증 결과:** **1089 PASS / 0 FAIL / 4 SKIP (경고 2건)** (소요 시간: 28.08초)
- **경고 사유:** 기존 timm 및 anomalib 라이브러리의 deprecation 경고 2건
- **SKIP 4건의 명확한 기술 사유:**
  - `test_day3_5_integration.py::test_t03_brightness_reduced_inspection`
  - `test_day3_5_step4.py::test_image_quality_warning_decision_confidence_policy`
  - `test_day3_5_step4_5.py::test_t03_final_verdict_quality_warning_reinspect`
  - `test_day3_5_step4_5.py::test_workflow_product_ng_under_quality_warning`
  - 위 4건은 테스트 실행 시 외부 격리 임시 디렉터리에 저조도 주입 이미지가 등록되지 않아 건너뛴 Day3.5 이미지 통합 테스트입니다.
  - Day4 Agent의 필수 보안, ID 범위, 판정 보호, Evidence/Pointer, 정답 격리 테스트에는 SKIP이 0건입니다.

### 1.2 대표 실제 Gemini E2E 실서버 검증 결과

| 시나리오 구분 | 대상 검사 ID | 실제 검증 회차 ID | 서버 최종 판정 | FastAPI / 분석 상태 | 전체 소요 시간 | 최종 Fact / Evidence |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **T01 정상 검사** | `INSP-001396` | `t01_operational_simple1` | **`OK`** (Rule 5) | HTTP 200 / `COMPLETED` | **13.578초** | **6개** / 1개 (PASS) |
| **T03 품질 경고** | `INSP-001398` | `t03_operational_final30_1` | **`REINSPECT`** (Rule 2) | HTTP 200 / `COMPLETED` | **24.600초** | **12개** / 2개 (PASS) |
| **T05 로드 실패** | `INSP-001405` | `t05_operational_earlyexit_final30_1` | **`ERROR`** (Rule 1) | HTTP 200 / `COMPLETED` | **16.333초** | **17개** / 2개 (PASS) |
| **T06 저장 OK (미탐)** | `INSP-001406` | `t06_operational_groundtruth_isolated_final30_1` | **`OK`** (판정 보존) | HTTP 200 / `COMPLETED` | **26.371초** | **6개** / 1개 (PASS) |

> **감사 확인 사항:**  
> - 4개 시나리오 각각 최소 1개 이상의 실제 실서버 성공 회차를 확인했습니다.  
> - 각 성공 회차는 단일 분석 실행(재시도 0회)으로 완료되었으며, 최종 JSON, Pydantic, Evidence ID, JSON Pointer 및 서버 최종 판정 불변성 검증을 100% 통과했습니다.  
> - 단, 단일 회차 성공이 반복 실행 안정성이나 상용 운영 신뢰성(SLA)을 보장하는 것은 아닙니다.

---

## 2. 시스템 아키텍처 및 역할 분리

VisionInsight는 안전성과 설명력을 동시 달성하기 위해 비전 처리, 규칙 판정, AI 에이전트의 책임을 엄격히 분리합니다.

```
[클라이언트 검사 요청] ➔ POST /inspections
  │
  ├─ 1. OpenCV 영상 품질 분석 (밝기 mean, std, min, max 계산 ➔ NORMAL / WARNING / ERROR)
  ├─ 2. CPU PatchCore 이상 탐지 (ResNet-18 특징 추출 ➔ anomaly_score 계산 ➔ result 도출)
  ├─ 3. 백엔드 결정론적 종합 판정 (6대 우선순위 규칙 ➔ final_result 확정, REINSPECT 분리)
  └─ 4. FastAPI 저장소 영구화 (inspections.jsonl 및 logs.jsonl 이중 감사 로그 기록)
       │
[사후 진단 요청] ➔ POST /analyze/{inspection_id}
  │
  ├─ 5. Gemini Function Calling (도구 제안 ➔ 서버 인자 검증 ➔ 4대 Python 도구 실행)
  ├─ 6. Evidence Store & Fact Catalog (E0001 영수증 발급, K0001 토큰 카탈로그 구축)
  ├─ 7. Gemini 단순 JSON 보고서 생성 (토큰 선택 방식 ➔ 스키마 호환성 확보)
  ├─ 8. Python 엄격 검증 파이프라인 (DiagnosisDraft 변환 ➔ Pydantic ➔ JSON Pointer 1:1 대조)
  └─ 9. 서버 판정 보호 및 최종 응답 (원본 final_result 불변 유지 ➔ 구조화 진단 보고서 반환)
```

### 각 컴포넌트의 명확한 역할 정의:
1. **OpenCV 이미지 품질 분석:** 조도 저하, 과노출, 이미지 파손을 독립 측정하여 품질 상태(`image_quality_status`)를 결정합니다.
2. **CPU PatchCore 이상 탐지:** 정상 이미지 180장으로 비지도 학습된 Coreset 메모리 뱅크를 통해 제품 외관의 결함 점수를 CPU 평균 42.53ms로 추론합니다 (`result`).
3. **백엔드의 결정적 최종 판정 (`backend/decision.py`):** 모델 소견과 영상 품질을 결합하여 `OK`, `NG`, `REINSPECT`, `ERROR`의 최종 판정을 규칙에 따라 확정합니다. 조도 이상 시 불량으로 오판하지 않고 `REINSPECT`로 분류합니다.
4. **FastAPI 저장 및 조회:** 검사 결과와 라이프사이클 이벤트를 스레드 세이프 JSONL로 영구화합니다.
5. **Gemini Function Calling:** AI는 임의의 코드를 실행하지 않고, 서버에 정의된 4대 조회 도구와 인자를 제안하는 역할만 수행합니다.
6. **Python 도구 실행:** FastAPI `AgentService`가 호출 인자를 검증한 뒤, 서버 환경에서 허용된 도구만 안전하게 실행합니다.
7. **Evidence Store와 Fact Catalog:** 도구 실행 시 서버가 고유 `Evidence ID`(`E0001`, `E0002`)를 발급하고, 수집된 데이터를 토큰 카탈로그(`K0001~`)로 정형화합니다.
8. **Pydantic 및 JSON Pointer 검증:** Gemini가 작성한 보고서의 모든 관측 사실을 서버 메모리의 실제 도구 결과와 1:1 결정적으로 대조합니다. 불일치 시 HTTP 502로 거부합니다.
9. **최종 구조화 진단 보고서:** 관측 사실(`observed_facts`), 가능한 원인(`possible_causes`), 점검 권고(`recommended_checks`), 안전 한계(`limitations`)를 명확히 구분하여 운영자에게 제공합니다.
10. **판정 불변 가드레일:** Gemini Agent는 사후 진단 보조 역할만 수행하며, 서버가 확정한 `final_result`를 임의로 번복할 수 없습니다. 실제 공장의 물리적 PLC, 컨베이어, 배출기 제어는 수행하지 않습니다.

---

## 3. T06 개발 과정 및 실서버 극복 이력

T06 시나리오(실제 파손 불량품 투입, 현재 모델의 이상 점수 32.27로 합격 처리된 미탐 사례)에 대해 실제 다음과 같은 10단계 개발 및 검증 과정이 있었습니다.

### 3.1 T06 10단계 개발 과정
1. **첫 번째 실제 E2E 시도:** 조사 도구(`get_inspection_result`) 실행과 Evidence 수집에는 성공함.
2. **최종 JSON 요청 504 발생:** 최종 진단 보고서 생성 요청에서 HTTP 504 타임아웃 발생.
3. **내부 원인 불명:** Google Gemini 서버 내부의 정확한 지연 원인은 **UNKNOWN**으로 확인.
4. **선택적 30초 타임아웃 설계:** 모든 요청이 아닌, 승인된 특정 신규 회차에 한해 최종 JSON 요청 상한을 30초로 분리 적용.
5. **오프라인 Mock 및 회귀 검증:** MockTransport를 통한 30초 타임아웃 전달 및 회귀 테스트 통과.
6. **신규 READY 생성:** 실제 E2E 재검증을 위한 독립 검사 인스턴스 준비.
7. **실서버 최종 JSON 수락:** 실제 재검증에서 최종 JSON 생성이 **HTTP 200 / 24.118초**에 성공 수신됨.
8. **전체 E2E 완전 성공:** 전체 분석 소요 시간 **26.371초 / HTTP 200 / `COMPLETED`** 달성.
9. **근거 및 스키마 검증 통과:** JSON 파싱, Pydantic, Fact 6개, Evidence ID, JSON Pointer 검증 전원 PASS.
10. **서버 원본 판정 불변 유지:** 정답 라벨이 은닉된 상태에서 모델의 OK 판정과 서버 최종 OK 판정이 번복 없이 보존됨.

### 3.2 T06 검증의 기술적 한계 명시
- **타임아웃 한계:** 30초 타임아웃 적용 후 24.118초에 성공했으나, 이것이 첫 번째 HTTP 504의 직접 원인을 해결했다고 확정할 수 없습니다. (서버 내부 원인 UNKNOWN)
- **자연어 검토 한계:** 실제 통신 당시 원본 ASGI 본문 전체가 별도로 보관되지 않아, T06의 자연어 안전성은 사후에 검증된 선택 코드와 변경되지 않은 서버 고정 문구를 재구성하여 검토했습니다.
- **미탐 복구 아님:** 외부 평가 정답 라벨은 Agent에 일절 제공되지 않았으며, 이 성공이 PatchCore의 미탐 결함을 사후에 찾아냈거나 모델 성능을 개선했다는 뜻이 아닙니다.

---

## 4. 머신러닝 모델 성능 및 엔지니어링 한계

### 4.1 공식 평가 지표 (83장 독립 테스트셋)
- **Image AUROC:** **0.8286**
- **정밀도 (Precision):** **100.0%** (1.0000, TP=32, FP=0)
- **재현율 (Recall):** **50.79%** (0.5079, TP=32, FN=31)
- **F1-Score:** **0.6737** | **임계값:** **34.1442** ($\mu + 3\sigma$)
- **CPU 단일 추론 속도:** **평균 42.53ms** (개발 환경 x86_64 CPU 실측치)

### 4.2 솔직한 엔지니어링 한계 고찰
1. **표본 한정 정밀도:** Precision 100%는 주어진 83장 테스트 표본에서의 수치이며, 모든 실제 산업 공정에서 위양성(FP)이 0%임을 보증하지 않습니다.
2. **미탐(FN) 31건 한계:** 실제 불량 63건 중 31건(미세 파손 및 오염)을 검출하지 못했습니다 (Recall 50.79%). 모델의 OK 판정이 실제 무결점 제품을 보증하지 않습니다.
3. **추론 속도와 Agent 지연시간의 분리:** PatchCore의 42.53ms는 순수 딥러닝 추론 시간이며, Gemini Agent 사후 진단 시간(13.58초~26.37초)이나 전체 라인 처리 속도가 아닙니다.
4. **평가 문서 제약사항 보존:**
   - 과거 209장 학습 모델 벤치마크(46.17ms)와 현재 180장/29장 모델(42.53ms)의 버전 차이를 혼합하지 않고 보존합니다.
   - 기존 `evaluation-results.md`의 유형별 표에서 contamination 21건 중 5건 검출인데 미검출 5건으로 오기된 산술 불일치(21-5=16)는 이번에 임의 수정하지 않고 현황 제약으로 보존합니다.
5. **물리적 제어 미연동:** 실제 공장 PLC, 컨베이어, 불량품 공압 배출기 제어는 현재 구현되어 있지 않으며 사후 진단 보조 프로토타입으로 운영됩니다.

---

## 5. Day 5 ~ Day 7 개발 계획 및 진행 로드맵

현재 Day 4 백엔드 Agent PoC는 완료되었으며, **Day 5 이후는 계획 수립 및 준비 중 상태**입니다. 구현 및 검증 증거가 확보되기 전까지 완료로 표시하지 않습니다.

### 5.1 Day 5: 심층 진단 및 실시간 영상 파이프라인 (준비 중 / 대기)

#### [기존 Day5 범위] 상황별 추가 조사 및 반례 평가:
- 조건부 심층 추가 조사 루프 구현
- T03 과거 이력 비교 트렌드 분석
- T05 관측값 부재 상태의 안전한 가설 수립 검증
- T06 불확실성 환경에서의 보수적 안전 고지 검증
- 무관한 WARN 이벤트 및 근거 부족 입력에 대한 반례 평가

#### [개정 Day5 범위] 영상 기반 실시간 검사 파이프라인:
- MVTec Bottle 컨베이어 주행 동영상 파일 로드 및 Live 시뮬레이터 입력 연동
- 실시간 영상 프레임 Grab 기능 구현
- 작업자 마우스 ROI(관심영역) 바운딩 박스 추출 모듈
- ROI 크롭 이미지 대상 기존 PatchCore 체크포인트 및 임계값(`34.1442`) 추론 연결
- 신규 실행 로그에서 불필요한 `product_id` 제외
- 조명 이상 또는 검사 실패 감지 시 조건부 Gemini 자율 재진단 워크플로우 연결

### 5.2 Day 6: React 웹 관제 대시보드 (개발 예정)
- React, TypeScript, Vite 기반 고성능 관제 프론트엔드 구축
- 컨베이어 동영상 Live View 스트리밍 플레이어 컴포넌트
- 실시간 프레임 Grab Image 뷰어 및 마우스 드래그 ROI 선택 박스
- 검사 결과 실시간 표출 (OK/NG/REINSPECT/ERROR 뱃지)
- Gemini 사후 진단 보고서 표출 패널 (관측 사실, 추천 조치, 안전 한계)

### 5.3 Day 7: Cloud Run 배포 및 최종 통합 검증 (개발 예정)
- Google Cloud Run Serverless CPU 컨테이너 배포
- JSONL 로컬 저장을 Google Cloud Storage(GCS) 영구 저장소 계층으로 전환
- Cloud Run HTTPS 엔드포인트 기반 실제 Gemini E2E 동작 및 성능 검증
- 시스템 최종 기술 문서화 및 발표 시연 리허설
