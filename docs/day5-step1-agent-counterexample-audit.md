# Day5 Step 1 — Agent 반례·조건부 조사 현황 감사

- 감사일: 2026-10-17
- 범위: 코드·기존 테스트·기록된 Gemini E2E의 읽기 전용 검토
- 판정: **감사 완료 / Day5 반례 평가 미완료**
- 이번 감사에서 Agent/API 호출, 테스트 실행·수정, 영상 검사, READY 생성은 수행하지 않았다.

## A. Day5 원계획과 개정 작업의 관계

저장소의 [원계획](plan.md#L343)은 밝기 경고 때 최근 이력 조회, 이미지 로드 실패 때 로그 우선 조회, 불량 입력과 정상 실행 로그의 구분, 무관 로그 과잉 해석 반례, 호출 Trace 반환을 요구한다. 원계획은 서로 다른 상황의 추가 조사와 근거 없는 단정 방지를 완료 기준으로 둔다.

2026-10-15 인수인계 시점 자료는 [구현 현황](implementation-status.md#L15)에서 역사적 스냅샷으로 보존되어 있고, 이후 영상 Live View/Grab/ROI/PatchCore 및 Agent 재진단 로드맵을 적고 있다. 그러나 저장소에서 원계획을 대체하는 하나의 정식 “2026-10-15 개정 Day5 단계별 계획” 문서는 찾지 못했다. 이번 감사는 사용자가 지정한 개정 Step 2~4(영상 Grab/ROI, JSONL 로그 정리, 조건부 재진단)를 후속 범위로 취급하며 원계획의 반례 평가 요구를 유지한다. 개정 문서 위치가 별도로 존재한다면 후속 Step 2 착수 전에 기준 문서로 연결해야 한다.

Day4는 [최종 보고서](day4-step5-final-verification.md#L278)의 제한을 포함해 `DAY4_DONE`이다. 대표 네 실제 E2E 성공은 Day4 범위의 증거이지, 반복 반례 평가 완료 증거가 아니다.

## B. Day4 기준선과 증거의 구분

Day4 오프라인 결과는 전체 **1089 PASS / 0 FAIL / 4 SKIP / 경고 2건**이다. 이번 감사에서는 테스트를 실행하지 않았다. 이전의 Agent/정책 테스트는 Fake SDK·MockTransport 및 저장소 fixture로 호출·Evidence·검증 계약을 확인한다. 실제 Gemini Trace는 특정 단일 회차에서 모델이 실제로 선택한 도구를 보여준다. 어느 쪽도 다른 쪽을 대신하지 않는다.

| 상황 | 기존 실제 E2E에서 확인된 도구·결과 | 이번 질문과 관련한 한계 |
|---|---|---|
| T03 `INSP-001398` | `get_inspection_result` + `analyze_image_quality`, 최종 `REINSPECT`, Fact 12개, PASS. [Trace 기록](day4-step4-gemini-validation.md#L3645) | `get_inspection_history` 호출 및 과거 밝기 분포 비교는 확인되지 않음 |
| T05 `INSP-001405` | 결과+로그 조회, `IMAGE_LOAD_FAILURE`, 17개 ERROR 사실, `ERROR` 판정 보존, PASS. [Trace 기록](day4-step4-gemini-validation.md#L5230) | 성공 fixture의 특정 오류 이벤트 경로 증거이며 로그 부재/손상 전부의 검증은 아님 |
| T06 `INSP-001406` | 결과 조회, `NORMAL`, `OK` 판정 보존, Fact 6개, PASS. [Trace 기록](day4-step4-gemini-validation.md#L6485) | 한 회차. ASGI 원문 본문은 보관되지 않았고 자연어 검토는 결정적 텍스트 재구성 기반 |

도구 동작을 네 종류로 구별한다.

- **Gemini 제안:** 조사 응답의 Function Call 이름과 인자.
- **서버 실행:** `_execute`가 allowlist·Pydantic 인자·대상 검사/제품 범위를 통과시킨 뒤 Python 메서드를 실제 실행한 Trace (`executed`, `success`, error, elapsed, Evidence ID).
- **정책 필수:** 종료 predicate 및 최종 coverage validator가 필수로 요구하는 근거. 현재 정상·경고·이미지 로드 실패 경로마다 다르다.
- **Mock 기대:** 테스트 응답 fixture가 지정한 호출. 실제 Gemini가 같은 순서나 선택을 했다는 증거가 아니다.

## C. 네 도구의 현재 호출·검증 정책

| 도구 | 반환 및 범위 | 호출 주체·제약 | 현재 정책상 역할 |
|---|---|---|---|
| `get_inspection_result` | 검사 ID의 저장 결과, allowlist 필드 | Gemini가 호출을 제안하고 서버가 검사 ID를 고정 대상과 대조 | 정상/경고/ERROR 종료 계약의 핵심 snapshot 및 Evidence |
| `analyze_image_quality` | 저장된 품질 상태·측정값·저장된 밝기 임계값 상태 | Gemini 제안 후 실행. 이미지 재로드나 임계값 재계산은 안 함 | T03 경고 predicate에서 결과와 일치하는 품질 증거를 요구 |
| `get_execution_logs` | 같은 inspection ID의 정제된 이벤트·timestamp·stage·level·metrics | Gemini 제안 후 실행. 도구는 대상 검사에 연결된 로그만 반환 | T05 필수. 경고에서는 서버 설정 `required_warning_event_codes`가 있을 때만 해당 이벤트 필수 |
| `get_inspection_history` | product alias로 요청한 제한된 동일 제품 이력 | Gemini 제안 후 alias 검증. 실제 storage 조회 시 trace에는 alias만 보임 | 허용된 선택 도구. 현재 T03 종료 정책은 이력을 필수로 요구하지 않음 |

호출은 백엔드가 시나리오별 네 도구를 일괄 강제하는 구조가 아니다. 모델 Function Call이 Python 실행의 전제이며, 서버는 허용 이름/인자/대상 범위 및 최대 라운드·호출·반복 횟수를 강제한다. 조사 종료 predicate는 이미 충분한 근거가 생긴 시점에 추가 조사 요청을 생략하게 한다. 실패 호출은 실행 Trace에 남고, 성공 결과만 Evidence Store/Fact Catalog에 들어간다. `DATA_UNAVAILABLE`은 조회 성공과 다르며, 저장소 예외·not-found 등은 실패 코드로 처리된다.

운영 제약은 `AgentLimits`에서 라운드 4, Python 호출 8, 같은 도구+인자 반복 2, 모델 요청 15초, 전체 60초, 안전 여유 2초, 도구 3초다. SDK `attempts=1`은 총 1회 시도로 재시도 0회를 뜻한다. 실제 단계별 의미와 테스트 대상은 `backend/agent/service.py`의 `_run`, `_execute`, `_request_timeout_seconds`를 확인했다.

## D. 종료 정책과 상태별 조사 흐름

- **NORMAL:** 검사 결과의 핵심 상태 6개가 일치하고 anomaly score/threshold가 유한하며 score ≤ threshold일 때 조기 종료 가능. 이력/로그 호출을 강제하지 않는다. 최종 JSON, core facts, Evidence 검증은 계속 수행한다.
- **IMAGE_QUALITY_WARNING:** 결과와 품질 도구 간 ID·상태·metric 일치 및 저장된 기준과의 일관성을 검사한다. 설정된 warning event 계약이 있으면 실제 로그 stage/timestamp를 요구한다. 과거 이력 분포 비교는 기본 필수조건이 아니다. 최종 보고서 coverage는 별도로 검증한다.
- **IMAGE_LOAD_FAILURE:** 기존 ERROR validator 재사용. 결과/로그의 성공 Trace, ID·Evidence 연결, 실제 `IMAGE_LOAD_FAILED`와 `INSPECTION_FAILED`, 필수 원천 사실 충족을 확인한다. 최종 ERROR 사실 coverage도 다시 검증한다. 관측되지 않은 지표는 `null`로 유지한다.
- **일반 ERROR/실제 `INFERENCE_FAILED`:** IMAGE_LOAD_FAILURE 전용 종료로 오인하지 않는다. 표준 ERROR 안전 경로와 bounded loop가 적용된다.
- **관련 없는 WARN/이벤트 없음:** 별도 정상 종료 유형으로 구현돼 있지 않다. Trace에 근거가 없으면 관련 원인 선택은 Evidence signal 검증에서 거부되어야 하지만, 모든 자연어 설명을 검증하는 별도 판정기는 아니다.

상세 구현은 [정상 predicate](../backend/agent/service.py#L125), [신호-원인 연결](../backend/agent/service.py#L176), [warning validator](../backend/agent/investigation.py#L42), [ERROR validator](../backend/agent/error_policy.py#L18), [load-failure 조기 종료](../backend/agent/error_policy.py#L100)에서 확인했다.

## E. T03 밝기 경고와 검사 이력 비교

저장된 T03 운영 도구가 반환하는 핵심 근거는 품질 상태, 밝기 mean/std/min/max, 크기, 그리고 저장된 경우 low/high threshold다. `threshold_status=NOT_RECORDED`이면 threshold를 만들어내지 않는다. `warning_evidence_ready`는 현재 검사 결과와 품질 결과를 비교하고, 기록된 threshold가 있으면 현재 mean과 비교한다. 이 검증은 현재 검사 내 일관성이지, 최근 여러 검사 밝기 분포와의 추세 비교가 아니다.

실제 T03 성공 Trace는 Gemini가 결과 도구와 품질 도구를 제안해 둘 다 실행한 뒤 서버가 `WARNING`으로 조사를 종료했다. 로그/이력 도구 호출은 실제 기록상 없다. `get_inspection_history`는 선언·검증·alias 범위 테스트가 있지만, Day4 성공 E2E에서 실행됐다고 볼 수 없다. 도구는 최대 1000개 저장 후보 중 valid timestamp를 정렬해 최대 20개를 반환하며, 응답도 전역 최신 이력을 보장하지 않는다고 표시한다.

결론: 원계획의 “밝기 경고 시 최근 검사 밝기 추이 추가 조회”는 **PARTIAL**이다. 이력 도구 기반 조회 기능과 도구 호출 프로토콜은 존재하지만, T03에서 실제 history 호출·현재 대비 통계/추세 계산·가설의 연결성은 검증되지 않았다. 실제 이력이 비어 있거나 `DATA_UNAVAILABLE`이면 비교는 `NOT TESTED/UNAVAILABLE`이어야 하며 임의 과거값으로 대체하면 안 된다. History는 모든 경고에서 무조건 호출할 필요가 있다는 근거는 없으나, 기존 계획을 충족하려면 최소한 의미 있는 history가 있는 조건부 케이스와 history 부재 케이스를 평가해야 한다.

`test_history_fact_cannot_support_target_lighting_hypothesis`는 history fact 하나만으로 `ILLUMINATION_CHANGE` 원인을 주장하는 것을 `EVIDENCE_MISMATCH`로 거부한다. 이는 무관한 과거 경고만으로 조명 원인을 단정하지 않도록 하는 제한이지만, 현재 밝기와 분포를 비교하는 기능의 검증은 아니다.

## F. T05 지표 부재 및 실행 실패 구분

`_record_data`는 numeric 필드가 없거나 비정상이면 null로 직렬화한다. 실제 성공 회차는 결과와 실행 로그 도구를 실행해 `IMAGE_LOAD_FAILED`, `INSPECTION_FAILED`를 확인했고, 필수 17개 최종 사실 검증과 서버 `ERROR` 판정 보존에 성공했다. `test_agent_error_policy.py`는 null을 0으로 쓰지 않는 assertion, 필수 이벤트 누락/타검사 로그/로그 저장소 실패 차단, `SKIPPED`/`UNKNOWN`만으로 모델 장애 원인·점검을 허용하지 않는 경계를 둔다.

조회 성공 후 빈 로그는 Trace의 `DATA_UNAVAILABLE`로 구분되어 오류 상황에 따라 불완전 데이터로 보고되거나 종료 정책에서 추가 조사 요구를 충족하지 못한다. 저장소 예외와 `NOT_FOUND`는 서로 다른 실패 코드이며, 성공한 분석이나 Evidence로 가장하지 않는다. 일반 실패가 IMAGE_LOAD_FAILURE로 둔갑하지 않고 실제 `INFERENCE_FAILED` 이벤트만 모델 가설을 지지할 수 있는 테스트도 있다.

결론: T05 표준 이미지 로드 실패와 필수 17개 사실 경로는 **실제 E2E VERIFIED**다. 임의 누락·타검사 로그·저장소 예외 등은 일부 Mock에서 fail-closed 확인됐다. 손상 JSONL, 모든 로그 누락 변형을 실제 Gemini로 반복 평가한 것은 아니므로 전체 실패 유형의 완전성은 주장하지 않는다.

## G. T06 판정 불변·불확실성·정답 격리

T06은 저장된 `COMPLETED/OK/OK/ALL_CHECKS_PASSED`, score 32.26792526245117, threshold 34.1442를 사용했다. 서버는 모델이 최종 결과를 바꾸도록 허용하지 않고, summary/action은 제한된 코드와 실제 fact reference로 변환한다. `NORMAL_MODEL_RESULT` 고정 문구에는 “실제 무결점 제품을 보증하지 않습니다”가 들어간다. T06 Mock 테스트는 OK snapshot, six core facts, 외부 평가 표식의 도구 응답·Evidence·Catalog·최종 변환 입력 비포함, NG/REINSPECT 변경 시도 및 unsupported fact를 확인한다. 실제 T06 최종 E2E는 Fact 6개와 `OK` 보존에 성공했다.

이 검증은 입력/전송/변환 경계와 고정 문구를 확인한 범위다. 외부 `../evaluation_private/`는 이번 감사에서 열거나 목록화하지 않았다. 실제 T06 원본 ASGI 본문이 보존되지 않아 사람의 원문 응답 독립 검토는 불가능하며, 이전 리뷰도 선택 결과와 고정 문구 재구성 기반이었다. 따라서 전체 자유 서술의 보편적 안전성을 입증했다고 말하지 않는다.

## H. 반례 A — 정상 입력과 무관한 WARN

기존 검사들은 실제 경고 상태의 품질 근거, warning code의 서버 소유 설정, 실행 로그 event의 stage/time, 잘못된 경고 카탈로그·판정 변경 차단을 검증한다. `get_execution_logs`는 inspection ID에 묶인 이벤트만 반환한다. 하지만 “정상 판정 입력 + 같은 검사에 귀속된 진단과 무관한 WARN 이벤트”를 독립 fixture로 넣고, 그 이벤트가 원인 가설로 연결되지 않는지 검증하는 명시적 테스트는 확인되지 않았다.

`_signals`는 허용 가능한 원인·점검 종류를 참조 Fact의 source field/event로 제한하며, history Fact는 밝기 원인 신호에서 제외한다. 이는 코드 기반 근거 제한이다. 그렇더라도 최종 natural-language 전체에서 인과 단정이 없다는 테스트는 별개이며, 자유 문장 출력은 제한된 code selection과 서버 고정 렌더링을 따르므로 구조/렌더링 검증과 임의 원문 판단을 구분해야 한다.

결론: 반례 A는 **PARTIAL / 신규 Mock 필요**. 검사와 무관한 WARN을 실행 로그에 두고 모델이 이를 이용해 illumination/equipment cause를 제안하는 경우, 코드가 차단하는지와 사용자 결과가 오해를 유발하지 않는지 함께 검증해야 한다. 로그 event 자체를 제거하거나 “WARN이면 무조건 history 조회”로 우회하면 안 된다.

## I. 반례 B — 관련 로그 없음 또는 도구 오류

기존 `test_missing_logs_are_returned_to_model_as_unavailable`는 로그 조회는 실행됐지만 빈 목록인 `DATA_UNAVAILABLE`을 성공 Evidence와 구분하고 Trace/Catalog에 실패를 남기는 것을 확인한다. `test_logs_failure_never_reaches_final_generation`은 저장소 예외와 not-found가 final generation에 도달하지 않도록 한다. ERROR 경로도 필수 로그 부재를 완료 불가로 만든다. 이 테스트들은 **NO_DATA와 TOOL_ERROR의 차이** 및 특정 필수 ERROR 정책에서의 차단을 검증한다.

그러나 “제품 NG 또는 이상 의심 + 정상 완료 로그만 있고 물리 원인을 지지하는 로그는 없음”을 별도 사례로 두어, NG 판정과 설비 고장 주장을 분리하고 근거 부족·추가 조회 필요성을 최종 사용자 문구까지 확인하는 전용 테스트는 확인되지 않았다. 구조적으로 unsupported cause/check는 Evidence signal에 없으면 거부된다. 이는 원인 code selection의 결정적 보장이지, 모든 원인 부재 상황에 대한 end-to-end natural-language 품질 검증은 아니다.

결론: **데이터 없음·도구 실패 경계는 일부 VERIFIED, Day5 제품 이상+정상 로그 반례는 PARTIAL**. 필요한 Mock은 성공 로그만 있는 NG/REINSPECT와 빈 로그, `DATA_UNAVAILABLE`, 저장소 `STORAGE_ERROR`를 구분한다. 가상의 이벤트를 채워 넣지 않는다.

## J. 기존 검증 매트릭스

| 검증 항목 | 기존 테스트·핵심 assertion | 실제 E2E 증거 | 상태 / 추가 필요 |
|---|---|---|---|
| T03 밝기 경고 | `test_agent_service.py::test_brightness_hypotheses_are_grounded_without_injection_information`: brightness facts가 hypothesis를 지지하고 주입 metadata가 최종 context/result에 없음. Warning integration은 quality fact coverage 검증 | T03 결과+quality 실제 호출, Fact12, REINSPECT | **VERIFIED** 기본 경로. 반례 수치·threshold 부재 변형은 tests 보강 여부 점검 |
| T03 이력 비교 | history bound/alias 테스트; history만으로 target lighting cause 금지 | 성공 Trace에 history 없음 | **PARTIAL**; 실제 comparative history case + no-history case 필요 |
| T05 null 보존 | `test_agent_error_policy.py::test_unmeasured_null_is_never_numeric_zero` | 실제 17 facts에 미측정 null, 0 대체 없음 | **VERIFIED** 표준 경로; 변형 손상 로그는 일부만 검증 |
| T05 로그 조사 | ERROR policy missing/wrong-inspection/log-failure assertion | 실제 get_execution_logs 성공, 두 필수 이벤트, ERROR17 PASS | **VERIFIED** 표준 경로 |
| T06 판정 불변 | `test_real_sdk_mock_transport_preserves_isolated_normal_path`: NG/REINSPECT mutation rejected; API snapshot checks | 실제 snapshot/final OK 유지 | **VERIFIED** 저장 판정 계약 |
| T06 불확실성 표현 | limitation/summary restrictions and T06 mock; actual fixed renderer reconstruction | 실제 선택 원인0, 권고1, 고정 limitation; 원문 미보관 | **PARTIAL** 원문 자유문장 독립검토 불가 |
| 무관 WARN | warning validator checks scope/event contract; relevant cause evidence gating | 해당 실제 반례 없음 | **NOT TESTED** 명시적 counterexample 필요 |
| 관련 로그 없음 | `test_missing_logs_are_returned_to_model_as_unavailable`; ERROR missing event tests | T05 성공은 logs present | **PARTIAL** NO_DATA 계약은 검증, NG+normal logs 시나리오 없음 |
| 도구 오류 | lookup failure and logs failure tests check failed trace/no false success | 실제 성공 회차만 해당 | **VERIFIED** selected error paths; all storage corruption cases 없음 |
| 불필요한 추가 조사 | normal fast path; warning stops after result+quality; load failure stops after result+logs | T01/T06 NORMAL, T03 warning, T05 image-load | **VERIFIED** 해당 세 표준 종료; optional history/error variants는 범위 제한 |
| 허위 Evidence | unsupported token/evidence/pointer/value/event mismatch rejected | 네 E2E 실제 Fact/Pointer 검증 PASS | **VERIFIED** structural provenance; causal relevance remains scenario-specific |
| 자연어 원인 단정 | enum cause/check signals + fixed server text; unsupported references rejected | 실제 일부 fixed output review; T06 raw body unavailable | **PARTIAL** free-form/general natural language not fully evaluated |

함수 assertion의 존재를 실제 모델 행동과 동일시하지 않는다. 실제 Trace는 [T03](day4-step4-gemini-validation.md#L3645), [T05](day4-step4-gemini-validation.md#L5230), [T06](day4-step4-gemini-validation.md#L6485)에 기록됐다.

## K. 이미 검증된 부분과 필요한 추가 평가

중복하지 않아도 되는 기준선: 결과/품질 조합의 T03 기본 경고, T05의 IMAGE_LOAD_FAILURE 17개 사실 및 null, T06 저장 OK/Fact/Evidence/판정·GT 경계, 도구 이름·인자 allowlist, 반복/라운드 상한, unsupported Evidence/Pointer 거부, NORMAL·WARNING·IMAGE_LOAD_FAILURE 표준 조기 종료.

Day5에서 추가로 확인할 것은 **상황별 정책 간 경계**다. 특히 history comparator 미검증, 관련 없는 WARN의 인과 유도, 제품 이상+정상/빈/실패 로그 상황의 최종 근거 부족 표현이다. 전체 기능을 다시 복제하는 테스트보다 아래 fixture 조합에 집중한다.

## L. 최소 반복 반례 평가 계획 — 구현하지 않음

최소 다섯 사례를 평가 단위로 고정한다. 원계획의 “최소 4개”를 충족하면서 T03 history 비교를 독립 평가하고, T05/T06의 이미 강한 경로는 기준선 재사용으로 중복을 줄인다.

| ID | 입력 fixture 및 분기 | 통과 조건 |
|---|---|---|
| CE-01 T03 history available | 현재 WARNING_LOW_BRIGHTNESS + 같은 product의 timestamp가 있는 최근 정상 검사 여러 건 | Gemini가 필요 시 alias로만 history 호출; 실제 반환값만 비교; trend를 인과 단정으로 승격하지 않음; Evidence/검사 범위 정합 |
| CE-02 T03 history absent | 같은 경고, history 성공 빈 목록 또는 `DATA_UNAVAILABLE` | 과거 분포를 생성하지 않음; 비교 불가를 밝힘; 현재 측정 기반의 한정 설명 유지 |
| CE-03 T05 measurement absent | T05 기준 결과/로그 및 null measurement, 핵심 이벤트/17 fact 검증 | logs 선택·실행과 null 보존, SKIPPED=모델 고장 금지. 기존 회귀를 반복 실행하지 않고 해당 validator fixture를 재사용 |
| CE-04 unrelated WARN | 정상 판정 + 같은 inspection의 비관련 WARN event + 관련 인과 필드 부재 | WARN을 사실로만 표시할 수 있고 cause/check의 인과 연결은 거부; 장비 고장 단정 없음; 불필요한 도구 조회 없음 |
| CE-05 suspected NG, normal/absent/error logs | 판정 NG 또는 이상 의심 + 성공한 정상 로그; 분리 variant로 빈 로그와 tool error | 제품 판정과 workflow 원인을 분리; NO_DATA/TOOL_ERROR trace 구분; 이벤트 생성 금지; unsupported cause/claim 거부 또는 안전 실패; bounded request |

각 Mock 사례를 **3회 고정 seed**로 반복해 결과 변동·중복 실행·호출 예산을 확인할 수 있다. Deterministic Python validator, tool routing fixture, Exact Fact/Pointers, server verdict immutability, fake SDK request count는 Mock에서 충분히 확인 가능하다. 다섯 사례를 매번 세 번씩 실제 Gemini에 보내는 것은 필요하지 않다. 실제 Gemini는 모델 선택의 분산과 자연어 변동을 확인하려면 별도 표본이 필요하며, Step 1에서는 승인되지 않았고 수행하지 않았다.

반복 결과는 회차별 비민감 JSONL/CSV에 `case_id`, fixture version/hash, run index, proposed calls, executed tools, trace/error, evidence IDs, selected facts, cause/check codes, verdict before/after, request count/latency, pass dimensions, reviewer note를 기록한다. 원본 평가 라벨은 evaluator 전용 별도 경계에 두고 Agent fixture·프롬프트·도구·Fact Catalog로 복사하지 않는다. 재현성은 같은 fixture와 seed를 쓰고, 이미 검증된 계약 assertion은 공통 helper로 재사용하되 서로 다른 사례의 outcome을 합산하거나 중복 통계로 세지 않는다.

실제 Gemini를 쓸 경우 별도 승인서에 회차, 최대 분석 수, 최대 HTTP 요청 수, timeout, 재시도 0, 비용 한도/청구 확인 여부, 응답 보관·민감정보 제거 정책을 명시해야 한다. 이 감사에서는 실호출 0회다.

## M. 영상 Grab/ROI 작업 전 Agent 데이터 계약

현재 Tool은 `inspection_id`로 저장 검사·로그를 연결하며, 로그 도구는 각 로그의 inspection ID를 검사하고 `product_id`는 이력 전용으로 사용한다. 따라서 새 영상 검사도 매 Grab/ROI 검사마다 새롭고 유일한 `inspection_id`를 발급하고, 기존 schema의 `product_id` 의미를 보존해야 한다. ROI 기반 PatchCore 결과는 서버가 저장한 inspection snapshot이어야 하며 Agent는 이미지 경로나 ROI 좌표를 임의로 열지 않는다.

새 영상 실패 원인을 Agent가 설명하려면 단계 이벤트(event_code, stage, timestamp, level, 필요한 정제 metrics), 저장 상태와 최종 사유의 계약이 필요하다. 기존 `IMAGE_LOAD_FAILURE` 정책은 이미지 load 실패 두 이벤트와 ERROR 17 facts에만 한정돼 있다. 신규 `VIDEO_SOURCE_UNAVAILABLE`, `FRAME_GRAB_FAILED`, `ROI_INVALID` 등을 기존 코드와 같은 뜻으로 취급하지 말고, Step 2~4에서 별도 계약과 허용 원인을 정한 후 테스트해야 한다. 로그 `product_id` 제거는 Agent 도구가 검사 ID 필터링에 의존하므로 가능하지만, 이력 도구의 동일 제품 범위 조회에는 product ID가 필요하다. 해당 값을 모든 이벤트에서 제거할지, 비식별 별도 관계로 유지할지 데이터 계약 결정을 먼저 해야 한다.

재진단은 서버가 새 검사와 로그를 확정·저장한 뒤에만 트리거해야 한다. 저장 전 Agent를 부르거나, 이전 검사 Trace를 새 ROI 결과에 재사용하거나, 새 로그의 제품 식별자 누락으로 history 범위를 잘못 확대하지 않도록 한다. 영상 파일/장치가 실제 존재하는지 확인하는 작업은 이번 감사 범위에서 하지 않았다.

## N. 다음 단계와 우선순위

1. **Step 2 착수 전:** 2026-10-15 개정 계획의 canonical 파일/기준을 등록하고, 영상 검사·로그 데이터 계약(inspection/product IDs, stage/event, ROI 좌표계, source/error taxonomy)을 확정한다.
2. **Agent 평가 준비:** CE-01/02 history 비교 기준과 근거 정렬, CE-04 무관 WARN, CE-05 NG+normal/no/error logs를 offline fixture 사례로 설계·승인한다. Step 1 범위에서는 구현 금지였으므로 아직 테스트 없음.
3. **T03 조건부 조사 결정:** history 호출을 항상 강제하기 전에 실제 history coverage/유효 timestamp 비율과 bounded tool budget을 평가한다. 데이터가 불충분하면 추세 비교 문구를 금지한다.
4. **영상 Step 2~4:** 저장/도구 contract를 먼저 구현하고, 신종 오류별 안전 종료 조건과 Agent 재진단 트리거를 명시적으로 연결한다. 기존 판정 및 ERROR 정책은 별도 승인 없이는 바꾸지 않는다.
5. **실제 Gemini 반복 평가:** Mock 결과 및 고정 검증 rubric 검토 뒤 별도 사용자 승인, 회차/요청/비용 상한을 설정하고 수행한다.

## O. 이번 감사 변경·실행 범위

- 생성 문서: `docs/day5-step1-agent-counterexample-audit.md` 하나.
- 코드·prompt·schema·tests·운영 JSONL·이미지·video·READY·E2E 기록은 수정하지 않았다.
- 외부 Ground Truth 경로를 열거나 나열하지 않았다.
- Agent 테스트·전체 pytest·Gemini API·새 검사/READY/실행은 수행하지 않았다.
- Git add/commit/push/reset 0건.

