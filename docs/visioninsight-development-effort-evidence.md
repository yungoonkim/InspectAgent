# VisionInsight 개발 작업량 — 확인 가능한 증거

## 범위와 해석 규칙

이 문서는 작업 시간 추정치가 아니라 저장소와 기록으로 확인할 수 있는 작업 산출물·검증 이력의 요약이다. Git commit 사이의 시간을 실제 코딩 시간으로 환산하지 않았고, 테스트 실행 시간을 개발 시간으로 계산하지 않았다.

## 근거가 확인되는 기술 작업 축

| 분야 | 근거 자료/구현 | 확인 가능한 성과 | 신뢰 수준 |
|---|---|---|---|
| 검사 API/데이터 | `backend/inspection.py`, `backend/storage.py`, `docs/inspection-data-schema.md` | 입력 registry, workflow, 기록/로그 계약 | 소스 코드 확인 |
| PatchCore | `backend/ml/patchcore_inferencer.py`, training/evaluation scripts, PatchCore audit docs | 모델 실행 경로와 보정 한계 문서화; 이중 Normalize 미해결 | 코드/문서 확인, 이번 추론 아님 |
| 영상/Grab/ROI | `backend/video_source.py`, `backend/grab_inspection.py`, `backend/reinspection_store.py` | H.264 frame, session-protected Capture, Crop provenance, 재검사 그룹 및 수동 이력 | 코드 확인 |
| Anomaly Map | `backend/anomaly_map_store.py`, `backend/inspection.py`, ImageView | map sidecar와 inspection/image metadata 연결 | 코드 확인, 이번 재현 아님 |
| Gemini Diagnostic | `backend/agent/` 및 Day 7 docs/tests | 별도 Function Calling 분석, Fake 검증/Live 안전 게이트 | 과거 보고+코드 구조 |
| Gemini Vision | `backend/vision_review.py`, `backend/vision_review_api.py`, `VisionReviewPanel.tsx` | Fake-only crop validation/persistence/disabled capability | 코드+이번 Fake tests |
| 재검사/작업자 판단 | `backend/reinspection_store.py`, `tests/test_reinspection_workflow.py`, `GrabInspectionPanel.tsx` | 3 attempt cap, immutable inspections, separate manual outcomes | 코드+이번 회귀 |
| UI 좌표/시각화 | `frontend/src/components/LiveView.tsx`, `ImageView.tsx`, frontend state/transform scripts | ROI coordinate mapping, zoom/pan, pixel inspector, overlay logic | unit tests; browser current run blocked |
| 테스트 안전성 | `scripts/run_safe_regression.ps1`, `scripts/safe_regression_backend.py` | isolated evidence folder, protected asset snapshot, forbidden-call counters | 코드 확인; 이번 full runner snapshot failed |

## 개발 단계와 검증 증거

- 저장소 문서에는 Day 1–7 및 Day 7 Step 8/8.1/9/10 단계별 작업/인수 기록이 존재한다. 문서 단계 수는 기간이나 투입 시간과 같지 않다.
- 저장된 안전 회귀 evidence `data/outputs/safe-regression/20261018-225800-d19e47a0/`은 과거 Backend 567 PASS/10 SKIP, Frontend 39 PASS, Chrome Mock 50 PASS, 80 protected files unchanged, 실제 Gemini/PatchCore 호출 0을 기록한다.
- 이번 Step10 관련 Python: 격리 run `data/outputs/day10-pytest-isolated-20261019/`에서 89 PASS; `data/outputs/day10-vision-pytest-20261019/`에서 54 PASS. 각각의 범위는 Step10 report에 구분했다.
- 이번 frontend unit: 39 PASS. `npm run lint`: PASS, 6 warnings. `tsc -b`: PASS. `npm run build`: PASS.
- 이번 안전 회귀 runner는 snapshot 단계 권한 오류로 테스트 전에 중단되어 `data/outputs/safe-regression/20261019-102005-ff7e7178/`에 FAIL evidence를 남겼다.
- 이번 Chrome mock harness 5종은 CDP Page.enable timeout으로 0 cases; output `data/outputs/day10-chrome-mock-20261019/`.

## Step10의 확인된 오류와 수정

- Windows pytest 기본 temp/cache 경로는 읽기 권한 오류를 내어 첫 시도에서 81 setup ERROR가 발생했다. 제품 테스트 실패로 판단하지 않고 `-p no:cacheprovider`와 별도 `--basetemp`로 격리 재실행하여 89 PASS를 얻었다.
- 안전 러너 보호 스냅샷은 `INSP-001650.json`을 읽지 못해 시작 실패했다. 이 운영 파일의 ACL을 바꾸거나 대체하지 않았다.
- Chrome 155 CDP `Page.enable` timeout이 5 mock groups 모두에서 발생했다. 브라우저 버전만 원인으로 확정하지 않았고 harness/browser transport 진단이 남아 있다.
- Frontend lint 6 warnings는 AgentPanel 1, ImageView 5에 있었고 무관한 UI 로직은 변경하지 않았다.

## 파일 수/투입 시간에 관한 한계

이 보고서 작성 시 Git 작업트리는 `.tmp_measurement_regressions/`라는 기존 untracked 디렉터리와 `tests/test_day10_decision_matrix.py` 신규 파일을 포함했다. 현재 Step10에서 수정한 구현 파일은 없다. Git diff 통계는 tracked diff만 보여 신규 untracked 내용은 포함하지 않으므로 전체 개발 파일 수로 오해하지 않는다. 일자별 전체 변경 파일 수는 이번에 재산출하지 않았다.

실제 투입 시간, 세션별 작업 분, 문제 해결 대기 시간은 확인 가능한 타임시트가 없어 **UNKNOWN**이다. 발표에서는 확인된 코드 계층·실험/테스트 계약·보안 경계·미해결 정확도 리스크를 설명하고, 근거 없는 시간 수치는 제시하지 않는다.
