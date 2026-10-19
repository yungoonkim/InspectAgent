# Day 7 Step 10 — 전체 UI 자동화 매트릭스

## 판정 기준

- `PASS`: 이번 실행 또는 저장된 하네스가 해당 계약을 직접 검사함.
- `PARTIAL`: 공통 유틸/과거 mock 증거는 있으나 이번 Chrome harness가 실패하거나 컨트롤별 검증이 분리되지 않음.
- `SKIP`: 명시적 safety policy에 의해 실행하지 않음.
- `NOT TESTED`: 현재 증거로 기능 동작을 입증할 수 없음.
- Chrome Mock은 실제 사용자 Chrome·운영 서버 검증과 다르다.

## 이번 검증 요약

- Frontend unit: 39 PASS, 0 FAIL, 0 SKIP.
- Step 10 신규 decision/reinspection/backend fake group: 89 PASS.
- Vision Fake + decision: 54 PASS.
- 현재 Chrome Mock 재실행 5개 그룹: 모두 CDP `Page.enable` 초기화 timeout, 각각 0 test.
- 기존 저장 안전회귀: Backend 567 PASS/10 SKIP, Frontend 39 PASS, Chrome Mock 50 PASS는 `data/outputs/safe-regression/20261018-225800-d19e47a0/summary.json`의 과거 증거이며 이번 결과가 아니다.
- 실제 Chrome 수동 확인: 이번 세션에서는 수행하지 않음.

## 컨트롤 및 워크플로우 검증표

| 화면/컴포넌트 | 컨트롤·입력 | 기대 동작 | API/연결 | 상태 | 테스트 증거 | Chrome 수동 |
|---|---|---|---|---|---|---|
| Header | MANUAL/AUTO 모드 선택 | 모드 전환, AUTO는 미구현 기능을 과장하지 않음 | App state | NOT TESTED | 전체 UI 매트릭스만 확인 | 필요 |
| LiveView | Play/Pause | 영상 재생/정지, ROI 유지 | video API | PARTIAL | ROI state unit에 재생 상태와 무관한 ROI binding | 필요 |
| LiveView | Seek/time slider | 프레임 위치 변경, ROI 유지 | video seek API | PARTIAL | ROI state 테스트는 frame index 독립성만 확인 | 필요 |
| LiveView | -1/+1 Frame | 한 프레임 이동 | video API | NOT TESTED | 개별 동작 증거 없음 | 필요 |
| LiveView | Frame index/시간 표시 | 현재 위치 표시 | video stream metadata | NOT TESTED | 이번 실행 미검증 | 필요 |
| LiveView/ROI | ROI 생성 | 원본 영상 픽셀 좌표로 생성 | local state | PARTIAL | production ROI mapping round-trip unit | 필요 |
| LiveView/ROI | Drag/Resize | pointer 좌표를 source ROI로 변환 | local state | PARTIAL | ROI clamp/mapping unit, Chrome 실행은 timeout | 필요 |
| LiveView | ROI Reset | 명시적 초기화 | local state | NOT TESTED | control 별 E2E 미통과 | 필요 |
| LiveView | ROI 유지 | 동일 video/revision/dimensions에만 유지 | ROI binding util | PASS(unit contract) | `test_reinspection_state.mjs`; 이번 단위 모음 내 39 PASS | 필요 |
| LiveView | 새 프레임 Grab | 새 Capture 발급, 기존 ROI 재사용 | `POST /video/grab` | PARTIAL | Grab identity unit, backend fake tests 과거/이번 일부 | 필요 |
| LiveView | 같은 frame/Crop 재사용 | 새 재검사로 가장하지 않고 거부 | Capture identity guard | PASS(fake) | `tests/test_reinspection_workflow.py` 포함 89 PASS | 필요 |
| ImageView | Crop 표시/소스 전환 | 현재 Capture/등록 이미지의 올바른 이미지 표시 | image fetch | PARTIAL | 과거 Chrome 50 mock, 이번 Chrome harness 시작 실패 | 필요 |
| ImageView | Zoom 100–4000% | 범위 clamp 및 pixel transform | local transform | PASS(unit) | `test_image_transform.mjs` | 필요 |
| ImageView | 포인터 기준 zoom | anchor pixel 고정 | local transform | PASS(unit) | transform tests | 필요 |
| ImageView | Pan/Reset | 이미지·overlay 같은 transform | local transform | PARTIAL | helper tests; 실제 browser run timeout | 필요 |
| ImageView | Grid | grid 표시 전환 | local state | NOT TESTED | 이번 테스트 증거 없음 | 필요 |
| ImageView | Pixel Inspector RGB/GV | 원본 픽셀 채널 기준 읽기 | source image data | PASS(unit) | source-channel GV test | 필요 |
| ImageView | 검은 padding 구분 | 패딩을 원본 픽셀로 오인하지 않음 | source bounds | PARTIAL | padding zoom helper test, pixel edge browser unverified | 필요 |
| ImageView | OK/NG/REINSPECT overlay | 저장 판정을 올바른 검사 ID에 표시 | inspection result | PARTIAL | 기존 mock 기록, 이번 화면 E2E 불가 | 필요 |
| ImageView | Heatmap on/off | 동일 검사 map만 표시 | `GET /inspections/{id}/anomaly-map` | PARTIAL | 기존 UI unit 및 과거 Chrome 50; 이번 Chrome timeout | 필요 |
| ImageView | Heatmap opacity | alpha 변경 | local rendering | PARTIAL | 과거 mock evidence; 이번 실행 없음 | 필요 |
| ImageView | image switch/stale response | 구 이미지 heatmap 제거 | abort/identity guard | PASS(unit) | stale metadata/PNG tests within 39 | 필요 |
| InspectionPanel | Registered static inspection | 등록 image_id로 새 검사 | `POST /inspections` | NOT TESTED | 이번 P0에서는 운영 API 호출 금지 | 필요(격리 서버 권장) |
| GrabInspectionPanel | Grab inspection | 서버 Capture 검증 후 새 검사 | `POST /captures/{capture_id}/inspect` | PASS(fake) | `test_grab_inspection.py` 포함 89 PASS | 필요 |
| InspectionPanel | Inspection ID 조회 | 저장된 검사 조회, 재추론 없음 | `GET /inspections/{id}` | NOT TESTED | GET/POST 차이 정적 계약만 확인 | 필요 |
| InspectionPanel | score/threshold/quality/final | 저장 결과의 원본 표시 | inspection response | PARTIAL | fake inspection tests; UI browser harness timeout | 필요 |
| Source badge | REGISTERED vs LIVEVIEW_GRAB | 이미지 출처와 result가 일치 | response metrics | PARTIAL | Grab exact-source unit; 전체 UI 실브라우저 미통과 | 필요 |
| GrabInspectionPanel | attempt 1/3…3/3 | server count와 표시 일치 | reinspection group API | PASS(fake) | `test_reinspection_workflow.py` 포함 89 PASS | 필요 |
| GrabInspectionPanel | 동일 제품 확인 | 명시 체크 없으면 차단 | reinspection API | PASS(fake) | continuity tests | 필요 |
| GrabInspectionPanel | 신규 Capture/4회차 차단 | 같은 이미지 재사용/초과 시 409 | reinspection store | PASS(fake) | same-frame/same-PNG/fourth attempt tests | 필요 |
| GrabInspectionPanel | reload 이후 이력 | 저장 그룹 상태 복원 | group GET | PASS(fake) | persisted history tests | 필요 |
| GrabInspectionPanel | 이미지/Heatmap 조회 | 선택 attempt의 source/map 표시 | inspection/map GET | PARTIAL | API fake tests; Chrome run 실패 | 필요 |
| Manual review | HOLD 기본, MANUAL_OK/NG, operator, reason | 수동 기록만 추가; 원 검사 immutable | manual review API | PASS(fake) | three outcomes + validation tests | 필요 |
| AgentPanel | 저장 Agent 보고서 GET | 기록 보고서 조회, live 호출 0 | `GET /agent-report` | NOT TESTED | 이번 세션 live/API test 안 함 | 필요 |
| AgentPanel | Live analyze confirm | 명시 확인 후 별도 live analysis | `POST /analyze/{id}` | SKIP | 실제 Gemini 호출 금지 | 별도 승인 필요 |
| AgentPanel | 오류/상태 | live failed와 stored report 구분 | agent API | PARTIAL | frontend state tests 39; browser test 불가 | 필요 |
| VisionReviewPanel | 대상 검사 선택 | REINSPECT + LIVEVIEW_GRAB만 허용 | `GET /inspections/{id}/vision-review` | PASS(fake contract) | Vision state and 54 Python tests | 필요 |
| VisionReviewPanel | image SHA/source | inspection/capture/hash/group 바인딩 | server crop validation | PASS(fake) | `tests/test_vision_review.py` | 필요 |
| VisionReviewPanel | LIVE disabled state | fake를 live로 표시하지 않음 | capabilities | PASS(fake contract) | live-disabled tests; run 54 PASS | 필요 |
| VisionReviewPanel | fake result source label | `FAKE_TEST`, 제품 판정 아님 | response mode | PASS(fake) | UI unit contract | 필요 |
| VisionReviewPanel | stale response/image switch | 오래된 의견을 다른 crop에 붙이지 않음 | request identity | PARTIAL | state utility tests; Chrome harness failed | 필요 |
| Network/error | 401/403/404/409/422/503, timeout | 안전한 오류/재호출 방지 | API clients | PARTIAL | fake service/error tests; UI별 전수는 아님 | 필요 |
| Browser/general | double-click, keyboard, resize, refresh | 중복 방어/반응형/키보드 계약 | mixed | NOT TESTED | 현재 Chrome harness가 시작 전 timeout | 필요 |
| ROI DB UI | preset 저장/활성화 화면 | 기능 존재 여부부터 확인 | PostgreSQL ROI API | NOT IMPLEMENTED/NOT TESTED | 이 화면 인벤토리에서 UI 컨트롤 없음 | 필요 없으면 범위 제외 |

## Chrome Mock 실행 세부 정보

명령 형태: `node frontend/scripts/test_step4_browser.mjs <installed-Chrome> --output <isolated-output> [--agent|--grab|--roi|--vision]`.
이번에는 5개 그룹 모두 browser version `Chrome/155.0.8059.82`에서 CDP `Page.enable` timeout. 출력은 `data/outputs/day10-chrome-mock-20261019/{base,agent,grab,roi,vision}/`에 격리됐다. 실제 웹앱/사용자 프로필을 열지 않고 로컬 mock Vite harness만 구동하도록 구성돼 있었으나, CDP 초기화 실패로 케이스 결과는 0개다.

## 사용자 Chrome 확인 체크리스트

실제 Chrome 확인 시에도 운영 Capture를 임의 재검사하지 말고, 기존 사용자가 승인한 검증용 검사/캡처만 선택한다.

1. LiveView에서 ROI 생성 후 Play/Pause, seek, frame step, Grab, REINSPECT 결과 뒤 ROI 위치·크기가 유지되는지 확인한다. 영상 속 병 자동 추적이 아님을 확인한다.
2. 새 프레임 Grab에서 Capture ID와 frame index가 바뀌고, 등록 이미지 결과와 LIVEVIEW_GRAB badge가 혼동되지 않는지 확인한다.
3. ImageView 확대/축소/이동/Reset, grid, RGB/GV, 검은 padding, Heatmap toggle/opacity를 확인한다. 이미지 변경 직후 이전 Heatmap이 사라지는지 확인한다.
4. 재검사 그룹 attempt 수, 제품 확인, 같은 Crop 차단, fourth-attempt 차단 및 새로고침 복원을 확인한다. 수동 결과는 HOLD 기본이며 원본 final_result는 유지돼야 한다.
5. Vision 패널은 LIVE disabled 상태여야 하며 실제 Provider 요청 없이 기존 Fake/기록 결과를 live로 표시하지 않아야 한다.
6. 별도 승인 없이 `POST /analyze`나 Vision live 버튼을 실행하지 않는다.
