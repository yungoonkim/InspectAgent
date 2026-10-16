# VisionInsight — 프레젠테이션 최종 점검 체크리스트 (`presentation/presentation-review-checklist.md`) [14장 발표본 최종 점검판]

> **문서 목적:** 기술 발표 담당자가 14장 프레젠테이션(`VisionInsight_Presentation_14slides.pptx`)을 최종 검수하고, 대본(`presentation-script.md`), 개요(`slide-outline.md`), 예상 질문집(`anticipated-questions.md`)과의 일치성을 보장하기 위한 점검 체크리스트입니다.

---

## 1. 슬라이드별 기술 정확성 및 디자인 점검 (14개 슬라이드 전수 검수)

| 슬라이드 | 점검 항목 | 기준 및 14slides 반영 내역 | 점검 결과 |
| :--- : | :--- | :--- | :---: |
| **Slide 1** | 표지 | • 단일 이미지 CPU 추론 평균 42.53ms 실측치 표기<br>• 실시간 제조 설비 처리량 과장 배제<br>• 발표일 2026.10.20 유지 | **PASS** |
| **Slide 2** | 문제 정의 | • 정상 이미지 180장 메모리 뱅크 학습 + 독립 29장 임계값 설정 분리 반영<br>• 조도 이상을 제품 결함과 구별하여 재검사(REINSPECT) 상태로 분류하도록 설계<br>• 실제 공장 폐기율 감소 실증 주장을 배제하고 원인 조사/점검 의사결정 지원으로 기술 | **PASS** |
| **Slide 3** | 시스템 아키텍처 | • 서버 규칙 기반 최종 검사 판정(`final_result`) 확정 명시<br>• 제조 설비 제어 표현(안전 격리, 오방출 방지 등) 제거 및 REINSPECT 분류 정정<br>• Gemini가 도구를 직접 실행하지 않고 Function Call 제안 후 서버가 실행함을 명시<br>• 실제 PLC/컨베이어 하드웨어 제어 미수행 명시 및 판정 불변 원칙 유지 | **PASS** |
| **Slide 4** | PatchCore 성능 | • Precision 100% 근거(TP=32, FP=0) 및 83장 표본 조건 명시 (실전 전수 보장 아님)<br>• Recall 50.79% 근거(TP=32, FN=31) 및 미탐 31건 솔직히 명시<br>• 개발 환경(x86_64 CPU) 실측 표현 정정 및 29장 통계 기반 고정 임계값(34.1442) 명시<br>• T06 사례 명시 및 실제 정답 라벨은 Agent에 미제공됨을 명시 | **PASS** |
| **Slide 5** | 검사 판정 체계 | • `result`(OK/NG/UNKNOWN)와 `final_result`(OK/NG/REINSPECT/ERROR) 구분<br>• 대표 4규칙 번호(Rule 1, 2, 4, 5) 및 Rule 4 사유 코드 `PRODUCT_ANOMALY_DETECTED` 정정<br>• **Rule 5 카드와 하단 박스 겹침 완벽 수정:** Rule 1~5 높이 0.95" 간격 1.05" 재설계 (Y: 1.35~5.45")<br>• 하단 별도 박스(Y: 5.60~7.05")에 Rule 3(`DEFECT_DETECTION_UNAVAILABLE`) 및 Rule 6(`UNKNOWN_STATE_COMBINATION`) 배치 (Clearance 0.15", Overlap 0%)<br>• REINSPECT를 실제 제품 격리/폐기가 아닌 서버 판정 상태 분류로 명시 | **PASS** |
| **Slide 6** | Gemini Function Calling | • sandbox 과장 표현 제거<br>• Gemini의 Function Call 제안 ➔ 서버 인자 검증 ➔ 서버 Python 실행 제어 흐름 명시<br>• 4대 Python 전용 도구 실제 구현 기준 표기 | **PASS** |
| **Slide 7** | 근거 및 판정 보호 | • '환각 완전 차단', '100% 무오류' 과장 표현 및 구버전 오타 완전 제거<br>• Pillar 2: "보고서에 포함된 구조화된 관측 사실(F0001~)을 서버의 실제 도구 결과와 결정적으로 대조"로 정밀화<br>• 하단: "T01의 관측 사실 6개와 T03의 관측 사실 12개가 서버의 Evidence 검증을 통과했습니다" 확인<br>• Evidence ID, Fact ID, JSON Pointer 1:1 결정적 검증 메커니즘 명시<br>• 원본 판정 불변 정책 명시 | **PASS** |
| **Slide 8** | Gemini 구조화 출력 | • HTTP 400의 정확한 거부 속성은 UNKNOWN으로 명시<br>• 단순 JSON 출력 ➔ Python DiagnosisDraft 변환 ➔ Pydantic ➔ 결정적 Evidence 검증 파이프라인 명시<br>• 모델 맹신이 아닌 서버 엄격 검증 구조 강조 | **PASS** |
| **Slide 9 (신규)** | 핵심 기술 난제와 해결 과정 | • **Slide 9 가독성 및 최신 상태 반영:** 3열 고대비 압축 카드 (HTTP 400 구조화 호환성 / HTTP 504 최종 생성 지연 / T05 ERROR 조기 종료 및 근거 검증), 문제·해결·결과 핵심 확대 및 대형 폰트 적용, 전체 pytest 984 PASS (경고 3건) 반영<br>• T05 카드: "기존 실서버 1회 FAIL (후속 조사 HTTP 504) → 조기 종료 개선 후 오프라인 PASS, 실서버 재검증 대기" 명시<br>• 하단 배너: T05 현황 및 984 PASS 배너 일치 | **PASS** |
| **Slide 10** | 실제 E2E: T01 & T03 | • **T01 정상 시나리오: 실서버 완전 성공 (PASS, 13.578초, 4,706 토큰, 팩트 6개)**<br>• **T03 조도 저하 시나리오: 실서버 완전 성공 (PASS, 24.600초, 9,873 토큰, 팩트 12개)**<br>• **T03 요청별 실측치: 도구1 2.43s, 도구2 3.05s, 최종 JSON 18.967s (30초 timeout 선택 적용)**<br>• 과거 504 원인 UNKNOWN 및 단일 성공으로 안정성 보장 불가 주석 포함 | **PASS** |
| **Slide 11** | 발표 데모 시연 | • T01 및 T03 독립형 정적 데모(`presentation/demo/`) 연계 시연 흐름 4단계 제시 (시연 시간 1분 40초 보호)<br>• T01 권장 조치 evidence_refs: `["F0003"]` 일치 표기<br>• T03 권장 조치 `["F0004", "F0007"]`, `["F0003"]` 일치 표기<br>• 유료 API 임의 호출 방지 원칙 및 정적 데모 재생 고지 | **PASS** |
| **Slide 12** | 구현 현황 및 로드맵 | • **전체 pytest 984개 PASS 반영 (오프라인 격리 환경, 경고 3건)**<br>• 1단: 실제 Gemini E2E PASS (T01, T03)<br>• 2단: 구현 및 오프라인 검증 PASS (ERROR 필수 17개 사실, T05 조기 종료 Mock PASS, 계측기 WARNING 정합화)<br>• **3단: 실제 E2E 미완료 (T05 기존 1회 FAIL / 수정 후 재검증 대기, T06 NOT TESTED)**<br>• 3단: React UI, 동영상 Grab/ROI, Cloud Run '개발 예정' 표기 | **PASS** |
| **Slide 13** | 한계 및 향후 개선 | • 미탐 한계(Recall 50.8%), Gemini 504 타임아웃, 호출 지연(13.58초 / 24.60초) 기술<br>• T03 최종 JSON 요청 시간(18.967초)과 전체 Agent E2E 소요 시간(24.600초) 명확히 구분<br>• 과거 14.15초 504 원인 UNKNOWN, 30초 설정 회차 단일 성공, 반복 검증 부족 명시<br>• 실제 물리적 PLC/배출기 제어 미수행 및 사후 비동기 진단 한정 명시 | **PASS** |
| **Slide 14** | 결론 | • 제목: 'VisionInsight — 근거 기반 산업 비전 AI Agent 설계'<br>• 4대 축(PatchCore, FastAPI, Gemini, Python) 명확히 요약<br>• 'AI가 판정을 대신하지 않고 검증된 정보를 이해·활용하도록 돕는 시스템' 메시지 일치 | **PASS** |

---

## 2. 시각 렌더링 검수 한계 및 좌표 안정성 보고

- **렌더링 도구 환경:**  
  현재 작업 환경에는 PowerPoint COM 자동화(`comtypes`)나 LibreOffice 헤드리스 렌더러가 없어 PPTX 슬라이드를 이미지 파일로 직접 일괄 변환하여 육안 검수를 수행하지 못했습니다.
- **보고 사항:**  
  따라서 본 보고서에서는 **"실제 슬라이드 렌더링 이미지를 통한 시각 검수를 완료했다"고 허위 주장하지 않습니다.**
- **대체 검증 조치:**  
  파이썬 코드 레벨(`generate_presentation_14slides.py`)에서 16:9 캔버스(너비 13.333인치, 높이 7.5인치)의 박스 좌표, 여백, 텍스트 상자 크기, 글자 크기(Pt) 및 줄 간격을 보수적으로 계산하여 배치했습니다.
  - 슬라이드 14장 전수 텍스트 파싱을 통해 텍스트 누락이나 예외 없이 정확히 생성되었음을 검증함
  - 모든 텍스트 상자의 `word_wrap = True` 및 상하좌우 패딩 부여
  - 3단 카드 간의 X축 간격(최소 0.25인치 이상)을 확보하여 텍스트 잘림 및 오브젝트 겹침 방지.

---

## 3. 발표 자료 간 일치성 최종 점검

1. **PPT 슬라이드 (`VisionInsight_Presentation_14slides.pptx`) ↔ 발표 대본 (`presentation-script.md`):**  
   - 14개 슬라이드의 순서, 제목, 핵심 메시지가 100% 일치합니다.
   - Slide 8의 Before/After 스키마 구조 설명과 신규 Slide 9의 3대 기술 난제 해결 과정의 역할 분리가 명확합니다.
   - 슬라이드 2의 180장/29장 역할 구분, 슬라이드 5의 Rule 4 / PRODUCT_ANOMALY_DETECTED, 슬라이드 13의 18.967초(최종 JSON)와 24.600초(전체 E2E) 구분이 완벽히 동기화되었습니다.
2. **데모 시나리오 (`demo-scenario.md`) ↔ Slide 11 시연 화면:**  
   - T01 및 T03 정적 데모(`presentation/demo/`) 시연 흐름 4단계와 권장 조치 필드(`["F0003"]`, `["F0004", "F0007"]`)가 완벽히 일치합니다.
3. **예상 질문집 (`anticipated-questions.md`) ↔ 본문 내용:**  
   - Part 1의 7대 집중 질문(가장 어려웠던 부분, Python 별도 검증 이유, HTTP 400 원인 UNKNOWN, 504와 30초 한계, T05 Mock vs E2E 미검증 이유, 복잡한 검증 구조 필요성, Codex vs Gemini 도구 선택) 및 Part 2의 18개 일반 기술 질문이 100% 일치하게 반영되었습니다.
