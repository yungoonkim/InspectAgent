# Gemini Vision Judge A — 백업, 세션 영향 및 오프라인 구현

## 범위와 현재 상태

- 2026-10-19 작업. Judge A 코드 및 선택 오프라인 회귀 COMPLETE. 실제 서버 적용, Chrome 동작 및 Google 응답은 NOT TESTED. 전체 상태는 임시 Capture 원본 소실 관측으로 PARTIAL이며 추가 구현은 중단했다.
- Google LIVE 기본 DISABLED 유지. 실제 Google 요청, 이미지 외부 전송, 실제 PatchCore 로드/추론, 서버 종료/시작/재시작 모두 0회.
- 실행 중 PID 15016은 기존 코드이며 `--reload` 없음. 디스크의 새 백엔드 코드가 현재 서버에 적용됐다고 주장하지 않는다.
- 기존 Diagnostic Agent, 모델, 34.1442 threshold, 밝기 하한 125.0, 판정 우선순위, RIG/수동 확인 정책은 수정하지 않았다.

## Capture BACKUP_PASS

새 폴더: `C:\Users\USER\VisionInsight_GrabBackup_Judge_20261019`

Manifest: `C:\Users\USER\VisionInsight_GrabBackup_Judge_20261019\backup_manifest.json`

원본: 프로젝트 `data/outputs/captures/`. 검증 시각: `2026-10-19T06:36:33Z`.
목록 4개를 고정하고 복사 전 원본, 복사 후 원본, 새 백업 SHA256을 전수 비교했다.
마지막 원본 재검증 및 목록 동일성도 통과했다. 기존 백업 폴더는 쓰지 않았고 서버 API 호출은 백업 조건으로 사용하지 않았다.

| 파일명 | bytes | SHA256 (세 값 동일) |
|---|---:|---|
| CAP-28eab9c089294112bf6f612ff68f77ef.png | 785587 | 53b50a1b44219428619c9771e962dfb0dcc8a6f303d294aa7d57eeb2429b017d |
| CAP-60da92435c054fbf8eaa77bf850254f2.png | 789184 | 7f26e6a11ff3b2f45be8950c757d56700a6003577d1e3513cb00ba96077cc910 |
| CAP-c569401d1a494eb88d3b0791222d4f18.png | 760339 | 1cb6b8446dadb78405c2b936e698353d898fa7038e8cf04d1cae041026532f2e |
| CAP-cbe53c32411c4c6882306098d809c569.png | 789184 | 7f26e6a11ff3b2f45be8950c757d56700a6003577d1e3513cb00ba96077cc910 |

백업은 PNG 바이트 복구 수단이지 서버의 Capture ID/소유 세션 재등록 기능이 아니다. 임의 재등록은 하지 않았다.

## 세션과 재시작 영향: CONFIRMED (정적 코드 + 합성 테스트)

- `backend/capture_store.py`의 `_sessions`(CSRF/만료), `_captures`(owner/metadata/만료/hash)는 메모리만 사용한다.
- cookie는 서버 메모리 세션과 함께 검증한다. 기본 Capture TTL 1800초, 세션 3600초이며 실효 환경값은 다를 수 있다.
- `authorize()`는 먼저 `cleanup()`을 호출한다. 읽기 GET도 만료 Capture PNG 정리를 유발할 수 있다.
- `close()`는 관리 Capture PNG를 삭제하고 세션을 비운다. 새 인스턴스의 최초 Capture 디렉터리 초기화도 관리 경로의 이전 파일을 정리한다.
- 영속 Crop, Map, JSONL, RIG, AI 보고서 파일을 CaptureStore 종료 코드가 지우지는 않는다.
- 그러나 `grab_inspection.authorize_record()`는 현재 유효 세션의 owner와 영속 Crop manifest의 owner를 비교하고 PNG hash를 검사한다.
- `vision_review_api.prepare()`는 현재 세션과 POST의 Origin/CSRF를 요구한 후 영속 Crop을 검증한다. 임시 Capture PNG 자체는 필요하지 않다.
- `require_grab_owner()`가 붙은 검사/이미지/Map 조회도 유효한 원 소유 세션이 필요하다. **파일이 남는 것과 Chrome API 접근 가능성은 다르다.**
- 서버 재시작 후 같은 Chrome cookie라도 새 `_sessions`에는 없으므로 유효하지 않다. 신규 bootstrap은 새로운 owner를 만들 뿐 원래 Crop/RIG 소유권을 복원하지 않는다.
- 따라서 INSP-001669의 영속 Crop이 남아도 현행 계약에서 재시작 후 같은 Chrome으로 정상 조회/Judge 요청을 계속할 수 있다고 보장할 수 없다. 일반 파일의 읽기 전용 사후 감사와는 구분한다.
- RIG는 별도 영속 파일에 owner와 3회 시도/수동 이력을 보존한다. 새 owner에는 404를 반환하며 원본 소유권이나 카운터는 변경하지 않는다.

기존 정당한 세션과 연결하는 영속 복구 기능은 **미구현**이다. 향후 별도 승인 아래 세션의 만료·폐기·CSRF와 안전한 서버 보관, 인증된 사용자 또는 만료되는 복구 증명으로 원래 owner를 검증하는 설계가 필요하다.
검사 ID, product_id, 자기신고 작업자 이름, PNG 백업만으로 권한을 회복시키면 안 된다.
현재 세션이 이미 만료됐는지는 API를 호출해 재현하지 않았으므로 UNKNOWN이다. 살아 있는 세션의 무중단 이관도 이번 작업에 포함하지 않는다.

## Judge 저장/표시 계약

- `VisionJudgeDraft`는 OK/NG/REINSPECT와 관찰·위치·근거·한계·작업자 권고를 엄격하게 검증한다. 미정의 enum/필드, 빈 근거, NG의 위치 누락을 거부한다.
- OK는 충분한 가시성과 뚜렷한 결함 근거가 없다는 독립 의견일 뿐 제품 정상 보증이 아니다.
- NG는 병 입구/테두리/이물질의 구체적인 시각적 의심 근거와 상대 위치가 필요하며 운영 NG 확정이 아니다.
- REINSPECT는 영상 품질·가시성·근거 부족에 대한 독립 판정이다. API 실패는 별도의 실패 상태이며 판정은 null이다.
- `StoredVisionJudge`: `prompt_version=bottle-vision-judge-a-v1`, `analysis_status`, nullable `judge_verdict`, `image_id`, 기존 검사/Capture/그룹/hash/해상도/모델/시각/출처를 저장한다.
- 모델에는 검증한 실제 PNG 바이트와 독립 Judge 지침만 제공한다. 기존 점수, 1차 판정값, 검사 ID, 정답 라벨을 주입하지 않는다. 지침의 REINSPECT enum은 기존 판정값 유출이 아니다.
- 과거 `bottle-independent-vision-v1`의 분류 5종은 그대로 읽는다. 누락된 옛 image_id를 새로 써 넣지 않으며 관찰 의견을 Judge 판정으로 자동 치환하지 않는다.
- GET/POST 경로, 별도 `OUTPUT_DIR/vision_reviews/state.json`, OS Lock, request_id 멱등성, PENDING 예약, 검사당 1회/일일 10회 제한은 유지한다. 옛 결과가 있어도 재분석 허용으로 우회하지 않는다.
- UI는 1차 서버 판정 / 독립 Judge 판정 / 작업자 개발용 수동 확인을 따로 표시한다. 작업자 상태는 기존 Grab 패널이 조회한 서버 그룹에서만 전달하고 그룹/검사 연결이 다르면 미조회로 표시한다.
- FAKE_TEST는 실제 Google 판정이 아니라고 표시한다. 과거 의견은 'Judge 미실행 · 과거 관찰 의견'으로 표시한다. 늦은 다른 검사 응답과 image_id/hash/Capture/그룹 불일치를 차단한다.

## 혼합 버전 적용 순서 및 승인 게이트

1. 새 프론트엔드는 `capabilities.result_contract=VISION_JUDGE_A_V1`가 없는 현재 구버전 서버에 Judge POST를 보내지 않는다. 과거 의견 조회는 호환한다.
2. UI 파일 변경의 HMR은 기존 조회를 다시 실행할 수 있으며 이는 세션 TTL 정리를 유발할 수 있음을 수정 전에 알렸다. 추가 서버 조회 API는 만들지 않았다.
3. 백엔드 새 코드 적용은 **사용자의 별도 재시작 승인 이후**에만 가능하다. 본 작업에서는 재시작하지 않는다.
4. 재시작 승인 전에 최신 Capture 백업 범위와 INSP-001669의 소유 세션 접근 복구 방안을 별도로 결정해야 한다. 백업만으로 세션 문제는 해결되지 않는다.
5. 새 서버 적용 후에도 LIVE는 기본 DISABLED이다. 기존 승인 플래그/검사 ID/hash/키 조건을 변경하지 않았다. SDK/HTTP 경계 1회 guard와 타임아웃도 기존 구현을 유지한다.
6. 실제 Google 호출·해당 PNG 외부 전송은 별도 검사 ID/hash/모델/비용/요청 상한을 명시한 사용자 승인 대상이다. 계정 모델 접근, 실제 응답 품질·정확도는 미검증이다.

## 변경 파일 (기존 dirty 변경을 보존한 추가 수정)

- `backend/vision_review.py`: Judge 지침/스키마·버전별 저장 검증·image_id 연결. 기존 API/Diagnostic/Decision/세션/RIG 코드는 수정하지 않음.
- `frontend/src/types/visionReview.ts`, `frontend/src/utils/visionReviewState.ts`, `frontend/src/components/VisionReviewPanel.tsx`: 버전 호환, 판정/실패 구분, 구서버 차단, 출처·이미지 연결.
- `frontend/src/App.tsx`, `frontend/src/components/GrabInspectionPanel.tsx`: 기존 서버 그룹 상태를 읽기 표시용 callback으로 전달. 검사·수동 확인 정책 변경 없음.
- `tests/test_vision_judge.py` 신규, 기존 `tests/test_vision_review.py`, `tests/test_step11_vision_transport.py`: 합성 Judge/옛 결과 호환·네트워크 격리 검증.
- `frontend/scripts/test_vision_judge_state.mjs` 신규, `frontend/scripts/test_roi_vision_state.mjs`, `frontend/scripts/vision_browser_cases.mjs`: 상태 검증 및 브라우저 fixture 계약 갱신. 브라우저 실행은 안 함.
- `docs/inspection-data-schema.md`, 본 문서.

## 실제 실행한 선택 테스트

증거 루트: `data/outputs/safe-regression/judge-a-20261019-339eee14/`

- Backend **215 PASS / 0 FAIL / 0 SKIP**: `backend/backend.xml`, `backend/safety.json`.
  - 선택 파일: `tests/test_vision_review.py`, `tests/test_vision_judge.py`, `tests/test_step11_vision_transport.py`, `tests/test_step11_core_connection.py`, `tests/test_reinspection_workflow.py`, `tests/test_agent_service.py`.
  - 38.32초. 원본 final_result/RIG/수동 이력 불변, 권한·PNG·멱등성·동시성·실패·실제 설치 SDK의 MockTransport 경계를 포함한다.
  - INSP-001669 문자열을 사용한 3개 테스트도 **임시 합성 레코드와 PNG**이다. 운영 검사/결과 저장소를 사용하거나 실제 성능을 측정한 것이 아니다.
- 세션 재시작 영향 합성 테스트 **1 PASS / 0 FAIL / 0 SKIP**: `session-final/backend.xml`, `session-final/safety.json`. 기존 cookie 거부, 신규 owner의 Crop/RIG 거부, 영속 바이트 보존 확인.
- Backend 합계 **216개의 서로 다른 테스트 PASS**. 각 실행 pytest의 기존 anyio import 순서 경고 1건. 테스트 실패는 없었다.
- Frontend Node 상태 테스트 **39 PASS / 0 FAIL / 0 SKIP**: `frontend.log`. Judge 신규 8건, 기존 ROI/Vision/재검사/복구/Agent 상태 31건.
- `npm.cmd run build` 성공 (TypeScript 포함), `npm.cmd run lint` 성공, 기존 AgentPanel/ImageView 경고 6건: `build.log`, `lint.log`.
- Chrome/CDP/전체 안전 러너/실제 Google/실제 모델/실제 서버 Judge 요청은 **실행하지 않음**. 통과로 주장하지 않는다.

재개 명령(새 격리 출력 폴더를 사용할 것):

```powershell
& C:\Users\USER\miniconda3\envs\vision-insight\python.exe scripts/safe_regression_backend.py backend --output data/outputs/safe-regression/judge-a-NEW/backend tests/test_vision_review.py tests/test_vision_judge.py tests/test_step11_vision_transport.py tests/test_step11_core_connection.py tests/test_reinspection_workflow.py tests/test_agent_service.py
node --test frontend/scripts/test_vision_judge_state.mjs frontend/scripts/test_roi_vision_state.mjs frontend/scripts/test_reinspection_state.mjs frontend/scripts/test_reinspection_recovery.mjs frontend/scripts/test_agent_analysis_state.mjs
```

## 보호 데이터 최종 확인: PARTIAL

운영 파일 85개의 SHA256 기준선은 `assets-before.json`에 별도로 기록했다. 일부 Map JSON은 sandbox 읽기 권한 제한으로 USER 권한 읽기만 승인받아 해싱했으며 ACL은 수정하지 않았다.
최종 `2026-10-19T06:47:02Z` 비교 결과는 `assets-after.json`, `protection.json`에 기록했다.

- **기준선 85개 → 현재 81개, `unchanged=false`. 임시 Capture PNG 4개 모두 원본 폴더에서 사라졌다. 운영 자산 전체 불변 PASS라고 보고할 수 없다.**
- 나머지 81개는 파일 크기·SHA256 모두 일치하며 새 운영 파일이나 변경된 파일은 없다. 검사 JSONL, 로그, 영속 Crop/Map, RIG/수동 이력 및 기존 보고서가 여기에 포함된다.
- INSP-001669는 실제 저장 기록 1건, `final_result=REINSPECT` 그대로이며 image_id/Capture 링크도 유지된다. 신규 Diagnostic 보고서와 운영 Vision state 파일은 존재하지 않는다.
- 원본 4개는 소실 전에 BACKUP_PASS를 검증했으며, 소실 확인 후에도 백업 4개 SHA256·크기를 다시 검증해 PASS를 확인했다. 현재 Capture 원본 PNG 수는 0이다.
- PID 15016과 시작 시각(2026-10-19 13:34:45 KST)은 계속 같았다. Codex는 서버 종료/시작/재시작, 원본 삭제/이동/복원 및 실서버 API 요청 명령을 실행하지 않았다.
- 가능한 경로는 서버의 `cleanup()`과 UI HMR 후 기존 조회의 authorize/bootstrap이다. 삭제 이벤트 로그나 호출 trace가 없어 **직접 원인은 UNKNOWN, TTL 정리는 코드상 가능한 설명**으로만 기록한다. 임의로 원인을 확정하지 않는다.
- 소실 관측 즉시 추가 코드 작업을 중단하고 사용자에게 알렸다. 백업을 운영 Capture에 재등록하거나 권한 owner를 바꾸지 않았다. 픽셀 백업이 있어도 메모리 세션은 복원되지 않는다.
- 해시 비교 보조 명령은 처음 sandbox Map JSON 접근 제한으로 USER 읽기 승인을 받았고, 최종 비교의 PowerShell JSON 배열 처리 오류도 보정해 재실행했다. 오류를 무시해 보호 검사 PASS로 처리하지 않았다. 제품 코드/단위 테스트의 실패는 아니며 보호 결과는 위 PARTIAL을 유지한다.

테스트 자체의 `safety.json`은 외부 네트워크/실제 모델 로드·추론/금지 IO/실제 Gemini 호출 모두 0이다. PNG 외부 백업과 코드/격리 테스트 산출물 외에 운영 저장소에 결과를 쓰지 않았다. 기존 검사·RIG 소유권 복구/실제 Judge 실행은 별도 승인까지 보류한다.
