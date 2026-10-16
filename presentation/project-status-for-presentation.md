# VisionInsight — 발표용 프로젝트 현황 및 실측 데이터 요약 (14장 발표본 기술 개정판)

> **문서 목적:** 2026년 10월 20일 기술 발표를 준비하는 발표자 및 Q&A 대응팀이 시스템의 실제 구현 상태와 실측 데이터를 정확히 파악하여 과장이나 허위 없이 발표하도록 돕는 공식 기준 문서입니다.  
> **기준 시점:** 2026-10-16 최신 Gemini E2E 실서버 검증(T01 PASS, T03 PASS), T05 ERROR 조기 종료 정책 구현 및 전체 pytest 984개 PASS 기록 완벽 반영

---

## 1. 구현 완료 / Mock 검증 / 실서버 검증 / 개발 예정 구분표

VisionInsight의 모든 기능은 아래 4단계로 명확히 구분되며, 미구현 기능을 구현 완료로 표현하지 않습니다.

| 기능 구분 | 세부 기능 및 항목 | 현재 상태 | 상세 내용 및 실측 근거 |
| :--- | :--- | :---: | :--- |
| **비전 검사 파이프라인** | 중립 이미지 매핑 (`IMG-BOTTLE-XXXX`) | **구현 완료** | MVTec 원본 파일명 및 결함 정답 라벨 완전 은닉 |
| | 고유 검사 ID 발급 (`INSP-XXXXXX`) | **구현 완료** | `product_id`와 분리된 단조 증가 순차 고유 식별자 |
| | OpenCV 기반 조도 품질 분석 | **구현 완료** | 밝기 통계(mean, std, min, max) 계산 및 4단계 품질 판정 |
| **머신러닝 (PatchCore)** | ResNet-18 Backbone 비지도 학습 | **구현 완료** | 정상 이미지 180장 Coreset 서브샘플링 (메모리 뱅크 `[9216, 384]`, 크기 24.18MB) |
| | 고정 결정 임계값 산출 | **구현 완료** | 독립 정상 검증 데이터 29장 통계 기반 **34.1442** ($\mu + 3\sigma$) |
| | CPU 단일 이미지 추론 속도 | **구현 완료** | 개발 환경(x86_64 CPU) 단일 이미지 **평균 42.53ms** (T01: 41.34ms, T03: 42.72ms) |
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
| | 판정 보호 정책 (Decision Guardrail) | **구현 완료** | Gemini가 최종 판정(`final_result`, `inspection_result`)을 임의 변경 불가 |
| | 경고 검사 조건부 조사 종료 (`investigation.py`) | **운영 통합 완료**<br>(실서버 검증 완료) | 조도 경고 시 결과+품질 지표 확보 후 즉시 최종 단계 직행 (T03 실서버 성공) |
| **스키마 최적화 (Step 4)** | 단순 JSON 스키마 및 토큰 카탈로그 전략 | **구현 완료** | 복잡한 스키마 호환성 문제 극복을 위해 단순 JSON 송신 후 Python에서 엄격 검증 |
| **실서버 Gemini E2E (Step 4)** | **T01 정상 시나리오 실서버 E2E 분석** | **실서버 검증 완료**<br>(**PASS**) | `INSP-001396` 실서버 성공: 2회 HTTP 200, 13.578초, 4,706 토큰, 관측 사실 6개 100% 통과 |
| | **T03 조도 저하 시나리오 실서버 E2E 분석** | **실서버 검증 완료**<br>(**PASS**) | `INSP-001398` 실서버 성공 (`t03_operational_final30_1`):<br>• 도구 1(`get_inspection_result`): HTTP 200, 2.43s (`E0001`)<br>• 도구 2(`analyze_image_quality`): HTTP 200, 3.05s (`E0002`)<br>• 최종 단순 JSON 보고서 생성: **HTTP 200, 18.967s (30초 timeout 선택 적용)**<br>• 전체 E2E 분석 시간: **24.600초**, 총 토큰: **9,873토큰**<br>• 관측 사실: **12개 (F0001~F0012) 100% 결정적 검증 통과**<br>• 판정 불변 보존: 모델 OK, 최종 판정 REINSPECT 보존<br>• 주의: 이전 15초 요청 시 14.15초 소요 504 원인은 **UNKNOWN**이며, 단일 회차 성공으로 향후 안정성을 보장하지 않음 |
| | **T05 영상 로드 실패 ERROR 시나리오** | **조기 종료 Mock PASS**<br>(**실서버 1회 FAIL / 재검증 대기**) | • 실서버 검증 기록: `INSP-001405` (`t05_operational_final30_1`) 1회 FAIL (도구 2개 성공, 이벤트 2건 및 17개 근거 확보 후 3차 후속 조사에서 HTTP 504 발생, 서버 내부 원인 UNKNOWN)<br>• 조기 종료 정책 구현: 필수 도구·로그·17개 근거 확보 후 최종 JSON 즉시 전환 (Mock 조사 2회+최종 1회 성공)<br>• 계측기 정정: WARNING 오분류 수정, `IMAGE_LOAD_FAILURE` 정상 인식<br>• 현황: **오프라인 Mock PASS / 실서버 개선 후 재검증 대기** |
| | **T06 미탐 평가사례 시나리오** | **평가사례 보존**<br>(**실서버 NOT TESTED**) | • 이상 점수 32.27로 합격 처리된 미탐 사례 보존 (정답 라벨은 Agent에 미제공)<br>• **실제 실서버 Gemini E2E: NOT TESTED** |
| **프론트엔드 (Day 6)** | React/TypeScript 웹 대시보드 | **개발 예정**<br>(디자인 기획 완료) | `design/stitch/`에 DesignA (Dark), DesignB (Light) 및 연동 가이드 완료.<br>실제 React 컴포넌트 코드는 미구현 |
| **영상 고도화** | 컨베이어 Live View 스트리밍 / 프레임 Grab / 마우스 ROI | **개발 예정**<br>(로드맵 수립) | Day 4 완료 후 Day 6과 연계하여 구축 예정 (기존 모델 및 임계값 34.1442 재사용) |
| **클라우드 인프라 (Day 7)** | Google Cloud Run 컨테이너 배포 | **개발 예정**<br>(배포 명세 완료) | Dockerfile, CPU 전용 휠, 배포 가이드 완료.<br>실제 클라우드 배포 및 콜드 스타트 실측은 미실시 |

---

## 2. 실측 데이터 및 평가 조건

### 2.1 PatchCore 평가 조건과 미탐 한계
- **데이터셋 분할 및 역할:**
  - `train/good` 209장 중 **180장**: PatchCore Coreset 메모리 뱅크 학습 (고정 시드 42)
  - `train/good` 홀드아웃 **29장**: 독립 정상 검증셋으로 임계값 산출에만 사용
  - **테스트 세트 83장**: 최종 성능 평가 전용 (정상 20장, 불량 63장)
- **성능 실측치:**
  - **Image AUROC:** **0.8286**
  - **정밀도 (Precision):** **100.0%** (근거: TP=32, FP=0 / 정상 표본: TN=20, FP=0)
  - **재현율 (Recall):** **50.79%** (근거: TP=32, FN=31 / 미탐 31건 발생)
  - **F1-Score:** **0.6737** | **임계값:** **34.1442** ($\mu + 3\sigma$)
- T06 시나리오(실제 파손 불량)가 이상 점수 32.27로 합격(`final_result=OK`) 처리된 것은 모델의 실제 한계이며, 이를 은폐하지 않고 정직하게 보존합니다. 중요하게도 실제 정답 라벨은 Gemini Agent에 제공되지 않습니다.

### 2.2 T01 실제 Gemini API 실서버 성공 실측치 (`t01_operational_simple1`)
- **검사 대상:** `INSP-001396` (정상 병 검사 `IMG-BOTTLE-0084`)
- **FastAPI 엔드포인트:** `POST /analyze/INSP-001396` (HTTP 200 OK, `analysis_status: COMPLETED`)
- **소요 시간:** 전체 약 **13.578초** (1차 Function Calling 2.88초 + 2차 단순 JSON 생성 10.53초)
- **토큰 사용량:** 총 **4,706 토큰** (입력 3,115, 출력 125, Thinking 1,466)
- **사용한 도구:** `get_inspection_result` (실제 실행 시간 2.23ms, Evidence ID: `E0001`)
- **근거 검증 결과:** 6대 관측 사실(`F0001`~`F0006`) 및 JSON Pointer 일치율 100% 통과
- **최종 AI 요약 내용:** *"기록된 모델 판정과 종합 판정은 OK입니다. 실제 무결점 제품을 보증하지 않습니다."*
- **권장 점검:** `check_code: CONTINUE_MONITORING` (`evidence_refs`: `["F0003"]`)

### 2.3 T03 실제 Gemini API 실서버 성공 실측치 (`t03_operational_final30_1`)
- **검사 대상:** `INSP-001398` (조도 저하 주입 검사 `IMG-BOTTLE-INJ-0001`)
- **FastAPI 엔드포인트:** `POST /analyze/INSP-001398` (HTTP 200 OK, `analysis_status: COMPLETED`)
- **소요 시간:** 전체 약 **24.600초** (도구 1: 2.43s, 도구 2: 3.05s, 최종 JSON: 18.967s)
- **토큰 사용량:** 총 **9,873 토큰** (입력 5,576, 출력 345, Thinking 3,952)
- **사용한 도구:** `get_inspection_result` (`E0001`), `analyze_image_quality` (`E0002`) (2개)
- **근거 검증 결과:** 12대 관측 사실(`F0001`~`F0012`) 및 JSON Pointer 일치율 100% 통과
- **최종 AI 요약 내용:** *"기록된 종합 판정은 REINSPECT입니다. 제품 불량 확정과 구분하여 재검사가 필요합니다."*
- **권장 점검:** `LIGHTING_EXPOSURE_CHECK` (`["F0004", "F0007"]`), `MANUAL_REINSPECTION` (`["F0003"]`)
- **안전 한계:** 4대 한계 필수 고지 (물리적 원인 불명, 모델 비보증, 기준치 미기록, 비보정 신뢰도)

### 2.4 전체 pytest 결과
- **현재 확인된 최신 전체 pytest:** **984 passed, 3 warnings** (오프라인 격리 환경)
  - 전체 pytest: **984 PASS (경고 3건)**
  - T05 이미지 로드 실패 전용 조기 종료 정책 Mock 검증 PASS
  - MockTransport timeout 전파 검증 PASS
  - 개선 이후 실제 Gemini API 재검증은 아직 수행하지 않음 (실서버 재검증 대기)
