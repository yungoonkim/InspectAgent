# Day 4 Step 3: 검사 사후 분석 HTTP API

## 요청과 선행 조건

```powershell
curl.exe -X POST http://localhost:8000/analyze/INSP-000001
```

본문은 필요하지 않습니다. 서버 저장소에 해당 검사 기록이 있어야 합니다.
검사 ID는 `INSP-` 뒤 6~12자리 숫자이며 기존 Step 1 규칙을 재사용합니다.
형식 오류는 422, 존재하지 않는 검사는 Gemini 준비/호출 전에 404입니다.
슬래시를 포함해 라우트에 매칭되지 않는 경로 탐색 요청은 일반 라우팅 404가 될 수 있습니다.
`status=FAILED` 검사도 존재하는 기록이므로 분석 대상입니다.

이 API는 저장된 기록에 대한 사후 분석입니다. 새 검사·이미지 로드·OpenCV 분석·PatchCore
추론·검사 JSONL 수정·분석 결과 파일 저장을 수행하지 않습니다.
실제 Gemini 요청과 실제 모델 가용성/진단 품질 검증은 승인 후 Day 4 Step 4에서 수행합니다.
Step 3 검증은 Mock 서비스 또는 실제 AgentService에 주입한 Mock SDK 응답만 사용했습니다.

## 라우터와 생명주기

`backend/agent/api.py`의 APIRouter를 `backend/main.py`에 등록했습니다.
`get_analysis_storage()`는 기존 `get_inspection_storage()`의 동일한 저장소 싱글톤을
사용합니다. 입력 검증 → Step 1 조회 도구를 이용한 존재 확인 → Agent 준비 순서입니다.
HTTP의 선행 존재 확인은 모델이 선택한 도구 호출이 아니므로 Tool Trace에 기록하지 않습니다.

`get_agent_service()`는 이 저장소에 연결된 InspectionTools와 기존 AgentService를 준비합니다.
서비스의 근거 비교/Function Calling 로직은 수정하거나 중복 구현하지 않았습니다.
FastAPI dependency_overrides로 저장소와 서비스를 교체할 수 있습니다.

lifespan은 기존 PatchCore 사전 초기화를 유지하면서 비활성 AgentRuntime만 생성합니다.
SDK 클라이언트는 서버 시작 시 생성/호출하지 않고, 존재하는 검사에 대한 첫 분석 요청에서
지연 생성합니다. 클라이언트를 앱 범위에서 재사용하고 shutdown에서 비동기/동기 자원을 닫습니다.
초기화 lock으로 중복 생성을 방지합니다. 요청별 AgentService와 기존 RequestState가
독립된 Trace/근거/제품 범위를 유지합니다.

키가 없으면 서버와 `/health`, `/inspections`, `/inspections/images`, `/docs`는 유지됩니다.
분석 요청에서만 `503 MISSING_API_KEY`를 반환합니다.
앱 실행 중 이미 사용 중인 SDK의 키 또는 HTTP timeout 설정이 바뀌면
`503 AGENT_CONFIG_CHANGED`를 반환합니다. 설정 변경 후 서버 재시작이 필요합니다.

## 응답 계약과 판정의 출처

성공 응답은 기존 DiagnosisResult를 상속한 AnalysisResponse입니다.
`analysis_id`는 서버가 매 요청마다 UUID 기반으로 발급하고 timestamp는 UTC입니다.
`inspection_result`, `final_result`, `final_reason_code`는 선행 조회에서 얻은 저장 기록이
권위입니다. 구형 기록에 없는 종합 판정은 null이며 새 판정을 계산하지 않습니다.

Agent의 검사 ID·snapshot 핵심 필드·요약이 선행 조회 기록과 모순되면
`502 EVIDENCE_MISMATCH`로 거부합니다. snapshot의 공개 필드도 서버 기록으로 구성합니다.
Step 2의 실제 evidence_id/JSON pointer/수치/이벤트/가설 검증은 그대로 재사용합니다.
HTTP Pydantic 검증만으로 근거 일치를 보장한다고 주장하지 않습니다.

다음은 가짜 저장소와 Mock SDK를 사용해 실제 HTTP 200으로 받은 응답의 **발췌**입니다.
분석 ID·시각·elapsed_ms는 해당 실행에서 생성/측정한 값이며 실설비 측정이나 Gemini 호출 지연이 아닙니다.
전체 응답에는 아래 필드 외에도 검사 snapshot, 관측 사실 6개, 권고, 한계 및 토큰 메타데이터가 포함됩니다.

```json
{
  "analysis_id": "ANALYSIS-8ba058a5a9554a468bd074e4719557c7",
  "inspection_id": "INSP-000001",
  "analysis_status": "COMPLETED",
  "error_code": null,
  "inspection_result": "OK",
  "final_result": "OK",
  "final_reason_code": "ALL_CHECKS_PASSED",
  "overall_summary": "기록된 모델 판정과 종합 판정은 OK입니다. 실제 무결점 제품을 보증하지 않습니다.",
  "observed_facts": [
    {
      "fact_id": "F0001", "evidence_id": "E0001",
      "source_tool": "get_inspection_result", "source_field": "/data/status",
      "source_event": null, "observed_value": "COMPLETED"
    }
  ],
  "possible_causes": [],
  "tools_used": ["get_inspection_result"],
  "tool_execution_trace": [
    {
      "sequence": 1, "round_number": 1,
      "tool_name": "get_inspection_result",
      "arguments": {"inspection_id": "INSP-000001"},
      "executed": true, "success": true, "error_code": null,
      "elapsed_ms": 2.945, "evidence_id": "E0001"
    }
  ],
  "model_name": "gemini-mock",
  "model_availability": "NOT_TESTED",
  "timestamp": "2026-10-15T01:52:42.500094+00:00"
}
```

전체 필드 정의는 `backend/agent/schemas.py`의 AnalysisResponse/DiagnosisResult를 기준으로 합니다.

## HTTP 오류 계약

```json
{"detail": {"analysis_status": "FAILED", "error_code": "MISSING_API_KEY"}}
```

| 상황 | HTTP | 대표 코드 |
|---|---:|---|
| 성공 | 200 | error_code=null |
| 잘못된 ID | 422 | INVALID_ARGUMENT |
| 검사 없음 | 404 | NOT_FOUND |
| 설정/저장소/도구 사용 불가 | 503 | MISSING_API_KEY, INVALID_MODEL_CONFIG, STORAGE_ERROR, TOOL_EXECUTION_FAILED |
| 외부 서비스/출력/근거 오류 | 502 | GEMINI_REQUEST_FAILED, RESPONSE_SCHEMA_INVALID, EVIDENCE_MISMATCH |
| 시간 초과 | 504 | AGENT_TIMEOUT, GEMINI_TIMEOUT, TOOL_TIMEOUT |
| 예상하지 못한 오류 | 500 | AGENT_INTERNAL_ERROR |

안정적인 코드만 반환하고 원본 예외·모델 원문·인증·경로는 반환하지 않습니다.
실패 응답에서는 상세 진단/Trace를 공개하지 않으며 실패를 HTTP 200으로 처리하지 않습니다.
전체 매핑은 `backend/agent/api.py`의 ERROR_STATUS에 정의합니다.

## Swagger와 검증 범위

`/openapi.json`에 POST 경로, 중립 검사 ID 설명, AnalysisResponse,
AnalysisErrorResponse, 200/404/422/500/502/503/504를 등록했습니다. `/docs`도 정상 동작합니다.
Step 1/2 도구·서비스, 모델·임계값·기존 검사 API 계약을 유지합니다.
실행 중인 동기 조회 스레드의 강제 종료 제한, 스토리지 I/O deadline,
JSONL 동시성/영구 저장과 실제 Gemini 검증은 남은 과제입니다.

검증 결과:

- Step 3 신규 API 테스트 69개 통과 (마지막 서버 시작 검증은 전체 실행에 포함)
- 기존 246개를 포함한 전체 315개 통과, 실패/건너뜀 0개
- 기존 timm/anomalib FutureWarning 2건
- 연속/동시 요청의 고유 analysis_id 및 요청별 Trace/검사 범위 분리 확인
- 동일 SDK 클라이언트 지연 생성/재사용/종료를 Mock으로 확인
- 운영 JSONL 두 파일, 체크포인트·메타데이터, 기존 도구/Agent 서비스/프롬프트/판정/검사 코드,
  기존 주입 이미지의 전체 테스트 전후 SHA256 일치

Conda `vision-insight`의 Python으로 다음을 실행했습니다.

```powershell
python -m pytest tests/test_agent_api.py -v
python -m pytest tests -v
```

실제 명령에는 캐시를 끄는 `-p no:cacheprovider`와 고유 `--basetemp`를 추가했습니다.
전체 회귀의 저장 경로·주입 이미지·출력은 임시 디렉터리로 격리하고 기존 주입 이미지 사본을 준비했습니다.
테스트의 Agent/SDK는 가짜 저장소 또는 임시 JSONL에 연결되며 실제 Gemini API 요청은 없습니다.
