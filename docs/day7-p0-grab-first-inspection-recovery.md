# P0 — 최초 Grab 검사 복원 차단 수정

## 확인한 원인

사용자가 Chrome에서 확인한 요청은 `GET /api/reinspection-groups/RIG-f36e0c4408f54cc1901629be1fa555d0`, HTTP 404, `REINSPECTION_GROUP_NOT_FOUND`다.
기존 UI는 localStorage의 이전 RIG/미완료 Capture 조회 실패를 모두 `blocked=true`로 유지하면서 그룹이 null이면 무조건 “최초 검사 준비”라고 표시했다. 재조회도 같은 이전 ID만 조회했다.

해당 RIG는 기본 영속 저장소 `data/outputs/reinspection_history/state.json`에 **존재**한다. 시도 3회, 남은 0회, `MANUAL_REVIEW_REQUIRED`, 현재 검사 INSP-001666, 수동 확인 0건이다. 삭제된 그룹이라고 단정하지 않는다.
`backend/reinspection_store.py:131`의 `_group()`은 미존재와 owner 불일치 모두 같은 404로 숨긴다. `CaptureStore.authorize()`의 세션 확인 실패는 읽기 요청에서 404 `CAPTURE_NOT_FOUND`이므로 이번 그룹 오류와 구분된다.
세션 변경에 따른 owner 범위 불일치가 유력하지만, 실행 서버의 실효 저장 경로·메모리 owner 비교를 직접 확보한 것은 아니므로 실제 내부 분기 확정은 제한된다. 소유권 보호를 우회하지 않았다.

## 최소 수정

백엔드는 변경하지 않았다. 현재 서버 PID 15016을 종료·재시작하지 않았다.

- `frontend/src/components/GrabInspectionPanel.tsx`: HTTP 오류 분류, 올바른 준비/차단 문구, 재조회 성공 반영, 명시적 새 제품 전환 및 늦은 Capture 응답 방어.
- `frontend/src/utils/reinspectionRecovery.ts`: 조회 전용 복구 절차, Capture ID/video/revision/frame/원본 해상도·ROI 검증, 정확한 그룹 404와 다른 오류 구분. localStorage는 마지막 선택/불확실 요청의 **UI 힌트**일 뿐이다.
- `frontend/src/utils/reinspectionState.ts`: 실제 버튼과 실행 handler가 공유하는 차단 조건 및 상태 문구. 기존 `canUseCapture()`의 재검사 정책은 유지했다.
- `frontend/scripts/test_reinspection_recovery.mjs`: Fake GET과 실제 UI gate 함수의 회귀.

명시적 `[새 제품 검사 시작]` 확인 후에만 `GET /captures/{현재Capture}`와 `GET /reinspection-groups/by-capture/{현재Capture}`로 현재 세션의 접근·출처·기존 연결을 확인한다. 연결 그룹이 있으면 그 서버 그룹을 복원하여 같은 Capture 재검사를 막는다.
유효한 Capture 확인 뒤 **정확한** 404 `REINSPECTION_GROUP_NOT_FOUND`일 때만 새로운 제품의 최초 검사 화면으로 전환한다. 이 404 자체가 전역적인 미사용 증명은 아니며, 실제 검사 POST 때 서버가 Capture claim/중복/동시성을 다시 강제한다.
새 그룹/검사 POST를 자동 실행하지 않는다. 사용자가 이후 검사 버튼을 명시적으로 눌러야 한다. 같은 제품의 재검사는 이전 그룹 복구 및 기존 한도를 유지해야 하며 새 제품으로 위장하면 안 된다.
401/403, Capture/session 404, 409, 500/503, 일반 404/네트워크 오류는 차단을 유지한다. 검증 성공 전에 오래된 힌트를 지우지 않는다. 성공 시에도 `visioninsight.manual-reinspection-group`, `visioninsight.manual-reinspection-pending-capture` 두 키만 다루며 localStorage 전체나 서버 기록은 삭제하지 않는다.

## 검증

- `node --test --test-reporter=tap frontend/scripts/test_reinspection_recovery.mjs frontend/scripts/test_reinspection_state.mjs frontend/scripts/test_grab_inspection.mjs`: **22 PASS / 0 FAIL / 0 SKIP**.
- 격리 harness로 기존 재검사 한도·연속성·Capture 중복·수동 판정 불변·접근 제어·서버 상태 복원·응답 유실 복구 7개 함수(파라미터 포함) 실행: **14 PASS / 0 FAIL / 0 SKIP**.
- `npm run build`(TypeScript 포함), `npm run lint`: 성공, 기존 lint 경고 6건 유지.
- Node 근거: `data/outputs/grab-first-inspection-fix/frontend.log`.
- Python 근거: `data/outputs/safe-regression/grab-first-inspection-fix/backend.xml`, `safety.json`. 외부 네트워크·실모델·실Gemini 카운터 0. anyio import 순서 경고 1건.
- 실제 Chrome DOM 클릭 및 실제 모델 검사는 **미실행**이다. 단위 검증을 사용자 Chrome 성공으로 주장하지 않는다.

## 중요한 파일 상태 변화 — 불변 PASS로 보고하지 않음

수정 전 검사 JSONL·이벤트 JSONL·RIG state 및 당시 Capture PNG 2개, 총 5개 SHA256을 기록했다.
종료 대조에서 JSONL 2개와 RIG state는 동일했지만 다음 PNG 2개는 없어졌고, Capture 폴더에는 marker 파일만 남아 있었다.

- CAP-1b77b4c227b4429e97efdd36cfd9c04f.png
- CAP-7645749db9da4ebb93b79d715acb9188.png

따라서 `data/outputs/grab-first-inspection-fix/protection-after.json`은 **unchanged=false**다. Capture 보존 PASS를 주장하지 않는다. 새 파일/백업을 임의 생성·복원하지 않았다.
서버 PID는 계속 15016이었다. Codex가 원본 삭제 명령, 서버 종료/재시작, curl/실서버 분석·검사 요청을 실행하지는 않았다.
다만 기존 `CaptureStore.cleanup()`은 TTL 만료 PNG를 삭제하며 `authorize()`/`bootstrap()`에서 실행된다. 프론트엔드 HMR 재마운트 후 브라우저의 기존 자동 그룹 GET도 authorize/cleanup을 통과할 수 있다. 이 경로가 실제 원인이었는지는 요청 시각/로그를 확보하지 않아 **UNKNOWN**이다. 사용자 조작이나 특정 호출의 탓이라고 단정하지 않는다.
이 변화 확인 후 추가 기능/백엔드 변경을 중단했다. 모델·판정·임계값·영속 Crop/Map·PostgreSQL·기존 백업에는 쓰기 작업을 하지 않았다.

## Chrome 확인 절차 및 현재 상태

**코드 수정·오프라인 검증 완료 / 실제 Chrome 확인과 Capture 소실 원인 확인은 PARTIAL**.

1. 백엔드 재시작은 필요 없다. 현재 화면이 예전 프론트 코드인지 먼저 확인한다. 코드가 반영되지 않았으면 임의로 서버를 재시작하지 말고 알린다.
2. 사라진 Capture의 화면 blob만으로 검사할 수는 없다. 사용자가 현재 영상에서 새 Grab/ROI Crop을 준비해야 한다. 이번 수정은 자동 Grab하지 않는다.
3. `[저장 그룹 새로 조회]` 후 이전 그룹 404가 명시되면, **실제로 새 제품을 검사하는 경우에만** `[새 제품 검사 시작]`의 확인창에 동의한다.
4. 서버 Capture/그룹 조회가 성공한 후 “최초 검사 1 / 3 준비”와 검사 버튼 활성화를 확인한다. 이 단계까지 모델은 실행되지 않는다.
5. 실제 검사 버튼 클릭은 사용자가 의도한 검사 실행 시점에만 한다. 같은 제품이 이미 3회 완료된 경우에는 새 그룹으로 우회하지 말고 기존 그룹 접근/수동 확인 절차를 복구해야 한다.
6. 401/403/500이면 차단 유지가 정상이다. Request 경로·상태·error_code만 확인하고 인증 헤더나 쿠키는 공유하지 않는다.
