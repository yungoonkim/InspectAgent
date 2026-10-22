# A-3-1 Shadow Quality Metrics 구현·격리 통합 검증

작성일: 2026-10-21. **코드 구현·격리 검증 완료. 기본 OFF. 실제 서버 적용·운영 활성화·실촬영 품질 정확도 검증은 미실시이며 A-3-2 승인 대기.**

## 1. 범위와 기존 설계와의 차이

원본 Grab Crop에 대해 mean/P10/P25, 기하 중심·가장자리 평균과 차이, raw/정규화 Tenengrad, Gray 모집단 분산을 계측한다.
기존125~150 품질 범위, PatchCore34.1442, 품질 경고→REINSPECT, 기존 API 응답/JSONL/로그/RIG/수동/Gemini 계약은 변경하지 않는다.
품질 분류나 새로운 warning을 생성하지 않는다. 중앙 사각형은 병 분할이 아니고 가장자리는 배경 정답이 아니다.

이번 승인에 따라 기존 제안에서 다음을 구분했다.
- 검증되지 않은 분모1.0은 **적용하지 않았다**. 아래 정확 정수 분산 및 수치 유효성 계약으로 변경했다.
- 저장 루트는 이번 요청의 `OUTPUT_DIR/quality_shadow_metrics/`를 사용한다. 과거 제안의 quality_observability 디렉터리를 만들거나 이전 데이터를 옮기지 않는다.
- 스키마 `quality-shadow-v1`, 계산 버전 `opencv-original-exact-variance-v1`을 분리해 저장한다. 과거 experimental-v1 설계 결과를 자동 변환하지 않는다.
- 단일 daemon 계산 스레드와 대기1개를 사용한다. hard 계산 timeout/계산 프로세스 강제중단은 구현하지 않았다. 유한 shutdown 대기와 작업 유실 한계는 아래에 명시한다.

## 2. 변경 파일

### 신규 런타임 모듈
- `backend/quality_shadow_metrics.py`: 검증된 PNG/원본 픽셀 측정, 버전·수치·상태 검증.
- `backend/quality_shadow_store.py`: 별도 불변 Sidecar, 스레드/OS lock, exclusive hard-link 발행.
- `backend/quality_shadow_worker.py`: 계산1/대기1, 중복·포화 차단, 예외·종료 상태 카운터.

### 기존 파일 최소 수정
- `backend/config.py`: Pydantic/Fallback 양쪽에 QUALITY_SHADOW_ENABLED 기본false만 추가. 사용자의 Gemini 설정은 보존.
- `backend/grab_inspection.py`: 선택적 worker 주입, 새로운 검사 commit 성공 이후에만 Shadow 예약.
- `backend/main.py`: OFF를 존중하는 worker 생성/유한 종료 연결. 기존 검사 응답 모델·라우트 변경 없음.

### 신규 검증·보고 파일
- `scripts/run_quality_shadow_tests.py`
- `tests/quality_shadow_helpers.py`
- `tests/test_quality_shadow_metrics.py`
- `tests/test_quality_shadow_store.py`
- `tests/test_quality_shadow_worker.py`
- `tests/test_quality_shadow_integration.py`
- 이 문서. 기존 A-1/A-2/A-3 문서·실험·테스트는 수정하지 않았다.

## 3. OFF/ON과 post-commit 연결

| 설정/상황 | 동작 |
|---|---|
| QUALITY_SHADOW_ENABLED 미설정/false | worker 생성 없음, Sidecar 디렉터리/계산/예약 없음. 기존 검사 그대로 |
| 격리 테스트에서 true | lifespan에서 worker 생성, 실제로 새 완료 검사가 commit된 뒤 비차단 예약 |
| 동일 Capture의 멱등 재응답/기존 검사 조회 | 기존 record를 반환할 뿐 신규 작업 예약 안 함 |
| 원 검사·로그·RIG commit 실패 | 원래 오류/상태 유지, Shadow 예약 안 함 |
| 모델 실패/미완료 등 completed(record)=false | Shadow 예약 안 함 |
| Shadow 계산/입력 확인/저장/예약 실패 | 원래 검사 결과와 응답 불변, 전용 카운터 또는 정제된 로그만 남김 |

연결 순서: 기존 세션/CSRF/소유권·Capture 검사 → 원본 ROI Crop 저장 → 기존 품질·모델·판정 → 검사/이벤트 저장 → RIG commit → 신규 operation 실행 여부 확인 → ShadowJob 예약.
ReinspectionStore.execute가 기존 record를 반환하는 경우도 있으므로 callback이 이번 요청에서 실행됐는지를 별도로 추적한다. RIG의 상태·횟수·원래 저장 순서는 변경하지 않는다.

job은 검사 레코드의 깊은 복사와 서버 내부 loader를 사용한다. worker가 기존 authorize_record로 영속 매니페스트 owner/image_id/hash를 검증한 바이트를 로드한 뒤 PNG header/hash/해상도/dtype/채널을 다시 검증한다.
Source는 inspection_id/image_id/crop_sha256/원본 폭·높이다. 임의 파일 경로나 클라이언트가 제공한 Shadow 출처를 받는 API는 없다.
계산은 이미 저장된 영속 Crop만 사용하며 CaptureStore 세션 발급·TTL cleanup·새 Grab을 호출하지 않는다.

## 4. 원본 픽셀 계산과 분모 정책

- BGR uint8, PNG 원본 해상도, 폭3~1920/높이3~1080. PNG 최대16MiB와 header 크기 확인 후 decode한다. 운영 Grab 크기/품질 제한은 바꾸지 않는다.
- BGR2GRAY uint8, 리사이즈·패딩·노출 보정·모델 전처리 없음. ImageView600×600과 무관.
- P10/P25는 linear percentile. 중심은 `[W//4,W-W//4)×[H//4,H-H//4)`이며 나머지 모든 픽셀은 가장자리다.
- 최소 변8 미만이면 중심/가장자리/차이만 null/TOO_SMALL_FOR_CENTER. 전체 통계와 유효한 미분은 보존한다.
- Sobel3/CV64F/scale1/delta0/BORDER_REFLECT_101의 mean(Gx²+Gy²)를 raw Tenengrad로 쓴다.

분산은 uint8 픽셀의 uint64 합·제곱합을 모은 뒤 **Python 정수**로 `N*sum(gray²)-sum(gray)²`를 계산하고 마지막에 N²로 나눈다. 큰 두 float 모멘트를 빼는 취소 오차를 피한다.
유효 크기에서 정수 합·제곱합은 uint64 범위 안이고 곱셈·뺄셈은 Python 정수이므로 overflow를 피한다.
정규화는 raw/variance다. 분산0은 null/ZERO_GRAY_VARIANCE다. 양의 분산이라도 유한하지 않으면 null/NON_FINITE다.

비상수 정수 픽셀 N개의 최소 가능한 양의 모집단 분산은 `(N-1)/N²`다. 한 픽셀만 다른 Gray code를 가지는 경우에 달성된다.
그보다 작은 양의 분산은 이 입력 계약에서 해석할 수 없으므로 null/NUMERICALLY_UNRESOLVED_VARIANCE로 처리한다. 분모에 epsilon을 더하거나 경험적 노출 threshold를 적용하지 않는다.
따라서 8×8 절반0/절반1의 분산0.25도 **계산 가능**하다. 160×160 중 한 픽셀만1 code 다른 분산 약0.00003906도 유한하게 계산한다.
이는 디지털 수치 안정성이지 센서 노이즈·저대비 영상에서 선명도 해석이 신뢰된다는 뜻이 아니다. 미세 픽셀 변화만으로도 normalized 값이 생기므로 실촬영 품질 분류에 사용하지 않는다.

각 지표는 독립적으로 실패를 처리해 다른 유효 값을 보존한다. Sobel 예외 시 raw=null/METRIC_EXCEPTION, normalized=null/DEPENDENCY_UNAVAILABLE이며 mean/분산 등은 유지한다.
NaN/Inf 계산은 해당 값 null/NON_FINITE, 불법 저장값은 Pydantic 및 allow_nan=False로 거부한다.
전체 계산 예외는 검증된 source에 한해 전부 null/COMPUTATION_FAILED, NOT_MEASURED로 저장한다. 실패 계산 시간도 실제 perf_counter 차이를 기록한다. 입력 자체를 검증할 수 없으면 결과를 만들지 않고 job_failed 카운터로 관측한다.

## 5. Sidecar 저장 구조와 불변성

```text
OUTPUT_DIR/quality_shadow_metrics/
  quality-shadow-v1/
    opencv-original-exact-variance-v1/
      INSP-xxxxxx/
        <원본 Crop SHA256>.json
        publication.lock
```

JSON 루트는 quality_observability이며 schema_version/algorithm_version/mode=SHADOW_ONLY/source/processing/metrics/status/measured_at/elapsed_ms를 포함한다.
상위 상태는 MEASURED / MEASURED_PARTIALLY / NOT_MEASURED, leaf는 value/unit/status/reason이다. 기존 quality_status/final_result/judge_verdict 필드를 넣으면 거부한다.
단위·범위·집계 상태·중심 geometry·면적 가중 mean·차이·정규화 관계를 검증한다. JSON 중복 key·손상·다른 identity·NaN/Inf를 거부한다.

동일 키는 버전/계산 버전/검사 ID/image_id/Crop hash/고정 processing이다. 같은 hash라도 다른 검사 ID를 합치지 않는다.
재발행 시 시각·elapsed_ms를 제외한 **실제 계측 내용**이 같으면 기존 파일을 반환한다. 내용이 다르거나 손상됐으면 SHADOW_RESULT_CONFLICT로 중단하며 기존 파일은 그대로 둔다.
worker는 이미 저장된 결과가 있으면 입력 바이트 검증 후 그 결과를 재사용하고 계산하지 않는다. 첫 실패/부분 결과도 불변이다. 자동 재계측·과거 누락 백필을 하지 않는다.

## 6. 원자성·동시성 검증

1. 같은 프로세스의 디렉터리 초기화는 모듈 mutex로 직렬화한다. store instance 내부 RLock도 사용한다.
2. 별도 publication.lock을 Windows msvcrt byte lock/POSIX flock으로 비차단 잠근다. 기존 RIG/Vision lock이나 state.json을 재사용하지 않는다.
3. 같은 디렉터리에 exclusive TMP를 쓰고 flush/fsync/close한 뒤 `os.link(TMP,final)`로 완성 파일을 **덮어쓰기 없이** 발행한다.
4. target 존재 시 원자 연산이 실패하고 기존 내용을 검증한다. os.replace/rename 덮어쓰기 fallback은 없다. 하드링크 미지원/권한/디스크 오류는 명시적 저장 실패다.
5. 자신의 TMP만 정리하며 기존 완성 파일/다른 TMP/운영 자료는 삭제하지 않는다. 중간 실패 파일을 최종 JSON으로 노출하지 않는다.

현재 Windows 임시 파일시스템에서 실제 hard-link 생성/samefile 확인/기존 target 거부, 별도 Python 프로세스의 OS lock 충돌과 해제 후 저장을 검증했다.
스레드 동시 동일 키/다른 ID 저장, target이 발행 직전 생기는 경합, 다른 내용 충돌, 부분 JSON 쓰기/permission/ENOSPC/미지원 link 오류를 검증했다.
다른 volume·네트워크 파일시스템·Cloud Run 저장·전원 장애 내구성까지 보장하지 않는다. 같은 파일시스템 내 원자적 보임과 power-loss 영속성은 별개다.

## 7. Worker 용량·장애·종료

- active/reserved1개 + pending1개, 총2개. 실제 계산은 한 daemon thread에서 순차 실행한다. 무제한 executor queue를 사용하지 않는다.
- 세 번째는 False/queue_full, 진행 중 같은 key는 False/duplicate. 수락 실패를 원 검사 응답 오류로 전파하지 않는다.
- snapshot()은 내부 상태와 accepted/published/existing_reused/computation_failed/job_failed/저장 오류/queue_full/shutdown 관련 카운터를 제공한다. 새 외부 상태 API는 만들지 않았다.
- 원 계산 실패는 실패 Sidecar로, 저장 실패·해시/입력 거부는 카운터로 구분한다. 예외 원문·이미지·owner·키를 로그에 넣지 않는다. 정제된 로그 handler 자체가 실패해도 원 검사는 보존한다.
- close는 새 수락을 중단하고 pending을 버린다. 진행 중 계산이 종료됐어도 close가 확인되면 결과를 폐기한다. 이미 발행에 들어간 작업은 원자적으로 완료될 수 있다.
- 기본 join 대기는1초다. 살아 있으면 False 및 shutdown_unfinished를 남긴다. **native 계산 강제 취소/hard timeout은 보장하지 않는다.** 원래 서버/Chrome/다른 프로세스를 종료하지 않는다.
- daemon과 메모리 queue는 프로세스 종료 시 작업을 잃을 수 있다. 테스트 전용 자식 Python이 수락 후 스스로 종료하는 시험에서 Sidecar가 생성되지 않는 것을 확인했다. 이 시험은 운영 서버 종료가 아니다.
- 여러 Uvicorn worker에 걸친 전역 계산 용량/세션 상태는 지원하지 않는다. 최초 활성화는 기존 Uvicorn workers1 정책을 유지해야 한다.

## 8. 최종 회귀와 중간 실패

최종 증거 폴더: `data/outputs/quality-shadow-validation/a3-1-tests-20261021-05/`

| 범위 | PASS | FAIL | SKIP |
|---|---:|---:|---:|
| 신규 수학/PNG | 25 | 0 | 0 |
| 신규 Sidecar | 17 | 0 | 0 |
| 신규 worker | 8 | 0 | 0 |
| 신규 post-commit/설정/lifespan 통합 | 15 | 0 | 0 |
| 기존 A-1/A-2/설계안 합성 검증 | 64 | 0 | 0 |
| 기존 Grab 검사 | 35 | 0 | 0 |
| 기존 RIG/수동 확인 | 46 | 0 | 0 |
| **합계** | **210** | **0** | **0** |

기존 설계안27개는 이전 Draft를 검증하는 역사적 테스트다. 이 통과가 운영 모듈에 분모1.0을 적용했다는 뜻은 아니다. 실제 새 계산의 양의 분산 경계는 신규 테스트가 별도로 확인한다.
격리 Fake inferencer와 ASGI TestClient로 실제 서버의 판정·저장·API 경로를 통과했으나, 실제 브라우저/실모델 E2E는 아니다.
정상 품질의 모델OK/NG, 품질 경고의 REINSPECT, 이미지 load 실패 ERROR, 모델/로그/RIG 저장 실패 및 중복 재응답을 검증했다.
ON 상태의 계산/저장/예약 실패 뒤 원 검사 JSONL·이벤트·RIG 바이트가 그대로인지 확인했다. OFF에서는 worker/계산/Sidecar 생성이 없다.

중간 산출물은 삭제하지 않았다.
- `a3-1-tests-20261021-01`: 201 PASS/3 FAIL. 테스트의 read_text 기본cp949가 한국어 UTF-8 기록을 읽지 못했다. 테스트에 encoding=UTF-8을 명시했다.
- `...-02`: 205 PASS. 당시 추가된 동시 다른 ID 테스트 포함.
- `...-03`: 209 PASS/1 FAIL, forbidden_io1. 독립 store의 병렬 재귀 mkdir 경로에서 Windows 경로 확인/격리 IO guard가 차단했다. 해당 호출은 실행 전 차단됐고 보호 정책은 완화하지 않았다. 같은 프로세스 내 디렉터리 초기화를 공통 mutex로 직렬화했다. guard 내부의 일시적 경로 해석 현상까지 확정 진단한 것은 아니다.
- `...-04`: 210 PASS. 이후 실패 결과의 elapsed_ms도 실제 시간을 쓰도록 보완했다.
- `...-05`: **최종210 PASS**, JUnit 약24.04초. safety.json의 forbidden_io/network/real_prediction/real_load/real_gemini_api_calls 모두0, 경고0.

검증 파일은 backend.xml / pytest.log / safety.json / quality-shadow-timing.json이다. git diff --check도 성공했다(Windows CRLF 변환 안내만 있음).

### 계산 시간

최종 합성280×280,30회: **평균2.06ms / P95 2.28ms**.
PNG hash/decode·수학·계약 검증/기본형 직렬화 포함, 디스크·queue/lock 대기·파일 발행 제외다. OpenCV5.0.0/NumPy2.4.6 환경의 단일 실행 결과이며 생산 SLA나 품질 정확도가 아니다.
기존 A-3의3.73ms는 다른 probe의 과거 측정이므로 개선률로 해석하지 않는다.

### 재실행

```bat
conda activate vision-insight
python -B scripts/run_quality_shadow_tests.py test --output data/outputs/quality-shadow-validation/a3-1-new-unique-run
```

출력은 존재하지 않는 새 경로만 허용한다. 기존 safe_regression_backend.run_tests의 네트워크·운영 쓰기·모델 차단과 임시 경로 주입을 재사용하지만 전체 안전 러너/Chrome 복구는 실행하지 않는다.
Settings의 .env 로드는 테스트 프로세스 안에서 차단한다. 테스트용 환경변수 변경은 실행 중 서버/사용자 CMD/.env를 변경하지 않는다.

## 9. 보호 자료와 서버 상태

수정 전 기준선 `data/outputs/quality-shadow-validation/a3-1-20261021-02/protection-before.json`:561파일, 읽기 미검증0.
최종 `protection-after-acceptance-tests.json`: 예기치 않은 변경0, 사용자 config AST 보존=true, A-2 Crop **60/60 해시 불변**.
기준선에 있던 세 승인 파일(config/main/grab)만 코드 변경됐고 새 런타임 모듈3개가 추가됐다. 나머지 기존558파일은 불변이다. 전체 판정·모델·영상·검사/이벤트·RIG·Gemini·Capture/Crop/Anomaly 자료를 해당 snapshot 범위에서 확인했다.
최초 sandbox snapshot의252개 PermissionError는 PASS로 취급하지 않았다. ACL을 변경하지 않고 승인된 읽기 전용 검증으로 완전한 기준선을 별도 생성했다.
이전 A-3의638파일과는 범위가 다르다. 이번561개는 기존 snapshot([]) 범위이며 A-1/A-2 집계 보고서 전체를 추가 해시한 숫자가 아니다.

시작 점검에서 포트8000 PID21796은 Uvicorn/backend.main, reload=false였고 부모도 reload 감시 프로세스로 식별되지 않았다. 서버를 종료·재시작하거나 요청하지 않았다.
**디스크 코드 변경과 실행 프로세스 적용은 다르다.** 기존 서버의 메모리 코드/환경을 hot patch하지 않았고 새 코드 활성화 상태를 실제 요청으로 확인하지 않았다.
운영 Google/이미지 전송/Grab/Capture/실 PatchCore/DB 연결/서버 조작은0회다. 별도 테스트 프로세스는 임시 저장소·합성 PNG만 사용했다. PostgreSQL 내용 불변성은 직접 검증하지 않았다.

## 10. A-3-2 전 남은 위험·승인·롤백

1. **기본 OFF를 유지한다.** 운영 ON은 별도 승인이다. 설정·실행 스크립트·.env를 이번에 활성화하지 않았다.
2. 실제 적용 직전에 PID/포트/reload/최신 Capture 보존 상태를 다시 확인한다. 재시작은 사용자가 직접 승인·실행하며 현재 임시 PNG가 과거 백업에 있다고 가정하지 않는다.
3. CaptureStore는 종료/초기화/TTL cleanup에서 임시 PNG/세션 등록을 잃을 수 있다. Shadow는 이 정책을 바꾸거나 세션·owner를 복구하지 않는다.
4. 실제 출력 volume의 하드링크/권한·여유 공간을 별도 허용된 경로에서 검증해야 한다. 이번 Windows 임시 FS 검증을 모든 배포 저장소 보장으로 확대하지 않는다.
5. 비내구 queue·soft shutdown·native hang 시 active 점유 위험을 승인받아야 한다. hard timeout/내구 queue/여러 HTTP worker/Cloud Run 영속 저장은 별도 작업이다.
6. 실제 촬영 품질 라벨·노이즈·스케일별 유효성은 미검증이다. 계측을 판정/Agent/UI evidence에 반영하는 승인과는 별개다.
7. rollback은 QUALITY_SHADOW_ENABLED=false로 신규 예약을 끄고 사용자 승인 후 설정을 반영하는 방식이다. 기존 Sidecar·Crop·JSONL·RIG를 삭제하거나 Git restore/reset으로 사용자 변경을 되돌리지 않는다. 실행 설정은 캐시될 수 있으므로 즉시 hot 변경을 보장하지 않는다.
8. 원자적 파일 보임은 확인했지만 전원 장애 후 durability·임의 로컬 공격자에 대한 완전한 FS 보안·모든 Windows 배포 환경은 미검증이다.

**A-3-1 구현·격리 수락 검증은 완료. 실제 운영 활성화는 수행하지 않고 A-3-2 승인을 기다린다.**
