# VisionInsight 구현 현황 보고서 (`docs/implementation-status.md`)

> **프로젝트:** VisionInsight — MVTec AD Bottle 기반 Vision 검사 이상 진단 AI Agent  
> **진행 단계:** Day 4 Step 1~5 완료 (`DAY4_DONE`, 백엔드 Agent PoC 범위)
>
> **최종 검증일:** 2026-10-17
> **최신 근거:** [Day4 Step5 최종 보고서](day4-step5-final-verification.md). 이번 전체 1089 PASS / 0 FAIL / 4 SKIP / 경고 2건, 대표 실제 Gemini E2E 4종 PASS 이력 확인. 배포 완료가 아님.

---

## 1. 개요 및 마일스톤 현황

VisionInsight 프로젝트의 Day 1~Day 3.5 이후 **Day4 Agent 구현·대표 실제 E2E 및 최종 오프라인 통합 검증**을 완료했습니다. 새 Gemini 요청 없이 기존 성공/실패 기록을 감사했습니다.

아래 2~6절은 2026-10-15 인수인계 당시의 구현·미완료·테스트 기록을 보존한 것입니다. 당시의 536 PASS 및 잔여 작업 목록을 현재 상태로 해석하지 마세요. 최신 완료 판정·미검증 범위·다음 단계는 위 Step5 보고서가 기준입니다.

| 마일스톤 | 목표 및 범위 | 상태 | 검증 결과 |
| :--- | :--- | :---: | :--- |
| **Day 1** | Bottle 이미지 로드 + `POST /inspections` 검사 ID 반환 | **완료** | 순차적 고유 ID(`INSP-XXXXXX`) 발급, 중립 `image_id` 매핑 |
| **Day 2** | OpenCV 밝기 지표 계산 + JSONL 검사/이벤트 로그 자동 저장 | **완료** | `train/good` 정상 통계 기반 임계값, 스레드 세이프 JSONL 저장 |
| **Day 3** | T01/T03/T05/T06 반복 재현 + 평가 정답 물리적 격리 | **완료** | 4대 시나리오 실측 검증 완료, 정답 라벨 100% 은닉, 57개 테스트 PASS |
| **Day 3.5** | PatchCore 이상 검출 + 종합 판정 + Cloud Run 배포 준비 + 보안 점검 | **완료** | 180장 Coreset 학습, 29장 독립 검증, 임계값 34.1442, final_result 정책, Cloud Run CPU Dockerfile, 데이터 접근 정책 수립, 105개 테스트 PASS |
| **Day 4** | Gemini AI Agent 실제 도구 호출 + 구조화 보고서 | **완료**<br>DAY4_DONE | 도구 4종·운영 단순 JSON 연결·FastAPI·Evidence/Pointer·판정 보호 완료. T01/T03/T05/T06 실제 성공 회차 확인. 최종 전체 1089 PASS / 4 SKIP / 경고 2건. SKIP 및 T06 원본 응답 미보관 한계는 Step5에 명시 |
| **신규 로드맵** | 동영상 Live View + 프레임 Grab + 마우스 드래그 ROI + PatchCore 추론 + Agent 재진단 | 계획 수립 | Day 4 완료 후 React 대시보드와 함께 구축 예정 (기존 모델/임계값 34.1442 유지) |
| **Day 5** | 상황별 추가 조사 + 반례 평가 | 대기 | Agent 심층 진단 및 가설 수립 기능 |
| **Day 6** | React E2E + Cloud Run 준비 | 대기 | 웹 대시보드 프론트엔드 (Live View 및 Grab View 포함) |
| **Day 7** | Cloud Run HTTPS API / Agent 분석 검증 + 최종 문서화 | 대기 | 배포 환경 검증 |

---

## 2. Day 3 핵심 시나리오 (T01, T03, T05, T06) 구현 내역

| 시나리오 | 실행 목적 | 입력 이미지 식별자 | 실제 측정 지표 | image_quality_status | result | 주요 발생 이벤트 |
| :---: | :--- | :--- | :--- | :---: | :---: | :--- |
| **T01** | 정상 Bottle 기준 검사 | `IMG-BOTTLE-0084`<br>(`train/good/000.png`) | mean: 135.86<br>std: 92.66 | `NORMAL` | `UNKNOWN` | `INSPECTION_STARTED`<br>`IMAGE_LOADED`<br>`ANALYSIS_COMPLETED` (INFO)<br>`INSPECTION_COMPLETED` |
| **T03** | 조도 저하(0.6x) 오류 주입 | `IMG-BOTTLE-INJ-0001`<br>(`injected_images/`) | mean: 81.24<br>std: 55.79 | `WARNING_LOW_BRIGHTNESS` | `UNKNOWN` | `INSPECTION_STARTED`<br>`IMAGE_LOADED`<br>`ANALYSIS_COMPLETED` (**WARN**)<br>`INSPECTION_COMPLETED` |
| **T05** | 이미지 로드 실패 재현 | `IMG-BOTTLE-NONEXISTENT`<br>(부재 가상 경로 stub) | 측정 불가<br>(`metrics={'error': ...}`) | `ERROR` | `UNKNOWN` | `INSPECTION_STARTED`<br>`IMAGE_LOAD_FAILED`<br>`INSPECTION_FAILED`<br>*(ANALYSIS_COMPLETED 미발생)* |
| **T06** | 불량 원본 정상 흐름 처리 | `IMG-BOTTLE-0001`<br>(`broken_large/000.png`) | mean: 138.37<br>std: 92.08 | `NORMAL` | `UNKNOWN` | `INSPECTION_STARTED`<br>`IMAGE_LOADED`<br>`ANALYSIS_COMPLETED` (INFO)<br>`INSPECTION_COMPLETED` |

---

## 3. 평가 정답 데이터 격리 구조

* **프로젝트 내부 (`InspectAgent/test_data/`)**:
  * 운영 코드 및 향후 Agent가 접근할 수 있는 영역입니다.
  * 중립 식별자(`IMG-BOTTLE-XXXX`) 및 변형 사본 이미지(`injected_images/`)만 보관됩니다.
  * `broken_large`, `contamination`, `good` 같은 원본 정답 라벨이나 0.6배 주입 계수는 일절 포함되지 않습니다.
* **프로젝트 외부 (`Project/evaluation_private/`)**:
  * 운영 FastAPI 및 Agent 도구의 파일 접근 경로에서 물리적으로 완전히 분리된 외부 디렉터리입니다.
  * `evaluation_answers.json` 등 정답 데이터는 오프라인 평가 러너에서만 별도로 읽도록 구성되어 있습니다.
  * 정적 코드 분석 결과 `backend/` 코드베이스 내에 `evaluation_private` 또는 `evaluation_answers`에 대한 참조가 전무(Zero Reference)함을 확인했습니다.

---

## 4. 검증 명령어 및 실행 방법

```bash
# 1. 전체 pytest 테스트 스위트 오프라인 회귀 실행 (네트워크 차단 격리 환경)
python -m pytest tests -q -p no:cacheprovider
# 마지막 전체 실행 결과: 536 passed, 3 warnings in 19.14s (100% 통과)

# 2. 스키마 후보 생성 및 로컬 메타데이터 점검
python -m scripts.agent_schema_candidates

# 3. 단순 보고서 프로토타입 관련 테스트
python -m pytest tests/test_agent_e2_partitions.py tests/test_agent_simple_report.py -q -p no:cacheprovider
# 결과: 50 passed
```

---

## 5. 현재 구현된 기능 vs 미구현 기능

### 구현 완료된 기능
1. **FastAPI 백엔드 서비스**:
   * `GET /health` : 헬스체크
   * `GET /baseline/brightness` : 정상 Bottle 밝기 기준 통계 제공
   * `POST /inspections` : 검사 생성, 밝기 분석, PatchCore 추론, 판정, JSONL 저장
   * `GET /inspections/images` : 등록된 중립 image_id 목록 조회
   * `POST /analyze/{inspection_id}` : 저장된 검사에 대한 사후 이상 진단 API (Mock E2E 검증 완료)
2. **OpenCV 비전 분석 및 PatchCore 추론**:
   * 이미지 크기, 그레이스케일 변환, 밝기 통계(mean, std, min, max) 계산
   * ResNet-18 Backbone 기반 PatchCore 비지도 결함 탐지 모델 (CPU 추론 41~43ms)
   * 정상 검증셋 기반 결정 임계값(`34.1442`) 및 산업용 종합 판정(`final_result`, `final_reason_code`) 로직
3. **JSONL 저장소 계층**:
   * `data/inspections.jsonl` : 검사 결과 레코드 저장
   * `data/inspection_logs.jsonl` : 세부 실행 이벤트 로그 저장 (스레드 세이프)
4. **Day 4 AI Agent 아키텍처 (Step 1~3)**:
   * 4대 조회 도구 (`backend/agent/tools.py`), `TARGET-PRODUCT` 불투명 별칭 처리
   * Gemini 수동 Function Calling 바인딩 (`backend/agent/service.py`)
   * Evidence ID 및 JSON Pointer 기반 서버 Python 결정적 근거 검증 (Grounding)
   * 정상 검사 조건부 조기 종료 (2요청 단축 경로)
   * 스키마 후보 격리 유틸리티 (`scripts/agent_schema_candidates.py`) 및 단순 보고서 프로토타입 (`scripts/agent_simple_report_prototype.py`)
5. **실서버 Gemini API 검증 (PASS 항목)**:
   * 실제 Gemini 모델 Function Calling 및 Python 도구 실행 (`get_inspection_result`) 성공
   * FunctionResponse `role="user"` 전송 프로토콜 검증
   * A/B/C 단순 스키마 후보 실서버 HTTP 200 수락
   * 단순 JSON 보고서 프로토타입 합성 실험 실서버 HTTP 200 수락 및 Python 근거 검증 100% 통과

### 아직 미완료된 기능 (진행 중 및 향후 예정)
1. **Day 4 잔여 과제 (진행 중)**:
   * 단순 JSON 보고서 프로토타입의 운영 `AgentService` 연결
   * T01 실제 Gemini API End-to-End 전체 분석 성공
   * T03 / T05 / T06 실제 Gemini 분석 검증 및 한국어 진단 품질 평가
   * Day 4 Step 5 통합 완료 선언
2. **신규 영상 검사 요구사항 (향후 로드맵)**:
   * MVTec Bottle 영상 파일 로드 및 컨베이어 Live View 스트리밍
   * 실시간 프레임 Grab 및 마우스 드래그 ROI 선택
   * ROI 이미지 대상 기존 PatchCore 체크포인트 및 임계값(`34.1442`) 적용
   * 조명 이상 또는 검사 실패 시 Gemini Agent 자율 재진단 연동
   * 실행 로그에서 불필요한 `product_id` 제외
3. **React 웹 프론트엔드 대시보드 (Day 6)**:
   * Live View 플레이어, Grab Image 뷰어, ROI 선택 박스, Agent 진단 패널
4. **Google Cloud Run 배포 및 영구 스토리지 계층 (Day 7)**

---

## 6. 다음 작업 인수인계 순서

1. 단순 JSON 보고서 프로토타입을 운영 AgentService에 연결
2. Pydantic 및 결정적 Evidence 검증 회귀 테스트
3. 전체 pytest 스위트 실행 (536개+ 통과 확인)
4. 별도 승인 후 T01 실제 Gemini End-to-End 분석 (1회)
5. 별도 승인 후 T03/T05/T06 실제 Gemini 분석 검증
6. Day 4 완료 판단 후 영상 Grab·ROI 기반 개발 진행

> 실제 Gemini API 요청이나 유료 모델 호출은 사전 사용자 승인 하에서만 1회씩 진행합니다.
