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
