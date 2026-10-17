# Day5 Step 1-B — 조건부 조사·반례 Mock 반복 평가

- 검증일: 2026-10-17
- 판정: **PARTIAL — 오프라인 고정 계약 Mock PASS, T03 추세 비교와 실제 Gemini 자율 선택은 미검증**
- 실제 Gemini API / Agent 분석 / 새 검사 / READY 생성: 0회

## A. 목적과 Day5 계획 대응

이 평가는 [기존 Day5 반례 감사](day5-step1-agent-counterexample-audit.md)에서 PARTIAL/NOT TESTED로 분류한 T03 이력 비교, 정상 검사와 무관한 WARN, 제품 이상 의심과 정상/빈 로그, 도구 오류를 합성 저장소와 Fake SDK로 반복 검증한다. 2026-10-17 작업 중 [Day4 완료 및 Day5~7 로드맵 요약](day4-completion-and-day5-roadmap-summary.md)이 새로 나타나 읽기 전용으로 확인했다. 이 요약은 기존 Day5 조건부 조사·반례 평가와 개정 Day5 영상 파이프라인을 함께 명시한다. 해당 파일 및 병렬 발표 자료는 수정하지 않았다.

Day4의 T01/T03/T05/T06 실제 Gemini 성공 기록은 과거 특정 회차 결과로 유지한다. 이 Mock은 실제 모델의 선택 확률·자연어 변동·실서버 동작을 증명하지 않는다.

## B. 변경 파일과 실행 환경

- 신규 테스트: `tests/test_agent_day5_counterexamples.py`
- 신규 결과 문서: `docs/day5-step1b-counterexample-mock-validation.md`
- 운영 `backend/`, 기존 테스트, 프롬프트, Schema, JSONL, 모델, 임계값은 수정하지 않았다.
- pytest는 Python 3.11 `vision-insight`에서 실행했다. 각 실행은 별도 임시 출력/저장 경로를 사용하고, HTTPX 네트워크 transport 및 Gemini SDK 경계를 차단했다. 평가 전용 경로 접근을 금지하는 audit hook도 테스트 프로세스에 적용했다.
- 실제 Gemini SDK의 인증 요청은 발생하지 않았다. 테스트의 “Mock 모델이 호출을 반환함”과 서버의 `tool_execution_trace.executed`는 별도 assertion으로 확인했다.

## C. 신규 테스트 설계 및 반복 결과

5개 핵심 사례를 각각 최소 3회 독립 parameterized run으로 실행했다. Case 2~4는 정상 동작과 부정 주장/근거 부족 변형을 각각 확인했다. 아래 성공 횟수는 정해진 테스트 assertion의 통과 횟수이며, 실제 Gemini 행동의 성공률이 아니다.

| 사례 | 반복별 결과 | 확인한 Mock 제안과 실제 Python 실행 | Evidence/Fact 및 판정 | 자연어 범위 | 판정 |
|---|---|---|---|---|---|
| 1. T03 경고 + 과거 이력 있음 | 1 PASS · 2 PASS · 3 PASS | Mock이 result 조회 후 `analyze_image_quality`와 alias/limit이 유효한 `get_inspection_history`를 요청. 실제 세 도구 실행, history는 `TARGET-PRODUCT` alias로 저장소에 조회 | E0001~E0003, 현재 품질 측정과 실제 합성 이력의 mean/timestamp Fact를 실제 Pointer로 선택. REINSPECT 유지. 조회 라운드 2회 후 final로 진행 | 조명 가설은 제한된 코드 선택이고 서버 문구는 고정. **추세 통계 계산은 하지 않았고 검증하지 않음** | 도구·출처 경계 PASS; trend 기능 PARTIAL |
| 2. T03 경고 + 이력 없음 | 정상 1~3 PASS; 조작 Fact 거부 1~3 PASS | Mock이 history 조회를 요청. 빈 결과는 `DATA_UNAVAILABLE`; 이후 무도구 응답으로 조사를 끝내고 final 생성 | 실패 trace에는 Evidence ID 없음. 정상 결과에 history Fact 없음, 자동 `RECORDS_INCOMPLETE` 한계 유지, REINSPECT 불변. K9999 이력 Fact 시도는 `EVIDENCE_MISMATCH` | 과거 통계 생성 없음. 한계는 서버 제한 문구 | PASS |
| 3. 정상 검사 + 무관 WARN | 안전 출력 1~3 × 동일 검사/타 검사; 인과 주장 거부 1~3 × 동일 검사/타 검사 모두 PASS | Mock이 result+logs를 같은 Function Call 응답으로 제안. 같은 검사 로그는 실행되고, 타 검사 ID 로그는 필터되어 빈 조회가 됨 | 동일 검사 WARN Fact만으로 `ILLUMINATION_CHANGE`를 고르면 거부. 타 검사 로그는 `DATA_UNAVAILABLE`이며 Evidence 없음; 없는 Fact 참조도 거부. 안전 보고는 OK 유지, causes 없음 | JSON 임의 문장 검증으로 확대하지 않음. 허용된 cause/check 코드와 서버 고정 문구 범위 | 구조적 근거 제한 PASS; 임의 자유 문장 일반화는 미검증 |
| 4. NG 의심 + 정상 또는 빈 로그 | 안전 출력 1~3 × 정상/빈; 허위 획득 실패 원인 거부 1~3 × 정상/빈 모두 PASS | Mock이 result 후 logs 조회, 다음 조사 응답은 종료 텍스트. 정상 로그만 있으면 E0002 발급, 빈 로그는 `DATA_UNAVAILABLE` | NG/최종 NG 유지, 정상 로그만으로 물리 원인 없음, 빈 로그는 성공 Evidence로 취급하지 않음. 허위 `IMAGE_ACQUISITION` 원인은 `EVIDENCE_MISMATCH` | 서버 고정 NG 요약과 수동 재검 권고. 근거 없는 원인 문장은 코드 선택 단계에서 거부 | PASS |
| 5. 조회 도구 저장소 오류 | 1 PASS · 2 PASS · 3 PASS | Mock이 결과+로그 Function Call을 제안. 실제 결과 조회 성공 후 logs 저장소 예외가 발생 | E0001만 성공 Evidence. 로그 Trace는 실행됨/실패/`STORAGE_ERROR`/Evidence 없음. 모델 재요청·최종 생성 없이 즉시 실패, 저장소의 NG 판정 불변 | 예외 내부 경로·비밀 표식이 결과에 노출되지 않음 | PASS |

**신규 모듈 합계:** 36 parameterized test executions PASS. 5개 평가 사례 각각 최소 3회 반복 조건을 충족했다. Case 2–4의 양성/음성 하위 run도 따로 셌다.

## D. 주장과 검증 범위

### 확인된 것

- Gemini가 제안했다고 fixture가 지정한 도구와 서버가 실제 실행한 Python 도구를 나눠 assertion했다.
- `get_inspection_history`의 product alias, limit, 실제 저장소 범위와 반환된 값의 Evidence/Pointer를 검사했다. 빈 목록은 `DATA_UNAVAILABLE`, 예외는 `STORAGE_ERROR`로 구별했다.
- 실패한 Evidence를 성공 Fact처럼 인용하거나, 다른 검사 로그를 연결하거나, 관측되지 않은 `IMAGE_LOAD_FAILED` 원인을 추가하면 거부되는 것을 확인했다.
- 서버의 저장된 T03 REINSPECT, T01 OK, 합성 NG 최종 판정이 모델의 보고서 선택으로 바뀌지 않는 것을 확인했다.
- 무관 WARN이나 정상 로그는 로그가 존재한다는 사실만으로 illumination/model cause를 지지하지 않는다. 관련 Fact가 없으면 원인 선택이 거부된다.
- 빈 history/빈 logs의 경우 무한 재조회 없이 상한 내 조사 및 최종 생성/안전 실패로 끝났다. 저장소 예외는 성공 분석으로 감추지 않았다.

### 확인하지 않은 것

- Mock이 도구를 요청한 것은 **실제 Gemini가 T03에서 history를 스스로 선택한다는 증거가 아니다**. 실제 T03 성공 회차는 결과+품질 도구만 사용했다.
- Case 1은 실제 과거 측정값을 Evidence로 카탈로그화하고 보고서 Fact로 선택하는 것을 확인했다. 시스템이 다건 평균/범위/추세를 계산하거나 이를 자동으로 조명 원인과 연결하는 기능은 확인되지 않았고 이번에 추가하지 않았다.
- 서버는 임의 자연어를 정규식으로 검사하지 않는다. 이 Agent 경로는 Summary/Cause/Check/limitation code를 서버 텍스트로 렌더링하므로 테스트는 잘못된 구조화 원인 선택 거부와 고정 문구를 평가했다. 임의의 원문 자연어 생성에 대한 별도 평가를 했다고 주장하지 않는다.
- 실제 Gemini의 도구 선택, 장기 반복 안정성, 응답 지연/비용은 평가하지 않았다.

## E. 기존 T05/T06·Agent 회귀

기존 관련 회귀를 새 테스트와 분리해 실행했다.

| 테스트 선택 | 결과 |
|---|---:|
| AgentService, tools, warning integration, ERROR policy, efficiency, image-load stop, reporting integration, T06 isolation, T05 timeout configuration, timeout measurement (`10` modules) | **421 PASS** |
| 전체 `tests` (한 번 실행) | **1125 PASS / 0 FAIL / 4 SKIP / 0 XFAIL / 0 XPASS / 경고 2건, 31.24초** |

전체 테스트는 2026-10-17 현재 작업 트리에서 새로 실행했다. 기존 기준 1089 PASS와 혼동하지 않는다. T05 17개/null/SKIPPED 안전성 및 T06 판정·정답 격리 테스트는 Agent 전체 회귀와 전체 suite에 포함됐다. 실제 E2E나 원본 검사 데이터 수정은 없었다.

전체 pytest의 기존 4 SKIP은 다음 Day3.5 T03 이미지 통합 테스트다. 임시 격리 `TEST_DATA_DIR`에 T03 주입 이미지가 등록되지 않아 skip됐으며 이번 Mock 테스트가 대체하지 않는다.

- `tests/test_day3_5_integration.py::test_t03_brightness_reduced_inspection` — 주입 이미지 등록 없음.
- `tests/test_day3_5_step4.py::test_image_quality_warning_decision_confidence_policy` — fault-injected image 없음.
- `tests/test_day3_5_step4_5.py::test_t03_final_verdict_quality_warning_reinspect` — T03 주입 이미지 없음.
- `tests/test_day3_5_step4_5.py::test_workflow_product_ng_under_quality_warning` — 같은 fixture 부재.

이는 이미지 실제 처리 통합 경로 미검증이지 Day5 Agent Mock PASS로 간주하지 않는다.

## F. 환경·diff 검사·작업 트리

- `python -m pip check`: `No broken requirements found.`
- `git diff --check`: **전역 검사에서 실패 표시**. 병렬로 변경 중인 `presentation/presentation-review-checklist.md`와 `presentation/slide-outline.md`의 trailing whitespace 및 관련 CRLF 알림이 출력됐다. 두 파일은 이번 작업에서 수정하지 않았으며 그대로 보존했다.
- 이번 신규 테스트와 감사 기준 문서에는 trailing whitespace가 없다. 테스트는 전용 임시 디렉터리로 출력을 보냈다.
- 작업 시작 시 이미 수정돼 있던 발표 파일과 `.tmp_measurement_regressions/`를 건드리지 않았다. 진행 중 새로 나타난 `docs/day4-completion-and-day5-roadmap-summary.md`도 읽기 전용으로 확인해 보존했다.
- Git add/commit/push/reset은 0건이다.

## G. 최소 보완 판단 및 다음 단계

이번 Mock은 기존 코드의 근거 제한, 데이터 부재/도구 실패 분리, 호출 상한, 판정 불변을 검증했고 운영 코드 수정은 필요하지 않았다. 다만 테스트 범위에서 발견한 기능 한계는 남는다.

1. T03 실제 이력 추세 요구를 완수하려면, 합성 history 여러 건에서 평균/범위/최근 기준을 어떻게 산출할지와 최신 timestamp/비교 불가 정책을 별도 승인·설계해야 한다. 현재 테스트는 기록된 값 조회와 provenance만 검증한다.
2. 정상 판정 직후 logs와 같은 추가 도구가 하나의 Gemini 응답에서 함께 제안되면 서버는 그 응답의 호출들을 실행한 뒤 종료 predicate를 적용한다. 추가 라운드는 억제되지만 같은 batch 안의 선택적 호출까지 미리 차단하지는 않는다. 비용/효율 요구가 생기면 최소 변경안을 별도 승인받아야 한다.
3. 실제 Gemini가 history/로그 도구를 언제 선택하는지와 생성 결과의 안정성은 offline Mock으로 결론 낼 수 없다. 필요하면 이 5개 fixture에 한정한 별도 승인, 분석·HTTP 상한, timeout, 재시도 0, 비용 확인 정책 아래 실서버 평가를 계획한다.
4. 영상 Grab/ROI Step 2~4 전에 검사 ID·로그 연결, 새 영상 오류 event/stage 계약, `product_id` 정리와 history 조회 관계, 저장 완료 후 재진단 트리거를 확정한다. 영상 구현은 이번 작업에서 수행하지 않았다.

따라서 **Step 1-B의 승인된 오프라인 Mock 평가 범위는 완료**, 전체 Day5 Agent 조사/실제 Gemini 반례 평가 상태는 **PARTIAL**이다. 실제 모델 자율 도구 선택 및 T03 밝기 추세 구현 검증을 완료했다고 표시하지 않는다.

