# VisionInsight E2E 검사 체인 통합 상태 독립 감사 보고서

- **작성일자:** 2026-10-19
- **발표 예정일:** 2026-10-20
- **작성 주체:** 독립 기술 검토자 및 발표 자료 담당자 (Independent Technical Reviewer)
- **문서 목적:** LiveView부터 실제 이미지 검사, 로그 저장, Gemini AI 보고서, Gemini Vision, React UI 표시에 이르는 전체 E2E 파이프라인의 실제 구현 상태와 검증 근거를 엄밀하게 감사하고 누락·미연결 사항을 도출

---

## 1. E2E 검사 체인 8단계 통합 상태 총괄표

VisionInsight의 전체 E2E 검사 파이프라인 8개 핵심 단계에 대한 엄밀한 구현 및 검증 분류입니다.

| 단계 | 파이프라인 구간 | 최종 상태 분류 | 핵심 구현 파일 및 실측 증거 | 비고 및 주의사항 |
| :---: | :--- | :---: | :--- | :--- |
| **1** | LiveView → ROI → Grab → Crop 저장 | **실제 구현 및 실환경 검증 완료** | `backend/video_source.py`<br>`backend/grab_inspection.py`<br>`backend/capture_store.py`<br>`frontend/src/components/LiveView.tsx` | • H.264 비디오 1920×480 프레임 Grab 검증 완료<br>• Vite Same-Origin Proxy를 통한 SameSite=Strict 쿠키 인가 통과<br>• 무손실 Crop PNG 생성 및 SHA256 해시 검증 완료 |
| **2** | 실제 PatchCore 추론 → 이상 점수 → Heatmap | **과거 검증 완료, 현재 재검증 필요**<br>(정적 이미지 및 단일 Grab 검사 실측 기록 보유, 현 세션 재실행 필요) | `backend/ml/patchcore_inferencer.py`<br>`backend/inspection.py`<br>`backend/anomaly_map_store.py`<br>`data/outputs/inspection_anomaly_maps/` | • 정적 이미지(T01~T06) 단일 추론 42.53ms 검증 기록 보유<br>• Grab Crop 단일 실제 추론 기록(INSP-001652: Score 40.1631) 존재<br>• Step 10에서는 모델 추론 0회(NOT TESTED)<br>• **컨베이어 자동(AUTO) 실시간 투입은 미연결(MANUAL Grab만 완성)** |
| **3** | OK / NG / REINSPECT / ERROR 판정 | **실제 구현 및 오프라인 검증 완료**<br>(결정표 8개 분기 단위 테스트 100% PASS, 실환경 브라우저 연동 대기) | `backend/decision.py`<br>`tests/test_day10_decision_matrix.py` | • 결정론적 6대 우선순위 판정 로직<br>• 영상 품질 저하(`WARNING_LOW_BRIGHTNESS`) 시 모델 NG보다 REINSPECT 우선 적용<br>• Step 10 격리 실행 89 PASS에서 결정표 전수 통과 확인 |
| **4** | 검사 결과 JSONL 및 실행 로그 저장 | **실제 구현 및 실환경 검증 완료** | `backend/storage.py`<br>`data/inspections.jsonl`<br>`data/inspection_logs.jsonl` | • Append-only 단조 증가 감사 로그 완비<br>• 생명주기 이벤트(STARTED, LOADED, ANALYZED, COMPLETED, FAILED) 자동 기록<br>• 원본 판정 및 감사 추적성 보존 |
| **5** | Inspection ID로 검사·이미지·로그 연결 | **실제 구현 및 실환경 검증 완료** | `backend/inspection.py`<br>`backend/reinspection_store.py`<br>`docs/inspection-data-schema.md` | • `product_id`와 고유 `inspection_id` 완전 분리<br>• `INSP-XXXXXX` 단일 키로 검사 결과, 이벤트 로그, Anomaly Map Sidecar(`.npz`, `.json`, `.png`), Crop 메타데이터 100% 연결<br>• 재검사 그룹(`RIG-*`)과 연결 추적 지원 |
| **6** | Gemini Diagnostic Agent (Function Calling 보고서) | **과거 검증 완료, 현재 재검증 필요**<br>(Day 4 실서버 API 통과, Day 7 코드 리팩터링 후 오프라인 Mock 완료, 현 LIVE 미호출) | `backend/agent/service.py`<br>`backend/agent/tools.py`<br>`tests/test_day7_step2_agent_offline_mock.py`<br>`docs/day4-step4-gemini-validation.md` | • 4대 조회 도구(결과, 로그, 품질, 이력) 기반 Fact Catalog 구축<br>• Day 4 실서버 E2E 통과(T01: 13.58s, T03: 24.60s, T05: 16.33s, T06: 26.37s)<br>• Day 7 `v1beta` 명시 및 구조화 로깅 리팩터링 완료(Mock 6 PASS)<br>• **발표 당일 실시간 호출 검증 필요** |
| **7** | Gemini Vision REINSPECT 실제 Crop 2차 분석 | **코드 구현 및 오프라인 Fake/Mock 검증만 완료**<br>(LIVE 전송은 안전 게이트로 의도적 비활성화/차단) | `backend/vision_review.py`<br>`backend/vision_review_api.py`<br>`frontend/src/components/VisionReviewPanel.tsx` | • REINSPECT 판정된 Crop PNG 바이트만 전달하는 독립 파이프라인 구현<br>• 별도 상태 저장소(`vision_reviews/state.json`) 및 OS Lock 적용<br>• 신규 Vision 단위 54 PASS / Mock 7 PASS 통과<br>• **실제 Gemini Vision LIVE 연동은 비활성(DISABLED)** |
| **8** | AI 보고서가 UI에 표시되는 경로 | **과거 저장 결과 조회 및 UI 렌더링 검증 완료**<br>(신규 생성 시연은 브라우저 E2E 검증 필요) | `frontend/src/components/AgentPanel.tsx`<br>`frontend/src/components/VisionReviewPanel.tsx`<br>`frontend/src/components/ImageView.tsx` | • Agent 진단 보고서: Fact와 Hypothesis 분리 렌더링 검증 완료<br>• 과거 검사 ID(`INSP-001396`, `INSP-001398`) 숏컷 조회 정상 동작<br>• Vision Review 패널: 독립 카드 형태로 배치 완료 (Fake 배지 표기) |

---

## 2. 단계별 세부 감사 및 검증 근거

### [단계 1] LiveView → ROI → Grab → Crop 저장
- **상태:** **실제 구현 및 실환경 검증 완료**
- **아키텍처 및 구현 내용:**
  1. 컨베이어 벨트 H.264 MP4 스트림(1920×480)을 HTML5 Video 플레이어로 재생 (`LiveView.tsx`).
  2. 사용자가 원하는 프레임에서 `[Pause]` 후 마우스 드래그로 직사각형 ROI를 지정.
  3. `[Grab & Inspect]` 클릭 시 백엔드 `POST /api/videos/{video_id}/grab` 호출.
  4. Vite 프록시(`/api` → `http://127.0.0.1:8000`)를 통해 브라우저 `SameSite=Strict`, `HttpOnly` 세션 쿠키가 온전히 전달되어 401 권한 오류 원천 차단 (`docs/day6-phase-f1-browser-grab-hotfix.md`).
  5. 백엔드 `GrabInspectionRuntime`이 1920×480 원본 프레임에서 half-open ROI 좌표로 무손실 슬라이싱 수행 (`backend/grab_inspection.py:167`).
  6. 슬라이싱된 이미지를 `data/outputs/grab_inspection_inputs/IMG-GRAB-*.png`로 영구 저장하고, SHA256 해시를 manifest에 기록.
- **실측 검증 근거:**
  - Chrome 브라우저에서 `CAP-*` 생성(201 Created) 및 782KB 무손실 PNG 수신 확인.
  - INSP-001652 실제 검사에서 Crop 크기 284×272, uint8 BGR 3채널, SHA256 `8eaca8529474f2493b2e854937186dc4ed34afabaa3a561cd036a1a4da8ca2a7` 정합성 확인.
  - 프론트엔드 단위 테스트 39 PASS 통과 (`test_image_transform.mjs`, `test_grab_inspection.mjs` 등).

### [단계 2] 실제 PatchCore 추론 → 이상 점수 → Heatmap
- **상태:** **과거 검증 완료, 현재 재검증 필요** (컨베이어 자동 AUTO 검사는 미연결)
- **아키텍처 및 구현 내용:**
  1. OpenCV로 디코딩된 BGR 이미지를 `patchcore_inferencer.predict(image)`에 전달 (`backend/inspection.py:494-518`).
  2. ResNet-18 Backbone 기반 임베딩 추출 후 Coreset 메모리 뱅크(`[9216, 384]`, 24.18MB)와의 최근방 이웃 거리 계산.
  3. 스칼라 이상 점수(`anomaly_score`) 산출 및 고정 임계값(`34.1442`) 비교: 초과 시 모델 소견 `NG`, 이하 시 `OK`.
  4. 추론 시 생성된 2차원 Anomaly Map(`[256, 256]`)을 추출하여 Sidecar Artifact(`.npz`, `.json`, `_overlay.png`)로 영구 저장 (`backend/anomaly_map_store.py`).
  5. 프론트엔드 `ImageView`에서 Jet Colormap 기반 반투명 히트맵 오버레이 렌더링.
- **실측 검증 근거 및 한계:**
  - 과거 83장 테스트 세트 평가에서 단일 추론 평균 42.53ms 기록 (`docs/patchcore-cpu-benchmark.md`).
  - Grab Crop 실제 검사 기록: `INSP-001652`에서 anomaly score 40.1631317, model result NG 산출 확인 (`docs/day7-step8-reinspection-workflow-and-manual-review.md`).
  - **한계:** Step 10에서는 모델을 로드하거나 추론하지 않았음(0회). 또한 컨베이어 실시간 비디오 스트림 통과 시 자동으로 Active ROI를 잘라 추론하는 "AUTO 파이프라인"은 미연결이며, 현재는 사용자가 Grab 버튼을 누르는 "MANUAL 검사"만 동작함.

### [단계 3] OK / NG / REINSPECT / ERROR 판정
- **상태:** **실제 구현 및 오프라인 검증 완료**
- **아키텍처 및 구현 내용 (`backend/decision.py:28-85`):**
  - 시스템 판정의 6대 우선순위:
    1. 파이프라인 실행 실패 → `ERROR / INSPECTION_FAILED`
    2. 영상 품질 상태가 NORMAL 아님 (조도 저하 등) → `REINSPECT / IMAGE_QUALITY_WARNING` (모델 소견 NG보다 우선)
    3. 모델 미완료 또는 raw 소견 UNKNOWN → `REINSPECT / DEFECT_DETECTION_UNAVAILABLE`
    4. NORMAL 품질 + raw NG → `NG / PRODUCT_ANOMALY_DETECTED`
    5. NORMAL 품질 + raw OK → `OK / ALL_CHECKS_PASSED`
    6. 기타 미정의 조합 → `REINSPECT / UNKNOWN_STATE_COMBINATION`
- **실측 검증 근거:**
  - `tests/test_day10_decision_matrix.py`에서 production `determine_final_verdict` 함수를 직접 호출하여 8대 조합 전수 검증 통과 (89 PASS 격리 테스트 스위트 내).
  - INSP-001652 실제 사례: 모델 소견은 NG(40.1631 > 34.1442)였으나, 평균 조도 59.76이 기준치 125.0 미만이어서 영상 품질 경고(`WARNING_LOW_BRIGHTNESS`)가 발동, 최종 판정은 `REINSPECT`로 결정론적 확정됨.

### [단계 4] 검사 결과 JSONL 및 실행 로그 저장
- **상태:** **실제 구현 및 실환경 검증 완료**
- **아키텍처 및 구현 내용 (`backend/storage.py`):**
  1. `data/inspections.jsonl`: 검사 ID, 제품 ID, 이미지 ID, 이상 점수, 품질 지표, 모델 소견, 최종 서버 판정, 소요 시간 등을 Append-only JSON 객체로 영구 저장.
  2. `data/inspection_logs.jsonl`: 검사 시작(`INSPECTION_STARTED`), 이미지 로드(`IMAGE_LOADED`), 품질 분석 완료(`ANALYSIS_COMPLETED`), 추론 완료(`INSPECTION_COMPLETED`) 등 생명주기 이벤트를 밀리초 타임스탬프와 함께 기록.
- **실측 검증 근거:**
  - 실제 운영 파일 `data/inspections.jsonl`에 INSP-000001부터 INSP-001652에 이르는 실측 이력 누적 보존.
  - 감사 추적성(Audit Trail) 보장: 과거 검사 이력은 일체 수정되거나 덮어쓰이지 않음.

### [단계 5] Inspection ID로 검사·이미지·로그 연결
- **상태:** **실제 구현 및 실환경 검증 완료**
- **아키텍처 및 구현 내용:**
  1. 제품 식별자(`product_id`)와 독립된 단조 증가 순차 고유 검사 ID(`INSP-XXXXXX`) 발급.
  2. 단일 검사 ID로 다음 자산이 100% 참조 무결성으로 연결됨:
     - 검사 결과: `GET /inspections/{inspection_id}`
     - 실행 이벤트 로그: `GET /inspections/{inspection_id}/logs`
     - Anomaly Map Sidecar: `GET /inspections/{inspection_id}/anomaly-map` (`.json`, `.npz`, `_overlay.png`)
     - 원본 입력 이미지: `GET /images/{image_id}` 또는 `GET /captures/{capture_id}/image`
     - 재검사 그룹: `GET /reinspections/{group_id}` (최대 3회 재검사 ID 체인 추적)
- **실측 검증 근거:**
  - `docs/inspection-data-schema.md`에 정의된 데이터 계약에 따라 백엔드 라우터 및 프론트엔드 API 클라이언트가 완전 구현됨.
  - Step 8 재검사 워크플로우 테스트 79 PASS에서 그룹-검사 간 양방향 링크 검증 완료.

### [단계 6] Gemini Diagnostic Agent의 Function Calling 도구와 보고서 생성
- **상태:** **과거 검증 완료, 현재 재검증 필요** (Mock 검증 100% 완료, LIVE 검증 대기)
- **아키텍처 및 구현 내용 (`backend/agent/service.py`, `backend/agent/tools.py`):**
  1. LLM에게 원본 정답 라벨이나 임의 파일 경로를 제공하지 않고, 4대 읽기 전용 도구만 제공:
     - `get_inspection_result`: 검사 점수, 품질 상태, 모델 소견, 서버 최종 판정 조회
     - `get_execution_logs`: 단계별 처리 시간 및 이벤트 타임라인 조회
     - `analyze_image_quality`: 밝기 통계(mean, std, min, max) 및 조도 판정 상세 조회
     - `get_inspection_history`: 동일 제품/유사 검사의 과거 이력 조회
  2. **근거 기반 그라운딩 (Deterministic Grounding):** 에이전트가 생성한 모든 보고서는 도구 반환값과 JSON Pointer로 1:1 일치해야 하며, Evidence Store에 기록된 Fact만 인정됨.
  3. **판정 보호 가드레일 (Decision Guardrail):** LLM이 서버의 `final_result`를 임의로 번복하거나 가짜 결함을 지어내는 환각 원천 차단.
- **실측 검증 근거:**
  - Day 4 실서버 Gemini API 실측치:
    - T01 (정상 병 INSP-001396): 13.578초, 4,706 토큰, 관측 사실 6개 100% 통과 (PASS)
    - T03 (조도 저하 INSP-001398): 24.600초, 9,873 토큰, 관측 사실 12개 100% 통과 (PASS)
    - T05 (영상 로드 실패 INSP-001405): 16.333초, 11,426 토큰, 관측 사실 17개 100% 통과 (PASS)
    - T06 (미탐 한계 INSP-001406): 26.371초, 7,202 토큰, OK 판정 불변 보존 (PASS)
  - Day 7 리팩터링: `api_version="v1beta"` 명시 주입, 예외 마스킹 및 구조화 관측성 도입, 오프라인 Mock 테스트(`tests/test_day7_step2_agent_offline_mock.py`) 6종 ALL PASS.
  - **주의:** 안전 규칙 준수를 위해 Step 10에서는 실제 Gemini API 호출 0회를 유지하였으므로, 발표 직전 리허설에서 단 1회의 실서버 호출 확인이 권장됨.

### [단계 7] REINSPECT의 Gemini Vision 실제 Crop 분석 경로
- **상태:** **코드 구현 및 오프라인 Fake/Mock 검증만 완료 (LIVE 연결은 안전 게이트로 의도적 차단됨)**
- **아키텍처 및 구현 내용 (`backend/vision_review.py`, `backend/vision_review_api.py`):**
  1. 기존 Diagnostic Agent(로그/수치 기반 텍스트 분석)와 완전히 독립된 신규 시각 분석 엔진.
  2. 오직 `LIVEVIEW_GRAB` 출처이자 최종 판정이 `REINSPECT`인 검사에 대해서만 실행 허용.
  3. 클라이언트가 보낸 임의의 이미지나 URL을 받지 않고, 서버에 영구 보존된 무손실 원본 Crop PNG 바이트만 추출하여 해시(SHA256)를 재검증한 후 모델에 전달.
  4. 히트맵 오버레이나 정답 라벨, 이상 점수는 모델 프롬프트에서 완전히 배제하여 순수한 시각적 외관 관찰만 수행하도록 강제.
  5. 응답 분류: `DEFECT_SUSPECTED`, `QUALITY_ISSUE`, `NO_VISIBLE_DEFECT`, `INCONCLUSIVE`, `ANALYSIS_FAILED` 5종으로 엄격 제한.
  6. 독립 저장소: `data/outputs/vision_reviews/state.json`에 원자적 OS Lock으로 저장되며, 서버의 원본 `final_result`를 절대 수정하지 않는 제2 소견(Second Opinion)으로만 작동.
- **실측 검증 근거:**
  - 신규 Fake Vision 백엔드 테스트 46 PASS + 결정표 8 PASS = **54 PASS** 통과 (`tests/test_vision_review.py`).
  - Chrome Mock 테스트 7 PASS 통과.
  - **한계:** 후보 모델 `gemini-4-argon`의 실제 이미지 지원 및 API 호환성이 미검증 상태이며, 비인가 외부 전송 및 과금 방지를 위해 LIVE 호출 어댑터는 안전하게 DISABLED 상태로 동결되어 있음.

### [단계 8] AI 보고서가 UI에 표시되는 경로
- **상태:** **과거 저장 결과 조회 및 UI 렌더링 검증 완료**
- **아키텍처 및 구현 내용:**
  1. `AgentPanel.tsx`: `GET /analyze/{inspection_id}` 호출을 통해 진단 보고서 수신.
     - 판정 배지(OK/NG/REINSPECT)를 서버 결과와 동일하게 표시.
     - Observed Facts(관측 사실)와 Hypotheses(가설), Recommended Actions(권장 조치)를 아코디언 및 카드 UI로 구분 렌더링.
     - Fact 클릭 시 근거 JSON Pointer 앵커링 툴팁 제공.
  2. `VisionReviewPanel.tsx`: `GET /inspections/{inspection_id}/vision-review` 호출을 통해 독립 렌더링.
     - 시각적 소견 분류(DEFECT_SUSPECTED 등) 배지 및 세부 관찰 내용 표시.
     - 하단에 황색 `[FAKE_TEST / OFFLINE MOCK]` 배지를 표시하여 실서버 결과와 명확히 구분.
- **실측 검증 근거:**
  - 프론트엔드 빌드 및 단위 테스트 39 PASS 통과 (`npm run build`, `tsc -b` 성공).
  - 과거 저장된 `INSP-001396`(T01), `INSP-001398`(T03)에 대한 진단 보고서 숏컷 로드 및 렌더링 정상 동작 확인.

---

## 3. 핵심 개념 구분: Diagnostic Agent vs Gemini Vision

발표자 및 검토자가 가장 혼동하기 쉬운 두 가지 AI 기능의 명확한 기술적 차이점입니다:

| 비교 항목 | 기존 Gemini Diagnostic Agent (Day 4 완성) | 신규 Gemini Vision (Day 7 신규 구현) |
| :--- | :--- | :--- |
| **분석 대상** | **검사 메타데이터, 이벤트 로그, 조도 통계 수치** (텍스트/JSON) | **REINSPECT 판정된 원본 병 Crop PNG 이미지 자체** (바이너리 바이트) |
| **입력 데이터** | `tools.py`가 반환하는 점수, 판정, 로그 타임라인, 밝기 평균/표준편차 | 서버가 SHA256을 검증한 무손실 BGR Crop 이미지 바이트 스트림 |
| **동작 메커니즘** | Gemini의 **Function Calling** (4대 읽기 전용 도구 자율 호출) | Gemini 멀티모달 **Vision Understanding** (이미지 프롬프트 직접 입력) |
| **목적 및 역할** | "왜 REINSPECT/ERROR가 발생했는가?"에 대한 **공정 원인 추론 및 감사 보고서 작성** | "조도 저하 상태의 병 사진에 실제 균열이나 이물이 보이는가?"에 대한 **시각적 2차 소견 제시** |
| **최종 판정 영향** | 서버 판정 번복 불가 (가드레일로 불변 보존) | 서버 판정 번복 불가 (작업자 참고용 독립 의견으로 보존) |
| **현재 연동 상태** | **오프라인 Mock 100% 검증 / 과거 실서버 API 검증 기록 보유** | **오프라인 Fake 100% 검증 / 실서버 LIVE 전송은 안전 게이트로 차단** |

> **중요 주의사항:** 시연 중 과거에 이미 생성되어 저장된 AI 보고서(`INSP-001396` 등)를 버튼 클릭으로 불러오는 동작은 **"저장된 데이터의 성공적인 조회"**이지, **"신규 AI 보고서의 실시간 생성 성공"**이 아닙니다. 발표 시 이 점을 정직하게 구분하여 설명해야 합니다.

---

## 4. 발견된 누락 사항 및 기술적 연결 갭 (Gaps)

1. **LiveView ROI Crop의 PatchCore 자동(AUTO) 파이프라인 부재:**
   - LiveView에서 잘라낸 Crop은 현재 사용자가 수동으로 검사하는 MANUAL 워크플로우에만 연결되어 있습니다. 컨베이어 스트림에서 트리거 신호를 받아 자동으로 Crop 후 추론하는 실시간 AUTO 파이프라인은 향후 과제입니다.
2. **최신 임시 Capture PNG 4개의 비영속성 리스크:**
   - `data/outputs/captures/`에 존재하는 임시 Capture 4개는 서버 재시작 시 `CaptureStore.close()`에 의해 자동 삭제되는 메모리 관리 자산입니다. 영구 저장된 Crop(`IMG-GRAB-*`)과 달리, 임시 Capture는 서버 재시작 전에 백업이 필수적입니다.
3. **Gemini Vision LIVE 비활성화 상태:**
   - `VisionReviewPanel.tsx`의 실시간 분석 실행 버튼은 기본적으로 DISABLED이며, 백엔드도 LIVE 호출 어댑터가 의도적으로 차단되어 있습니다. 발표 시 "오프라인 아키텍처 및 데이터 안전 격리 완성, LIVE 어댑터는 실환경 검증 게이트 대기 중"으로 설명해야 합니다.
4. **OpenCV 기하 검사 PoC의 미실행 상태:**
   - 병 입구 림(Rim)의 진원도 및 동심도를 측정하는 `scripts/experiments/opencv_rim_inspection.py`는 독립 스크립트 초안으로만 작성되어 있으며, 실제 검사 파이프라인이나 판정 규칙에 연결되지 않았습니다.
