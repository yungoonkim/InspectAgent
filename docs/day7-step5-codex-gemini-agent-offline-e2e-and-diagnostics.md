# Day7 Step5 — Gemini Agent 독립 감사·오프라인 E2E·안전 진단

작성일: 2026-10-18. 발표 예정일: 2026-10-20.

## A. 최종 상태

**COMPLETE — 오프라인 감사·재현 결함 수정·자동 회귀 통합 범위. 실제 Live Agent 성공은 NOT VERIFIED.**

최종 러너: **PASS WITH SKIP**, 종료 코드 0.

| 그룹 | PASS | FAIL | SKIP | 경고 |
|---|---:|---:|---:|---:|
| Backend 선택 회귀 | 411 | 0 | 10 | 1 |
| Frontend Node TAP | 26 | 0 | 0 | 0 |
| 기존 ImageView Chrome Mock E2E | 12 | 0 | 0 | 아래 콘솔 한계 참조 |
| 신규 AgentPanel Chrome Mock E2E | 8 | 0 | 0 | 아래 콘솔 한계 참조 |
| TypeScript / Build | 각 명령 성공 | 0 | 0 | 0 |
| lint | 명령 성공 | 0 | 0 | 6 |

실제 Gemini API 요청 **0회**, 실제 PatchCore checkpoint 로딩·자동 추론 **0회**, PostgreSQL 연결·변경 **0건**. 운영 보호 파일 **32개**의 전후 파일 집합과 SHA256 동일. 전체 pytest는 실행하지 않았다.

최종 증거: `data/outputs/safe-regression/20261018-154632-de67a058/`의 summary.json, backend.xml, pytest.log, safety.json, protection.json, 각 단계 로그와 브라우저 result.json. 설치된 **Chrome/155.0.8059.82**를 새 임시 프로필로 사용했다.

사용자가 Chrome에서 확인한 INSP-001650/IMG-BOTTLE-0084, score31.3346, threshold34.1442, OK 및 Heatmap 정상 동작은 **사용자 검증 기록**이다. 이번에 해당 검사·이미지·모델을 재실행하지 않았다.

## B. 확인한 Agent 코드 구조

AGENTS.md, AUTO/MANUAL 명세, 기술 스택 문서, Day7 Step1/2/4 및 Codex 인수인계 문서, Day4 성공/실패 감사 기록, 현재 Agent 구현과 기존 테스트를 확인했다. 추가 적용 AGENTS.md는 없었다. 작업 전부터 존재하던 코드 변경·미추적 파일과 발표 자료의 삭제/이동 상태를 그대로 보존했다.

```text
POST /analyze/{inspection_id}
→ get_validated_inspection_id: 엄격한 업무 ID 검사
→ get_analysis_context: 기존 기록을 조회, 요청별 AnalysisContext(dict/InspectionTools)
→ AgentRuntime.service: 앱 단위 SDK client 지연 생성·재사용
→ AgentService.analyze: 요청별 RequestState, deadline, trace/evidence/repeats
→ _run → _generate: SDK Content / GenerateContentConfig / FunctionDeclaration
→ _execute: 이름 allowlist → Pydantic 인자 → inspection/product 범위 검증
→ Python InspectionTools → dict 결과 → 비식별 context view
→ RequestState.evidence[E0001...] 및 ToolExecutionTrace
→ 후속 조사 Content(role=user, FunctionResponse) 또는 조사 조기 완료
→ build_catalog: 서버 소유 K-token / Evidence ID / JSON Pointer / 실제 scalar
→ 별도 structured 요청: tools 없음, SimpleReport JSON 토큰 선택
→ convert_simple_report → DiagnosisDraft(Pydantic)
→ _verify_report: 실제 Evidence·값·이벤트·필수 사실·가설·조치 검증
→ 서버 고정 문구 DiagnosisResult
→ analyze_inspection: 원본 snapshot/summary 재대조 → AnalysisResponse
```

주요 위치: `backend/agent/api.py:69`, `backend/agent/api.py:142`, `backend/agent/api.py:190`, `backend/agent/service.py:106`, `backend/agent/service.py:254`, `backend/agent/service.py:333`, `backend/agent/service.py:417`, `backend/agent/service.py:457`, `backend/agent/reporting.py:104`, `backend/agent/reporting.py:192`.

### Client/요청 설정 — 변경하지 않음

- 설치 SDK는 배포 메타데이터로 확인한 **google-genai 2.31.0**. 기본 모델 설정은 **gemini-3.8-flash**. 이번에 모델의 외부 가용성을 조회·검증하지 않았다.
- Developer API key 방식. 키 값·.env 내용은 출력하지 않았다. 테스트는 `_env_file=None`, API key 없음 또는 명시적인 OFFLINE_SYNTHETIC_NOT_A_KEY만 사용했다.
- Runtime과 요청의 HttpOptions는 v1beta 명시, retry attempts=1. 설치 SDK `_api_client.py:890`에도 Developer API 기본 v1beta가 있다. 명시 이전과 달랐다고 단정할 근거가 없다.
- 요청 기본값: temperature0, candidate_count1, max_output_tokens4096, automatic_function_calling.disable=True, automatic_continuation=False, Tool 모드 AUTO.
- 기본 Agent deadline60초, 조사 요청15초, 최종 요청15초, 도구3초. 최종 요청은 남은 deadline에서 2초를 유보한 정수 budget과 설정값 중 작은 값을 쓴다. 환경 설정의 실제 실행값이 과거와 같았다는 증거는 아니다. HTTP 전체 처리 시간 상한과 Agent 내부 deadline도 구분한다.
- 앱 소유 client는 재사용하고 shutdown에서 aio.aclose 후 close한다. 서비스가 직접 생성하는 fallback client의 정리 결함은 F/G절에서 설명한다.

## C. 네 가지 Function Calling 도구 계약

`backend/agent/service.py:117`의 function_declarations와 ARGUMENT_MODELS 등록명이 일치한다. callable 자체를 SDK에 넘기지 않으며 서버가 실행한다.

| 등록명 | 인자 | Python 결과/안전 계약 |
|---|---|---|
| get_inspection_result | inspection_id 필수 | 기존 판정·수치 whitelist 조회. 원본 final_result를 다시 계산하지 않음 |
| analyze_image_quality | inspection_id 필수 | 저장 품질/밝기/기록된 기준치만 조회. 이미지·현재 threshold 재분석 없음 |
| get_execution_logs | inspection_id 필수 | 검사의 저장 이벤트를 timestamp 순으로 조회. 원문 message와 임의 경로 제외 |
| get_inspection_history | product_id 필수, limit 기본5/1~20, inspection_id 선택 | 같은 제품의 제한된 후보 이력. WARNING 비교는 현재 inspection에 바인딩 |

스키마는 Pydantic extra=forbid, StrictStr/StrictInt, ID pattern을 사용한다. bool limit·추가 인자·다른 inspection_id를 거부한다. 실제 제품 ID는 서버만 알고, 모델에는 **TARGET-PRODUCT** alias를 전달한다. history가 임의 제품을 조회하지 못하도록 서버가 실제 ID로 치환한다. `InspectionTools._lookup`도 반환 record의 inspection_id를 재확인한다.

도구 응답은 ok/data/error/metadata envelope다. 성공한 실제 Python 실행만 Evidence ID를 받는다. DATA_UNAVAILABLE에는 성공 Evidence를 만들어 넣지 않는다. 도구 raw 메시지·image_id는 모델 context에서 제외한다. SDK의 FunctionResponse는 제안된 call의 name/id를 보존하고 role=user로 전달한다. 서버 조기 완료 시 해당 결과는 최종 catalog에 들어가며, **실제로 보내지 않은 후속 FunctionResponse 전송을 주장하지 않는다.**

오프라인의 스키마 생성·SDK 직렬화 검증은 실제 Google 서버의 스키마 수락까지 입증하지 않는다.

## D. 다회차 Tool Loop와 제한

- 기본 **실행 도구 round 최대4, 총 실행 call 최대8, 동일 인자 호출 최대2**. 반복을 전부 금지하는 구조가 아니라 유한 허용이다.
- 한 응답의 여러 call을 각각 검증하여 순차 실행한다. 9번째 실행, 반복 3번째, 5번째 실행 round는 차단된다. 전역 도구 worker/slot은4로 제한하며 초과 시 TOOL_CAPACITY_EXCEEDED다.
- _run은 최대4개 실행 round 뒤 **추가 종료 응답 확인용 SDK turn**을 허용한다. 그 응답에 도구가 있으면 실행 전에 TOOL_ROUND_LIMIT다. 따라서 ‘SDK 요청도 최대4회’라고 해석하면 틀린다.
- 성공한 최종 JSON까지 포함한 일반적인 SDK 요청 상한은 **6회**(최대5 조사/종료 응답 + 최종1). 정상 조기 종료 경로는 보통 결과 도구1 + 최종1, 총2회다. 실패는 더 일찍 종료될 수 있다.
- WARNING에서 품질 Evidence가 확보되면 서버 BACKEND_POLICY가 history를 추가할 수 있다. 이 실행도 총 call 제한에 포함하며 GEMINI가 직접 제안한 호출로 위장하지 않는다.
- _TOOL_EXECUTOR의 timeout은 read-only Python 조회의 대기를 제한한다. 이미 실행 중인 worker를 강제 중단한다는 보장은 없으며 slot은 실제 종료 시 해제한다.

## E. Evidence Store / Fact Catalog 검증

Evidence Store는 별도의 영속 DB가 아니라 **요청별 RequestState.evidence dict**다. 공유 client와 달리 요청 상태는 공유하지 않는다.

1. 실제 실행·성공 trace와 Evidence ID/name을 대조한다.
2. whitelist leaf scalar만 catalog로 만든다. 원본 메시지·제품 ID·파일 경로·Ground Truth는 catalog에 넣지 않는다.
3. 모델은 값·JSON Pointer를 자유 생성하지 않고 서버 K-token을 선택한다.
4. 서버가 K-token을 Evidence ID/Pointer/observed_value로 변환한다. catalog를 다시 생성하여 변조 여부도 대조한다.
5. _verify_report가 JSON Pointer를 원본 Evidence에 해석하여 scalar 값·타입·도구·이벤트를 재검증한다. bool은 수치와 동일 취급하지 않는다.
6. 필수 핵심6필드, ERROR/품질 경고의 추가 근거, 가설·조치의 의미상 연결과 최종 요약을 검증한다. Hypothesis는 is_hypothesis=True와 서버 제한 문구로 표시한다.
7. API가 최초 조회한 원본 snapshot과 결과를 다시 대조한다. 다른 검사 근거, 임의 final_result/trace/observed_value 필드 추가는 거부한다.

기존 reporting integration 30개, tools76개, service81개에 신규 API E2E를 더해 검증했다. 서로 다른 요청이 E0001/K0001을 재사용하더라도 요청별 catalog가 분리됨을 동시 분석으로 확인했다. 원본/서버 판정 정책은 수정하지 않았다.

## F. 기존 GEMINI_REQUEST_FAILED 원인 확인 수준

**최근 POST /analyze/INSP-001442 장애의 ROOT CAUSE UNKNOWN.**

확인 가능한 것은 당시 502/GEMINI_REQUEST_FAILED라는 기록과 현재 코드가 generate_content의 비-timeout 예외를 그 코드로 감싼다는 사실이다. 당시 예외 클래스·Provider 상태·실패 turn을 특정하는 원본 trace는 이번 감사에서 확보하지 못했다. Day7 Step1 문서가 제시한 ‘첫 요청에서 실패해 모든 도구 미실행’까지는 새로 입증하지 못했다.

- Model ID, SDK 버전, v1beta 명시 누락을 근본 원인으로 확정하지 않는다.
- 사용자가 승인했던 단일 연결 요청은 RESPONSE_TEXT=None / MAX_TOKENS / 토큰16의 별도 실험이다. 실제 Function Calling·최종 보고서 성공이 아니며 MAX_TOKENS를 기존 502의 원인으로 연결하지 않는다.
- 이번 재현으로 확인한 것은 **예외 원문 로그 유출, Mock NG 출처 누락, fallback client 정리 누락, UI 실패/저장 상태 혼동**이다. 이 결함들의 원인은 확인했지만 과거 Provider 장애를 해결했다고 하지 않는다.

## G. Provider 예외 분류 및 구조화 로그

### 재현과 최소 보완

`step5-reproduce-02/backend.xml`: 신규31개 중 **9 FAIL / 22 PASS**. Mock NG 제한 문구 누락1, Provider 예외 원문의 합성 prompt/path/비밀 문자열 로그 유출6, 연결/SDK 예외 원문 유출2를 재현했다. 실제 민감 데이터나 네트워크는 사용하지 않았다.

기존 정규식은 Bearer/key 같은 일부 패턴만 마스킹하므로 임의 Provider 메시지에 포함된 prompt·경로·Tool payload를 안전하게 제거할 수 없었다. `service.py`에서 **원문을 기록하지 않고 message=[REDACTED] 상수**만 남기게 했다. 일반 내부 예외도 원문 없이 분류 필드만 기록한다.

로그 필드: correlation_id, model, stage(TOOL_ROUND_n/STRUCTURED_REPORT), exception_class, 가능한 http_status/provider_code. Timeout은 TimeoutError와 None 상태를 명시한다. Provider code는 기존 diagnostics의 고정 코드 allowlist로 제한한다. API key·Authorization·prompt·이미지 경로·전체 tool response·SDK response body는 로그에 넣지 않는다.

신규 provider 시험은 **400/401/403/429/500/503 × 조사/최종 stage**를 검증했다. 기존 테스트의 APIError-shaped Fake도 알려진 allowlist 코드만 보존한다. 초기 전체 선택 회귀의 해당 Mock 호환성 실패4건을 확인하고 검증 assertion을 약화하지 않은 채 보완했다.

`step5-close-reproduce/backend.xml`: async cleanup 실패 시 owned client.close 미호출1건을 재현했다. fallback 정리도 finally에서 sync close를 시도하도록 수정했다. client/API 설정은 바꾸지 않았다.

| 상황 | HTTP / 안정 오류 코드 |
|---|---|
| Provider 400/401/403/429/5xx, 연결/SDK 오류 | 502 / GEMINI_REQUEST_FAILED |
| 로컬 Gemini 대기 timeout | 504 / GEMINI_TIMEOUT |
| Agent 전체 deadline / tool 대기 | 504 / AGENT_TIMEOUT 또는 TOOL_TIMEOUT |
| 미허용 도구 / 잘못된 인자 / 타 검사 | 502 / TOOL_NOT_ALLOWED, TOOL_ARGUMENT_INVALID, INSPECTION_SCOPE_MISMATCH |
| call/round/repeat 상한 | 502 / TOOL_CALL_LIMIT, TOOL_ROUND_LIMIT, TOOL_REPEAT_LIMIT |
| 빈 응답 / MAX_TOKENS | 502 / MODEL_RESPONSE_INVALID, MODEL_RESPONSE_INCOMPLETE |
| JSON 구문 / schema / Evidence 실패 | 502 / FINAL_JSON_INVALID, RESPONSE_SCHEMA_INVALID, EVIDENCE_MISMATCH |
| 저장소/가용성 문제 | 503 / 기존 STORAGE_ERROR 등 |

Provider 인증 오류는 서버 자격 증명 문제일 수 있으므로 로컬 사용자 인증 오류401로 바꾸지 않았다. **원격 HTTP504 SDK 예외는 기존 계약상 502일 수 있고, 로컬 TimeoutError의504와 다르다.** 오류 분류 보완은 요청 성공률 개선이나 Provider 원인 규명을 의미하지 않는다.

## H. 과거 E2E 성공과 최근 502의 구분

`docs/day4-step5-final-verification.md:166`의 당시 완료 감사에는 실제 성공 기록이 있다.

| 과거 시나리오/ID | 당시 기록 | 최종 요청 timeout 기록 |
|---|---|---|
| T01 / INSP-001396 | 200 / COMPLETED, 결과 도구1 | 기본15초 |
| T03 / INSP-001398 | 200 / COMPLETED, 결과·품질2 | 승인된 회차30초 |
| T05 / INSP-001405 | 200 / COMPLETED, 결과·로그2 | 승인된 회차30초 |
| T06 / INSP-001406 | 200 / COMPLETED, 결과 도구1 | 승인된 회차30초 |

이것은 **기존 감사 기록의 재확인**이지 이번 실호출 결과가 아니다. 과거 T06 성공 ID001406과 이번 요청의 예시001390도 혼동하지 않는다. 원본 E2E·평가 정답 파일을 새로 열지 않았다.

초기 Day4 Step4의 T01 502/후속 Provider400 기록도 존재한다. 복합 schema/role=tool 문제를 거쳐 user FunctionResponse·signature 보존, 단순 JSON 토큰 선택·서버 엄격 검증으로 발전한 이력과 이후 성공을 구분한다.

현재 SDK2.31.0, 모델 설정, temperature0/4096 토큰/attempts1/단순 JSON 구조는 과거 최종 감사와 큰 틀에서 같다. Git의 기존 안정화 service 소스와도 대조했다. 반면 현재는 WARNING history 정책이 있고, 현 기본 최종 timeout15초는 과거 일부 성공 회차의 명시적30초와 다르다. **어느 차이가 최근502를 유발했는지는 UNKNOWN**이다. 새로 30초나 다른 모델로 바꾸지 않았다. 과거 모든 run의 환경·프롬프트·Provider 서버 상태가 현재와 같았다는 완전한 fingerprint도 없다.

## I. 실제 수정 파일 및 이유

기존 파일6개 최소 수정:

- `backend/agent/service.py`: 원문 없는 진단, 안전 상태 코드, 검증 실패 로그, known Mock NG 제한 문구, owned client 정리.
- `backend/agent/diagnostics.py`: 고정 allowlist Provider code 함수 공유. Generation Config 변경 없음.
- `frontend/src/components/AgentPanel.tsx`: 실패 후 이전 성공 제거, 저장/라이브 상태 분리, 검사 ID·요청 순서 guard, 중복 확인 클릭 차단, 503 오진 방지.
- `scripts/safe_regression_backend.py`: 신규 Agent E2E38개와 기존 API70개를 기존 선택 그룹에 추가. 경고/실호출 안전 지표 기록.
- `scripts/run_safe_regression.ps1`: 기존 그룹을 유지하면서 신규 Node/Agent Chrome 그룹 추가, 경고 수·실제 호출 수·운영 보호 결과 출력.
- `frontend/scripts/test_step4_browser.mjs`: 기존12개를 그대로 유지하고 --agent 모드에서 동일 격리 브라우저 기반을 재사용. ImageView 생산 코드는 변경하지 않음.

신규 파일5개:

- `tests/test_day7_step5_agent_e2e.py`: FakeGemini, 독립 JSONL, HTTP→service→Python 도구→Evidence→최종 검증→보고서 GET의 오프라인 E2E.
- `frontend/src/utils/agentAnalysisState.ts`: 구분된 live 상태 및 안전 오류 문구.
- `frontend/scripts/test_agent_analysis_state.mjs`: 상태/503/timeout/안전 문구5개 단위 테스트.
- `frontend/scripts/agent_browser_cases.mjs`: 실제 AgentPanel의 합성8개 시나리오.
- 본 보고서.

기존 dirty tree에서의 Git 전체 diff는 Gemini의 선행 변경도 포함한다. 작업 시작 파일218개의 SHA 비교상 위 Codex 기존6개 외에 documentation-index 문서의 동시 변경1건을 관찰했다. 해당 문서는 Codex가 수정·복원하지 않았으며 다른 작업을 덮지 않았다. 작업 시작 시 이미 보였던 발표 PPT 삭제/이동도 그대로다.

## J. T01 / T03 / T06 / MOCK NG / ERROR Mock E2E

| 시나리오 | 입력 | 검증 결과 |
|---|---|---|
| T01 | 합성 INSP-001396 / OK | 결과 도구 → 유효 catalog → 최종 보고서/GET. 원본 OK와 JSONL 해시 유지 |
| T03 | 합성 INSP-001398 / 저밝기 REINSPECT + 합성 과거 기록 | 결과·품질, BACKEND_POLICY history 실제 Python 실행. REINSPECT 유지, 조명 가능성은 hypothesis |
| T06 | 합성 INSP-001390 / OK | 저장된 OK 유지. 임의 NG·결함 사실 생성 없음. 모델 무결점 보증 불가 한계 유지 |
| MOCK NG | 합성 INSP-001391 / 점수45 / NG | 모델을 실행하지 않은 fixture. 서버가 테스트 fixture/실제 PatchCore 성능 아님을 제한 문구에 추가 |
| ERROR | 합성 INSP-009990 / 이미지 로드 실패 | ERROR/UNKNOWN/null 점수 유지, 실제 저장된 실패 이벤트에 Evidence 연결 |

모든 fixture는 테스트 코드로 새로 생성했다. 기존 검사·사용자 제품의 실제 결과·이미지·정답을 복사하지 않았다. 예시 ID가 같아도 실제 저장 기록을 읽었다는 의미가 아니다. Mock 완료 응답의 운영상 LIVE_AGENT_ANALYSIS provenance는 **생산 경로의 동작 시험**이며 테스트 로그에서 실제 Gemini 성공으로 집계하지 않는다.

## K. 악성/비정상 Function Call 방어

신규38개 + 기존 service/API/reporting/반례 테스트에서 다음을 검증했다.

- 미허용 도구, 필수 인자 누락, bool·추가 인자, 다른 inspection_id: Python 실행 전에 거부.
- 여러 call/같은 도구 반복/round·call 제한, 초과 후 추가 요청·가짜 Evidence 없음.
- 빈 응답/MAX_TOKENS/깨진 JSON/없는 Evidence 토큰/임의 Pointer·observed_value/판정 변경 시도: 안전 실패, 원본 JSONL 동일.
- 기존 catalog 변조·실제 Fact 값 불일치·다른 제품 alias·signature 및 FunctionResponse 연결 검증 유지.
- 동시 요청의 RequestState/Evidence/catalog 혼입 방지.
- Provider timeout/연결/SDK/429/5xx는 자동 재시도 없이 종료.
- 앱 client 재사용·종료 및 fallback cleanup은 Fake 생성자만 사용해 검증.

잘못된 JSON 문자열 인자는 SDK 이전의 자유 파일 경로로 해석하지 않는다. 서버에서 dict/Pydantic 스키마를 만족하지 않으면 거부한다. 모델의 보고서 필드는 추가 필드도 거부한다.

## L. 오프라인 네트워크 차단

기존 안전 러너의 실제 SDK 생성 금지·HTTPX 실제 전송 금지·socket 연결 금지·checkpoint 로딩 금지·운영 경로 쓰기 금지를 유지했다. 네이티브 모델은 생성하지 않았다. Windows asyncio의 표준 socketpair self-pipe 외 실제 연결은 허용하지 않는다. 신규 E2E에도 genai.Client와 BaseApiClient request/async_request 금지 fixture를 두었다. 필요한 생성자 lifecycle 시험은 명시적 Fake만 주입했다.

FastAPI 요청은 실서버가 아닌 ASGI TestClient로 전달했다. 모든 기록/보고서는 고유 run 하위 임시 디렉터리다. .env 자동 로딩은 끄고 기존 DB URL/API key를 테스트에 전달하지 않았다. 기존 Agent의 상대 보고서 저장 경로도 임시 cwd 안이다.

Chrome은 기존 설치본과 신규 프로필을 사용하며 Mock fetch만 처리한다. 실서버 proxy는 없고 하위 localhost 테스트 서버는 모든 API/POST 직접 전송을 거부한다. 화면의 확인 버튼 클릭은 **가짜 transport에만** 연결된다. 실제 서버의 Inspect/Gemini 버튼을 클릭하지 않았다. 사용자 Chrome/서버 프로세스를 종료하지 않았다.

최종 safety.json: forbidden_io=0, network=0, real_prediction=0, real_load=0, real_gemini_api_calls=0. Python 가드가 악의적인 native 코드까지 막는 OS sandbox라는 주장은 하지 않는다. Vite HMR의 CSP 차단/Canvas 성능 안내는 브라우저 증거에 남아 있으며 운영 콘솔이 완전히 무경고라는 의미도 아니다.

## M. Backend 자동화 결과

동일 명령으로 실행했다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_safe_regression.ps1
```

backend는 `safe_regression_backend.py backend --output <RUN>` 아래에서 선정된13개 모듈을 `pytest -q -rs --tb=short -p no:cacheprovider --basetemp <RUN>/pytest --junitxml <RUN>/backend.xml --log-file <RUN>/pytest.log`로 실행한다.

| 범위 | PASS / FAIL / SKIP |
|---|---|
| 기존 Step4 선택 그룹 | 303 / 0 / 10 |
| 신규 Step5 Agent Fake E2E | 38 / 0 / 0 |
| 기존 test_agent_api 추가 통합 | 70 / 0 / 0 |
| **최종 합계** | **411 / 0 / 10**, 18.03초 |

초기 모델 비활성화 fixture 설정 전 startup model loader에 접근하려던 테스트는 안전 가드가 실행 전에 SKIP시켰다. 실제 로딩은 없었으며 startup에서도 ENABLE_PATCHCORE=False를 적용한 뒤 정상 실행했다. 초기 통합의4 FAIL은 APIError-shaped Mock 진단 코드 호환성이었고 allowlist 처리로 해결했다. 실패 결과를 숨기거나 기존 assertion을 제거하지 않았다.

## N. Frontend / Chrome Mock E2E 회귀

- 기존 Node21 + 신규5 = **26 PASS**, 123.8211ms. 기존 좌표·GV·Heatmap 검증을 제거하지 않았다.
- 기존 Chrome Mock12: 그대로 PASS. 사용자 확인된 PatchCore/Sidecar/ImageView/Zoom/Pan 소스는 변경하지 않았다.
- 신규 Agent Chrome Mock8: 저장 GET만 실행, 라이브 실패 후 이전 성공 제거, 중복 확인 방지, cached live와 신규 live 구분, 늦은 GET/POST 차단, 비-key503 오진 방지, HTTP200/FAILED에 성공 배지 금지를 확인했다.

UI에는 RECORDED TEST FIXTURE, STORED LIVE REPORT, LIVE NOT YET VERIFIED / RUNNING / FAILED / COMPLETED를 구분한다. 완료 상태는 이번 탭의 정상 POST 응답일 때만 표시하고 단순 저장 GET은 새 live 검증으로 승격하지 않는다. known Mock NG 입력은 별도 fixture 입력 배지를 표시한다.

`step5-browser-reproduce`에서 기존 UI의 ‘라이브502 후에도 예전 fixture 보고서/배지 유지’를 실제 Chrome으로 재현한 뒤 최소 수정했다. --agent 모드는 같은 Chrome harness를 재사용할 뿐 실제 모델/API 성공을 입증하지 않는다.

## O. TypeScript / Build / Lint

`frontend/node_modules/.bin/tsc.cmd -b`, `npm.cmd run lint`, `npm.cmd run build` 모두 종료0. 최종 Vite build는351ms다. 패키지 설치·SDK/Model/Production Generation Config·threshold·timeout 설정 변경은 없었다.

## P. 기존10 SKIP 및 lint6 경고

- 실제 모델 로딩/추론 제외6, 모델 선행 데이터가 없는 기존 조회1, 실제 데이터셋 없는 storage workflow2, Windows symlink 생성 권한 부재1 = **10 SKIP** 그대로다. 억지로 실제 모델/이미지를 실행하거나 PASS로 재표기하지 않았다.
- pytest1 경고는 anyio 사전 import에 따른 PytestAssertRewriteWarning이다.
- lint6건: AgentPanel의 기존 state-in-effect1, ImageView state-in-effect2, ImageView exhaustive-deps3. 새로 생겼던 refs 경고는 이번 AgentPanel 범위에서 제거했다. 기존6 경고를 숨기거나 ImageView를 수정하지 않았다.

## Q. 실제 Gemini API 호출

**0회.** 단일 연결 스크립트는 읽기만 했으며 --execute-once나 실서버 POST /analyze를 실행하지 않았다. 과거 단일 요청 승인도 재사용하지 않았다. 이번 HTTP POST는 모두 ASGI/Fake 또는 브라우저 Mock 응답이다.

## R. 실제 PatchCore 자동 추론

**checkpoint 로딩0회 / 실제 forward0회.** 신규 fixture·startup에서 비활성화하고 전역 가드도 유지했다. 사용자 INSP-001650의 실제 모델 실행을 이번 자동화 결과로 합산하지 않는다.

## S. 운영 데이터 및 원본 파일

운영 JSONL/기존 Sidecar·보고서/모델/전처리·판정 소스/영상/.env 등 최종 fingerprint **32개 전후 동일**. 작업 시작 시 읽을 수 있었던218개 파일의 비교에서도 금지 코드·기존 JSONL·공식 checkpoint 변경이 없었다. 초기 샌드박스 baseline에서는 일부 기존 Sidecar의 해시 읽기가 거부돼 제외됐으며, 이를 읽은 것으로 주장하지 않는다. 해당 Sidecar를 포함한 운영32개는 승인된 샌드박스 외부 러너에서 전후 비교했다. 원본 이미지와 Ground Truth는 읽지 않았다.

ImageRegistry/LiveView/Grab/ROI/PostgreSQL/Sidecar/ImageView 소스 변경0건, 운영 inspection_id 발급0건, 기존 운영 JSONL append0건, PostgreSQL/Docker/Volume 작업0건, 외부 평가 경로 접근·목록 조회0건, Git add/commit/push/reset/restore/clean0건. 빌드 산출물과 고유 테스트 출력만 별도로 생성했다.

## T. 남은 위험

1. 최근502의 실제 Provider 원인은 UNKNOWN, 현재 Live Function Calling 성공은 NOT VERIFIED다. 현재 모델 가용성/계정권한/과금/네트워크는 새 실호출 없이 확정할 수 없다.
2. 과거 일부 성공의 최종30초와 현 기본15초 차이는 위험 후보일 뿐 인과 증거가 아니다. 무단 변경하지 않았다.
3. Mock NG 출처는 현재 알려진 fixture ID에 대해 명시한다. 임의로 주입된 모든 기록의 provenance를 추론하는 일반 시스템은 아니다.
4. 기존 Agent 보고서는 상대 디렉터리에 저장하고 같은 ID 파일을 덮어쓰며 저장 오류를 삼키는 구현이다. 이번에는 원본 검사 불변성과 정상 임시 저장을 검증했지만 보고서 영속 저장의 원자성/실패 상태는 별도 보완 대상이다. 따라서 후속 live 계획에서 기존 보고서 덮어쓰기 승인을 별도로 확인해야 한다.
5. 브라우저 버튼 중복은 ref로 차단하지만 여러 탭/외부 클라이언트의 중복 POST를 서버 idempotency로 막은 것은 아니다. 라이브 승인은 단일 탭·한 요청으로 제한해야 한다.
6. API 오류 body는 기존 안정 코드 계약을 유지한다. 상세 제공자 진단은 서버 로그에 있으며 correlation_id는 현재 inspection_id 기반이라 같은 검사에 대한 여러 동시 요청의 고유 request UUID는 아니다.
7. 기존 Normalize/Calibration 문제는 변경하지 않았으며 해결된 것으로 표시하지 않는다. 전체 회귀/Cloud Run/공용 네트워크 인증을 이번에 승인한 것도 아니다.
8. 저장 보고서 GET은 `backend/main.py:628`의 별도 파일 조회다. POST와 동일한 strict ID 검증을 사용하는 구조가 아니며 파일 읽기 오류 원문을 반환할 수 있다. 저장 보고서 경로 보안은 별도 확인·최소 보완이 필요한 위험으로 남긴다. 이번에는 임의 파일 접근 실험이나 허용 범위 밖 main.py 수정은 하지 않았다.

## U. 별도 승인 후 1회 Live E2E 계획 — 미실행

**지금은 실행하지 않는다. 아래 전체 범위의 명시 승인이 필요하다.**

- 대상: 사용자 확인 완료 **INSP-001650**. 먼저 저장 결과 OK/score31.3346/threshold34.1442가 그대로인지 읽기 전용으로 확인한다. 이미지·PatchCore는 재실행하지 않는다.
- 정확한 endpoint: 현재 승인된 localhost 백엔드의 **POST /analyze/INSP-001650**, JSON body 없음. 예: 로컬 서버가8000일 때 `http://127.0.0.1:8000/analyze/INSP-001650`. 실제 포트는 실행 전 운영자가 확인한다.
- Model/SDK: 기존 gemini-3.8-flash / google-genai2.31.0 유지. 실제 서버의 비민감 설정 fingerprint(api_version, model, budget, attempts)만 확인하고 키/헤더는 출력하지 않는다.
- ‘1회’의 의미를 구분한다: **분석 HTTP 요청1회**, 기본 도구 실행 최대4 round/8 call/동일2. 정상 조기 종료라면 예상 SDK2회, 구현상 보수적 **SDK/외부 전송 최대6회**. **외부 SDK 요청 딱1회만 승인한다면 완전한 Function Calling E2E는 진행할 수 없으므로 중단하고 승인을 다시 확인한다.**
- timeout: 현 기본 Agent60초/조사15초/최종15초/도구3초, SDK attempts1. 실제 서버에 다른 승인 설정이 있으면 기록하고 범위를 먼저 합의한다. 자동 연장·모델 교체·토큰 설정 변경 없음.
- 과금: SDK 요청별 외부 Google API 과금 가능. 여러 도구 round가 하나의 무과금 요청이라는 오해를 피한다.
- 수명/저장: 새 inspection_id·운영 검사/로그 JSONL은 만들지 않는다. 성공 시 분석 ID·진단 응답 및 Agent 보고서 파일이 생성될 수 있다. **같은 ID의 기존 보고서가 있으면 덮어쓰기 전 별도 승인 없이는 중단한다.** 모델/이미지/Sidecar/ROI DB는 불변이어야 한다.
- 실행: 사용자 승인 후 단일 탭에서 확인 버튼1회 또는 승인된 단일 HTTP 클라이언트 중 하나만 사용한다. 다른 탭의 분석·자동 테스트·재시도는 정지한 상태로 확인한다. 사용자 서버 프로세스를 강제 종료하지 않는다.
- 상한 계측: 분석 요청1, SDK 전송 최대6, 자동 retry0을 외부 요청 카운터로 기록할 수 있는 승인된 계측을 사용한다. 실패 시 **재실행하지 않는다**. 카운터/진단 필드만 기록하고 prompt·credentials·tool payload 원문은 저장하지 않는다.
- 성공 조건: HTTP200/COMPLETED, 실제 Python 도구 실행 trace, 유효 Evidence/Fact/Pointer, 원본 OK/snapshot 불변, 새 분석 ID와 provenance 확인, JSONL/모델/Sidecar 해시 동일. GET 저장 조회 성공만으로 live 성공 판정 금지.
- 실패 시: HTTP·error_code·correlation_id·stage·exception_class·Provider http_status/provider_code·실제 SDK 전송 횟수만 확인한다. MAX_TOKENS/JSON/Evidence 실패도 구분하고 추측성 원인 확정이나 자동 재시도를 하지 않는다.

**오프라인 준비 완료 상태에서 종료한다. 실제 API 호출·추가 기능 개발은 다음 사용자 승인을 기다린다.**
