# Day 4 Step 4 — 실제 Gemini 검증 기록

## 승인 범위와 실행 방식

- Phase B: T01 `INSP-001396` 한 건만 명시적으로 승인받아 분석 1회 시도했습니다.
- FastAPI TestClient를 통해 실제 `POST /analyze/INSP-001396` 라우트를 실행했습니다.
- AgentService와 Python 조회 도구는 실제 구현을 사용했습니다. Gemini 클라이언트는 Mock이 아니라
  공식 SDK의 실제 요청을 전달하는 계측 래퍼를 사용했습니다.
- SDK 호출과 실제 HTTP 전송 경계, Python 도구와 저장소 조회를 각각 관찰했습니다.
- 모델 변경, 재시도, 신규 검사 생성, 다른 시나리오 호출은 수행하지 않았습니다.
- API 키·인증 헤더·원시 예외·원본 경로·평가 정답은 기록하지 않습니다.

## 환경과 제한

- SDK: `google-genai==2.31.0`
- 모델: `gemini-3.8-flash`
- API 키 존재 확인 후 인증에만 사용했습니다. 값은 출력하지 않았습니다.
- 최대 도구 라운드 4, 실행 8회, 동일 호출 2회
- 모델 timeout 15초, 도구 timeout 3초, Agent 실행 timeout 60초
- SDK `attempts=1`, 자동 Python 함수 실행 비활성화
- 실제 분석 시도 1회, SDK generate_content 호출 2회, HTTP POST 전송 시도 2회

## 시나리오 결과

| 시나리오 | 검사 ID | 분석 HTTP | 실제 Function Calling | 근거 검증 | 최종 결과 |
|---|---|---:|---|---|---|
| T01 | INSP-001396 | 502 | 1차 요청에서 발생, Python 조회 성공 | NOT TESTED | FAIL |
| T03 | — | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED |
| T05 | — | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED |
| T06 | — | NOT TESTED | NOT TESTED | NOT TESTED | NOT TESTED |

저장된 T01 판정은 status=COMPLETED, result=OK, final_result=OK,
final_reason_code=ALL_CHECKS_PASSED, image_quality_status=NORMAL,
defect_detection_status=COMPLETED였습니다.

### 실제 외부 요청

| 요청 | 단계 | Gemini HTTP | 결과 | 시간 |
|---|---|---:|---|---:|
| 1 | Function Calling | 200 | get_inspection_result 호출 반환 | 3273.667 ms |
| 2 | FunctionResponse를 포함한 후속 Function Calling | 400 | SDK ClientError, 분석 중단 | 319.444 ms |

두 번째 요청에는 실제 도구 결과의 FunctionResponse 1개가 포함됐습니다.
1차 응답의 호출 ID 1개와 thought signature 1개가 후속 요청에 보존됐음을 계측했습니다.
다만 후속 요청은 400으로 거부됐으므로 FunctionResponse의 서버 수락/처리가 성공했다고 판단하지 않습니다.
최종 Structured Output 요청에는 도달하지 않았습니다.

초기 모델 요청은 성공했으므로 모델 자체가 전혀 사용 불가능하다고 단정하지 않습니다.
두 번째 요청의 정확한 거부 필드는 이번에 기록한 안전한 상태 정보만으로 확정할 수 없습니다.
현재 코드의 FunctionResponse 메시지 role 등 후속 요청 호환성을 오프라인에서 점검할 필요가 있습니다.
광범위한 예외 키워드 분류만으로 모델 미지원이나 인증 실패를 확정하지 않습니다.

### Python 도구와 저장소 실행

HTTP의 선행 존재 확인과 모델 선택 도구 실행은 구분했습니다.
각 단계에서 get_inspection_result → 저장소 get_inspection 조회가 실제 발생했습니다.
아래 Trace는 선행 존재 확인을 제외한, 실제 모델이 요청한 Python 도구 실행 기록입니다.

```json
{
  "sequence": 1,
  "round_number": 1,
  "tool_name": "get_inspection_result",
  "arguments": {"inspection_id": "INSP-001396"},
  "executed": true,
  "success": true,
  "error_code": null,
  "elapsed_ms": 2.474,
  "evidence_id": "E0001"
}
```

실제 tools_used는 `["get_inspection_result"]`입니다.
도구 실행 라운드는 1회였고 후속 응답에서는 추가 도구 실행이 발생하지 않았습니다.
도구 호출 상한과 전체 분석 시간 제한을 초과하지 않았습니다.

### HTTP 응답과 분석 상태

```json
{
  "detail": {
    "analysis_status": "FAILED",
    "error_code": "GEMINI_REQUEST_FAILED"
  }
}
```

분석 HTTP 상태는 502, Agent 상태는 FAILED입니다. 최종 진단·관측 사실·원인 후보·점검 권고는
생성되지 않았으므로 해당 품질과 결정적 근거 검증 결과는 NOT TESTED입니다.
HTTP 실행 구간(lifespan 시작/종료 포함)은 7502.475 ms, 계측 프로세스 전체는 10940.849 ms였습니다.
현재 서비스의 model_availability 필드는 고정 NOT_TESTED이며 이를 실제 전체 프로토콜 성공으로 해석하지 않습니다.

## 토큰과 비용

| 요청 | 입력 | 출력 | thinking | total |
|---|---:|---:|---:|---:|
| 1 | 962 | 28 | 209 | 1199 |
| 2 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE |

위 수치는 1차 응답의 실제 SDK usage_metadata입니다. 전체 과금 토큰이나 비용으로 확정하지 않습니다.
총 비용은 NOT AVAILABLE입니다.

## 데이터 보호 및 후속 작업

- 각 실제 HTTP 요청 본문을 계측 경계에서 검사하고 금지 정보나 API 키가 발견되면 전송 전에
  차단하도록 했습니다. 이번 요청에서는 차단이 발생하지 않았습니다.
- 제품 ID 별칭 처리와 image_id 제외 정책, 기존 도구 허용 필드 정책을 유지했습니다.
- 운영 검사/이벤트 JSONL, PatchCore 체크포인트, 모델 메타데이터의 실행 전후 SHA256이 동일했습니다.
- 임계값·검사 정책·원본 이미지·평가 정답 파일은 변경하지 않았습니다.
- 이번 실행에서는 호환성 코드를 수정하지 않았고 추가 회귀 테스트/pytest 재실행도 하지 않았습니다.
  직전 전체 회귀 결과는 315개 통과이며 실제 API의 전체 성공을 증명하지 않습니다.
- T01 재실행이나 T03/T05/T06 호출은 하지 않았습니다. 추가 실제 API 요청은 별도 승인이 필요합니다.
- 후속 요청 호환성의 원인 확인·최소 수정·Mock 회귀 검증이 먼저 필요하며,
  현재 상태로 Step 5 완료 준비가 됐다고 판단하지 않습니다.

## T01 HTTP 400 오프라인 분석 및 최소 수정

이 절은 위 실제 실행 이후의 오프라인 작업입니다. 실제 Gemini 재호출은 0회이며,
과거 T01의 FAIL 또는 다른 시나리오의 NOT TESTED를 성공으로 변경하지 않습니다.
설치된 SDK는 `google-genai==2.31.0`입니다. 모델 ID와 SDK 버전은 변경하지 않았습니다.

### 확정한 구현 문제와 원인 확정의 한계

- 기존 코드는 FunctionResponse Content에 `role="tool"`을 지정했습니다.
  설치된 SDK의 `Content.role` 설명은 `user` 또는 `model`만 명시하지만 필드 자체는
  일반 문자열이므로 Pydantic이 `tool`을 거부하지 않습니다.
- SDK의 `_transformers.t_contents`와 `models._Content_to_mldev`는 명시적인 Content의
  role을 user로 교정하지 않습니다. 실제 SDK 변환기로 `tool`이 그대로 직렬화됨을
  네트워크 없이 재현했습니다. 이는 GenerateContent 프로토콜과의 구체적인 불일치입니다.
- FunctionResponse role을 `user`로 수정했습니다. 이전 첫 user Content와 모델이 반환한
  전체 candidate.content는 원래 객체 그대로 유지합니다.
- 기존 코드에서는 Function Call이 없는 마지막 모델 Content를 버려 최종 JSON 요청 앞에
  user Content가 연속 배치될 수 있었습니다. 해당 모델 Content도 보존하도록 수정했습니다.
  이는 후속 대화 구성 문제이며, T01 두 번째 요청 400의 직접 원인으로 주장하지 않습니다.
- 실제 기록에서 확인 가능한 오류는 두 번째 Function Calling 요청의 HTTP 400,
  SDK `ClientError`, Agent의 `GEMINI_REQUEST_FAILED`, 분석 HTTP 502입니다.
  당시 공개 가능한 서버 reason/status 문자열이나 거부 필드가 저장되지 않았으므로
  **서버 reason과 실제 400의 확정 원인은 UNKNOWN**입니다.
- role 불일치는 우선 수정한 유력한 원인 후보입니다. 수정 후 실제 서버 수락 여부,
  모델별 추가 제약, 최종 Structured Output의 실제 지원 여부는 NOT TESTED입니다.

### 공식 문서 대조

- [Function Calling 안내](https://ai.google.dev/gemini-api/docs/function-calling):
  현재 안내가 Interactions API 중심으로 연결되는 점을 확인했습니다. 기존 GenerateContent를
  Interactions나 OpenAI 호환 API의 역할 체계와 혼용하지 않습니다.
- [GenerateContent thought signature 지침](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures):
  user → model의 Function Call → user의 FunctionResponse 순서와 병렬 호출의 그룹 보존을
  기준으로 사용했습니다. 서명은 해당 Part에 유지하며 재구성하거나 합치지 않습니다.
- [공식 Python SDK 수동 호출 예제](https://googleapis.github.io/python-genai/#manually-declare-and-invoke-a-function-for-function-calling):
  candidate.content 전체 재사용 방식은 기존 코드와 같습니다. 다만 현재 예제 자체에는
  `role='tool'`이 남아 있어 위 프로토콜 예시 및 설치된 Content 설명과 불일치합니다.
  따라서 공식 문서가 모두 일치한다고 주장하지 않으며, 명시적인 GenerateContent 역할 정의와
  실제 설치 SDK의 직렬화 결과를 함께 근거로 최소 수정했습니다.

### 요청 구성 점검 결과

| 항목 | 오프라인 확인 결과 |
|---|---|
| 최초 user Content | 두 번째 및 이후 요청에서 동일 객체/내용 유지 |
| 모델 candidate.content | 전체 객체, 여러 Part의 순서와 경계 유지 |
| thought signature | 합성 바이트 0~255로 SDK 직렬화·역디코딩 후 일치 검증; 실제 서명 미출력 |
| FunctionResponse 역할 | user로 수정, 결과 Content에는 FunctionResponse Part만 배치 |
| 호출 이름/ID | 여러 호출 및 여러 라운드에서 순서별 일치 검증 |
| 도구 결과 JSON | 실제 InspectionTools의 허용 필드 응답을 dict로 전달; SDK JSON 직렬화 성공 |
| 도구 선언/설정 | 후속 Function Calling 요청에도 동일 네 선언과 AUTO 설정 유지 |
| 최종 JSON 요청 | 마지막 모델 응답 보존 후 별도 user 지시; 기존 도구 없는 구조화 요청 유지 |
| 잘못된 역할/순서 | SDK 호출 전 MODEL_RESPONSE_INVALID로 차단, 기존 HTTP 502 매핑 재사용 |
| 보안 및 근거 검증 | 검사 ID 고정, 제품 별칭, image_id 제외, JSON Pointer 검증, 서버 소유 Trace 유지 |

설치 SDK의 자동 continuation도 기본 활성화되어 있음을 소스에서 확인했습니다.
재시도와는 별개로 추가 요청을 만들 수 있어 `automatic_continuation=False`를 명시했습니다.
이는 비용/호출 수 통제 보강이며 기존 HTTP 400의 원인이라고 주장하지 않습니다.
기존 attempts=1, 수동 함수 실행, 도구·라운드·시간 제한은 유지합니다.

### 수정 파일 및 검증

- `backend/agent/service.py`: user 역할, 전체 모델 응답 보존, 전송 전 대화 순서·호출 응답
  대응 검증, 자동 continuation 비활성화. 내부 예외를 외부에 출력하지 않습니다.
- `tests/test_agent_service.py`: 기존 단일 호출 검증 보강 및 신규 16개 테스트.
  실제 SDK AsyncModels를 사용하되 전송 계층을 AsyncMock으로 대체해 요청 JSON을 검사했습니다.
  SDK 내부 변환 함수 사용 테스트는 설치 버전 종속 회귀 테스트이며 서버의 수락을 증명하지 않습니다.
- `tests/test_agent_api.py`: 두 번째 요청에서 합성 SDK ClientError(400)가 발생하는 신규 테스트 1개.
  실제 Python 조회 이후 재시도 없이 안전한 HTTP 502가 반환되고 임시 JSONL이 유지됨을 검증했습니다.
- `docs/day4-step4-gemini-validation.md`: 실제 실행 기록을 유지하고 이 오프라인 분석을 추가했습니다.
  API 및 응답 스키마, Step 1 조회 도구는 수정하지 않았습니다.

실행 환경: Conda vision-insight. pytest는 임시 검사/로그/출력 경로를 사용하고,
BaseApiClient의 동기·비동기 전송 메서드를 차단한 래퍼에서 실행했습니다.
테스트마다 Mock 또는 로컬 SDK 직렬화만 사용했습니다.

| 검증 | 실제 결과 |
|---|---|
| Agent 서비스 + HTTP 테스트 | 151 passed |
| 전체 `pytest tests -q -p no:cacheprovider` | 332 passed, 0 failed, 0 skipped |
| 기존 315개 회귀 + 신규 테스트 | 315 + 17개 모두 통과 |
| 실제 SDK 전송 경계 호출 시도 | 0회 |
| 실제 Gemini API 요청 | 0회 |
| `python -m pip check` | No broken requirements found |
| 변경 대상 한정 `git diff --check` | 오류 없음 |
| 저장소 전체 `git diff --check` | 기존 별도 문서의 trailing whitespace 1건; 이번 범위에서 미수정 |

첫 전체 실행에서는 빈 임시 test_data 경로에 기존 이미지 fixture가 없어 1 failed / 327 passed /
4 skipped가 발생했습니다. 기존 공개 시나리오 파일과 주입 이미지의 복사본을 임시 경로에 준비한 뒤
전체 332개 통과를 확인했습니다. 테스트 기대 결과나 운영 데이터를 변경해 해결하지 않았습니다.
SDK 직렬화 테스트 초기 fixture의 snake_case/REST camelCase 차이와 로그 조회의 선행 검사 존재 확인
횟수도 실제 SDK/도구 계약에 맞게 바로잡았습니다. 전체 실행 경고 3건은 외부 라이브러리 deprecation
2건과 테스트 래퍼의 anyio import rewrite 경고 1건입니다.

운영 검사 JSONL·이벤트 JSONL·체크포인트·메타데이터의 전후 SHA256이 동일합니다.
임계값·원본 이미지·평가 정답·기존 판정은 수정하지 않았습니다.
Git add/commit/push, 실제 API 재시도, 모델 전환은 수행하지 않았습니다.

T01 재검증을 위한 오프라인 준비는 완료했습니다. 실제 프로토콜 성공 여부는 별도 승인 후
T01 한 건으로 확인해야 하며, 승인 전 재호출하거나 다른 시나리오로 진행하지 않습니다.

## 수정 후 T01 재검증 승인 실행 — 외부 전송 전 계측 차단

### 승인과 실제 실행 범위

- 실행 시각: 2026-10-15 06:11:32 UTC (한국 시각 15:11:32).
- 승인된 `POST /analyze/INSP-001396`을 FastAPI TestClient에서 정확히 한 번 호출했습니다.
- 모델은 `gemini-3.8-flash`, SDK는 `google-genai==2.31.0`을 유지했습니다.
- 라운드 4, 도구 실행 8회, 동일 호출 2회, 모델 timeout 15초, 도구 timeout 3초,
  전체 분석 timeout 60초를 변경하지 않았습니다.
- attempts=1 및 automatic_continuation=False를 확인했습니다.
- SDK의 aiohttp 경로에는 연결 오류 시 별도 재전송 분기가 있어, 이번 수동 실행에서는
  HTTPX 경로를 사용하도록 실행 프로세스 안에서만 설정했습니다. 운영 코드는 변경하지 않았습니다.
- 실제 SDK generate_content와 실제 AgentService를 사용했으며 Mock Gemini 응답은 사용하지 않았습니다.
  단, 아래 계측 문제로 외부 Gemini 서버에 요청이 전달되지는 않았습니다.

### 관측 결과

| 항목 | 실제 결과 |
|---|---|
| HTTP 분석 요청 / Agent analyze 실행 | 각각 1회 |
| SDK generate_content 호출 | 1회, 로컬 실패 |
| 외부 Gemini HTTP 전송 | 0회, 전송 전 차단 |
| Gemini HTTP 상태 / 서버 reason | NOT AVAILABLE / NOT AVAILABLE |
| 실제 Function Call | NOT TESTED; 모델 응답 없음 |
| 모델이 선택한 Python 도구 실행 | 0회 |
| HTTP 선행 검사 조회 | get_inspection_result → 저장소 get_inspection, 성공 1회 |
| FunctionResponse 후속 요청 | NOT TESTED |
| 최종 구조화 응답 / 근거 검증 | NOT TESTED / NOT TESTED |
| 분석 HTTP / Agent 상태 | 502 / FAILED |
| Agent 오류 코드 | GEMINI_REQUEST_FAILED |
| tools_used / Tool Execution Trace | [] / [] |
| 토큰 사용량 / 비용 | NOT AVAILABLE / NOT AVAILABLE |
| HTTP lifespan 포함 실행 시간 | 112.503 ms |
| SDK 호출 구간 | 3.195 ms |
| 저장소 쓰기 시도 | 0회 |
| 종합 결과 | BLOCKED — 계측용 검사 오류; Gemini 재검증 미완료 |

실제 HTTP 응답:

```json
{
  "detail": {
    "analysis_status": "FAILED",
    "error_code": "GEMINI_REQUEST_FAILED"
  }
}
```

선행 존재 확인은 모델이 선택한 도구 실행이 아닙니다. 따라서 이번 실행에서
Function Calling이나 Python 도구 실행 Trace가 성공했다고 보고하지 않습니다.
외부 서버 응답이 없었으므로 기존 HTTP 400의 재발 또는 해결 여부도 확인할 수 없습니다.

### 계측 오류의 오프라인 확인과 수정

이번 수동 실행용 보안 계측 코드가 요청 본문의 모든 딕셔너리에서 product_id 값을 검사했습니다.
도구 선언의 `properties.product_id`는 JSON Schema 객체인데, 이를 실제 제품 ID로 오인하여
`OUTBOUND_IDENTIFIER_BLOCKED`로 차단했습니다. 실제 HTTPX 전송 함수 실행 전 발생한
**계측 코드의 거짓 양성**이며, 운영 검사 데이터 유출이나 Gemini 서버의 HTTP 400이 아닙니다.
초기 실행 결과에는 예외 원문 대신 LOCAL_OR_TRANSPORT_ERROR만 기록됐으며, 이후 네트워크 없는
동일 SDK 직렬화 재현에서 구체적인 차단 원인을 확인했습니다.

계측의 식별자 검사는 실제 contents 데이터에 적용하고, 도구 선언 스키마와 구분하도록 수정했습니다.
본문 전체의 금지 문자열·키·경로 검사는 유지합니다. 운영 Agent의 데이터 허용 목록이나
판정·근거 검증 정책은 완화하거나 변경하지 않았습니다.

오프라인 확인 4개:

1. SDK가 생성한 네 도구 선언의 정상 JSON Schema 허용.
2. 별칭 처리되지 않은 실제 product_id 차단.
3. image_id 차단.
4. 합성 비밀 문자열 차단.

모두 기대대로 동작했고 이 오프라인 확인의 네트워크 요청도 0회입니다.
수정 후 실제 분석 또는 모델 요청은 다시 실행하지 않았습니다.

### 변경 및 데이터 보호

- 정제된 실행 결과와 수동 실행용 계측 스크립트는 Git 제외 경로인
  `data/outputs/manual_validation/`에만 생성했습니다.
- 스크립트의 단일 실행 잠금 파일을 유지하여 실수로 같은 승인을 재사용하지 못하게 했습니다.
- 이 문서에 실제 관측 결과를 추가했습니다. backend, 모델, 기존 테스트 코드는 변경하지 않았습니다.
- 운영 검사 JSONL·이벤트 JSONL·체크포인트·모델 메타데이터의 실행 전후 SHA256이 동일했습니다.
- API 키·인증 헤더·실제 제품 ID·원본 검사 경로·서명 원문·평가 정답은 결과 파일과 문서에 저장하지 않았습니다.
- 임계값 34.1442와 기존 판정은 유지했습니다. T03/T05/T06 분석, 추가 실제 요청,
  모델 전환, Git add/commit/push는 수행하지 않았습니다.
- 이번 작업에서 전체 pytest는 재실행하지 않았습니다. 직전 오프라인 전체 회귀 결과는
  332 passed이며, 이번 실제 프로토콜 성공을 증명하지 않습니다.

계측용 오류를 수정했지만 실제 T01 재검증은 아직 미완료입니다.
추가 실제 분석은 새 승인을 받은 뒤 한 번만 시도해야 합니다.

## 수정 계측 적용 후 새 승인 T01 재검증 — Gemini 504로 중단

### 실행 전 오프라인 점검

새 승인을 받아 기존 실행 기록과 잠금 파일을 유지한 채 별도 단일 실행 잠금을 사용했습니다.
실행 전 실제 T01 저장 레코드와 설치 SDK의 도구 선언·후속 요청 JSON을 사용하여
다음 8개 점검을 수행했으며, 모두 통과했습니다. 이 점검 중 SDK 네트워크 전송 메서드는
차단했으며 호출 시도도 0회였습니다.

1. 실제 운영 조회 응답의 원본 식별자는 외부 전송 대상으로 허용하지 않음.
2. 기존 _context_view의 제품 별칭·image_id 제외 적용 후 운영 조회 응답 허용.
3. 정상적인 네 도구 선언의 JSON Schema 허용.
4. SDK로 직렬화한 운영 조회 결과의 FunctionResponse 후속 요청 허용.
5. 별칭 처리되지 않은 product_id 차단.
6. image_id 차단.
7. 절대 경로 차단.
8. 오프라인 점검 중 네트워크 요청 시도 0회 확인.

실제 실행에서도 동일한 오프라인 점검을 먼저 통과해야만 분석 요청이 시작되도록 했습니다.
SDK·모델·키 존재 여부와 기존 제한값의 일치를 확인했으며 키 값은 기록하지 않았습니다.

### 실제 실행과 요청별 결과

- 시작: 2026-10-15 06:18:06 UTC (한국 시각 15:18:06).
- 대상: T01 `INSP-001396`, `POST /analyze/INSP-001396` 1회.
- 실제 FastAPI 라우트·AgentService·InspectionTools·JSONL 저장소·Gemini SDK를 사용했습니다.
- 모델: `gemini-3.8-flash`, SDK: `google-genai==2.31.0`.
- SDK generate_content 호출 5회, 실제 외부 HTTP POST 전송 5회, 분석 시도 1회.
- 자동 재시도·모델 변경·다른 시나리오 분석·추가 분석 시도는 0회입니다.

| 요청 | 단계 | 전송된 FunctionResponse 누적 수 | Gemini HTTP | 모델 응답 / 안전한 오류 코드 | SDK 구간 시간 |
|---|---|---:|---:|---|---:|
| 1 | Function Calling | 0 | 200 | get_inspection_result | 2065.942 ms |
| 2 | FunctionResponse 후속 Function Calling | 1 | 200 | get_execution_logs | 6030.845 ms |
| 3 | FunctionResponse 후속 Function Calling | 2 | 200 | analyze_image_quality | 2486.109 ms |
| 4 | FunctionResponse 후속 Function Calling | 3 | 200 | get_inspection_history | 3326.494 ms |
| 5 | FunctionResponse 후속 Function Calling | 4 | 504 | ServerError / DEADLINE_EXCEEDED | 14393.113 ms |

네 도구 실행 라운드 이후의 5번째 요청은 추가 도구를 실행한 것이 아니라 기존 서비스가
증거 수집 완료 여부를 확인하는 후속 모델 요청입니다. 이 요청에서 외부 서버가 504를 반환했고,
최종 Structured Output 요청 단계에는 도달하지 않았습니다. 재시도는 하지 않았습니다.

두 번째 요청은 `role=user`의 FunctionResponse로 실제 HTTP 200을 받았고, 세 번째와 네 번째
요청도 성공했습니다. 따라서 이전 두 번째 요청의 400은 이번 실행에서는 재현되지 않았습니다.
다만 과거 서버 reason이 없으므로 과거 400의 유일한 원인이 role이었다고 소급 확정하지 않습니다.

모든 후속 전송에서 호출 이름/ID 대응, Part 경계 및 thought signature 바이트 보존,
FunctionResponse의 user 역할을 전송 경계에서 확인했습니다. 서명 원문은 기록하지 않았습니다.
2~4번째 요청에서는 서버의 정상 후속 응답을 확인했습니다. 5번째 요청에는 네 번째 도구 결과도
전송됐으나 504이므로 해당 결과의 서버 처리 완료를 확정하지 않습니다.

### 실제 Python 도구 실행 Trace

| 순서 | 라운드 | 도구 | executed | success | evidence_id | 도구 시간 |
|---:|---:|---|---|---|---|---:|
| 1 | 1 | get_inspection_result | true | true | E0001 | 2.104 ms |
| 2 | 2 | get_execution_logs | true | true | E0002 | 21.996 ms |
| 3 | 3 | analyze_image_quality | true | true | E0003 | 1.875 ms |
| 4 | 4 | get_inspection_history | true | true | E0004 | 9.225 ms |

첫 세 검사 단위 도구의 인자는 모두 `inspection_id=INSP-001396`이며,
이력 도구의 Trace 인자는 `product_id=TARGET-PRODUCT, limit=5`입니다.
실제 제품 ID는 공개하지 않습니다.

실제 tools_used는 위 네 도구이며 호출 순서와 같습니다. Python 함수와 저장소 읽기를 각각
계측했습니다. HTTP 선행 존재 확인을 포함한 Python 조회는 5회였고, 그중 선행 조회 1회는
모델 도구 Trace에서 제외했습니다. 저장소 읽기는 get_inspection 4회, get_logs 1회,
list_inspections 1회였습니다. 로그·영상 품질 조회의 선행 검사 존재 확인도 포함한 수치입니다.

### 최종 HTTP 결과와 근거 검증

- 분석 HTTP: **502**.
- Agent 상태: **FAILED**, 오류 코드: **GEMINI_REQUEST_FAILED**.
- 정확한 실패 단계: **5번째 FunctionResponse 후속 Function Calling 요청**.
- 외부 오류: **HTTP 504 / ServerError / DEADLINE_EXCEEDED**.
- 추가적인 내부 원인: UNKNOWN. 원시 오류 메시지나 민감한 서버 응답은 저장하지 않았습니다.
- 최종 구조화 응답: **NOT TESTED**.
- 최종 Pydantic 진단 및 JSON Pointer 관측 사실 검증: **NOT TESTED**.
- 최종 진단·관측 사실·가설·점검 권고: 생성되지 않음.
- 종합 결과: **FAIL — 실제 Function Calling과 네 도구 실행은 확인했으나 최종 분석 미완료**.

현재 서비스는 SDK ServerError를 GEMINI_REQUEST_FAILED로 정제하므로 외부 Gemini의 504가
분석 API에서는 기존 계약에 따라 502로 반환됐습니다. Agent 전체 timeout(60초)이나
도구 timeout으로 분류해서는 안 됩니다. 이번 승인 범위에서 오류 매핑은 수정하지 않았습니다.

```json
{
  "detail": {
    "analysis_status": "FAILED",
    "error_code": "GEMINI_REQUEST_FAILED"
  }
}
```

### 토큰·실행 시간·제한 준수

| 요청 | 입력 | 출력 | thinking | total |
|---|---:|---:|---:|---:|
| 1 | 962 | 28 | 103 | 1093 |
| 2 | 1359 | 28 | 722 | 2109 |
| 3 | 2775 | 28 | 21 | 2824 |
| 4 | 2956 | 22 | 120 | 3098 |
| 5 | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE | NOT AVAILABLE |
| 성공 응답의 확인 가능한 합계 | 8052 | 106 | 966 | 9124 |

합계는 1~4차 응답의 SDK usage_metadata 합산이며 실패 요청의 토큰이나 전체 과금을 포함한다고
주장하지 않습니다. 비용은 NOT AVAILABLE입니다.

HTTP lifespan 포함 실행 시간은 **28411.990 ms**였습니다. 최대 도구 라운드 4,
실행 8회, 동일 호출 2회, 모델 timeout 15초, 도구 timeout 3초, 전체 timeout 60초를 유지했습니다.
실제 도구 실행은 4회로 제한 안에 있으며, SDK attempts=1·automatic_continuation=False와
전송 경계의 재시도 차단을 유지했습니다. aiohttp 내부 연결 재전송 분기를 피하도록
이번 수동 실행은 HTTPX 경로를 사용했습니다.

### 보호 상태와 후속 작업

- 저장소 쓰기 시도 0회. 운영 검사/이벤트 JSONL·체크포인트·모델 메타데이터 전후 SHA256 동일.
- PatchCore 재추론·재학습·임계값 변경·신규 검사 생성·원본 이미지/평가 정답 수정 없음.
- 평가 정답·원본 경로·키·실제 제품 ID·서명 원문을 Gemini 입력 또는 결과 기록에 포함하지 않음.
- 정제된 결과는 Git 제외 경로의 별도 실행 결과 파일에 보관하고 이 문서에 관측 결과만 추가함.
- backend와 기존 테스트 코드는 변경하지 않음. 수동 계측 스크립트와 이 문서만 갱신함.
- 이번 작업에서는 실행 전 오프라인 8개 점검을 수행했으며 전체 pytest는 재실행하지 않음.
  직전 전체 회귀 결과는 332 passed이며 이번 전체 진단 성공을 의미하지 않음.
- T03/T05/T06, 추가 실제 API 요청, Git add/commit/push를 실행하지 않음.

실패 후 추가 요청 없이 중단했습니다. T01 추가 시도나 다른 시나리오 실행에는 새 승인이 필요합니다.

## T01 Gemini 504 오프라인 흐름 분석 및 최소 효율화

이 절의 작업은 실제 Gemini 요청 **0회**로 수행했습니다. 위 실험의 504/FAIL을 성공으로
변경하지 않았으며, 수정 후 실제 모델의 동작·지연 시간·최종 진단 성공 여부는 NOT TESTED입니다.

### 과거 5회 요청의 역할과 제한

| 요청 / Function Calling 루프 번호 | 요청 직전 실행 완료된 모델 선택 도구 | 이번 응답 / 이후 실행 | 시간(ms) | 입력 / 출력 / thinking / total |
|---|---|---|---:|---|
| 1 / 1 | 없음 | 결과 조회 선택·실행 | 2065.942 | 962 / 28 / 103 / 1093 |
| 2 / 2 | 결과 조회 | 로그 조회 선택·실행 | 6030.845 | 1359 / 28 / 722 / 2109 |
| 3 / 3 | 결과·로그 | 영상 품질 조회 선택·실행 | 2486.109 | 2775 / 28 / 21 / 2824 |
| 4 / 4 | 결과·로그·영상 품질 | 이력 조회 선택·실행 | 3326.494 | 2956 / 22 / 120 / 3098 |
| 5 / 5 | 결과·로그·영상 품질·이력 | 504 DEADLINE_EXCEEDED, 추가 도구 실행 없음 | 14393.113 | NOT AVAILABLE |

코드의 기존 루프는 `max_tool_rounds + 1`회의 모델 요청을 허용했습니다. 첫 네 라운드에서
도구를 실행한 뒤에도 모델이 더 이상 도구를 요청하지 않는 응답을 받아야 최종 JSON 단계로
넘어갔습니다. 5번째 요청은 동일한 AUTO Function Calling 설정으로 보내는 **종료 확인 단계**였으며,
새 도구 요청이 응답에 있었다면 TOOL_ROUND_LIMIT로 거부할 구조입니다. 실제로는 응답이 504라
추가 도구 요청이나 종료 의사가 무엇이었는지는 알 수 없습니다. 구조화 응답 요청은 아니었습니다.
성공했다면 별도 6번째 Structured Output 요청이 추가될 수 있었습니다.

전체 HTTP 실행은 28411.990 ms로 60초 미만이었고 전체 Agent timeout이 발생한 것이 아닙니다.
모델 요청은 매번 asyncio.wait_for 15초와 SDK HttpOptions 15000ms가 적용됐습니다.
설치 SDK 소스는 이를 HTTPX 15초로 변환하고 기본 X-Server-Timeout 헤더도 설정합니다.
당시 헤더 원문을 저장한 것은 아니므로 헤더의 실제 전송값을 새 관측처럼 주장하지 않습니다.
5번째 요청은 약 14.393초 후 **서버의 504/DEADLINE_EXCEEDED**를 받았습니다.
이는 로컬 asyncio TimeoutError와 다르며 현재 코드가 일반 SDK 오류로 정제해 API 502가 된 것입니다.

서버 혼잡, 모델의 생성·추론 시간, 누적 컨텍스트가 각각 어느 정도 영향을 주었는지는 UNKNOWN입니다.
불필요한 요청·컨텍스트 증가를 확인한 것과 504의 서버 내부 원인을 입증한 것은 구분합니다.

### 누적 컨텍스트와 중복 읽기

실제 전송 본문 전체의 바이트 수와 서명 원문은 당시 저장하지 않았습니다. 따라서 각 과거 요청의
정확한 바이트 크기는 **NOT RECORDED**입니다. 기록된 실제 입력 토큰은 962 → 1359 → 2775 →
2956으로 증가했고, 5번째 요청 사용량은 없습니다.

오프라인에서 현재 저장된 같은 T01 레코드와 동일 도구 인자를 조회하고 별칭 처리 및 evidence_id를
적용해 얻은 도구 응답의 UTF-8 JSON 크기는 다음과 같습니다. 이는 **현재 저장소 기준 재구성**이며
모델 Part·서명·선언·system_instruction이 포함된 과거 전체 HTTP 본문 크기가 아닙니다.

| 현재 도구 응답 | 개별 바이트 | 해당 응답까지 누적 바이트 | 데이터 수 |
|---|---:|---:|---:|
| get_inspection_result | 665 | 665 | 검사 1건 |
| get_execution_logs | 3426 | 4091 | 이벤트 6건 |
| analyze_image_quality | 396 | 4487 | 품질 결과 1건 |
| get_inspection_history | 3271 | 7758 | 이력 5건 |

요청 1에는 도구 응답이 없고, 요청 2~5에는 이 표의 누적 결과가 차례로 포함되는 구조입니다.
실제 모든 모델 요청은 기존 65536바이트 컨텍스트 검사 통과 후 전송됐습니다. 컨텍스트 크기 제한
위반을 504의 확정 원인으로 볼 수 없습니다.

모델은 같은 이름·인자의 도구를 반복하지 않았습니다. 다만 결과 도구와 품질 도구는 같은 저장된
영상 품질/지표를 포함하므로 정상 검사에서 의미가 중복됩니다. 이력 5건을 조회해야 할 추세 관련
문제는 T01의 저장된 정상 판정에서 확인되지 않았습니다. 도구가 네 개 있다는 이유로 전부 사용할
필요는 없습니다. 기존 코드가 네 도구 실행을 강제한 것은 아니며, 실제 모델이 모두 선택했습니다.

저장소 get_inspection 4회는 HTTP 선행 존재 확인, 결과 조회, 로그의 선행 존재 확인,
품질 조회에서 발생했습니다. 나머지는 get_logs 1회·list_inspections 1회입니다.
이들 저장소 읽기를 같은 모델 도구의 반복 실행으로 오해해서는 안 됩니다. HTTP 존재 확인은
미등록 검사에 Gemini를 호출하지 않기 위한 별도 보안 경계이므로 제거하지 않았습니다.

### 대안 비교와 선택

| 대안 | 장점 | 한계 / 위험 |
|---|---|---|
| A. 시스템 지침 개선 | 기존 모델 도구 선택을 그대로 유지, 작은 변경 | 실제 모델의 지침 준수는 보장되지 않아 단독으로 요청 수 상한을 줄이지 못함 |
| B. 상황별 호출 예산 축소 | 최악의 비용 상한을 낮추기 쉬움 | 필요한 조사 전에 소진될 수 있고, 예산 소진을 충분한 근거로 오인할 위험 |
| C. 결과 조회 후 조건부 조사·구조화 전환 | 관측된 근거에 따라 정상 단건을 결정적으로 조기 종료 | 충분성 조건을 보수적으로 정의해야 하며 복잡한 사례에는 일반 조사가 필요 |

**A + 제한된 C**를 선택했습니다. B의 동적 예산 축소는 하지 않았습니다.

- 첫 요청은 검사 결과만 조회하도록 지침을 명확히 했습니다. 도구 목록을 병렬 체크리스트처럼
  실행하지 않고, 로그는 실행/추론 실패나 이벤트 조사에, 품질은 경고/관련 근거에,
  이력은 추세 비교가 필요한 경우에만 선택하도록 했습니다.
- 서버는 status=COMPLETED, result=OK, image_quality_status=NORMAL,
  defect_detection_status=COMPLETED, final_result=OK, final_reason_code=ALL_CHECKS_PASSED가
  모두 저장돼 있고, 유한한 anomaly_score와 decision_threshold가 존재하며 score <= threshold인
  경우에만 현재 도구 응답 묶음 뒤 곧바로 구조화 단계로 전환합니다.
- 위 비교는 **조사 종료 자격 확인**일 뿐 판정을 다시 계산하거나 기존 result를 바꾸지 않습니다.
  숫자가 없거나 모순되거나 핵심 필드가 누락되면 조기 전환하지 않습니다.
- 경고·실행 실패·추론 불가·구형 기록은 기존 모델 조사 루프를 유지합니다. 필요한 추가 조사를
  서버가 자동 일괄 실행하지 않으며, 모델이 고른 도구만 실행합니다. 경고/실패에 대한 도구 선택은
  지침과 Mock 검증으로 확인했지만 실제 모델의 선택은 아직 미검증입니다.
- 모델이 한 응답에서 이미 요청한 병렬 호출은 기존 검증 후 전부 처리하고 대응 FunctionResponse를
  보존합니다. 비용 때문에 Part를 삭제하거나 실행하지 않은 도구를 성공으로 기록하지 않습니다.
  따라서 같은 첫 응답에서 네 도구를 모두 선택하는 경우까지 서버가 막는 하드 예산 정책은 아닙니다.
- 종료 확인 모델 요청을 생략하더라도 도구 결과는 생략하지 않습니다. 마지막 user Content의
  FunctionResponse를 그대로 최종 구조화 요청에 전달하고, 최종 생성 지시를 system_instruction에
  넣습니다. 같은 user 턴에 별도의 일반 텍스트를 섞지 않습니다.
- 최종 JSON/Pydantic/JSON Pointer/여섯 필수 관측 사실·요약·가설 검증을 모두 그대로 수행합니다.
  근거 불일치나 최종 요청 실패를 정상 성공으로 반환하지 않습니다.
- 모델 ID, 전역 최대 4라운드/8회/동일 호출 2회, 15/3/60초 제한, 재시도 설정은 변경하지 않았습니다.

### 예상 효과와 미검증 범위

정상 단건에서 첫 모델 응답이 결과 도구 한 개를 선택하고 저장된 충분성 조건을 충족하면
**Function Calling 1회 + Structured Output 1회 = 2회**입니다. Mock으로 실제 Python 결과 조회와
최종 구조화 검증을 이 두 요청 안에서 확인했습니다. 이전 가장 짧은 정상 흐름의 3회에서
종료 확인 1회를 제거하고, 관측된 T01의 5회 실패 경로와 비교하면 3회 감소를 기대할 수 있습니다.
과거 네 도구 조사 이후 별도 구조화 단계까지 필요했던 잠재 6회 경로와 비교하면 4회 차이입니다.
이는 조건부 코드 경로 비교이며 실제 비용·토큰·지연 시간 감소를 측정한 수치가 아닙니다.

실제 모델이 필수 도구를 선택하지 않거나 병렬 선택을 하거나 최종 생성에 실패하면 위 효과가
보장되지 않습니다. 경고/실패/누락 기록의 기존 추가 조사와 종료 확인은 유지됩니다.
최종 구조화 요청에 대화의 FunctionResponse 이력을 전달하는 방식은 로컬 SDK 직렬화로 검증했지만
수정 후 실제 Gemini의 수락과 진단 품질은 NOT TESTED입니다. 15초 내 최종 생성 성공도 보장하지 않습니다.

### 변경 파일과 회귀 검증

- `backend/agent/service.py`: 보수적인 정상 근거 충분성 판단, 조건부 구조화 전환,
  FunctionResponse 턴 유지와 구조화 단계의 시스템 지시.
- `backend/agent/prompts.py`: 근거별 도구 선택과 정상 최소 조사 원칙, 최종 생성 지시.
- `tests/test_agent_efficiency.py`: 신규 25개(매개변수 사례 포함).
- `tests/test_agent_service.py`, `tests/test_agent_api.py`: 기존 테스트 유지. 정상 Mock 응답을
  불필요한 준비 응답 없는 두 요청으로 조정했고, 다중 라운드 검증에는 필드 누락 기록을 사용해
  일반 조사 경로를 실제로 검증합니다. 보안·상한·근거 일치 검증의 기대 오류를 완화하지 않았습니다.
- `docs/day4-step2-agent.md`, 이 문서: 변경된 정상 전환과 사실/가설/미검증 범위 기록.

| 검증 | 실제 결과 |
|---|---|
| 관련 Agent/HTTP/효율화 테스트 초기 실행 | 171 passed; 이후 측정값 예외 사례 5개 추가 |
| 전체 `pytest tests -q -p no:cacheprovider` | **357 passed, 0 failed, 0 skipped**, 19.15초 |
| 기존 회귀와 신규 사례 | 332 + 25개 모두 통과 |
| 실제 Gemini 호출 및 SDK 전송 시도 | **0회** |
| `python -m pip check` | No broken requirements found |
| 변경 대상 한정 `git diff --check` | 오류 없음 |

전체 테스트는 Conda vision-insight에서 임시 저장 경로·공개 fixture 복사본을 사용했고,
SDK의 동기/비동기 실제 전송 경계를 차단했습니다. 운영 JSONL, 체크포인트, 메타데이터의
전후 SHA256은 동일합니다. 기존 외부 라이브러리 경고 2건과 래퍼의 anyio rewrite 경고 1건이 있습니다.
최초 관련 테스트에서는 연속 요청 fixture의 구형 준비 응답이 남아 1개가 실패했고,
실제 변경된 두 요청 프로토콜에 맞게 fixture를 정리한 뒤 전체 통과를 확인했습니다.

신규 검증에는 정상에서 로그·품질·이력 추가 조회가 없는 경로, 누락/비정상 필드 및
모순된 수치의 조기 종료 차단, 경고의 품질 조회·실패의 로그 조회, 서명·호출 ID·FunctionResponse
직렬화, 근거 불일치 거부, 최종 요청의 모델/전체 timeout, 요청별 Trace·토큰 사용량 분리가 포함됩니다.

모델/임계값/평가 정답/원본 이미지/운영 JSONL을 변경하지 않았고 Git add/commit/push를 실행하지 않았습니다.
T01 실제 재검증을 위한 오프라인 준비는 완료했지만, 재호출은 별도 승인 후에만 가능합니다.

## 정상 조기 종료 적용 후 T01 실제 재검증 — 구조화 요청 400

### 사전 점검 및 승인 범위

2026-10-15의 새 승인에 따라 T01 `POST /analyze/INSP-001396` 분석을 한 번만 실행했습니다.
실제 실행 시작은 2026-10-15 07:06:53 UTC (한국 시각 16:06:53)입니다.
이 절은 앞선 실패 기록과 별도 회차이며 과거 결과를 덮어쓰지 않습니다.

실행 전 서비스·프롬프트·HTTP 경계·스키마·효율화 테스트·이 문서를 확인했습니다.
SDK `google-genai==2.31.0`, 모델 `gemini-3.8-flash`, 키 존재 여부와 기존 제한값 일치를
확인했으며 키 값은 출력하지 않았습니다. 기존 검사 데이터로 정상 조기 종료 자격도 확인했습니다.

- 운영 원본 식별자 차단, 허용 필드·별칭 적용 데이터 허용, 정상 SDK 도구 선언 허용,
  SDK FunctionResponse 직렬화 허용, 원본 제품 ID·image_id·절대 경로 차단 등
  기존 오프라인 8개 점검을 모두 통과했습니다. 해당 점검의 네트워크 시도는 0회입니다.
- `tests/test_agent_efficiency.py`를 실제 SDK 전송 차단 상태로 실행해 **25 passed**를 확인했습니다.
  이 테스트의 실제 SDK 전송 시도도 0회였습니다. 이번 전체 pytest 재실행은 하지 않았으며,
  직전 전체 회귀 결과는 357 passed입니다.
- FastAPI TestClient로 실제 라우트를 실행했고 기존 AgentService·InspectionTools·JSONL 저장소와
  실제 SDK 응답을 사용했습니다. 우회 Agent나 Mock Gemini 응답은 사용하지 않았습니다.
- 전역 제한 4라운드/8회/동일 호출 2회 및 모델 15초/도구 3초/전체 60초를 유지했습니다.
  attempts=1, 자동 함수 실행·자동 continuation 비활성화 및 전송 재시도 차단을 적용했습니다.
  이전과 마찬가지로 수동 실행의 전송은 HTTPX 경로로 제한했습니다.

### 이번 회차 결과 요약

| 항목 | 관측 결과 |
|---|---|
| 검사 ID | INSP-001396 |
| 모델 / SDK | gemini-3.8-flash / google-genai 2.31.0 |
| 분석 시도 / 실제 Gemini HTTP 요청 | 1회 / 2회 |
| 실제 Function Call | PASS — get_inspection_result |
| 실제 Python 도구 / 저장소 조회 | PASS — 조회 도구 1회 및 JSONL 읽기 성공 |
| FunctionResponse 전송 구성 | PASS — user 역할·모델 Content·호출 이름/ID·서명 보존 |
| FunctionResponse 포함 후속 요청 성공 | FAIL — 최종 구조화 요청 HTTP 400 |
| 정상 조기 종료 | PASS — 도구 1회 뒤 조건 충족, 즉시 구조화 단계 전환 |
| 불필요한 로그·품질·이력 조회 | 없음 |
| 최종 구조화 진단 생성 | FAIL — 요청 거부로 응답 없음 |
| 최종 DiagnosisDraft Pydantic 검증 | NOT TESTED |
| 관측 사실·JSON Pointer 결정적 근거 검증 | NOT TESTED |
| 분석 API HTTP | 502 |
| Agent 상태 / 오류 코드 | FAILED / GEMINI_REQUEST_FAILED |
| 확인된 입력 / 출력 / Thinking / total 토큰 | 1152 / 28 / 87 / 1267 |
| 실패한 두 번째 요청 사용량 / 전체 비용 | NOT AVAILABLE / NOT AVAILABLE |
| Agent analyze 실행 시간 | 2365.126 ms |
| HTTP lifespan 포함 시간 | 2431.788 ms |
| 전체 판정 | **FAIL — 최종 구조화 진단 및 근거 검증 미완료** |

### 실제 외부 요청

| 요청 | 단계 | FunctionResponse 수 | Gemini HTTP | 응답 또는 안전한 오류 | SDK 구간 시간 |
|---|---|---:|---:|---|---:|
| 1 | Function Calling, round 1 | 0 | 200 | get_inspection_result Function Call | 2239.892 ms |
| 2 | Structured Output, round 2 | 1 | 400 | ClientError / INVALID_ARGUMENT, RESPONSE_SCHEMA 지표 | 120.767 ms |

2번째 요청은 기존 실패의 종료 확인용 Function Calling 요청이 아닙니다.
도구 없는 `response_mime_type=application/json`, `response_schema=DiagnosisDraft` 요청이었습니다.
FunctionResponse가 user Content에 포함되고, 최초 user와 전체 모델 Content, Part 경계,
호출 이름/ID 및 thought signature 바이트가 유지됨을 전송 경계에서 확인했습니다.
그러나 400으로 거부됐으므로 FunctionResponse의 서버 처리 완료나 최종 스키마 수락을
성공으로 판단하지 않습니다. 400·429·504 중 이번에 관측한 오류는 2번째 요청의 400입니다.

오류에서 안전하게 확인한 정보는 **HTTP 400 / ClientError / INVALID_ARGUMENT**와
정제된 **RESPONSE_SCHEMA 지표**입니다. 이 지표는 오류 메시지에 response_schema 관련 표현이
있었다는 뜻이며, 구체적인 거부 필드나 제약을 확정한 것은 아닙니다. 추가 상세 원인은 UNKNOWN입니다.
원시 오류 메시지·서명·제품 데이터·키·내부 경로는 결과 문서에 기록하지 않았습니다.
앞선 FunctionResponse role 문제와 같은 원인이라고 단정하지 않습니다.
다음 작업이 승인된다면 DiagnosisDraft의 SDK 직렬화와 서버 스키마 제약을 오프라인에서
점검해야 합니다. 이번에는 코드 수정 후 추가 호출하거나 다른 모델로 전환하지 않았습니다.

### 실제 Python 실행과 조기 종료

```json
{
  "sequence": 1,
  "round_number": 1,
  "tool_name": "get_inspection_result",
  "arguments": {"inspection_id": "INSP-001396"},
  "executed": true,
  "success": true,
  "error_code": null,
  "elapsed_ms": 2.207,
  "evidence_id": "E0001"
}
```

실제 tools_used는 `["get_inspection_result"]`입니다. HTTP 선행 검사 존재 확인에서의
결과 조회 1회와 모델이 요청한 결과 조회 1회를 구분했습니다. HTTP 구간의 저장소 get_inspection은
총 2회였으며 도구 Trace에는 모델 선택으로 실행된 1회만 포함됐습니다.

Gemini는 허용 도구 이름과 고정 검사 ID를 반환했고 서버 검증을 통과했습니다.
서버가 확인한 저장 값은 다음과 같습니다.

| 필드 | 실제 저장 값 |
|---|---|
| status / defect_detection_status | COMPLETED / COMPLETED |
| result / final_result | OK / OK |
| image_quality_status | NORMAL |
| final_reason_code | ALL_CHECKS_PASSED |
| anomaly_score | 31.334630966186523 |
| decision_threshold | 34.1442 |

유한한 이상 점수가 저장된 임계값 이하이고 여섯 핵심 판정이 정상 조합이므로,
실제 도구 1회 실행 뒤 `_normal_evidence_ready=True`가 관측됐습니다.
이는 **서버 정책에 의한 전환**이며 Gemini가 별도의 종료 응답을 반환한 것은 아닙니다.
모델이 선택한 조회는 결과 도구 하나였고 로그·품질·이력 조회와 종료 확인 요청은 생략됐습니다.

도구 근거 E0001은 확보됐으나 최종 observed_facts가 생성되지 않았으므로 근거 연결의
최종 검증은 NOT TESTED입니다. 진단 요약·가설·권고·한계도 생성되지 않았습니다.
따라서 제품 무결점 보증이나 근거 없는 설명이 최종 진단에 포함됐는지는 평가할 응답이 없습니다.
기존 검사 판정은 변경하지 않았으며 result=OK를 실제 무결점 보증으로 취급하지 않는 정책도 유지했습니다.

### 사용량과 데이터 보호

첫 응답의 실제 usage_metadata는 입력 1152, 출력 28, Thinking 87, total 1267입니다.
두 번째 오류 응답에는 사용량이 없어 전체 과금 사용량·비용으로 확정하지 않습니다.
자동 재시도와 추가 분석 시도는 0회입니다.

저장소 쓰기 시도는 0회였고 운영 검사 JSONL·이벤트 JSONL·체크포인트·모델 메타데이터의
전후 SHA256이 동일했습니다. PatchCore 초기화/추론을 실험에 사용하지 않았으며 원본 이미지,
평가 정답, 임계값을 변경하지 않았습니다. 제품 별칭과 image_id 제외 정책을 유지했습니다.

이번 작업은 Git 제외 경로의 단일 실행 계측 스크립트에 이번 승인용 잠금·결과 식별자와
조기 종료/스키마 검증 계측을 추가하고, 정제된 회차 결과를 별도 파일에 저장했습니다.
기존 실패 결과·잠금 파일은 유지했습니다. backend·기존 테스트 코드는 변경하지 않았습니다.
이 문서에 이번 회차를 추가했으며 Git add/commit/push는 수행하지 않았습니다.

### 결론과 중단 상태

실제 도구 호출과 정상 조기 종료는 확인됐지만 최종 구조화 요청이 거부되어 전체 결과는 FAIL입니다.
T03/T05/T06 및 Day 4 Step 5를 진행하지 않았습니다. 구조화 스키마 호환성의 오프라인 분석이
먼저 필요하며, 추가 실제 요청과 나머지 시나리오는 별도 승인 전 실행하지 않습니다.

## Response Schema HTTP 400 오프라인 분석 및 JSON Schema 전달 수정

이 절의 작업은 실제 Gemini API 요청 **0회**로 수행했습니다. 직전 실험의 FAIL을 PASS로
변경하지 않았습니다. 수정 후 서버의 스키마 수락·최종 진단 품질은 NOT TESTED입니다.

### 관측된 실패 위치와 확정할 수 없는 정보

직전 T01의 두 번째 요청은 SDK가 본문을 직렬화하고 실제로 전송한 Structured Output 요청입니다.
SDK 내부 변환 과정의 예외가 아니라 **서버에서 HTTP 400 / INVALID_ARGUMENT**를 반환했습니다.
첫 Function Calling, Python 결과 조회, 조기 종료는 이미 성공했습니다.
서버는 최종 요청을 전송받았지만 생성 요청으로 수락하지 않았습니다.
기록에는 RESPONSE_SCHEMA 관련 지표만 있으며 정확한 거부 필드·상세 reason은 저장되지 않았습니다.
따라서 **실제 서버가 거부한 정확한 필드와 과거 400의 확정 원인은 UNKNOWN**으로 유지합니다.

### 원본부터 전송 스키마까지 추적

| 단계 | 수정 전 확인 결과 |
|---|---|
| 원본 | DiagnosisDraft 및 ObservedFact, CauseSelection, CheckSelection |
| 서버 모델 | extra=forbid, 엄격한 scalar 타입, ID·pointer 패턴, 길이·배열 제한, Enum 유지 |
| 원본 JSON Schema | 소문자 type, $defs 1개 맵·정의 3개, $ref 3개, anyOf 2개 |
| 원본 추가 제약 | additionalProperties=false 4곳, pattern 6곳, maxLength 2곳, default=null 1곳 |
| 설정 | response_schema=DiagnosisDraft, response_json_schema 미지정 |
| SDK 2.31.0 경로 | t_schema → model_json_schema → process_schema → types.Schema → responseSchema |
| SDK 변환 | 정의를 inline, null을 nullable로 변경, type 대문자화, property_ordering 추가 |
| 최종 JSON 본문 | additional_properties, any_of, max_length, min_items, max_items 등 SDK 필드명도 포함 |

원본과 수정 후 전달 스키마 모두 동일한 33개 스키마 노드이며, 참조를 해석한 최대 깊이는
5개 노드입니다. 예: 루트 객체 → 배열 → 항목 객체 → evidence_refs 배열 → 문자열.
이 정도 구조가 서버의 복잡도 제한을 초과했다고 입증하지는 않았습니다.

필수 루트 필드는 inspection_id, overall_summary, observed_facts, possible_causes,
recommended_checks, limitations 여섯 개입니다. ObservedFact는 fact_id, evidence_id,
source_tool, source_field, observed_value를 요구합니다. source_event는 선택 필드이며 null을
허용합니다. observed_value는 bool/int/float/string/null을 허용하되 실제 타입과 값은 서버가
도구 응답과 비교합니다. 원본에 oneOf는 없고 anyOf 두 곳을 사용합니다.

### 확인된 계약 불일치와 공식 근거

설치 SDK는 공용 types.Schema에 additional_properties를 노출하며,
process_schema의 Developer API 제한 검사는 해당 값이 truthy인 경우만 차단합니다.
그래서 StrictModel이 생성한 **false 값은 로컬 검증을 통과하고 responseSchema 안에 남습니다**.
실제 설치 SDK 변환기로 이를 재현했습니다.

하지만 공식 GenerateContent의 Schema 필드 목록에는 additionalProperties가 없습니다.
반면 JSON Schema 응답 경로에는 additionalProperties 지원이 명시돼 있습니다.
이는 **SDK가 직렬화할 수 있는 객체와 해당 REST 필드의 계약이 동일하지 않은 구체적 문제**입니다.
snake_case 표기만으로 모든 필드가 잘못됐다고 주장하지는 않습니다.
anyOf 자체도 지원되므로 이를 원인으로 단정하거나 제거하지 않았습니다.

참고한 공식 문서:

- [GenerateContent Schema 및 GenerationConfig](https://ai.google.dev/api/generate-content#Schema):
  두 스키마 전달 경로의 차이와 JSON Schema 키·참조 규칙을 확인했습니다.
- [SDK JSON Response Schema 예제](https://googleapis.github.io/python-genai/#json-response-schema):
  일반 JSON Schema는 response_json_schema로 제공하는 예제가 있습니다.
- [Structured Output 안내](https://ai.google.dev/gemini-api/docs/structured-output):
  JSON Schema 일부만 지원하고 별도 애플리케이션 검증이 필요함을 확인했습니다.

현재 Structured Output 안내는 Interactions API 예제가 중심이지만 이 프로젝트는 GenerateContent를
사용합니다. 이를 혼용하지 않고 설치 SDK 2.31.0의 _GenerateContentParameters_to_mldev와
t_json_schema의 실제 동작을 근거로 response_json_schema를 선택했습니다.
SDK/모델 변경이나 API 전면 교체는 하지 않았습니다.

### 최소 수정과 수정 전후 비교

서버 검증 모델을 새로 만들거나 약화하지 않고, 기존 모델에서 외부 전달용 스키마를 생성합니다.

| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| 설정 | response_schema=DiagnosisDraft | response_json_schema=diagnosis_response_json_schema() |
| 전송 필드 | generationConfig.responseSchema | generationConfig.responseJsonSchema |
| 표현 | SDK OpenAPI Schema 객체로 변환 | 검토한 표준 JSON Schema dict 그대로 전달 |
| 정의/참조 | inline으로 변환 | $defs/$ref 보존, 참조 노드에 불필요한 형제 키 없음 |
| nullable | nullable=true 및 any_of | anyOf의 명시적인 null 분기 유지 |
| 객체 추가 필드 금지 | additional_properties=false | additionalProperties=false 보존 |
| Enum·필수 필드·배열 제한 | 원본 | 동일 값 유지 |
| 문자열 pattern/maxLength | SDK Schema에 포함 | 외부에서 제외하되 원래 Pydantic에서 계속 강제 |
| default=null | 원본 annotation | 외부에서 제외, 서버 선택 필드 기본값 유지 |
| 최종 검증 | DiagnosisDraft + 결정적 근거 비교 | 변경 없음 |

GenerateContent JSON Schema의 명시된 지원 목록에 없는 pattern/maxLength와 필요하지 않은
default annotation만 외부 projection에서 제외했습니다. 필드 자체·required·null 허용·Enum·배열
제약은 제거하지 않았습니다. 각 값의 패턴/길이/엄격한 타입/추가 필드 금지는 여전히 서버의
원본 Pydantic이 강제하므로 잘못된 생성 결과는 성공으로 반환되지 않습니다.
외부 모델의 문자열 생성 제약 일부가 서버 전용으로 이동하므로 실제 생성 품질은 재검증이 필요합니다.

추가로 검토되지 않은 새로운 스키마 속성이 생기면 임의로 무시하지 않고 projection을 거부합니다.
이때 기존 RESPONSE_SCHEMA_INVALID 오류로 안전하게 실패하며 최종 모델 요청은 보내지 않습니다.
이 프로젝트가 사용하는 검토된 부분집합만 허용한다는 의미이지, oneOf 같은 검토되지 않은 키를
Gemini 전체에서 지원하지 않는다고 주장하는 것은 아닙니다.

기존 JSON 덤프 방식(기본 구분자)의 스키마 부분 크기는 legacy responseSchema 3249바이트,
수정 후 responseJsonSchema 2846바이트였습니다. 전체 HTTP 본문 크기나 실제 토큰 절감 측정은 아닙니다.
새 SDK 변환 후 responseJsonSchema가 projection 결과와 정확히 일치함을 확인했습니다.

### 보존한 동작과 변경 파일

- `backend/agent/schemas.py`: DiagnosisDraft는 그대로 두고 검토된 외부 JSON Schema projection 추가.
- `backend/agent/service.py`: 구조화 단계의 스키마 설정만 변경, projection 오류의 안전한 처리 추가.
- `tests/test_agent_response_schema.py`: 신규 29개 테스트(매개변수 사례 포함).
- `tests/test_agent_api.py`: 기존 두 번째 요청 ClientError(400) → 안전한 502 검증에 새 설정 확인 추가.
- `docs/day4-step2-agent.md`, 이 문서: 현재 전달 방식 및 오프라인 분석 기록.

검사 ID 고정, 네 도구 허용 목록, 인자 검증, 제품 별칭, image_id 제외, FunctionResponse user 역할,
모델 Content/서명/호출 ID 보존, 정상 조기 종료, 호출 수·시간 제한은 변경하지 않았습니다.
DiagnosisDraft의 필수 정보와 strict 검증, 여섯 핵심 관측 사실, evidence_id·실제 Trace·JSON Pointer
비교, 요약과 저장 판정의 일치, 가설/권고 근거 검증도 변경하지 않았습니다.
API 응답 모델 및 기존 검사 API 계약은 유지했습니다.

### 오프라인 회귀 결과

| 검증 | 실제 결과 |
|---|---|
| 신규 Response Schema 사례 | 29개, 전체 실행에서 모두 통과 |
| 스키마·효율화·Agent·HTTP 관련 테스트 | 205 passed |
| 전체 `pytest tests -q -p no:cacheprovider` | **386 passed, 0 failed, 0 skipped**, 17.68초 |
| 기존 회귀 + 신규 | 357 + 29개 |
| 실제 SDK generate_content 직렬화 | 실제 AsyncModels + Mock 전송으로 2요청 구조화 성공 확인 |
| 실제 Gemini HTTP 요청 / 실제 SDK 전송 경계 호출 시도 | **0회 / 0회** |
| `python -m pip check` | No broken requirements found |
| 변경 대상 한정 `git diff --check` | 오류 없음 |

SDK 기반 테스트의 성공은 로컬 변환과 Mock 응답에 대한 성공입니다. 외부 서버가 스키마를
수락했다는 증거로 취급하지 않습니다. 공식 문서 확인을 위한 웹 조회와 Gemini 모델 호출도 구분합니다.
테스트는 임시 저장 경로·공개 fixture 복사본을 사용하고 SDK의 동기/비동기 실제 전송을 차단했습니다.
외부 라이브러리 경고 2건과 테스트 래퍼의 anyio rewrite 경고 1건이 남아 있습니다.

신규 검증 범위: 필수/선택 필드·중첩 참조·Enum·Nullable·scalar 타입·배열 제한 보존,
미검토 키 차단, pattern/길이/추가 필드의 서버 검증 유지, evidence_id/값 불일치·중복 사실 거부,
실제 SDK의 새 JSON 스키마 전송과 정상 2요청 경로, 실제 Python 도구 실행·Trace·근거 연결,
JSON 직렬화 및 projection 실패 시 최종 요청 미발생을 포함합니다.
기존 Function Calling·조기 종료·HTTP 400 안전 매핑·보안·시간 제한 테스트도 모두 통과했습니다.

운영 검사/이벤트 JSONL·체크포인트·모델 메타데이터의 전후 SHA256이 동일합니다.
모델 ID·SDK 버전·임계값 34.1442·원본 이미지·평가 정답은 변경하지 않았습니다.
Git add/commit/push, 실제 재호출, 다른 시나리오, Step 5는 수행하지 않았습니다.

### 최종 판단

T01 실제 재검증을 위한 오프라인 준비는 완료했습니다. 그러나 서버의 정확한 기존 거부 필드는
UNKNOWN이고 새 JSON Schema에 대한 실제 모델 수락, FunctionResponse 이력과 구조화 응답의
조합, 진단 생성 시간·품질은 NOT TESTED입니다. 이들을 확인하려면 별도 승인된 T01 한 건의
실제 재검증이 필요합니다. 이번에는 재호출하지 않고 사용자 승인을 기다립니다.

## response_json_schema 적용 후 T01 실제 재검증 — 구조화 요청 400 지속

이번 새 승인 범위에서 T01 `INSP-001396`의 실제 분석을 한 번만 실행했습니다.
시작 시각은 2026-10-15 07:24:14 UTC (한국 시각 16:24:14)입니다.
이 회차는 앞선 실패 기록을 보존한 별도 실험이며, 결과는 **FAIL**입니다.

### 사전 오프라인 점검

- 기존 운영 식별자 차단·허용 데이터 허용·도구 선언·FunctionResponse 직렬화 등 8개 점검 통과.
- responseJsonSchema 전송값 일치, legacy responseSchema 부재, 잘못된 additional_properties 부재,
  원본 필수 필드와 정의 유지 등 추가 계측 5개 점검 통과.
- `tests/test_agent_response_schema.py`와 `tests/test_agent_efficiency.py`를 실제 SDK 전송 차단 상태로
  실행해 **54 passed**를 확인했습니다. 테스트 중 실제 SDK 전송 시도는 0회였습니다.
- Enum·Nullable·배열·참조·필수 필드, 서버 Pydantic/결정적 근거 검증, FunctionResponse의 역할·ID·서명,
  정상 조기 종료는 현재 코드 및 위 테스트로 점검했습니다.
- SDK 2.31.0·기존 모델·기존 제한값·키 존재 여부를 확인했습니다. 키 값은 출력하지 않았습니다.
- 전체 pytest는 이번에 재실행하지 않았으며 직전 전체 회귀 결과는 **386 passed**입니다.

### 회차 결과

| 항목 | 실제 결과 |
|---|---|
| 검사 / 엔드포인트 | INSP-001396 / POST /analyze/INSP-001396 |
| 모델 / SDK | gemini-3.8-flash / google-genai 2.31.0 |
| 실제 분석 시도 | 1회 |
| 실제 Gemini HTTP 요청 | 2회 |
| 실제 Function Calling | PASS — get_inspection_result |
| Python 도구 및 저장소 조회 | PASS — 실제 조회 성공 |
| FunctionResponse 전송 구성 | PASS — user 역할, 호출 이름/ID·전체 모델 Content·Part·서명 보존 |
| FunctionResponse 포함 후속 요청 성공 | FAIL — Structured Output 요청 HTTP 400 |
| 정상 조기 종료 | PASS — 조회 1회 후 바로 구조화 단계 전환 |
| 로그·품질·이력 추가 조회 / 종료 확인 요청 | 없음 / 없음 |
| response_json_schema 실제 사용 | 확인 — SDK 설정과 전송 JSON 모두 확인 |
| 최종 구조화 진단 생성 | FAIL — 요청 거부 |
| 최종 Pydantic / 관측 사실 근거 검증 | NOT TESTED / NOT TESTED |
| 분석 API HTTP / Agent 상태 | 502 / FAILED |
| Agent 오류 코드 | GEMINI_REQUEST_FAILED |
| 기존 검사 판정 | OK / OK / ALL_CHECKS_PASSED, 운영 기록 변경 없음 |
| 확인된 입력 / 출력 / Thinking / total 토큰 | 1152 / 28 / 88 / 1268 |
| 실패 요청의 사용량 / 전체 비용 | NOT AVAILABLE / NOT AVAILABLE |
| Agent 실행 시간 | 3327.315 ms |
| HTTP lifespan 포함 실행 시간 | 3396.132 ms |
| 최종 결론 | **FAIL — 구조화 응답과 최종 근거 검증 미완료** |

### 실제 요청별 결과

| 요청 | 단계 | Gemini HTTP | 응답 또는 안전한 오류 | 시간 |
|---|---|---:|---|---:|
| 1 | Function Calling, round 1 | 200 | get_inspection_result Function Call | 2210.239 ms |
| 2 | Structured Output, round 2 | 400 | ClientError / INVALID_ARGUMENT / reason UNKNOWN | 1111.531 ms |

실제 FastAPI 라우트와 기존 AgentService·InspectionTools·저장소를 사용했습니다.
SDK 네트워크 및 도구 실행 경계는 계측했지만, Gemini 응답이나 Python 도구 결과를 Mock으로 대체하지 않았습니다.

두 번째 전송에서 다음을 확인했습니다.

- generationConfig.responseJsonSchema가 서버가 생성한 검토된 JSON Schema와 정확히 일치.
- generationConfig.responseSchema가 없음.
- 잘못된 legacy additional_properties 필드가 없음.
- 표준 JSON Schema의 additionalProperties=false는 유지됨.
- FunctionResponse 1개가 user Content로 포함되고 호출 이름/ID·Part 경계·서명 바이트가 보존됨.
- 최초 user와 전체 모델 Content가 유지됨.

그러나 서버가 HTTP 400 / INVALID_ARGUMENT를 반환했으므로 FunctionResponse 처리 완료나
최종 스키마 수락은 성공으로 판단하지 않습니다. 이번 정제된 오류에는 추가 분류 지표가 없었으며
정확한 거부 필드와 상세 원인은 **UNKNOWN**입니다. 앞선 RESPONSE_SCHEMA 지표가 이번에도
관측됐다고 주장하지 않습니다. 스키마 자체와 FunctionResponse 이력을 동반한 구조화 요청 등
가능한 원인은 현재 기록만으로 구분할 수 없습니다.

따라서 legacy 필드 제거가 확인됐다는 사실과 전체 400이 해결됐다는 주장은 구분해야 합니다.
기존 additional_properties 불일치가 유일한 원인이었다고 확정할 수 없습니다.
이번 실행 도중 스키마·모델을 바꾸거나 추가 호출로 원인을 시험하지 않았습니다.

### 실제 도구 Trace와 조기 종료

```json
{
  "sequence": 1,
  "round_number": 1,
  "tool_name": "get_inspection_result",
  "arguments": {"inspection_id": "INSP-001396"},
  "executed": true,
  "success": true,
  "error_code": null,
  "elapsed_ms": 2.161,
  "evidence_id": "E0001"
}
```

실제 tools_used는 `["get_inspection_result"]`입니다. HTTP 선행 존재 확인의 조회 1회와
모델이 선택한 실제 도구 조회 1회를 구분했으며, HTTP 구간의 저장소 get_inspection은 총 2회입니다.
공개 Trace는 모델 선택으로 실행한 1회만 포함합니다.

저장된 여섯 판정 필드는 정상 조합이었고 anomaly_score=31.334630966186523,
decision_threshold=34.1442였습니다. 실제 `_normal_evidence_ready=True`가 관측돼
서버 정책에 따라 바로 구조화 요청으로 전환했습니다. 모델이 별도의 종료 응답을 반환한 것은 아닙니다.
관측 사실을 생성할 수 있는 도구 근거 E0001은 확보됐지만 최종 observed_facts가 없으므로
최종 evidence_id·JSON Pointer 일치 검증은 NOT TESTED입니다.

실제 분석 API 응답:

```json
{
  "detail": {
    "analysis_status": "FAILED",
    "error_code": "GEMINI_REQUEST_FAILED"
  }
}
```

### 제한·보안·중단 상태

- 최대 4라운드·8회 실행·동일 호출 2회, 모델 15초·도구 3초·전체 60초를 유지했습니다.
- SDK attempts=1, 자동 함수 실행/자동 continuation 비활성화, 전송 경계 재시도 차단을 유지했습니다.
  aiohttp 내부 연결 재전송 분기를 피하도록 이전과 같이 수동 실험은 HTTPX 경로를 사용했습니다.
- 자동 재시도·추가 분석·다른 모델 요청·다른 시나리오 실행은 0회입니다.
- 저장소 쓰기 시도 0회. 운영 검사/이벤트 JSONL·체크포인트·모델 메타데이터의 전후 SHA256 동일.
- 기존 판정·임계값·원본 이미지·평가 정답은 변경하지 않았으며, 키·원본 경로·정답·주입 정보·서명
  원문을 입력 또는 결과 기록에 포함하지 않았습니다.
- Git 제외 경로의 기존 계측 스크립트에 이번 승인용 별도 실행 잠금과 스키마 전송 확인만 추가하고,
  정제된 결과를 별도 회차 파일에 보관했습니다. backend/기존 테스트 코드는 변경하지 않았습니다.
- 기존 실패 기록과 잠금 파일을 유지했습니다. Git add/commit/push는 수행하지 않았습니다.

T01은 부분 성공 항목이 있으나 최종 완료 기준을 만족하지 못했습니다. 추가 실제 요청 없이
중단했으며 T03/T05/T06, Step 5 및 다른 후속 작업은 별도 승인 없이 진행하지 않습니다.

## 후속 오프라인 분석: 전체 요청 구성과 독립 구조화 단계

### 범위와 원인 확정 수준

이번 작업은 실제 Gemini 요청 **0회**인 코드 분석·Mock·설치 SDK 직렬화 검증입니다.
기존 두 번째 요청의 HTTP 400 / INVALID_ARGUMENT 재발 기록은 보존합니다.
`response_json_schema` 사용 및 잘못된 `additional_properties` 부재에도 서버가 거부했습니다.
설치 SDK의 직렬화는 완료되어 실제 HTTP 응답을 받았으므로, 과거 실패 위치는 로컬 Pydantic
생성 단계가 아니라 원격 요청 검증 단계입니다. 정확한 거부 필드·오류 reason은 여전히
**UNKNOWN**이며, 특정 Content 또는 스키마 속성을 확정 원인으로 지정하지 않습니다.

확인된 구성상의 문제는 최종 단계에 도구가 없는데도 기존 system_instruction이
`get_inspection_result` 호출을 요구했다는 점입니다. 이는 단계별 지침 충돌이지 HTTP 400의
확정 원인은 아닙니다. 그 밖에 네이티브 Function Calling 이력을 유지하면서 tools를 제거하고
출력 형식을 전환하는 조합은 호환성 조사 대상입니다. 조합 자체가 금지됐다고 판단하지 않습니다.

### 공식 문서와 설치 SDK의 구분

- 공식 모델 문서에는 정확한 ID `gemini-3.8-flash`와 Function Calling·Structured outputs·Thinking
  지원이 기재되어 있습니다. 지원되지 않는 `minimal` Thinking 설정은 현재 요청에 없습니다.
  [모델 문서](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)
- 공식 문서는 Gemini 3 계열의 도구와 구조화 출력 조합도 설명합니다. 따라서 두 기능이
  원천적으로 함께 사용 불가능하다는 가설은 채택하지 않았습니다. 다만 최신 예제의
  `response_format`과 설치 SDK 2.31.0의 필드는 구분해야 합니다. 설치된 GenerateContentConfig에는
  해당 필드가 없고, 기존 `response_json_schema` 직렬화 경로를 그대로 사용합니다.
  [구조화 출력 문서](https://ai.google.dev/gemini-api/docs/generate-content/structured-output?hl=en)
- 공식 수동 Function Calling 예제는 후속 조사 시 전체 모델 Content를 다시 포함합니다.
  현재 조사 루프도 모델 Content 객체·Part 순서·서명 바이트·호출 ID를 유지합니다.
  [Function Calling 문서](https://ai.google.dev/gemini-api/docs/generate-content/function-calling?authuser=0&hl=en),
  [서명 문서](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures)
- 설치된 `google-genai==2.31.0`에서 `response_schema`는 SDK Schema 변환을 거치고,
  `response_json_schema`는 `t_json_schema`가 그대로 반환하여 `responseJsonSchema`로 전달합니다.
  새 config를 요청마다 생성하므로 이전 `tool_config`가 최종 요청에 잔존하지 않습니다.
  [SDK 문서](https://googleapis.github.io/python-genai/)
- 2.31.0 릴리스 노트에는 이 프로젝트의 이력+스키마 전환 HTTP 400과 직접 일치하는 수정 또는
  제한이 확인되지 않았습니다. 관련 알려진 SDK 결함 여부는 **UNKNOWN**입니다.
  [공식 릴리스](https://github.com/googleapis/python-genai/releases/tag/v2.31.0)

모델 기능 지원 문서와 이번 계정·요청에 대한 서버 수락은 다릅니다. 실제 모델 목록 조회나
지원 여부를 시험하는 Gemini 요청은 하지 않았습니다.

### 첫 요청과 최종 요청 비교

| 항목 | 조사 요청 | 수정 전 최종 요청 | 수정 후 최종 요청 |
|---|---|---|---|
| Content | 초기 user 텍스트, 후속 조사는 native 이력 | user → model(FunctionCall) → user(FunctionResponse) | 독립 user 텍스트 1개 |
| 모델 Content·서명 | 후속 조사에서 원형 보존 | 동일 이력 포함 | 조사 이력을 전송하지 않음 |
| 결과 데이터 | 실제 Python 조회 결과 | native FunctionResponse | 같은 서버 보관 결과의 Evidence 문서 |
| system_instruction | 도구 선택·보안·진단 지침 | 조사 지침 + 최종 지시 | 근거 해석·보안·최종 진단 전용 |
| tools / tool_config | 4개 선언 / AUTO | 없음 / 없음 | 없음 / 없음 |
| response_mime_type | 미설정 | application/json | application/json |
| response_json_schema | 미설정 | DiagnosisDraft 투영 | 동일 투영, 변경 없음 |

설치 SDK의 로컬 직렬화에서 실제 REST 본문의 키는 조사 단계에
`contents`, `systemInstruction`, `generationConfig`, `tools`, `toolConfig`이며,
최종 단계에는 앞의 세 개만 있습니다. 변환기의 내부 `_url`은 라우팅 보조 필드로 구분합니다.
generationConfig는 공통 `temperature=0`, `candidateCount=1`, `maxOutputTokens=4096`에,
최종 단계만 `responseMimeType`과 `responseJsonSchema`를 추가합니다.
`thinkingConfig`, `responseSchema`, 불필요한 `functionCallingConfig`는 최종 본문에 없습니다.
SDK 전용 AFC 비활성화·automatic_continuation=False·HTTP timeout 및 attempts=1도 유지합니다.

스키마는 필수 루트 필드 6개, `$defs` 3개, 중첩 객체/배열·Enum·Nullable anyOf·$ref를 유지합니다.
로컬 합성 fixture의 스키마 문서 JSON 최대 깊이는 7이지만 이는 Gemini의 서버 복잡도 계산값이
아닙니다. 서버에서 허용할 정확한 복잡도와 특정 거부 속성은 여전히 UNKNOWN입니다.

### A/B 설계 비교와 선택

| 기준 | A: 네이티브 조사 이력 재사용 | B: 독립된 검증 근거 요청 |
|---|---|---|
| 요청 계약 | 공식 수동 후속 호출 방식과 가깝지만 단계 전환 조합 미검증 | 도구 없는 일반 구조화 요청으로 결합 축소, 서버 수락 미검증 |
| thought signature | 전체 모델 Part와 바이트 보존 필요 | 원래 조사 루프에서 보존, 최종에는 모델 이력 자체가 없음 |
| 컨텍스트 | 모델 생각·호출 인자·종료 문장도 누적 | 실제 allowlist 결과와 최소 provenance만 전송 |
| 근거 추적 | FunctionResponse의 evidence_id 연결 | 같은 evidence_id·source_tool·document 및 서버 Trace 연결 |
| 환각·유출 | 검증은 동일하나 모델의 자유 문장도 재전송 | 모델 자유 문장 제외, 원래 도구 allowlist·별칭 정책 유지 |
| 최종 검증 | 원래 서버 Evidence와 대조 | 동일 서버 Evidence와 대조, 약화 없음 |

**B를 최소한의 호환성 위험 완화안으로 선택했습니다. 실제 HTTP 400 해결이 증명된 것은 아닙니다.**
Function Calling 조사·Python 실행은 그대로 두고, 최종 요청 생성과 해당 단계의 지침만 분리합니다.
정상 조기 종료는 유지하며, 추가 종료 확인 또는 모델 요청을 만들지 않습니다.

독립 요청의 user 텍스트는 JSON 봉투이며, 구조는 다음과 같습니다. 실제 운영 값은 기록하지 않습니다.

```text
inspection_id
evidence[E0001] = {source_tool, document: 원래 allowlist 도구 응답}
tool_execution_trace[] = {sequence, tool_name, executed, success, error_code, evidence_id}
```

JSON Pointer는 봉투가 아니라 각 `document`를 기준으로 해석합니다. 실패한 도구는 성공 근거로
만들지 않으며 오류 코드와 성공 여부만 Trace에 남깁니다. 서버의 원래 Evidence·snapshot·Trace가
최종 검증의 권위이고, 모델이 생성한 조사 텍스트는 근거에 포함하지 않습니다.
이미지 ID는 제외하고 제품 ID는 기존 별칭을 유지합니다. 원시 메시지·임의 metrics·사적 평가 필드는
기존 도구 allowlist에 의해 제외되며, 서명·호출 ID·모델 생각도 독립 요청에 넣지 않습니다.

중요한 계측 차이: 정상 조기 종료 경로에서는 native FunctionResponse를 다음 모델 요청에
재전송하지 않고, **동일한 실제 조회 결과를 독립 근거 텍스트로 전달**합니다. 따라서 이 경로를
네이티브 FunctionResponse 후속 수락 성공으로 보고하면 안 됩니다. 추가 조사 라운드에서는
기존 native FunctionResponse의 user 역할·이름·ID·Part 경계·서명 보존을 그대로 검증합니다.

로컬 합성 정상 fixture에서 최종 Content 크기는 기존 1,077 → 새 1,069바이트,
직렬화 변환 결과 전체는 7,925 → 6,832바이트였습니다. 가상 서명 길이를 사용한 단일 fixture의
관찰일 뿐이며, 실제 토큰·비용 감소나 운영 데이터의 감소율을 보증하지 않습니다.
정상 경로의 예상 모델 요청 수는 여전히 2회이고 실제 요청 수는 다음 승인 실험에서 확인해야 합니다.

### 오프라인 단계별 재현

| 요청 구성 | SDK 직렬화 | 실제 서버 수락 |
|---|---|---|
| 단순 구조화 스키마 + user 텍스트 | PASS | NOT TESTED |
| 전체 진단 스키마 + user 텍스트 | PASS | NOT TESTED |
| FunctionCall 포함 모델 이력 + 전체 스키마 | PASS | NOT TESTED |
| user FunctionResponse까지 포함한 이력 + 전체 스키마 | PASS | NOT TESTED |
| 독립된 서버 근거 + 전체 스키마 | PASS | NOT TESTED |

세 번째 구성의 미응답 FunctionCall도 SDK 변환기 자체는 직렬화합니다. 이것은 유효한 대화 순서나
서버 수락을 증명하지 않습니다. 서비스는 자체 history 검증을 유지하고, 최종 요청에는 user
1개·일반 text Part 1개만 허용하여 native 이력이 실수로 재삽입되는 것을 전송 전에 차단합니다.
실제 SDK AsyncModels를 사용하는 Mock transport 테스트도 최종 responseJsonSchema와 새 Content를
확인합니다. 테스트 대역 반환은 실제 Gemini의 결과가 아닙니다.

### 변경 파일과 검증

- `backend/agent/service.py`: 서버 Evidence 봉투 생성, 최종 단일 텍스트 요청 제한, 최종 요청 분리.
- `backend/agent/prompts.py`: 공통 보안/근거 지침을 유지하면서 조사·보고 전용 지침 분리.
- `tests/test_agent_report_request.py`: 신규 27개. 다섯 요청 형태, 실제 근거 보관·격리,
  변조 거부, 비공개 필드 비노출, Content 제한, 크기 제한, T01/T03/T05/T06 합성 Mock 검사.
- `tests/test_agent_service.py`, `tests/test_agent_efficiency.py`, `tests/test_agent_response_schema.py`,
  `tests/test_agent_api.py`: 새 최종 요청 계약 반영. native 후속 조사 프로토콜·HTTP 502 회귀 유지.
- `docs/day4-step2-agent.md`, 본 문서: 독립 최종 요청과 미검증 범위 설명.

최초 관련 테스트 실행은 228 PASS / 2 FAIL이었습니다. 기존 누적 컨텍스트 테스트는 이제
전송되지 않는 최종 native 이력 대신 추가 조사 이력이 실제로 한도를 넘도록 fixture를 수정했습니다.
독립 근거 패킷의 크기 상한도 별도 테스트합니다. 짧은 sleep에 의존하던 timeout fixture는
취소될 때까지 기다리는 Event로 바꿔 Windows 타이머 스케줄링에 따른 불안정성을 제거했습니다.
운영 timeout·호출 제한 또는 오류 계약은 변경하지 않았습니다.

검증은 Conda `vision-insight` Python, 임시 JSONL·출력·로그 경로와 공개 테스트 fixture 복사본에서
수행했습니다. pytest 실행 중 실제 SDK sync/async 요청 경로를 차단했고 호출 시도도 0회였습니다.

| 항목 | 결과 |
|---|---|
| 직전 기준 회귀 | 기존 386개 유지 |
| 신규 테스트 | 27개 |
| 전체 pytest | **413 passed, 3 warnings**, 실패·건너뜀 0 |
| 실행 | `python -m pytest tests -q -p no:cacheprovider`에 임시 경로·간결 출력 옵션 적용 |
| `python -m pip check` | No broken requirements found |
| 변경 파일 공백 검사 | PASS |
| 실제 Gemini 요청 / SDK 전송 시도 | **0회 / 0회** |
| 검사·이벤트 JSONL / 체크포인트 / 모델 메타데이터 | 작업 전후 SHA256 동일 |
| 모델 / SDK / 고정 임계값 | 변경 없음 |

### 다음 승인 실험에서 확인할 사항

오프라인 구조·검증 준비는 완료했지만 실제 서버 수락·최종 JSON 생성·최종 근거 검증은
**NOT TESTED**입니다. 사용자 승인 후 T01 한 건으로 독립 구조화 요청의 실제 HTTP 상태,
조회 결과의 근거 봉투 전달, Pydantic·결정적 비교, 저장 판정 일치를 확인해야 합니다.
기존 계측에서 native FunctionResponse 수락과 독립 Evidence 전달을 구분하여 기록해야 합니다.
서버가 스키마 자체의 다른 속성이나 복잡도를 거부할 가능성은 남아 있으며, 추가 실패 시
안전한 오류 reason이 확보되지 않는 한 원인은 UNKNOWN으로 유지합니다.

이번 작업에서는 실제 T01 재호출, 다른 시나리오 호출, Step 5, 배포 또는 Git add/commit/push를
수행하지 않았습니다. 추가 실제 API 검증은 별도 승인을 기다립니다.

## 실제 재검증: T01 독립 Evidence 기반 구조화 요청

### 승인 범위와 사전 점검

2026-10-15 07:49 UTC(16:49 KST), 사용자 승인으로 T01 `INSP-001396` 한 건의 분석을
`POST /analyze/INSP-001396`에 정확히 한 번 요청했습니다. 모델은 `gemini-3.8-flash`,
SDK는 `google-genai==2.31.0`으로 유지했습니다. 아래 결과는 Mock이 아니라 실제 Gemini
전송을 계측한 결과입니다. FastAPI TestClient로 실제 ASGI 엔드포인트와 기존 의존성·서비스·
저장소를 호출했고, 별도 우회 Agent나 신규 검사를 만들지 않았습니다.

사전 점검에서 API 키 존재만 확인했으며 값은 출력하지 않았습니다. 실제 저장 레코드의
allowlist 결과·제품 별칭·이미지 ID 제외, SDK 도구 선언, 정상 조기 종료 조건, 최종 단일 user
텍스트의 Evidence 봉투, tools/toolConfig 부재, responseJsonSchema 일치, 잘못된
additional_properties 부재, 필수 필드·정의 유지를 확인했습니다. 사전 점검의 네트워크 시도는
0회였고, 관련 오프라인 테스트는 다음 명령으로 **81개 통과**했습니다.

```powershell
python -m pytest tests/test_agent_report_request.py tests/test_agent_efficiency.py tests/test_agent_response_schema.py -q -p no:cacheprovider
```

실제 실행은 Git 제외 경로의 기존 수동 계측 스크립트에 이번 승인용 별도 잠금과 독립 Evidence
검증을 적용했습니다. 잠금은 기존 파일을 덮어쓰지 않는 생성 방식이며, 같은 분석의 재실행을
차단합니다. 운영 backend와 테스트 코드는 이번 실험에서 변경하지 않았습니다.

### 실제 요청별 결과

| 요청 | 단계 | Gemini HTTP | 확인 결과 | SDK 요청 시간 |
|---|---|---|---|---:|
| 1 | Function Calling 조사 | 200 | 모델이 get_inspection_result 선택, 실제 Python 조회 성공 | 2,815.313ms |
| 2 | 독립 구조화 진단 | 400 / INVALID_ARGUMENT | 서버 근거와 동일한 봉투 전송 확인, 최종 진단 생성 실패 | 1,223.924ms |

SDK generate 호출과 실제 HTTP 전송은 각각 **2회**였습니다. 자동 재시도·대체 모델·추가 분석은
0회입니다. 두 번째 요청은 조사 대화 이력이 없는 독립 user 텍스트 1개였고, 실제 전송 경계에서
Evidence와 최소 Trace가 서버 생성 패킷과 정확히 일치함을 확인했습니다. tools와 toolConfig는
없었으며, responseJsonSchema는 검토한 투영과 일치했습니다. responseSchema와 잘못된
additional_properties도 없었습니다.

안전한 오류 정보는 `ClientError`, HTTP `400`, 상태 `INVALID_ARGUMENT`입니다.
추가로 공개할 수 있는 오류 reason과 정확한 거부 필드는 **UNKNOWN**입니다. 이번 오류의
정제된 메시지 지표는 빈 목록이었으므로 RESPONSE_SCHEMA 지표가 다시 관측됐다고 주장하지
않습니다. 이력 분리 후에도 거부가 재발했지만 스키마의 특정 속성 또는 모델의 정확한 거부
조건은 이번 결과만으로 확정할 수 없습니다.

### 실제 Python 실행과 조기 종료

Agent가 생성한 실제 Tool Execution Trace는 다음 한 건입니다.

```json
{
  "sequence": 1,
  "round_number": 1,
  "tool_name": "get_inspection_result",
  "arguments": {"inspection_id": "INSP-001396"},
  "executed": true,
  "success": true,
  "error_code": null,
  "elapsed_ms": 2.254,
  "evidence_id": "E0001"
}
```

- 첫 모델 응답에서 실제 Function Call 1개, 호출 ID 1개, 서명이 있는 Part 1개를 수신했습니다.
  호출 ID와 서명 원문은 기록하지 않았습니다.
- 서버가 검증한 함수 인자로 기존 조회 도구가 실제 저장소를 읽었습니다.
- HTTP 존재 확인까지 합하면 `get_inspection_result` 메서드 및 저장소 get_inspection은 각각
  2회 실행됐습니다. 그중 첫 번째는 HTTP 선행 존재 확인이고, 모델 선택에 따른 Agent 도구
  실행은 Trace에 있는 **1회**입니다. 이를 두 번의 모델 도구 실행으로 계산하지 않습니다.
- `tools_used`는 `get_inspection_result` 하나입니다. 로그·품질·이력 조회는 실행하지 않았습니다.
- 저장된 여섯 핵심 상태가 정상 조합이며 anomaly_score=31.334630966186523,
  decision_threshold=34.1442였습니다. 실행 도구 1개 직후 `normal_evidence_ready=true`를
  관측했으며, **서버 정책**에 따라 종료 확인 없이 독립 구조화 단계로 전환했습니다.
  모델이 스스로 조기 종료를 결정했다고 해석하지 않습니다.
- 최종 요청은 E0001 문서와 최소 Trace를 전달했습니다. native FunctionResponse와 모델
  Content·서명은 이 독립 요청에 포함하지 않는 설계이므로, 이번 결과는 native FunctionResponse
  후속 수락 또는 서명 재전송 성공을 검증한 것이 아닙니다.

### 최종 결과와 사용량

| 항목 | 실제 결과 |
|---|---|
| 검사 ID / 분석 시도 | INSP-001396 / 1회 |
| 실제 SDK 요청 / HTTP 전송 | 2회 / 2회 |
| Function Calling / Python 조회 | PASS / PASS |
| 정상 검사 조기 종료 | PASS, 서버 정책 적용 |
| 독립 구조화 요청 | FAIL, 요청 2에서 HTTP 400 |
| 최종 구조화 진단 | 생성되지 않음 |
| 최종 Pydantic / Evidence·JSON Pointer 검증 | NOT TESTED / NOT TESTED |
| FastAPI HTTP | 502 |
| analysis_status / 오류 코드 | FAILED / GEMINI_REQUEST_FAILED |
| 기존 저장 판정 | OK / OK / ALL_CHECKS_PASSED 유지 |
| 확인된 입력 / 출력 / Thinking 토큰 | 1,152 / 28 / 79 |
| 확인된 합계 토큰 | 1,259 |
| 실패 요청의 토큰 / 전체 비용 | NOT AVAILABLE / NOT AVAILABLE |
| Agent 분석 시간 / 전체 HTTP 실행 시간 | 4,045.072ms / 4,110.767ms |
| 전체 T01 검증 | **FAIL** |

토큰은 성공한 첫 Gemini 응답에서 확인된 값이며, 실패한 두 번째 요청까지 포함한 전체 사용량으로
단정하지 않습니다. 최종 구조화 응답이 없어 Pydantic·근거 비교는 도달하지 못했습니다.
최종 판정이 생성됐다는 의미의 성공은 아니며, 저장된 원래 판정은 변경하지 않았습니다.

실제 FastAPI 응답:

```json
{"detail":{"analysis_status":"FAILED","error_code":"GEMINI_REQUEST_FAILED"}}
```

HTTP 오류 응답에 Trace를 추가하지 않았으며, 위 Trace는 계측한 Agent 내부 실행 기록입니다.

### 보호·제한·중단

- 기존 최대 4라운드·8회 도구 실행·동일 호출 2회, 모델 15초·도구 3초·전체 60초를 유지했습니다.
- SDK attempts=1, AFC·자동 continuation 비활성화 및 전송 경계 재시도 차단을 유지했습니다.
  이전과 같이 HTTPX 전송을 사용하여 aiohttp 내부 연결 재전송 분기를 사용하지 않았습니다.
- 저장소 쓰기 시도 0회. 운영 검사/이벤트 JSONL·체크포인트·모델 메타데이터는 작업 전후
  SHA256이 동일합니다. 임계값 34.1442·원본 이미지·검사 판정 정책도 변경하지 않았습니다.
- 평가 정답·원본 경로·주입 정보·키·서명 원문을 전송 또는 결과 문서에 포함하지 않았습니다.
- 이번에는 사전 오프라인 81개 테스트만 다시 실행했습니다. 이전 전체 413개 통과는 이전 보고이며,
  이번 실험에서 전체 pytest를 재실행한 것으로 보고하지 않습니다.
- 결과는 별도 회차로 추가했으며 이전 실패 기록·기존 잠금·결과 파일을 보존했습니다.

독립 요청도 최종 생성 단계에서 실패했으므로 나머지 실제 시나리오 진행 준비가 완료됐다고
판정하지 않습니다. 다음 작업은 추가 실험이 아니라 별도 지시에 따른 오프라인 원인 분석이
필요합니다. 추가 T01 호출, T03/T05/T06, Step 5 또는 Git add/commit/push 없이 중단했습니다.

## 오프라인 원인 격리: 스키마 A~D 비교와 안전한 오류 상세

### 결론과 변경 범위

이번 작업의 실제 Gemini 요청은 **0회**입니다. T01과 다른 운영 시나리오를 재실행하지 않았습니다.
최근 독립 구조화 요청의 400 / INVALID_ARGUMENT는 확인된 과거 사실이며, 정확한 서버 거부
필드와 근본 원인은 여전히 **UNKNOWN**입니다. 오프라인에서 현재 최종 요청에 새로 확인된
명백한 계약 위반은 없으므로 **운영 스키마·프롬프트·서비스·API를 다시 변경하지 않았습니다.**

별도로 확인된 문제는 기존 수동 계측이 SDK 예외의 구조화된 `details`를 추출하지 않고
메시지의 키워드만 분류해 오류 reason과 필드 경로를 보존하지 않았다는 관측성 한계입니다.
설치 SDK 2.31.0의 APIError는 원래 응답 JSON을 `details`에 보유하므로, 향후 승인 실험에서
안전한 일부만 추출하도록 보강했습니다. 과거 저장 기록에는 원본 details가 없으므로 이전
거부 필드를 소급 복원할 수는 없습니다.

### 최종 요청의 실제 구성 점검

| 항목 | 확인 결과 |
|---|---|
| 모델 / SDK | gemini-3.8-flash / google-genai 2.31.0, 변경 없음 |
| MIME | response_mime_type=application/json |
| 스키마 | response_json_schema만 설정, response_schema 없음 |
| 도구 설정 | tools·tool_config 없음, 최종 본문에도 tools·toolConfig 없음 |
| Content | role=user 1개·일반 text Part 1개, 서버 Evidence와 최소 Trace |
| 조사 이력 | model Content·FunctionCall·FunctionResponse·서명 없음 |
| system_instruction | 최종 보고 전용 일반 텍스트, 도구 선택 지침 없음 |
| 생성 옵션 | temperature=0, candidate_count=1, max_output_tokens=4096 |
| SDK 실행 옵션 | AFC/automatic_continuation 비활성화, timeout=15000ms, attempts=1 |
| 현재 로컬 SDK의 유효 API 설정 | Gemini Developer API / v1beta / 승인된 Google 호스트 |
| 요청 옵션 덮어쓰기 | per-request API 버전·base_url·extra_body 미설정, 현재 client extra_body 없음 |

API 버전·호스트는 현재 설정으로 SDK 클라이언트를 생성해 로컬 옵션만 확인한 결과입니다.
해당 과정에서도 HTTP 전송은 없었습니다. 직전 실제 실행 기록에는 API 버전이 따로 저장되지
않았으므로 과거 전송 URL의 버전을 새 관측 사실처럼 확정하지 않습니다. 향후 수동 계측에는
허용된 버전 문자열만 기록하도록 추가했으며 전체 URL·헤더·키를 기록하지 않습니다.

SDK 변환기의 내부 `_url`은 REST 본문 필드가 아닙니다. 신규 테스트는 실제
BaseApiClient._build_request까지 오프라인으로 실행해 이 보조 필드가 제거되고, 최종 본문에
`contents`, `systemInstruction`, `generationConfig`만 남는지 확인했습니다.
systemInstruction도 text Part이며, 최종 user 텍스트 외에 잘못된 role 또는 일반 추가 턴은 없습니다.
현 설정에서 서로 충돌하는 responseSchema/responseJsonSchema나 잔존 functionCallingConfig는
발견하지 못했습니다.

### 공식 계약과 스키마 범위

설치 SDK의 response_json_schema는 별도의 Schema 변환 없이 JSON을 responseJsonSchema로
전달합니다. 공식 SDK 문서에도 기존 response_mime_type + response_json_schema 방식이 남아
있지만 최신 생성 가이드 예제는 response_format을 사용합니다. 설치된 GenerateContentConfig에는
response_format 필드가 없습니다. 이 차이는 확인된 사실이지만 기존 방식이 이 모델에서 폐지됐거나
반복 400의 원인이라는 증거는 아닙니다. 모델·SDK·요청 필드를 임의로 교체하지 않았습니다.
[공식 SDK 문서](https://googleapis.github.io/python-genai/)

REST의 JSON Schema 지원 목록을 기준으로 현재 투영에 목록 밖 속성은 없었습니다.
$defs/$ref/anyOf와 additionalProperties는 명시 범위에 있으며, 모든 참조는 존재하는 정의를
가리키고 순환 참조나 $ref에 일반 형제 속성이 붙는 경우는 없습니다. `nullable` 대신 표준
anyOf의 null 타입을 사용합니다. 실제 모델이 이 조합을 수락할지는 별도 문제입니다.
[REST GenerationConfig 계약](https://ai.google.dev/api/generate-content#generationconfig)

공식 문서는 큰 스키마·깊은 중첩이 거부될 수 있다고 설명하지만 모델별 정확한 수치 한도를
제공하지 않습니다. 크기나 깊이만 보고 현재 스키마가 과도하다고 확정할 수 없습니다.
[구조화 출력 가이드](https://ai.google.dev/gemini-api/docs/generate-content/structured-output?hl=en)

### 단계별 축소 분석

A~C는 **테스트 전용 합성 스키마**이며 운영 DiagnosisDraft를 대체하지 않습니다.
공통 중립 텍스트와 같은 SDK 설정을 유지하고 스키마만 비교했습니다. 원래 보고 전용 지침은
전체 DiagnosisDraft의 필드를 요구하므로, 축소 실험에서 그 지침을 그대로 사용하면 목표가
충돌할 수 있습니다. 따라서 비교 fixture의 지침은 네 단계 모두 동일한 일반 JSON 생성 지침입니다.
운영 보고 지침 자체는 별도의 실제 서비스 Mock 테스트에서 그대로 확인했습니다.

| 단계 | 필드 구성 | 스키마 바이트 | 컨테이너 깊이 | $defs / $ref / anyOf | null / 배열 | SDK 직렬화 | 서버 수락 |
|---|---|---:|---:|---|---|---|---|
| A | summary:string | 90 | 1 | 0 / 0 / 0 | 0 / 0 | PASS | NOT TESTED |
| B | summary·status·recommended_checks:string[] | 222 | 2 | 0 / 0 / 0 | 0 / 1 | PASS | NOT TESTED |
| C | summary·observed_facts内 evidence_id/source_field/observed_value | 362 | 3 | 0 / 0 / 0 | 0 / 1 | PASS | NOT TESTED |
| D | 全 DiagnosisDraft 필수 필드·Enum·배열 제한·표준 제약 | 2,846 | 4 | 3 / 3 / 2 | 2 / 6 | PASS | NOT TESTED |

바이트는 로컬 json.dumps 기본 공백을 포함한 UTF-8 스키마 문서의 측정값입니다. 컨테이너 깊이는
참조를 해석한 객체·배열 계층 수이며, 이전에 보고한 스키마 문서 자체의 JSON 깊이 7과는 다른
지표입니다. Gemini 서버 내부 복잡도 값이나 임계값이 아닙니다.

- A~D 모두 공식 REST 명시 목록 밖 속성 0개였고, MIME과 단독 responseJsonSchema 설정을
  유지했습니다. 이것은 로컬 계약 점검이지 실제 서버 호환성 PASS가 아닙니다.
- D는 기존 모든 진단 필드·정의·필수 필드를 유지합니다. 서버 Pydantic의 pattern/maxLength 등은
  원래대로 적용하며, 운영 전달 스키마 투영에도 변경이 없습니다.
- C의 문자열 evidence_id가 실제 도구 결과와 연결됐다는 사실은 스키마 구조만으로 입증되지
  않습니다. 운영의 JSON Pointer·Evidence ID·Trace 결정적 비교가 계속 최종 검증 기준입니다.
- 새 테스트는 미검토 속성을 주입했을 때 검출하는지도 확인합니다. 이는 현재 JSON Schema
  경로의 명시 목록 검사이며, 같은 이름의 속성이 다른 Schema API에서도 모두 금지된다는
  의미는 아닙니다.

### 안전한 오류 상세 수집

`backend/agent/diagnostics.py`의 `safe_gemini_error(failure, stage)`는 APIError에서 다음 정보만
새 객체로 추출합니다. 운영 HTTP 오류 응답에 새 필드를 추가하거나 원시 예외를 로그에 남기지 않습니다.

| 반환 필드 | 정책 |
|---|---|
| http_status | 정수 100~599만 허용 |
| google_api_code | Google 표준 상태 코드 allowlist, 그 외 UNKNOWN |
| reason | google.rpc.ErrorInfo의 사전 허용 상수만, 메시지에서 추론하지 않음 |
| field_violations | google.rpc.BadRequest.fieldViolations의 안전한 field와 허용 reason만 |
| request_stage | FUNCTION_CALLING / STRUCTURED_OUTPUT / UNKNOWN |
| sdk_exception_type | APIError / ClientError / ServerError / UNKNOWN |

필드 경로는 길이·문법뿐 아니라 알려진 요청 필드·JSON Schema 키·서버 진단 모델의 필드 이름을
모두 allowlist로 검증합니다. 임의 키, 경로, 제어 문자 또는 확인 불가 경로는 UNKNOWN으로
바꿉니다. 상세 항목은 최대 16개만 조사하고 위반 필드는 최대 10개만 보존합니다.
message·description·metadata·domain·요청/응답 본문·프롬프트·헤더·서명·예외 문자열은 복사하지
않습니다. 문자열을 일부 치환하는 방식이 아니라 허용 구조만 새로 생성합니다.
상세가 없거나 미지원 reason이면 UNKNOWN을 유지합니다.

이 정책은 표준 ErrorInfo와 BadRequest 형식에 근거합니다.
[Google 오류 상세 정의](https://raw.githubusercontent.com/googleapis/googleapis/master/google/rpc/error_details.proto)

예시(Mock 오류이며 실제 서버 결과가 아님):

```json
{
  "http_status": 400,
  "google_api_code": "INVALID_ARGUMENT",
  "reason": "INVALID_SCHEMA",
  "field_violations": [{"field": "generationConfig.responseJsonSchema", "reason": "INVALID_VALUE"}],
  "request_stage": "STRUCTURED_OUTPUT",
  "sdk_exception_type": "ClientError"
}
```

수동 계측 스크립트의 API 오류 수집에 이 함수를 연결했습니다. 기존 실행 잠금은 그대로이며
스크립트를 실제 분석 모드로 실행하지 않았습니다. 서비스의 실패 코드는 기존
GEMINI_REQUEST_FAILED, HTTP 매핑은 502로 유지합니다. 오류가 구조화 details를 제공하지 않는
경우에는 이 개선 후에도 원인이 UNKNOWN일 수 있습니다.

### 변경 파일과 테스트 결과

- 신규 `backend/agent/diagnostics.py`: 순수 allowlist 기반 오류 정제 함수.
- 신규 `tests/test_agent_schema_isolation.py`: A~D 축소 fixture·SDK 요청 생성·스키마 점검·
  오류 개인정보 차단·크기 제한·실패 계약 회귀 **39개**.
- Git 제외 `data/outputs/manual_validation/run_t01_retry.py`: 향후 승인 실험의 정제 오류 상세와
  안전한 API 버전 계측만 보강. 승인 잠금·호출 제한·전송 정책은 변경하지 않았습니다.
- 본 문서: 이전 실제 실패 기록을 보존한 채 분석과 승인 계획 추가.

새 테스트 최초 실행에서 37 PASS / 1 FAIL이었습니다. SDK 모델 변환의 내부 `_url`을 실제
HTTP 본문 필드로 가정한 테스트 기대값 문제였으며, SDK _build_request까지 검증하도록
수정했습니다. 이를 서버 HTTP 400의 원인으로 오인하거나 운영 요청을 변경하지 않았습니다.

| 검증 | 실제 결과 |
|---|---|
| 신규 테스트 | 39개 |
| 기존 회귀 | 기존 413개 유지 |
| 전체 pytest | **452 passed, 3 warnings**, 실패·건너뜀 0 |
| 전체 테스트 명령 | `python -m pytest tests -q -p no:cacheprovider`에 임시 경로·간결 출력 옵션 적용 |
| pip check | No broken requirements found |
| Python 문법 / 변경 파일 공백 검사 | PASS / PASS |
| 실제 Gemini 요청 / SDK 전송 시도 | **0회 / 0회** |
| 운영 JSONL·체크포인트·메타데이터 | 전후 SHA256 동일 |

전체 테스트는 Conda vision-insight, 임시 JSONL·출력·로그 경로와 공개 fixture 복사본을 사용했고,
실제 SDK request/async_request 경로를 차단했습니다. 평가 전용 정답을 별도로 조회하지 않았고,
원본 이미지·평가 파일을 수정하지 않았으며 고정 임계값 34.1442도 유지합니다.

### 다음 실제 실험 계획 — 이번에는 실행하지 않음

목적은 T01 재시도가 아니라 **구조화 출력 레이어의 최소 서버 재현**입니다. 기존 공식 SDK의
generate_content를 사용하되 Function Calling이나 검사 조회를 실행하지 않고, 같은 중립적인
합성 입력·일반 JSON 생성 지침·모델·API 버전·생성 옵션을 유지하며 스키마만 바꿉니다.
운영 Agent나 판정 검증을 우회해 성공시키는 실험으로 해석하지 않습니다.

| 순서 | 별도 승인 대상 | 예상 HTTP 요청 | 확인할 가설 | 중단 기준 |
|---|---|---:|---|---|
| 1 | A 최소 summary | 1회 | 단순 스키마와 현재 SDK JSON 경로도 거부되는가 | 실패하면 B~D 실행하지 않고 오류 상세 분석 |
| 2 | B 기본 진단 | 1회 | 문자열 필드·배열 추가에서 거부가 시작되는가 | 실패하면 C~D 중단 |
| 3 | C Evidence 구조 | 1회 | 배열 속 객체·근거 필드 구조에서 거부되는가 | 실패하면 D 중단 |
| 4 | D 원래 전체 스키마 | 1회 | 정의·참조·Union·Enum·배열 제한이 합쳐진 전체만 거부되는가 | 실패 시 축소 비교만 수행, 즉석 재호출 금지 |

각 실험은 앞 단계 결과 보고 후 **개별 사용자 승인**을 받아야 합니다. 모두 승인돼 진행하더라도
상한은 4회이며 자동 재시도·모델 목록 조회·모델 전환은 없습니다. 각 요청은 15초 제한·SDK
attempts=1·자동 continuation 비활성화·전송 재시도 차단을 유지합니다. 인증/429/5xx/timeout 또는
안전성 위반이 발생하면 나머지 실험을 중단합니다. API 호출마다 비용이 발생할 수 있으며,
실제 입력·출력·Thinking 토큰과 금액은 실행 전 **NOT AVAILABLE**입니다.

A~C는 응답 JSON의 시험 스키마 일치만 검증합니다. D는 원래 Pydantic을 적용하고 합성 Evidence와
일치하는지도 확인하지만, 이것이 실제 T01의 도구 실행과 진단 성공을 증명하지는 않습니다.
D까지 통과한 경우에만 운영 T01 전체 분석의 추가 승인 여부를 별도로 검토합니다. 그것은 위
4회 예산이나 이번 작업에 포함되지 않으며 자동으로 실행하지 않습니다.

지금 실제 호출 없이 더 확인할 수 있는 범위는 로컬 요청 빌드·스키마 정적 검사·안전한 오류
fixture와 회귀 테스트입니다. 서버가 특정 제약을 거부하는지와 계정/모델의 유효 지원 여부는
이 방법만으로 입증할 수 없습니다. 이번 작업은 오프라인 분석·최소 계측 수정·테스트·기록에서
종료하며 T01/T03/T05/T06, Step 5, 배포 또는 Git add/commit/push 없이 다음 지시를 기다립니다.

## 실제 최소 재현: 스키마 A 서버 수락 검증

### 승인과 실행 범위

2026-10-15 08:40 UTC(17:40 KST), 사용자 승인으로 최소 스키마 A의 실제 Gemini HTTP 요청을
**한 번만** 전송했습니다. T01 분석 API나 다른 스키마 실험은 실행하지 않았습니다.

- 모델: `gemini-3.8-flash`
- SDK: `google-genai==2.31.0`
- API: Gemini Developer API / `v1beta`
- 스키마: `summary:string`이 필수인 object, 기존 A fixture와 동일한 90바이트
- 설정: `response_mime_type=application/json`, `response_json_schema`만 사용
- 입력: 무해한 합성 텍스트만 사용, 운영 검사·제품·이미지·평가 정보 미사용
- tools·tool_config·Function Calling 이력 없음
- SDK attempts=1, AFC·자동 continuation 비활성화, 요청 제한 15초 유지

Git 제외 경로의 전용 실행기 `data/outputs/manual_validation/run_schema_a_once.py`를 사용했습니다.
기존 Agent나 운영 스키마는 변경하지 않았습니다. 실행기는 별도 생성 전용 잠금으로 재실행을
차단하고, 실제 전송 경계에서 모델·호스트·API 버전·본문 구조·스키마를 검증한 뒤 최대 1회만
허용합니다. HTTPX transport retries=0과 중복 전송 차단도 적용했습니다.

사전 로컬 직렬화·입력 제한·JSON 검증 점검과 실제 SDK를 사용하는 Mock 응답 시험을 통과했습니다.
Mock 시험의 가상 응답은 아래 실제 결과와 별개이며, 사전 외부 HTTP 요청은 0회였습니다.
첫 Mock 실행에서는 네트워크 차단 fixture가 Windows 이벤트 루프의 내부 소켓 생성까지 막아
실패했습니다. 이벤트 루프 생성 후 차단을 적용하는 테스트 방식으로 바로잡았으며 실제 요청을
시도하거나 SDK·운영 코드를 수정한 문제는 아닙니다.

### 실제 관측 결과

| 항목 | 실제 결과 |
|---|---|
| 실제 Gemini HTTP 요청 | **1회** |
| Gemini HTTP 상태 | **200** |
| 최소 스키마 A 수락 | PASS |
| 응답 종료 | STOP |
| 실제 JSON 텍스트 생성 | PASS |
| 엄격한 JSON 파싱 | PASS |
| summary 필드 존재 | PASS |
| summary 자료형 | string, PASS |
| 스키마 A 일치 | PASS |
| 입력 토큰 | 35 |
| 출력 토큰 | 12 |
| Thinking 토큰 | 185 |
| 합계 토큰 | 232 |
| 전송 소요 시간 | 3,271.855ms |
| 전체 실행 시간 | 3,346.048ms |
| 비용 | NOT AVAILABLE |
| 자동 재시도 / 추가 요청 | 0회 / 0회 |
| 전체 실험 | **PASS** |

HTTP 200뿐 아니라 실제 모델이 반환한 텍스트를 JSON으로 파싱하고 object 안에 필수 summary가
존재하며 문자열인지 검증했습니다. 중복 키나 비표준 NaN/Infinity를 허용하지 않았습니다.
A는 additionalProperties를 제한하지 않는 스키마이므로 그 계약 그대로 검증했습니다.
프롬프트·요청 본문·실제 응답 문장·인증 정보는 결과 기록에 포함하지 않았습니다.
실패가 없으므로 오류 reason·fieldViolations·SDK 오류 유형은 **NOT APPLICABLE**입니다.

### 데이터 보호와 변경 사항

- 이번 실험의 운영 데이터 파일 접근은 감사 훅으로 차단했습니다. 운영 data·모델·dataset·
  test_data 경로 접근 시도는 **0회**였으며, JSONL이나 모델의 해시를 계산하기 위해 해당 파일을
  읽는 작업도 하지 않았습니다.
- 검사 레코드 조회·Python 검사 도구 실행·Function Calling·FastAPI 분석 호출은 모두 0회입니다.
- 운영 JSONL·체크포인트·메타데이터·원본 이미지·판정 정책·고정 임계값 34.1442를 변경하지 않았습니다.
- 변경은 Git 제외 전용 실행기와 이번 검증 문서에 한정됩니다. 실행 잠금과 정제된 메타데이터
  결과는 Git 제외 경로에 보관했습니다. 기존 실패 기록과 기존 실험 잠금은 유지합니다.
- 이번에는 전용 실행기의 오프라인 점검과 Mock 시험을 수행했으며 전체 pytest는 재실행하지
  않았습니다. 이전 전체 452개 통과를 이번 실행 결과로 다시 주장하지 않습니다.

### 해석과 다음 승인 경계

최소 A가 실제 서버에서 성공했으므로, 현재 계정·모델·Developer API/v1beta와
response_json_schema 조합이 **모든 경우에 실패한다는 가설은 배제할 수 있습니다.**
그러나 전체 DiagnosisDraft의 반복 HTTP 400 원인이나 스키마 B/C/D의 지원 여부는 여전히
확정할 수 없습니다. 이 결과는 운영 Agent의 최종 진단 성공을 증명하지도 않습니다.

다음으로는 동일한 합성 입력·공통 설정에서 기본 진단 스키마 B를 **별도 승인 후 1회** 검증하면
필드·배열 추가 시점에서 거부가 시작되는지 좁힐 수 있습니다. 비용이 발생할 수 있으며, 이번
승인에 B/C/D 또는 T01 전체 분석은 포함되지 않습니다. 추가 실험·T03/T05/T06·Step 5·배포·
Git add/commit/push 없이 A 결과 기록에서 중단했습니다.

## 실제 최소 재현: 스키마 B 서버 수락 검증

### 승인 범위와 사전 검증

2026-10-15 08:46 UTC(17:46 KST), 사용자 승인으로 B 스키마의 실제 Gemini 요청을 **1회만**
전송했습니다. 모델 `gemini-3.8-flash`, SDK `google-genai==2.31.0`, Developer API / `v1beta`를
유지했습니다. A 실험을 재실행하지 않았으며 C/D, T01 또는 다른 Agent 분석도 실행하지 않았습니다.

B는 필수 `summary:string`, `status:string`, `recommended_checks:string[]`로 구성된
기존 222바이트 fixture와 동일합니다. A 때의 무해한 합성 user 입력, system_instruction,
생성 옵션, MIME, timeout, 인증 주입과 전송 제어를 그대로 재사용하고 response_json_schema만
B로 교체했습니다. 오프라인에서 입력과 스키마 이외 설정을 직접 비교하여 일치함을 확인했습니다.
tools·tool_config·조사 이력은 없으며 response_schema도 설정하지 않았습니다.

Git 제외 실행기 `data/outputs/manual_validation/run_schema_b_once.py`는 A 실행기의 제어 코드를
모듈로 불러오되 A의 main을 실행하지 않습니다. B용 별도 잠금·결과 파일과 세 필드 검증만
적용합니다. A 실행기와 기존 A 결과·잠금은 변경하지 않았습니다.
사전 직렬화·유효/무효 필드 fixture·실제 SDK를 사용하는 Mock 전송 검증을 통과했고, 이 과정의
실제 외부 요청은 0회였습니다. Mock 결과는 아래 실제 실행 결과와 구분합니다.

### 실제 관측 결과

| 항목 | 결과 |
|---|---|
| 실제 Gemini HTTP 요청 | **1회** |
| HTTP 상태 / 오류 코드 | **200 / NOT APPLICABLE** |
| B 스키마 수락 | PASS |
| 실제 JSON 생성 / 엄격한 파싱 | PASS / PASS |
| summary 필수 필드 / 문자열 | PASS / PASS |
| status 필수 필드 / 문자열 | PASS / PASS |
| recommended_checks 필수 필드 / 문자열 배열 | PASS / PASS |
| 응답 종료 | STOP |
| 스키마 검증 | **PASS** |
| 입력 / 출력 / Thinking 토큰 | 35 / 27 / 279 |
| 합계 토큰 | 341 |
| 전송 시간 / 전체 실행 시간 | 3,902.910ms / 3,972.607ms |
| 비용 | NOT AVAILABLE |
| 자동 재시도 / 추가 실제 요청 | 0회 / 0회 |
| 전체 B 실험 | **PASS** |

실제 응답을 JSON object로 파싱한 뒤 필수 summary·status가 문자열이고 recommended_checks가
list이며 각 원소가 문자열인지 확인했습니다. B는 minItems가 없으므로 빈 배열도 계약상 허용하며,
additionalProperties 제한이 없으므로 임의로 더 강한 제약을 추가하지 않았습니다.
중복 키 및 NaN/Infinity는 허용하지 않았습니다. HTTP 200만으로 성공 처리한 결과가 아닙니다.

실패가 없어 안전한 오류 reason·필드 위반 경로·SDK 예외 유형은 **NOT APPLICABLE**입니다.
오류가 발생했을 때는 기존 allowlist 기반 수집 함수를 사용하도록 유지했습니다. API 키,
프롬프트·요청 본문·응답 문장·원시 오류·인증 헤더는 기록하지 않았습니다.

### 보호와 중단 상태

- 실제 전송 경계에서 승인된 모델·API 버전·설정·B 스키마·동일 합성 입력을 확인했습니다.
- 요청 최대 1회, SDK attempts=1, HTTPX retries=0, AFC·자동 continuation 비활성화,
  15초 제한과 별도 생성 전용 잠금을 유지했습니다.
- 운영 데이터 감사 훅의 접근 시도는 0회였습니다. 검사 레코드·JSONL·데이터셋·평가 정답·
  모델 파일을 읽거나 수정하지 않았습니다. 검사 도구·Function Calling도 실행하지 않았습니다.
- AgentService·운영 스키마·판정 정책·모델 및 임계값 34.1442는 변경하지 않았습니다.
- 변경 파일은 B 전용 Git 제외 실행기와 본 문서입니다. 이번 검증은 전용 오프라인 점검·Mock·
  실제 단일 요청이며 전체 pytest는 다시 실행하지 않았습니다. 기존 452개 통과는 이전 보고입니다.

### 해석과 다음 승인 경계

A뿐 아니라 B의 기본 문자열 필드와 문자열 배열 조합도 현재 서버에서 수락됐습니다.
따라서 이 단순 필드·배열 추가만으로 항상 400이 발생한다는 가설은 이번 결과와 맞지 않습니다.
전체 DiagnosisDraft의 HTTP 400 원인과 C/D의 수락 여부는 여전히 미확정입니다.

다음 원인 격리를 위해 C의 observed_facts 배열 내부 객체와 evidence_id 필드 구조를 동일한
입력·설정에서 1회 확인할 필요가 있습니다. **C는 별도 승인 후에만 실행**하며, 이번 승인에
포함되지 않습니다. C/D·A 재실행·T01 전체 분석·다른 시나리오·Step 5·배포 또는
Git add/commit/push 없이 B 결과 기록에서 중단했습니다.

## 실제 최소 재현: 스키마 C 서버 수락 검증

### 승인 범위와 사전 점검

2026-10-15 08:51 UTC(17:51 KST), 사용자 승인으로 Evidence 포함 C 스키마의 실제 Gemini
요청을 **1회만** 전송했습니다. 모델 `gemini-3.8-flash`, SDK `google-genai==2.31.0`,
Developer API / `v1beta`를 유지했습니다. AB 재실행, D 실험 또는 T01 전체 분석은 하지 않았습니다.

스키마는 `tests/test_agent_schema_isolation.py`의 기존 schema_cases 함수에서 C 항목만
AST literal로 읽어 그대로 사용했습니다. 새 스키마를 임의로 정의하거나 D를 실행하지 않았습니다.
C는 summary:string 및 observed_facts 배열로 구성되며, 배열 원소는 필수 evidence_id,
source_field, observed_value 문자열을 가진 object입니다. 크기는 기존과 같은 362바이트입니다.

Git 제외 실행기 `data/outputs/manual_validation/run_schema_c_once.py`를 추가했습니다.
AB 실행기를 제어 코드로만 불러오고 AB의 main 또는 실험 요청은 실행하지 않습니다.
B에서 사용한 user 입력과 system_instruction·모델·SDK·API 버전·생성/HTTP 옵션을 비교해
스키마 이외의 변경이 없음을 확인했습니다. response_mime_type=application/json과 단독
response_json_schema를 유지하며 tools·tool_config·Function Calling 이력은 없습니다.

사전 직렬화·유효/무효 중첩 fixture·빈 배열 허용·필수 필드 누락 거부와 실제 SDK를 사용하는
Mock 전송 검증을 통과했습니다. 최초 오프라인 실행기의 AST 접근에 문법 사용 오류가 있어
수정한 뒤 점검을 다시 완료했습니다. 이는 실행기 fixture 읽기 문제로, 운영 코드나 요청 설정의
호환성 문제는 아니었고 해당 과정의 실제 Gemini 요청은 0회였습니다.

### 실제 관측 결과

| 항목 | 실제 결과 |
|---|---|
| 실제 Gemini HTTP 요청 | **1회** |
| HTTP 상태 / 오류 코드 | **200 / NOT APPLICABLE** |
| C 스키마 수락 | PASS |
| 실제 JSON 생성 / 엄격한 파싱 | PASS / PASS |
| summary 필수 필드 / 문자열 | PASS / PASS |
| observed_facts 필수 필드 / 배열 | PASS / PASS |
| observed_facts 원소 수 | 1개 |
| 배열 원소 object 구조 | PASS, 실제 원소 1개 검증 |
| evidence_id / source_field / observed_value 필수 문자열 | 모두 PASS |
| 응답 종료 | STOP |
| 전체 C 스키마 구조 검증 | **PASS** |
| 입력 / 출력 / Thinking 토큰 | 35 / 38 / 282 |
| 합계 토큰 | 355 |
| 전송 시간 / 전체 실행 시간 | 3,951.061ms / 4,042.671ms |
| 비용 | NOT AVAILABLE |
| 자동 재시도 / 추가 실제 요청 | 0회 / 0회 |
| 전체 C 실험 | **PASS — 구조화 출력 수락·구조 검증에 한정** |

실제 응답을 JSON object로 파싱한 뒤 summary와 observed_facts, 배열 내부 object의 세 필수
문자열을 모두 검사했습니다. 빈 배열만 받아 구조 검증이 공허하게 통과한 경우가 아니라 실제
중첩 object 1개를 검증했습니다. C에 없는 minItems·식별자 패턴·additionalProperties 제한을
임의로 추가하지 않았습니다. 중복 키와 NaN/Infinity는 허용하지 않았습니다.

실패하지 않았으므로 안전한 reason·필드 위반 경로·SDK 예외 유형은 **NOT APPLICABLE**입니다.
API 키·원시 오류 메시지·프롬프트·요청 본문·응답 문장·인증 헤더는 결과에 기록하지 않았습니다.

### Evidence 참조와 의미 검증의 한계

공통 합성 입력에는 Evidence 레지스트리, 실제 evidence_id 또는 source_field 매핑을 제공하지
않았습니다. 그럼에도 응답에 observed_facts 원소 1개와 **입력에 제공되지 않은 Evidence 참조
1건**이 생성됐습니다. 식별자의 실제 문자열이나 생성 문장은 결과 문서에 복사하지 않습니다.

이번 PASS는 서버가 C 스키마를 수락하고 필수 자료형을 충족했다는 의미입니다. 생성된 참조가
실제 근거라는 의미는 아니며, 관측 주장 전체의 의미적 사실 일치를 확인한 결과도 아닙니다.
운영 Evidence·JSON Pointer·Tool Trace 기반 결정적 검증은 **NOT TESTED**입니다.
이번 결과를 운영 진단 품질 또는 최종 Agent 성공으로 보고하지 않습니다.

### 보호와 중단 상태

- 최대 실제 요청 1회, SDK attempts=1, HTTPX retries=0, AFC·자동 continuation 비활성화,
  15초 제한, 승인된 모델·API 버전·본문을 확인하는 전송 경계, C 전용 생성 잠금을 유지했습니다.
- 감사 훅의 운영 데이터 접근 시도는 **0회**입니다. 운영 JSONL·모델·이미지·평가 정답을
  읽거나 수정하지 않았고 Python 검사 조회 도구와 Function Calling도 실행하지 않았습니다.
- 운영 DiagnosisDraft·AgentService·판정 정책·고정 임계값 34.1442를 변경하지 않았습니다.
- 변경은 C 전용 Git 제외 실행기와 본 문서이며 기존 AB 결과·실행기·잠금과 실패 기록을 보존했습니다.
- 이번에는 전용 오프라인 점검·Mock·실제 C 요청을 검증했습니다. 전체 pytest는 재실행하지
  않았으며 기존 452개 통과는 이전 보고입니다.

### 다음 승인 경계

A/B에 이어 C의 배열 내부 객체·Evidence 문자열 필드 구조도 실제 서버에서 수락됐습니다.
이 단순 중첩 구조가 항상 400을 일으킨다는 가설은 이번 결과와 맞지 않습니다. 다만 원래
전체 DiagnosisDraft의 반복 HTTP 400 원인과 D의 서버 수락 여부는 여전히 **UNKNOWN**입니다.

다음 원인 격리를 위해 정의·참조·Union·Enum·배열 제한이 포함된 원래 D 스키마의 실제 수락을
별도 승인 후 1회 확인할 필요가 있습니다. 이번에는 D/T01/다른 시나리오/Step 5 또는
Git add/commit/push 없이 C 실험 기록에서 중단했습니다.

## 실제 최소 재현: 전체 DiagnosisDraft 스키마 D 서버 검증

### 승인 범위와 사전 점검

2026-10-15 08:57 UTC(17:57 KST), 사용자 승인으로 D 스키마 요청을 **1회만** 전송했습니다.
모델 `gemini-3.8-flash`, SDK `google-genai==2.31.0`, Developer API / `v1beta`를 유지했습니다.
ABC 재실행, T01/T03/T05/T06 전체 분석 또는 추가 스키마 실험은 하지 않았습니다.

전송 스키마는 운영과 동일한 `diagnosis_response_json_schema()`의 반환값을 그대로 사용했습니다.
이는 원래 DiagnosisDraft에서 기존 운영 투영 함수가 생성하는 2,846바이트 JSON Schema입니다.
원본 Pydantic 모델의 pattern/maxLength/default를 서버 검증에 남기는 기존 투영 정책도 변경하지
않았습니다. 새로 제약을 제거하거나 다른 스키마를 만들어 성공시키려 하지 않았습니다.
루트 필수 필드와 세 정의의 필수 필드·속성, Enum·Nullable·배열·참조를 유지하며 직렬화된
responseJsonSchema가 운영 생성 결과와 정확히 같은지 확인했습니다.

ABC의 공통 합성 입력·system_instruction·모델·SDK·API 버전·생성/HTTP 옵션과 비교해 스키마
이외 변경이 없음을 확인했습니다. application/json과 단독 response_json_schema를 사용했고
tools·tool_config·Function Calling 이력은 없습니다. 입력에는 실제 검사 데이터나 Evidence
레지스트리를 포함하지 않았습니다.

Git 제외 실행기 `data/outputs/manual_validation/run_schema_d_once.py`를 추가해 기존 단일 요청
제어 코드만 재사용했습니다. ABC의 main이나 요청은 실행하지 않았습니다. D 전용 생성 잠금으로
같은 승인 건의 재실행을 차단합니다. 사전 직렬화·합성 Pydantic fixture·Nullable/Scalar Union·
필수 필드 누락 거부·실제 SDK Mock·민감 값 없는 Pydantic 오류 경로 기록 시험을 통과했습니다.
이 사전 점검의 실제 외부 Gemini 요청은 0회였습니다.

### 실제 관측 결과

| 항목 | 실제 결과 |
|---|---|
| 실제 Gemini HTTP 요청 | **1회** |
| HTTP 상태 | **400** |
| Google API 표준 오류 코드 | INVALID_ARGUMENT |
| D 스키마 서버 수락 | FAIL |
| 모델의 구조화 JSON 생성 | 생성되지 않음 |
| 모델 JSON 파싱 | NOT TESTED, 도달하지 못함 |
| 전체 필수 필드·중첩 구조 검증 | NOT TESTED |
| 실제 응답 Enum·Nullable 검증 | NOT TESTED |
| 실제 응답 Pydantic 검증 | NOT TESTED |
| 운영 근거 검증 | NOT TESTED |
| 입력 / 출력 / Thinking 토큰 | NOT AVAILABLE / NOT AVAILABLE / NOT AVAILABLE |
| 합계 토큰 / 비용 | NOT AVAILABLE / NOT AVAILABLE |
| 전송 시간 / 전체 실행 시간 | 1,253.555ms / 1,320.235ms |
| 자동 재시도 / 추가 요청 | 0회 / 0회 |
| 전체 D 실험 | **FAIL** |

최종 진단이 생성되지 않았으므로 Pydantic 오류 필드가 발생한 경우가 아닙니다. 입력에 없는
관측 사실이나 Evidence ID 생성 여부도 실제 모델 응답이 없어 NOT TESTED입니다.
오프라인 Mock의 Pydantic 성공을 실제 서버 결과로 혼동하지 않습니다. 실패 요청의 사용량은
응답에서 확인되지 않았으며 0토큰 또는 무료라고 단정하지 않습니다.

### 안전한 실제 오류 정보

```json
{
  "http_status": 400,
  "google_api_code": "INVALID_ARGUMENT",
  "reason": "UNKNOWN",
  "field_violations": [],
  "request_stage": "STRUCTURED_OUTPUT",
  "sdk_exception_type": "ClientError"
}
```

기존 allowlist 수집 함수를 사용했으나 안전하게 보존할 수 있는 추가 reason이나 필드 위반
경로를 확보하지 못했습니다. 빈 field_violations는 거부 필드가 없다는 증거가 아니라,
수집 가능한 표준 필드 정보가 없다는 뜻입니다. 정확한 서버 거부 필드와 원인은 여전히
**UNKNOWN**입니다. 요청 본문·프롬프트·원시 오류·키·인증 헤더·서명 원문은 기록하지 않았습니다.

### 보호와 해석

- 실제 전송 경계에서 모델·v1beta·전체 D 스키마·입력·설정을 확인했습니다. 최대 1회,
  attempts=1, HTTPX retries=0, AFC·자동 continuation 비활성화와 15초 제한을 유지했습니다.
- 감사 훅의 운영 데이터 접근 시도는 **0회**였습니다. JSONL·모델·메타데이터·이미지·평가
  정답을 읽거나 수정하지 않았으며 검사 조회 도구나 Function Calling도 실행하지 않았습니다.
- 운영 DiagnosisDraft·AgentService·Function Calling·조기 종료·JSON Pointer 검증·판정 정책·
  고정 임계값 34.1442를 변경하지 않았습니다.
- 변경은 D 전용 Git 제외 실행기와 본 문서입니다. 기존 ABC 결과·잠금·과거 실패 기록을
  유지했고 이번에는 전체 pytest를 재실행하지 않았습니다. 이전 452개 통과는 이전 보고입니다.

동일한 합성 입력·공통 설정에서 A/B/C는 성공하고 운영 전체 D는 거부되는 차이를 확인했습니다.
이는 T01의 실제 검사 데이터나 Function Calling 이력 없이도 D 구성에서 400을 재현한 결과입니다.
다만 정의·참조·Union·Enum·배열 제한·스키마 규모 중 어떤 요소 또는 조합이 문제인지 특정하지
못했으므로 어느 하나를 확정 원인으로 지목하지 않습니다.

**T01 전체 Agent 재검증은 보류**하는 것이 타당합니다. D의 서버 거부 요소를 더 격리하는
별도 오프라인 분석이 먼저 필요하며, 추가 실제 호출에는 다시 승인이 필요합니다.
이번에는 실패 직후 추가 호출·즉석 스키마 변경·모델 전환 없이 중단했습니다.
ABC/T01/T03/T05/T06·Step 5·배포 또는 Git add/commit/push는 수행하지 않았습니다.

## D HTTP 400 원인 격리: 오프라인 부분 스키마 후보

### 범위와 현재 결론

이번 작업은 오프라인 후보 생성·직렬화·회귀 테스트만 수행했습니다. **실제 Gemini 요청은 0회**이고
ABCD 또는 T01/T03/T05/T06은 재실행하지 않았습니다. 기존 서버 결과 C PASS / D HTTP 400은
과거 관측으로 유지합니다. 정확한 거부 속성과 원인은 여전히 **UNKNOWN**이며 운영 스키마를
수정할 근거가 확정됐다고 판단하지 않았습니다.

분석 기준은 원본 Pydantic JSON 문서가 아니라 `response_json_schema`가 설치 SDK 2.31.0의
변환과 실제 `_build_request`를 거친 후 생성하는 `generationConfig.responseJsonSchema`입니다.
클라이언트나 저장소를 만들지 않고 해당 로컬 직렬화 경로만 호출합니다. `_url`은 SDK 요청
빌드에서 제거되는 내부 보조 필드이며 스키마나 실제 REST 본문에 포함되지 않습니다.

### 실제 전송 D의 구조

최상위 여섯 필드는 모두 required이며 최상위 nullable 필드는 없습니다.

| 필드 | 전송 자료형·제약 |
|---|---|
| inspection_id | string, title만 추가되어 있음 |
| overall_summary | string, Enum 5종 |
| observed_facts | ObservedFact 참조 배열, minItems=1 / maxItems=40 |
| possible_causes | CauseSelection 참조 배열, maxItems=4, 빈 배열 허용 |
| recommended_checks | CheckSelection 참조 배열, minItems=1 / maxItems=8 |
| limitations | Enum 6종 문자열 배열, maxItems=6, 빈 배열 허용 |

중첩 정의는 다음과 같습니다.

- ObservedFact: fact_id·evidence_id·source_tool·source_field·observed_value가 required입니다.
  source_tool은 도구 이름 Enum입니다. source_event는 선택 필드이며 string/null anyOf,
  observed_value는 **required이지만** boolean/integer/number/string/null anyOf입니다.
  required와 null 허용은 독립된 조건이므로 분할 과정에서 혼동하지 않았습니다.
- CauseSelection: cause_code Enum과 evidence_refs 문자열 배열이 required입니다.
- CheckSelection: check_code Enum과 evidence_refs 문자열 배열이 required입니다.
  두 evidence_refs 배열은 모두 minItems=1 / maxItems=10이며 사실의 fact_id를 참조하는 의미를 가집니다.

| 전송 스키마 지표 | C | D |
|---|---:|---:|
| UTF-8 바이트 | 362 | 2,846 |
| 참조 해석 후 객체·배열 최대 깊이 | 3 | 4 |
| 스키마 노드 | 7 | 33 |
| $defs / $ref | 0 / 0 | 3 / 3 |
| anyOf / null 타입 | 0 / 0 | 2 / 2 |
| Enum 노드 | 0 | 5 |
| 배열 노드 | 1 | 6 |
| additionalProperties=false 객체 | 0 | 4 |

D에는 minItems 4곳, maxItems 6곳, title 20곳이 있습니다. `const`, `oneOf`, `minLength`,
`maxLength`, `pattern`, `description`, `default`는 실제 전송 스키마에 **없습니다**.
따라서 원래 Pydantic의 pattern/maxLength/default를 이번 전송의 직접 거부 속성으로
지목하지 않습니다. 서버의 원래 엄격한 Pydantic 검증에는 관련 제약을 그대로 유지합니다.

### C에서 검증된 것과 D의 추가 요소

| 구분 | 내용 | 실제 서버 확인 수준 |
|---|---|---|
| C에서도 존재 | object, required, observed_facts 배열 내부 object, 문자열 evidence_id/source_field/observed_value | 과거 C에서 PASS |
| D의 필드 변경 | summary 대신 overall_summary, 검사 ID·원인·권고·한계 추가, fact_id/source_tool/source_event 추가 | 전체 조합에서만 HTTP 400 관측 |
| D의 인코딩 변경 | 직접 선언 객체를 $defs/$ref로 표현 | D의 개별 속성으로는 NOT TESTED |
| D의 타입 변경 | 문자열 값에서 Scalar Union으로 확대, optional-nullable source_event | 개별 조합 NOT TESTED |
| D의 제약 변경 | Enum, 배열 크기 제한, 객체의 추가 필드 금지, title | 개별 조합 NOT TESTED |

현재 사용한 JSON Schema 키는 공식 REST 지원 목록에 명시되어 있습니다. 참조도 모두 존재하는
정의를 가리키고 순환 또는 일반 형제 속성이 붙은 $ref는 없습니다. 하지만 속성의 개별 지원이
이 전체 조합의 서버 수락을 보증하지는 않습니다.
[REST JSON Schema 계약](https://ai.google.dev/api/generate-content#generationconfig)

공식 가이드는 큰 스키마와 깊은 중첩이 거부될 수 있음을 설명하지만 모델별 확정 한도를
제공하지 않습니다. 2,846바이트·깊이 4만으로 한도 초과라고 판단하지 않았습니다.
지원되는 제약의 상호작용, Scalar Union, 참조 처리, 객체 닫힘, 전체 규모를 **가설 후보**로만
유지합니다. 모델·SDK를 바꾸거나 검증을 완화하지 않았습니다.
[구조화 출력 제한](https://ai.google.dev/gemini-api/docs/generate-content/structured-output?hl=en)

### E1/E2 필드 분할과 의존성

문서상 필드 순서로 기계적으로 자르면 evidence_refs가 참조할 fact_id 구조와 분리됩니다.
이를 피하기 위해 D 필드 여섯 개를 의미 의존성에 따라 3개씩 분할했습니다.

- E1 그룹: inspection_id, overall_summary, limitations.
- E2 그룹: observed_facts, possible_causes, recommended_checks.

두 그룹의 교집합은 없으며 합집합은 D의 모든 최상위 필드와 정확히 같습니다. 각 그룹을 C에
병합하고 required도 합칩니다. E2의 observed_facts는 이름이 같으므로 **C 정의를 D 정의로 교체**하며
이를 중복 필드로 추가하지 않습니다. E2에는 fact_id와 cause/check evidence_refs가 함께 남고,
도달 가능한 세 $defs만 복사해 유효한 참조를 유지합니다.

분할의 공통 기준은 C이므로 C의 summary는 유지합니다. D의 루트 title과 루트
additionalProperties=false를 E1/E2에 공통으로 추가하지 않습니다. 두 후보가 성공하더라도
이 공통 메타데이터 차이 또는 여러 그룹의 결합 효과까지 검증한 것으로 해석해서는 안 됩니다.
실험용 후보는 운영 DiagnosisDraft와 동일한 보고서 계약이 아니므로 Agent에 연결하지 않습니다.

### 후보 구성과 실제 SDK 직렬화

| 후보 | C 대비 추가·교체 | 주요 제약 | 바이트 / 깊이 | SDK 직렬화 | 실제 서버 |
|---|---|---|---|---|---|
| E1 | inspection_id·overall_summary·limitations | summary Enum, limitations Enum·maxItems=6, 기존 title | 927 / 3 | PASS | NOT TESTED |
| E2 | observed_facts 교체, possible_causes·recommended_checks 추가 | 3 defs/refs, 2 Union, Enum, 배열 제한, 중첩 객체 닫힘 | 2,265 / 4 | PASS | NOT TESTED |
| E3 | overall_summary, fact.source_tool/source_event/observed_value | Enum + optional Nullable + required Scalar Union, 참조·배열 제한 없음 | 961 / 3 | PASS | NOT TESTED |
| E4 | 기존 observed_facts 배열만 변경 | minItems=1 / maxItems=40만 추가 | 393 / 3 | PASS | NOT TESTED |
| E5 | 기존 C의 동일 fact 객체를 정의로 이동 | 1 $defs/$ref만 추가, 타입·필드·제약 의미는 C와 동일 | 423 / 3 | PASS | NOT TESTED |
| E6 | 루트와 fact 객체 | additionalProperties=false만 추가 | 424 / 3 | PASS | NOT TESTED |

E6는 E1/E2 분할에서 놓칠 수 있는 객체 닫힘을 별도로 격리하기 위해 준비한 추가 후보입니다.
E5가 성공해도 D의 더 복잡한 참조 세 개가 성공했다고 단정할 수 없고, E3도 Enum과 두 Union을
묶은 후보이므로 실패하면 다시 나눠야 합니다. E4는 우선 C에 존재하는 배열의 제약만 다루며
모든 D 배열 제한을 한 번에 검증하지 않습니다. title 등 메타데이터 또는 다른 제약 결합은
필요하면 이후 별도 통제 후보로 나눕니다.

위 바이트는 json.dumps 기본 공백을 포함한 로컬 측정이며 서버의 복잡도 수치가 아닙니다.
직렬화 PASS는 로컬 SDK 요청 생성 성공만 뜻합니다. 이번 E 후보의 서버 수락은 모두 NOT TESTED입니다.
유틸리티의 C/D 분석 출력도 이번 오프라인 작업의 상태를 표시하며 과거 C PASS / D FAIL 기록을
덮어쓰거나 재판정하지 않습니다.

### 승인 이후의 최소 호출 전략 — 이번에는 실행하지 않음

**첫 후보로 E2 하나를 권장합니다.** C에 없던 참조·Union·Enum·배열 제약과 근거/선택 의존성이
집중된 절반이므로, 실패가 재현되면 전체 D보다 작은 범위에서 조사할 수 있습니다.
이는 원인 가능성에 대한 우선순위 판단이지 E2가 실패한다는 관측 사실은 아닙니다.

1. 동일 모델·SDK·v1beta·합성 입력·공통 설정에서 E2만 1회, 별도 승인 후 실행합니다.
2. HTTP 400이면 **그 자리에서 중단**하고 결과를 보고합니다. 이후 다시 승인받아
   observed_facts 단독과 cause/check 선택 필드를 나눕니다. 선택 필드를 시험할 때는
   먼저 검증된 fact_id 구조를 공통 기반으로 두어 의존성 누락을 새 오류 원인으로 만들지 않습니다.
3. E2가 성공하면 결과 보고 후 E1의 별도 승인을 요청합니다. E1이 실패하면 그 세 필드를
   1개/2개로 다시 나누는 계획을 수립합니다.
4. 실패한 하위 그룹에 따라 E3/E4/E5/E6 중 필요한 것만 개별 승인으로 시험합니다.
   모든 그룹이 성공해도 전체 D의 상호작용·공통 루트 정책이 남으므로 원인 해결을 선언하지 않습니다.

각 승인 실험은 최대 HTTP 1회, attempts=1, 무재시도와 기존 시간 제한을 유지합니다.
인증·429·5xx·timeout 등 공통 실패도 즉시 중단하며 다음 후보를 자동 호출하지 않습니다.
비용이 발생할 수 있고 금액·토큰 사용량은 사전 NOT AVAILABLE입니다. 전체 필요 요청 수는
결과와 추가 승인에 따라 달라지므로 정해진 수로 보증하지 않습니다.

### 최소 수정안의 경계

아직 운영 수정안은 **적용하지 않았습니다**. 검증 가능한 준비 상태는 실험 전용 후보뿐입니다.
향후 참조가 확정 원인이면 전송 표현만 inline으로 바꾸는 동등 변환을 우선 검토할 수 있습니다.
배열 제약 또는 추가 속성 금지가 확정 원인이면 생성용 투영만 최소 조정하는 방안을 검토하되
서버의 원래 Pydantic·extra=forbid·배열 제한·결정적 근거 검증은 유지해야 합니다.
이들은 조건부 검토안이며 확정 원인 없는 변경 승인이나 자동 적용을 의미하지 않습니다.

### 변경 파일과 실제 테스트

- 신규 `scripts/agent_schema_candidates.py`: 운영 경로와 분리된 순수 오프라인 후보 생성·
  SDK 요청 빌드·지원 키/required/참조/배열 상한/깊이 점검. 클라이언트·키·저장소·전송 호출 없음.
- 신규 `tests/test_agent_schema_candidates.py`: 34개. C/D 보존, 분할 중복·누락, 참조 폐쇄,
  required 유효성, 후보 독립성, 각 속성의 단독 변경, 합성 witness/무효 데이터 점검,
  원래 Pydantic 거부 유지, 실제 네트워크 금지 검증.
- 본 문서: 기존 실험 결과를 유지한 채 이번 분석과 승인 계획 추가.

유효성 점검은 이번 후보가 사용하는 부분집합에 대한 정적 검사와 테스트 전용 합성 witness
검사입니다. 범용 JSON Schema 인증이나 Gemini 서버의 검증기를 구현했다고 주장하지 않습니다.
모든 후보는 실제 SDK 직렬화 결과에서도 같은 필드·참조·제약을 유지했습니다.

| 검증 | 결과 |
|---|---|
| 신규 테스트 | 34 passed |
| 전체 회귀 | **486 passed, 3 warnings**, 실패·건너뜀 0 |
| 기존 기준 | 기존 452개 유지 |
| 전체 명령 | `python -m pytest tests -q -p no:cacheprovider`에 임시 경로·간결 출력 옵션 적용 |
| 분석 명령 | `python -m scripts.agent_schema_candidates` — 로컬 메타데이터만 출력 |
| pip check / 문법·공백 검사 | PASS / PASS |
| 실제 Gemini 요청 / SDK 전송 시도 | **0회 / 0회** |
| 운영 JSONL·체크포인트·모델 메타데이터 | 전후 SHA256 동일 |
| 운영 schemas/service/prompts/tools/api 소스 | 전후 SHA256 동일 |

전체 테스트는 Conda vision-insight, 임시 JSONL·출력 경로 및 공개 fixture 복사본을 사용했고
실제 SDK request/async_request 경로를 차단했습니다. 기존 Function Calling·정상 조기 종료·
Evidence/JSON Pointer 비교·HTTP 실패 매핑을 포함한 회귀를 유지했습니다. 모델·SDK·임계값
34.1442는 변경하지 않았고 평가 전용 정답을 별도로 조회하지 않았습니다.

실제 서버 수락과 거부 속성은 오프라인 테스트만으로 확정할 수 없습니다. 이번 작업은 이
준비와 보고에서 종료하며 E2 또는 다른 실제 실험은 별도의 사용자 승인을 기다립니다.

## 실제 부분 스키마 검증: E2 관측 사실·원인·권고 그룹

### 승인 범위와 사전 점검

2026-10-15 09:40 UTC(18:40 KST), 사용자 승인으로 E2 요청을 **1회만** 전송했습니다.
모델 `gemini-3.8-flash`, SDK `google-genai==2.31.0`, Developer API / `v1beta`를 유지했습니다.
다른 E 후보·ABCD 재실행·T01 또는 다른 운영 시나리오 분석은 하지 않았습니다.

`scripts/agent_schema_candidates.py`의 `build_candidates()["E2"]`를 그대로 사용했습니다.
E2의 루트 필드는 C의 summary 및 D에서 가져온 observed_facts·possible_causes·recommended_checks이며,
모두 required입니다. 세 참조 정의와 fact_id/evidence_refs 구조를 유지한 2,265바이트 스키마입니다.
원래 C·D 생성 결과와 운영 DiagnosisDraft가 변경되지 않았는지 오프라인으로 확인했습니다.

이전 실험과 동일한 합성 user 입력·system_instruction·모델·SDK·API 버전·생성/전송 옵션을
사용하고 response_json_schema만 E2로 바꿨습니다. MIME은 application/json이며 response_schema,
tools·tool_config·Function Calling 이력은 없습니다. SDK attempts=1, HTTPX retries=0,
자동 continuation/AFC 비활성화, 15초 제한과 최대 1회 전송 차단을 유지했습니다.

전용 Git 제외 실행기 `data/outputs/manual_validation/run_schema_e2_once.py`를 추가했습니다.
원래 단일 요청 제어 코드를 모듈로만 재사용해 A의 main이나 요청은 실행하지 않았습니다.
E2 전용 생성 잠금으로 재실행을 막습니다. SDK 직렬화·필수/참조 유효성·자료형·Enum·추가 필드
거부와 안전한 로컬 오류 기록을 오프라인 fixture로 확인했습니다. 실제 SDK Mock의 성공 결과는
아래 실제 실패와 별개이며, 사전 외부 Gemini 요청은 0회였습니다.

### 실제 관측 결과

| 항목 | 실제 결과 |
|---|---|
| 실제 Gemini HTTP 요청 | **1회** |
| HTTP 상태 / 표준 오류 코드 | **400 / INVALID_ARGUMENT** |
| E2 서버 수락 | FAIL |
| 모델의 구조화 JSON 생성 | 생성되지 않음 |
| JSON 파싱 | NOT TESTED, 도달하지 못함 |
| 필수 필드·중첩 구조 검증 | NOT TESTED |
| fact_id·evidence_refs 자료형 검증 | NOT TESTED |
| 운영 근거 일치 검증 | NOT TESTED |
| 입력 / 출력 / Thinking 토큰 | NOT AVAILABLE / NOT AVAILABLE / NOT AVAILABLE |
| 전체 토큰 / 비용 | NOT AVAILABLE / NOT AVAILABLE |
| 전송 시간 / 전체 실행 시간 | 1,108.424ms / 1,166.123ms |
| 자동 재시도 / 추가 요청 | 0회 / 0회 |
| 전체 E2 실험 | **FAIL** |

JSON 응답이 없으므로 초기 메타데이터의 필드 존재 false를 실제 모델의 필드 누락으로
해석하지 않습니다. 파싱·Enum/Nullable·배열/객체 제약 및 fact_id/evidence_refs 검증은
도달하지 못했습니다. 로컬 검증기는 실제 전송 스키마의 타입·Enum·Union·참조·required·
배열 제한·중첩 객체 닫힘을 검사하도록 준비했지만, Mock 시험을 실제 서버 검증 성공으로
보고하지 않습니다. 실패 요청의 사용량은 확인되지 않았으며 0토큰 또는 무료로 단정하지 않습니다.

### 실제 안전한 오류 정보

```json
{
  "http_status": 400,
  "google_api_code": "INVALID_ARGUMENT",
  "reason": "UNKNOWN",
  "field_violations": [],
  "request_stage": "STRUCTURED_OUTPUT",
  "sdk_exception_type": "ClientError"
}
```

기존 안전 수집 함수로 추가 reason이나 필드 경로를 확보하지 못했습니다. 정확한 거부 속성은
여전히 UNKNOWN입니다. 요청 본문·프롬프트·원시 오류 메시지·키·인증 헤더·서명 원문은
기록하지 않았습니다.

### 보호 상태와 다음 격리 후보

- 운영 데이터 감사 훅의 접근 시도는 **0회**입니다. JSONL·모델·메타데이터·원본 이미지·
  평가 정답을 읽거나 수정하지 않았고 Python 검사 조회 도구와 Function Calling도 실행하지 않았습니다.
- 운영 AgentService·DiagnosisDraft·판정 정책·고정 임계값 34.1442를 변경하지 않았습니다.
- 변경은 E2 전용 Git 제외 실행기와 본 문서입니다. 후보 생성 유틸리티·기존 실험 결과·잠금은
  유지했습니다. 이번에는 전용 사전 점검과 Mock을 수행했으며 전체 pytest는 다시 실행하지
  않았습니다. 기존 486개 통과는 이전 오프라인 작업의 결과입니다.

D의 검사 ID·최상위 요약 Enum·한계 필드 그룹과 루트 객체 닫힘 없이도 E2에서 HTTP 400을
재현했습니다. 따라서 관측 사실·선택 객체 그룹의 제약과 조합을 더 좁혀 조사할 수 있습니다.
그러나 제외한 필드 그룹이 항상 안전하거나 참조·Union 중 하나가 확정 원인이라고 판단하지 않습니다.

**다음 실제 후보로는 E5를 권장합니다.** 이미 성공한 C 객체의 필드·자료형을 그대로 두고
$defs/$ref 표현만 추가한 가장 작은 대비 실험이므로 참조 인코딩의 독립 영향을 먼저 확인할 수
있습니다. E5가 성공해도 복잡한 D/E2의 세 참조와 제약 결합까지 검증된 것은 아닙니다.
이후에는 필요에 따라 observed_facts 단독과 선택 객체를 더 분할하고 Enum/Union·배열 제한을
각각 격리하는 별도 오프라인 계획을 세워야 합니다.

E5 또는 다른 후보는 이번에 실행하지 않았으며 실제 검증은 **별도 승인 후 최대 1회**로
진행해야 합니다. 실패 직후 추가 호출·즉석 수정·모델 전환 없이 중단했습니다.
E1/E3/E4/E5/E6·ABCD·T01/T03/T05/T06·Step 5·배포 또는 Git add/commit/push는 수행하지 않았습니다.

## E2 세부 격리 및 단순 JSON 보고서 대안: 오프라인 검증

이번 작업은 실제 Gemini 요청 없이 후보 준비·설계·Mock 검증만 수행했습니다.
이전 C 성공, D/E2 HTTP 400 실패 기록을 보존합니다. 정확한 서버 거부 필드와 reason은
여전히 **UNKNOWN**입니다. 운영 AgentService·DiagnosisDraft·Function Calling·조기 종료는 변경하지 않았습니다.

### E2 분할 기준과 실제 SDK 직렬화 결과

`scripts/agent_schema_candidates.py`의 `build_e2_partitions()`가 기존 E2의 복사본에서 생성합니다.
`build_e2_subcandidate(fields)`로 필요한 필드만 더 분할할 수 있으며 자동으로 후보를 늘리거나 요청하지 않습니다.

| 후보 | 최상위 필수 필드 | 바이트 / 컨테이너 깊이 | 정의 / 참조 | Union / Enum / null | 로컬 SDK / 실서버 |
|---|---|---:|---:|---:|---|
| C | summary, observed_facts | 362 / 3 | 0 / 0 | 0 / 0 / 0 | 성공 / 이전 PASS |
| E2 | summary, observed_facts, possible_causes, recommended_checks | 2,265 / 4 | 3 / 3 | 2 / 3 / 2 | 성공 / 이전 FAIL |
| E2-A | summary, observed_facts | 1,042 / 3 | 1 / 1 | 2 / 1 / 2 | 성공 / NOT TESTED |
| E2-B | summary, observed_facts, possible_causes, recommended_checks | 1,558 / 4 | 2 / 2 | 0 / 2 / 0 | 성공 / NOT TESTED |
| E5 | summary, observed_facts | 423 / 3 | 1 / 1 | 0 / 0 / 0 | 성공 / NOT TESTED |

바이트 수는 SDK 변환 후 `generationConfig.responseJsonSchema`의 compact UTF-8 JSON 기준입니다.
깊이는 참조를 해석한 객체·배열 컨테이너 기준이며 `$defs` 저장 위치 자체를 추가 중첩으로 계산하지 않습니다.

- E2-A는 원래 ObservedFact 전체를 유지합니다. fact_id, evidence_id, source_tool, source_field,
  source_event, observed_value의 기존 필수 여부·자료형·Nullable/Scalar Union을 보존합니다.
  source_tool Enum, ObservedFact의 `additionalProperties=false`, observed_facts의 1~40개 제한도 동일합니다.
- E2-B는 CauseSelection/CheckSelection과 evidence_refs 배열을 그대로 유지합니다.
  참조 대상이 사라지지 않도록 observed_facts에는 원래 fact_id 문자열만 필수인 최소 객체를 둡니다.
  관측 배열의 기존 1~40개 제한을 유지하고, 축소 객체에 새로운 추가 필드 금지 조건을 붙이지 않습니다.
  원인 최대 4개, 권고 1~8개, 각 evidence_refs 1~10개와 기존 코드 Enum·객체 제한을 유지합니다.
- `evidence_refs`는 fact_id를 가리키는 문자열입니다. JSON Schema만으로 실제 외래 키 일치나
  관측 사실의 진실성을 입증할 수 없으므로 운영 Python 근거 검증은 별도로 유지합니다.
- 분석 대상 필드 그룹은 A의 관측 사실과 B의 원인·권고입니다. summary 및 의존성용 fact_id는 공유합니다.
  A의 전체 관측 구조와 B의 원인·권고, required, 필요한 정의를 합쳐 원본 E2를 정확히 재구성하는 테스트가 통과했습니다.
  **E2-A와 E2-B가 각각 서버에서 성공하더라도 결합한 E2의 성공은 보장되지 않습니다.**
- 원본 C/D/E2와 운영 Pydantic 스키마 불변, 잘못된 참조·필수 필드·미검토 속성 거부를 검증했습니다.

### C와 E2의 차이 및 원인 후보

C는 문자열 중심의 인라인 관측 객체입니다. E2는 provenance 도구 Enum, source_event Nullable,
observed_value의 엄격한 scalar Union/Nullable, 원인·권고 코드 Enum, 참조 배열 및 배열 길이 제한,
닫힌 중첩 객체와 세 개의 `$defs/$ref`를 함께 추가합니다. 크기와 최대 깊이도 증가합니다.
현재 전송 스키마에는 const, oneOf, pattern, maxLength, default, description이 없습니다.

[공식 REST GenerationConfig 계약](https://ai.google.dev/api/generate-content#generationconfig)과
[공식 구조화 출력 안내](https://ai.google.dev/gemini-api/docs/structured-output)를 대조했을 때,
현재 사용된 `$defs`, `$ref`, anyOf, enum, additionalProperties, minItems/maxItems 등의 존재만으로
명백한 계약 위반이라고 판정할 근거는 확인하지 못했습니다. 설치된 SDK 2.31.0도 직렬화합니다.
지원 키워드의 조합·복잡도 또는 모델별 제한은 가능한 가설이며 정확한 한계와 거부 원인은 UNKNOWN입니다.
E5는 참조 표현만 바꾸는 더 작은 대비 실험이지만, 실제 E2의 Union·Enum·배열 제약 결합을 재현하지는 않습니다.

### 운영 경로 밖의 단순 JSON + Python 검증 대안

`scripts/agent_simple_report_prototype.py`는 네트워크·저장소 생성·운영 전환 기능이 없는 실험용 변환기입니다.
Gemini 출력 스키마는 다음 다섯 필수 필드로 한정합니다.

```json
{
  "overall_summary": "NORMAL_MODEL_RESULT",
  "observed_fact_refs": ["K0001", "K0002"],
  "possible_causes": [],
  "recommended_checks": ["CONTINUE_MONITORING:K0002"],
  "limitations": []
}
```

위 예시는 문법 설명일 뿐이며 완전한 검사 근거를 갖춘 성공 응답은 아닙니다.
K 토큰은 해당 요청의 서버 카탈로그에 실제로 존재해야 합니다. 필수 핵심 사실을 빠뜨리면 실패합니다.
모든 원소가 문자열인 네 배열과 summary 문자열만 전송 스키마로 선언합니다.
전송 스키마는 **454바이트, 깊이 2**, 참조·Enum·Union 없이 로컬 SDK 직렬화가 성공했습니다.
이 새 스키마의 **실제 서버 수락 여부는 NOT TESTED**입니다. 이전 B 성공을 이 스키마의 성공으로 간주하지 않습니다.

변환 및 검증 경계:

1. 실제 실행에 성공한 Trace와 연결된 서버 Evidence에서만 허용된 scalar 필드를 추출합니다.
   경로·임의 로그 메시지·추가 metrics·이미지/제품 ID 등은 카탈로그 대상에서 구조적으로 제외합니다.
   K 토큰은 evidence_id, source_tool, JSON Pointer, 실제 값, 관련 이벤트를 가리킵니다.
2. 모델은 관측값을 새로 쓰는 대신 검증 가능한 사실 토큰을 선택합니다.
   원인·권고는 `CODE:K0001,K0002` 형식으로 선택한 사실에 연결합니다. 원인 코드는 가설입니다.
   즉 모델의 기여는 근거 선택·요약 코드·가설·권고 선택이며, 실제 관측값은 서버가 관측한 데이터입니다.
3. `SimpleReport`는 추가 필드·잘못된 자료형·크기 초과를 거부합니다. 중복 JSON 키와 NaN도 거부합니다.
   존재하지 않는 토큰, 선택하지 않은 사실 참조, 중복 토큰, 임의 문장, 잘못된 코드도 정상화하지 않고 거부합니다.
4. 서버 카탈로그가 실제 값·포인터·검사 소유권·실행 Trace와 그대로 일치하는지 다시 비교합니다.
   선택된 토큰을 F 순번과 원래 provenance로 변환하고 기존 `DiagnosisDraft`를 그대로 검증합니다.
   검사 ID는 요청 상태에서 가져오고, 누락된 핵심 사실이나 당시 기록되지 않은 지표를 자동 보충하지 않습니다.
5. 기존 `AgentService._verify_report()`를 그대로 호출하여 여섯 핵심 필드, JSON Pointer의 값과 자료형,
   이벤트, 가설·권고의 근거, summary와 저장 판정의 일치 여부를 검증합니다.
   최종 검사 판정·tools_used·Trace·사용량은 서버 자료가 권위이며 모델이 작성하지 않습니다.
   가설·권고·요약의 최종 문장은 기존 서버 표현을 사용합니다.

따라서 외부 전송 스키마는 단순해지지만 서버 검증이 느슨해지지 않습니다.
구형 레코드의 실제 null도 그대로 비교하며 가짜 Evidence ID, 값 변조, 다른 검사 카탈로그,
실행되지 않은 Trace, 근거 없는 원인은 실패합니다. 부족한 필수 사실을 선택한 경우도 실패합니다.
오류는 FINAL_JSON_INVALID, RESPONSE_SCHEMA_INVALID, EVIDENCE_MISMATCH, INSUFFICIENT_EVIDENCE,
CONTEXT_TOO_LARGE 등 기존 안전한 코드로 처리하고 예외 원문을 반환하지 않습니다.
카탈로그 기본 상한은 512개/65,536바이트, 응답은 65,536바이트이며 초과 시 임의 축약 없이 실패합니다.
운영 도입 시에는 별도 승인 후 최종 출력 생성·변환 경계와 해당 테스트만 연결해야 합니다.
Function Calling 조사와 라우터·기존 API 응답 스키마는 재작성할 필요가 없습니다.

### 두 방식 비교와 추천

| 기준 | A: 전체 DiagnosisDraft 문제 격리 | B: 단순 JSON + 엄격한 Python 검증 |
|---|---|---|
| 구현 난이도 | 변경은 작지만 서버 원인 격리에 불확실성 | 카탈로그·변환 계층이 추가됨 |
| 기존 코드 변경 | 후보 생성만 유지, 원인 확정 후 최소 변경 | 승인 후 최종 생성/변환 경계만 연결 |
| Gemini 호환성 | 전체 D/E2는 실제 실패 | 단순해지지만 새 스키마는 서버 미검증 |
| Function Calling | 유지 | 유지; 기존 실제 도구 선택·실행과 분리하지 않음 |
| 근거 신뢰성 | 기존 Pydantic·결정적 검증 | 동일 검증 + 카탈로그 소유권/값 비교 |
| 출력 안정성 | 외부 스키마와 서버 모델이 가까움 | 외부는 단순; 토큰/코드 프로토콜 관리 필요 |
| 요청 수 | 정상 경로 예상 약 2회, 모델 행동에 따라 변동 | 변환은 로컬이므로 추가 요청 불필요, 같은 예상 경로 |
| 추정 비용 | 실패 격리 실험 비용 발생 가능 | 출력은 짧아질 수 있으나 카탈로그 입력 증가 가능 |
| 유지보수 | 서버/모델 스키마 제약과 결합 | 변환기·카탈로그 버전 및 private verifier 결합 관리 필요 |
| 포트폴리오 적합성 | 엄격한 native 구조화 출력 사례 | 실제 조사·근거 검증 중심의 Agent 목적에 적합 |

현재 운영은 전환하지 않습니다. **바로 다음 실험은 E2-A 한 건**을 추천합니다.
최근 요구의 분할 기준에 따라 실패 범위를 실제 관측 구조와 선택 객체 그룹으로 좁힐 수 있기 때문입니다.
이전 문서의 E5 추천도 참조 인코딩만 확인하는 유효한 대안이지만 이번에는 관측 그룹을 우선합니다.
E2-A가 실패하면 관측 그룹 내부를 오프라인에서 다시 분할하고, 성공하면 E2-B에 대한 별도 승인을 요청합니다.
어느 결과도 단독 속성의 인과관계나 결합 스키마 성공을 확정하지 않습니다.

원인 규명이 장기화될 경우의 구현 대안으로는 **B를 추천**합니다. 이미 검증된 실제 Function Calling과
Python 근거 검증을 보존하면서 모델이 생성할 계약을 줄일 수 있습니다. 다만 운영 전환은 승인 후에만 가능합니다.
E2-A 검증은 최대 1 HTTP 요청·자동 재시도 없음으로 계획하며 모델 사용량에 따라 비용이 발생합니다.
이후 E2-B 또는 더 작은 후보는 결과에 따라 각각 별도 승인해야 하므로 전체 격리 횟수는 확정할 수 없습니다.
B를 선택하면 별도의 합성 스키마 1회 검증과 별도 승인된 T01 분석 1회가 필요합니다.
T01 내부 정상 예상 경로는 약 2 HTTP 요청이나 고정 보장하지 않습니다. 이번에는 어느 요청도 실행하지 않았습니다.
실제 토큰·비용은 NOT AVAILABLE이며, 스키마 축소만으로 비용 감소를 보장하지 않습니다.

### 변경 파일 및 실제 테스트 결과

- 수정: `scripts/agent_schema_candidates.py`, 본 문서.
- 생성: `scripts/agent_simple_report_prototype.py`, `tests/test_agent_e2_partitions.py`, `tests/test_agent_simple_report.py`.
- 신규 두 파일: `python -m pytest tests/test_agent_e2_partitions.py tests/test_agent_simple_report.py -q -p no:cacheprovider`
  실행 결과 **50 passed**.
- 전체: Conda vision-insight Python으로 `pytest.main(['tests', '-q', '-p', 'no:cacheprovider', ...])` 실행,
  **536 passed, 3 warnings in 19.14s**. 기존 486개와 신규 50개가 모두 통과했습니다.
  저장 경로는 임시 디렉터리로 격리하고 공개 테스트 fixture만 복사했습니다.
  SDK sync/async 전송 진입점을 차단한 상태에서 **REAL_SDK_TRANSPORT_ATTEMPTS 0**을 확인했습니다.
- Function Calling, 정상 조기 종료, 기존 근거 검증, 400의 안전한 오류 처리 등 기존 회귀 테스트도 포함했습니다.
- `python -m pip check`: **No broken requirements found**.
- `git diff --check`와 신규 미추적 파일을 포함한 변경 파일 별도 공백 검사: 오류 0건.
- 보호 대상 운영 JSONL 두 파일·체크포인트·메타데이터 및 service/schemas/prompts/tools/api/diagnostics의
  전후 SHA256이 모두 동일했습니다. 모델 임계값 34.1442와 운영 정책을 변경하지 않았습니다.
- API 키·평가 정답·원본 경로·서명 원문을 출력하지 않았습니다. 실제 Gemini 요청은 **0회**입니다.

실서버 호환성, 새 토큰 프로토콜에 대한 실제 모델의 준수율, 최종 T01 진단 성공과 비용은 아직 미검증입니다.
오프라인 결과는 서버 수락 PASS나 운영 전환 승인으로 해석하지 않습니다. 다음 실험은 별도 승인을 기다립니다.

## 실제 단순 JSON 진단 스키마: 합성 Evidence 단일 실험

사용자가 승인한 단순 보고서 요청 한 건만 실행했습니다. 운영 T01 분석, 다른 스키마·시나리오,
Function Calling 또는 운영 전환은 수행하지 않았습니다. 기존 실패 기록은 보존합니다.

### 요청 범위 및 사전 점검

- 모델 `gemini-3.8-flash`, SDK `google-genai==2.31.0`, Developer API / `v1beta`를 유지했습니다.
- 기존 `simple_output_schema()` 그대로 454바이트·깊이 2, 다섯 필수 필드를 사용했습니다.
- `response_mime_type=application/json`, `response_json_schema`만 지정했습니다.
  tools/tool_config, Function Calling 이력은 없으며 하나의 user Content에 합성 근거만 전달했습니다.
- 실제 운영 기록 대신 fake 저장소의 정상 합성 레코드로 기존 조회 도구를 실행하여 서버 Evidence와
  카탈로그를 구성했습니다. 이 로컬 실행은 Gemini가 선택한 Function Call이 아닙니다.
  생성된 카탈로그 토큰만 선택하도록 지시하고 여섯 핵심 상태와 추천 코드의 의미를 설명했습니다.
- 서버가 합성 관측값·포인터·토큰을 결정했습니다. 모델은 사실 토큰과 요약·권고 코드를 선택하며
  임의의 관측값·검사 판정·Trace를 생성하도록 하지 않았습니다.
- SDK 자동 재시도 attempts=1, HTTP transport retries=0, 모델 요청 제한 15초를 적용했습니다.
  전송 가드는 정확한 모델 URL·설정·스키마·Content를 확인하고 두 번째 HTTP 전송을 차단합니다.
  배타적 실행 lock으로 같은 승인 회차를 다시 실행하지 못하게 했습니다.
- 실행 전 관련 오프라인 테스트 **50 passed in 1.01s**.
  전용 `--offline-only` 점검도 PASS: SDK 전송 0회, 키 존재 true(값 미출력), 운영 데이터 접근 시도 0회.
  가짜 토큰, 핵심 사실 누락, summary/판정 충돌이 거부됨을 다시 확인했습니다.

### 실제 관측 결과

| 항목 | 결과 |
|---|---|
| 실행 시각 | 2026-10-15T10:00:53.541210+00:00 |
| 실제 Gemini HTTP 요청 | **1회** |
| HTTP 응답 | **200** |
| 단순 JSON 스키마 수락 | PASS |
| JSON 생성 / 엄격한 파싱 | PASS / PASS |
| SimpleReport 필수 필드·자료형 검증 | PASS |
| 입력 카탈로그 토큰만 참조 | PASS |
| 생성된 관측 사실 수 | 6개 |
| 기존 DiagnosisDraft 변환 | PASS |
| 기존 Pydantic 검증 | PASS |
| Evidence ID / JSON Pointer / 실제 값 / Trace 연결 검증 | PASS |
| 여섯 핵심 상태의 근거 충족 | PASS |
| 합성 검사 판정 유지 | OK / OK / ALL_CHECKS_PASSED |
| 검증된 결과의 analysis_status | COMPLETED |
| A: Gemini 서버 호환성 | **PASS** |
| B: 변환 및 근거 검증 | **PASS** |
| 전체 합성 실험 | **PASS** |
| 입력 토큰 | 1,509 |
| 출력 토큰 | 97 |
| Thinking 토큰 | 541 |
| 총 토큰 | 2,147 |
| HTTP 전송 시간 | 6,285.259ms |
| 전체 실험 시간 | 6,347.872ms |
| 안전한 오류 정보 | 오류 없음; HTTP 200, 오류 코드·reason·필드 경로 해당 없음 |
| 자동 재시도 / 추가 호출 | 0회 / 0회 |
| 운영 데이터 접근 시도 | 0회 |
| 실제 비용 | NOT AVAILABLE |
| 실제 운영 T01 검증 | **NOT TESTED** |

`analysis_status=COMPLETED`는 합성 자료에 대한 기존 Python 검증 결과입니다.
이 실험은 분석 HTTP 엔드포인트를 호출하지 않았으므로 FastAPI의 HTTP 200 또는 운영 T01 성공을 뜻하지 않습니다.
관측 사실을 모델이 스스로 새로 측정한 것도 아니며 서버 자료에서 선택한 토큰을 실제 근거로 복원한 결과입니다.

### 변경 및 보호 상태

- 추가한 Git 제외 수동 실행기: `data/outputs/manual_validation/run_simple_report_once.py`.
  기존 단일 요청 제어를 재사용하고 단순 출력 프로토타입의 변환·검증을 연결했습니다.
- 실행 lock 및 원문 없는 요약 결과 JSON도 같은 Git 제외 수동 실험 디렉터리에만 저장했습니다.
  원시 응답·프롬프트·키·인증 헤더·서명은 저장하거나 출력하지 않았습니다.
- 운영 JSONL 두 파일, 체크포인트, 모델 메타데이터, service/schemas/prompts와 단순 출력 프로토타입의
  전후 SHA256이 모두 동일했습니다. 임계값 34.1442 및 기존 검사 정책은 유지했습니다.
- 이번 회차에는 관련 50개 테스트와 전용 사전 점검을 실행했습니다. 전체 pytest는 재실행하지 않았습니다.
  전체 536개 통과는 직전 오프라인 회차 결과입니다.

### 결론 및 다음 승인 범위

이번 한 건에서 단순 스키마의 서버 수락과 합성 Evidence 기반 엄격한 변환·근거 검증이 함께 성공했습니다.
이는 모든 입력에서의 준수율이나 D/E2 HTTP 400의 정확한 원인을 입증하지 않습니다.
다양한 상태·오류·부분 근거에 대한 실제 모델 동작, 운영 T01 및 FastAPI 연결은 아직 미검증입니다.

운영 전환을 위해서는 별도 승인을 받은 뒤 최종 생성 경계에만 카탈로그·변환기를 연결하고,
기존 시간·호출·컨텍스트 상한 및 안전한 HTTP 오류 매핑을 유지하며 관련·전체 회귀 테스트를 실행해야 합니다.
그 후 운영 T01 실제 재검증은 추가 승인을 받아야 합니다. 이번에는 전환·추가 API 실험·Step 5 또는
Git add/commit/push 없이 중단했습니다.

## 단순 JSON 보고서 운영 연결: 오프라인 회귀 검증 (2026-10-16)

### 시작 상태 및 이전 실험 확인

작업 시작 시 `git status --short` 출력은 비어 있었고 `git diff --check`도 통과했습니다.
최근 커밋은 `1069fe0` (2026-10-15, Gemini Function Calling 및 AI 진단 기능 구현),
이전 두 커밋은 `4ef84b8`, `ad81350`입니다. 어제 합성 Evidence 단일 실험 결과와 프로토타입은
최신 커밋에 실제 포함되어 있었습니다. 이번 작업에서 새 Git 커밋은 만들지 않았습니다.

이전 문서의 Function Calling·Python 조회·정상 조기 종료 성공, D/E2 HTTP 400,
E2-A/E2-B 오프라인 직렬화 성공 기록을 확인하고 그대로 보존했습니다.
단순 JSON 합성 실험은 HTTP 1회/200, 토큰 2,147개, JSON·변환·Pydantic·결정적 검증 PASS였습니다.
이 결과는 합성 Evidence 기준이며 운영 T01 End-to-End 성공을 의미하지 않습니다.
모델 `gemini-3.8-flash` 및 SDK `google-genai==2.31.0`을 변경하지 않았습니다.

### 운영 연결 범위 및 변경 파일

- 생성: `backend/agent/reporting.py` — 검증된 카탈로그·단순 보고서 스키마·변환 로직의 공통 구현.
- 생성: `backend/agent/errors.py` — 오케스트레이션과 변환기가 공유하는 동일 AgentFailure 계약.
  service 모듈에서도 기존 이름으로 계속 import할 수 있어 호출자 오류 계약을 유지합니다.
- 수정: `backend/agent/service.py` — 최종 생성에 단순 스키마와 카탈로그를 사용하고 변환 후 기존 검증 호출.
- 수정: `backend/agent/prompts.py` — 최종 단계의 토큰 선택·코드 문법·필수 사실·근거 정책 설명.
  조사 단계의 기존 Function Calling 지침은 변경하지 않았습니다.
- 수정: `scripts/agent_simple_report_prototype.py` — 운영 공통 구현을 재노출하는 호환 모듈로 축소.
  운영 코드가 scripts 또는 tests를 import하지 않으며 중복 변환 구현과 순환 import가 없습니다.
- 생성: `tests/test_agent_reporting_integration.py` — 새 계약을 직접 사용하는 운영/HTTP 테스트 30개.
- 수정: `tests/test_agent_service.py`, `tests/test_agent_efficiency.py`, `tests/test_agent_report_request.py`,
  `tests/test_agent_response_schema.py`, `tests/test_agent_schema_isolation.py`, `tests/test_agent_api.py`,
  `tests/test_agent_simple_report.py` — Mock 출력·최종 요청 단언을 새 계약에 맞춰 갱신.
- 수정: 본 문서에 새 결과를 추가했습니다. 과거 실제 실험 결과는 수정하지 않았습니다.

### 새 최종 진단 처리 흐름

1. 기존 Gemini Function Calling이 도구를 선택하고 서버가 허용된 Python 조회 도구만 실행합니다.
2. 요청별 Evidence 및 실제 Tool Trace를 보관하고 기존 정상 검사 조건부 조기 종료를 적용합니다.
3. 실행에 성공한 Evidence에 연결된 허용 scalar만 카탈로그 K 토큰으로 구성합니다.
4. 독립된 user Content에 검사 ID, 카탈로그, 최소 서버 Trace만 전달합니다.
   원시 검사 객체·원시 로그·임의 metrics나 이전 model Content·서명은 최종 요청에 넣지 않습니다.
5. 최종 요청은 기존과 동일한 **454바이트·깊이 2** 단순 JSON 스키마를 사용합니다.
   `response_mime_type=application/json`, `response_json_schema`만 설정하며 tools/tool_config는 없습니다.
6. 엄격한 JSON 파싱과 SimpleReport 검증을 수행합니다. 중복 키·NaN·추가 필드·잘못된 자료형을 거부합니다.
7. 카탈로그를 서버 Evidence와 재비교하고 선택된 K 토큰을 실제 provenance·값과 F 사실 참조로 매핑합니다.
   모델이 선택한 사실·가설·권고만 변환하며 핵심 사실 누락·잘못된 토큰을 자동 보충하거나 치환하지 않습니다.
8. 기존 DiagnosisDraft Pydantic 검증과 **변경하지 않은 `_verify_report()`**를 순서대로 적용합니다.
9. 동일한 DiagnosisResult 및 FastAPI 응답 계약으로 결과를 반환합니다.

모델은 요약 코드, 사실 선택, 원인·권고·한계 코드를 제안합니다. 관측값·판정·검사 ID·Trace를 생성하지 않습니다.
코드의 최종 문장 렌더링과 필수 안전 한계 고지는 기존 서버 정책 그대로이며 새로운 분석 사실을 만들어 넣지 않습니다.
기존 전체 DiagnosisDraft는 서버 검증 및 과거 격리 실험용으로 그대로 남아 있으며 최종 Gemini 전송에만 사용하지 않습니다.

### 보존된 검증 경계

- 검사 ID 고정, 도구 allowlist/인자 검증, 제품 ID 별칭 범위, 조회 도구 sanitizer를 유지했습니다.
- 실제 실행 성공 Trace와 Evidence ID의 연결을 확인한 후에만 카탈로그를 만듭니다.
- source_tool·Evidence ID·JSON Pointer·이벤트·실제 scalar 값 및 여섯 핵심 사실의 검증을 유지했습니다.
- 가설·권고가 선택된 사실을 참조해야 하며, 밝기·실행 실패·추론 실패 등의 실제 신호가 없으면 거부합니다.
- 모델은 inspection_id/product_id/observed_value/provenance/tools_used/Trace를 출력할 수 없습니다.
  이런 필드를 추가하면 RESPONSE_SCHEMA_INVALID이고, 저장 판정과 summary 충돌은 EVIDENCE_MISMATCH입니다.
- 기존 JSON/검증/모델 실패 코드와 HTTP 오류 매핑을 유지합니다. 실패를 정상 HTTP 200으로 바꾸지 않았습니다.
  중복 토큰과 금지된 ID 추가는 이제 토큰 응답의 구조 검증 단계에서 더 일찍 거부됩니다.
- 4라운드·8도구 실행·동일 호출 2회, 모델 요청 15초·도구 대기 3초·전체 분석 60초를 유지했습니다.
  자동 재시도는 활성화하지 않았습니다.
- 카탈로그는 최대 512개이며 크기 상한은 기존 프로토타입의 65,536바이트와 요청 설정 중 작은 값을 적용합니다.
  최종 전체 Content에도 기존 요청 크기 제한을 적용하고 초과 시 자르거나 근거를 보충하지 않고 실패합니다.

### 테스트 실행 및 실제 결과

모든 검증은 Conda vision-insight Python과 Mock/로컬 SDK 직렬화만 사용했습니다.
전체·Agent 검증에서는 SDK sync/async 전송 진입점을 차단하고 전송 시도 횟수가 **0**임을 확인했습니다.
운영 저장 경로 대신 새 임시 JSONL·출력 디렉터리를 사용했고 전체 회귀에 필요한 공개 fixture만 복사했습니다.

| 검증 | 실제 결과 |
|---|---|
| 신규 운영 통합/HTTP 테스트 | **30 passed**, 경고 1건, 4.35초 |
| 수정된 관련 Agent 테스트 7개 파일 | **307 passed**, 경고 1건, 6.96초 |
| 모든 `test_agent*.py` | **461 passed**, 경고 1건, 8.32초 |
| 전체 `tests` | **566 passed**, 경고 3건, 24.16초 |
| SDK 전송 시도 | **0회** |
| 실제 Gemini API 요청 | **0회** |
| `python -m pip check` | No broken requirements found |
| `git diff --check` 및 미추적 파일 공백 검사 | 오류 없음 |

기준 536개에 신규 30개를 추가하여 566개 모두 통과했으며 테스트를 삭제하거나 skip하지 않았습니다.
주요 실행 인자는 `python -m pytest tests/test_agent_reporting_integration.py -q -p no:cacheprovider`,
Agent 전체 파일 목록, `python -m pytest tests -q -p no:cacheprovider`와 같습니다.
실제 실행은 임시 저장 경로와 새 `--basetemp`를 지정한 `pytest.main()`을 SDK 전송 차단 문맥에서 호출했습니다.

정상·품질 경고·실패 기록·저장 판정 OK의 Mock 흐름, 실제 Python 조회 실행, 정상 조기 종료,
최종 스키마 직렬화, 관측 사실·Trace 연결, 원본 판정/JSONL 불변, 잘못된 토큰·실행되지 않은 근거,
가짜 Evidence ID·잘못된 Pointer, 카탈로그 변조, 근거 없는 가설·권고, 추가 필드·ID 변경 시도,
JSON 오류·모델 오류·시간 및 호출 한도 회귀를 검증했습니다.
직접 새 단순 JSON을 반환하는 신규 테스트와 별도로 기존 fixture는 테스트 전용 도우미에서
요청 카탈로그의 정확히 일치하는 사실 토큰으로 표현합니다. 운영 코드에는 구형 출력 fallback을 추가하지 않았습니다.

초기 관련 테스트에서는 기존 공용 pytest 임시 폴더 접근 권한 문제 및 구형 Mock/envelope 단언이 실패했습니다.
새 임시 basetemp를 사용하고 Mock 계약과 단언을 갱신하여 해결했습니다. 보안 검증을 완화하지 않았습니다.
SDK 로컬 직렬화 성공이나 Mock 통과를 실제 서버 검증 성공으로 표현하지 않습니다.

### 보호 상태 및 다음 절차

운영 JSONL 두 파일, PatchCore 체크포인트·메타데이터 및 tools/schemas/api/diagnostics의 전후 SHA256이
모두 동일했습니다. 고정 임계값 34.1442, 기존 검사 기록·판정, 이미지, 평가 영역을 변경하지 않았습니다.
API 키·평가 정답·내부 경로·서명 원문을 출력하지 않았으며 SDK/모델 변경도 없습니다.

운영 연결과 오프라인 회귀는 완료했습니다. **새 운영 경로의 실제 T01 End-to-End는 NOT TESTED**입니다.
실제 모델의 토큰 선택 준수율, 다양한 오류/부분 근거 상태에서의 품질, 실제 지연·사용량·비용은 미검증입니다.
기존 동기 조회 스레드의 강제 종료 불가 및 개발용 JSONL 동시성 한계도 남아 있습니다.

다음 작업은 별도 승인을 받은 T01 `POST /analyze/INSP-001396` 한 건의 실제 검증입니다.
승인 전 키 존재 여부·전송 계약·재시도 비활성화를 확인하고, 승인 후에만 실제 요청/Trace/변환/근거 검증/HTTP 결과를
계측해야 합니다. 추가 호출·다른 시나리오·Step 5는 별도 승인 대상입니다.
이번에는 실제 API 요청, 배포 또는 Git add/commit/push 없이 중단합니다.

## 실제 운영 T01 End-to-End: 단순 JSON 보고서 경로 (2026-10-16)

사용자가 승인한 `INSP-001396` 분석 **1회만** 수행했습니다. 모델은 `gemini-3.8-flash`,
SDK는 `google-genai==2.31.0`, 외부 API는 Developer API / `v1beta`를 유지했습니다.
자동 재시도, 모델·스키마 변경, 다른 검사 및 시나리오 실행은 없었습니다.
이 결과는 앞선 합성 Evidence 실험과 구분되는 실제 저장 검사 기록 기반의 운영 Agent 검증입니다.

### 사전 점검과 실행 경로

- 시작 시 Git 상태에는 바로 앞 운영 연결 작업의 미커밋 변경이 남아 있었습니다.
  최신 커밋은 여전히 `1069fe0`입니다. 기존 변경을 되돌리거나 덮어쓰지 않았습니다.
- 기존 저장소와 InspectionTools로 대상 기록 존재 및 OK / OK / ALL_CHECKS_PASSED를 확인했습니다.
  평가 정답·원본 이미지·Ground Truth를 읽거나 신규 검사를 생성하지 않았습니다.
- API 키는 존재 여부만 확인했습니다. 모델·SDK·도구 allowlist·최종 단순 스키마 직렬화,
  검사 ID 고정·sanitizer·판정 및 근거 검증 경로와 기존 호출/시간 제한을 확인했습니다.
- 별도 서버 프로세스를 띄우지 않고 `httpx.ASGITransport`로 실제 FastAPI 앱의
  **POST /analyze/INSP-001396**을 정확히 한 번 호출했습니다.
  운영 라우터·저장소 의존성·AgentRuntime·AgentService·실제 Gemini SDK를 통과했으며
  Mock Agent나 저장소 override를 사용하지 않았습니다.
  ASGI 앱의 lifespan을 별도로 실행하지 않아 분석에 불필요한 PatchCore 모델 예열도 하지 않았습니다.
  이는 프로세스 내 ASGI HTTP 검증이며 Uvicorn TCP 또는 배포 서버 HTTPS 검증은 아닙니다.
- 관련 오프라인 테스트 **30 passed, 경고 1건, 4.31초**, 실제 SDK 전송 시도 0회.
  수동 실행기의 `--offline-only` 사전 점검도 PASS였습니다.
- 별도 Git 제외 실행기로 실제 SDK/HTTP 전송·조회·변환·검증을 관찰했습니다.
  SDK attempts=1 및 HTTP transport retries=0, 전송 가드, 배타적 승인 회차 lock을 적용했습니다.
  계측은 실제 구현에 위임하며 운영 AgentService 기능이나 검사 정책을 수정하지 않았습니다.

### 실제 요청별 결과

실행 회차 시각: `2026-10-16T00:35:24.116147+00:00` (한국 시간 09:35).

| Gemini 요청 | 단계 | HTTP | 실제 결과 | SDK 소요 시간 |
|---|---|---:|---|---:|
| 1 | Function Calling | 200 | 모델이 get_inspection_result 선택 | 2,878.060ms |
| 2 | 독립 단순 JSON 최종 생성 | 200 | JSON 생성 후 변환·근거 검증 통과 | 10,528.745ms |

첫 요청에서 실제 Function Call이 발생했습니다. 서버가 고정된 검사 ID와 함수 인자를 검증하고
실제 Python 조회 도구를 실행한 후 정상 조기 종료 조건을 충족했습니다.
로그·품질·이력 조회와 별도 종료 확인 요청은 수행하지 않았습니다.
최종 생성에는 서버 카탈로그와 최소 Trace만 전달했으며 이전 Function Calling 대화·tools/tool_config는 없습니다.

이 조기 종료 경로는 FunctionResponse를 조사 루프에 다시 전송하는 대신 독립 최종 생성으로 전환합니다.
따라서 이번 결과를 FunctionResponse 후속 대화나 thought signature 왕복 전송 검증으로 해석하지 않습니다.
서명 원문은 출력·기록하지 않았습니다.

### 실제 Python 도구 및 Trace

| 순서 | 조사 라운드 | 도구 | executed | success | evidence_id | 도구 시간 |
|---:|---:|---|---|---|---|---:|
| 1 | 1 | get_inspection_result | true | true | E0001 | 2.229ms |

- `tools_used=[get_inspection_result]`, Agent 내부 도구 실행은 **1회**입니다.
- HTTP 존재 확인도 동일 Python 조회 도구를 사용하므로 전체 경로의 도구 호출 및 저장소
  `get_inspection` 읽기는 각각 **2회**입니다. 존재 확인은 Gemini가 선택한 실행이나 Agent Trace에 포함하지 않습니다.
- 정상 조기 종료 검사는 실행 도구 1개 시점에 true였습니다. 실제 모델의 도구 선택과 서버 조기 종료 정책을 구분합니다.
- 네 도구가 모두 실행됐다고 보고하지 않습니다. 다른 도구에 대한 이번 실서버 검증은 NOT TESTED입니다.

### 최종 응답 및 근거 검증

| 항목 | 관측 결과 |
|---|---|
| FastAPI POST 횟수 / HTTP | 1회 / **200** |
| analysis_status | **COMPLETED** |
| inspection_id 일치 | PASS: INSP-001396 |
| 단순 JSON 생성·엄격한 파싱 | PASS |
| SimpleReport 필수 필드·자료형 | PASS |
| 기존 DiagnosisDraft 변환 | PASS |
| 기존 Pydantic 검증 | PASS |
| Evidence ID / JSON Pointer / 실제 값 결정적 검증 | PASS |
| 관측 사실 / 실행 Trace 연결 | 6개 사실, 모두 성공한 E0001에 연결 |
| FastAPI 최종 응답 스키마 | PASS |
| 원본 제품 / 종합 / 이유 | OK / OK / ALL_CHECKS_PASSED 유지 |
| 원인 가설 | 0개, 확인되지 않은 장애 원인 추가 없음 |
| 권고 | CONTINUE_MONITORING, 실제 OK 근거 검증 통과 |
| 한계 | 기존 서버 안전 정책에 따른 한계 4개 포함 |
| 전체 T01 E2E | **PASS** |

기존 검증기는 핵심 여섯 사실과 실제 값, 가설·권고의 참조 관계, 저장 판정과 요약 일치를 확인했습니다.
최종 요약과 한계는 기존 서버 정책대로 모델 OK가 실제 무결점 보증이 아님을 명시합니다.
이번 정상 기록에서 물리적 장애 원인을 만들어 내거나 기존 판정을 변경하지 않았습니다.

### 사용량·제한·데이터 보호

| 사용량 | 요청 1 | 요청 2 | 합계 |
|---|---:|---:|---:|
| 입력 토큰 | 1,152 | 1,963 | **3,115** |
| 출력 토큰 | 28 | 97 | **125** |
| Thinking 토큰 | 91 | 1,375 | **1,466** |
| 총 토큰 | 1,271 | 3,435 | **4,706** |

- 실제 외부 HTTP 요청 **2회**, 두 요청 모두 HTTP 200, 오류 코드 없음.
- 전체 ASGI 분석 실험 시간 **13,577.580ms (약 13.578초)**.
  두 모델 요청 모두 15초 이내, Agent 전체 60초 이내이며 도구 실행도 3초 이내입니다.
- 최대 4조사 라운드·8도구 실행·동일 호출 2회 제한을 유지했습니다. 추가 시도 및 자동 재시도는 없습니다.
- 실제 과금액은 **NOT AVAILABLE**입니다. 토큰 수만으로 금액을 확정하지 않습니다.
- 검사/이벤트 JSONL·PatchCore 체크포인트·메타데이터의 전후 SHA256이 모두 동일했습니다.
  저장소 쓰기 시도는 0회, 임계값 34.1442 및 검사 판정은 변경하지 않았습니다.
- 최종 전송에도 sanitizer·카탈로그 허용 필드·제품 별칭/이미지 ID 비노출 정책을 유지했습니다.
  API 키·프롬프트 전문·원본 경로·평가 정답·서명 원문은 출력하거나 결과 파일에 저장하지 않았습니다.

### 변경 범위 및 남은 검증

추가는 본 문서와 Git 제외 수동 실행기 `data/outputs/manual_validation/run_t01_simple_e2e_once.py`,
해당 회차 lock 및 정제된 계측 JSON뿐입니다. 기존 운영 Agent 코드와 테스트는 이번에 수정하지 않았습니다.
`git diff --check`는 통과했습니다. 이번 회차 전체 pytest는 재실행하지 않았으며,
전체 566개 통과는 직전 오프라인 운영 통합 회차의 결과입니다.

T01 실제 FastAPI 앱→Gemini Function Calling→Python 조회→독립 단순 JSON→엄격한 변환·근거 검증은 완료했습니다.
다양한 입력에서의 반복 성공률, T03/T05/T06, 긴 조사 루프의 새 출력 경로, 배포 서버 HTTPS와
실제 비용은 이번에 검증하지 않았습니다. D/E2의 과거 HTTP 400 정확한 원인도 여전히 UNKNOWN입니다.
후속 권장 작업은 T03/T05/T06 검증 범위·비용에 대한 별도 승인을 받는 것입니다.
이번 승인 회차는 종료하며 추가 API 요청·Step 5·기능 개발·Git add/commit/push를 수행하지 않습니다.

## 실제 운영 T03 밝기 경고 E2E: 조사 단계 HTTP 504 (2026-10-16)

사용자가 승인한 T03 `INSP-001398` 분석을 **정확히 1회** 수행했습니다.
모델 `gemini-3.8-flash`, SDK `google-genai==2.31.0`, Developer API / `v1beta`를 유지했습니다.
결과는 **기술적 E2E FAIL**, 최종 진단 품질 평가는 **NOT TESTED**입니다.
도구 선택과 실제 조회에는 부분 성공이 있으나 최종 보고서가 없으므로 전체 PASS로 처리하지 않습니다.
기존 T01 및 과거 실험 기록은 변경하지 않았습니다.

### 사전 점검과 실행 범위

- AGENTS 지침과 Git 상태를 확인했습니다. 이전 운영 통합의 미커밋 변경을 그대로 보존했습니다.
- 기존 저장소를 읽어 대상 검사·연결 이벤트 로그·저장된 품질 지표의 존재를 확인했습니다.
  평가 정답이나 이미지·주입 정보를 조회하거나 런타임 컨텍스트로 제공하지 않았습니다.
- 키 존재 여부만 확인했으며 모델·SDK·도구 allowlist·고정 검사 ID·sanitizer·카탈로그 변환 및
  Python 검증 경로, 기존 4라운드/8도구/동일 호출 2회/15초 모델/3초 도구/60초 전체 제한을 확인했습니다.
- 오프라인 전용 실행기 점검 PASS, 실제 Gemini 요청 0회였습니다.
  경고 시나리오 Mock 회귀 테스트 1개도 실제 실행하여 **1 passed in 4.73s**였습니다.
- 실제 FastAPI 앱의 **POST /analyze/INSP-001398**을 ASGITransport로 한 번 호출했습니다.
  운영 라우터·저장소·AgentRuntime·AgentService·실제 Gemini SDK를 사용했으며 Mock Agent는 없습니다.
  별도 서버나 PatchCore 추론을 실행하지 않았습니다. 배포 서버 TCP/HTTPS 검증은 아닙니다.
- SDK attempts=1, transport retries=0, 요청 범위 가드 및 배타적 회차 lock을 유지했습니다.
  T01/T05/T06, 다른 스키마·모델, 실패 후 추가 호출은 실행하지 않았습니다.

### 실제 Gemini 요청별 결과

회차 시각: `2026-10-16T01:15:43.196978+00:00` (한국 시간 10:15).

| 요청 | 조사 라운드 / 단계 | HTTP | 실제 결과 | SDK 소요 시간 |
|---|---|---:|---|---:|
| 1 | 1 / FUNCTION_CALLING | 200 | get_inspection_result 선택 | 2,727.430ms |
| 2 | 2 / FUNCTION_CALLING | 200 | analyze_image_quality 선택 | 3,653.919ms |
| 3 | 3 / FUNCTION_CALLING | **504** | **DEADLINE_EXCEEDED**, 응답 실패 | 14,191.344ms |

실패 위치는 두 번째 도구의 FunctionResponse를 포함한 **후속 조사 요청**입니다.
독립 단순 JSON 최종 생성 요청에 도달하지 않았습니다. 이번 실패는 구조화 스키마 HTTP 400 재발이 아닙니다.
세 번째 응답이 없으므로 모델이 추가 도구를 원했는지 조사를 마치려 했는지는 **UNKNOWN**입니다.
15초 로컬 요청 제한 또는 60초 전체 제한이 직접 발생시킨 로컬 timeout이 아니라,
실제 Gemini 서버가 HTTP 504와 DEADLINE_EXCEEDED를 반환한 것으로 계측됐습니다.
왜 서버 deadline에 도달했는지에 대한 구체적인 내부 원인은 UNKNOWN입니다.

안전하게 수집한 오류:

```json
{
  "http_status": 504,
  "google_api_code": "DEADLINE_EXCEEDED",
  "reason": "UNKNOWN",
  "field_violations": [],
  "request_stage": "FUNCTION_CALLING",
  "sdk_exception_type": "ServerError"
}
```

원시 오류 메시지·프롬프트·인증 정보·서명은 출력하거나 기록하지 않았습니다.

### 실제 도구 실행과 프로토콜

| 순서 | 도구 라운드 | 도구 | executed / success | 근거 ID | 실행 시간 |
|---:|---:|---|---|---|---:|
| 1 | 1 | get_inspection_result | true / true | E0001 | 2.890ms |
| 2 | 2 | analyze_image_quality | true / true | E0002 | 1.896ms |

- Agent가 실제 실행한 도구는 2개이며 중복 조회 도구 호출은 없었습니다.
  HTTP 존재 확인을 포함한 경로 전체 Python 도구 호출은 get_inspection_result 2회 + analyze_image_quality 1회,
  저장소 get_inspection 읽기는 3회입니다. HTTP 존재 확인은 Agent Trace에 포함하지 않습니다.
- 두 후속 요청의 FunctionResponse 역할은 user이며 함수 이름·호출 ID가 원래 Function Call과 일치했습니다.
  전체 모델 Content 객체 재사용 및 Part 경계·thought signature의 바이트 보존도 계측했습니다.
  요청 2는 HTTP 200으로 후속 프로토콜 처리가 확인됐고, 요청 3의 전송 구조는 유효했으나 서버는 504를 반환했습니다.
- T03에 정상 조기 종료가 적용되지 않은 것은 기존 정책과 일치합니다. 두 도구 실행 후 모두 ready=false였습니다.
- Agent는 이번에 로그·이력 조회를 선택하지 않았습니다. 아래 로그 정보는 사전 읽기 전용 확인 결과이며,
  Gemini가 로그를 조회하거나 로그에 근거한 최종 진단을 했다고 보고하지 않습니다.

### 실제 저장된 밝기 근거와 진단 품질의 경계

| 기록 항목 | 읽기 전용 조회 결과 |
|---|---|
| image_quality_status | WARNING_LOW_BRIGHTNESS |
| 밝기 mean / std | **81.24 / 55.79** |
| min / max | 18.0 / 153.0 |
| 영상 크기 / 채널 | 900 × 900 / 3 |
| 검사 당시 밝기 임계값 | **NOT_RECORDED**, brightness_thresholds=null |
| 제품 판정 | OK |
| 종합 판정 | REINSPECT |
| 실제 final_reason_code | IMAGE_QUALITY_WARNING |

사전 조회한 실제 이벤트에는 `ANALYSIS_COMPLETED` / stage=analyze / level=WARN이 있으며,
위 mean/std/min/max가 기록돼 있습니다. `INSPECTION_COMPLETED` / stage=complete / level=WARN에는
WARNING_LOW_BRIGHTNESS·REINSPECT·IMAGE_QUALITY_WARNING이 기록돼 있습니다.
별도의 밝기 경고 이벤트 코드를 만들어 내지 않았습니다.

실제 Agent도 검사 결과와 저장 품질 도구를 성공적으로 읽었으므로 위 품질 상태·측정값·기준 미기록 상태가
도구 결과로 확보됐습니다. 그러나 이를 인용한 최종 관측 사실·권고·가설은 생성되지 않았습니다.
현재 설정을 과거 밝기 임계값으로 대체하지 않았으며, 모델 판정 임계값 34.1442를 밝기 기준으로 혼동하지 않습니다.
기록상 제품 OK와 품질 사유 REINSPECT는 별개입니다. 실제 조명 장치·카메라 고장이나 설정 변경의 증거는 없습니다.
권고의 적절성·사실과 가설 구분·최종 설명의 정확성은 보고서 미생성으로 **NOT TESTED**입니다.

### 최종 응답과 검증 단계

| 항목 | 결과 |
|---|---|
| FastAPI 요청 횟수 / HTTP | 1회 / **502** |
| analysis_status | **FAILED** |
| 안전한 오류 코드 | GEMINI_REQUEST_FAILED |
| 실제 Function Calling 및 Python 조회 | 부분 성공: 도구 2개 실행 성공 |
| 최종 단순 JSON 생성·파싱 | NOT TESTED: 해당 단계 미도달 |
| SimpleReport 구조 검증 | NOT TESTED |
| DiagnosisDraft 변환 / Pydantic 검증 | NOT TESTED / NOT TESTED |
| 최종 Evidence ID / JSON Pointer 결정적 검증 | NOT TESTED |
| 검사 ID 범위 | 실행된 두 도구 모두 INSP-001398 |
| 기술적 E2E 결과 | **FAIL** |
| 진단 품질 평가 | **NOT TESTED** |

### 사용량·제한·보호

| 확인된 토큰 | 요청 1 | 요청 2 | 요청 3 | 확인된 합계 |
|---|---:|---:|---|---:|
| 입력 | 1,152 | 1,660 | NOT AVAILABLE | **2,812** |
| 출력 | 28 | 28 | NOT AVAILABLE | **56** |
| Thinking | 197 | 349 | NOT AVAILABLE | **546** |
| 총 토큰 | 1,377 | 2,037 | NOT AVAILABLE | **3,414** |

- 실제 Gemini HTTP 요청은 **3회**이고 자동 재시도·추가 분석은 0회입니다.
- 전체 실험 시간은 **20,684.617ms (약 20.685초)**입니다. 기존 호출 수와 시간 제한을 유지했습니다.
- 실패한 요청 3의 사용량과 실제 비용은 확인 불가입니다. 확인된 3,414토큰을 전체 과금 토큰으로 단정하지 않습니다.
- 운영 JSONL 2개·체크포인트·메타데이터 및 service/reporting/schemas/prompts/tools/api의
  총 10개 보호 파일의 전후 SHA256이 모두 동일했습니다. 저장소 쓰기 시도는 0회입니다.
- 실행 후 대상 기록을 다시 읽어 **OK / REINSPECT / IMAGE_QUALITY_WARNING 불변**을 확인했습니다.
  기존 T01/T03/T05/T06을 포함한 JSONL 전체와 임계값 34.1442는 변경하지 않았습니다.
- 수동 실행기의 초기 요약 필드 `verdict_unchanged=false`는 성공 응답이 없는 상태에서
  `returned_verdict`와 저장 판정을 비교한 값입니다. 저장 판정 변경을 뜻하지 않습니다.
  파일 해시와 실행 후 저장소 재조회가 실제 불변 검증 근거입니다. 초기 계측 기록은 그대로 보존합니다.

### 변경 범위와 다음 작업

추가는 본 문서와 Git 제외 수동 실행기 `data/outputs/manual_validation/run_t03_simple_e2e_once.py`,
해당 승인 회차 lock·정제된 계측 JSON입니다. 운영 AgentService·스키마·검증·설정을 수정하지 않았습니다.
전체 pytest는 이번에 재실행하지 않았습니다. 전체 566개 통과는 이전 오프라인 운영 통합 결과입니다.

T05/T06은 실행하지 않았습니다. 다음 실제 호출은 별도 승인이 필요합니다.
먼저 이번 세 번째 조사 요청과 경고 검사 종료 전환 흐름을 **오프라인에서** 검토하는 것을 권장합니다.
서버 504 내부 원인이 확인되지 않은 상태에서 timeout 증가·모델 변경·자동 재시도로 해결됐다고 주장하지 않습니다.
T05의 실행 실패와 제품 판정 UNKNOWN을 구분해야 하며, T06은 저장된 모델 OK만 사용하고 실제 정답을 제공하면 안 됩니다.
운영 수정 필요성은 이번 실패만으로 확정하지 않습니다. 코드 수정·재검증은 별도 승인 후 진행해야 합니다.
T03 재호출·T05/T06·Step 5·후속 기능·배포·Git add/commit/push 없이 중단했습니다.

## T03 HTTP 504 및 경고 조사 종료 정책: 오프라인 비교 (2026-10-16)

이번 회차는 분석·실험용 정책·Mock 테스트만 수행했습니다. **실제 Gemini 요청은 0회**이며,
운영 AgentService·보고서 변환·프롬프트·스키마·오류 계약을 변경하지 않았습니다.
기존 미커밋 운영 통합 작업과 별도 사용자 변경을 보존했고 앞선 T03 실패 기록을 수정하지 않았습니다.

### 확인된 세 번째 요청의 발생 이유

운영 `_run()`은 각 모델 응답의 Function Call을 실제 실행하고 FunctionResponse를 user Content에 추가합니다.
그 뒤 `_normal_evidence_ready()`만 확인합니다. 이 함수는 COMPLETED / OK / NORMAL / COMPLETED / OK /
ALL_CHECKS_PASSED와 유한한 score ≤ threshold가 모두 충족된 정상 기록만 대상으로 합니다.
T03의 WARNING_LOW_BRIGHTNESS / REINSPECT / IMAGE_QUALITY_WARNING은 이 조건에 해당하지 않습니다.

따라서 결과 조회 후에도, 품질 조회 후에도 ready=false였고 다음 반복의 세 번째 모델 요청이 발생했습니다.
현재 경고 경로는 모델이 Function Call 없는 응답을 반환해야 최종 독립 JSON 생성 단계로 넘어갑니다.
세 번째 요청이 곧 최종 보고서 생성인 것은 아닙니다. 이 요청은 AUTO Function Calling 조사 단계였습니다.
모델이 다음 조회를 하려 했는지 종료 응답을 하려 했는지는 504로 응답이 없어 **UNKNOWN**입니다.

현재 조사 지침은 충분한 근거 이후 불필요한 종료 확인을 피하라고 안내하지만 서버 종료 분기는 정상 검사에만 있습니다.
또한 조사 SYSTEM_INSTRUCTION에는 수집 후 DiagnosisDraft를 반환하라는 기존 문구가 남아 있고,
실제 최종 단계는 별도 단순 토큰 JSON을 요구합니다. 조사 단계가 초안을 작성하면 다시 최종 생성할 여지가 있습니다.
이는 향후 승인 후 정리할 설계상 중복 가능성이지 이번 서버 504의 확정 원인이 아닙니다.

### 확보된 Evidence와 분석 한계

| 근거 | 확보된 내용 | 확보되지 않거나 주장할 수 없는 내용 |
|---|---|---|
| E0001: get_inspection_result | 여섯 핵심 상태, 제품 OK, 종합 REINSPECT, IMAGE_QUALITY_WARNING, 모델 점수/임계값, 저장 품질 지표 | 실제 제품 정답·물리적 원인 |
| E0002: analyze_image_quality | WARNING_LOW_BRIGHTNESS, mean 81.24, std 55.79, min 18, max 153, 900×900×3 | 당시 밝기 임계값은 NOT_RECORDED, 장비 고장 확정 불가 |
| 실행 이벤트 | 개발자 사전 조회에서 analyze/WARN 및 complete/WARN 확인 | Agent는 로그 도구를 선택하지 않았으므로 로그 기반 단계 설명의 최종 검증은 미실행 |
| 최종 보고서 | 생성 단계에 도달하지 못함 | JSON·DiagnosisDraft·최종 Evidence 검증과 권고 품질은 NOT TESTED |

두 도구는 같은 저장 검사 기록을 읽으므로 지표가 겹칩니다. 독립 센서의 교차 검증은 아닙니다.
다만 품질 도구는 당시 기준의 기록 여부를 명시하므로 의미가 없는 동일 함수 반복과도 구분해야 합니다.
저장 품질 상태를 설명하는 제한된 보고서는 두 근거로 구성할 수 있지만, 경고 발생 단계·시간·이벤트 순서를
설명하거나 숨은 실행 오류를 조사하려면 실제 로그가 필요합니다. 현재 코드에 모든 밝기 경고의 로그 조회를
무조건 강제하는 규칙은 없으며, 프롬프트는 실행/추론 실패나 이벤트 근거가 필요한 경우 로그를 권합니다.

### 실패 요청 구성·컨텍스트·시간 제한

- 요청 1은 user 목표, 요청 2는 user → model(Function Call) → user(FunctionResponse),
  요청 3은 user → model → user → model → user 순서의 누적 조사 이력입니다.
- 요청 3에는 결과 및 품질 FunctionResponse 두 개와 네 도구 선언, 조사 system_instruction이 포함됩니다.
  최종용 response_mime_type/response_json_schema는 아직 설정되지 않았습니다.
- 앞선 실제 계측에서 함수 이름·ID·user 역할 및 모델 Content/Part/서명 보존은 확인됐습니다.
  요청 2는 실제 HTTP 200, 요청 3은 실제 HTTP 504였습니다. 프로토콜/스키마 오류로 확정할 근거는 없습니다.
- 기존 SDK timeout은 요청별 15초, 도구 3초, 전체 60초, retry attempts=1입니다.
  실제 수동 계측 transport retries=0도 유지됐습니다. 실제 요청은 3회, 재시도는 0회였습니다.
- 요청 3은 약 14.191초에 ServerError / DEADLINE_EXCEEDED를 반환했습니다.
  로컬 TimeoutError라면 GEMINI_TIMEOUT이지만, 서버 SDK 예외는 현재 일반 GEMINI_REQUEST_FAILED로 정제되어
  FastAPI 502가 됩니다. 이 오류 계약은 이번에 변경하지 않았습니다.
- 실제 요청 3의 원문·정확한 직렬화 바이트 수와 사용 토큰은 저장되지 않아 **UNKNOWN**입니다.
  확인된 요청 1/2 입력 토큰은 1,152 / 1,660이며 요청 3의 전체 컨텍스트 크기로 대체하지 않습니다.
  증가한 컨텍스트나 호출 수가 서버 504를 일으켰다고 인과관계를 확정할 수 없습니다.

### 실험 정책 B: 좁은 경고 범위의 결정적 종료

추가 모듈 `scripts/agent_warning_policy_experiment.py`는 운영 경로에 import되지 않습니다.
`warning_evidence_ready(state, required_event_codes=())`는 다음 조건을 모두 확인합니다.

1. 고정 검사 ID가 snapshot·두 도구 데이터·실제 실행 인자에 일치하고 정상적으로 실행된 Trace가 존재해야 합니다.
2. 실행/추론 COMPLETED, 제품 OK, 품질 LOW/HIGH_BRIGHTNESS 경고, 종합 REINSPECT,
   이유 IMAGE_QUALITY_WARNING이어야 합니다. 저장 모델 score/threshold도 유한하고 score ≤ threshold여야 합니다.
3. 결과와 품질 도구의 Evidence ID·metadata·성공 Trace가 연결되고 여섯 핵심 상태와 측정값이 일치해야 합니다.
   과거 오류·불완전 실행·충돌·다른 도구의 추가 조사 흔적이 있으면 이 좁은 정책으로 종료하지 않습니다.
4. mean/std/min/max가 유효하고 0~255 범위이며 min ≤ mean ≤ max, 크기·채널도 유효해야 합니다.
   누락된 값·잘못된 근거 ID·다른 검사·불일치는 False로 처리하여 기존 조사 경로를 유지합니다.
5. NOT_RECORDED이면 brightness_thresholds=null이라는 명시적 기록을 받아들이되 기준을 만들어 내지 않습니다.
   RECORDED이면 저장 low/high 범위와 실제 측정값이 LOW/HIGH 경고 방향을 뒷받침해야 합니다.
6. 이벤트가 필수인 서버 프로필에서는 해당 로그 조회가 실제 성공하고 올바른 코드·단계·시각·수치가 있어야 합니다.
   실험은 ANALYSIS_COMPLETED / INSPECTION_COMPLETED 두 이벤트 프로필을 지원합니다.
   다른 필수 이벤트, 누락·시각 오류·상충 수치·오류 이벤트는 종료하지 않습니다.

`required_event_codes`는 실험용의 신뢰된 서버 정책 입력이지 모델이 정하거나 이미 운영 API에 추가된 인자가 아닙니다.
운영 도입 전에는 보고서 목적별 필수 로그 프로필을 승인하고 조사 지침에도 그 요구를 반영해야 합니다.
예를 들어 경고 단계/순서를 요구하는 보고서라면 기본 무로그 프로필로 종료해서는 안 됩니다.
이벤트를 조회하지 않은 기본 프로필에서는 사건 단계나 설비 원인을 주장할 수 없습니다.

이 정책은 실제 제품 정답을 판별하거나 미기록 물리적 장애가 없다고 보증하지 않습니다.
T05의 실행 실패/UNKNOWN/ERROR, 모델 NG·추론 실패·불명확한 상태는 범위 밖입니다.
T01/T06처럼 품질 NORMAL인 저장 OK는 기존 정상 종료 규칙을 그대로 사용하고 경고 규칙에 넣지 않습니다.

### 종료 충분성과 최종 보고서 충분성은 별도 검증

현재 운영 `_verify_report()`의 필수 관측은 핵심 여섯 상태입니다. 품질 도구를 조회했다고 해서 모델이
밝기 수치와 당시 기준 미기록 상태까지 최종 관측에 반드시 선택하는 것은 아닙니다.
따라서 종료 조건을 OR로 추가하는 것만으로 요청된 경고 설명 품질이 보장되지는 않습니다.

실험 `warning_report_covered()`는 **기존 Pydantic 및 `_verify_report()`가 실제 값·JSON Pointer·참조를 검증한 뒤**
추가로 품질 상태, mean/std/min/max, threshold_status의 관측 포함을 요구합니다.
기준이 기록됐다면 실제 low/high, 이벤트가 필수라면 해당 source_event와 실제 stage 사실도 필요합니다.
누락된 설명은 EVIDENCE_MISMATCH로 거부하며 자동 생성·정상화·재요청하지 않습니다.
원인/권고의 참조·판정 보호는 기존 검증을 그대로 통과해야 합니다. NOT_RECORDED에 대한 기존 안전 한계도 유지합니다.

운영 구현을 수정하는 대신 테스트 전용 ExperimentalWarningAgent와 제한된 테스트 문맥의 predicate 교체로 비교했습니다.
운영 `_run()`을 복사하거나 운영 파일을 고치지 않았고 테스트 종료 후 원래 정책으로 복원됩니다.
이 추가 설명 검증도 아직 운영 정책이 아니라 승인이 필요한 제안입니다.

### 현행 A와 제안 B 비교

| 기준 | A: 모델이 조사 계속/종료 선택 | B: 근거 충분성으로 서버가 종료 |
|---|---|---|
| 장점 | 예상하지 못한 로그·추세 조사에 유연함 | 종료 이유가 명시적이며 경계·누락을 테스트 가능 |
| 단점 | 경고에서 무도구 종료 응답을 받기 위한 추가 모델 요청이 필요할 수 있음 | 좁은 규칙이 아직 조회하지 않은 유용한 로그를 놓칠 위험 |
| 기본 경고 Mock | 결과 → 품질 → 무도구 종료 → 최종: **4회** | 결과 → 품질 → 최종: **3회** |
| 로그 필수 Mock | 결과 → 품질 → 로그 → 무도구 종료 → 최종: **5회** | 결과 → 품질 → 로그 → 최종: **4회** |
| 정보 보호 | 기존 sanitizer·Pydantic·Evidence 검증 | 동일 검증 + 실험용 종료/설명 충분성 검사 |
| 실패 처리 | 조사/최종 단계 어느 쪽도 504 가능 | 조사 1회를 생략해도 최종 504/timeout 가능 |
| 실제 비용·시간 개선 | 이번 측정 없음 | 이번 측정 없음, 감소량/성공률 UNKNOWN |

위 호출 수는 명시한 순서대로 응답하는 Mock의 실제 결과입니다. 실제 모델이 다른 도구를 선택하면 달라집니다.
현행 루프의 최대 SDK 요청 수는 조사 최대 4라운드 + 무도구 종료 응답 1회 + 최종 1회로 최대 6회이며,
제안 실험은 기존 상한·모델/전체 시간 제한을 늘리지 않습니다. 도구 실행 상한은 별도로 8회입니다.
T03의 실제 실패 경로는 3번째 조사에서 중단됐으므로 현행 성공 경로 4회를 실제 관측했다고 주장하지 않습니다.

Mock SDK 직렬화에서 관찰한 contents 크기는 아래와 같습니다. system_instruction·도구 선언·스키마를 제외한
compact UTF-8 contents만 계산했으며, 합성 fixture와 가짜 서명을 사용한 값으로 실제 T03 요청 크기가 아닙니다.

| Mock 단계 | 역할 순서 | contents 바이트 |
|---|---|---:|
| 첫 조사 | user | 127 |
| 결과 후 조사 | user/model/user | 1,018 |
| 품질 후 조사 또는 로그 요청 | user/model/user/model/user | 1,675 |
| 결과+품질의 독립 최종 생성 | user | 6,057 |
| 로그 필수 프로필의 독립 최종 생성 | user | 15,651 |

제안은 기본 Mock에서 1,675바이트의 조사 요청 한 번을 생략했지만 동일한 최종 근거 패킷을 유지했습니다.
최종 카탈로그 자체가 클 수 있으므로 실제 토큰·Thinking·지연·비용 감소를 이 바이트 차이로 계산하지 않습니다.

### 오프라인 테스트와 보호 결과

변경은 실험 모듈·`tests/test_agent_warning_policy_experiment.py`·본 문서의 세 파일로 한정됩니다.

| 검증 | 실제 결과 |
|---|---|
| 신규 Mock/정책 테스트 | **65 passed**, 경고 1건, 5.87초 |
| 모든 Agent 테스트 | **526 passed**, 경고 1건, 12.84초 |
| 전체 pytest | **631 passed**, 경고 3건, 31.02초 |
| pip check | No broken requirements found |
| git diff --check 및 새 파일 공백 검사 | 오류 없음 |
| 실제 Gemini 요청 / SDK 전송 시도 | **0회 / 0회** |

기준 566개와 신규 65개가 모두 통과했으며 기존 테스트를 수정·삭제·skip하지 않았습니다.
vision-insight Python에서 `pytest.main()`으로 새 파일, `test_agent*.py`, 전체 `tests`를 각각 실행했습니다.
공통 인자는 `-q -p no:cacheprovider --tb=short --disable-warnings --basetemp <새 임시 폴더>`이며
검사/로그/출력 경로를 임시 디렉터리로 분리하고 공개 fixture만 복사했습니다. SDK sync/async 전송을 차단했습니다.

검증에는 두 Evidence 충분/불충분, 누락·변조·상충·고정 ID·필수 로그·이벤트 시각/수치,
실제 토큰 선택과 JSON Pointer 검증, 최종 설명 누락 거부, 동일 호출 제한, 라운드/도구 상한,
현행 세 번째 조사 504 → HTTP 502, 제안의 최종 504/timeout 거부, T01/T05/저장 OK 경계가 포함됩니다.

운영 JSONL·체크포인트·메타데이터와 service/reporting/schemas/prompts/tools/diagnostics/api/config의
총 12개 보호 파일은 시작/종료 SHA256이 모두 동일했습니다. 모델·SDK·임계값 34.1442도 변경하지 않았습니다.
Ground Truth와 원본 이미지는 읽지 않았으며 API 키 값·실제 요청 본문·서명 원문을 출력하거나 외부로 전송하지 않았습니다.

### 추천 최소 변경안 및 승인 경계

**B안을 좁은 품질 경고 범위에 한정해 검토하되 종료 predicate만 단독 추가하지 않는 것을 추천합니다.**
운영 승인 후 필요한 최소 지점은 (1) 기존 정상 종료 또는 경고 근거 충족으로 조사 종료,
(2) 최종 보고서의 밝기/기준 상태·필수 이벤트 설명 coverage 검사,
(3) 조사/최종 지침의 요구 일치와 서버 소유 필수 로그 프로필 명시입니다.
기존 DiagnosisDraft·Pydantic·결정적 값 검증·FastAPI 판정 권한·시간/호출 제한을 완화할 필요는 없습니다.

남은 위험은 좁은 정책 밖의 숨은 이벤트 누락, 원인 진단 범위 축소, 모델의 필수 토큰 선택 실패,
최종 생성의 서버 deadline 및 카탈로그 크기입니다. 충분하지 않으면 기존 조사로 돌아가고,
최종 검증 실패를 성공으로 처리하지 않아야 합니다. 서버 504의 내부 원인은 여전히 UNKNOWN입니다.

운영 연결·프롬프트/coverage 정책 변경은 **별도 승인**, 그 후 T03 실제 재검증도 비용을 설명하고 **별도 승인**이 필요합니다.
이번에는 실제 호출·운영 코드 변경·T03 재실행·T05/T06·Step 5·Git add/commit/push 없이 중단합니다.

## 경고 검사 조건부 조사 종료 운영 통합: 오프라인 회귀 (2026-10-16)

이번 승인 범위는 운영 연결과 Mock 검증입니다. **실제 Gemini API 요청은 0회**이며 T03을 재실행하지 않았습니다.
이전 T01 실제 PASS, T03의 조사 요청 3에서 발생한 서버 504 및 미확정 원인 기록을 보존합니다.
시작 시 있던 미커밋 변경과 별도 사용자 작업은 되돌리거나 덮어쓰지 않았습니다.

### 최소 통합 구조와 변경 파일

- 생성: `backend/agent/investigation.py` — 경고 범위, 근거 충분성, 필수 이벤트 정책, 최종 설명 coverage.
- 수정: `backend/agent/service.py` — 기존 정상 또는 경고 충분성으로 조사 종료, 최종 검증 뒤 경고 coverage 적용.
- 수정: `backend/agent/reporting.py` — 기존 CORE_FIELDS와 타입 보존 scalar 비교를 공통 소유하도록 이동.
  service의 기존 import 이름도 유지하여 호출자와 기존 결정적 검증의 의미를 바꾸지 않았습니다.
- 수정: `backend/agent/prompts.py` — 조사 단계의 구형 전체 DiagnosisDraft 생성 요구를 제거하고,
  품질 조회·별도 최종 단계·밝기/기준 상태·필수 이벤트의 실제 stage/timestamp 선택 요구를 일치시켰습니다.
- 수정: `scripts/agent_warning_policy_experiment.py` — 공통 운영 구현을 재노출하는 호환 모듈로 정리.
  운영 코드가 scripts/tests를 import하지 않으며 정책을 중복 구현하지 않습니다.
- 생성: `tests/test_agent_warning_policy_integration.py` — 실제 AgentService를 사용하는 신규 30개 Mock/HTTP 테스트.
- 수정: 기존 warning_policy_experiment 테스트는 역사적 흐름 비교용 LegacyWarningAgent만 남기고
  제안 경로를 실제 운영 AgentService로 전환했습니다. 예전 65개 테스트도 모두 유지했습니다.
- 수정: service/simple_report/reporting_integration/efficiency/report_request/api 관련 테스트의
  경고 Mock에 실제 품질 도구 선택과 필수 관측을 명시하고 변경된 3요청 경로를 검증합니다.
  누락된 모델 관측을 운영 코드에서 보충하는 fallback은 추가하지 않았습니다.
- 본 문서에 결과를 추가했습니다. 기존 DiagnosisDraft·FastAPI·조회 도구·설정 스키마는 변경하지 않았습니다.

### 운영 종료 조건

이전에는 정상 검사 `_normal_evidence_ready()`만 조사 루프를 종료했습니다.
이제 `_investigation_ready()`가 **기존 정상 종료 또는 경고 근거 충분성**을 검사합니다.
기존 함수 자체와 정상 판정의 의미는 그대로입니다.

경고 종료는 다음의 좁은 프로필에 한정됩니다.

1. 검사 프로그램/추론 COMPLETED, 제품 OK, LOW/HIGH_BRIGHTNESS 경고,
   종합 REINSPECT, 이유 IMAGE_QUALITY_WARNING.
2. 고정 inspection_id가 snapshot·실제 도구 인자·검사/품질 데이터에 일치.
3. get_inspection_result와 analyze_image_quality의 실제 성공 Trace/Evidence ID/metadata 연결 및
   여섯 핵심 상태·지표 일치. 저장 모델 점수/임계값도 유한하고 score ≤ threshold.
4. 실제 mean/std/min/max와 크기/채널 유효성. 당시 기준이 RECORDED면 기록된 low/high와 경고 방향의 일치.
   NOT_RECORDED면 기준값은 null 그대로 두며 현재 설정으로 보충하지 않음.
5. 필수 이벤트 프로필이 있다면 실제 조회 로그의 코드·단계·시각·측정값·종합 판정 근거 충족.

정보가 누락·상충되면 경고 조기 종료를 하지 않고 기존 조사와 호출/시간 상한을 유지합니다.
T05처럼 실행 실패인 상태나 모델 UNKNOWN/NG, 추론 실패는 이 경고 종료 범위에 넣지 않습니다.
T06처럼 품질 NORMAL인 저장 OK도 경고로 재해석하지 않으며 기존 정상 정책을 그대로 사용합니다.
여기서 정상/경고는 저장된 운영 판정이며 실제 제품 정답은 사용하지 않습니다.

### 명시적인 필수 로그 정책

서버가 AgentService 생성자에 다음과 같이 신뢰된 프로필을 지정합니다.

```python
AgentService(tools, settings=settings, client=client,
             required_warning_event_codes=("ANALYSIS_COMPLETED", "INSPECTION_COMPLETED"))
```

- 기본값은 빈 tuple입니다. 현재 inspection_id 전용 FastAPI 분석은 단순 밝기 설명 프로필로,
  결과·품질 근거가 충분하면 추가 로그를 무조건 요구하지 않습니다.
- 계약상 경고 이벤트 단계/시각/순서를 다뤄야 하는 서버 팩토리·DI에서는 위 생성자 프로필을 명시해야 합니다.
  이 설정을 모델이 결정하거나 새 HTTP 인자로 입력받게 하지 않았습니다.
- 프로필은 tuple/list를 검증한 뒤 tuple로 고정합니다. 중복·잘못된 자료형·지원하지 않는 코드가 있으면
  INVALID_WARNING_LOG_POLICY로 즉시 거부하며 무로그 정책으로 조용히 바꾸지 않습니다.
- 현재 지원하는 경고 이벤트는 ANALYSIS_COMPLETED와 INSPECTION_COMPLETED입니다.
  다른 장비 이벤트를 지원한다고 주장하지 않으며, 별도 계약이 필요하면 명시적으로 확장·검증해야 합니다.
- 요구 코드를 조사 user 목표와 최종 서버 근거 패킷에 전달하여 모델도 실제 로그를 선택하도록 안내합니다.
  요구 로그가 없거나 DATA_UNAVAILABLE이면 조기 종료하지 않으며 최종 경고 coverage도 실패합니다.
- 선택 로그가 없다는 이유만으로 결과·품질 근거가 충분한 보고서를 실패시키지는 않습니다.
  모델이 선택 로그나 추가 이력까지 조회한 경우 조기 종료는 보수적으로 유지하되,
  최종 검증에서 유효한 추가 이력 또는 선택 로그 DATA_UNAVAILABLE를 필수 로그 누락과 구별합니다.
  성공하지 않은 로그를 tools_used에 넣거나 실제 이벤트로 만들어 내지 않습니다.

### 조사 종료와 최종 보고서 검증의 분리

최종 단순 JSON → 엄격한 파싱 → 카탈로그 토큰 매핑 → 기존 DiagnosisDraft/Pydantic →
기존 Evidence ID/JSON Pointer/실제 값/가설·권고 참조/저장 판정 검증을 그대로 수행합니다.
그 검증을 통과한 뒤, 위 경고 프로필에 해당하는 보고서에는 다음 coverage를 추가 적용합니다.

- 품질 도구의 경고 상태와 mean/std/min/max가 실제 관측 사실로 선택돼야 합니다.
- threshold_status가 포함돼야 하며 RECORDED이면 실제 low/high도 포함돼야 합니다.
  NOT_RECORDED이면 기존 MISSING_BRIGHTNESS_THRESHOLDS 한계를 유지합니다.
- 필수 이벤트는 각 실제 로그 행의 source_event와 stage 및 timestamp가 함께 선택돼야 합니다.
  서로 다른 행의 stage와 timestamp를 섞어 조건을 충족시키지 못하게 합니다.
- 두 생명주기 이벤트가 모두 필수이면 실제 시각의 역전도 거부합니다.
  같은 타임스탬프만으로 물리적 발생 순서를 확정하지 않습니다.
- Evidence가 없거나 필수 설명이 누락되면 EVIDENCE_MISMATCH로 거부합니다.
  관측값·기준·이벤트·참조를 자동 보충하거나 재요청하지 않습니다.

기존 nullable/과거 기록의 검증은 유지하며 경고 추가 검사는 명시된 완료·모델 OK·품질 경고 프로필에 한정합니다.
순수 종료 조건을 최종 충분성 검사로 그대로 재사용하지 않고, 최종 보고서에서는 이미 수집한 유효한 추가 이력과
선택 로그 부재를 허용하도록 분리했습니다. 이는 기존 유효한 조사 결과를 불필요하게 거부하지 않기 위한 차이입니다.

### Mock 검증과 실제 실행 결과

| 검증 | 실제 결과 |
|---|---|
| 신규 운영 통합/HTTP 테스트 | **30 passed**, 경고 1건, 4.78초 |
| 기존 정책 실험 회귀 | **65 passed**, 경고 1건, 4.50초 |
| 모든 Agent 테스트 | **556 passed**, 경고 1건, 8.86초 |
| 전체 pytest | **661 passed**, 경고 3건, 23.05초 |
| pip check | No broken requirements found |
| git diff --check 및 신규 파일 공백 검사 | 오류 없음 |
| 실제 Gemini API / SDK 전송 시도 | **0회 / 0회** |

기준 631개와 신규 30개가 모두 통과했습니다. 기존 테스트는 삭제하거나 skip하지 않았습니다.
초기 관련 회귀의 경고 Mock 7개는 품질 조회·밝기 설명이 없거나 구형 종료 응답을 전제해 실패했습니다.
실제 새 계약에 맞게 품질 조회와 필수 관측을 명시하고, 경고 3요청/오류 기존 경로를 구분하여 해결했습니다.
서버 검증을 완화하거나 실패를 성공으로 바꾸지 않았습니다.

실행은 vision-insight Python의 pytest.main()으로 신규 파일, 모든 test_agent*.py, 전체 tests를 각각 지정했습니다.
인자는 `-q -p no:cacheprovider --tb=short --disable-warnings --basetemp <새 임시 폴더>`이며
검사/로그/출력 경로를 임시로 격리하고 공개 fixture만 복사했습니다. SDK sync/async 전송은 차단했습니다.

| Mock 시나리오 | 동작 |
|---|---|
| T01 정상 / T06 저장 OK | 기존 1도구·2모델 요청, 경고 분기 미적용 |
| T03 기본 경고 | 결과 → 품질 → 독립 최종 JSON, **3모델 요청** |
| T03 필수 로그 | 결과 → 품질 → 실제 로그 → 최종 JSON, **4모델 요청** |
| T03 밝기·기준·필수 이벤트 누락 | 보고서 거부, HTTP 502 / EVIDENCE_MISMATCH |
| T05 실행 실패 | 기존 실패 조사·로그 경로 유지, 제품 UNKNOWN / 종합 ERROR 보존 |
| 최종 Gemini 504 / timeout | 기존 안전한 오류·HTTP 매핑, 자동 재시도 없음 |

실제 AgentService와 FastAPI Mock 통합에서 토큰/JSON Pointer 변조, 없는 근거, 부적절한 가설·권고,
검사 ID·판정 변경, 필수 로그 누락·시각 역전, 선택 로그 부재·추가 이력, 호출/라운드/시간 제한을 검증했습니다.
새 스키마를 만들지 않았으며 최종 전송 스키마는 기존 단순 JSON 계약 그대로입니다.

### 데이터 보호와 다음 단계

운영 JSONL 두 파일·체크포인트·모델 메타데이터 및 schemas/tools/api/diagnostics/config의
총 9개 보호 파일은 전후 SHA256이 모두 동일했습니다. 고정 임계값 34.1442도 그대로입니다.
원본 데이터를 수정하거나 평가 Ground Truth 조회 경로를 추가하지 않았고 API 키·실제 요청 본문·서명 원문을 출력하지 않았습니다.
기존 사용자 변경 및 별도 design 작업은 그대로 보존했습니다.

운영 통합과 오프라인 검증은 완료됐지만 **새 경고 종료 정책의 실제 T03 E2E는 NOT TESTED**입니다.
세 번째 조사 요청을 생략할 수 있는 정책 개선이지 서버 504의 내부 원인을 해결한 것이 아닙니다.
실제 모델이 품질·필수 이벤트를 선택하고 최종 필수 사실을 모두 포함할지, 최종 요청의 지연·비용은 미검증입니다.
기본 순차 선택의 Mock 기대 요청 수는 3회지만 실제 호출 수나 성공률을 보장하지 않습니다.

별도 실서버 승인을 받기 전 수동 계측기는 기존 정상 predicate만 보지 않고 새 `_investigation_ready()`의
경고 종료 판단도 확인하도록 오프라인 점검해야 합니다. 기존 호출·시간 제한과 단일 승인 회차를 유지해야 합니다.
이번에는 실제 T03/T05/T06 분석·추가 Gemini 호출·Step 5·기능 개발·배포·Git add/commit/push 없이 중단합니다.

## T03 경고 조건부 조사 종료 적용 후 실제 E2E 재검증 — 2026-10-16

### 승인 범위와 사전 점검

사용자 승인에 따라 `INSP-001398` 분석을 정확히 한 번 수행했습니다.
기존 FastAPI `POST /analyze/INSP-001398`를 IN_PROCESS_ASGI 전송으로 실행했으며,
외부 Gemini 요청은 실제 Developer API / v1beta로 전송했습니다.
모델은 `gemini-3.8-flash`, SDK는 `google-genai==2.31.0`을 유지했습니다.
운영 코드·출력 스키마·모델 설정은 수정하지 않았습니다.

실행 전 네트워크를 차단한 사전 점검이 PASS했습니다. API 키는 존재 여부만 확인했습니다.
필수 이벤트 로그 설정은 빈 튜플 `()`로, 이번 밝기 경고에서 추가 로그를 강제하지 않습니다.
저장 판정 `OK / REINSPECT / IMAGE_QUALITY_WARNING`, 품질 상태 `WARNING_LOW_BRIGHTNESS`,
mean `81.24`, std `55.79`, 당시 기준 `NOT_RECORDED` 및 기준값 null을 확인했습니다.
두 실제 조회 결과를 대상으로 한 오프라인 종료 판단도 true였습니다.

제한은 조사 4라운드, 도구 실행 8회, 동일 호출 2회, 전체 분석 60초,
모델 요청 15초, 도구 대기 3초를 유지했습니다. SDK attempts=1 및 HTTP transport retries=0입니다.
기존 실패 회차의 잠금·결과는 보존하고 새 `t03_operational_warningstop1` 회차를 사용했습니다.

### 실제 Gemini 요청별 결과

분석 시작 계측 시각은 `2026-10-16T02:19:16.986670+00:00`입니다.
아래 시간은 HTTP 전송 계층의 경과 시간이며 SDK 계층 시간과 구분합니다.

| 요청 | 단계 | HTTP | HTTP 시간(ms) | SDK 시간(ms) | 입력 | 출력 | Thinking | 총 토큰 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | Function Calling | 200 | 1928.110 | 1942.303 | 1226 | 28 | 103 | 1357 |
| 2 | Function Calling | 200 | 3687.144 | 3690.132 | 1640 | 28 | 422 | 2090 |
| 3 | 독립 최종 단순 JSON 생성 | 504 | 14153.648 | 14155.110 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

실제 Gemini HTTP 전송은 **3회**, SDK 요청도 3회였습니다. 분석 시도와 FastAPI POST는 각각 1회입니다.
자동 재시도·모델 변경·추가 분석은 수행하지 않았습니다.
확인된 부분 사용량은 입력 2866 / 출력 56 / Thinking 525 / 합계 **3447토큰**입니다.
실패한 세 번째 요청의 사용량이 없어 전체 사용량과 실제 비용은 UNKNOWN입니다.
전체 HTTP 분석 실행 시간은 **19903.203ms (19.903초)**입니다.

### 실제 도구 실행과 종료 정책

| 순서 | Trace 라운드 | Gemini가 선택한 Python 도구 | executed | success | Evidence | 도구 시간(ms) |
|---|---:|---|---|---|---|---:|
| 1 | 1 | get_inspection_result | true | true | E0001 | 2.004 |
| 2 | 2 | analyze_image_quality | true | true | E0002 | 2.598 |

첫 조사 후 종료 판단은 CONTINUE였고, 두 번째 조회 후에는
`ready=true / policy=WARNING / trace_round=2 / E0001,E0002`를 기록했습니다.
즉 Gemini의 실제 도구 선택 후 서버의 경고 조건부 종료가 적용됐습니다.
추가 로그·이력 조회와 세 번째 조사/종료 확인 요청은 생략됐습니다.
세 번째 외부 요청은 추가 조사가 아니라 **최종 보고서 생성 요청**입니다.

두 번째 조사 요청에서 첫 모델 Content 재사용, FunctionResponse의 user 역할 및 호출 ID 일치,
Part 경계와 thought signature 보존을 확인했습니다. 서명 원문은 기록하지 않습니다.
최종 요청에는 Function Calling 이력·tools·tool_config 없이 신뢰된 근거 카탈로그와 최소 Trace를 전달했습니다.
HTTP 사전 존재 확인까지 포함한 Python 조회 함수 호출은 3회지만, Agent의 실제 도구 실행은 2회입니다.
`tools_used`는 위 두 도구뿐이며 Trace 라운드는 `[1, 2]`입니다.

### 실패 단계와 검증 도달 여부

최종 FastAPI 응답은 **HTTP 502**, Agent 상태는 **FAILED**,
오류 코드는 **GEMINI_REQUEST_FAILED**입니다.
실패 요청은 3번, 실패 단계는 **STRUCTURED_OUTPUT**입니다.
안전한 SDK 진단은 HTTP 504 / `DEADLINE_EXCEEDED` / `ServerError`, reason UNKNOWN,
field violations는 빈 목록입니다. 서버 내부의 정확한 504 원인은 여전히 UNKNOWN입니다.
모든 관측된 모델 요청과 전체 실행은 설정된 시간·호출 제한 안에서 끝났습니다.

| 항목 | 결과 |
|---|---|
| 실제 Function Calling 및 Python 조회 | PASS |
| 경고 조건부 조사 종료 | PASS |
| E0001/E0002 확보 | PASS |
| 최종 단순 JSON 응답 생성 | FAIL — 외부 요청 HTTP 504 |
| JSON 파싱·단순 스키마 검증 | NOT TESTED |
| DiagnosisDraft 변환·Pydantic 검증 | NOT TESTED |
| 최종 관측 사실의 Evidence ID / JSON Pointer 결정적 검증 | NOT TESTED |
| 최종 밝기 설명·가설·권고의 진단 품질 | NOT TESTED |
| 전체 T03 E2E | **FAIL** |

실제 조회에서 밝기값과 당시 기준 미기록 사실을 확보했지만, 최종 보고서는 생성되지 않았으므로
보고서가 이를 정확히 반영했거나 근거 없는 장비 고장을 배제했다고 주장하지 않습니다.
Evidence 확보와 최종 보고서 근거 검증의 성공은 구별합니다.

### 데이터 보호 및 다음 경계

검사 JSONL·이벤트 JSONL·PatchCore 체크포인트·모델 메타데이터의 전후 SHA256이 모두 동일했습니다.
쓰기가 차단된 운영 저장소에 대한 write_attempts는 0이었습니다.
저장 판정 `OK / REINSPECT / IMAGE_QUALITY_WARNING`과 고정 임계값 `34.1442`는 보존했습니다.
실패 응답에는 원본 판정 필드가 없으므로 반환 판정 일치 검사는 NOT TESTED이며,
이는 저장 판정이 변경됐다는 뜻이 아닙니다. 저장 데이터 불변은 파일 해시로 확인했습니다.

운영 코드와 스키마 수정은 없으며 기존 사용자 변경사항을 보존했습니다.
이번 실행에서는 pytest를 재실행하지 않았습니다. 이전 Mock 138개 및 전체 661개 통과는 과거 결과입니다.
API 키·내부 프롬프트·원본 경로·평가 정답·서명 원문은 공개하지 않았습니다.

이번 정책은 추가 조사를 생략하는 데 실제로 성공했으나 최종 모델 요청의 지연을 해결하지는 못했습니다.
다음 권장 작업은 별도 승인하에 최종 요청의 timeout/504를 오프라인 분석하는 것입니다.
시간 제한 확대·운영 코드 변경·추가 실서버 재호출은 이번 회차에서 수행하지 않았습니다.
T01/T05/T06 분석, Step 5 및 Git add/commit/push 없이 중단합니다.

## T03 최종 JSON 504 오프라인 비교 분석 — 2026-10-16

### 범위와 관측/재구성의 구분

이번 작업의 실제 Gemini API 요청은 **0회**입니다. T03 분석 API를 재실행하지 않았습니다.
운영 AgentService·reporting·investigation·prompts 및 모델/SDK/설정은 수정하지 않았습니다.
과거 T01 성공 결과와 T03 warningstop1 실패 결과의 허용된 계측 항목을 비교했습니다.
완전한 과거 요청 본문 스냅샷은 보관되지 않았으므로 당시 요청의 정확한 바이트 수·프롬프트 동일성은 UNKNOWN입니다.

크기 비교는 현재 코드와 같은 두 검사 ID의 읽기 전용 조회 도구로 Evidence를 재구성한 값입니다.
SDK 생성/전송 함수는 차단하고 실제 `_generate()`에는 주입된 로컬 capture 더블을 사용했습니다.
`analyze()`나 FastAPI 분석 엔드포인트는 호출하지 않았으며, 기록/로그/원본 이미지/정답의 조회 범위를 확장하지 않았습니다.
T01은 결과 조회만, T03은 결과 및 품질 조회만 재구성했습니다.
이 값은 과거 실제 전송 본문 또는 모델 토큰 수의 복원 결과가 아닙니다.

### T01과 T03 최종 요청 비교

| 항목 | T01 현재 코드 재구성 | T03 현재 코드 재구성 |
|---|---:|---:|
| 모델 / 설치 SDK | gemini-3.8-flash / 2.31.0 | 동일 |
| response_mime_type | application/json | 동일 |
| 응답 스키마 | 단순 5필드 response_json_schema | 동일 |
| 공백 제거 직렬화한 스키마 UTF-8 크기 | 419바이트 | 419바이트 |
| 최종 system_instruction 문자 수 | 2973 | 2973 |
| user 텍스트 문자 수 / UTF-8 바이트 수 | 3694 / 3694 | 5436 / 5436 |
| Evidence ID 수 / 카탈로그 항목 수 | 1 / 20 | 2 / 29 |
| 최소 Trace 항목 수 | 1 | 2 |
| source_field와 값이 같은 카탈로그 쌍의 반복 수 | 0 | 8 |
| SDK 변환 결과를 compact JSON으로 인코딩한 크기 | 7858바이트 | 9800바이트 |
| max_output_tokens | 4096 | 4096 |
| thinking_config / thinking budget 명시 | 없음 | 없음 |
| 요청 timeout / retry attempts | 15000ms / 1 | 동일 |
| 최종 Content 역할·Part | user 1개, text Part 1개 | 동일 |
| tools / tool_config / FC 이력 | 없음 | 없음 |

SDK 변환 크기는 요청 객체의 비교용 인코딩이며 인증 헤더를 포함한 실제 HTTP wire 크기가 아닙니다.
두 스키마의 SHA256도 동일했습니다. 직렬화는 성공했으나 실서버 수락/속도는 이번에 검증하지 않았습니다.
카탈로그는 token/evidence_id/source_tool/source_field/observed_value/source_event의 같은 필드 구조입니다.
Trace는 실행·도구·Evidence 식별용이며 관측값 전체를 중복 저장하지 않습니다.
T03의 반복 값 8쌍은 검사 결과와 품질 조회에 공통으로 존재하는 정보이며 서로 다른 출처입니다.
단순히 중복이라는 이유로 삭제하면 필수 품질 도구 출처와 JSON Pointer 검증을 잃을 수 있으므로 삭제하지 않았습니다.

최종 system_instruction은 두 시나리오에서 같은 템플릿을 사용하며,
T03에서는 조건에 따라 품질 상태, mean/std/min/max, threshold_status를 추가 선택해야 합니다.
NOT_RECORDED를 유지하고 현재 설정을 당시 기준으로 대체하면 안 됩니다.
기본 프로파일의 required_warning_event_codes는 빈 튜플로, 이번에는 이벤트 단계/시각을 강제하지 않습니다.
별도의 완성된 T03 응답 예시는 없고 필드·코드 목록과 CODE:K토큰 형식 지시가 있습니다.
서버 내부의 자유 서술 보고서 대신 이미 단순화된 코드/토큰 선택 출력입니다.
Thinking 수준/예산을 명시하지 않았으므로 실제 서버의 기본값과 T03 실패 요청의 Thinking 사용량은 UNKNOWN입니다.

과거 T01 최종 생성 요청은 SDK 계층 10528.745ms, 입력 1963 / 출력 97 / Thinking 1375 / 총 3435토큰으로 성공했습니다.
T03 최종 생성 요청은 HTTP 계층 14153.648ms, SDK 계층 14155.110ms에 504로 실패했습니다.
T03 실패 요청의 토큰 수는 없으므로 입력 증가가 추론량·지연을 얼마나 늘렸는지는 계산할 수 없습니다.

### 시간 제한 계층과 새로 확인한 SDK 동작

설치된 SDK 2.31.0 구현에서 HttpOptions.timeout은 밀리초이며 15000을 HTTPX의 15초로 변환합니다.
또한 `_build_request()`는 `populate_server_timeout_header()`를 호출하여
기존 헤더가 없으면 **X-Server-Timeout: 15**를 생성합니다.
오프라인 테스트로 변환과 헤더 생성, 기존 값이 있으면 덮어쓰지 않는 동작을 확인했습니다.
과거 실제 헤더 전체는 수집하지 않았으므로 당시 헤더 관측 사실과 현재 SDK의 기본 생성 동작은 구분합니다.

| 계층 | 코드에서 확인된 설정·동작 |
|---|---|
| Gemini 응답 | 실제 HTTP 504 / DEADLINE_EXCEEDED / ServerError; reason UNKNOWN |
| SDK HTTP | HttpOptions 15000ms → HTTPX 15초, 기본 서버 timeout 헤더 15초 |
| 모델 요청 | asyncio.wait_for 15초, 로컬 만료는 GEMINI_TIMEOUT |
| Agent 전체 | asyncio.timeout 60초, 로컬 만료는 AGENT_TIMEOUT |
| 수동 계측기 | 1개 ASGI POST, SDK 요청 상한 6 및 단일 회차 잠금; 별도 강제 wall-clock timer 없음 |
| 계측기 PASS 판단 | 전체 측정 시간 60000ms 미만을 검사하는 사후 조건 |
| FastAPI | 분석 라우트에 추가 timeout middleware 없음; 이번 실행은 소켓 서버가 아닌 ASGITransport |
| 재시도 | SDK attempts=1, 명시적 HTTPX transport retries=0 |

Agent의 60초는 `_run()`을 감싸며 HTTP 사전 조회/지연 초기화 및 종료 처리 전체를 강제하는 별도 API timer가 아닙니다.
이번 계측 시간 19.903초와 모델 요청 14.154초는 각각 60초와 15초보다 작습니다.
HTTPX 로컬 timeout만으로 만들어진 실패가 아니라 실제 HTTP 504가 반환됐다는 점이 중요합니다.
그러나 14.154초라는 시간만으로 서버 deadline의 정확한 작동 시점·내부 원인을 확정할 수 없습니다.

공식 참고: [Google Gen AI SDK 문서](https://googleapis.github.io/python-genai/).
문서 일반 설명보다 해당 환경에 설치된 2.31.0의 변환·헤더·전송 구현을 우선 확인했습니다.

### 원인 후보와 판단

확인된 사실은 T03의 최종 입력/필수 선택 사실이 더 많다는 점, Thinking 예산을 명시하지 않는다는 점,
HTTP timeout이 SDK 기본 서버 timeout 헤더 생성에도 쓰인다는 점입니다.
가능한 가설은 서버 처리/대기 지연, 추가 토큰 선택·근거 조합에 필요한 생성 시간,
SDK가 요청한 deadline과 서버/중간 게이트웨이 deadline의 상호작용입니다.
이 중 어느 것도 실제 서버의 504 원인으로 입증되지 않았습니다.
64KiB 로컬 컨텍스트 제한 초과나 FC 이력 잔존, 추가 조사 반복이 이번 최종 요청 실패 원인이라는 증거는 없습니다.
과거 복잡한 D 스키마의 400 문제와 이번 단순 스키마의 504를 같은 원인으로 취급하지 않습니다.

### 별도 실험 모듈과 개선안 비교

새 `scripts/agent_final_request_experiment.py`는 운영 코드에 연결되지 않습니다.
현재 코드의 최종 설정을 로컬에서 capture하고 메타데이터만 산출하며,
별도 후보로 user JSON의 공백만 제거합니다. 카탈로그·토큰·값·Trace·스키마·지침은 제거하지 않습니다.
공백 제거 전후 JSON 객체가 동일하고 기존 변환/Pydantic/Evidence 검증이 유지되는지 확인했습니다.

| 후보 | 이점 | 제한·승인 경계 |
|---|---|---|
| A 기존 요청 유지·관찰 | 운영 변경 없음, 현상 분리 용이 | 새 유료 요청 승인 필요; 일시적 서버 지연인지 단일 결과로 판별 불가 |
| B 입력 중복/설명 축소 | 컨텍스트 감소 가능 | 공백 제거만 안전한 Mock 후보로 구현; 출처 중복 삭제·지침 재작성은 별도 설계/승인 필요 |
| C 출력 단순화 | 이미 5필드 코드/토큰 방식 | 필수 6개 core+6개 품질 사실 유지 필요; 구조 축소만으로 개선된다는 근거 없음 |
| D timeout 재검토 | HTTP/서버 헤더/로컬 deadline 관계 명확화 | 무조건 확대·재시도 금지; 변경 실험은 별도 승인 필요 |

공백만 줄인 비교값은 T01 user 3694→3439바이트, SDK 변환 결과 7858→7603바이트,
T03 user 5436→5061바이트, SDK 변환 결과 9800→9425바이트입니다.
이는 바이트 감소만 입증하며 토큰·지연·비용 개선이나 504 해결은 NOT TESTED입니다.
추천은 운영을 그대로 두고 안전한 deadline 메타데이터와 최종 생성 부담을 우선 구분하는 것입니다.
운영 최적화 승인을 받는다면 의미가 같은 공백 축소부터 검토할 수 있지만 기대 효과는 제한적입니다.

### Mock·회귀 테스트와 한계

신규 `tests/test_agent_final_request_experiment.py` **15개 PASS**:
정상/경고 최종 설정 비교, Evidence·입력 증가, 공백 후보의 변환/검증,
NOT_RECORDED 유지, 필수 품질 사실 누락 거부, 가짜 토큰 거부, 판정 보존,
SDK timeout/header 변환, 서버 504/로컬 모델 timeout/전체 timeout 구분을 확인했습니다.
SDK sync/async 요청·실제 클라이언트·기본 HTTP 전송은 테스트에서 차단했습니다.
Mock 504는 오류 처리 재현이며 실제 서버 내부 실패 원인 재현이 아닙니다.

최종 관련 108개 실행은 **107 PASS / 기존 초단기 deadline 테스트 1 FAIL**이었습니다.
실패는 `test_agent_efficiency.py::test_final_request_keeps_model_and_overall_deadlines`의
20ms 전체 timeout 사례에서 기대 AGENT_TIMEOUT 대신 GEMINI_TIMEOUT을 받은 것입니다.
동일한 기존 deadline 사례 2개를 분리 재실행하면 2 PASS였으며,
신규 15개와 기존 경고 정책 HTTP 통합 30개도 재확인 시 **45 PASS**였습니다.
앞선 신규/요청/효율/계측 묶음 78개 실행은 78 PASS였습니다.
초단기 취소 타이밍의 비결정성은 미해결 위험으로 남기며 전체 회귀 PASS로 표현하지 않습니다.
테스트 작성 중 Pydantic limits와 비동기 Mock fixture 사용 오류는 테스트 코드에서 수정했습니다.
운영 timeout 처리나 검증은 변경하지 않았습니다.

실행 명령은 vision-insight Python의 `-m pytest`에 위 5개 관련 파일과
`-q -p no:cacheprovider --basetemp data/outputs/manual_validation/offline_final_request_regressions_20261016`을 지정했습니다.
분리 재확인은 deadline 테스트 2개 및 신규/경고 통합 파일을 지정했습니다.
`python -m pip check`는 정상입니다. 이번에는 전체 pytest를 실행하지 않았습니다.
공백 검사는 오류 없이 통과했습니다(기존 LF/CRLF 경고 별도).

### 보호와 다음 승인 사항

운영 service/reporting/investigation/prompts, 운영 JSONL 두 개, 체크포인트·메타데이터의
총 8개 파일 SHA256은 전후 동일했습니다. 기존 사용자 변경·design/presentation 작업도 보존했습니다.
평가 정답은 읽지 않았고 API 키·프롬프트 전문·원본 경로·서명·원시 헤더는 출력하지 않았습니다.

다음 승인된 실서버 실험에서는 최종 요청 단계의 HTTP 시간, SDK 시간, 허용된 timeout 숫자,
설정 존재 여부, 성공 시 입력/출력/Thinking 사용량을 우선 확인해야 합니다.
새 계측의 운영 연결, 입력 공백/지침 최적화, 출력 예산·Thinking/timeout 변경 및
실제 Gemini 요청은 각각 별도 사용자 승인이 필요합니다.
T03 재실행·T05/T06 분석·Step 5·Git add/commit/push 없이 오프라인 분석을 종료합니다.

## 최종 JSON 요청별 timeout 후보의 오프라인 검증 — 2026-10-16

### 범위와 SDK 근거

이번 작업은 실험 모듈·테스트·본 문서만 변경했습니다. 실제 Gemini 요청은 **0회**이며,
운영 timeout 설정 변경과 T03 실서버 재검증은 수행하지 않았습니다.
설치 버전은 `google-genai==2.31.0`이고 모델/Developer API/v1beta는 유지했습니다.
SDK 생성 및 모델 호출을 사용한 테스트도 모두 가짜 키·합성 입력·HTTPX MockTransport에서만 실행됐습니다.
실제 기본 sync/async HTTP transport는 차단했습니다.

설치된 `_api_client.py`와 [공식 SDK v2.31.0 구현](https://github.com/googleapis/python-genai/blob/v2.31.0/google/genai/_api_client.py)을 대조했습니다.
공식 호출별 설정 수단은 `GenerateContentConfig(http_options=HttpOptions(timeout=...))`입니다.
SDK `_build_request()`는 클라이언트 기본 HttpOptions와 호출별 HttpOptions를 `patch_http_options()`로 병합합니다.
호출에 명시한 non-null timeout이 기본값보다 우선하며, 헤더는 딕셔너리 병합됩니다.
요청 timeout은 밀리초에서 초로 변환되어 HTTP transport로 전달됩니다.
`populate_server_timeout_header()`는 해당 초 값을 올림해 X-Server-Timeout에 넣지만 이미 있는 값은 덮어쓰지 않습니다.

단일 클라이언트에서 호출별 timeout 분리가 가능합니다. 테스트에서 기본 15000ms인 동일 클라이언트로
호출 설정을 15000→30000→15000ms로 변경했을 때 다음을 확인했습니다.

| 전송 경로 | Mock 호출 수 | X-Server-Timeout | HTTPX read timeout | 기본 클라이언트 timeout |
|---|---:|---|---|---|
| sync 실제 SDK → MockTransport | 3 | 15 → 30 → 15 | 15 → 30 → 15초 | 15000ms 유지 |
| async 실제 SDK → MockTransport | 3 | 15 → 30 → 15 | 15 → 30 → 15초 | 15000ms 유지 |

이는 실제 SDK의 요청 생성·직렬화·헤더·transport 진입을 검증한 것이며 Gemini 서버 deadline 동작 검증은 아닙니다.
HTTP transport timeout은 로컬 연결/읽기 등 대기 제한이고, 서버 헤더는 서버에 전달하는 시간 예산입니다.
서버가 그 예산을 어떻게 적용했는지, 과거 14.154초 504를 왜 반환했는지는 여전히 UNKNOWN입니다.
sync/async의 옵션 병합은 공통이며, 이번 async 검증은 실제 수동 계측기와 같은 HTTPX 분기를 강제했습니다.
aiohttp 분기는 설치 SDK에서 ClientTimeout(total=...)을 사용하는 것을 확인했으나 이번 Mock 전송 검증 대상은 아닙니다.

주의: 기본/사용자 헤더에 X-Server-Timeout: 15를 고정하면 호출별 HTTP timeout을 30000으로 바꿔도
헤더가 15로 유지될 수 있습니다. 이 동작도 별도로 테스트했습니다.
실제 통합에서는 전역 클라이언트 설정을 요청마다 변경하지 말고 호출별 옵션을 사용해야 합니다.
별도 클라이언트는 필요하지 않으며, 사용할 경우 인증·재시도·연결 풀·async/sync 종료 수명주기를 각각 관리해야 합니다.

### A/B/C 실험 정책

운영 API가 import하지 않는 `scripts/agent_timeout_policy_experiment.py`를 추가했습니다.
`TimeoutPolicy`가 시간 예산을 계산하고 `ExperimentalTimeoutAgent` 테스트 서브클래스가 기존
Function Calling·최종 JSON·Pydantic·Evidence 검증을 그대로 호출합니다.
운영 AgentService나 설정 클래스는 변경하지 않았습니다.

| 정책 | 조사 요청 | 최종 JSON | 전체 | 장점 | 위험·난이도 |
|---|---|---|---|---|---|
| A 현행 명목값 | 15초 | 15초 | 60초 | 최소 지연 상한, 변경 없음 | 최종 생성에 부족한지 실서버에서 미확정 |
| B 단계 분리 후보 | 15초 | 30초 | 60초 | 조사 제한 유지, 최종 생성 예산만 분리 | 늦은 최종 진입 시 전체 제한과 충돌; 긴 대기·자원 점유 가능 |
| C 남은 예산 후보 | 15초 유지, 부족하면 차단 | min(후보 상한 30초, 남은 시간−여유) | 60초 | 전체 예산·후처리 여유를 고려 | monotonic 기준·예산 고갈 오류 처리 추가 필요 |

30초는 후보일 뿐 최적값이나 해결책이 아닙니다. 여유 2초도 실험 정책 파라미터입니다.
테스트 모듈은 A/B에도 공통 사전 예산 guard를 두어 남은 안전 예산보다 긴 요청은 차단합니다.
이는 현행 운영 A가 이미 사전 guard를 가진다는 의미가 아니며, 현행은 주로 전체 asyncio.timeout에 의존합니다.
C의 조사 요청은 15초를 임의 축소하지 않고 예산 부족 시 차단하며, 최종 요청만 남은 예산에 맞춰 축소합니다.
정수 초로 내림하여 SDK 서버 헤더의 올림 때문에 안전 여유를 넘지 않도록 했습니다.

실험 예: 경과 45.2초, 전체 60초, 여유 2초이면 최종 timeout은 12초이며
SDK 호출 옵션도 실제로 12000ms가 됩니다. 경과 59초이면 최종 모델 호출 전에 AGENT_TIMEOUT으로 중단합니다.
전체 60초, 도구/라운드/동일 호출 제한은 유지합니다. 호출 후 원래 limits 객체가 복원되는 것도 확인했습니다.
서브클래스의 일시적 limits 변경은 요청 전용 실험 구현이며 운영 구현 패턴으로 자동 채택하지 않습니다.
운영화 시에는 요청별 지역 변수로 산출한 동일 timeout을 SDK 옵션과 asyncio.wait_for 양쪽에 전달해야 합니다.
SDK만 30초로 바꾸고 기존 wait_for 15초를 남기는 방식은 올바른 분리가 아닙니다.

모든 호출에 retry attempts=1을 유지했습니다. 전송 timeout 확대와 재시도 활성화는 별개입니다.
후보 B/C는 요청 수나 출력 상한을 늘리지 않지만, 실서버 처리·Thinking·비용 영향은 미검증입니다.

### 20ms 테스트 안정화

기존 5ms 모델/20ms 전체 deadline 테스트는 검사 조회·스레드 대기·직렬화 시간까지 실제 wall-clock으로
함께 측정해 최종 생성 진입 전에 취소되거나 deadline 순서가 달라질 수 있었습니다.
과거 GEMINI_TIMEOUT/AGENT_TIMEOUT 차이를 일으킨 정확한 런타임 취소 인터리빙은 재구성할 수 없어 UNKNOWN입니다.
이것은 실서버 HTTP 504의 원인으로 확인된 문제가 아닙니다.

새 `tests/agent_deadline_control.py`는 실제 asyncio timeout/wait_for의 콜백을 기록하고,
최종 Mock 생성 함수가 진입한 뒤 선택한 deadline 콜백을 명시적으로 발동합니다.
실제 경과 시간/짧은 sleep에 의존하지 않으며 15초/60초 기본값으로 오류 매핑을 확인합니다.
`tests/test_agent_efficiency.py`의 두 테스트와 직전 실험 테스트의 단기 sleep 사례를 이 방식으로 교체했습니다.
운영 이벤트 루프·timeout·AgentService는 수정하지 않았습니다.

테스트 helper는 Python 3.11 asyncio의 내부 콜백 이름을 사용하므로 Python 버전 변경 시 점검이 필요합니다.
콜백 제어는 취소 처리와 설정 연결의 결정적 테스트이지 실제 15초/60초 wall-clock 성능 시험은 아닙니다.
운영의 모든 취소 race를 해결했다고 주장하지 않습니다.

### 테스트 결과와 보호

| 검증 | 실제 결과 |
|---|---|
| 신규 timeout 후보 테스트 | **31 PASS** |
| 관련 timeout/최종 요청/효율/계측 테스트 | **82 PASS**, 5.08초 |
| 전체 pytest | **718 PASS**, 실패·건너뜀 0, 경고 2, 25.71초 |
| pip check | No broken requirements found |
| git diff --check 및 신규 파일 공백 검사 | 공백 오류 없음, LF/CRLF 경고 별도 |
| 실제 Gemini API 요청 | **0회** |

T01/T03/T05/T06 Mock 경로를 A/B/C 각각으로 검증했습니다.
정상/경고 종료, 기존 실패 조사, 단순 JSON 변환 및 Pydantic/Evidence 검증을 유지한 채
모델 요청 수는 각각 2/3/4/2회이며, 이는 Mock 시퀀스 결과이지 실서버 예상 보장이 아닙니다.
예산 부족/잘못된 clock 입력/서버 헤더 올림/기존 헤더 유지도 검증했습니다.

관련 실행은 vision-insight Python의 `-m pytest`에 신규 timeout, final_request_experiment,
efficiency, validation_measurements 파일과 `-q -p no:cacheprovider`를 지정했습니다.
전체 실행은 `pytest.main(['tests','-q','-p','no:cacheprovider','--basetemp',...])`를 사용하고,
검사/로그/출력/test_data 경로를 새 임시 작업 폴더로 분리했습니다.
공개 중립 PNG fixture만 복사했고 원본 이미지는 수정하지 않았습니다.
전체 테스트의 기존 이미지/PatchCore 회귀는 임시 저장소에서 실행됐으며 실제 Gemini 분석은 실행하지 않았습니다.
보호 운영 파일 쓰기는 audit hook으로 차단하고 실제 기본 HTTP transport도 차단했습니다.
경고 2개는 기존 timm/anomalib FutureWarning입니다.

운영 service/schemas/config/reporting/investigation, 운영 JSONL 2개, 체크포인트·메타데이터의
총 9개 파일은 전후 SHA256이 동일했습니다. 고정 임계값 34.1442와 기존 검사 기록은 보존했습니다.
평가 정답·API 키·인증 헤더·실제 요청 본문·서명은 출력하지 않았습니다.
기존 사용자 변경과 design/presentation 관련 파일도 그대로 보존했습니다.

### 추천과 승인 경계

최소 운영 변경 후보는 단일 클라이언트를 유지하면서 **단계별 timeout 선택 지점을 하나로 만들고**,
SDK 호출별 HttpOptions와 로컬 wait_for에 같은 값을 적용하는 것입니다.
최종 요청에는 C처럼 전체 남은 예산과 여유를 검사하는 방어를 함께 두는 편이 안전합니다.
기본값은 우선 현행 15초로 보존하고, 30초 상한은 별도 승인된 실험 값으로만 검토할 수 있습니다.
전체 60초와 재시도 비활성화는 유지해야 합니다.

운영 timeout 설정/예산 계산 연결은 별도 사용자 승인이 필요합니다.
그 뒤 T03 단일 실서버 재검증도 별도로 승인받아야 합니다.
이번 검증은 서버 504 해결·진단 성공·지연/비용 개선을 입증하지 않습니다.
실제 서버의 정확한 DEADLINE_EXCEEDED 원인은 여전히 UNKNOWN으로 유지합니다.
T03/T05/T06 실서버 호출·운영 통합·Step 5·Git add/commit/push 없이 중단합니다.

## Gemini 요청별 timeout 정책 운영 통합 및 Mock 회귀 — 2026-10-16

### 승인 범위와 변경 파일

이번 사용자 승인은 timeout 정책의 운영 연결과 오프라인 테스트에 한정됩니다.
실제 Gemini API 요청은 **0회**이며 T03/T01/T05/T06 실서버 분석은 실행하지 않았습니다.
기존 사용자 변경사항과 과거 실험 기록은 그대로 보존했습니다.

| 파일 | 이번 변경 |
|---|---|
| backend/config.py | 최종 JSON 전용 환경 설정 및 값 검증, fallback 설정 반영 |
| backend/agent/schemas.py | AgentLimits.final_model_timeout_seconds 추가 |
| backend/agent/service.py | 요청별 monotonic deadline, 단계별 timeout 선택, 호출별 헤더/SDK/wait_for 일치 |
| scripts/agent_timeout_policy_experiment.py | 실험 서브클래스가 새 최종 timeout 필드를 명시적으로 사용하도록 호환 수정 |
| tests/test_agent_operating_timeouts.py | 신규 운영 timeout·예산·공유 SDK 클라이언트 검증 |
| docs/day4-step4-gemini-validation.md | 본 결과 추가 |

공유 SDK 클라이언트 생성이나 FastAPI 응답 계약은 변경하지 않았습니다.
운영 서비스에서 실험 서브클래스를 import하거나 선택하지 않습니다.
단순 JSON 스키마·조회 도구·조사 종료·Evidence 검증 및 종합 판정 코드는 변경하지 않았습니다.

### 설정과 명시적 30초 후보 선택

| 항목 | 현재 기본값 / 제한 | 사용 위치 |
|---|---|---|
| AGENT_MODEL_TIMEOUT_SECONDS | 기존 15초 유지 | Function Calling 조사 요청 및 기본 클라이언트 |
| AGENT_FINAL_MODEL_TIMEOUT_SECONDS | **기본 15초**, 정수 1~30초 | 최종 단순 JSON 요청 전용 |
| AGENT_REQUEST_TIMEOUT_SECONDS | 기존 기본 60초 유지 | 요청별 Agent 전체 deadline |
| FINAL_REPORT_RESERVE_SECONDS | 2초 | 최종 요청 이후 검증 여유 |

새 최종 설정은 환경변수 또는 기존 Settings로 주입합니다.
예를 들어 **별도 승인된 실험을 준비할 때에만** 환경변수
`AGENT_FINAL_MODEL_TIMEOUT_SECONDS=30`을 명시할 수 있습니다.
PowerShell 예시는 `$env:AGENT_FINAL_MODEL_TIMEOUT_SECONDS = '30'`이며 이번에는 실행하지 않았습니다.
설정 캐시를 사용하므로 실행 중인 서버는 설정 재적용/재시작이 필요합니다.
HTTP 요청 본문이나 모델 도구 인자로 timeout을 선택하게 하지 않습니다.
직접 AgentService에 AgentLimits를 주입하는 테스트/내부 호출에서는 해당 limits가 우선합니다.

잘못된 0·음수·30 초과·소수·NaN/Infinity·bool·비수치 값은 Settings/AgentLimits에서 거부합니다.
환경변수 문자열 '30'은 Settings에서 정수로 변환하지만 AgentLimits는 정수 타입을 엄격히 요구합니다.
실제 로컬 설정을 값만 확인한 결과 **조사 15 / 최종 15 / 전체 60초**였습니다.
기본값, .env, 모델 ID, SDK 버전, 재시도 설정은 변경하지 않았습니다.

### 전체 예산과 단계별 선택

analyze() 진입 시 RequestState에 `time.monotonic() + request_timeout_seconds`의 deadline을 저장합니다.
기존 전체 asyncio.timeout에는 초기화에 소요된 시간을 뺀 나머지를 전달하므로 새 예산을 다시 부여하지 않습니다.
deadline은 요청별 상태에만 존재하며 외부 도구/모델/HTTP 응답에 포함하지 않습니다.
FastAPI 사전 검사 조회는 AgentService.analyze() 호출 전이므로 이 Agent 60초 범위 밖이라는 기존 경계는 유지합니다.

조사 요청은 기존 model_timeout_seconds를 유지하며, 남은 전체 예산보다 길면 전송 전에 AGENT_TIMEOUT으로 중단합니다.
최종 요청은 `min(final_model_timeout_seconds, floor(deadline - now - 2))`로 결정합니다.
가용 시간이 1초 미만이면 요청을 보내지 않고 AGENT_TIMEOUT으로 중단합니다.
정수 초로 내림하여 SDK 서버 헤더의 올림과 로컬 대기 시간이 어긋나지 않도록 합니다.

최종 상한 30초의 Mock 예시:
- 충분한 예산: 조사 15초 / 최종 30초.
- 45.2초 경과: 최종 요청은 12초로 축소하고 전체 60초는 유지.
- 58.1초 경과: 최종 요청 없이 AGENT_TIMEOUT.

기본 최종 상한 15초도 예산이 부족하면 같은 안전 제한을 적용합니다.
시간 제한을 분리하기 위해 서비스 공유 limits를 실행 중에 변경하지 않고 요청별 지역 변수 하나를 사용합니다.
전체 timeout·도구·호출 횟수·조사 라운드·반복 호출 제한을 확대하지 않았습니다.

### SDK HTTP / 서버 헤더 / 로컬 대기의 일치

선택한 timeout_seconds 하나를 다음에 모두 사용합니다.
- GenerateContentConfig.http_options.timeout: 초 × 1000ms.
- 호출별 headers의 X-Server-Timeout: 올림한 초 값.
- asyncio.wait_for: 같은 초 값.

호출별 표준 X-Server-Timeout 헤더를 명시하므로 기존 SDK 공통 헤더의 15가 최종 30을 가로막지 않습니다.
SDK가 공개 지원하는 HttpOptions 병합을 사용하며 내부 비공개 구현을 운영 코드에서 패치하지 않습니다.
기존 인증/사용자 지정 헤더를 지우거나 클라이언트 전역 설정을 변경하지 않습니다.
SDK retry attempts=1은 모든 요청에서 유지합니다.

실제 SDK와 HTTPX MockTransport를 연결한 운영 AgentService 테스트에서,
동일 클라이언트의 기본 헤더를 15로 둔 채 다음을 확인했습니다.

| 순서 | 단계 | HTTPX read timeout | X-Server-Timeout |
|---|---|---:|---:|
| 1 | 조사 | 15초 | 15 |
| 2 | 최종 JSON, 명시적 후보 | 30초 | 30 |
| 3 | 다음 분석의 조사 | 15초 | 15 |
| 4 | 다음 분석의 기본 최종 JSON | 15초 | 15 |

클라이언트 기본 헤더 15는 변하지 않았고 합성 Authorization 및 사용자 지정 헤더도 모두 보존됐습니다.
이 검증은 SDK가 생성하는 표준 이름의 X-Server-Timeout 헤더를 대상으로 합니다.
Mock HTTP 응답으로 보고서 변환·Pydantic·결정적 Evidence 검증까지 통과했습니다.
이는 실서버 deadline 동작이나 504 해결을 입증하지 않습니다.

### 테스트 결과

| 순서 | 실제 실행 | 결과 |
|---|---|---|
| 1 | python -m pytest tests/test_agent_operating_timeouts.py -q -p no:cacheprovider | **신규 34 PASS**, 4.86초 |
| 2 | 모든 tests/test_agent*.py, 외부 transport 차단·임시 저장소 | **647 PASS**, 9.88초 |
| 3 | 전체 tests, 외부 transport 차단·보호 쓰기 차단·임시 저장소 | **752 PASS**, 실패/건너뜀 0, 경고 2, 31.45초 |
| 4 | python -m pip check | 정상 |
| 5 | git diff --check 및 신규 파일 공백 검사 | 오류 없음, 기존 LF/CRLF 경고 별도 |

초기 신규 테스트는 DiagnosisResult에 HTTP 전용 필드가 있다고 가정하여 AttributeError가 발생했습니다.
실제 서비스 계약인 inspection_snapshot의 result/final_result/final_reason_code를 비교하도록 테스트만 정정했습니다.
판정 비교를 삭제하거나 검증을 완화하지 않았으며 해당 10개 시나리오도 모두 통과했습니다.

15초 기본/30초 opt-in 각각에서 T01 정상 종료, T03 경고 종료, 필수 로그 T03,
T05 실패 조사, T06 저장 정상 판정을 검증했습니다.
도구 실행·Evidence 연결·JSON 변환·Pydantic/결정적 검증·검사 판정 불변을 확인했습니다.
기존 초단기 deadline 대신 제어된 콜백을 사용하는 타이밍 테스트도 관련/전체 실행에서 통과했습니다.
실제 SDK 504의 기존 GEMINI_REQUEST_FAILED → HTTP 502 매핑과 재시도 없는 종료도 유지했습니다.
예산 고갈의 AGENT_TIMEOUT은 기존 HTTP 504 매핑을 그대로 사용합니다.

Agent/전체 실행은 vision-insight Python에서 pytest.main()을 호출하고
`-q -p no:cacheprovider --basetemp <회차별 임시 폴더>`를 사용했습니다.
검사/로그/출력/test_data 경로를 운영 경로와 분리하고 중립 공개 PNG fixture만 임시로 복사했습니다.
전체 테스트의 기존 Vision/PatchCore 검사도 임시 저장소만 사용했습니다.
실제 기본 sync/async HTTP transport를 차단했고 SDK MockTransport는 합성 입력/가짜 키만 사용했습니다.
경고 2건은 기존 timm/anomalib FutureWarning입니다.

### 보호와 실서버 재검증 경계

운영 검사/이벤트 JSONL, 모델 체크포인트/메타데이터,
tools/investigation/reporting/decision 총 8개 보호 파일의 전후 SHA256이 모두 동일했습니다.
고정 임계값 34.1442와 기존 T01/T03/T05/T06 기록을 보존했고 평가 정답은 읽지 않았습니다.
기존 사용자 변경사항·design/presentation 작업과 과거 잠금/실험 결과도 그대로 보존했습니다.

운영 timeout 통합과 오프라인 회귀 검증은 완료됐지만 실제 T03 최종 생성의 성공 여부는 NOT TESTED입니다.
과거 서버 DEADLINE_EXCEEDED의 정확한 내부 원인은 여전히 UNKNOWN입니다.
2초 여유는 방어 정책이며 CPU 블로킹이나 서버 생성 지연이 반드시 그 안에 끝난다는 보장은 아닙니다.
커스텀 transport·비표준 중복 헤더 설정은 별도 점검 대상입니다.

다음 T03 실서버 검증에는 **최종 상한 30초 사용 및 분석 1회에 대한 별도 승인**이 필요합니다.
승인 후 설정 재적용, 새 단일 회차 잠금 식별자, 실제 timeout/header 전파 사전 계측을 확인해야 합니다.
기존 t03_operational_warningstop1 잠금은 보존돼 있으므로 기존 회차를 재사용하면 안 됩니다.
이번 작업에서는 실제 API 호출·T03 재실행·T05/T06 분석·Step 5·배포·Git add/commit/push 없이 중단합니다.

## T03 최종 JSON 30초 실제 검증 사전 중단 — 2026-10-16

사용자가 `INSP-001398`의 실제 분석 1회를 승인했으나, 사전 점검에서 실행·계측 준비 문제가 발견되어
지시된 중단 조건에 따라 **실제 Gemini 요청 없이 중단**했습니다. E2E 결과는 **NOT TESTED**입니다.
분석 API POST 0회, AgentService.analyze() 실행 0회, 실제 Gemini HTTP 요청 0회입니다.
실험 실패나 새로운 서버 오류가 발생한 것으로 해석하지 않습니다.

### 확인한 항목

- 별도 Python 자식 프로세스 안에서만 AGENT_FINAL_MODEL_TIMEOUT_SECONDS=30을 설정했습니다.
- 해당 설정으로 생성한 운영 AgentService의 최종 timeout 상한은 30초, 조사는 15초, 전체는 60초였습니다.
- AgentLimits의 기본 최종 timeout은 15초입니다. .env·시스템 환경변수·기본 설정은 수정하지 않았습니다.
- SDK 2.31.0, 모델 gemini-3.8-flash, API 키 존재 여부를 확인했으며 키 값은 출력하지 않았습니다.
- 필수 경고 이벤트 설정은 빈 튜플입니다. 기존 T03 결과와 품질 정보만 읽기 전용으로 조회했습니다.
- 저장 판정 OK / REINSPECT / IMAGE_QUALITY_WARNING, mean 81.24, std 55.79, NOT_RECORDED가 일치했습니다.
- 운영 코드의 요청별 SDK timeout·X-Server-Timeout·wait_for 연결 및 2초 여유 정책은 유지돼 있습니다.

### 중단 이유

1. 수동 스크립트 run_t03_simple_e2e_once.py의 ATTEMPT가 여전히
   `t03_operational_warningstop1`이며, 이 회차의 analysis_started.lock이 이미 존재합니다.
   기존 단일 실행 보호장치를 그대로 실행하면 잠금 생성 단계에서 중단됩니다.
   기존 잠금을 삭제하거나 회차를 임의 변경하여 실행하지 않았습니다.
2. 공통 계측기의 SDK 요청 항목에는 단계·결과·시간·토큰이 있지만 실제 http_options.timeout 값이 없습니다.
   HTTP 전송 항목에도 요청별 X-Server-Timeout 및 transport timeout 기록이 없습니다.
   따라서 이번 요청의 핵심인 실제 30초 전파를 현재 산출물만으로 검증할 수 없습니다.

운영 설정이 30초를 전달하지 못하는 문제는 아닙니다. 설정 전달은 오프라인에서 확인됐지만,
새 회차 식별자와 timeout 전파 계측이 준비되지 않았다는 구체적인 차이가 있습니다.
이번에는 운영 코드나 계측기를 즉석 수정하고 유료 호출로 진행하지 않았습니다.

### 미검증 항목과 다음 경계

실제 SDK/서버 timeout 전파, 요청별 HTTP 상태·시간·사용량, Function Calling 실행,
최종 JSON 생성·DiagnosisDraft·Pydantic·Evidence 검증과 진단 품질은 모두 NOT TESTED입니다.
추가 토큰/비용 사용은 없으며 새로운 실제 서버 오류 정보도 없습니다.
이전 HTTP 504의 정확한 원인은 여전히 UNKNOWN입니다.
이번에는 pytest를 재실행하지 않았고, 이전 전체 752개 PASS는 과거 검증 결과입니다.

운영 코드·설정·검사 JSONL·모델·평가 정답·기존 실험 파일 및 잠금은 수정하지 않았습니다.
이번 파일 변경은 본 문서의 사전 중단 기록 추가뿐입니다.
다음에는 계측기에서 새 단일 회차와 요청별 timeout/헤더 기록을 준비하고 Mock으로 확인해야 합니다.
사전 문제가 발견되면 중단하라는 이번 지시에 따라 그 보완 작업과 실제 T03 재검증은 다음 승인을 기다립니다.
T01/T05/T06 실서버 분석, Step 5, Git add/commit/push 없이 중단합니다.

## T03 30초 회차 READY 및 timeout 계측기 보완 — 2026-10-16

### 범위와 새 회차

이번 승인은 수동 계측기·오프라인 테스트·새 실행 회차 준비에 한정됩니다.
실제 Gemini API 요청과 운영 T03 분석은 **0회**입니다.
운영 AgentService/config/schemas/investigation/reporting/tools/decision은 변경하지 않았습니다.

새 회차 ID는 **t03_operational_final30_1**이며 기존 규칙대로
`data/outputs/manual_validation/`의 회차별 파일명 접두사를 사용합니다.
준비 전 ready/lock/result 파일명이 모두 비어 있음을 확인했고 다음 준비 파일만 생성했습니다.

| 항목 | 준비 결과 |
|---|---|
| 준비 manifest | t03_operational_final30_1_ready.json |
| 상태 | READY |
| 대상 | INSP-001398 |
| 실제 분석 / 실제 Gemini HTTP | 0 / 0 |
| 예상 실행 잠금 | t03_operational_final30_1_analysis_started.lock — **아직 없음** |
| 예상 결과 | t03_operational_final30_1_sanitized_result.json — **아직 없음** |
| 설정 전제 | 조사 15초 / 최종 상한 30초 / 전체 60초 / 여유 2초 |
| 실서버 승인 | 별도 필요 |

준비 manifest는 불변의 준비 기록입니다. 실제 실행 여부는 별도 lock/result로 판단합니다.
검증 함수는 READY라도 lock 또는 result가 있으면 재실행을 거부합니다.
준비 함수는 세 파일 중 하나라도 있으면 충돌로 거부하고, 준비 파일 생성 자체도 exclusive open을 사용합니다.
회차 ID의 경로/제어 문자 입력은 거부합니다.
기존 t03_operational_warningstop1 잠금과 결과는 삭제·덮어쓰기·재사용하지 않았습니다.
새 잠금은 별도 승인된 실제 실행 시점에만 exclusive open으로 생성됩니다.

T03 스크립트는 새 회차를 참조하며 사전 점검에서 준비 manifest의 정확한 일치,
미사용 상태 및 AGENT_FINAL_MODEL_TIMEOUT_SECONDS=30을 확인하도록 했습니다.
.env·시스템 환경변수·운영 기본값을 변경하지 않았습니다.
이번 준비만으로 main()의 승인 실행 경로를 호출하지 않았습니다.

### 변경 파일

- scripts/agent_validation_measurements.py: timeout/예산의 허용 필드 추출, ContextVar 기반 요청 분리, 회차 준비/검증.
- data/outputs/manual_validation/run_t01_simple_e2e_once.py: 공통 SDK/HTTP/public wait_for 관찰 지점 연결.
- data/outputs/manual_validation/run_t03_simple_e2e_once.py: 새 READY 회차 및 명시적 최종 30초 전제 확인.
- data/outputs/manual_validation/t03_operational_final30_1_ready.json: 실행 전 준비 manifest.
- tests/test_agent_timeout_measurements.py: 신규 SDK MockTransport·보안·회차 충돌 테스트.
- data/outputs/manual_validation/test_t03_measurements.py: 기존 T01/T03 계측에 15/30초와 예산 차단 검증 추가.
- docs/day4-step4-gemini-validation.md: 본 기록 추가.

수동 스크립트/manifest/수동 테스트는 기존 Git 무시 디렉터리에 있습니다.
새 tracked 테스트는 공유 계측 helper와 SDK MockTransport를 검증하며, 수동 runner 테스트는 명시적으로 별도 실행했습니다.

### 계측 지점과 관측 가능성

환경변수 값을 다시 출력하는 대신 실제 호출 경계에서 다음 값만 추출합니다.

| 경계 | 기록하는 허용 필드 |
|---|---|
| SDK generate_content 진입 | sdk_timeout_ms, sdk_retry_attempts, 요청 순서/단계 |
| Agent 모델 요청 관찰 | agent_limit_seconds, agent_deadline_monotonic, remaining_agent_budget_seconds |
| public asyncio.wait_for 진입 | local_wait_timeout_seconds, request_deadline_monotonic, deadline_source |
| HTTPX AsyncClient.send 진입 | connect/read/write/pool timeout 확장값, X-Server-Timeout의 숫자값, 충돌 여부 |
| HTTP 응답 이후 | HTTP 상태, 경과 시간; 기존 SDK 계층 토큰 사용량/오류 단계 |

wait_for deadline은 공개 함수 진입 시각에 실제 전달된 timeout을 더한 **파생 값**이며
deadline_source=DERIVED_FROM_PUBLIC_WAIT_FOR_ENTRY로 표시합니다. 내부 timer handle을 읽었다고 주장하지 않습니다.
HTTPX timeout은 request.extensions에 실제 지정된 phase 설정값입니다.
MockTransport가 실제 연결/read 대기를 해당 시간에 강제 종료함을 시험한 것은 아닙니다.
transport_absolute_deadline과 server_absolute_deadline은 **NOT OBSERVABLE**입니다.
서버가 실제 처리한 deadline의 절대 시각을 SDK 설정만으로 계산해 관측값으로 둔갑시키지 않습니다.
확장값/헤더가 없거나 숫자로 안전하게 확인할 수 없으면 NOT OBSERVABLE을 기록합니다.

Agent 모델 요청과 public wait_for를 읽기 전용 observer로 감싸고 ContextVar로 SDK/HTTP 전송 Task에 연결했습니다.
원래 함수를 그대로 호출하며 SDK 내부 코드, 실제 timeout 설정, 인증 헤더와 네트워크 요청 내용을 바꾸지 않습니다.
부족한 예산으로 SDK 전에 거부된 요청은 model_requests_blocked에 단계·안전한 코드·남은 예산만 기록합니다.
그런 요청을 SDK 요청/HTTP 전송 성공으로 집계하지 않습니다.
HTTP와 SDK 수·도구 실행 수·Trace 라운드/Evidence 집계는 기존처럼 구분합니다.

실제 timeout 전파의 충돌/미관측 상태를 timeout_propagation_valid로 집계하며,
전파를 확인하지 못한 상태에서는 전체 수동 검증 결과를 PASS로 만들지 않습니다.
자동 재시도 설정 attempts=1 확인과 SDK 요청당 한 HTTP 전송의 기존 guard도 유지합니다.

### Mock 관측 결과와 민감 정보 차단

실제 설치 SDK와 MockTransport의 공유 클라이언트로 다음을 관측했습니다.

| 순서 | 단계 | SDK timeout | HTTPX read timeout | 서버 전달 헤더 | public wait_for |
|---|---|---:|---:|---:|---:|
| 1 | 조사 설정 | 15000ms | 15초 | 15 | 15초 |
| 2 | 최종 JSON 설정 | 30000ms | 30초 | 30 | 30초 |
| 3 | 후속 조사 설정 | 15000ms | 15초 | 15 | 15초 |

별도 Mock 504에서는 최종 요청에 적용된 30000ms/30초가 HTTP 상태 504와 함께 남고
실패 단계는 STRUCTURED_OUTPUT으로 기록됐습니다. 실제 서버 504 원인 재현은 아닙니다.
SDK 최종 설정 30초에 서버 헤더가 15인 합성 요청은 충돌로 탐지하되 요청 자체는 수정하지 않았습니다.
추가 원시 헤더·인증·Cookie·본문을 복사하지 않고 숫자 timeout과 정해진 상태/출처만 반환합니다.
악의적 timeout 헤더 텍스트는 원문 대신 NOT OBSERVABLE로 처리했습니다.
합성 API 키/Authorization/Cookie/사용자 헤더/프롬프트/스냅샷 표식이 기록에 남지 않는 테스트도 통과했습니다.
인증 헤더가 Mock 수신 지점에는 그대로 도착함을 확인하여 계측기가 인증 동작을 제거하지 않았음을 검증했습니다.

### 테스트 결과

| 순서 | 실제 실행 | 결과 |
|---|---|---|
| 1 | 신규 tests/test_agent_timeout_measurements.py | **21 PASS**, 0.80초 |
| 2 | 수동 test_t03_measurements.py + 기존 test_agent_validation_measurements.py | **25 PASS**, 4.90초 |
| 3 | 모든 tests/test_agent*.py | **668 PASS**, 10.01초 |
| 4 | 전체 tests | **773 PASS**, 실패/건너뜀 0, 경고 2, 25.47초 |
| 5 | pip check | No broken requirements found |
| 6 | git diff --check 및 변경 수동/신규 파일 공백 검사 | 공백 오류 없음, 기존 LF/CRLF 경고 별도 |

표준 전체 tests에는 신규 21개가 추가됐습니다. Git 무시 디렉터리의 수동 테스트 14개는 별도 실행했으며
이를 전체 773개에 중복 합산하지 않습니다. 기존 수동 테스트 7개에서 7개 사례가 늘었습니다.
T01/T03/필수 로그 T03의 15/30초, 504/JSON 오류/스키마 오류,
예산 부족으로 전송 전 차단, 준비 충돌·기존 기록 보존·외부 호출 없는 READY를 확인했습니다.
기존 60초/2초 여유와 T05/T06·근거 검증·판정 보호는 관련/전체 Agent 회귀에서 통과했습니다.

vision-insight Python으로 `-m pytest ... -q -p no:cacheprovider`를 사용했고,
Agent/전체 실행은 pytest.main()에 회차별 임시 basetemp를 지정했습니다.
검사/로그/출력/test_data는 운영 경로와 분리하고, 전체 회귀용 공개 중립 PNG만 복사했습니다.
실제 기본 sync/async HTTP transport는 차단했고 모든 SDK 전송은 MockTransport 또는 테스트 더블로 처리했습니다.
전체 테스트의 기존 로컬 Vision/PatchCore 검사는 임시 저장소에서 실행됐습니다.
경고 2건은 기존 timm/anomalib FutureWarning입니다.

### 최종 준비 상태와 보호

새 회차 READY/실행 0/HTTP 0/새 잠금 없음/새 결과 없음을 재확인했습니다.
운영 코드·설정·스키마·도구·판정·JSONL·모델 및 기존 회차 lock/result의
총 13개 보호 파일 SHA256은 전후 모두 동일했습니다. 임계값 34.1442와 기존 검사 기록은 보존했습니다.
평가 정답을 읽지 않았고 기존 사용자 변경과 design/presentation 파일을 보존했습니다.

계측기와 회차 준비는 완료됐지만 실제 T03 최종 30초 E2E는 여전히 NOT TESTED입니다.
다음 별도 승인 시 검증 프로세스에서만 최종 상한 30초를 명시하고 기존 단일 승인 실행 경로를 사용해야 합니다.
실행 직전 READY/잠금·결과 부재/모델·SDK·키 존재/원본 판정/예산을 다시 점검해야 합니다.
30초 성공 여부와 과거 서버 504의 정확한 원인은 아직 UNKNOWN입니다.
실서버 호출·T03 재실행·T05/T06 분석·Step 5·Git add/commit/push 없이 중단합니다.

## T03 최종 JSON 상한 30초 실제 E2E — t03_operational_final30_1

### 승인 범위와 실행 결과

사용자 승인에 따라 `INSP-001398`을 기존 T03 수동 스크립트로 **정확히 한 번** 분석했습니다.
계측 시작 시각은 `2026-10-16T05:22:36.565146+00:00`입니다.
실제 FastAPI `POST /analyze/INSP-001398`를 IN_PROCESS_ASGI로 호출하고,
내부 Gemini HTTP는 실제 Developer API / v1beta로 전송했습니다.
모델 `gemini-3.8-flash`, SDK `google-genai==2.31.0`은 유지했습니다.

| 최종 항목 | 실제 결과 |
|---|---|
| 회차 | t03_operational_final30_1 |
| 실제 분석 / FastAPI POST | **1회 / 1회** |
| 실제 Gemini HTTP / SDK 요청 | **3회 / 3회** |
| FastAPI | **HTTP 200** |
| analysis_status | **COMPLETED** |
| 전체 E2E | **PASS** |
| 기술적 완료 / 밝기 진단 품질 | **PASS / PASS** |
| 전체 HTTP 분석 시간 | **24600.289ms (24.600초)** |
| 자동 재시도 / 추가 분석 | **없음 / 없음** |
| 오류 | 없음 |

실행 전 READY, 새 잠금/결과 부재, 기존 잠금/결과 보존, 키 존재, 원본 판정·밝기값을 확인했습니다.
최종 timeout 상한 30초는 Python 자식 프로세스 내부 환경변수로만 지정했습니다.
.env·시스템 환경변수·프로젝트 기본값은 수정하지 않았습니다.
실행 후 다른 프로세스에서 확인한 기본 설정도 **조사 15 / 최종 15 / 전체 60초**입니다.
운영 코드·출력 스키마·모델·SDK는 이번에 수정하지 않았습니다.

### 요청별 실제 timeout과 HTTP 결과

아래 HTTP 시간은 HTTPX send 경계에서 잰 값이며 SDK 전체 경과와 구분합니다.
잔여 Agent 예산도 HTTP 전송 경계에서 읽은 값입니다.
transport timeout은 실제 request.extensions의 connect/read/write/pool 값으로 모두 동일했습니다.

| 요청 | 단계 | SDK timeout | HTTPX 각 phase | X-Server-Timeout | 로컬 wait_for | 잔여 예산 | HTTP | HTTP 시간 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | Function Calling | 15000ms | 15초 | 15 | 15초 | 59.984초 | 200 | 2427.414ms |
| 2 | Function Calling | 15000ms | 15초 | 15 | 15초 | 57.531초 | 200 | 3053.389ms |
| 3 | 독립 최종 JSON | 30000ms | 30초 | 30 | 30초 | 54.484초 | 200 | 18967.153ms |

SDK 계층 경과는 순서대로 2441.151 / 3056.371 / 18969.093ms였습니다.
모든 요청에서 sdk_retry_attempts=1, automatic_retry_observed=false,
server_timeout_conflict=false, transport_timeout_conflict=false를 확인했습니다.
timeout_propagation_valid=true입니다. 환경변수만 보고 전파 성공으로 판단한 것이 아닙니다.

Agent 전체 제한은 60초였고 최종 요청 시점 잔여 예산이 충분하여 30초가 축소 없이 적용됐습니다.
공통 Agent deadline의 monotonic 값은 19230.984였습니다.
public wait_for 진입 시 계산한 요청별 deadline은 19186.000 / 19188.437 / 19206.500입니다.
이 값은 DERIVED_FROM_PUBLIC_WAIT_FOR_ENTRY이며 내부 timer/서버 절대 deadline 관측값이 아닙니다.
transport_absolute_deadline 및 server_absolute_deadline은 **NOT OBSERVABLE**입니다.
최종 파생 deadline과 Agent deadline 사이에도 2초보다 큰 여유가 있었고 전체 실행 시간은 60초 이내였습니다.

### Function Calling·Python 조회·조건부 종료

| 순서 | Trace 라운드 | Gemini가 선택한 도구 | executed | success | Evidence | 도구 경과 |
|---|---:|---|---|---|---|---:|
| 1 | 1 | get_inspection_result | true | true | E0001 | 2.402ms |
| 2 | 2 | analyze_image_quality | true | true | E0002 | 3.030ms |

두 도구의 인자는 모두 고정 대상 INSP-001398이었습니다.
도구 결과를 실제 저장소에서 조회했으며 tools_used도 이 두 도구만 포함합니다.
HTTP 사전 존재 조회까지 포함한 분석 구간의 Python 조회는 3회지만 Agent 도구 실행은 2회입니다.
SDK 요청 3회와 도구 실행 2회를 혼동하지 않습니다.

첫 결과 조회 후 CONTINUE, 품질 조회 후 **ready=true / policy=WARNING / trace_round=2**가 관측됐습니다.
서버 정책에 의해 추가 로그·이력·종료 확인 조사를 생략하고 최종 보고서 요청으로 전환했습니다.
기본 필수 이벤트 로그 설정은 빈 목록이며, 이번 분석은 이벤트 발생 순서나 장비 이벤트를 주장하지 않습니다.
두 번째 조사 요청에서 모델 Content 원형 재사용, FunctionResponse의 user 역할·호출 ID 일치,
Part 경계와 thought signature 보존을 확인했습니다. 서명 원문은 출력하지 않았습니다.
최종 요청은 도구/FC 이력 없이 독립 Evidence 카탈로그와 최소 Trace를 사용했습니다.

### 최종 JSON과 결정적 근거 검증

| 단계 | 실제 결과 |
|---|---|
| 단순 JSON 생성 / 파싱 | PASS / PASS |
| 단순 스키마 검증 | PASS |
| DiagnosisDraft 변환 | PASS |
| Pydantic 검증 | PASS |
| Evidence ID·JSON Pointer·정확한 값 비교 | PASS |
| 관측 사실 / 실제 Trace 연결 | **12개 / 모두 유효** |
| 필수 core/품질 사실·권고 근거 | PASS |
| 검사 ID·원본 판정 | 일치 |

E0001에서 실행 상태/제품 판정/품질 상태/추론 상태/최종 판정/원인 코드의 core 사실 6개를 확보했습니다.
E0002에서 품질 상태와 아래 5개 값을 포함한 품질 사실 6개를 확보했습니다.

| fact_id | 실제 source_field | 실제 값 |
|---|---|---|
| F0007 | /data/image_quality_status | WARNING_LOW_BRIGHTNESS |
| F0008 | /data/metrics/max | 153.0 |
| F0009 | /data/metrics/mean | **81.24** |
| F0010 | /data/metrics/min | 18.0 |
| F0011 | /data/metrics/std | **55.79** |
| F0012 | /data/threshold_status | **NOT_RECORDED** |

당시 밝기 기준 숫자를 생성하거나 현재 설정으로 대체하지 않았습니다.
관측 사실의 source_event는 모두 null이며 존재하지 않는 이벤트 사실은 추가되지 않았습니다.
실제 저장 제품 판정 **OK**, 최종 판정 **REINSPECT**, 원인 **IMAGE_QUALITY_WARNING**을 유지했습니다.
REINSPECT를 제품 NG로 바꾸거나 모델 OK를 최종 정상 확정으로 바꾸지 않았습니다.

가능한 원인은 ILLUMINATION_CHANGE 및 EXPOSURE_SETTING이며 둘 다 실제 밝기 상태 사실 F0004/F0007을 참조합니다.
서버가 렌더링하는 설명은 조명 조건/노출 설정 변화의 **가능성**이며 장비 고장이 확인됐다는 확정 표현이 아닙니다.
권고 LIGHTING_EXPOSURE_CHECK도 F0004/F0007에 연결되고,
MANUAL_REINSPECTION은 실제 REINSPECT 사실 F0003에 연결됩니다.
최종 한계 설명은 4개이며 서버 검증/렌더링 경로에서
모델 정상 판정의 비보증, 물리 원인 미확정, 비보정 신뢰도, 당시 밝기 기준 미확인을 유지합니다.
이 보고서는 관측·가설·권고를 구분했으며 새로운 측정값·이벤트·장비 고장을 만들어내지 않았습니다.

### 실제 토큰 사용량과 비용

| 요청 | 입력 | 출력 | Thinking | 총 토큰 |
|---|---:|---:|---:|---:|
| 1 | 1226 | 28 | 80 | 1334 |
| 2 | 1617 | 28 | 251 | 1896 |
| 3 | 2733 | 289 | 3621 | 6643 |
| 합계 | **5576** | **345** | **3952** | **9873** |

세 요청 모두 SDK usage metadata가 존재하며 usage_complete=true입니다.
실제 청구 금액은 확인하지 못해 **UNKNOWN**입니다. 금액을 임의 추정하지 않았습니다.

### 보호·해석·다음 경계

운영 코드/설정/스키마/도구/판정·운영 JSONL 두 개·모델 체크포인트/메타데이터 및
기존 warningstop1 잠금/결과의 **13개 보호 파일 SHA256이 전후 모두 동일**했습니다.
운영 write_attempts=0이며 고정 임계값 34.1442와 기존 T01/T03/T05/T06 검사 기록도 보존했습니다.
평가 정답·원본 이미지 경로·인증정보·프롬프트 전문·thought signature 원문은 출력하지 않았습니다.
기존 사용자 변경사항과 이전 실패 기록을 수정하거나 삭제하지 않았습니다.

새 회차에는 실제 실행 잠금과 PASS 결과 파일이 생성됐으므로 **이미 사용한 회차**입니다.
READY manifest는 준비 시점의 불변 기록일 뿐, 같은 회차를 다시 실행할 수 있다는 의미가 아닙니다.
추가 분석은 새 회차 준비와 별도 승인이 필요합니다.

이번 최종 요청은 30초가 실제 전파된 상태에서 18.967초에 성공했습니다.
이 관측은 15초보다 긴 생성 시간이 필요했던 이번 성공 사례를 보여주지만,
기존 504가 오직 15초 설정 때문이었다거나 30초가 항상 성공한다는 인과·성공률을 입증하지 않습니다.
과거 서버의 정확한 내부 DEADLINE_EXCEEDED 원인은 여전히 UNKNOWN입니다.

이번 작업에서 pytest는 재실행하지 않았습니다. 이전 준비 단계 전체 773 PASS는 과거 검증 결과입니다.
변경 파일은 이번 회차 lock/result와 본 문서 추가뿐이며 운영 코드는 변경하지 않았습니다.
권장 다음 단계는 별도 승인 후 T05 실패 기록 분석과 T06 저장 판정 보호를 각각 단일 검증하는 것입니다.
이번에는 T05/T06, Step 5, 추가 모델 요청, Git add/commit/push 없이 중단합니다.

## T05 ERROR 사전 오프라인 점검 — t05_operational_error1

이번 작업은 저장 기록 읽기, Mock 검증 및 계측 회차 준비만 수행했다.
**실제 INSP-001405 분석 0회, 실제 Gemini HTTP 요청 0회, 실제 E2E NOT TESTED**이다.
운영 backend/ 정책·validator·출력 스키마·설정은 변경하지 않았다.
기존 T01/T03 PASS는 이전 실제 실험 기록이며 이번 Mock 결과와 구분한다.

### A. 준비 판정과 저장 기록

**엄격한 오류 근거의 필수 포함 보장 관점에서는 BLOCKED**, 계측 회차 준비 자체는 **READY**다.
현재 validator는 이미 선택된 사실의 정확성은 검증하지만, ERROR 보고서에 반드시 오류 이벤트와
미측정 사실을 포함하도록 강제하지 않는다. 이를 해결했다고 주장하거나 운영 코드를 수정하지 않았다.
실서버 분석 전에 이 공백에 대한 운영 보완 또는 알려진 한계를 감수하는 실험 범위를 별도로 승인받아야 한다.

읽기 전용 조회 대상은 기존 `INSP-001405` 및 연결 로그뿐이다.

| 항목 | 실제 저장/조회 결과 |
|---|---|
| status | FAILED |
| result | UNKNOWN |
| image_quality_status | ERROR |
| defect_detection_status | SKIPPED |
| final_result | ERROR |
| final_reason_code | INSPECTION_FAILED |
| anomaly_score / decision_threshold / inference_time_ms | 키는 저장되어 있으나 모두 null; 0이 아님 |
| 밝기 mean/std/min/max, width/height/channels | 원본 metrics에 키 없음; 도구에서는 null |
| applied_thresholds | 원본 metrics에 키 없음; 품질 도구의 threshold_status=NOT_RECORDED |
| 레코드 최상위 error/error_code/error_message | 저장되지 않음(NOT_RECORDED) |
| metrics.error | 비어 있지 않은 오류 문자열 존재; 원문 비출력, 도구 allowlist에서 제외 |
| 별도의 구조화 오류 코드 | NOT_RECORDED; 로딩 실패의 근거는 아래 실제 event_code |
| 특정 물리적 원인/장비 고장 | UNKNOWN |

실제 이벤트 순서는 다음과 같다. 동일 시각의 두 이벤트는 저장 순서를 유지한다.

| 순서 | UTC timestamp | level | stage | event_code |
|---|---|---|---|---|
| 1 | 2026-10-14T11:07:13.616990+00:00 | INFO | init | INSPECTION_STARTED |
| 2 | 2026-10-14T11:07:13.618533+00:00 | ERROR | load | IMAGE_LOAD_FAILED |
| 3 | 2026-10-14T11:07:13.618533+00:00 | ERROR | complete | INSPECTION_FAILED |

로그 message는 저장되어 있으나 원문을 출력/복사하지 않았다. 조회 도구는 message를 제외한다.
이 기록에는 IMAGE_LOADED 또는 INFERENCE_STARTED/COMPLETED 이벤트가 없으므로
PatchCore 추론이 완료됐다고 해석하지 않는다. 다른 검사나 평가 정답으로 이 원인을 보충하지 않았다.

### B. 도구와 현행 ERROR 조사 경로

- `get_inspection_result`: 조회 성공(ok=true)이며 검사 실행은 FAILED다. 두 성공 개념을 구분한다.
- `get_execution_logs`: 실제 세 이벤트를 시각 순으로 반환한다. 이미지 로드 실패를 설명할 핵심 근거다.
- `analyze_image_quality`: 호출 가능하고 ok=true다. 재분석하지 않으며 ERROR/null 통계만 반환한다.
  이 응답을 정상 영상 품질이나 실측값 확보로 해석하면 안 된다.
- `get_inspection_history`: 허용 도구이나 이번 원인 확인에는 필수가 아니다. 실제 이력을 조회하지 않았다.
  호출 시에는 결과 도구로 확인한 실제 제품에 연결된 TARGET-PRODUCT 별칭만 허용된다.

현행 `_investigation_ready`는 정상 또는 완료된 model-OK 밝기 경고의 충분성만 판단한다.
FAILED/UNKNOWN/ERROR/SKIPPED인 T05는 어느 조기 종료 분기도 만족하지 않는다.
경고 전용 required_warning_event_codes를 설정해도 ERROR의 필수 로그 계약으로 바뀌지 않는다.
ERROR에서는 모델이 추가 도구 없는 응답을 반환하면 snapshot 존재 확인 후 최종 보고서로 넘어간다.

Mock의 결과→로그→도구 없는 종료 응답→최종 JSON 경로는 모델 요청 4회, 도구 실행 2회다.
결과와 로그를 같은 모델 응답에서 요청하면 요청 수는 달라질 수 있다. 이는 예상 경로이며 실측치가 아니다.
ERROR 전용 조기 종료는 새로 구현하지 않았다. 무의미한 반복은 동일 호출 2회 상한으로 차단된다.
전체 정책은 4라운드/도구 8회/전체 60초/도구 3초/최종 안전 여유 2초를 유지한다.

### C. Evidence 안전성 및 확인된 공백

Mock에서 실제 기존 Python 도구를 가짜 저장소에 대해 실행했다.
결과 E0001, 로그 E0002와 실제 Trace의 executed=true/success=true를 연결했고,
`/data/1/event_code`, `/data/1/stage`, `/data/1/timestamp`에 동일 IMAGE_LOAD_FAILED 이벤트를 연결했다.
최종 단순 JSON→기존 DiagnosisDraft→Pydantic→결정적 검증 경로가 통과했다.
IMAGE_ACQUISITION은 가설로만 표시되고 IMAGE_REGISTRATION_ACCESS_CHECK가 실제 오류 이벤트에 연결됐다.

차단 확인: 가짜 K 토큰/Evidence ID/JSON Pointer, 값이 null인 위치에 숫자 0 삽입,
검사 ID 불일치, 다른 source_event, 핵심 사실 누락, OK 요약으로 변경,
근거 없는 밝기 가설/계속 정상 운전 권고, 변조된 카탈로그.
검사 판정은 서버 snapshot에서 유지되며 도구 allowlist/ID 고정/sanitizer는 변경하지 않았다.

다만 다음은 **현행 동작으로 허용되는 공백**이다. 테스트가 이 동작을 관측했으며 안전성 해결의 PASS가 아니다.

1. 로그를 요청하지 않거나, 로그가 DATA_UNAVAILABLE이거나, 조회 후 보고서에서 오류 이벤트를 빼도
   핵심 상태 6개와 ERROR에 맞는 일반 재검사 권고만으로 COMPLETED가 가능하다.
2. anomaly_score/품질 통계가 미측정이라는 사실은 snapshot/null로 유지되지만,
   해당 미측정 사실을 observed_facts에 반드시 포함시키지는 않는다.
3. SKIPPED 또는 result=UNKNOWN은 현행 `_signals`에서 model 신호로 취급된다.
   따라서 MODEL_AVAILABILITY 가설/MODEL_SERVICE_CHECK가 허용될 수 있다.
   로딩 실패로 추론을 건너뛴 것이 모델 서비스 장애를 입증하는 것은 아니다.
4. 밝기 기준 없음에 대한 일반 한계 문구가 ERROR에도 붙는다. 이것이 밝기 검사 수행의 근거는 아니다.

이 공백을 테스트 삭제, 가짜 Evidence 보충, validator 완화, 운영 수정으로 숨기지 않았다.
권장 보완은 별도 승인 후 ERROR 보고서의 필수 오류 이벤트/미측정 사실 범위와
SKIPPED의 모델 장애 가설 허용 범위를 명시하는 것이다. 이번에는 제안만 한다.

### D. 수동 계측기 및 READY 회차

준비한 회차: `t05_operational_error1`, 대상 `INSP-001405`.

- `scripts/agent_validation_measurements.py`: 준비 manifest에 scenario/final_timeout을 선택적으로 전달한다.
  기존 T03 기본값 및 manifest 구조는 그대로다. T05는 명시적으로 final_timeout=15를 사용한다.
- `data/outputs/manual_validation/run_t05_simple_e2e_once.py`: 기존 T03/T01 계측 observer와
  단일 ASGI POST, 배타적 lock, 보호 파일 해시, 안전한 오류 수집을 재사용한다.
  T05 전용 읽기 전용 preflight와 prepare-only만 추가했다. 오류 이벤트의 보고서 포함 여부는 별도 계측한다.
- `data/outputs/manual_validation/t05_operational_error1_ready.json`: READY/analysis_attempts=0/
  gemini_http_requests=0/approval_required=true. 실행 lock/result는 생성하지 않았다.

준비 및 `--offline-only` 실행은 실제 검사/로그의 읽기만 수행하며 AgentService.analyze를 호출하지 않았다.
T03의 기존 사용 회차·잠금·결과를 삭제/재사용/덮어쓰기하지 않았다.
동일 회차 재준비, lock/result 존재 시 실행, manifest와 timeout 불일치는 차단된다.
수동 runner와 READY 기록은 기존 규칙대로 Git ignored 로컬 산출물이다.

SDK/HTTPX/X-Server-Timeout/local wait/잔여 예산/실패 단계는 기존 전송 경계 계측을 재사용한다.
조사 15초, 최종 기본 15초, 전체 60초, 여유 2초다. 30초를 선택하거나 영구 설정을 수정하지 않았다.
향후 최종 30초는 별도 승인과 일치하는 새 준비 설정이 필요하며 현재 T05 runner는 15초만 허용한다.
서버 내부 absolute deadline은 여전히 NOT OBSERVABLE이다.

### E. 테스트·보호·실행 경계

Conda `vision-insight` Python에서 실행했다. 신규 테스트는 실제 T05가 아닌 중립 ID의
가짜 저장소/Mock Gemini를 사용하며 HTTPX 기본 외부 transport와 SDK 실제 요청을 차단한다.
전체 회귀의 검사/로그 저장은 임시 경로로 격리하고 보호 파일 쓰기를 audit guard로 차단했다.

| 실행 범위 | 실제 결과 |
|---|---|
| `pytest tests/test_agent_t05_preflight.py -q -p no:cacheprovider` | 신규 35 PASS |
| `pytest`의 `tests/test_agent*.py` 대상 | 703 PASS |
| 기존 로컬 `test_t03_measurements.py` | 14 PASS |
| `pytest tests -q -p no:cacheprovider` | 기존 773 + 신규 35 = 808 PASS, 기존 라이브러리 경고 2건 |
| `python -m pip check` | No broken requirements found |
| `git diff --check` 및 새 파일 공백 검사 | 공백 오류 없음; 기존 LF/CRLF 안내는 오류와 구분 |
| 실제 Gemini HTTP / 실제 T05 분석 | 0회 / 0회 |
| T05 실제 E2E, 실제 토큰/시간/비용 | NOT TESTED |

신규 테스트 최초 실행에서 테스트의 반복 제한 코드 기대값을 실제 TOOL_REPEAT_LIMIT에 맞췄고,
새 계측 preflight가 도구 선언의 product_id 스키마를 운영 product_id 값으로 오인하던 구성을
기존 계측 방식처럼 tools와 contents 경계를 구분해 수정했다. 운영 sanitizer는 변경하지 않았다.
오류가 난 기대값을 삭제하거나 검증 수준을 낮추지 않았으며 이후 신규 35개가 통과했다.

사전·사후 SHA256 비교 대상 14개(운영 관련 코드/판정, JSONL 두 개, 체크포인트/메타데이터,
기존 T01/T03 성공 결과 및 T03 잠금)가 모두 동일했다. 고정 임계값 34.1442도 변경하지 않았다.
사용자 기존 변경사항을 보존했고 평가 정답/이미지 데이터/프롬프트/키/원시 예외를 출력하지 않았다.

실제 T05 E2E는 아직 승인/실행하지 않았다. 먼저 오류 필수 근거 공백의 처리 방침을 결정하고,
운영 보완이 필요하다면 해당 수정과 회귀 검증을 별도 승인받은 뒤 단일 실서버 실험을 승인받아야 한다.
T06, 이후 단계, 실제 외부 요청, Git add/commit/push 없이 여기서 중단한다.

## T05 ERROR 필수 근거 정책 운영 보완 — 오프라인 검증

### A. 변경 범위와 전제

이 절은 앞 절의 공백 분석에 대한 후속 보완이며 이전 실제/Mock 기록을 변경하지 않는다.
실제 Gemini 요청 **0회**, 실제 T05 분석 **0회**, T05 실제 E2E **NOT TESTED**다.
수정 전 사용자 변경사항과 기존 T01/T03 결과를 보존했다.

운영 변경은 `backend/agent/error_policy.py` 신규 정책, `backend/agent/service.py`의
최종 요청 전 gate/보고서 coverage/ERROR 전용 신호 분리, `backend/agent/prompts.py` 지침 추가뿐이다.
investigation.py의 기존 정상/경고 충분성, 도구, reporting.py 변환, DiagnosisDraft와
단순 출력 스키마, config.py 및 검사 판정 로직은 수정하지 않았다.
스키마 확장 없이 기존 scalar observed_value=null과 JSON Pointer로 미산출 사실을 표현한다.

### B. ERROR 조사 완료 gate

적용 범위는 inspection_id나 시나리오 이름이 아니라 저장 snapshot의 **status=FAILED 및 final_result=ERROR**다.
현재 저장 계약의 final_reason_code=INSPECTION_FAILED를 확인하고, 다른 사유/불명확한 조합은 안전하게 거부한다.
모델이 조사 종료를 선택하더라도 최종 JSON 요청 전에 `error_required_facts`를 실행한다.
결과 또는 로그 도구가 실제 성공하지 않았으면 최종 생성으로 넘어가지 않는다.

필수 조건:
- 결과와 로그의 executed/success/evidence_id, 실제 Evidence 문서 및 metadata가 연결되어야 한다.
- 두 도구의 검증된 inspection_id 인자는 요청 ID와 일치해야 하고 결과 문서 ID도 일치해야 한다.
- 반복 조회 결과와 snapshot의 핵심 상태/측정값은 같아야 한다.
- 실제 level=ERROR의 INSPECTION_FAILED/complete 이벤트가 있어야 한다.
- 관측된 IMAGE_LOAD_FAILED/load, INFERENCE_FAILED/inference 등 기존 저장 계약의 실패 이벤트는
  실제 stage/level/유효 timestamp와 함께 검증한다. 오류 이벤트의 명시적 판정 metrics가 snapshot과 충돌하면 거부한다.
- IMAGE_LOAD_FAILED가 실제로 있으면 UNKNOWN/ERROR/SKIPPED와 미산출 수치가 일관되어야 하고
  로드 실패 시각이 검사 실패 완료 시각보다 늦으면 거부한다.

로그가 없거나 조회를 생략했으면 INSUFFICIENT_EVIDENCE로 실패한다. 도구의 STORAGE_ERROR/NOT_FOUND도 유지한다.
이미 선택한 Evidence의 위조는 EVIDENCE_MISMATCH 등 기존 안전한 코드로 실패한다.
모두 기존 HTTP 오류 매핑을 사용하며 INSUFFICIENT_EVIDENCE/EVIDENCE_MISMATCH는 HTTP 502다.
서버가 가짜 Function Call을 만들거나 누락 로그를 자동 실행/추정/보충하지 않는다.
모델의 도구 선택은 유지하되, 서버 gate가 그 선택만으로 근거 없는 완료를 허용하지 않는다.

**일반 ERROR를 이미지 로드 실패로 간주하지 않는다.** INSPECTION_FAILED만 있는 유효 로그는
일반 실행 실패만 설명할 수 있다. IMAGE_LOAD_FAILED의 부재를 로드 성공의 증거로 삼지 않으며,
이미지 획득 가설/점검은 실제 IMAGE_LOAD_FAILED event_code 사실에 연결해야 한다.
알 수 없는 ERROR 이벤트나 유효하지 않은 로그는 fail-closed로 처리한다.
새로운 오류 코드/미검증 원인별 필수 이벤트를 지어내지 않았다.

새 ERROR 조기 종료나 호출 예산 확대는 없다. 순차 결과→로그→모델 종료→최종 JSON Mock은
여전히 모델 요청 4회/도구 실행 2회다. 모델 동작에 따라 달라지며 실제 요청 수를 예측 확정하지 않는다.
조사 15초/최종 기본 15초 및 선택 30초/전체 60초/안전 여유 2초/도구 3초,
4라운드/8도구/동일 호출 2회와 자동 재시도 비활성화를 그대로 유지한다.

### C. 최종 DiagnosisDraft 필수 coverage

기존 Pydantic과 정확한 scalar/JSON Pointer/source_event 검증 후 별도의 ERROR coverage를 적용한다.
필수 사실은 서버가 요구하되 모델 대신 선택하거나 만들어 넣지는 않는다.

1. 결과 도구의 핵심 6개 상태: status/result/image_quality_status/defect_detection_status/final_result/final_reason_code.
2. 같은 결과 Evidence의 anomaly_score/decision_threshold/inference_time_ms/metrics.mean/metrics.std.
   저장된 null은 null 사실로 포함되어야 하며 0, 문자열 또는 현재 설정으로 치환할 수 없다.
3. 조회된 각 실제 ERROR 이벤트의 event_code/stage/timestamp를 같은 Evidence ID와 같은 로그 행의
   JSON Pointer, source_event에 연결해야 한다. 로그를 조회했어도 보고서에서 생략하면 거부한다.

T05의 현재 저장 내용에서는 **17개 사실**(핵심 6 + 미측정 5 + 오류 이벤트 두 개의 각 3개)이 필요하다.
실제 저장 결과/로그의 읽기 전용 도구 호출로 E0001/E0002와 17개 요구 사실이 구성됨을 확인했다.
이 확인에서는 AgentService.analyze와 SDK 요청을 차단했고 최종 보고서를 생성하지 않았다.
실제 T05 분석 완료 또는 실제 모델의 17개 토큰 선택 성공을 뜻하지 않는다.

미측정 한계는 실제 null 사실 및 SKIPPED와 연결해 구조적으로 드러낸다.
자연어 키워드나 설명 문장의 유사도로 판정하지 않으며, 새 API/DiagnosisDraft 필드를 추가하지 않았다.
사실 누락, 가짜 K/Evidence ID, 잘못된 Pointer, source_event 오류, 수치 조작 또는 판정 변경은 거부한다.

### D. SKIPPED와 모델 장애 분리

workflow ERROR 범위에서는 SKIPPED, UNKNOWN 또는 상태 조합만으로 model/load 신호를 만들지 않는다.
MODEL_AVAILABILITY 가설과 MODEL_SERVICE_CHECK는 **실제 INFERENCE_FAILED event_code 사실을
선택하고 그 fact_id를 참조한 경우에만** 허용한다.
IMAGE_ACQUISITION/IMAGE_REGISTRATION_ACCESS_CHECK도 실제 IMAGE_LOAD_FAILED event_code를 참조해야 한다.
기존 원인·권고 코드와 가설 표시를 유지하므로 특정 체크포인트 손상/CPU 부족/장비 고장을 확정하지 않는다.
별도 실제 추론 실패 이벤트가 있는 합성 양성 사례는 허용해 향후 모델 장애 증거까지 영구 차단하지 않았다.
ERROR 밖의 기존 정상/경고/추론 실패 판정 정책은 이번에 변경하지 않았다.

### E. 테스트와 수정 파일

신규:
- `tests/test_agent_error_policy.py`: 필수 coverage, 생략/조회 실패/다른 ID, null과 0, 위조·이벤트 불일치,
  SKIPPED/UNKNOWN 가설 차단, 실제 추론 오류 양성, 일반 ERROR 비오분류, HTTP 502, 호출 상한 및 SDK 직렬화/MockTransport.
- `tests/agent_error_fixtures.py`: 실제 계약에 맞는 합성 ERROR 기록/로그/토큰·draft fixture만 제공한다.

직접 관련 기존 fixture/기대값 보강:
`tests/test_agent_t05_preflight.py`, `tests/test_agent_service.py`, `tests/test_agent_api.py`,
`tests/test_agent_simple_report.py`, `tests/test_agent_reporting_integration.py`,
`tests/test_agent_efficiency.py`, `tests/test_agent_report_request.py`,
`tests/test_agent_operating_timeouts.py`, `tests/test_agent_validation_measurements.py`,
`tests/test_agent_timeout_policy_experiment.py`, `tests/test_agent_warning_policy_experiment.py`.

과거 공백을 허용한다고 관측하던 테스트는 이제 거부를 검증한다. 양성 fixture에는 실제 오류 level/stage,
검사 실패 이벤트 및 미측정 사실을 추가했다. 첫 Agent 회귀에서 8건이 실패한 원인은 옛 fixture의
누락 근거/부정확한 필드 및 중복 토큰·로그 행 위치였다. 실제 가짜 저장소의 로그 위치와 동일하게 보강했다.
검증 조건 삭제·validator 완화·운영 데이터 수정으로 통과시키지 않았다.

Conda vision-insight Python에서 외부 HTTPX 기본 transport를 차단하고 테스트 저장 경로를 격리해 실행했다.
신규 suite의 SDK 요청 생성은 로컬 직렬화 및 MockTransport만 사용한다.
전체 회귀에는 원본 저장 파일/모델/데이터셋 쓰기 금지 audit guard를 적용했다.

| 실행 명령/범위 | 실제 최종 결과 |
|---|---|
| `pytest tests/test_agent_error_policy.py tests/test_agent_t05_preflight.py -q -p no:cacheprovider` | 신규 53 + 기존 T05 35 = 88 PASS |
| `pytest`의 `tests/test_agent*.py` 대상 | 756 PASS |
| `pytest tests -q -p no:cacheprovider` | 기존 808 + 신규 53 = **861 PASS**, 기존 경고 2건 |
| `python -m pip check` | No broken requirements found |
| `git diff --check` 및 신규 파일 공백 검사 | 공백 오류 없음; LF/CRLF 안내와 no-index 차이 종료값은 오류와 구분 |
| 실제 Gemini API / 실제 T05 분석 | **0회 / 0회** |

T01/T03 필수 경고 로그/T06 저장 판정, JSON→DiagnosisDraft→Pydantic→Evidence,
timeout/deadline 및 504 오류 매핑 회귀가 통과했다. 이는 실제 모델의 새 지침 준수나 E2E 성공률 검증은 아니다.

### F. 보호 및 READY/BLOCKED 판단

SHA256 사전·사후 비교 **28개 모두 동일**: 운영 검사/로그 JSONL, 체크포인트/메타데이터,
판정/config/schema/도구 파일 및 기존 T01/T03/T05/T06 관련 잠금·준비·결과 산출물이다.
임계값 34.1442와 기존 검사 판정을 바꾸지 않았다. 기존 사용자 변경사항도 되돌리지 않았다.
API 키/원시 예외/원본 이미지 경로/평가 정답/thought signature는 출력하지 않았다.

**운영 ERROR 정책과 저장 근거는 READY**다. `t05_operational_error1_ready.json`은 그대로 보존했고
실행 lock/result는 없다. 실제 실행은 하지 않았다.

그러나 **실서버 실행 준비의 최종 판정은 BLOCKED**로 남긴다. 현재 로컬 수동 runner의
`error_log_coverage_enforced_by_service=False`는 이전 공백 분석 때의 고정값이다.
이번 운영 정책에서는 더 이상 맞지 않으며 그대로 실행하면 계측 보고가 실제 정책과 모순된다.
이번 허용 범위에 수동 계측기 변경은 포함되지 않아 runner 및 READY 산출물을 수정하지 않았다.
별도 승인으로 해당 표시를 실제 정책 검증 결과에 연결하고 Mock으로 확인한 후 실서버 실행을 승인받아야 한다.

T05 runner의 최종 timeout은 15초만 허용하는 상태이며 30초 선택은 별도 승인/준비 사항이다.
실제 모델이 필수 17개 사실을 누락하면 안전하게 실패하며 서버가 자동 보충하거나 재시도하지 않는다.
ERROR가 많거나 로그가 과도하면 기존 context/40개 사실/호출·시간 상한에서 안전하게 실패할 수 있다.
T05 E2E, T06 실제 분석, 새 모델 요청, 이후 단계, Git add/commit/push는 실행하지 않고 중단한다.

## T05 ERROR 계측기 정정 및 실행 준비 — 오프라인 검증

### A. 불일치와 변경 범위

앞 절에서 발견한 수동 runner의 `error_log_coverage_enforced_by_service=False` 고정 표시를 제거했다.
이를 True 상수로 바꾸지 않았으며, 운영 정책 함수와 실제 서비스 검증 동작을 관측하는 계측으로 대체했다.
backend/ 전체, 프롬프트/JSON Schema/판정/timeout 설정은 이번에 수정하지 않았다.
기존 사용자 변경사항과 이전 실험 결과는 되돌리지 않았다.

변경 파일:
- `scripts/agent_validation_measurements.py`: 정책 적용/필수 근거 측정과 격리된 오프라인 동작 probe.
- `data/outputs/manual_validation/run_t05_simple_e2e_once.py`: preflight와 조사/최종 검증 observer 연결.
- `tests/test_agent_error_measurements.py`: 신규 계측 테스트 25개.
- `tests/test_agent_t05_preflight.py`: 실제 AgentService 생성에 필요한 max_payload 설정을 가짜 settings에 추가.
- 본 문서의 새 섹션. 기존 T01/T03 runner와 실제 결과/잠금/READY 파일은 수정하지 않았다.

### B. 운영 정책을 재사용하는 계측

검사 적용 여부는 운영 `error_report_scope(state)`로 판단한다.
필수 도구·이벤트·사실은 운영 `error_required_facts(state)`가 반환한 실제 CatalogEntry에서 얻는다.
계측기에 별도의 ERROR 분기 조건, 필수 사실 17개 목록, 필수 이벤트 목록을 재구현하지 않았다.
출력은 Evidence ID/source_tool/source_field/source_event 구조만 포함하며 observed_value는 복사하지 않는다.

`policy_enabled`는 함수 존재나 상수만으로 True가 되지 않는다. preflight에서 SDK 대신 로컬 더블과
복사된 RequestState/서비스를 사용해 다음을 확인한다.
1. 실제 서비스의 조사 흐름이 로그 없는 ERROR 상태를 최종 요청 전에 거부한다.
2. 정책에서 얻은 전체 사실로 만든 로컬 검증용 draft는 실제 서비스 validator를 통과한다.
3. 핵심 상태 외의 필수 사실 하나를 제거한 draft는 실제 서비스 validator가 거부한다.
4. SKIPPED 사실만 참조하는 모델 장애 가설과 모델 서비스 점검 권고는 각각 거부한다.

이는 모델 응답이 아닌 **오프라인 정책 기능 점검**이다. AgentService.analyze, 실제 SDK 생성/요청,
FastAPI 분석 POST를 호출하지 않는다. 조사 probe의 generate는 로컬 Content만 반환하며
최종 생성 시도가 감지되면 네트워크 없이 차단한다. 서비스/원본 상태는 복사해 사용한다.
알 수 없는 정책, 연결되지 않은 gate, 예상하지 못한 실패는 False 또는 NOT OBSERVABLE로 표시한다.
preflight는 policy_enabled/applicable/offline evidence 점검이 모두 True일 때만 통과한다.
실패 사유는 안전한 코드만 기록하고 원본 예외 문자열은 복사하지 않는다.

### C. READY와 실제 분석 상태 분리

| 항목 | 이번 실제 저장 기록의 읽기 전용 preflight 결과 |
|---|---|
| policy_enabled | true — 위 오프라인 기능 점검에 근거 |
| policy_applicable | true — 운영 정책 함수 결과 |
| required_tools | get_inspection_result, get_execution_logs |
| required_event_codes | IMAGE_LOAD_FAILED, INSPECTION_FAILED |
| required_fact_count | 17 — 운영 정책 반환값에서 계산 |
| offline_required_evidence_valid | true — 준비 단계 저장 근거 점검 |
| required_evidence_collected | **NOT TESTED** — 실제 분석 실행의 수집 결과가 아님 |
| report_validation_passed | **NOT TESTED** — 실제 Gemini 보고서를 검증하지 않음 |

17개는 현재 저장 내용에 대한 관측 결과이지 계측기 상수가 아니다.
핵심 상태 6개, 실제 null인 측정 관련 사실 5개, 두 오류 이벤트의 event_code/stage/timestamp 6개다.
실제 값·시각은 계측 메타데이터에 중복 복사하지 않고 JSON Pointer로 연결한다.

향후 승인된 실행에서는 조사 observer가 실제 RequestState로 수집 충족 여부를 갱신한다.
필수 Evidence가 없으면 False이며, 미관측 항목을 임의 성공으로 바꾸지 않는다.
최종 observer는 기존 실제 서비스 validator를 먼저 호출하고 성공 결과 및 운영 coverage를 확인한 후에만
report_validation_passed=true를 기록한다. 실제 검증 예외는 false로 기록하며 다시 던진다.
단순 True 인자, READY 상태 또는 근거 수집 성공만으로 최종 보고서 검증을 통과시킬 수 없다.

정책 함수가 없거나 호출할 수 없으면 NOT OBSERVABLE 및 안전한 unavailable_reason을 남기고 준비를 차단한다.
정책의 반환 요구사항이 바뀌면 메타데이터의 사실 목록과 개수도 바뀌는 Mock을 검증했다.
T01/T03/T06 정상·경고 기록에는 ERROR 정책 비적용을 표시하고 기존 조기 종료 동작을 변경하지 않는다.

### D. 테스트 결과와 실행 방법

Conda vision-insight Python에서 다음 순서로 검증했다.

| 실행 명령/범위 | 실제 결과 |
|---|---|
| `pytest tests/test_agent_error_measurements.py -q -p no:cacheprovider` | 신규 25 PASS |
| `pytest tests/test_agent_t05_preflight.py tests/test_agent_error_policy.py -q -p no:cacheprovider` | 기존 T05/ERROR 88 PASS |
| 기존 계측 두 모듈 + 로컬 `test_t03_measurements.py` | 46 PASS |
| `pytest`의 `tests/test_agent*.py` 대상 | 781 PASS |
| `pytest tests -q -p no:cacheprovider` | 기존 861 + 신규 25 = **886 PASS**, 기존 경고 2건 |
| `python -m pip check` | No broken requirements found |
| `git diff --check` 및 변경/신규 계측 파일 공백 검사 | 공백 오류 없음 |

기존 계측 두 모듈은 tests/test_agent_validation_measurements.py와 tests/test_agent_timeout_measurements.py다.
T01/T03/T05/T06 분기, T03 30초/조사 15초 전파, 잔여 예산, 잠금 충돌, 504와 민감 정보 비노출 회귀가 포함된다.
Mock 정책 미확인/미연결/근거 누락은 성공 표시나 최종 요청 없이 거부됐다.
신규 테스트 첫 실행의 2건 실패는 가짜 저장소 ID와 공용 수집 helper ID가 달랐던 fixture 오류였다.
중립 ID를 일치시켜 수정했으며 검사 ID 고정 검증을 완화하지 않았다.

외부 HTTPX 기본 transport/실제 SDK 요청을 차단했다. 실제 저장 기록 preflight에서도
SDK Client/요청/AgentService.analyze를 차단하고 counters=0임을 확인했다.
전체 회귀는 검사/로그/출력 저장소를 임시 디렉터리로 격리하고 원본 운영 저장 파일·모델·데이터셋 쓰기를 차단했다.
LF/CRLF 안내와 no-index의 차이 종료값은 공백 검사 실패와 구분했다.

### E. 회차 보존과 파일 보호

`t05_operational_error1`은 기존 **READY** 그대로다. READY manifest의 바이트/SHA256이 같고
실행 lock/result는 없다. 새 회차를 만들거나 기존 회차를 실행/완료 상태로 바꾸지 않았다.
기존 T01/T03 검증 결과와 잠금도 그대로다.

사전 비교 대상 99개 중 허용된 기존 T05 테스트 1개를 제외하고 보호 상태를 확인했다.
backend/ 전체 Python 코드, 운영 JSONL, 모델/메타데이터, 기존 준비/결과/잠금 및 관련 범위 밖 파일을 포함한
**92개 SHA256이 동일**했다. 임계값 34.1442와 기존 검사 기록을 변경하지 않았다.

나머지 **presentation/demo/의 기존 파일 6개는 작업 중 해시 변경이 관측됐다.**
대상은 t03-demo-readme.md/zip, t03-demo-talk-track.md, t03-report-demo-full.png,
t03-report-demo.html/pdf다. 이번 작업 명령에서는 해당 파일을 수정하지 않았고,
변경 주체/원인은 UNKNOWN이다. 내용 검토·복원·덮어쓰기하지 않았으며 동시 사용자 작업 가능성을 보존했다.
따라서 범위 밖 모든 파일이 동일했다고 보고하지 않는다.

### F. 최종 준비 판정과 경계

**T05 계측기 불일치 BLOCKED는 해소됐으며 실서버 실행 준비 상태는 READY**다.
이는 Gemini E2E PASS가 아니라 별도 승인 후 단일 분석을 시작할 수 있는 오프라인 준비 판정이다.
실제 Gemini HTTP 요청 **0회**, 실제 T05 분석 **0회**, 실제 최종 보고서/Pydantic/Evidence 검증은 NOT TESTED다.

timeout 설정은 바꾸지 않았다. 조사 기본 15초/최종 기본 15초/선택 후보 30초/전체 60초/여유 2초를 유지한다.
현재 manifest/runner의 기존 15초 조건을 확인했을 뿐, T05 실제 실행의 30초 사용 여부는 이번에 결정하지 않았다.
향후 실제 요청에는 timeout 선택과 준비 상태의 일치 확인 및 **T05 분석 1회에 대한 별도 승인**이 필요하다.
매 실행 전 preflight를 다시 수행하며 실패하면 lock/외부 요청 전에 중단한다.
실제 모델의 17개 사실 선택, 지연 시간, 토큰 및 비용은 아직 확인하지 않았다.
로컬 runner는 기존대로 Git ignored 산출물이므로 다른 환경에서는 파일 존재/버전을 다시 확인해야 한다.
T05/T06 실서버 분석, 이후 단계, Git add/commit/push 없이 여기서 중단한다.

## T05 최종 JSON 30초 실제 E2E 승인 — 사전 설정 불일치로 중단

### 실행 회차와 판정

대상은 INSP-001405, 준비 회차는 기존 `t05_operational_error1`이다.
사용자는 실제 분석 1회 및 해당 자식 프로세스의 최종 JSON timeout 30초를 승인했다.
그러나 준비 기록과 수동 runner가 여전히 15초로 고정되어 있어 **BLOCKED / NOT TESTED**로 중단했다.
실제 분석, FastAPI 분석 POST, Gemini 요청, SDK 클라이언트 생성은 실행하지 않았다.

### 확인한 구체적 불일치

| 위치 | 현재 코드/기록 | 승인 조건과의 차이 |
|---|---|---|
| `t05_operational_error1_ready.json` | timeouts_seconds.final_ceiling=15 | 이번 최종 요청 상한은 30초 |
| `run_t05_simple_e2e_once.py` preflight | validate_ready_attempt(..., final_timeout=15) | 준비 기록도 15초 기준으로 검증 |
| 같은 preflight | AGENT_FINAL_MODEL_TIMEOUT_SECONDS == 15 요구 | 자식 프로세스에서 30을 설정하면 assertion을 통과할 수 없음 |
| 같은 runner의 기록/prepare | final_timeout_ceiling_seconds 및 final_timeout=15 | 승인된 실행 조건과 불일치 |

운영 AgentService의 요청별 30초 지원, 전체 60초/안전 여유 2초, attempts=1 재시도 제한 및
ERROR 조사/보고서 gate 연결은 코드에서 유지됨을 확인했다. 문제는 운영 timeout 기능 부재가 아니라
현재 수동 회차와 실행 preflight의 15초 고정 조건이다.
환경변수만 30으로 바꾸거나 기록 표시만 변경해서 해결된 것으로 취급하지 않았다.
기존 preflight는 실행 lock을 만들기 전에 호출되므로 해당 안전 조건을 우회하지 않았다.

### 이번 실행의 관측 범위

| 항목 | 결과 |
|---|---|
| READY 기록 | 존재, READY 그대로 보존 |
| 실행 lock / 결과 파일 | 없음 / 없음 |
| 실제 T05 분석 시도 | 0회 |
| 실제 FastAPI 분석 HTTP / analysis_status | NOT TESTED / NOT TESTED |
| 실제 Gemini HTTP 요청 | 0회 |
| 실제 Function Calling / 두 Python 도구 실행 | NOT TESTED / NOT TESTED |
| 실제 오류 이벤트 수집 / 17개 필수 사실 검증 | NOT TESTED / NOT TESTED |
| JSON / DiagnosisDraft / Pydantic / Evidence | 모두 NOT TESTED |
| 모델 장애 주장·미측정 값의 실제 보고서 안전성 | NOT TESTED — 보고서 미생성 |
| 실제 적용 SDK/HTTPX/header/wait_for timeout | NOT TESTED — 전송 없음 |
| 실제 서버 절대 deadline | NOT OBSERVABLE |
| 분석 시간 / 사용 토큰 / 청구 비용 | NOT TESTED / NOT AVAILABLE / 확인 불가 |

핵심 사전 조건 불충족을 확인한 시점에 실행을 중단했다. 이후 API 키 존재 여부나 저장 기록의
추가 조회를 계속하지 않았으며, 이전 오프라인 근거 점검을 이번 실제 실행의 성공으로 재사용하지 않았다.
API 키/프롬프트/원본 이미지 경로/평가 정답/thought signature는 출력하거나 전송하지 않았다.
코드 변경과 분석 실행이 없으므로 pytest는 재실행하지 않았다. 기존 886 PASS는 이전 작업의 결과다.

### 보존 및 다음 조치

운영 코드·프롬프트·스키마·설정, JSONL, 모델, 기존 준비/결과/잠금과 수동 계측기는 변경하지 않았다.
기존 READY를 30초 또는 COMPLETED로 덮어쓰거나 새 회차를 생성하지 않았다.
프로젝트 .env, 전역 환경변수 및 기본 timeout도 변경하지 않았다.
평가 Ground Truth는 접근하지 않아 해시 비교 대상에서도 제외했다.
점검 전후 보호 파일 49개 SHA256이 동일했고, presentation/demo/의 두 스냅샷 사이에도 해시 변경은 없었다.
해당 영역은 복원하거나 수정하지 않았다. 이번 문서 추가 후 git diff --check도 통과했다.

필요한 다음 조치는 **같은 회차의 30초 실행을 지원하는 수동 계측기/준비 기록의 정합화 방식을 별도로
승인받아 오프라인 검증하는 것**이다. 현재 승인 조건을 15초로 낮춰 실행하거나 다른 회차로 우회하지 않는다.
그 후 실제 T05 단일 E2E를 다시 승인받아야 하며, T06 실제 검증은 아직 진행하지 않는다.
운영 코드 수정, 재시도, 추가 시나리오, Git add/commit/push 없이 중단한다.

## T05 30초 실행 회차 정합화 — 준비 전용 오프라인 검증

### A. 이전 중단 원인과 회차 선택

앞 절의 중단은 운영 ERROR 정책 문제가 아니라 15초 READY와 수동 runner의 15초 고정 조건에
30초 프로세스 설정을 결합할 수 없었던 문제다. 이전 실제 분석/API 요청은 0회였으며 그 기록을 보존했다.
현재 회차 관리는 준비 기록의 정확한 일치, 파일 충돌 차단, 배타적 실행 잠금만 제공한다.
동일 ID의 설정 개정·승인 이력을 추가하는 기능은 없으므로 기존 기록을 수정하는 대신 새 회차를 준비했다.

| 구분 | 회차 ID | 준비 상한 | 상태 | 실행 lock/result |
|---|---|---|---|---|
| 최초 준비 이력 | t05_operational_error1 | 최종 15초 | READY 원본 보존 | 없음/없음 |
| 이번 30초 후보 | t05_operational_final30_1 | 최종 30초 | 새 READY | 없음/없음 |

두 회차 모두 inspection_id=INSP-001405다. 기존 15초 기록을 30초 이력으로 둔갑시키지 않았다.
새 READY의 approval_required=true는 **실제 API 분석 승인이 여전히 필요함**을 뜻한다.
이번 승인은 30초 구성 준비만 허용하며 실제 실행 허가로 재사용하지 않는다.

### B. 변경 파일과 엄격한 설정 대조

- `scripts/agent_validation_measurements.py`: `validate_attempt_timeout` 추가.
- `data/outputs/manual_validation/run_t05_simple_e2e_once.py`: 고정 15초 assertion 대신 승인된 준비 설정 대조,
  명시적 회차 선택 CLI 및 준비 전용 timeout 선택 추가.
- `data/outputs/manual_validation/t05_operational_final30_1_ready.json`: 새 준비 기록만 생성.
- `tests/test_agent_t05_timeout_configuration.py`: 신규 42개 오프라인 테스트.
- 본 문서 추가. backend/ 운영 코드와 기존 테스트/결과/잠금/READY는 수정하지 않았다.

실행 전 다음 세 값이 정확히 일치해야 한다.
1. 선택한 READY의 timeouts_seconds.final_ceiling.
2. 자식 프로세스 환경변수 AGENT_FINAL_MODEL_TIMEOUT_SECONDS의 값.
3. 그 프로세스에서 로드한 Settings의 최종 요청 timeout.

준비 및 프로세스 선택은 15 또는 30의 엄격한 정수/문자열 표현만 허용한다.
15초는 환경변수 미설정 시 기본값으로 유지한다. 30초는 프로세스 환경변수의 명시적 선택이 필요하며
Settings 또는 .env 값만 30인 상태는 허용하지 않는다. helper는 환경변수나 설정 파일을 변경하지 않는다.
READY 전체 내용도 기존 ready_manifest 계약과 정확히 대조하므로 ID/대상/시나리오/모델/SDK/API 버전,
READY 상태, 전체 60초/조사 15초/여유 2초, approval_required와 파일 이름이 혼합되면 차단된다.
기록 누락·읽기 실패·잘못된 timeout·실행 lock/result 존재도 API 요청 전에 차단한다.

`--attempt-id`로 회차를 명시적으로 선택한다. 환경변수 30만 설정해도 기존 15초 회차에서
자동으로 새 회차로 전환하지 않으며 ATTEMPT_PROCESS_TIMEOUT_MISMATCH로 차단한다.
`--prepare-final-timeout`은 --prepare-only에서만 허용한다. 실제 실행 모드에서 이를 우회 인자로 쓸 수 없다.
기존 default 회차와 최종 timeout 기본값 15초는 유지했다.

### C. 실제 수행한 준비와 preflight

준비 명령은 다음이며 분석을 수행하지 않는다.

```text
python data/outputs/manual_validation/run_t05_simple_e2e_once.py --attempt-id t05_operational_final30_1 --prepare-final-timeout 30 --prepare-only
```

이후 별도 Python 자식 프로세스 안에서만 AGENT_FINAL_MODEL_TIMEOUT_SECONDS=30을 설정하고,
같은 스크립트에 `--attempt-id t05_operational_final30_1 --offline-only`를 전달했다.
실제 SDK Client/요청, 외부 HTTPX transport 및 AgentService.analyze를 차단한 상태로 점검했다.
프로젝트 .env/상위 프로세스/시스템 환경변수와 기본 설정은 바꾸지 않았다.

| 확인 항목 | 실제 오프라인 관측 |
|---|---|
| 회차/config preflight | PASS |
| 준비된 최종 상한 | 30초 |
| 운영 ERROR 정책 활성화 | true, 서버 검증 동작 probe 사용 |
| 필수 도구/오류 이벤트/사실 | 2개/2개/17개 |
| 실제 final timeout 적용 | NOT TESTED — 실제 서버 전송 없음 |
| 실제 보고서 검증 | NOT TESTED |
| 실제 분석 / 실제 Gemini HTTP | 0회 / 0회 |

회차 설정에 승인된 30초는 상한이며, 실제 요청은 기존 운영 코드에 따라
min(30, floor(남은 전체 예산 - 2))초로 안전하게 축소될 수 있다.
부족한 예산을 확대하거나 자동 재시도를 활성화하지 않았다.

### D. SDK 전파 및 회귀 테스트

새 테스트는 READY 설정에서 선택한 상한을 운영 AgentLimits에 전달하고 실제 설치 SDK와
MockTransport로 요청 생성/전송 경계를 관측했다. 입력은 합성이며 실제 Gemini 서버에 접속하지 않았다.
조사→최종 JSON→다시 조사에 대해 다음이 일치했다.

| 항목 | Mock 실측 |
|---|---|
| SDK timeout ms | 15000 → 30000 → 15000 |
| HTTPX read timeout 초 | 15 → 30 → 15 |
| X-Server-Timeout 초 | 15 → 30 → 15 |
| 로컬 asyncio.wait_for 초 | 15 → 30 → 15 |
| Agent 전체 예산 / 최종 여유 | 60초 / 2초 |
| SDK attempts | 각 요청 1 — 재시도 없음 |

오래된 공통 X-Server-Timeout:15도 최종 요청에는 30으로 덮어쓰고 후속 조사는 다시 15로 격리됐다.
잔여 예산에 따른 안전한 축소/요청 전 차단, T01/T03/T05/T06, ERROR Evidence,
T03 필수 로그와 504 처리는 기존 운영·계측 회귀에서 함께 확인했다.
서버 내부 절대 deadline과 실제 504 해결 효과는 여전히 NOT OBSERVABLE/NOT TESTED다.

Conda vision-insight Python에서 외부 transport를 차단하고 임시 저장 경로를 사용했다.
전체 회귀에서는 운영 JSONL/모델/원본 데이터셋 쓰기도 audit guard로 차단했다.

| 실행 범위 | 실제 최종 결과 |
|---|---|
| `pytest tests/test_agent_t05_timeout_configuration.py -q -p no:cacheprovider` | 신규 42 PASS |
| T05 계측 + 사전 점검 + ERROR 정책 | 기존 113 PASS |
| 기존 계측 2개 모듈 + 운영 timeout + 로컬 T03 계측 | 80 PASS |
| `pytest`의 `tests/test_agent*.py` 대상 | 823 PASS |
| `pytest tests -q -p no:cacheprovider` | 기존 886 + 신규 42 = **928 PASS**, 기존 경고 2건 |
| `python -m pip check` | No broken requirements found |
| `git diff --check` 및 새/변경 파일 공백 검사 | 오류 없음 |

서로 반대인 15/30 조합, 승인 준비 기록 없음, ID 불일치, 잘못된 timeout, 변경된 모델/예산/상태,
읽을 수 없는 기록, 이미 사용한 회차, 준비 인자의 실행 모드 사용은 모두 차단됐다.
기존 15초 준비 이력과 기본값 보존 및 환경변수만으로 회차가 자동 선택되지 않는 것도 검증했다.
테스트 실패나 validator 완화를 통해 통과시키지 않았다.

### E. 보호 상태와 다음 승인 경계

실행 전후 비교한 기존 보호 파일 **83개 SHA256이 모두 동일**했다.
backend/ 전체 Python 코드, JSONL, 모델/메타데이터, 기존 검사에 연결된 준비/실험 결과/잠금,
기존 테스트와 최초 T05 15초 READY를 포함한다. 임계값 34.1442 및 운영 데이터는 변경하지 않았다.
평가 Ground Truth는 읽지 않았다. API 키/인증정보/프롬프트/원본 이미지 경로를 출력하지 않았다.

발표 자료는 별도 작업 영역으로 보존했다. 비교 시점 presentation/ 및 presentation.zip 목록은
30개→32개였고 기존 항목 5개의 변경과 2개 추가가 관측됐다. 수정 주체는 확정하지 않았으며,
이번 작업에서는 해당 파일을 작성/복원/덮어쓰기하지 않았다. 발표 자료 전체 불변을 주장하지 않는다.

**T05 30초 실행 준비 상태: READY.** 실제 사용할 회차는 `t05_operational_final30_1`이며
기존 `t05_operational_error1`은 15초 최초 준비 기록으로 남긴다.
두 회차에 실행 잠금/결과는 없고 실제 E2E는 아직 NOT TESTED다.
이 작업에서 실제 분석/실제 Gemini 요청은 각각 0회다.

다음 실서버 실행은 새 30초 회차 ID, 자식 프로세스의 명시적 30초 설정과 함께
사용자의 **T05 실제 분석 정확히 1회 승인**을 다시 받아야 한다.
실행 직전에 READY/잠금/기록/환경변수/키 존재 여부 및 ERROR 정책을 재검증해야 한다.
실제 보고서의 17개 필수 사실 선택, 지연/토큰/비용과 Gemini 서버 응답은 아직 검증하지 않았다.
T05/T06 실제 실행, 신규 이미지 검사, 후속 개발, Git add/commit/push 없이 여기서 중단한다.

## T05 신규 30초 회차 실제 E2E 단일 실행 — 조사 요청 HTTP 504 / FAIL

### A. 회차와 사전 확인

- 회차: `t05_operational_final30_1`, 대상: `INSP-001405`.
- 계측 기록 시각: `2026-10-16T07:19:54.915279+00:00`.
- 모델 `gemini-3.8-flash`, SDK `google-genai==2.31.0`, Developer API / `v1beta` 유지.
- 신규 READY의 ID/대상/최종 상한 30초를 확인했고 실행 전 잠금과 결과는 없었다.
  기존 `t05_operational_error1`의 최초 15초 READY는 변경하지 않았다.
- 별도 자식 프로세스에서만 `AGENT_FINAL_MODEL_TIMEOUT_SECONDS=30`을 설정했다.
  READY, 프로세스 환경변수, Settings가 일치했으며 `.env`와 기본 설정은 수정하지 않았다.
- 조사 15초, 최종 상한 30초, 전체 60초, 최종 안전 여유 2초 유지.
  조사 최대 4라운드, 도구 최대 8회, 동일 호출 최대 2회, 도구 timeout 3초 유지.
- 실제 호출 전 SDK/HTTP transport와 `AgentService.analyze`를 차단한 `--offline-only`
  점검이 PASS했다. 키는 존재 여부만 확인했다. ERROR 정책의 조사 차단/보고서 커버리지/
  완전한 Mock 보고서 수용/SKIPPED 기반 모델 장애 주장 거부 probe가 모두 통과했다.
  이는 오프라인 정책 점검이며 실제 보고서 검증 성공을 의미하지 않는다.

실제 실행은 기존 `run_t05_simple_e2e_once.py`의
`--attempt-id t05_operational_final30_1 --approved-single-analysis` 경로로 정확히 한 번 수행했다.
별도 서버를 기동하지 않고 실제 FastAPI 앱에 IN_PROCESS_ASGI로
`POST /analyze/INSP-001405`를 1회 보냈으며, Gemini에는 실제 Google HTTPS 요청을 전송했다.
독점 잠금과 신규 sanitized 결과 파일을 생성했다. 실행 이후 해당 회차는 이미 사용한 회차이며
READY 원본이 남아 있어도 다시 실행할 수 없다.

### B. 실제 결과와 요청별 계측

**최종 결과: FAIL.** FastAPI **HTTP 502**, `analysis_status=FAILED`,
오류 코드 `GEMINI_REQUEST_FAILED`.
세 번째 **조사(Function Calling)** 요청이 HTTP 504로 실패했다.
최종 JSON 요청은 시작하지 않았으므로 이번 실행에서 최종 30초 timeout의 실제 전파/효과는
**NOT TESTED**다. 이 실패를 최종 JSON 30초 요청 실패로 기록하지 않는다.

| 요청 | 단계 / 확인된 응답 | HTTP | HTTP 전송 경과 초 | SDK 호출 경과 초 | 입력 / 출력 / Thinking / 합계 토큰 |
|---|---|---|---|---|---|
| 1 | 조사, `get_inspection_result` 선택 | 200 | 2.283027 | 2.297489 | 1,279 / 28 / 90 / 1,397 |
| 2 | 조사, `get_execution_logs` 선택 | 200 | 2.282188 | 2.284978 | 1,557 / 28 / 146 / 1,731 |
| 3 | 조사 후속 요청, 응답 생성 실패 | 504 | 13.958728 | 13.961904 | UNKNOWN |

| 요청 | SDK timeout ms | HTTPX connect/read/write/pool 초 | X-Server-Timeout 초 | 로컬 wait_for 초 | 시작 시 Agent 잔여 예산 초 |
|---|---|---|---|---|---|
| 1 | 15000 | 각각 15 | 15 | 15 | 59.984 |
| 2 | 15000 | 각각 15 | 15 | 15 | 57.687 |
| 3 | 15000 | 각각 15 | 15 | 15 | 55.375 |

HTTPX 값은 실제 요청의 timeout extensions, 서버 전달 값은 허용된 헤더만 관측한 결과다.
세 요청 모두 SDK/HTTPX/헤더/로컬 제한이 일치했고 오래된 헤더 충돌은 없었다.
SDK attempts는 각각 1, transport retry는 0이며 자동·수동 재시도는 없었다.
서버 내부 절대 deadline과 transport 내부 절대 deadline은 **NOT OBSERVABLE**이다.
로컬 요청 deadline은 공개 wait_for 진입 시각과 제한으로 계산한 값이며 서버 deadline 실측이 아니다.

안전한 실패 상세:

| 항목 | 실제 관측 |
|---|---|
| 실패 요청 / 단계 | 3 / FUNCTION_CALLING |
| Gemini HTTP / 표준 코드 | 504 / DEADLINE_EXCEEDED |
| SDK 예외 유형 | ServerError |
| 허용 reason | UNKNOWN |
| 안전한 field violations | 빈 목록; 정확한 거부/장애 필드 UNKNOWN |
| 실제 서버 내부 원인 | UNKNOWN |

14초 안팎의 응답 시간만으로 설정된 15초가 서버 장애의 유일한 원인이라고 단정하지 않는다.
이 실행은 HTTP 400이나 최종 스키마 거부를 재현한 것도 아니다.

### C. Function Calling, Python 도구와 오류 Evidence

| 순서 | Trace 라운드 | Gemini가 선택한 실제 Python 도구 | 검사 ID | 실행 / 성공 | Evidence | 도구 경과 ms |
|---|---|---|---|---|---|---|
| 1 | 1 | get_inspection_result | INSP-001405 | true / true | E0001 | 2.282 |
| 2 | 2 | get_execution_logs | INSP-001405 | true / true | E0002 | 22.171 |

필수 두 도구는 모델이 실제 선택했고 서버에서 인자 검증 후 실제 저장소를 조회했다.
Agent 도구 실행은 **2회**, Trace는 **2라운드**, 실제 Gemini HTTP 요청은 **3회**다.
계측된 Python 조회 함수 진입 **3회**에는 FastAPI 사전 결과 조회 1회가 포함되어 있으므로
이를 Agent 도구 실행 3회 또는 Gemini 요청 재시도로 해석하지 않는다.
다른 검사 Evidence 혼합이나 중복 Agent 도구 실행은 관측되지 않았다.

결과 조회의 FunctionResponse는 요청 2에 포함됐고 후속 HTTP 200을 확인했다.
로그 조회의 FunctionResponse와 앞선 결과 응답은 요청 3에 포함되어 실제 전송됐지만
HTTP 504 때문에 해당 후속 요청의 성공은 확인하지 못했다.
전송 경계에서 user 역할, 함수 이름/호출 ID 대응, Part 경계와 thought signature 보존 검사가 통과했다.
서명 원문과 전체 요청 본문은 출력/저장하지 않았다.

원본 기록과 로그의 순서는 다음과 같았다.

| 순서 | 이벤트 | stage / level | 저장 시각 UTC |
|---|---|---|---|
| 1 | INSPECTION_STARTED | init / INFO | 2026-10-14T11:07:13.616990+00:00 |
| 2 | IMAGE_LOAD_FAILED | load / ERROR | 2026-10-14T11:07:13.618533+00:00 |
| 3 | INSPECTION_FAILED | complete / ERROR | 2026-10-14T11:07:13.618533+00:00 |

필수 두 ERROR 이벤트는 E0002의 실제 로그에 연결됐다. 마지막 두 이벤트는 시각이 같으며
엄격한 시간 차이가 있었다고 주장하지 않는다. 저장 목록의 순서와 단계는 위 표와 같다.
별도 INFERENCE 실패 이벤트는 없었다.

### D. 17개 필수 사실과 보고서 검증의 경계

운영 `error_required_facts`를 사용하는 계측에서 `policy_enabled=true`,
`policy_applicable=true`, **`required_evidence_collected=true`**, 필수 사실 수 **17**을 확인했다.
이것은 조사 단계에서 필요한 실제 근거가 존재한다는 뜻이며,
최종 보고서에 17개가 반영됐다는 의미가 아니다.

| 범주 | Evidence / JSON Pointer | 실제 근거 |
|---|---|---|
| 핵심 상태 6개 | E0001: `/data/status`, `/data/result`, `/data/final_result`, `/data/final_reason_code`, `/data/image_quality_status`, `/data/defect_detection_status` | FAILED / UNKNOWN / ERROR / INSPECTION_FAILED / ERROR / SKIPPED |
| 미측정 5개 | E0001: `/data/anomaly_score`, `/data/decision_threshold`, `/data/inference_time_ms`, `/data/metrics/mean`, `/data/metrics/std` | 모두 null, 미산출/미기록; 0 또는 NORMAL로 바꾸지 않음 |
| 이미지 로딩 실패 3개 | E0002: `/data/1/event_code`, `/data/1/stage`, `/data/1/timestamp` | IMAGE_LOAD_FAILED / load / 실제 저장 시각 |
| 검사 실패 3개 | E0002: `/data/2/event_code`, `/data/2/stage`, `/data/2/timestamp` | INSPECTION_FAILED / complete / 실제 저장 시각 |

| 검증 단계 | 이번 실제 실행 결과 |
|---|---|
| 필수 두 도구 실행 / 실제 오류 이벤트 확보 | PASS |
| 필수 근거 17개 수집 가능성 및 조사 Evidence 검증 | PASS |
| ERROR 정책의 보고서 생성 전 필수 근거 gate 직접 도달 | NOT TESTED — 조사 요청 3에서 먼저 실패 |
| 최종 JSON 생성 / 파싱 / 단순 스키마 검증 | NOT TESTED |
| DiagnosisDraft 변환 / Pydantic 검증 | NOT TESTED |
| 최종 Fact ID / Evidence ID / JSON Pointer 결정적 검증 | NOT TESTED |
| 보고서의 필수 17개 사실 커버리지 | NOT TESTED |
| 최종 보고서 원본 판정 보호 / 원인·권고 근거 검증 | NOT TESTED |
| 자연어 안전성, 모델 고장 단정·미측정 값 생성 여부 | NOT TESTED — 보고서 미생성 |
| 최종 JSON 30초 SDK/HTTPX/헤더/wait_for 전파 | NOT TESTED — 최종 요청 없음 |

현재 ERROR 검사는 T01 정상/T03 경고 조기 종료 대상이 아니다.
두 도구 후 종료 검사 모두 `ready=false`, `policy=CONTINUE`였고 조사 요청 3으로 진행했다.
그 응답을 받지 못했으므로 모델이 추가 도구를 선택하려 했는지 또는 조사 종료를 반환하려 했는지는
**UNKNOWN**이다. 실제 실행에서 ERROR 필수 조사 정책을 우회해 완료 처리한 사실은 없다.
SKIPPED가 모델 장애를 증명하지 않는 정책은 사전 Mock probe에서 확인했으나,
이번 실제 최종 진단의 안전성 PASS로 대신 표시하지 않는다.

### E. 판정·운영 파일 보호와 사용량

- 원본 상태 `FAILED / UNKNOWN / ERROR / INSPECTION_FAILED` 유지.
  quality ERROR, defect SKIPPED, 점수/기준/추론 시간 null, 밝기 통계 미기록 상태를 읽기 전용으로 확인했다.
- 실행 전후 기존 보호 파일 **52개 SHA256이 모두 동일**했다.
  backend Python 코드, 운영 JSONL 2개, PatchCore 체크포인트/메타데이터,
  계측 스크립트 및 기존 T01/T03/T05/T06 관련 준비/결과/잠금을 포함한다.
  JSONL 전체 해시 일치로 기존 검사 기록과 로그 불변을 확인했다.
- 신규 파일은 해당 회차의 `_analysis_started.lock`과 `_sanitized_result.json` 2개뿐이다.
  기존 15초/신규 30초 READY 원본과 기존 실서버 결과/잠금은 보존했다.
- 별도 발표 작업 영역은 비교한 **33개 파일이 동일**했다. 해당 파일을 수정/복원하지 않았다.
- 원본 저장소 판정은 불변이지만 실패 API에 완료 진단 판정이 반환된 것은 아니다.
  계측의 `verdict_unchanged=null`을 완료 보고서 판정 검증 성공으로 바꾸지 않는다.
- PatchCore 재추론/재학습, 임계값 34.1442 변경, 평가 Ground Truth 조회는 수행하지 않았다.
  운영 코드·프롬프트·스키마·모델·SDK와 환경설정도 변경하지 않았다.

| 항목 | 실제 확인 결과 |
|---|---|
| Agent 분석 / FastAPI POST | 각각 1회 |
| 실제 Gemini HTTP / SDK 호출 | 각각 3회 |
| 자동 / 수동 재시도 | 각각 0회 |
| 최종 JSON HTTP 요청 | 0회 |
| 확인된 입력 / 출력 / Thinking 토큰 | 2,836 / 56 / 236 |
| 확인된 합계 | **3,128 토큰**, 성공 요청 1~2만의 부분 합계 |
| 실패 요청 사용량 / 전체 확정 사용량 | UNKNOWN, `usage_complete=false` |
| 전체 분석 계측 시간 | **18.672640초** |
| HTTP 전송 경과 시간 합계 | 18.523943초; 전체 분석 시간과 구분 |
| 실제 청구 비용 | UNKNOWN — 과금 기록 조회 안 함 |
| 호출·전체 시간 제한 준수 | 확인된 3요청/2도구/18.673초, 기존 한도 이내 |

### F. 확인 명령과 남은 작업

이번에는 위 네트워크 차단 사전 점검과 실제 단일 실행을 수행했다.
전체 pytest와 pip check는 반복하지 않았다. 마지막 전체 **928 PASS / 기존 경고 2건**은
이전 오프라인 회차의 결과이며 이번 실행 결과로 재사용하지 않는다.
`git diff --check`는 공백 오류 없이 통과했다. 기존 작업 파일의 LF/CRLF 변환 안내는 별도 경고다.
문서는 기존 기록을 보존하고 이 섹션만 추가했다.

실제 실패 원인은 요청 3의 `504 / DEADLINE_EXCEEDED`까지 확인했고 서버 내부 원인은 UNKNOWN이다.
최종 30초 timeout이 적용되는 단계에 도달하지 못했으므로 효과/실패를 평가할 수 없다.
다음 권장은 ERROR 근거 충족 후 조사 종료 정책과 추가 조사 요청 필요성의 **오프라인 검토**다.
운영 정책 변경, 새 회차 생성/추가 유료 분석, T05 재검증 및 T06 실제 분석은 각각 별도 승인이 필요하다.
현재 회차 잠금을 유지하며 재실행하지 않는다. T06 E2E는 NOT TESTED로 남긴다.
T05 재시도, 다른 시나리오, 신규 이미지 실험, 후속 개발, Git add/commit/push 없이 중단한다.

## T05 ERROR 근거 충족 후 후속 조사 발생 — 읽기 전용 원인 분석 및 종료 설계

### A. 결론과 분석 범위

**분석 상태: PARTIALLY IDENTIFIED.**
세 번째 조사 요청이 발생한 애플리케이션 제어 흐름은 **ROOT CAUSE IDENTIFIED**다.
HTTP 504 자체의 Gemini 서버 내부 원인은 여전히 **UNKNOWN**이다.

핵심 답변: **운영 `_investigation_ready`는 정상 검사와 밝기 경고의 종료 조건만 검사한다.
ERROR 필수 근거 검사 `error_required_facts`는 조사 루프를 빠져나온 뒤 실행된다.
따라서 T05의 17개 원천 근거가 이미 충분해도 종료 결과는 False이며,
서버는 모델의 다음 조사 응답을 받기 위해 세 번째 요청을 보낸다.**
이는 근거 부족 판정에 의해 발행된 요청이 아니라, ERROR 조기 종료 분기가 없는 일반 루프의 계속이다.

이번에는 기존 회차 결과와 코드만 읽고, 합성 fixture 및 메모리 내 MockTransport로 재현했다.
운영 코드·테스트·스크립트·회차 기록은 수정하지 않았고 새 실행 회차도 생성하지 않았다.
실제 Gemini 요청/실제 검사 분석은 각각 **0회**, Git add/commit/push도 **0건**이다.

### B. 실제 Trace 역추적과 코드 위치

근거는 `t05_operational_final30_1_sanitized_result.json`의 SDK/HTTP 목록,
Tool Execution Trace, `early_exit_checks`, `error_policy`다. 전체 원본 요청 스냅샷은 없으므로
당시 Content의 정확한 바이트 크기나 실패한 모델의 내부 판단은 재구성하지 않는다.

| 순서 | 실제 관측 / 상태 전이 |
|---|---|
| 1 | 조사 요청 1 HTTP 200. Gemini가 `get_inspection_result`, 인자 `inspection_id=INSP-001405` 선택 |
| 2 | `_execute`가 allowlist·Pydantic 인자·검사 ID·호출 예산을 확인하고 실제 저장소 조회. 성공 Trace 1 / 라운드 1 / E0001 발급 |
| 3 | FunctionResponse를 user Content에 추가. 종료 검사 `ready=false`, `policy=CONTINUE` |
| 4 | 조사 요청 2에 첫 응답 전달, HTTP 200. Gemini가 동일 검사 ID의 `get_execution_logs` 선택 |
| 5 | 실제 로그 조회 성공. Trace 2 / 라운드 2 / E0002. IMAGE_LOAD_FAILED 및 INSPECTION_FAILED 확보 |
| 6 | 두 도구 후에도 종료 검사 `ready=false`, `policy=CONTINUE`. 계측의 ERROR 원천 근거 검사만 17개 충족 확인 |
| 7 | `_run`의 다음 반복이 조사 요청 3을 발행. 두 FunctionResponse가 포함된 전송이며 역할·호출 ID·Part·서명 보존 검사 통과 |
| 8 | 조사 요청 3 HTTP 504 / DEADLINE_EXCEEDED / SDK ServerError. 새로운 Function Call 응답이나 도구 실행은 관측되지 않음 |
| 9 | `_generate`의 일반 예외 변환 → AgentFailure(GEMINI_REQUEST_FAILED) → `analyze`의 FAILED 결과 → FastAPI HTTP 502 |

주요 코드 근거:

- `backend/agent/service.py:337`: `_investigation_ready`는 `_normal_evidence_ready OR warning_evidence_ready`뿐이다.
- `backend/agent/service.py:349`: 조사 루프의 다음 반복 첫 동작이 `await self._generate(...)`다.
  `structured` 인자가 없으므로 기본 False이며 조사 요청이다.
- `backend/agent/service.py:353`: 모델 응답에 Function Call이 없고 snapshot이 있으면 루프를 종료한다.
- `backend/agent/service.py:357`: 도구를 제안한 응답의 라운드 상한을 검사한다.
- `backend/agent/service.py:366`: 해당 응답의 도구 실행과 FunctionResponse 구성 후 종료 조건을 평가한다.
- `backend/agent/service.py:368`: 루프 종료 후에만 ERROR scope 및 `error_required_facts(state)`를 강제한다.
- `backend/agent/service.py:371`: 그 뒤 독립 user Content로 `structured=True` 최종 JSON을 요청한다.
- `backend/agent/service.py:267`: 조사 timeout은 기존 model timeout 15초, 최종 요청만 선택적 상한/잔여 예산/2초 여유를 사용한다.
- `backend/agent/service.py:319`: SDK ServerError는 GEMINI_REQUEST_FAILED로 변환된다.
  로컬 TimeoutError의 GEMINI_TIMEOUT과 다르다.
- `backend/agent/service.py:220`: `analyze`가 AgentFailure를 안전한 FAILED DiagnosisResult로 반환한다.
- `backend/agent/api.py:198` 및 `backend/agent/api.py:31`: FAILED 결과의 오류 코드가 HTTP 502로 매핑된다.

`run_t05_simple_e2e_once.py:84`의 관측 래퍼는 실제 종료 결과를 먼저 받은 뒤
`error_policy_measurements(..., phase="INVESTIGATION")`를 기록하고 원래 결과를 그대로 반환한다.
계측의 `required_evidence_collected=true`가 서버의 종료 결과를 True로 바꾸지는 않는다.
따라서 **필수 ERROR 정책은 존재하지만 ERROR 조사 조기 종료 정책은 존재하지 않는다.**

요청 3 시작 시 잔여 예산은 55.375초였다. 전체 60초 예산 부족 때문에 발생한 실패가 아니다.
실측 SDK 15000ms / HTTPX 각 15초 / X-Server-Timeout 15 / wait_for 15초는 조사 단계와 일치했다.
최종 JSON 30초 설정은 당시 선택됐지만 그 단계에 도달하지 못했다.
서버가 요청 3에서 추가 도구를 선택하려 했는지, 단순 조사 종료를 반환하려 했는지는 UNKNOWN이다.

### C. 현재 상태 전이와 근거 충분성

| 상태 | 원천 근거 | 현재 종료 조건 | 현재 다음 동작 |
|---|---|---|---|
| snapshot 없음 + 모델 도구 제안 없음 | 검사 결과 없음 | 루프 내 거부 | INSUFFICIENT_EVIDENCE |
| ERROR 결과만 조회 | 필수 로그/이벤트 누락 | 정상 False, 경고 False | 후속 조사; 모델이 종료하면 루프 뒤 ERROR gate에서 차단 |
| T05 결과+로그, 17개 충족 | 실제 Trace/Evidence/이벤트 유효 | 여전히 False | 다음 조사 요청 발행 |
| 근거 충분 + 다음 모델 응답에 도구 없음 | 17개 충족 | 모델 종료 경로 | ERROR gate → 카탈로그 → 최종 JSON → 변환/검증 |
| 근거 충분 + 다음 모델이 추가 도구 제안 | 17개 충족 | 충분성에 따른 추가 차단 없음 | allowlist/ID/도구·반복·라운드·시간 예산 안에서 추가 도구 실행 |
| 필수 로그 조회가 STORAGE_ERROR | 증거 확보 실패 | `_execute`에서 즉시 실패 | STORAGE_ERROR; 최종 JSON 없음 |
| 로그 빈 목록 DATA_UNAVAILABLE | 필수 증거 불충족 | ERROR 조기 종료 없음 | 모델에게 결과 전달 후, 루프 종료 시 ERROR gate에서 차단 |
| 정상 또는 지원되는 밝기 경고 충분 | 각자 전용 조건 충족 | True | 추가 조사 없이 최종 JSON |

현재 기본 한도는 도구 실행 8회, 동일 인자 호출 2회, 도구가 있는 조사 응답 최대 4라운드다.
루프 범위는 `range(1, max_tool_rounds + 2)`이므로 5번째 조사 응답은 도구 없는 종료 응답을
받을 수 있지만, 도구를 제안하면 실행 전에 TOOL_ROUND_LIMIT이다. 최종 JSON 요청은 별도다.
이 한도들은 무한 조사를 막지만 근거 충분 상태의 추가 조사 자체를 막지는 않는다.

T05의 원천 근거 17개는 다음과 같이 유효했다. 단순 도구 이름 두 개의 존재만으로 충분하다고 보지 않는다.

- E0001 핵심 6개: status / result / image_quality_status / defect_detection_status / final_result / final_reason_code.
- E0001 미산출 5개: anomaly_score / decision_threshold / inference_time_ms / metrics.mean / metrics.std의 실제 null.
- E0002 오류 6개: 실제 IMAGE_LOAD_FAILED, INSPECTION_FAILED 각 행의 event_code / stage / timestamp.
- `error_required_facts`는 snapshot 일치, 검사 ID, 성공 Trace, Evidence 소유권/카탈로그,
  stage·ERROR level·유효 시각·저장 판정 일치 및 이미지 로딩 실패 시 null/단계 조건 등을 검사한다.

이 수집 판정은 필요한 원천 근거의 충족이지 최종 Fact ID나 보고서 커버리지의 통과가 아니다.
실제 회차에서 최종 JSON·DiagnosisDraft·Pydantic·최종 Evidence/Pointer·17개 보고서 사실 검증은
여전히 **NOT TESTED**다. 루프 뒤 서비스 ERROR gate에도 직접 도달하지 못했다.

일반 ERROR와 T05를 구별해야 한다. 현재 운영 계약은 INSPECTION_FAILED만 기록된 일반 실패를
이미지 로딩 실패로 추정하지 않는다. 해당 합성 사례는 14개 사실로 일반 실패 보고서를 허용한다.
이는 기존 `test_generic_failure_is_not_invented_as_load_failure`가 명시하는 경계다.
**T05의 두 오류 이벤트/17개 계약을 일반 ERROR 전체에 무조건 적용하거나,
일반 ERROR validator의 성공만으로 T05 전용 종료 준비 완료라고 간주해서는 안 된다.**

### D. T03과 T05 비교 및 Q1–Q10 답변

T03은 `investigation.py:24`의 경고 scope와 `warning_evidence_ready`가 도구 배치 직후 적용된다.
COMPLETED/OK/REINSPECT/IMAGE_QUALITY_WARNING, 실제 품질 조회, 측정값 일치,
점수·기준 일관성, Trace/Evidence 연결과 선택된 필수 경고 이벤트를 모두 요구한다.
기준값 미기록은 NOT_RECORDED/null로 유지하며 별도 최종 `warning_report_covered`도 실행한다.
T05는 FAILED/UNKNOWN/ERROR/SKIPPED이므로 정상 및 경고 scope 모두에 속하지 않는다.
ERROR 정책을 경고 정책에 합치거나 T03의 수치 조건을 그대로 적용할 수 없다.

| 질문 | 확인된 답변 |
|---|---|
| Q1 | 도구 배치 후 `_investigation_ready=False` → `_run` 다음 반복의 `_generate(structured=False)` |
| Q2 | 두 도구/이벤트는 필요조건. 소유권·상태·null·시각 등 17개 실제 근거 검사가 필요하며, 현행 조기 종료 조건은 그것과 별개 |
| Q3 | 17개는 계측과 루프 뒤 ERROR gate/최종 커버리지에서 검증. 현재 `_investigation_ready`에는 연결되지 않음 |
| Q4 | ERROR 필수 조사/보고서 정책은 있지만 ERROR 전용 조기 종료는 없음 |
| Q5 | T03은 도구 배치 직후 결정적 ready로 종료, T05는 정상/경고 ready가 False여서 모델의 무도구 응답을 기다림 |
| Q6 | 실제 회차는 근거 부족이 아닌 일반 조사 루프의 계속. 세 번째 응답을 받지 못해 모델 의도는 UNKNOWN |
| Q7 | 좁게 정의한 ERROR ready를 같은 종료 지점에 연결하면 가능하다는 설계. 이번에 운영 구현하지 않음 |
| Q8 | 필수 조사 및 최종 검증을 모두 남겨야 함. 마지막 FunctionResponse 전송 여부와 복합 오류의 맥락 누락 위험은 별도 검토 필요 |
| Q9 | FAILED/ERROR인 다른 기록도 동일 반복 구조. INFERENCE_FAILED와 일반 실패는 각자 별도 충분성 계약 없이는 빠른 종료 대상으로 확대 불가 |
| Q10 | 서버 내부 504 원인은 UNKNOWN. Mock 504는 오류 매핑 재현일 뿐 서버 원인 재현이 아님 |

공유할 것은 Trace/Evidence 소유권, 실제 값/Pointer 검증과 도구 배치 후 결정 구조다.
상태 scope, 필수 도구, null/측정값 규칙, 오류·경고 이벤트 계약은 분리해야 한다.
정책상 추가 맥락이 필수이거나 추론 실패·복합 오류·불명확한 실패가 있는 경우 추가 조사는 합당할 수 있다.
실제 T05의 추가 조사에 그러한 명시적 서버 요구가 있었다는 근거는 없지만,
Gemini가 무슨 조사를 하려 했는지까지 불필요했다고 확정하지는 않는다.

### E. 비네트워크 재현과 기존 테스트

프로젝트 파일을 만들거나 수정하지 않고 Python stdin에서 기존 합성 fixture와 SDK-shaped 응답을 사용했다.
실제 `_run`, `_execute`, `_generate`, 변환기와 validator를 그대로 실행했다.
설치 SDK 변환기로 wire 구조를 직렬화한 뒤 `httpx.MockTransport`로만 전송했다.
SDK 클라이언트 생성, 실제 SDK request/async_request와 실제 HTTP transport를 차단했다.
실제 검사 ID 대신 합성 INSP-000001을 사용했고 운영 JSONL을 재현 입력으로 읽지 않았다.

| 재현 | Mock 요청 수 | 확인 결과 |
|---|---|---|
| A 결과만 조회 후 모델 종료 | 2 | 로그 누락으로 INSUFFICIENT_EVIDENCE, 최종 JSON 없음 |
| B 결과+로그+모델 종료+최종 | 4 | 17개 수집 직후 ready=False; 세 번째 조사 후 네 번째 JSON에서 17개 보고서 검증 COMPLETED |
| B 세 번째 조사에 Mock 504 | 3 | FastAPI ASGI HTTP 502 / GEMINI_REQUEST_FAILED, 최종 없음 |
| C 충분한 근거 후 품질 도구 추가 제안 | 5 | 세 번째 도구도 허용, 별도 조사 종료 후 JSON; COMPLETED |
| C 결과 조회 반복 | 4 | 동일 결과 도구 세 번째 실행 시도에서 TOOL_REPEAT_LIMIT |
| D 빈 로그 | 3 | DATA_UNAVAILABLE 전달 후 종료 gate에서 INSUFFICIENT_EVIDENCE |
| D 로그 저장소 예외 | 2 | STORAGE_ERROR, 즉시 중단 |
| D INSPECTION_FAILED 누락 | 3 | INSUFFICIENT_EVIDENCE |
| D 일반 INSPECTION_FAILED만 존재 | 4 | 일반 오류 보고서 14개 사실 COMPLETED, 이미지 로딩 실패 원인 생성 안 함 |
| D 핵심 result 누락 | 3 | ERROR 원천 근거 gate에서 INSUFFICIENT_EVIDENCE |
| E T01 합성 정상 | 2 | 정상 조기 종료 및 최종 검증 COMPLETED |
| E T06과 같은 저장 OK 경계 | 2 | 평가 정답 없이 저장 OK 정책 유지, ERROR 비적용 |
| E T03 합성 경고 | 3 | 결과+품질 후 바로 최종 JSON COMPLETED |
| E T03 필수 로그 계약 | 4 | 필요한 실제 로그 조회까지 진행 후 최종 COMPLETED |

최종 Mock 재현 **14개 assertion 통과**. B/C에서 세 번째 조사 Content는
user/model/user/model/user이며 FunctionResponse 2개가 포함됐다.
최종 JSON은 별도 user Content 1개이고 tools가 없었다.
조사 timeout/허용 헤더 15초, 최종 후보 30초도 구조적으로 관측했다.
이는 SDK 직렬화+Mock 전송이며 실제 Gemini 서버 지원·지연·성공률 측정이 아니다.
첫 임시 재현의 핵심 result 누락 사례에서는 예상 오류 코드를 EVIDENCE_MISMATCH로 두어 assertion이 실패했다.
실제 실패가 더 앞선 ERROR gate의 INSUFFICIENT_EVIDENCE임을 확인하고 임시 분석의 예상만 정정했다.
프로젝트 테스트나 운영 validator는 변경하지 않았다.

기존 테스트 실행은 Miniconda vision-insight에서 다음 8개 모듈을 대상으로 했다.
`test_agent_error_policy`, `test_agent_t05_preflight`, `test_agent_warning_policy_integration`,
`test_agent_efficiency`, `test_agent_service`, `test_agent_operating_timeouts`,
`test_agent_error_measurements`, `test_agent_api`.
실행 옵션은 `pytest -q -p no:cacheprovider --basetemp <외부 임시 디렉터리>`였다.
HTTP transport 차단과 프로젝트 내 쓰기 금지 audit guard를 함께 적용했다.

- **기존 관련 pytest 353 PASS**, 12.46초, 경고 1건(anyio 선행 import에 따른 assert rewrite 안내).
- 실제 외부 transport 시도 **0회**, 실제 Gemini API 요청 **0회**.
- 신규 영구 테스트/테스트 변경 **0개**. 14개 임시 재현을 pytest 신규 개수에 합산하지 않는다.
- 전체 pytest는 미실행: 운영·테스트 변경 없는 원인 분석 단계라 직접 관련 회귀에 한정했다.
  기존 전체 928 PASS는 이전 회차 결과다.
- `python -m pip check`: No broken requirements found.
- `git diff --check`: 공백 오류 없음. 기존 LF/CRLF 안내는 별도 경고다.

### F. 대안 비교와 최소 수정 설계 — 구현하지 않음

| 대안 | 장점 | 위험 / 기존 영향 | 예상 파일 / 테스트 | 추천 |
|---|---|---|---|---|
| A 모든 ERROR에서 `error_required_facts` 충족 시 종료 | 기존 validator 재사용, 조사 응답을 줄일 수 있음 | 일반 실패 14개도 통과하며 복합/추론 오류에 필요한 맥락이 끝났다는 보장이 없음 | error_policy.py / service.py, 모든 ERROR 유형의 충분성·누락 회귀 필요 | 일괄 적용 비추천 |
| B ERROR 전용 ready를 추가하되 확인된 이미지 로딩 실패 계약으로 범위 제한 | T05의 실제 17개 계약과 안전한 종료를 직접 연결, 정상/경고 분리 | 마지막 FunctionResponse 전송 의미 및 알 수 없는 추가 맥락, 최종 생성 실패 가능성 | error_policy.py / service.py, T05 양성·음성/다른 ERROR 비적용 테스트 | 최소 범위 추천 |
| C 요청 수·시간 예산만 조정 | 원인별 종료 규칙을 만들지 않음 | 근거 충분 후 조사 요청이 그대로 남고, 단순 상한 축소는 필요한 조사까지 실패시킬 수 있음. timeout 확대는 지연 증가 | service.py / 설정·timeout 테스트, 전체 예산 회귀 | 이번 원인에 대한 단독 해결책으로 비추천 |

추천 B의 설계:

1. `error_policy.py`에 이미지 로딩 실패용 독립 충분성 함수(예: `error_evidence_ready`)를 둔다.
   검사 ID 하드코딩 없이 FAILED/ERROR/INSPECTION_FAILED와 실제 성공 Trace/Evidence를 기준으로 한다.
2. 기존 `error_required_facts`를 재사용해 두 필수 도구, 일치하는 검사 ID, 실제 값,
   두 오류 이벤트의 정확한 stage/유효 시각, null 5개와 SKIPPED/UNKNOWN을 검증한다.
   이 T05 유형의 17개 집합 전체를 요구하되 **개수만 17인지 비교하는 것으로 대체하지 않는다**.
3. 실제 IMAGE_LOAD_FAILED가 없거나 일반 실패만 있으면 이 빠른 경로는 False다.
   INFERENCE_FAILED·복합/미지원 오류, 상충하거나 실패한 Trace, 미충족 서버 추가 조사 계약이 있으면
   좁은 빠른 경로로 종료하지 않는다. 다른 오류 유형 지원은 별도 계약과 승인이 필요하다.
4. `service.py:337`에 기존 정상 OR 경고 조건을 보존한 채 새 조건만 OR로 연결한다.
   동일 모델 응답의 도구 배치는 모두 처리하고, 기존 `service.py:366`에서만 종료를 판단한다.
   함수는 준비되지 않은 경우 False를 반환하고 도구를 자동 호출하거나 가짜 Evidence를 만들지 않는다.
   복구 가능한 근거 부족과 내부 오류/컨텍스트 초과를 구별해 무차별 예외 무시는 하지 않는다.
5. 루프 뒤 ERROR gate를 그대로 유지한다. 카탈로그 → 단순 JSON → DiagnosisDraft/Pydantic →
   `_verify_report` → `error_report_covered`의 17개 사실/ID/Pointer/null/판정/원인·권고 검증도 그대로 둔다.
   조사 충분성과 최종 보고서 성공은 계속 독립된 단계다.
6. 모델/SDK/스키마/프롬프트/도구/호출 한도/전체 60초/조사 15초/최종 기본 15초는 변경하지 않는다.
   최종 30초는 승인된 회차에서만 선택하고 잔여 예산-2초로 제한한다. 재시도도 활성화하지 않는다.

**FunctionResponse 계약 주의:** 두 번째 도구 직후 종료하면 로그의 FunctionResponse는 로컬 이력에
정상 구성되지만 그 이력을 사용하는 다음 조사 HTTP 요청은 생략된다.
최종 요청에는 독립 카탈로그로 실제 로그 Evidence를 전달하므로 동일 정보를 잃는 것은 아니나,
"마지막 FunctionResponse 후속 조사 요청이 서버에서 성공했다"고 주장할 수는 없다.
이는 기존 T03 독립 최종 요청 방식과 같은 경계다. 모든 FunctionResponse의 별도 조사 응답 확인을
필수 계약으로 유지한다면 요청 3 생략과 그 확인을 동시에 달성할 수 없으므로 사용자 판단이 필요하다.
서명/호출 ID를 변경하거나 가짜 ACK를 생성하는 방식은 제안하지 않는다.

현재 Mock 기본 경로의 조사 3회+최종 1회는 설계 B에서 조사 2회+최종 1회가 되는 것이 예상이다.
이는 해당 도구 순서에 대한 **구조적 예상 4→3회**이지 실제 측정된 지연·비용 절감이나 성공 보장이 아니다.
실제 실패 회차의 요청 3이 최종 JSON 요청으로 대체될 수 있다는 뜻이지,
실패한 총 3요청이 항상 총 2요청으로 줄어든다는 뜻도 아니다.
최종 JSON은 30초로도 실패하거나 보고서 검증에서 거부될 수 있다.

### G. 후속 테스트 계획과 승인 경계

구현 승인을 받으면 최소 운영 변경 예상은 `backend/agent/error_policy.py`,
`backend/agent/service.py` 두 파일이다. 프롬프트·DiagnosisDraft·출력 스키마 변경은 필요 없다고 판단한다.
직접 관련 테스트는 `tests/test_agent_error_policy.py`, `tests/test_agent_t05_preflight.py`의
기존 "ERROR는 항상 ready=False / 모델 종료를 기다려 4회" 전제를 분석 범위에 맞게 분리해야 한다.
새 좁은 ready 양성 및 범위 밖 ERROR 음성을 함께 두며, 일반 ERROR 비적용 assertions를 지워서는 안 된다.
계측은 기존 policy collection과 별도로 실제 ERROR stop 분기를 식별하는 관측만 필요할 수 있다.
이는 추후 허용될 때 `scripts/agent_validation_measurements.py`와 관련 계측 테스트에서 검토한다.

필요한 후속 assertions:

- 두 필수 도구/두 실제 오류 이벤트/17개 근거 충족 직후 다음 요청이 **조사가 아닌 최종 JSON**인지 확인.
- 로그 미조회/조회 실패/빈 로그, 이벤트·상태·null·시각·소유권·Trace 불일치는 ready=False 또는 안전 실패.
- 원천 근거가 충분해도 보고서에서 17개 중 하나 누락, 가짜 토큰/Pointer, null→0,
  SKIPPED만으로 모델 장애 원인/복구 권고, 원본 판정 변경 시 거부.
- INFERENCE_FAILED, 일반 INSPECTION_FAILED만 존재, 복합/미지원 오류는 새 빠른 경로에 진입하지 않음.
- T01/T03/T03 필수 로그/T06 저장 OK의 기존 경계, 도구 배치/호출 ID/서명/Trace와 독립 최종 Content 유지.
- 최종 요청 15/30초 및 잔여 예산 축소, 전체 60초, 재시도 없음, 504/JSON/근거 오류 매핑 유지.
- 계측의 ERROR 조사 충분성 True와 최종 보고서 검증 NOT TESTED/FAIL/PASS가 혼동되지 않음.

기존 회차의 정확한 요청 바이트/서버 부하/서버 내부 deadline, 요청 3의 모델 의도와 504 내부 원인은 UNKNOWN이다.
추가로 계측한다면 종료 결정의 policy/reason, ERROR required/collected 항목 수,
필수 추가 조사 요구 및 남은 예산 등 안전한 구조 메타데이터만 기록할 것을 제안한다.

이번 전후 비교는 기존 **162개 파일**을 대상으로 했다.
발표 자료를 제외한 **127개는 모두 SHA256 동일**했으며 backend/tests/scripts,
운영 JSONL 2개, 모델/메타데이터, 기존 수동 회차의 READY·결과·잠금을 포함한다.
별도 발표 영역 35개 중 5개 문서의 변경이 관측됐다. 이 작업에서 쓰지 않았고 작성 주체는 확정하지 않았다.
사용자/다른 에이전트 동시 작업으로 취급하여 수정·복원하지 않았으며 발표 자료 전체 불변을 주장하지 않는다.
검증 문서만 기존 기록을 보존하여 이 섹션을 추가했다.

다음 단계는 **운영 ERROR 종료 정책 최소 통합과 그 테스트에 대한 별도 승인**이다.
그 이후 실제 E2E 검증도 새 명시적 승인과 안전한 새 회차가 필요하다.
이번에는 이미 사용한 T05 회차를 재실행하거나 새 READY/잠금을 만들지 않았다.
T06 분석, 실제 API 호출, 운영 수정 및 후속 개발 없이 여기서 중단한다.

## T05 이미지 로딩 실패 전용 조사 조기 종료 — 운영 통합 및 오프라인 회귀

### A. 구현 범위와 이전 실패의 구분

**운영 종료 정책 및 오프라인 검증: PASS. 실제 Gemini 재검증: NOT TESTED.**
기존 `t05_operational_final30_1`의 조사 요청 3 HTTP 504 / DEADLINE_EXCEEDED,
FastAPI 502 / FAILED, 18.673초, 확인된 3,128토큰 기록은 그대로 보존한다.
이번 수정은 ERROR 필수 근거가 충분해도 정상/경고 조건만 검사해 조사를 계속했던 분기만 보완한다.
Google 서버 내부의 504 원인을 해결했다거나 최종 JSON 30초가 성공한다고 주장하지 않는다.

운영 변경은 다음 두 파일뿐이다.

- `backend/agent/error_policy.py:100`: `image_load_failure_evidence_ready(state)` 추가.
- `backend/agent/service.py:339`: 기존 정상 OR 경고 종료 뒤 새 predicate 연결.
  잘못된 snapshot 자료형은 False로 처리하고, 서버의 추가 필수 이벤트 계약이 설정돼 있으면
  새 이미지 로딩 실패 경로로 종료하지 않는다.

프롬프트, JSON Schema, config, SDK/모델 설정, scripts는 수정하지 않았다.
기존 사용자 작업을 되돌리지 않고 허용된 정책·직접 관련 테스트·이 문서만 수정했다.

### B. 정확한 충분성 조건과 validator 재사용

새 helper는 기존 `error_required_facts(state)`의 결과를 그대로 사용한다.
17개 사실의 필드 목록이나 null 판정 규칙을 새 운영 helper에 복사하거나,
단순히 도구 2회/사실 수 17인지 비교하는 규칙을 만들지 않았다.

1. 기존 ERROR validator가 FAILED / ERROR / INSPECTION_FAILED, 검사 ID,
   성공한 결과·로그 도구의 Trace/Evidence 연결과 실제 필드·값을 검증해야 한다.
2. 반환된 필수 사실의 이벤트 집합이 실제 IMAGE_LOAD_FAILED와 INSPECTION_FAILED여야 한다.
   이 조건으로 기존 validator의 이미지 로딩 실패 분기가 요구하는 UNKNOWN / ERROR / SKIPPED,
   미산출 null 5개, 실제 오류 stage·level·시각 및 순서 검사를 재사용한다.
3. 모든 Trace가 실제 실행/성공, error_code 없음, 필수 사실에서 유도한 도구에 속함,
   정확히 동일 inspection_id 인자여야 한다. 추가 도구나 실패한 조사를 조용히 무시하지 않는다.
4. Trace Evidence ID 집합과 실제 Evidence Store 키가 일치해야 한다.
   소유권·metadata·카탈로그 일관성은 기존 validator와 build_catalog가 함께 검사한다.
5. 누락·잘못된 타입·validator 오류 등 예외가 있으면 helper는 False다.
   서버의 추가 필수 경고 이벤트 계약이 비어 있지 않으면 Service도 이 빠른 종료를 선택하지 않는다.

T05 합성 fixture에서 기존 validator가 반환한 필수 근거는 실제로 **17개**였다.
일반 INSPECTION_FAILED만 있는 오류, INFERENCE_FAILED 또는 복합/미지원 ERROR 이벤트,
로그 미조회/실패, UNKNOWN·SKIPPED만 존재하는 상태에는 새 종료를 적용하지 않는다.
검사 ID `INSP-001405` 자체는 운영 코드에 하드코딩하지 않았다.

기존 루프 뒤 `error_required_facts` gate와 최종 `error_report_covered`를 모두 유지한다.
조사 충분성 True는 최종 보고서 성공을 뜻하지 않는다. 단순 JSON 파싱·토큰 매핑·DiagnosisDraft·
Pydantic·Fact/Evidence/Pointer·null·원인/권고 근거·원본 판정 보호 검증을 그대로 실행한다.
새 predicate가 잘못 True를 반환하는 테스트에서도 루프 뒤 gate가 로그 누락을 차단했다.

### C. 마지막 FunctionResponse와 독립 최종 요청

별도 ACK용 조사 요청은 현재 독립 최종 JSON 계약의 필수 단계가 아니다.
SDK 직렬화와 MockTransport로 다음을 검증했다.

- 도구 배치를 모두 실행한 뒤 종료를 판단한다. 같은 모델 응답의 도구를 중간에 버리지 않는다.
- 마지막 get_execution_logs 결과는 E0002로 서버 Evidence Store에 보존된다.
- 실제 FunctionResponse를 원래 함수 이름/호출 ID로 user Content에 구성한다.
  조사 모델의 Content/Part/서명은 변경하지 않으며 완성된 로컬 이력은 `_validate_history`를 통과한다.
- 마지막 로그 FunctionResponse를 포함하는 **별도 조사 HTTP 요청은 생략**된다.
  그 요청이 Gemini에서 성공하거나 마지막 응답이 별도로 ACK됐다고 보고하지 않는다.
- 최종 JSON 요청은 T03과 동일하게 조사 이력을 재사용하지 않는 독립 user Content다.
  tools/tool_config/function-call/response 이력을 포함하지 않으므로 미해결 조사 이력을 전송하지 않는다.
- 두 도구의 실제 근거가 모두 최종 카탈로그에 포함되며, 기존 validator의 17개 항목을
  Evidence ID / source_tool / JSON Pointer / event / 실제 값 단위로 대조했다.
  최종 Mock JSON 선택 토큰 → DiagnosisDraft → Pydantic → 결정적 검증까지 통과했다.

순차 도구 조회에서는 **조사 2회 + 최종 JSON 1회 = Mock 요청 3회**다.
두 도구가 같은 모델 응답에 포함된 별도 Mock에서는 조사 1회 + 최종 1회이며,
두 도구와 두 Evidence가 모두 보존됐다. 실제 모델이 항상 같은 순서/횟수를 선택한다는 보장은 아니다.
실서버에서 이 변경을 실행한 것은 아니므로 최종 요청 수락·지연·내용 품질은 NOT TESTED다.

### D. 테스트 변경과 안전성 검증

새 파일 `tests/test_agent_image_load_stop.py`의 **42개**는 충분성/누락/타입/소유권/이벤트/
예외/추가 조사 계약, 배치 및 순차 프로토콜, 15/30초 최종 설정, 최종 사실 누락,
루프 뒤 gate 유지와 다른 ERROR의 모델 종료 대기를 검증한다.
기존 `test_agent_error_policy.py`의 필수 사실 누락 매개변수에 image_quality_status를 추가해
전체 17개 각각의 보고서 누락 거부를 확인했다(기존보다 **1개** 증가).
기존 계측기의 레이블 한계를 드러내는 테스트 **1개**를 추가했다.
따라서 전체 신규 테스트 증가는 **44개**, 기존 928 + 44 = **972개**다.

직접 관련된 기존 T05 성공 Mock에서 불필요한 모델 종료 text 응답을 제거하고 기대 요청 수를 4→3으로 바꿨다.
근거가 부족하거나 일반/추론 ERROR인 경우에는 `continue_investigation=True` fixture로 기존 모델 종료 대기를 유지했다.
보고서 사실·값·ID·Pointer 검증이나 오류 기대 조건은 완화하지 않았다.

수정한 기존 테스트 모듈:
`tests/test_agent_t05_preflight.py`, `tests/test_agent_error_policy.py`, `tests/test_agent_service.py`,
`tests/test_agent_api.py`, `tests/test_agent_efficiency.py`, `tests/test_agent_report_request.py`,
`tests/test_agent_reporting_integration.py`, `tests/test_agent_operating_timeouts.py`,
`tests/test_agent_timeout_policy_experiment.py`, `tests/test_agent_warning_policy_experiment.py`,
`tests/test_agent_validation_measurements.py`.

| 대상 | 오프라인 확인 |
|---|---|
| 이미지 로딩 실패 + 근거 충분 | ready=True, 후속 조사 없음, 순차 3요청 / 도구 2회 / 17개 최종 사실 검증 PASS |
| IMAGE_LOAD_FAILED / INSPECTION_FAILED / 필수 도구·필드·Evidence 누락 | ready=False, 기존 추가 조사 또는 안전 차단 |
| 검사 ID·Trace·metadata·시각·단계·값 불일치 | ready=False; 기존 validator도 거부 |
| 일반 ERROR / 실제 INFERENCE_FAILED / 복합 오류 | 새 ready=False, 기존 ERROR 계약 유지 |
| 추가 도구/서버 필수 이벤트 계약 | 빠른 종료하지 않음 |
| 최종 보고서 필수 사실 부족·null→0·가짜 Evidence/Pointer·판정 충돌 | 기존 검증에서 거부 |
| SKIPPED / UNKNOWN 기반 모델 장애 원인·복구 권고 | 근거 부족으로 거부 |
| 별도 실제 INFERENCE_FAILED 근거 | 기존 모델 장애 가설 검토 계약 유지 |
| T01 / T06과 같은 저장 OK | 기존 정상 경로, 평가 정답 없이 2요청 Mock PASS |
| T03 / 필수 로그 있는 T03 | 기존 경고 충분성·보고서 커버리지·요청 수 유지 |
| 504 / timeout / 반복·도구·라운드 상한 | 기존 안전 오류 매핑과 제한 유지 |

초기 단위 실행에서 잘못된 snapshot이 list일 때 기존 정상 종료 검사에서 AttributeError가 발생했다.
helper는 이미 False였지만 Service 진입부의 자료형 guard를 추가해 같은 음성 테스트를 통과시켰다.
테스트 삭제나 조건 완화로 처리하지 않았다.

### E. 테스트 실행 결과와 환경 격리

Conda vision-insight Python에서 실제 HTTP transport를 차단하고 `PYTHONDONTWRITEBYTECODE=1`,
pytest cache 비활성화, 외부 임시 basetemp, 프로젝트 내 쓰기 차단 audit guard를 적용했다.
SDK 직렬화 테스트의 전송은 MockTransport만 사용했다.

| 실행 범위 | 실제 결과 |
|---|---|
| 최초 신규 predicate 단위 선택 | 31 PASS / 1 FAIL — 위 snapshot 자료형 문제 확인 |
| 보완 후 신규 모듈 전체(단위 32 + 통합/안전 10) | **42 PASS**, 4.50초 |
| 기존 T05·경고·정상·API·timeout·계측 등 관련 13개 모듈 | **518 PASS**, 10.03초 |
| 계측 한계 테스트 추가 후 Agent 전체 `tests/test_agent*.py` | **867 PASS**, 12.28초 |
| 최초 전체 실행 | **924 PASS / 48 FAIL**, 운영 JSONL 쓰기를 보호 guard가 차단 |
| 출력 경로 격리 후 전체 `pytest tests -q -p no:cacheprovider` | **972 PASS**, 26.93초, 경고 3건 |
| `python -m pip check` | No broken requirements found |
| `git diff --check` | 공백 오류 없음; 기존 LF/CRLF 안내만 존재 |

최초 전체 실패는 Agent 회귀가 아니라 기존 Vision 통합 테스트가 기본 운영 저장 경로로 쓰려 했기 때문이다.
guard를 해제하거나 테스트를 삭제하지 않았다. 재실행 자식 프로세스에서만 INSPECTIONS_FILE,
INSPECTION_LOGS_FILE, OUTPUT_DIR, LOG_DIR, TEST_DATA_DIR을 외부 임시 경로로 설정했다.
기존 중립 이름의 주입 이미지 fixture만 임시 디렉터리에 복사했고 기존 Vision 테스트의 쓰기도
그 안에 격리했다. OpenCV 출력 역시 프로젝트 내 쓰기를 차단했다.
운영 설정 파일·환경변수 기본값·검사 JSONL은 변경하지 않았다.
신규 이미지 일반화 실험을 추가한 것이 아니라 요청된 기존 전체 회귀를 실행한 것이다.

최종 전체 경고 3건은 기존 timm/anomalib FutureWarning 2건과
가드 실행기의 httpx/anyio 선행 import에 따른 pytest assert-rewrite 안내 1건이다.
실제 외부 HTTP transport 시도는 모든 실행에서 **0회**였다.

### F. 계측 레이블의 남은 한계 — scripts 수정 안 함

기존 `scripts/agent_validation_measurements.py:314`는 ready이고 정상 경로가 아니면
모두 `policy="WARNING"`으로 기록한다. 새 ERROR 종료에서도 이 레이블은 잘못 표시된다.
이 레이블을 ERROR 정책 또는 경고 정책의 성공 증거로 사용해서는 안 된다.
이번에 허용되지 않은 scripts를 변경하지 않았으며 이 한계를 명시적으로 재현하는 테스트를 추가했다.

실제 운영 종료 predicate, ERROR applicability, 17개 원천 근거 수집 및 최종 보고서 검증은
이 레이블과 독립적으로 확인했다. 기존 계측 회귀의 T05 기대 요청 수는 3회로 갱신하되
WARNING 레이블은 **기존 계측의 한계**임을 별도 테스트로 드러냈다.
실서버 재검증 전에 ERROR/IMAGE_LOAD_FAILURE 분기 식별을 위한 계측 보완을 별도 승인받는 것이 권장된다.

### G. 불변성과 다음 단계

- 조사 15초 / 최종 기본 15초 / 승인 시 선택 상한 30초 / 전체 60초 / 안전 여유 2초 유지.
  SDK attempts=1, 자동·수동 재시도 활성화 없음. timeout 설정 파일은 변경하지 않았다.
- 전후 비교한 기존 162개 중 허용된 운영 2개·직접 관련 테스트 11개만 변경됐다.
  **나머지 149개 SHA256은 모두 동일**하며 운영 JSONL, 모델/메타데이터, 변경 금지 backend 설정/프롬프트,
  scripts, 기존 회차 READY/잠금/결과, 발표 자료 35개를 포함한다.
- 신규 파일은 오프라인 테스트 `tests/test_agent_image_load_stop.py` 하나다.
  문서는 기존 실패/분석 기록을 유지한 채 이 섹션만 추가했다.
- 원본 검사 상태 및 임계값 34.1442를 변경하지 않았다. 평가 Ground Truth는 Agent에 전달하지 않았다.
  기존 T05 15초 READY와 사용된 30초 회차를 그대로 보존했고 새 실제 검증 회차는 만들지 않았다.
- 실제 Gemini 분석 **0회**, 실제 Gemini API 요청 **0회**, Git add/commit/push **0건**.

운영 분기의 오프라인 완료 기준은 충족했다. 마지막 FunctionResponse의 별도 조사 ACK는
의도적으로 요청하지 않으며, 독립 최종 카탈로그 전달과 최종 엄격 검증으로 구별한다.
실제 T05의 최종 JSON 30초 성공 여부·지연·내용 품질, 기존 Google 504 내부 원인은 여전히 미확인이다.
다음은 필요 시 계측기 레이블 보완 승인, 새 검증 회차 준비 승인 및 실제 T05 단일 E2E 승인이다.
T05/T06 실서버 분석, 회차 생성, 후속 개발 또는 Git 작업 없이 여기서 중단한다.

## T05 계측 WARNING 정합화 — 최소 수정 및 오프라인 검증

**결과: PASS(계측/오프라인). 실제 T05 E2E는 기존 FAIL 기록 그대로다.**

- 원인: `record_investigation_stop`이 ready=True이고 정상 경로가 아니면 모두 WARNING으로 분류했다.
  운영 이미지 로딩 실패 종료가 추가된 뒤에도 같은 이분법이 남아 있었다.
- 변경: `scripts/agent_validation_measurements.py`와 직접 관련된
  `tests/test_agent_validation_measurements.py`만 수정했다. 수동 T05 스크립트 수정은 필요 없었다.
  운영 Agent/ERROR 정책/timeout/프롬프트/Schema는 변경하지 않았다.
- 실제 종료 결과를 그대로 반환하면서 기존 정상 판정, 운영 `warning_evidence_ready`,
  운영 `image_load_failure_evidence_ready`를 재사용해 NORMAL / WARNING / IMAGE_LOAD_FAILURE를 구분한다.
  추가 필수 이벤트 계약도 고려한다. 17개 근거 규칙은 계측기에 복제하지 않았다.
- ready=False는 기존 CONTINUE를 유지한다. ready=True여도 유형을 입증할 수 없거나
  정책 관측에 예외가 있으면 UNKNOWN이다. 오류를 정상 처리하거나 FAIL/BLOCKED를 해제하지 않는다.

기존 출력의 `early_exit_checks.ready/policy`만 정정했으며 별도 출력 필드를 무리하게 추가하지 않았다.
단계 구분은 기존 항목을 사용한다.

| 단계 | 기존 확인 항목 |
|---|---|
| 필수 도구·이벤트·원천 사실 수집 | error_policy의 required_tools / required_event_codes / required_fact_count / required_evidence_collected |
| 실제 조기 종료와 유형 | early_exit_checks의 ready / policy; 검증된 이미지 로딩 실패는 IMAGE_LOAD_FAILURE |
| 최종 JSON 단계 진입 | sdk_requests의 STRUCTURED_OUTPUT 항목; 진입과 요청 성공은 별개 |
| 최종 보고서 검증 | error_policy.report_validation_passed 및 기존 JSON/Pydantic/Evidence 검증 항목 |

원천 근거만 확보한 상태의 보고서 검증은 NOT TESTED를 유지했다.
합성 T05 성공 Mock에서는 조사 2회+최종 JSON 1회, 17개 관측 사실 및 최종 검증 COMPLETED를 확인했다.
이는 실제 Gemini E2E PASS가 아니다. T05 최종 Mock 504는 GEMINI_REQUEST_FAILED / FAILED와
STRUCTURED_OUTPUT 실패 단계를 그대로 유지했고, 기존 실서버 FAIL 결과 파일은 수정하지 않았다.

검증한 음성 사례는 필수 도구 누락/실패, 오류 이벤트·사실 누락, 검사 ID·Evidence 불일치,
추론 실패, 추가 필수 이벤트 조건이다. 모두 IMAGE_LOAD_FAILURE로 잘못 표시하지 않았다.
기존 T01/T03, 15/30초 설정·회차 충돌 차단, 근거 수집과 보고서 검증의 분리도 회귀 통과했다.

| 실행 | 결과 |
|---|---|
| 변경 분기 중심 선택 테스트 | 13 PASS; 이후 도구 실패 사례도 추가 |
| 관련 계측/T05/timeout 6개 모듈 | 181 PASS |
| 전체 pytest — 이번 작업에서 1회만 실행 | **984 PASS / 경고 3건**, 26.19초 |
| 신규 테스트 증가 | **12개**; 기존 972 + 12 = 984 |
| git diff --check | 공백 오류 없음; 기존 LF/CRLF 안내만 존재 |

전체 회귀는 앞서 검증한 외부 임시 JSONL/출력/주입 이미지 fixture 격리를 재사용했다.
실제 HTTP transport와 프로젝트 내 쓰기를 차단했고 외부 HTTP 시도는 0회였다.
경고 3건은 기존 timm/anomalib 안내 2건과 가드 실행기의 anyio assert-rewrite 안내 1건이다.
기존 보호 비교 대상 163개 중 위 계측/테스트 2개 외 **161개 SHA256 동일**을 확인했다.
backend 운영 코드, 운영 JSONL, 모델/메타데이터, 기존 READY/잠금/실서버 결과, 발표 자료를 보존했다.
이 문서는 기존 기록을 유지하며 본 섹션만 추가했다.

실제 Gemini 분석/API 요청 **0회**, 신규 실서버 회차 **0개**, Git add/commit/push **0건**이다.
다음에는 별도 승인 후 안전한 새 회차 준비와 T05 실제 단일 E2E가 필요하다.
최종 JSON 30초의 실제 T05 성공 여부와 이전 Google 504 내부 원인은 여전히 미확인이다.
계측 정합화까지만 완료하고 중단한다.
