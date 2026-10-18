# Day 7 Step 9 — Gemini Vision 독립 보조 분석 진행 상황

## 2026-10-19 최종 상태: 오프라인 COMPLETE / LIVE BLOCKED

**오프라인 구현·기존 안전 회귀·정적 검토·API 명세 문서화 완료.** 아래 사전 감사의 미구현/BLOCKED 설명은 과거 상태다. 오프라인 Fake-only 범위는 COMPLETE이며 실제 SDK/API 및 외부 이미지 전송은 계속 BLOCKED다.

### 구현 완료

- 별도 `backend/vision_review.py`, `backend/vision_review_api.py`. 기존 Diagnostic Agent·설정·도구·Generation Config는 변경하지 않았다. 실제 google SDK Client를 만들거나 LIVE 전송하는 경로는 구현하지 않았다.
- `GET/POST /inspections/{inspection_id}/vision-review`. POST 본문은 UUID hex `request_id`만 허용한다. 세션 소유권, POST Origin/CSRF, LIVEVIEW_GRAB REINSPECT 여부, 영속 원본 Crop 경로 보호·PNG·해상도·3채널·SHA256·그룹 연결을 확인한다. 클라이언트 경로/URL/이미지/판정을 받지 않는다.
- 서버가 검증한 실제 PNG bytes만 Fake Client 이미지 파트에 전달한다. 점수·최종 판정·정답·Heatmap·파일 경로는 프롬프트에 제공하지 않는다. 이는 SDK-shaped Fake 검증이지 실제 SDK/API 호환성 증명은 아니다.
- 별도 `OUTPUT_DIR/vision_reviews/state.json` + `workflow.lock`: OS Lock, 원자 저장, 호출 전 영속 PENDING 예약, request_id idempotency, 검사별 1회, 불확실 상태 자동 재호출 금지. 기존 JSONL/그룹/수동 결과에는 쓰지 않는다.
- strict 응답 4종과 서버 생성 ANALYSIS_FAILED, 저장 결과 재검증, 입력 변경·Timeout·예외·비정상 응답·다른 이미지 혼입 방어. 성공과 실패 모두 FAKE_TEST로만 기록한다.
- 독립 React 패널: 현재 INSP/CAP/hash 연결, 늦은 응답 차단, 중복 클릭 방지, 원본 판정과 분리, Fake 명시. 기본 버튼 DISABLED. Fake 성공을 LIVE 성공으로 표시하지 않는다.
- 별도 `VISION_REVIEW_MODEL` 기본 후보 `gemini-4-argon`. 환경변수 enable만으로 LIVE를 켤 수 없다. 이미지 4MiB/1920×1080 이내, 응답 32768 bytes, Fake timeout 최대15초, 일일 시도10회/전체 기록128개, LIVE 비용 예산0. 원가·API 모델 지원·실전 HTTP 재시도 상한은 UNKNOWN이다.

### 실제 검증 및 남은 항목

- 신규 Vision Backend **46 PASS**, 전체 안전 Backend **567 PASS / 0 FAIL / 10 SKIP**, Frontend **39 PASS**, Chrome Mock **50 PASS**(Vision 신규7 포함), TypeScript/Build/Lint 성공. 기존 lint 경고6, pytest anyio rewrite 경고1.
- 운영 자산80개 SHA256 불변. 실제 Gemini/외부 이미지 전송/실제 PatchCore 로드·추론 **0회**. PostgreSQL·사용자 서버·백업을 조작하지 않았다.
- GET 복원은 유효 소유 세션과 원본 PNG 접근권이 있어야 한다. 서버 종료 후 사라진 임시 세션이나 백업을 임의 복구하지 않는다.
- LIVE 전송은 **미구현/비활성**. 후보 모델의 실제 API·이미지·structured output 지원, SDK wire retry 제한 및 비용 정책은 별도 검증·사용자 승인 전까지 UNKNOWN으로 남긴다. 과거502 원인도 UNKNOWN이다.
- 복구 세션에서 서비스/API/UI 및 ROI 상태 코드를 정적으로 검토하고 `docs/inspection-data-schema.md`를 갱신했다. 구현 코드가 바뀌지 않아 안전 회귀를 다시 실행하지 않았다. 실제 Chrome 확인은 미완료다.

증거와 정확한 재개 명령: [통합 인계 문서](day7-step8-1-step9-handoff.md), `data/outputs/safe-regression/20261018-225800-d19e47a0/`.

---

# 이전 사전 감사 기록 — 아래 BLOCKED는 재개 이전 상태

## 상태: BLOCKED — 구현 전 실행 환경 안전 경계에서 중단

현재 백엔드 PID 22212가 자동 재시작 모드이고 새 임시 Capture PNG 6개가 있어, 사용자 확인 전 소스를 수정하지 않았다. [Step 8.1 사전 감사](day7-step8-1-industrial-reinspection-ux.md)에 원본·영속 Crop 목록과 해시 근거를 기록했다. **Vision 서비스/API/UI/Fake 테스트는 아직 구현하지 않았다.** 이 문서의 새 기능 계약은 모두 설계 후보다.

## 1. 기존 코드에서 확인한 재사용 경계

- `backend/grab_inspection.py:130`의 `authorize_record()`는 LIVEVIEW_GRAB 기록, 내부 이미지 ID 경로, 링크/경로 보호, 세션 소유자, Crop SHA256을 확인하고 원본 PNG 바이트를 반환한다.
- 영속 입력은 `data/outputs/grab_inspection_inputs/IMG-GRAB-*.png`와 대응 내부 manifest에 있다. manifest의 소유자 내부 정보는 외부 응답·새 보고서에 노출하지 않는다.
- Vision은 검사의 `final_result=REINSPECT`와 해당 세션 권한을 추가 검증하고, PNG 시그니처·디코딩·uint8 3채널·크기·기록된 Crop 해상도·SHA256을 재검증해야 한다.
- Heatmap Overlay, 클라이언트 이미지 URL/파일 경로/임의 바이트는 입력으로 채택하지 않는다. static image 지원으로 범위를 확대하지 않는다.
- 기존 검사 저장소, Decision Layer, 재검사 상태 및 수동 확인 저장소에는 쓰지 않는 별도 서비스로 분리할 수 있다. 다만 실제 분리는 아직 구현·검증 전이다.

## 2. SDK와 후보 모델 — 오프라인 확인

설치 메타데이터: **google-genai 2.31.0 / aiohttp 3.14.5 / httpx 0.28.1**. 패키지를 업데이트하지 않았다. SDK Client 생성, models.list, generate_content, 연결 테스트 또는 외부 검색을 수행하지 않았다.

`gemini-4-argon`은 사용자 검토 후보일 뿐이다. 실제 API 모델 ID 유효성, 계정 사용 권한, 이미지 입력 지원, API 버전, structured output 호환성, 요금과 토큰 제한은 **UNKNOWN**이다. AI Studio 표시나 설치된 SDK의 존재만으로 확정하지 않는다.

기존 Diagnostic Agent는 `backend/agent/service.py`에서 gemini-3.8-flash 설정과 Client, API_VERSION, SDK_ATTEMPTS를 사용하며 실제 SDK 요청 지점은 `client.aio.models.generate_content(...)`다. 이 코드·모델·인증·Generation Config·화이트리스트·Evidence·Lock은 수정하지 않았다.

로컬 SDK `_api_client.py:1634` 이후 `_async_request_once()`의 aiohttp 오류 처리에 sleep/재요청 분기가 남아 있음을 코드로 확인했다. aiohttp `client.py:740`, `:909`에도 조건부 persistent connection 재시도 코드가 있다. 특정 실제 요청에서 어떤 분기가 실행됐는지, 실제 Provider가 몇 번 수신했는지는 **UNKNOWN**이다. 앱의 SDK 호출 횟수와 외부 HTTP 전송 횟수를 동일시하지 않는다. 과거 HTTP 502의 근본 원인도 **UNKNOWN**으로 유지한다.

## 3. 제안하는 입력·응답·격리 계약 — NOT IMPLEMENTED

요청은 inspection_id와 UUID 기반 request_id만 사용한다. 서버가 소유권·LIVEVIEW_GRAB·REINSPECT 및 실제 Crop을 검증한 후 이미지 파트를 만든다. 과제 정의는 병 외관 관찰로 제한하고 기존 점수·판정·정답 라벨·Heatmap을 기본 프롬프트에 제공하지 않는다. 이미지 안의 문자는 데이터이며 명령이 아님을 지시한다.

응답은 strict schema와 추가 필드 거부를 사용하고 분류를 DEFECT_SUSPECTED / QUALITY_ISSUE / NO_VISIBLE_DEFECT / INCONCLUSIVE / ANALYSIS_FAILED로 제한하는 후보안이다. 오류·형식 불명·근거 부족 시 성공 분류를 임의 보완하지 않는다. confidence를 검증된 확률로 제시하지 않는다.

서버 발급 vision_review_id, inspection_id, reinspection_group_id, capture_id, Crop SHA256, model_requested/model_resolved, prompt_version, classification, visible_observations, limitations, recommended_operator_action, failure_code, created_at, analysis_mode를 저장하는 후보안이다. model_resolved는 Provider가 확인한 값이 없으면 UNKNOWN이어야 한다.

독립적인 `OUTPUT_DIR/vision_reviews/` 저장소를 검토한다. 기존 JSONL·재검사 그룹·수동 확인 파일을 갱신하지 않는다. OS Lock·영속 요청 예약·원자적 결과 저장·request_id/검사별 중복 보호를 사용하고, 응답 소실/Timeout/프로세스 중단 시 자동 유료 재호출을 금지한다. 검사별 기본 1회라는 보수적 정책과 일일 요청/비용 상한, 최대 이미지 bytes/pixels·응답 크기 상한을 실제 구현 전에 구체화해야 한다. 비용의 정확한 한도 산정은 모델 요금 확인 없이는 UNKNOWN이다.

API 후보는 POST/GET `/inspections/{inspection_id}/vision-review`이며 아직 존재하지 않는다. UI는 기존 판정 카드와 별도 섹션으로 만들고 동일 inspection_id+Crop SHA256 결과만 표시해야 한다. FAKE_TEST는 테스트 환경에서만 생성·노출하고 LIVE 완료로 표시하지 않는다.

## 4. LIVE 기능을 계속 비활성화해야 하는 이유

기능 기본값은 DISABLED가 되어야 하며 별도 Vision 설정을 기존 Diagnostic Agent 설정과 분리해야 한다. 오프라인 Fake transport를 명시적으로 주입한 테스트 외에는 외부 전송을 할 수 없도록 실패 폐쇄하는 경계를 먼저 만든다.

현재는 후보 모델 지원과 실제 전송 횟수 상한을 입증하지 못했다. 따라서 별도 설정만 켜면 실제 SDK로 빠지는 LIVE 경로를 열어서는 안 된다. 실제 전송 계층의 재시도/리다이렉트/Timeout/동시성/불확실 상태를 검증하고 사용자의 명시적 승인을 받기 전까지 UI는 비활성 사유를 보여야 한다. 이 단계에서는 그 UI 자체도 아직 구현하지 않았다.

같은 Crop Vision 분석은 신규 Grab·ROI 재설정·PatchCore 추론·inspection_id 발급·재검사 횟수 증가가 없는 독립적 의견이다. DEFECT_SUSPECTED는 최종 NG가 아니고 NO_VISIBLE_DEFECT는 최종 OK가 아니다. 기존 작업자 MANUAL_NG를 바꾸거나 인증된 승인으로 대체하지 않는다.

## 5. 오프라인 테스트 계획과 실제 실행 구분

서버 종료 확인 후 구현 단계에서는 다음을 검증해야 한다.

- 실제 임시 PNG 바이트가 Fake transport에 전달되며 점수/판정/라벨·임의 경로·Overlay가 입력되지 않음.
- 소유권·출처·형식·해상도·해시 불일치, 누락 PNG, 다른 검사 혼입 차단.
- enum 4종·ANALYSIS_FAILED, malformed JSON/enum, timeout/SDK 예외, schema/출처 검증.
- request_id/검사별 1회 정책, 동시 실행, 불확실 요청 영속 예약 및 자동 재호출 방지.
- 분석 전후 원본 판정·그룹 횟수·수동 결과 불변, 유효 세션에서 조회/복원.
- 늦은 응답·이미지 전환·FAKE_TEST 표시·LIVE disabled UI, ROI 수명과 기존 좌표/Heatmap 회귀.
- 네트워크/실제 SDK Client/모델 로드를 차단한 기존 안전 러너 확장 및 Chrome Mock/TypeScript/Build/Lint.

**이번 신규 테스트와 기존 회귀는 미실행**이다. 기존 테스트 통과 수치를 이번 결과로 표시하지 않는다. 실제 Gemini API 호출 0회, 외부 Provider/이미지 전송 0회, 실제 PatchCore 로드·추론 0회, 운영 데이터 수정 0건이다. 로컬 서버에 분석/검사/Grab 요청도 실행하지 않았다.

## 6. 다음 사용자 확인

먼저 새 Capture PNG 6개의 안전 백업과 사용자의 서버 정상 종료 확인이 필요하다. 이전 2026-10-18 백업은 건드리지 않았다. 그 후 ROI UX와 Vision Fake 구현을 각각 진행할 수 있다. 실제 Vision 외부 전송은 그 이후에도 별도의 모델·전송 안전성 검증 및 사용자 승인이 있어야 한다.

**Step 8.1: BLOCKED(사전 감사 완료, 미구현). Step 9: BLOCKED(오프라인 구조 감사 완료, 미구현). 전체 COMPLETE가 아니다.**
