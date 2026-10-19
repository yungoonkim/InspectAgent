# Day 7 Step 10 — 검사 신뢰성 및 판정 QA

## 상태 요약

- P0 자동 판정/재검사/Fake Vision 회귀: **PARTIAL**. 실제 판정 함수와 격리된 grab/reinspection/vision 테스트는 실행했으나, 전체 안전 러너는 보호 파일 읽기 권한 문제로 시작하지 못했고 Chrome Mock 런타임도 CDP 초기화 단계에서 실패했다.
- PatchCore 결함 검출력 재평가: **NOT TESTED**. 모델 로드와 추론은 이번 작업에서 0회다.
- Step 8.1 ROI 유지: 코드 및 상태 유틸 테스트 존재. 이번 실브라우저 검증은 실패/미완료.
- Gemini Vision: Fake-only offline 코드/테스트. LIVE 전송은 disabled이며 API 지원도 UNKNOWN.

## 실행 환경 및 안전 경계

- `127.0.0.1:8000`에는 LISTEN 프로세스가 없었다. 프로세스 조회 결과 `python.exe`가 둘 있었고 그중 PID 25328은 `uvicorn backend.main:app --reload --reload-dir backend`였다. 따라서 백엔드 코드는 수정하지 않았다. 서버를 종료·재시작하지 않았다.
- `data/outputs/captures/`에서 PNG 4개를 확인했다. 원본 Capture는 열거나 변경하지 않았다.
- 작업 전 Git 상태: 기존 `?? .tmp_measurement_regressions/`. 이 폴더는 보존했다.
- 실제 Gemini API/외부 전송/PatchCore 모델 로드·추론: **0회**.

## 실제 이미지 입력 및 데이터 경로 — 정적 코드 감사

1. 정적 이미지 경로는 서버 `ImageRegistry`에서 중립 image ID를 경로로 해석하고 `cv2.imread`로 디코딩한다 (`backend/inspection.py:78-98, 100-167`). `execute_inspection_workflow`에서 디코딩된 `image` 객체를 `inferencer.predict(image)`에 직접 전달한다 (`backend/inspection.py:494-518`). 이는 호출 계약상 이미지 바이트/픽셀 입력이 모델 경로에 도달함을 보여 준다. 이번에는 해당 경로의 실제 모델 실행을 검증하지 않았다.
2. Grab 경로는 서버 Capture/세션을 검증하고 crop을 저장한 뒤 같은 crop 이미지 ID를 검사 workflow에 연결한다 (`backend/grab_inspection.py:148-190, 230-240`). Crop SHA256 및 provenance를 record metrics에 남기는 경로가 있다 (`backend/grab_inspection.py:54-70, 132-146`).
3. 점수/모델명/추론 시간은 `inferencer.predict` 반환값에서 읽고, 점수가 threshold보다 **엄격히 클 때** 원시 결과 `NG`; 같거나 낮으면 `OK`가 된다 (`backend/inspection.py:513-518, 570-580`). `determine_final_verdict`는 이 원시 결과를 final result와 분리한다 (`backend/inspection.py:581-587`).
4. Map은 같은 prediction의 `anomaly_map`으로 저장되고 inspection/image ID 및 원본 크기를 metadata에 기록한다 (`backend/inspection.py:537-550`). 다만 이번에 과거 Sidecar 파일 대조·모델 재실행은 하지 않았다.
5. inference latency는 `inference_time_ms`로 별도 기록한다. 전체 HTTP 요청 latency와 비교할 관측값은 이번 감사에서 수집하지 않았다.
6. 저장 검사 조회는 저장소 GET 경로이고, 신규 분석은 별도 POST 경로다. 저장된 JSON/Sidecar를 보여 주는 UI 결과만으로 새 추론이 실행됐다고 볼 수 없다. 이번 테스트는 실제 API 운영 요청과 PatchCore를 호출하지 않았다.

### 판정 정책

`backend/decision.py:28-85`의 실제 `determine_final_verdict` 우선순위:

| 입력 상태 | 결과 | 근거 |
|---|---|---|
| pipeline `FAILED` | `ERROR / INSPECTION_FAILED` | 최우선 |
| quality가 `NORMAL` 아님 | `REINSPECT / IMAGE_QUALITY_WARNING` | 모델 NG도 덮지 않고 재검사 |
| 모델 미완료 또는 raw 결과 `UNKNOWN` | `REINSPECT / DEFECT_DETECTION_UNAVAILABLE` | 점수 판정 불가 |
| NORMAL + raw NG | `NG / PRODUCT_ANOMALY_DETECTED` | 모델 결과 적용 |
| NORMAL + raw OK | `OK / ALL_CHECKS_PASSED` | 검사 완료 |
| 기타 조합 | `REINSPECT / UNKNOWN_STATE_COMBINATION` | 보수 fallback |

워크플로우의 모델 호출 예외는 inference status를 `FAILED`로 기록하지만, 해당 경로에서 전체 workflow status 인자는 `COMPLETED`로 전달되고 raw 결과는 UNKNOWN이다 (`backend/inspection.py:552-587`). 따라서 모델 예외는 이 경로에서 **ERROR가 아니라 REINSPECT**로 끝날 수 있다. 이는 “pipeline 자체 실패→ERROR”와 “완료된 pipeline 안의 모델 단계 실패→REINSPECT” 구분이다. Grab 전용 실패 경로도 별도 API/예외 매핑을 가진다. API 전체의 모든 오류 케이스를 이번에 새로 입증하지 않았다.

## 자동화 분기 검증

신규 `tests/test_day10_decision_matrix.py`는 production `determine_final_verdict`를 직접 호출해 OK, NG, warning+OK, warning+NG, model skipped/failed UNKNOWN, pipeline failed, fallback 총 8 조합을 검증한다. 테스트 구현에 별도 decision logic은 없다.

- 첫 실행은 기본 Windows pytest temp 경로 접근권한 문제로 **8 PASS / 81 ERROR**였다. 제품 코드 실패로 분류하지 않았다.
- 격리 `--basetemp=data/outputs/day10-pytest-isolated-20261019`, `-p no:cacheprovider` 재실행: **89 PASS / 0 FAIL / 0 SKIP**, 29.70초 (`tests/test_day10_decision_matrix.py`, `tests/test_grab_inspection.py`, `tests/test_reinspection_workflow.py`). 여기에는 score 경계/NaN, mock Crop pipeline, reinspection 횟수·동시성·수동판정 회귀가 포함된다.
- 추가 `tests/test_vision_review.py` + 결정표: **54 PASS / 0 FAIL / 0 SKIP**, 14.25초. Fake SDK 입력 Crop/해시 연결, 실패 처리, 중복·동시 요청, 원본 판정 불변 및 live-disabled 계약 테스트.
- 테스트 경로는 Fake inferencer/Fake client이며 실제 PatchCore/Gemini는 실행하지 않았다.
- 저장소 저장 오류, 로그 저장 오류, 모든 API status 및 실제 ERROR 응답 계약의 전체 행렬은 아직 독립적인 전수 검증으로 완료하지 않았다.

## 기존 모델 성능 근거와 한계

`scripts/evaluate_patchcore_testset.py:1-80`은 공식 checkpoint `models/patchcore/patchcore_bottle.ckpt`, metadata threshold(기본값 34.1442), CPU inferencer 및 MVTec Bottle test 하위 범주를 대상으로 한 평가 실행기를 기술한다. 스크립트 실행은 하지 않았다. 또한 `docs/day4-completion-and-day5-roadmap-summary.md:96-111`에 역사적 요약값이 기록되어 있다.

| 기록된 과거 지표 | 값 |
|---|---:|
| 표본 | 83 (good 20, defect 63) |
| TP / FP / FN | 32 / 0 / 31 |
| Recall | 50.79% |
| Precision | 100% (표본 한정) |
| Image AUROC | 약 0.8286 |
| Threshold | 34.1442 |

이 값은 이 저장소의 **과거 보고 기록**이다. 이번 실행에서 재계산하거나 checkpoint fingerprint·실행 시점·전처리 provenance를 독립 재현하지 않았다. 평가 실행기는 `dataset/bottle/test`의 클래스 폴더를 enumerate한다고 코드에 쓰지만, 평가 이미지/정답을 이번에 열지 않았다. Ground Truth 경로에 접근하지 않았다. 그래서 수치는 운영 LiveView Crop의 검출 성능으로 일반화할 수 없다.

과거 T06 `INSP-001406`은 score 약 32.27, 저장 raw/final OK의 미검출 사례로 문서화되어 있다 (`docs/day4-completion-and-day5-roadmap-summary.md:77-95`). 이는 모델의 놓침 위험을 보여 주는 역사적 사례일 뿐, 이번에 정답 데이터로 재검증한 것은 아니다.

Normalize 경로는 이전 감사에서 학습 1회, calibration/운영 2회로 기록되었고 해결되지 않았다. 본 작업에서 바꾸거나 추론으로 확인하지 않았다.

## 테스트 결과 및 증거 경로

- 과거 안전 회귀 증거: `data/outputs/safe-regression/20261018-225800-d19e47a0/summary.json`, `safety.json`, `protection.json` — 당시 Backend 567 PASS/0 FAIL/10 SKIP, Frontend 39 PASS, Chrome Mock 50 PASS, TypeScript/Build/Lint PASS, 80 보호 파일 불변 기록. 이는 과거 결과다.
- 이번 safe runner: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_safe_regression.ps1`는 snapshot 시작 때 운영 파일 `data/outputs/inspection_anomaly_maps/INSP-001650.json` 읽기 권한 오류로 중단. 생성 경로 `data/outputs/safe-regression/20261019-102005-ff7e7178/`. **Pytest/browser 단계는 실행되지 않았고** runner FAIL은 코드 테스트 실패와 구분한다.
- 프런트 단위: `node --test --test-reporter=tap scripts/test_image_transform.mjs ../frontend/test_f31_units.js scripts/test_step4_regression.mjs scripts/test_agent_analysis_state.mjs scripts/test_grab_inspection.mjs scripts/test_reinspection_state.mjs scripts/test_roi_vision_state.mjs` — 39 PASS/0 FAIL/0 SKIP, 143 ms.
- Python quality: `npm.cmd run lint` (6 warnings), `tsc -b` (PASS), `npm.cmd run build` (PASS). 경고는 AgentPanel 1, ImageView 5이며 이번에는 수정하지 않았다.
- Chrome Mock 5 group (base/agent/grab/roi/vision)은 모두 Chrome 155의 CDP `Page.enable` timeout으로 0 test / 1 harness failure each. Output root: `data/outputs/day10-chrome-mock-20261019/`. 실제 브라우저 동작 검증으로 주장할 수 없다.
- Git status 마지막 관측: 기존 `.tmp_measurement_regressions/`, 신규 `tests/test_day10_decision_matrix.py`; 별도 문서 추가 이후 재확인이 필요하다.

## 다음 P0/P1 조치

1. 사용자가 `--reload` 서버를 직접 안전 종료하고 Capture 보존을 확인한 뒤에만 Backend 통합 runner 재시도 검토. 운영 자산 snapshot에서 ACL 읽기 문제를 고친 후에는 별도 승인/검증이 필요하며 운영 JSONL을 임의로 바꾸지 않는다.
2. Chrome CDP timeout 원인을 harness/browser 환경에서 분리 진단하고, 임시 프로필 기반 mock E2E를 재검증한다.
3. save-inspection/log failure, invalid ID, duplicate/concurrent POST 및 GET-vs-new-inference 차이를 임시 저장소 테스트로 추가 확인한다.
4. 실제 검출 성능 재평가, OpenCV PoC, 실제 Gemini Vision은 P1 별도 승인 범위다. OpenCV PoC는 이번 P0에서 실행하지 않았고 기준 라벨이 없다.

### 결론

P0는 자동화 회귀의 상당 부분을 Fake 기반으로 검증했으나, 안전 runner와 브라우저 E2E가 실패하여 **PARTIAL**이다. 모델의 결함 검출 정확도는 이번 작업에서 검증하지 않았다.
