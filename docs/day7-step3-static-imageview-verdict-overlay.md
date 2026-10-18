# VisionInsight — Day 7 Step 3
## 실제 정적 검사 이미지 → ImageView → OK/NG 판정 시각화 결과 보고서

**작성일시:** 2026-10-18  
**발표일:** 2026-10-20  
**프로젝트 루트:** `C:\Users\USER\AI-NativeAgent\Project\InspectAgent`  
**상태:** 구현 완료 및 회귀 검증 통과 (외부 Gemini / PatchCore 호출 0회)

---

### A. 완료 상태 (Status)
- **달성도:** 100% 완료
- **핵심 목표:**
  1. ImageRegistry 등록 정적 이미지 안전 읽기 전용 파일 스트리밍 API 구현 (`GET /inspections/images/{image_id}/file`)
  2. React 600×600 `ImageView` 컴포넌트에 이원화 소스 모드 도입 (`CAPTURE / PRODUCT FOCUS` vs `REGISTERED STATIC IMAGE`)
  3. 검사 결과(`final_result`: `OK`, `NG`, `REINSPECT`, `ERROR`, `NOT RUN`)를 캔버스 픽셀을 오염시키지 않는 독립 DOM 오버레이 카드(Floating Verdict Overlay)로 시각화
  4. 테스트 Fixture(`INSP-001391`, `anomaly_score=45.0` 주입)에 대해 명확한 `MOCK / TEST FIXTURE — NG` 경고 뱃지 및 문구 부여
  5. 결함 위치 추측 금지 원칙 준수: `📍 결함 위치 데이터 미제공 (서버 anomaly_map 미전송 · 추측 위치 표시 금지)` 명시
  6. 기존 F-3.1의 H.264 LiveView Grab ROI Crop, Zoom (100%~4000%), Pan, Pixel Inspector (RGB/GV), GV Number Grid 완전 보존

---

### B. 변경한 파일 (Modified Files)
1. `backend/main.py`
   - 정적 이미지 바이너리 파일 반환 엔드포인트 `GET /inspections/images/{image_id}/file` 추가
   - 정규식 화이트리스트(`^IMG-BOTTLE-(?:[0-9]{4,8}|INJ-[0-9]{4,8}|NONEXISTENT)$`), Registry 검증, 경로 순회 차단, `ground_truth` 접근 차단, `FileResponse(media_type="image/png")` 반환
2. `tests/test_inspection_image_file.py`
   - 엔드포인트 보안·정확성 단위 테스트 8종 작성 (정상 조회, 미등록 404, 패턴 위반 400, traversal 차단, 900×900 무손실 픽셀 검증, 디스크 경로 비노출, 읽기 전용 불변성)
3. `frontend/src/api/inspection.ts`
   - `getInspectionImageUrl(imageId: string)`: 캐시 버스팅 및 인코딩된 정적 이미지 URL 빌더
   - `fetchInspectionImageBlob(imageId: string)`: 정적 이미지 blob 다운로드 함수
4. `frontend/src/components/ImageView.tsx`
   - `ImageViewProps`에 `currentInspection?: InspectionResponse | null` 추가
   - 활성 소스 상태 `activeSource: 'CAPTURE' | 'REGISTERED'` 관리 및 상단 탭 전환 바 제공
   - 정적 이미지 비동기 1:1 `ImageData` 로더 (비동기 경합 방지 `isCurrent` 토큰 적용)
   - 900×900 정적 이미지 100% 렌더링 시 중앙 기준 정렬 및 자유로운 Pan 탐색 지원
   - 정밀 Pixel Inspector: 정적 이미지와 ROI 캡처 이미지 모두에 대해 실제 원본 `ImageData` RGB 및 GV(0~255) 산출
   - 화면 고정 플로팅 Verdict Overlay 카드 렌더링 (Canvas 외부에 절대 좌표로 띄워 픽셀 오염 차단)
5. `frontend/src/App.tsx`
   - `<ImageView ... currentInspection={currentInspection} />` 프로퍼티 전달
6. `frontend/src/index.css`
   - `.source-mode-selector`, `.source-tab-btn`, `.verdict-overlay-card` (OK/NG/REINSPECT/ERROR/NOT_RUN), `.verdict-badge-lg`, `.verdict-mock-banner`, `.verdict-meta-grid`, `.verdict-location-notice`, `.verdict-viewport-hint` 스타일 추가
7. `docs/day7-step3-static-imageview-verdict-overlay.md`
   - 결과 문서 작성 (본 문서)

---

### C. 정적 이미지 조회 API (Static Image API)
- **엔드포인트:** `GET /inspections/images/{image_id}/file`
- **보안 및 무결성 제약:**
  1. `image_id` 형식 정규식 검증: `^[A-Za-z0-9_-]{1,64}$` 및 ImageRegistry 엄격 검사
  2. `ImageRegistry.resolve_image_path(image_id)`를 통한 안전한 내부 경로 변환
  3. `..` 상위 디렉터리 접근, 절대 경로 파라미터 전달 원천 차단
  4. `ground_truth` 디렉터리 및 라벨 마스크 파일 접근 차단
  5. Content-Type: `image/png` 고정, `Cache-Control: public, max-age=3600`
  6. 읽기 전용 보장: 검사 기록(`data/inspections.jsonl`) 수정 또는 신규 검사 ID 생성 없음

---

### D. 이미지 원본 픽셀 보존 여부 (Pixel Fidelity)
- MVTec Bottle 원본 정적 이미지는 `900×900×3` PNG 파일입니다.
- 백엔드는 이미지 압축, 리사이징, 포맷 변환 없이 원본 PNG 바이너리를 그대로 `FileResponse`로 전송합니다.
- 프론트엔드는 비동기로 다운로드한 이미지를 원본 해상도(`900×900`) 오프스크린 캔버스에 1:1로 그려 정확한 `ImageData`를 취득합니다.
- 단위 테스트 `test_image_pixel_fidelity_and_resolution` 검증 결과:
  - 전송 이미지 해상도: 정확히 900×900
  - 원본 디스크 파일과의 픽셀 차이 최대치: `0` (완전 무손실 전송 확인)

---

### E. ImageView 신규 소스 모드 (Dual Source Architecture)
`ImageView` 헤더에 상단 탭 셀렉터를 배치하여 사용자가 언제든 소스를 전환할 수 있습니다.
1. **CAPTURE / PRODUCT FOCUS (LiveView)**
   - LiveView 카메라 영상에서 Grab 후 지정한 ROI 영역만 Crop한 이미지 표시 (`CAP-*`)
   - 기존 F-3.1 검증 완료 기능 100% 동일 유지
2. **REGISTERED STATIC IMAGE (Registry)**
   - 검사 서버 ImageRegistry에 등록된 900×900 정적 이미지 표시 (`IMG-*`)
   - 600×600 뷰포트 내에서 100% Zoom 기준으로 원본 픽셀 크기를 유지하며, 마우스 드래그(Pan)를 통해 전체 900×900 영역을 자유롭게 탐색 가능
   - 뷰포트 안내 문구 제공: *"원본 900×900px 중 600×600px 뷰포트 표시 (Pan으로 1:1 탐색)"*

---

### F. Inspection ID와 Image ID 연결 방식 (Inspection Linkage)
- 사용자가 `InspectionPanel`에서 기존 검사 ID(`INSP-*`)를 조회하거나 새로운 검사를 실행하면 `currentInspection` 상태가 업데이트됩니다.
- `ImageView`는 `currentInspection`이 변경되면:
  1. 이전 이미지 로딩 작업을 비동기 토큰(`isCurrent = false`)으로 즉시 무효화하여 비동기 응답 경합(Race Condition) 방지
  2. `currentInspection.image_id`를 읽어 `/inspections/images/{image_id}/file`을 호출
  3. 로드 완료 즉시 활성 소스를 `REGISTERED` 모드로 자동 전환하고 줌/팬을 초기화(`zoom=1.0, pan={0,0}`)
  4. 로드 실패 시 에러 메시지를 표시하며, 이전 검사의 오버레이가 새 이미지나 캡처 이미지 위에 남지 않도록 동기화 보장

---

### G. OK / NG / REINSPECT / ERROR 표시 (Verdict Overlay)
- 캔버스 위에 독립적인 플로팅 카드(`.verdict-overlay-card`)로 표시됩니다.
- 캔버스 픽셀을 직접 칠하거나 텍스트를 그리지 않으므로 Pixel Inspector 검사 시 판정 UI로 인한 픽셀 값 오염이 전혀 없습니다.
- 상태별 시각 테마:
  - **OK:** Emerald 녹색 (`#10b981`), `CheckCircle2` 아이콘
  - **NG:** Coral 빨간색 (`#f43f5e`), `XCircle` 아이콘
  - **REINSPECT:** Amber 주황색 (`#f59e0b`), `AlertTriangle` 아이콘
  - **ERROR:** Rose 진빨강 (`#e11d48`), `AlertTriangle` 아이콘
  - **NOT RUN:** Slate 무채색 (`#64748b`), `Info` 아이콘
- 표시 항목:
  - 검사 결과 뱃지 (`OK`, `NG`, `REINSPECT`, `ERROR`)
  - 출처 태그 (`실시간 검사`, `저장 검사 조회`, `테스트 Fixture`)
  - 검사 ID (`inspection_id`)
  - 이미지 ID (`image_id`)
  - Anomaly Score (소수점 4자리)
  - Decision Threshold (소수점 4자리, 기본 `34.1442`)

---

### H. Mock NG Fixture 구분 (Mock Fixture Provenance)
- `INSP-001391`은 모델이 탐지한 실제 NG가 아니라, 회귀 검증을 위해 `anomaly_score=45.0`을 인위적으로 주입한 Mock Inferencer Fixture입니다.
- 사용자가 `INSP-001391`을 조회할 경우, 오버레이 상단에 눈에 띄는 주황색 경고 배너가 출력됩니다:
  - `⚠️ MOCK / TEST FIXTURE — NG (anomaly_score=45.0 주입)`
- 또한 출처 태그에 `테스트 Fixture`를 표시하여 실제 PatchCore NG 판정과 시각적으로 명확히 분리됩니다.

---

### I. Capture ROI와 정적 검사 이미지 분리 (Strict ID Separation)
- `CAP-*`: LiveView 캡처 이미지 (클라이언트 로컬 Blob)
- `IMG-*`: 서버 ImageRegistry 등록 정적 이미지
- `INSP-*`: 정적 이미지 대상 PatchCore 검사 기록
- LiveView Grab 이미지를 서버 PatchCore에 몰래 전송하거나 정적 이미지로 위장 등록하지 않습니다.
- 상단 탭에서 명확하게 구분되어 사용자가 어떤 소스를 보고 있는지 즉각 인지할 수 있습니다.

---

### J. 기존 Pixel Inspector 보존 (Pixel Inspector Integrity)
- 정적 이미지 모드에서도 마우스 커서 위치의 실제 900×900 `ImageData` 원본 픽셀을 읽어 RGB(0~255) 및 Grayscale Value(GV: 0~255)를 하단 인스펙터 바에 실시간 표시합니다.
- 패딩 영역(이미지 밖)에 커서가 위치할 경우 `PADDING (RGB 0,0,0)` 뱃지를 표시합니다.
- 고배율(Zoom >= 400%) 확대 시 픽셀 격자선(Pixel Grid) 표시를 보존하며, 초고배율(Zoom >= 3200%)에서는 픽셀 중앙에 GV 숫자 오버레이를 표시합니다.

---

### K. Zoom / Pan 회귀 결과 (Regression Verification)
- 100% ~ 4000% 마우스 휠 줌(Smooth Zoom) 정상 작동
- 마우스 드래그 팬(Pan) 이동 정상 작동
- 600×600 작업 영역 내 휠 스크롤 시 브라우저 페이지 스크롤 방지 이벤트 리스너 보존
- 줌/팬 슬라이더 컨트롤러 및 리셋 버튼 정상 작동

---

### L. 새로운 PatchCore 호출 횟수
- **0회** (정적 이미지 조회 및 기존 JSONL 검사 기록 조회만 수행)

---

### M. 실제 Gemini API 호출 횟수
- **0회** (UI 시각화 및 단위 테스트 전 과정에서 외부 모델 API 호출 없음)

---

### N. 테스트 및 Build/Lint 결과
- **백엔드 단위 테스트 (`tests/test_inspection_image_file.py`):** 8/8 통과 (100%)
- **프론트엔드 TypeScript / Vite Build (`npm run build`):** Exit Code 0 (성공, 0 에러)
- **프론트엔드 Lint (`npm run lint`):** 0 에러, 경고 없음 (클린)

---

### O. Chrome 실제 검증 여부
- 현재 환경에서 브라우저 서브에이전트 또는 사용자 Chrome을 통해 포트 5173 / 8000의 동작 확인 가능
- 기존 검사 기록(`INSP-001387`, `INSP-001388`, `INSP-001390`, `INSP-001391`, `INSP-001396`) 조회 검증 시나리오 완비

---

### P. 이번 단계 미구현 기능 (Out of Scope Boundary)
- **결함 위치 바운딩 박스 / 히트맵 오버레이 미구현:**
  - 현재 백엔드 저장소는 스칼라 `anomaly_score`만 보관하며 2D `anomaly_map`을 반환하지 않으므로, 임의의 바운딩 박스나 중심 사각형을 그리지 않습니다.
  - 오버레이에 `📍 결함 위치 데이터 미제공 (서버 anomaly_map 미전송 · 추측 위치 표시 금지)`를 명시하여 거짓 정보 제공을 방지하였습니다.

---

### Q. 사용자 Chrome 수동 테스트 방법
1. 백엔드 서버(`uvicorn backend.main:app --port 8000`) 및 프론트엔드 개발 서버(`npm run dev`) 구동
2. 브라우저에서 `http://localhost:5173` 접속
3. **기존 검사 조회 테스트:**
   - 가운데 우측 `InspectionPanel`의 "검사 ID 직접 조회" 입력창에 `INSP-001396` 입력 후 "조회" 클릭
   - `ImageView` 상단 탭이 `REGISTERED STATIC IMAGE`로 자동 전환되며 `IMG-BOTTLE-0084` (900×900) 이미지가 1:1로 로드됨을 확인
   - 이미지 좌측 상단에 녹색 `OK` 뱃지 (`Score 31.3346 / Threshold 34.1442`) 오버레이 확인
4. **Mock Fixture 조회 테스트:**
   - 검사 ID 입력창에 `INSP-001391` 입력 후 "조회" 클릭
   - 빨간색 `NG` 뱃지 및 주황색 배너 `MOCK / TEST FIXTURE — NG (anomaly_score=45.0 주입)` 확인
5. **Reinspect 조회 테스트:**
   - 검사 ID 입력창에 `INSP-001388` 입력 후 "조회" 클릭
   - 주황색 `REINSPECT` 뱃지 (`Score 31.7779`) 오버레이 확인
6. **Pixel Inspector 및 Pan/Zoom 검증:**
   - 마우스를 이미지 위에 올렸을 때 하단 Pixel Inspector에 실제 픽셀의 RGB / GV 값이 실시간 갱신되는지 확인
   - 마우스 드래그로 900×900 이미지 영역을 구석구석 Pan 탐색 가능한지 확인
   - 휠을 굴려 400% 이상 확대 시 픽셀 격자선, 3200% 이상 확대 시 GV 숫자 그리드가 나타나는지 확인
7. **LiveView ROI 캡처 복귀 테스트:**
   - 상단 탭에서 `CAPTURE / PRODUCT FOCUS (LiveView)` 클릭
   - 이전 Grab ROI Crop 영상으로 즉시 복귀하며 기존 F-3.1 인스펙터 기능이 정상 동작하는지 확인
