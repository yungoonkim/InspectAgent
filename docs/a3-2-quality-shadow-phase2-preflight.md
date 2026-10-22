# A-3-2 Phase 2 활성화 전 최종 점검

점검일: 2026-10-21(KST). **최종 상태: BLOCKED — 현재 Capture 4개의 외부 보존 확인이 선행돼야 한다.**
버전 수정 및 격리 회귀는 통과했지만 실제 활성화·서버 재시작·실검사는 승인되지 않았다. 이번 변경은 이 문서뿐이다.

## 1. 현재 서버와 Worker

읽기 전용 netstat/CIM 확인 결과:
- 127.0.0.1:8000 LISTEN, PID21796 python.exe, backend.main:app/Uvicorn.
- 명시적 `--workers 1`, `--reload` 없음. 부모PID28268에도 reload 인자 없음. PID21796의 자식 프로세스는 조회 시 없었다.
- 실행 계정 DESKTOP-6NSMR7D\USER. 프로세스 생성 시각2026-10-21 00:49:44 UTC.
- config/main/Grab/계측/store/worker의 현재 파일 수정 시각은01:39~02:20 UTC로 프로세스 생성 이후다.

이는 실행 중 서버에 최신 코드가 적용됐다는 증거가 아니다. 특히 main lifespan은 시작 시 한 번 실행되므로 새 Worker 연결이 현재 서버에서 시작됐다고 볼 수 없다.
실행 중 모듈·설정 캐시·Shadow 스레드의 실제 상태는 **NOT VERIFIED**다. 서버 API, 프로세스 메모리, 비밀 환경값을 조회하지 않았다.
지원되는 hot 활성화 경로는 없다. 사용자 승인 후 정상 재시작해야 최신 코드와 설정을 적용할 수 있다.
현재 CMD에 뒤늦게 set해도 이미 실행 중인 프로세스 환경은 바뀌지 않는다.

## 2. 최신 코드·설정 확인

| 항목 | 확인 내용 |
|---|---|
| 버전 필수 | quality_shadow_metrics.py:62~63의 두 Literal 필드에 기본값 없음 |
| 내부 생성 | finish에서 SCHEMA_VERSION/ALGORITHM_VERSION 명시. 성공·부분·실패 경로 공통 |
| 지원 버전 | quality-shadow-v1 / opencv-original-exact-variance-v1. 누락 자동 보완 없음 |
| 기본 OFF | config.py Pydantic/Fallback 모두 QUALITY_SHADOW_ENABLED=false |
| 우선순위 | Pydantic init 인자 > OS 환경변수 > .env > file secrets > 기본값. 설치된 소스에서 순서 확인. Fallback은 OS/기본값만 사용 |
| 설정 캐시 | get_settings는 lru_cache, main 전역 및 lifespan에서 사용. 호출 시 ensure_directories도 실행되므로 이번 점검에서 호출하지 않음 |
| ON 기동 | lifespan에서 AgentRuntime/VideoRuntime 다음, 기존 모델 preload 전에 factory 실행. true면 전용 계산 스레드1개 생성 |
| OFF | factory가 None 반환, Shadow 스레드·디렉터리 생성 안 함 |
| post-commit | Grab inspect의 ReinspectionStore.execute 정상 반환 후 신규 operation 실행·completed·ON·worker 존재 조건을 모두 확인 |
| 저장 확인 | execute는 검사 레코드·종료 이벤트 확인, RIG/Capture COMMITTED 상태 저장 후 반환. 검사/로그/RIG 전체가 단일 트랜잭션이라는 뜻은 아님 |
| 실패 격리 | enqueue 예외는 정제된 로그, Worker 실패는 전용 카운터/실패 Sidecar. 원 검사 응답/판정 재작성 없음 |
| 기존 계약 | 검사 JSONL/API에 Shadow 필드 추가 없음. GV125~150, PatchCore34.1442, 품질 경고 우선순위와 RIG/수동/Gemini 정책 유지 |

이전 최종 JUnit을 재확인했다: **235 PASS / 0 FAIL / 0 ERROR / 0 SKIP**,26.701초.
증거: `data/outputs/quality-shadow-validation/a3-2b-regression-20261021-01/backend.xml` 및 safety.json.
이번에는 테스트를 다시 실행하지 않았다. 현재 서버에서 통과한 실검사 결과로 표현하지 않는다.

사용자의 Gemini 설정은 변경하지 않았다. 기존 의도값 LIVE=true/model=gemini-3.8-flash/Vision timeout30/Agent final timeout30의 실제 서버 적용 여부는 별도이며 비밀 설정을 열람해 확인하지 않았다.
Shadow 활성화는 Gemini 호출을 예약하지 않는다. 이번 Phase 2 계획에도 Google 요청은 포함하지 않는다.

## 3. Capture 보존 — 현재 차단 요인

현재 원본 폴더: `C:\Users\USER\AI-NativeAgent\Project\InspectAgent\data\outputs\captures\`.

| 실제 파일 | 바이트 | SHA256 |
|---|---:|---|
| CAP-6df4fef554f84bfaaf96fc100af8ddfa.png | 596987 | 126641c3e70b475affc0d7533b02e6f774eab7346b39f0b305fd1a65f14a1c63 |
| CAP-9465b84420654e7e96e3b4e673850600.png | 596697 | 359bb9f2a68bc7762eafff5861c9c5e23f878b304680134ff64093995bae3586 |
| CAP-b637a66957984aac9fae2a90df814afa.png | 594642 | 8143b5c8543aaddc985d0ff106bfec1b3802082568050b9c5141bbd2eac212f9 |
| CAP-fe3fd93422304f7597e57e65ea0967e6.png | 590546 | 785945392c0f7de579aaf4b8b1c93e135e8385b74033f7a385ecc1d3e561c10b |

C:\Users\USER 바로 아래의 다음 기존 백업7개 폴더에서 동명 CAP PNG와 SHA256을 대조한 결과, 현재4개 모두 일치하는 백업을 찾지 못했다.

- VisionInsight_GrabBackup_20261018
- VisionInsight_GrabBackup_Judge_20261019
- VisionInsight_GrabBackup_LivePreflight_20261019_192831_b2d13295
- VisionInsight_GrabBackup_Step11_20261019
- VisionInsight_GrabBackup_Step11_20261019_Incremental_01
- VisionInsight_GrabBackup_Step9_20261018
- VisionInsight_PersistentBackup_P0_20261019

확인 범위 밖에도 백업이 없다고 단정하지 않는다. 원본의 복사·복원·삭제는 수행하지 않았다.

현재 활성 Capture/세션/CSRF/미완료 Inspector·RIG 상태는 **NOT VERIFIED**다. 파일 mtime은 메모리 등록·만료 여부의 증거가 아니다.
사용자는 현재 진행 중 검사/수동 확인 여부와 위4개의 다른 백업 위치를 알려주거나, 새 외부 폴더로 무덮어쓰기 백업·해시 검증을 별도 승인해야 한다.

위험의 실제 코드 근거:
- CaptureStore는 세션과 Capture 등록을 메모리에 보관한다.
- close는 등록 Capture를 제거하고 세션을 비운다.
- marker가 있는 디렉터리의 최초 초기화도 관리 PNG/TMP를 정리한다. 고아 PNG가 남았다고 재시작 후 보존을 보장할 수 없다.
- bootstrap/authorize는 TTL cleanup을 실행한다. 이번에는 이를 유발할 API를 호출하지 않았다.
- 영속 Crop/검사/Heatmap/RIG/Gemini 기록과 임시 Capture는 별개다. 기존 세션 소유권은 재시작 후 자동 복원되지 않으며 owner를 바꿔 우회하지 않는다.

## 4. Sidecar 운영 저장환경

코드 기본 OUTPUT_DIR는 `data/outputs`, 절대 기본 경로는 `C:\Users\USER\AI-NativeAgent\Project\InspectAgent\data\outputs`다.
상대 설정은 PROJECT_ROOT에 결합하며 절대 설정은 그대로 사용한다.
**실행 중 프로세스의 유효 OUTPUT_DIR는 NOT VERIFIED**다. 실제 .env/프로세스 비밀 환경은 열람하지 않았으므로 기본 경로와 실제 설정을 동일하다고 단정하지 않는다.
사용자가 기존 실행 설정의 비밀값을 제외한 OUTPUT_DIR와 새 실행 환경의 동일 경로 사용 여부를 확인해야 한다.

```text
<유효 OUTPUT_DIR>/quality_shadow_metrics/
  quality-shadow-v1/opencv-original-exact-variance-v1/
    <실제 Inspection ID>/<실제 Crop SHA256>.json
```

기본 출력 디렉터리는 존재하며 reparse/link 속성은 보이지 않았다. **기본 Shadow 디렉터리는 없고 그 경로의 Sidecar는0개**다. 다른 OUTPUT_DIR의 부재까지 입증하지 않는다.
C:는 Healthy NTFS, 조회 시 여유 공간1,448,216,236,032bytes(약1.45TB)였다. 디스크 부족의 즉각적 징후는 없지만 quota·향후 변동까지 보장하지 않는다.
기본 출력 부모 ACL은 USER 소유, 상속 활성, USER FullControl 허용이다. 서버 실행 계정도 USER다. **실제 경로의 유효 쓰기·하드링크 생성은 이번에 실행 검증하지 않았다.**
NTFS는 현재 저장 설계와 호환되는 후보이며, 이전235개 격리 회귀에서 Windows hard-link/OS lock을 실제 검증했다. 이를 다른 volume/네트워크 FS/실제 계정의 특정 경로 쓰기 성공으로 확대하지 않는다.

저장은 전용 스레드/OS lock → 같은 디렉터리 exclusive TMP 전체 쓰기/flush/fsync/close → os.link no-replace 발행이다.
최종 파일이 있으면 JSON/버전/source/내용 검증 후 동일 결과만 재사용한다. 다른 identity/버전/내용/손상은 충돌이며 자동 교체·복구하지 않는다.
하드링크 미지원·권한·공간 오류 시 안전하지 않은 덮어쓰기 fallback은 없다. Sidecar 실패는 원 검사 판정을 바꾸지 않는다.
이번에 운영 또는 임시 폴더에 쓰기 시험/Sidecar를 생성하지 않았다.

## 5. 승인 후 활성화 명령 — 지금 실행 금지

선행 조건: Capture 보호 완료, 활성 Inspector/RIG 영향 사용자 확인, 실제 OUTPUT_DIR 확인, **재시작 및 제한 실검사에 대한 명시적 승인**.
기존 서버가 실행 중인 동안 두 번째 Uvicorn을 기동하지 않는다.
사용자가 기존 터미널에서 정상 종료한 뒤 새 Miniconda Prompt에서 기존 비공개 Gemini 설정 공급 경로를 유지하며 실행한다.

```bat
cd /d C:\Users\USER\AI-NativeAgent\Project\InspectAgent
conda activate vision-insight
set "QUALITY_SHADOW_ENABLED=true"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

새 Prompt 세션에만 Shadow 환경변수를 설정하며 .env/config/전역 환경은 수정하지 않는다. Gemini 설정을 다시 지정하거나 키를 echo하지 않는다.
CMD의 OS=true는 .env의 false보다 우선한다. `--reload`/복수 worker/다른 bootstrap 경로는 사용하지 않는다.
기존 ENABLE_PATCHCORE=true이면 startup에서 모델을 미리 로드할 수 있으므로 사용자 재시작 승인에 그 로드도 포함돼야 한다. 이번에는 로드하지 않았다.
단순 ON 설정은 Worker 기동의 정적 조건일 뿐 실제 성공 증거가 아니다. factory 시작 실패는 None/정제된 경고로 격리되므로 첫 정상 Sidecar를 확인해야 한다.

## 6. 첫 제한 실검사 수락 절차

별도 승인 범위: 사용자 재시작 + startup 모델 로드 + **새 Capture 최대1개, 실제 PatchCore 추론 최대1회, 새 Inspection1건의 정상 append**.
Google/이미지 외부 전송/Diagnostic/Judge LIVE 호출은0회로 유지하며 별도 승인 없이는 버튼을 누르지 않는다.

1. 시작 직전 최신 기존 검사·로그·Crop·RIG 기준선을 확인한다. 기존 행을 수정/삭제하지 않는다.
2. 사용자가 정상 새 세션으로 VID-000003에서 병/프레임/ROI를 선택한다. 과거 세션·RIG owner를 강제 복원하지 않는다.
3. Grab1회와 검사1회를 수행한다. 실패해도 자동 재시도·두 번째 검사 없이 보고한다.
4. 실제 새 ID로 JSONL/이벤트/영속 Crop/manifest/RIG/해당 Heatmap을 확인한다. 과거 검사 ID를 새 결과처럼 사용하지 않는다.
5. 같은 ID의 Sidecar1개를 확인하고 source image_id/ID/PNG 바이트 SHA256/매니페스트/provenance/원본 크기를 대조한다. publication.lock은 JSON 결과 수에서 제외한다.
6. `round(shadow.metrics.mean_gv.value,2)`와 기존 metrics.mean의 일치, P10/P25·중심/가장자리·Tenengrad·분산의 유한값 또는 null+사유를 검증한다.
7. null이 실제로 없으면 그 실물 실패 분기는 미관찰로 기록한다. 임의 Blur/밝기 변형·새 경고·강제 판정을 적용하지 않는다.
8. worker 전후 기존 검사 결과/이벤트/RIG 내용이 바뀌지 않는지 확인한다. 같은 모델/품질 상태에서 기존 순수 결정 함수와 최종 판정·사유를 대조할 수 있으나 재추론하지 않는다.
9. 조회/F5/동일 저장 결과 조회로 파일이 변경·증식하지 않는지 확인한다. 중복 검증을 위해 검사 POST를 다시 실행하지 않는다.

실패 주입·큐 포화는 이미 격리 회귀로 검증했다. 운영 권한/디스크를 고장내거나 추가 검사로 포화를 유도하지 않는다.
계측 때문에 기존 판정/응답이 달라지면 실패로 보고하고 추가 검사를 멈춘다. 단순히 Sidecar가 없으면 수락 실패/worker 미기동/저장 실패/미완료 검사 등을 구분하며 성공으로 간주하지 않는다.
elapsed_ms는 계산 시간이고 queue 대기/저장 I/O 분리 시간은 현재 **NOT MEASURED**다. 파일 mtime으로 정확히 역산하지 않는다.

## 7. 롤백 — 별도 재시작 승인 필요

1. 신규 검사 요청을 멈추고 미완료 Worker와 최신 Capture 보호 상태를 확인한다.
2. 사용자 승인 후 기존 ON 서버를 정상 종료한다. pending은 폐기될 수 있고 native 계산은 hard 취소되지 않으며 이미 발행 중 파일은 완성될 수 있다.
3. 같은 비공개 설정을 유지한 실행 Prompt에서 아래를 적용한다.

```bat
set "QUALITY_SHADOW_ENABLED=false"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

명시적 false를 권장한다. `set "QUALITY_SHADOW_ENABLED="`로 제거만 하면 .env의 true가 다시 적용될 수 있다.
실행 중 서버를 둔 채 이 명령으로 중복 기동하지 않는다. Inspector/세션 손실 위험은 활성화 때와 같다.
기존 Sidecar/JSONL/PNG/이벤트/RIG/Gemini 기록을 지우거나 덮어써 되돌리지 않는다. Git restore/reset 롤백도 하지 않는다.

## 8. 남은 위험 및 사용자 결정

| 항목 | 상태/필요 조치 |
|---|---|
| 버전 및 격리 회귀 | PASS, 기존235건 증거 재사용 |
| Capture4개 보존 | **BLOCKED**: 확인한7개 백업 폴더에서 일치0. 다른 백업 위치 확인 또는 신규 백업 승인 필요 |
| 활성 세션/Inspector/RIG | NOT VERIFIED: 사용자 현재 Chrome 작업 상태 확인 필요 |
| 실제 OUTPUT_DIR | NOT VERIFIED: 사용자의 비밀값 제외 설정 확인 필요 |
| 운영 쓰기/hard-link | 미실행: 경로/계정/volume 확인 후 제한된 첫 검사로 관찰하거나 격리 쓰기 시험을 별도 승인 |
| 운영 활성화/새 검사 | 별도 승인 대기, 이번에 실행하지 않음 |
| 큐·종료·내구성 | 계산1+대기1, 메모리 유실 가능, join1초/하드 timeout 미보장. 여러 HTTP worker 미지원 |
| 실제 품질 정확도 | 미검증. Shadow 통계로 OK/NG/REINSPECT를 재판정하지 않음 |

## 9. 이번 작업의 실행 범위

서버 API·운영 설정 변경·시작/종료/재시작·실제 Grab/Capture·모델 로드/추론·Google 호출·DB 연결은0회다.
기존 백업과 Capture는 읽기 대조만 했고 복사/정리하지 않았다. 실제 .env/키/세션 토큰을 열람·출력하지 않았다.
테스트 재실행과 새 운영 Sidecar 생성도0회다. 기존 사용자 변경은 보존했다.
보고서 작성 전후 관련 코드·검사/로그 JSONL·현재 Capture PNG 등13개 파일의 SHA256을 대조해 변경0을 확인했다. 전체 운영 자산이나 DB 불변성을 직접 검증한 것으로 확대하지 않는다.
**점검 결과를 보고한 뒤 중단한다.**
