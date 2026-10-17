# VisionInsight Day4 Step5 — 최종 통합 검증 및 공식 완료 보고서

- 검증일: 2026-10-17
- 최종 판정: **DAY4_DONE — 백엔드 Agent PoC 범위, 아래 SKIP·품질 검토 한계 명시**
- 이번 작업: 읽기 전용 코드/기존 실서버 산출물 감사, 오프라인 테스트, README 및 문서 정리만 수행.
- 실제 Gemini API 요청 0회, READY 생성 0건, 실제 E2E 신규 실행 0건, Git add/commit/push 0건.
- Day4 완료는 프로젝트 전체 개발·웹 E2E·배포·상용 운영 신뢰성 완료가 아니다.

## 1. Day4 개발 목표

### 1.1 당초 계획과 완료 기준

[원계획](plan.md)의 Day4 절은 조회 도구 4개, Gemini 도구 호출 연결,
관측/가설 분리·근거 ID 지침, `POST /analyze/{inspection_id}` 구현을 요구한다.
명시된 완료 기준은 **Agent가 로그와 품질 정보를 실제 도구 호출로 읽고 구조화된 보고서를 반환**하는 것이다.
[AGENTS.md](../AGENTS.md)도 실제 도구 호출과 구조화 보고서를 Day4 기준으로 둔다.
후속 [인수인계서](day4-agent-handoff.md)의 기존 Step5는 운영 연결·대표 E2E·진단 품질·통합 완료를 요구한다.

실제 구현은 공식 google-genai SDK의 수동 Function Calling과 Python 결정적 검증을 사용한다.
원계획의 “강의 요구 프레임워크”는 구체 제품/버전/채점 조건이 명세돼 있지 않다.
후속 Step2 문서에서 공식 SDK 수동 호출 구조로 구체화됐으며 본 판정은 그 저장소 기술 계약을 대상으로 한다.
별도 교육기관의 특정 프레임워크 사용 요건 충족 여부까지 검증한 것은 아니다.

### 1.2 계획 대비 실제 구현

| 당초 항목 | 실제 코드·증거 | 판정 |
|---|---|---|
| 결과·로그·품질·최근 이력 4개 조회 | `backend/agent/tools.py`, `tests/test_agent_tools.py` | 완료 |
| Gemini 실제 함수 호출 | 수동 Function Calling, 도구 인자 검증·Python 실행 Trace, 대표 4종 실서버 성공 기록 | 완료 |
| 관측/가설/점검/한계 구분 및 근거 ID | `schemas.py`, `reporting.py`, `service.py`, `prompts.py` | 완료 |
| FastAPI 사후 분석 | `backend/agent/api.py` 및 `backend/main.py` 라우터 연결 | 완료 |
| 실제 로그·품질 조회 후 구조화 보고서 | T03 실제 품질 도구, T05 실제 로그 도구 및 최종 엄격 검증 PASS | 완료 |

보고서 초기 예시와 달리 실제 JSON 필드는 `observed_facts`, `possible_causes`,
`recommended_checks`, `limitations`, `tool_execution_trace`로 구체화됐다.
복잡한 DiagnosisDraft Schema를 Gemini에 직접 전송하는 초기 방식은 HTTP 400 이력 이후,
단순 JSON 선택 토큰을 Python에서 엄격한 DiagnosisDraft로 변환하는 구조로 변경됐다.
검증을 제거하거나 관측값을 모델이 생성하도록 바꾼 것이 아니다.

기술 마일스톤 Step1~5는 **5/5 완료**로 판정한다. 전체 7일 프로젝트 완료율이라는 뜻이 아니다.
상황별 추가 조사·반례 평가의 확장은 원계획 Day5, 브라우저/UI와 배포는 Day6~7 범위로 남긴다.

## 2. Agent 아키텍처

```text
저장된 검사 원본(판정 권위)
  → FastAPI POST /analyze/{inspection_id}: ID·존재 확인
  → 요청별 AgentService + RequestState
  → Gemini Function Calling: 허용 도구 제안
  → 서버 allowlist·Pydantic 인자·검사/제품 범위 검증
  → 실제 Python 조회 도구 → Evidence Store(E0001 등) + Tool Trace
  → 서버 조사 완료 조건 / 제한된 일반 조사 루프
  → 독립 Fact Catalog(K 토큰, Evidence ID, JSON Pointer, 실제 값)
  → Gemini 단순 JSON 선택 보고서(도구 없는 별도 요청)
  → JSON 파싱 → Python DiagnosisDraft 변환 → Pydantic
  → Fact/Evidence/Pointer/값/필수 사실/가설·조치 근거 검증
  → 서버 고정 문구 렌더링 → API 원본 판정 재확인 → AnalysisResponse
```

PatchCore·Decision이 제품/종합 판정을 확정한다. Agent는 검사 사후 조사와 설명만 수행한다.
Agent 분석 API는 이미지를 재로드하거나 PatchCore를 재실행하거나 검사/로그 JSONL을 수정하지 않는다.
실제 PLC·컨베이어·배출 장치 제어는 구현 범위가 아니다.

조사를 계속할 때 모델 Content·thought signature·Function Call ID와 FunctionResponse의
연결을 보존한다. 조기 종료 시 마지막 FunctionResponse는 로컬 이력에 남고,
최종 요청은 그 도구 결과의 독립 카탈로그를 사용한다. 실제 후속 FunctionResponse 전송이
생략된 경우를 “Gemini에 반환됐다”고 보고하지 않는다.

## 3. 구현 기능 목록

| 단계 | 현재 구현 및 검증 범위 | 주요 코드/테스트 |
|---|---|---|
| Step1 조회 도구 | 결과·저장 품질·실행 로그·동일 제품 이력. ID 검증, allowlist 직렬화, 잘못된 저장소 응답/입력 차단. 이미지 재분석·임의 파일 조회 없음 | `tools.py`; `test_agent_tools.py` |
| Step2 서비스 | 수동 Function Calling, 호출 예산, Evidence Store, Catalog, 단순 JSON 변환, Pydantic/Pointer, 판정 불변, 안전한 코드 기반 문구 | `service.py`, `reporting.py`, `schemas.py`; `test_agent_service.py`, `test_agent_reporting_integration.py` |
| Step2 종료/안전 | NORMAL, 품질 경고, 이미지 로딩 실패 종료 조건. 원천 부족 시 계속 조사하거나 최종 생성 전 안전 실패 | `investigation.py`, `error_policy.py`; `test_agent_efficiency.py`, `test_agent_warning_policy_integration.py`, `test_agent_image_load_stop.py` |
| Step3 HTTP | lazy SDK 준비, 정상 응답·입력/존재 검증·실패 매핑·원본 불변·요청별 격리 | `api.py`; `test_agent_api.py` |
| Step4 실제 검증 | T01/T03/T05/T06 각각 실제 성공 회차와 과거 실패/READY/잠금 보존 | 아래 실서버 감사 표 및 [상세 기록](day4-step4-gemini-validation.md) |

### 3.1 종료 계약의 구분

- **NORMAL / T01·T06:** 저장 핵심 상태 6개가 COMPLETED/OK/NORMAL/COMPLETED/OK/ALL_CHECKS_PASSED이고,
  유한한 점수·임계값이 존재하며 점수가 임계값 이하인 경우 정상 조기 종료한다.
  최종 보고서에는 별도로 핵심 Fact/Evidence 검증을 요구한다.
- **IMAGE_QUALITY_WARNING / T03:** 원본은 모델 OK / 최종 REINSPECT다. 결과·품질 도구의
  일치하는 상태/측정 근거를 확인한다. 설정된 `required_warning_event_codes`가 있으면
  실제 로그와 이벤트 stage/timestamp도 요구하며 최종 보고서에도 같은 조건을 검증한다.
  아래 실제 T03 성공 회차는 결과·품질 두 도구를 사용했으며 로그 도구를 호출했다고 주장하지 않는다.
- **IMAGE_LOAD_FAILURE / T05:** 성공한 결과/로그 도구, 대상 ID·Trace·Evidence 소속,
  실제 IMAGE_LOAD_FAILED 및 INSPECTION_FAILED, 기존 validator의 필수 원천 근거를 확인한다.
  T05의 17개는 핵심 6 + 미산출/미기록 5 + 이벤트 근거 6이다. 부족하면 조기 종료하지 않는다.
  루프 종료 후 원천 검사와 최종 보고서의 필수 사실 검사는 모두 유지한다.
- 실제 INFERENCE_FAILED나 일반 ERROR는 이미지 로딩 실패 전용 조기 종료 대상으로 일반화하지 않는다.
  SKIPPED/UNKNOWN만으로 모델 장애를 추론하거나 수리를 권고할 수 없다.
- 근거가 충분한 모든 일반/비표준 ERROR가 자동으로 최소 요청으로 끝난다는 보장은 없다.
  T03의 추가 history 등 비표준 경로의 조사 효율은 제한 안에서 별도 Day5 검토 대상으로 남긴다.

### 3.2 API 오류와 검사 오류의 분리

검사 이미지 로딩 실패(ERROR/SKIPPED/UNKNOWN)는 원본 검사 상태이고,
Gemini HTTP 실패는 별도의 Agent 분석 실패다. 검사 ERROR여도 근거 기반 설명이 성공하면 HTTP 200/COMPLETED다.
반대로 검사 OK라도 Gemini 요청이 실패하면 분석은 실패할 수 있다.

입력 오류 422, 없는 검사 404, 키/저장소 준비 불가 503, 근거 불일치 및 Gemini 원격 요청 실패 502,
로컬 Gemini/Agent/도구 timeout 504, 예상 밖 내부 실패 500으로 구분한다.
원격 Gemini HTTP 504가 SDK 예외로 관측된 사례는 GEMINI_REQUEST_FAILED/HTTP 502였으며,
이를 로컬 15초 wait_for 초과가 입증된 것으로 해석하지 않는다.

## 4. 최종 통합 테스트

### 4.1 이번 실행과 과거 실행의 구분

| 이번 실행 범위 | 결과 | 시간 |
|---|---|---|
| `tests/test_agent_*.py` | 988 PASS | 14.36초 |
| READY/timeout/T06 격리 5개 모듈 + 데이터 격리·보안 모듈 | 213 PASS / 경고 2건 | 13.04초 |
| 전체 `tests`, **1회만 실행** | **1089 PASS / 0 FAIL / 4 SKIP / XFAIL 0 / XPASS 0 / 경고 2건** | **28.08초** |
| `python -m pip check` | No broken requirements found | 정상 |
| `git diff --check` | 공백 오류 없음 | 정상 |

그룹은 중복되므로 수치를 합산하지 않는다. 테스트나 assertion·skip 조건은 수정하지 않았다.
과거 전체 1089 PASS는 입력 타입 보강 이전이었다. 이번에는 그 보강이 포함된 현재 코드를 전체 재검증했다.
경고는 기존 timm.models.layers 및 anomalib dinov2 deprecation 2건이다.
Git의 LF/CRLF 알림은 pytest 경고와 별개이며 diff 공백 검사 실패가 아니다.

실행 환경은 Python 3.11 / Miniconda vision-insight다. 정확한 재현 명령은
[README 테스트 절](../README.md#84-테스트-실행-및-검증-결과)에 기재했다.
OUTPUT_DIR/LOG_DIR/TEST_DATA_DIR/검사·로그 JSONL을 새 외부 tempfile 경로로 분리했고,
기본 HTTPTransport/AsyncHTTPTransport를 차단해 SDK MockTransport/테스트 대역만 사용했다.
외부 평가 파일 open 차단 guard, PYTHONDONTWRITEBYTECODE=1, 기본 최종 timeout 15도 적용했다.
Windows 내부 socketpair 전체 차단은 사용하지 않았다.
실제 E2E 실행 옵션이나 검증 회차 생성 스크립트를 호출하지 않았다.

전체 실행 옵션은 `tests -q -rs -p no:cacheprovider --basetemp <외부 임시 경로>/pytest
--junitxml <외부 임시 경로>/results.xml`이다.
이번 산출물은 `%TEMP%/vision_day4_step5_mhaixbkj/results.xml`에 격리했다.
JUnit도 총 1093건 / errors 0 / failures 0 / skipped 4를 확인했다. SKIP 4개 모두 type=pytest.skip이다.
임시 산출물은 영구 증거 저장소가 아니며 운영 JSONL/검증 회차에는 쓰지 않았다.

### 4.2 SKIP 4건의 실제 이유와 영향

| 정확한 테스트 | 이번 SKIP 이유 | 필요한 환경·이번 미검증 범위 | Day4 판정 영향 |
|---|---|---|---|
| `test_day3_5_integration.py::test_t03_brightness_reduced_inspection` | No injected images registered | 격리 registry에 T03 주입 이미지 필요. 실제 저밝기 입력의 PatchCore 점수/완료 통합 미실행 | Day3.5 이미지 의존 추가 통합 범위로 제외; PASS로 세지 않음 |
| `test_day3_5_step4.py::test_image_quality_warning_decision_confidence_policy` | No fault-injected images found | 같은 입력 등록 필요. 품질 경고의 decision_confidence 및 WARN 로그까지 해당 이미지 경로에서 미검증 | 해당 경로의 미검증을 남기되 Day4 Agent 필수 근거/판정 검증과 구분 |
| `test_day3_5_step4_5.py::test_t03_final_verdict_quality_warning_reinspect` | T03 injected image not present | 같은 입력 등록 필요. 이미지부터 REINSPECT까지 이 테스트의 재실행 미수행 | Day4 품질 경고 API·Mock·기존 실제 성공과 별개로 제외 명시 |
| `test_day3_5_step4_5.py::test_workflow_product_ng_under_quality_warning` | T03 injected image not present | 입력 등록 및 Mock NG 추론 필요. 실제 이미지 품질+모델 NG 동시 경로 미실행 | Day3.5 결합 통합은 남음; 순수 판정 우선순위 테스트는 통과 |

4개 모두 외부 임시 TEST_DATA_DIR에 주입 이미지가 등록되지 않아 기존 조건에 따라 SKIP됐다.
이미지를 임의 생성하거나 운영 generator를 실행해 이 숫자를 바꾸지 않았다.
독립 `isolated_t03_input` fixture는 원본 사본과 tmp registry/storage를 사용하며,
`test_data_isolation_and_security.py::test_t03_synthetic_injection_parameters_not_leaked`는 실제 PASS했다.
이는 그 fixture의 한 테스트 범위만 보장하며 위 네 경로 전체를 대신 실행한 것은 아니다.

필수 Day4 보안/ID 범위/판정 보호/Evidence/Pointer/T06 정답 격리 테스트에는 SKIP이 없었다.
T03 필수 사실·변조 거부·서버 판정 보호 Mock과 과거 실제 T03 성공도 별도 확인했다.
따라서 네 이미지 통합 제외를 문서화한 상태에서 Day4 백엔드 범위 완료를 허용한다.
이 테스트들을 검증 완료로 주장하지 않으며, Day3.5 포함 모든 이미지 조합의 무결한 커버리지 판정은 하지 않는다.

## 5. 실제 Gemini E2E 통합 감사

이번에는 기존 산출물만 읽었다. 원본 산출물은 `data/outputs/manual_validation/`에 있고 Git에 추가하지 않았다.
실행 당시 모델은 gemini-3.8-flash다. 최소 1개 성공 회차의 존재를 확인하는 감사이지 반복 성공률 평가가 아니다.

| 시나리오 / 검사 ID | 실제 성공 회차 | 서버 최종 판정 | FastAPI / 분석 | 전체 시간 | 최종 Fact / Evidence | 감사 |
|---|---|---|---|---|---|---|
| T01 / INSP-001396 | t01_operational_simple1 | OK | 200 / COMPLETED | 13.578초 | 6 / 1 | PASS |
| T03 / INSP-001398 | t03_operational_final30_1 | REINSPECT | 200 / COMPLETED | 24.600초 | 12 / 2 | PASS |
| T05 / INSP-001405 | t05_operational_earlyexit_final30_1 | ERROR | 200 / COMPLETED | 16.333초 | 17 / 2 | PASS |
| T06 / INSP-001406 | t06_operational_groundtruth_isolated_final30_1 | OK | 200 / COMPLETED | 26.371초 | 6 / 1 | PASS (자연어 검토 범위는 아래 구분) |

| 회차 | 실제 Python 조사 도구 | 실제 Gemini HTTP 순서 | 최종 HTTP 시간 / 선택 상한 | 확인 토큰 |
|---|---|---|---|---|
| T01 | get_inspection_result | 조사 200 → 최종 200 | 10.527초 / 기본 15초 | 4706 |
| T03 | get_inspection_result, analyze_image_quality | 조사 200 → 조사 200 → 최종 200 | 18.967초 / 30초 | 9873 |
| T05 | get_inspection_result, get_execution_logs | 조사 200 → 조사 200 → 최종 200 | 11.063초 / 30초 | 11426 |
| T06 | get_inspection_result | 조사 200 → 최종 200 | 24.118초 / 30초 | 7202 |

T01의 4706은 SDK 요청별 1271+3435에서 확인했다. 초기 T01 기록에는 현재처럼 계층별 timeout
필드가 없으므로 “모든 timeout 계층을 당시 실측했다”고 하지 않는다. T03/T05/T06의 후속 정밀 계측과 구분한다.
각 성공 회차의 실제 분석 1회와 재시도 0회를 확인했고, 최종 JSON·Pydantic·Evidence·판정 불변은 PASS다.

### 5.1 T05의 구분

원본 FAILED / UNKNOWN / ERROR / INSPECTION_FAILED,
image_quality_status=ERROR, defect_detection_status=SKIPPED다.
anomaly_score/decision_threshold/inference_time_ms는 null, 밝기 평균·표준편차는 미기록이며 0으로 대체하지 않았다.
실제 IMAGE_LOAD_FAILED 및 INSPECTION_FAILED가 E0002의 오류 근거와 연결됐다.
원천 17개 수집과 최종 DiagnosisDraft의 17개 필수 사실 검증이 모두 성공했다.
이는 모델 체크포인트 고장이나 실제 카메라 장애가 확인됐다는 의미가 아니다.

### 5.2 T06의 검증 범위

원본 COMPLETED / OK / OK / ALL_CHECKS_PASSED,
anomaly_score=32.26792526245117, decision_threshold=34.1442가 보존됐다.
NORMAL 종료 후 최종 JSON 요청은 SDK/HTTPX/헤더/wait_for 모두 30초였으며 최종 Fact는 6개다.
20개 카탈로그 후보는 사후 동일 원본/Trace로 재구성한 수치이지 검증 Fact 20개가 아니다.

- 실제 최종 JSON·DiagnosisDraft·Pydantic·Fact/Evidence/Pointer 검증: **PASS**.
- 검증된 선택 코드 및 변경되지 않은 서버 고정 문구를 재구성한 자연어 사후 검토: **PASS**.
- 원본 ASGI 응답 전체의 보관 및 이를 이용한 독립 자연어 재검토: **미수행 / 자료 미보관**.

재구성 요약은 “기록된 모델 판정과 종합 판정은 OK입니다. 실제 무결점 제품을 보증하지 않습니다.”다.
권고는 F0003의 OK를 근거로 한 CONTINUE_MONITORING, 원인 가설은 0개다.
무결점 보장·실제 결함 발견·정답 라벨·설비 고장 주장은 없다. 고정 문구 범위를 넘는 완전한 자유 자연어 검증이라고 과장하지 않는다.
외부 평가 정답을 사용하지 않았으며 이 성공이 PatchCore 미탐을 복구했다는 뜻도 아니다.

## 6. 실패 및 개선 이력

| 보존한 이력 | 관측된 문제 | 이후 조치·남은 한계 |
|---|---|---|
| 초기 T01 및 Schema 실험 | role=tool 직렬화/복합 Schema HTTP 400, 일부 후속 조사 HTTP 504 | user FunctionResponse·Content/signature 보존, 단순 JSON/Python 엄격 검증으로 전환. 과거 산출물 유지 |
| T03 operational_simple1 / warningstop1 | 후속 조사 504, 조기 종료 보완 후 최종 JSON 15초 요청도 504 | 선택적 최종 30초 회차에서 18.967초 요청 성공. 서버 내부 원인 UNKNOWN |
| T05 operational_final30_1 | 도구 2개·원천 근거 확보 뒤 일반 루프가 세 번째 조사 요청, HTTP 504 | 기존 validator를 재사용한 이미지 로딩 실패 전용 종료 조건 추가. earlyexit 회차에서 최종 생성/17개 검증 PASS. 모든 ERROR 일반화 아님 |
| T06 groundtruth_isolated_1 | 조사 200/NORMAL 이후 최종 JSON 15초 요청 504, 전체 16.232초 | 독립 지정 final30 회차에서 최종 24.118초 성공. 기존 FAIL 보존, 이전 504 내부 원인 UNKNOWN |
| READY 준비 임시 래퍼 | 모든 socket.connect 차단으로 Windows asyncio 내부 127.0.0.1 socketpair까지 RuntimeError | 외부 API 경계 차단과 내부 IPC를 분리해 오프라인 재현·호환 확인. 운영 코드 결함으로 둔갑시키지 않음 |

30초 성공만으로 기존 HTTP 504가 로컬 timeout 때문이었다고 확정하지 않는다.
실제 서버 절대 deadline·실제 비용은 UNKNOWN/NOT OBSERVABLE이며 반복 실행 안정성도 미검증이다.

## 7. 안전성 검증

| 계약 | 코드/검증 근거 | 최종 상태 |
|---|---|---|
| 판정 권위 | API 원본 snapshot·요약 재검증, 서버 final_result 변경 거부 | PASS |
| Tool allowlist·범위 | 도구 4개만 선언, Pydantic 인자, 대상 inspection/product 일치·경로/코드 실행 금지 | PASS |
| Evidence·Pointer | 실제 실행 성공 Trace·Evidence ID·원본 scalar·event·값 타입 검증 | PASS |
| 보고서 구조 | SimpleReport → DiagnosisDraft, 중복/가짜 토큰·없는 Evidence/Pointer·불일치 값 거부 | PASS |
| ERROR 안전성 | 미기록 null 보존, 필수 오류 사실, SKIPPED만으로 모델 장애 가설·수리 권고 금지 | PASS |
| 정답 격리 | 도구 응답 allowlist·컨텍스트 ID 정제·Catalog/변환 입력·전송 경계 검사, T06 격리 테스트 | PASS (확인한 경로 범위) |
| 제한·재시도 | 라운드 4, 도구 호출 8, 동일 호출 반복 2, 전체 60초, 여유 2초, 자동/수동 재시도 0 | PASS |

기본 조사 15초 / 최종 JSON 15초를 유지한다. 검증 인프라는 승인된 특정 T03/T05 회차 및
정확한 신규 T06 final30 회차에서만 최종 상한 30초를 선택한다. 조사까지 30초로 늘린 것이 아니다.
운영 설정의 최종 timeout 기능과 수동 회차 승인 정책을 구분하며, 회차 ID를 운영 Agent 정책에 하드코딩하지 않는다.
최종 요청 제한은 min(선택 상한, floor(잔여 전체 시간-2))다. SDK attempts=1은 최초 시도만이며 재시도 0회를 뜻한다.

외부 평가 경로의 내용·파일명 목록·마스크·정답·해시를 읽지 않았다.
OS 차원의 완전한 공격자 격리나 모든 식별자에서 정보 추론이 불가능함을 주장하지 않는다.

## 8. 알려진 한계

### 8.1 PatchCore 성능과 Agent 성능의 분리

기존 [평가 보고서](evaluation-results.md)와 README의 83장 **평가 부분집합** 기록은
AUROC 0.8286, Precision 100%, Recall 50.79%, TP32/TN20/FP0/FN31이다.
CPU 단일 이미지 평균 42.53ms는 기존 README의 측정 기록이며 이번에 다시 벤치마크하지 않았다.
Gemini 지연·라인 처리량·모든 환경의 검출 보장으로 해석하지 않는다.
특히 Recall과 FN31의 미탐 한계는 그대로 남아 있다. Agent 성공은 모델 성능 개선이 아니다.

문서 간 차이도 확인했다. `patchcore-cpu-benchmark.md`에는 이전 209장 학습 모델의
46.17ms 기록이 있으며 현재 metadata는 180장/독립 검증29장이다. 두 모델 시점의 수치를 혼합하지 않는다.
`evaluation-results.md`의 유형별 표에는 contamination 21장 중 5장 검출인데 미검출 “5건”으로
적힌 산술적 불일치가 있다(21-5=16). 종합 FN31과 구분하며 유형별 FN값은 이번에 재검증했다고 하지 않는다.
평가 원본에 접근하거나 이 문서를 임의 정정하지 않았다. 총괄 지표를 새 평가로 둔갑시키지 않는다.

### 8.2 운영·품질 한계

- 네 시나리오 각각 최소 1개 성공은 반복 안정성·통계적 신뢰성·상용 SLA가 아니다.
- Gemini HTTP 504 가능성, 서버 내부 원인과 실제 과금 UNKNOWN이 남는다.
- T06 ASGI 원본 본문이 없어 독립 원문 재검토는 불가능하다. 코드 기반 재구성 검토와 구분한다.
- 기존 일부 result의 `actual_final_timeout_seconds=NOT TESTED` 표시는 preflight 값이 남은 계측 한계다.
  T06 실제 최종 30초는 요청별 SDK/HTTPX/헤더/wait_for 기록으로 확인하며 원본 결과를 고치지 않았다.
- 위 네 이미지 통합 SKIP 경로는 이번 전체 실행에서 미검증이다.
- 정상/품질 지표는 실제 물리적 고장·제품 무결점의 보증이 아니다. 실제 설비 미연동이다.
- JSONL은 개발용이다. Cloud Run 영구 저장·인증·브라우저 E2E·배포는 별도 단계다.

## 9. 배포 전 남은 작업

다음은 이번에 수행하지 않았으며 별도 승인 후 범위를 확정해야 한다.

1. Day5 추가 조사·무관 경고/제품 NG 반례 평가, T03 비표준 조사 효율 검토.
2. 외부 임시 fixture로 남은 이미지 통합 4건을 확인하고 평가 문서 산술/버전 차이를 별도 감사.
3. 원본 응답의 안전한 보관·자연어 독립 검토·stale timeout 요약 표시 개선 설계.
4. 실제 웹 UI 연동 및 로컬 브라우저 E2E. 이번에는 Playwright를 시작하지 않았다.
5. 배포 설정·환경·비밀값·인증·요청량/비용·스토리지 영속성 점검 후 Cloud Run/프론트 배포 검증.
6. 발표 자료와 데모 최신화는 다른 작업과 충돌하지 않도록 별도 승인. 이번에는 수정하지 않았다.

## 10. 최종 Day4 완료 판정

### 10.1 완료 근거

본 작업의 10개 필수 조건(핵심 구현, 조회 도구, Function Calling, API, 근거/Pointer,
판정 불변, 대표 실제 4종 성공, 전체 FAIL 0, 제약 문서화, README/최종 보고서)을 확인했다.
원계획의 로그·품질 실제 조회 및 구조화 보고서 기준도 T05/T03 기록으로 충족한다.
필수 보안·근거 테스트의 SKIP은 없고, 이미지 의존 Day3.5 네 경로는 위와 같이 명시적으로 제외한다.
따라서 **DAY4_DONE**으로 판정한다. 이 제외 및 T06 원문 미보관 한계를 삭제한 무조건적 완료 선언은 아니다.

### 10.2 보호·변경 범위

작업 전후 기존 대조 파일 **182개 SHA256 모두 동일**, 기존 READY·잠금·실제 PASS/FAIL 결과 신규 생성/변경 0건이다.
대조 범위는 backend/scripts/tests/presentation(캐시 제외), 두 운영 JSONL, PatchCore 체크포인트·메타데이터,
수동 검증 디렉터리의 기존 파일, 확인 원본 이미지 2개다. 전체 이미지 데이터셋 해시나 외부 정답 해시는 아니다.
기존 사용자 변경과 `.tmp_measurement_regressions/`는 복원·삭제하지 않았다.

변경은 README, 이 신규 보고서, 기존 구현 현황·인수인계의 최신 상태 표시,
Step4 문서의 최종 감사 참조 추가뿐이다. 기존 실서버 상세 이력은 보존했다.
실제 Gemini API 요청 **0회**, READY·실제 E2E 신규 실행 **0건**, Git add/commit/push **0건**이다.
운영 코드·테스트·모델·프롬프트·Schema·timeout·배포·발표 파일은 수정하지 않았다.
Day4 판정과 문서 정리 후 추가 개발이나 실서버 실행 없이 중단한다.
