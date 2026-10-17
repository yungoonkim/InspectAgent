# VisionInsight — Day 6 Phase F-2 완료 보고서
## React 정적 이미지 PatchCore 검사 및 Gemini AI Agent 실제 연동

**문서 버전:** 1.0.0  
**작성일자:** 2026-10-17  
**작업 환경:** Miniconda `vision-insight` (Python 3.11) / React 19 + TypeScript 6 + Vite 8  
**상태:** COMPLETE (발표용 핵심 MVP 연동 완료 / F-3.1 UI 전면 보존 / Gemini 무단 호출 0회)

---

## 1. 기존 F-3.1 상태

Day 6 Phase F-3.1에서 사용자가 Windows Chrome 수동 테스트로 직접 검증을 완료한 다음 핵심 머신비전 UX 5대 기능은 무단 수정이나 삭제 없이 **100% 완전 보존**되었습니다:
1. **Pause → ROI 선택 → Grab → Product Focus 표시**: 재생 중 ROI 조작 차단 및 일시정지 상태에서 정확한 Grab-Crop 연계
2. **ROI 편집 Cyan / 적용 Green 상태 구분**: 이동·리사이즈 시 Cyan(`EDITING`), Grab/적용 시 Green(`APPLIED`)
3. **ROI Center 좌표 표시**: LiveView 오버레이 상단에 `ROI Center: (X, Y) · W×H` 실시간 렌더링
4. **ImageView 휠 Zoom 시 브라우저 페이지 스크롤 방지**: non-passive wheel listener `e.preventDefault()` 적용
5. **3200~4000% 픽셀별 GV 및 Pixel Inspector 값 확인**: 캔버스 픽셀 정중앙 폰트 렌더링 및 RGB/GV/상태 바 연동

---

## 2. 확인한 실제 FastAPI API 계약

| Endpoint | HTTP Method | 요청 데이터 | 응답 데이터 | 인증 / 가드 | 모델 / Gemini 실행 여부 | 용도 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `/inspections/images` | `GET` | 없음 | `{ total_images, image_ids, sample_ids }` | 없음 | 0회 (순수 Registry 메타데이터) | 안전한 중립 `image_id` 목록 제공 |
| `/inspections` | `GET` | Query `limit=50` | `{ total, inspections: [...] }` | 없음 | 0회 (순수 JSONL 스토리지 조회) | 최근 검사 이력 목록 제공 |
| `/inspections/{id}` | `GET` | Path `inspection_id` | `InspectionResponse` | 없음 | 0회 (순수 JSONL 스토리지 조회) | 특정 검사 결과 조회 |
| `/inspections` | `POST` | `{ product_id, image_id }` | `InspectionResponse` (201) | 없음 | **PatchCore 추론 실행** (단, 사용자 직접 버튼 클릭 시에만) | 신규 정적 이미지 결함 검사 실행 |
| `/inspections/{id}/agent-report` | `GET` | Path `inspection_id` | `AgentReport` (저장 보고서) | 없음 | **0회** (사전 저장 JSON 캐시/Fixture 조회) | 기존 Gemini 진단 보고서 조회 |
| `/analyze/{id}` | `POST` | Path `inspection_id` | `AgentReport` | `GEMINI_API_KEY` 필요 | **Gemini Function Calling 실행** | 신규 Gemini AI 진단 실행 |

---

## 3. 새로 만든 Inspection UI (`InspectionPanel.tsx`)

`frontend/src/components/InspectionPanel.tsx`는 기존 빈 틀에서 실제 백엔드 연동 패널로 완전 구현되었습니다:
- **데이터 출처 명시**: `SOURCE: REGISTERED STATIC IMAGE` (MVTec AD Bottle)
- **등록 이미지 선택**: 서버 `GET /inspections/images`에서 조회한 중립 `image_id` 드롭다운 제공
- **제품 ID 입력**: 기본값 `ABCD1541` (수정 가능)
- **발표 시연 숏컷 버튼**:
  - `[T01:OK]`: `INSP-001387` (정상 병, Score 31.33)
  - `[T03:Warn]`: `INSP-001388` (저조도 경고, REINSPECT)
  - `[T06:NG]`: `INSP-001391` (오염/결함, Score 45.0, NG)
- **검사 ID 검색 및 Datalist 자동완성**: 최근 검사 기록을 기반으로 빠른 ID 입력 및 `[조회]` 지원
- **신규 검사 버튼 `[Inspect 실행]`**: 사용자 직접 클릭 시에만 `POST /inspections` 호출
- **서버 결정적 최종 판정 카드**:
  - `OK` (Emerald), `NG` (Rose), `REINSPECT` (Amber), `ERROR` (Red)
  - Anomaly Score, Decision Threshold (`34.1442` 고정), 영상 품질 상태, 원인 코드 상세 표시

---

## 4. 새로 만든 Agent UI (`AgentPanel.tsx`)

`frontend/src/components/AgentPanel.tsx`는 Gemini AI의 실제 Function Calling 기반 진단 결과를 표시합니다:
- **판정 불변 가드레일 배지**: AI는 원인 진단 및 권고사항만 제공하며 서버의 최종 OK/NG 판정을 절대 번복하지 않음을 시각화
- **진단 대상 ID 연동**: `InspectionPanel`에서 조회/검사된 `inspection_id`가 실시간 자동 동기화
- **`[기존 보고서 조회]` 버튼**: Gemini 실호출 없이 `GET /inspections/{id}/agent-report`를 호출하여 기저장된 진단 리포트 표시
- **Overall Summary**: 결함 상태 및 이상 원인에 대한 3문장 이내 종합 분석
- **Observed Facts & Evidence 테이블**:
  - Fact ID (`F0001`~`F0006`), Evidence ID (`E0001`), Source Tool (`get_inspection_result`), JSON Pointer (`/data/final_result` 등), 관측값 표시
- **가설 및 의심 원인 (Possible Causes)**: 신뢰도(Confidence) 및 가설 설명 카드
- **권장 조치 계획 (Action Plan)**: 점검 코드, 작업 지침, 근거 참조 링크
- **분석 한계 안내 (Limitations)**: 물리적 결함 확정 불가 및 환경 요인 구분 안내
- **사용된 도구 목록 배지**: `get_inspection_result`, `analyze_image_quality` 등 호출된 서버 도구 목록 표시

---

## 5. 정적 이미지 선택 방식

- 서버의 `GET /inspections/images`를 호출하여 중립 식별자 (`IMG-BOTTLE-0001`, `IMG-BOTTLE-0084` 등) 목록만 드롭다운에 표시합니다.
- `broken_large`, `contamination`, `good` 등 원본 디렉터리 경로 및 Ground Truth 라벨은 클라이언트에 일체 노출되지 않습니다.
- 프론트엔드 임의의 경로 입력은 불가능하며, 서버 Registry가 유효성을 검증한 안전한 ID만 선택할 수 있습니다.

---

## 6. 기존 검사 결과 조회 방식

- 발표 시연 안정성을 위해 신규 검사보다 먼저 구현되었습니다.
- 사용자가 `inspection_id`를 입력하거나 숏컷(`[T01:OK]`, `[T03:Warn]`, `[T06:NG]`)을 누르고 `[조회]`를 클릭하면 `GET /inspections/{id}`가 호출됩니다.
- 스토리지의 JSONL 데이터를 단순 역직렬화하여 반환하므로 **추가 PatchCore ML 추론이 0회** 발생하며 지연 없이 즉각 렌더링됩니다.
- 조회된 결과에는 배지로 `STORED INSPECTION RESULT`가 표시되어 실시간 검사 결과와 구분됩니다.

---

## 7. 신규 검사 실행 방식

- `[Inspect 실행]` 버튼을 사용자가 직접 클릭할 때만 `POST /inspections`가 호출됩니다.
- **자동 검사 절대 금지 준수**: 페이지 로드 시, 이미지 선택 변경 시, LiveView Grab 시 자동 검사가 발생하지 않습니다.
- 요청 진행 중 중복 클릭을 차단하기 위해 `isInspecting` 상태가 활성화되고 버튼이 비활성화됩니다.
- 서버 응답 수신 시 배지가 `LIVE INSPECTION RESULT`로 전환되며 판정과 점수가 갱신됩니다.

---

## 8. 저장된 Gemini 분석 조회 방식

- `GET /inspections/{id}/agent-report`를 통해 조회합니다.
- `data/outputs/agent_reports/{id}.json`에 캐시된 실제 분석 결과 또는 검증된 Fixture를 읽기 전용으로 조회합니다.
- `INSP-001396` (T01 Normal OK), `INSP-001398` (T03 Warning Low Brightness -> Reinspect)에 대해 실제 Day4/Day5에서 검증된 리포트가 내장되어 있어 발표 시 API 키나 지연 없이 즉시 시연 가능합니다.
- 출처에 따라 `RECORDED TEST FIXTURE (검증된 근거)` 또는 `STORED REPORT` 배지가 명확히 부착됩니다.

---

## 9. Gemini 실호출 방지 안전 설계

1. **2단계 사용자 명시 승인 모달**: `[Gemini AI 진단 실행]` 버튼을 누르면 즉시 호출되지 않고 확인 모달이 팝업됩니다.
   - *"현재 검사(ID)에 대해 Gemini AI 분석을 새로 실행합니다. 실제 API 호출 및 약 20~30초의 분석 시간이 소요될 수 있습니다. 계속하시겠습니까?"*
2. **개발 및 자동 테스트 중 실호출 0회**: 단위 테스트 및 빌드 검증 과정에서 Gemini API 실호출은 일체 발생하지 않았습니다.
3. **API Key 미설정 안전 처리**: 백엔드에 `GEMINI_API_KEY`가 없을 경우 `503 MISSING_API_KEY`를 반환하며, 프론트엔드는 시스템 크래시 없이 시연 안내 메시지 배너를 표시합니다.

---

## 10. 기존 API 누락 및 최소 Adapter 추가 내역

기존 라우터에서 UI 조회를 위한 안전한 읽기 전용 엔드포인트가 누락되어 있어 아래 3개의 최소 Adapter만 추가했습니다:
1. `GET /inspections`: JSONL 스토리지의 최근 검사 이력 목록 조회 (ML 추론 없음)
2. `GET /inspections/{inspection_id}`: 특정 검사 단건 조회 (ML 추론 없음)
3. `GET /inspections/{inspection_id}/agent-report`: 캐시/Fixture 리포트 조회 (Gemini 호출 없음)
4. `backend/agent/api.py`: `POST /analyze/{inspection_id}` 성공 시 결과를 `data/outputs/agent_reports/`에 캐싱하는 로직 추가

---

## 11. TypeScript, Build, Lint 결과

- **TypeScript (`tsc -b`)**: PASS (컴파일 오류 0건)
- **Vite Production Build (`npm run build`)**: PASS
  - `dist/index.html`: 0.77 kB
  - `dist/assets/index-IoMWkzsp.css`: 17.21 kB
  - `dist/assets/index-ODAoVNZ7.js`: 288.22 kB (gzip: 88.68 kB)
  - 빌드 시간: 359ms
- **Oxlint (`npm run lint`)**: PASS (0 errors, 1 harmless react-in-effect warning, exit code 0)

---

## 12. 관련 단위 테스트 결과

Python 백엔드 신규 조회 엔드포인트 및 라우터 단위 테스트 실행:
- 명령어: `C:\Users\USER\miniconda3\envs\vision-insight\python.exe -m pytest tests/test_inspections.py -k "test_list or test_get"`
- 결과: **4 passed in 4.63s**
  - `test_list_inspection_images_neutral_ids`: PASS (중립 ID 노출 및 라벨 비노출 검증)
  - `test_list_recent_inspections`: PASS (이력 조회 및 34.1442 임계값 검증)
  - `test_get_inspection_by_id`: PASS (단건 조회 및 404 처리 검증)
  - `test_get_stored_agent_report`: PASS (저장 리포트 무호출 조회 검증)

---

## 13. Chrome 검증 여부

- **상태:** `NOT TESTED` (자동화 브라우저 샌드박스 드라이버 404 환경 제약으로 인한 subagent 자동 브라우저 세션 미수행)
- **수동 검증 절차:** 사용자가 Windows Chrome에서 즉시 확인할 수 있도록 섹션 16에 상세 검증 순서 제공.

---

## 14. 기존 F-3.1 기능 보존 여부

- `LiveView.tsx`: H.264 스트림 재생, Seek, ±1 Frame, ROI 선택, Cyan/Green 상태, Center 좌표 표시 완전 보존.
- `ImageView.tsx`: 600×600 프레임, 100%~4000% 줌, Pan, Pixel Inspector GV 숫자 렌더링, wheel preventDefault 완전 보존.
- 프론트엔드 코드 전수 감사 결과 F-3.1에서 구현된 머신비전 핵심 기능 일체 유지 확인.

---

## 15. 미구현 기능 (의도된 범위 격리)

- **LiveView Crop (CAP) → PatchCore 실검사**: 정적 이미지 검사(`IMG-*`)와 동영상 Crop(`CAP-*`)의 계약 분리 유지.
- **PatchCore 이중 정규화 수정**: A/B 격리 실험 결과 보존 및 threshold `34.1442` 불변 유지.
- **PostgreSQL ROI 자동 적용**: 수동 ROI 편집 모드 유지.
- **AUTO 모드 컨베이어 트리거**: 발표 일정 및 수동 제어 안정성을 위해 MANUAL 중심 유지.

---

## 16. 사용자가 직접 테스트할 방법 (Windows Chrome)

1. **서버 구동 확인**:
   - Backend: `http://127.0.0.1:8000/health` (응답: `{"status": "ok"}`)
   - Frontend: `http://localhost:5173`
2. **Chrome 브라우저에서 `http://localhost:5173` 접속**:
   - 상단 Stepper: `1. 라이브 스트림` ~ `5. Gemini 진단` 워크스페이스 로드 확인.
   - 중앙 우측 `InspectionPanel` 확인:
     - 드롭다운에 `IMG-BOTTLE-0001` 등 정적 이미지 목록이 표시되는지 확인.
     - 숏컷 버튼 `[T01:OK]` 클릭 → 검사 ID `INSP-001387` 자동 조회 및 최종 결과 `OK`, Score `31.33`, Threshold `34.1442` 표시 확인.
     - 숏컷 버튼 `[T06:NG]` 클릭 → 검사 ID `INSP-001391` 자동 조회 및 최종 결과 `NG`, Score `45.0` 표시 확인.
   - 하단 `AgentPanel` 확인:
     - 상단에 진단 대상 ID `INSP-001396` 또는 선택된 ID 연동 확인.
     - `[기존 보고서 조회]` 클릭 → `RECORDED TEST FIXTURE` 배지와 함께 Overall Summary, Observed Facts 테이블(6건 관측 근거), 권장 조치 확인.
   - 신규 Gemini 분석 안전 모달 확인:
     - `[Gemini AI 진단 실행]` 클릭 → 확인 모달 팝업 표시 확인.
     - `[취소 (돌아가기)]` 클릭 → 모달 닫힘 및 API 미호출 확인.
3. **LiveView & ImageView F-3.1 보존 확인**:
   - LiveView 일시정지 후 ROI 선택 및 Grab 클릭 → ImageView 600×600에 100% 중앙 배치 및 4000% 휠 줌 인스펙터 정상 작동 확인.

---

## 17. 발표용 시연 순서 (12분 발표 권장 흐름)

1. **시연 A: 머신비전 영상 Grab 및 600×600 정밀 관찰 (F-3.1)**
   - 컨베이어 H.264 영상 재생 중 병 통과 순간 `일시정지`
   - ROI 선택 (Cyan 테두리 및 Center 좌표 확인) → `Grab` 클릭
   - 600×600 ImageView에 Product Focus 적용 (Green 테두리)
   - 마우스 휠로 4000% 줌인하여 픽셀 내부 GV 숫자와 Pixel Inspector RGB 확인
2. **시연 B: AI 정적 이미지 PatchCore 결함 검사 (F-2)**
   - 우측 `InspectionPanel`의 발표 시연 숏컷 `[T01:OK]` 클릭 → 정상 판정 확인
   - `[T06:NG]` 클릭 → 이상 점수 45.00으로 불량(NG) 판정 확인
   - 드롭다운에서 새 정적 이미지 선택 후 `[Inspect 실행]` 클릭 → 실시간 PatchCore 추론 결과 확인
3. **시연 C: Gemini AI Agent 근거 기반 이상 진단 (F-2)**
   - 하단 `AgentPanel`로 이동
   - `[기존 보고서 조회]` 클릭 → Gemini가 서버 도구로 조회한 6대 사실(Observed Facts)과 Evidence 테이블 시연
   - "서버의 최종 판정은 불변 가드레일로 보호되며, Gemini는 결함 원인 분석과 조치 계획을 지원합니다" 설명
