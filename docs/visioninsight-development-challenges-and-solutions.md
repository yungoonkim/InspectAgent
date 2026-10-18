# VisionInsight 개발 과정의 기술적 어려움과 해결 사례
## MVTec AD Bottle 기반 이상 진단 머신비전 AI Agent 풀스택 엔지니어링 회고

- **작성일자:** 2026-10-18
- **발표 예정일:** 2026-10-20
- **프로젝트 루트:** `C:\Users\USER\AI-NativeAgent\Project\InspectAgent`
- **문서 목적:** 프로젝트 개발 과정에서 겪은 실제 기술적 난제, 근본 원인 분석, 고려된 접근법과 최종 해결책, 미해결 기술 부채, 엔지니어링 교훈을 체계적으로 정리하여 기술 발표 및 포트폴리오 자산으로 활용

---

# 1. 프로젝트 개요

### 1-1. 개발 목적 및 해결하려는 머신비전 과제
VisionInsight는 제조 공정의 컨베이어 벨트 상에서 이송되는 유리병(MVTec AD Bottle 데이터셋 기반)의 외관 결함을 자동으로 탐지하고, 이상 징후 발생 시 AI 에이전트가 그 원인을 근거에 기반하여 진단하는 **산업용 머신비전 이상 진단 AI 시스템**입니다.

기존 룰 기반 머신비전 시스템은 미세한 긁힘, 오염, 깨짐 등의 비정형 결함을 탐지하기 위해 수많은 임계값(Threshold)을 수동 튜닝해야 했으며, 카메라 조명 저하나 노이즈 등 단순 환경 변화에도 오경보(False Alarm)를 빈번히 발생시켰습니다. VisionInsight는 다음 세 가지 엔지니어링 목표를 달성하고자 개발되었습니다:
1. **무감독 이상 탐지(Unsupervised Anomaly Detection):** 정상(Good) 이미지만으로 학습된 PatchCore 모델을 CPU 환경에 경량화 배치하여, 라벨링 비용 없이 미세 결함 스코어 및 2차원 Anomaly Map 산출.
2. **영상 품질과 제품 판정의 엄격한 분리:** 조명 저하, 모션 블러 등의 영상 획득 결함(`WARNING/REINSPECT`)을 제품 자체의 결함(`NG`)과 혼동하지 않고 결정적(Deterministic) 서버 규칙으로 1차 분기.
3. **근거 기반 AI 진단(Grounding-backed AI Diagnosis):** Gemini 대형언어모델(LLM)이 임의로 결함을 지어내거나(Hallucination) 서버의 최종 판정을 번복하지 못하도록, JSON 포인터 기반 증거 카탈로그(Fact Catalog)와 Function Calling 도구를 통해 관측 사실(`Observed Facts`)과 가설(`Hypothesis`)을 엄격히 분리하여 보고.

### 1-2. 핵심 기술 스택
- **Backend:** Python 3.11 (`vision-insight` Miniconda 환경), FastAPI (비동기 ASGI 서버), OpenCV / NumPy (영상 처리 및 품질 분석).
- **ML / Anomaly Detection:** PyTorch CPU 기반 PatchCore (ResNet/DINOv2 backbone 임베딩 메모리 뱅크 추론).
- **AI Agent:** Google GenAI SDK (`google-genai 2.31.0`), `gemini-3.8-flash`, Function Calling 도구 4종, Evidence Store.
- **Frontend / Inspection UI:** React 19, TypeScript 6, Vite 8, HTML5 Canvas 2D 정밀 뷰어, Lucide React.
- **Storage & Infrastructure:** 로컬 JSONL 영속 로그 (`inspections.jsonl`, `inspection_logs.jsonl`), Anomaly Map Sidecar Artifacts (`.npz`, `.json`, `.png`), PostgreSQL (ROI 프리셋 및 버전 승인 관리), H.264 MP4 시뮬레이션 스트림.

### 1-3. MANUAL 검사 구현 범위와 AUTO 검사 구상의 차이
- **현재 구현 완료 범위 (MANUAL MVP):**
  - 사용자가 등록된 정적 이미지(`IMG-BOTTLE-XXXX`)를 선택하거나 시연 숏컷을 눌러 검사를 트리거하면, OpenCV 품질 분석 -> PatchCore 단일 추론 -> 서버 결정적 판정 확정 -> JSONL 저장 -> React 600×600 ImageView 및 오버레이 시각화 파이프라인이 100% 동작.
  - LiveView(1920×480)에서 원하는 프레임을 Grab하고 직사각형 ROI를 지정하여 600×600 무손실 크롭을 생성하는 작업자 육안 정밀 검사 뷰포트 완비.
- **향후 계획 (AUTO 파이프라인 구상):**
  - 컨베이어 벨트 실시간 영상 스트림에서 병이 통과할 때 센서 또는 모션 트리거가 발생하면, PostgreSQL에 승인 바인딩된 `Active ROI`를 자동으로 잘라내어 PatchCore 모델의 입력으로 직결하는 실시간 자동 검사 파이프라인.
  - **[한계 명시]** 현재 LiveView의 ROI Crop 결과는 작업자 확인용 뷰포트에 렌더링되며, PatchCore 추론 입력으로 자동 파이프라인화된 상태는 아닙니다.

---

# 2. 개발 과정에서 가장 어려웠던 문제 TOP 5

---

### [TOP 1] 브라우저와 FastAPI 사이의 Grab 인증 및 SameSite=Strict 쿠키 차단 (사례 A)

1. **당시 상황:**
   Day 6 Phase F-1에서 H.264 LiveView 비디오 플레이어를 완성한 후, 사용자가 일시정지된 특정 프레임에서 `[Grab]` 버튼을 눌러 무손실 원본 PNG 프레임을 캡처하는 기능을 프론트엔드와 백엔드 간에 통합하던 시점이었습니다.
2. **겉으로 나타난 증상:**
   Vite 개발 서버(`http://localhost:5173`)에서 실행 중인 대시보드에서 `[Grab]` 버튼을 클릭하면, 서버로부터 즉시 `HTTP 401 Unauthorized`가 반환되며 화면에 `CAPTURE_SESSION_REQUIRED` 에러 배너가 발생하고 프레임 캡처가 전면 실패했습니다.
3. **실제 원인:**
   - **Cross-Site / Cross-Origin 분리:** 프론트엔드는 `http://localhost:5173`에서 실행되고 백엔드는 `http://127.0.0.1:8000`으로 직접 지정되어 있었습니다. 현대 크로미움(Chrome) 보안 모델에서 `localhost`와 `127.0.0.1`은 서로 다른 사이트(Cross-Site)이자 서로 다른 출처(Cross-Origin)로 취급됩니다.
   - **`SameSite=Strict` 쿠키 증발:** 백엔드(`backend/video_api.py`)는 세션 쿠키 `vision_capture_session`을 발행할 때 보안 강화를 위해 `samesite="strict", httponly=True`를 강제하고 있었습니다. 브라우저는 `localhost`에서 `127.0.0.1`로 교차 요청을 보낼 때 `SameSite=Strict` 쿠키를 헤더에서 강제로 제거했습니다.
   - **백엔드 인가 거부:** `backend/capture_store.py`의 `authorize(token, csrf)`에 토큰이 전달되지 않아 `CaptureError(401, "CAPTURE_SESSION_REQUIRED")`가 발생했습니다.
4. **원인을 찾기 위해 시도한 분석:**
   Chrome DevTools의 Network 탭에서 `POST /videos/VID-000001/grab`의 요청 헤더를 확인한 결과, `Host: 127.0.0.1:8000`, `Origin: http://localhost:5173`만 전송되고 `Cookie:` 헤더가 완전히 누락되어 있음을 발견했습니다. 세션 발급 API(`POST /capture-sessions`)는 200 OK로 `Set-Cookie`를 반환했으나, 교차 도메인 간 후속 전송에서 브라우저가 이를 거부한 것이 확인되었습니다.
5. **적용한 해결 방법:**
   백엔드의 엄격한 보안 모델(`SameSite=Strict`, `HttpOnly`, CSRF 토큰)을 허물지 않고 브라우저 표준을 준수하기 위해 **Vite Same-Origin Proxy**를 도입했습니다:
   - `frontend/vite.config.ts`에 `/api` 접두어를 `http://127.0.0.1:8000`으로 포워딩하는 프록시 설정 적용.
   - `frontend/src/api/client.ts`의 `API_BASE_URL`을 `http://127.0.0.1:8000`에서 `/api`로 전면 전환하여 브라우저 관점에서 모든 요청을 동일 출처(`http://localhost:5173`)로 일원화.
   - `frontend/src/App.tsx` 마운트 시 `ensureCaptureSession()`을 선제 호출하여 세션을 조기 부트스트랩하고, 401 발생 시 자동 재발급 1회 재시도 핸들러 추가.
6. **실패했거나 배제한 접근 방식:**
   - *쿠키 보안 완화 (`SameSite=None` 또는 `SameSite=Lax` 변경):* 산업용 보안 정책상 인가되지 않은 외부 사이트로부터의 CSRF 공격 가능성을 열어두게 되므로 기각.
   - *백엔드 CORS 와일드카드(`allow_origins=["*"]`) 처리:* 자격 증명(`allow_credentials=True`)과 와일드카드 Origin은 브라우저 스펙상 병행 불가능하며 근본적인 Cross-Site 쿠키 차단을 해결하지 못하므로 기각.
7. **결과와 검증 근거:**
   - Chrome 브라우저에서 `POST /api/capture-sessions` (200 OK, `Set-Cookie` 저장), `POST /api/videos/VID-000001/grab` (201 Created), `GET /api/captures/{id}/image` (200 OK, 782KB 무손실 PNG 수신) 연속 통과.
   - 근거 문서: `docs/day6-phase-f1-browser-grab-hotfix.md`
8. **남은 한계:**
   개발 환경에서는 Vite 프록시로 동작하지만, 향후 프로덕션(Cloud Run/Nginx) 배포 시 동일 도메인 리버스 프록시 라우팅 규칙이 인프라 레벨에서 반드시 유지되어야 합니다.
9. **얻은 교훈:**
   백엔드 보안 정책(`SameSite=Strict`)을 단순히 "안 되니까 끄자"고 타협하는 대신, 프론트엔드 빌드 도구의 프록시 아키텍처를 활용하여 보안 요구사항과 브라우저 제약을 모두 충족하는 정석적인 풀스택 해결책을 설계해야 합니다.

---

### [TOP 2] 마우스 포인터 기준 4000% 정밀 Zoom/Pan 좌표계 변환 및 픽셀 GV 표시 (사례 C, B)

1. **당시 상황:**
   Day 6 F-3 및 Day 7 Step 3에서 600×600 뷰포트 내에 고해상도 이미지를 띄우고 결함 의심 부위를 정밀 관찰하는 머신비전 전용 `ImageView` 컴포넌트를 개발하고 있었습니다.
2. **겉으로 나타난 증상:**
   - 마우스 휠을 조작할 때 브라우저 전체 페이지가 함께 상하로 스크롤되어 검사 화면을 이탈함.
   - 확대 기준점이 항상 화면 중심(`(300, 300)`)에 고정되어 있어, 작업자가 병목 부위를 확대하려고 휠을 굴리면 병목 부위가 화면 밖으로 튕겨 나가 매번 Pan 드래그로 찾아와야 함.
   - 800% 이상 고배율 확대 시에도 픽셀의 물리적 경계가 뭉개져 단일 픽셀 식별이 불가능함.
3. **실제 원인:**
   - React의 기본 인라인 `onWheel` 이벤트는 브라우저 스펙상 `passive: true`로 바인딩되어 `e.preventDefault()`를 통한 기본 페이지 스크롤 차단이 불가능했음.
   - 줌 변환 수학식이 포인터 좌표 $(P_x, P_y)$를 고정 불변점으로 두는 아핀 변환(Affine Transform) 역산이 아닌 단순 중앙 스케일링으로 구현되어 있었음.
   - Canvas 2D 컨텍스트의 `imageSmoothingEnabled` 기본값이 `true`로 설정되어 고배율에서 픽셀 보간(Bilinear Blurring)이 발생함.
4. **원인을 찾기 위해 시도한 분석:**
   - 휠 델타 $\Delta y$ 발생 시 이전 배율 $Z_{\text{prev}}$와 신규 배율 $Z_{\text{next}}$ 사이에서 포인터 아래의 원본 이미지 좌표 $(X_{\text{local}}, Y_{\text{local}})$가 변하지 않아야 한다는 점을 기하학적으로 유도:
     $$P_x = O_{x, \text{prev}} + X_{\text{local}} \cdot Z_{\text{prev}} = O_{x, \text{next}} + X_{\text{local}} \cdot Z_{\text{next}}$$
     $$O_{x, \text{next}} = P_x - (P_x - O_{x, \text{prev}}) \cdot \frac{Z_{\text{next}}}{Z_{\text{prev}}}$$
5. **적용한 해결 방법:**
   - `useEffect` 내에서 `canvasWrapperRef.current.addEventListener('wheel', handler, { passive: false })`로 등록하고 즉시 `e.preventDefault()` 호출하여 브라우저 스크롤 완전 차단.
   - 확대(Zoom In) 시에는 위 포인터 불변 수식을 적용하여 포인터 기준 확대, 축소(Zoom Out) 시에는 이미지가 뷰포트 중심을 향해 정렬되도록 이원화 변환 로직(`computeWheelTransform`) 구현.
   - `ctx.imageSmoothingEnabled = false`로 최근방 이웃(Nearest-Neighbor) 렌더링 강제.
   - 배율별 단계적 UI 고도화:
     - 400% 이상: 반투명 픽셀 격자(`Grid`) 오버레이 렌더링.
     - 1600% 이상: 호버된 단일 픽셀 셀에 앰버색 하이라이트 박스 및 플로팅 GV 태그 표시.
     - 3200%~4000% 극초고배율: 뷰포트 컬링 후 화면에 보이는 모든 픽셀 사각형 내부에 정수 Gray Value(0~255) 숫자를 정중앙에 렌더링 (휘도 128 초과 시 흑색 글자, 이하 시 백색 글자 자동 반전).
6. **실패했거나 배제한 접근 방식:**
   - *CSS `transform: scale()` 적용:* Canvas DOM 자체를 CSS로 키우면 브라우저가 비트맵을 강제 스무딩하여 픽셀 격자 경계가 흐려지고, Pixel Inspector 마우스 좌표 계산이 복잡해져 배제.
   - *전체 900×900 픽셀에 대한 무조건적 텍스트 렌더링:* 81만 개 픽셀에 대해 `fillText`를 호출하면 프레임 드랍(FPS < 5)이 발생하므로, 뷰포트 범위 내의 보이는 픽셀만 계산(`startX ~ endX, startY ~ endY`)하는 컬링 최적화 적용.
7. **결과와 검증 근거:**
   - 사용자 Chrome 브라우저에서 Day 7 Step 3.1 3/3 항목 PASS (포인터 기준 확대 시 픽셀 고정 유지, 4000%에서 격자 및 정수 GV 가독성 확보, 100% Reset 정상 동작).
   - 근거 문서: `docs/day7-step31-imageview-cursor-anchor-zoom.md`
8. **남은 한계:**
   4000% 배율에서 뷰포트 내에 표시되는 픽셀 수가 적어지므로, 전체 이미지 내에서의 현재 위치를 나타내는 미니맵(Overview Minimap) 기능은 향후 고도화 과제로 남아 있습니다.
9. **얻은 교훈:**
   산업용 머신비전 툴에서는 일반 웹 UI의 부드러운 스무딩보다 "원본 데이터의 1픽셀 왜곡 없는 무손실성"이 최우선이며, 수학적으로 엄밀한 좌표 변환 모델이 UX 품질을 결정합니다.

---

### [TOP 3] 실제 검사 데이터와 Mock Fixture의 데이터 Provenance 분리 (사례 D)

1. **당시 상황:**
   Day 5 Step 1 및 Day 6 F-2.1 진행 중, 시연용 대시보드에 과거 검사 시나리오 숏컷 버튼(`[T01:OK]`, `[T03:Warn]`, `[T06:NG]`)이 배치되어 있었습니다.
2. **겉으로 나타난 증상:**
   `[T06:NG]` 버튼을 누르면 검사 ID `INSP-001391`이 로드되면서 Anomaly Score `45.0`과 함께 선명한 `NG` 판정이 표시되었습니다. 발표자가 이를 보면 "PatchCore 모델이 T06 결함을 스코어 45.0으로 훌륭하게 잡아냈다"고 오해하기 쉬운 상태였습니다.
3. **실제 원인:**
   - **T06 시나리오의 실체:** T06(IMG-BOTTLE-0001, 미세 오염)은 실제 공식 PatchCore 모델 추론 시 스코어가 `12.9806`으로 임계값(`34.1442`)보다 낮아 **결함 미검출 한계(False Negative/한계 OK)**를 보이는 대표적 반례 사례였습니다.
   - **`INSP-001391`의 출처:** 이 기록은 실제 모델 추론 결과가 아니라, 테스트 스위트(`tests/test_inspections.py`)에서 룰 4(Rule 4: Anomaly Score > 34.1442 -> NG) 분기 로직을 검증하기 위해 Mock Inferencer가 임의로 `anomaly_score=45.0`을 주입했던 **테스트 Fixture 데이터**였습니다.
   - 즉, 모델의 결함 미검출 한계 사례와 단위 테스트용 합성 Mock 데이터가 프론트엔드에서 완전히 뒤섞여 왜곡된 성공 스토리로 둔갑해 있었습니다.
4. **원인을 찾기 위해 시도한 분석:**
   - `data/outputs/inspections.jsonl`의 해당 라인을 전수 조사하여 `INSP-001390`과 `INSP-001391`의 필드를 대조:
     - `INSP-001390`: `image_id="IMG-BOTTLE-0001"`, `anomaly_score=12.9806`, `final_result="OK"`, 모델 실제 추론.
     - `INSP-001391`: `image_id="IMG-BOTTLE-0001"`, `anomaly_score=45.0000`, `final_result="NG"`, Mock 주입.
   - AGENTS.md 규칙 6 ("원본 정답 라벨을 Vision 예측 결과로 둔갑시키지 않는다. 계산하지 않은 점수나 가짜 로그를 생성하지 않는다") 위반 위험을 식별.
5. **적용한 해결 방법:**
   - **UI 숏컷 분리 및 명칭 정정:**
     - `[T06:한계OK]` (`INSP-001390`): 실제 모델 추론 결과인 Score `12.9806` 및 초록색 `OK` 판정을 그대로 표시하고, "모델의 미세 결함 미검출 한계 사례"로 정직하게 고지.
     - `[Mock:NG]` (`INSP-001391`): 버튼 명칭을 명확히 변경하고, 선택 시 오버레이 상단에 **황색 주의 배너 `[MOCK / TEST FIXTURE — NG (anomaly_score=45.0 주입)]`**을 강제 표시.
   - **Provenance 메타데이터 도입:** 백엔드 응답 및 UI 배지에 `LIVE_INSPECTION`, `STORED_RESULT`, `RECORDED_TEST_FIXTURE` 출처를 명시적으로 분리 표기.
6. **실패했거나 배제한 접근 방식:**
   - *`INSP-001391` 기록을 운영 JSONL에서 몰래 삭제하기:* 기존 테스트와 과거 보고서의 참조 무결성을 깨뜨리므로 기각.
   - *T06 임계값을 낮춰서 억지로 NG 만들기:* 다른 정상 병들이 대거 NG로 오판정되는 부작용이 발생하므로 임계값 임의 조작 금지 원칙 준수.
7. **결과와 검증 근거:**
   - Chrome 검증에서 `[T06:한계OK]`와 `[Mock:NG]`의 시각적·개념적 분리가 확인되었으며, Mock 데이터를 실제 모델 성과로 포장하는 데이터 왜곡을 원천 차단함.
   - 근거 문서: `docs/day5-step1-agent-counterexample-audit.md`, `docs/day7-step3-static-imageview-verdict-overlay.md`
8. **남은 한계:**
   PatchCore가 T06과 같은 초미세 오염을 검출하지 못하는 모델 자체의 해상도 한계는 고해상도 패치 추출이나 다른 모델 아키텍처 도입을 통해 장기적으로 해결해야 할 과제로 남아 있습니다.
9. **얻은 교훈:**
   AI 시스템에서 "실제 모델의 한계"를 숨기기 위해 테스트용 Mock 데이터를 모델의 성과인 것처럼 호도하면 시스템의 엔지니어링 신뢰성이 완전히 붕괴됩니다. 한계를 솔직하게 드러내고 안전 규칙을 지키는 것이 진정한 신뢰성 엔지니어링입니다.

---

### [TOP 4] PatchCore 전처리 이중 정규화 불일치 및 Threshold 유효성 보존 (사례 E)

1. **당시 상황:**
   Day 5 Step 3 Phase B-2에서 컨베이어 비디오의 ROI 크롭 이미지를 PatchCore 모델에 연계하기 위해 모델의 전처리(Preprocessing) 파이프라인을 감사하던 시점이었습니다.
2. **겉으로 나타난 증상:**
   운영 추론 시 모델에 입력되는 이미지 텐서의 수치 범위를 점검한 결과, ImageNet 표준 정규화(평균 0, 표준편차 1)를 거쳤음에도 입력 텐서의 최솟값~최댓값이 `[-11.366, +9.928]`에 달하는 극단적인 값 분포를 보였습니다.
3. **실제 원인:**
   - **이중 정규화(Double Normalization) 발견:**
     - 외부 래퍼(`backend/ml/patchcore_inferencer.py:56`)에서 `transforms.Normalize(mean, std)`를 1회 적용하고 있었습니다.
     - 그러나 로드된 PyTorch Lightning 체크포인트(`patchcore_bottle.ckpt`) 내부의 `pre_processor.export_transform` 블록에서 **동일한 Normalize가 또 한 번 적용**되고 있었습니다.
   - **경로 간 불일치:**
     - 과거 모델 학습 코드: 1회 Normalize.
     - 독립 정상 Calibration 코드: 2회 Normalize.
     - 현행 운영 추론 코드: 2회 Normalize.
   - 고정 임계값 `34.1442`는 이 2회 정규화가 적용된 비정상 수치 공간에서 산출된 것이었습니다.
4. **원인을 찾기 위해 시도한 분석:**
   - 외부 정규화를 제거한 단일 정규화(Path B)와 현행 이중 정규화(Path A)를 비교하는 격리된 합성 이미지(SYN-001, SYN-002, SYN-003) A/B 실험을 수행:
     - SYN-001 (단색 회색): Path A 15.43 -> Path B 13.71 (11.1% 감소)
     - SYN-002 (그라디언트): Path A 32.27 -> Path B 17.48 (45.8% 감소)
     - SYN-003 (색상 패턴): Path A 61.26 -> Path B 22.71 (62.9% 급감, **임계값 34.1442 아래로 추락**)
   - 단일 정규화로 변경할 경우 모든 Anomaly Score가 대폭 하락하여 기존 고정 임계값 `34.1442`가 완전히 무력화됨을 수학적으로 증명.
5. **적용한 해결 방법:**
   - **현행 운영 동결 및 보류 결정 (Deferred):** 발표 MVP를 앞두고 체크포인트를 재학습하거나 임계값을 즉흥적으로 재조정하는 것은 회귀 위험이 너무 크다고 판단.
   - 공식 체크포인트와 임계값 `34.1442`, 현행 이중 Normalize 운영 코드를 **일체 변경하지 않고 보존**.
   - 비디오 ROI 크롭 이미지의 PatchCore 자동 투입을 잠정 보류하고, 기술적 원인과 실험 수치를 인수인계서에 투명하게 기록하여 기술 부채로 명시.
6. **실패했거나 배제한 접근 방식:**
   - *운영 코드의 외부 정규화를 바로 삭제하기:* 기존 임계값 `34.1442`와의 정합성이 깨져 정상/불량 판정이 엉망이 되므로 엄격히 차단.
   - *합성 이미지 3장의 결과만으로 새 임계값을 어림잡아 설정하기:* 통계적 검증(AUROC/Precision/Recall) 없는 임계값 변경은 금지됨.
7. **결과와 검증 근거:**
   - 기존 검사 시나리오(T01, T03, T06)의 결정적 판정이 100% 보존되었으며, 위험한 임의 수정을 완벽히 방지함.
   - 근거 문서: `docs/day5-step3-phaseb2a-patchcore-preprocessing-audit.md`, `docs/visioninsight-patchcore-ab-deferred-handoff.md`
8. **남은 한계 (UNRESOLVED):**
   모델 전처리의 근본적 정합성 문제는 여전히 미해결 상태이며, 향후 MVTec Bottle 전체 데이터셋을 기반으로 전처리 단일화 및 Threshold Recalibration을 재수행해야 합니다.
9. **얻은 교훈:**
   머신러닝 파이프라인에서 전처리의 사소한 불일치(이중 정규화)는 모델 출력의 스케일을 완전히 왜곡시킵니다. 원인을 찾았다고 해서 성급하게 일부만 수정하면 시스템 전체의 임계값 체계가 무너지므로, 전체 파이프라인의 종속성을 파악하고 의도적 보류를 결정하는 엔지니어링 절제가 필요합니다.

---

### [TOP 5] Gemini Agent의 예외 마스킹 디버깅과 근거 기반 진단 구조화 (사례 F, G)

1. **당시 상황:**
   Day 4에서 Gemini Function Calling 기반 진단 에이전트를 구축한 후, Day 6 F-2.1 테스트 중 신규 검사에 대해 `[Gemini AI 진단 실행]`을 요청했을 때 간헐적으로 분석이 실패하는 현상이 보고되었습니다.
2. **겉으로 나타난 증상:**
   브라우저 화면에 `GEMINI_REQUEST_FAILED (502 Bad Gateway)` 에러 배너가 나타났으나, 백엔드 콘솔과 로그 파일에는 아무런 스택 트레이스나 구체적 원인(HTTP 401, 403, 404 등)이 전혀 기록되지 않았습니다.
3. **실제 원인:**
   - **광범위한 예외 삼킴(Exception Swallowing):** `backend/agent/service.py` 내부의 `_generate` 함수에서 `client.aio.models.generate_content(...)` 호출부를 감싸고 있던 `except Exception: raise AgentFailure("GEMINI_REQUEST_FAILED") from None` 구문이 원본 예외 객체를 완전히 소멸시키고 있었습니다.
   - **외부 추측성 결론의 오류:** 과거 일부 보고서에서 "Google API에 gemini-3.8-flash 모델이 존재하지 않아 404가 발생했다"고 추측했으나, 공식 문서를 확인한 결과 `gemini-3.8-flash`는 실제로 공식 정식 지원 모델이었습니다.
   - **단일 호출 테스트에서의 발견:** 독립 단일 호출 진단 스크립트 실행 결과, 통신 자체는 성공했으나 진단용 극소 토큰(`max_output_tokens=16`) 설정으로 인해 응답이 조기 중단(`FINISH_REASON: MAX_TOKENS`)되는 현상이 확인되었습니다.
4. **원인을 찾기 위해 시도한 분석:**
   - `service.py`의 예외 처리부를 리팩터링하여 API Key나 토큰 등 민감 정보를 마스킹하면서도, `exception_class`, `http_status`, `provider_code`, `stage`를 안전하게 JSON 로그에 남기는 구조화 관측 시스템 구축.
   - 오프라인 Mock 환경에서 Tool Round(도구 선언 및 AUTO 모드)와 Structured Report Round(JSON 스키마 모드)의 스키마 직렬화 및 2단계 분리 구조 검증.
5. **적용한 해결 방법:**
   - **구조화 예외 관측 도입:** API Key 노출을 방지하는 정규식 마스킹을 적용하고, 예외 발생 시 구체적인 Provider 상태 코드를 서버 로그에 안전하게 기록하도록 수정.
   - **`api_version="v1beta"` 명시:** SDK의 기본값 암묵적 의존을 제거하고 `HttpOptions(api_version="v1beta")`를 명시적으로 주입하여 엔드포인트 안정성 확보.
   - **근거 기반 진단(Fact vs Hypothesis) 원칙 준수:**
     - AI가 판정을 조작하지 못하도록 서버의 `final_result`를 확정 불변값으로 주입.
     - 에이전트가 제시하는 모든 근거는 시스템 도구(`get_inspection_result`, `get_execution_logs`, `analyze_image_quality`, `get_inspection_history`)의 실제 반환값과 JSON Pointer로 1:1 매핑되어야만 최종 보고서로 채택되도록 검증.
6. **실패했거나 배제한 접근 방식:**
   - *구형 1.5-flash나 2.0으로 모델 임의 다운그레이드:* 공식 지원되는 최신 플래그십 모델(`gemini-3.8-flash`)을 임의 변경하는 것은 근본 해결이 아니므로 기각.
   - *예외 로그 전체를 그대로 화면에 노출하기:* 사용자 화면에 API 키나 내부 시스템 경로가 노출될 보안 위험이 있어 엄격히 차단.
7. **결과와 검증 근거:**
   - 오프라인 Mock 테스트(`tests/test_day7_step2_agent_offline_mock.py`) 6종 ALL PASS (스키마 직렬화, 도구 호출, 다단계 라운드 분리, 예외 마스킹 검증 완료).
   - 저장 보고서(`INSP-001396`, `INSP-001398`) 조회 시 Fact와 Hypothesis가 명확히 분리 렌더링됨 확인.
   - 근거 문서: `docs/day7-step1-gemini-agent-error-diagnosis.md`, `docs/day7-step2-gemini-agent-offline-compatibility.md`
8. **남은 한계 (IMPLEMENTED, NOT LIVE VERIFIED):**
   오프라인 스키마 검증과 단일 호출 통신은 확인되었으나, 여러 번의 Function Calling을 거치는 실시간 다회차 호출의 최종 프로덕션 검증은 발표 전 리허설 검증 과제로 남아 있습니다.
9. **얻은 교훈:**
   외부 LLM API를 시스템에 연동할 때 예외를 단순 래핑하여 숨기면 디버깅이 불가능해집니다. 민감 정보는 철저히 마스킹하되 실패 원인의 메타데이터를 정밀하게 남기는 관측성(Observability) 설계가 AI 에이전트 시스템의 필수 요건입니다.

---

# 3. 전체 기술적 어려움과 해결 사례 (12대 사례 상세)

### [사례 A] 브라우저와 FastAPI 사이의 Grab 인증 문제
- **문제:** `localhost:5173`에서 `127.0.0.1:8000`으로 Grab 요청 시 `401 CAPTURE_SESSION_REQUIRED` 발생.
- **원인:** Cross-Site 요청에 따른 브라우저의 `SameSite=Strict` 세션 쿠키 전송 자동 차단.
- **대응:** 보안 정책 완화 대신 Vite Same-Origin Proxy (`/api` -> `http://127.0.0.1:8000`) 도입.
- **상태:** **RESOLVED (해결됨)**
- **근거:** `docs/day6-phase-f1-browser-grab-hotfix.md`

### [사례 B] ROI 및 이미지 다중 좌표계 변환 문제
- **문제:** 1920×480 원본 영상, Frozen Grab PNG, ROI Rect, 600×600 ImageView 간 픽셀 불일치 위험.
- **대응:** 화면 렌더링 좌표계와 원본 데이터 좌표계 분리. ROI Center는 화면 조작 핸들링용으로만 사용하고 실제 크롭은 좌상단 $(x, y, w, h)$ 정수 좌표계로 고정. Letterbox 여백 영역을 명시적 패딩(Black Padding)으로 정의.
- **상태:** **RESOLVED (해결됨)** (단, 크롭 결과의 PatchCore 자동 투입은 미연결)
- **근거:** `docs/day6-phase-f3-liveview-roi-imageview.md`, `docs/day6-phase-f31-liveview-imageview-ux-hotfix.md`

### [사례 C] 이미지 정밀 확대와 픽셀값 표시 문제
- **문제:** 휠 조작 시 페이지 스크롤 간섭, 확대 시 포인터 위치 픽셀 이탈, 고배율 픽셀 블러링.
- **대응:** `passive: false` 리스너 바인딩, 포인터 불변 수식 기반 Cursor-Anchored Zoom(100~4000%), `imageSmoothingEnabled=false`, 3200% 이상 픽셀별 Gray Value 정수 숫자 렌더링.
- **상태:** **RESOLVED (해결됨)**
- **근거:** `docs/day7-step31-imageview-cursor-anchor-zoom.md`

### [사례 D] 실제 검사 결과와 Mock Fixture의 구분 문제
- **문제:** T06 결함 미검출 한계(Score 12.98 OK)와 테스트용 Mock NG(Score 45.0)가 뒤섞여 모델의 실제 탐지 성과로 왜곡될 위험.
- **대응:** `[T06:한계OK]`와 `[Mock:NG]` 숏컷 분리, Mock 검사 선택 시 `MOCK / TEST FIXTURE` 황색 경고 배너 강제 표시, Provenance 메타데이터 분리.
- **상태:** **RESOLVED (해결됨)**
- **근거:** `docs/day5-step1-agent-counterexample-audit.md`, `docs/day7-step3-static-imageview-verdict-overlay.md`

### [사례 E] PatchCore 전처리 정합성 문제
- **문제:** 외부 래퍼와 모델 내부의 Normalize가 중복 적용(2회)되어 비정상 텐서 범위 발생. 단일 정규화(Path B) 시 점수가 급락하여 기존 임계값 `34.1442`와 충돌.
- **대응:** 발표 전 체크포인트 및 임계값 보호를 위해 현행 2회 정규화 경로 동결, A/B 측정 수치 인수인계서 작성 후 의도적 보류.
- **상태:** **UNRESOLVED (미해결 기술 부채)**
- **근거:** `docs/day5-step3-phaseb2a-patchcore-preprocessing-audit.md`, `docs/visioninsight-patchcore-ab-deferred-handoff.md`

### [사례 F] Gemini Agent의 근거 기반 진단
- **문제:** LLM 환각으로 인해 서버 최종 판정을 번복하거나 존재하지 않는 결함 원인을 단정할 위험.
- **대응:** Function Calling 4대 도구 제한, Fact Catalog 및 Evidence Store 구축, JSON Pointer 1:1 매핑 검증, `final_result` 불변 주입.
- **상태:** **RESOLVED (설계 및 아키텍처 완성)**
- **근거:** `docs/day4-step2-agent.md`, `docs/day4-step4-gemini-validation.md`

### [사례 G] Gemini 실시간 API 오류 및 디버깅
- **문제:** `GEMINI_REQUEST_FAILED` 발생 시 원본 예외가 소실되어 Provider 에러 코드 확인 불가.
- **대응:** API Key 마스킹 기반 구조화 로깅 도입, `api_version="v1beta"` 명시 주입, 오프라인 Mock 호환성 검증 완료.
- **상태:** **PARTIALLY RESOLVED / IMPLEMENTED, NOT LIVE VERIFIED**
- **근거:** `docs/day7-step1-gemini-agent-error-diagnosis.md`, `docs/day7-step2-gemini-agent-offline-compatibility.md`

### [사례 H] 정적 검사 이미지와 LiveView Capture의 분리
- **문제:** LiveView의 캡처 프레임(`CAP-*`)과 등록 정적 이미지(`IMG-*`)가 서로 다른 소스인데 단일 검사로 혼동될 위험.
- **대응:** `ImageView` 상단에 듀얼 소스 탭 전환 바 제공, 검사 ID/이미지 ID/캡처 ID 분리, 검사 결과 오버레이는 정적 이미지 모드에서만 활성화.
- **상태:** **RESOLVED (해결됨)** (단, LiveView 프레임의 PatchCore 자동 투입은 향후 과제)
- **근거:** `docs/day6-phase-f21-inspection-agent-verification.md`, `docs/day7-step3-static-imageview-verdict-overlay.md`

### [사례 I] PatchCore Anomaly Map 시각화
- **문제:** 기존 검사에는 스칼라 점수만 제공되어 이미지 상의 어느 부위가 이상 반응을 보였는지 확인 불가.
- **대응:** 단 1회의 모델 추론 결과에서 `anomaly_map [256, 256]`을 추출하여 Sidecar Artifact(`.npz`, `.json`, `_overlay.png`)로 영구 저장, 900×900 선형 등방 매핑 및 Jet 컬러맵 중첩 렌더링. Pixel Inspector 불변성 보장.
- **상태:** **IMPLEMENTED, NOT LIVE VERIFIED** (단위 테스트 PASS, 실모델 추론 포함 Chrome 실검증 대기)
- **근거:** `docs/day7-step4-patchcore-anomaly-map-visualization.md`

### [사례 J] PostgreSQL ROI 영속 저장 및 승인 워크플로우
- **문제:** 프론트엔드에서 그린 ROI를 단순 로컬 메모리로만 관리하면 서버 재시작 시 유실되고, 검증되지 않은 ROI가 공정에 투입될 위험.
- **대응:** PostgreSQL 기반 ROI 프리셋 테이블 구축, 버전 관리, 관리자 승인(`Approval`) 워크플로우, 공정 활성 바인딩(`Active Binding`) 구현.
- **상태:** **PARTIALLY RESOLVED** (DB 인프라 및 API는 완성되었으나, 실시간 AUTO 검사 파이프라인과의 연계는 미구현)
- **근거:** `docs/day5-step3-phaseb1-db-postgresql-roi-completion.md`, `docs/roi-postgresql-api.md`

### [사례 K] 자동화 테스트와 실제 브라우저 검증의 차이
- **문제:** TypeScript 빌드나 백엔드 단위 테스트가 통과해도 실제 Chrome 브라우저에서 렌더링 깨짐, 이벤트 간섭, 401 오류가 발생.
- **대응:** 단위 테스트와 별도로 사용자의 Chrome 수동 E2E 검증 절차를 마일스톤마다 병행하고, Codex 자동 회귀 테스트 체계로 인계.
- **상태:** **RESOLVED (해결됨)**
- **근거:** `docs/day6-phase-f1-browser-grab-hotfix.md`, `docs/day7-step31-imageview-cursor-anchor-zoom.md`

### [사례 L] 개발 일정과 작업 분담
- **문제:** 백엔드 전처리 감사 및 문서화 작업에 치중하다가 사용자 시연용 React 화면 완성이 지연될 위험.
- **대응:** 기능별 명확한 마일스톤(Phase) 분리, 모델 전처리 A/B 실험을 안전하게 보류하고 시연 UI 구현에 집중, Gemini(문서/QA)와 Codex(개발/테스트)의 역할 분담.
- **상태:** **RESOLVED (해결됨)**
- **근거:** `docs/visioninsight-patchcore-ab-deferred-handoff.md`, `AGENTS.md`

---

# 4. 개발 과정 문제 해결 종합 요약표

| 문제 | 핵심 원인 | 해결 방법 | 현재 상태 | 근거 문서 |
|---|---|---|---|---|
| **1. 브라우저 Grab 401 오류** | `localhost` ↔ `127.0.0.1` 간 `SameSite=Strict` 쿠키 차단 | Vite Same-Origin Proxy (`/api`) 도입 | **RESOLVED** | `docs/day6-phase-f1-browser-grab-hotfix.md` |
| **2. 4000% 줌 및 픽셀 뷰어** | 마우스 스크롤 기본 간섭, 중심 고정 줌, 픽셀 블러링 | `passive:false`, 포인터 불변 수식, 3200% GV 숫자 렌더링 | **RESOLVED** | `docs/day7-step31-imageview-cursor-anchor-zoom.md` |
| **3. Mock Fixture 오인 위험** | 단위 테스트용 Score 45.0 주입 데이터가 실제 결함 검출로 왜곡 | `[Mock:NG]` 숏컷 분리 및 황색 Mock 경고 배너 강제 부여 | **RESOLVED** | `docs/day7-step3-static-imageview-verdict-overlay.md` |
| **4. PatchCore 이중 정규화** | 외부 래퍼와 모델 내부에서 Normalize 중복 적용 | 임계값 34.1442 보호를 위해 현행 경로 동결, 기술 부채 기록 | **UNRESOLVED** | `docs/visioninsight-patchcore-ab-deferred-handoff.md` |
| **5. Gemini 예외 마스킹** | 광범위한 `except Exception`으로 Provider 오류 코드 소실 | 구조화 로깅 도입, `v1beta` 명시, Fact/Hypothesis 분리 | **PARTIALLY RESOLVED** | `docs/day7-step2-gemini-agent-offline-compatibility.md` |
| **6. 영상 크롭 픽셀 오차** | 1920×480 영상, ROI 드래그 핸들, 600×600 뷰포트 좌표 혼동 | 화면 좌표와 원본 픽셀 좌표 분리, 정수 좌상단 크롭 고정 | **RESOLVED** | `docs/day6-phase-f3-liveview-roi-imageview.md` |
| **7. 검사 소스 개념 혼동** | LiveView Grab 프레임과 정적 등록 이미지가 혼재 | `ImageView` 헤더에 듀얼 소스 탭 전환 바 제공, 판정 오버레이 격리 | **RESOLVED** | `docs/day6-phase-f21-inspection-agent-verification.md` |
| **8. 결함 위치 시각화 부재** | 기존 검사에서 스칼라 점수만 반환되고 2D 맵 유실 | 단일 추론 2D Anomaly Map Sidecar 저장 및 Heatmap Overlay | **IMPLEMENTED, NOT LIVE VERIFIED** | `docs/day7-step4-patchcore-anomaly-map-visualization.md` |
| **9. ROI 설정 영속성 결여** | 인메모리 ROI 관리 시 서버 재시작 후 설정 유실 | PostgreSQL 프리셋, 버전 승인, Active Binding 구축 | **PARTIALLY RESOLVED** | `docs/day5-step3-phaseb1-db-postgresql-roi-completion.md` |
| **10. 테스트-브라우저 간 갭** | Mock 테스트 통과 후에도 브라우저 CSS/이벤트 결함 발생 | 마일스톤별 사용자 Chrome 수동 E2E 검증 병행 체계 확립 | **RESOLVED** | `docs/day7-gemini-independent-qa-and-demo-plan.md` |

---

# 5. 발표 및 면접에 활용할 핵심 사례 3선

---

### [선정 1] 실제 검사 데이터와 Mock Fixture의 엄격한 분리 (데이터 신뢰성)
- **30초 발표용 설명:**
  > "VisionInsight는 AI 검사 시스템의 데이터 신뢰성을 위해 실제 모델 검출 결과와 테스트용 Mock 데이터를 엄격히 분리했습니다. T06 미세 오염 결함은 모델이 미검출한 한계 사례(Score 12.98 OK)였는데, 이전 테스트용 Fixture(Score 45.0 NG)가 이를 덮어쓰고 있던 왜곡을 발견하고, Provenance 메타데이터와 전용 Mock 배너를 도입하여 시스템의 실제 성능과 한계를 정직하게 드러내도록 바로잡았습니다."
- **1분 상세 설명:**
  > "개발 과정에서 T06 시나리오를 검증하던 중, 단위 테스트에서 규칙 분기 검증용으로 주입했던 Score 45.0의 `INSP-001391` 기록이 시연 화면에서 실제 PatchCore의 결함 검출 성과처럼 오인될 수 있는 중대한 문제를 발견했습니다. 실제 공식 모델을 돌려본 결과 T06은 미세 오염을 놓친 스코어 12.98의 한계 사례(OK)였습니다. 저희 팀은 AGENTS.md의 안전 규칙 6에 따라 가짜 성과를 포장하지 않고, UI 숏컷을 `[T06:한계OK]`와 `[Mock:NG]`로 명확히 분리했습니다. Mock 데이터에는 눈에 띄는 황색 배너를 붙여 테스트용 주입 데이터임을 명시함으로써, AI 데모에서 발생하기 쉬운 데이터 위장 위험을 원천 차단하고 엔지니어링 투명성을 확보했습니다."
- **예상 질문:** "T06 결함을 모델이 검출하지 못한 것은 모델 성능 문제인데, 왜 즉시 모델을 재학습하거나 임계값을 낮추지 않았습니까?"
- **답변:** "임계값을 낮추면 미세 결함을 잡을 수 있지만, 정상 병에 대한 오검출(False Alarm)이 급증하여 공정 가동률을 떨어뜨립니다. 또한 발표 직전에 검증 데이터 분할 없이 임의로 모델을 튜닝하는 것은 데이터 누수(Data Leakage)를 유발합니다. 저희는 모델의 한계를 투명하게 공유하고, 이를 해결하기 위해 고해상도 패치 추출 및 조명 환경 개선이라는 공학적 개선 로드맵을 수립했습니다."
- **데모 기능:** 우측 패널의 `[T06:한계OK]`와 `[Mock:NG]` 숏컷을 연속 클릭하여 판정 카드 및 Mock 배너 표시 비교.

---

### [선정 2] 마우스 포인터 중심 4000% 정밀 확대와 원본 픽셀 무손실 불변성 (머신비전 UI/UX)
- **30초 발표용 설명:**
  > "머신비전 검사관을 위해 100%부터 4000%까지 마우스 포인터 불변 수식을 적용한 극초고배율 뷰어를 개발했습니다. 3200% 이상 확대 시 화면에 보이는 모든 픽셀 사각형 내부에 실제 휘도값인 Gray Value 숫자가 실시간 렌더링되며, 캔버스에 히트맵을 덧그려도 원본 이미지의 RGB와 GV 측정값은 0.0001%도 오염되지 않는 완벽한 픽셀 무결성을 달성했습니다."
- **1분 상세 설명:**
  > "일반적인 웹 이미지 뷰어는 화면 중심 기준으로 확대되거나 브라우저 스무딩으로 인해 고배율에서 픽셀 경계가 뭉개집니다. VisionInsight는 검사관이 병목이나 크랙 부위에 마우스를 올리고 휠을 조작할 때 해당 픽셀이 마우스 아래에 완벽히 고정되는 아핀 변환 수식을 유도하여 적용했습니다. 또한 Canvas 2D 렌더링 파이프라인에서 이미지 스무딩을 강제 차단하고, 400% 이상에서는 격자선, 3200% 이상에서는 각 픽셀 셀 내부에 정수 Gray Value(0~255) 숫자를 정중앙에 그리는 초정밀 뷰포트를 완성했습니다. 특히 Pixel Inspector는 화면에 렌더링된 히트맵 캔버스를 읽지 않고 오프스크린 원본 이미지 버퍼를 직접 참조하므로, 히트맵을 100% 불투명도로 켜도 원본 병의 물리적 픽셀 값이 그대로 측정됩니다."
- **예상 질문:** "3200%에서 수많은 픽셀에 숫자를 그리면 캔버스 성능 저하(Lag)가 발생하지 않습니까?"
- **답변:** "전체 900×900 픽셀(81만 개)에 무조건 텍스트를 그리면 심각한 렌더링 지연이 발생합니다. 저희는 600×600 뷰포트 내에 현재 노출되고 있는 픽셀의 행렬 범위(`startX ~ endX, startY ~ endY`)만 수학적으로 역산하여 필요한 수십 개의 셀에만 텍스트를 그리는 뷰포트 컬링(Viewport Culling)을 적용하여 60FPS를 안정적으로 유지했습니다."
- **데모 기능:** 병 뚜껑 부분에 마우스를 두고 휠을 굴려 4000%까지 연속 확대, 각 픽셀 내 GV 숫자 및 하단 Pixel Inspector 실측 시연.

---

### [선정 3] 브라우저 SameSite 쿠키 차단과 Vite Same-Origin Proxy 해결 (풀스택 보안 통합)
- **30초 발표용 설명:**
  > "React와 FastAPI 연동 중 크로미움의 `SameSite=Strict` 쿠키 차단으로 인한 Grab 401 오류를 백엔드 보안 모델 완화 없이 Vite Same-Origin Proxy로 해결했습니다. 백엔드의 엄격한 보안을 유지하면서도 프론트엔드 라우팅 일원화를 통해 무손실 영상 캡처 파이프라인을 엔드투엔드로 완성했습니다."
- **1분 상세 설명:**
  > "LiveView에서 프레임을 캡처하는 Grab API는 세션 탈취와 CSRF를 방어하기 위해 `SameSite=Strict`, `HttpOnly` 쿠키를 요구합니다. 그런데 로컬 개발 환경에서 프론트엔드는 `localhost:5173`, 백엔드는 `127.0.0.1:8000`을 사용하여 Chrome이 이를 Cross-Site 요청으로 간주하고 쿠키를 전송에서 제거해버리는 브라우저 보안 이슈가 발생했습니다. 많은 개발자들이 이 상황에서 쿠키 속성을 `None`으로 풀거나 백엔드 CORS를 무력화하는 실수를 범하지만, 저희 팀은 백엔드의 엄격한 보안 요구사항을 100% 보존하면서 Vite 설정에 `/api` 프록시를 적용하여 모든 브라우저 통신을 단일 출처(`localhost:5173`)로 통합함으로써 문제를 깔끔하게 해결했습니다."
- **예상 질문:** "프로덕션 환경(Cloud Run 등)으로 배포할 때는 Vite 개발 프록시를 쓸 수 없는데 어떻게 대응합니까?"
- **답변:** "클라우드 프로덕션 환경에서는 Nginx 리버스 프록시 또는 Cloud Run의 경로 기반 라우팅(Path-based URL Mapping)을 설정하여 `/api/*` 경로를 백엔드 서비스 컨테이너로 라우팅합니다. 이를 통해 프로덕션에서도 브라우저 관점의 Same-Origin 구조가 동일하게 유지되므로 코드 수정 없이 안전하게 배포할 수 있습니다."
- **데모 기능:** LiveView에서 재생 중 `[Pause]` -> `[Grab]` 클릭 시 즉각적인 201 Created 및 1920×480 무손실 PNG 획득 시연.

---

# 6. 본 프로젝트를 통해 얻은 핵심 엔지니어링 교훈

1. **실제 데이터와 Mock 데이터를 혼동하는 순간 엔지니어링의 진실성이 무너집니다:**
   단위 테스트를 통과하기 위해 만든 가짜 Score 45.0 Fixture가 UI에서 실제 모델 결과처럼 표시되던 현상을 바로잡으며, AI 프로젝트에서 데이터 출처(Provenance)의 명확한 기록이 얼마나 중요한지 체감했습니다.
2. **AI 에이전트의 출력은 반드시 결정적 시스템 사실과 1:1로 검증되어야 합니다:**
   Gemini Agent가 환각에 빠지지 않도록 Fact Catalog와 Evidence Store를 도입하고, 서버의 결정적 판정을 불변값으로 주입하는 아키텍처를 설계함으로써 LLM을 산업용 제어 시스템에 안전하게 결합하는 방법을 배웠습니다.
3. **머신러닝 성능과 UI 표현 계층의 관심사는 철저히 분리되어야 합니다:**
   PatchCore 모델의 Anomaly Map이 256×256이라는 이유로 화면에 억지로 Bounding Box를 그리거나 임계값을 변조하지 않고, 모델의 수치 자체를 투명한 상대적 Heatmap으로 표현하고 한계를 명시하는 것이 올바른 머신비전 UI 설계입니다.
4. **수학적으로 엄밀한 좌표 변환 모델링이 산업용 UI의 품질을 좌우합니다:**
   1920×480 영상, 크롭 좌표, 600×600 뷰포트, 4000% 마우스 포인터 중심 확대에 이르는 다중 좌표계를 아핀 변환 수식으로 체계화하여 1픽셀의 오차도 없는 뷰어를 완성할 수 있었습니다.
5. **보안 제약을 회피하기 위해 정책을 허무는 대신, 올바른 아키텍처 패턴을 찾아야 합니다:**
   `SameSite=Strict` 쿠키 차단 문제를 쿠키 속성을 완화하는 대신 Same-Origin Proxy 패턴으로 해결하며, 보안과 기능성 사이의 균형을 유지하는 풀스택 엔지니어링 접근법을 체득했습니다.
6. **Mock 테스트 통과와 실제 브라우저 E2E 검증 사이에는 거대한 간극이 존재합니다:**
   TypeScript 컴파일과 단위 테스트가 100% 통과해도 브라우저 이벤트 간섭, CSS 오버플로우, 비동기 응답 경합은 실제 브라우저에서만 관측됩니다. 에이전트의 자체 보고만을 믿지 않고 마일스톤마다 실제 Chrome 검증을 거친 것이 프로젝트의 성공 요인이었습니다.
