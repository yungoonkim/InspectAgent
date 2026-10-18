# VisionInsight — Day 7 Step 2
## Gemini Function Calling Agent 요청 구조 비교 및 오프라인 호환성 검증 보고서
### 문서 위치: `docs/day7-step2-gemini-agent-offline-compatibility.md`
### 작성일: 2026-10-18 | 발표 예정일: 2026-10-20
### 상태: OFFLINE VALIDATED (외부 Gemini API 호출: 0회)

---

## 1. 개요 및 목적

본 문서는 VisionInsight의 Gemini Function Calling Agent(`backend/agent/service.py`)와 사용자가 직접 실행하여 성공한 Google Gemini API 단일 요청(`scripts/day7_gemini_single_call.py`) 간의 요청 구조, SDK 계약, 파라미터 직렬화, 생명주기를 코드 수준에서 1:1 비교 분석하고, 확인 가능한 호환성을 오프라인 Mock 테스트로 검증한 결과를 기록합니다.

### 핵심 원칙
- **외부 API 호출 엄격 제한:** Google Gemini API 실제 호출 **0회**, 실제 PatchCore 추론 **0회**, 신규 JSONL 생성 **0건**.
- **검증 상태 명확화:** **OFFLINE VALIDATED**로 선언하며, 실제 모델과의 통신이 수반되지 않았으므로 **LIVE VERIFIED**로 단정하지 않음.
- **기존 기능 절대 보존:** LiveView, ROI, ImageView, Zoom/Gray Inspector, PatchCore Threshold(34.1442), 기존 저장 보고서 조회, 데이터베이스 및 Ground Truth 불변 유지.

---

## 2. 단일 요청과 Agent 요청 비교표 (20개 항목)

| 번호 | 비교 항목 | 성공한 단일 요청 (`day7_gemini_single_call.py`) | 기존 VisionInsight Agent 요청 (`backend/agent/service.py`) | 차이점 요약 및 분석 |
|---|---|---|---|---|
| 1 | **SDK 버전** | `google-genai` 2.31.0 | `google-genai` 2.31.0 | **동일.** Miniconda `vision-insight` (Python 3.11.16) 환경 공유 |
| 2 | **Gemini Client 생성 방법** | `genai.Client(api_key=..., http_options=HttpOptions(api_version='v1beta', ...))` (1회용 생성/종료) | `AgentRuntime`에서 앱 수명주기 동안 1회 지연 생성(싱글톤), Fallback 시 `service.analyze` 내 생성 | 단일 요청은 `api_version='v1beta'`를 명시 전달하였으나, 기존 Agent는 미지정(SDK 기본값 의존). Client 생명주기는 1회용 vs 커넥션 풀 공유 |
| 3 | **API 버전** | `v1beta` (명시적 설정) | `v1beta` (암묵적 기본값) | 단일 요청은 명시 설정, Agent는 암묵적 의존 |
| 4 | **모델명** | `gemini-3.8-flash` (`settings.GEMINI_MODEL`) | `gemini-3.8-flash` (`settings.GEMINI_MODEL`) | **동일.** 일관된 타깃 모델 유지 |
| 5 | **모델 요청 메서드** | `await client.aio.models.generate_content(...)` | `await client.aio.models.generate_content(...)` | **동일.** 비동기 호출 및 `asyncio.wait_for` 타임아웃 래핑 |
| 6 | **GenerateContentConfig** | 단일 텍스트 요청 설정 (tools 없음, MIME 없음) | 2단계 분리: Tool 탐색 라운드는 `tools=[types.Tool(...)]` + `tool_config=AUTO`, 최종 보고서 라운드는 `response_mime_type="application/json"` + `response_json_schema=...` | 단일 요청은 단순 텍스트 모드. Agent는 Tool 라운드와 Structured Report 라운드를 엄격히 분리하여 스키마/도구 충돌 방지 |
| 7 | **max_output_tokens** | `16` (연결 확인 전용, `FINISH_REASON: MAX_TOKENS` 유도) | `4096` (`AgentLimits.max_output_tokens`, 256~8192 범위) | 단일 요청은 최소 진단용. Agent는 다단계 도구 호출 및 구조화 보고서 생성에 적합한 4096 토큰 유지 |
| 8 | **thinking 관련 설정** | `None` (설정하지 않음) | `None` (설정하지 않음) | **동일.** 별도 thinking 설정 없음 |
| 9 | **Function Calling 도구 선언** | `tools=None` (도구 없음) | `tools=[types.Tool(function_declarations=function_declarations())]` (4개 도구) | 단일 요청은 도구 미사용. Agent는 `get_inspection_result`, `get_execution_logs`, `analyze_image_quality`, `get_inspection_history` 4개 선언 |
| 10 | **Function Calling 모드** | `None` | `types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="AUTO"))` | 단일 요청은 미사용, Agent는 AUTO 모드 |
| 11 | **response_mime_type** | `None` (기본 text/plain) | Tool 라운드: `None`, 최종 라운드: `"application/json"` | 단일 요청은 텍스트, Agent 최종 라운드는 JSON 지정 |
| 12 | **response_schema** | `None` | Tool 라운드: `None`, 최종 라운드: `simple_output_schema()` (`response_json_schema` 전달) | 단일 요청은 미사용, Agent 최종 라운드는 정형 토큰 카탈로그 기반 스키마 투영 |
| 13 | **contents 구조** | 단순 문자열 (`"Reply exactly OK"`) | `[types.Content(role="user", parts=[types.Part.from_text(...)])]` -> 이후 model `function_call`과 user `function_response`가 누적되는 다회차 대화 리스트 | 단일 요청은 단순 문자열, Agent는 `types.Content` 기반 정형 대화 히스토리 |
| 14 | **system_instruction** | `None` | Tool 라운드: `SYSTEM_INSTRUCTION`, 최종 라운드: `REPORT_SYSTEM_INSTRUCTION` | 단일 요청은 프롬프트 없음, Agent는 증거 수집/추론 제약 규칙 전달 |
| 15 | **Tool 응답 반환 형식** | N/A (도구 없음) | `types.Part(function_response=types.FunctionResponse(name=call.name, id=call.id, response=result))` | 단일 요청은 해당 없음. Agent는 SDK 정식 `FunctionResponse` 구조로 서버 결과 전달 |
| 16 | **SDK 자동 Function Calling (AFC)** | `AutomaticFunctionCallingConfig(disable=True)`, `automatic_continuation=False` | `AutomaticFunctionCallingConfig(disable=True)`, `automatic_continuation=False` | **동일.** SDK의 암묵적 로컬 실행을 비활성화하고 서버 수동 제어 루프 유지 |
| 17 | **SDK Retry 설정** | `retry_options=HttpRetryOptions(attempts=1)` | `retry_options=HttpRetryOptions(attempts=1)` | **동일.** SDK 내부 자동 재시도 1회로 제한 (무한 재시도 차단) |
| 18 | **Timeout 설정** | `HttpOptions(timeout=int(timeout*1000))` + `asyncio.wait_for(timeout=timeout)` | `HttpOptions(timeout=int(timeout*1000), headers={'X-Server-Timeout': ...})` + `asyncio.wait_for(timeout=timeout)` | 거의 동일. Agent는 추가로 `X-Server-Timeout` 헤더 명시 |
| 19 | **비동기 Client 생명주기** | 1회 호출 직후 `client.aio.aclose()` 및 `client.close()` 명시적 해제 | `AgentRuntime` 앱 수명주기 싱글톤 관리 (서버 종료 시 `aclose()`). `RequestState`는 요청 격리 | 단일 요청은 요청별 단기 수명주기, Agent는 커넥션 풀을 재사용하는 앱 스코프 수명주기 |
| 20 | **Gemini 응답 파싱 로직** | `candidate.finish_reason`, `part.text` 단순 추출 | `candidate.finish_reason == STOP` 검증, `part.function_call` 추출/검증, 최종 라운드는 `part.text` 추출 후 `convert_simple_report`로 증거 검증 | 단일 요청은 기본 텍스트 파싱, Agent는 함수 호출 검증, STOP 상태 검증, JSON 포인터 기반 증거 일치 엄격 검증 |

---

## 3. 실제 코드에서 확인한 차이점 분석

1. **API 버전 명시성 차이:**
   - `day7_gemini_single_call.py`에서는 `HttpOptions(api_version="v1beta", ...)`를 Client 초기화 및 `GenerateContentConfig`에 명시적으로 지정하여 Google API v1beta 엔드포인트 통신을 보장했습니다.
   - 기존 `service.py`와 `api.py`에서는 `api_version`이 누락되어 SDK 기본값에 암묵적으로 의존하고 있었습니다.
2. **단일 호출 vs 다단계 Function Calling:**
   - 단일 호출은 `tools=None`으로 단순 텍스트 프롬프트를 처리했습니다.
   - Agent는 Tool Round(도구 선언 및 AUTO 모드)와 Structured Report Round(JSON 스키마 모드)로 명확히 분리되어 동작합니다. 두 설정이 단일 요청에서 충돌하는 문제는 없습니다.
3. **출력 토큰 크기:**
   - 단일 호출의 `max_output_tokens=16`은 의도적으로 `FINISH_REASON: MAX_TOKENS`를 유발한 진단용 설정이었습니다.
   - Agent의 `max_output_tokens=4096`은 정상적인 보고서와 다중 함수 호출 인수를 수신하기 위한 적정 크기로 보존되어야 합니다.

---

## 4. Function Calling Schema 및 GenerateContentConfig 검증

### 4-1. 도구 선언 스키마 (`ARGUMENT_MODELS`)
- `get_inspection_result`: `InspectionArguments` (`inspection_id: INSP-[0-9]{6,12}`)
- `get_execution_logs`: `InspectionArguments` (`inspection_id: INSP-[0-9]{6,12}`)
- `analyze_image_quality`: `InspectionArguments` (`inspection_id: INSP-[0-9]{6,12}`)
- `get_inspection_history`: `HistoryArguments` (`product_id: str`, `limit: int = 5`, `inspection_id: Optional[str] = None`)

SDK `google.genai 2.31.0`의 `_Tool_to_mldev` 및 `_common.convert_to_dict` 직렬화 검증 결과:
- `types.FunctionDeclaration(parameters_json_schema=arguments.model_json_schema())`는 wire format으로 `functionDeclarations` 배열 내에 올바르게 배치됩니다.
- OpenAPI 3.0 / JSON Schema 호환 규격에 따라 `type: "object"`, `properties`, `required`, `additionalProperties: false` 구조가 정상 직렬화됩니다.

### 4-2. GenerateContentConfig 호환성
- **Tool Round:** `tools` 선언 시 `response_mime_type`과 `response_json_schema`가 `None`으로 유지되므로 Google GenAI SDK의 스키마-도구 상호 배타성 제약을 완벽히 준수합니다.
- **Report Round:** `tools=None` 상태에서 `response_mime_type="application/json"` 및 `response_json_schema=simple_output_schema()`가 전달되어 스키마 충돌이 발생하지 않습니다.
- **Thinking Config:** 미설정(`None`) 상태로 Flash 계열 모델의 기본 추론 모드로 동작합니다.

---

## 5. SDK Retry / Timeout / Client 생명주기 점검

1. **Retry 제어:**
   - `HttpRetryOptions(attempts=1)`이 Client 생성부와 매 요청 `GenerateContentConfig` 양쪽에 일관되게 주입되어 있습니다.
   - 네트워크 장애 또는 HTTP 오류 발생 시 내부적인 무한 재시도 루프가 원천 차단됩니다.
2. **Timeout 제어:**
   - SDK 차원의 `timeout=int(timeout_seconds * 1000)`과 HTTP 헤더 `X-Server-Timeout`이 설정됩니다.
   - 애플리케이션 차원의 `asyncio.wait_for(timeout=timeout_seconds)` 및 전체 분석 수명주기 `asyncio.timeout(remaining)`이 2중으로 보호합니다.
3. **Client 생명주기:**
   - `AgentRuntime`은 `FastAPI` 앱 수명주기 동안 `genai.Client` 1개를 안전하게 재사용(Keep-Alive 및 커넥션 풀링)하며, 셧다운 시 `aclose()`를 통해 커넥션을 정리합니다.
   - 각 분석 요청의 상태(`RequestState`)는 엄격히 독립 인스턴스로 격리되어 동시 요청 간 오염이 없습니다.

---

## 6. 발견된 코드 결함 및 적용한 최소 수정

### 발견된 결함: `api_version="v1beta"` 누락
- **현상:** 단일 성공 요청(`day7_gemini_single_call.py`)은 `HttpOptions(api_version="v1beta")`를 명시적으로 주입하였으나, Agent 서비스(`backend/agent/service.py`)와 런타임(`backend/agent/api.py`)에서는 `api_version`이 명시되지 않고 있었습니다.
- **위험성:** SDK 내부 기본값이 변경되거나 특정 프록시/환경에서 v1 알파/베타 엔드포인트 라우팅 불일치가 발생할 수 있는 위험이 있었습니다.

### 적용한 최소 수정 (Diff 요약)
1. `backend/agent/service.py` (Line 274):
   ```python
   # Fallback Client 생성 시 api_version="v1beta" 명시
   http_options=types.HttpOptions(
       api_version="v1beta",
       timeout=int(self.limits.model_timeout_seconds * 1000),
       retry_options=types.HttpRetryOptions(attempts=1),
   )
   ```
2. `backend/agent/service.py` (Line 337):
   ```python
   # GenerateContentConfig 요청 옵션에 api_version="v1beta" 명시
   http_options=types.HttpOptions(
       api_version="v1beta",
       timeout=int(timeout_seconds * 1000),
       headers={"X-Server-Timeout": str(math.ceil(timeout_seconds))},
       retry_options=types.HttpRetryOptions(attempts=1),
   )
   ```
3. `backend/agent/api.py` (Line 90):
   ```python
   # AgentRuntime Client 초기화 시 api_version="v1beta" 명시
   http_options=types.HttpOptions(
       api_version="v1beta",
       timeout=int(settings.AGENT_MODEL_TIMEOUT_SECONDS * 1000),
       retry_options=types.HttpRetryOptions(attempts=1),
   )
   ```

---

## 7. Step C: 10개 오프라인 Mock 검증 결과

구현 파일: `tests/test_day7_step2_agent_offline_mock.py` (총 13개 세부 테스트 케이스)

| 시나리오 | 테스트 명칭 | 검증 내용 | 결과 |
|---|---|---|---|
| **Test 1** | `test_scenario_01_first_agent_request_structure` | 최초 요청의 모델명(`gemini-3.8-flash`), 4개 도구 선언, AUTO 모드, 4096 토큰, v1beta 옵션, AFC 비활성화 확인 | **PASS** |
| **Test 2** | `test_scenario_02_function_calling_response_handling` | 가상 FunctionCall 수신 시 서버 도구 실행, 실행 추적(E0001, success=True), snapshot 갱신 확인 | **PASS** |
| **Test 3** | `test_scenario_03_tool_result_return_payload_structure` | 2회차 요청에서 도구 실행 결과(`FunctionResponse`)의 SDK 정식 구조와 ok: True 전달 확인 | **PASS** |
| **Test 4** | `test_scenario_04_final_response_produces_agent_report` | 구조화 최종 응답 수신 시 `DiagnosisResult(analysis_status="COMPLETED")` 및 한국어 요약 생성 확인 | **PASS** |
| **Test 5** | `test_scenario_05_evidence_verification_deterministic_pointer` | 모든 `ObservedFact`가 서버 스토리지의 JSON Pointer 및 원본 스칼라와 1:1 결정적 일치 확인 | **PASS** |
| **Test 6** | `test_scenario_06_server_verdict_immutability` | Agent 실행 및 분석 완료 후에도 검사의 원본 판정(`final_result`, `result`)이 불변 유지됨을 확인 | **PASS** |
| **Test 7** | `test_scenario_07_model_errors_safe_mapping_and_logging` | 400, 403, 404, 429 오류 발생 시 `GEMINI_REQUEST_FAILED`(502) 안전 매핑 및 API 키 마스킹 로깅 확인 | **PASS (4종)** |
| **Test 8** | `test_scenario_08_timeout_handling_without_infinite_retry` | `TimeoutError` 시 `GEMINI_TIMEOUT`(504) 발생 및 추가 재시도 없이 1회로 안전 종료 확인 | **PASS** |
| **Test 9** | `test_scenario_09_no_function_call_in_round1_safe_rejection` | 1회차에 도구 호출 없이 텍스트 도착 시 `INSUFFICIENT_EVIDENCE`(502)로 안전 차단 확인 | **PASS** |
| **Test 10** | `test_scenario_10_max_tokens_safe_rejection_no_hallucination` | `finish_reason=MAX_TOKENS` 시 `MODEL_RESPONSE_INCOMPLETE`(502) 발생 및 허위 보고서 생성 방지 확인 | **PASS** |

---

## 8. 기존 테스트 회귀 검증 결과

실행 명령:
```powershell
pytest tests/test_agent_service.py tests/test_agent_api.py tests/test_agent_day7_error_observability.py tests/test_day7_gemini_single_call.py tests/test_day7_step2_agent_offline_mock.py
```

결과:
```text
============================= 190 passed in 6.98s =============================
- tests/test_agent_service.py: 81 passed
- tests/test_agent_api.py: 70 passed
- tests/test_agent_day7_error_observability.py: 10 passed
- tests/test_day7_gemini_single_call.py: 16 passed
- tests/test_day7_step2_agent_offline_mock.py: 13 passed
총합: 190 / 190 PASS (100%)
```

---

## 9. 안전 및 호출 제한 준수 확인

1. **실제 Gemini API 호출 횟수:** **0회** (`forbid_real_gemini_client` fixture를 통해 실제 Client 호출 시 AssertionError 유발).
2. **신규 Agent 실시간 분석 호출:** **0회** (`POST /analyze/{inspection_id}` 라이브 호출 없음).
3. **PatchCore 추론 및 JSONL 생성:** **0건** (기존 운영 데이터 보존).
4. **보안 무결성:** `.env` 및 API 키, Bearer 토큰의 노출 0건, 마스킹 확인 완료.

---

## 10. 여전히 미확정인 문제 및 한계 (LIVE VERIFICATION REQUIRED)

오프라인 검증을 통해 코드 레벨 계약, 직렬화 스키마, 오류 핸들링, 타임아웃, 증거 포인터 결정론이 모두 검증되었으나, 다음 사항은 **실제 Google Gemini API 실호출을 통해서만 확정**할 수 있습니다:

1. **Google 서버 측 Tool Calling 스키마 검증기와의 실시간 호환성:**
   - `parameters_json_schema`에 포함된 Pydantic v2 필드(`title`, `maxLength`, `pattern`)가 Google의 `v1beta` 백엔드 서버 정책에 따라 수락되는지 여부는 실제 1회 네트워크 요청을 통해 검증되어야 합니다.
2. **다회차 대화 세션의 토큰 누적 및 할당량:**
   - 1회 단일 호출(16 토큰)과 달리 다회차 Function Calling 과정에서 Google API 프로젝트의 QPM/TPM Quota가 충분한지 여부.
3. **현재 상태 판정:**
   - **OFFLINE VALIDATED (완료)**
   - **LIVE VERIFIED (미완료 — 사용자의 실제 1회 실호출 승인 필요)**

---

## 11. 향후 실제 Agent 실호출 전 권장 조치

1. 사용자가 Day 7 Step 1에서 구현된 관측성 로깅이 활성화된 상태에서, 단일 검사 건(`INSP-001442`)에 대해 실시간 분석 1회를 승인/실행.
2. 만약 Google 서버에서 `GEMINI_REQUEST_FAILED`가 재발할 경우, Day 7 Step 1 로깅으로 기록될 `provider_code`와 `http_status`를 통해 즉각적인 특정(예: QUOTA, PERMISSION, SCHEMA) 가능.
3. 정상 응답 시 React 대시보드에서 `INSP-001442`의 실시간 보고서 생성 및 렌더링 확인.
