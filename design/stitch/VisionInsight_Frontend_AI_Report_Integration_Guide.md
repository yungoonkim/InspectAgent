# VisionInsight 프론트엔드 — Gemini AI 진단 보고서 연동 명세

> **목적:** Day 5–6 React UI 개발 시, 실제 T01 분석 응답 JSON을 올바르게 렌더링하고 Stitch A/B 디자인을 API에 연결하기 위한 참고 문서.  
> **근거 자료:** `response_1792113985724.json` (T01 실제 응답), `DesignA.html` (다크), `DesignB.html` (라이트), 사용자 제공 Day 4 검증 보고.  
> **검증 범위:** T01 `INSP-001396`의 `analysis_status=COMPLETED`, 실제 Gemini 도구 조회 및 근거 검증 성공. **T03은 HTTP 504로 실패**, T05/T06은 실서버 미검증.  
> 이 문서는 **구현 명세/참고자료**이며 React 컴포넌트 구현이나 기존 API 수정이 완료되었다는 의미가 아닙니다.

## 1. UI와 응답의 핵심 원칙

1. **PatchCore 검사 판정**과 **Gemini AI 진단 설명**은 서로 다른 정보다. Gemini가 검사 결과를 덮어쓰거나 결함을 확정했다고 표현하면 안 된다.
2. 메인 화면에는 **Live View → Grab Frame → ROI 선택 → Run Inspection**을 상단에, **PatchCore 결과 + Gemini 진단**을 하단에 배치한다.
3. 보고서 기본 뷰는 **요약 + 권장 점검**만 간결하게 노출한다. `observed_facts`, `possible_causes`, `limitations`, 실행 Trace는 접기/펼치기 또는 별도 상세 화면으로 제공한다.
4. 사전 녹화된 영상은 **SIMULATED LIVE / Demo Mode**로 표시한다. 물리 카메라 연결, PLC, Ejector, Jetson, FPS 등 구현·측정되지 않은 기능/지표를 지어내지 않는다.
5. 초기 화면에 예시 NG 및 크랙 mm 수치가 **실제 검사 결과처럼 선표시되지 않도록** 한다. 반드시 `대기` 상태부터 시작하고, 실제 API 응답을 받은 뒤 렌더링한다.
6. 기존 검사와 로그 데이터는 변경하지 않는다. **이벤트 로그에서 `product_id`를 보여주지 않는다.** 검사 이력에는 적법한 기존 데이터 계약에 따라 표시할 수 있다.

## 2. 참조 디자인과 프로젝트 내 권장 위치

```
design/
  stitch/
    DesignA.html  # Industrial dark, 기본 다크 테마 참조
    DesignB.html  # Modern AI light, 기본 라이트 테마 참조
    VisionInsight_Frontend_AI_Report_Integration_Guide.md  # 본 문서 권장 위치
```

React에서는 두 HTML을 별개 앱으로 복사하지 말고 **공유 컴포넌트 + 테마 토큰(dark/light)** 방식으로 재구성한다.

권장 컴포넌트 (파일명은 예시): `InspectionWorkspace`, `LiveVideoPanel`, `GrabRoiPanel`, `PatchCoreResultCard`, `GeminiReportCard`, `ObservedFactsAccordion`, `RecommendedChecks`, `InspectionHistoryView`, `EventLogView`.

Stitch HTML 내부 샘플 데이터와 이미지 URL은 **UI 참고용**이다. 실시간 기능/측정값/실제 근거로 취급하지 말 것.

## 3. 분석 API 연동

현재 확인된 분석 엔드포인트:

```http
POST /analyze/{inspection_id}
```

- T01 예: `POST /analyze/INSP-001396`.
- **이 엔드포인트는 기존 보고서를 조회하는 GET이 아니라 새 Gemini 분석을 실행할 수 있는 POST다.** API 비용/지연이 발생하므로 UI 마운트·탭 전환·자동 새로고침 시 호출하지 말 것.
- 사용자가 명시적으로 **AI 진단 실행**을 눌렀을 때만 호출하고, 로딩 중에는 중복 실행을 막는다.
- 호출 후 별도 저장/재조회 API가 존재하는지는 **현재 자료만으로 확인되지 않는다**. 임의로 `/reports` API나 영구 저장을 가정하지 말 것.
- 실제 백엔드 `backend/main.py`, `backend/agent/service.py`, 응답 스키마를 코드로 재확인하고, **현재 계약을 기준으로 프론트엔드 타입을 작성**한다.
- 네트워크, 인증/환경설정, 타임아웃, 서버 HTTP 502 등의 오류를 사용자에게 안전하게 보여준다. 실패를 성공으로 위장하지 않는다.

### 메인 응답 JSON 필드

| 필드 | 역할 | 메인 화면 표시 |
|---|---|---|
| `inspection_id` | 검사 식별자 | 짧게 표시 |
| `analysis_status` | AI 분석 상태 (`COMPLETED`, `FAILED` 등 실제 백엔드 계약 확인) | **필수** |
| `error_code` | 실패 시 오류 코드 | 실패 안내에 사용 |
| `overall_summary` | **AI 진단 요약** | **항상 우선 표시** (성공 시) |
| `inspection_snapshot` | 분석 당시 조회된 검사 결과 스냅샷 | PatchCore 결과 카드와 상세 |
| `observed_facts` | **근거에 연결된 관측 사실 배열** | 상세 펼치기 |
| `possible_causes` | **가능한 원인 분석 배열** | 존재 시만 표시 |
| `recommended_checks` | **권장 점검 배열** | **우선 표시** |
| `limitations` | **진단 한계/주의사항 배열** | 펼치기 |
| `tools_used` | 조회에 사용한 Python 도구 목록 | 개발자 상세 |
| `tool_execution_trace` | 도구 실행 증적 | 개발자 상세 |
| `model_name` | Gemini 모델 식별자 | 선택적 정보 |
| `token_usage` | 요청별 사용량 | 개발자 상세 |
| `analysis_id` | 분석 인스턴스 식별자 | 상세/디버그 |
| `inspection_result` | 검사 모델 판정 | 검사 결과 카드 |
| `final_result` | 최종 집계 판정 | 검사 결과 카드 |
| `final_reason_code` | 최종 판정 사유 코드 | 상세/사유 설명 |
| `timestamp` | 분석 시각 (ISO 8601 UTC) | 사용자 로컬 시간 포맷 |

`model_availability`는 샘플에서 `NOT_TESTED`이며 모델 실행 가능/불가능을 판단하는 UI 상태로 오용하지 말 것.

## 4. 실제 T01 데이터로 확인한 보고서

**검사:** `INSP-001396` / `analysis_status=COMPLETED` / `error_code=null`.

### 4.1 기본 진단 (`overall_summary`)

> 기록된 모델 판정과 종합 판정은 OK입니다. 실제 무결점 제품을 보증하지 않습니다.

### 4.2 관측 사실 (`observed_facts`: 6개)

| fact_id | source_field | observed_value | evidence_id |
|---|---|---|---|
| F0001 | `/data/defect_detection_status` | `COMPLETED` | E0001 |
| F0002 | `/data/final_reason_code` | `ALL_CHECKS_PASSED` | E0001 |
| F0003 | `/data/final_result` | `OK` | E0001 |
| F0004 | `/data/image_quality_status` | `NORMAL` | E0001 |
| F0005 | `/data/result` | `OK` | E0001 |
| F0006 | `/data/status` | `COMPLETED` | E0001 |

관측 사실 렌더링에는 `fact_id`, `evidence_id`, `source_tool`, `source_field`, `observed_value`를 사용한다. `observed_value`는 타입이 바뀔 수 있으므로 문자열로 단정하지 말고 안전하게 표현한다.

### 4.3 가능한 원인 (`possible_causes`)

T01 실제 값: `[]`.

- **원인이 비어 있는 것은 정상적인 결과일 수 있다.** 가짜 원인을 추가하지 않는다.
- 기본 화면에서는 섹션을 생략하거나 “추가 원인 가설 없음”으로 표시한다.

### 4.4 권장 조치 (`recommended_checks`: 1개)

- `check_code`: `CONTINUE_MONITORING`
- `instruction`: `현재 기록된 판정을 유지하면서 후속 검사와 현장 상태를 관찰하세요.`
- `evidence_refs`: `["F0003"]` → 관측 사실 `F0003` (최종 결과 OK)

> 주의: `recommended_checks[].evidence_refs`는 이 샘플에서 **Evidence ID `E0001`이 아니라 Fact ID `F0003`을 가리킨다**. UI 링크는 `fact_id`를 기준으로 관측 사실까지 이동시키고, 그 사실에서 `evidence_id`를 보여주는 계층으로 구현한다.

### 4.5 진단 한계 (`limitations`: 4개)

- 검사 당시 밝기 기준치가 확인되지 않아 현재 설정으로 대체하지 않았습니다.
- 모델의 OK 판정은 실제 무결점 제품을 보증하지 않습니다.
- 규칙 기반 HIGH 신뢰도는 보정된 확률이나 100% 신뢰도를 뜻하지 않습니다.
- 검사 기록만으로 물리적 장애 원인을 확정할 수 없습니다.

### 4.6 검사 결과 (`inspection_snapshot`)

```json
{
  "status": "COMPLETED",
  "result": "OK",
  "image_quality_status": "NORMAL",
  "defect_detection_status": "COMPLETED",
  "final_result": "OK",
  "final_reason_code": "ALL_CHECKS_PASSED",
  "anomaly_score": 31.334630966186523,
  "decision_threshold": 34.1442
}
```

UI에서 `result`(PatchCore 판정)과 `final_result`(집계 판정)를 분리하고, `anomaly_score`와 `decision_threshold`는 숫자를 임의로 변형하지 않는다. 점수 UI의 막대 최대값을 `50` 또는 `100`으로 고정해 확률처럼 오해시키지 말 것.

## 5. 추천 React 출력 구조

### Live Inspection 화면

- **상단 좌:** `LiveVideoPanel` — 재생/일시정지, Grab Frame, SIMULATED LIVE 표시.
- **상단 우:** `GrabRoiPanel` — Grab 이전 empty state, Grab 이후 정지 이미지와 ROI, Reset ROI, Run Inspection.
- **하단 좌:** `PatchCoreResultCard` — 검사 전 대기, 검사 후 점수/임계값, 모델 `result`와 최종 `final_result` / 사유 코드.
- **하단 우:** `GeminiReportCard` — AI 분석 버튼, 로딩/성공/실패 상태. 성공 시 `overall_summary`와 `recommended_checks`를 우선 노출하고, 관측 사실·한계는 아코디언 사용.

### AI Report 별도 화면

검사 ID·분석 시각·보고서 요약·권고·관측 사실·근거 연결·한계·실행 Trace 순서로 상세 표현한다. **과거 보고서를 조회하는 API가 구현되기 전에는 영구 보고서 목록이 존재하는 척하지 않는다.**

### React 조건부 렌더링 예시 (개념 코드)

```tsx
// response는 실제 API 응답 스키마에 맞춰 런타임 검증 후 사용
if (report.analysis_status === 'FAILED') {
  return <ErrorState code={report.error_code ?? 'ANALYSIS_FAILED'} />;
}

if (report.analysis_status === 'COMPLETED') {
  return (
    <GeminiReportCard
      summary={report.overall_summary}
      checks={report.recommended_checks}
      facts={report.observed_facts}
      causes={report.possible_causes}
      limitations={report.limitations}
    />
  );
}

return <AnalysisPendingState />;
```

위 `ErrorState`, `GeminiReportCard`, `AnalysisPendingState`는 **제안 컴포넌트명이며 현재 코드에 존재한다고 확인되지 않았다.** 실제 스키마 타입/필드 nullable 여부는 백엔드 계약을 확인할 것.

## 6. 상태 전이 및 오류 UX

| 상태 | 표시 | 사용자 행동 |
|---|---|---|
| 초기 / 검사 전 | “검사 대기 중”, 보고서 없음 | Grab → ROI → 검사 실행 |
| 검사 진행 | 진행 스피너 및 버튼 중복 실행 방지 | 완료 대기 |
| 검사 결과만 있음 | PatchCore/최종 판정 표시, Gemini ‘분석 실행’ | 명시적 클릭으로 분석 |
| AI 분석 중 | “근거를 분석하고 있습니다” | 중복 요청 방지 |
| `COMPLETED` | 요약·권고, 상세 Evidence/한계 | 세부 내용 펼치기 |
| `FAILED` / HTTP 502 | “AI 진단을 완료하지 못했습니다” + 안전한 코드 | 수동 재시도 여부를 명시적으로 선택; 자동 호출 금지 |
| 필드 없음 / 빈 배열 | 데이터 없음/가설 없음 | 가짜 텍스트 생성 금지 |

**T03 참고:** 실제 테스트는 `HTTP 502`, `analysis_status=FAILED`, `error_code=GEMINI_REQUEST_FAILED`; 세 번째 Gemini 조사 요청에서 HTTP 504가 발생했다. **T03 최종 진단 JSON은 생성되지 않았다.** 따라서 실패 시 하드코딩된 밝기 권고를 ‘Gemini 생성 보고서’로 보여주면 안 된다. 검사 기록에 저장된 `OK / REINSPECT / IMAGE_QUALITY_WARNING`은 별도 검사 결과로 표시할 수 있다.

## 7. 주요 데이터 연결 주의사항

- `analysis_status`는 AI 분석 상태이며 `inspection_snapshot.status`는 검사 기록 상태다. 둘을 혼합하지 않는다.
- `inspection_result`와 `final_result`를 혼동하지 않는다. T03처럼 `OK / REINSPECT` 조합이 가능하다.
- `possible_causes=[]`을 오류로 간주하지 않는다.
- 원인이나 권고는 **검증된 보고서 필드 그대로** 보여준다. 뷰 계층에서 결함 이름, 실제 물리 치수, 고장 원인을 추측해 생성하지 않는다.
- `model_name`은 응답에 존재하는 값을 표시한다. Stitch의 기존 임의 모델 버전 문구(예: Gemini 1.5/Flash, PatchCore v1.2)는 제거한다.
- `tools_used`/`tool_execution_trace`는 일반 사용자를 위한 요약 카드가 아니라 상세/디버그 화면에 둔다.
- 서버가 확인하지 않은 ‘HIGH 확률’, ‘카메라 연결’, ‘물리 불량 확정’, ‘Ejector 작동’ 등을 UI에 표시하지 않는다.
- `timestamp`는 ISO 8601(UTC)에서 한국 시간 등 사용자 환경에 맞게 변환하되 원본 시간값은 유지한다.
- `token_usage`의 요청별 숫자를 단순 합산할 때 SDK usage 필드 정의를 확인한다. 이를 실제 과금 금액으로 환산해 확정 표시하지 않는다.

## 8. 구현 단계별 수용 기준 (Codex 체크리스트)

- [ ] `design/stitch/DesignA.html`, `DesignB.html`을 읽고 공통 React 레이아웃 구현
- [ ] 다크/라이트 테마 토글이 같은 컴포넌트와 데이터를 공유함
- [ ] 최초 화면에서는 검사 결과와 Gemini 결과가 대기 상태임
- [ ] Grab Frame/ROI/검사 실행 기능은 **실제 구현된 백엔드 API 계약**과 연결됨; 미구현이면 명시적으로 비활성/데모 처리
- [ ] `POST /analyze/{inspection_id}`는 명시적 사용자 액션에만 호출됨
- [ ] 성공 시 `overall_summary`, `recommended_checks` 렌더링
- [ ] 상세에서 `observed_facts`, `possible_causes`, `limitations` 렌더링
- [ ] `evidence_refs` → `fact_id` 링크 및 `evidence_id` 추적 가능
- [ ] 빈 `possible_causes`를 정상 처리
- [ ] `result`와 `final_result`를 독립적으로 표시
- [ ] HTTP 502/`FAILED`에서 오류 안내, 임의 AI 보고서 생성 없음
- [ ] 로그 화면에는 `product_id` 노출 없음
- [ ] 화면에 허구의 센서 지표/균열 치수/모델 버전 없음
- [ ] UI 테스트에서 T01 성공, T03 실패, 빈 배열 및 미수집 상태 확인
- [ ] 실제 Gemini 유료 호출 없이 Mock으로 프론트엔드 검증

## 9. 프론트엔드 개발 전에 확인할 미확정 사항

1. Grab/ROI 및 `Run Inspection`의 실제 API 경로·요청 본문·응답 모델: Day 5 백엔드 개발 결과를 기준으로 확인.
2. Gemini 보고서 영구 저장 및 과거 보고서 조회 API: **현재 미확인**. 필요하면 별도 설계/승인.
3. 전체 E2E에서 T03/T05/T06 보고서 형식의 실제 다양성: **미검증**.
4. AI 분석 POST의 실제 성공/실패 HTTP 응답 계약과 nullable 필드: 실제 FastAPI 스키마를 기준으로 확인.
5. 동영상 리소스와 ROI 이미지 처리 방식: 실제 프로젝트 파일 및 백엔드 계약으로 결정.

---

**구현 경계:** 이 문서를 참고한 React UI 개발은 Day 5·6에 별도 승인 후 진행한다. Gemini 실제 호출, 모델 재학습, 데이터 변경, Git add/commit/push는 UI 참고자료 제작의 일부가 아니다.
