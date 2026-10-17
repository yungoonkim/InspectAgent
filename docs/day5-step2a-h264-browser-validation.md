# Day5 Step 2-A 최종 보완: FFmpeg H.264 및 Chrome 검증

## 1. 최종 상태와 승인 범위

2026-10-17 최종 상태: **COMPLETE**.

| 검증 | 이번 실제 결과 |
|---|---|
| 휴대용 FFmpeg/ffprobe 확보 및 libx264 | PASS |
| H.264 MP4 변환 | **ENCODE_PASS** |
| OpenCV 전수 재디코딩 | **OPENCV_PASS: 240/240** |
| FFmpeg 전수 재디코딩 및 PTS | PASS: 240/240 |
| 범례·메타데이터 격리 | 확인 범위 내 PASS |
| 병 영역 보존 | 전수 수치 비교 및 9개 시점 표본 비교 완료, 손실 압축 한계 유지 |
| Chrome 실제 재생·pause·seek·ended·loop | **BROWSER_PASS** |
| frame_index 기반 반복 seek | PASS: 5개 인덱스 × 3회 |
| 원본·clean mp4v·운영 데이터 보호 | PASS |
| Day5 Step 2 Phase B 입력 후보 | **승인 가능**, 실제 등록·구현은 별도 승인 |

이번 영상은 MVTec Bottle 이미지에서 합성한 컨베이어 시뮬레이션이다. 실제 카메라·설비 성능이나 영상 ROI의 PatchCore 검출 성능을 입증하는 자료가 아니다. 이미 만들어진 **clean mp4v만 변환 입력**으로 사용했다. 최초 원본 MP4는 누적 손실 비교용으로만 읽었고, 원본 데이터셋 이미지·클래스 폴더·정답 파일·외부 평가 경로는 읽거나 목록 조회하지 않았다.

VideoFileSource, FastAPI 영상·Grab API, 캡처 저장소, ROI, React, PatchCore 검사, Gemini Agent 변경·호출은 수행하지 않았다.

## 2. 이전 실패와 이번 해결 방식

다음 과거 기록을 그대로 보존했다.

- [최초 H.264 시도](day5-step2a-clean-video-validation.md): OpenCV `avc1` writer에서 OpenH264 DLL 로드·초기화 실패, BLOCKED.
- [mp4v 재시도](day5-step2a-mp4v-retry-validation.md): 깨끗한 mp4v 생성과 OpenCV 검증 성공, Chrome은 `MEDIA_ERR_SRC_NOT_SUPPORTED` / `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`로 실패, PARTIAL.

기존 mp4v 실패에서는 실제 Range 206 전달 후 브라우저가 지원 스트림을 찾지 못했다. 이번에는 같은 계열의 격리 Chrome 검증에서 **FFmpeg libx264로 인코딩한 H.264/AVC 영상**이 실제로 재생됐다. HTTP 전달과 코덱 지원을 구분해 검증했다.

이는 **FFmpeg 실행 파일을 통한 변환 성공**이다. 기존 OpenCV `avc1` VideoWriter 또는 OpenH264 DLL 문제를 수정·재검증한 것이 아니다.

## 3. 환경과 FFmpeg 도입

### 3.1 기존 환경 조사

- 프로젝트: `C:/Users/USER/AI-NativeAgent/Project/InspectAgent`.
- Python: `C:/Users/USER/miniconda3/envs/vision-insight/python.exe`, **3.11.16**.
- OpenCV: **5.0.0**, 기존 설치 유지.
- Node: 기존 **v24.11.0**, 추가 패키지 없음.
- Chrome: `C:/Program Files/Google/Chrome/Application/chrome.exe`.
- PATH, 기존 사용자 도구 폴더, `C:/ffmpeg`, 표준 FFmpeg 설치 후보, 해당 Conda `Library/bin`에서 필요한 기존 ffmpeg/ffprobe를 발견하지 못했다. 컴퓨터 전체에 없다고 단정하지 않는다.
- `git status --short`의 기존 Agent/tests/발표/PPT 변경과 미추적 파일을 확인하고 보존했다. H.264 출력·신규 보고서 경로가 비어 있었고 두 입력 SHA256이 승인 값과 같았다.

### 3.2 신뢰 경로와 다운로드

[FFmpeg 공식 다운로드 페이지](https://ffmpeg.org/download.html)가 Windows 빌드 배포처로 안내하는 [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)를 확인했다. 해당 배포처의 release essentials ZIP과 게시된 SHA256을 HTTPS로 받았다.

| 항목 | 실제 값 |
|---|---|
| 배포본 | **9.0.2 essentials_build**, Windows x86-64 portable |
| ZIP | `https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip` |
| 게시 체크섬 | `https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip.sha256` |
| ZIP 크기 | **114,768,076 bytes** |
| ZIP 계산 SHA256 | `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba` |
| 게시 SHA256과 비교 | **완전 일치** |

PowerShell HTTP 요청이 응답 없이 정체되어 취소한 뒤, 기존 Windows `curl.exe`의 명시적 연결·전체 시간 제한을 사용했다. curl 자동 재시도는 0회였고 HTTPS 및 HTTPS 리다이렉트만 허용했다. 정체의 내부 원인은 UNKNOWN이다. 다운로드한 스크립트를 실행하지 않았다.

체크섬 일치 **후에만** ZIP을 열었다. 각 ZIP 항목의 절대경로·해제 경로 이탈·Unix symlink를 검사하고 새 배포 디렉터리에 압축 해제했다. 기존 설치나 바이너리를 덮어쓰지 않았다.

게시 SHA256은 **같은 배포처의 HTTPS 자료**다. 전송 무결성 일치는 확인했지만 별도 PGP·Authenticode 서명이나 독립적인 공급망 검증까지 수행한 것은 아니다. 공식 FFmpeg 프로젝트가 직접 제공하는 서명된 소스 tarball과 이 Windows 제3자 빌드의 검증 수준을 혼동하지 않는다.

### 3.3 실제 휴대용 경로와 실행 확인

설치 루트:

`C:/Users/USER/AppData/Local/VisionInsight/tools/ffmpeg/9.0.2-essentials/`

실행 파일:

```text
C:/Users/USER/AppData/Local/VisionInsight/tools/ffmpeg/9.0.2-essentials/distribution/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe
C:/Users/USER/AppData/Local/VisionInsight/tools/ffmpeg/9.0.2-essentials/distribution/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe
```

- 두 실행 파일의 `-version`: **9.0.2-essentials_build-www.gyan.dev**.
- 빌드: GCC 16.2.0, `--enable-libx264` 및 static/GPL 구성 확인.
- `-encoders`: **libx264 H.264/AVC** 확인.
- ffmpeg.exe SHA256: `3256173f3f8bffd7df12227c68adf68025edb1832273a9530688a7bb1ed8edec`.
- ffprobe.exe SHA256: `f0d36ecbbdd3bcfac3efa078c96c7271c2e68b3810595552ac3b7f17e9a65c52`.
- 설치 루트의 `installation.json`에 출처·다운로드 URL·ZIP/실행 파일 해시 기록.

시스템 PATH·레지스트리·Python/Conda 패키지를 변경하지 않았다. 프로젝트 Git 디렉터리에 도구 바이너리를 넣지 않았다. 실행 시 두 도구 모두 위 **절대경로**를 사용했다.

## 4. 실제 변환과 영상 계약

신규 `scripts/convert_conveyor_h264.py`에서 승인된 두 입력 해시를 확인하고 기존 출력이 있으면 실패하도록 했다. 실제 인코딩은 **1회**, 새 H.264 MP4는 **1개**다.

변환 옵션:

```text
-hide_banner -nostdin -n
-i data/outputs/videos/bottle_conveyor_clean_mp4v_1920x480_8s.mp4
-map 0:v:0 -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p
-fps_mode passthrough -movflags +faststart -an -map_metadata -1 -map_chapters -1
data/outputs/videos/bottle_conveyor_clean_h264_1920x480_8s.mp4
```

draw/crop/resize/filter·범례 제거 처리를 다시 적용하지 않았다. 병·프레임을 선택적으로 교체하지 않았다. 추가 CRF 탐색이나 재인코딩은 하지 않았다.

| 항목 | ffprobe/실제 확인 |
|---|---|
| 출력 경로 | `data/outputs/videos/bottle_conveyor_clean_h264_1920x480_8s.mp4` |
| 파일 크기 | **1,542,933 bytes** |
| 컨테이너 | MP4, ffprobe format=`mov,mp4,m4a,3gp,3g2,mj2` |
| codec / tag | **h264 / avc1**, MIME codec=`avc1.64001f` |
| profile / level | **High / 3.1** (`level=31`) |
| 픽셀 형식 | **yuv420p**, 8bit, progressive |
| 해상도 | **1920 × 480** |
| sample aspect / display aspect | 1:1 / 4:1 |
| 평균/기록 FPS | **30/1 / 30/1** |
| time_base / start_time | **1/15360 / 0.000000** |
| duration | **8.000000초** |
| nb_frames / nb_read_frames | **240 / 240** |
| faststart | **moov(offset 32) < mdat(offset 2458)** |

SHA256:

| 파일 | 사전·사후 또는 생성 해시 |
|---|---|
| 최초 원본 mp4v, 보존 | `daefc8f14912e2a1e1fac77823f7eee97572e47722d3276f93ea3530b1cdda82` |
| clean mp4v, 변환 입력·보존 | `cfefcd68116d79670d5d09a016f57f998d5c654499c4bdeaf7b32bdba248ce5e` |
| 신규 clean H.264 | `f1c5a12ee25672bfb8241311ecd16f7fefb7e549cb43a44a81bb4858ea9f9a2d` |

## 5. 전체 프레임·시간축 검증

- OpenCV: 세 영상의 대응 프레임 **240개 모두** 순차 디코딩, 모든 프레임 shape `(480,1920,3)` 확인. 다음 읽기는 모두 EOF.
- FFmpeg: `-xerror -f framehash -hash sha256` 디코딩 **240개**, 명령 exit 0. 프레임별 해시를 외부 임시 증거에 기록.
- ffprobe: 실제 `-count_frames`로 240 확인. 프레임별 presentation timestamp가 **index/30**과 0.000001초 이내로 일치. 0~7.966667초의 일정한 표시 간격 확인.
- 240개 축소 보존 영역 fingerprint의 가장 가까운 clean mp4v 프레임이 모두 같은 인덱스: **순서 불일치 0/240**.
- B-frame 압축의 DTS 재정렬과 표시 PTS를 혼동하지 않았다. 검증한 것은 표시 순서다.
- decoder는 `finally`에서 해제하고 `isOpened()==False`를 확인했다.

이 확인은 해당 합성 영상의 프레임 대응·표시 시간축 검증이다. 독립 촬영 표본 수나 산업용 영상의 통계적 성능 증명이 아니다.

## 6. 추가 압축 손실과 누적 손실

전수 대응 프레임에 대해 아래 두 비교를 별도로 계산했다. PSNR은 프레임별 dB의 평균이며 전체 파일 단일 pooled PSNR이 아니다. MAE는 BGR 채널 0~255 스케일이다.

| 비교 | 영역 | 평균 MAE | 평균 PSNR(dB) | 프레임별 PSNR 최소~최대 | 전체 최대 채널 차이 |
|---|---|---:|---:|---|---:|
| clean mp4v → H.264, **이번 추가 손실** | 보존 영역 `y=0:443` | **0.8347** | **44.4092** | 43.3764~45.7954 | 40 |
| clean mp4v → H.264 | 병 band `y=107:414` | **0.8825** | **44.0571** | 42.6809~46.1570 | 36 |
| 최초 원본 → H.264, **누적 손실** | 보존 영역 `y=0:443` | **2.2911** | **39.3608** | 38.6613~39.4983 | 39 |
| 최초 원본 → H.264 | 병 band `y=107:414` | **2.2296** | **39.3693** | 38.9653~39.5177 | 34 |

이전 clean mp4v의 원본 대비 보존 영역 MAE 2.1126 / PSNR 40.5345dB는 **과거 측정값**이며 위 신규 수치와 구분한다. 범례가 있던 하단 영역은 누적 품질 비교에서 제외했다.

### 시각 검수

- **0/30/60/90/120/150/180/210/239**에서 clean mp4v와 H.264의 대응 contact sheet를 메모리로 표시해 확인했다.
- **0/120/239**는 같은 위치의 병 band 세부 영역을 원래 픽셀 크기로 나란히 확인했다.
- 대표 표본의 병 위치·윤곽·움직임·가시적인 파손/이물 외관 특징은 유지됐으며 심각한 새로운 블록 노이즈·가림·구조 변형은 발견되지 않았다.
- Chrome의 첫 프레임과 반복 재생 후 실제 화면 screenshot도 확인했다. 플레이어 controls·일시적 로딩 UI는 영상 파일의 픽셀이 아니다.

**240개 전수 육안 검수가 아니다.** 자동 전수 비교와 표본 육안을 구분한다. 실제 픽셀 차이가 존재하므로 작은 결함의 완벽한 무손실 보존, 모델 점수·검출 성능의 동일성까지 보장하지 않는다. PSNR을 임의 합격 임계값으로 사용하지 않았다. 모델 성능 검증은 후속 ROI 단계의 별도 과제다.

## 7. 범례·메타데이터·Ground Truth 격리

이미 범례가 제거된 MP4만 인코더 입력으로 사용했다. 클래스를 읽어 병·프레임을 선택하지 않았다. 정답 UI가 재등장할 새 렌더링 단계는 없다.

- 전체 프레임의 하단 내부 `y=448:480` 채널 범위: B=12~16, G=20~23, R=26~29.
- 해당 영역의 프레임별 공간 표준편차 최대: B=0.299276, G=0.065945, R=0.072122. mp4v의 완전 단색과 달리 미세한 압축 변동이 존재한다.
- 변환 이력·전수 하단 화소 검사·9개 시점 실제 영상 검수에서 기존 클래스명 범례 재출현은 발견되지 않았다. 임의 OCR 보장으로 확대하지 않는다.
- 상단의 중립 프로젝트명·합성 시뮬레이션 설명은 남아 있다. 평가 클래스나 개별 정답 표시는 표본에서 발견되지 않았다.
- 출력 파일명은 중립적이다. ffprobe의 `format.filename`은 도구가 보고한 입력 경로이지 영상에 내장한 경로 태그가 아니다.
- 비디오 stream **1개**, 오디오·자막·첨부·chapter 없음.
- 실제 stream tags: `language=und`, `handler_name=VideoHandler`, `encoder=Lavc63.1.102 libx264`.
- 실제 format tags: `major_brand=isom`, `minor_version=512`, `compatible_brands=isomiso2avc1mp41`, `encoder=Lavf63.1.102`.
- 클래스명·정답 경로는 확인한 파일명·태그에 없다. 원본 메타데이터를 복사하지 않았다.

외부 Ground Truth의 파일 목록·라벨·이미지·마스크는 접근·복사·수정 **0건**이다. 원본 데이터셋 파일도 이번 변환에 사용하지 않았다.

## 8. 실제 Chrome 검증

기존 `scripts/verify_conveyor_browser.mjs`의 CLI 입력 인자를 유지하며 검증 범위만 확장했다. 기존 mp4v 실패 자료는 수정·삭제하거나 다시 성공으로 해석하지 않았다.

추가 계측: src 지정 전 loadedmetadata/loadeddata/playing/pause/seeking/seeked/ended/error 이벤트, 첫 프레임·seek별 canvas fingerprint, pause 후 400ms 시간 정지, 0/2/4/6/7.9초 seek, 반복 재생 이벤트와 416 응답.

### 8.1 격리와 실제 표시

- 실제 브라우저: **Chrome/155.0.8059.82**, headless Chromium.
- 임시 localhost 서버와 새 임시 프로필 사용. 개인 프로필·쿠키·계정 미사용.
- 외부 요청은 폐쇄 localhost proxy/DNS 제한과 CDP Fetch allowlist로 차단. 관측된 페이지 외부 요청 **0건**.
- 운영 FastAPI·React는 변경하지 않았다. 기존 제한 실행 환경의 GPU 기동 문제를 재현하지 않도록 승인된 실행 경계에서 시작했으며 Chrome 자체 sandbox는 끄지 않았다.
- loadedmetadata/loadeddata 발생. 실제 `videoWidth=1920`, `videoHeight=480`, `duration=8`, 최초 readyState=4.
- 첫 프레임 decodedFrames=4, canvas pixel min/max=0/255, 실제 screenshot에서 병 영상 표시 확인.
- 재생 후 currentTime=**0.609136초**, decodedFrames=22, droppedFrames=0.
- `canPlayType()`는 참고용이다. 실제 이벤트·화면·시간 진행을 판정 근거로 사용했다. 참고로 스크립트의 H.264 지원 조회 문자열은 level 4.0이고 실제 파일은 ffprobe로 확인한 level 3.1이다.

### 8.2 pause·seek·종료·loop

| 항목 | 실제 결과 |
|---|---|
| play() / playing | 성공·이벤트 관측 |
| pause | paused=True, **0.609694초**가 400ms 후에도 동일 |
| seek 0초 | seeking/seeked 발생, currentTime=0, 화면 checksum=1000399097 |
| seek 2초 | seeking/seeked 발생, currentTime=2, 화면 checksum=1467117774 |
| seek 4초 | seeking/seeked 발생, currentTime=4, 화면 checksum=2807219145 |
| seek 6초 | seeking/seeked 발생, currentTime=6, 화면 checksum=987779960 |
| seek 7.9초 | seeking/seeked 발생, currentTime=7.9, 화면 checksum=323687445 |
| 종료 | currentTime=8, ended=True, **ended 이벤트 발생** |
| 반복 | 7.8초에서 loop 재생 후 0초 seek/seeked/playing 관측, **0.503611초**로 진행 |
| 두 번째 재생 | playing 재발생·decodedFrames 증가 확인 |
| 디코딩 오류 | video.error=null, error 이벤트 0건 |

5개 seek 모두 정상 프레임을 얻었고 canvas checksum이 서로 달라 실제 영상 데이터 갱신을 확인했다. 이는 브라우저의 시점 이동·디코딩 검증이며 **OpenCV와 브라우저의 완벽한 프레임 동기화 검증이 아니다**.

### 8.3 HTTP 전달

| 요청 | 응답 |
|---|---|
| 실제 Chrome `GET /` | 200 |
| 실제 Chrome `GET /clip.mp4`, `Range: bytes=0-` | **206 Partial Content** |
| Content-Type | **video/mp4** |
| Accept-Ranges | bytes |
| Content-Range | **bytes 0-1542932/1542933** |
| Content-Length | 1,542,933 |
| Node의 별도 범위 초과 Probe `bytes=1542933-` | **416**, `Content-Range: bytes */1542933` |

416은 Chrome의 자동 요청이 아니라 Node fetch의 별도 Probe임을 구분한다. favicon 404는 영상 실패가 아니다. 전체 영상이 버퍼링돼 이후 seek마다 추가 Range 요청이 필요하지 않았다.

임시 서버의 성공이 향후 FastAPI Range/라우터/CORS 구현의 성공을 증명하지 않는다. 스크립트 결과 **15개 checks 모두 True**, `status=BROWSER_PASS`다. 종료 시 서버 closed와 브라우저 exit를 확인했으며 해당 임시 프로필에 속한 Chrome 프로세스 **0개**도 별도 조회로 확인했다.

## 9. H.264 Grab 정확성 사전 검증

전체 순차 디코딩에서 확보한 기준 배열과 새 decoder의 랜덤 seek를 비교했다. 실제 VideoFileSource나 API는 만들지 않았다.

| frame_index | timestamp(ms) | 다음 POS_FRAMES | 반복 결과 | 기준 배열과 화소 비교 |
|---:|---:|---:|---|---|
| 0 | 0 | 1 | 3/3 PASS | 완전 동일 |
| 60 | 2000 | 61 | 3/3 PASS | 완전 동일 |
| 120 | 4000 | 121 | 3/3 PASS | 완전 동일 |
| 180 | 6000 | 181 | 3/3 PASS | 완전 동일 |
| 239 | 7966.6667 | 240 | 3/3 PASS | 완전 동일 |

모든 반환 크기는 `(480,1920,3)`, **15/15 동일**이었다. 마지막 프레임 다음 읽기는 모두 EOF. 별도 `set(POS_FRAMES,240)`는 True였지만 실제 `read()`는 False였다. 즉 OpenCV 위치 설정 반환값만으로 유효 프레임으로 인정하지 않았다. 이는 API의 범위 초과 HTTP 오류 처리를 구현한 것이 아니다.

모든 decoder 해제를 확인했다. 결과는 해당 파일·OpenCV 5.0.0·지정 인덱스에 한정된다. MVP의 정확성 기준은 **순차 디코딩**으로 유지하고 다른 영상/VFR/코덱의 seek까지 일반화하지 않는다.

## 10. 재현 명령과 증거 위치

실제 변환·검증 명령:

```powershell
& 'C:/Users/USER/miniconda3/envs/vision-insight/python.exe' scripts/convert_conveyor_h264.py --ffmpeg C:/Users/USER/AppData/Local/VisionInsight/tools/ffmpeg/9.0.2-essentials/distribution/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe --ffprobe C:/Users/USER/AppData/Local/VisionInsight/tools/ffmpeg/9.0.2-essentials/distribution/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe --clean data/outputs/videos/bottle_conveyor_clean_mp4v_1920x480_8s.mp4 --original data/outputs/videos/mixed_bottle_conveyor_single_lane_1920x480_8s.mp4 --output data/outputs/videos/bottle_conveyor_clean_h264_1920x480_8s.mp4 --evidence-dir C:/Users/USER/AppData/Local/Temp/vision_day5_h264_rsct0gdv
```

생성 스크립트는 기존 출력이 있으면 실패한다. 재실행을 위해 결과를 자동 삭제하거나 덮어쓰지 않는다.

실제 브라우저 검증 명령:

```powershell
& 'C:/Program Files/nodejs/node.exe' scripts/verify_conveyor_browser.mjs data/outputs/videos/bottle_conveyor_clean_h264_1920x480_8s.mp4 'C:/Program Files/Google/Chrome/Application/chrome.exe' C:/Users/USER/AppData/Local/Temp/vision_day5_h264_browser_391ea9e86848496ead1a6e6fa5218bd9
```

외부 임시 증거:

- `%TEMP%/vision_day5_h264_rsct0gdv/`: 사전·사후 보호 manifest, `encode.json`, `ffprobe.json`, `frame_pts.json`, `ffmpeg_decode.json`, `h264_validation.json`.
- `%TEMP%/vision_day5_h264_browser_391ea9e86848496ead1a6e6fa5218bd9/`: `browser_validation.json`, `browser-first.png`, `browser.png`, stderr 및 격리 프로필.
- FFmpeg 사용자 도구 루트: ZIP·게시 checksum 파일·배포본·`installation.json`.

외부 임시 증거는 영구 보관을 보장하지 않는다. 대응 영상 contact sheet와 세부 시각 비교는 메모리에서 수행했고 신규 검사/캡처 레코드를 만들지 않았다.

## 11. 변경 범위·보호 및 정적 점검

이번 프로젝트 산출물은 다음 4개다.

1. 신규 `data/outputs/videos/bottle_conveyor_clean_h264_1920x480_8s.mp4` 1개.
2. 신규 `scripts/convert_conveyor_h264.py`.
3. 제한적 수정 `scripts/verify_conveyor_browser.mjs`.
4. 신규 본 보고서 `docs/day5-step2a-h264-browser-validation.md`.

기존 `data/outputs/**` ignore 유지. 바이너리나 영상을 Git에 강제로 추가하지 않았다.

사전 보호 manifest **4,506개 파일** 중 **4,505개 SHA256 동일**, 승인된 브라우저 검증 스크립트 1개만 변경. 예상하지 못한 변경·누락 **0건**. 최초 원본·clean mp4v·원본 렌더러/metadata·운영 검사/로그 JSONL·모델·임계값·기존 E2E/READY/잠금·기존 문서·발표/PPT의 사전 상태를 보존했다. 다른 에이전트의 기존 작업을 복원하거나 수정하지 않았다.

Python 메모리 내 syntax compile 및 Node `--check` PASS. 이번 파일 범위 `git diff --check`와 신규 미추적 파일의 별도 공백 검사 PASS. 전체 `git diff --check`는 기존 발표 문서 3개(`presentation-review-checklist.md`, `presentation-script.md`, `slide-outline.md`)의 trailing whitespace로 FAIL이며 타 에이전트 파일을 수정하지 않았다.

전체 pytest는 실행하지 않았다. **1175 PASS / 0 FAIL / 4 SKIP / 경고 2건은 이전 공식 기준**이며 이번 영상 검증의 신규 결과가 아니다.

실제 Gemini API 요청 **0회**, Ground Truth 열람·수정 **0건**, 운영 JSONL·모델·임계값 변경 **0건**, 신규 검사·Agent 분석·READY·잠금 **0건**, Git add/commit/push/reset **0건**이다. Python/Conda·OpenCV 교체·시스템 PATH 영구 변경·레지스트리 설정 작업도 하지 않았다.

## 12. Phase B 인수인계와 남은 한계

권장 후보:

- `video_id`: **VID-000001**.
- 등록 후보: `data/outputs/videos/bottle_conveyor_clean_h264_1920x480_8s.mp4`.
- `source_revision`: **f1c5a12ee25672bfb8241311ecd16f7fefb7e549cb43a44a81bb4858ea9f9a2d**.
- 고정 계약: 1920×480, 30 FPS, 240프레임, 8초, frame_index 0~239.
- 백엔드 Grab와 Chrome Live View의 **입력 후보 승인 가능**. 실제 레지스트리 등록은 하지 않았다.

남은 한계:

1. 실제 카메라·산업 설비 영상이 아닌 합성 시뮬레이션이다.
2. 원본 대비 손실 압축 차이가 있으며 모든 미세 결함 픽셀의 동일성은 보장하지 않는다.
3. 기존 83장 정적 이미지 평가 성능을 영상 ROI 성능으로 해석할 수 없다. 이번에는 PatchCore 추론을 하지 않았다.
4. Chrome headless의 해당 버전·로컬 HTTP 환경 검증이다. 다른 브라우저/기기·실제 React·운영 FastAPI·배포 환경은 NOT TESTED.
5. 브라우저 currentTime과 서버 frame_index의 정확한 매핑·동시 사용자·캡처 보관·보안·CORS는 Phase B 이후 구현·검증 대상이다.
6. 새 FFmpeg 도입은 기존 OpenCV avc1/OpenH264 문제의 해결을 뜻하지 않는다.

다음 권장 단계는 별도 사용자 승인 후 **Day5 Step 2 Phase B: VideoFileSource 및 수동 Grab API**다. 이번에는 구현을 시작하지 않고 영상 준비 완료와 검증 결과를 보고한 뒤 종료한다.
