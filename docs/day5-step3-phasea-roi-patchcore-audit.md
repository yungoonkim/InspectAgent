# Day5 Step 3 Phase A — 저장·수동 ROI와 PatchCore 연결 감사

## 1. 판정·범위·문서 우선순위

- 감사일: 2026-10-17. **Phase A: COMPLETE — 코드 감사 및 Phase B 설계 완료. 구현 완료가 아니다.**
- 최우선 기준: `docs/visioninsight-auto-manual-inspection-spec.md:18`, `:115`, `:160`, `:226`. 가장 먼저 읽었다. AUTO는 사전 저장·승인 ROI, MANUAL은 ImageView 지정 ROI를 사용하며 동일 검사 엔진을 재사용한다.
- 상태 표기: **CONFIRMED**는 읽은 코드·기록 또는 이번 메모리 영상 관찰, **DESIGN PROPOSAL**은 미구현 제안, **NOT TESTED**는 실제 실행 검증하지 않은 사항, **BLOCKED**는 선행 승인 없이는 진행할 수 없는 범위다.
- 운영 소스·테스트 수정, API 호출, 새 Grab/검사/ROI 이미지 저장, PatchCore 로딩·추론, Gemini 호출, pytest 실행은 하지 않았다. 신규 산출물은 이 문서 하나다.
- 이전 전체 회귀 **1268 PASS / 0 FAIL / 4 SKIP / 경고 2건 / 31.86초**는 `docs/day5-step2-phaseb-video-grab-implementation.md:179`의 과거 실행이다. 이번에 측정한 pytest 결과가 아니다.

### 기록과 현재 코드의 차이 — CONFIRMED

최우선 설계 문서 `:66`과 `:73`에는 영상·Grab 미구현 및 1175 PASS가 남아 있다. 현재 `backend/video_source.py`, `backend/video_api.py`, `backend/capture_store.py` 및 Step 2 Phase B 보고서는 구현 완료와 1268 PASS를 기록한다. 설계 문서의 **사용자 확정 기능 요구사항은 유지**하되 이 상태 문구는 과거 스냅샷으로 구분한다. README의 1089 PASS와 `docs/patchcore-cpu-benchmark.md:40`의 209장 학습 설명도 현재 metadata의 180/29 분할과 구분해야 한다. 이번에 기존 문서를 갱신하지 않았다.

독립된 Step 2 Phase A 보고서 파일은 현재 docs 목록에서 확인하지 못했다. 현재 존재하는 최우선 설계 문서, Step 2 Phase B 문서, Step 2-A 세 보고서로 계약·이력을 대조했으며 존재하지 않는 문서를 인용하지 않는다. 최초 H.264 BLOCKED, mp4v PARTIAL, FFmpeg H.264 COMPLETE 이력은 그대로 보존한다.

## 2. 조사 방법과 근거 범위

프로젝트 루트는 `C:\Users\USER\AI-NativeAgent\Project\InspectAgent`다. AGENTS, Git 상태, 기존 변경·미추적 파일을 확인했다. 적용 범위의 추가 AGENTS는 발견하지 못했다. 다른 에이전트의 Agent 변경, 발표/PPT, 임시 회귀 디렉터리를 수정하지 않았다.

읽기 전용 명령은 `git status --short`, `rg`, `Get-Content`, `Get-FileHash` 및 아래 Python 환경의 메모리 디코딩이었다.

```text
C:/Users/USER/miniconda3/envs/vision-insight/python.exe -B -
```

위 stdin 코드는 cv2/NumPy·표준 라이브러리만 사용했다. backend 모듈, torch, 모델 또는 ImageRegistry를 초기화하지 않았다. 소스 파일을 읽는 것과 앱 lifespan/검사를 실행하는 것을 구분했다. Python 3.11.16, OpenCV 5.0.0, 설치 배포 metadata의 anomalib 2.7.0을 확인했다. 프로그램 설치·네트워크 접근은 없었다.

승인 H.264를 메모리에서 순차 디코딩해 240개 프레임과 EOF/release를 확인했다. 0/30/60/90/120/150/180/210/239의 축소 contact sheet만 메모리로 만들어 표본 시각 검토했다. 원본 프레임·ROI·캡처 파일을 생성하지 않았다. 전수 육안 검사, 결함 분류, 모델 성능 검사가 아니다.

## 3. 기존 PatchCore 입력·전처리·출력 — CONFIRMED

### 3.1 실제 입력 경로

| 계층 | 실제 계약과 근거 |
|---|---|
| HTTP | `backend/main.py:152`의 InspectionCreateRequest는 product_id와 image_id. `:441`의 create_inspection_endpoint가 workflow를 호출한다. |
| Registry | `backend/inspection.py:73`의 ImageRegistry. `:149`의 get_path가 Path 또는 None을 반환한다. 사용자 경로가 아닌 중립 ID를 사용한다. |
| 파일 로드 | `backend/inspection.py:404`의 기본 `cv2.imread(str(image_path))`. 통상 uint8 H×W×3 BGR로 디코딩한다. 기본 COLOR 로드는 grayscale도 3채널로 읽고 알파는 보존하지 않는다. 원본 depth/alpha를 검증·보존하는 별도 계약은 없다. |
| 품질 분석 | `backend/inspection.py:463` → `backend/vision.py:275` analyze_image. ROI 연결 전 현재는 로드한 전체 이미지가 대상이다. |
| 추론 | `backend/inspection.py:508`의 `inferencer.predict(image)`. 반환 dict에서 score/time/model_name을 읽는다. |
| 결과 | `backend/inspection.py:623` InspectionRecord 생성, `:640` 검사 저장, `:641` 로그 저장, `:643` `(record, logs)` 반환. |

원본 정적 이미지들의 실제 해상도 전수 분포는 **NOT TESTED**다. `tests/test_patchcore_inferencer.py:49`의 900×900은 합성 테스트 배열이지 모든 원본 이미지가 900×900이라는 증거가 아니다. 이번에 데이터셋 이미지·클래스 폴더를 열지 않았다.

### 3.2 wrapper의 확인된 전처리

`backend/ml/patchcore_inferencer.py:135`의 `_prepare_image()`:

1. str/Path: PIL open 후 RGB 변환.
2. 3채널 ndarray: **BGR → RGB**, PIL Image 생성.
3. 2차원 ndarray: **GRAY → RGB**. 4채널 ndarray 등 다른 shape는 ValueError.
4. PIL 입력: RGB 변환.
5. `:53`의 Resize((256, 256)) → ToImage → ToDtype(float32, scale=True) → ImageNet Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225]).
6. `:157`에서 배치 차원 추가, device로 전송. wrapper 출력은 `[1,3,256,256]`.

wrapper 자체에는 center crop, padding, 임의 회전, 배경 제거, grayscale 추론 전환이 없다. 비정사각형 ROI를 그대로 전달하면 256×256로 강제 변형된다. 입력 dtype을 uint8로 제한하는 명시적 guard는 이 wrapper에 없으므로 새 입력 어댑터가 uint8 BGR3/자원 상한을 검증해야 한다.

`predict()`는 `:159`에 정의되어 `:178`에서 `torch.no_grad()`로 **Lightning 모델 객체 전체**를 호출한다. score float, anomaly_map ndarray(문서상 float32 256×256), inference_time_ms, model_name/backbone dict를 반환한다. 내부 측정 시간은 `_prepare_image()` 이후의 모델 호출 구간이므로 PNG 처리·HTTP·저장·전체 전처리 시간과 같지 않다.

### 3.3 추가로 발견한 전처리 중복 위험 — DESIGN RISK / NOT TESTED

wrapper만 보고 “정규화가 딱 한 번”이라고 확정할 수 없다. 현재 설치된 소스를 읽으면 다음 경로가 추가로 존재한다.

- `%CONDA_PREFIX%/Lib/site-packages/anomalib/models/components/base/anomalib_module.py:246`의 forward는 `:270`에서 활성 pre_processor, 모델, post_processor를 호출한다.
- `anomalib/models/image/patchcore/lightning_model.py:182`의 configure_pre_processor는 기본 Resize256와 ImageNet Normalize를 구성한다(`:223`). CenterCrop은 인자가 있을 때만 추가한다.
- `anomalib/pre_processing/pre_processor.py:99`, `:151`은 export_transform을 구성·실행한다.
- `scripts/train_patchcore.py:122`의 모델 생성은 pre_processor=False를 명시하지 않는다. 설치된 base의 `:201`은 checkpoint의 component 설정을 복원할 수 있다.

따라서 **로드된 체크포인트의 실제 pre_processor/export_transform 활성 상태에 따라 중복 Resize/Normalize 가능성**이 있다. 체크포인트를 로딩·역직렬화하지 않았으므로 현재 실행 모델에서 실제 중복이 발생했다고 단정하지 않는다. 설치 라이브러리 수정도 하지 않았다.

**Phase B 권장 선행 점검:** 별도 승인된 모델 로딩 범위에서 실제 transform chain을 관찰하고 기존 경로와 ROI 경로의 동등성을 확인한다. 중복이 재현돼도 Step 3 구현과 함께 몰래 수정하지 않는다. 전처리 변경은 점수·기존 calibration 의미를 바꿀 수 있으므로 별도 재현 근거/승인이 필요하며 34.1442를 임의 재조정하지 않는다.

### 3.4 판정·오류·ID

`backend/inspection.py:305`에서 **로드 전에** inspection_id를 발급한다. 등록/로드 실패도 UNKNOWN·ERROR·SKIPPED의 실패 기록과 실제 실패 로그를 저장한 뒤 예외를 올린다(`:346`, `:387`, `:429`). Day1의 execute_inspection(`:194`)은 현재 HTTP의 전체 workflow와 다르다.

추론 예외는 `:530`에서 FAILED로 기록되며 raw result는 UNKNOWN을 유지한다. 현재 일반 inference 실패가 항상 final ERROR인 것은 아니다. `backend/decision.py:65`의 순서는 다음과 같다.

1. workflow status FAILED → ERROR.
2. 품질이 NORMAL이 아님 → REINSPECT.
3. 추론 미완료 또는 raw UNKNOWN → REINSPECT.
4. 나머지 정상 품질에서 raw NG/OK → NG/OK.

`backend/inspection.py:548`은 **score > threshold이면 NG**, 같거나 작으면 OK다. `backend/config.py:83` 기본 임계값 및 모델 metadata의 calibrated_threshold는 **34.1442**. inferencer=None이면 SKIPPED/UNKNOWN이며 이를 정상 제품으로 바꾸지 않는다. 이 우선순위와 모델·전처리는 Phase B에서도 그대로 사용한다.

## 4. 현재 capture_id·PNG·세션 계약 — CONFIRMED

- `backend/video_source.py:156` grab_frame: 요청별 독립 VideoCapture, 첫 프레임부터 지정 인덱스까지 순차 read. uint8/3채널/등록 해상도 검사. `:100` contextmanager가 release/동시 슬롯 반환.
- `backend/video_api.py:151` POST Grab: video_id/revision/index 검증 → 허용 Origin → 서버 세션 쿠키·CSRF → 추출 → CaptureStore.save. 실제 ROI/검사 호출은 없다.
- `backend/capture_store.py:143` save: 원본 크기 BGR 프레임을 PNG로 인코딩하고 임시 파일·fsync·os.replace로 저장. CAP-UUID와 세션 소유권을 연결한다. 검사 ID를 만들지 않는다.
- `backend/video_api.py:166`, `:176`: 메타데이터/PNG GET. 세션·TTL·파일 검사, PNG는 no-store. 공개 StaticFiles 경로가 아니다.
- `backend/capture_store.py:193`은 타 세션·만료·없는 파일을 404로 처리한다. `:213` image는 내부 저장 SHA256을 확인하고 **bytes**를 반환한다.
- `backend/capture_store.py:45` 기본 캡처 TTL 1800초, 세션 3600초. cleanup(`:101`)은 접근 시 실행하는 lazy 정리이며 상주 정리 worker는 없다. close와 재시작 후 초기화에서 소유 캡처를 지우는 정책이다(`:61`, `:224`). 단일 프로세스 로컬 MVP다.
- 쿠키는 HttpOnly/SameSite=Strict, 비로컬 Secure, POST는 Origin/CSRF를 검사한다(`backend/video_api.py:136`). 이것은 로그인/영구 사용자 신원이 아니다.

`capture_id`는 접근 통제된 일시적 입력이고 `image_id`는 기존 검사 registry 식별자다. 서로 치환하지 않는다. 현재 CaptureStore에는 검사 동안 pin하는 public API 또는 metadata+bytes를 한 번에 얻는 snapshot 메서드가 없다.

## 5. 승인 영상 및 기하학 검토

### 5.1 이번 확인 — CONFIRMED

| 항목 | 실제 확인 |
|---|---|
| 파일 | `data/outputs/videos/bottle_conveyor_clean_h264_1920x480_8s.mp4` |
| 등록 | `backend/video_source.py`의 DEMO_VIDEO: VID-000001 |
| SHA256 | `f1c5a12ee25672bfb8241311ecd16f7fefb7e549cb43a44a81bb4858ea9f9a2d`, 승인값과 일치 |
| OpenCV metadata | 1920×480, 30FPS, frame_count240 |
| 메모리 read | 240프레임 후 EOF, release 확인. 프레임 파일 저장 없음 |
| 기존 인증된 형식 | H.264/yuv420p,8초. 코덱/Chrome 재검증은 이번에 하지 않고 Step 2 보고서와 구분 |

생성 코드 `data/outputs/videos/render_conveyor.py:29`를 **읽기만** 했다. 실행·재합성하거나 코드가 가리키는 데이터셋/정답 폴더를 열지 않았다. 정답 category 배열을 ROI/트리거 선정에 사용하지 않았다.

코드에서 sprite는 원래 이미지의 contour bounding box를 잘라 260×260으로 resize하고, 296×296 canvas에 배치 후 -28~28도 회전한다(`:41`, `:46`, `:119`). 병 중심 y=260, x 간격350, 이동은 `start_x + elapsed*252`다(`:16`, `:130`, `:139`, `:147`). 따라서 오른쪽 이동, 30FPS에서 명목상 **8.4px/frame**, 중심 간 도착 간격 약1.389초다. 이 값은 합성기 기하이지 센서/제품 검출 성능이 아니다.

합성은 y=[107,414)로 제한한다(`:64`). 레일은 y78~105와415~442, 범례 제거는 y=[443,480)다. 전체 sprite canvas가 중앙에 있을 때 y=[112,408)로 놓이므로 세로 여유가 작다. 회전·원본 foreground 선택에서 이미 없어진 외관은 ROI 어댑터로 복원할 수 없다.

표본 시각 검토에서는 원형 상면 제품이 가로로 연속 이동하고 좌우 프레임 경계에서 일부가 잘리며, 작은 ROI가 아닌 전체 1920×480 입력에는 여러 제품이 동시에 보임을 확인했다. 불량 종류/정답은 판별하지 않았다.

추가 메모리 측정은 grayscale>95인 픽셀이 y=[110,412)에서 열당10개 이상인 x열의 연속 구간을 보는 **기하 보조 휴리스틱**이었다. 예를 들어 frame0의 한 밝은 외곽 구간 [221,479), frame1 [229,487), frame30 [473,731)로 오른쪽 이동과 약258px 외곽 폭을 관찰했다. 어두운 내부 때문에 구간이 나뉘므로 이것을 제품 검출기나 전체 병 경계 정답으로 사용하지 않는다. 95는 이 메모리 관찰용 값이지 새 영상 품질/판정 임계값이 아니다. 운영 코드에 추가하지 않았다.

### 5.2 후보와 제한 — DESIGN PROPOSAL

중앙 검사 위치 중심 약(960,260), 약300×300 사각형은 **기하 후보**가 될 수 있다. 예시 후보 x810/y110/w300/h300은 중앙에 정렬된 296px sprite canvas를 수용하려는 설계값일 뿐 **저장·승인·MODEL-VALIDATED ROI가 아니다**. 후보를 적용한 crop/검사도 하지 않았다.

이 후보와 이웃 중심의350px 간격만으로 모든 회전 외곽·그림자·가림이 안전하다고 단정할 수 없다. 각 목표 프레임의 전체 병 포함·이웃 배제·레일 배제·압축 가장자리와 여유를 원본 해상도로 추가 검토해야 한다. 모든 프레임에 이 고정 ROI가 유효하지 않다. **승인 트리거 인덱스 목록은 확정하지 않았다.**

## 6. 정적 입력과 영상 ROI의 도메인 차이

| 항목 | 확인 사실 / 위험 / 미검증 |
|---|---|
| 크기·배경 | CONFIRMED: contour crop→260 정사각 resize→회전·alpha 합성, 다른 belt/그림자 배경. 원래 이미지 전체 배경/여백과 다르다. |
| 비율 | CONFIRMED: 원래 contour bounding box를 정사각으로 변경. 추가 비정사각 ROI는 wrapper256 변형을 더한다. |
| 방향 | CONFIRMED: 합성기 회전이 있음. 원래 학습 영상의 방향 분포와 동등성은 NOT TESTED. |
| 색·밝기 | CONFIRMED: 합성 BGR/alpha/배경/그림자·두 번 이상의 손실 재인코딩 이력. 픽셀 분포가 원본과 동일하지 않다. |
| 작은 특징 | DESIGN RISK: 축소·회전·mask erosion/blur·압축으로 작은 외관 특징이 약화될 수 있다. 이번에 모든 결함 보존을 증명하지 않았다. |
| 위치·잘림 | CONFIRMED: 좌우 화면 경계와 ROI 경계에서 잘릴 수 있음. 여러 제품이 전체 프레임에 동시에 존재. |
| 품질 판정 | DESIGN RISK: ROI 면적/배경이 바뀌면 밝기 mean도 바뀐다. 기존125/150 품질 규칙을 유지하되 결과가 REINSPECT일 수 있다. 새 기준으로 맞춰 PASS를 만들지 않는다. |
| 모델 적합성 | NOT TESTED: 영상 ROI score/Recall/Precision/latency/임계값 유효성. 동일 모델 호출은 분포 동등성 증명이 아니다. |

모델 metadata(`models/patchcore/model_metadata.json`)는 train180/val29, 입력256, ResNet18, calibration34.1442를 기록한다. 과거 정적83장 AUROC0.8286/Precision100%/Recall50.79%는 `docs/evaluation-results.md:34`의 기록이며, 평균42.53ms는 `README.md:19`의 과거 측정이다. **영상 ROI 및 HTTP 성능으로 전용하지 않는다.** GT 파일이나 calibration 원본/정답으로 ROI·트리거·임계값을 튜닝하지 않는다.

## 7. 저장 ROI 및 수동 ROI 계약 — DESIGN PROPOSAL

### 7.1 좌표·검증

- `x,y,width,height`: StrictInt, bool/문자열/실수/NaN/Infinity 거부. extra 필드 금지.
- top-left 원점, ORIGINAL_IMAGE_PIXELS_TOP_LEFT, 회전/자동 축척 없음. 영역은 **[x,x+width)×[y,y+height)**.
- x/y≥0, width/height>0, 합이 검증된 원본 width/height 이하. 경계에 정확히 접하는 것은 허용.
- 원본/ROI 최대 pixel 수·입력 bytes 상한을 먼저 적용. 매우 큰 값은 crop/할당 전에 거부.
- **MVP 최소32×32 제안**: 자원·무의미한 극소 입력 방지용이며 모델 유효성 기준이 아니다. 사용자 승인 후 설정값으로 확정한다. 32 미만을 모델이 원천 처리하지 못한다고 주장하지 않는다.
- 비율은 계산·기록하되 임의 새 양품 임계값을 만들지 않는다. 정사각형을 초기 UI 권장으로 하고 다른 비율은 256×256 변형 경고를 표시한다. 자동 padding/회전 보정 금지.
- 저장 ROI의 source revision/해상도/제품/버전을 매번 확인. 다른 해상도에 묵시적으로 scale 적용 금지.
- 경계가 맞는 것과 병이 온전히 들어온 것은 다르다. 후자는 수동 확인 또는 별도 검증된 트리거/설정 승인으로 다룬다.

### 7.2 저장 ROI 최소 구조(PROPOSED, 현재 미구현)

```json
{
  "roi_config_id": "ROI-<opaque-id>",
  "roi_config_version": 1,
  "source": {"kind": "VIDEO", "video_id": "VID-000001", "source_revision": "<verified-sha256>"},
  "product_id": "<user-selected-neutral-product-id>",
  "source_width": 1920,
  "source_height": 480,
  "coordinate_system": "ORIGINAL_IMAGE_PIXELS_TOP_LEFT",
  "roi": {"x": 810, "y": 110, "width": 300, "height": 300},
  "active": false,
  "approved_for_auto": false,
  "created_at": "<server-UTC>",
  "updated_at": "<server-UTC>"
}
```

위 좌표는 미승인 후보 예시이며 ID·시각·제품 값도 실행 결과가 아니다. 필드명은 본 제안이고 최우선 명세의 roi_id/roi_version과 의미를 대응시켜 Phase B에서 한 가지 명명으로 통일한다.

video_id만 연결하면 콘텐츠 교체를 검출할 수 없고, product_id만 연결하면 촬영 조건을 구분할 수 없다. **MVP는 video_id+revision+원본 크기+product_id**를 적용 범위로 권장한다. capture_id는 일시적 입력이지 preset 적용 대상을 대체하지 않는다. 향후 중립 source_id/카메라·profile로 확장하되 이번에 불필요한 카메라 관리 시스템을 만들지 않는다. 모델·전처리 계약은 preset 승인 및 검사 snapshot에 기록한다.

소유자는 서버가 검증한 capture session의 내부 owner에 연결하며 타 세션은404다. owner/cookie/CSRF를 외부 응답·로그에 넣지 않는다. 로컬 MVP는 **세션 소유 preset**을 권장한다. version은 추기형이고 PUT은 expected_version 검증 후 새 version을 발급한다. 충돌409, 이전 version 불변, 수정 시 AUTO 승인을 해제하고 명시적 재승인을 요구한다. 실행 중 최신 version으로 몰래 교체하지 않는다.

**저장과 소유권 제약:** 현재 세션은 서버 재시작으로 사라진다. preset을 디스크에 저장해도 다음 세션이 같은 사용자임을 확인할 수 없다. MVP는 이전 version을 감사용으로 남기고 AUTO는 재설정/재승인하는 안을 권장한다. 재시작 후에도 계속 사용하는 공유 설정이 필수라면 서버 관리 읽기 전용 승인 preset이나 안정적인 인증을 별도 선택해야 한다. 인증 없이 모든 세션이 공유 설정을 수정하는 안은 채택하지 않는다. 이 수명 정책은 구현 전 사용자 결정 사항이다.

### 7.3 수동 입력

CAPTURE는 capture_id의 owner/TTL/PNG hash/원본 크기/video revision을 서버에서 확인한다. REGISTERED_IMAGE는 기존 등록 image_id만 받아 원본 크기와 **이미지 bytes revision**을 검증한다. video source_revision과 이미지 콘텐츠 hash를 혼동하지 않는다.

MANUAL은 명시 ROI, AUTO는 저장된 ID+version만 허용한다. 둘 다/둘 다 없음은422다. AUTO에 임의 ROI를 덮어쓰거나 미승인 preset을 적용하지 않는다. 저장 이미지에서 정한 ROI를 VIDEO AUTO에 적용하려면 영상 측 해상도·위치를 재확인하고 별도로 저장·승인한다.

## 8. Trigger와 ROI 분리·후속 AUTO 책임

**DESIGN PROPOSAL:** 이 8초 CFR 데모는 실제 내용으로 확인한 트리거 프레임 목록을 별도 설정으로 사용하는 방식A를 우선한다. 방식B의 제품 위치 감지기는 현재 backend에서 확인하지 못했다. 배경·조명·회전 내성과 중복 감지 검증이 더 필요하며 이번 밝기 열 휴리스틱을 도착 감지 구현으로 승격하지 않는다.

트리거는 video revision/재생 사이클/검사 위치에 연결하되 ROI preset과 별도 ID·책임으로 관리한다. 제품 정답·결함 순서를 키로 사용하지 않는다. 각 목표 프레임에서 전체 병 포함·이웃 배제·ROI snapshot 적합성을 사람이 승인한다. ROI 설정만으로 제품 도착을 감지했다고 말하지 않는다.

Step 3 Phase B는 preset 검증·공통 검사 백엔드를 담당한다. Day6는 AUTO 상태 머신, 검증된 프레임으로 위치 정렬, Pause/Grab, 사이클ID+trigger키의 1회 실행, 결과 저장 확인 후 Play를 담당한다. 재전송 중복은 서버 측 멱등 키와도 연결해야 한다. loop마다 새 사이클, 처리 중에는 사이클을 바꾸지 않는다. 실패·timeout·입력 부적합은 ERROR_HOLD로 멈춘다. REINSPECT 후 재개 여부도 명시 정책으로 정하며 무조건 다음으로 진행하지 않는다. PLC는 구현하지 않는다.

## 9. 자동·수동 공통 검사 재사용안

| 안 | 장점 | 위험 / 결론 |
|---|---|---|
| A: 공용 ImageRegistry에 ROI PNG 등록 | 기존 image_id workflow 호출 가능 | `backend/inspection.py:144`는 단순 path 등록이며 owner/TTL/영속성 보호가 없다. 이미지 목록 노출·기존 POST를 통한 타인 ROI 재사용 위험. **공용 registry 무조건 등록은 비권장**. |
| B: workflow에 ndarray 입력 추가 | 중간 파일 감소 | ID·로드 실패·로그·저장 경로 변경이 커지기 쉽다. 최소안으로 채택하지 않음. |
| C: 요청 전용 registry+storage wrapper 내부 어댑터 | image_id/predict/decision 구현 재사용, private ROI 수명 통제 | 별도 artifact 수명·provenance가 필요하지만 **권장안**. |

### 권장 공통 서비스(PROPOSED)

1. Origin/CSRF/서버 세션을 검증한다.
2. 입력 snapshot을 획득한다. CaptureStore에 metadata+PNG bytes를 동일 lock에서 검증하는 public snapshot 메서드만 최소 추가한다. 저장 이미지는 registry로 허용된 파일의 경계·링크·크기를 검증하고 bytes snapshot을 만든다.
3. bytes hash·원본 크기·uint8 BGR3를 검증한다. 저장 이미지는 클라이언트가 선택한 image_revision도 일치해야 한다. 디코딩 bytes/최대 해상도 상한을 둔다.
4. AUTO는 소유·적용 범위·승인·기대 version이 일치하는 저장 ROI snapshot, MANUAL은 strict 좌표를 선택한다.
5. 공통 crop은 `image[y:y+height, x:x+width].copy()`다. 추가 resize/pad/회전/색 보정 없이 shape/empty를 재검증한다.
6. 비공개 artifact 디렉터리에 원자적으로 PNG를 저장하고 **capture_id와 별개의 중립 image_id**를 발급한다. 추론에 사용할 PNG가 crop 화소와 같음을 후속 테스트로 검증한다.
7. 요청 전용 ImageRegistry에 해당 1건만 등록하고 기존 `execute_inspection_workflow(product_id,image_id,registry=...,storage=...,inferencer=...,decision_threshold=34.1442)`를 호출한다. 공용 registry는 오염시키지 않는다.
8. InspectionStorageBase를 구현하는 얇은 위임 wrapper가 save_inspection 전에 `metrics.input_provenance`를 붙여 기존 저장소에 위임한다. workflow/추론/판정을 복제하거나 변경하지 않는다.
9. 성공·실패 모두 실제 record에 provenance를 연결하고 저장 확인 후 응답한다. 저장 실패는 HTTP 오류로 보류하며 자동 재생하지 않는다.

기본안에서는 기존 inspection/storage/ml/Agent 로직을 변경하지 않는다. 위임 storage의 모든 메서드·실패 분기와 metadata 저장은 Phase B 테스트가 필요하다. register_image 자체를 공개 API로 만들지 않는다.

**ID 호환 주의:** Agent의 `backend/agent/tools.py:16` 허용 정규식에 없는 IMG-ROI-UUID는 현재 image_id가 null로 정리된다. 최소 변경안은 기존 허용 형식 `IMG-BOTTLE-INJ-<8자리>`에서 미사용 번호를 영속 allocator로 확보하고 기존 registry/artifact와 충돌을 검사하는 방식이다. 다만 INJ의 기존 용도는 주로 시험 주입 이미지이므로 ROI에 재사용할 명명 계약 승인이 필요하다. 의미를 분리하려면 새 중립 형식과 좁은 Agent ID allowlist 확장을 별도 승인한다. 이번에 ID를 발급하지 않았다.

## 10. TTL·검사 이미지 수명·추적

### 10.1 TTL 경쟁 회피(PROPOSED)

CaptureStore.image는 lock에서 무결성을 검증한 bytes를 반환한다. **검사 시작 전에 metadata+bytes를 원자적 snapshot으로 획득**하면 이후 TTL 정리가 원본 PNG를 삭제해도 처리 중인 입력 bytes는 유지된다. metadata()와 image() 사이에 만료돼 획득하지 못하면404로 중단한다. 만료를 우회하지 않는다.

snapshot 획득 후에는 요청 소유의 불변 bytes로 완료할 수 있다. 추론 내내 전역 CaptureStore lock을 잡거나 만료 가능한 파일 path를 계속 참조하지 않는다. snapshot 메모리·동시 추론 개수를 제한하고 종료 시 해제한다. 만료 이후의 새 획득 요청은 거부한다.

### 10.2 저장 정책(PROPOSED, 승인 필요)

- 일시 capture는 기존30분/세션 수명을 유지한다. 전체 PNG를 무조건 영구 보관하지 않는다.
- 검사에 사용한 ROI artifact는 **초기안7일, 별도 용량·건수 제한**으로 private 보관한다. 처리 중에는 삭제하지 않는다. 가득 차면 참조 중 파일을 몰래 지우지 않고 신규 수용503 또는 명시적 보수를 선택한다.
- InspectionRecord/provenance/기존 로그는 capture TTL과 독립이다. ROI 이미지가 만료돼도 검사 결과를 삭제하지 않는다. 이후 이미지 조회 불가를 표시하고 전체 화소 재현 가능하다고 주장하지 않는다.
- 7일은 로컬 MVP 보존 제안이지 모델 기준이 아니다. 용량·기간은 사용자 확정 대상이며 Cloud Run 영속성/다중 replica는 별도 저장 계층이 필요하다.
- 입력 snapshot/ROI PNG는 workflow 전에 저장하고 record commit 전에는 pending으로 관리한다. 명백히 미참조이면 실패 cleanup, 부분 commit/저장 성공 여부 불명확 상태는 복구 대상으로 남긴다.
- 기존 검사 행과 로그 저장은 두 번의 쓰기이며 트랜잭션이 아니다(`backend/inspection.py:640`). 예외 후 무조건 파일 삭제·무조건 검사 재시도로 고아 기록/중복 검사를 늘리지 않는다.
- 기존 generator를 주입하고 재시작 시 영속 최대 검사ID 동기화를 확실하게 수행한다(`backend/inspection.py:170`). 별도 INSP 채번을 만들지 않으며 사전 입력 거부에서는 번호를 발급하지 않는다.

### 10.3 최소 provenance(PROPOSED)

InspectionRecord의 top-level extra는 ignore이므로 미정의 필드를 넣기만 하면 저장되지 않는다(`backend/storage.py:87`). 호환 확장은 검증된 `metrics.input_provenance`를 권장한다.

필수 후보: input_kind, 원본 image_id 또는 capture_id, 해당 시 video_id/revision/frame_index, 원본 bytes SHA256/크기, mode, 실제 ROI, preset ID/version, 결과 ROI 크기/hash/artifact 중립ID, model checkpoint SHA256/전처리 계약, 실제 검사 시작·완료 시각이다. record.image_id는 **실제 검사한 ROI image_id**, 원래 image_id는 provenance의 source로 구분한다.

model_name만으로 모델 버전을 식별하지 않는다. 실제 파일 hash·승인 metadata 일치를 서버 확인해 기록하며 기대 metadata hash를 확인 없이 실측이라고 쓰지 않는다. session/CSRF/내부 path/원본 파일명/class는 기록하지 않는다. owner는 private artifact index에 분리한다. 검사 결과의 product_id는 기존 의미로 유지한다.

## 11. 입력 부적합과 제품 NG 구분

**DESIGN PROPOSAL:** ROI schema/경계/적용 대상 오류422, 오래된 source/preset revision409, 타인·만료 capture/preset404, Origin/CSRF403, 모델 준비 불가/저장 용량503을 제안한다. 새 애플리케이션 error_code 이름은 Phase B에서 확정하며 기존 final_reason_code에 임의 NG 이유를 추가하지 않는다.

입력 검증은 workflow의 inspection_id 발급 **이전**이다. 거부 요청으로 제품 OK/NG나 가짜 검사 행·발생하지 않은 IMAGE_LOAD_FAILED를 만들지 않는다. 입력 준비 오류는 실행 전 HTTP 실패로 구분한다.

workflow 시작 후 로드·추론 오류는 기존 UNKNOWN/FAILED·SKIPPED/REINSPECT/ERROR의 실제 경로를 그대로 따른다. ERROR_HOLD는 자동 제어 UI 상태이지 새 제품 판정값이 아니다. 새 ROI API는 모델 준비 불가를 사전503으로 hold하는 안을 권장하나 기존 POST /inspections의 SKIPPED 계약은 변경하지 않는다.

잘린 병·복수 제품 혼입을 자동 판별하는 기능은 현재 없다. 사람의 재선택 또는 승인된 트리거/설정이 필요하며 crop 성공을 입력 적합성·양품으로 간주하지 않는다.

## 12. 로그·Agent 호환성과 위험

### CONFIRMED

- `backend/storage.py:134` 로그 schema에는 product_id 전용 필드가 없지만 **`backend/inspection.py:315` INSPECTION_STARTED message에는 실제 product_id 문자열이 포함된다.** Step4의 신규 로그 제외 정책은 아직 구현되지 않았다.
- 로그는 inspection_id로 연결한다(`backend/storage.py:329`). Grab 감사와 검사 시작 이후 lifecycle 로그는 별개다. 새 CAPTURE/ROI event는 현재 Agent enum 허용 목록에 없다(`backend/agent/tools.py:37`).
- Agent는 `_record_data`(`backend/agent/tools.py:95`)의 허용 필드만 전달한다. 실행 로그 message는 제외하고 _safe_metrics만 보낸다(`:187`). provenance 추가만으로 새 Fact/Evidence가 자동 생성되지 않는다.
- `_context_view`(`backend/agent/service.py:98`)는 제품을 TARGET-PRODUCT로 치환하고 image_id도 모델 context에서 제외한다. 기존4도구·Evidence/Fact/Pointer 검증은 유지한다.
- T03 이력 비교는 동일 product·크기/channels·과거 시각 등을 확인하지만 **ROI 좌표/version/source/전처리 계약으로 분리하지 않는다**(`backend/agent/tools.py:119`). 같은300×300이라도 서로 다른 ROI의 mean이 섞일 수 있다. 현재도 STORED_VALUES_ONLY_UNVERIFIED_MEASUREMENT_CONTRACT 제한을 표시한다(`:154`).

### DESIGN PROPOSAL

Step3은 기존 lifecycle event로 실제 로드/분석/추론/완료를 기록하고 ROI provenance는 결과 metadata에 둔다. ROI 준비 감사가 필요하면 별도 감사 영역에서 실제 이벤트만 기록한다. 미지원 event를 Agent가 이해했다고 주장하지 않는다.

신규 로그의 product_id 제거는 Step4에서 **producer message의 최소 수정**을 우선한다. 기록을 사후 조작하거나 가짜 product_id를 workflow에 넣어 우회하지 않는다. Step3에서 앞당기려면 해당 변경·회귀 테스트를 명시적으로 승인받는다.

기존 도구로 저장된 일반 판정/수치를 조회하는 것과 ROI 상세 설명·이종 ROI 이력의 의미적 안전성은 다르다. **새 ROI의 자동 Agent 재진단을 켜기 전에** 측정 계약/ROI 범위 필터 또는 비교 불가 처리를 Step4에서 승인·검증해야 한다. product_id를 촬영 profile 대신 변조하지 않는다. provenance를 통째로 Agent에 공개하지 않는다.

자유 자연어의 모든 인과 표현 안전성·실Gemini 자율 선택은 **NOT TESTED**다. Agent에 final_result 변경 권한을 주지 않는다.

## 13. 저장 이미지·ImageView 원본 pixel 계약

### 현행 — CONFIRMED

`GET /inspections/images`(`backend/main.py:498`)는 등록 중립ID 목록/sample만 제공하며 원본PNG/개별 크기/revision API가 아니다. `GET /test-image`는 대표 이미지 metadata용이며 임의 image_id의 ImageView 조회가 아니다. 현재 main/video/agent router에서 일반 저장 이미지 metadata·bytes 조회 API는 확인하지 못했다. 사용자 임의 파일 업로드가 이미 있다고 가정하지 않는다.

### 제안

- 최소 `GET /images/{image_id}`: 세션·허용ID 확인, 크기/channels/image_revision/안전URL. `GET /images/{image_id}/image`: 동일 인가·경계·용량 검증 후 bytes 제공. 내부 path/파일명/class는 제외한다. ID 목록은 기존 API를 재사용한다.
- MVP 허용 입력은uint8 Gray/BGR로 한정하고 기존 표준 COLOR 로드와 같은3ch BGR 정규화 계약을 기록한다. 알파/depth/profile 임의 지원을 주장하지 않는다. 표시 이미지와 검사 snapshot의 revision 대응을 보장한다.
- 표시PNG를 다시 인코딩하면 원본 파일 hash와 다를 수 있으므로 표시revision/입력revision을 구분해 서버에서 대응시킨다.
- Capture PNG는 OpenCV BGR 인코딩을 거쳐 브라우저RGB로 표시된다. `tests/test_capture_store.py:37`은 cv2 왕복 완전 일치와 PIL RGB(210,40,3)를 확인하는 기존 정의다. 이번에 재실행하지 않았다.
- pixel 검사 기준은 **서버 저장PNG의 원본(x,y)** 다. R/G/B 각0~255이며 BGR index를 뒤집지 않는다.
- GV는 cv2.COLOR_BGR2GRAY의uint8 결과를 기준으로 한다(`backend/vision.py:40`). 개념식0.299R+0.587G+0.114B의 JS 구현과 정밀 반올림 동등성은 미검증이다. 필요하면 Day6 별도 승인으로 서버 pixel 조회 API를 검토하되 Step3 최소 API에 필수 추가하지 않는다.
- 확대 보간된 화면색이 아니라 원본 buffer를 읽는다. credential fetch→blob→canvas의 CORS/taint·색 관리·보간 영향을 Day6에서 확인한다.
- 화면 좌표에서 표시 원점/letterbox를 빼고 zoom·Pan 역변환으로 원본 좌표를 얻는다. pixel은 floor 후0≤x<W/0≤y<H. ROI는 시작floor/끝ceil 등 명시적 반올림 규칙의 정수 반개구간으로 바꾸고 서버에서 다시 검증한다.
- Fit/100%/PixelGrid는 표시 동작이지 이미지 재저장이 아니다.500×500은250,000pixel이며 모든 값을 동시에 문자로 표시할 필요는 없다. 원본 pixel을 가리켰을 때 정확한 좌표/GV/RGB를 표시하는 것이 목적이다.

## 14. Phase B API안 — 모두 PROPOSED / 미구현

기존 `POST /inspections`는 유지하고 **POST /roi-inspections**에서 내부 공통workflow를 호출한다. from-capture/from-image를 따로 늘리는 대신 판별 union으로 통합한다.

| Method/path | 제안 책임 |
|---|---|
| GET /roi-presets | owner의 preset 목록, source/product/active 필터 |
| POST /roi-presets | strict 좌표/대상 저장. 명시 승인 없으면AUTO 비활성 |
| GET /roi-presets/{roi_config_id} | owner에게 현재/지정 version 제공 |
| PUT /roi-presets/{roi_config_id} | expected_version 후 새 version, AUTO 재승인 |
| GET /images/{image_id} | 저장 이미지 원본 크기/revision/안전URL |
| GET /images/{image_id}/image | 인가된 표시 이미지 |
| POST /roi-inspections | AUTO 저장ROI 또는MANUAL 명시ROI 공통검사 |

검사 artifact 재표시가 필요하면 보관·owner 계약 승인 후 `GET /roi-inspections/{inspection_id}/image`를 최소 추가하는 후보로 둔다. 기존 전체 결과 조회 API가 있다고 가정하지 않는다.

### MANUAL 요청 예시(PROPOSED)

```json
{
  "mode": "MANUAL",
  "product_id": "<neutral-product-id>",
  "input": {"kind": "CAPTURE", "capture_id": "CAP-<server-issued-id>"},
  "roi": {"x": 810, "y": 110, "width": 300, "height": 300}
}
```

저장 이미지 input은 `{ "kind":"REGISTERED_IMAGE", "image_id":"<registered-neutral-id>", "image_revision":"<verified-content-sha256>" }`로 대체한다.

### AUTO 요청 예시(PROPOSED)

```json
{
  "mode": "AUTO",
  "product_id": "<neutral-product-id>",
  "input": {"kind": "CAPTURE", "capture_id": "CAP-<server-issued-id>"},
  "roi_preset": {"roi_config_id": "ROI-<owned-id>", "roi_config_version": 1}
}
```

mode는 모델 판정 조건이 아니다. trigger/cycle·서버 멱등 키 추가는 Day6 제어와 별도 승인으로 확정한다. 이 예시로 AUTO 전체 구현을 완료했다고 보지 않는다.

### 응답 예시(PROPOSED, 실제 미측정)

```json
{
  "inspection_id": "INSP-<server-issued-id>",
  "image_id": "<neutral-roi-image-id>",
  "result": "<stored-OK-NG-UNKNOWN>",
  "image_quality_status": "<actual-stored-quality>",
  "final_result": "<stored-OK-NG-REINSPECT-ERROR>",
  "final_reason_code": "<existing-server-reason>",
  "input_provenance": {"input_kind": "CAPTURE", "roi_config_version": 1}
}
```

실제 응답은 기존 InspectionResponse 상당을 재사용하고 provenance는 검증된 안전 projection만 제공한다. 이 예시의 ID/결과는 실행값이 아니다. 기존 POST의extra 동작을 무단 변경하지 않고 신규schema는extra=forbid로 제한한다.

## 15. Phase B 최소 변경 파일 후보

| 파일(모두 후보) | 책임 |
|---|---|
| 신규 backend/roi_schemas.py | strict 좌표, source union, AUTO/MANUAL, preset/provenance |
| 신규 backend/roi_presets.py | owner/version/승인, 원자적 설정 저장 |
| 신규 backend/roi_artifacts.py | private ROI PNG/index/hash, 보존/용량/pending |
| 신규 backend/roi_inspection.py | snapshot·crop·요청별 registry·위임storage·workflow 호출 |
| 신규 backend/roi_api.py | preset/저장 이미지/공통 검사router, 기존session/CSRF 재사용 |
| 수정 backend/capture_store.py | public atomic snapshot 메서드만 최소 추가 |
| 수정 backend/main.py | router/lifecycle 연결 중심 |
| 수정 backend/config.py | ROI minimum/제한·저장 경로·보관 기간 |
| 수정 docs/inspection-data-schema.md | 승인된ROI/ID/추적 계약 |
| 신규 tests/test_roi_presets.py, test_roi_inspection.py, test_roi_api.py | 경계/소유권/공통검사/저장·실패/API, artifact 테스트 포함 |
| 신규 docs/day5-step3-phaseb-roi-patchcore-implementation.md | 구현 후 실측 보고 |

신규backend는 책임별5파일을 초기안으로 한다. 파일 수만 줄이려고 저장/검사/HTTP 의존을 섞지 않는다. 기존inspection/storage/ml/Agent 로직 변경은 기본0이며 ID allowlist·로그 전진 배치·전처리 문제가 추가 변경을 요구하면 재승인한다. 신규 프레임워크·패키지는 필요하지 않다.

## 16. Phase B 테스트 계획 — NOT RUN

### 16.1 좌표·preset
- 정상/음수/0/최소 미달/경계 접촉·초과/거대 정수/float·문자열·bool/extra 거부.
- 원본 크기·source revision 불일치, 비율 경고, 임의 resize/pad가 추가되지 않음.
- 생성/조회/목록/수정·version 경쟁·구version 불변·수정 후AUTO 승인 해제.
- 타owner/없는설정/다른source·product/비활성/미승인·AUTO 설정 없음/명시ROI 덮어쓰기 거부.
- 세션 만료·재시작 preset 정책, 검사 중 설정 변경이 사용snapshot을 바꾸지 않음.

### 16.2 입력·PNG·수명·보안
- 유효/없는/타세션/만료capture, 누락·변조·hash/크기 불일치.
- snapshot/cleanup 경쟁, 획득 후TTL 만료에도bytes 유지, 획득 전 만료는 거부.
- 등록image_id/표시PNG/크기/revision, path·URL·encoded traversal·symlink/junction 거부.
- 과대bytes/해상도/손상·비지원depth-alpha-format 안전 처리.
- BGR→PNG→RGB, crop 화소 완전 일치, 반개구간 경계/GV 반올림 계약.
- artifact 원자적쓰기·용량·write/fsync/rename 실패·미참조 정리·부분저장 복구·처리 중 보존.
- 보관 만료 후 검사metadata는 유지되고 이미지만 조회 불가.
- owner/Origin/CSRF/CORS, 응답에 내부path/class/session 미노출.

### 16.3 공통workflow Mock
- 동일 입력bytes/ROI면 AUTO preset과 MANUAL이 동일crop/공통workflow를 사용.
- threshold34.1442/동점 경계/품질warning 우선/UNKNOWN·SKIPPED·모델예외·로드/저장실패 기존정책 유지.
- 입력 거부는INSP 미발급, 실제 시작은 기존채번·저장, 성공/실패provenance/실제시각/version/hash 보존.
- 공용registry/이미지 목록 오염 없음, ID 충돌·재시작 동기화, 기존POST로 타인privateROI 접근 불가.
- 동시추론 상한·자원해제·중복요청/부분commit 처리, 모델미준비를 제품NG로 기록하지 않음.

### 16.4 기존 회귀 재사용
다음 정의를 읽었으며 이번 실행 결과는 없다. Phase B에서는 관련 테스트부터 진행하고 전체는 이후 최대1회다.

| 기존 파일:라인 | 재사용 범위 |
|---|---|
| `tests/test_inspections.py:44`, `:104`, `:124`, `:172` | 기존API/중립ID/JSONL/로드실패 |
| `tests/test_storage.py:140`, `:200`, `:233` | workflow/로드실패/밝기warning |
| `tests/test_day3_5_step4_5.py:227`, `:253`, `:286`, `:311` | 판정우선순위/모델비활성/legacy |
| `tests/test_capture_store.py:37`, `:74`, `:127`, `:158` | PNG/BGR·TTL·재시작·변조 |
| `tests/test_video_source.py:72`, `:85`, `:123` | 반복·동시성·release |
| `tests/test_video_api.py:96`, `:158`, `:180`, `:229` | Grab·CSRF·owner/expiry·실영상 |
| `tests/test_agent_history_comparison.py:71`, `:111`, `:162`, `:212` | 실제값/scope/파생Fact 거부/WARNING조사 |
| `tests/test_agent_t06_isolation.py:54`, `:70` 및 기존error/warning/Fact/Pointer/timeout/Step1-B | T05/T06·근거·판정 보호 |

기존SKIP4는 `docs/day5-step2-phaseb-video-grab-implementation.md:188`의 T03 주입fixture 부재이며 ROI Mock 성공으로 해소됐다고 보고하지 않는다.

### 16.5 실모델 별도 승인
먼저Mock으로 crop/위임/판정 불변을 확인한다. 실PatchCore 검증은 **Phase B에서 사용자가 명시 승인한 최소 입력·격리 출력**에 한정한다. 허용 정상 테스트 이미지와 승인영상의 기하ROI를 후보로 하고 GT에 따라 선택하지 않는다. 현재는 미승인/NOT TESTED다.

실로드 transform chain·checkpoint hash·기존경로 동등성을 확인한다. score가 나쁘다고 임계값/전처리를 몰래 바꾸지 않는다.83장 평가 재실행·GT참조는 불필요하며 금지 범위를 유지한다. Gemini 호출도 필요하지 않다.

## 17. Phase B 전 결정 사항·남은 위험

1. **소유/지속성:** 세션 소유preset인지, 재시작 후에도 사용할 서버 관리 승인preset인지 확정한다. 인증 없는 공유 편집은 배제한다.
2. **ID:** 기존 허용형식의 예약번호를 쓸지 새 중립형식/좁은Agent allowlist 확장을 승인할지 결정한다. capture_id 직접 전용은 금지다.
3. **보존:** 최소32px·ROI artifact7일·용량/건수·부분commit 복구와 만료 후 재현성 제한을 승인한다.
4. **모델:** 실로드 전처리 확인과 최소ROI 추론의 승인 범위를 정한다. 중복이 실증돼도 별도 수정안/승인 전에는 변경하지 않는다.
5. **로그/Agent:** product_id 로그 제거를Step4까지 유지할지 앞당길지 정한다. 이종ROI 이력 비교와ROI전용Fact는Step4에서 검토하고 자동재진단을 무조건 켜지 않는다.
6. **기하:** 후보ROI/trigger 목록은 미승인이다. 원본 해상도로 전체포함·이웃배제를 확인한 후 활성화하며 이번 후보를 자동등록하지 않는다.

이는 Phase A 감사 완료와 구분한 Phase B 선행 결정이다. 미구현을 실행실패로 꾸미지 않는다. **ROI 모델 적합성은 NOT TESTED**, 완전한 촬영조건 일치·실설비성능은 LIMITATION이다.

## 18. 보호·종료 확인

이번 변경은 이 신규 분석 문서 하나다. backend/tests/scripts/기존docs/PPT/모델/승인영상/운영JSONL은 변경하지 않았다. 감사 시작에 기록한 기존208파일의SHA256을 종료 시 비교하여 **변경0·누락0**, 해당 집합의 신규 파일은 이 문서1개임을 확인했다. 기존 Git 변경·미추적 파일 목록도 유지됐다. 보호를 이유로 금지 평가 경로를 탐색하지 않았다.

최초 원본·clean mp4v·승인H.264의 종료 해시는 각각 기존 승인값 daefc8f1…1cdda82 / cfefcd68…248ce5e / f1c5a12e…a9f9a2d와 일치한다. 신규 문서의 scoped `git diff --check`와 untracked 문서를 포함한 `git diff --no-index --check -- NUL <문서>`에서 공백 오류 진단은 없었다. no-index 반환1은 새 문서와 NUL의 차이에 따른 값이며 성공 종료0으로 보고하지 않는다. LF→CRLF 안내는 공백 오류와 구분한다. 기존 발표 문서의 전체 diff를 수정하거나 정리하지 않았다.

실Gemini API0회, 모델로드/추론0회, ROI검사0회, API Grab0회, 신규검사ID/READY/실E2E0건, pytest0회. 원본데이터셋 이미지·GT·외부평가 경로의 목록/열람/복사0건. 영상은 읽기만 했다. Git add/commit/push/reset0건.

AUTO는 저장승인ROI, MANUAL은 명시ROI, 공통workflow/판정 재사용 설계를 유지한다. **Phase B 구현·실모델 검증은 시작하지 않고 사용자 승인 대기로 종료한다.**
