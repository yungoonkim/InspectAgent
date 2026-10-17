# VisionInsight — 프레젠테이션 최종 점검 체크리스트 (`presentation/presentation-review-checklist.md`) [Day4 최종 완료 점검판]

> **문서 목적:** 기술 발표 담당자가 14장 프레젠테이션(`VisionInsight_Presentation_14slides_verified.pptx`)을 최종 검수하고, 대본(`presentation-script.md`), 개요(`slide-outline.md`), 프로젝트 현황 요약(`project-status-for-presentation.md`)과의 일치성을 보장하기 위한 점검 체크리스트입니다.

---

## 1. 슬라이드별 기술 정확성 및 디자인 점검 (14개 슬라이드 전수 검수)

| 슬라이드 | 점검 항목 | 기준 및 14slides 반영 내역 | 점검 결과 |
| :--- : | :--- | :--- | :---: |
| **Slide 1** | 표지 | • 단일 이미지 CPU 추론 평균 42.53ms 실측치 표기<br>• 4대 시나리오 실제 Gemini E2E 성공 (T01/T03/T05/T06 PASS) 표기<br>• 전체 pytest 1089 PASS / 4 SKIP (경고 2건) 표기<br>• 발표일 2026.10.20 유지 | **PASS** |
| **Slide 2** | 문제 정의 | • 정상 이미지 180장 메모리 뱅크 학습 + 독립 29장 임계값 설정 분리 반영<br>• 조도 이상을 제품 결함과 구별하여 재검사(REINSPECT) 상태로 분류하도록 설계<br>• "Gemini가 Function Calling으로 조회를 요청하면, 서버가 허용된 Python 도구를 검증·실행하여 실제 검사 근거를 수집"으로 도구 호출 표현 정정 | **PASS** |
| **Slide 3** | 시스템 아키텍처 | • 서버 규칙 기반 최종 검사 판정(`final_result`) 확정 명시<br>• 검사 결과(`data/inspections.jsonl`) 및 감사 로그(`data/inspection_logs.jsonl`) 공식 파일명 표기<br>• 로컬 저장은 개발용이며 Cloud Run 영구 저장은 GCS 연동 과제임을 명시<br>• 순수 모델 추론 42.53ms 측정치 표기 (FastAPI/Gemini/라인 제어 미포함)<br>• 실제 PLC/컨베이어 하드웨어 제어 미수행 명시 및 판정 불변 원칙 유지 | **PASS** |
| **Slide 4** | PatchCore 성능 | • Precision 100% 근거(TP=32, FP=0) 및 83장 표본 조건 명시 (실전 전수 보장 아님)<br>• Recall 50.79% 근거(TP=32, FN=31) 및 미탐 31건 솔직히 명시<br>• CPU 42.53ms는 PatchCore 모델 추론 시간이며 Agent 전체/라인 처리속도 아님을 명시<br>• T06 사례 명시 및 실제 정답 라벨은 Agent에 미제공됨을 명시<br>• 과거 209장(46.17ms) 모델 대비 현재 180장(42.53ms) 차이 및 contamination FN 표기 불일치는 현황 제약으로 보존 | **PASS** |
| **Slide 5** | 검사 판정 체계 | • `result`(OK/NG/UNKNOWN)와 `final_result`(OK/NG/REINSPECT/ERROR) 구분<br>• 대표 4규칙 번호(Rule 1, 2, 4, 5) 및 Rule 4 사유 코드 `PRODUCT_ANOMALY_DETECTED` 정정<br>• Rule 1~5 높이 0.95" 간격 1.05" 재설계 (Y: 1.35~5.45")<br>• 하단 별도 박스(Y: 5.60~7.05")에 Rule 3(`DEFECT_DETECTION_UNAVAILABLE`) 및 Rule 6(`UNKNOWN_STATE_COMBINATION`) 배치 (Clearance 0.15", Overlap 0%)<br>• REINSPECT를 실제 제품 격리/폐기가 아닌 서버 판정 상태 분류로 명시 | **PASS** |
| **Slide 6** | Gemini Function Calling | • sandbox 과장 표현 제거<br>• Gemini의 Function Call 제안 ➔ 서버 인자 검증 ➔ 서버 Python 실행 제어 흐름 명시<br>• 4대 Python 전용 도구 실제 구현 기준 표기 | **PASS** |
| **Slide 7** | 근거 및 판정 보호 | • '환각 완전 차단', '100% 무오류' 과장 표현 및 구버전 오타 완전 제거<br>• Pillar 2: "보고서에 포함된 구조화된 관측 사실(F0001~)을 서버의 실제 도구 결과와 결정적으로 대조"로 정밀화<br>• 하단: "4대 대표 시나리오 T01(6개), T03(12개), T05(17개), T06(6개)의 관측 사실 전원이 서버의 Evidence 및 JSON Pointer 검증을 통과했습니다" 확인<br>• Evidence ID, Fact ID, JSON Pointer 1:1 결정적 검증 메커니즘 명시<br>• 원본 판정 불변 정책 명시 | **PASS** |
| **Slide 8** | Gemini 구조화 출력 | • HTTP 400의 정확한 거부 속성은 UNKNOWN으로 명시<br>• 단순 JSON 출력 ➔ Python DiagnosisDraft 변환 ➔ Pydantic ➔ 결정적 Evidence 검증 파이프라인 명시<br>• 모델 맹신이 아닌 서버 엄격 검증 구조 강조 | **PASS** |
| **Slide 9** | 핵심 기술 난제와 해결 과정 | • 3열 고대비 압축 카드 (HTTP 400 구조화 호환성 / HTTP 504 분리 계측 / T05 조기 종료 & T06 판정 불변성 완결)<br>• T03/T06 504 원인 UNKNOWN 및 30초 timeout 선택 적용 명시 (504 직접 해결은 미확정)<br>• T05 17개 관측 사실 조기 종료 및 T06 정답 격리/판정 불변 완결 명시<br>• 하단 배너: T01·T03·T05·T06 대표 4개 시나리오에서 각각 실제 Gemini E2E 성공 회차 확보 (단일 성공 회차가 반복 실행 안정성을 보증하는 것은 아님) | **PASS** |
| **Slide 10** | 실제 E2E: 4대 시나리오 | • **4열 대형 수치 중심 카드 레이아웃으로 프로젝터 가독성 대폭 개선**<br>• 카드 내부 본문 크기: 시나리오명 18pt, PASS 12.5pt, 최종 판정 15pt, 전체 소요시간 17pt, Fact 13.5pt<br>• **T01 정상:** INSP-001396, 13.58초, Fact 6개 100% 통과, 최종 OK<br>• **T03 품질 경고:** INSP-001398, 24.60초, Fact 12개 100% 통과, 최종 REINSPECT<br>• **T05 로드 실패:** INSP-001405, 16.33초, Fact 17개 100% 통과, 최종 ERROR<br>• **T06 저장 OK:** INSP-001406, 26.37초, Fact 6개 100% 통과, 최종 OK (불변)<br>• 하단 주석: T06 30초 timeout 적용 회차 성공(504 직접 해결 미확정), 원본 ASGI 미보관으로 재구성 코드 기반 사후 검토 한계 명시 | **PASS** |
| **Slide 11** | 발표 데모 시연 | • T01 및 T03 독립형 정적 데모(`presentation/demo/`) 연계 시연 흐름 4단계 제시 (시연 집중 조작 시간 1분 40초 별도 구분)<br>• 4대 시나리오 실서버 성공 보고서 핵심 특징 비교 표기<br>• 유료 API 임의 호출 방지 원칙 및 정적 데모 재생 고지 | **PASS** |
| **Slide 12** | 구현 현황 및 로드맵 | • **중복 `• •` 글머리표 완전 제거 및 폰트 10~14pt 가독성 확대**<br>• **1단: Day4 백엔드 Agent PoC 완료 (`DAY4_DONE`, 1089 PASS / 4 SKIP, 4대 E2E 성공 회차 확보)**<br>• **2단: Day5 진행 상황 (Step 1 감사 COMPLETE, Step 1-B Mock 36회 PASS, 개정 Day5 영상 파이프라인 예정)**<br>• **3단: Day6~7 UI 및 배포 로드맵 (Day6 React 웹 관제, Day7 Cloud Run 배포 예정)**<br>• Day 5 이후 과제는 실증 증거 확보 전 미완료(진행/대기/예정) 상태로 엄격 관리 명시 | **PASS** |
| **Slide 13** | 한계 및 향후 개선 | • 미탐 한계(Recall 50.79%, FN 31건), Gemini 504 타임아웃, 호출 지연(13.58초 ~ 26.37초) 기술<br>• 과거 504 원인 UNKNOWN 및 30초 설정 회차 성공이 504 직접 해결인지 미확정 명시<br>• T06 원본 ASGI 본문 미보관으로 재구성 코드 기반 검토 한계 명시<br>• 실제 물리적 PLC/배출기 제어 미수행 및 사후 비동기 진단 한정 명시 | **PASS** |
| **Slide 14** | 결론 | • 제목: 'VisionInsight — 근거 기반 산업 비전 AI Agent 설계'<br>• 4대 축(PatchCore: CPU 42.53ms 측정, FastAPI: final_result 확정 및 로컬 JSONL 기록, Gemini: 도구 조회 사후 진단, Python: 엄격 근거 검증/판정 보호) 명확히 요약<br>• 'AI가 판정을 대신하지 않고 검증된 정보를 이해·활용하도록 돕는 시스템' 메시지 일치 | **PASS** |

---

## 2. 시각 렌더링 검수 한계 및 좌표 안정성 보고

- **내용 검증 vs 시각적 렌더링 검증 상태 분리:**
  - **내용 및 수치 무결성 검증:** **PASS** (14개 슬라이드 전체 텍스트 및 핵심 수치 일치 확인)
  - **시각적 육안 렌더링 검증:** **NOT TESTED (실제 렌더러 부재)**
- **렌더링 도구 환경:**  
  현재 작업 환경에는 PowerPoint COM 자동화(`comtypes`)나 LibreOffice 헤드리스 렌더러가 없어 PPTX 슬라이드를 이미지 파일로 직접 일괄 렌더링하여 육안 시각 검수를 수행하지 못했습니다.
- **보고 사항:**  
  따라서 본 보고서에서는 **"실제 슬라이드 렌더링 이미지를 통한 시각 검수를 완료했다"고 허위 주장하지 않습니다.**
- **대체 검증 조치:**  
  파이썬 코드 레벨(`generate_presentation_14slides_verified.py`)에서 16:9 캔버스(너비 13.333인치, 높이 7.5인치)의 박스 좌표, 여백, 텍스트 상자 크기, 글자 크기(Pt) 및 줄 간격을 보수적으로 계산하여 배치했습니다.
  - 슬라이드 14장 전수 텍스트 파싱을 통해 텍스트 누락이나 예외 없이 정확히 14장 슬라이드가 정상 생성되었음을 검증함
  - Slide 10: 4열 카드 너비 2.75인치, 간격 0.244인치, 높이 4.48인치로 캔버스(13.333인치) 내 정렬 완벽 확인. 본문 폰트 12.5~18pt로 확대하여 프로젝터 가독성 극대화
  - Slide 12: 3열 카드 너비 3.7인치, 간격 0.3인치로 3단 체계 정렬 확인. 중복 글머리표 완전 제거 및 본문 폰트 10~14pt로 확대
  - 모든 텍스트 상자의 `word_wrap = True` 및 상하좌우 패딩 부여
  - 카드 간의 간격을 확보하여 텍스트 잘림 및 오브젝트 겹침 방지.

---

## 3. 발표 자료 간 일치성 최종 점검

1. **PPT 슬라이드 (`VisionInsight_Presentation_14slides_verified.pptx`) ↔ 발표 대본 (`presentation-script.md`):**  
   - 14개 슬라이드의 순서, 제목, 핵심 메시지가 100% 일치합니다.
   - Slide 9의 3대 기술 난제와 Slide 10의 4대 시나리오 실측 비교(대형 핵심 지표)가 완벽히 동기화되었습니다.
   - Slide 12의 Day4 완료 및 Day5 진행(감사 COMPLETE, Mock 36회 PASS), Day6~7 계획 분리 구조가 대본과 정확히 일치합니다.
2. **프로젝트 현황 요약 (`project-status-for-presentation.md`) ↔ 슬라이드 내용:**  
   - 전체 pytest 1089 PASS / 4 SKIP (경고 2건) 및 4대 시나리오 E2E 실측치가 100% 일치합니다.
   - T06 10단계 개발 과정 및 한계(30초 직접 해결 미확정, ASGI 미보관)가 완벽히 동기화되었습니다.
3. **슬라이드 개요 (`slide-outline.md`) ↔ 본문 내용:**  
   - 슬라이드별 핵심 메시지와 시간 배분이 12분 발표에 맞게 정밀하게 동기화되었습니다. (발표/데모 12분, Slide 10~11 구간 2분 30초 중 정적 데모 조작 1분 40초 별도 구분)
