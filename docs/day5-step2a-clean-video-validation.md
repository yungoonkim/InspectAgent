# Day5 Step 2-A — 깨끗한 영상 파생본 준비 및 인코더 사전 검증

- 작업일: 2026-10-17
- 최종 상태: **BLOCKED — 확인한 H.264 인코더의 초기화 실패**
- 깨끗한 파생 영상: **미생성**
- 검사 입력 후보: **NOT APPROVED**
- 파생본 전체 프레임·브라우저 재생·Grab 정확성: **NOT TESTED**
- 실제 Gemini API / 검사 / Agent 분석 / READY / 실행 잠금 생성: **0건**

## 1. 범위와 중단 근거

사용자는 원본 보존, 범례 없는 파생본 1개 제작, 전체 프레임 안전성 및 브라우저 검증을 승인했다. 외부 바이너리 설치·다운로드는 승인하지 않았으며, 필요한 인코더가 없어 설치 승인이 필요한 경우 중단하도록 지정했다.

기존 Day4/Day5 기록과 운영 코드는 수정하지 않았다. 이전 전체 pytest **1175 PASS / 0 FAIL / 4 SKIP / 경고2**는 과거 결과다. 이번에는 pytest를 실행하지 않았다.

## 2. 원본 확인과 보존

원본 상대경로:

`data/outputs/videos/mixed_bottle_conveyor_single_lane_1920x480_8s.mp4`

이번 읽기 전용 점검에서 파일 크기 2,800,935 bytes, OpenCV open 성공, 1920×480, FPS30, 프레임 수240을 확인했다. 첫 프레임 및 239번 프레임이 디코딩됐고 그 다음 읽기는 EOF였다. reader는 finally에서 해제했다. 이번 원본 점검은 240개 전체 프레임 디코딩이 아니다.

기존 컨테이너·생성 기록은 MP4 / MPEG-4 Part 2(`mp4v`), 길이8초다. 새 파생본의 codec/pixel format/profile/level을 검증한 것으로 해석하지 않는다.

| 보호 파일 | 사전 및 사후 동일한 SHA256 |
|---|---|
| 원본 MP4 | `daefc8f14912e2a1e1fac77823f7eee97572e47722d3276f93ea3530b1cdda82` |
| `data/outputs/videos/render_conveyor.py` | `31d46f2f2aefdd03bfeb31be1f9296d562e45a60525d51c4dbe30a4d123966e5` |
| `data/outputs/videos/render_metadata.json` | `f0aa2bc3a748d793ffa431c3b4f682008674629578ea27aae6778fcd719eb372` |
| `data/outputs/videos/render_metadata_single_lane.json` | `e6d557a1aa8a9df4875771093b1d30c8a52445ad3d742b0427ed1b9826470182` |

## 3. 범례 제거 방식의 설계 근거

기존 `render_conveyor.py:64`는 병 합성 영역을 `y=107:414`로 제한한다. 85행의 하단 레일은415~441행이며, 97~101행은 baseline y=468에 SOURCE MIX, 클래스명 범례와 합성 표시를 그린다. 배경색은79행의 BGR=(17,22,29)다.

Phase A에서 원본 프레임의 하단 범례를 시각적으로 확인한 기록이 있다. 이번에는 생성 코드를 다시 읽어 원본을 검사 입력으로 승인할 수 없음을 확인했다.

권장 방식은 선택안A다. **원본을 디코딩한 전체240프레임의 `frame[443:480, 0:1920]`만 중립 배경으로 교체**한다. 해상도를 유지하고 상단 합성 영상 표시는 남긴다. 병 합성 영역이나 등장 순서에는 직접 손대지 않는다.

이는 재개 후 실행할 설계안이다. 이번에는 영역 교체나 인코딩을 수행하지 않았다. 인코딩 전 보존 영역의 픽셀 동일성과 재압축 후 외관 보존, 전체 프레임의 안전성은 미검증이다. 클래스명에 따른 병·프레임 선택, 원본 데이터셋 이미지나 외부 정답 조회는 필요하지 않다.

## 4. 인코더의 실제 실패

확인한 기존 환경은 다음과 같다.

- Miniconda `vision-insight`의 OpenCV 5.0.0. FFmpeg 백엔드 있음. avcodec61.19.100 / avformat61.7.100.
- PATH, 확인한 Miniconda 환경의 Library/bin·Scripts 및 표준 설치 후보에서 ffmpeg/ffprobe 실행 파일을 찾지 못했다. 컴퓨터 전체에 없다는 뜻은 아니다.
- 해당 Python 환경에서 imageio_ffmpeg, PyAV, Playwright, Selenium을 찾지 못했다.
- Google Chrome, Microsoft Edge 및 Node v24.11.0의 내장 WebSocket은 존재한다. 새 설치는 수행하지 않았다.

프로젝트 밖 임시 경로를 대상으로 기존 OpenCV의 H.264 인코더 초기화를 확인했다.

```python
writer = cv2.VideoWriter(
    temporary_probe_path,
    cv2.CAP_FFMPEG,
    cv2.VideoWriter_fourcc(*"avc1"),
    30.0,
    (1920, 480),
)
```

실제 로그:

```text
Failed to load OpenH264 library: openh264-2.5.0-win64.dll
[libopenh264] Unable to create encoder
Could not open codec libopenh264, error: Unspecified error (-1313558101)
VIDEOIO/FFMPEG: Failed to initialize VideoWriter
```

`writer.isOpened()`는 False였다. finally에서 release했고, 임시 probe 동영상도 생성되지 않았다. DLL 검색 경로·종속 DLL·아키텍처 등 Windows loader 내부 원인은 확정하지 못했다. 확인한 실행 환경에서 OpenH264를 이용할 수 없다는 범위의 결과다.

사용자의 중단 조건에 따라 라이브러리나 FFmpeg를 다운로드·설치하지 않고 영상 생성을 중단했다. 다른 코덱으로 임의 변경해 후보를 승인하지 않았다.

## 5. 검증 상태

| 항목 | 결과 |
|---|---|
| 현재 OpenCV H.264 인코더 초기화 | FAIL |
| `bottle_conveyor_clean_1920x480_8s.mp4` 생성 | NOT CREATED |
| 파생본 SHA256·코덱·pixel format·profile/level | NOT TESTED |
| 파생본 audio/subtitle/attachment/태그 검사 | NOT TESTED |
| 파생본 전체240프레임 순차 디코딩 | NOT TESTED |
| 대응 프레임·중복/누락·화소 차이/PSNR | NOT TESTED |
| 지정9개 시점 파생본 육안 검수 | NOT TESTED |
| 전체 프레임 범례 제거 확인 | NOT TESTED |
| Chromium 표시·재생·pause/seek/end/loop | NOT TESTED |
| 순차 디코딩과 랜덤 seek 비교 | NOT TESTED |
| 반복 Grab 재현성 | NOT TESTED |
| 안전한 검사 입력 후보 | NOT APPROVED |

원본의 OpenCV 디코딩 성공은 파생본 인코딩·브라우저 재생 성공의 증거가 아니다. 브라우저 실행 파일의 존재 역시 재생 성공을 뜻하지 않는다. 파생본이 없어 이번에는 브라우저를 시작하지 않았다.

## 6. 재개에 필요한 승인과 후속 절차

이미 설치된 ffmpeg/ffprobe 또는 호환 OpenH264 라이브러리의 실제 경로를 제공받을 수 있다면 먼저 이용 가능 여부를 확인한다. 사용할 기존 도구가 없다면 H.264 인코더를 포함한 FFmpeg/ffprobe 등의 도입에 별도 사용자 승인이 필요하다.

도구가 확보되면 원본과 출력 경로 충돌을 재확인하고 다음을 수행한다.

1. 하단 고정 UI 영역만 교체하고 전체240프레임을 원래 순서로 인코딩한다.
2. 가능하면 MP4/H.264/yuv420p를 사용한다. 명시적인 영상 스트림만 만들고 원본 태그·음성·자막·첨부를 복사하지 않는다.
3. 원본과 파생본의 전체 대응 프레임을 비교한다. 직접 교체한 영역과 재압축에 따른 보존 영역의 차이를 구분해 측정한다. 임의 PSNR 기준으로 외관 보존을 보장하지 않는다.
4. 기존 범례 영역은 전체 프레임을 자동 검사하고 지정9개 시점은 육안 확인한다. 전수 자동 검사와 표본 육안 검사를 구분한다.
5. 0/60/120/180/239번에서 순차·seek·반복 추출·EOF·해제를 검증한다.
6. 설치된 Chrome 등을 사용해 임시 localhost 서버와 독립 HTML video에서 실제 표시·재생·pause·seek·end·loop를 확인한다. 운영 FastAPI와 React는 변경하지 않는다.

중립 ID 제안은 `VID-000001`, 출력 경로 제안은 `data/outputs/videos/bottle_conveyor_clean_1920x480_8s.mp4`다. 이번에 등록하거나 생성하지 않았다. 향후 source_revision은 최종 MP4의 콘텐츠 SHA256으로 하고 콘텐츠가 바뀌면 revision도 변경한다. 외부 API에 원본 경로나 클래스명을 전달하지 않는다.

## 7. 보호 파일과 산출물

기존 backend/scripts/tests/docs, 모델, 검사·로그 JSONL, manual_validation 회차, 기존 영상 디렉터리, 발표 자료 등 **4,500개 파일의 SHA256은 사전/사후 모두 동일**했다. 기존 미추적 파일, `.tmp_measurement_regressions/`, 발표·Gamma 관련 변경을 보존했다. 외부 평가 경로의 목록·본문·라벨·마스크에는 접근하지 않았다.

이번 프로젝트 내 산출물은 본 보고서1개다. 사전 해시 manifest는 프로젝트 밖 `%TEMP%/vision_day5_step2a_qwwcdl78/protected_before.json`에 있다. 파생 영상·영구 생성 스크립트·테스트 코드는 추가하지 않았다.

실제 Gemini API 요청0회, 운영 JSONL·모델·임계값 변경0건, READY·잠금·실제 E2E 생성0건, Git add/commit/push/reset 0건이다. VideoFileSource, Grab API, ROI, PatchCore 연동은 구현·실행하지 않았다.
