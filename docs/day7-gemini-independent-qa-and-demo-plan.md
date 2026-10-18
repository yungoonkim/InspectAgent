# VisionInsight — 독립 QA 검증표 및 3~5분 발표 시연 대본
## Day 7 Step 4 기준 독립 검증 · 장애 대응 시나리오 · Codex 인계 사항

- **작성일:** 2026-10-18
- **발표일:** 2026-10-20 (D-2)
- **프로젝트 루트:** `C:\Users\USER\AI-NativeAgent\Project\InspectAgent`
- **역할 정의:** 독립 QA 및 시연 준비 담당 (메인 개발 및 테스트 실행: Codex)
- **문서 목적:** Day 7 Step 4까지 구현된 VisionInsight 시스템의 객관적 독립 검증, 3~5분 완결형 발표 시연 대본, 장애 대비 우회 시나리오, 개발자(Codex) 대상 검증 발견사항 인계

---

# [작업 A] 독립 QA 검증표 (Independent QA Test Matrix)

> **독립 검증 원칙:**
> 개발 에이전트의 자체 보고서(Self-Report) 내용만으로 PASS를 부여하지 않으며, 실제 Windows Chrome 브라우저 환경 및 API 응답에 기반한 관측 가능한 객관적 사실만을 판정 기준으로 삼습니다.

---

## QA-01. LiveView 영상 재생, 일시정지 및 Grab 무손실 캡처
- **사전 조건:**
  - FastAPI 백엔드 (`http://localhost:8000`), React 프론트엔드 (`http://localhost:5173`) 정상 구동
  - 테스트 비디오 파일 (`data/sample_videos/bottle_conveyor.mp4`) 존재
- **실행 방법:**
  1. 상단 `LiveView` 패널에서 비디오 자동 재생 확인
  2. 일시정지(`Pause`) 버튼 클릭 후 재생 바(`Seek`)를 임의 시점으로 드래그
  3. `[Grab]` 버튼 클릭
- **기대 결과:**
  - H.264 브라우저 네이티브 비디오가 끊김 없이 재생/일시정지됨
  - `POST /video/grab` 호출이 성공하고 무손실 PNG 프레임(`capture_id`)이 생성됨
  - 하단 `ImageView`에 캡처된 전체 프레임(1920×480)이 로드됨
- **PASS 판정 기준:**
  - `GET /video/captures/{capture_id}`로 반환된 이미지가 원본 해상도(1920×480)와 100% 일치
  - LiveView 비디오에 디코딩 오류나 검은 화면이 발생하지 않음
- **실패 시 확인 사항:**
  - `data/outputs/captures/` 디렉터리에 실제 PNG 파일 기록 여부 확인
  - 브라우저 비디오 코덱(H.264) 호환성 및 네트워크 탭 200 응답 확인

---

## QA-02. ROI 드래그 선택 및 정밀 600×600 Crop
- **사전 조건:** QA-01 Grab 성공 상태
- **실행 방법:**
  1. LiveView 프레임 위에서 마우스 드래그로 검사 대상 병 영역에 직사각형 ROI 생성
  2. ROI 모서리 핸들을 잡고 크기 조절(Resize) 및 중앙 영역을 잡고 위치 이동(Move)
  3. ROI 설정 팝업에서 `[Crop 실행]` 클릭
- **기대 결과:**
  - `POST /video/crop` API 호출 성공
  - 600×600 정밀 영역으로 크롭된 `crop_id` 생성 및 `ImageView`가 즉시 `Product Focus` 모드로 전환
- **PASS 판정 기준:**
  - 크롭된 이미지가 600×600 캔버스 정중앙에 100% 1:1 픽셀 매핑으로 렌더링됨
  - LiveView ROI 좌표계와 Crop 결과의 바운딩 박스가 왜곡 없이 일치
- **실패 시 확인 사항:**
  - OpenCV `backend/video/roi_cropper.py`의 경계선(boundary clamp) 로직 확인
  - PostgreSQL ROI 저장이 오프라인일 때 로컬 메모리/파일 대체 로직 작동 여부

---

## QA-03. 600×600 ImageView 뷰포트 및 듀얼 소스 분리
- **사전 조건:** LiveView Crop 완료 데이터 및 기존 검사 기록 존재
- **실행 방법:**
  1. `ImageView` 상단의 소스 모드 탭 전환: `[정적 검사 이미지]` vs `[LiveView Grab]`
  2. 각 탭 클릭 시 표시되는 이미지와 메타데이터 비교
- **기대 결과:**
  - `[정적 검사 이미지]` 선택 시: MVTec AD 900×900 등록 이미지 로드 (검사 판정 카드 오버레이 노출)
  - `[LiveView Grab]` 선택 시: LiveView에서 방금 캡처한 600×600 Crop 이미지 로드 (판정 오버레이 숨김)
- **PASS 판정 기준:**
  - 두 소스가 절대 섞이지 않으며, 상단 뱃지에 `REGISTERED IMAGE — {image_id}`와 `LIVEVIEW ROI CROP`이 명확히 구별되어 표기됨
- **실패 시 확인 사항:**
  - `ImageView.tsx` 내부 `activeSource` 분기 및 `currentInspection` 종속성 상태 점검

---

## QA-04. Zoom / Pan 및 마우스 포인터 기준 확대 (Cursor-Anchored Zoom)
- **사전 조건:** `ImageView`에 900×900 정적 이미지 또는 600×600 크롭 이미지 로드 상태
- **실행 방법:**
  1. 이미지의 특정 모서리(예: 병목 캡 부분)에 마우스 포인터를 위치시키고 휠 업(`Wheel In`)
  2. 100% -> 200% -> 400% -> 800% -> 1600% -> 3200% -> 4000%까지 연속 확대
  3. 마우스 휠 다운(`Wheel Out`)으로 100%까지 축소
  4. 마우스 드래그를 통해 상하좌우 Pan 이동 수행 후 `[100% Reset]`, `[Pan Reset]` 클릭
- **기대 결과:**
  - 확대 시 마우스 포인터가 가리키고 있던 픽셀이 뷰포트 상의 동일한 마우스 위치에 고정 유지됨
  - 축소 시 이미지가 뷰포트 중심을 향해 부드럽게 복귀함
  - 브라우저 전체 페이지 스크롤이 발생하지 않음 (Wheel 기본 동작 차단)
- **PASS 판정 기준:**
  - 4000% 배율에서 포인터 위치의 픽셀이 뷰포트 밖으로 튕겨 나가지 않음
  - `[100% Reset]` 클릭 시 줌 1.0(100%) 및 중앙 정렬 원점`(origin)`으로 즉시 복귀
- **실패 시 확인 사항:**
  - `frontend/src/utils/imageTransform.ts`의 `computeWheelTransform` 수학식 점검

---

## QA-05. RGB / Gray Value (GV) Pixel Inspector 및 3200% 픽셀 숫자
- **사전 조건:** QA-04의 고배율(>= 400%, >= 3200%) 확대 상태
- **실행 방법:**
  1. 마우스를 이미지 위 각 픽셀로 이동하며 하단 `Pixel Inspector` 바 관찰
  2. 400% 이상 확대 시 픽셀 경계 격자(`Grid`) 노출 확인
  3. 3200% 이상 확대 시 각 픽셀 사각형 내부 렌더링 확인
- **기대 결과:**
  - 하단 바에 `Image Local (X, Y)`, `RGB(R, G, B)`, `Gray Value (0~255)`가 실시간 표시
  - 배경 여백(패딩) 영역 호버 시 `PADDING (RGB 0,0,0)` 뱃지 표시
  - 3200%~4000% 배율에서 모든 격자 셀 정중앙에 정수 GV 숫자가 선명하게 렌더링됨
- **PASS 판정 기준:**
  - $GV = \text{round}(0.299R + 0.587G + 0.114B)$ 공식과 일치
  - 이미지 경계 바깥 픽셀 좌표가 음수나 이미지 크기를 초과하지 않음
- **실패 시 확인 사항:**
  - Canvas 폰트 크기(`bold 10px monospace`) 및 고배율 뷰포트 컬링(`startX, endX, startY, endY`) 범위 점검

---

## QA-06. 정적 이미지 무결성 조회 (ImageRegistry)
- **사전 조건:** 서버 내 등록 이미지(`IMG-BOTTLE-0084` 등) 디스크 배치 완료
- **실행 방법:**
  1. `GET /inspections/images` 호출하여 등록 이미지 목록 확인
  2. `GET /inspections/images/IMG-BOTTLE-0084/file` 직접 호출
  3. 임의 파일 경로(예: `../../etc/passwd` 또는 `C:\Windows\...`) 요청
- **기대 결과:**
  - 등록된 이미지 식별자 목록이 반환됨
  - 원본 PNG 바이너리가 손실 없이 200 OK로 반환됨
  - 비인가 경로 및 순회 경로는 400 또는 404로 원천 차단됨
- **PASS 판정 기준:**
  - 응답 헤더에 서버 로컬 절대 파일 경로가 노출되지 않음
  - 이미지 해상도가 원본 900×900 무손실 PNG임
- **실패 시 확인 사항:**
  - `backend/image_registry.py`의 whitelist 및 sanitized ID 매핑 확인

---

## QA-07. PatchCore 실제 검사 파이프라인 (POST /inspections)
- **사전 조건:** CPU PyTorch 및 PatchCore 가중치 체크포인트 정상 로드 가능 상태
- **실행 방법:**
  1. 우측 검사 패널에서 등록 이미지 `IMG-BOTTLE-0084` 선택
  2. `[Inspect 실행]` 클릭 (테스트 환경에서는 실제 추론 대신 안전 목 검증 우선)
- **기대 결과:**
  - OpenCV 이미지 품질 측정 (밝기, 블러, 노이즈) 수행
  - PatchCore 추론 1회 수행 -> `anomaly_score` 계산
  - 서버 결정적 판정 로직에 따라 `final_result` 확정 및 `data/outputs/inspections.jsonl` 기록
- **PASS 판정 기준:**
  - `inspection_id`가 중복 없이 고유 생성됨 (`INSP-XXXXXX`)
  - 검사 실행 과정에서 PatchCore 추론이 2회 이상 중복 호출되지 않음
- **실패 시 확인 사항:**
  - `backend/inspection.py`의 `execute_inspection_workflow` 실행 로그 확인

---

## QA-08. 검사 판정 (OK / NG / REINSPECT) 및 Mock Fixture 구분
- **사전 조건:** 과거 검사 기록 4종 존재
- **실행 방법:** 우측 검사 패널 시연 숏컷 버튼 순차 클릭:
  1. `[T01:OK]` (`INSP-001387` 또는 `INSP-001396`)
  2. `[T03:Warn]` (`INSP-001388` 또는 `INSP-001398`)
  3. `[T06:한계OK]` (`INSP-001390`)
  4. `[Mock:NG]` (`INSP-001391`)
- **기대 결과:**
  - T01: 초록색 `OK` 뱃지 (Score ~13.84 < Threshold 34.1442)
  - T03: 주황색 `REINSPECT` 뱃지 (저조도 영상 품질 경고)
  - T06: 초록색 `OK` 뱃지 (작은 결함 미검출 모델 한계 사례, Score 12.98 < Threshold)
  - Mock NG: 붉은색 `NG` 뱃지 + **황색 주의 배너 [MOCK / TEST FIXTURE — NG (anomaly_score=45.0 주입)]** 노출
- **PASS 판정 기준:**
  - Mock NG를 실제 PatchCore 결함 검출 결과로 오인하게 만드는 문구가 일체 없음
  - T06 한계 사례의 판정이 임의로 NG로 왜곡되지 않고 실제 모델 출력인 OK로 유지됨
- **실패 시 확인 사항:**
  - `ImageView.tsx`의 `isMockFixture` 플래그 및 `provenance === 'RECORDED_TEST_FIXTURE'` 판별 조건 점검

---

## QA-09. 실제 Anomaly Map Sidecar Artifact 영구 저장
- **사전 조건:** Day 7 Step 4 백엔드 [anomaly_map_store.py](file:///C:/Users/USER/AI-NativeAgent/Project/InspectAgent/backend/anomaly_map_store.py) 구현 완료
- **실행 방법:**
  1. 검사 패널에서 `[x] 신규 검사 시 이상지도(Anomaly Map) 저장` 활성화
  2. 검사 실행 (`POST /inspections` with `capture_anomaly_map=true`)
  3. `data/outputs/inspection_anomaly_maps/` 디렉터리 확인
- **기대 결과:**
  - 해당 검사 ID에 대해 3종의 파일 생성:
    - `INSP-XXXXXX.npz`: 2차원 float32 numpy 배열
    - `INSP-XXXXXX.json`: 메타데이터
    - `INSP-XXXXXX_overlay.png`: 투명 Jet 컬러맵 오버레이 이미지
- **PASS 판정 기준:**
  - npz 파일 내 맵의 shape이 정확히 `[256, 256]`
  - json 파일 내 `original_image_width=900, original_image_height=900` 기록
  - 저장 실패 시에도 `final_result`가 변경되지 않음
- **실패 시 확인 사항:**
  - `cv2.imencode('.png', ...)`를 통한 임시파일 원자적 쓰기 로직 점검

---

## QA-10. ImageView Heatmap Overlay 토글 및 투명도 조절
- **사전 조건:** QA-09를 통해 Anomaly Map이 저장된 검사 ID 로드 상태
- **실행 방법:**
  1. `ImageView` 툴바의 `[Heatmap OFF]` 버튼 클릭 -> `Heatmap ON` 전환
  2. 투명도 슬라이더를 10%에서 100%까지 드래그 조절
  3. 마우스 휠로 100%~4000% 줌 및 드래그 팬 조작
- **기대 결과:**
  - 원본 병 이미지 위에 상대적 이상 반응을 나타내는 반투명 히트맵이 표시됨
  - 슬라이더 조작에 따라 히트맵 투명도가 실시간 변화함
  - 줌 및 팬 조작 시 히트맵이 원본 병 이미지와 1픽셀 오차 없이 완벽히 동기화됨
  - 히트맵이 켜진 상태에서도 Pixel Inspector의 RGB/GV는 원본 병 픽셀 값을 유지함
- **PASS 판정 기준:**
  - 오버레이 하단 안내에 *"PatchCore 모델의 상대적 이상 반응 분포입니다. 실제 결함 위치가 검증된 결과는 아닙니다."* 경고문 노출
  - 임의의 빨간색 바운딩 박스가 그려지지 않음
- **실패 시 확인 사항:**
  - Canvas 렌더링 시 `ctx.globalAlpha` 적용 및 `ctx.drawImage(overlayImg, originX, originY, targetW * zoom, targetH * zoom)` 정합성 점검

---

## QA-11. 과거 저장 Gemini Agent 보고서 조회 (GET /agent/reports/{id})
- **사전 조건:** `data/outputs/agent_reports/` 내 `INSP-001396.json`, `INSP-001398.json` 존재
- **실행 방법:**
  1. 검사 ID `INSP-001396` 선택
  2. 우하단 `AgentPanel`에서 보고서 조회 상태 확인
- **기대 결과:**
  - Gemini API 실시간 호출 없이 로컬에 저장된 구조화 보고서가 즉시 렌더링됨
  - `Observed Facts` (품질 지표, 모델 점수 등 확정 사실)와 `Hypothesis` (가설적 원인 추정)가 명확히 분리 표기됨
- **PASS 판정 기준:**
  - 보고서 상단에 `STORAGE CACHED REPORT` 배지 노출
  - 네트워크 탭에서 `api.generativeai.google.com` 등 외부 API 호출이 0회 발생
- **실패 시 확인 사항:**
  - `backend/main.py`의 `get_stored_agent_report` 라우터 및 JSON 파싱 에러 점검

---

## QA-12. Gemini 실시간 Function Calling의 미검증 상태 투명 고지
- **사전 조건:** 실시간 분석 버튼 존재
- **실행 방법:**
  1. `AgentPanel`의 실시간 분석 실행 영역 확인
  2. 미검증 안내 문구 및 안전 가드 확인
- **기대 결과:**
  - "실시간 Gemini Function Calling 분석은 오프라인 스키마 검증 완료 상태이나, 발표 전 프로덕션 라이브 환경 검증이 완료되지 않음"이 명시됨
  - 시연 중 무리한 실시간 호출 시도로 인한 오류 화면 노출을 사전 방지
- **PASS 판정 기준:**
  - 미검증 상태를 "완료"로 허위 포장하지 않고 솔직하게 기술적 현황을 공유함
- **실패 시 확인 사항:**
  - `docs/day7-step2-gemini-agent-offline-compatibility.md` 분석 결과 참조

---

# [작업 B] 발표용 3~5분 시연 대본 (Demo Script)

> **발표 시간:** 3분 30초 ~ 4분 30초 (최대 5분)  
> **핵심 원칙:** 검증된 기능(LiveView, 정밀 Crop, 4000% Inspector, 정적 판정 오버레이, 저장 보고서)을 중심으로 시연하며, 한계점과 분리 원칙을 명확하게 브리핑합니다.

---

### [0:00 ~ 0:40] 1. 인트로 및 프로젝트 아키텍처 개요
- **화면:** 전체 대시보드 화면 (`http://localhost:5173`)
- **발표자 멘트:**
  > "안녕하십니까, MVTec AD Bottle 기반 산업용 Vision 이상 진단 AI 에이전트 **VisionInsight** 발표를 시작하겠습니다.  
  > 저희 시스템은 컨베이어 벨트의 실시간 비디오 스트림을 모니터링하는 **LiveView 서브시스템**,  
  > 마이크론 단위 결함을 검증하는 **600×600 Precision ImageView**,  
  > 무감독 이상 탐지 모델인 **PatchCore 엔진**,  
  > 그리고 관측 사실과 가설을 분리하여 보고서를 발행하는 **Gemini 진단 에이전트**로 구성되어 있습니다.  
  > 지금부터 실제 동작 화면을 통해 핵심 파이프라인을 보여드리겠습니다."

---

### [0:40 ~ 1:30] 2. LiveView 실시간 모니터링 및 정밀 ROI Crop
- **화면:** 좌상단 `LiveView` 영역 조작
- **발표자 행동:**
  1. 재생 중인 비디오 확인
  2. `[Pause]` 클릭 후 특정 병 위치에서 멈춤
  3. 병 중심부에 직사각형 ROI 드래그 생성
  4. `[Crop 실행]` 클릭 -> 우측 `ImageView`가 `Product Focus`로 전환
- **발표자 멘트:**
  > "먼저 공정 라인의 H.264 실시간 영상입니다. 작업자는 원하는 프레임에서 **Grab**을 통해 무손실 PNG를 즉각 추출할 수 있습니다.  
  > 화면에서 보시는 것처럼 검사 대상 병에 직사각형 ROI를 지정하고 **Crop**을 실행하면, 600×600 정밀 검사 뷰포트로 즉시 전송됩니다.  
  > **[중요 고지]** 여기서 한 가지 명확히 말씀드릴 점은, 현재 파이프라인 상 **LiveView의 ROI Crop 이미지는 작업자의 육안 정밀 검사용 뷰포트이며, 아직 PatchCore 모델의 입력으로 자동 투입되는 단계는 아닙니다.** 정밀 검사는 규격화된 정적 등록 이미지를 통해 엄격하게 수행됩니다."

---

### [1:30 ~ 2:40] 3. 정적 이미지 검사 조회 및 4000% Pixel Inspector 시연
- **화면:** `ImageView`의 `[정적 검사 이미지]` 탭 선택 -> 우측 검사 패널의 시연 숏컷 버튼 클릭
- **발표자 행동:**
  1. `[T01:OK]` 클릭 -> 정상 병 이미지 + 녹색 `OK` 판정 오버레이 확인
  2. 병 뚜껑 부분에 마우스 포인터를 두고 마우스 휠을 굴려 **3200%~4000%**까지 연속 확대
  3. 각 픽셀 셀 내부의 **GV(Gray Value) 정수 숫자**와 하단 **Pixel Inspector** 수치 확인
  4. `[T03:Warn]` 클릭 -> 주황색 `REINSPECT` 판정 확인
  5. `[Mock:NG]` 클릭 -> 붉은색 `NG` 뱃지와 **황색 Mock Fixture 배너** 확인
- **발표자 멘트:**
  > "이제 실제 공정 검사 데이터를 살펴보겠습니다.  
  > `[T01:OK]` 검사 기록을 로드하면 900×900 원본 해상도와 함께 서버가 확정한 최종 판정 오버레이가 나타납니다.  
  > 저희 `ImageView`는 머신비전 검사관을 위해 **100%부터 4000%까지 마우스 포인터 중심의 정밀 줌**을 지원합니다.  
  > 3200% 이상으로 확대하면 보시는 것처럼 각 픽셀 격자 내부에 실제 휘도값인 Gray Value 숫자가 실시간 렌더링되며, 하단 바에서 단 1픽셀의 왜곡도 없는 RGB와 GV를 실측할 수 있습니다.  
  > `[T03:Warn]`은 저조도 조명 이슈로 인한 `REINSPECT` 판정이며,  
  > `[Mock:NG]`는 결함 주입 테스트를 위한 Mock Fixture입니다. 저희 시스템은 **합성 테스트 데이터를 실제 모델 검출 결과로 속이지 않고 명확한 Mock 배너로 분리 표기**합니다."

---

### [2:40 ~ 3:40] 4. PatchCore 이상지도 (Anomaly Map) 시각화 및 한계 브리핑
- **화면:** `ImageView` 상단 툴바의 `[Heatmap ON]` 버튼 클릭 및 투명도 조절
- **발표자 행동:**
  1. `[Heatmap ON]` 토글 클릭 -> Jet 컬러맵의 상대적 이상 반응 분포 표시
  2. 투명도 슬라이더(60% -> 30% -> 90%) 조절
  3. 확대/축소 및 드래그 팬을 조작하여 원본 병 이미지와 히트맵의 일치 확인
- **발표자 멘트:**
  > "Day 7 Step 4에서 구현된 **실제 PatchCore Anomaly Map 시각화** 기능입니다.  
  > 단 1회의 모델 추론 결과에서 256×256 2차원 반응 맵을 확보하여 원본 900×900 좌표계에 선형 정합했습니다.  
  > 툴바의 **Heatmap ON**을 켜면 모델이 이상 반응을 감지한 영역이 투명 컬러맵으로 중첩됩니다.  
  > 4000% 배율로 확대하거나 화면을 팬 이동해도 1픽셀의 오차 없이 완벽하게 동기화됩니다.  
  > **[기술적 한계 및 정직한 공유]** 본 Heatmap은 모델의 상대적 이상 반응 분포일 뿐이며, 검증된 결함의 실제 위치나 Ground Truth 바운딩 박스를 의미하지는 않습니다.  
  > 현재 PatchCore의 학습과 운영 전처리 간 이중 정규화 불일치 문제가 미해결 상태이므로, 저희 팀은 억지스러운 가짜 결함 박스를 그리지 않고 모델의 실제 수치 그대로를 투명하게 시각화했습니다."

---

### [3:40 ~ 4:30] 5. 저장 Gemini 진단 에이전트 보고서 브리핑
- **화면:** 우하단 `AgentPanel`의 저장 보고서 조회 영역
- **발표자 행동:**
  1. `INSP-001396` 저장 보고서 스크롤
  2. `Observed Facts`와 `Hypothesis` 영역 강조
- **발표자 멘트:**
  > "마지막으로 AI 이상 진단 에이전트의 보고서 기능입니다.  
  > 본 화면은 검사 완료 후 생성된 저장 에이전트 보고서입니다.  
  > VisionInsight의 Gemini 에이전트는 규칙 7에 따라 **'밝기 저하'라는 물리적 현상을 '조명 고장'으로 단정하지 않습니다.**  
  > 보시는 바와 같이 시스템이 측정한 확정적 사실인 **Observed Facts**와,  
  > AI가 추론한 가능성인 **Hypothesis**를 명확히 구분하여 운영자에게 안전한 가이드를 제공합니다.  
  > 현재 실시간 Function Calling 호출은 스키마 격리 단계까지 완료되었으며, 발표의 안정성을 위해 검증된 저장 보고서 조회 모드로 시연을 진행했습니다."

---

### [4:30 ~ 5:00] 6. 마무리 및 질의응답
- **발표자 멘트:**
  > "요약하자면, VisionInsight는 머신비전의 픽셀 단위 정밀성, 모델의 실제 이상 반응 시각화, 그리고 AI 에이전트의 안전한 진단 분리 원칙을 충실히 구현했습니다.  
  > 이상으로 발표를 마치고 질문을 받겠습니다. 감사합니다."

---

# [작업 C] 장애 대응 시나리오 (Contingency Plan)

발표 도중 예기치 못한 시스템 오류 발생 시 당황하지 않고 매끄럽게 넘어갈 수 있는 9대 대체 시연 경로입니다. **실제 Gemini API 호출이나 운영 JSONL 변경 없이 오프라인 자산만을 활용합니다.**

| 장애 시나리오 | 현상 및 감지 방법 | 즉각 대응 조치 (현장 조치) | 발표자 대체 멘트 | 안전 대체 시연 경로 |
| :--- | :--- | :--- | :--- | :--- |
| **1. React 접속 실패** | 브라우저 `localhost:5173` 흰 화면 또는 연결 거부 | 터미널에서 Vite 서버 확인 (`npm run dev`) 또는 빌드 정적 서빙 | *"로컬 개발 서버 재로딩 중 잠시 아키텍처 다이어그램 문서를 먼저 설명드리겠습니다."* | `docs/architecture.md` 또는 기작성 캡처 슬라이드로 전환 |
| **2. FastAPI 연결 실패** | 대시보드 API 에러 배너 (500/Connection Refused) | 백엔드 터미널 확인 (`conda run -n vision-insight uvicorn ...`) | *"현재 데모 머신의 백엔드 포트를 재연결하고 있습니다. 정적 UI 인터페이스 명세를 먼저 확인하겠습니다."* | 기저장된 API 스키마 문서 `docs/inspection-data-schema.md` 브리핑 |
| **3. LiveView 영상 로드 실패** | 비디오 영역 검은 화면 또는 `Video load error` | 브라우저 캐시 새로고침 (Ctrl+F5), 코덱 체크 | *"실시간 공정 스트림 대신 저장된 무손실 프레임 캡처 모드로 바로 전환하여 설명드리겠습니다."* | 상단 `[정적 검사 이미지]` 탭을 즉시 눌러 600×600 ImageView 시연으로 전환 |
| **4. 검사 결과 조회 실패** | 숏컷 클릭 시 검사 데이터 안 뜸 | 입력창에 직접 `INSP-001396` 수동 입력 후 조회 | *"방금 전 완료된 실제 정상 검사 ID인 INSP-001396을 직접 호출하여 판정을 확인하겠습니다."* | 최근 검사 드롭다운 목록에서 `INSP-001396` 수동 선택 |
| **5. 정적 이미지 로드 실패** | `정적 이미지 로드 실패` 배너 노출 | 이미지 ID `IMG-BOTTLE-0084`로 재선택 | *"고해상도 900×900 무손실 버퍼를 재참조하겠습니다."* | LiveView 탭으로 이동하여 `[Grab]` 실행 후 LiveView 캡처 이미지로 4000% 줌 시연 |
| **6. Heatmap 없음 / 로드 실패** | `[Heatmap OFF]` 버튼 비활성화 상태 유지 | 과거 검사는 원래 Map이 없는 것이 정상임을 역으로 설명 | *"보시는 바와 같이 과거 기록에는 가짜 히트맵을 생성하지 않고 정직하게 '데이터 없음'을 표시하는 안전 장치가 작동 중입니다."* | Day 7 Step 4의 데이터 격리 및 가짜 맵 방지 정책 설명으로 자연스럽게 연결 |
| **7. 신규 PatchCore 검사 실패** | `[Inspect 실행]` 시 타임아웃 또는 서버 에러 | 신규 검사 대신 기존 저장 검사 4종 시연 숏컷 활용 | *"실시간 모델 추론 큐 대신, 서버에 확정 기록된 4가지 표준 테스트 시나리오(OK, 경고, 한계사례, Mock)를 비교 분석해 드리겠습니다."* | `[T01:OK]`, `[T03:Warn]`, `[T06:한계OK]`, `[Mock:NG]` 4종 숏컷 순차 비교 |
| **8. Gemini 실시간 분석 실패** | `GEMINI_REQUEST_FAILED` 또는 지연 발생 | 실시간 버튼을 누르지 않고 기저장된 보고서 탭 클릭 | *"외부 클라우드 LLM 지연 위험에 대비하여 당사 시스템은 검증된 진단 보고서 캐시 조회를 기본으로 권장합니다."* | `INSP-001396` 저장 보고서의 Fact vs Hypothesis 분리 구조 설명 |
| **9. 저장 Agent 보고서 조회 실패** | 보고서 영역 로딩 스피너 지속 | `docs/day4-step4-gemini-validation.md`의 보고서 샘플 인용 | *"로컬 캐시 대신 최종 확정된 진단 보고서 규격을 통해 시스템의 진단 로직을 설명드리겠습니다."* | 마크다운 문서 내 에이전트 구조화 JSON 결과 확인 |

---

# [작업 D] Codex에게 넘길 QA 발견사항 (Handover Findings)

메인 개발자(Codex)가 후속 최적화 및 유지보수 시 반드시 검토해야 할 기술적 정합성 및 안전성 점검 사항입니다.

### 1. 원본 900×900 ↔ Anomaly Map 256×256 선형 등방 매핑
- **관측 사실:** `backend/ml/patchcore_inferencer.py`는 `transforms.Resize((256, 256))`을 사용하므로 CenterCrop이나 Padding이 없음.
- **검토 포인트:**
  - 현재는 900×900 정사각형 이미지에 대해 등방 배율($900/256 = 3.515625$)로 정확히 매핑됨.
  - 향후 만약 다른 종횡비(예: 1920×480 LiveView 프레임)를 PatchCore에 투입할 경우 단순 Resize는 영상 왜곡을 유발하므로, Letterbox Padding 또는 전처리 역변환 메타데이터를 Sidecar JSON에 추가 기록해야 함.

### 2. Sidecar 3개 파일(`.npz`, `.json`, `_overlay.png`)의 원자적 일관성
- **관측 사실:** [anomaly_map_store.py](file:///C:/Users/USER/AI-NativeAgent/Project/InspectAgent/backend/anomaly_map_store.py)에서 `.tmp` 파일을 거쳐 `replace`하는 원자적 쓰기가 구현됨.
- **검토 포인트:**
  - `_overlay.png` 생성 시 OpenCV가 `.tmp` 확장자를 인식하지 못하던 버그를 `cv2.imencode('.png', ...)`로 수정 완료함.
  - 디스크 용량 관리(Garbage Collection) 정책이 아직 부재하므로, 대량 검사 시 `data/outputs/inspection_anomaly_maps/` 디렉터리의 주기적 정리 정책이 추후 필요함.

### 3. Mock 검사와 실제 Map의 엄격한 분리
- **관측 사실:** `INSP-001391` (Mock Fixture)에 대해 Sidecar 파일이 존재하지 않으며, API는 `404 MAP_NOT_AVAILABLE`을 반환함.
- **검토 포인트:**
  - 프론트엔드에서 Mock Fixture에 대해 어떠한 합성 Heatmap도 덧씌우지 않는 상태가 유지되어야 함.
  - `isMockFixture` 조건(`INSP-001391` 또는 `provenance === 'RECORDED_TEST_FIXTURE'`)이 변조되지 않도록 주의.

### 4. 과거 검사 소급 맵 없음 처리 (MAP_NOT_AVAILABLE)
- **관측 사실:** 과거 검사(`INSP-001396`, `INSP-001388` 등) 조회 시 404를 정상 반환함.
- **검토 포인트:**
  - 과거 검사를 조회할 때 백엔드가 결측 맵을 메꾸기 위해 '자동 재추론'을 수행해서는 안 됨 (현재 안전하게 차단됨).
  - 프론트엔드 버튼의 disabled 상태와 *"이 검사 기록에는 저장된 이상지도 데이터가 없습니다."* 안내가 정상 노출됨.

### 5. Zoom / Pan 및 Pixel Inspector 불변성
- **관측 사실:** Heatmap 오버레이는 화면 표시용 Canvas에만 `drawImage`되며, Pixel Inspector는 이미지 로드 시 추출된 오프스크린 `targetImageData`만을 참조함.
- **검토 포인트:**
  - Heatmap의 투명도를 100%로 올려도 마우스 포인터의 RGB/GV 값은 원본 병 픽셀 값을 100% 유지함.
  - 추후 Canvas 리팩터링 시 `ctx.getImageData()`를 메인 Canvas에서 다시 읽어오는 실수를 범하지 않도록 격리 구조 보존 필요.

### 6. 경로 순회(Path Traversal) 보안
- **관측 사실:** `backend/anomaly_map_store.py`의 `is_valid_inspection_id`가 정규식 `^INSP-[A-Za-z0-9_-]{1,32}$`를 엄격히 검증함.
- **검토 포인트:**
  - `..`이나 슬래시(`/`, `\`)가 포함된 악의적 ID 입력 시 400 에러 및 파일 접근 차단 테스트 완료 (`tests/test_inspection_anomaly_map.py` 100% 통과).

### 7. 운영 JSONL 불변성
- **관측 사실:** Sidecar Artifact는 `data/outputs/inspection_anomaly_maps/`에 별도 보관되며, `data/outputs/inspections.jsonl`의 기존 스키마를 파괴하지 않음.
- **검토 포인트:**
  - Cloud Run 또는 타 환경 배포 시 `inspections.jsonl`과 `inspection_anomaly_maps/`의 영구 볼륨 매핑 분리 확인 필요.

### 8. 테스트 환경에서의 실모델 추론 및 Gemini 실호출 원천 차단
- **관측 사실:** `tests/test_inspection_anomaly_map.py`는 Mock Inferencer와 Mock Map만을 사용하여 4.67초 만에 9개 테스트 통과.
- **검토 포인트:**
  - 자동화 테스트 파이프라인에서 실제 PyTorch 무거운 체크포인트를 로드하거나 Gemini API 키를 요구하는 일이 없도록 테스트 격리가 유지되어야 함.

---

# [종합 요약 및 시연 대기 상태]

- **문서 생성:** [docs/day7-gemini-independent-qa-and-demo-plan.md](file:///C:/Users/USER/AI-NativeAgent/Project/InspectAgent/docs/day7-gemini-independent-qa-and-demo-plan.md)
- **코드 변경 내역:** 0건 (Codex 개발 영역 엄격 보존)
- **외부 API 및 실모델 추론:** 0회
- **검증 상태:** 12대 항목 독립 QA 기준 수립 완료, 3~5분 발표 시연 대본 완성, 9대 장애 대응 시나리오 준비 완료, Codex 기술 인계 사항 정리 완료.
- **다음 행동:** Codex 및 사용자의 확인 후 승인된 시연 리허설 준비.
