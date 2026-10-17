# Day5 Step 1-C Phase B — T03 저장 밝기 이력 비교

- 검증일: 2026-10-17
- 최종 상태: **COMPLETE — 승인된 서버 구현 및 오프라인 계약 검증 범위**
- 최신 전체 pytest: **1175 PASS / 0 FAIL / 4 SKIP / XFAIL·XPASS 0 / 경고 2건, 28.64초**
- 실제 Gemini API 요청, 신규 READY, 실행 잠금, 실제 E2E 분석: **0건**
- 실제 Gemini의 자율 도구 선택·새 Function Declaration의 실서버 수락·언어 품질·반복 안정성은 NOT TESTED.

## A. 목적 및 기준

[Step 1 감사](day5-step1-agent-counterexample-audit.md)와 [Step 1-B 평가](day5-step1b-counterexample-mock-validation.md)는 과거 검사 mean/timestamp의 조회·Evidence 연결을 확인했지만, 현재 밝기와 과거 mean들의 평균/min/max/차이는 계산하지 않았다. 기존 Day5의 조건부 추가 조사 요구를 충족하기 위해 이 부분만 구현했다.

Day4의 공식 완료 및 기존 T01/T03/T05/T06 실제 Gemini 기록은 변경하지 않았다. 이전 전체 1125 PASS는 과거 기준이며, 이번 전체 결과와 구분한다. Phase A의 T03 동일 제품 과거 91건은 이번 집계의 고정 표본 수로 사용하지 않는다. 각 조회가 실제 선택한 표본 수만 보고한다.

## B. 선택한 구조 및 변경 파일

기존 4개 도구를 유지하고 `get_inspection_history`에 선택적 `inspection_id`를 추가했다. 기존 `data` 리스트를 보존하면서, 비교 요청에만 최상위 `brightness_comparison`을 추가한다. AgentService가 서버 정책으로 추가 조회할 때도 기존 `_execute`의 allowlist·인자·제품 범위·호출 상한·thread pool·timeout·Evidence 발급 경계를 그대로 사용한다.

| 수정 파일 | 실제 함수/계약 및 목적 |
|---|---|
| `backend/agent/schemas.py` | `HistoryArguments`, `ObservedFact`, `ToolExecutionTrace`: 선택적 대상 검사 ID, 비교 summary 포인터, 호출 출처·실제 비교 대상 추가 |
| `backend/agent/tools.py` | `_brightness_comparison`, `InspectionTools.get_inspection_history`: 저장 값 필터링·집계 및 하위 호환 응답 |
| `backend/agent/reporting.py` | `_verified_comparison`, `_build_catalog`: 현재 snapshot 바인딩·통계 재계산·실제 leaf 카탈로그 |
| `backend/agent/investigation.py` | `_warning_evidence_ready`: 검증된 history 또는 DATA_UNAVAILABLE 이후 WARNING 종료 허용 |
| `backend/agent/service.py` | `_ensure_warning_history`, `_run`, `_execute`, `_verify_report`, `_report_contents`: 조건부 1회 조회·출처·대상 검증·최종 재검증 및 고정 제한 문구 |
| `tests/test_agent_history_comparison.py` | 신규 테스트 50개 |
| `tests/test_agent_day5_counterexamples.py` | 기존 36개 유지. T03의 불필요한 readiness 응답 제거 및 실제 3회 Mock 요청 계약 반영 |
| `tests/test_agent_warning_policy_experiment.py` | 빈 이력 fixture 명시, DATA_UNAVAILABLE Trace 검증, 실행 순서 차이에 따른 Evidence ID와 관측 내용 구분 |
| `tests/test_agent_warning_policy_integration.py` | WARNING 정책 이력 조회와 조기 종료의 새 Trace·요청 수 검증 |
| `tests/test_agent_efficiency.py` | WARNING에서 실제 추가 Python history 실행 확인 |
| `tests/test_agent_final_request_experiment.py` | 원격 504/로컬 timeout 오류 검증에 정책 history Trace 반영 |
| `tests/test_agent_operating_timeouts.py` | 30초 timeout·재시도 금지 assertion 유지, 정책 Trace 추가 |
| `tests/test_agent_report_request.py` | 최종 입력 Trace의 명시적 origin/비교 대상 필드 검증 |
| `tests/test_agent_reporting_integration.py` | history 빈 목록 fixture 및 성공/데이터 부재 구분 |
| `tests/test_agent_validation_measurements.py` | Gemini 요청 수와 실제 Python 실행 수를 구분하고 성공 Evidence만 계산 |
| 본 문서 | 구현 및 검증 결과 기록 |

`backend/vision.py`, 검사 판정 로직, `backend/config.py`, 프롬프트, `scripts/`, README 및 Day4 문서는 수정하지 않았다.

## C. 레거시 history 계약

- `get_inspection_history(product_id, limit=5)`의 인자 의미, `data` 리스트, 정렬 및 기존 `/data/0/metrics/mean` 같은 포인터는 유지한다. 추가 인자를 필수로 만들지 않았다.
- `get_inspection_history(product_id, limit=5, inspection_id=...)`는 같은 레거시 리스트와 함께 `brightness_comparison`을 반환한다.
- 레거시 `data`는 종전처럼 최근 후보의 리스트다. 현재/미래 검사 등이 들어갈 수 있으므로 비교 통계에는 이 리스트를 무조건 사용하지 않는다. 비교 표본은 별도 `brightness_comparison.samples`에 정확히 보관한다.
- Gemini에는 제품 alias `TARGET-PRODUCT`만 전달한다. `_execute`가 실제 제품 ID로 치환하고 비교 대상 검사 ID를 현재 요청과 검증한다. WARNING의 레거시 모델 제안에도 Python 호출에만 현재 검사 ID를 보충한다. Trace의 `arguments`는 모델 제안을 보존하고 `comparison_inspection_id`로 실제 적용 대상을 표시한다.
- `_context_view`를 통해 비교의 current/samples에서도 실제 product_id는 alias로 바뀌고 image_id는 제거된다.

## D. 계산, 필터와 조회 범위

`_brightness_comparison()`은 원본 이미지를 열지 않고 저장된 `metrics.mean`을 사용한다. 포함 조건은 다음과 같다.

1. 동일 제품, 유효한 검사 ID, 대상 검사 자신이 아님.
2. 유효한 timezone 포함 timestamp이며 대상 검사보다 엄격하게 과거임. 같은 시각도 제외한다.
3. COMPLETED이고 영상 품질이 NORMAL 또는 밝기 WARNING이며 최종 ERROR가 아님.
4. mean이 실제 int/float, finite, 0–255. bool/string/null/누락/NaN/Infinity는 제외한다.
5. width/height/channels가 현재의 유효한 입력 크기와 일치함.
6. 동일 검사 ID가 후보 집합에서 중복되면 해당 ID의 모든 항목을 제외한다. 충돌한 중복 중 임의의 하나를 고르지 않는다.

동일 제품 저장 후보 최대 1,000건에서 **필터 → timestamp/검사 ID 최신순 정렬 → limit(1–20)** 순으로 선택한다. 동시각이면 검사 ID로 결정적으로 정렬한다. 같은 조건을 만족해도 limit 밖의 표본은 평균에 포함하지 않는다. `metadata.scan_limit`, `candidate_count`, `scan_limit_reached`, `global_latest_guaranteed=False`는 후보 범위의 한계를 보존한다.

계산 필드는 `summary.current_mean`, `sample_count`, `historical_mean`, `historical_min`, `historical_max`, `absolute_mean_difference`다. 마지막 값은 **|현재 mean − 과거 평균|**이다. 평균은 저장된 값의 `math.fsum(values) / sample_count`이며 추가 품질 임계값이나 판정 규칙은 없다. 반환 표본 전체를 Evidence에 보관하고 동일 표본으로 재계산한다.

## E. 표본 수와 측정 조건 한계

| 상태 | 실제 의미 및 처리 |
|---|---|
| `NO_HISTORY` | 동일 제품 후보 없음. 기존 `DATA_UNAVAILABLE`, `ok=False`, data=[] 유지. 계산된 과거 값은 null이며 성공 Evidence를 발급하지 않음 |
| `NO_COMPARABLE_HISTORY` | 후보는 있지만 유효한 비교 표본 0건. 조회 성공 Evidence에 sample_count=0, 평균/min/max/차이=null 보존 |
| `CURRENT_UNAVAILABLE` | 현재 mean/시각/크기가 유효하지 않음. 과거 통계 생성하지 않음 |
| `SINGLE_OBSERVATION` | 표본 1건과의 제한적인 비교. 분포·장기 추세를 의미하지 않음 |
| `DESCRIPTIVE_SUMMARY` | 표본 2건 이상에 대한 제한된 기술통계 |

크기 일치는 비교를 위한 필요 조건이며 알고리즘·ROI 버전의 완전 일치 증거는 아니다. 현재 저장 계약에는 해당 버전이 없으므로 `summary.scope=STORED_VALUES_ONLY_UNVERIFIED_MEASUREMENT_CONTRACT`를 카탈로그에도 전달한다. 현재와 과거 값이 같아도 설비 정상성·독립 촬영·추세를 증명하지 않는다. 서버 최종 응답에는 이 제한을 고정 문구로 추가한다.

저장소 예외는 기존 `STORAGE_ERROR`로 분석 실패 처리하며, DATA_UNAVAILABLE와 구분한다. 원래 예외의 비밀값·내부 경로는 전달하지 않고 해당 실패 Trace에는 Evidence ID를 발급하지 않는다.

## F. Evidence, Fact 및 JSON Pointer

- 비교는 실제 `get_inspection_history` Python 도구 결과에 포함된다. 도구가 성공한 경우에만 기존 순번 기반 Evidence ID가 발급된다.
- 기존 카탈로그 leaf를 먼저 모두 등록하고 비교 summary leaf를 뒤에 추가한다. 기존 data 포인터를 재해석하거나 과거 산출물의 Fact/Evidence ID를 변경하지 않는다.
- 새 포인터 예: `/brightness_comparison/summary/historical_mean`, `/brightness_comparison/summary/sample_count`. 허용 범위는 비교 summary로 한정한다.
- `_verified_comparison()`은 current가 현재 snapshot과 정확히 일치하는지, Trace의 대상 검사·요청 limit·후보 수·표본 수가 맞는지 확인한다. 저장된 Evidence 표본으로 필터·정렬·통계를 다시 계산하고 실제 비교 객체와 타입을 포함한 JSON 일치를 검증한다.
- `_verify_report()`에도 재계산 검증을 연결하여 직접 DiagnosisDraft를 검증하는 경로 역시 허위 통계를 허용하지 않는다. 기존 JSON 파싱·Pydantic·Fact ID·Evidence ID·포인터·관측값 검증을 유지한다.
- 원본 저장소를 최종 단계에서 다시 조회하지는 않는다. 서버가 발급한 Evidence 표본의 재현성과 현재 snapshot 바인딩을 검증하는 계약이다.
- 최종 모델은 제공된 카탈로그 토큰을 선택한다. 비교 정보를 입력에 제공하지만 모델이 모든 비교 항목을 최종 Fact로 선택하도록 강제하지는 않는다. 신규 성공 Mock은 비교 summary를 선택해 실제 Fact 연결까지 검증한다.
- `_signals()`의 history Fact 제외는 유지한다. history 통계만으로 조명/설비 고장을 원인 코드의 근거로 선택하면 EVIDENCE_MISMATCH다.

## G. WARNING 조건부 조회와 호출 출처

적용 범위는 기존 `warning_report_scope`: COMPLETED / 모델 OK / 결함 검사 COMPLETED / 밝기 WARNING / REINSPECT / IMAGE_QUALITY_WARNING다. 제품 범위와 성공한 품질 조회가 있을 때만 필요하다.

Gemini가 history를 이미 제안·실행했다면 재조회하지 않는다. 제안하지 않았다면 결과·품질 및 필수 로그의 준비가 끝난 시점 또는 최종 생성 직전에 `_ensure_warning_history()`가 기존 `_execute()`로 최대 1회 요청한다. 필수 로그 조사가 남아 있을 때는 정책 조회를 미뤄 후속 모델 제안 기회를 보존한다.

- `origin=GEMINI`: 모델이 제안한 호출. WARNING 비교의 대상 ID는 서버에서 검증·보충한다.
- `origin=BACKEND_POLICY`: 백엔드가 보장한 history 조회. 모델의 자율 선택으로 보고하지 않는다.
- `executed/success/error_code/evidence_id`: 실제 Python 실행·성공·데이터 부재·실패를 별도로 기록한다.

성공 또는 DATA_UNAVAILABLE 이후 불필요한 readiness Gemini 요청 없이 종료할 수 있다. 저장소 오류는 최종 생성 전 실패한다. 동일 WARNING의 추가 history 실행은 TOOL_REPEAT_LIMIT으로 차단하며 재시도하지 않는다. 한 Gemini 응답 안의 전역 다중 Function Call 실행 순서는 바꾸지 않았다.

기존 기본 한도는 조사 요청 15초, 최종 요청 15초(승인 설정에서만 30초), 전체 60초, 최종 예약 2초, 도구 실행 3초, 도구 라운드 4회, 전체 도구 실행 8회, 일반 동일 호출 2회다. 이번 WARNING history에는 더 좁은 1회 정책을 적용한다. SDK attempts=1은 최초 요청만 뜻하며 재시도 0회다. 최종 요청의 `min(설정 상한, floor(잔여 예산-2))`를 유지한다. 정책 조회도 기존 호출 수·도구 timeout·전체 분석 deadline의 적용을 받으며 Gemini 요청을 추가하지 않는다.

## H. 격리 fixture 예시와 검증

| 격리 fixture | 실제 assertion 결과 |
|---|---|
| 현재80, 과거100/120/140 | n=3, 평균120, min100, max140, 절대 차이40 |
| 현재80, 과거120 한 건 | SINGLE_OBSERVATION, n=1, 평균=min=max120, 차이40 |
| 이력0건 | DATA_UNAVAILABLE, 성공 Evidence 없음, 최종 현재 판정 유지 |
| 후보는 있지만 mean=null | NO_COMPARABLE_HISTORY, n=0, 과거 통계 null |
| 저장소 예외 | STORAGE_ERROR, 실패 Trace 보존, 신규 Gemini 최종 요청 및 재시도 없음 |
| 평균/min/max/표본 수/차이 변조 | 카탈로그 및 최종 검증에서 EVIDENCE_MISMATCH |
| 미래/자기 자신/타 제품/중복/크기 불일치 | 표본 제외 또는 변조 검증 거부 |
| history 비교를 조명 원인 근거로 지정 | EVIDENCE_MISMATCH |

대표 테스트는 `test_three_samples_are_computed_from_stored_means_with_legacy_data_unchanged`, `test_scope_time_status_dimensions_and_duplicates_are_filtered_before_limit`, `test_tampered_derived_statistics_are_rejected_by_catalog_and_final_validation`, `test_false_pointer_fact_and_history_causal_claim_are_rejected`, `test_warning_policy_executes_one_python_history_without_another_model_request`다. 이전 history 제안·필수 로그 대기·동일 batch 중복·호출 예산·실제 임시 JSONL 불변도 별도 assertion으로 확인한다.

## I. 오프라인 환경 및 실행 결과

Python 3.11 Miniconda `vision-insight`를 사용했다. 프로젝트 밖 `%TEMP%` 하위에 OUTPUT_DIR, LOG_DIR, TEST_DATA_DIR, 검사/로그 JSONL, pytest basetemp와 JUnit을 모두 분리했다. 기존 T03 독립 fixture는 기존 테스트가 준비하고, 등록되지 않은 이미지 통합 테스트 4건은 기존 조건대로 SKIP했다.

임시 프로세스 래퍼는 기본 HTTPX 전송과 외부 socket.connect를 차단하며 Windows 내부 loopback IPC는 유지한다. 외부 평가 경로 open/listdir/scandir를 audit hook으로 차단했다. 실제 API Client를 금지하는 기존/신규 Mock fixture도 사용한다. 이 래퍼는 프로젝트 코드에 추가하지 않았다.

초기 Agent+보안 선택 실행에서 Agent 1,074건은 통과했으나 보안 5건이 PatchCore 초기화의 Hugging Face 메타데이터 연결 시도로 차단됐다. 테스트 자식 프로세스의 `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`로 기존 로컬 캐시를 사용해 보안 7건 PASS를 확인했다. 새 다운로드나 네트워크 허용으로 해결하지 않았다. 운영 설정과 테스트 코드는 이 환경 문제 때문에 수정하지 않았다.

| 실행 | 실제 결과 |
|---|---|
| 신규 비교 + history/WARNING/Step1-B 초기 관련 회귀 | 249 PASS / 7.55초 (신규 테스트 추가 보강 전 실행) |
| 마지막 비교·Step1-B·WARNING 실험·계측 관련 실행 | 175 PASS / 0 FAIL / 5.48초 |
| 보안 단독 오프라인 캐시 확인 | 7 PASS / 경고2 / 8.92초 |
| 최종 전체 tests, 정확히 1회 | **1175 PASS / 0 FAIL / 4 SKIP / 경고2 / 28.64초** |
| 최종 전체에 포함된 신규 비교 테스트 | **50 PASS** |
| 최종 전체에 포함된 Step1-B 반복 반례 | **36 PASS** |
| 최종 전체에 포함된 Agent 테스트 | **1074 PASS** |
| 최종 전체에 포함된 T06 격리 모듈 | **19 PASS** |
| pip check | No broken requirements found |

그룹별 수치는 중복되므로 합산하지 않는다. 신규 fixture의 카탈로그 envelope/ERROR 조치 참조 오류는 수정했다. 기존 테스트의 실제 오류 거부 assertion은 유지했다. 이후 실패는 새 정책으로 추가된 Python history Trace, 제거된 불필요한 readiness 요청, 실행 순서별 Evidence ID 차이에 맞춰 관련 기대값을 갱신했다. skip/xfail 또는 기대 실패 허용은 추가하지 않았다.

최종 실행 명령은 별도 임시 래퍼를 통해 다음 pytest 인자를 호출했다.

```text
C:/Users/USER/miniconda3/envs/vision-insight/python.exe <임시 offline_pytest.py> tests --tb=short
pytest.main: tests --tb=short -q -rs -p no:cacheprovider --basetemp <외부 임시 경로>/pytest --junitxml <외부 임시 경로>/results.xml
```

최종 JUnit은 `%TEMP%/vision_step1c_tests_c5_9a_ea/results.xml`이다. 총1179건 / failures0 / errors0 / skipped4이며, Agent·신규·Step1-B별 집계도 이 파일에서 확인했다. 경고는 기존 timm/anomalib deprecation 2건이다.

SKIP은 다음 4건이며 이번 비교 테스트 성공과 별개다.

- `tests/test_day3_5_integration.py::test_t03_brightness_reduced_inspection`
- `tests/test_day3_5_step4.py::test_image_quality_warning_decision_confidence_policy`
- `tests/test_day3_5_step4_5.py::test_t03_final_verdict_quality_warning_reinspect`
- `tests/test_day3_5_step4_5.py::test_workflow_product_ng_under_quality_warning`

모두 격리 환경의 주입 이미지 미등록/부재에 따른 기존 SKIP이다. 이미지를 새로 생성해 수치를 바꾸지 않았다.

## J. 회귀 및 보호 결과

T03 REINSPECT, T05 ERROR/UNKNOWN/null/SKIPPED, T06 저장 OK·NORMAL 조기 종료·Ground Truth 격리, 공통 Pydantic/Evidence/Pointer 및 timeout/호출 제한 회귀가 최종 전체에서 통과했다. NORMAL과 IMAGE_LOAD_FAILURE에 정책 history를 추가하지 않았다. 과거 실제 Gemini 성공은 재실행하지 않았다.

운영 검사/로그 JSONL, 모델/메타데이터, 기존 manual_validation 회차·READY·잠금·Trace·실행기, 확인 가능한 이미지, 발표 자료 등 **기존 보호 파일4,394개 SHA256은 사전/사후 전부 동일**했다. 외부 평가 경로는 열거나 목록 조회·해시 계산하지 않았다. 기존 `.tmp_measurement_regressions/` 및 타 에이전트의 미추적 파일을 보존했다.

`git diff --check -- backend/agent tests`는 exit0이다. 전체 `git diff --check`는 기존 발표 문서의 trailing whitespace로 exit2다. 해당 파일은 이번 작업에서 수정하지 않았고 보호 해시도 동일하다.

- `presentation/presentation-review-checklist.md`: 49/53/56행
- `presentation/presentation-script.md`: 247/248/249행
- `presentation/slide-outline.md`: 64/66/68/70행

Git의 LF/CRLF 안내는 pytest 경고와 별개다. 이번 작업은 허용된 Agent 코드·관련 테스트·본 문서에 한정했다. Git add/commit/push/reset은 0건이다.

## K. 한계와 다음 승인 단계

Mock이 특정 호출을 제안한 경우와 BACKEND_POLICY가 조회를 보장한 경우를 구분했다. Mock은 서버 계약과 고정 입력의 검증을 제공하며 실제 Gemini의 자율적인 history 선택·언어 품질·반복 안정성을 측정하지 않는다. 통계값과 원인 코드의 연결은 제한하지만 자유로운 자연어 인과관계 전체를 검증한 것은 아니다.

현재 스키마에 기록되지 않은 알고리즘·ROI 버전의 완전 일치, 과거91건의 독립 표본성, 실제 조명 장치 고장 여부는 LIMITATION/NOT TESTED다. 기존 T06 원본 ASGI 본문 미보관에 따른 사후 자연어 검토 한계도 유지한다. 이번 실제 비용은 발생하지 않았으며 과거 Gemini 실제 청구액은 여전히 UNKNOWN이다.

전역 다중 Function Call 선제 억제는 별도 최적화로 남긴다. 모델이 이미 같은 WARNING에서 history를 실행한 뒤 다시 제안하면 TOOL_REPEAT_LIMIT으로 안전하게 실패하며, 캐시 응답 재사용 정책은 이번에 추가하지 않았다.

Day5 Step2 영상 Grab API로 넘어갈 서버 계약 인수인계는 준비됐다. 영상 검사에서도 inspection_id를 로그 연결 키로 유지하고, ROI/측정 버전을 향후 기록할 때 history의 비교 가능 조건을 명시해야 한다. 실행 로그 product_id 제거와 재진단 트리거는 Step4 승인 범위에서 다룬다. Step2 구현 및 실제 Gemini 평가는 각각 별도 승인이 필요하며 이번 작업에서 시작하지 않았다.
