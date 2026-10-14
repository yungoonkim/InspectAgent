# VisionInsight 구현 현황 보고서 (`docs/implementation-status.md`)

> **프로젝트:** VisionInsight — MVTec AD Bottle 기반 Vision 검사 이상 진단 AI Agent  
> **진행 단계:** Day 3 - Step 4 완료 (오류 주입 시나리오 통합 검증 완료)  
> **최종 검증일:** 2026-10-14  

---

## 1. 개요 및 마일스톤 현황

VisionInsight 프로젝트의 Day 1 (FastAPI 기반 검사 ID 발급 및 이미지 로드), Day 2 (OpenCV Brightness 분석 및 JSONL 저장), Day 3 (T01, T03, T05, T06 오류 주입 시나리오 및 정답 분리) 구현과 통합 검증을 완료했습니다.

| 마일스톤 | 목표 및 범위 | 상태 | 검증 결과 |
| :--- | :--- | :---: | :--- |
| **Day 1** | Bottle 이미지 로드 + `POST /inspections` 검사 ID 반환 | **완료** | 순차적 고유 ID(`INSP-XXXXXX`) 발급, 중립 `image_id` 매핑 |
| **Day 2** | OpenCV 밝기 지표 계산 + JSONL 검사/이벤트 로그 자동 저장 | **완료** | `train/good` 정상 통계 기반 임계값, 스레드 세이프 JSONL 저장 |
| **Day 3** | T01/T03/T05/T06 반복 재현 + 평가 정답 물리적 격리 | **완료** | 4대 시나리오 실측 검증 완료, 정답 라벨 100% 은닉, 57개 테스트 PASS |
| **Day 4** | Gemini AI Agent 실제 도구 호출 + 구조화 보고서 | 대기 | Day 3 검사 API 및 JSONL 데이터 기반 Agent 도구 연동 예정 |
| **Day 5** | 상황별 추가 조사 + 반례 평가 | 대기 | Agent 심층 진단 및 가설 수립 기능 |
| **Day 6** | React E2E + Cloud Run 준비 | 대기 | 웹 대시보드 프론트엔드 및 컨테이너 빌드 |
| **Day 7** | Cloud Run HTTPS API / Agent 분석 검증 + 최종 문서화 | 대기 | 배포 환경 검증 |

---

## 2. Day 3 핵심 시나리오 (T01, T03, T05, T06) 구현 내역

| 시나리오 | 실행 목적 | 입력 이미지 식별자 | 실제 측정 지표 | image_quality_status | result | 주요 발생 이벤트 |
| :---: | :--- | :--- | :--- | :---: | :---: | :--- |
| **T01** | 정상 Bottle 기준 검사 | `IMG-BOTTLE-0084`<br>(`train/good/000.png`) | mean: 135.86<br>std: 92.66 | `NORMAL` | `UNKNOWN` | `INSPECTION_STARTED`<br>`IMAGE_LOADED`<br>`ANALYSIS_COMPLETED` (INFO)<br>`INSPECTION_COMPLETED` |
| **T03** | 조도 저하(0.6x) 오류 주입 | `IMG-BOTTLE-INJ-0001`<br>(`injected_images/`) | mean: 81.24<br>std: 55.79 | `WARNING_LOW_BRIGHTNESS` | `UNKNOWN` | `INSPECTION_STARTED`<br>`IMAGE_LOADED`<br>`ANALYSIS_COMPLETED` (**WARN**)<br>`INSPECTION_COMPLETED` |
| **T05** | 이미지 로드 실패 재현 | `IMG-BOTTLE-NONEXISTENT`<br>(부재 가상 경로 stub) | 측정 불가<br>(`metrics={'error': ...}`) | `ERROR` | `UNKNOWN` | `INSPECTION_STARTED`<br>`IMAGE_LOAD_FAILED`<br>`INSPECTION_FAILED`<br>*(ANALYSIS_COMPLETED 미발생)* |
| **T06** | 불량 원본 정상 흐름 처리 | `IMG-BOTTLE-0001`<br>(`broken_large/000.png`) | mean: 138.37<br>std: 92.08 | `NORMAL` | `UNKNOWN` | `INSPECTION_STARTED`<br>`IMAGE_LOADED`<br>`ANALYSIS_COMPLETED` (INFO)<br>`INSPECTION_COMPLETED` |

---

## 3. 평가 정답 데이터 격리 구조

* **프로젝트 내부 (`InspectAgent/test_data/`)**:
  * 운영 코드 및 향후 Agent가 접근할 수 있는 영역입니다.
  * 중립 식별자(`IMG-BOTTLE-XXXX`) 및 변형 사본 이미지(`injected_images/`)만 보관됩니다.
  * `broken_large`, `contamination`, `good` 같은 원본 정답 라벨이나 0.6배 주입 계수는 일절 포함되지 않습니다.
* **프로젝트 외부 (`Project/evaluation_private/`)**:
  * 운영 FastAPI 및 Agent 도구의 파일 접근 경로에서 물리적으로 완전히 분리된 외부 디렉터리입니다.
  * `evaluation_answers.json` 등 정답 데이터는 오프라인 평가 러너에서만 별도로 읽도록 구성되어 있습니다.
  * 정적 코드 분석 결과 `backend/` 코드베이스 내에 `evaluation_private` 또는 `evaluation_answers`에 대한 참조가 전무(Zero Reference)함을 확인했습니다.

---

## 4. 검증 명령어 및 실행 방법

```bash
# 1. T03 오류 주입 이미지 생성 및 원본 SHA-256 불변성 검증
python scripts/generate_t03_fault.py

# 2. T01, T03, T05, T06 시나리오 2회 반복 자동 검증 러너 실행
python scripts/verify_day3_scenarios.py

# 3. 전체 pytest 테스트 스위트 회귀 검증 (총 57개 테스트)
pytest tests -v
```

---

## 5. 현재 구현된 기능 vs 미구현 기능

### 구현 완료된 기능
1. **FastAPI 백엔드 서비스**:
   * `GET /health` : 헬스체크
   * `GET /baseline/brightness` : 정상 Bottle 밝기 기준 통계 제공
   * `POST /inspections` : 검사 생성, 밝기 분석, 영상 품질 판정, JSONL 저장
   * `GET /inspections/images` : 등록된 중립 image_id 목록 조회
2. **OpenCV 비전 분석 및 무결성 보호**:
   * 이미지 크기, 그레이스케일 변환, 밝기 통계(mean, std, min, max) 계산
   * 0.6배 밝기 감쇄 주입(`inject_brightness_fault`) 및 분리 저장(`save_modified_image`)
   * 원본 파일 SHA-256 해시 검증을 통한 무수정 보장
3. **JSONL 저장소 계층**:
   * `data/inspections.jsonl` : 검사 결과 레코드 저장
   * `data/inspection_logs.jsonl` : 세부 실행 이벤트 로그 저장
   * 스레드 락 기반 동시성 안전 보장, `inspection_id` 기준 상호 연결
4. **오류 주입 시나리오 4종**:
   * T01(정상), T03(조도 저하), T05(로드 실패), T06(불량 원본 완수) 100% 재현

### 아직 구현하지 않은 기능 (Day 4 이후 예정)
1. **Gemini AI Agent 연동 (Day 4)**:
   * Google GenAI SDK를 활용한 Agent 도구(Tool Calling) 연동
   * `inspections.jsonl` 및 `inspection_logs.jsonl` 기반 이상 원인 추론 및 구조화 보고서 생성
2. **독립 결함 분류 모델 (Day 4~5)**:
   * Bottle 표면 크랙/오염 판정(OK/NG) 모델 연동 (현재는 `result: UNKNOWN` 유지)
3. **React 웹 프론트엔드 대시보드 (Day 6)**
4. **Google Cloud Run 배포 및 영구 스토리지 계층 (Day 6~7)**

---

## 6. 알려진 제약 및 Day 4 준비 사항

1. **StarletteDeprecationWarning**:
   * `testclient.py`에서 `httpx` 관련 경고가 1건 발생하나 테스트 및 실제 API 동작에는 영향이 없는 알려진 개발 환경 이슈입니다.
2. **Day 4 연동 준비 완료**:
   * Day 4에서 Gemini Agent가 호출할 도구(`tools/`)는 `backend/inspection.py`의 `execute_inspection_workflow` 및 `backend/storage.py`의 `get_inspection`, `get_logs` API를 그대로 재사용할 수 있도록 인터페이스가 완비되어 있습니다.
