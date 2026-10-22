# A-3-2 Phase 1 — Shadow Metrics 활성화 준비 점검

작성일: 2026-10-21. **Phase 1: PARTIAL / Phase 2: NOT READY(버전 필수 검증 수정 및 별도 실행 승인 필요).**
운영 코드·config·.env·실행 서버 설정은 변경하지 않았다. 실제 활성화·서버 API 요청·실검사·Google 호출은 수행하지 않았다.
이 문서는 Phase 2 실행 승인이 아니며, 아래 명령도 지금 실행하지 않는다.

## 1. 현재 실제 연결

| 항목 | 코드 기준 확인 |
|---|---|
| 설정 | `backend/config.py:45` Pydantic QUALITY_SHADOW_ENABLED default=false. Fallback도199행에서 기본false |
| 값 우선순위 | 설치된 Pydantic Settings의 init 인자 > 프로세스 OS 환경변수 > 설정 파일(.env) > 기본값. 별도 secrets source는 기본값 앞에 위치. Fallback은 OS 환경변수/기본값만 읽음 |
| 설정 캐시 | get_settings는 lru_cache. main 모듈 전역 settings와 lifespan에서 사용하는 객체는 서버 프로세스 내에 캐시됨 |
| worker 생성 | `backend/main.py:59` 부근: AgentRuntime/VideoRuntime 생성 뒤, 기존 모델 pre-load 앞에서 factory 호출 |
| OFF | factory가 None 반환, 계산 스레드·Shadow 디렉터리·작업 없음 |
| 원 검사 저장 | `backend/inspection.py:662` 검사 JSONL →663 이벤트 JSONL. 원자적 단일 트랜잭션은 아님 |
| RIG commit | `backend/reinspection_store.py:219` 이후 저장 검사/종료 로그 확인 → 그룹/횟수/Capture COMMITTED 저장 → return |
| enqueue | GrabInspectionRuntime.inspect에서 execute 정상 반환 후, 이번 요청의 operation이 실행됐고 completed(record)일 때만 예약. 멱등 재응답·과거 조회에는 예약 안 함 |
| 입력 확인 | 내부 loader가 기존 authorize_record의 owner/image_id/매니페스트/hash 검증. worker는 같은 바이트의 PNG/header/hash/해상도/uint8 BGR 확인 |
| 예외 격리 | enqueue/계산/저장 실패는 전용 로그·카운터/실패 Sidecar로 처리. 기존 검사 응답/판정/JSONL/RIG를 바꾸지 않음 |
| 종료 | lifespan에서 worker.close를 별도 thread로 기다린 후 기존 Agent/Capture 종료. close 기본 join1초이며 hard timeout 보장은 없음 |

Pydantic 우선순위는 프로젝트 .env 대신 **합성 설정 파일**로 재확인했다. OS=false가 파일=true를 이기고, 명시적 init=true가 OS=false를 이겼다.
현재 서버의 환경변수나 .env 실제 값은 읽지 않았다. 위 내용은 로딩 규칙이지 실제 서버가 ON/OFF라는 증거가 아니다.
현재 기본 OUTPUT_DIR의 `data/outputs/quality_shadow_metrics/`는 존재하지 않았다. 이것도 다른 OUTPUT_DIR나 메모리 worker 유무까지 입증하지 않는다.

### Gemini 설정 보존

사용자가 의도한 값은 Vision LIVE=true / model=gemini-3.8-flash / Vision timeout30 / Agent final timeout30이다.
현재 소스 기본값은 LIVE=false, 나머지 위 모델/30/30이다. LIVE=true는 기존 사용자 환경설정으로 제공돼야 하며 이번에는 검증·변경하지 않았다.
기존 config.py는 작업 전후 SHA256 동일이다. 실제 .env와 키는 열람·출력·수정하지 않았다.
Shadow 설정/지표는 Gemini 모델·동의·도구·보고서 경로와 연결되지 않는다. AgentRuntime은 lazy SDK 생성 구조이며 Shadow를 켠다고 AI 진단 요청을 보내는 경로는 없다.

## 2. Sidecar 계약과 새로 발견한 차단 문제

```text
<실제 OUTPUT_DIR>/quality_shadow_metrics/
  quality-shadow-v1/
    opencv-original-exact-variance-v1/
      <새 Inspection ID>/<Crop SHA256>.json
```

루트 quality_observability 안에 schema_version/algorithm_version/source/processing/metrics/status/measured_at/elapsed_ms를 저장한다.
source에는 검사 ID/중립 IMG-GRAB ID/Crop SHA256/원본 폭·높이, metrics에는 Mean/P10/P25/중심·가장자리·차이/raw·normalized Tenengrad/Gray 분산9개가 있다.
원본 픽셀·반열린 좌표이며 Resize 없음. status=MEASURED/MEASURED_PARTIALLY/NOT_MEASURED, leaf는 null+사유를 지원한다.
비유한 수치·단위·범위·계산 관계·잘못된 source를 검증한다. 기존 API/Inspection JSONL에는 필드를 추가하지 않는다.

저장은 스레드 mutex와 OS lock 아래 exclusive TMP에 전체 쓰기/flush/fsync/close 후 os.link로 no-overwrite 발행한다.
같은 키/같은 계측 내용은 기존 결과 재사용, 다른 내용/손상은 충돌. 시각·elapsed_ms는 멱등 내용 비교에서 제외한다.
현재 Windows 임시 FS의 하드링크/프로세스 lock 검증은 A-3-1 과거 결과다. 이번 표적 스모크에서 정상 발행·기존 파일 불변을 다시 확인했지만 모든 배포 FS를 보장하지 않는다.

### P0: 버전 누락이 거부되지 않음 — 재현됨

`backend/quality_shadow_metrics.py:62`와63에서 schema_version/algorithm_version이 Literal이면서 **기본값**을 가진다.
ShadowStore.read/publish의 model_validate가 누락 버전을 현재 버전으로 보충하므로 다음4개 검증이 실패했다.

| 조건 | 기대 | 실제 |
|---|---|---|
| 저장 JSON에서 schema_version 누락 | 손상/버전 미확정으로 거부 | 현재 schema 버전으로 보충하여 읽음 |
| 저장 JSON에서 algorithm_version 누락 | 거부 | 현재 계산 버전으로 보충하여 읽음 |
| publish 입력에서 schema_version 누락 | 거부·미발행 | 기본 버전으로 정상 발행 |
| publish 입력에서 algorithm_version 누락 | 거부·미발행 | 기본 계산 버전으로 정상 발행 |

모두 **격리 합성 파일**에서 재현했다. 기존 운영 데이터의 손상을 발견한 것은 아니다.
반대로 검사 ID/Crop SHA256 누락(read/publish4건), 알 수 없는 명시적 버전2건은 정상 거부됐다.
과거210 PASS는 버전 누락 조건을 포함하지 않았다. 이번 FAIL을 과거 결과로 덮지 않는다.

### 최소 수정안 — 이번에는 미실행

우선 권장: `quality_shadow_metrics.py`에서 두 버전 필드의 기본값을 제거해 필수 필드로 만들고, 내부 finish()에서 두 상수를 명시적으로 전달한다.
이렇게 하면 read/publish 둘 다 누락을 거부하고 정상 신규 계측/이미 버전이 기록된 결과의 계약은 유지할 수 있다. 판정/응답 API/기존 파일 변경은 필요하지 않다.
대안은 store의 raw 입력·저장 JSON에서 버전 key 존재를 별도 검사하는 방식이다. producer 기본값과 persisted 계약을 구분해야 한다.
**사용자 수정 승인 후** 새22개 게이트 전부 통과, 관련 저장·계측 회귀를 확인해야 한다. 기존 무버전 파일을 자동 변환하거나 내용을 채우지 않는다.

### 정규화 해석 정정

현재 구현은 저분산을 모두 null로 만들지 않는다. 분산0→ZERO_GRAY_VARIANCE, 비유한→NON_FINITE, uint8 비상수 입력의 최소 가능한 분산 `(N-1)/N²` 미만→NUMERICALLY_UNRESOLVED_VARIANCE다.
분산0.25와 미세한 양의 분산도 수치적으로 유효하면 계산된다. 미검증 하한1.0은 적용되지 않았다. 수치 계산 가능이 실제 선명도/촬영 품질 신뢰성을 뜻하지 않는다.

## 3. 이번 격리 스모크 결과

실행 결과: **18 PASS / 4 FAIL / 0 ERROR / 0 SKIP**, 총22개. A-3-1의210개 전체는 재실행하지 않았다.

| 검증 | 결과 |
|---|---|
| init/OS/합성 dotenv 우선순위 | PASS1 |
| 검사 ID/SHA 누락 거부 | PASS4 |
| 알 수 없는 버전 거부 | PASS2 |
| 버전 누락 거부 | **FAIL4**, 위 차단 문제 |
| OFF 기본값·worker·디렉터리 미생성 | PASS2 |
| OFF/ON lifespan 생성·종료 | PASS2 |
| Fake 검사 OK/NG의 검사·로그·RIG commit 후 접수/Sidecar ID·SHA·mean 일치/원본 기록 불변 | PASS2 |
| 계산/저장 실패 시 원 검사 응답·기록 보존 | PASS2 |
| 계산1+대기1·중복/세 번째 포화 차단 | PASS1 |
| 기존 결과 계산 없이 재사용 | PASS1 |
| Sidecar 발행·멱등·완성 파일 바이트 불변 | PASS1 |

실행 범위는 `selection.json`에 저장했다. ASGI TestClient 및 Fake 모델, 격리 CaptureStore/PNG/JSONL만 사용했으며 실제 서버·실제 영상 Grab에 요청하지 않았다.
테스트 프로세스에서만 기본 Shadow/Vision LIVE를 false로 두고 명시적 테스트 객체에서만 Shadow ON을 모사했다. .env는 테스트 프로세스의 Settings에서 비활성화했다.
ON 실패/미실행 상태를 실제 서버의 결과라고 보고하지 않는다.

재실행(새 고유 출력 폴더, 현재는 버전 게이트 때문에 exit1이 정상적으로 보고됨):

```bat
conda activate vision-insight
python -B scripts/run_quality_shadow_readiness.py --output data/outputs/quality-shadow-validation/a3-2-new-unique-run
```

최종 증거: `data/outputs/quality-shadow-validation/a3-2-phase1-20261021-02/`
- backend.xml:22개,18 PASS/4 FAIL, 약2.42초.
- pytest.log: 실패 원인. 새 테스트의 DID NOT RAISE4건.
- safety.json: forbidden_io/network/real_prediction/real_load/real_gemini_api_calls 모두0, 경고0.
- selection.json: 실제 선택 범위. 이전 `...-01` 실행도 같은18/4이며 보존했다.

## 4. 현재 서버·Capture와 재시작 위험

읽기 전용 OS 점검 시 포트8000 LISTEN, PID21796 python.exe, Uvicorn/backend.main, 명시적 workers1, reload 없음이었다.
실행 중 서버의 환경·메모리 설정/모듈 버전은 직접 확인하지 않았다. 변경된 디스크 코드는 재시작 없이 적용됐다고 단정할 수 없다.
QUALITY_SHADOW_ENABLED를 기존 CMD에 뒤늦게 set하거나 .env 파일을 바꿔도 이미 실행 중인 프로세스와 cached Settings/worker에는 자동 반영되지 않는다. 정상 적용에는 **사용자 관리 재시작**이 필요하다.

현재 존재한 PNG4개(백업 여부는 이번에 확인하지 않음):
- CAP-6df4fef554f84bfaaf96fc100af8ddfa.png —596987bytes
- CAP-9465b84420654e7e96e3b4e673850600.png —596697bytes
- CAP-b637a66957984aac9fae2a90df814afa.png —594642bytes
- CAP-fe3fd93422304f7597e57e65ea0967e6.png —590546bytes

CaptureStore.close는 관리 중 PNG와 메모리 등록/세션을 정리한다. 초기 디렉터리 처리와 bootstrap/authorize의 TTL cleanup도 PNG를 삭제할 수 있다.
mtime만으로 현재 메모리 등록·세션 유효성을 알 수 없다. 이번에는 bootstrap/조회 API를 호출하지 않았고, PNG를 복원·복사·삭제하지 않았다.
재시작 직전의 **그 시점** 목록·해시·외부 백업 포함 여부를 확인하고 누락분은 별도 승인 후 보호해야 한다. 위4개가 이전 백업에 있다고 가정하지 않는다.
영속 JSONL/Crop/Heatmap/RIG/수동/Gemini 기록은 재시작과 별개이나 예전 session 소유권 접근은 자동 복원되지 않는다.
진행 중 Inspector/RIG를 정당하게 마무리할 수 없는 경우 전환을 보류한다. 3회 제한/수동 확인 조건을 조용히 완화하거나 새 세션에 기존 owner를 옮기지 않는다.

## 5. Phase 2 실행 계획 — 아직 승인되지 않음

### 사전 게이트
1. 버전 필수 검증 최소 수정 승인을 별도로 받고 수정·격리 회귀를 통과한다.
2. 실제 OUTPUT_DIR volume의 권한/공간/하드링크 지원과 최신 Capture 보존을 확인한다. 추가 테스트 파일·백업이 필요하면 범위 승인을 먼저 받는다.
3. 사용자에게 서버 재시작, 모델 startup preload, **새 Capture 최대1개·PatchCore 실제 추론 최대1회·신규 Inspection1건**의 정상 기록 추가를 명시적으로 승인받는다. 실패 후 자동 재시도하지 않는다.
4. 기존 기록은 덮어쓰지 않으며 새 검사에 따른 정상 append만 허용한다. Google/이미지 외부 전송은0회이고 별도 승인 없이는 Judge/Diagnostic 실행 버튼을 누르지 않는다.

### 사용자 수동 전환

아래는 **사전 게이트 통과 및 Phase 2 승인 후에만** 실행할 CMD Miniconda Prompt 명령이다.
사용자가 기존 서버 터미널에서 Ctrl+C로 정상 종료한 뒤 같은 비공개 설정 출처를 유지한다. API 키를 set/echo하거나 파일을 다시 만들지 않는다.

```bat
cd /d C:\Users\USER\AI-NativeAgent\Project\InspectAgent
conda activate vision-insight
set "QUALITY_SHADOW_ENABLED=true"
set "VISION_REVIEW_LIVE_ENABLED=true"
set "VISION_REVIEW_MODEL=gemini-3.8-flash"
set "VISION_REVIEW_TIMEOUT_SECONDS=30"
set "AGENT_FINAL_MODEL_TIMEOUT_SECONDS=30"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Gemini4개 값은 사용자가 의도한 값을 보존하기 위해 기재했다. LIVE=true 자체가 실호출 승인은 아니며 이번 검증에서는 Google 호출을 하지 않는다.
기존 GV/PatchCore 설정은 재지정하지 않는다. `--reload`와 `python -m backend.main` 경로는 사용하지 않는다.
startup의 기존 ENABLE_PATCHCORE=true 경로는 모델을 메모리에 로드할 수 있으므로 이 동작도 재시작 승인 범위에 포함돼야 한다.

### 제한적 검사와 수락 기준

| 항목 | 수락 기준 |
|---|---|
| 새 정상 세션 | Chrome 새로고침 후 정상 세션/CSRF/소유권 흐름. 예전 세션/RIG 참조를 강제 복원하지 않음 |
| 실제 검사1건 | 등록 영상(시연은 VID-000003)에서 사용자가 직접 병/프레임/ROI 선택, Grab1회, 검사1회. 결과를 미리 OK/NG/REINSPECT로 정하지 않음 |
| 영속 연결 | 실제 발급 Inspection ID 기준 JSONL·이벤트·Crop·manifest·RIG·Heatmap 확인. 고정 과거 ID를 새 결과로 사용하지 않음 |
| Shadow 파일 | 실제 OUTPUT_DIR 아래 올바른 schema/algorithm/ID/hash 파일1개. publication.lock은 Sidecar JSON 수에 포함하지 않음 |
| 원본 동일성 | PNG SHA256=manifest=검사 provenance=Sidecar source, 크기·image_id·ID 모두 일치 |
| Mean | round(shadow mean_gv,2)=기존 metrics.mean. 다른 신규 값은 유한값 또는 null+정당한 사유 |
| null 사례 | 실제 sample에 null이 없으면 실물에서 해당 실패 분기는 미관찰로 기록. null을 만들려고 이미지/판정 기준을 조작하지 않음 |
| 1차 판정 불변 | 같은 검사 record의 입력 상태/모델 소견으로 기존 determine_final_verdict를 순수 재확인하고 결과/사유 일치. worker 전후 해당 record/로그/RIG 기존 내용이 바뀌면 실패 |
| 중복 없음 | 조회/F5로 재계측되지 않으며 파일 바이트 불변. 검증 목적으로 검사 POST/실추론을 재실행하지 않음 |
| 장애 격리 | 격리된 실패 주입 결과를 근거로 유지. 운영 권한·디스크를 고장내거나 실제 세 번째 검사를 만들어 포화를 유도하지 않음 |

모델/원 검사 자체가 실패하거나 completed 조건이 충족되지 않으면 Sidecar 미생성은 설계상 가능하다. 이를 Shadow 성공이나 입력 품질 정상으로 표시하지 않는다. 추가 검사는 새 승인 후 진행한다.

### 관측성의 한계

현재 Sidecar elapsed_ms는 계산 시간이며 PNG read/decode 전체·queue wait·저장 I/O 시간을 분리해 저장하지 않는다.
worker.snapshot은 프로세스 내부 카운터일 뿐 외부 상태 API나 영속 로그가 아니다. 정상 worker 생성도 별도 startup 성공 로그가 없어 첫 정상 Sidecar 발행으로 간접 확인할 수 있을 뿐이다.
실제 큐 대기·쓰기 지연을 파일 mtime이나 HTTP 시간에서 정확하게 역산하지 않는다. Phase 2에서 별도 계측을 승인하지 않으면 해당 값은 **NOT MEASURED**로 남긴다.
정확한 분리 계측이 필수라면 timestamps/성공 카운터/저장시간의 안전한 진단 추가를 별도 승인받아야 하며 이번에는 구현하지 않았다.

## 6. 롤백·남은 위험·승인

롤백도 사용자 재시작 승인과 최신 Capture 보존이 선행된다. 같은 CMD에서 **다음 명령은 승인 후에만** 사용한다.

```bat
set "QUALITY_SHADOW_ENABLED=false"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

기존 ON 서버는 먼저 사용자가 정상 종료해야 한다. .env에 true가 있어도 같은 CMD의 명시적 false가 우선한다. Gemini 설정·과거 Sidecar·검사·이미지·RIG는 지우지 않는다.
native 계산은 강제 취소되지 않고 종료 중 pending이 유실될 수 있다. 이미 발행 중인 결과는 완성될 수 있다. shutdown_unfinished는 메모리 카운터이고 main은 close의 False 반환을 별도로 영속 기록하지 않는다.
메모리 queue 내구성, hard timeout, 여러 HTTP worker, 네트워크 FS/전원 장애, 실촬영 품질 정확도는 계속 미검증이다.

필요 승인:
- 먼저 **버전 필수화 최소 코드 수정 및 격리 회귀** 승인.
- 그 후 최신 Capture 보호와 사용자 수동 재시작을 포함한 Phase 2 제한 검사1건 승인.
- 정확한 운영 queue/I/O 진단이나 추가 검사/백업/Google 호출은 별도 범위 승인.

**현재는 Phase 2 실행 불가다. 보고 후 중단하며, 어떤 운영 설정도 true로 바꾸지 않는다.**

## 7. 이번 변경·보존 근거

추가 파일은 이 문서, `tests/test_quality_shadow_activation_readiness.py`, `scripts/run_quality_shadow_readiness.py` 및 격리 테스트 산출물뿐이다.
운영 코드10개·기존 보고서/러너·검사 JSONL2개·Capture PNG4개 등18개 작업 전후 SHA256을 비교해 변경0을 확인했다. 전체 운영 자산을 다시 검증한 것으로 확대하지 않는다.
.env는 열람/수정하지 않았고 PostgreSQL은 연결하지 않아 DB 내용 불변성은 직접 검증하지 않았다.
실제 서버 시작/종료/재시작·요청·새 운영 Grab/Capture·PatchCore 로드/추론·Google API·운영 Sidecar 생성은0회다. synthetic 파일에 대한 실패 재현은 격리 폴더에만 남겼다.
