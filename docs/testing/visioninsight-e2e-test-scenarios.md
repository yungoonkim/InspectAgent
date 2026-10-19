# VisionInsight — Gemini Computer Use + Playwright E2E 테스트 시나리오 명세서

> **문서 상태:** 테스트 설계 명세서 (테스트 실행기 개발, 브라우저 조작, 실제 검사 생성 및 Google API 호출 미실행 상태)  
> **프로젝트:** VisionInsight (산업용 Vision 검사 이상 진단 AI Agent)  
> **테스트 대상 환경:**  
> - Frontend: `http://localhost:5173` (React 18, TypeScript, Vite)  
> - Backend: `http://127.0.0.1:8000` (FastAPI, PyTorch/PatchCore, OpenCV)  
> **기준 영상:** `VID-000003` 전용 (16초, 480프레임, 30fps, 1920×480, H.264 MP4, 양품/불량 혼합 영상)  
> **제외 영상:** `VID-000001`, `VID-000002` (본 자동화 테스트에서 Grab이나 검사 실행 절대 금지)  
> **개정 일자:** 2026년 10월 20일 (최신 구현 반영 개정판)  

---

## 1. 테스트 전략 및 핵심 원칙

### 1.1 도구 역할 분담과 하이브리드 검증 원칙
본 E2E 테스트는 **Gemini Computer Use**와 **Playwright**의 상호 보완적인 강점을 결합하여 설계되었습니다.

1. **Gemini Computer Use (시각 인지 및 휴먼 인터랙션 검증)**:
   - 실제 Chrome 화면 스크린샷을 기반으로 사람이 보는 관점에서의 시각적 이상 검증
   - 텍스트 겹침, CSS 스타일 누락, 반응형 레이아웃 깨짐, 버튼 시각적 가독성 확인
   - 영상 Pause 후 ROI 오버레이 및 크롭 결과의 시각적 형태 왜곡 관찰
   - Heatmap(이상 점수 시각화) 및 Edge(초록: 병 외곽, 노랑: 내부 림 후보) 오버레이의 시각적 렌더링 관찰
2. **Playwright (결정론적 DOM 제어 및 시스템 상태 검증)**:
   - DOM 요소의 정확한 셀렉터 기반 상태(Disabled, Hidden, Active, aria-selected 등) 검증
   - 네트워크 요청/응답(HTTP Status, JSON Schema, Response Time) 모니터링
   - 검사 ID(`INSP-XXXXXX`), Capture ID(`CAP-XXXXXX`), 영상 ID(`VID-000003`) 간의 데이터 무결성 검증
   - 탭 전환 시 컴포넌트 언마운트/재마운트 과정에서의 로컬 상태 보존 검증
   - 반복 재현 가능한 회귀 테스트 하네스 제공
3. **교차 검증 원칙 (Cross-Validation Guardrail)**:
   - **Gemini Computer Use의 시각적 판단만으로 PASS를 확정하지 않습니다.** 반드시 Playwright를 통한 DOM 속성, 네트워크 응답, 저장 기록 등의 객관적 근거를 함께 대조하여 최종 판정합니다.
   - DOM이나 데이터 검증이 불가능한 시각적 배치 항목은 "육안 확인 필요"로 기록합니다.

---

### 1.2 VID-000003 전용 테스트 규칙 (동적 선택 및 안전 가드레일)

현재 VisionInsight에는 `VID-000001`~`VID-000003`이 등록되어 있으며, 초기 기본 선택 영상은 `VID-000002`일 수 있습니다. 따라서 자동화 테스트에서는 다음 4단계 규칙을 엄격히 적용합니다.

1. **테스트 시작 시 영상 선택 UI(`select#live-video-source`)에서 `VID-000003`을 선택합니다.**
2. **실제 적용된 영상 ID가 `VID-000003`인지 확인합니다** (헤더 뱃지 및 드롭다운 value).
3. **선택·검증에 실패한 경우에만 후속 검사 실행을 중단합니다.**
4. **`VID-000001`과 `VID-000002`로는 어떠한 Grab이나 검사도 실행하지 않습니다.**

```
[테스트 시작]
      │
      ▼
[select#live-video-source 확인]
      │
      ├─ VID-000003 이미 선택됨 ───► [검증 통과 후 진행]
      │
      └─ 다른 영상(VID-000002 등) ──► [select에서 VID-000003 선택]
                                             │
                                             ▼
                                  [적용 상태 재검증: VID-000003?]
                                       ├─ 성공 ──► [후속 검사 진행]
                                       └─ 실패 ──► [안전 중단 (ABORT)]
```

- **검증된 기준 영상 사양:**
  - 영상 ID: `VID-000003`
  - 재생 길이 / 프레임 수: 16초 / 480프레임 (frame_index: 0 ~ 479)
  - 해상도 / 주사율: 1920×480 CFR / 30.00 fps
  - 코덱: H.264 MP4
  - 특성: 양품과 불량 병 원본이 혼합된 컨베이어 시연 영상

---

### 1.3 정답 라벨과 모델 출력의 분리 원칙
- **라벨 격리:** `VID-000003` 영상 속 물리적 병의 정상/불량 여부(Ground Truth)와 PatchCore 모델의 예측 결과(Prediction)를 엄격히 분리합니다.
- **하드코딩 금지:** 모델 결과를 임의의 `OK`나 `NG`로 단정하여 테스트 기대값으로 하드코딩하지 않습니다.
- **미검증 상태 관리:** 실제 육안 및 물리적 검증을 거치지 않은 병 인스턴스는 정답 라벨을 `UNKNOWN`으로 유지합니다.
- **수치 보존:** 기존 전체 ROI 평균 GV 하한(125.0) 및 PatchCore 이상 점수 임계값(34.1442)은 변경하지 않습니다.

---

### 1.4 테스트 위험도 등급 (Safety Execution Levels)

모든 시나리오는 시스템 상태 변경 위험도와 외부 API 과금 리스크에 따라 세 단계로 엄격히 구분됩니다.

| 위험 등급 | 분류 명칭 | 설명 및 범위 | 실행 권한 및 안전 정책 | 포함 시나리오 |
| :---: | :--- | :--- | :--- | :--- |
| **Level 1** | **읽기 전용 UI 테스트** | 기존 저장 데이터 조회, 영상 재생/정지, 탭 전환, Heatmap 토글, Zoom/Pan, Pixel Inspector, Edge 오버레이 조작 등 | 추가 승인 없이 자동 회귀 하네스에서 즉시 실행 가능 (상태 변경 없음) | TC-01, TC-07, TC-08, TC-09, TC-10, TC-11, TC-12, TC-13(조회), TC-15(조회) |
| **Level 2** | **상태 변경 검사 E2E** | 신규 Grab/Capture 생성, 실제 PatchCore 로컬 추론, 재검사 그룹 생성, 새 제품 검사 전환, 수동 확인 기록 생성 | 사용자 명시 승인 필요. 테스트 데이터 식별 및 횟수 제한. 저장 기록 무단 삭제 금지 | TC-02, TC-03(선행의존), TC-04, TC-05, TC-06, TC-13(실검사), TC-14 |
| **Level 3** | **외부 Google API 테스트** | Gemini Vision Judge 실제 이미지 전송 및 Gemini Diagnostic Agent 실시간 보고서 생성 | **기본 자동화에서 완전 제외.** 별도 전송 동의, 토큰/비용 한도 통제, 사전 승인 필수 | (TC-15의 LIVE 실호출에만 한정) |

---

### 1.5 확인된 실제 API 엔드포인트 목록

소스코드 및 라우터 확인을 거친 실제 API 엔드포인트는 다음과 같습니다 (추측성 가상 경로는 사용하지 않습니다).

- **비디오 관련 엔드포인트 (`backend/video_api.py`):**
  - `GET /videos`: 등록된 비디오 소스 목록 조회
  - `GET /videos/{video_id}`: 단일 비디오 메타데이터 조회
  - `GET /videos/{video_id}/stream`: H.264 비디오 스트리밍
  - `POST /videos/{video_id}/grab`: 프레임 캡처 및 임시 Capture 생성
  - `POST /capture-sessions`: 브라우저 캡처 세션 발급 및 CSRF 토큰 갱신
  - `GET /captures/{capture_id}`: 캡처 메타데이터 조회
  - `GET /captures/{capture_id}/image`: 캡처 이미지 PNG 다운로드
- **검사 및 재검사 관련 엔드포인트 (`backend/main.py`, `backend/grab_inspection.py`):**
  - `POST /captures/{capture_id}/inspect`: Grab 이미지 기반 PatchCore 검사 실행
  - `GET /inspections`: 최근 검사 기록 목록 조회 (`?limit=50`)
  - `GET /inspections/{inspection_id}`: 단일 검사 상세 결과 조회
  - `GET /inspections/{inspection_id}/anomaly-map`: PatchCore 이상지도 메타데이터 조회
  - `GET /inspections/{inspection_id}/anomaly-map/overlay.png`: 이상지도 투명 오버레이 PNG 반환
  - `GET /inspections/{inspection_id}/agent-report`: 저장된 Gemini Agent 진단 보고서 조회
  - `GET /reinspection-groups/{group_id}`: 재검사 그룹 상태 조회
  - `GET /reinspection-groups/by-capture/{capture_id}`: 캡처와 연결된 재검사 그룹 조회
  - `POST /reinspection-groups/{group_id}/manual-reviews`: 작업자 수동 판정 기록 추가
- **Vision Judge 관련 엔드포인트 (`backend/vision_review_api.py`):**
  - `GET /inspections/{inspection_id}/vision-review`: 기존 저장된 Vision Judge 결과 조회
  - `POST /inspections/{inspection_id}/vision-review`: 신규 Vision Judge 분석 요청 (동의 필요)

---

## 2. 15개 필수 테스트 시나리오 상세 명세

---

### [그룹 A] LiveView와 Grab 검사 (TC-01 ~ TC-06)

---

#### TC-01. VID-000003 영상 선택 및 16초 재생 확인
- **테스트 목적:** 영상 선택 UI에서 `VID-000003`을 안전하게 선택·검증하고, 16초(480프레임, 30fps) 영상이 정상 재생 및 정지/탐색되는지 확인한다.
- **우선순위 / 위험 등급:** **P0 / Level 1 (읽기 전용 UI)**
- **사전 조건:** Frontend 및 Backend 구동 중, 브라우저 로드 완료. (기본 선택 영상이 `VID-000002`일 수 있음).
- **테스트 데이터 및 영상 프레임 조건:** `VID-000003` (1920×480, 480 frames, 16.0s, 30.0fps).
- **단계별 사용자 조작:**
  1. `select#live-video-source` 드롭다운의 현재 선택값 확인.
  2. 선택값이 `VID-000003`이 아니라면 드롭다운에서 `VID-000003` 옵션 선택.
  3. 헤더 또는 드롭다운의 적용 영상 ID가 `VID-000003`으로 갱신되었는지 확인 (불일치 시 테스트 즉시 중단).
  4. 재생 컨트롤러에서 `Play` 버튼 클릭 후 약 3초 재생 관찰.
  5. `Pause` 버튼 클릭.
  6. 타임 슬라이더를 8.0초(프레임 240 부근)로 이동 후 `+1 Frame`, `-1 Frame` 클릭.
- **예상 UI 결과:**
  - `select#live-video-source`에 `VID-000003 · 16초 · 480프레임 · 양품/불량 원본 혼합 데모` 표시.
  - 헤더 뱃지에 `VID-000003` 표시.
  - 재생 시 `STREAM PLAYING`, 정지 시 `STREAM PAUSED` 인디케이터 표시.
  - 타임라인 및 프레임 표시계가 정상 갱신.
- **예상 API 또는 데이터 검증:**
  - `GET /videos` 목록 내 `VID-000003` 메타데이터 존재 확인.
  - `GET /videos/VID-000003` 응답: `duration_seconds: 16.0`, `frame_count: 480`.
  - `GET /videos/VID-000003/stream` 비디오 스트림 정상 수신.
- **PASS / FAIL 판정 기준:**
  - PASS: `VID-000003`이 정상 선택·검증되고, 비디오 재생/정지/프레임 이동이 에러 없이 동작함.
  - FAIL: `VID-000003` 선택 실패, 재생 에러 배너 발생, 또는 프레임 슬라이더 조작 시 화면 멈춤.
- **Gemini Computer Use 담당 작업:**
  - Chrome 화면에서 비디오 재생 시 영상이 까맣게 나오거나 깨지지 않는지 시각적 관찰.
  - 타임라인 슬라이더와 프레임 텍스트가 겹치지 않고 명확히 표시되는지 확인.
- **Playwright 담당 작업:**
  - `select#live-video-source` 값 변경 및 단언.
  - `video` 태그의 `currentTime`, `paused` 속성 검증.
- **실패 시 확보할 증거:** `video_playback_failed.png`, 콘솔 로그, Network HAR.
- **상태 변경 및 복구 방법:** 상태 변경 없음 (읽기 전용).

---

#### TC-02. 영상 Pause → ROI 선택 → Grab Crop 생성
- **테스트 목적:** 일시정지 상태에서 병 영역에 ROI를 지정하고 Grab 실행 시 원본 좌표계 기반의 정밀 Crop 및 Capture가 생성되는지 검증한다.
- **우선순위 / 위험 등급:** **P0 / Level 2 (상태 변경: Capture 생성)**
- **사전 조건:** TC-01 완료 상태 (`VID-000003` 로드 완료, 영상 Pause 상태).
- **테스트 데이터 및 영상 프레임 조건:** `frame_index = 120` (검증 예정 예시 프레임, 병이 화면 중앙에 위치).
- **단계별 사용자 조작:**
  1. 프레임을 `120`으로 이동 후 일시정지 확인.
  2. ROI 지정 버튼 클릭 (ROI EDITING 모드 진입).
  3. 영상 뷰어 상에서 병 본체 영역을 마우스로 드래그하여 사각형 ROI 설정 (약 x: 800, y: 40, w: 320, h: 400).
  4. Grab 실행 버튼 클릭.
- **예상 UI 결과:**
  - 드래그 중 ROI 사각형 및 크기/중심 좌표 오버레이 표시.
  - Grab 클릭 후 중앙 ImageView 패널에 잘라낸 병 이미지(Crop) 표출.
  - `Crop 생성 완료 (Capture ID: CAP-...)` 알림 표시.
- **예상 API 또는 데이터 검증:**
  - `POST /videos/VID-000003/grab` 요청 (페이로드: `frame_index`, `source_revision`).
  - 응답: `status: 201`, `{ capture_id: "CAP-...", width: ..., height: ..., image_url: "..." }`.
- **PASS / FAIL 판정 기준:**
  - PASS: HTTP 201 수신, 유효한 `CAP-` ID 발급, ImageView에 해당 크롭 이미지가 렌더링됨.
  - FAIL: Grab 실패 에러 배너 발생, 또는 Crop 이미지가 로드되지 않음.
- **Gemini Computer Use 담당 작업:**
  - ROI 박스가 병 외곽을 적절히 감싸고 있는지 확인.
  - ImageView에 나타난 Crop 이미지가 찌그러지거나 회전되지 않았는지 시각적 검사.
- **Playwright 담당 작업:**
  - 마우스 드래그 이벤트 시뮬레이션 및 `POST /videos/VID-000003/grab` 응답 추출.
- **실패 시 확보할 증거:** `grab_crop_failed.png`, 네트워크 요청 페이로드 덤프.
- **상태 변경 및 복구 방법:** `backend/data/captures/`에 임시 PNG 생성됨 (테스트 세션 종료 시 TTL 관리 대상).

---

#### TC-03. 신규 정상 Capture에서 Grab 이미지 검사 버튼 활성화 확인
- **테스트 목적:** 정상 발급된 신규 Capture 상태에서 불필요한 차단 없이 검사 버튼이 올바르게 활성화되는지 확인한다.
- **우선순위 / 위험 등급:** **P0 / Level 1 (검사 실행 전 UI 확인, 단 Level 2 신규 Capture 생성에 의존)**
- **사전 조건:** TC-02 성공 완료 직후 (신규 Capture 발급 완료 상태, 아직 검사 버튼 클릭 안 함).
- **테스트 데이터 및 영상 프레임 조건:** TC-02에서 생성된 `capture_id`.
- **단계별 사용자 조작:**
  1. 우측 패널의 `Grab 이미지 검사` 탭 활성화 확인.
  2. 패널 하단의 검사 실행 버튼 상태 및 안내 문구 확인.
- **예상 UI 결과:**
  - 상태 배너: `최초 검사 1 / 3 준비` 또는 `신규 Capture 검사 가능` 문구 표출.
  - 검사 실행 버튼이 활성화(`disabled` 아님) 상태임.
  - 차단 에러 메시지(오래된 세션, RIG 충돌 등)가 일체 표시되지 않음.
- **예상 API 또는 데이터 검증:**
  - `GET /reinspection-groups/by-capture/{capture_id}` 호출 결과: `404 REINSPECTION_GROUP_NOT_FOUND` (신규 캡처이므로 정상).
  - 프론트엔드 검사 차단 유틸이 `false`를 반환.
- **PASS / FAIL 판정 기준:**
  - PASS: 검사 버튼이 활성화되어 있고 복구 경고 배너가 없음.
  - FAIL: 신규 캡처임에도 버튼이 비활성화(`disabled`)되어 있거나 차단 경고 표시.
- **Gemini Computer Use 담당 작업:**
  - 버튼의 시각적 활성화 상태(파란색 배경, hover 반응) 확인.
- **Playwright 담당 작업:**
  - 검사 실행 버튼의 `toBeEnabled()` 단언.
- **실패 시 확보할 증거:** `button_disabled_state.png`, LocalStorage 상태 덤프.
- **상태 변경 및 복구 방법:** 상태 변경 없음.

---

#### TC-04. Grab 검사 완료 후 검사 ID, PatchCore 점수, 품질 상태, 서버 최종 판정 표시
- **테스트 목적:** 실제 Grab 이미지 검사를 수행하여 고유 검사 ID(`INSP-`), 모델 점수, 영상 품질 상태, 서버 최종 판정(`final_result`)이 4대 핵심 규칙에 맞게 정확히 표시되는지 검증한다.
- **우선순위 / 위험 등급:** **P0 / Level 2 (상태 변경: 실제 PatchCore 추론 및 검사 저장)**
- **사전 조건:** TC-03 상태 (검사 버튼 활성화).
- **테스트 데이터 및 영상 프레임 조건:** TC-02의 신규 Capture.
- **단계별 사용자 조작:**
  1. 검사 실행 버튼 클릭.
  2. 백엔드 모델 추론 완료까지 대기 (실제 CPU 연산 완료 대기).
  3. 결과 패널에 표시된 메타 데이터 확인.
- **예상 UI 결과:**
  - 검사 완료 뱃지: `검사 완료 (INSP-XXXXXX)` 표출.
  - 메타 정보 필:
    - 검사 방식: `LIVEVIEW_GRAB`
    - PatchCore 모델 판정: `OK` (초록) 또는 `NG` (빨강)
    - 이상 점수: `Score XX.XXXX / 34.1442`
    - 영상 품질: `NORMAL` (초록) 또는 `WARNING_LOW_BRIGHTNESS` (노랑)
    - 서버 최종 판정: `최종 OK`, `최종 NG`, 또는 `최종 REINSPECT`
- **예상 API 또는 데이터 검증:**
  - `POST /captures/{capture_id}/inspect` 요청.
  - 응답: `status: 200`, `{ inspection_id: "INSP-...", anomaly_score: ..., result: "...", quality_status: "...", final_result: "..." }`.
- **PASS / FAIL 판정 기준:**
  - PASS: HTTP 200 수신, `INSP-` 검사 ID 발급, 모델 판정과 서버 판정이 분리 표출됨.
  - FAIL: 검사 에러 배너 발생, 검사 ID 누락, 또는 판정 필드 렌더링 오류.
- **Gemini Computer Use 담당 작업:**
  - 메타 필 텍스트가 줄바꿈되어 겹치거나 카드 밖으로 삐져나가지 않는지 시각적 검사.
  - 판정 결과에 따른 색상(초록/빨강/노랑)이 정확히 스타일링되었는지 확인.
- **Playwright 담당 작업:**
  - 응답 JSON의 `inspection_id`, `anomaly_score`, `final_result` 추출 및 DOM 일치 단언.
- **실패 시 확보할 증거:** `grab_inspection_result_failed.png`, 백엔드 응답 JSON 로그.
- **상태 변경 및 복구 방법:** `data/inspections.jsonl`에 신규 검사 레코드 1건 추가됨.

---

#### TC-05. 같은 Capture 중복 검사 차단과 정상적인 새 제품 검사 흐름 확인
- **테스트 목적:** 이미 검사가 완료된 동일 Capture에 대한 중복 검사 실행을 방지하고, 사용자가 새 제품 검사로 정상 전환할 수 있는지 검증한다.
- **우선순위 / 위험 등급:** **P0 / Level 2 (상태 전이 검증)**
- **사전 조건:** TC-04 검사 완료 직후 상태.
- **테스트 데이터 및 영상 프레임 조건:** TC-04에서 완료된 Capture.
- **단계별 사용자 조작:**
  1. 검사 완료 후 검사 실행 버튼이 비활성화되었는지 확인.
  2. 새 제품 검사 준비 또는 새 프레임 Grab 실행.
  3. 타임라인을 다른 프레임(`frame_index = 200` 검증 예정 예시)으로 이동 후 새 Grab 실행.
- **예상 UI 결과:**
  - 동일 Capture 완료 상태에서는 중복 검사 불가 안내 표시 및 버튼 비활성화.
  - 새 프레임 Grab 시 새로운 Capture ID가 발급되며, 다시 `최초 검사 1 / 3 준비` 상태로 갱신됨.
- **예상 API 또는 데이터 검증:**
  - 동일 `capture_id`로 재차 검사 요청 시 서버가 `409 CONFLICT` 반환(UI 버튼이 사전에 비활성화되어야 함).
- **PASS / FAIL 판정 기준:**
  - PASS: 동일 Capture에 대한 연속 검사가 원천 차단되고, 새 Grab 후 새 제품 검사 상태로 정상 전이됨.
  - FAIL: 동일 Capture로 중복 검사가 임의 실행됨.
- **Gemini Computer Use 담당 작업:**
  - 버튼의 비활성화(회색조) 및 툴팁/안내 문구가 명확하게 인지 가능한지 확인.
- **Playwright 담당 작업:**
  - 검사 실행 버튼의 `toBeDisabled()` 단언.
  - 새 Grab 실행 후 새 `capture_id` 바인딩 단언.
- **실패 시 확보할 증거:** `duplicate_inspection_allowed.png`.
- **상태 변경 및 복구 방법:** 신규 2번째 Capture 생성됨.

---

#### TC-06. 오래된 RIG·pending Capture 상태 및 HTTP 404 발생 시 안전한 복구 흐름 확인
- **테스트 목적:** 브라우저 LocalStorage에 과거의 만료된 재검사 그룹(`RIG-`)이나 삭제된 캡처(`CAP-`) 힌트가 남아있어 HTTP 404가 발생하더라도, 서버 소유권을 침해하지 않고 UI가 안전하게 복구되는지 검증한다.
- **우선순위 / 위험 등급:** **P1 / Level 2 (복구 흐름 검증)**
- **사전 조건:** 임의의 만료된 RIG ID를 LocalStorage에 설정 후 페이지 새로고침.
- **테스트 데이터 및 영상 프레임 조건:** `localStorage.setItem('visioninsight.manual-reinspection-group', 'RIG-expired-mock-9999')`.
- **단계별 사용자 조작:**
  1. 페이지 새로고침(F5) 수행.
  2. Grab 검사 패널의 상태 배너 확인.
  3. `[저장 그룹 새로 조회]` 또는 `[새 제품 검사 시작]` 버튼 클릭.
  4. 확인 팝업창에서 승인 선택.
- **예상 UI 결과:**
  - 초기 로드 시 `이전 재검사 그룹을 조회할 수 없습니다 (404)` 경고 표시.
  - `[새 제품 검사 시작]` 확인 후 오래된 UI 힌트가 안전하게 제거되고 `최초 검사 1 / 3 준비` 상태로 복구됨.
  - 화면 전체가 락업(영구 비활성화)되지 않음.
- **예상 API 또는 데이터 검증:**
  - `GET /reinspection-groups/RIG-expired-mock-9999` 호출 시 `404 Not Found` 수신.
  - LocalStorage의 `visioninsight.manual-reinspection-group` 키 정리.
- **PASS / FAIL 판정 기준:**
  - PASS: HTTP 404 수신 후에도 사용자 확인을 통해 정상적인 최초 검사 모드로 복구 완료됨.
  - FAIL: 화면이 영구히 blocked 상태로 유지되거나 콘솔 Uncaught Exception 발생.
- **Gemini Computer Use 담당 작업:**
  - 복구 확인 모달 창의 텍스트가 명확하고 확인/취소 버튼이 명확히 보이는지 확인.
- **Playwright 담당 작업:**
  - LocalStorage 조작 및 404 네트워크 인터셉트 검증 후 상태 회복 단언.
- **실패 시 확보할 증거:** `recovery_flow_failed.png`, 콘솔 에러 로그.
- **상태 변경 및 복구 방법:** LocalStorage 힌트 정리.

---

### [그룹 B] 이미지 및 AI 검사 결과 UI (TC-07 ~ TC-12)

---

#### TC-07. Grab 검사 / 정적 이미지 검사 상위 탭 전환 및 상태 보존
- **테스트 목적:** `Grab 이미지 검사` 탭과 `정적 이미지 검사` 탭 간 전환 시 저장된 기존 검사 결과, 입력값, ROI 상태가 유실되지 않고 보존되는지 검증한다.
- **우선순위 / 위험 등급:** **P1 / Level 1 (읽기 전용 UI, 기존 저장 데이터 활용)**
- **사전 조건:** 저장된 검사 결과가 존재하는 상태 (신규 검사를 실행하지 않고 기존 `INSP-XXXXXX` 결과 로드 상태).
- **테스트 데이터 및 영상 프레임 조건:** 기존 저장 검사 레코드 1건.
- **단계별 사용자 조작:**
  1. 상위 탭에서 `[정적 이미지 검사]` 탭 클릭 (`#static-inspection-tab`).
  2. 정적 이미지 검사 패널 표시 확인.
  3. 다시 상위 탭에서 `[Grab 이미지 검사]` 탭 클릭 (`#grab-inspection-tab`).
- **예상 UI 결과:**
  - `[정적 이미지 검사]` 탭 클릭 시 정적 패널이 열리고 Grab 패널은 `hidden` 처리됨.
  - `[Grab 이미지 검사]`로 복귀 시 직전에 확인했던 검사 결과, 이상 점수, 뷰어 상태가 그대로 유지됨.
- **예상 API 또는 데이터 검증:**
  - 불필요한 백엔드 검사 API 재호출(Re-inspection)이 발생하지 않음 (로컬 React State 유지).
- **PASS / FAIL 판정 기준:**
  - PASS: 탭 전환 후 복귀 시 모든 상태(검사 ID, 점수, 뷰어 이미지)가 동일하게 보존됨.
  - FAIL: 탭 복귀 시 화면이 초기화되거나 이미지가 사라짐.
- **Gemini Computer Use 담당 작업:**
  - 활성 탭 인디케이터(하단 파란 밑줄)가 정확히 이동하는지 시각적 확인.
- **Playwright 담당 작업:**
  - `#grab-inspection-tab`과 `#static-inspection-tab`의 `aria-selected` 속성 변화 단언.
- **실패 시 확보할 증거:** `tab_state_lost.png`.
- **상태 변경 및 복구 방법:** 상태 변경 없음.

---

#### TC-08. 1차 PatchCore 검사 / 2차 Gemini Judge 서브탭 전환 및 상태 보존
- **테스트 목적:** Grab 검사 내부의 `1차 · PatchCore 검사` 서브탭과 `2차 · Gemini Vision Judge` 서브탭 간 전환이 매끄럽게 동작하고 데이터가 독립적으로 보존되는지 검증한다.
- **우선순위 / 위험 등급:** **P1 / Level 1 (읽기 전용 UI, 기존 저장 데이터 활용)**
- **사전 조건:** 저장된 검사 결과가 로드된 상태.
- **테스트 데이터 및 영상 프레임 조건:** 해당 없음.
- **단계별 사용자 조작:**
  1. 서브탭 `[2차 · Gemini Vision Judge]` 클릭 (`#judge-inspection-tab`).
  2. 서브탭 `[1차 · PatchCore 검사]` 클릭 (`#patchcore-inspection-tab`).
- **예상 UI 결과:**
  - 2차 서브탭 선택 시 Vision Judge 패널(독립 참고 의견 안내, 기존 검사 결과, 동의 체크박스) 표출.
  - 1차 서브탭 복귀 시 PatchCore 모델 점수 및 사유 코드가 온전히 유지됨.
- **예상 API 또는 데이터 검증:**
  - 탭 클릭만으로 외부 Google API나 백엔드 검사 API가 임의 호출되지 않음.
- **PASS / FAIL 판정 기준:**
  - PASS: 서브탭 전환이 즉각 발생하고 양쪽 패널의 데이터가 충돌 없이 보존됨.
  - FAIL: 서브탭 클릭 시 오류 발생 또는 컴포넌트 렌더링 실패.
- **Gemini Computer Use 담당 작업:**
  - 서브탭 전환 시 레이아웃 점프(CLF) 현상이 없는지 시각적 확인.
- **Playwright 담당 작업:**
  - 서브탭 패널의 `hidden` 속성 토글 상태 검증.
- **실패 시 확보할 증거:** `subtab_switch_error.png`.
- **상태 변경 및 복구 방법:** 상태 변경 없음.

---

#### TC-09. 검사 ID 일치 및 이전 검사 결과가 현재 Crop에 섞이지 않는지 확인
- **테스트 목적:** 서로 다른 두 검사를 조회했을 때, 이전 검사의 점수나 결과가 새로운 이미지 화면에 잔존(Ghosting)하는 현상을 원천 방지한다.
- **우선순위 / 위험 등급:** **P0 / Level 1 (데이터 무결성 검증)**
- **사전 조건:** 최소 2건 이상의 검사 결과가 저장소에 존재하는 상태.
- **테스트 데이터 및 영상 프레임 조건:** 저장된 검사 ID 2건 (예: 검사 A, 검사 B).
- **단계별 사용자 조작:**
  1. 검사 ID 입력창에 검사 A의 ID 입력 후 조회.
  2. 표시된 결과 확인.
  3. 검사 ID 입력창에 검사 B의 ID 입력 후 조회.
- **예상 UI 결과:**
  - 조회가 완료되면 입력창의 ID와 상단 헤더, 메타 정보 필의 검사 ID가 정확히 1:1 일치해야 함.
  - 검사 A의 점수가 검사 B 화면에 남아있지 않음.
- **예상 API 또는 데이터 검증:**
  - `GET /inspections/{id}` 응답의 `inspection_id`와 화면 표출 텍스트의 일치성.
- **PASS / FAIL 판정 기준:**
  - PASS: 조회된 모든 필드(점수, 판정, 타임스탬프)가 요청한 검사 ID의 데이터와 정확히 일치함.
  - FAIL: 검사 A를 조회했는데 검사 B의 점수나 이미지가 섞여서 표시됨.
- **Gemini Computer Use 담당 작업:**
  - 검사 ID 라벨 텍스트와 이미지 캡션의 ID가 동일한지 대조 확인.
- **Playwright 담당 작업:**
  - 입력값, 응답 데이터, 결과 텍스트의 3자 일치 단언.
- **실패 시 확보할 증거:** `inspection_id_mismatch.png`.
- **상태 변경 및 복구 방법:** 상태 변경 없음.

---

#### TC-10. Heatmap ON/OFF, Zoom/Pan, Pixel Inspector 좌표 검증
- **테스트 목적:** 이미지 뷰어의 PatchCore Heatmap 오버레이 토글, 100%~4000% 줌/팬 인터랙션, 마우스 커서 위치의 Pixel Inspector(RGB/GV) 계측 기능의 정확성을 검증한다.
- **우선순위 / 위험 등급:** **P1 / Level 1 (읽기 전용 인터랙션, 저장된 기존 검사 활용)**
- **사전 조건:** Heatmap 데이터가 저장된 기존 검사 결과 로드 상태.
- **테스트 데이터 및 영상 프레임 조건:** 기존 저장 검사 레코드 1건.
- **단계별 사용자 조작:**
  1. 이미지 뷰어 툴바에서 `Heatmap ON/OFF` 버튼 클릭 (`.heatmap-toggle-btn`).
  2. 투명도 슬라이더(`input[type="range"]`)를 조절.
  3. 뷰어 내에서 줌 인(Zoom In) 조작 (마우스 휠 또는 줌 버튼).
  4. 마우스 드래그로 이미지 이동(Pan).
  5. 이미지 픽셀 위에 마우스 호버 후 Pixel Inspector 패널 확인.
- **예상 UI 결과:**
  - Heatmap OFF 시 원본 이미지만 깨끗하게 표시, ON 시 컬러맵 오버레이 복원.
  - 줌 인 시 픽셀이 앵커를 중심으로 확대되며, 단순 확대 표시일 뿐 원본에 없던 세부 정보가 마법처럼 복원되는 것이 아님을 유의.
  - Pixel Inspector에 현재 픽셀 좌표(`X, Y`), RGB 값, 회색조(`GV`)가 표시됨.
  - 검은 패딩 영역에 마우스 위치 시 패딩 영역임이 구분됨.
- **예상 API 또는 데이터 검증:**
  - `GET /inspections/{id}/anomaly-map` 및 `GET /inspections/{id}/anomaly-map/overlay.png` 정상 로드 확인.
- **PASS / FAIL 판정 기준:**
  - PASS: Heatmap 토글/투명도 조절이 즉각 반영되고, 줌/팬 좌표 변환이 작동하며 Pixel Inspector 수치가 표출됨.
  - FAIL: Heatmap 로드 실패, 줌 조작 시 화면 이탈, 또는 Pixel Inspector 멈춤.
- **Gemini Computer Use 담당 작업:**
  - Heatmap 컬러 오버레이가 이미지 위에 자연스럽게 정합되는지 관찰.
  - 패널에 "상대적 이상 반응 분포이며 결함 위치 확정이 아님" 안내 문구가 표시되는지 확인.
- **Playwright 담당 작업:**
  - 캔버스의 포인터 이벤트 시뮬레이션 및 Inspector 수치 단언.
- **실패 시 확보할 증거:** `heatmap_zoom_inspector_failed.png`.
- **상태 변경 및 복구 방법:** 상태 변경 없음.

---

#### TC-11. 병 외곽 Edge·내부 림 후보 ON/OFF 및 실제 Crop 좌표 정합성 [구현 완료 / Chrome 회귀 자동화 대기]
- **테스트 목적:** 이미 구현된 병 테두리 검출 기능(`BottleEdgeDetails.tsx`, `detectBottleEdges`)에서 병 외곽(초록) 및 내부 림 후보(노랑) 오버레이가 올바르게 토글되고, 평가 상태 및 기하 수치가 정확히 표출되는지 검증한다.
- **우선순위 / 위험 등급:** **P1 / Level 1 (읽기 전용 UI, 브라우저 측 이미지 분석)**
- **사전 조건:** Grab Crop 이미지가 뷰어에 표시된 상태.
- **테스트 데이터 및 영상 프레임 조건:** 기존 저장 Crop 표본 (실제 검증 사례: 외곽 성공 3건, 실패 1건 / 내부 림 불확실 3건, 실패 1건).
- **단계별 사용자 조작:**
  1. 이미지 뷰어 툴바에서 `병 테두리 ON/OFF` 버튼 클릭 (`button.btn-tool`).
  2. 아코디언 `<details className="bottle-edge-information">` 펼침 상태 확인.
  3. 외곽 및 내부 림 후보의 상태 라벨(`성공 (기하 조건)`, `불확실`, `실패`) 확인.
  4. 폐곡선, 연결 성분, 원형도 4πA/P², 기준 반경, 반경 편차 수치 확인.
  5. 이미지를 Zoom/Pan 했을 때 Edge 오버레이가 원본 픽셀 좌표와 일치하여 함께 이동하는지 확인.
- **예상 UI 결과:**
  - 외곽선은 초록색, 내부 림 후보는 노란색으로 정밀 렌더링됨.
  - 요약문에 `병 테두리 · 외곽: {상태} / 내부 림 후보: {상태}` 표시.
  - **정상 동작 기준:** 외곽 검출 성공이 제품 정상 판정을 뜻하지 않으며, 내부 림 검출이 불확실하거나 실패한 경우라도 그 상태가 솔직하게 표출되면 정상 통과임.
- **예상 API 또는 데이터 검증:**
  - 본 분석은 브라우저 측 픽셀 연산(`detectBottleEdges`)이므로 별도의 백엔드 API 호출이 발생하지 않음.
- **PASS / FAIL 판정 기준:**
  - PASS: 버튼 토글 시 오버레이가 정확히 나타나고, Zoom/Pan 시 좌표 정합성을 유지하며, 기하 평가 수치가 올바르게 표시됨.
  - FAIL: 오버레이 토글 불가, 줌 조작 시 선이 어긋남, 또는 컴포넌트 렌더링 크래시.
- **Gemini Computer Use 담당 작업:**
  - 초록색 외곽선과 노란색 림 선이 병 이미지 윤곽 위에 적절히 겹치는지 시각적 정합성 확인.
- **Playwright 담당 작업:**
  - `button.btn-tool` 클릭 및 `aria-pressed` 토글 단언.
  - `details.bottle-edge-information` 내부의 상태 텍스트 단언.
- **실패 시 확보할 증거:** `edge_overlay_error.png`.
- **상태 변경 및 복구 방법:** 상태 변경 없음.

---

#### TC-12. 전체 ROI·병 영역·병 내부·배경 평균 GV 표시 및 실패 상태 확인 [구현 완료 / Chrome 회귀 자동화 대기]
- **테스트 목적:** `BottleEdgeDetails.tsx`에 이미 구현된 4대 영역별 밝기 통계(A·전체 ROI, B·외곽 내부 후보, C·닫힌 림 후보 내부, D·외곽 바깥 후보)가 정확히 표출되고, 닫힌 영역 부재 시 '계산 불가'가 올바르게 안내되는지 검증한다.
- **우선순위 / 위험 등급:** **P1 / Level 1 (읽기 전용 UI, 브라우저 측 이미지 분석)**
- **사전 조건:** TC-11의 병 테두리 상세 정보가 활성화된 상태.
- **테스트 데이터 및 영상 프레임 조건:** 실제 Chrome 검증 사례 (전체 ROI: 118.47, 병 외곽 내부: 64.88, 내부 림: 계산 불가, 배경: 238.87).
- **단계별 사용자 조작:**
  1. `<div className="edge-region-statistics">` 영역 확인.
  2. 4대 영역(A, B, C, D)의 평균 / 중앙값 / 표준편차 GV 및 픽셀 수 확인.
  3. C 영역(내부 림)의 '계산 불가' 안내 문구 확인.
- **예상 UI 결과:**
  - 각 영역 카드에 `평균 / 중앙값 / 표준편차 GV: XX.XX / XX.XX / XX.XX` 및 픽셀 수/면적비 표출.
  - 내부 림이 완전히 닫힌 원으로 검출되지 않았을 때: `계산 불가 — 외곽 분할이 불확실하거나 해당 경계가 완전히 닫히지 않았습니다. 추정값을 채우지 않습니다.` 문구가 표시됨 (정상 동작).
  - 하단에 "서버는 기존 전체 ROI 평균(125.0)을 유지하며, 영역별 GV는 서버 품질/최종 판정에 미반영" 안내문 표시.
- **예상 API 또는 데이터 검증:**
  - 가상의 서버 `quality_metrics` API 구조를 단언하지 않음 (브라우저 캔버스 픽셀 데이터 기반 분석).
- **PASS / FAIL 판정 기준:**
  - PASS: 4대 영역 통계 및 미검출 시 '계산 불가' 처리가 정직하게 렌더링됨.
  - FAIL: 수치가 `NaN`으로 깨지거나, 계산 불가 상황에서 엉뚱한 가짜 수치가 채워짐.
- **Gemini Computer Use 담당 작업:**
  - 4개 카드 레이아웃이 가지런하고 수치가 겹치지 않는지 확인.
- **Playwright 담당 작업:**
  - `.edge-region-statistics` 내부 카드 텍스트 파싱 및 수치 유효성 검증.
- **실패 시 확보할 증거:** `region_gv_display_error.png`.
- **상태 변경 및 복구 방법:** 상태 변경 없음.

---

### [그룹 C] 판정·세션·안전성 (TC-13 ~ TC-15)

---

#### TC-13. PatchCore 모델 판정과 서버 최종 판정 분리 확인
- **테스트 목적:** 조도 저하(WARNING_LOW_BRIGHTNESS) 발생 시 모델 판정이 OK이더라도 서버 규칙 2번에 의해 최종 판정이 `REINSPECT`로 분리 확정되는 오판 방지 비즈니스 로직을 검증한다.
- **우선순위 / 위험 등급:**  
  - **기존 결과 조회 시: Level 1 (읽기 전용, 권장)**  
  - **신규 검사 실행 시: Level 2 (상태 변경)**
- **사전 조건:** 조도 경고가 포함된 검사 결과 로드 (예: 시나리오 T03 검사 데이터 `INSP-001398`).
- **테스트 데이터 및 영상 프레임 조건:** 기존 저장된 `INSP-001398` (평균 GV: 81.24).
- **단계별 사용자 조작:**
  1. 검사 결과 패널 확인.
  2. `PatchCore 모델 판정`과 `서버 최종 판정` 뱃지를 각각 대조.
- **예상 UI 결과:**
  - `PatchCore 모델 판정`: `OK` (초록)
  - `영상 품질`: `WARNING_LOW_BRIGHTNESS` (노랑)
  - `서버 최종 판정`: **`최종 REINSPECT`** (노랑, 사유 코드: `IMAGE_QUALITY_WARNING`)
  - 모델 판정이 OK이더라도 서버 최종 판정은 `REINSPECT`로 명확히 분리됨.
- **예상 API 또는 데이터 검증:**
  - `GET /inspections/{id}`: `result == "OK"`, `quality_status == "WARNING_LOW_BRIGHTNESS"`, `final_result == "REINSPECT"`.
- **PASS / FAIL 판정 기준:**
  - PASS: 모델 판정(OK)과 최종 판정(REINSPECT)이 분리되어 표시되고 서버 판정 불변 규칙 준수.
  - FAIL: 조도 저하인데 최종 판정이 `OK`로 자동 승인되거나, 불량품(`NG`)으로 오진단됨.
- **Gemini Computer Use 담당 작업:**
  - 두 판정 뱃지가 시각적으로 명확히 분리되어 위치하는지 확인.
- **Playwright 담당 작업:**
  - `data-verdict` 속성 및 텍스트 단언 (`result` vs `final_result`).
- **실패 시 확보할 증거:** `verdict_separation_failed.png`.
- **상태 변경 및 복구 방법:** 기존 조회 시 상태 변경 없음.

---

#### TC-14. 동일 제품 재검사 그룹 최대 3회 및 작업자 수동 확인 흐름
- **테스트 목적:** 동일 제품에 대해 최대 3회까지만 재검사가 허용되고, 3회 REINSPECT 후 작업자의 수동 확인(`MANUAL_OK` / `MANUAL_NG`)을 거치는 워크플로우를 검증한다.
- **우선순위 / 위험 등급:** **P0 / Level 2 (상태 전이 및 수동 판정 레코드 생성)**
- **사전 조건:** `REINSPECT` 판정 검사 1건 완료 상태 (Attempt 1/3).
- **테스트 데이터 및 영상 프레임 조건:** `VID-000003`의 동일 제품 영역.
- **단계별 사용자 조작:**
  1. 동일 제품 확인 체크 후 2회차 Grab 및 검사 실행 (Attempt 2/3).
  2. 동일 제품 확인 체크 후 3회차 Grab 및 검사 실행 (Attempt 3/3).
  3. 3회 완료 후 검사 버튼 비활성화 및 수동 검토 안내 배너 확인.
  4. 수동 확인 패널에서 판정(`MANUAL_OK`), 작업자 ID, 사유 입력 후 확정 버튼 클릭.
- **예상 UI 결과:**
  - 회차 뱃지가 `1/3` ➔ `2/3` ➔ `3/3`으로 순차 증가.
  - 3회 초과 시 4회차 검사 실행 버튼이 원천 차단됨.
  - Gemini Vision 호출은 재검사 횟수 카운트에 절대 포함되지 않음.
  - 수동 판정 완료 후 수동 확인 결과가 별도 필드로 추가되며, 원본 `final_result`는 수정되지 않고 보존됨.
- **예상 API 또는 데이터 검증:**
  - `POST /reinspection-groups/{group_id}/manual-reviews` 호출: `status: 200`.
  - 상세 저장 경로 및 내부 스키마는 **"Codex 구현 시 실제 코드 확인 필요"**로 표기.
- **PASS / FAIL 판정 기준:**
  - PASS: 3회 초과 차단, 수동 확인 레코드 정상 추가, 원본 검사 불변성 준수.
  - FAIL: 4회차 재검사가 실행되거나, 수동 판정이 원본 검사의 `final_result`를 덮어씀.
- **Gemini Computer Use 담당 작업:**
  - 수동 검토 입력 폼의 레이아웃이 깨지지 않고 사용자 입력을 명확히 받는지 확인.
- **Playwright 담당 작업:**
  - 재검사 회차 텍스트 단언 및 4회차 차단 상태 단언.
- **실패 시 확보할 증거:** `reinspection_limit_breached.png`.
- **상태 변경 및 복구 방법:** 재검사 그룹 상태에 수동 기록 1건 추가.

---

#### TC-15. Gemini Vision Judge 및 Diagnostic Agent 기존 결과 표시
- **테스트 목적:** 실제 외부 Google API 호출 없이도 기존에 안전하게 저장된 실제 LIVE 검증 결과(예: `INSP-001694`)가 올바르게 표출되는지 검증하고, 동의 없는 외부 전송을 방지한다.
- **우선순위 / 위험 등급:** **P1 / Level 1 (기본 조회 모드) [LIVE 호출은 Level 3 별도 승인]**
- **사전 조건:** 실제 LIVE 검증 결과가 저장된 검사 레코드 로드 (실제 검증 사례: `INSP-001694`의 저장된 Gemini Judge NG 결과와 서버 REINSPECT 결과가 별도 표시됨).
- **테스트 데이터 및 영상 프레임 조건:** `INSP-001694` (실제 검증 모델: `gemini-3.8-flash`).
- **단계별 사용자 조작:**
  1. `2차 · Gemini Vision Judge` 서브탭 활성화 (`#judge-inspection-tab`).
  2. 저장된 결과 표시 확인 (모델명 `gemini-3.8-flash`, 시각적 소견, 독립 참고 의견 안내).
  3. 외부 전송 동의 체크박스가 기본적으로 해제(Unchecked)되어 있는지 확인.
  4. 다른 검사나 새 Crop 선택 시, 이전 동의 체크박스가 자동 해제되는지 확인.
- **예상 UI 결과:**
  - 저장된 보고서 조회 시 외부 네트워크 요청 없이 즉시 결과 렌더링.
  - Gemini Judge의 NG 소견과 서버의 REINSPECT 판정이 별도로 표시됨 (판정 불변).
  - 동의 체크박스를 누르지 않으면 실시간 분석 요청 버튼이 비활성화됨.
- **예상 API 또는 데이터 검증:**
  - `GET /inspections/INSP-001694/vision-review` 호출: 저장된 캐시 결과 반환.
  - **주의:** Google API 호출은 FastAPI 백엔드에서 발생할 수 있으므로, 브라우저 네트워크 모니터링뿐 아니라 **서버 로그 감사(호출 카운터 0 확인)**를 함께 검증해야 함.
- **PASS / FAIL 판정 기준:**
  - PASS: 외부 호출 없이 저장된 `gemini-3.8-flash` 결과가 올바르게 표출되고, 동의 체크박스가 안전하게 관리됨.
  - FAIL: 단순 조회만으로 백엔드에서 외부 Google API가 호출되거나 판정이 임의 덮어씌워짐.
- **Gemini Computer Use 담당 작업:**
  - 모델명(`gemini-3.8-flash`) 및 주의 안내 캡션("독립 2차 참고용이며 서버 최종 판정을 대체하지 않음") 시각적 확인.
- **Playwright 담당 작업:**
  - 체크박스 미체크 시 분석 버튼 `disabled` 속성 검증.
- **실패 시 확보할 증거:** `unauthorized_api_call.png`.
- **상태 변경 및 복구 방법:** 상태 변경 없음.

---

## 3. 테스트 데이터 Manifest 규격 (검증 예정 예시)

향후 모델의 실제 검출력(Precision, Recall, False Positive, False Negative)을 정량 산출하기 위해, 영상의 각 프레임과 병 인스턴스에 대한 Ground Truth를 관리할 `test_data/manifest_vid000003.json` 규격을 제안합니다.

```json
{
  "manifest_version": "1.0.0",
  "video_id": "VID-000003",
  "video_spec": {
    "width": 1920,
    "height": 480,
    "fps": 30.0,
    "frame_count": 480,
    "duration_seconds": 16.0,
    "codec": "h264"
  },
  "bottles": [
    {
      "bottle_instance_id": "BOTTLE-VID03-EXAMPLE-001",
      "frame_index": 120,
      "recommended_roi": {
        "x": 800,
        "y": 40,
        "width": 320,
        "height": 400
      },
      "ground_truth_label": "UNKNOWN",
      "defect_type": null,
      "label_source": "UNVERIFIED_PENDING_AUDIT",
      "verification_status": "PENDING"
    },
    {
      "bottle_instance_id": "BOTTLE-VID03-EXAMPLE-002",
      "frame_index": 240,
      "recommended_roi": {
        "x": 820,
        "y": 38,
        "width": 320,
        "height": 402
      },
      "ground_truth_label": "UNKNOWN",
      "defect_type": null,
      "label_source": "UNVERIFIED_PENDING_AUDIT",
      "verification_status": "PENDING"
    }
  ]
}
```
> **원칙:** 위 프레임 번호와 좌표는 검증 예정 예시일 뿐이며, 전수 검증 전까지 라벨을 임의로 양품(`OK`)이나 불량(`NG`)으로 확정하지 않고 `UNKNOWN`으로 관리합니다.

---

## 4. 시나리오 요약 및 실행 위험도 매트릭스

| ID | 시나리오 제목 | 우선순위 | 위험도 등급 | 구현 및 자동화 상태 | 주요 검증 포인트 |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **TC-01** | VID-000003 영상 선택 및 16초 재생 확인 | P0 | Level 1 | **Phase 1 자동화 대상** | `select#live-video-source` 동적 선택 및 검증 |
| **TC-02** | 영상 Pause → ROI 선택 → Grab Crop 생성 | P0 | Level 2 | Phase 2 자동화 대상 | `POST /videos/VID-000003/grab`, `CAP-` 발급 |
| **TC-03** | 신규 정상 Capture에서 검사 버튼 활성화 확인 | P0 | Level 1 (선행의존) | Phase 2 자동화 대상 | TC-02 Capture 의존, 검사 버튼 활성화 확인 |
| **TC-04** | Grab 검사 완료 후 점수/품질/최종판정 표시 | P0 | Level 2 | Phase 2 자동화 대상 | `POST /captures/{id}/inspect`, 판정 분리 표출 |
| **TC-05** | 같은 Capture 중복 검사 차단 및 새 제품 전환 | P0 | Level 2 | Phase 2 자동화 대상 | 동일 Capture 버튼 비활성화, 새 Grab 전환 |
| **TC-06** | 오래된 RIG·pending 상태 및 404 안전 복구 | P1 | Level 2 | Phase 2 자동화 대상 | LocalStorage 정리, `[새 제품 검사 시작]` 복구 |
| **TC-07** | Grab / 정적 이미지 상위 탭 전환 및 보존 | P1 | Level 1 | **Phase 1 자동화 대상** | 기존 검사 활용, `#grab-inspection-tab` 보존 |
| **TC-08** | 1차 PatchCore / 2차 Judge 서브탭 전환 | P1 | Level 1 | **Phase 1 자동화 대상** | 기존 검사 활용, 서브탭 전환 및 레이아웃 유지 |
| **TC-09** | 검사 ID 일치 및 이전 결과 잔존 방지 | P0 | Level 1 | Phase 2 자동화 대상 | 입력 ID와 결과 ID 1:1 일치 단언 |
| **TC-10** | Heatmap ON/OFF, Zoom/Pan, Pixel Inspector | P1 | Level 1 | **Phase 1 자동화 대상** | 기존 검사 활용, 툴바 토글, 픽셀 좌표 계측 |
| **TC-11** | 병 외곽 Edge·내부 림 후보 ON/OFF | P1 | Level 1 | **Phase 1 자동화 대상** | 초록 외곽/노랑 림, 성공·불확실·실패 표출 |
| **TC-12** | 영역별 GV와 계산 불가 상태 확인 | P1 | Level 1 | **Phase 1 자동화 대상** | 4대 영역 통계, 림 미닫힘 시 계산 불가 표출 |
| **TC-13** | 모델 판정과 서버 최종 판정 분리 확인 | P0 | Level 1 (조회) | Phase 2 자동화 대상 | 모델 OK vs 서버 REINSPECT 판정 분리 단언 |
| **TC-14** | 동일 제품 재검사 최대 3회 및 수동 확인 | P0 | Level 2 | Phase 2 자동화 대상 | 3회 초과 차단, 수동 판정 레코드 추가 |
| **TC-15** | Gemini Vision Judge 기존 결과 표시 및 동의 | P1 | Level 1 (조회) | Phase 2 자동화 대상 | `INSP-001694`, `gemini-3.8-flash`, 동의 가드레일 |
