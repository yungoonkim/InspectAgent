# Day7 Step6-B — Agent 실효 설정 및 단일 실행 안전장치

작성: 2026-10-18. 실제 Gemini/실서버 분석 POST 없이 수행했다.

## A. 차단 원인별 해결 여부

**안전장치 구현·오프라인 검증: COMPLETE. Live 재시도 준비: READY WITH RISKS. Live 성공 여부: NOT VERIFIED.**

| 기존 차단 원인 | 보완 | 확인 수준 |
|---|---|---|
| 별도 Python 프로세스 설정만 확인 | 분석 서버 내부 설정 조회 + 실제 POST 의존성의 사전 검증 | CONFIRMED: 실제 localhost GET 200, 설정 일치 |
| TCP 상태로 동시 분석 여부를 추정 | POST 진입 시 비차단 OS 파일 Lock 획득, 경쟁 요청 409 | CONFIRMED: Fake 동시 HTTP 및 별도 Python 프로세스 경합 검증 |
| 기본 Tool Loop 계산상 최대 6회였음 | 요청별 실제 dispatch 카운터로 7번째 호출 전 차단 | CONFIRMED: 직접 경계 및 다회차 Loop 검증 |

기존 `AgentRuntime._lock`은 SDK Client 생성만 직렬화했다. 분석 전체의 실행권은 없었다. SDK attempts=1과 자동 Function Calling 비활성화는 이미 있었으므로 값을 바꾸지 않았다. 기존 ThreadPool/4개 slot은 읽기 전용 Python 도구 제한이지 분석 요청 제한이 아니다.

## B. 실효 설정 검증

### 실제 서버 관측

`GET http://127.0.0.1:8000/agent/runtime-safety`만 호출했다. 이 GET은 Client 생성·Gemini 요청·검사·보고서 저장을 하지 않는다. 비밀값 대신 설정 whitelist와 인증정보 구성 여부 boolean만 반환한다.

최종 관측: `safety_revision=day7-step6b-v1`, PID **8532**, `configuration_matches=true`, `credentials_configured=true`, `client_initialized=false`, `client_configuration_matches=true`.

| 항목 | 서버 내부 관측값 |
|---|---|
| Model | gemini-3.8-flash |
| SDK / API | google-genai 2.31.0 / v1beta |
| SDK attempts / 자동 Retry | 1 / 0 |
| Tool Round / Call / 동일 인자 반복 | 4 / 8 / 2 |
| Provider dispatch 상한 | 6, 최종 structured 요청 포함 |
| Agent 전체 deadline | 60초 |
| 조사 / 최종 모델 요청 timeout | 각각 최대 15초 |
| Python 도구 대기 timeout | 3초 |
| max_output_tokens / payload 상한 | 4096 / 65536 bytes |

최종 요청 timeout은 남은 Agent budget에 따라 더 짧아질 수 있다. Agent deadline은 의존성 조회·보고서 파일 저장까지 포함한 HTTP 전체 timeout 보장은 아니다. SDK 버전/모델/제한/timeout이 승인 프로필과 달라지면 실제 POST에서 Client 생성 전에 `503 AGENT_RUNTIME_CONFIG_MISMATCH`로 거부한다. API 키 미설정은 기존 `MISSING_API_KEY` 계약을 유지한다. 인증정보/Client 생성 timeout 변경에 대한 기존 `AGENT_CONFIG_CHANGED`도 유지한다.

설정 기대값은 새 검증 정책이며 Production Generation Config를 수정하거나 덮어쓰지 않는다. 향후 모델/SDK/timeout 변경은 기대 프로필도 재검토해야 한다.

### 진단 경로 제한

- 소켓 peer가 loopback이고 요청 URL host가 localhost/127.0.0.1/::1인 경우만 허용한다. 그 외 404.
- OpenAPI에는 노출하지 않는다. 응답에 키·인증 헤더·원본 환경변수·Prompt·Tool Response·파일 경로가 없다.
- `worker_count=UNKNOWN`을 반환한다. 애플리케이션이 전체 프로세스 수를 스스로 확정했다고 주장하지 않는다.
- 로컬 직접 접속 점검 전용이다. 공개 배포/프록시 경유의 인증 수단이 아니며 공개 라우팅 대상에 포함하지 않아야 한다.

근거: `backend/agent/api.py:168`, `backend/agent/api.py:206`, `backend/agent/runtime_safety.py:28`, `backend/agent/runtime_safety.py:43`.

## C. 분석 동시 실행 차단과 Worker 범위

POST route-level yield dependency가 먼저 비차단 실행권을 얻는다. 경쟁 요청은 `409 AGENT_BUSY`로 즉시 종료하며 Context 조회·Client 생성·Provider 호출 이전에 차단된다. 읽기/저장/응답 검증까지 실행권 안에서 처리한다. 성공·실패·timeout·취소 시 `finally`로 handle을 닫는다. Lock 파일을 제거하는 정리 코드는 없다.

- Windows: `msvcrt.locking(LK_NBLCK)`의 첫 byte 배타 Lock.
- POSIX: 비차단 `flock(LOCK_EX | LOCK_NB)`.
- Lock 파일은 체크아웃 경로의 hash로 식별하여 로컬 TEMP에 둔다. 운영 JSONL/Agent Report/Sidecar는 Lock 저장소로 사용하지 않는다.
- 메모리 Lock과 달리 같은 체크아웃·같은 TEMP namespace의 다른 Worker/프로세스에도 적용된다. 별도 Python subprocess가 소유 중에는 거부되고 해제 후 획득되는 것을 검증했다.
- 파일 접근/Lock 오류는 `503 AGENT_ADMISSION_UNAVAILABLE`로 fail closed. 프로세스 종료 시 OS가 handle Lock을 회수한다.
- 다른 사용자·다른 TEMP·다른 체크아웃·다른 호스트/replica까지 보호하지 않는다. Redis/DB 기반 분산 Lock 또는 공개 운영용 인증을 구현한 것이 아니다. 실행 중 Lock 파일을 외부에서 삭제/교체해서는 안 된다.

프로세스 읽기 전용 감사에서는 8000 listener PID28464가 vision-insight 환경의 기존 `uvicorn --reload` 프로세스였고 명시적 `--workers` 인자가 없었다. 당시 직접 child PID29684 하나와 진단 PID가 일치했다. 이후 최종 소스 반영 시 진단 PID8532로 바뀌었다. **기존 watcher의 자동 반영이며 Codex가 종료/재시작 명령을 실행한 것은 아니다.** Worker 1개는 관측 시점의 사실이며 보호의 근거를 영구적인 단일 Worker 가정에만 두지 않는다.

마지막 CIM 재확인에서도 PID28464의 Python child는 **8532 하나**였고 최종 진단 PID와 일치했다.

GET/일반 검사/ImageView/Heatmap route에는 admission dependency를 붙이지 않았다. 분석이 대기 중인 Fake 요청에서도 진단 GET이 처리되는 것을 확인했다.

근거: `backend/agent/api.py:193`, `backend/agent/runtime_safety.py:50`.

## D. Provider 6회 상한

`RequestState.provider_calls`를 0으로 시작한다. `_generate`에서 실제 SDK 메서드 호출 직전 상한을 검사하고 1 증가한다. 6회가 이미 dispatch되었으면 `PROVIDER_REQUEST_LIMIT`로 실패하며 SDK를 호출하지 않는다. 조사/종료 확인/최종 JSON 요청 모두 같은 카운터를 사용한다. 다른 분석 요청의 카운터는 공유하지 않는다.

각 dispatch에는 `correlation_id`, `stage`, `provider_request_number`, 상한을 기록한다. timeout/provider 예외에도 요청 번호를 추가했다. 기존 예외 유형·HTTP status·allowlisted provider code 및 원문 redaction을 유지했다. 이 번호는 SDK dispatch 시도 횟수이지 Google 서버가 수신했다고 증명하는 응답 로그가 아니다.

SDK Client 및 개별 GenerateContentConfig 모두 기존과 동일한 v1beta/attempts=1이다. 자동 Function Calling/continuation은 비활성화되어 있고 실패 후 재호출하지 않는다. 모델·temperature·token budget·timeout·tool schema는 바꾸지 않았다.

근거: `backend/agent/service.py:116`, `backend/agent/service.py:366`.

## E. 이번 변경 파일

| 파일 | 이번 변경 |
|---|---|
| backend/agent/runtime_safety.py | 새 승인 프로필·안전한 설정 투영·프로세스 간 admission |
| backend/agent/api.py | POST admission, Client 생성 전 검증, 로컬 GET 진단, 안전한 오류 코드 |
| backend/agent/service.py | 요청별 Provider 상한·dispatch 번호; 기존 SDK 설정값을 상수로 재사용 |
| tests/test_day7_step6b_runtime_safety.py | 신규 오프라인 25 cases |
| tests/test_agent_api.py | 새 409 계약/실행권 정책/승인 모델과 Fake SDK에 맞춘 기존 테스트 보완 |
| scripts/safe_regression_backend.py | 기존 선택 테스트를 유지하며 신규 모듈 추가 |
| 본 문서 | 결과·한계·다음 승인 절차 |

기존 다른 Agent/프론트엔드/PPT 변경 상태를 보존했다. 기존 Step5 수정분을 되돌리지 않았다. 기존 회귀 PowerShell 진입점은 변경하지 않았다.

## F. Fake 검증 결과

최종 신규 모듈: **25 PASS / 0 FAIL / 0 SKIP**, 1.98초, pytest bootstrap 경고 1건.

- 정상 Function Calling → Python Tool → Evidence/Fact/Pointer → JSON 검증 → 최종 OK 불변.
- 중첩 HTTP 요청 하나만 실행, 두 번째는 409·Provider 0회. Client 생성도 추가하지 않음.
- Provider 예외/TimeoutError, 실제 짧은 Agent deadline, 요청 취소 후 실행권 해제.
- 별도 runtime/thread 및 별도 Python 프로세스 경합 차단/해제 후 재획득.
- Lock 저장소 접근 실패 시 fail closed.
- 6회 허용, 7번째 사전 거부, 다음 요청은 독립 카운터 0에서 시작.
- 실제 `_run`의 4 tool rounds + 종료 응답 + 최종 JSON = 6회 완료.
- 테스트에서 round를 5로 늘려도 최종 7번째 요청은 거부. Production API는 이 설정 자체도 불일치로 거부.
- 모델/SDK/API/retry/제한/timeout 불일치 시 Provider 0회.
- 진단은 로컬만 허용, 비밀값 비노출·읽기 전용·OpenAPI 비노출.

중간 실행에서 기존 테스트 3건이 새 계약과 충돌했다. Mock 모델명이 승인 프로필과 달라 503이 된 lifecycle test, OpenAPI 응답 집합에 409가 추가된 test, 동시 요청 모두 200을 요구하던 test였다. 실제 모델/Provider 오류가 아니다. 테스트를 승인 모델명+Fake SDK, 409 검증, 중첩 요청 거부 후 순차 재실행의 Client 재사용/독립 trace 검증으로 변경했다. assertion 삭제나 skip으로 숨기지 않았다. 변경 후 관련 135 cases가 모두 통과했고 다회차 상한 2 cases를 추가 확인했다.

## G. 회귀 실행

실제 실행 명령:

```powershell
& 'C:/Users/USER/miniconda3/envs/vision-insight/python.exe' -B scripts/safe_regression_backend.py backend --output data/outputs/safe-regression/step6b-targeted-20261018-4 tests/test_day7_step6b_runtime_safety.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_safe_regression.ps1
& 'C:/Users/USER/miniconda3/envs/vision-insight/python.exe' -B scripts/safe_regression_backend.py backend --output data/outputs/safe-regression/step6b-final-backend-20261018
```

| 그룹 | PASS | FAIL | SKIP | 비고 |
|---|---:|---:|---:|---|
| Backend 선택 회귀 | 440 | 0 | 10 | 최종 12.12초, 경고 1 |
| Frontend Node | 26 | 0 | 0 | 기존 코드 변경 없음 |
| Chrome ImageView/Heatmap Mock | 12 | 0 | 0 | 실제 백엔드 분석 호출 없음 |
| Chrome Agent Mock | 8 | 0 | 0 | 실제 Google 요청 없음 |
| TypeScript / Build / Lint | 각 명령 성공 | 0 | 0 | lint 기존 경고 6건 유지 |

회귀 러너 최종 상태: **PASS WITH SKIP**, exit 0. 전체 pytest를 실행한 것이 아니다.

통합 증거: `data/outputs/safe-regression/20261018-163410-ecb2d6bd/`의 summary.json/backend.xml/safety.json/protection.json 및 두 browser 결과. 마지막 진단 boolean 추가 후 Backend 선택 회귀도 `step6b-final-backend-20261018/`에서 동일한 440/0/10으로 재확인했다. 브라우저는 설치된 Chrome/155.0.8059.82와 임시 프로필을 사용했다.

10 SKIP은 Windows symlink 권한 1, 실제 checkpoint 로드/추론 제외 6, 빈 격리 저장소의 조회 1, 실제 데이터셋 workflow 제외 2다. 기존 정책을 바꾸지 않았다. pytest 경고는 anyio assert-rewrite 1건, lint는 기존 AgentPanel 1/ImageView 5건이다.

## H. 운영 자산 보호

작업 시작 전 hash 기준: `data/outputs/safe-regression/step6b-baseline-20261018-162431/protected-before.json`. 작업 전후 보호 파일 **32개**의 파일 집합·SHA256이 동일하다. .env는 값 출력 없이 hash만 확인했다. 검사/로그 JSONL, Agent 보고서, Sidecar, 모델, 영상, 판정 코드 및 inferencer 보호를 포함한다.

실서버 읽기 전용 조회에서 `INSP-001650`은 `COMPLETED`, `final_result=OK`; 실제 Agent 보고서 `INSP-001650.json`은 여전히 없다. 이 검사에 대한 POST는 **0회**다.

오프라인 harness는 고유 실행 디렉터리/합성 JSONL/Mock Client를 사용했다. socket/실제 SDK/실제 checkpoint·dataset/private 접근 및 격리 경로 밖 쓰기를 차단했다. 최종 safety.json의 forbidden_io/network/real_prediction/real_load는 모두 0. 테스트 subprocess도 API/모델이 아닌 Lock 모듈만 실행한다.

**실제 Gemini API 0회, 실제 PatchCore 추론 0회, PostgreSQL 접속/변경 0건, 운영 보고서 생성/덮어쓰기 0건, Ground Truth 접근 0건, Git add/commit/push/reset/restore/clean 0건.**

마지막 기준선 재비교도 PASS였다. 작업 전후 git status를 비교해 다른 작업 변경사항을 보존했다. 이번 tracked 변경의 `git diff --check`는 0이었고 새 파일의 no-index check에도 공백 오류 진단이 없었다. no-index exit 1은 빈 파일과 내용이 다르기 때문이며 LF/CRLF 알림은 Git 공백 오류와 구분했다.

## I. 남은 위험

1. 과거 502의 근본 원인은 계속 **UNKNOWN**. 오프라인 성공은 Provider 가용성/실제 Function Calling 성공을 입증하지 않는다.
2. SDK attempts=1·6 dispatch 상한을 검증했지만 실제 Google 수신 횟수/과금은 이번에 관측하지 않았다. timeout/cancellation도 이미 전송된 원격 작업의 취소를 보장하지 않는다.
3. 기존 보고서 저장은 실패를 삼키며 기존 파일을 덮어쓸 수 있다. 이번에는 수정하지 않았다. 다음 Live 직전 보고서 부재 확인, 이후 실제 파일 유효성 확인이 필수다. HTTP 200만으로 완전 성공을 선언하지 않는다.
4. 저장 보고서 GET의 경로/파싱 오류 처리에 대한 기존 후속 위험은 남아 있다. 이번에 재추론·운영 데이터 쓰기를 추가하지 않았다. 저장 GET 성공과 신규 Live 성공은 구분해야 한다.
5. OS Lock은 로컬 동일 namespace 범위다. 여러 호스트/다른 체크아웃의 서버, 별도 진단 스크립트의 직접 SDK 호출은 보호하지 않는다. 공개 배포용 인증/분산 admission은 별도 작업이다.
6. 기존 개발 reloader는 파일 변경 시 프로세스를 교체할 수 있다. 다음 Live 중에는 소스 수정/배포 및 다른 분석 도구 실행을 멈춰야 한다.
7. PatchCore Normalize/Calibration 이슈는 이번 범위 밖이며 변경하지 않았다.

## J. Live 재시도 준비 상태

**READY WITH RISKS.** 두 기존 차단 원인은 로컬 직접 접속 및 같은 실행 namespace 범위에서 해소되었다. 설정 검증은 실제 처리 프로세스에서 수행되고, 동시 분석은 사전 조회가 아니라 원자적 실행권으로 거부된다.

단, **이전 Live 승인은 새 코드에 재사용하지 않는다.** 다음에는 사용자에게 아래 조건으로 새로운 승인을 받아야 한다.

- 대상 INSP-001650, 분석 POST 정확히 1회 이하, 내부 dispatch 최대 6회, 재시도 0회.
- 직전 로컬 진단 revision/설정/credential 구성 여부 확인, 보고서 부재 및 원본 JSONL hash 확인.
- 기존 개발 소스 변경·다른 분석/직접 SDK 스크립트 중지. 기존 프로세스를 Codex가 강제 종료하지 않음.
- 실제 Provider·Function Calling·서버 Tool/Evidence/Fact/Pointer 검증·LIVE provenance·실제 유효 보고서 저장·원본 OK/hash 보존을 모두 확인해야 PASS.
- 실패/timeout/클라이언트 연결 종료 후 재실행 금지. 409도 승인된 POST를 다시 자동 실행할 근거로 삼지 않음.

## K. 재시작 여부와 사용자 절차

**현재 추가 재시작은 필요하지 않다.** 기존 reloader가 반영한 실제 서버에서 최종 revision과 설정 일치를 GET으로 확인했다. Codex가 서버 재시작 명령을 실행하지 않았다.

나중에 진단이 404이거나 revision/설정 불일치이면 Live를 실행하지 않는다. 사용자가 해당 서버를 실행한 터미널에서 직접 Ctrl+C로 종료한 뒤 아래처럼 단일 Worker/no-reload로 시작할 수 있다. 이 절차는 이번에 실행하지 않았다.

```powershell
conda activate vision-insight
Set-Location C:\Users\USER\AI-NativeAgent\Project\InspectAgent
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

시작 후 별도 터미널에서 읽기 전용 진단만 확인한다.

```powershell
curl.exe --noproxy "*" --retry 0 --connect-timeout 3 --max-time 5 http://127.0.0.1:8000/agent/runtime-safety
```

이 단계에서 분석 POST는 실행하지 않는다. 새 실행 계획에 대한 사용자 명시적 승인 후에만 다음 Live 검증을 진행한다.
