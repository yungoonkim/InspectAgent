# Day5 Step 2-A 재시도: mp4v 파생 영상 및 Chromium 검증

## 1. 최종 판정과 작업 범위

2026-10-17 검증 결과: **PARTIAL**.

| 구분 | 이번 실제 결과 |
|---|---|
| 기존 mp4v 인코더 Probe | PASS: 소형 및 원본 해상도 |
| 범례 없는 파생 MP4 생성 | PASS |
| OpenCV 전체 프레임 디코딩 | PASS: 240/240 |
| 범례 제거 및 보존 영역 검증 | 전수 자동 검사와 표본 육안 검사 완료, 손실 압축 한계 유지 |
| 순차 기준 대비 반복 seek | PASS: 5개 인덱스 × 3회, 15/15 완전 일치 |
| 실제 Chromium 재생 | **BROWSER_FAIL** |
| 백엔드 Grab 개발용 입력 후보 | **APPROVED: 해당 파일·OpenCV 환경에 한정** |
| Day6 React Live View 입력 | **NOT APPROVED** |

원본 MP4만 입력으로 사용했다. 원본 데이터셋 이미지나 외부 평가 데이터는 읽지 않았고, 병을 교체하거나 결함을 가리지 않았다. VideoFileSource, FastAPI 영상/캡처 API, ROI, PatchCore 검사, React UI는 구현·실행하지 않았다.

이전 [H.264 최초 시도 BLOCKED 기록](day5-step2a-clean-video-validation.md)은 변경하지 않았다. 당시 `openh264-2.5.0-win64.dll` 로드 및 인코더 초기화 실패는 해결되지 않았다. 이번에는 승인된 기존 OpenCV `mp4v`만 사용했으며 DLL·FFmpeg·패키지·브라우저를 다운로드하거나 설치하지 않았다.

## 2. 환경과 사전 보호

- 프로젝트: `C:/Users/USER/AI-NativeAgent/Project/InspectAgent`.
- Python: `C:/Users/USER/miniconda3/envs/vision-insight/python.exe`.
- OpenCV: **5.0.0**, 기존 FFmpeg 백엔드 사용.
- Node: **v24.11.0**, 내장 HTTP/fetch/WebSocket으로 브라우저 검증. Playwright 등 새 의존성 없음.
- Chrome: `C:/Program Files/Google/Chrome/Application/chrome.exe`, 실제 CDP 확인 버전 **Chrome/155.0.8059.82**.
- 기존 backend/Agent/tests 수정, `.tmp_measurement_regressions/`, 발표/PPT/Gamma 관련 작업은 현재 작업과 구분해 보존했다.
- 원본 해시가 승인된 값과 동일하고 새 출력 경로가 비어 있음을 확인한 후 생성했다. 이미 존재하는 출력에 대해서는 생성 스크립트가 실패하도록 했다.

## 3. mp4v Probe

프로젝트 밖 격리 임시 디렉터리에서 합성 단색 프레임으로 시험했다. 원본 병 이미지나 평가 자료를 사용하지 않았다.

| Probe | writer.isOpened | 기록/실제 디코딩 | FPS | EOF/해제 |
|---|---|---|---|---|
| 160 × 120 | True | 6 / 6 | 30 | 정상 |
| 1920 × 480 | True | 6 / 6 | 30 | 정상 |

두 파일의 실제 존재, 메타데이터, 재디코딩을 확인했다. H.264로 자동 전환하지 않았다. Probe 파일은 재현 근거와 함께 외부 임시 디렉터리에만 보관했다.

## 4. 범례 위치와 처리

읽기 전용으로 확인한 기존 `data/outputs/videos/render_conveyor.py`:

- `composite()`의 병 합성 영역은 `y=107:414`로 제한된다.
- `make_background()`의 기본 배경색은 **BGR `(17, 22, 29)`**.
- 하단 rail은 `y=415:442`, 범례 baseline은 `y=468`.
- 기존 클래스명 범례는 `GOOD`, `BROKEN LARGE`, `BROKEN SMALL`, `CONTAMINATION`이다. 개별 병과 정답의 일대일 대응까지 확인했다는 뜻은 아니다.

실제 원본 첫 프레임에서도 하단 범례와 병 영역의 공간적 분리를 확인했다. 각 디코딩 프레임의 **`frame[443:480, :]`만 고정 배경색으로 교체**했다. 해상도를 자르거나, 병을 이동·변형하거나, 결함 부위를 선택적으로 처리하지 않았다. 원본 렌더러는 실행·수정하지 않았다.

인코더에 전달하기 직전 모든 프레임의 `frame[:443]`가 원본 디코딩 배열과 완전히 같음을 assertion으로 확인했다. 재인코딩 후에는 손실 압축 차이가 있으므로 원본과 비트 단위 동일하다고 주장하지 않는다.

## 5. 실제 영상과 SHA256

| 항목 | 원본 | 파생본 |
|---|---|---|
| 상대경로 | `data/outputs/videos/mixed_bottle_conveyor_single_lane_1920x480_8s.mp4` | `data/outputs/videos/bottle_conveyor_clean_mp4v_1920x480_8s.mp4` |
| 파일 크기 | 2,800,935 bytes | **2,600,611 bytes** |
| 컨테이너/비디오 | MP4 / MPEG-4 Part 2 | MP4 / MPEG-4 Part 2 (`mp4v`) |
| 해상도 | 1920 × 480 | **1920 × 480** |
| FPS | 30 | **30** |
| 프레임 | 240 | **240**, 0~239 |
| 길이 | 8.000초 | **8.000초** |

원본 SHA256, 사전·사후 동일:

```text
daefc8f14912e2a1e1fac77823f7eee97572e47722d3276f93ea3530b1cdda82
```

파생본 SHA256:

```text
cfefcd68116d79670d5d09a016f57f998d5c654499c4bdeaf7b32bdba248ce5e
```

컨테이너 직접 검사에서 sample entry `mp4v`, timescale `15360`, duration `122880`, `stts=[(240, 512)]`를 확인했다. 고정 프레임 간격은 1/30초다. OpenCV decoder FOURCC 표기는 `FMP4`, decoder pixel format은 **I420**이다. 이를 H.264 인코딩으로 표현하지 않는다.

비디오 track 하나만 존재한다. `mdir` handler는 메타데이터용이며 오디오 track이 아니다. 오디오·자막·첨부 track은 없고 텍스트 태그는 인코더 표기 **`©too: Lavf61.7.100`**뿐이다. 원본 태그를 복사하지 않았다. 중립 파일명과 실제 MP4 메타데이터에서 평가 클래스명·정답 경로는 발견되지 않았다.

권장 중립 ID는 `VID-000001`, `source_revision`은 위 파생본 콘텐츠 SHA256이다. 서버 레지스트리에 등록하지 않았으며 외부 API가 내부 경로나 원본 이름을 반환하도록 구현하지 않았다.

## 6. 전수 자동 검사와 표본 육안 검사

원본과 파생본을 처음부터 순차적으로 함께 디코딩했다. 240개 대응 프레임 모두 크기가 동일했고 241번째 읽기는 양쪽 모두 EOF였다. 모든 캡처 핸들은 `finally`에서 해제했다.

### 6.1 보존 영역의 재압축 차이

아래 값은 프레임별 측정값의 최소/평균/최대다. 임의 합격 임계값을 만들지 않았다.

| 영역 | 지표 | 최소 | 평균 | 최대 |
|---|---|---:|---:|---:|
| `y=0:443` | MAE, 0~255 채널 단위 | 2.0563 | **2.1126** | 2.3784 |
| `y=0:443` | PSNR, dB | 39.4796 | **40.5345** | 40.8842 |
| 병 합성 band `y=107:414` | MAE | 1.9616 | **2.0388** | 2.2522 |
| 병 합성 band `y=107:414` | PSNR, dB | 39.9409 | **40.6793** | 41.1864 |

전체 측정에서 보존 영역 채널별 최대 절대 차이는 **33**이었다. 이 차이를 0 또는 픽셀 완전 보존이라고 표현하지 않는다. 모든 프레임에 대한 축소 보존 영역 fingerprint 최근접 원본은 각각 같은 인덱스였으며 불일치 **0/240**이었다. 생성 시 프레임별 일대일 기록, 균일한 컨테이너 타임라인과 함께 순서 보존을 확인했다. 원본 자체에 반복되는 외관이 있을 수 있으므로 fingerprint 검사는 독립 촬영 여부의 증명이 아니다.

### 6.2 범례 제거의 전수 확인

교체 영역 `y=443:480`은 240개 모두 고정 배경색으로 입력되었다. 재디코딩 후 내부 `y=448:480`은 각 프레임 내에서 공간 표준편차가 B/G/R 모두 **0**이었다. 프레임 전체에서 해당 내부 영역의 채널 범위는 B=14, G=21~22, R=26~27이었다. 압축에 의한 프레임 간 미세 색차는 있지만 문자 모양은 남지 않았다.

교체 영역 전체와 지정 배경색의 최대 채널 오차는 **10**이다. 경계 주변의 압축 차이를 포함하는 값이며 병 영역과 겹치지 않는다. 생성 코드의 실제 문자 위치, 전 프레임 고정 영역 치환, 디코딩한 영역의 균일성 및 시각 표본을 결합해 기존 범례 제거를 확인했다. OCR 결과만으로 텍스트 부재를 선언하지 않았다.

### 6.3 육안 확인 범위와 한계

- 원본 첫 프레임: 범례 위치, 병 영역과 분리, 기존 header 확인.
- 파생본 **0/30/60/90/120/150/180/210/239**: 메모리 기반 contact sheet로 실제 확인.
- 하단 범례는 보이지 않았으며 표본에서 병의 배치·윤곽·가시적인 외관 특징 및 이동 장면을 확인했다. 심각한 구조 왜곡이나 새 가림은 발견되지 않았다.
- 상단의 프로젝트명·합성 영상 설명은 남아 있지만 평가 클래스명이나 개별 정답 표시는 발견되지 않았다.

**240개 전수 육안 검수가 아니다.** 전체 대응 프레임은 자동 수치 검사했고 육안은 위 표본만 확인했다. 모든 미세 결함 픽셀의 무손실 보존이나 기존 PatchCore 성능의 동일성을 보장하지 않는다. 입력 후보 승인은 정답성 UI 제거와 디코딩·Grab 개발 가능성에 대한 것이지 영상 ROI 검사 성능에 대한 승인이 아니다.

## 7. 순차 기준, 랜덤 seek 및 반복 Grab

브라우저 판정 전에 오프라인 디코딩 검증에 포함해 수행했다. 실제 API나 VideoFileSource는 만들지 않았다.

| frame_index | 순차 기준 시각(ms) | 다음 POS_FRAMES | 독립 decoder seek 반복 | 순차 대비 화소 차이 |
|---:|---:|---:|---|---|
| 0 | 0 | 1 | 3/3 PASS | MAE=0, 최대 차이=0 |
| 60 | 2000 | 61 | 3/3 PASS | MAE=0, 최대 차이=0 |
| 120 | 4000 | 121 | 3/3 PASS | MAE=0, 최대 차이=0 |
| 180 | 6000 | 181 | 3/3 PASS | MAE=0, 최대 차이=0 |
| 239 | 7966.6667 | 240 | 3/3 PASS | MAE=0, 최대 차이=0 |

기준 배열은 전체 순차 디코딩에서 확보했다. 각 반복마다 새로운 `VideoCapture`로 `CAP_PROP_POS_FRAMES`를 지정했다. 15개 결과가 기준 배열과 완전히 같았으며 크기는 모두 `(480, 1920, 3)`이었다. 마지막 프레임 다음 읽기는 3회 모두 EOF였다. 모든 decoder는 해제했다.

이 결과는 **해당 파일·OpenCV 버전·5개 인덱스의 seek 검증**이다. 모든 코덱이나 임의의 VFR 영상에 일반화하지 않는다. 후속 MVP의 정확성 기준은 여전히 순차 디코딩이며, seek 최적화는 별도 구현 승인 범위다.

## 8. 실제 Chromium/HTTP 검증: BROWSER_FAIL

### 8.1 격리 방식과 래퍼 준비 이력

기존 운영 FastAPI·React는 사용하거나 변경하지 않았다. Node 내장 모듈만으로 `127.0.0.1` 임시 HTTP 서버와 HTML `<video>`를 만들었다. `/`와 `/clip.mp4`만 제공하며 임의 파일 경로를 받지 않는다. 단일 byte Range에 206을 응답하는 임시 검증 서버다. 이것은 **향후 FastAPI Range 구현의 검증이 아니다**.

개인 Chrome 프로필을 사용하지 않고 새 임시 `user-data-dir`를 사용했다. background networking·sync·extensions 등을 비활성화했고, 외부 주소는 localhost 폐쇄 proxy와 DNS 제한으로 막았다. CDP Fetch 경계에서도 해당 localhost 주소 외 요청을 차단했다. 실제 페이지 외부 요청은 관측되지 않았다. 브라우저 보안 sandbox를 끄거나 시스템 보안 정책을 변경하지 않았다.

사전 래퍼 기동 과정도 보존했다.

1. 제한된 실행 환경에서 Chrome GPU 프로세스가 접근 거부 계열 exit code로 종료했고 `Page.enable`이 timeout됐다. 영상 HTTP 요청은 0건이었다. 이 단계는 코덱 재생 실패로 분류하지 않았다.
2. 승인된 외부 실행 과정에서 이전 임시 폴더 접근이 거부되어 새 격리 폴더를 사용했다. 최초 localhost 탐색 래퍼는 영상 요소를 확보하지 못했다. 이 역시 실제 mp4v 재생 결과가 아니다.
3. DNS 제한의 localhost 예외에 `127.0.0.1`을 명시하고 탐색 결과를 계측한 뒤 실제 HTML·영상 요청과 재생 시도를 확보했다. 이 변경은 **검증 스크립트에만** 있으며 운영 설정 변경이 아니다.

### 8.2 실제 요청 및 재생 결과

| 항목 | 실제 관측 |
|---|---|
| 브라우저 | Chrome/155.0.8059.82, headless Chromium |
| HTML | `GET /` → **200** |
| MP4 요청 | `GET /clip.mp4`, `Range: bytes=0-` |
| MP4 응답 | **206**, `Content-Type: video/mp4`, `Accept-Ranges: bytes` |
| 응답 범위 | `Content-Range: bytes 0-2600610/2600611` |
| Content-Length | 2,600,611 |
| readyState / networkState | 0 / 3 |
| videoWidth / videoHeight | **0 / 0** |
| duration | 미확보 |
| decodedFrames / currentTime | **0 / 0** |
| video.error.code | **4: MEDIA_ERR_SRC_NOT_SUPPORTED** |
| video.error.message | `PipelineStatus::DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDemuxer: no supported streams` |
| 실제 play() | **NotSupportedError: The element has no supported sources.** |
| 실제 영상 표시·재생 | FAIL |
| pause / 중간 seek / 마지막 seek / ended / loop | **NOT TESTED: 지원 스트림 부재로 재생 불가** |

`canPlayType('video/mp4; codecs="mp4v.20.9"')`도 빈 문자열이었지만 판정 근거는 그것만이 아니다. **실제 MP4 요청·206 응답·media error·play() 거부**를 확인했다. HTTP 서버의 파일 전달 실패와 구분되는 테스트 브라우저의 지원 스트림 오류다. 모든 Chromium 배포판이 동일하다는 일반화는 하지 않는다.

이 실패 후 다른 인코더 탐색·설치·재인코딩·재생 반복을 진행하지 않았다. 임시 서버와 해당 Chrome 프로세스는 종료했다. 검증 후 세 개 임시 프로필에 속한 Chrome 프로세스가 **0개**임을 읽기 전용으로 별도 확인했다. 최초 제한 환경의 프로세스 조회 접근 거부를 0개 확인의 근거로 쓰지 않았다.

## 9. 재현 명령과 산출물

신규 파일:

1. `data/outputs/videos/bottle_conveyor_clean_mp4v_1920x480_8s.mp4`: 파생 영상 1개. 기존 `data/outputs/**` ignore 유지.
2. `scripts/clean_conveyor_mp4v.py`: 승인 원본 해시 확인, 기존 출력 거부, footer 치환·인코딩 및 순차/대응/seek 검증.
3. `scripts/verify_conveyor_browser.mjs`: 격리 localhost Range 서버·개인 프로필 없는 Chromium/CDP 시험·종료 처리.
4. 본 문서.

실제 생성 명령:

```powershell
& 'C:/Users/USER/miniconda3/envs/vision-insight/python.exe' scripts/clean_conveyor_mp4v.py --source data/outputs/videos/mixed_bottle_conveyor_single_lane_1920x480_8s.mp4 --output data/outputs/videos/bottle_conveyor_clean_mp4v_1920x480_8s.mp4 --evidence-dir C:/Users/USER/AppData/Local/Temp/vision_day5_mp4v_v99hvzyu
```

출력이 이미 존재하므로 위 생성 명령을 다시 실행하면 덮어쓰지 않고 실패한다. 이번 작업에서는 1회만 생성했다.

실제 최종 브라우저 명령:

```powershell
& 'C:/Program Files/nodejs/node.exe' scripts/verify_conveyor_browser.mjs data/outputs/videos/bottle_conveyor_clean_mp4v_1920x480_8s.mp4 'C:/Program Files/Google/Chrome/Application/chrome.exe' C:/Users/USER/AppData/Local/Temp/vision_day5_browser_7d04da2845154e8e916f3ae97e4ea75c
```

임시 증거는 영구 프로젝트 파일이 아니므로 보관 수명은 보장되지 않는다.

- `%TEMP%/vision_day5_mp4v_v99hvzyu/`: `protected_before.json`, `protected_after.json`, `probes.json`, `video_validation.json`, 두 Probe MP4, 최초 브라우저 기동 로그.
- `%TEMP%/vision_day5_browser_b8013f183f8a4bc79f905c5747238439/`: 재생 전 래퍼 탐색 실패 기록.
- `%TEMP%/vision_day5_browser_7d04da2845154e8e916f3ae97e4ea75c/`: 최종 `browser_validation.json`, `browser_stderr.txt`, `browser.png`, 격리 프로필.

시각 표본 contact sheet는 메모리에서만 표시했다. 새 캡처 이미지나 검사 레코드를 프로젝트에 저장하지 않았다.

## 10. 보호·정적 점검 및 이전 회귀 기준 구분

사전/사후 **기존 4,501개 파일 SHA256 동일, 변경 0·누락 0**.

| 보호 범위 | 사전 파일 수 |
|---|---:|
| backend | 23 |
| data | 4,352 |
| docs | 22 |
| models | 7 |
| presentation | 37 |
| scripts | 17 |
| tests | 42 |
| README.md | 1 |

해당 사전 manifest에 포함된 운영 검사·로그 JSONL, 모델/임계값 메타데이터, 기존 실제 E2E/READY/잠금, 원본 영상 및 생성 파일·발표 자료를 보존했다. 외부 평가 경로의 목록·본문·이미지·라벨·마스크에는 접근하지 않았다. 모델 추론과 원본 데이터셋 접근도 하지 않았다.

추가 핵심 보호 파일의 SHA256:

| 파일 | 사전·사후 동일 해시 |
|---|---|
| `render_conveyor.py` | `31d46f2f2aefdd03bfeb31be1f9296d562e45a60525d51c4dbe30a4d123966e5` |
| `render_metadata.json` | `f0aa2bc3a748d793ffa431c3b4f682008674629578ea27aae6778fcd719eb372` |
| `render_metadata_single_lane.json` | `e6d557a1aa8a9df4875771093b1d30c8a52445ad3d742b0427ed1b9826470182` |

Python 메모리 내 syntax compile 및 `node --check` PASS. 신규 스크립트·문서의 공백 검사 PASS. 전체 `git diff --check`는 **기존 발표 문서 3개**의 trailing whitespace로 FAIL: `presentation/presentation-review-checklist.md`, `presentation/presentation-script.md`, `presentation/slide-outline.md`. 해당 타 에이전트 파일을 수정하지 않았다. 신규 미추적 파일은 일반 `git diff`만으로 검사되지 않으므로 별도 공백 검사로 구분했다.

전체 pytest는 실행하지 않았다. **1175 PASS / 0 FAIL / 4 SKIP / 경고 2건은 이전 공식 기준**이며 이번 mp4v 검증 결과가 아니다.

실제 Gemini API 요청 **0회**, 신규 검사·Agent 분석 **0회**, READY·실행 잠금·실제 E2E 신규 생성 **0건**, 운영 JSONL·모델·임계값 변경 **0건**, Git add/commit/push/reset **0건**이다.

## 11. 후속 승인 사항

- 깨끗한 MP4는 해당 OpenCV 환경의 **백엔드 Grab 개발용 후보**로 사용할 수 있다. `video_id + frame_index + source_revision` 계약과 순차 디코딩 기준을 유지한다. VideoFileSource/Grab API의 실제 구현은 별도 Phase B 승인이 필요하다.
- 실제 테스트 Chrome이 mp4v를 재생하지 못했으므로 **React Live View 입력은 NOT APPROVED**다. 전체 브라우저 연동 준비 완료로 선언하지 않는다.
- H.264 등 호환 인코더 도입 또는 기존 호환 도구 경로 제공과 재검증은 별도 사용자 승인이 필요하다. DLL 다운로드, 패키지 설치, 시스템 설정 변경을 자동 진행하지 않는다.
- 압축 전후 수치·표본 검수는 모든 결함 픽셀의 보존 또는 영상 ROI의 PatchCore 성능을 증명하지 않는다. 정적 이미지 83장 평가 성능을 이 영상 성능으로 인용하지 않는다.

브라우저 실패를 기록하고 이 단계에서 종료한다. 영상 API·ROI·추가 인코더 작업을 이어서 수행하지 않는다.
