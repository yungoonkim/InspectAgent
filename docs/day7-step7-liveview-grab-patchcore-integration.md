# Day7 Step7 — MANUAL LiveView Grab Crop → 기존 PatchCore 검사 → Heatmap

작성: 2026-10-18. **구현 및 격리 Mock 검증 COMPLETE / 실제 모델·사용자 Chrome 연결 검증 NOT TESTED.**

## A. 기존 구조 감사

- LiveView는 `floor(currentTime * fps)`를 프레임 범위로 clamp한다. ROI는 화면 좌표가 아니라 원본 영상 픽셀의 정수 좌표다.
- 기존 `/videos/{video_id}/grab`은 세션 소유의 **전체 프레임 PNG**를 CaptureStore에 저장한다. 공식 영상은 1920×480, 30FPS이다.
- ROI Grab의 기존 Crop은 **브라우저 canvas의 PNG data URL과 ImageData**뿐이었다. 서버에 Crop 파일이 존재하거나 capture_id가 Crop 자체를 가리킨다는 가정은 틀리다.
- 기존 `POST /inspections`는 등록 `image_id`만 받는다. capture_id를 image_id로 보내면 등록 검증을 통과하지 못한다.
- 기존 workflow는 요청별 ImageRegistry와 storage를 주입받을 수 있다. 모델 predict 결과의 score/map을 같은 1회 추론에서 사용하므로 이를 재사용했다.
- 기존 ImageView는 검사 이미지·Overlay를 같은 canvas draw rectangle에 표시하고 Pixel Inspector는 별도 원본 ImageData를 읽는다. 이 공간 계산을 변경하지 않았다.

확인: `frontend/src/components/LiveView.tsx:73`, `frontend/src/App.tsx:141`, `frontend/src/utils/imageCropper.ts:28`, `backend/capture_store.py:137`, `backend/inspection.py:296`, `backend/ml/patchcore_inferencer.py:159`.

최우선 AUTO/MANUAL 문서의 과거 미구현 표시는 현재 코드와 다르다. 기능 방향은 그대로 따르되 실제 구현을 기준으로 조사했다. AUTO 제어 및 PostgreSQL ROI 설정은 이번 입력 경로와 연결하지 않았다.

## B. 구현 연결 경로

```text
MANUAL Pause / ROI 조정 / Grab
  → 기존 브라우저 Crop 미리보기
  → 사용자가 [Grab 이미지 검사] 클릭
  → POST /captures/{capture_id}/inspect
  → Origin + 세션 + CSRF + Capture TTL/소유권/PNG 무결성 검증
  → 원본 전체 프레임의 동일 정수 ROI를 서버에서 재추출
  → 새 불변 IMG-GRAB-UUID.png 및 비공개 소유권 manifest 저장
  → 요청 전용 ImageRegistry (전역 등록 목록에는 추가하지 않음)
  → 기존 execute_inspection_workflow + 기존 inferencer.predict 1회
  → 기존 Decision Layer / JSONL 저장 / Sidecar 저장
  → INSP-ID와 Capture/ROI provenance 반환
  → ImageView가 서버에 보존된 실제 검사 입력 PNG를 로드
  → 그 이미지와 일치하는 Heatmap만 표시
```

브라우저 Crop 파일을 업로드하거나 클라이언트가 파일 경로를 지정하는 방식이 아니다. 서버의 동결 Capture PNG를 입력 근거로 삼는다. 따라서 브라우저 영상 표시 프레임과 서버 프레임의 완벽한 동기화를 새로 입증했다고 주장하지 않는다.

신규 API:

- `POST /captures/{capture_id}/inspect`: 201, 기존 InspectionResponse 형태. body는 `product_id`, `source_revision`, `roi`만 허용.
- `GET /inspections/{inspection_id}/input-image`: 세션 소유권을 확인한 검사 Crop PNG, `no-store`.
- 기존 map metadata/overlay GET에도 **Grab 입력인 경우만** 소유권 검증 추가. Overlay는 Grab일 때 `no-store`. 정적 이미지의 기존 접근 계약은 유지.

요청 계약 예시 — ROI 수치는 실제 승인 위치가 아니라 형식 예시:

```json
{
  "product_id": "ABCD1541",
  "source_revision": "<capture.source_revision>",
  "roi": {"x": 17, "y": 21, "width": 160, "height": 96}
}
```

승인된 동작의 입력 검증: bool/float/음수/0 크기/추가 필드 거부, 원본 경계 및 revision 검증, PNG uint8 3채널 검증. ID·파일 누락/다른 소유자는 404, 세션/CSRF/Origin 오류는 401/403, revision 및 실행 중 충돌은 409, 부적합 형식은 415, 부적합 이미지/ROI는 422, 모델/공간 계약/저장 가용성 문제는 안전한 503이다. 내부 경로와 예외 원문을 오류 응답에 넣지 않는다.

ROI 최소 16×16은 현재 로컬 MVP의 입력 방어 정책이지 산업 표준이나 병 전체 포함·성능 승인 기준이 아니다. 제품 ID는 기존 이미지 검사 경로와 같이 중립 문자열로 다루며 PostgreSQL 제품/ROI 자원을 새로 생성하지 않는다.

## C. 변경 파일 및 이유

| 파일 | 책임 |
|---|---|
| backend/grab_inspection.py | 새 입력 스키마, Capture 검증, 서버 Crop, 소유권/용량/중복 보호, 기존 workflow 어댑터 |
| backend/main.py | 신규 검사/입력 PNG API, Grab map의 소유권 검증 연결 |
| frontend/src/components/GrabInspectionPanel.tsx | MANUAL 전용 검사 버튼·로딩·Capture/ROI·결과·한계 문구 |
| frontend/src/utils/grabInspectionState.ts | Crop 식별 및 응답 출처 일치 검증 |
| frontend/src/api/inspection.ts | 세션/CSRF 포함 검사 요청, 전용 입력 이미지 URL |
| frontend/src/types/inspection.ts | UI provenance에 LIVEVIEW_GRAB 추가 |
| frontend/src/App.tsx | Capture/ROI/정적 선택 간 요청 세대 분리, 이전 결과 초기화, 새 프레임에서 이전 Crop 제거 |
| frontend/src/components/InspectionPanel.tsx | 늦게 도착한 정적 검사/조회 응답도 같은 선택 세대로 검증 |
| frontend/src/components/ImageView.tsx | Grab 검사 이미지의 비공개 URL/credential 및 출처 표시. Zoom/Pan 계산 불변 |
| frontend/src/utils/step4ImageState.ts | IMG-GRAB Overlay의 credential 포함. 기존 취소/ID/크기 검증 재사용 |
| tests/test_grab_inspection.py | 신규 35개 합성 PNG / MOCK TEST 통합 테스트 |
| frontend/scripts/test_grab_inspection.mjs | 출처/ROI 일치 등 Node 단위 테스트 3개 |
| frontend/scripts/grab_browser_cases.mjs | 신규 Mock Chrome 검증 8개 |
| frontend/scripts/test_step4_browser.mjs | 기존 격리 브라우저 실행기에 --grab 추가 |
| scripts/safe_regression_backend.py | 신규 모듈 추가, Capture/검사 Crop 디렉터리도 보호 지문에 포함 |
| scripts/run_safe_regression.ps1 | 기존 그룹 유지, 새 Node/Chrome 그룹 및 미실행 SKIP 표시 |
| 본 문서 | 계약·검증·위험·다음 승인 계획 |

기존 `backend/inspection.py`, CaptureStore, VideoFileSource, inferencer, Decision Layer, Sidecar 저장소 구현, Agent 코드, PostgreSQL schema는 수정하지 않았다. 기존 다른 Agent 변경/PPT 삭제·이동 상태를 복원하거나 덮어쓰지 않았다.

## D. Capture / Inspection 매핑 및 수명

ID는 혼용하지 않는다: 기존 `CAP-UUID` → 서버 생성 `IMG-GRAB-UUID` → 기존 생성기의 `INSP-...`.

기존 InspectionRecord의 자유형 `metrics` 안에 다음을 추가한다. **기존 JSONL top-level schema 변경·이전·rewrite 없음.**

- `input_source = LIVEVIEW_GRAB`
- `input_provenance`: capture_id, video_id, frame_index, source_revision, CFR timestamp, 원본 크기, ROI 스냅샷, Crop 크기, Capture PNG/Crop PNG SHA256, 모델 입력 크기, 전처리 식별, 한계 문구
- `anomaly_map_available`: 저장된 map의 image_id/원본 크기 정합성까지 확인한 가용성

실제 inspection_id는 원래 record의 ID이며 Sidecar도 같은 ID/image_id를 사용한다. 세션 보안정보는 검사 metrics에 저장하지 않는다. 소유권 hash는 비공개 manifest에만 보존한다. 전역 ImageRegistry나 공개 이미지 목록으로 Crop을 노출하지 않는다.

검사 입력은 `OUTPUT_DIR/grab_inspection_inputs/IMG-GRAB-UUID.png`에 원본 Crop 크기로 불변 저장한다. 원본 Capture PNG는 수정하지 않는다. Capture bytes를 먼저 확보하므로 검사 중 기존 TTL 정리가 발생해도 모델 입력이 사라지지 않는다.

Capture의 기존 TTL 30분과 세션 60분은 유지한다. 검사 입력 PNG·기록은 Capture TTL 후에도 남지만 **이미지/Heatmap 접근에는 소유 세션이 필요**하다. 앱 재시작/세션 만료 후 이전 Capture 소유권을 새 세션에 임의 승계하지 않으므로 과거 Grab 입력 이미지는 404가 될 수 있다. 장기 다중 사용자 이미지 이력은 별도 인증/보존 정책이 필요하다.

신규 입력은 기본 128개·PNG 합계 256MiB 상한으로 제한한다. 자동 영구 삭제는 추가하지 않았다. 저장이 애매하게 실패하면 근거 파일을 임의 삭제하지 않고 해당 실행 키를 재실행 불가 상태로 유지한다. 기존 JSONL·Sidecar·입력 파일을 아우르는 DB transaction을 구현했다고 주장하지 않는다. 저장 장애의 운영 복구/보존 관리 및 다중 replica는 후속 범위다.

## E. Crop / 모델 입력 해상도

1. 공식 Grab 원본: 1920×480 PNG, uint8 BGR(OpenCV)/RGB(웹).
2. 서버 Crop: `frame[y:y+height, x:x+width]`, 원본 픽셀 정수 half-open 범위, 크기 W×H. 클라이언트 미리보기와 같은 영역이다.
3. **inferencer.predict에 전달하는 ndarray는 W×H BGR 원본 Crop**이다.
4. 기존 `_prepare_image`가 BGR→RGB→PIL Resize(256×256)→float32 Tensor/scale→외부 Normalize를 수행한다.
5. 기존 모델 내부 전처리도 유지한다. 기존 감사에서 확인된 이중 Normalize 문제는 제거하지 않는다.
6. 반환 map은 256×256이어야 하며 score/map이 유한하지 않으면 정상 검사로 통과시키지 않는다.

실제 로드된 모델에서 CPU인지, 외부 transform/내부 export_transform에 허용된 Resize/채널 변환/Normalize 외의 공간 연산이 없는지 요청 시 확인한다. 알 수 없는 transform, 다른 Resize, Crop/Pad/Flip 등은 **추론 전에 503 GRAB_SPATIAL_TRANSFORM_UNVERIFIED**로 차단한다. 실제 모델 객체에 대한 이 Gate 통과 여부는 이번에 실행하지 않았다.

## F. Anomaly Map 공간 정렬

Crop의 원점은 (0,0)이다. 원본 프레임 위치는 provenance의 ROI offset으로만 보존한다. Overlay에 ROI offset을 다시 적용하지 않는다.

기존 Sidecar의 축별 변환은 map pixel center i에 대해 `(i + 0.5) * crop_size / map_size - 0.5`다. 서버가 map을 **Crop W×H**로 INTER_LINEAR 변환해 RGBA PNG를 생성한다. 1920×480이나 900×900, CSS 600×600으로 임의 맞춤하지 않는다.

ImageView는 서버 Crop PNG와 Overlay를 같은 원본 크기 검증 후 동일 origin/zoom/pan rectangle에 그린다. 600×600은 작업 viewport일 뿐이다. RGB/GV는 Overlay 합성 전 원본 Crop의 ImageData에서 읽는다. 기존 request cancellation/inspection_id/image_id/dimension 검증도 그대로 적용한다.

검증 근거:

- 비정사각 160×96 Crop이 서버에서 원본 ROI와 byte-equivalent 화소인지 확인.
- 비대칭 256×256 가로/세로 marker map을 기존 Sidecar에 저장하고 Overlay 색상·160×96 크기를 독립 OpenCV 변환과 비교.
- Chrome에서 동일 Crop/Overlay draw rectangle, Zoom, 실제 포인터 Pan, 원본 RGB/GV 불변을 확인.
- 검사 후 ImageView는 실제 검사한 **서버 PNG**를 자동 로드하며 `LIVEVIEW GRAB CROP`으로 표시한다.

이 근거는 좌표/표시 계약 검증이며 실제 PatchCore가 병의 결함 위치를 정확히 찾았다는 성능 검증은 아니다.

## G. 기존 서버 판정 보존

기존 workflow와 `determine_final_verdict`를 그대로 사용한다. threshold=34.1442, 품질 경고 우선순위, OK/NG/UNKNOWN 및 최종 OK/NG/REINSPECT/ERROR를 변경하지 않았다.

예를 들어 모델 예외는 기존 정책에서 `result=UNKNOWN`, `defect_detection_status=FAILED`, 최종 `REINSPECT/DEFECT_DETECTION_UNAVAILABLE`로 기록된다. 이를 임의 NG 또는 OK로 바꾸지 않는다. 이번 테스트에서 처음 ERROR를 기대했던 신규 assertion은 실제 기존 정책에 맞춰 수정했다. 파이프라인 FAILED 자체와 모델 가용성 실패를 구분한다.

Map 저장 실패는 판정을 임의 변경하지 않으며 `anomaly_map_available=false` 및 ImageView의 MAP_NOT_AVAILABLE로 구분한다. 검사 버튼 완료 메시지도 Heatmap 미생성을 표시한다. 신규/기존 Sidecar를 덮어쓰는 fallback은 없다.

## H. 모델/Calibration/Normalize 위험

UI에 아래 문구를 그대로 표시한다.

> LiveView Grab 기반 검사는 기존 PatchCore 모델을 이용한 실험적 검사입니다. 영상 Crop에 대한 임계값 보정 및 검출 성능은 별도로 검증되지 않았습니다.

영상 합성·압축·병 크기·배경·잘림·비정사각 Crop의 256×256 변형과 기존 정적 학습 분포 차이는 남아 있다. 경계 내 ROI라고 병 전체 포함을 보장하지 않는다. 사람이 ImageView에서 입력을 확인해야 한다.

이중 Normalize는 **UNRESOLVED**. Calibration 29장 재실행, threshold 적합성, 실제 Grab score/정적 이미지 평가 수치/검출 성능은 이번에 검증하지 않았다. CPU/공간 Gate가 통과해도 모델 성능이 검증되는 것은 아니다. 실제 공장 품질 보증 또는 공식 영상 ROI calibration 완료라고 발표하면 안 된다.

Gemini Live도 별도 미해결 사항이며 이번에 호출하거나 수정하지 않았다. 새 Grab 입력의 Agent 분석은 UI에서 연결하지 않고 기존 정적 이미지 Agent 경로만 유지한다.

## I. Fake Inferencer 통합 테스트

신규 **35 PASS / 0 FAIL / 0 SKIP**, 2.63초. 전부 합성 PNG와 `MOCK_TEST_ONLY` 결과다.

- 소유 Capture 조회, 엄격한 ROI/형식/revision/경계/권한/CSRF/Origin/TTL 검증.
- 실제 Crop ndarray가 기존 workflow→주입 inferencer로 정확히 한 번 전달됨.
- 서로 다른 Capture의 pixel/ID/출처 분리, 반복 요청의 같은 inspection_id 재사용, 실행 중 요청 거부.
- 서버 Crop PNG/metadata/JSONL/Sidecar 정합성, 원본 Capture 불변, 비정사각 map 공간 검증.
- 다른 세션의 입력 PNG/map metadata/Overlay 접근 차단, Capture TTL 후 입력 유지, 세션 만료 후 fail closed.
- NG/threshold 경계/NaN/모델 예외/모델 미가용/저장 오류/Map 저장 오류/CPU·공간 Gate 확인.

새 PNG/manifest는 exclusive 생성하며 partial 입력 파일 저장 오류는 이번 요청이 만든 파일만 정리한다. 모델 실행 후 JSONL 저장 결과가 불명확한 경우 자동 재추론하지 않는다.

## J. 기존 안전 회귀 결과

실행:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_safe_regression.ps1
```

| 그룹 | PASS | FAIL | SKIP |
|---|---:|---:|---:|
| Backend 선택 회귀 | 475 | 0 | 10 |
| Frontend Node | 29 | 0 | 0 |
| 기존 ImageView Chrome Mock | 12 | 0 | 0 |
| 기존 Agent Chrome Mock | 8 | 0 | 0 |
| 신규 Grab Chrome Mock | 8 | 0 | 0 |

TypeScript/Build/Lint 모두 성공. 기존 lint 경고 **6건 유지**, pytest bootstrap 경고 anyio assert-rewrite 1건. 신규 ref lint 경고는 useLayoutEffect 기반 source 갱신으로 제거했다.

최종 증거: `data/outputs/safe-regression/20261018-201222-23d27f19/`의 summary.json/backend.xml/safety.json/protection.json 및 세 browser 결과. Backend 14.31초. 설치된 Chrome/155.0.8059.82, 새 임시 프로필 사용. 사용자의 기존 브라우저/서버를 강제 종료하지 않았다.

10 SKIP은 기존 Windows symlink 1, 실제 checkpoint 실행 제외 6, 격리 저장소 빈 조회 1, 실제 데이터셋 workflow 제외 2다. 전체 pytest를 실행하거나 PostgreSQL 테스트를 활성화한 것이 아니다.

초기 신규 테스트 실패는 storage 생성자가 빈 JSONL을 미리 만드는 계약 및 모델 실패 시 기존 REINSPECT 정책을 테스트에서 잘못 가정한 것이었다. 실제 코드 확인 후 파일 미존재 대신 빈 내용, 판정은 기존 정책으로 검증했다. assertion 삭제/skip이나 운영 판정 변경으로 숨기지 않았다.

## K. 운영 데이터 보호

작업 시작 기준선 `data/outputs/safe-regression/step7-before/protected-before.json`의 기존 **32개 운영 자산 SHA256 모두 동일**. Agent 소스 6개도 이전 Live 시점 지문과 동일하다.

회귀 러너 보호 대상에 **기존 Capture marker**까지 추가하여 이제 **33개**다. 32→33은 보호 범위 확대이지 새 운영 검사/이미지 생성이 아니다. 최종 runner 전후 33개도 동일하다.

실 운영 `grab_inspection_inputs` 디렉터리는 생성되지 않았고 운영 Capture PNG도 0개였다. 모든 신규 검사 기록/입력/Sidecar는 고유 테스트 디렉터리에만 생성됐다. 운영 JSONL·기존 보고서·모델·영상·Sidecar 수정 없음. PostgreSQL 접속/변경, 데이터셋/평가 Ground Truth 접근, Git add/commit/push/reset/restore/clean은 모두 0건이다.

기존 개발 watcher가 소스 변경을 자동 반영할 수 있지만 별도 서버 종료/재시작 명령은 실행하지 않았다. 기존 CaptureStore의 재시작 시 폐기/TTL 정책은 변경하지 않았다.

## L. 실제 Gemini API 호출

**이번 단계 0회.** Fake SDK 및 브라우저 Mock transport만 사용했다. 이전 실제 Gemini 실패를 이번 성공으로 바꾸어 표현하지 않는다.

## M. 실제 PatchCore 추론

**이번 단계 0회.** 안전 harness에서 실제 predict/모델 로드를 차단했으며 최종 safety.json의 실제 prediction/load/network/금지 I/O 카운터는 모두 0이다. 운영 검사 API를 실제로 호출하지 않았다. 기존 서버의 startup preload와 실제 모델 forward는 구분한다.

## N. 사용자 Chrome 및 실제 모델 1회 검증 계획 — 아직 미실행

다음은 **별도 명시적 승인 후** 수행한다. 승인에는 새 Capture PNG·검사 입력 PNG·JSONL append·새 Sidecar 생성 허용, 실제 CPU predict 최대 1회가 포함되어야 한다. Gemini는 계속 0회다.

1. 실제 검증 중 소스 수정/서버 재시작을 하지 않는다. 이전 Capture는 서버 reload 후 무효일 수 있으므로 새로 Grab한다.
2. Chrome MANUAL에서 영상 Pause→ROI 선택/Move/Resize→Grab. 완전한 병 포함 여부를 사람이 확인한다. Crop 치수·Capture ID·frame_index·revision·ROI를 기록한다. AUTO는 실행하지 않는다.
3. 검사 전 기존 JSONL/모델/Sidecar hash를 보관한다. 이 단계의 새 입력/검사 ID는 서버가 발급하므로 특정 ID를 미리 가정하지 않는다.
4. [Grab 이미지 검사]를 **한 번만** 누른다. 요청은 `POST /captures/<방금 생성된 CAP-ID>/inspect`, JSON은 현재 product_id/revision/원본 ROI, credential cookie와 X-Capture-CSRF 포함이다. 임의 경로·이미지 업로드·Gemini 요청은 없다.
5. CPU/공간 Gate가 거부하면 실제 추론을 강행하지 않는다. 설정/모델을 자동 수정하거나 재시도하지 않는다. 네트워크/저장 오류로 결과가 불명확해도 자동 재클릭하지 않는다.
6. 응답의 INSP-ID, `input_source=LIVEVIEW_GRAB`, Capture/ROI 스냅샷, source/crop/model 해상도, finite score/34.1442/서버 verdict, 실제 model_version 및 `anomaly_map_available` 확인.
7. 해당 세션의 서버 input-image PNG가 Crop과 일치하는지, map/overlay가 같은 INSP/image_id/W×H인지 확인. Heatmap ON/OFF·투명도·100/200/4000%·Pan에서 RGB/GV 불변 및 좌표 정합성을 확인한다.
8. 다른 Capture/정적 이미지로 바꾸면 이전 결과/Heatmap이 사라지는지 확인한다. 추가 모델 검사는 하지 않는다.
9. 기존 운영 파일은 수정되지 않고 승인된 새 입력/검사 append/Sidecar만 생성됐는지 비교한다. 정상 모델 실행·파일 저장·시각 정합성 확인과 모델 검출 성능 검증은 별개로 보고한다.

서버 검사 응답이 있어도 map 또는 입력 파일 저장/정합성이 불완전하면 실제 통합 검증은 PARTIAL이다. score가 낮거나 final_result가 OK라는 이유로 영상 Crop의 정상 제품 여부를 입증했다고 하지 않는다.

## O. 완료 상태

**COMPLETE — 연결 구현·Fake 통합·안전 회귀 범위.** 실제 모델/사용자 Chrome 검증 및 영상 Crop calibration은 NOT TESTED다. 이번 결과를 실제 PatchCore 성능 검증 또는 Normalize 문제 해결로 해석하지 않는다.

다음 실제 모델 실행·새로운 기능·AUTO·Gemini 작업은 수행하지 않고 사용자 승인을 기다린다.
