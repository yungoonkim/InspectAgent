# Day5 Step 2 Phase B — VideoFileSource 및 수동 Grab

## 1. 결과와 범위

2026-10-17 최종 상태: **COMPLETE**.

최우선 기준인 [자동·수동 검사 설계](visioninsight-auto-manual-inspection-spec.md) v1.0을 확인하고, **획득(Grab)과 검사(Inspection)를 분리**했다. 자동 검사에서 저장 ROI를 사용한다는 방향을 유지했다. 이번에는 영상 등록·제공·프레임 PNG 획득·세션/TTL만 구현했다.

- 신규 테스트 **93 PASS**: VideoFileSource 43, CaptureStore 24, API 26.
- 전체 pytest **1268 PASS / 0 FAIL / 4 SKIP / XFAIL·XPASS 0 / 경고 2건, 31.86초**, 전체 실행 정확히 1회.
- 실제 H.264와 FastAPI ASGI 통합 B01~B10 확인, 실제 Uvicorn 스트림의 **Chrome 재생 PASS**.
- 실제 Gemini API 요청 0회. 운영 JSONL·기존 모델·승인 영상·Ground Truth 변경 0건.

ROI/자동 검사 시퀀스/제품 도착 감지/검사·재생 제어/React/PLC/Agent 확장은 구현하지 않았다. 여기서 COMPLETE는 **이번 획득 인프라 범위**이며 AUTO/MANUAL 전체 설계의 완료가 아니다.

## 2. 구현 파일과 책임

| 파일 | 구현 |
|---|---|
| `backend/video_source.py` | `VideoEntry`, 승인 정적 레지스트리, `VideoFileSource`, revision/경로/상한 검증, 요청별 순차 decoder |
| `backend/capture_store.py` | `CaptureStore`, 서버 발급 세션·CSRF, 원자적 PNG 저장, 소유권·TTL·용량·무결성 검사 |
| `backend/video_api.py` | 영상·캡처 라우터, 엄격한 요청 모델, `VideoRuntime`, 세션 부트스트랩, 정제된 오류 응답 |
| `backend/config.py` | 영상/캡처 상한·저장 경로·명시적 CORS origin 설정 추가, 기존 검사 설정 유지 |
| `backend/main.py` | 라우터/lifespan 연결, 종료 시 캡처 정리, wildcard 대신 명시적 credential CORS |
| `tests/test_video_source.py` | 프레임/동시성/메타데이터/경로/decoder 실패·해제 43건 |
| `tests/test_capture_store.py` | PNG·색 채널·세션·TTL·저장 실패·재시작·보안 24건 |
| `tests/test_video_api.py` | HTTP/Range/strict 입력/세션/CORS/실제 승인 영상 통합 26건 |
| `tests/video_helpers.py` | tmp 경로의 작은 합성 mp4v fixture와 junction/symlink 구성 |
| `tests/video_http_probe.py` | 격리 Uvicorn 실제 스트림·임시 검증 페이지·Chrome 실행 및 종료 |
| `scripts/verify_conveyor_browser.mjs` | 기존 CLI 유지, 선택적 loopback API stream/page URL 및 실제 HTTP 계측 추가 |
| `docs/inspection-data-schema.md` | 기존 검사 명세를 보존하면서 영상·캡처 계약 링크 추가 |

설계 기준·기존 Day4/Day5 결과·Agent 구현·검사 workflow·storage/vision/decision은 수정하지 않았다. 브라우저 스크립트 변경은 실제 FastAPI URL을 기존 검증기에 연결하는 테스트 지원에 한정한다.

## 3. 등록 영상과 VideoFileSource

승인된 정적 레지스트리에 **VID-000001 한 개**만 등록했다. 디렉터리 자동 검색·사용자 경로/URL 등록은 없다. 원본 mp4v와 clean mp4v는 등록하지 않는다.

| 항목 | 실제 값 |
|---|---|
| 내부 파일 | `data/outputs/videos/bottle_conveyor_clean_h264_1920x480_8s.mp4` |
| source_revision | `f1c5a12ee25672bfb8241311ecd16f7fefb7e549cb43a44a81bb4858ea9f9a2d` |
| 승인 형식 | H.264 High Level 3.1 / yuv420p / MP4 faststart |
| 크기·시간축 | 1920×480, CFR 30FPS, 240프레임, 8초, 인덱스0~239 |
| 파일 크기 | 1,542,933 bytes |

위 내부 파일 경로는 운영자 문서용이며 **API 응답에는 포함하지 않는다**. 형식 인증의 근거는 [Step 2-A H.264 검증](day5-step2a-h264-browser-validation.md)과 고정 콘텐츠 hash다. 런타임은 hash와 OpenCV 크기/FPS/count/codec를 재확인한다. FFmpeg 실행 파일에 런타임 의존성을 추가하지 않았다.

`verified_path()`는 파일 크기 상한 확인 후 실제 콘텐츠 SHA256을 읽어 승인 revision과 비교한다. metadata/stream/Grab에서 검증한다. `reject_links()`는 symlink와 Windows reparse point/junction을 거부하고 canonical path가 설정 root 안에 있는지 확인한다.

`grab_frame()`은 공유 커서/공유 VideoCapture 없이 **요청 전용 decoder**로 첫 프레임부터 지정 인덱스까지 순차적으로 읽는다. 반환 배열은 uint8 BGR 3채널이며 승인된 원본 크기를 검증한다. 성공/EOF/예외에서 finally로 decoder와 semaphore를 해제한다.

동시 decode 기본 2개. metadata probe에도 같은 상한을 적용하며 기다리는 무한 큐 대신 429를 반환한다. native decoder를 thread timeout으로 강제 중단한다고 주장하지 않는다. 파일 시스템은 서버 관리 전용이며 적대적인 로컬 프로세스의 검사 직후 파일 교체까지 OS sandbox 수준으로 보장하지 않는다.

이 레지스트리는 승인된 CFR 파일 계약이다. 임의 VFR 영상의 지원·seek 정확성으로 일반화하지 않는다. 랜덤 seek 최적화는 이번 구현에 적용하지 않았다.

## 4. 설정

| 환경변수 | 기본값 |
|---|---|
| `VIDEO_ROOT` | `data/outputs/videos` |
| `VIDEO_MAX_BYTES` | 134217728 (128MiB) |
| `VIDEO_MAX_WIDTH` / `VIDEO_MAX_HEIGHT` | 1920 / 1080 |
| `VIDEO_MAX_FRAMES` / `VIDEO_MAX_DECODERS` | 900 / 2 |
| `CAPTURE_DIR` | `data/outputs/captures` |
| `CAPTURE_TTL_SECONDS` | 1800 (30분) |
| `CAPTURE_SESSION_SECONDS` | 3600 (60분) |
| `CAPTURE_MAX_BYTES` | 268435456 (256MiB, 관리 PNG payload 합계) |
| `CAPTURE_MAX_COUNT` / `CAPTURE_MAX_PER_SESSION` | 128 / 32 |
| `CAPTURE_MAX_SESSIONS` | 256 |
| `CAPTURE_COOKIE_SECURE` | false; ENVIRONMENT가 local이 아니면 항상 Secure |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |

상한은 로컬 데모 설정이지 처리 성능 측정값이 아니다. 상대 경로는 프로젝트 root 기준이다. 저장 경로는 설정할 수 있지만 HTTP 입력으로 변경할 수 없다.

기존 React/Vite package 설정은 발견되지 않았으므로 5173은 **향후 개발 기본값**이며 현재 프론트엔드 포트를 실증한 값이 아니다. origin 설정은 쉼표 구분 문자열이며 경로·사용자정보·wildcard를 허용하지 않는다. 실제 Day6 origin과 배포 origin은 명시적으로 설정해야 한다.

## 5. API 계약

| Method | 경로 | 성공 |
|---|---|---|
| GET | `/videos` | 200, 승인 영상의 metadata 목록 |
| GET | `/videos/{video_id}` | 200, metadata |
| GET / HEAD | `/videos/{video_id}/stream` | 200 또는 Range 206 |
| POST | `/capture-sessions` | 200, 세션 쿠키 및 CSRF bootstrap |
| POST | `/videos/{video_id}/grab` | **201**, PNG 저장 및 캡처 metadata |
| GET | `/captures/{capture_id}` | 200, 소유 캡처 metadata |
| GET | `/captures/{capture_id}/image` | 200, private PNG |

metadata 필드: `video_id`, `source_revision`, `width`, `height`, `fps`, `frame_count`, `duration_seconds`, `codec`, `stream_url`, `frame_index_min`, `frame_index_max`. `/videos`는 이를 `videos` 배열로 감싼다. 내부 파일명·절대경로·평가 라벨을 반환하지 않는다.

stream은 설치된 **FastAPI 0.143.0 / Starlette 1.8.0**의 FileResponse를 사용한다. GET/HEAD, 200/206/416, Content-Type/Length/Range/Accept-Ranges를 실제 검증했다. ETag는 콘텐츠 revision, Cache-Control은 `no-cache`다. Range 오류 400/416은 Starlette의 전송 응답이며 일반 API 오류 JSON과 다를 수 있다.

### Grab 요청

```json
{
  "frame_index": 120,
  "source_revision": "f1c5a12ee25672bfb8241311ecd16f7fefb7e549cb43a44a81bb4858ea9f9a2d"
}
```

Pydantic 2.14.1의 StrictInt로 bool/float/문자열/음수를 거부한다. 범위는 등록된 frame_count 미만이다. 추가 JSON 필드를 금지한다. revision은 필수 lowercase hex 64자리이며 올바른 형식의 다른 revision은 409다. 잘못된 형식은 422다.

검증된 응답 계약:

| 필드 | 의미 |
|---|---|
| `capture_id` | 서버가 생성한 `CAP-` + UUID4 hex32 |
| `video_id`, `source_revision`, `frame_index` | 요청·검증한 원본 식별 |
| `frame_timestamp_ms` | **frame_index / fps × 1000**; 120번=4000ms |
| `timestamp_basis` | `CFR_FRAME_INDEX` |
| `pts_ms` | **null**, 실제 PTS를 읽었다고 주장하지 않음 |
| `width`, `height` | PNG 원본 해상도 1920×480 |
| `image_url` | `/captures/{capture_id}/image` |
| `created_at`, `expires_at` | 서버 UTC ISO8601 |
| `status` | `CAPTURED` — 제품 판정이 아님 |

문서에 가짜 실제 capture_id를 넣지 않는다. 통합 테스트에서 UUID·시각은 매번 서버가 생성했다. 같은 인덱스 반복 Grab도 새로운 capture_id다. Grab만으로 `image_id`/`inspection_id`/판정/운영 JSONL을 생성하지 않는다.

## 6. 세션, CSRF와 CORS

1. React가 허용된 Origin에서 `POST /capture-sessions`, `credentials: include`를 호출한다.
2. 서버가 예측 불가능한 32바이트 난수 세션을 발급한다. 쿠키 이름은 `vision_capture_session`, HttpOnly, host-only, Path=/, SameSite=Strict다.
3. 응답의 별도 `csrf_token`을 메모리에 보관하고 Grab에 `X-Capture-CSRF`로 전송한다. 세션 ID는 JSON에 노출하지 않는다.
4. Grab은 **허용 Origin + 유효한 서버 세션 + 일치하는 CSRF**를 모두 요구한다. 임의 클라이언트 세션 문자열은 신뢰하지 않는다.
5. 캡처 metadata/PNG는 쿠키 소유권·TTL을 검증한다. 타 세션/없는/만료 캡처는 모두 404다.

서버는 세션 키의 hash와 CSRF/만료 시간을 메모리에 보관한다. 유효 세션 bootstrap은 같은 토큰을 유지하며 서버 만료 시간을 연장하지 않는다. 재발급된 Cookie max-age와 무관하게 서버의 절대 세션 만료가 우선한다. 세션 TTL과 캡처 TTL은 별개다.

기존 wildcard+credential CORS를 명시적 origin 목록으로 바꿨다. 허용 origin은 credential·CSRF preflight를 통과하고 비허용 origin은 허용 헤더를 받지 못한다. POST의 Origin 검사는 CORS와 별도로 서버에서 수행한다. 쿠키만으로 CSRF를 방어한다고 주장하지 않는다.

로컬 HTTP에서만 Secure=false를 허용한다. production/cloudrun 등 non-local에서는 Secure=true다. Strict 쿠키 정책이므로 개발 프론트/백엔드는 같은 host를 사용하고, localhost와 127.0.0.1을 서로 섞지 않는다. 다른 site에 분리 배포하는 인증·쿠키 정책은 별도 검토 대상이다.

**로컬 세션 소유권은 완전한 사용자 로그인/계정 인증이 아니다.** 비브라우저의 위조 Origin, 로컬 파일 시스템 관리자, 악의적 동시 사용자 전체를 방어하는 상용 인증 시스템이라고 주장하지 않는다. 세션/CSRF 값을 응용 로그에 기록하지 않는다.

## 7. PNG 저장과 TTL·재시작

- 전체 원본 프레임을 PNG로 인코딩한다. crop/resize/ROI는 적용하지 않는다.
- OpenCV BGR → PNG RGB 인코딩 후 OpenCV round-trip 배열 완전 일치 및 Pillow RGB 채널 역순 일치를 실제 검증했다. Day6의 브라우저 canvas/Pixel Inspector 정확성은 별도 검증이다.
- 전용 CAPTURE_DIR의 `TMP-UUID`에 기록·flush·fsync 후 `CAP-UUID.png`로 원자적 rename한다. 실패 시 이번 임시/최종 파일을 정리한다. 디스크/권한 문제는 정제된 503이며 실제 OS 삭제 불가까지 무조건 복구한다고 보장하지 않는다.
- 관리 payload 총량·파일 수·세션별 수·세션 수를 제한한다. 파일 시스템 전체 공간을 예약하는 quota 시스템은 아니다.
- `.visioninsight-captures` marker로 관리 디렉터리를 구분한다. 소유 marker가 없는 비어 있지 않은 디렉터리나 알 수 없는 파일은 삭제하지 않고 거부한다.
- metadata·세션·소유권은 메모리 전용이다. **단일 프로세스/단일 replica 전용**, 동일 CAPTURE_DIR의 다중 worker 동시 사용은 지원하지 않는다.
- 정상 종료 시 현재 캡처·세션을 정리한다. 비정상 재시작 후 과거 세션/캡처는 접근할 수 없다. 첫 저장소 초기화에서 올바른 marker와 관리 파일명 패턴을 확인한 뒤 과거 관리 PNG/TMP만 정리한다.
- TTL 정리는 요청 시 및 종료 시 수행한다. **유휴 상태에서 정확히 30분에 파일을 삭제하는 background timer는 없다**. 만료 캡처는 다음 접근에서 404·정리되며, idle 중 디스크 잔존은 용량 상한 안에서 허용한다.
- 이미지 응답 전 실제 파일 존재/크기/링크와 SHA256 무결성을 확인한다. metadata/PNG/session 응답은 `no-store`, PNG는 `image/png`와 nosniff다. 디렉터리를 StaticFiles로 공개하지 않는다.

Cloud Run의 임시 파일 시스템·다중 replica·영구 보관·분산 세션은 해결하지 않았다.

## 8. 오류 계약

일반 오류는 기존 FastAPI 스타일의 `{"detail":{"error_code":"..."}}`이며 원문 예외·사용자명·서버 경로를 반환하지 않는다.

| HTTP | 대표 코드·조건 |
|---|---|
| 404 | `VIDEO_NOT_FOUND`, `VIDEO_NOT_AVAILABLE`, `CAPTURE_NOT_FOUND` |
| 422 | Pydantic 입력 오류 또는 `FRAME_INDEX_INVALID` |
| 409 | `VIDEO_REVISION_MISMATCH`(요청), `VIDEO_REVISION_CHANGED`(실제 파일) |
| 415 | `VIDEO_FORMAT_UNSUPPORTED`, `VIDEO_METADATA_INVALID`, `VIDEO_FRAME_INVALID`, `VIDEO_DECODE_UNAVAILABLE` |
| 413 | `VIDEO_LIMIT_EXCEEDED` |
| 429 | `VIDEO_DECODER_BUSY` |
| 401 | `CAPTURE_SESSION_REQUIRED`(Grab) |
| 403 | `CAPTURE_ORIGIN_FORBIDDEN`, `CAPTURE_CSRF_INVALID` |
| 503 | `VIDEO_UNAVAILABLE`, `VIDEO_DECODE_FAILED`, `VIDEO_FRAME_UNAVAILABLE`, `CAPTURE_STORAGE_UNAVAILABLE`, `CAPTURE_CAPACITY_EXCEEDED`, `CAPTURE_SESSION_LIMIT` |

symlink/junction 등 보안상 사용할 수 없는 등록 경로도 정제된 오류로 거절한다. 사용자 임의 경로/URL/파일명은 도구 입력으로 받지 않는다.

## 9. 테스트 실행과 결과

외부 `%TEMP%/vision_video_phaseb_t9irxly5/`에서 출력·로그·TEST_DATA_DIR·검사 JSONL·CAPTURE_DIR·pytest basetemp·JUnit을 분리했다. 임시 offline_pytest 래퍼는 기본 HTTPX 전송과 외부 socket connect를 차단하고 Windows loopback IPC는 유지한다. 외부 평가 경로 읽기/목록 및 기존 보호 파일 쓰기를 audit hook으로 차단했다. HF/Transformers는 offline cache만 사용했다.

| 실행 | 실제 결과 |
|---|---|
| 최초 신규 3모듈 | 89 PASS / 6.70초 |
| 보강 신규 실행 | 92 PASS / 경고2 / 11.35초; 실제 앱 테스트의 불필요한 model startup context는 이후 제거 |
| Agent·검사·저장소·신규 관련 회귀 | 1187 PASS / 경고3 / 24.18초; 신규 OpenAPI 중복 operation 경고 발견 |
| GET/HEAD operation 분리 후 신규+Agent API | **163 PASS / 0 FAIL / 경고0 / 8.48초** |
| 최종 전체 tests, **1회** | **1268 PASS / 0 FAIL / 4 SKIP / 경고2 / 31.86초** |
| 최종 전체에 포함된 신규 | **93 PASS**, source43 / store24 / API26 |
| 최종 전체에 포함된 Agent | **1074 PASS** |
| pip check | **No broken requirements found** |

그룹별 PASS는 중복이 있으므로 합산하지 않는다. 이전 **1175 PASS**는 이번 실행이 아니다. 최종 JUnit은 tests1272 / errors0 / failures0 / skipped4, suite time31.850초다. XFAIL/XPASS는 없다. 경고2는 기존 timm/anomalib deprecation이며 신규 OpenAPI 경고는 남지 않았다.

기존 SKIP4는 그대로다. 주입 fixture를 새로 등록하거나 skip/assertion을 바꾸지 않았다.

| 테스트 | 실제 SKIP 사유 |
|---|---|
| `test_day3_5_integration.py::test_t03_brightness_reduced_inspection` | No injected images registered |
| `test_day3_5_step4.py::test_image_quality_warning_decision_confidence_policy` | No fault-injected images found |
| `test_day3_5_step4_5.py::test_t03_final_verdict_quality_warning_reinspect` | T03 injected image not present |
| `test_day3_5_step4_5.py::test_workflow_product_ng_under_quality_warning` | T03 injected image not present |

신규 순수 보안·계약 테스트는 승인 영상이 없어도 작은 합성 fixture로 실행된다. 실제 H.264 파일 통합 1건만 파일 미설치 환경에서는 명시적으로 skip한다. 이번 환경에는 파일이 있어 **실제 실행·PASS**했고 신규 skip은 없다. 테스트용 작은 MP4/PNG는 tmp에만 생성하며 승인 영상을 복제·재인코딩하지 않는다.

전체 실행 명령:

```text
C:/Users/USER/miniconda3/envs/vision-insight/python.exe -B <외부 임시>/offline_pytest.py <외부 임시>/full tests -q -rs --tb=short --junitxml=<외부 임시>/full.xml
```

실제 `<외부 임시>`는 `C:/Users/USER/AppData/Local/Temp/vision_video_phaseb_t9irxly5`다. 임시 래퍼는 프로젝트 코드에 추가하지 않았다.

## 10. 실제 파일·FastAPI 통합 B01~B10

`test_real_approved_video_and_main_router`는 **실제 backend.main 앱과 승인된 H.264**를 ASGI TestClient로 실행했다. 임시 API/Store unit fixture와 구분한다.

| 시나리오 | 결과 |
|---|---|
| B01 목록 | VID-000001·실제 revision·1920×480·h264, 경로 미노출 |
| B02 stream | 실제 승인 파일 전체 bytes, HEAD 길이, 206/416 확인 |
| B03 frame0 | 201·PNG·원본 순차 배열과 완전 일치 |
| B04 frame120 | 201·4000ms·PNG 완전 일치 |
| B05 frame239 | 201·마지막 프레임 PNG 완전 일치 |
| B06 frame240 | 422·캡처 수 증가 없음 |
| B07 잘못된 revision | 409·캡처 수 증가 없음 |
| B08 타 세션 | 실제 승인 영상 캡처 이미지 404 |
| B09 TTL | 테스트 clock으로 1800초 경과, 404 및 실제 PNG 정리 |
| B10 기존 영향 | /health 정상·Grab에 inspection_id 없음·기존 검사/Agent 회귀 PASS·보호 JSONL 동일 |

단위 source 테스트는 0/60/120/180/239를 각각 3회 추출해 순차 기준과 동일함을 확인했다. 서로 다른 인덱스 동시 추출, 실제 활성 decoder를 Event로 유지한 상태의 상한 거부, EOF/constructor/read/release 실패 후 slot 반환, 경로 탐색과 실제 Windows directory junction 이탈 거부도 확인했다.

PNG 채널 역전 방지·타 세션 metadata와 이미지 모두 차단·30초 합성 TTL·세션 만료 구분·디스크/encode/fsync/rename 실패·한도·재시작·변조·파일 삭제도 별도 assertion으로 검증했다. 단순 HTTP 성공만으로 판정하지 않았다.

## 11. 실제 Uvicorn/Chrome 스트리밍

`tests/video_http_probe.py`는 **실제 FastAPI 앱**을 loopback Uvicorn에 띄우고, 프로세스 한정 검증 HTML을 연결했다. 해당 테스트 페이지는 backend 라우터에 영구 추가하지 않았다. PatchCore startup을 끄고 Gemini Client를 차단했으며 저장 경로는 별도 temp였다.

- Chrome **155.0.8059.82**, 새 임시 프로필·외부 통신 차단 사용.
- 실제 `/videos/VID-000001/stream` 요청: **Range bytes=0- → 206**.
- Content-Type=`video/mp4`, Accept-Ranges=`bytes`, Content-Length=`1542933`, Content-Range=`bytes 0-1542932/1542933`, ETag=승인 SHA256.
- 실제 표시·loadedmetadata·1920×480·8초·play/currentTime 증가·pause 시간 정지·0/2/4/6/7.9초 seek·화면 갱신·ended·loop·재생 재개·video.error 없음: **15 checks 모두 PASS**.
- 별도 Node 범위 초과 Probe는 **416**, Content-Range=`bytes */1542933`. Chrome 자체가 416을 요청했다고 보고하지 않는다.
- 실제 화면 screenshot도 확인했다. 서버와 브라우저 종료를 확인했다.

이는 Step 2-A의 Node 파일 서버가 아니라 **FastAPI FileResponse 엔드포인트의 HTTP 실증**이다. 그래도 브라우저 표시 프레임과 Grab PNG의 픽셀 단위 동기화나 React UI를 검증한 것은 아니다.

재현 명령:

```text
C:/Users/USER/miniconda3/envs/vision-insight/python.exe -B tests/video_http_probe.py --evidence-dir <새 격리 임시 디렉터리>
```

이번 증거 위치는 `%TEMP%/vision_phaseb_browser_9342a17e32124bc5a53c4b181015e076/`: `browser_validation.json`, `api_http.json`, `browser_runner.json`, screenshot·stderr·격리 프로필이다. pytest 증거는 위 `vision_video_phaseb_t9irxly5`의 `full.xml`, `pre-full.xml`, `regression.xml`, 보호 manifest에 있다. 임시 증거의 영구 보관은 보장하지 않는다.

## 12. 보호 및 변경 범위 확인

사전 보호 파일 **4510개** 중 기존 config/main/브라우저 검증기와 계약 링크를 추가한 데이터 스키마 문서만 승인 범위에서 수정했다. 다른 기존 파일은 SHA256을 비교해 보존했다. 신규 파일은 위 구현·테스트·문서뿐이며 승인 영상·기존 manual_validation 회차에 예상치 못한 새 산출물이 없다.

운영 검사/Agent JSONL·모델/임계값·원본/clean mp4v/H.264·렌더러/metadata·기존 READY/잠금/E2E·발표/PPT·다른 에이전트의 기존 수정은 보존했다. `.tmp_measurement_regressions`를 수정·정리하지 않았다. 기본 운영 `data/outputs/captures`도 이번 검증에서는 생성하지 않고 전부 temp에 저장했다.

이번 파일의 syntax·공백 검사와 scoped `git diff --check` PASS. 전체 diff의 기존 발표 문서 공백 오류는 별도이며 수정하지 않았다. pip check PASS. 패키지·Python/Conda·배포 설정은 변경하지 않았다.

실제 Gemini 요청0회, 외부 Ground Truth 열람·목록·수정0건, 운영 JSONL·모델·임계값 변경0건, 운영 검사/READY/잠금/E2E 신규 실행0건, Git add/commit/push/reset 0건이다. 기존 회귀 테스트가 임시 JSONL에서 검사 workflow를 실행한 것과 운영 실검사를 구분한다.

## 13. Day6 React 인수 계약

1. `GET /videos`와 상세 metadata를 조회한다.
2. stream_url을 LiveView video에 연결하고 합성 Simulation Live임을 표시한다.
3. 허용 Origin과 `credentials: include`로 capture session을 bootstrap한다. CSRF는 메모리에 보관한다.
4. 수동 Pause 후 `floor(currentTime * fps)`를 초기 frame_index 후보로 계산한다. duration 끝에서 240이 될 수 있으므로 0~239를 검증하고 명시적으로 유효 프레임을 선택한다.
5. source_revision과 frame_index로 POST Grab한다. Origin/쿠키/CSRF가 필요하다.
6. 반환 image_url을 credential fetch해 PNG blob으로 ImageView에 표시한다. cross-origin 이미지를 canvas에 쓸 때 CORS/credentials·taint를 검증하고 blob URL 수명도 관리한다.
7. **서버 PNG를 ROI/픽셀 조회/검사의 기준 이미지로 사용**한다. 브라우저 currentTime의 부동소수점 경계·표시 지연과 서버 프레임의 완전 일치는 Day6 별도 검증이다.
8. 원본 픽셀 좌표는 왼쪽 위 원점의 x/y/width/height다. CSS 좌표·zoom/pan은 원본 좌표로 변환해야 한다.
9. 잘린 병은 품질을 자동 승인하지 않고 이전/다음 프레임·재Grab·사용자 확인을 거친다.
10. ROI 선택 후 Step3의 공통 검사 API로 넘긴다. 해당 API는 이번에 구현하지 않았다.

Zoom/Pan/Fit/100%/GV·RGB/픽셀 격자/ROI 편집·저장 UI는 아직 NOT IMPLEMENTED다.

## 14. Step3와 자동·수동 공통 경계

Step3은 쿠키 소유권·TTL을 유지하며 `CaptureStore.metadata()`/`image()`로 검증된 PNG bytes를 받아야 한다. capture_id를 경로나 image_id로 직접 치환하지 않는다. ROI 검사 후 별도 중립 image_id 등록 어댑터로 기존 검사 workflow를 재사용한다. 저장 ROI는 영상 revision·원본 해상도·제품 범위·버전을 확인해야 한다.

**최종 AUTO:**

`제품 위치 도착 → LiveView 자동 Pause → 서버 Grab → 사전 저장·승인 ROI 적용 → 동일 PatchCore 검사 → 결과 저장 → LiveView 자동 Play`

사용자의 Grab 버튼이나 매번 ROI 지정을 요구하지 않는다. 위치 도착 트리거와 저장 ROI는 별개다. 실패하면 ERROR_HOLD로 정지하고 임의 OK/NG·무조건 재생을 하지 않는다. 실제 트리거 프레임·저장 ROI·자동 상태 머신은 후속 승인 범위다.

**최종 MANUAL:**

`허용 저장 이미지 또는 LiveView Pause/Grab → ImageView → 사용자 ROI 지정 → 동일 PatchCore 검사 → 결과 확인`

수동 Pause/Grab 자체가 검사를 시작하지 않는다. 수동 검사 후 자동 Play하지 않으며 사용자가 재개한다. 수동 ROI의 AUTO 저장은 별도 확인 절차다.

기존 임계값34.1442와 OK/NG/REINSPECT/ERROR 서버 판정 정책을 유지한다. Gemini는 관측 근거 설명용이며 실제 제품 정답 판정권을 갖지 않는다. ROI/PatchCore 연결·UI·자동 제어·PLC·배포는 추가 구현하지 않고 **Day5 Step3 별도 승인 대기**로 종료한다.
