# VisionInsight — Day 7 Step 4 결과 보고서
## PatchCore 실제 Anomaly Map 저장 및 ImageView 결함 의심 영역 시각화

**문서 작성일:** 2026-10-18  
**프로젝트 발표일:** 2026-10-20  
**프로젝트 경로:** `C:\Users\USER\AI-NativeAgent\Project\InspectAgent`  
**담당 영역:** FastAPI 백엔드 / PatchCore Anomaly Map Artifact / React ImageView 시각화

---

### A. 구현 상태 (Implementation Status)
**COMPLETE**
- PatchCore 2차원 Anomaly Map (`[256, 256]`)의 단일 추론 결과 보존 및 Sidecar Artifact 저장 구현 완료.
- 읽기 전용 Anomaly Map 메타데이터 (`GET /inspections/{inspection_id}/anomaly-map`) 및 투명 RGBA 오버레이 PNG (`GET /inspections/{inspection_id}/anomaly-map/overlay.png`) API 구현 완료.
- React `ImageView` (600×600) 내 Heatmap 토글(`[Heatmap ON/OFF]`), 투명도 조절 슬라이더(10%~100%), 1:1 동기화 Canvas 오버레이 렌더링 구현 완료.
- 원본 Pixel Inspector (RGB / GV) 데이터 불변성 100% 보장.
- 과거 검사(`INSP-001396`, `INSP-001398`, `INSP-001390`, `INSP-001391`) 및 Mock Fixture에 대한 가짜 맵 생성 금지 및 `MAP_NOT_AVAILABLE` (404) 처리 완료.
- 개발 및 테스트 중 실제 PatchCore 모델 추론 0회, Gemini API 호출 0회 원칙 완벽 준수.

---

### B. 실제 Predict 반환 타입 및 anomaly_map Shape
- **반환 구조:** `PatchCoreInferencer.predict(image: np.ndarray) -> dict`
- **실제 반환 필드:**
  - `anomaly_score`: `float` (결정적 스칼라 점수)
  - `anomaly_map`: `np.ndarray` (2차원 `float32`, shape: `[256, 256]`)
- **차원 및 데이터 타입 검증:**
  - 차원: 2차원 단일 채널 (`H=256, W=256`)
  - 타입: `np.float32`
  - 값 범위: 0 이상 양의 실수 (정규화 전 feature distance 기반 반응도)

---

### C. 원본 900×900 ↔ anomaly_map 좌표 대응 근거
- **전처리 파이프라인 분석 (`backend/ml/patchcore_inferencer.py`):**
  - 입력: `Image.fromarray(image_rgb)` (원본 900×900)
  - 변환: `transforms.Resize((256, 256))` (CenterCrop, Padding, 회전, 이동 없음)
  - 종횡비: 원본(900×900)과 모델 입력(256×256)이 모두 1:1 정사각형.
- **좌표 대응 관계 (Isotropic Linear Scaling):**
  $$x_{\text{orig}} = x_{\text{map}} \times \frac{900}{256}, \quad y_{\text{orig}} = y_{\text{map}} \times \frac{900}{256}$$
  $$x_{\text{map}} = x_{\text{orig}} \times \frac{256}{900}, \quad y_{\text{map}} = y_{\text{orig}} \times \frac{256}{900}$$
- **오버레이 렌더링:**
  - 백엔드에서 Jet 컬러맵을 적용하고 기저 반응(하위 20%) 투명화 알파 마스크를 결합한 900×900 RGBA PNG를 생성.
  - 프론트엔드 Canvas에서 원본 900×900 이미지와 완벽히 동일한 Canvas Transform `(originX, originY, targetW * zoom, targetH * zoom)`으로 중첩 렌더링하므로, 100%~4000% 줌 및 팬 조작 시 1픽셀의 오차도 없이 일치함.

---

### D. 현재 preprocessing 정합성 문제와 분리 여부
- **현행 모델 제약:**
  - 현행 PatchCore에는 학습과 운영 전처리 간 이중 정규화 불일치 문제가 보고되어 있음.
  - 본 작업에서는 모델 체크포인트, threshold (`34.1442`), 전처리 정규화 코드를 일체 수정하지 않음.
- **표시 한계 명시:**
  - Heatmap은 "현행 PatchCore 모델의 상대적 이상 반응 분포"일 뿐이며, Ground Truth나 검증된 절대 결함 위치가 아님을 화면에 명시 (`verdict-location-notice`).
  - 이미지 판정 임계치 `34.1442`를 픽셀 단위 이진화 임계치로 전용하지 않음.
  - 가짜 Bounding Box 표시를 전면 배제함.

---

### E. 기존 검사의 중복 Predict 방지
- **기존 동작 원칙:**
  - `execute_inspection_workflow` 실행 시 `inferencer.predict()`는 단 1회만 호출됨.
  - 동일한 `pred` 딕셔너리에서 `pred_score`와 `pred["anomaly_map"]`을 동시에 취득.
- **읽기 전용 GET API:**
  - `GET /inspections/{inspection_id}/anomaly-map`
  - `GET /inspections/{inspection_id}/anomaly-map/overlay.png`
  - 위 엔드포인트는 저장된 디스크 Sidecar 파일만 읽으며, 모델 인퍼런스를 절대 트리거하지 않음.

---

### F. 신규 검사에서 Map 확보 방식
- `POST /inspections` 요청 스키마에 선택적 필드 추가:
  - `capture_anomaly_map: bool = False` (기본값 `False`로 기존 호환성 100% 보장)
- 사용자가 프론트엔드 `InspectionPanel`에서 `[x] 신규 검사 시 이상지도(Anomaly Map) 저장` 체크 후 [Inspect 실행] 버튼을 눌렀을 때만 `capture_anomaly_map=True`로 전송.
- 단 1회의 PatchCore 추론 결과에서 맵을 추출하여 Sidecar 저장소에 비동기 원자적 저장.
- 저장 실패 시에도 `final_result` 및 `anomaly_score`를 변조하지 않고 에러 로깅 후 정상 응답.

---

### G. Sidecar 저장 파일 구조
- **저장 디렉터리:** `data/outputs/inspection_anomaly_maps/`
- **파일 포맷:**
  1. `INSP-XXXXXX.npz`: 압축된 원본 2D float32 numpy 배열 (`anomaly_map`)
  2. `INSP-XXXXXX.json`: 메타데이터 (스키마 버전, 크기, 정합 정보, 정규화 범위 등)
  3. `INSP-XXXXXX_overlay.png`: 원본 이미지 크기(900×900)에 맞춘 4채널 RGBA 투명 Heatmap 오버레이
- **보안 및 안전성:**
  - 정규식 `^INSP-[A-Za-z0-9_-]{1,32}$` 검증으로 Path Traversal 공격 차단.
  - `.tmp` 파일 생성 후 `replace`를 이용한 원자적 쓰기(Atomic Write) 적용.
  - `np.nan_to_num`으로 NaN/Inf 제거 및 최대 맵 크기(`2048×2048`) 제한.

---

### H. 읽기 전용 API
1. **메타데이터 조회:**
   - `GET /inspections/{inspection_id}/anomaly-map`
   - 응답: `AnomalyMapMetadataResponse` (`localization_available`, `original_image_width`, `anomaly_map_width`, `visualization_range`, `spatial_transform` 등)
   - 맵이 없는 경우: `404 Not Found` (`detail="MAP_NOT_AVAILABLE"`)
2. **오버레이 PNG 조회:**
   - `GET /inspections/{inspection_id}/anomaly-map/overlay.png`
   - 응답: `image/png` (투명 배경 Jet 히트맵)
   - 맵이 없는 경우: `404 Not Found` (`detail="MAP_NOT_AVAILABLE"`)

---

### I. ImageView Heatmap Overlay
- **토글 컨트롤:** 상단 툴바에 `[Flame 아이콘] Heatmap ON/OFF` 버튼 추가 (기본값 OFF).
- **투명도 슬라이더:** Heatmap 활성화 시 슬라이더(10%~100%, 기본 60%) 노출.
- **비활성화 처리:** 저장된 맵이 없는 과거 검사나 Mock Fixture의 경우 버튼이 비활성화되며 툴팁으로 안내.
- **Canvas 중첩 렌더링:**
  - 원본 이미지 위에 `ctx.globalAlpha = heatmapOpacity`를 적용하여 1:1 위치에 렌더링.
  - 이후 픽셀 격자(Grid) 및 3200% GV 숫자 텍스트를 최상단에 렌더링하여 가독성 유지.

---

### J. Zoom/Pan 좌표 일치
- `ImageView`의 기존 `calculateOrigin(targetW, targetH, zoom, pan)` 결과인 `(originX, originY)`와 `targetW * zoom, targetH * zoom`을 원본 이미지와 Heatmap 오버레이가 100% 동일하게 공유.
- 100%~4000% 마우스 포인터 중심 확대, 뷰포트 중심 축소, Pan 드래그, 100% Reset 시에도 오버레이와 원본 이미지가 정확히 밀착하여 동기화됨.

---

### K. Pixel Inspector 불변성
- `ImageView`의 Pixel Inspector (`RGB`, `Gray Value`, `Local Coord`)는 이미지 로드 시 오프스크린 캔버스에서 1회 추출한 원본 `targetImageData`를 직접 조회함.
- 화면 표시용 `canvasRef`에 Heatmap을 그려도 `targetImageData`의 원본 RGB 값은 0.0001%도 오염되지 않음.
- 마우스 호버 시 표시되는 RGB/GV 값은 Heatmap 색상이 아닌 원본 병 이미지의 실제 픽셀 값임이 보장됨.

---

### L. OK/NG/REINSPECT 및 Mock 구분
- **OK 검사:** Anomaly Score가 정상이어도 모델의 미세 반응 분포가 존재할 수 있으며, 이를 정상 범위 내의 분포로 투명하게 표시.
- **NG 검사:** 서버의 최종 결정적 NG 판정 및 스코어를 보존하며, 결함 부위의 높은 반응 영역을 강조 표시.
- **REINSPECT 검사:** 저조도 등 영상 품질 이상으로 인한 경고 검사의 경우, 원인을 오해하지 않도록 판정 뱃지와 안내 문구 유지.
- **Mock Fixture (`INSP-001391`):** Mock NG 데이터에 임의의 가짜 맵을 생성하지 않으며, `MAP_NOT_AVAILABLE`로 처리하여 모델 검출 결과로 위장하지 않음.

---

### M. 과거 Map 없는 기록 처리
- `INSP-001387`, `INSP-001396`, `INSP-001388`, `INSP-001398`, `INSP-001390`, `INSP-001391` 등 과거 검사는 저장된 Sidecar가 없음.
- API 조회 시 즉시 404 (`MAP_NOT_AVAILABLE`)를 반환하며, 모델 재추론을 시도하지 않음.
- UI상에 "📍 이 검사 기록에는 저장된 이상지도 데이터가 없습니다. (추측 위치 표시 금지)" 안내 문구 표시.

---

### N. 실제 PatchCore 추론 횟수: 0회
- 백엔드 구현 및 단위 테스트 과정에서 실제 Torch 모델 로드 및 추론 0회.
- 순수 Mock inferencer 및 더미 2D 맵 fixture를 통해 정합성 검증 완료.

---

### O. 실제 Gemini API 호출 횟수: 0회
- Gemini API 실호출 0회.

---

### P. 테스트 결과
- **신규 단위 테스트:** `tests/test_inspection_anomaly_map.py`
  - `test_is_valid_inspection_id` PASSED
  - `test_save_and_retrieve_anomaly_map_artifact` PASSED
  - `test_spatial_peak_alignment` PASSED (가상 피크 (128, 64) -> 900x900 원본 (450, 225) 매핑 검증)
  - `test_nan_inf_sanitization` PASSED
  - `test_post_inspections_default_capture_false_preserves_single_call` PASSED
  - `test_post_inspections_capture_true_saves_sidecar_from_single_predict` PASSED (중복 추론 0회 검증)
  - `test_get_anomaly_map_api_read_only` PASSED (추론 없이 Sidecar 읽기 검증)
  - `test_get_anomaly_map_not_available_404` PASSED
  - `test_path_traversal_blocked` PASSED
  - **결과:** **9/9 PASSED** (4.67s)
- **기존 회귀 테스트:** `tests/test_inspections.py`, `tests/test_inspection_image_file.py`
  - **결과:** **19/19 PASSED** (9.67s)

---

### Q. TypeScript / Build / Lint
- **TypeScript 빌드:** `npm run build`
  - `tsc -b && vite build` -> **0 errors**, built in 363ms.
- **Linter:** `npm run lint` (`oxlint`)
  - **0 errors** (기존 hook warning 외 신규 에러 없음).

---

### R. Chrome 실동작 검증 상태
- 코드 준비 및 단위 테스트/빌드 완료 상태.
- 실제 PatchCore 인퍼런스를 통한 실시간 검사 및 Chrome 브라우저 UI 검증은 사용자가 직접 Chrome에서 수행할 수 있도록 절차 준비 완료.

---

### S. 미구현 기능
- **결함 바운딩 박스 (Bounding Box):** 픽셀 단위 임계값 및 바운딩 박스 생성 알고리즘이 미검증된 상태이므로 지침에 따라 구현하지 않음 (상대적 Heatmap 오버레이만 지원).
- **과거 검사 소급 맵 생성:** 과거 검사 기록에 대한 자동 재추론 및 가짜 맵 생성 금지 지침에 따라 미지원.

---

### T. 사용자 수동 테스트 절차 (Chrome)
1. **서버 및 프론트엔드 구동 확인:**
   - 백엔드: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
   - 프론트엔드: `npm run dev` (`http://localhost:5173`)
2. **과거 검사 기록 확인:**
   - `INSP-001396` 또는 `INSP-001391` 선택.
   - 상단 툴바의 `Heatmap OFF` 버튼이 비활성화(disabled)되어 있는지 확인.
   - 오버레이 하단에 "📍 이 검사 기록에는 저장된 이상지도 데이터가 없습니다." 문구 확인.
3. **신규 이상지도 저장 검사 실행:**
   - `IMG-BOTTLE-0084` (정상 병) 또는 다른 등록 이미지 선택.
   - `[x] 신규 검사 시 이상지도(Anomaly Map) 저장` 체크박스 체크.
   - `[Inspect 실행]` 버튼 클릭.
   - 검사 완료 후 생성된 검사 ID(예: `INSP-001443`)가 `ImageView`에 로드됨.
4. **Heatmap 오버레이 및 상호작용 검증:**
   - 상단 툴바의 `Heatmap OFF` 버튼이 활성화되는지 확인.
   - 클릭하여 `Heatmap ON`으로 전환 시 반투명 컬러 히트맵이 병 이미지 위에 표시되는지 확인.
   - 투명도 슬라이더를 10% ~ 100%로 조절하여 오버레이 밝기 확인.
   - 마우스 휠로 100% ~ 4000% Zoom 및 드래그 Pan 수행 시, Heatmap이 원본 병 이미지와 정확히 일치하여 확대/이동하는지 확인.
   - 마우스 커서를 올렸을 때 하단 Pixel Inspector의 `RGB` 및 `Gray Value`가 Heatmap 색상이 아닌 원본 병 픽셀 값을 유지하는지 확인.
