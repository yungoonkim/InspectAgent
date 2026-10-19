# VisionInsight 실제 검사 E2E 실행 체크리스트 및 Gemini API 기술 조사서

- **작성일자:** 2026-10-19
- **발표 예정일:** 2026-10-20
- **작성 주체:** VisionInsight 독립 통합 검증 담당자 (Independent Integration Verification Lead)
- **문서 목적:** 새로운 단일 검사 ID(`INSP-XXXXXX`)를 기준으로 [LiveView 프레임 획득 → PatchCore 실추론 → JSONL 저장 → Gemini Diagnostic 진단 → Gemini Vision 2차 분석 → React UI 표출]에 이르는 전 과정을 사용자가 Chrome 브라우저에서 직접 검증할 수 있는 정밀 실행 시나리오, Google Gemini 공식 API 기술 조사 결과, 성공 판정 기준 및 발표용 증거 수집 매뉴얼 수립

---

## 1. 신규 검사 1건의 완전한 E2E 검증 시나리오 (클릭 순서 및 단계별 검증)

사용자가 Chrome 브라우저(`http://localhost:5173`)와 로컬 파일시스템에서 **단 하나의 신규 검사 ID**를 추적하며 시스템의 실동작을 검증하는 5단계 정밀 절차입니다.

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  [A] 이미지 획득 │ ───> │  [B] 실제 검사   │ ───> │  [C] 데이터 저장 │
│  LiveView Grab  │      │  PatchCore 추론 │      │  JSONL & Sidecar│
└─────────────────┘      └─────────────────┘      └─────────────────┘
                                                           │
                         ┌─────────────────┐               │
                         │ [E] Gemini      │ <─────────────┤
                         │     Vision 분석 │               ▼
                         └─────────────────┘      ┌─────────────────┐
                                                  │ [D] Diagnostic  │
                                                  │     AI 보고서   │
                                                  └─────────────────┘
```

---

### [단계 A] 이미지 획득 (LiveView → ROI → Grab → Crop 저장)

#### 1. 실행할 UI 동작
1. 브라우저에서 `http://localhost:5173` 접속.
2. 상단 `LiveView` 플레이어에서 컨베이어 영상(1920×480)이 재생 중일 때, 새로운 병이 중앙 검사 영역에 도달하는 순간 `[Pause]` 버튼 클릭.
3. 일시정지된 비디오 캔버스 위에서 마우스 왼쪽 버튼을 누른 채 드래그하여 병 본체를 감싸는 직사각형 ROI 박스를 지정.
4. 우측 `Inspection / Grab` 패널에서 ROI 좌표(예: `x=700, y=120, width=284, height=272`) 확인.
5. `[Grab & Inspect]` 버튼 클릭.

#### 2. 각 단계의 API 및 저장 파일 연결
- **호출 API:**
  - `POST /api/videos/VID-000001/grab`: 브라우저의 `vision_capture_session` 쿠키와 함께 전송되어 201 Created 응답 수신.
  - 응답 본문에서 고유한 Capture ID(예: `CAP-3c483952db514e27832d9a69f573672f`) 확인.
- **저장 파일 및 위치:**
  - 임시 원본 프레임: `data/outputs/captures/CAP-<uuid>.png` (1920×480 무손실 PNG, 약 780KB).
  - 영구 Crop 이미지: `data/outputs/grab_inspection_inputs/IMG-GRAB-<uuid>.png`.
  - 메타데이터 매니페스트: `data/outputs/grab_inspection_inputs/IMG-GRAB-<uuid>.json`.

#### 3. 검증 방법 및 기준
- PowerShell에서 새로 생성된 파일의 해시 및 해상도 확인:
  ```powershell
  # 가장 최근 생성된 Crop 이미지 확인
  Get-ChildItem data/outputs/grab_inspection_inputs/*.png | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | ForEach-Object {
      [PSCustomObject]@{
          Name = $_.Name
          Size = $_.Length
          SHA256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
          LastWrite = $_.LastWriteTime
      }
  }
  ```
- **성공 판정:**
  - Crop 파일의 크기가 ROI에서 지정한 `width × height`와 1픽셀 오차 없이 일치해야 함.
  - SHA256 해시가 백엔드 manifest 파일 내부의 `image_sha256`과 정확히 일치해야 함.

---

### [단계 B] 실제 이미지 검사 (PatchCore 추론 vs 단순 과거 조회 구분)

#### 1. 실제 모델 추론 확인 절차
- `[Grab & Inspect]`가 트리거되면 백엔드는 `execute_inspection_workflow`를 실행하고 `patchcore_inferencer.predict(image)`를 호출합니다.
- **화면 관측:**
  - 중앙 뷰포트에 잘라낸 병 이미지가 로드되고, 우측 상단에 새로운 고유 검사 ID(예: `INSP-001653`)가 발급됨.
  - `Anomaly Score` 수치(예: `40.1631`)와 `Decision Threshold` (`34.1442`)가 표시됨.
  - 영상 조도 분석 결과(평균 밝기 `mean`, `image_quality_status`) 표시.
  - 최종 판정 배지(`OK`, `NG`, `REINSPECT`, `ERROR` 중 하나) 확인.
  - `[Heatmap Overlay]` 스위치를 켜면 병 결함 의심 부위에 반투명 컬러맵 중첩 표시.

#### 2. 과거 결과 조회 vs 신규 모델 추론을 구분하는 4대 기준

| 구분 기준 | 단순 과거 결과 조회 (Stored Query) | 실제 신규 모델 추론 (New Inference) |
| :--- | :--- | :--- |
| **네트워크 API 호출** | `GET /inspections/INSP-001652` (단순 조회) | `POST /inspections` 또는 `POST /grab-inspections` (신규 실행) |
| **HTTP 소요 시간** | **5ms ~ 20ms 이내** (JSON 단순 반환) | **50ms ~ 150ms 이상** (OpenCV 디코딩 + PyTorch CPU 연산 시간 포함) |
| **Anomaly Map 생성** | 기존 `INSP-XXXXXX.npz` 파일 날짜 변화 없음 | 새로운 검사 ID 명의의 `.npz`, `.json`, `_overlay.png` 파일이 디스크에 즉시 생성됨 |
| **추론 타임스탬프** | 과거 날짜/시간으로 기록된 메타데이터 | 현재 시점의 실시간 타임스탬프(`created_at`) 및 `inference_time_ms` 실측치 기록 |

---

### [단계 C] 검사 데이터 영속 저장 (기존 데이터 보존 및 신규 추가 검증)

#### 1. 신규 레코드 검증 절차
- **검증 파일:**
  1. `data/inspections.jsonl`: 검사 결과 테이블.
  2. `data/inspection_logs.jsonl`: 생명주기 이벤트 로그.
  3. `data/outputs/inspection_anomaly_maps/`: Sidecar 아티팩트 디렉터리.
- **검증 명령:**
  ```powershell
  # 1. inspections.jsonl의 가장 마지막 행 확인
  Get-Content data/inspections.jsonl -Tail 1 | ConvertFrom-Json | Select-Object inspection_id, product_id, anomaly_score, final_result, created_at

  # 2. inspection_logs.jsonl에서 해당 검사 ID의 이벤트 목록 확인
  Get-Content data/inspection_logs.jsonl | ConvertFrom-Json | Where-Object { $_.inspection_id -eq "INSP-001653" } | Select-Object step, event, message, timestamp
  ```

#### 2. 무결성 및 비파괴 원칙 검증
- **검증 기준:**
  - `inspections.jsonl`의 총 라인 수가 정확히 $N \rightarrow N + 1$로 증가해야 함.
  - 이전 라인들의 SHA256 해시나 내용이 단 1바이트도 변경되지 않아야 함 (Append-only 보장).
  - `GET /inspections/{new_id}` 및 `GET /inspections/{new_id}/logs` 재호출 시 디스크 파일의 데이터와 100% 일치해야 함.

---

### [단계 D] 신규 Gemini Diagnostic AI 보고서 생성 검증

#### 1. 실행할 UI 동작
1. 우측 검사 패널 하단의 `[Gemini AI 진단 실행]` (또는 `[Analyze with Gemini]`) 버튼 클릭.
2. 로딩 상태 스피너와 함께 백엔드 분석 파이프라인 작동 확인.

#### 2. 신규 생성 여부 검증 (과거 저장 보고서 조회와 구별하는 방법)
- **과거 저장 보고서 로드:** 기 저장된 `INSP-001396`(T01), `INSP-001398`(T03) 버튼을 누르면 0.1초 만에 화면에 텍스트가 뜸. 이는 생성 성공이 아니라 캐시된 결과의 단순 조회임.
- **실제 신규 생성 성공의 필수 증거:**
  1. **네트워크 호출:** `POST /analyze/INSP-001653` 호출이 발생하고 HTTP 200 수신.
  2. **처리 시간 (Latency):** Function Calling 도구 4개 실행 및 Gemini 왕복으로 인해 **최소 10초~25초 소요**.
  3. **실제 도구 호출 흔적 (Tool Execution Traces):**
     - 에이전트가 `get_inspection_result(inspection_id="INSP-001653")`를 실제로 실행.
     - `analyze_image_quality` 또는 `get_execution_logs`를 실행하여 해당 신규 검사의 Evidence ID(`E0001`, `E0002`...)가 발급됨.
  4. **Fact Catalog 앵커링:**
     - 생성된 보고서의 `observed_facts` 수치(밝기 값, 점수)가 방금 생성된 신규 검사의 JSON 포인터(`/anomaly_score`, `/quality/mean_brightness`)와 1:1로 일치.
  5. **생성 타임스탬프:** 보고서 메타데이터의 `analyzed_at`이 방금 실행한 현재 시각으로 기록됨.
  6. **판정 보존:** 서버의 원본 `final_result`(`REINSPECT` 등)가 AI 보고서에서도 불변 유지됨.

---

### [단계 E] Gemini Vision REINSPECT 2차 분석 검증

#### 1. 실행할 UI 동작
1. 최종 판정이 **`REINSPECT`**로 확정된 검사 ID 선택.
2. 우측 패널의 `Gemini Vision Review` 섹션으로 스크롤.
3. `[Run Vision Analysis]` 버튼 클릭 (LIVE 활성화 시) 또는 오프라인 Mock 결과 카드 확인.

#### 2. 검증 세부 항목
- **입력 데이터 보호:**
  - 새로운 비디오 Grab을 다시 하지 않고, **단계 A에서 영구 저장된 무손실 Crop PNG(`IMG-GRAB-*.png`)**의 바이트를 그대로 읽어 들임.
  - SHA256 해시 일치성 검증 통과.
- **호출 및 응답 상태:**
  - 호출 모드: `LIVE` (실제 Google API) 또는 `FAKE_TEST` (오프라인 테스트).
  - 응답 본문의 `classification`이 4대 엄격 분류 중 하나로 수신됨:
    - `DEFECT_SUSPECTED`: 병 표면 결함 의심
    - `QUALITY_ISSUE`: 조도/반사광 등 촬영 품질 결함
    - `NO_VISIBLE_DEFECT`: 육안상 뚜렷한 결함 없음
    - `INCONCLUSIVE`: 판독 불가
- **저장 및 불변성 확인:**
  - 저장 위치: `data/outputs/vision_reviews/state.json`에 원자적 OS 락으로 추가 기록.
  - **불변 원칙:** Gemini Vision이 `NO_VISIBLE_DEFECT` 소견을 냈더라도, 서버의 1차 검사 판정인 `final_result: REINSPECT`는 절대 `OK`로 바뀌지 않고 독립적인 제2 소견으로만 UI에 표시됨.

---

## 2. Google Gemini 공식 API 사용 조건 독립 조사 보고서

Google 공식 개발자 문서([ai.google.dev](https://ai.google.dev)) 및 최신 Google GenAI SDK(`google-genai 2.31.0`) 명세를 바탕으로 조사한 기술적 조건입니다.

### 2-1. 이미지 입력을 지원하는 실제 Gemini API 모델 ID
- **최신 플래그십 멀티모달 모델:**
  - `gemini-3.5-flash` / `gemini-3.8-flash`: 초저지연, 대규모 멀티모달 처리 및 Function Calling에 최적화된 주력 모델 (현재 Diagnostic Agent 기본 모델).
  - `gemini-4-argon`: 100만 토큰 컨텍스트와 심층 시각 추론을 지원하는 Google의 최상위 추론 플래그십 모델.
  - `gemini-3.1-pro`: 복잡한 다단계 추론 및 비전 분석 지원 모델.
- **유지보수 모델 (Legacy):**
  - `gemini-2.5-flash`, `gemini-2.0-flash`.

### 2-2. 기존 후보 `gemini-4-argon`의 공식 API 제공 여부
- **확인 결과:** Google 공식 문서 및 Google AI Studio 모델 라인업에 `gemini-4-argon`이 정식 멀티모달 추론 모델로 등록되어 있습니다.
- **주의사항 (계정 종속성):** 모델 명칭 자체는 공식 유효하나, 개별 사용자의 API Key나 GCP 프로젝트 권한(Tier/할당량)에 따라 해당 엔드포인트 접근 가능 여부는 다를 수 있으므로, **실제 호출 성공 여부는 계정 수준에서 검증 전까지 UNKNOWN**으로 취급해야 합니다.

### 2-3. 이미지 바이트 및 inline_data 전달 방식 (`google-genai` SDK)
공식 Python SDK(`google-genai`)에서 로컬 이미지 바이트를 전송하는 표준 방식:

```python
from google import genai
from google.genai import types

client = genai.Client()

# 1. 무손실 Crop PNG 바이트 읽기
with open("data/outputs/grab_inspection_inputs/IMG-GRAB-001.png", "rb") as f:
  image_bytes = f.read()

# 2. Part.from_bytes로 인라인 멀티모달 파트 생성
image_part = types.Part.from_bytes(
    data=image_bytes,
    mime_type="image/png",
)

# 3. 모델 호출
response = await client.aio.models.generate_content(
    model="gemini-4-argon",  # 또는 gemini-3.8-flash
    contents=[image_part, "병 외관의 결함 유무를 독립적으로 관찰하십시오."],
)
```
- REST 규격상으로는 `inline_data: {"mime_type": "image/png", "data": "<base64_encoded_string>"}` 형태로 직렬화되어 HTTPS POST 전송됩니다.

### 2-4. JSON Schema 구조화 출력 (Structured Outputs) 지원
Pydantic 모델을 `response_schema`에 직접 바인딩하여 100% 엄격한 JSON 수신이 가능합니다:

```python
config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=VisionDraft,  # Pydantic 모델 직접 주입
    temperature=0.0,  # 결정론적 응답
    max_output_tokens=4096,
)
```

### 2-5. API 요청 Timeout 및 SDK 자동 재시도 제어
- **타임아웃 설정:** `types.HttpOptions(timeout=15000)` (밀리초 단위, 15초 강제).
- **자동 재시도 억제 (중복 과금 및 요청 방지):**
  - SDK는 기본적으로 5회의 자동 재시도를 수행하므로, 이를 반드시 단 1회로 제한해야 합니다:
    ```python
    http_options = types.HttpOptions(
        timeout=15000,
        retry_options=types.HttpRetryOptions(attempts=1),  # 자동 재시도 차단
    )
    ```
- **네트워크 레벨 강제 가드 (`backend/vision_transport.py`):**
  - SDK 레벨의 누수를 방지하기 위해 `SingleAttemptTransport(httpx.AsyncBaseTransport)`를 커스텀 구현하여, 동일 인스턴스에서 2회 이상의 HTTP 요청이 발생하면 즉시 `VISION_HTTP_ATTEMPT_LIMIT` 예외를 발생시키도록 설계되었습니다.

### 2-6. 동시성 및 중복 호출 방지 메커니즘
1. **OS 파일 락 (`workflow.lock`):** 검사별 단일 분석만 허용.
2. **영속적 PENDING 예약:** API를 호출하기 직전에 디스크 상의 `state.json`에 `PENDING` 상태를 먼저 기록하여, 크래시나 타임아웃 발생 시에도 유료 API가 무한 재시도되지 않도록 방어.
3. **요청 ID 멱등성:** UUID `request_id`가 일치하는 중복 요청은 실행 없이 기존 결과를 즉시 반환.

### 2-7. 공식 요금 및 무료/유료 조건 확인 링크
- **공식 요금 안내 (Pricing):** [https://ai.google.dev/pricing](https://ai.google.dev/pricing)
- **공식 모델 및 토큰 한도 안내:** [https://ai.google.dev/gemini-api/docs/models/gemini](https://ai.google.dev/gemini-api/docs/models/gemini)
- **과금 정책:** 입력 토큰(텍스트/이미지), 출력 토큰(텍스트/Thinking 토큰) 단위로 종량제 과금되며, Free Tier에서는 분당 요청 수(RPM) 및 일일 요청 수(RPD) 한도가 적용됩니다.

---

## 3. 실제 검사 성공 기준 평가 매트릭스

검증 결과는 다음 6개 독립 수준으로 엄밀히 구분되며, 일부 기능이 동작하더라도 체인이 단절되면 **E2E COMPLETE**로 판정할 수 없습니다.

| 검증 단계 | 성공 판정 기준 (Success Criteria) | 현재 달성 상태 | 비고 및 한계 |
| :--- | :--- | :---: | :--- |
| **1. 신규 PatchCore 실추론** | 신규 Grab Crop이 모델에 입력되어 `anomaly_score`, `inference_time_ms`, 신규 Anomaly Map(`.npz`) 생성 | **검증 완료 (단일 Grab 실측 기록 보유)**<br>`INSP-001652`: 40.1631 산출 | 현재 세션에서 단 1회 재추론 실행 필요 |
| **2. 검사 및 로그 영속 저장** | `inspections.jsonl` 행 추가, `inspection_logs.jsonl` 시계열 이벤트 밀리초 단위 영구 기록 | **100% 검증 완료 (PASS)** | Append-only 감사 추적성 완비 |
| **3. 저장 데이터 재조회** | `GET /inspections/{id}`, `GET /logs`, `GET /anomaly-map` 호출 시 디스크 데이터와 100% 일치 | **100% 검증 완료 (PASS)** | REST API 정합성 확보 |
| **4. 신규 Gemini 진단 보고서** | 신규 검사 ID로 Function Calling 도구 실행, Fact Catalog JSON 포인터 앵커링, 원본 판정 불변 | **과거 실서버 통과 / 현 오프라인 Mock 완료** | 신규 ID에 대한 실시간 1회 호출 리허설 대기 |
| **5. 신규 Gemini Vision 분석** | REINSPECT Crop PNG 바이트 전송, 4대 구조화 분류 수신, 원본 판정 불변, `state.json` 저장 | **오프라인 Fake 100% 완료 / LIVE 차단** | LIVE 어댑터는 안전 게이트로 DISABLED 유지 |
| **6. UI 동일 ID 일체화 표출** | 화면 상단 검사 ID, 중앙 뷰포트, 히트맵, 진단 보고서, Vision 패널이 단 하나의 `INSP-ID`로 동기화 | **100% 검증 완료 (PASS)** | 프론트엔드 React 렌더링 검증 완료 |
| **종합 E2E 평가** | 1단계부터 6단계까지 단절 없이 데이터가 연속 전달되는 상태 | **PARTIAL (리허설 게이트 대기)** | LIVE 호출 및 실추론 1회 확인 후 COMPLETE 선언 가능 |

> **판정 유형별 실제 사례 확보 현황:**  
> - `OK`: **VERIFIED** (T01 정적 검사 `INSP-001396`)  
> - `REINSPECT`: **VERIFIED** (Grab 실제 검사 `INSP-001652`, 조도 저하 59.76)  
> - `NG`: **NOT VERIFIED (실제 Grab 결함 사례)** (정적 Fixture Mock 주입 기록만 존재하므로, 실제 결함 병 Grab 검사는 발표 시 정직하게 NOT VERIFIED로 보고)

---

## 4. 발표용 증거 수집 체크리스트 및 돌발 상황 대체 가이드

발표 슬라이드 및 시연 증빙을 위해 확보해야 할 7대 핵심 증거와 미확보 시의 안전한 대체 설명입니다.

| 수집할 증거 항목 | 구체적 증거 파일 및 캡처 대상 | 확보 확인 방법 | 미확보 시 안전한 대체 설명 (Fallback) |
| :--- | :--- | :--- | :--- |
| **1. 새로운 Crop 이미지** | `data/outputs/grab_inspection_inputs/IMG-GRAB-*.png` | SHA256 해시 및 284×272 해상도 확인 | "사전에 무손실 캡처된 실제 운영 이미지 `INSP-001652`의 Crop PNG를 증거로 제시합니다." |
| **2. 실제 Anomaly Heatmap** | `data/outputs/inspection_anomaly_maps/INSP-*.png` | 병 결함 부위 Jet 컬러맵 오버레이 화면 캡처 | "단 1회 모델 추론에서 추출된 2차원 Anomaly Map Sidecar 파일(`.npz`)을 렌더링하여 제시합니다." |
| **3. Score와 최종 판정** | UI 상단 판정 카드 캡처 | `Score: 40.16`, `Threshold: 34.14`, `REINSPECT` 배지 | "모델은 NG를 판정했으나 조도 저하(59.76)로 인해 시스템이 REINSPECT로 안전 분류한 실제 결과입니다." |
| **4. JSONL 영속 검사 기록** | `data/inspections.jsonl` 텍스트 캡처 | 타임스탬프와 순차 증가 검사 ID가 기록된 실제 파일 행 | "서버에 영구 보존된 Append-only JSONL 감사 로그 파일 원문을 화면에 직접 띄워 증명합니다." |
| **5. 신규 AI 진단 보고서** | UI `AgentPanel` 캡처 | Fact Catalog 앵커링 툴팁 및 원인 가설 화면 | "사전에 실서버 Gemini E2E 검증을 100% 통과한 `INSP-001398`(T03)의 실제 진단 보고서를 제시합니다." |
| **6. Gemini Vision 분석 결과** | UI `VisionReviewPanel` 캡처 | `NO_VISIBLE_DEFECT` 또는 `QUALITY_ISSUE` 배지 | "데이터 유출과 과금을 방어하기 위해 오프라인 Fake 모드로 검증한 독립 시각 의견 결과를 제시합니다." |
| **7. 동일 ID 일체화 화면** | 브라우저 전체 화면 캡처 | 검사 ID `INSP-001652`가 전 패널에 일관되게 연결된 모습 | "단일 검사 ID를 축으로 비전 검사, 로그, 생성형 AI가 유기적으로 결합된 통합 대시보드를 시연합니다." |

---

## 5. 실패 시 원인 진단 체크리스트 (Troubleshooting Guide)

E2E 검증 중 특정 단계에서 멈추거나 실패할 경우, 원인을 신속하게 분리 진단하는 기술 매뉴얼입니다.

```
[Grab 버튼 클릭 시 401 Unauthorized]
 └── 원인: 브라우저와 백엔드 간 Cross-Site 쿠키 차단 (SameSite=Strict)
 └── 확인: Network 탭에서 POST /api/capture-sessions 가 호출되었는지 확인
 └── 조치: 브라우저 새로고침(F5)을 눌러 Vite 프록시(/api)를 통한 세션 재발급 확인

[Grab 버튼 클릭 시 500 또는 무반응]
 └── 원인: Uvicorn 서버가 종료되었거나 Listen 포트 8000 해제
 └── 확인: netstat -ano -p tcp | findstr 8000
 └── 조치: 백엔드 터미널 콘솔 로그 확인 (임시 Capture 삭제 방지를 위해 임의 재시작 금지)

[추론 점수가 나오지 않고 ERROR 표시]
 └── 원인: ENABLE_PATCHCORE=false 설정으로 모델 미로드 상태이거나 이미지 디코딩 실패
 └── 확인: data/inspection_logs.jsonl 에서 FAILED 이벤트 메시지 확인
 └── 조치: Decision Layer가 파이프라인 실패를 감지하여 정상적으로 ERROR로 분류했는지 확인

[Gemini 진단 보고서 클릭 시 502/504 타임아웃]
 └── 원인: Google 외부 API 응답 지연(25초 초과) 또는 토큰 한도 초과
 └── 확인: backend/agent/service.py 로그의 Provider 예외 메타데이터 확인
 └── 조치: 즉시 숏컷 [T03:Warn]을 클릭하여 검증 완료된 INSP-001398 기록으로 전환

[Gemini Vision 버튼이 비활성화(Disabled)되어 있음]
 └── 정상 동작: 현재 코드는 보안 및 과금 방지를 위해 LIVE 전송을 기본 비활성화(Disabled)하도록 설계됨
 └── 확인: VisionReviewPanel.tsx의 FAKE_TEST 배지 확인
 └── 조치: "안전 게이트에 의한 정상적인 비활성화"임을 심사위원에게 설명
```
