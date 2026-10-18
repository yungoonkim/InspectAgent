# Step 8.1 + Step 9 안전 작업 인계 — 2026-10-18

## 1. 상태와 안전 경계

사용자 긴급 인계 요청으로 새 기능 확장을 중단한다.

| 범위 | 상태 | 실제 완료 / 미완료 |
|---|---|---|
| Step 8.1 | COMPLETE | ROI 유지 구현·안전 회귀·정적 검토 완료. 사용자의 실제 Chrome 수동 확인은 별도 수행 |
| Step 9 오프라인 | COMPLETE | Fake 전용 서비스/API/UI·안전 회귀·정적 검토·API 명세 완료. LIVE는 별도 BLOCKED |
| Step 9 LIVE | BLOCKED | 전송 어댑터 미구현, 기본 DISABLED. 모델 지원 및 SDK HTTP 재요청 상한 UNKNOWN |

실제 Gemini API·외부 이미지 전송·PatchCore 로드/추론 0회. 서버 시작/종료/재시작 0회. PostgreSQL 접속/변경 없음. 모델·threshold34.1442·밝기125·Normalize·Calibration·Decision·Diagnostic Agent는 이번에 변경하지 않았다.

코드 수정 전 및 복구 확인에서 port8000 LISTEN 0, backend.main/Uvicorn/reload 프로세스 0을 확인했다. CIM 조회는 기본 권한에서 한 차례 거부됐고, 읽기 전용 재조회에서 0건을 확인했다. 서버를 시작·종료·재시작하지 않았다. 다음 세션도 상태를 다시 확인하고 사용자 서버가 실행/reload 중이면 백엔드 편집을 보류한다.

## 2. 이번 변경 파일

신규 Backend:
- `backend/vision_review.py`: strict 입력/출력/저장 스키마, PNG 검증, Fake-only 서비스, 별도 파일 Lock/영속 예약/제한.
- `backend/vision_review_api.py`: 세션·Origin·CSRF·영속 Crop 권한을 검증하는 GET/POST 라우터.

기존 Backend 최소 변경:
- `backend/main.py`: Vision 라우터 등록만 추가. 기존 dirty Agent/검사 코드는 보존.
- `backend/grab_inspection.py`: 기존 Capture PNG 해시를 재검사 중복 검사에 전달.
- `backend/reinspection_store.py`: 같은 그룹의 같은 녹화 프레임/동일 PNG 재검사 차단. 3회·수동 확인 정책 불변.

Frontend:
- `frontend/src/App.tsx`, `components/LiveView.tsx`: ROI 수명과 Capture 수명 분리, 기존 ROI 적용 Grab, 늦은 응답/중복 Grab 방어, Vision 패널 연결.
- `frontend/src/components/GrabInspectionPanel.tsx`: 재검사 안내 수정. 새 ROI를 매번 요구하지 않음.
- 신규 `frontend/src/utils/roiLifetime.ts`, `utils/visionReviewState.ts`, `api/visionReview.ts`, `types/visionReview.ts`, `components/VisionReviewPanel.tsx`.

테스트/러너:
- 신규 `tests/test_vision_review.py`, `frontend/scripts/test_roi_vision_state.mjs`, `frontend/scripts/roi_browser_cases.mjs`, `frontend/scripts/vision_browser_cases.mjs`.
- 변경 `tests/test_reinspection_workflow.py`: 서로 다른 Fake 프레임 데이터와 2개 중복 프레임/PNG 방어 테스트.
- 변경 `frontend/scripts/grab_browser_cases.mjs`, `frontend/scripts/test_step4_browser.mjs`: 신규 Mock harness와 서로 다른 Capture 프레임.
- 변경 `scripts/safe_regression_backend.py`, `scripts/run_safe_regression.ps1`: 기존 그룹 유지, 신규 검증·보호 경로 추가.
- 이번 인계 문서 및 기존 Step8.1/Step9 문서 진행 현황 갱신.

`docs/inspection-data-schema.md`, Agent/ImageView/inspection 등 저장소의 여러 수정은 이전 작업부터 dirty 상태다. 이번 세션이 전부 수정한 것으로 간주하거나 되돌리지 않는다. 발표 PPT 삭제/신규 파일도 기존 상태이며 절대 손대지 않는다.

## 3. 구현 계약 및 사용 흐름

- ROI 키는 video_id/source_revision/원본 width/height. 원본 half-open 픽셀 좌표 유지. Play/Pause/Seek/Step/Grab/REINSPECT는 ROI를 지우지 않는다. 소스 변경·범위 오류·명시 Reset은 무효화한다.
- 동일 녹화 프레임은 새 광학 정보가 아니다. 다른 프레임 선택 → 저장 ROI로 Grab → 동일 제품 명시 확인 → 새 Capture 검사. 최대 완료3회 정책은 유지한다.
- 같은 Crop Vision 의견은 신규 Capture/검사/횟수 증가 없이 별도 패널에 표시한다. 기본 UI에서는 실제 API 비활성 이유만 표시하며 Fake 결과를 생성하지 않는다.
- 원본 검사 SOURCE는 기존 InspectionPanel의 LIVEVIEW_GRAB/REGISTERED STATIC IMAGE 구분을 보존했다. Zoom/Pan/Heatmap/Pixel Inspector 코드는 이번에 수정하지 않았다.
- `GET /inspections/{inspection_id}/vision-review`: 권한 있는 해당 Crop의 저장 결과 및 capabilities 조회.
- `POST` 같은 경로: `{ "request_id": "32자리 소문자 UUID hex" }`만 허용. 기본 서버는 403 VISION_LIVE_DISABLED. 명시 Fake DI 테스트만 생성 가능.
- GET/POST 응답 `{available, review, capabilities}`. review는 VREV/INSP/RIG/CAP, Crop hash/크기, 모델 요청/응답 식별자, prompt_version, 분류, 관찰/한계/권고, failure_code, 시각, FAKE_TEST를 연결한다.
- 4개 의견 enum은 엔진 OK/NG가 아니다. 오류는 별도 ANALYSIS_FAILED. 관찰 근거가 비어 있는 성공 의견은 거부한다. schema 검증은 모델 주장 진실성/정확도를 보증하지 않는다.
- `OUTPUT_DIR/vision_reviews/state.json`과 자체 `workflow.lock`. 같은 파일 경로를 공유하는 로컬 OS Lock 범위다. 분산 클라우드 저장/다중 호스트 보장은 하지 않는다.
- 호출 전 영속 PENDING, 실패/취소/불확실 결과 자동 재전송 금지, 검사별1회/일10회/전체128개. 저장 실패/프로세스 중단의 PENDING은 수동 조사 대상이다.
- 초기화/기본 GET은 실제 SDK를 만들지 않는다. `VISION_REVIEW_MODEL`만 별도 설정이고 enable 환경변수로 LIVE를 활성화할 수 없다.

## 4. 실제 실행 결과

최종 명령:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_safe_regression.ps1
```

최종 증거 디렉터리: `data/outputs/safe-regression/20261018-225800-d19e47a0/`.

| 그룹 | PASS | FAIL | SKIP |
|---|---:|---:|---:|
| Backend 안전 선택 회귀 | 567 | 0 | 10 |
| Frontend 단위 | 39 | 0 | 0 |
| Chrome Heatmap / Agent / Grab | 12 / 8 / 15 | 0 | 0 |
| Chrome 신규 ROI / Vision | 8 / 7 | 0 | 0 |
| TypeScript / Build / Lint | 성공 | 0 | 0 |

Backend 49.99초, pytest anyio rewrite 경고1. Lint 기존6개(AgentPanel/ImageView effect/ref dependency), 신규 경고 없음. Chrome 총50 PASS. 전체 pytest를 실행한 결과가 아니라 **안전 선택 회귀**다.

SKIP10: Windows symlink 권한1, 실제 모델 제외6, 격리 저장소 빈 조회1, 실제 데이터셋 의존2. 억지 활성화하지 않았다.

집중 Vision46 PASS(11.42초): 실제 임시 Crop bytes, 4종 enum/실패, JSON/PNG/hash/소유권/Origin/CSRF, UUID 중복·동시성·Timeout·취소PENDING·저장 결과 재검증, 기존 판정/그룹/수동 결과 불변을 확인했다.

중간 실패는 숨기지 않는다: 관련 테스트 첫 실행121 PASS/1 FAIL(테스트의 고정 frame122 충돌)을 순차 Fake 프레임으로 수정 후124 PASS. ROI 브라우저 첫 실패는 Mock data-URL fetch가 기존 CSP에 차단된 것으로 메모리 Response로 수정(CSP 완화 없음), 두 번째 실패는 기존 Agent GET Mock 누락으로 정확한404를 추가했다. 최종 ROI8 PASS. 초기에 새 lint 경고1개는 render의 ref 읽기를 상태값으로 대체해 제거했다. 최종 알려진 FAIL 없음.

## 5. 운영 자산

최종 러너의 보호 운영 파일80개 SHA256 전후 일치. `safety.json`의 network/forbidden_io/real_prediction/real_load/real_gemini_api_calls 모두0. Chrome Mock은 별도 loopback 정적 테스트 서버만 사용하며 실제 백엔드/API로 빠지지 않는다.

작업 시작 증거는 `data/outputs/safe-regression/step81-step9-start/protected-before.json`. 후속 복구 세션에서 읽기 전용 해시 비교를 수행해 `Operational assets: PASS`를 확인했다. 최초 권한으로는 보호된 Anomaly Map Sidecar 읽기 오류가 났고, 같은 helper의 승인된 재시도는 통과했다. 최종 러너 `protection.json`은 `unchanged=true`, `files=80`이다.

사용자 서버 종료 전86개와 현재80개의 차이는 임시 Capture6개다. 백업을 운영 세션에 재등록하지 않았다. 기존 두 외부 백업은 수정/삭제하지 않았다. 기존 검사 JSONL/재검사/수동 확인/Crop/Sidecar/모델/영상은 러너 기준 불변이다.

## 6. 다음 Codex 재개 순서

1. AGENTS.md와 두 진행 문서 및 이 인계를 읽고 git status --short 확인. 기존 dirty 파일을 삭제/복원하지 말 것.
2. port8000 및 backend.main/Uvicorn/reload 감시 프로세스를 읽기 전용으로 재확인. 실행 중이면 백엔드 편집 전에 사용자 안전 확인.
3. 코드 변경 없이 최종 summary/safety/로그 검토. 필요 시 최초 기준선 대조:

```powershell
& C:/Users/USER/miniconda3/envs/vision-insight/python.exe -B scripts/safe_regression_backend.py verify --output data/outputs/safe-regression/step81-step9-start
```

4. 이번 문서 변경만 대상으로 `git diff --check`를 수행. 구현 변경 없이 두 상세 보고서와 데이터 스키마를 검토 완료했다. 이후 수정 시 이전 감사 기록을 보존.
5. 코드 수정이 필요할 경우 안전 러너 재실행. 위 최종 통과 수치를 새 실행 결과로 재사용하지 말 것. 단일 Vision 집중 실행 예:

```powershell
& C:/Users/USER/miniconda3/envs/vision-insight/python.exe -B scripts/safe_regression_backend.py backend --output data/outputs/safe-regression/step9-handoff-next tests/test_vision_review.py
```

6. 사용자 Chrome 점검 안내: 사용자가 서버 실행한 후 MANUAL Pause/ROI → Grab → Play/Pause/Seek/Step에서 좌표 유지 → 다른 프레임 Grab에 같은 ROI 확인 → 명시 Reset. 실제 검사 버튼은 별도 승인 전 누르지 않는다. 기존 접근 가능한 REINSPECT 선택 시 Vision은 별도 패널·DISABLED여야 한다. 새 세션으로 과거 Crop 접근 불가면 실패 폐쇄가 정상이다.
7. 실제 모델/네트워크 없이 최종 보고하고 사용자 승인 대기. 이번 인계는 LIVE 호출 승인이 아니다.

미해결: 후보 모델 API/이미지/SDK structured output 지원 UNKNOWN, 실전 SDK wire 재전송 상한 UNKNOWN, 과거502 UNKNOWN. 실제 Vision 전송 어댑터·승인된 비용 한도·인증/배포 정책을 별도 설계/승인하기 전 LIVE 활성화 금지. Vision 일별 `days` 카운터는 UTC 날짜별 키가 누적되므로 장기 운영 전 크기 관리 검토가 필요하다. 파일 Lock은 공유 가능한 로컬 파일시스템 협력 프로세스 범위이며 다중 호스트 분산 저장 보장이 아니다. 조기 HOLD/수동 확인은 현재3회 정책을 바꾸므로 별도 승인안으로만 제안한다.

## 8. 복구 세션의 정적 검토 및 사용자의 Chrome 점검

- `roiLifetime.ts`, `App.tsx`, `LiveView.tsx`: ROI source identity는 video_id/revision/원본 width/height. ROI 좌표는 원본 정수 픽셀 경계로 검사한다. 같은 source에서 재생/탐색/Grab은 ROI를 유지하고 source 변경은 상태를 초기화한다. 서버 재검사 저장소는 그룹의 같은 frame_index 또는 Crop PNG SHA256을 거부한다.
- `vision_review_api.py`: 세션 권한과 Crop 소유권을 확인한 뒤 저장된 PNG bytes를 `validate_crop`으로 검사한다. `VisionReviewService`는 실제 SDK가 없고 LIVE를 false로 고정한다. UI는 검사/Capture/hash/group이 맞는 저장 결과만 표시한다.
- `docs/inspection-data-schema.md`에 신규 GET/POST 계약을 추가했다. 이번 복구 세션은 코드 테스트를 다시 실행하지 않았으며 이전 저장 결과만 확인했다.
- Chrome 점검은 사용자가 서버를 직접 실행한 뒤 MANUAL Pause → ROI 설정/적용 → Play/Pause, Seek, Frame Step 후 같은 ROI 좌표 확인 → 다른 프레임 Grab에서 기존 ROI Crop 확인 → 명시 Reset 확인 순서다. 녹화 영상은 프레임마다 제품이 ROI 내부인지 사용자가 확인해야 한다.
- Vision 패널은 접근 가능한 기존 Grab REINSPECT 이미지에서만 나타나며, 기본 LIVE 버튼이 disabled이고 모델 지원 UNKNOWN 안내인지 확인한다. Fake E2E의 결과는 테스트 전용이다. 새 세션에서 Crop 접근권이 없으면 실패 폐쇄가 정상이다. 실제 검사와 Vision 호출은 별도 승인 전 실행하지 않는다.
