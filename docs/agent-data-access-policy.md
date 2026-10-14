# VisionInsight — Gemini AI Agent 데이터 접근 정책 및 보안 계약
> **문서 번호:** POL-AGENT-001  
> **버전:** 1.1 (Day 3.5 프롬프트 8 보완 반영)  
> **적용 단계:** Day 4 Gemini AI Agent 개발 및 운영 전반  
> **준수 규정:** `AGENTS.md` 데이터 및 안전 규칙 (규칙 1~9)  

---

## 1. 개요 및 목적

VisionInsight는 MVTec AD Bottle 기반 산업용 Vision 검사 이상 진단 AI Agent 서비스입니다.  
본 문서는 Day 4에 구현될 **Gemini AI Agent가 검사 결과 및 실행 로그를 조회할 때 접근 가능한 데이터의 범위와 엄격히 금지되는 데이터를 정의**하여, 평가 정답 누출, 내부 시스템 정보 유출 및 환각(Hallucination)에 의한 오진단을 방지하는 것을 목적으로 합니다.

---

## 2. 파일 접근 범위 및 도구(Tools) 원칙

### 2.1 접근 권한 차단 원칙 (파일 분리만으로 보안 간주 금지)
- **핵심 원칙:** 평가 전용 데이터가 프로젝트 외부에 있다는 사실만으로 Agent의 접근 권한이 자동으로 차단된 것으로 간주하지 않습니다.
- **도구 탑재 제한:**
  - Agent에게 임의 파일 경로 조회(`open()`, 파일 시스템 탐색 등) 기능을 제공하지 않습니다.
  - Agent에게 쉘 명령어 실행(`subprocess`, `os.system`) 기능을 제공하지 않습니다.
  - Agent에게 임의 Python 코드 실행(`eval()`, `exec()`, REPL) 기능을 제공하지 않습니다.
  - Agent에게 평가 폴더나 데이터셋 폴더 검색 기능을 제공하지 않습니다.
- **접근 방식:**
  - 오직 사전에 승인되고 통제된 **4개의 정형 Python 도구(Function Calling)**만을 통해 서버 내부 저장소의 살균된 데이터만 조회합니다.
  - 모든 도구 파라미터는 `inspection_id: str` 또는 `product_id: str`과 같은 정규화된 비즈니스 식별자만을 허용하며, 파일 경로나 SQL/JSON 질의 문자열은 인자로 허용하지 않습니다.

### 2.2 Agent 전용 검사 조회 4대 도구 명세

| 도구 함수명 | 파라미터 | 반환 내용 | 접근 목적 |
| :--- | :--- | :--- | :--- |
| `get_inspection_result` | `inspection_id: str` | 단일 검사 결과 (`InspectionRecord` 살균본) | 최종 판정, 제품 판정, 영상 품질 및 이상 점수 확인 |
| `get_execution_logs` | `inspection_id: str` | 검사 라이프사이클 이벤트 로그 목록 | 단계별 실행 상태, 지연시간, 이상 징후 추적 |
| `analyze_image_quality` | `inspection_id: str` | 영상 품질 지표 (밝기 통계 및 임계값 비교) | 조명 어두움/밝음 등 영상 획득 환경 분석 |
| `get_inspection_history` | `product_id: str, limit: int = 5` | 동일 제품의 과거 최근 검사 이력 목록 | 반복 결함 여부 및 트렌드 파악 |

---

## 3. 데이터 접근 허용 및 금지 항목

### 3.1 허용 데이터 (Allowed Fields)
Agent는 오직 아래에 명시된 비즈니스 검사 필드만을 제공받습니다.

1. **식별자:** `inspection_id` (예: `INSP-000001`), `product_id` (예: `ABCD1541`), 중립 `image_id` (예: `IMG-BOTTLE-0001`)
2. **타임스탬프:** `timestamp` (ISO 8601 형식)
3. **상태 및 판정:**
   - `status`: 검사 프로그램 실행 상태 (`COMPLETED`, `FAILED`)
   - `result`: PatchCore 제품 판정 (`OK`, `NG`, `UNKNOWN`)
   - `image_quality_status`: 영상 품질 판정 (`NORMAL`, `WARNING_LOW_BRIGHTNESS`, `WARNING_HIGH_BRIGHTNESS`, `ERROR`)
   - `defect_detection_status`: PatchCore 추론 상태 (`COMPLETED`, `FAILED`, `SKIPPED`)
   - `decision_confidence`: 규칙 기반 판정 신뢰도 (`HIGH`, `UNCERTAIN_DUE_TO_IMAGE_QUALITY`, `NOT_APPLICABLE`)
   - `final_result`: 산업용 종합 검사 판정 (`OK`, `NG`, `REINSPECT`, `ERROR`)
   - `final_reason_code`: 종합 판정 대표 사유 코드 (`ALL_CHECKS_PASSED`, `PRODUCT_ANOMALY_DETECTED`, `IMAGE_QUALITY_WARNING`, 등)
4. **측정 지표 (Metrics):**
   - OpenCV 밝기 통계: `mean`, `std`, `min`, `max`, `width`, `height`, `channels`
   - 모델 추론 지표: `anomaly_score`, `inference_time_ms`, `decision_threshold` (34.1442), `model_version`
5. **살균된 이벤트 로그:**
   - 타임스탬프, 로그 레벨 (`INFO`, `WARN`, `ERROR`), 스테이지 (`init`, `load`, `analyze`, `inference`, `decision`, `complete`), 이벤트 코드, 살균된 메시지

### 3.2 엄격 금지 데이터 (Strictly Prohibited Fields)
아래 항목은 어떠한 경우에도 Agent에게 전달되거나 도구 응답, 프롬프트에 포함되어서는 안 됩니다.

1. **평가 정답 및 레이블:**
   - 실제 정상/불량 정답 (Ground Truth Labels)
   - 원본 결함 클래스명 (`broken_large`, `broken_small`, `contamination`)
   - Ground Truth 이상 영역 마스크 및 결함 좌표
   - `evaluation_answers.json`, `bottle_image_mask_pairs.json`
2. **테스트 시나리오 및 합성 오류 주입 정보 (T03 누출 방지):**
   - **T03의 합성 조도 저하 주입 사실 및 조작 배율(0.6x 등)은 오프라인 평가 하네스 전용 정보입니다.**
   - 운영 Agent 프롬프트, 도구 출력, 컨텍스트에 합성 주입 사실이나 조작 파라미터를 절대 제공하지 않습니다.
   - Agent는 테스트 정답을 미리 알고 사후 해설하듯 설명해서는 안 되며, 오직 검사 데이터(`mean=81.24`, `image_quality_status=WARNING_LOW_BRIGHTNESS`)만을 객관적으로 보고해야 합니다.
3. **시스템 내부 경로 및 인프라 정보:**
   - Windows 드라이브 절대 경로 (`C:\...`) 및 Linux 컨테이너 경로 (`/app/...`, `/tmp/...`)
   - 원본 MVTec 데이터셋 폴더 구조 (`dataset/bottle/test/...`)
   - 모델 체크포인트의 서버 로컬 절대 파일 경로
4. **비밀정보 및 인증 토큰:**
   - Gemini API Key, Google Cloud 서비스 계정 키, 환경변수 파일(`.env`)
5. **미가공 시스템 에러:**
   - Python Exception Stack Trace, 내부 프레임워크 덤프

---

## 4. Agent 보고서 작성 및 진단 원칙 (AGENTS.md 규칙 준수)

1. **관측·가설·한계의 엄격한 분리 (AGENTS.md 규칙 7):**
   - **관측 (Observation):** 검사 지표상에서 실제로 측정된 수치만 기술합니다 (예: "영상 평균 밝기가 81.24로 정상 기준치 하한인 125.0보다 낮게 측정됨").
   - **가설 (Hypothesis):** 측정치에 기반한 추정 원인은 가설로만 제시합니다 (예: "조명 장비의 광량 저하, 카메라 노출 설정 이상, 또는 외부 광원 차단 가능성이 있음").
   - **한계 (Limitation):** 조명 고장이나 설비 파손 여부를 확인된 사실로 단정하지 않으며, 현장 점검 필요성을 명시합니다 (예: "현재 시스템의 영상 분석만으로는 실제 물리적 조명 장치의 기계적 고장 여부를 확정할 수 없으며 현장 조명 센서 점검이 요구됨").
2. **테스트 정답 사전 인지 배제:**
   - Agent는 T01, T03, T05, T06의 실제 정답(양품/불량/합성 주입 여부)을 전혀 모르는 상태에서 오직 전달받은 검사 레코드와 이벤트 로그만을 바탕으로 분석합니다.
3. **모델 판정의 한계 명시 (T06 미검출 사례):**
   - 모델 점수가 임계값 이하(`result=OK`)라 하더라도 실제 100% 양품을 의미하지 않으며, 현재 모델의 Recall(50.79%) 한계로 인한 미검출 가능성이 상존함을 진단 보고서의 주의사항으로 포함합니다.
4. **오류 살균 (Sanitization):**
   - 저장소 조회 실패 시 파일시스템 경로나 Traceback을 노출하지 않고, `NOT_FOUND`, `INVALID_ID` 등의 중립적 에러 코드를 반환합니다.

---

## 5. Day 7 Cloud Run 검사 이미지 제공 방식 계획

현재 Docker 구성([Dockerfile](file:///c:/Users/USER/AI-NativeAgent/Project/InspectAgent/Dockerfile), [.dockerignore](file:///c:/Users/USER/AI-NativeAgent/Project/InspectAgent/.dockerignore))은 운영 보안 및 이미지 경량화를 위해 **원본 MVTec 평가 데이터셋 전체(`dataset/`)를 컨테이너 빌드에서 완전히 제외**하고 있습니다.

따라서 검사 이미지가 제공되지 않으면 운영 컨테이너에서 `POST /inspections` 호출 시 이미지를 로드할 수 없어 검사가 실패(`image_quality_status=ERROR`, `final_result=ERROR`)하게 됩니다.

이를 해결하기 위해 Day 7 배포 시 다음 두 가지 방식 중 하나를 확정해야 합니다:

### 5.1 방식 비교

| 구분 | 방안 A: 최소 데모 검사 이미지 번들링 | 방안 B: Google Cloud Storage(GCS) 스트리밍 연동 |
| :--- | :--- | :--- |
| **개념** | 중립 식별자로 명명된 소수의 데모 이미지(예: 5~10장)만 `demo_images/` 폴더로 컨테이너에 포함 | 실제 검사 이미지를 GCS 버킷에 보관하고, 검사 요청 시 스트리밍 다운로드 또는 서명된 URL로 로드 |
| **장점** | • 외부 스토리지 의존성 없이 즉시 자립 구동<br>• 포트폴리오 데모 및 E2E 테스트 검증에 최적<br>• 추가 클라우드 비용 0원 | • 실제 산업 현장의 대용량 이미지 파이프라인과 완벽 부합<br>• 이미지 추가 시 컨테이너 재빌드 불필요 |
| **단점** | • 번들링된 데모 이미지 외의 신규 이미지 검사 불가 | • Cloud Storage 버킷 생성 및 IAM 인증 필요<br>• 다운로드 지연시간 발생 및 스토리지 과금 |

### 5.2 Day 7 배포 전 필수 체크리스트
- [ ] 검사 이미지 제공 방식 확정 (방안 A 데모 번들링 vs 방안 B Cloud Storage 연동)
- [ ] 운영 컨테이너 내 이미지 로드 경로(`DATASET_PATH` 또는 GCS 어댑터) 설정 일치 확인
- [ ] `GET /inspections/images`가 운영 환경에서 유효한 중립 ID 목록을 정상 반환하는지 검증
- [ ] *현재 단계(Day 3.5)에서는 Cloud Storage를 실제로 연결하지 않음*
