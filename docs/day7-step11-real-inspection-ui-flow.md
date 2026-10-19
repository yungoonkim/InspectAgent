# Step 11 — 실제 Crop 검사·로그·새 AI 보고서·UI 연결

## 판정

**코드 연결 및 오프라인 검증 COMPLETE. 실제 PatchCore/Google 신규 E2E는 NOT TESTED, 별도 승인 대기.**
Google 성공 또는 결함 검출 정확도 개선을 확인한 단계는 아니다. OpenCV와 전체 러너/CDP 복구는 보류했다.

## 기존에 실제 구현되어 있던 경로

`Capture ID → owner/CSRF/revision 검증 → 서버 원본 프레임의 ROI crop → 원본 PNG 배타 저장 → 기존 검사 서비스 → 품질 평가·PatchCore predict 1회 → 같은 반환값의 score/map → 기존 Decision → 검사/이벤트 JSONL → Sidecar → UI`

- `backend/grab_inspection.py:132`: owner와 영속 Crop manifest/hash 확인.
- `backend/grab_inspection.py:158`: 원본 BGR frame의 반열린 ROI Crop. UI padding 이미지를 모델/품질 분석에 넣지 않는다.
- `backend/grab_inspection.py:224`: capture/video/frame/ROI, Crop SHA256·크기, 모델 입력 256×256 기록.
- `backend/inspection.py:514`: 전달받은 실제 이미지로 inferencer.predict. 저장 조회와 별도다.
- `backend/inspection.py:538`: 동일 predict의 anomaly_map 저장. `backend/inspection.py:571`: threshold 비교.
- `backend/inspection.py:582`: 기존 서버 Decision. `backend/inspection.py:662`: 검사 저장 후 이벤트 로그 저장.
- Map은 256×256 모델 좌표에서 Crop 원래 해상도에 대응한다. 기존 RGB/GV·ImageView Zoom/Pan/Heatmap 변환 코드는 수정하지 않았다.

INSP-001652는 **기존 사용자 실측 기록**이다. Crop 284×272, GV 59.76 < 125.0이며 모델 NG(40.1631 > 34.1442)여도 품질 경고 우선으로 REINSPECT가 된다. 이번에 재추론하지 않았고, 검은 화면 padding이 들어간 것이라고 단정하지 않는다. 병·배경의 원본 픽셀은 품질 통계에 포함된다. 품질 정책과 Normalize/Calibration은 변경하지 않았다.

검사 JSONL·로그·Map 세 종류를 묶는 분산 트랜잭션은 기존에 없다. Map 저장 실패 시 unavailable, 로그 저장 실패 시 불완전 산출물 가능성은 남는다. 정상 경로의 Fake 검증이 저장소 장애의 원자적 전체 롤백을 입증하지 않는다. 이 작업에서 운영 저장 스키마를 바꾸지 않았다.

## 수정한 실제 연결 문제

### 1. Grab 검사 대상이 Diagnostic UI에서 제외되던 문제

`frontend/src/App.tsx`는 Grab이면 AgentPanel에 null을 주고 과거 fixture ID를 기본값으로 사용했다.
이제 정적/Grab 모두 **현재 선택된 동일 inspection_id**를 전달한다. 선택 초기화 때 과거 기본 보고서를 자동으로 가져오지 않는다.
부모가 지정한 대상 ID는 readOnly이며 다른 패널과 혼입하지 않는다. 저장 조회와 신규 POST는 명시적으로 분리한다.

### 2. 신규 Agent 보고서 저장 실패/덮어쓰기

기존 POST의 `open(..., 'w')`와 `except: pass`는 저장 실패에도 200을 줄 수 있었다.
`backend/agent/report_store.py:21`에 별도 보고서 저장 경계를 추가했다.

- `OUTPUT_DIR/agent_reports/{inspection_id}.json`으로 GET/POST 저장 경로를 통일한다.
- 기존 파일이 있으면 Provider 전 **409 AGENT_REPORT_EXISTS**. 기존 기록은 덮어쓰지 않는다.
- 검증된 JSON을 새 임시 파일에 쓰고 fsync 후 hard link로 완성본을 배타적으로 공개한다. 파일시스템이 지원하지 않으면 fail-closed다.
- 저장 실패는 **503 AGENT_REPORT_STORAGE_FAILED**, 완료로 숨기지 않는다.
- GET은 읽기만 한다. 잘못된 ID, 손상 JSON, 다른 inspection_id 파일을 안전하게 거부하고 내부 경로를 노출하지 않는다.
- 실제 런타임은 LIVE_AGENT_ANALYSIS, 주입 Fake는 FAKE_TEST를 기록한다. 기존 RECORDED_TEST_FIXTURE는 유지한다.
- 모델/Generation Config/Function Calling 4개 도구·Fact/Pointer 검증·동시성 Lock은 그대로다.

이는 로컬 NTFS 파일 발행 방식이며 Cloud Run의 영구 저장 보장을 추가한 것은 아니다. 파일 fsync와 원자적 공개를 전원 손실까지 포함한 모든 플랫폼의 저장 보증으로 주장하지 않는다.

### 3. 같은 Crop의 독립 Vision 분석

새 Vision 어댑터·API scope·결과 저장은 [별도 보고서](day7-step11-gemini-vision-live-integration.md)에 설명했다.
UI에는 신규 요청과 저장 의견 조회, LIVE/FAKE_TEST를 나눠 표시한다. 저장 LIVE를 읽는 것은 신규 유료 분석이 아니다.
실제 전송이 비활성일 때도 과거 유효 결과는 조회할 수 있다. 기본 상태에는 외부 전송 버튼이 비활성이다.
같은 Crop Vision 분석은 새 inspection_id·Capture·PatchCore 실행·재검사 횟수를 만들지 않는다.

## 테스트 근거와 재실행 명령

최종 집중 Backend **300 PASS / 0 FAIL / 0 SKIP** = 핵심 289 + 별도 저장 보고서 회귀 11. 최종 작은 저장 예외 처리 변경 후 중복 5건, 실제 SDK 타입/Fake 출처 강화 후 중복 106건도 다시 통과했다.
Frontend **41 PASS**, TypeScript/Build/Lint 성공, lint 기존 경고 6개. Chrome 자동화와 전체 안전 러너는 **미실행**이다.
신규 테스트는 `tests/test_step11_core_connection.py`, `tests/test_step11_vision_transport.py`다. 기존 API/Fake/GET 테스트의 임시 저장소와 덮어쓰기 기대값만 관련 범위에서 보완했다. 운영 fixture를 테스트에 복사하지 않았다.

```powershell
conda activate vision-insight
python scripts/safe_regression_backend.py backend --output data/outputs/safe-regression/step11-NEW-UNIQUE tests/test_step11_vision_transport.py tests/test_step11_core_connection.py tests/test_agent_api.py tests/test_day7_step5_agent_e2e.py tests/test_day7_step6b_runtime_safety.py tests/test_vision_review.py tests/test_grab_inspection.py tests/test_reinspection_workflow.py tests/test_agent_day7_error_observability.py tests/test_inspections.py::test_get_stored_agent_report
node --test frontend/scripts/test_image_transform.mjs frontend/test_f31_units.js frontend/scripts/test_step4_regression.mjs frontend/scripts/test_agent_analysis_state.mjs frontend/scripts/test_grab_inspection.mjs frontend/scripts/test_reinspection_state.mjs frontend/scripts/test_roi_vision_state.mjs
cd frontend
npm run build
npm run lint
```

출력 폴더는 매번 새 이름을 사용한다. 위 Python 명령은 snapshot/full runner가 아니라 선택된 파일만 실행하는 격리 harness다. network·운영 쓰기·실모델 차단은 유지한다. 이 문서에 재개 명령을 기록했으며 서버는 실행하지 않았다.

## 보호 데이터

###  변경 파일과 이유

| 파일 묶음 | 변경 이유 |
|---|---|
| `backend/agent/report_store.py`(신규), `backend/agent/api.py`, `backend/agent/schemas.py`, `backend/main.py` | 동일 저장 경계, 배타 발행, 안전한 GET/실패 응답, Fake/LIVE 출처 |
| `backend/vision_transport.py`(신규), `backend/vision_review.py`, `backend/vision_review_api.py` | default-disabled 단일 Crop 승인 및 실제 SDK 전송 경계, 결과 계측 |
| `frontend/src/App.tsx`, `frontend/src/components/AgentPanel.tsx`, `frontend/src/components/VisionReviewPanel.tsx` | 같은 검사 ID 연결, 과거 기본 fixture 제거, 분석 동의·독립 패널 |
| `frontend/src/types/agent.ts`, `frontend/src/types/visionReview.ts`, `frontend/src/utils/agentAnalysisState.ts`, `frontend/src/utils/visionReviewState.ts` | Fake 출처/오류/전송 계측 타입과 요청 가능 조건 |
| `tests/test_step11_core_connection.py`, `tests/test_step11_vision_transport.py`(신규) | Crop·Map·로그·신규 보고서·Vision 연결 및 설치 SDK의 Mock HTTP 검증 |
| `tests/test_agent_api.py`, `tests/test_day7_step5_agent_e2e.py`, `tests/test_day7_step6b_runtime_safety.py` | 임시 보고서 경로, 기존 파일 보존 계약, Fake provenance 회귀 |
| `tests/test_vision_review.py`, `tests/test_agent_day7_error_observability.py`, `tests/test_inspections.py` | 모델 문서 지원 상태, 저장 LIVE 조회, 운영 보고서에 의존하지 않는 GET fixture |
| `frontend/scripts/test_agent_analysis_state.mjs`, `frontend/scripts/test_roi_vision_state.mjs` | 저장 실패·기존 보고서 오류와 Vision 요청/동의 조건 단위 검증 |
| `docs/inspection-data-schema.md` 및 Step 11 신규 문서 3개 | 최신 API/승인/검증/보류 계약 |

기존 untracked OpenCV 초안·Step 10 문서·Gemini 별도 발표 문서는 수정하지 않았다. 다른 에이전트가 추가한 `docs/gemini-day7-real-e2e-execution-checklist.md`도 그대로 보존했다.

### 무결성 근거

`data/outputs/step11-core-offline/protection-before.json`과 모든 테스트 종료 후의 `protection-final.json`: **85개 파일의 SHA256 및 파일 집합 불변**, 추가·누락 0개. 최종 확인 시에도 backend/reload 프로세스와 포트 8000 listener가 없었다.
범위는 검사/실행 JSONL, Capture/Crop/Map/기존 보고서/재검사·Vision 상태, 모델 폴더, Decision/Inferencer다. 백업 폴더에는 쓰기 작업을 하지 않았다. PostgreSQL은 접속하지 않았다.
최초 비교 명령의 PowerShell JSON 배열 처리 오류 산출물 `protection-invalid-array-attempt.json`은 **무효**다. files=85를 강제한 `protection-verified.json`과 최종 `protection-final.json`만 근거로 사용한다.
운영 보고서/Vision 결과를 새로 만들지 않았고 테스트 결과는 고유 run 디렉터리에만 생성했다. .env와 평가 정답은 열지 않았다.

## 사용자 Chrome 검증 순서 — 별도 승인 후

1. 사용자가 필요할 때 서버를 직접 실행한다. `--reload` 없이 단일 로컬 worker를 권장한다. 예: `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`. 시작 시 기존 정책에 따라 모델 preload가 발생할 수 있다.
2. 서버 재시작 전 Capture 세션은 복구되지 않는다. 백업 PNG를 운영 세션으로 임의 재등록하지 않는다. 새 세션에서 새 프레임/ROI로 Grab한다.
3. **실제 검사를 별도로 승인한 뒤에만** Grab 이미지 검사 버튼을 1회 눌러 새 inspection_id, Capture/ROI, score/품질/final_result, Heatmap을 확인한다.
4. 그 ID가 Agent 대상에도 같게 표시되는지 확인한다. 기존 보고서 조회 404는 신규 진단 실패가 아니라 아직 보고서가 없다는 의미다.
5. **Diagnostic 유료 분석을 별도 승인한 뒤에만** 새 AI 진단 버튼을 누른다. success뿐 아니라 새 analysis_id·도구/Evidence와 실제 JSON 저장을 확인한다. 기존 보고서가 있으면 재분석이 차단돼야 한다.
6. REINSPECT이면 같은 ID/PNG SHA의 Vision 패널을 확인한다. 이번 상태에서는 DISABLED가 정상이다. Vision 한 장 외부 전송은 모델·해시·비용·1회 상한에 대해 별도 승인을 받아야 한다.
7. 이미지 전환 시 과거 결과/Heatmap/AI 응답이 새 이미지로 붙지 않아야 한다. 저장 조회만으로 검사/분석 실행 성공을 주장하지 않는다.

## 남은 한계

- Diagnostic 과거 502 근본 원인 및 기존 SDK 내부 HTTP 재요청 위험은 이 변경으로 해결됐다고 선언하지 않는다. 신규 Live 실행은 별도 승인·상한 확인이 필요하다.
- Argon 계정 접근·실제 응답 지연·관측 의견 신뢰도 미검증. Vision Mock 전송 성공은 Google 실제 응답 성공이 아니다.
- Capture owner 세션이 만료/재시작되면 과거 파일이 영속이어도 보호된 Crop/Map/Vision 조회는 거부될 수 있다. 인증/owner 복구를 우회하지 않았다.
- PatchCore 정규화·영상 Crop calibration·실제 결함 Recall은 여전히 별도 문제다. UI 연결이나 Fake 성공으로 제조 품질 보증을 주장하지 않는다.
