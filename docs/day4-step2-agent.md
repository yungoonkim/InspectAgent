# Day 4 Step 2: Gemini Agent 오케스트레이션

이 단계는 공식 `google-genai==2.31.0` SDK의 Generate Content Function Calling
프로토콜과 Mock 기반 검증을 구현합니다. 실제 Gemini 호출·모델 가용성·실제 진단 품질은
`NOT TESTED`입니다. 이후 구현된 HTTP 엔드포인트의 계약은
[Day 4 Step 3 API 문서](day4-step3-api.md)를 참조하세요.

## 모듈과 호출

- `backend/agent/tools.py`: 기존 Step 1 도구를 변경 없이 재사용합니다.
- `backend/agent/service.py`: `AgentService(tools, settings=None, client=None, limits=None)`와
  `async analyze(inspection_id: str) -> DiagnosisResult`를 제공합니다.
- `backend/agent/prompts.py`: 운영용 지침이며 평가 문서나 시나리오 정답을 포함하지 않습니다.
- `backend/agent/schemas.py`: 호출 인자·제한·진단 초안·최종 결과·실행 Trace를 검증합니다.
- `tests/test_agent_service.py`: SDK 응답 객체와 AsyncMock 클라이언트로 네트워크 없이 검사합니다.

`client` 주입은 SDK 형태(`client.aio.models.generate_content`)를 가진 테스트 대역을 위한 것입니다.
서비스 코드 자체는 실제 SDK 클라이언트도 생성할 수 있으므로, 실제 분석 호출은 별도 승인이 필요합니다.
클라이언트를 주입하지 않으면 기존 `GEMINI_API_KEY`와 `GEMINI_MODEL` 설정을 사용합니다.
모델 ID는 형식만 검증하며, 모델 목록이나 실제 API를 조회하지 않습니다.

## Function Calling 프로토콜

공식 SDK의 자동 Python 함수 실행은 편리하지만 실행 전 검증과 상세 감사 Trace를
서버가 직접 제어하기 위해 수동 실행을 선택했습니다.

1. 네 개의 `types.FunctionDeclaration(parameters_json_schema=...)`를 선언합니다.
2. `AutomaticFunctionCallingConfig(disable=True)`, Function Calling mode `AUTO`로 요청합니다.
3. 후보의 `Content.parts[].function_call`에서 이름·인자를 읽고 검증합니다.
4. 허용된 `InspectionTools` 메서드만 호출합니다. 선행 일괄 조회는 없습니다.
5. 반환된 모델 Content를 그대로 다음 요청에 포함하여 thought signature를 보존합니다.
6. 실제 도구 결과를 `types.FunctionResponse(name, id, response)`로 전달합니다.
   함수 응답 ID는 모델이 반환한 호출 ID를 그대로 연결하며 공개 Trace에는 포함하지 않습니다.
7. 여러 호출은 반환 순서대로 실행하고, 여러 라운드는 제한 안에서 계속합니다.
8. 저장된 여섯 핵심 판정이 모두 정상 조합이고, 유한한 이상 점수·임계값이 기록되어
   점수가 임계값 이하이면 도구 결과를 받은 직후 종료 확인 없이 구조화 단계로 전환합니다.
   그렇지 않으면 기존 제한 내 조사를 유지하며 모델이 추가 호출을 요청하지 않을 때 전환합니다.
   도구 없는 별도 요청에서
   `response_mime_type=application/json`과 `response_json_schema=diagnosis_response_json_schema()`를 사용합니다.
   외부 전달용 JSON Schema는 DiagnosisDraft에서 생성하며, 서버에서는 원래 DiagnosisDraft의
   엄격한 Pydantic 검증과 결정적 근거 검증을 그대로 적용합니다.
   최종 요청은 독립된 `user` Content의 JSON 텍스트에 서버가 보관한 실제 Evidence와
   최소 실행 Trace만 담습니다. `evidence_id`별 `source_tool`과 원래 도구 응답 `document`를
   유지하고, JSON Pointer는 해당 document를 기준으로 검증합니다.
   조사 단계의 모델 Content·서명·FunctionResponse는 최종 요청으로 넘기지 않습니다.
   정상 조기 종료에서는 네이티브 FunctionResponse 후속 전송 대신 동일 조회 결과를 이 근거
   패킷으로 전달합니다. 추가 조사가 필요한 라운드에서는 기존 FunctionResponse 프로토콜과
   전체 Content·서명·호출 ID 보존을 유지하며, 병렬 호출의 Part나 응답을 생략하지 않습니다.
   최종 전용 system_instruction은 도구 선택 지침을 포함하지 않습니다. 서버가 보유한 원래
   Evidence와 Trace가 검증 기준이며 모델이 생성한 요약이나 조사 문장은 근거로 사용하지 않습니다.
   이는 요청 구성의 결합을 줄이는 오프라인 개선이며 실제 서버 호환성 입증은 별도 승인 실험이 필요합니다.
9. JSON 파싱, 엄격한 Pydantic 검증, 실제 근거 비교를 통과해야 분석 성공입니다.

SDK 공식 참고:
- [Function Calling 및 수동 함수 응답](https://googleapis.github.io/python-genai/#function-calling)
- [JSON Response Schema](https://googleapis.github.io/python-genai/#json-response-schema)
- [Structured Output](https://ai.google.dev/gemini-api/docs/structured-output)

설치된 SDK에서 HttpOptions timeout은 밀리초, HttpRetryOptions attempts는 최초 요청을 포함한
횟수임을 확인했습니다. `attempts=1`로 자동 재시도를 끕니다. 사용량은 SDK가 반환한
prompt/candidates/total token count만 기록하고, 없으면 null입니다. HTTP 헤더·원본 응답 덤프는 노출하지 않습니다.

## 대상과 컨텍스트 경계

검사 ID는 Step 1 검증을 재사용하고 모든 검사 조회 호출에 고정합니다.
이력은 성공한 `get_inspection_result`의 실제 제품 ID가 확인된 뒤에만 허용합니다.
Gemini에는 제품 ID를 `TARGET-PRODUCT`라는 불투명 별칭으로 전달하고,
모델이 이 별칭을 요청할 때만 서버가 신뢰된 실제 제품 ID로 해석합니다.
원본 제품 ID·image_id는 모델 컨텍스트에서 제거하거나 중립화합니다.
Step 1의 반환값과 검사 기록 자체는 변경하지 않습니다.

모델에 파일·쉘·Python 실행·검색·임의 HTTP·비밀정보 조회 도구를 제공하지 않습니다.
인자는 엄격한 Pydantic 모델로 검증하며 추가 인자·다른 검사 ID·미확인 제품 ID를 거부합니다.
로그 메시지와 주입·정답 정보는 Step 1 도구의 허용 필드 추출로 제외합니다.
도구 데이터는 시스템 명령으로 취급하지 않습니다.

## 근거 검증과 진단 표현

모델의 DiagnosisDraft는 검사 ID, 요약 코드, observed_facts, 원인 후보 코드,
점검 코드, 한계 코드만 포함합니다. 임의의 prose·Trace·tools_used를 초안에 추가할 수 없습니다.
서버가 검증된 코드에 대응하는 한국어 표현을 생성하여 경로·정답·근거 없는 수치가
자유 문장에 섞이는 것을 구조적으로 제한합니다. 진단 표현은 의도적으로 제한적입니다.

각 사실은 `fact_id`, `evidence_id`, `source_tool`, `source_field`(JSON pointer),
`source_event`, `observed_value`로 구성합니다. 서버는 다음을 결정적으로 비교합니다.

- 실제 성공한 호출에서 생성한 evidence_id와 도구 이름
- 도구 응답의 해당 scalar 값과 모델의 값 (숫자는 정확히 비교, bool과 숫자는 구분)
- 로그 사실의 source_event와 실제 해당 로그의 event_code
- status/result/image_quality_status/defect_detection_status/final_result/final_reason_code의
  필수 사실과 현재 대상 검사 snapshot
- 요약 코드와 저장된 final_result
- 원인·점검 코드의 참조 사실과 지원 조건

밝기 경고가 있어야 조명·노출 가설/점검을 선택할 수 있습니다.
로드 실패 이벤트 또는 FAILED+영상 ERROR 근거가 있어야 이미지 획득 가설/점검을 선택합니다.
추론 불가/UNKNOWN 판정 근거는 모델·판정 기준 점검에 연결합니다.
이력의 다른 검사 사실만으로 현재 검사에 대한 장애 가설을 확정하지 않습니다.
Pydantic 검증만으로 사실 일치를 주장하지 않습니다.

최종 결과는 inspection_id, analysis_status, error_code, overall_summary,
inspection_snapshot, observed_facts, possible_causes, recommended_checks, limitations,
tools_used, tool_execution_trace, model_name, token_usage, model_availability를 포함합니다.
필수 한계 문구는 서버가 보완하며 당시 밝기 기준치는 현재 설정으로 대체하지 않습니다.

## 실행 Trace

Trace는 모델이 작성하지 않고 서버가 실제 실행에서 생성합니다.
sequence, round_number, tool_name, 검증된 arguments, executed, success, error_code,
실측 elapsed_ms, evidence_id를 포함합니다. 미허용 이름은 null이며 원시 인자는 기록하지 않습니다.
제품 인자는 공개 Trace에 별칭으로 기록합니다.
tools_used는 실제 실행되고 도구 응답이 성공한 기록만 중복 없이 집계합니다.

Mock 프로토콜 테스트의 검증된 흐름:

| 예시 | 요청/실행 순서 | Trace |
|---|---|---|
| 단일 호출 | 모델이 결과 조회 요청 → 실제 Python 결과 조회 → 최종 JSON | sequence 1, round 1, executed/success=true, E0001 |
| 한 라운드 복수 호출 | 결과 조회와 로그 조회 요청 → 각각 실제 Python 실행 | sequence 1/2, round 1/1, E0001/E0002 |
| 여러 라운드 | 첫 라운드 결과 조회 → 두 번째 라운드 로그 조회 | sequence 1/2, round 1/2, E0001/E0002 |
| 잘못된 도구 | 모델이 미허용 함수 요청 → 검증 거부 | executed=false, success=false, TOOL_NOT_ALLOWED |

위 흐름은 실제 Gemini가 선택했다는 증거가 아닌 Mock 응답에 대한 서버 실행 검증입니다.
실제 SDK 응답의 FunctionCall/FunctionResponse 형태를 사용하고 저장소 spy로 Python 호출을 확인합니다.
실행 시간은 테스트 환경에서 측정하며 고정된 가짜 지연시간을 보고하지 않습니다.

## 제한과 실패 코드

| 설정 | 기본값 |
|---|---:|
| AGENT_MAX_TOOL_ROUNDS | 4 |
| AGENT_MAX_TOOL_CALLS | 8 |
| AGENT_MAX_REPEAT_CALLS | 2 |
| AGENT_REQUEST_TIMEOUT_SECONDS | 60 |
| AGENT_MODEL_TIMEOUT_SECONDS | 15 |
| AGENT_TOOL_TIMEOUT_SECONDS | 3 |
| AGENT_MAX_PAYLOAD_BYTES | 65536 |

SDK 요청당 최대 출력은 4096 tokens입니다. 도구 라운드 종료 확인 요청과 별도 구조화 요청도
전체 시간 제한에 포함합니다. 반환 결과와 누적 대화 Contents의 UTF-8 JSON 크기를 제한합니다.
초과 시 자르거나 성공으로 처리하지 않고 실패합니다.

동기 Step 1 도구는 최대 4개의 공유 worker와 비차단 capacity gate로 실행합니다.
타임아웃은 응답 대기를 종료하지만 이미 시작한 Python 스레드를 강제 중단하지 못합니다.
따라서 읽기 전용 조회가 잠시 계속될 수 있으며 작업 완료 시 슬롯을 반환합니다.
이 제한은 명시적인 정책이며 스토리지 드라이버 차원의 I/O deadline은 후속 과제입니다.
SDK client 종료는 별도의 bounded cleanup을 적용합니다.

주요 안정적 실패 코드는 다음과 같습니다.

- 설정/서비스: INVALID_ARGUMENT, INVALID_MODEL_CONFIG, MISSING_API_KEY,
  GEMINI_REQUEST_FAILED, GEMINI_TIMEOUT, AGENT_TIMEOUT
- 호출: TOOL_NOT_ALLOWED, TOOL_ARGUMENT_INVALID, INSPECTION_SCOPE_MISMATCH,
  PRODUCT_SCOPE_MISMATCH, TOOL_CALL_LIMIT, TOOL_REPEAT_LIMIT, TOOL_ROUND_LIMIT,
  TOOL_TIMEOUT, TOOL_CAPACITY_EXCEEDED, TOOL_EXECUTION_FAILED
- 데이터: NOT_FOUND, STORAGE_ERROR, DATA_UNAVAILABLE, TOOL_RESPONSE_INVALID,
  TOOL_DATA_TOO_LARGE, CONTEXT_TOO_LARGE, MODEL_RESPONSE_TOO_LARGE
- 최종 결과: INSUFFICIENT_EVIDENCE, MODEL_RESPONSE_INVALID, MODEL_RESPONSE_INCOMPLETE,
  UNEXPECTED_FUNCTION_CALL, FINAL_JSON_INVALID, RESPONSE_SCHEMA_INVALID, EVIDENCE_MISMATCH

DATA_UNAVAILABLE인 선택적 로그/이력은 모델에 실패 응답으로 전달하고 한계를 표시할 수 있습니다.
검사 부재·저장소 실패·잘못된 호출·자원 제한·최종 검증 실패는 analysis_status=FAILED입니다.
검사 status=FAILED인 레코드를 성공적으로 조사한 경우에는 분석 상태가 COMPLETED일 수 있습니다.
내부 예외·API 키·모델 원문·평가 정답은 오류 결과에 포함하지 않습니다.

## 검증과 남은 작업

SDK 설치 과정에서 websockets가 17.2에서 SDK 요구 범위의 16.1.1로 조정됐습니다.
`pip check`로 의존성 정합성을 확인했습니다. 기존 ML/Web 핵심 패키지는 교체하지 않았습니다.
실제 모델의 프로토콜 지원·기능 선택·토큰 과금·진단 품질은 아직 검증하지 않았습니다.
이력 조회 범위, JSONL 손상 행·다중 프로세스·영구 저장, 모델 로딩 실패 시 기록 부재,
기존 개발 API 노출 및 오래된 평가/구현 문서 문제는 이번 범위에서 수정하지 않습니다.
Step 3의 HTTP 연결은 별도 Mock 검증으로 완료하며, 실제 API 호출 검증은 Step 4에서 승인 후 진행합니다.

검증 결과:
- Step 2 신규 Mock 테스트: 65개 통과
- Step 1 도구 테스트와 합동 실행: 141개 통과
- 전체 회귀: 기존 181개 + 신규 65개 = 246개 통과, 실패/건너뜀 0개
- 기존 timm/anomalib FutureWarning 2건
- `pip check`: No broken requirements found
- `git diff --check`: 공백 오류 없음 (저장소의 LF/CRLF 안내만 발생)
- 운영 JSONL 두 파일, 체크포인트, 모델 메타데이터, Step 1 tools.py,
  판정/API 코드와 기존 주입 이미지의 전체 실행 전후 SHA256 일치

실행 명령은 Conda `vision-insight`의 Python으로
`python -m pytest tests/test_agent_service.py tests/test_agent_tools.py -q -p no:cacheprovider`와
`python -m pytest tests -q -p no:cacheprovider`를 사용했습니다.
실제 실행에는 고유한 `--basetemp`를 지정하고, 전체 실행에서는 검사·로그·주입 이미지·산출물
경로를 임시 디렉터리로 바꾼 뒤 기존 주입 이미지 사본을 준비했습니다.
최초 실행은 기존 pytest 임시 폴더 권한 때문에 54개 통과/1개 setup 오류였으며,
새 임시 폴더로 재실행했습니다. 누적 컨텍스트 한계 테스트의 기대 요청 횟수를
실제 2회로 바로잡았습니다. 기능 검증과 실제 API 검증을 구분합니다.
