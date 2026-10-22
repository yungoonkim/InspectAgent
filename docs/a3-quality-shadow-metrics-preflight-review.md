# A-3 Shadow Quality Metrics 운영 적용 사전 점검

작성일: 2026-10-21. **이번 변경은 이 문서 신규 작성뿐이다. 운영 연결·운영 Sidecar 생성·테스트 재실행·서버 조작은 하지 않았다.**

| 점검 | 결론 |
|---|---|
| A-3 설계 안전성 | **PARTIAL**: 계약·기존 합성 검증은 확인. 저장/worker/장애 주입 통합 검증과 사용자 선택은 남음 |
| config.py | **EXPECTED USER CHANGE**: 사용자가 설명한 Gemini 설정 변경과 현재 diff가 일치. 작성 주체를 Git/mtime만으로 입증한 것은 아님 |
| 62/64 불일치 | **RESOLVED**: 최종 신규27 + 기존37 = 64, 중복0 |
| 운영 구현 착수 | 아래 승인 범위를 확정하면 진행 가능. **이 문서는 구현·서버 재시작 승인이 아님** |

기존 `docs/a3-quality-shadow-metrics-design.md`의 역사적 안전 보류·테스트 집계는 보존한다. 현재 해석과 집계 정정은 이 문서를 기준으로 한다.

## 1. config.py diff 및 변경 시점

### 1.1 확인 방법과 결과

읽기 전용 `git status --short`, `git diff -- backend/config.py`, `git diff --cached -- backend/config.py`를 확인했다.
tracked 수정은 config.py 하나이며, 기존 A-1/A-2/A-3 문서·실험·테스트의 untracked 상태는 그대로 보존했다. staged diff는 비어 있다.
config diff는 49줄 추가/11줄 삭제다. 실제 의미 있는 변경은 다음과 같다.

| 항목 | Pydantic Settings | Fallback | 의도와 비교 |
|---|---|---|---|
| VISION_REVIEW_LIVE_ENABLED | 필드 추가, default=false | 환경변수 기본false, 1/true/yes를 true로 해석 | 일치 |
| VISION_REVIEW_MODEL | 필드 추가, default=gemini-3.8-flash | 같은 환경변수/기본 모델 | 일치 |
| VISION_REVIEW_TIMEOUT_SECONDS | 필드 추가, default=30, gt=0 | 같은 환경변수/기본30, 0 이하 거부 | 필드 추가 의도와 일치; **현재 기본은30초** |
| AGENT_FINAL_MODEL_TIMEOUT_SECONDS | 기본15→30, 범위1~30/기존 validator 유지 | 기본15→30, 기존 범위 검사 유지 | 일치 |

그 외는 빈 줄·주석·PORT Field의 여러 줄 포맷 변경이다. PORT의 기존 default_factory 의미는 동일하다.
GEMINI_MODEL 기존 Flash 기본값, Agent TOOL 단계 기본15초, Agent 전체 요청60초 등은 이 diff에서 바뀌지 않았다.
밝기125/150, PatchCore checkpoint/metadata/device, OUTPUT_DIR 및 검사/로그 경로에는 diff가 없다. `backend/decision.py`의 tracked 수정도 없다.
따라서 현재 diff에서 **예상 밖의 임계값·저장 경로·판정 변경은 발견하지 않았다.** Git 밖의 과거 편집 전체까지 없었다는 주장은 하지 않는다.

근거 위치: `backend/config.py:42`, `backend/config.py:51`, `backend/config.py:189`, `backend/config.py:203`.
Pydantic의 프로젝트 .env 참조는 기존 SettingsConfigDict에 이미 있으며, 이번 diff가 .env 로더 자체를 신설한 것은 아니다.
Fallback은 여전히 process environment를 읽는다. .env·키 값은 열람하지 않았고 실제 서버의 적용 값·활성화 상태는 확인하지 않았다.
설정 필드 추가와 모든 소비 경로에서 그 설정이 적용된다는 주장은 구분한다. 이번에는 Gemini 설정 동작을 실행 검증하지 않는다.

### 1.2 해시와 시점의 범위

| 증거 | UTC 시각/의미 |
|---|---|
| 기존 문서가 기록한 당시 config mtime | 2026-10-21 00:29:29.413543; 당시 관측값이며 현재 mtime과 다름 |
| A-3 최초 protection-before.json 생성 | 2026-10-21 00:31:53.705203 |
| A-3 protection-final.json 생성 | 2026-10-21 00:47:18.976569 |
| 현재 config mtime | **2026-10-21 00:48:12.856839**, 위 최종 보호 결과 이후 |

현재 config SHA256: `bad4a81018cf6773654d8f4a3b2a3b3783f58f56480520ffa111c54642d3b36c`.
현재 바이트는 A-3 protection-before.json의 config SHA256과 **불일치**한다.
기존638개 불변 결과는 당시 기준선부터 당시 최종 비교까지의 증거이지 **현재 config까지 동일하다는 증거가 아니다.** 현재 변경은 사용자의 편집 설명과 diff가 일치하므로 EXPECTED로 분류하지만, mtime만으로 편집자나 정확한 변경 내용을 복원할 수는 없다.
다음 실제 구현 직전에는 사용자 변경을 포함한 새 기준선을 승인된 범위에서 수집해야 한다. 이번에는 과거 해시 결과나 config를 덮어쓰지 않았다.

## 2. 테스트 집계 정정 — 재실행 없음

기존 JUnit XML의 testcase를 파일별로 집계하고 `(classname,name)` 중복을 검사했다.

| 파일 | 중간 성공 실행 | 최종 성공 실행 |
|---|---:|---:|
| tests/test_quality_shadow_design.py | 25 | **27** |
| tests/test_quality_candidates.py | 25 | 25 |
| tests/test_quality_baseline_analysis.py | 12 | 12 |
| 전체 | 62 | **64** |
| FAIL / ERROR / SKIP | 0 / 0 / 0 | **0 / 0 / 0** |
| 중복 testcase key | 0 | **0** |

추가2건은 같은 신규 테스트 함수의 parameterized 사례다.

- `test_proposed_variance_floor_has_an_explicit_boundary[1-False]`: 8×8 절반0/절반1 → 분산0.25, normalized=null.
- `test_proposed_variance_floor_has_an_explicit_boundary[2-True]`: 절반0/절반2 → 분산1.0, normalized 계산.

즉 기존37개가 늘어난 것이 아니라 **신규 테스트가25→27로 증가**했다. 기존 최종 보고의 신규25라는 부분만 중간 실행 집계를 잘못 재사용했다. 독립 실행62개와64개를 합산하지 않는다.

증거:
- 중간: `data/outputs/quality-analysis/a3-shadow-design-validation-20261021-tests/unit-tests.xml`, suite timestamp 2026-10-21T09:33:46.666921+09:00.
- 최종: `data/outputs/quality-analysis/a3-shadow-design-validation-20261021-final-tests/unit-tests.xml`, suite timestamp 2026-10-21T09:34:33.056010+09:00.
- 최종 `unit-safety.json`: pytest_exit=0, network_attempts=0, blocked_io=0.
- `a3-shadow-design-validation-20261021-verified/unit-tests-final.xml`은 파싱 불가능한 미완성 XML이다. 같은 폴더의 초기 unit-safety는 exit3/blocked_io1. 이를 최종 PASS에 포함하지 않는다.

**확인된 과거 최종 결과: 64 PASS / 0 FAIL / 0 ERROR / 0 SKIP. 이번 점검의 신규 테스트 실행은0회다.**
테스트는 합성 입력/순수 품질 함수와 Draft 계약 검증이다. 실제 Sidecar·worker·운영 API의 동시성/권한/장애 테스트 통과를 뜻하지 않는다.

## 3. 저장 방식 비교 및 권장안

| 방식 | 동시성·멱등성 | 원자성·복구·호환성 | 판단 |
|---|---|---|---|
| 검사 ID별 불변 JSON | key별 OS lock+스레드 mutex. 기존 파일 검증 후 재사용 | 같은 디렉터리 임시 파일→완성 파일 원자 발행. 손상 범위가 해당 계측에 한정되고 기존 JSONL 불변 | **권장** |
| 별도 append-only JSONL | 전체 파일 쓰기 lock/중복 index 필요. append 한 번으로 항상 원자적이라고 가정 불가 | 부분 마지막 행·중복·조회 index 복구 필요. 중간 손상도 탐지해야 함. 검사 단위 독립 복구가 어려움 | 초기 규모에서 이점 적음 |
| 별도 SQLite 저장소 | transaction+UNIQUE key 활용 가능 | journal/잠금/마이그레이션/백업·복구 대상 추가. 기존 PostgreSQL과는 별개이나 도입 범위 증가 | 규모 증가 시 재검토, 지금 도입하지 않음 |

### 3.1 경로와 불변성

`settings.absolute_output_path / "quality_observability" / "experimental-v1" / inspection_id / (crop_sha256 + ".json")`

`backend/config.py:114`의 absolute_output_path를 사용한다. 상대 OUTPUT_DIR는 PROJECT_ROOT 기준, 절대 경로는 기존 설정을 따른다. 현재 출력 루트를 하드코딩하거나 .env를 따로 읽지 않는다.
내용 루트는 기존 제안대로 `quality_observability`. 필수 identity는 inspection_id/image_id/crop_sha256/원본 폭·높이, version과 processing policy다.
원본 픽셀 좌표·Gray변환·중심 창·Sobel·분모 정책은 버전 내에서 고정한다. **이 중 계산 의미를 바꾸면 새 schema/algorithm 버전 및 새 경로**를 사용하며 같은 파일을 대체하지 않는다.
같은 hash라도 다른 inspection_id이면 별도 결과다. 임의 파일 경로·owner/token을 저장하거나 새 권한의 근거로 사용하지 않는다.

멱등 key는 `(version, inspection_id, image_id, crop_sha256, processing policy)`다. 경로에 없는 image_id/policy도 내용과 반드시 대조하며 불일치하면 충돌로 처리한다.
동일 key의 첫 terminal 결과는 성공/부분 실패/전체 실패 모두 불변으로 보존한다. elapsed_ms/measured_at 차이 때문에 같은 key를 충돌로 만들지 않고, 기존 완성 결과를 반환한다. source/policy가 다르면 덮어쓰지 않는다.
읽기·탭 전환·동일 검사 요청의 재응답·서버 재시작만으로 과거 누락 파일을 자동 재계측하지 않는다. 실패 결과 재측정/백필은 별도 승인·새 attempt/version 계약이 필요하다.

### 3.2 상태와 유효성

- 모든9개 값 유효: `MEASURED`; 일부: `MEASURED_PARTIALLY`; 모두 실패: `NOT_MEASURED`.
- leaf는 `{value,unit,status,reason}`. 실패한 값만 null+명시적 사유로 두고 이미 유효하게 계산한 다른 지표를 보존한다.
- reason은 Draft의 TOO_SMALL_FOR_CENTER / LOW_GRAY_VARIANCE / NON_FINITE / TIMEOUT / MODULE_EXCEPTION을 유지하는 안이다. 새 사유가 필요하면 먼저 계약·테스트에 반영한다.
- `allow_nan=False`, Pydantic finite 검사, 필드별 단위/범위와 집계 상태 검사. 시간은 UTC offset 포함, elapsed_ms도 유한 비음수다.
- 저장 전 normalized=raw/variance 관계, 작은 분모일 때 null, 작은 중심 창일 때 관련 값 null 같은 **필드 간 의미 검증을 추가해야 한다.** 현재 Draft validator만으로 모든 계산 관계가 입증되지는 않는다.
- 신뢰할 검사/source를 확인하기 전 입력 손상·해시 불일치가 발견되면 그 source의 정상 결과 파일을 만들지 않고 별도 정제된 계측 오류를 남긴다.
- 파일 부재/큐 미수락/저장 실패는 `NOT_AVAILABLE`에 해당한다. 파일이 없는데 NOT_MEASURED 결과가 영속 저장됐다고 표현하지 않는다.

독립 생명주기: Capture TTL/수동 판정/세션 종료에 연동해 지우지 않는다. 원본 Crop 삭제·과거 계측 재계산·retention 정리는 이번 도입에 포함하지 않는다. 로컬 OUTPUT_DIR는 Cloud Run 영속 저장 보장이 아니며 배포 저장 계층은 별도 결정 대상이다.

## 4. 원자적 발행·잠금·장애 정책

### 4.1 한 결과를 발행하는 순서

1. 서버에서 검사 레코드·매니페스트·같은 PNG 바이트의 해시·크기·출처를 검증한다. 클라이언트가 경로/정책/판정값을 지정하지 않는다.
2. key를 프로세스 내 thread mutex로 등록하고 bounded queue에 넣는다. 중복 key와 큐 초과는 계측만 수락하지 않는다. 요청 스레드에서 디스크 쓰기 대기를 하지 않는다.
3. 전용 worker가 Shadow 전용 고정 lock 파일의 OS lock을 획득한다. RIG/Vision Judge의 lock/state.json을 함께 쓰지 않는다. lock 파일은 사용 중 교체·삭제하지 않는다.
4. 완성 파일이 있으면 JSON/identity/policy/유한성 검증 후 재사용한다. 충돌·손상은 기존 파일 보존+계측 오류로 중단한다. 서로 다른 worker에서 작업을 받더라도 계산 전 확인부터 발행까지 lock을 유지한다.
5. 완성 파일과 **같은 디렉터리**에 고유 TMP 파일을 exclusive 생성한다. 전체 JSON 직렬화/flush/fsync/close가 성공한 뒤에만 발행한다.
6. target이 이미 있으면 실패하는 원자적 no-replace 연산을 사용한다. 초기 Windows 로컬 파일시스템에서는 `os.rename`의 target 존재 시 실패 동작을 대상으로 검증한다. POSIX의 일반 rename은 대체할 수 있으므로 같은 코드가 안전하다고 가정하지 않는다. 플랫폼별 지원이 없으면 저장을 거부하며 `os.replace`로 우회하지 않는다.
7. 경쟁 중 완성 파일이 먼저 생기면 기존 결과를 다시 검증·재사용한다. 권한/디스크/잠금 실패는 Shadow 진단만 남기고 원 검사 응답/상태를 변경하지 않는다.

`backend/reinspection_store.py:111`의 `_write`는 mutable state.json을 os.replace로 갱신한다. **불변 Sidecar 발행에 그대로 재사용하면 안 된다.** OS lock 패턴은 참고할 수 있지만 새 경로/오류 경계/전용 lock으로 분리한다.
lock 획득은 bounded/nonblocking 정책으로 설계하며 inspection 응답을 무한 대기시키지 않는다. 원자적 보임과 전원 장애 후 물리적 내구성은 별개다. fsync만으로 모든 Windows/네트워크 파일시스템의 power-loss 내구성을 보장하지 않는다.

### 4.2 복구와 실패

| 장애 | 안전한 반응 |
|---|---|
| 중간 종료/TMP 잔존 | 독자는 정규 완성 파일만 읽음. TMP를 자동 승격·완성으로 해석하지 않음. 정리는 운영자 승인 후 별도 수행 |
| 완성 JSON 손상/다른 identity | 해당 계측 조회 오류. 기존 파일 그대로 보존, 다른 이미지/과거 파일을 대신 연결하지 않음 |
| 디스크 부족/권한 거부/잠금 충돌 | 계측 저장 실패/NOT_AVAILABLE. 원 검사 성공을 오류로 바꾸거나 실패를 성공으로 위장하지 않음 |
| 예외 로그도 저장 불가 | 기존 검사 기록을 수정하지 않고 프로세스의 정제된 Shadow 진단으로 알림. 영속 결과 저장 성공 주장 금지 |
| source와 Crop 불일치 | 전송·계측 거부. 원본·매니페스트를 복원/교체하거나 owner를 바꾸지 않음 |
| 원래 검사/이벤트/RIG commit 실패 | 그 원래 오류를 그대로 전파. Shadow를 예약하지 않음 |

Shadow 전용 진단에는 stage/error code/검사 ID 수준의 최소 식별만 허용하고 이미지·키·토큰·owner·개인정보·임의 예외 payload는 넣지 않는다. inspection_logs.jsonl에 계측 오류를 추가해 기존 검사 로그를 변경하지 않는다.
Sidecar와 기존 검사 JSONL 사이의 분산 트랜잭션은 만들지 않는다. post-commit 프로세스 종료로 계측 파일이 없을 수 있다는 한계를 명시하고 다음 검사를 재실행해 채우지 않는다.

## 5. 정규화 Tenengrad 분모 검토

### 확인된 실험 근거

| 입력 | 분산/처리 | 증거 |
|---|---|---|
| 단색 검정0/극저조도1/흰색255 | 분산0, raw0, normalized=null | 기존27개 테스트의 단색 사례 |
| 160×160 중 한 픽셀만1 | 분산 약0.00003906, normalized=null | tiny variance 테스트. 수치는 fixture의 모집단 분산 식으로 계산 |
| 8×8 절반0/절반1 | 분산0.25, normalized=null | 최종 추가 경계 테스트 |
| 8×8 절반0/절반2 | 분산1.0, normalized 계산 | 최종 추가 경계 테스트 |
| 3×3 단색 | 전체 통계 유효, 중심 창 null, normalized=null | 작은 영상·단색 테스트 |
| NaN/Inf 입력·계산값 | 입력 거부 또는 해당 값 null/NON_FINITE, 불법 JSON 거부 | 기존 격리 테스트 |

A-2 저장 CSV60행의 std_gv²를 읽어 확인한 원본 Gray 분산 범위는 **4651.23~7899.44 GV²**, 1.0 미만은0건이다. 새 PNG 계측은 하지 않았다.
따라서 원본60개는 작은 분모 문제의 실데이터 검증 표본이 아니다. gain/blur 합성 비율의 유망함과 분모 하한 최적성은 별개다.

### 권장 계약

1. 원본 uint8 Gray, ddof0의 유한 분산과 Sobel3 raw를 먼저 계산한다. 분모에 epsilon을 더하거나 0을 유효한 normalized 값으로 대입하지 않는다.
2. 분산0: normalized=null/LOW_GRAY_VARIANCE. raw/mean/P10/P25/유효 영역 통계는 유지한다.
3. **분산1.0 GV² 미만도 null로 하는 현재 Draft를 보수적 수치 guard 후보로 유지**하되, 운영 임계값으로 확정하지 않는다. 1 Gray code 미만의 표준편차를 경계로 제안한 공학적 선택이며 실제 촬영 라벨로 보정된 기준이 아니다.
4. 사용자가 이 guard를 승인하면 버전 내에서 고정하고 정확히1.0부터 계산한다. 미승인 상태에서는 운영 연결을 하지 않는다. 향후 변경은 버전 변경 대상으로 한다.
5. 분모/분자/계산 결과가 비유한이면 해당 지표 null/NON_FINITE. shape/dtype 오류는 입력 실패이며 원 검사와 무관하다.
6. 3×3 미만은 계측 입력 거부, 최소 변3~7에서는 중심 관련 값만 null. 크기·스케일·경계 처리 기록 없이 normalized 값끼리 비교하지 않는다.

A-2 helper의 >1e-12 조건과 A-3 Draft의 >=1.0 조건은 다르다. Draft는 A-2 helper를 호출해 불필요한 Laplacian/내부 정규화도 계산한다. 미래 순수 운영 모듈은 이 실험 모듈 전체를 import하지 않고, raw/분산 계산 후 guard를 통과한 경우만 나눗셈하도록 구현해야 한다.
실제 blur·저노출·정상 반사의 구분 임계값/분류 정확도는 계속 NOT VERIFIED다. 신규 지표로 기존 REINSPECT를 해제하지 않는다.

## 6. worker·동시성·서버 안전

정적 실행 경로만 확인했다. **현재 실행 중인 서버 PID/포트/worker 수를 조회·추정하지 않았다.**

- 사용자 명령 `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1`은 worker1, reload 없음이다.
- `Dockerfile`의 최종 명령도 workers1/reload 없음이다. 현재 로컬 서버가 이 설정으로 실행 중이라는 증거는 아니다.
- 반대로 `python -m backend.main`은 `backend/main.py:827`의 __main__ 블록을 실행하며 ENVIRONMENT=local이면 reload=true다. 두 실행 경로를 혼동하지 않는다.
- 최초 도입은 **Uvicorn1 + Shadow 전용 계산 worker1 + 대기1**을 승인안으로 제안한다. 계산 worker는 Uvicorn HTTP worker가 아니며 FastAPI/CaptureStore/모델/비밀 설정을 로드하지 않는다.
- worker1에서도 sync endpoint의 thread pool·동시 HTTP·중복 요청·background 작업이 경쟁하므로 메모리 mutex와 OS lock/원자 발행이 필요하다.
- 다중 Uvicorn에서는 프로세스별 lock/set/queue가 분리된다. Sidecar의 OS lock만으로 CaptureStore의 메모리 세션/등록이나 검사 ID 생성까지 다중 worker 안전해지는 것은 아니다. **worker 수 증가는 이번 승인 범위에서 제외**한다.
- 정상 검사·이벤트·RIG commit 후만 비차단 enqueue. lock/쓰기 대기와 계측 계산은 원 검사 응답 경로에서 분리한다. bounded queue 초과 시 계측만 미수락한다.
- timeout은 soft/hard를 구분한다. wait_for(to_thread())는 OpenCV 계산을 강제 종료하지 못한다. hard 제한이 필요하면 전용 자식 계산 프로세스만 제한·종료하는 정책을 별도 승인받는다. Uvicorn/사용자 Chrome을 종료하지 않는다.
- 기존 합성280×280 P95 3.73ms는 이전 실측이며 이번 재측정값이 아니다. decode/hash/IPC/disk 비용과 배포 호스트 동시 부하는 미측정이다. 기존15/35/255ms 예산도 잠정 제안이며 실측 deadline 보장으로 사용하지 않는다.

`backend/main.py:66`은 종료 시 captures.close()를 호출하고, `backend/capture_store.py:61`은 초기 고아 정리, bootstrap/authorize는 TTL cleanup을 수행한다.
Shadow worker는 이를 호출하지 않고 이미 영속 저장된 검증 Crop 바이트만 사용한다. 재시작/세션 조회로 임시 PNG를 보호하려 하지 않는다.
실제 구현 전에 포트/프로세스/reload 상태를 다시 읽기 전용 확인한다. reload가 있다면 어떤 감시 경로 파일도 승인 없이 수정하지 않는다.
재시작이 필요하면 그때의 최신 Capture 존재·백업을 확인한 뒤 사용자가 직접 실행한다. 이전 백업에 최신 파일이 포함됐다고 가정하지 않는다.

## 7. 운영 구현의 최소 승인 범위

| 대상 | 함수/역할 | 영향 경계 |
|---|---|---|
| 새 backend/quality_observability.py | pure measure/validate, v1 모델 | 원본 Crop 통계만. backend.vision/decision 수정 없음 |
| 새 backend/quality_observability_store.py | identity 검증, key lock, read/publish-no-replace | 별도 OUTPUT_DIR 하위만 생성. 기존 ReinspectionStore._write 재사용 금지 |
| 새 backend/quality_observability_worker.py | bounded admission/계산/timeout/전용 진단 | 모델·Gemini·CaptureStore 미참조 |
| backend/grab_inspection.py:148 | inspect의 execute 정상 반환 후 enqueue | 기존 return/원래 예외/검사 결과 보존. 신규 commit만 예약 |
| backend/config.py | Shadow enabled 기본false 및 승인된 자원 설정 추가 | **사용자 Gemini 변경 유지**, 기존 경로/임계값/timeout 변경 없음 |
| backend/main.py lifespan | Shadow worker 생성·유한 종료 연결 | 자동 서버 재시작 없음. Capture 기존 종료 정책 수정 없음 |
| 신규 격리 tests | 수학·store·worker·Fake 검사 통합 | 임시 저장소/합성 입력, 운영 파일 미사용 |

**예약 흐름:** 기존 owner/session/source 검증 → 원본 Crop 저장 → 기존 품질/모델/판정 → 검사/로그 저장 → RIG commit → 새 commit 여부 확인 → 검증 바이트로 Shadow enqueue → 별도 불변 Sidecar.
execute는 동일 Capture 요청의 멱등 재응답에서도 기존 record를 반환한다(`backend/reinspection_store.py:167`). 단순히 return 뒤 무조건 enqueue하면 과거 검사 백필이 될 수 있다.
따라서 기존 operation callback이 이번 요청에서 실제 실행되어 commit됐는지를 호출자 내부 상태로 구분하고, 기존 record 재반환·조회에는 예약하지 않는 최소 hook이 필요하다. RIG 저장 계약/횟수를 바꿀 필요는 없다.

기존 검사 JSONL/API 응답 스키마는 변경하지 않는다. 초기 계측 저장만 승인 대상으로 삼고 신규 GET/UI/Agent 노출은 별도 단계로 분리하는 안을 권장한다.
나중에 GET을 승인하면 기존 소유권·세션 보호와 검사 ID 연결을 그대로 재사용하고 `docs/inspection-data-schema.md`를 함께 갱신해야 한다.
이 단계에서는 품질125~150, PatchCore34.1442, 기존 reason/final_result/모델 판정/RIG/작업자/Gemini를 어느 경로에서도 변경하지 않는다.

### 구현 후 필수 격리 검증

1. 기존64개 수학/합성 회귀 유지 및 분모·기하·필드 관계 검증 보강. 실이미지 품질 정확도로 보고하지 않음.
2. 임시 PNG/검사/매니페스트에서 source tuple/hash/좌표 일치 및 변경·손상 거부. 원본 파일 불변.
3. 여러 스레드/별도 임시 프로세스의 동일 key 경쟁에서 완성 파일1개, 첫 결과 불변. 다른 ID/이미지 혼입 거부.
4. 임시 파일 중단·동일 target 충돌·invalid JSON·permission/disk/lock 실패를 격리 주입. ACL을 운영 파일에서 변경하지 않음.
5. Fake inferencer의 OK/NG/REINSPECT/ERROR 및 원 검사·로그·RIG 저장 실패를 통과시켜 Shadow enabled/disabled 전후 응답·저장 결과 동일성 확인.
6. worker 예외/timeout/큐 초과·서버 중단 모사·멱등 재응답 시 재계측 없음. 테스트 전용 worker만 정리.
7. source 검증/파일 IO/계산/대기/IPC 시간 분리 측정. 운영 연결 승인 후에도 실제 모델·Google 호출은 별도 승인 대상.

## 8. 롤백·남은 위험·승인 결정

롤백은 Shadow 신규 예약을 끄고 전용 worker를 승인된 정책으로 유한 종료하는 방식이다. 기존 Sidecar/TMP/검사/로그/매니페스트를 삭제·복원·수정하지 않는다.
get_settings의 캐시 및 실행 프로세스 설정 때문에 비활성화에도 사용자 재시작이 필요할 수 있다. hot reload/즉시 반영을 약속하지 않는다. 재시작은 최신 Capture 보존과 사용자 승인이 선행돼야 한다.
Sidecar 저장 장애는 원래 성공한 검사 응답을 바꾸지 않지만 계측은 누락될 수 있다. 검사 파이프라인 자체 장애는 그대로 오류로 유지한다.

남은 미검증:
- Windows 파일시스템별 atomic-no-replace/lock contention/크래시·전원 장애 내구성.
- Sidecar·worker 구현과 프로세스 자원/IPC/실부하, 원 검사 실패와의 통합 격리.
- Draft의 모든 상호 필드 관계 검증, 실제 낮은 대비/실촬영 품질 라벨 및 guard 최적성.
- 현재 서버 상태·프로세스 환경값·DB 내용·실운영 권한. 현재 A-3 코드가 실행 중 서버에 반영됐다는 주장을 하지 않음.

사용자가 승인해야 할 구체적 선택:
1. **저장만 하는 Shadow v1**: 원본 픽셀9개 지표, JSONL/API/판정 불변, 전경 분할 제외.
2. 중심 QUARTER_INSET_MIN_SIDE_8 및 normalized 분모1.0을 **수치적 계산 보류 guard**로 사용할지. 품질 판정 기준으로 사용 금지.
3. 버전·경로·불변 key·첫 terminal 결과 보존·자동 재측정/백필 금지·부분/전체 실패 계약.
4. Uvicorn1/계산 worker1/대기1, 단일 호스트 로컬 저장과 플랫폼별 no-replace 검증. hard/soft timeout 및 전용 계산 프로세스 종료 권한.
5. 위 최소 코드/격리 테스트 범위와 측정 후 deadline 확정. 실제 서버 적용/재시작·최신 Capture 백업·실추론·Google 요청은 **별도 승인**.

**진행 판단: 승인안은 제시 가능하나, 운영 구현·활성화는 아직 미승인이다. 사용자 변경 보존 및 과거 집계 정정은 완료했고, 저장/worker 검증은 구현 단계의 수락 게이트로 남긴다.**

## 9. 이번 작업의 보존·실행 범위

기존 보고서/XML/CSV/config를 읽고 Git diff와 파일 메타정보를 확인했다. 새 실험·테스트·운영 Sidecar·백업 파일은 만들지 않았다.
작성 전후 관련 코드·기존 문서·기존 검증 코드/XML/안전 JSON 등16개 파일의 SHA256 비교 결과 **16/16 불변, 변경0**이다. 이는 전체 운영 자산638개 재검증을 대신하지 않는다.
이번에는 보호 전체 scan/ACL 변경/서버 API/DB 접근을 하지 않았다. 이미지·영상·모델·Capture에 쓰기/삭제 명령을 실행하지 않았다. DB 내용 불변성은 직접 검증하지 않았다.
Google API·신규 Grab/Capture·PatchCore 로드/추론·서버 시작/종료/재시작·Git 변경 명령은 모두0회다.
