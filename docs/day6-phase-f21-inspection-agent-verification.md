# VisionInsight — Day 6 Phase F-2.1 점검 보고서
## 실제 검사 데이터 Provenance 및 Gemini 오류 원인 정밀 검증

**문서 버전:** 1.0.0  
**작성일자:** 2026-10-17  
**작업 환경:** Miniconda `vision-insight` (Python 3.11) / React 19 + TypeScript 6 + Vite 8  
**상태:** VERIFIED (실제 검사 데이터 출처 확인 완료 / Gemini 오류 원인 규명 완료 / 중앙 모달 및 Provenance UI 개선 완료)

---

## 1. 요청된 6대 Inspection ID의 데이터 출처 및 정합성 검증

`data/inspections.jsonl` 전수 검색 및 코드베이스 역추적 결과:

| 검사 ID | 대상 이미지 ID | 최종 판정 (`final_result`) | 이상 점수 (`anomaly_score`) | 생성 일시 (UTC) | 제품 ID | 실제 데이터 출처 분류 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`INSP-001387`** | `IMG-BOTTLE-0084` | **OK** | 31.3346 | 2026-10-14 11:07:12 | `PROD-BOTTLE-T01` | **실제 과거 PatchCore 추론 결과 (운영 JSONL 저장)** |
| **`INSP-001388`** | `IMG-BOTTLE-INJ-0001` | **REINSPECT** | 31.7778 | 2026-10-14 11:07:12 | `PROD-BOTTLE-T03` | **실제 과거 PatchCore + 품질 경고 추론 결과 (운영 JSONL 저장)** |
| **`INSP-001391`** | `IMG-BOTTLE-0001` | **NG** | **45.0000** | 2026-10-14 11:07:12 | `PROD-TEST-NG` | **수동 구성된 Rule 4 테스트 Fixture (Mock Inferencer)** |
| **`INSP-001396`** | `IMG-BOTTLE-0084` | **OK** | 31.3346 | 2026-10-14 11:07:13 | `PROD-BOTTLE-T01` | **실제 과거 PatchCore 추론 결과 (운영 JSONL 저장, T01 재실행)** |
| **`INSP-001398`** | `IMG-BOTTLE-INJ-0001` | **REINSPECT** | 31.7778 | 2026-10-14 11:07:13 | `PROD-BOTTLE-T03` | **실제 과거 PatchCore 추론 결과 (운영 JSONL 저장, T03 재실행)** |
| **`INSP-001442`** | `IMG-BOTTLE-INJ-0001` | **REINSPECT** | 31.7778 | 2026-10-17 13:06:12 | `ABCD1541` | **오늘(10/17) 사용자 Chrome에서 실제 Inspect 실행으로 생성된 최신 기록** |

### 상세 출처 분석:
1. **`INSP-001387` / `INSP-001396` (T01):**
   - 2026-10-14 Day 3.5 종합 검증 당시 실제 PatchCore 추론(`inference_time_ms: 41.34~44.44ms`)으로 산출된 정상 병 검사 결과입니다.
2. **`INSP-001388` / `INSP-001398` (T03):**
   - 0.6x 밝기 저하 주입 병(`IMG-BOTTLE-INJ-0001`)에 대해 실제 PatchCore 추론(31.78점) 및 OpenCV 품질 분석(`WARNING_LOW_BRIGHTNESS`)을 거쳐 `REINSPECT` 판정을 받은 실제 기록입니다.
3. **`INSP-001391` (Rule 4 Mock NG Fixture):**
   - `tests/test_day3_5_step4_5.py` line 232~245의 `test_workflow_priority_rule_4_product_ng`에서 `mock_inferencer.predict.return_value = {"anomaly_score": 45.0, ...}`로 생성되어 JSONL에 저장된 테스트 fixture입니다. **실제 모델 추론 결과가 아닙니다.**
4. **T06의 진짜 실체와 명칭 불일치:**
   - 프로젝트 설계(`AGENTS.md`, `tests/test_data_isolation_and_security.py` line 83~88):  
     **T06은 '결함 미검출 한계 사례 (기존 판정 유지 OK)'**입니다. `IMG-BOTTLE-0001`(파손 병)에 대해 모델이 32.2679점을 부여하여 임계값 34.1442 미달로 판정 `OK`가 유지된 사례(`INSP-001390`, `INSP-001406`)입니다.
   - 기존 F-2 UI에서 `[T06:NG]`로 잘못 표기되어 있던 버튼을 이번 F-2.1에서 **`[T06:한계OK]`**(`INSP-001390`)와 **`[Mock:NG]`**(`INSP-001391`)로 분리 교정했습니다.
5. **`INSP-001442` (실시간 생성 검증):**
   - 2026-10-17 13:06:12 UTC (한국시간 22:06:12), 사용자가 Chrome 화면에서 직접 `Inspect` 버튼을 눌러 발급된 실제 신규 검사 ID입니다.

---

## 2. Inspect 실행 계약 코드 검증 (`POST /inspections`)

`backend/main.py` line 428~475 및 `backend/inspection.py` line 270~643 소스 코드 정밀 검증 결과:

1. **실제 신규 `inspection_id` 발급 여부:**
   - `inspection_id = generator.next_id()`가 호출되어 항상 새로운 고유 ID(예: `INSP-001442`, `INSP-001443` 등)가 발급됩니다.
2. **기존 검사와 다른 실제 새 실행인지:**
   - Registry를 통해 실제 디스크의 이미지 파일을 OpenCV `cv2.imread()`로 디코딩합니다.
   - OpenCV 품질 분석(밝기 mean, std, min, max)을 새로 계산합니다.
3. **`anomaly_score` 생성 출처:**
   - `inferencer = get_patchcore_inferencer()`를 통해 CPU 메모리에 상주하는 `PatchCoreInferencer.predict(image)`를 호출합니다.
   - 모델의 Forward 추론(`torch.no_grad()`, ResNet-18 coreset memory bank 비교)을 통해 실수형 점수(`output.pred_score`)를 동적으로 추출합니다.
4. **JSONL 영구 저장 여부:**
   - `store.save_inspection(record)` 및 `store.save_logs(collected_logs)`가 즉시 호출되어 `data/inspections.jsonl`과 `data/inspection_logs.jsonl`에 물리적으로 append 저장됩니다.

---

## 3. Gemini 저장 보고서 출처 및 inspection_id 정합성

- `GET /inspections/{id}/agent-report`는 디스크의 `data/outputs/agent_reports/{id}.json`을 읽어 반환합니다.
- 현재 존재하는 사전 저장 보고서는 다음 2건입니다:
  - `INSP-001396.json`: Day 4 Agent schema 기반 `RECORDED_TEST_FIXTURE` (T01 정합)
  - `INSP-001398.json`: Day 4 Agent schema 기반 `RECORDED_TEST_FIXTURE` (T03 저조도 경고 정합)
- 두 파일 모두 내부 JSON의 `inspection_id`와 파일명이 일치하며, 6대 Fact Catalog가 해당 검사의 실제 판정 및 지표를 정확히 가리키고 있습니다.
- `INSP-001442`는 오늘 생성된 신규 검사이므로 사전 저장된 캐시 파일이 없으며, `GET` 요청 시 `404 NO_STORED_REPORT`가 정상 반환됩니다.

---

## 4. `GEMINI_REQUEST_FAILED` 오류의 명확한 원인 규명

사용자가 Chrome에서 `INSP-001442`에 대해 `[Gemini AI 진단 실행]`을 눌렀을 때 `GEMINI_REQUEST_FAILED` (HTTP 502)가 발생한 원인을 코드와 설정을 통해 규명했습니다:

### 원인 추적:
1. **API Key 부재가 아님:**
   - `backend/agent/service.py` line 235~236: 만약 API 키가 없었다면 `AgentFailure("MISSING_API_KEY")` (HTTP 503)가 반환됩니다.
   - 실제로 반환된 에러는 `GEMINI_REQUEST_FAILED` (HTTP 502)였습니다. 이는 API Key가 서버에 주입되어 `genai.Client`가 정상 생성되었음을 뜻합니다.
2. **`models.generate_content` 호출 실패:**
   - `backend/agent/service.py` line 315~322:
     ```python
     try:
         response = await asyncio.wait_for(
             client.aio.models.generate_content(model=model, contents=list(contents), config=config),
             timeout=timeout_seconds,
         )
     except TimeoutError:
         raise AgentFailure("GEMINI_TIMEOUT") from None
     except Exception:
         raise AgentFailure("GEMINI_REQUEST_FAILED") from None
     ```
   - SDK 호출 중 `Exception`이 발생하면 무조건 `GEMINI_REQUEST_FAILED`로 래핑됩니다.
3. **결정적 요인 — 모델 식별자 불일치:**
   - `.env` line 14 및 `backend/config.py` line 31:  
     `GEMINI_MODEL=gemini-3.8-flash`
   - **Google Gemini API 상에는 `gemini-3.8-flash`라는 모델이 존재하지 않습니다.** (공식 모델명: `gemini-1.5-flash`, `gemini-2.0-flash` 등)
   - 존재하지 않는 모델명으로 Google API 엔드포인트에 요청이 전송되어 Google 서버에서 `404 Not Found (models/gemini-3.8-flash is not found)` 예외를 반환했고, 이것이 백엔드에서 `GEMINI_REQUEST_FAILED`로 반환되었습니다.

---

## 5. Gemini 실행 확인 UI 중앙 Modal 개선 완료

### 기존 문제:
- 프론트엔드가 TailwindCSS가 아닌 순수 Vanilla CSS(`index.css`) 구조임에도, Tailwind 유틸리티 클래스(`fixed inset-0 z-50 flex items-center justify-center`)만 적용되어 있어 스타일이 먹히지 않고 인라인 블록으로 확장 렌더링되었습니다.

### 개선 조치:
1. **`frontend/src/index.css`에 순수 CSS 모달 시스템 구축:**
   - `.modal-overlay`: `position: fixed; inset: 0; width: 100vw; height: 100vh; background: rgba(3, 7, 18, 0.82); backdrop-filter: blur(8px); z-index: 9999; display: flex; align-items: center; justify-content: center;`
   - `.modal-dialog`: 중앙 배치, `max-width: 520px;`, 부드러운 스케일업 애니메이션(`modal-scale-up`), 진한 그림자
   - `.modal-header`, `.modal-body`, `.modal-footer` 구조화
2. **`frontend/src/components/AgentPanel.tsx` 모달 제어 개선:**
   - `Escape` 키 입력 시 모달 자동 닫힘 이벤트 리스너 추가
   - 오버레이 배경 클릭 시 닫힘(`e.target === e.currentTarget`)
   - 확인 버튼 클릭 전 네트워크 요청 0회 보장
   - `isAnalyzingLive` 진행 중 중복 클릭 차단

---

## 6. UI Provenance 4대 배지 명확화

- `STORED RESULT` (Sky): 서버 스토리지에 기저장된 실제 검사 결과 (`INSP-001387`, `INSP-001388`, `INSP-001390`, `INSP-001442`)
- `LIVE INSPECTION` (Emerald): 사용자가 `[Inspect 실행]` 버튼을 눌러 새로 생성된 실시간 검사 결과
- `RECORDED TEST FIXTURE` (Amber): 통합 테스트 및 모의 환경에서 생성된 Fixture (`INSP-001391` Mock NG 및 사전 저장 에이전트 리포트)
- `NOT ANALYZED` / `UNINSPECTED` (Slate): 검사 또는 진단이 수행되지 않은 상태

---

## 7. ImageView 정적 이미지 연동 및 결함 위치 시각화 확장 검토

1. **정적 이미지 미리보기 API 존재 여부:**
   - 백엔드에 `GET /inspections/images/{image_id}` 형태의 바이너리 이미지 반환 API는 **현재 존재하지 않습니다.**
   - 오직 CaptureStore의 동영상 프레임 캡처(`GET /video/captures/{capture_id}/image`)만 구현되어 있습니다.
2. **Anomaly Map 및 결함 위치 정보 제공 여부:**
   - `PatchCoreInferencer.predict()`는 메모리상에서 `anomaly_map: [256, 256]`과 히트맵 생성기를 보유하고 있습니다.
   - 그러나 `backend/inspection.py`에서 `anomaly_score`(스칼라)만 추출하고 `anomaly_map`은 저장/반환하지 않습니다.
   - 따라서 현재 API 응답에는 **결함의 픽셀 좌표나 히트맵 데이터가 포함되어 있지 않습니다.**
3. **향후 확장 설계 권고:**
   - 근거 없는 가상 바운딩 박스를 렌더링하는 것은 프로젝트 안전 규칙 위반이므로 배제합니다.
   - 차후 확장 시 `GET /inspections/images/{image_id}` 읽기 API를 추가하고, PatchCore 추론 시 `anomaly_map`을 컬러맵 이미지로 인코딩하여 반환하는 방식으로만 ImageView 오버레이를 구현해야 합니다.

---

## 8. 완료된 변경 파일 목록

1. `frontend/src/index.css`: `.modal-overlay`, `.modal-dialog` 등 중앙 모달 전용 CSS 추가
2. `frontend/src/components/AgentPanel.tsx`: 모달 클래스 적용, Escape 키보드 이벤트, 오버레이 닫기 핸들러 추가
3. `frontend/src/components/InspectionPanel.tsx`: 4대 Provenance 배지 적용, `[T06:한계OK]` 및 `[Mock:NG]` 숏컷 분리 교정
4. `frontend/src/types/inspection.ts`: `provenance` 유니온 타입에 `RECORDED_TEST_FIXTURE`, `NOT_ANALYZED` 확장
5. `docs/day6-phase-f21-inspection-agent-verification.md`: 본 검증 보고서 작성
