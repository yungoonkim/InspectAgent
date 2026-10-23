# VisionInsight 개선 이력

- 기준 발표일: **2026-10-20**
- 표준 이력 문서 설정일: **2026-10-22 (KST)**
- 관리 규칙: 프로젝트 루트 `AGENTS.md`의 「개선 이력 관리」

## 1. 발표 기준선과 기존 이력 보존

기존 상세 문서는 [VisionInsight_개선_변경이력.md](VisionInsight_개선_변경이력.md)이다. 기존 파일을 이동·이름 변경·수정하거나 내용을 중복 복사하지 않고 그대로 보존한다.

- **고정 발표 기준선:** 기존 문서의 「1. 2026-10-20 발표 당시 기능 — 기준선」을 원문으로 유지한다.
- **기존 날짜별 기록:** 기존 문서의 「6. 날짜별 변경 이력」을 유지하고, 이후 확인된 변화는 아래에 새 항목으로 누적한다.
- 원문에 기록된 과거 상태는 당시 기록이다. 이후 구현·검증에 따른 상태 변화는 후속 항목으로 구분하며 소급 수정하지 않는다.
- 발표 자료나 기존 보고서만으로 발표 당일의 코드 스냅샷·실호출 상태를 새로 입증하지 않는다. 근거가 불명확한 내용은 완료로 보완하지 않는다.

발표 이전 회귀 수치인 Backend 567 PASS / 10 SKIP, Frontend 39 PASS, Chrome CDP 50 PASS, 보호 자료 80개 불변은 `data/outputs/safe-regression/20261018-225800-d19e47a0/`의 **과거 실행 증거**이며 발표 이후 신규 실행 수치에 합산하지 않는다.

## 2. 기록 원칙과 상태

| 상태 | 의미 |
|---|---|
| 구현검증 완료 | 명시한 범위의 구현과 실제 검증 완료. 격리 검증인지 운영 검증인지 반드시 구분 |
| PARTIAL | 구현·검증 일부만 완료되었거나 운영 수락 기준이 남음 |
| 분석 완료 | 읽기 전용 조사·오프라인 분석 완료. 운영 기능 개선과 구분 |
| 설계미구현 | 설계·정책·프롬프트만 준비되고 코드 구현은 미실시 |
| 검증 미실시 | 코드 초안 등이 있지만 관련 테스트를 실행하지 않음 |
| 미확인 | 날짜·실행 여부·결과를 뒷받침할 근거 부족 |

항목에는 실제 수행 날짜, 변경 전후, 수정 파일, 검증 방법·결과·증거, 적용 여부 및 남은 한계를 기록한다. 기존 기록은 삭제하지 않는다. 명시적인 읽기 전용 요청에서는 이 문서를 갱신하지 않고 추가 예정 내용을 보고한다.

## 3. 날짜별 후속 기록

### 2026-10-21 — Shadow Sidecar 버전 필수화 검증

- **변경 전:** 스키마·알고리즘 버전 누락을 기본값으로 보완하는 문제가 있었다.
- **변경 후:** 누락·잘못된 버전을 거부하고 내부 정상 생성 경로에서는 두 버전을 명시한다.
- **수정 파일:** `backend/quality_shadow_metrics.py`, `tests/test_quality_shadow_versions.py`, `tests/test_quality_shadow_integration.py`.
- **검증:** 기존 기록 기준 **235 PASS / 0 FAIL / 0 SKIP**. 이번 문서 설정 작업에서 재실행하지 않았다.
- **근거:** [버전 검증 수정 보고서](../a3-2-quality-shadow-version-validation-fix.md), `data/outputs/quality-shadow-validation/a3-2b-regression-20261021-01/backend.xml` 및 `safety.json`.
- **상태:** 버전 수정·격리 검증 완료. **A-3-2 전체 상태는 PARTIAL 유지**.
- **한계:** 격리 회귀 통과를 모든 운영 수락 기준의 완료로 확대하지 않는다. 실제 검사 `INSP-001741`의 연결 검증과 UI/F5·Worker 운영 미검증 항목은 기존 보고와 구분한다.

### 2026-10-22 — 신규 3단계 검사 프로세스 Phase 1

- **변경 전:** RIG의 수동 판정이 정상 완료 검사 3회 조건에 결합되어 있었다.
- **변경 후:** 신규 RIG에 `workflow_policy="judge-assisted-v1"`을 명시하고, 정상 완료 검사 한 건 이후 Judge 보조 검토와 작업자 확인을 지원한다. 기존 RIG는 기존 정책을 유지한다.
- **수정 파일:** `backend/config.py`, `backend/reinspection_store.py`, `backend/grab_inspection.py`, `backend/main.py`, `tests/test_judge_assisted_workflow.py`.
- **설정:** `JUDGE_ASSISTED_WORKFLOW_ENABLED=false` 기본값. 운영 활성화·프론트엔드 변경·서버 재시작 미실시.
- **검증 방법:** Miniconda `vision-insight`의 `python.exe -B -` 인라인 실행에서 기존 `scripts.safe_regression_backend.run_tests()`와 추가 운영 데이터 접근 차단을 사용했다. 합성 입력·임시 저장소·Fake Provider 기반이다.
- **검증 결과:** 신규 정책 **53건**과 기존 관련 회귀 **191건**, 합계 **244 PASS / 0 FAIL / 0 SKIP**. 중복 합산하지 않는다.
- **증거:** `C:/Users/USER/AppData/Local/Temp/visioninsight-judge-assisted-phase1-r0ogmdzc/backend.xml`, `pytest.log`, `safety.json`. 문서 설정 시 기존 JUnit의 244건 및 실패·오류·SKIP 0을 읽기 전용으로 재확인했다. 새 테스트 실행은 아니다.
- **안전성:** 해당 실행의 `safety.json`은 운영 보호 영역 I/O·외부 네트워크·실제 모델 로드·추론·Gemini 호출 0을 기록했다. 기존 보호 기준선 454개 중 승인한 소스 3개 외 451개 해시 불변을 확인한 작업 결과가 있다.
- **상태:** **구현검증 완료 — 백엔드 정책 분리·격리 검증 범위 한정**.
- **한계:** 실제 Chrome E2E 및 신규 정책 운영 활성화는 미실시. 프론트엔드는 신규 상태와 `null` 횟수 값을 처리해야 한다. 기존 미완료 RIG를 자동 전환하지 않는다.

### 2026-10-22 — 과거 캐시 안전 확인 및 자동 정리 작업 진행 상태

- **변경 전:** 과거 Chrome CDP 테스트의 프로필·캐시가 누적되었다.
- **확인된 범위:** 과거 Chrome/GPU 캐시 **391개 디렉터리·3,211개 파일·802,646,860바이트**를 재확인했다. Windows Restart Manager 사용 프로세스 조회 결과 0개이며, 독점 읽기·하드링크 검사에서 실패 0개를 확인했다.
- **실제 정리:** **캐시 삭제 0건**. 과거 Vite 캐시도 삭제하지 않았다. 삭제 절차는 준비했지만 실행하지 않았다.
- **코드 초안:** `frontend/scripts/browser_cache_cleanup.mjs`, `frontend/scripts/test_browser_cache_cleanup.mjs`, `frontend/scripts/test_step4_browser.mjs`에 자동 정리와 격리 테스트 초안을 작성했다.
- **검증:** 해당 자동 정리 테스트와 실제 Chrome E2E는 **실행하지 않았다**. 문서 설정 요청으로 작업 범위를 전환했으며 캐시 정리 작업을 자동 재개하지 않는다.
- **상태:** **PARTIAL — 읽기 전용 안전 확인 완료, 정리 미실행, 코드 초안 검증 미실시**.
- **한계:** 캐시 자동 정리를 구현검증 완료 또는 확보 용량 실적으로 표시하지 않는다. 후속 작업에서 코드 검토·격리 테스트·정리 직전 안전 재확인이 필요하다.

### 2026-10-22 — 개선 이력 갱신 규칙 설정

- **변경 전:** 루트 `AGENTS.md`에 표준 개선 이력 경로와 작업 완료 시 갱신 의무가 없었다. 기존 상세 이력은 별도 한국어 파일명으로 존재했다.
- **변경 후:** 기존 지침 뒤에 갱신 규칙을 추가하고 이 파일을 표준 누적 경로로 설정했다. 기존 상세 문서는 원문 참조로 보존한다.
- **수정 파일:** `AGENTS.md`, `docs/progress/visioninsight-improvement-log.md`.
- **검증:** 정적 대조 PASS. 기존 `AGENTS.md` 본문이 그대로 접두부로 보존됐고, 기존 상세 문서·소스·설정 등 14개 파일의 SHA256이 불변이다. Markdown 상대 링크 2개가 유효하며 표준 경로 파일은 1개다. `git diff --check -- AGENTS.md`도 통과했다. 운영 테스트·서버·검사·외부 API 실행은 하지 않았다.
- **상태:** 문서 설정 완료 — 정적 검증 범위. 런타임 기능 구현이나 백그라운드 자동화와 구분한다.
- **한계:** Codex 작업 완료 절차에 대한 지침이며 파일 감시·예약 실행·백그라운드 자동 갱신 프로그램을 설치한 것이 아니다.

### 2026-10-23 — 제출 안정화 Step 2: 실행 안내 및 제출 리소스 계약 보완

- **변경 전:** 루트 README는 `requirements.txt`만 안내해 ML 의존성이 빠졌고 Frontend README는 Vite 기본 템플릿이었다. 프론트엔드 설치·Node 요구사항·제출 리소스 구분이 없었으며 개발자 PC 전용 링크 3개와 오래된 timeout·향후 기능 설명이 남아 있었다.
- **변경 후:** Windows x64/Python 3.11 Conda 준비, `python -m pip install -r requirements-prod.txt -r requirements.txt`, Node 요구사항과 `npm ci`·개발 실행·빌드 절차를 문서화했다. 단일 worker·Capture/자동 reload 위험, 선택적 ROI DB·Gemini, REQUIRED/DEMO_REQUIRED/OPTIONAL/EXCLUDE, 후속 격리 검증 계획을 추가했다. 실행 명령은 안내일 뿐 이번 작업에서 실행하지 않았다.
- **수정 파일:** `README.md`, `frontend/README.md`, `docs/progress/visioninsight-improvement-log.md`만 변경했다. 비밀값 없는 기존 `.env.example`을 재사용하고 새 설정 파일을 만들지 않았다.
- **검증 방법:** `vision-insight`의 `python.exe -B -` 인라인 표준 라이브러리 분석으로 Python AST·정적 import·npm 잠금 선언·문서 링크·리소스 SHA256을 확인했다. `git --no-optional-locks diff --check`로 문서 공백 오류를 점검했다. 분석용 파일·설치 결과·테스트 로그는 생성하지 않았다.
- **정적 검증 결과:** Python 157개 구문 오류·검사 범위 내 로컬 모듈 누락 0, TS/TSX/MJS 68개 상대 import 누락 0. npm 직접 의존성 선언과 lock 일치, Vite 8.3.4의 Node 요구사항은 `^20.19.0 || >=22.12.0`이다. 두 README의 로컬 파일 링크 13개가 유효하며 개발자 PC `file:///` 링크는 상대 링크로 바꿨다. 동적 실행·전체 의존성 설치 가능성을 이 결과로 보장하지 않는다.
- **리소스 검증:** Checkpoint는 Metadata 해시와 일치하고 34.1442를 유지한다. 등록 영상 3개의 SHA256, Grab 검사 86건의 Crop·Manifest·provenance 연결, Heatmap 메타데이터 88개와 NPZ/Overlay 연결, Shadow 3개의 버전·검사·이미지 해시·9개 지표 필드 연결을 확인했다. 지표 재계산·새 검사·추론은 하지 않았다.
- **보존 검증:** 허용 문서 3개를 제외한 기존 Git 추적 파일 423개의 해시가 동일하다. 별도 보호 그룹의 `.env` 2개, 검사 JSONL 2개, Grab 파일 172개, Heatmap 264개, Shadow 3개, RIG 상태·Judge 상태 각 1개, Agent 보고서 10개, 모델 2개, 영상 5개, Capture 디렉터리 파일 2개도 전후 해시가 동일하다. 그룹 간 중복이 있으므로 합계로 고유 파일 수를 주장하지 않는다. 기존 미추적 `.tmp_measurement_regressions/`는 보존했다.
- **보안:** `.env.roi-db.local`의 DB 인증정보·관리 토큰은 제출 제외로 명시했다. 값은 출력·변경하지 않았다. 루트 `.env`의 Gemini 키는 디스크상 비어 있지만 실행 프로세스의 유효 키·설정은 NOT_VERIFIED이다. 테스트의 고정 인증 문자열은 별도 검토 대상이며 현재 토큰과 다르다는 사실만으로 과거 비밀 여부를 단정하지 않는다.
- **발견된 설정 차이:** `backend/config.py`의 Vision timeout 기본값은 30초지만 `VisionReviewService.from_environment()`는 OS 환경변수와 15초 fallback을 사용한다. 모델도 Settings 기본 `gemini-3.8-flash`와 달리 서비스의 OS 변수 미설정 fallback은 `gemini-4-argon`이다. `.env`만으로 동일 적용된다고 안내하지 않고 명시적 CMD 모델·timeout·LIVE 설정을 문서화했다. 모델의 실제 Google 접근 가능성은 미검증이다. 런타임 코드·Gemini 정책은 변경하지 않았다. Diagnostic Agent의 현재 조사 15초·최종 상한 30초·전체 60초 계약도 과거 회차와 구분했다.
- **서버 및 검증 제한:** 점검 당시 Backend PID 26164/8000, worker 1, reload 없음 및 Frontend PID 9196/5173을 읽기 전용 확인했다. 실행 프로세스의 실제 CWD·유효 저장 경로는 확정하지 않았다. 서버 시작·종료·재시작, DB 연결, 패키지 설치, npm 빌드·테스트, 브라우저 조작, Grab·추론·Gemini 호출은 모두 0회다.
- **상태·근거:** **문서 보완·정적 검증 완료 / 제출 실행 재현성은 PARTIAL**. 근거는 변경한 README의 실행·리소스·검증 범위와 이번 작업의 채팅 도구 출력이다. 기존 235/244/1089 PASS 등의 수치를 새 테스트 실행 결과로 사용하지 않는다. **A-3-2는 PARTIAL 유지**다.
- **남은 한계:** 실제 VisionInsight 제출 ZIP은 프로젝트 루트·바로 위 디렉터리에서 확인하지 못했다. ZIP의 비밀정보 제외·필수 파일 포함, 깨끗한 환경의 CPU 휠/전이 의존성 설치·모델 초기화, npm 설치/빌드·API/DB/세션 조회는 NOT_VERIFIED이다. 실제 ZIP 경로와 독립 실행 범위를 승인받은 뒤 후속 검증하며 압축·공유·운영 활성화를 자동 진행하지 않는다.

### 2026-10-23 — 제출 안정화 Step 3: 이전 ZIP 구성 확인 및 독립 실행 보류

- **대상 구분:** 사용자가 `VisionInsight_Source.zip`은 이전 버전이며 향후 압축 형식의 참고용이라고 확인했다. 이를 최종 제출 ZIP으로 간주하지 않았다. 루트 `VisionInsight_Source.zip`과 Downloads의 동명 파일은 16,639,135바이트·SHA256 `2ead48460b4d3ebaddf3e895e9241119d4be52f82aede5e68105c53f9d7738cb`로 동일하다.
- **읽기 전용 확인:** ZIP은 `InspectAgent/` 아래 파일 389개이며 경로 이탈·심볼릭 링크·대소문자 중복 경로·암호화 항목은 검사 범위에서 발견되지 않았다. Backend Python 39개의 정적 `backend.*` 모듈 참조는 ZIP 안에서 해소된다. 압축 해제·실행은 하지 않았다.
- **현재 제출 계약 대비 누락:** Checkpoint, 등록 영상 3개, Dataset 입력 PNG, Shadow 운영 모듈 3개, 표준 개선 이력이 없다. 두 README도 Step 2 보완 전 버전이다. ZIP 안의 이전 main은 Shadow를 참조하지 않으므로 Shadow 모듈 부재만으로 그 구버전의 import 실패를 단정하지 않는다.
- **보안 범위:** `.env.example`은 있으며 비밀값 후보는 빈 키 또는 placeholder다. `.env`, `.env.roi-db.local` 및 파일명 기준의 서비스 계정·ADC·비밀키 후보는 발견되지 않았다. 이것은 내부 모든 파일의 실사용 비밀 부재를 입증하는 전수 검증이 아니다. 비밀값 출력·설정 변경은 하지 않았다.
- **실행 결과:** 최종 제출본이 아직 준비되지 않아 npm 설치·빌드, 새 Python 환경 생성·설치·검사, Backend/Frontend 기동·브라우저/API 연결은 모두 **BLOCKED / 미실시**다. 모델 추론·Gemini LIVE·DB 및 이전 이력 복원도 NOT_TESTED다. 새 ZIP을 임의 생성하지 않았다.
- **변경·보호:** 이번 단계는 이 이력 항목만 추가했다. 기존 Step 2 README 수정과 사용자 제공 ZIP을 보존했으며 기존 서버·패키지·node_modules·Capture·검사·DB·모델·영상은 조작하지 않았다. 증거는 이번 채팅의 ZIP 메모리 분석 결과이며 별도 분석 파일은 생성하지 않았다.
- **상태 및 다음 조건:** **참고 ZIP 구성 분석 완료 / Step 3 독립 실행은 BLOCKED**. 최신 소스·보완 README와 승인된 필수 리소스를 포함하고 실사용 비밀·캐시·기존 ZIP 중첩을 제외한 최종 ZIP을 사용자가 준비·지정한 후 검증한다. 기존 A-3-2 PARTIAL과 과거 회귀 수치는 변경하지 않는다.

### 2026-10-23 — Gemini Judge 설정 회귀 수정 및 신규 3단계 검사 UI 연결

- **변경 전·원인:** HTTP Judge 생성 경로가 `Settings`의 `.env` 설정과 달리 `VisionReviewService.from_environment()`에서 LIVE·모델·timeout을 OS 환경변수로 다시 읽었다. 점검한 기존 Backend PID 26164에는 API 키가 비어 있지 않았지만 세 Vision 설정 변수는 없었고, 디스크 `.env`에는 LIVE 허용·모델·30초가 있었다. 따라서 `VISION_LIVE_DISABLED_APPROVAL_REQUIRED`를 반환하는 설정 경로 불일치가 확인됐다. 비밀값은 출력·변경하지 않았다. LIVE 기본 OFF는 기존 안전 정책으로 유지한다.
- **이전 동작 근거:** 기존 Judge 상태 파일에서 2026-10-20의 성공 LIVE 저장 회차와 모델 `gemini-3.8-flash`를 읽기 전용 확인했다. 예: `INSP-001735`의 COMPLETED/NG, HTTP 200·시도 1회. 과거 성공을 이번 외부 호출 결과로 사용하지 않는다. 과거 실행 당시 환경 전체는 복원하지 않았다.
- **변경 후:** HTTP 경로는 새 `from_settings()`에서 서버의 동일 Settings를 사용한다. OS > `.env` > 기본값이며 LIVE 기본 false, 모델 기본 `gemini-3.8-flash`, timeout 기본 30초다. 기존 직접 호출용 `from_environment()` 계약은 보존했다. 요청별 Crop 전송 동의·세션/CSRF·소유권·SHA256·중복 방지·실패 시 판정 없음은 유지했다. 버튼 disabled를 우회하거나 실제 API 호출을 하지 않았다.
- **신규 정책:** 이전 Phase 1의 백엔드 `judge-assisted-v1`을 재사용하고 신규 그룹 생성 기본값만 true로 바꿨다. 신규 REINSPECT 정상 완료 검사 한 건 이후 작업자 확인을 허용하며 Gemini 미실행·비활성·실패도 차단 사유가 아니다. Gemini OK/NG는 참고 의견이고 REINSPECT/실패도 자동 HOLD를 기록하지 않는다. 작업자가 명시적으로 MANUAL_OK/MANUAL_NG/HOLD를 감사 필드와 함께 저장한다. 시스템 MANUAL_REVIEW_REQUIRED와 작업자 HOLD를 구분한다. `max_attempts=1`로 흉내 내지 않으며 신규 그룹의 두 횟수 상한 필드는 null이다.
- **호환성·UI:** 기존 정책 식별자가 없는 RIG의 3회 정책·미완료 그룹 마무리 경로·검사 이력·Judge/수동 확인 의미를 보존했다. 신규 그룹에는 1/3 안내와 동일 제품 재촬영 체크를 표시하지 않는다. 1차 → 선택적 Judge → 수동 확인 탭 이동은 외부 호출을 하지 않는다. 기존 localStorage 힌트를 자동 삭제하지 않고 새 제품 전환 시 명시적 확인·현재 Capture 소유권 및 미사용 검증을 유지한다. ERROR 복구·중복 Capture 차단·원본 JSONL 확정·Shadow post-commit은 변경하지 않았다.
- **수정 파일:** `backend/config.py`, `backend/vision_review.py`, `backend/vision_review_api.py`; `frontend/src/App.tsx`, `components/{GrabInspectionPanel,InspectionTabs,VisionReviewPanel}.tsx`, `types/reinspection.ts`, `utils/{reinspectionState,visionReviewState}.ts`; `frontend/scripts/test_{grab_capture_recovery,inspection_tabs,reinspection_recovery,reinspection_state,vision_judge_state,vision_review_panel}.mjs`; `tests/test_grab_inspection.py`, `tests/test_judge_assisted_workflow.py`, 신규 `tests/test_vision_review_settings.py`; `README.md`, `frontend/README.md`, 이 이력 문서. 위 frontend 상대 경로는 `frontend/src/` 기준이다. 선행 문서 변경을 보존했다.
- **검증 방법:** 기존 독립 검증용 Python 3.11 환경을 변경 없이 사용하고 `-B` 인라인 실행으로 `scripts.safe_regression_backend.run_tests()`를 호출했다. 추가 감사 훅으로 운영 출력·로그·실사용 DB 설정 접근을 차단하고 합성 PNG·임시 저장소·Fake Provider·ASGI/MockTransport만 사용했다. `node --test --test-reporter=tap`은 19개 모의 테스트 스크립트에 한정했으며 실제 서버/브라우저를 실행하지 않았다. 빌드는 별도 사본과 이전 격리 환경의 의존성 사본으로 `npm run build`를 실행했다. 새 패키지 설치는 없다.
- **최종 결과:** Backend 10개 모듈 **313 PASS / 0 FAIL / 7 SKIP**. Judge 관련 156 PASS, 신규/레거시 RIG·Grab 135 PASS, Shadow 통합 18 PASS, 정적 검사 API 4 PASS/7 SKIP이며 중복 없는 합계다. SKIP은 실제 Checkpoint 적재가 필요한 6건과 빈 격리 저장소의 이력 조회 1건이다. Frontend **145 PASS / 0 FAIL / 0 SKIP**, TypeScript·Vite 빌드 PASS. 최초 확대 Frontend 실행은 변경 전 “1/3 준비” 문구를 기대한 테스트 1건 실패였고 신규 정책 안내에 맞게 기대값을 수정한 후 최종 통과했다. 선행 112건·30건 표적 실행은 최종 합계에 중복 합산하지 않는다.
- **증거:** `C:/Users/USER/VisionInsight_Regression/judge-workflow-20261023_171306_9532cb13/`의 `protected-before.json`, `backend-regression/{backend.xml,pytest.log,safety.json,console.log}`, `frontend-final.tap`, `frontend-build-final.log`. 안전 카운터는 운영 보호 영역 I/O·외부 네트워크·실제 모델 적재/추론·Gemini 호출 모두 0이다. 개발 서버 PID 26164/8000과 Vite PID 9196/5173의 시작 시각이 유지됨을 확인했다.
- **보존:** 기준선 931개에서 승인한 이번 변경 파일만 변경됐고 기존 데이터/모델 510개는 해시 불변이다. 실사용 `.env`·`.env.roi-db.local`, Checkpoint·임계값 34.1442·GV 기준·판정 함수·검사 JSONL·RIG·Crop/Manifest·Heatmap·Shadow·영상·기존 파일명/ID 매핑을 변경하지 않았다. 운영 DB는 연결하지 않아 DB 내용의 직접 불변 검증은 하지 않았다.
- **상태·미검증:** **구현검증 완료 — 최신 코드 및 격리 테스트 범위 / Gemini는 IMPLEMENTED_NOT_LIVE_VERIFIED**. 신규 Retry 정책은 코드·모의 UI까지 검증했지만 실행 중 Uvicorn은 no-reload이며 재시작하지 않아 적용되지 않았다. 사용자가 기존 탭을 닫았다고 확인한 후 Frontend를 수정했다. 실제 Chrome E2E·외부 LIVE·새 검사·모델 추론은 미실시다. 재시작은 Capture/진행 중 작업 확인 후 별도 승인이 필요하다. 실제 API 키를 새 실행 세션에 안전하게 제공해야 하며 기존 프로세스 키의 자동 승계를 가정하지 않는다. 제출 ZIP은 수정하지 않았으므로 최신 변경 반영을 위한 재패키징도 별도 작업이다. **A-3-2 PARTIAL 유지**.

## 4. 이후 기록 양식

```markdown
### YYYY-MM-DD — 변경 제목

- 변경 전:
- 변경 후:
- 수정 파일:
- 검증 방법·명령:
- 결과와 증거:
- 상태 및 적용 범위:
- 기존 데이터·API 호환성:
- 미검증 사항·다음 작업:
```

읽기 전용 조사·설계·프롬프트 작성은 실제 기능 구현으로 기록하지 않는다. 기존 검사 데이터·파일명·ID 매핑·이미지 경로를 이력 정리 목적으로 변경하지 않는다.
