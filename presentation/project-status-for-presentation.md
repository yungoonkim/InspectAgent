# VisionInsight — 발표용 프로젝트 현황 및 실측 데이터 요약 (Day4 최종 완료 및 기술 개정판)

> **문서 목적:** 2026년 10월 20일 기술 발표를 준비하는 발표자 및 Q&A 대응팀이 시스템의 실제 구현 상태와 실측 데이터를 정확히 파악하여 과장이나 허위 없이 발표하도록 돕는 공식 기준 문서입니다.  
> **기준 시점:** 2026-10-17 최신 Gemini E2E 실서버 검증(T01, T03, T05, T06 4대 시나리오 전원 PASS), Day4 Step 1~5 공식 완료(`DAY4_DONE`), 전체 pytest 1089 PASS / 0 FAIL / 4 SKIP (경고 2건) 기록 완벽 반영

---

## 1. 구현 완료 / 실서버 검증 / 개발 예정 구분표

VisionInsight의 모든 기능은 아래 4단계로 명확히 구분되며, 미구현 기능을 구현 완료로 표현하지 않습니다.

| 기능 구분 | 세부 기능 및 항목 | 현재 상태 | 상세 내용 및 실측 근거 |
| :--- | :--- | :---: | :--- |
| **비전 검사 파이프라인** | 중립 이미지 매핑 (`IMG-BOTTLE-XXXX`) | **구현 완료** | MVTec 원본 파일명 및 결함 정답 라벨 완전 은닉 |
| | 고유 검사 ID 발급 (`INSP-XXXXXX`) | **구현 완료** | `product_id`와 분리된 단조 증가 순차 고유 식별자 |
| | OpenCV 기반 조도 품질 분석 | **구현 완료** | 밝기 통계(mean, std, min, max) 계산 및 4단계 품질 판정 |
| **머신러닝 (PatchCore)** | ResNet-18 Backbone 비지도 학습 | **구현 완료** | 정상 이미지 180장 Coreset 서브샘플링 (메모리 뱅크 `[9216, 384]`, 크기 24.18MB) |
| | 고정 결정 임계값 산출 | **구현 완료** | 독립 정상 검증 데이터 29장 통계 기반 **34.1442** ($\mu + 3\sigma$) |
| | CPU 단일 이미지 추론 속도 | **구현 완료** | 개발 환경(x86_64 CPU) 단일 이미지 **평균 42.53ms** (PatchCore 모델 추론 시간이며 Agent 전체/라인 처리속도 아님) |
| | 모델 결함 소견 (`result`) | **구현 완료** | 점수 $\le$ 34.1442: `OK`, 초과: `NG`, 미수행/실패: `UNKNOWN` |
| **산업용 종합 판정** | 결정론적 6대 우선순위 판정 로직 (`decision.py`) | **구현 완료** | `result`와 `image_quality_status`를 결합하여 `final_result` 도출 |
| | 재검(`REINSPECT`) 분리 정책 | **구현 완료** | 조도 이상 시 제품 결함 판정과 구분하여 재검사 상태로 분류 (Rule 2) |
| | 물리적 제어 미수행 명시 | **현황 확인** | 판정값 확정 단계이며 실제 공장 PLC, 배출기, 컨베이어 제어는 미수행 |
| **감사 추적 저장소** | JSONL 이중 영구화 엔진 (`storage.py`) | **구현 완료** | `inspections.jsonl` (검사 결과) 및 `inspection_logs.jsonl` (이벤트 로그) |
| | 감사 추적성 (Audit Trail) | **구현 완료** | 검사 생명주기 이벤트(시작, 로드, 분석, 완료, 실패) 자동 기록 |
| **Agent 도구 (Step 1)** | 4대 Python 조회 도구 (`tools.py`) | **구현 완료** | `get_inspection_result`, `get_execution_logs`, `analyze_image_quality`, `get_inspection_history` |
| | 데이터 살균 및 불투명 별칭 처리 | **구현 완료** | `TARGET-PRODUCT` 불투명 별칭화, `image_id` 제외, 민감 필드 필터링 |
| **Agent 오케스트레이션 (Step 2)** | 수동 Function Calling 바인딩 | **구현 완료** | SDK 자동 실행 차단, 서버 제어 단일 라운드 실행 및 순서 검증 |
| | 결정적 근거 검증 (Deterministic Grounding) | **구현 완료** | Evidence ID 발급, JSON Pointer, 실제 도구 실행 Trace 및 값 일치 검증 |
| | 판정 보호 정책 (Decision Guardrail) | **구현 완료** | Gemini가 최종 판정(`final_result`, `result`)을 임의 변경 불가 |
| | 조건부 조사 조기 종료 (`investigation.py`) | **구현 완료** | NORMAL 조기종료(T01/T06), 경고 조기종료(T03), 이미지 로드 실패 전용 조기종료(T05) |
| **스키마 최적화 (Step 4)** | 단순 JSON 스키마 및 토큰 카탈로그 전략 | **구현 완료** | 복잡한 스키마 호환성 문제 극복을 위해 단순 JSON 송신 후 Python에서 엄격 검증 |
| **실서버 Gemini E2E (Step 4)** | **T01 정상 시나리오 실서버 E2E** | **실서버 검증 완료**<br>(**PASS**) | `INSP-001396`: 2회 HTTP 200, 13.578초, 4,706 토큰, 관측 사실 6개 100% 통과 |
| | **T03 조도 저하 시나리오 실서버 E2E** | **실서버 검증 완료**<br>(**PASS**) | `INSP-001398` (`t03_operational_final30_1`): 3회 HTTP 200, 24.600초 (최종 JSON 18.967s), 9,873 토큰, 관측 사실 12개 100% 통과 |
| | **T05 로드 실패 ERROR 시나리오** | **실서버 검증 완료**<br>(**PASS**) | `INSP-001405` (`t05_operational_earlyexit_final30_1`): 3회 HTTP 200, 16.333초 (최종 JSON 11.063s), 11,426 토큰, 관측 사실 17개 100% 통과 (조기 종료 성공) |
| | **T06 미탐 보존 시나리오** | **실서버 검증 완료**<br>(**PASS**) | `INSP-001406` (`t06_operational_groundtruth_isolated_final30_1`): 2회 HTTP 200, 26.371초 (최종 JSON 24.118s), 7,202 토큰, 관측 사실 6개 통과, 최종 OK 판정 불변 보존 |
| **Day 4 종합 판정** | **Day 4 백엔드 Agent PoC** | **공식 완료**<br>(**DAY4_DONE**) | Step 1~5 (5/5 완료), 전체 pytest 1089 PASS / 0 FAIL / 4 SKIP (경고 2건) |
| **Day 5 계획 (준비 중)** | **[기존 Day5] 추가 조사 및 반례 평가** | **개발 예정**<br>(계획 수립) | 조건부 추가 조사, T03 이력 비교, T05 관측값 부재, T06 불확실성 검증, 무관 WARN 반례 평가 |
| | **[개정 Day5] 영상 기반 실시간 파이프라인** | **개발 예정**<br>(계획 수립) | 동영상 Live 시뮬레이터 연동, 프레임 Grab, 마우스 ROI 추출, 기존 PatchCore 연결, product_id 제외 로그 |
| **프론트엔드 (Day 6)** | React/TypeScript 웹 대시보드 | **개발 예정**<br>(디자인 기획 완료) | Live View 플레이어, Grab Image 뷰어, 마우스 드래그 ROI 선택 박스, 실시간 진단 패널 |
| **클라우드 인프라 (Day 7)** | Google Cloud Run 컨테이너 배포 | **개발 예정**<br>(배포 명세 완료) | Dockerfile, CPU 전용 휠, GCS 영구저장 연동, HTTPS 실환경 E2E 검증 |

---

## 2. 실측 데이터 및 평가 조건

### 2.1 PatchCore 평가 조건과 미탐 한계
- **데이터셋 분할 및 역할:**
  - `train/good` 209장 중 **180장**: PatchCore Coreset 메모리 뱅크 학습 (고정 시드 42)
  - `train/good` 홀드아웃 **29장**: 독립 정상 검증셋으로 임계값 산출에만 사용
  - **테스트 세트 83장**: 최종 성능 평가 전용 (정상 20장, 불량 63장)
- **성능 실측치:**
  - **Image AUROC:** **0.8286**
  - **정밀도 (Precision):** **100.0%** (근거: TP=32, FP=0 / 해당 83장 표본 기준이며 전수 보장 아님)
  - **재현율 (Recall):** **50.79%** (근거: TP=32, FN=31 / 미세 파손 및 오염 미탐 31건 발생)
  - **F1-Score:** **0.6737** | **임계값:** **34.1442** ($\mu + 3\sigma$)
  - **CPU 단일 추론 속도:** **평균 42.53ms** (PatchCore 모델 추론 시간이며 Agent 전체/라인 처리속도 아님)
- **평가 문서 제약사항 보존:**
  - 과거 209장 학습 모델 벤치마크(46.17ms)와 현재 180장 학습/29장 검증 모델(42.53ms)의 버전 차이를 혼합하지 않고 보존합니다.
  - 기존 `evaluation-results.md`의 유형별 표에서 contamination 21건 중 5건 검출인데 미검출 5건으로 오기된 산술 불일치(21-5=16)는 이번에 임의 수정하지 않고 현황 제약사항으로 보존합니다.
  - T06 시나리오(실제 파손 불량)가 이상 점수 32.27로 합격(`final_result=OK`) 처리된 것은 모델의 실제 한계이며 정직하게 보존합니다. 실제 정답 라벨은 Agent에 미제공됩니다.

### 2.2 T01 실제 Gemini API 실서버 성공 실측치 (`t01_operational_simple1`)
- **검사 대상:** `INSP-001396` (정상 병 검사 `IMG-BOTTLE-0084`)
- **FastAPI 엔드포인트:** `POST /analyze/INSP-001396` (HTTP 200 OK, `analysis_status: COMPLETED`)
- **소요 시간:** 전체 약 **13.578초** (1차 조사 2.88초 + 2차 최종 JSON 10.53초)
- **토큰 사용량:** 총 **4,706 토큰** (입력 3,115, 출력 125, Thinking 1,466)
- **사용한 도구:** `get_inspection_result` (실제 실행 시간 2.23ms, Evidence ID: `E0001`)
- **근거 검증 결과:** 6대 관측 사실(`F0001`~`F0006`) 및 JSON Pointer 일치율 100% 통과
- **최종 판정 및 권고:** 모델 OK / 서버 최종 OK 불변 유지, 권장 점검: `CONTINUE_MONITORING` (`F0003` 앵커링)

### 2.3 T03 실제 Gemini API 실서버 성공 실측치 (`t03_operational_final30_1`)
- **검사 대상:** `INSP-001398` (조도 저하 주입 검사 `IMG-BOTTLE-INJ-0001`)
- **FastAPI 엔드포인트:** `POST /analyze/INSP-001398` (HTTP 200 OK, `analysis_status: COMPLETED`)
- **소요 시간:** 전체 약 **24.600초** (도구 1: 2.43s, 도구 2: 3.05s, 최종 JSON: 18.967s)
- **토큰 사용량:** 총 **9,873 토큰** (입력 5,576, 출력 345, Thinking 3,952)
- **사용한 도구:** `get_inspection_result` (`E0001`), `analyze_image_quality` (`E0002`) (2개)
- **근거 검증 결과:** 12대 관측 사실(`F0001`~`F0012`) 및 JSON Pointer 일치율 100% 통과
- **최종 판정 및 권고:** 모델 OK / 서버 최종 REINSPECT 불변 유지, 권장 점검: `LIGHTING_EXPOSURE_CHECK`, `MANUAL_REINSPECTION`
- **주의:** 최종 JSON 요청에 30초 timeout을 선택 적용하여 18.967초에 성공. 과거 15초 요청 시 504 원인은 UNKNOWN이며 단일 회차 성공으로 반복 안정성을 보장하지 않음.

### 2.4 T05 실제 Gemini API 실서버 성공 실측치 (`t05_operational_earlyexit_final30_1`)
- **검사 대상:** `INSP-001405` (영상 로드 실패 검사 `IMG-BOTTLE-NONEXISTENT`)
- **FastAPI 엔드포인트:** `POST /analyze/INSP-001405` (HTTP 200 OK, `analysis_status: COMPLETED`)
- **소요 시간:** 전체 약 **16.333초** (도구 1 + 도구 2 순차 조사 후 최종 JSON 11.063s)
- **토큰 사용량:** 총 **11,426 토큰**
- **사용한 도구:** `get_inspection_result` (`E0001`), `get_execution_logs` (`E0002`) (2개)
- **근거 검증 결과:** 관측 사실 17개 (핵심 6 + 미산출 5 + 이벤트 6) 100% 통과
- **최종 판정 및 안전 정책:** 원본 FAILED / ERROR / INSPECTION_FAILED 보존. SKIPPED만으로 모델 장애나 카메라 수리를 오추론하지 않도록 안전 가드레일 작동.

### 2.5 T06 개발 과정 및 실서버 성공 실측치 (`t06_operational_groundtruth_isolated_final30_1`)

#### T06 10단계 개발 및 해결 과정:
1. 첫 번째 실제 E2E에서 조사 도구 실행과 Evidence 수집 성공
2. 최종 JSON 생성 요청에서 HTTP 504 발생
3. 서버 내부 원인은 UNKNOWN
4. 특정 신규 회차에만 최종 JSON 30초 적용
5. 오프라인 Mock과 회귀 검증 성공
6. 신규 READY 생성
7. 실제 재검증에서 최종 JSON HTTP 200 / 24.118초 수신
8. 전체 E2E HTTP 200 / COMPLETED / 26.371초 달성
9. JSON·Pydantic·Evidence/Pointer 검증 PASS
10. 최종 원본 OK 판정 불변성 유지

#### T06 실측치 및 알려진 한계:
- **검사 대상:** `INSP-001406` (미탐 불량 검사 `IMG-BOTTLE-0001`)
- **소요 시간:** 전체 약 **26.371초** (도구 조사 2.25초 + 최종 JSON 24.118초)
- **토큰 사용량:** 총 **7,202 토큰**
- **사용한 도구:** `get_inspection_result` (`E0001`, 1개)
- **근거 검증 결과:** 관측 사실 6개 100% 통과, anomaly_score(32.2679) 및 decision_threshold(34.1442) 보존
- **한계 명시:**
  - 30초 timeout 적용이 첫 HTTP 504의 직접 원인을 해결했다고 확정하지 않습니다 (원인 UNKNOWN).
  - 원본 ASGI 본문이 미보관되어 T06 자연어 안전성은 재구성된 선택 코드와 서버 고정 문구로 검토했다는 한계를 명시합니다.
  - 외부 평가 정답 라벨은 Agent에 일절 제공되지 않았으며, 이 성공이 PatchCore 미탐을 복구했다는 뜻이 아닙니다.

### 2.6 최신 전체 pytest 결과
- **실행 결과:** **1089 PASS / 0 FAIL / 4 SKIP / 경고 2건** (총 1093건, 소요시간: 28.08초)
- **경고 2건:** 기존 timm 및 anomalib dinov2 라이브러리 deprecation 경고
- **SKIP 4건의 명확한 사유:**
  - `test_day3_5_integration.py::test_t03_brightness_reduced_inspection` (No injected images registered)
  - `test_day3_5_step4.py::test_image_quality_warning_decision_confidence_policy` (No fault-injected images found)
  - `test_day3_5_step4_5.py::test_t03_final_verdict_quality_warning_reinspect` (T03 injected image not present)
  - `test_day3_5_step4_5.py::test_workflow_product_ng_under_quality_warning` (T03 injected image not present)
  - 4건 모두 외부 임시 디렉터리에 주입 이미지가 등록되지 않아 건너뛴 것이며, Day4 Agent 보안/근거/판정보호 테스트의 SKIP은 0건입니다.
