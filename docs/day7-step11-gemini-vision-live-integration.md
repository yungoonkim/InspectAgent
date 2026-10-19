# Step 11 — Gemini Vision LIVE 어댑터 구현 및 오프라인 검증

## 상태와 범위

- **구현·오프라인 검증 COMPLETE / 실제 Google E2E NOT TESTED / LIVE 기본 DISABLED**.
- 서버 종료 확인 후 구현했다. 포트 8000 listener와 Uvicorn/reload/backend.main 프로세스가 없었다. 서버를 시작·종료·재시작하지 않았다.
- 기존 Function Calling Diagnostic Agent의 모델, generation 설정, 도구, Evidence 검증, OS Lock은 변경하지 않았다. Vision은 별도 전송 계층이다.
- 실제 Provider 요청, 이미지 외부 전송, PatchCore 로드·추론은 각각 **0회**. 공개 Google 문서 조회는 수행했으며 이는 인증 요청/이미지 전송이 아니다.

## 모델·SDK 근거

2026-10-19 공개 [모델 문서](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon)를 조회했다.
`gemini-4-argon`의 이미지 입력과 structured output 지원이 문서에 명시되어 있다. 계정별 이용 가능성·쿼터·실제 응답 품질은 **NOT TESTED**다. models.list 등의 인증 API는 호출하지 않았다.

설치 환경은 google-genai **2.31.0**, HTTPX **0.28.1**이다. 업그레이드하지 않았다.
해당 SDK `_api_client.py`의 retry 및 custom HTTPX client 선택 경로, `_common.py`의 URL-safe Base64 직렬화와 `models.py`의 inlineData 변환을 확인했다.
Mock wire payload의 PNG를 URL-safe Base64로 복원하여 저장 원본과 byte equality를 검사했다. 이 SDK는 inlineData 내부 `mime_type`을 사용한다. 실제 Google의 수신 결과를 검증한 것은 아니다.

[가격표](https://ai.google.dev/gemini-api/docs/pricing)상 Argon은 무료 tier가 없고, 2026-11-30까지 입력 $2 / 출력(생각 토큰 포함) $10 per 1M tokens다. 12월 이후 가격은 달라진다. 이미지 한 장의 정확한 비용은 토큰 사용량 없이는 확정하지 않는다.
일일 시도 제한은 금액 기반 과금 상한이 아니다. [계정별 rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)는 별도 확인이 필요하다.

## 입력 및 API 계약

기존 `GET/POST /inspections/{inspection_id}/vision-review`를 재사용한다. POST 본문은 `request_id` UUID hex뿐이다.

1. Origin/CSRF 및 Capture 세션 소유권 확인.
2. 저장 검사 `LIVEVIEW_GRAB` + `final_result=REINSPECT` 확인.
3. 서버의 `GrabInspectionRuntime.authorize_record()`로 영속 Crop PNG를 읽는다. 임의 URL/경로/클라이언트 이미지 입력은 받지 않는다.
4. PNG header, 바이트·픽셀 크기, uint8 3채널 decode, ROI 해상도, manifest/검사 SHA256, 그룹 연결을 검증한다.
5. 전송 직전과 응답 후에 동일한 이미지 연결·권한을 다시 검증한다.
6. 텍스트 과제 정의 + **실제 PNG 바이트**만 전달한다. score, final_result, 검사 정답, Heatmap은 전달하지 않는다.
7. strict `VisionDraft` 검증 후 별도 Vision 저장소에만 기록한다.

핵심 위치: `backend/vision_review.py:108`(정책·이미지 검증 영역), `backend/vision_review.py:240`(생성), `backend/vision_review_api.py:17`(API), `backend/vision_transport.py:48`(SDK 어댑터).

## 승인·전송 상한

다음은 **향후 명시적 승인 후에만** 설정할 항목이다. 이번에는 설정하지 않았다. `.env`도 수정하지 않았다.

| 별도 설정 | 의미 |
|---|---|
| `VISION_REVIEW_LIVE_ENABLED` | 기본 false. 정확히 true일 때만 다음 조건 검토 |
| `VISION_REVIEW_MODEL` | Diagnostic 설정과 독립. 검증한 ID는 gemini-4-argon만 허용 |
| `VISION_REVIEW_APPROVED_INSPECTION_ID` | 사용자가 외부 전송을 승인한 단일 검사 ID |
| `VISION_REVIEW_APPROVED_IMAGE_SHA256` | 그 검사의 승인 PNG SHA256 |
| 기존 `GEMINI_API_KEY` 설정 | 값을 출력·하드코딩하지 않고 기존 런타임에서 전달 |

위 조건이 모두 충족돼도 다른 검사/해시는 fail-closed다. UI에 현재 Crop 외부 전송 동의 체크가 추가된다. 기본 상태에서 버튼은 비활성이다.

- 목적지는 고정 HTTPS `generativelanguage.googleapis.com/v1beta/models/gemini-4-argon:generateContent` POST만 허용한다. query 및 redirect는 거부한다.
- SDK retry attempts=1(최초 1회, 추가 재시도 0), HTTPX transport retries=0, proxy 환경 무시, AFC 비활성.
- `SingleAttemptTransport`가 inner HTTP transport 위임 직전 시도를 증가시키고 **두 번째 HTTP 요청을 위임 전에 거부**한다.
- client 재사용 요청도 one-shot guard로 거부한다. 동시 생성은 기존 Vision OS 파일 Lock, 검사당 1회, PENDING 선기록으로 제한한다.
- SDK timeout 및 외부 coroutine 제한은 15초, 최대 출력 4096 tokens다. 같은 timeout으로 Argon이 실제 완료 가능한지는 **NOT TESTED**다.
- TCP 패킷 재전송 횟수를 계측한 것이 아니다. 검증 대상은 SDK→HTTPX의 애플리케이션 HTTP 요청 위임 횟수다.
- 동일 request_id의 완료 결과 재조회는 재전송하지 않는다. 다른 request_id의 추가 시도는 거부한다. 중단 후 PENDING이면 자동 재호출하지 않는다.
- 일일 최대 10회, 총 저장 이력 128개, 입력 최대 4MiB/1920×1080, 응답 텍스트 32KiB는 기존 보수적 제한을 유지한다. 이번 승인 scope에서는 1개 검사만 가능하다.

## 결과와 저장

`OUTPUT_DIR/vision_reviews/state.json`에 owner, request_id, PENDING/FINISHED와 `vision_review_id`, inspection/capture/group ID, PNG SHA256, 크기, 모델, prompt_version, 시각을 별도로 저장한다.
`analysis_mode`는 LIVE 또는 FAKE_TEST이며 Fake HTTP transport는 반드시 FAKE_TEST다.
추가 안전 진단은 `http_attempts`(0..1 또는 미계측 null), `provider_http_status`, 예외 클래스와 안전한 failure_code다. 키·PNG·prompt·원문 SDK 예외는 저장하지 않는다.

의견은 DEFECT_SUSPECTED / QUALITY_ISSUE / NO_VISIBLE_DEFECT / INCONCLUSIVE다. 실패는 ANALYSIS_FAILED로 저장하며 자동 재호출하지 않는다. 최종 저장이 실패하면 200 완료로 감추지 않고 기존 저장 오류 경로로 거부한다. 이미 선기록한 PENDING은 불확실 상태로 남아 중복 유료 요청을 막는다.
저장된 LIVE 의견은 현재 LIVE가 다시 비활성이어도 같은 유효 owner/이미지 연결이면 GET으로 읽을 수 있다.
원본 PatchCore 판정·그룹 횟수·수동 결과는 불변이다.

## 실제 수행한 오프라인 검증

| 범위 | 결과 | 근거 |
|---|---|---|
| 핵심 API/Fake/설치 SDK MockTransport 집중 회귀 | **289 PASS / 0 FAIL / 0 SKIP** | `data/outputs/safe-regression/step11-final-verified/backend.xml` |
| 최종 보고서 저장 정리 예외 처리 변경 후 재확인(위 5건과 중복) | **5 PASS** | `step11-persistence-final/backend.xml` |
| 실제 SDK 타입/Fake 출처 강화 후 재확인(위 범위와 중복) | **106 PASS** | `step11-provenance-final/backend.xml` |
| 저장 보고서/Provider 오류 관측 추가 회귀 | **11 PASS / 0 FAIL / 0 SKIP** | `step11-report-get-final/backend.xml` |
| Frontend 단위 | **41 PASS / 0 FAIL / 0 SKIP** | `data/outputs/step11-core-offline/frontend-final.log` |
| TypeScript / Build / Lint | 성공, lint 경고 6개 | 같은 폴더 `typescript.log`, `build-final.log`, `lint-final.log` |

중복을 제외한 집중 Backend 범위는 **300 PASS**이며 전체 pytest 결과가 아니다. 각 Python 실행에는 기존 anyio import 순서에 따른 PytestAssertRewriteWarning 1건이 있었다.
SDK Mock 시나리오는 성공·400/401/403/429/500/503·redirect·timeout·connection failure, 두 번째 요청 사전 차단, 승인 scope 누락/다른 모델/다른 검사/다른 해시, 실제 저장 합성 PNG→SDK 바이트 일치 및 idempotency를 포함한다.
재검사/작업자 결과 불변, 원본 파일 무변경, 세션·CSRF·해시 방어를 기존 Fake 회귀로 확인했다.
각 `safety.json`의 운영 접근·네트워크·실모델·실API 카운터는 모두 0이다.

초기 실패도 보존했다. `step11-core-01`의 Fake product alias 및 덮어쓰기 기대값 오류, `step11-transport-01`의 Windows asyncio socketpair 차단, 후속 테스트의 SDK MIME 필드/Base64 가정 오류는 수정했다. 실제 SDK가 사용하는 URL-safe Base64로 정확한 PNG 일치 검증을 유지했다. 이전 실패를 PASS로 간주하지 않는다.

## 남은 승인 게이트

1. 사용자가 새 Capture 검사를 명시적으로 수행하고 대상 inspection_id·실제 PNG 해시·크기를 확인한다. 서버 재시작 전 옛 세션의 owner를 우회해 과거 Crop을 보내지 않는다.
2. 유료 계정 접근, 데이터 외부 전송, 15초 제한 및 최대 1 HTTP 요청을 포함한 계획을 승인받는다.
3. 승인 scope 설정과 UI 동의 후 **해당 Crop 한 장만** 시험한다. 이번 작업에서는 실행하지 않는다.
4. HTTP 200만으로 성공하지 않는다. 구조화 결과의 inspection/hash 일치, 파일 저장 및 원본 판정 불변을 확인한다.
5. 실패/timeout에는 재시도하지 않는다. 과거 Diagnostic HTTP 502 원인은 여전히 UNKNOWN이며, Vision의 Mock 성공을 그 문제 해결로 표현하지 않는다.
