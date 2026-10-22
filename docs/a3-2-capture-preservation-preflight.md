# A-3-2 Capture 보호·재시작 전 조사 및 백업 승인안

조사일: 2026-10-21, 데이터 대조 기준04:07 UTC(13:07 KST).
**Capture 보존 BLOCKED / 백업 NOT STARTED / 서버 재시작 불가(보존·세션/RIG 영향 확인 및 별도 승인 전).**
이번 변경은 이 문서뿐이다. 기존 PNG/JSONL/RIG/config/.env, 운영 프로세스는 변경하지 않았다.

## 1. 현재 Capture 4개

파일명에서 확장자 .png를 제외한 값이 Capture ID이며, 검사 provenance와 RIG claim으로 다시 대조했다.
아래는 모두 **전체 프레임1920×480 PNG**다. ImageView에 표시하는 작은 ROI Crop과 같은 파일이 아니다.

| 파일명 | 바이트 | SHA256 |
|---|---:|---|
| CAP-fe3fd93422304f7597e57e65ea0967e6.png | 590546 | 785945392c0f7de579aaf4b8b1c93e135e8385b74033f7a385ecc1d3e561c10b |
| CAP-6df4fef554f84bfaaf96fc100af8ddfa.png | 596987 | 126641c3e70b475affc0d7533b02e6f774eab7346b39f0b305fd1a65f14a1c63 |
| CAP-9465b84420654e7e96e3b4e673850600.png | 596697 | 359bb9f2a68bc7762eafff5861c9c5e23f878b304680134ff64093995bae3586 |
| CAP-b637a66957984aac9fae2a90df814afa.png | 594642 | 8143b5c8543aaddc985d0ff106bfec1b3802082568050b9c5141bbd2eac212f9 |

정확한 절대 경로:
- `C:\Users\USER\AI-NativeAgent\Project\InspectAgent\data\outputs\captures\CAP-fe3fd93422304f7597e57e65ea0967e6.png`
- `C:\Users\USER\AI-NativeAgent\Project\InspectAgent\data\outputs\captures\CAP-6df4fef554f84bfaaf96fc100af8ddfa.png`
- `C:\Users\USER\AI-NativeAgent\Project\InspectAgent\data\outputs\captures\CAP-9465b84420654e7e96e3b4e673850600.png`
- `C:\Users\USER\AI-NativeAgent\Project\InspectAgent\data\outputs\captures\CAP-b637a66957984aac9fae2a90df814afa.png`

| Capture ID | 파일 생성 UTC | 파일 수정 UTC |
|---|---|---|
| CAP-fe3fd93422304f7597e57e65ea0967e6 | 2026-10-20 11:54:03.942332 | 2026-10-20 11:54:03.944314 |
| CAP-6df4fef554f84bfaaf96fc100af8ddfa | 2026-10-20 11:56:16.401447 | 2026-10-20 11:56:16.402458 |
| CAP-9465b84420654e7e96e3b4e673850600 | 2026-10-20 11:56:33.320732 | 2026-10-20 11:56:33.321735 |
| CAP-b637a66957984aac9fae2a90df814afa | 2026-10-20 11:57:16.789209 | 2026-10-20 11:57:16.790211 |

시각은 Windows 파일 메타데이터이며 Capture API created_at/expires_at과 동일하다고 단정하지 않는다.
4개 총2,378,872bytes. PNG 헤더 확인과 읽기 전용 decode만 했고 재저장·재인코딩하지 않았다.

## 2. 영구 Crop 및 검사 연결 — 새로 확인된 사실

**4개 모두 이미 검사에 사용됐고 해당 ROI Crop이 영속 저장돼 있다.** 이전 외부 백업 불일치는 전체 Capture 바이트에 대한 것이며, 영속 ROI까지 없다는 뜻은 아니다.

| Capture 파일 접두 식별 | 검사 ID | 영상/프레임 | ROI(x,y,w,h) | 1차 최종 판정 | 현재 저장 RIG 상태 |
|---|---|---|---|---|---|
| fe3fd934… | INSP-001735 | VID-000003 /26 | 926,122,276,276 | REINSPECT | RETRY_ALLOWED,1/3,남음2 |
| 6df4fef5… | INSP-001736 | VID-000003 /93 | 926,122,276,276 | REINSPECT | RETRY_ALLOWED,1/3,남음2 |
| 9465b844… | INSP-001737 | VID-000003 /163 | 926,122,276,276 | REINSPECT | RETRY_ALLOWED,1/3,남음2 |
| b637a669… | INSP-001738 | VID-000003 /161 | 918,121,299,280 | OK | COMPLETED,1/3,추가 허용0 |

영속 Crop의 절대 기본 디렉터리:
`C:\Users\USER\AI-NativeAgent\Project\InspectAgent\data\outputs\grab_inspection_inputs\`.

| 검사 | 실제 PNG(같은 stem의 .json 매니페스트도 존재) | PNG SHA256 |
|---|---|---|
| INSP-001735 | IMG-GRAB-bbe1ea7338b2411991a20ce25c8ff69e.png | b861aa2b158599e8f54c19603182ec48a7b84fa2743a22c1e22e46af0167498b |
| INSP-001736 | IMG-GRAB-1e79ffd9e7a14fa4a8def138c9060307.png | 5932d4ff8b5cfd3c365b61a6922f7cb9378296f606463ed825ce5b06db03e5b9 |
| INSP-001737 | IMG-GRAB-eb720626627d499ba6fb2061f8b15e30.png | ba59bb2caaa9e09373e7f0b0e2d38578e47642864c3db5bef81eeefefa18f1ed |
| INSP-001738 | IMG-GRAB-73d0f2f8d7ae4be28beeb5616e5b2037.png | fc3b61b031509673a77782883156a621fa664852849d4452084f219d1d8a58b5 |

검증 결과:
- data/inspections.jsonl의 각 ID는1행이며 각각1688~1691행에 대응한다.
- 각 Capture의 실제 SHA256=해당 검사 input_provenance.capture_sha256.
- 각 실제 Crop의 SHA256=검사 crop_sha256=매니페스트 crop_sha256, image_id 일치.
- Capture를 메모리에서 decode한 실제 ROI 픽셀과 영속 Crop의 픽셀은 **4/4 정확히 동일**하다.
- 영상 source_revision은4개 모두 `bcdf19620579a60b4d7211f6cb7e2db948336b240b0ac78114c18bb2359ef7d5`다.
- 각 검사에 이벤트6개가 실제 존재한다: INSPECTION_STARTED, IMAGE_LOADED, ANALYSIS_COMPLETED, INFERENCE_STARTED, INFERENCE_COMPLETED, INSPECTION_COMPLETED.
- 이벤트의 Capture ID 직접 문자열 매칭은 없었으며, 검사 ID를 통해 연결했다.

ROI 외부의 전체 프레임 픽셀까지 영속 Crop에 보존된 것은 아니다. 4개의 전체 PNG와 해시가 같은 Crop 매니페스트도 없었다.
따라서 **검사 ROI 증거는 보존됨 / 전체 Capture 외부 보존은 미완료**로 구분한다. 기존7개 외부 백업 대조 결과는 직전 phase2-preflight 보고서를 재사용했으며 새로 백업하지 않았다.

## 3. 세션·메타데이터와 복원 한계

현재 Capture 폴더에는 PNG4개와 .visioninsight-captures marker만 있고 각 Capture의 .json은 없다.
CaptureStore.save는 전체 프레임 PNG를 쓰고 owner/metadata/expires/digest를 `_captures`에만 등록한다. `_sessions`도 메모리다.
영상/프레임/source revision/ROI/검사/RIG 연결은 이미 저장된 provenance와 RIG 이력에서 확인했다.
과거 owner 연결은 매니페스트·RIG group·Capture claim 간 일치 여부만 내부적으로 대조했고4/4 일치했다. owner 식별값은 출력·문서화하지 않았다.
**이 일치는 현재 세션의 유효성이나 요청 권한 검증을 대신하지 않는다.**

활성 세션, CSRF, 메모리 Capture 등록, 실제 expires_at/TTL, 현재 Chrome 선택/진행 상태는 **NOT VERIFIED**다.
인증 조회도 authorize/cleanup을 거칠 수 있으므로 이번에 API로 확인하지 않았다. 사용자에게 토큰/쿠키 값을 요청하지 않는다.
4개 파일은 현재 PID 생성 시각보다 먼저 만들어졌다. 현재 PID가 이를 등록 중이라고 추정하지 않으며, 기본 TTL보다 오래됐다는 사실만으로 실제 만료·삭제를 확정하지 않는다.
marker는 관리 디렉터리 표시일 뿐 세션·영상·소유권 복원 정보가 아니다.
파일·매니페스트·owner 연관 기록을 백업해도 세션 토큰/CSRF/메모리 등록을 안전하게 복원하는 지원 경로는 없다. 역으로 owner를 지정해 접근을 복구하지 않는다.

## 4. RIG 상태 — 영속 상태는 VERIFIED, 현재 처리 중 여부는 NOT VERIFIED

읽기 대상은 `data/outputs/reinspection_history/state.json`이며 API의 lock/write 경로를 호출하지 않고 원본 바이트를 읽었다.

| 상태 | 그룹 수 |
|---|---:|
| RETRY_ALLOWED | 41 |
| MANUAL_REVIEW_REQUIRED | 1 |
| MANUAL_REVIEWED | 3 |
| COMPLETED | 22 |
| RECOVERY_REQUIRED | 0 |
| 총계 | 67 |

Capture claim78개는 모두 COMMITTED이며 RESERVED0이다. attempt_count와 attempts 길이 불일치 및0~3 범위 위반은0건이었다.
이는 **영속 파일 스냅샷에서 미확정 예약이 보이지 않았다**는 뜻이며 현재 메모리/HTTP 실행 중 작업이 없다는 증명은 아니다.

현재4개와 연결된 정확한 그룹:
- INSP-001735: RIG-b00711257e1c4e5c94a5140e1022860b
- INSP-001736: RIG-82989d0ee4fd481bbb9d1a55fdd8358b
- INSP-001737: RIG-a6091c3d2dc843da969ae88d43990d04
- INSP-001738: RIG-f7e423f4734d4be8b1b6676f9cd76459

수동 검토 대기는 별도 과거 그룹 RIG-f36e0c4408f54cc1901629be1fa555d0, 현재 검사INSP-001666,3/3이다. 이번4개 그룹과 혼동하지 않는다.
과거 RETRY_ALLOWED41개 전부가 지금 작업 중인 제품이라는 뜻도 아니다.
사용자는 현재 Chrome의 검사 ID/그룹/회차를 육안으로 확인하고 위3개 재검사 가능 그룹 또는 과거 수동 대기를 계속할 필요가 있는지 결정해야 한다.
백업 전 새로고침·세션 재발급·추가 조회를 권하지 않는다. TTL 정리를 유발할 수 있다.

검사/로그/Crop/매니페스트/그룹 횟수/수동 이력은 영속 파일로 남지만, 재시작으로 세션이 사라지면 기존 owner 그룹과 비공개 Crop의 정상 API 접근을 잃을 수 있다.
파일 존재만으로 새 세션에 권한을 주지 않는다. 3회 제한을 초기화하거나 그룹을 완료 상태로 바꾸지 않는다.

## 5. 실제 서버·저장 경로 확인 범위

PID21796은 여전히 127.0.0.1:8000 LISTEN이며 같은 시작 시각2026-10-21 00:49:44.098758 UTC다.
실행 파일은 `C:\Users\USER\miniconda3\envs\vision-insight\python.exe`.
확인한 실행 옵션: uvicorn / backend.main:app / --host 127.0.0.1 / --port8000 / --workers1, reload 없음. --app-dir/--env-file 플래그도 보이지 않았다.
이는 config.py의 자체 .env 로드를 사용하지 않는다는 뜻이 아니다.

| 항목 | 확인 결과 |
|---|---|
| 실제 프로세스 작업 디렉터리 | NOT VERIFIED. WMI 실행 옵션만으로 CWD를 알 수 없음 |
| 실행 중 OUTPUT_DIR | NOT VERIFIED. 현재 프로세스의 캐시 설정/환경을 읽지 않음 |
| 실행 중 CAPTURE_DIR | NOT VERIFIED. 위 관측 폴더와 서버 활성 경로를 같다고 단정하지 않음 |
| 실행 중 TTL/세션 만료 | NOT VERIFIED. 기본값1800초/3600초는 실제 적용값의 증거가 아님 |
| 디스크 경로 계약 | OUTPUT_DIR 기본data/outputs, CAPTURE_DIR 기본data/outputs/captures. 둘은 별도 설정이며 상대값은 PROJECT_ROOT에 결합 |
| .env 시각 | 내용 열람 없이 stat만 확인. 수정2026-10-21 00:31:15 UTC로 PID 시작 이전 |
| config.py 시각 | 수정2026-10-21 01:39:06 UTC로 PID 시작 이후 |

현재 .env의 mtime이 PID보다 이르다는 사실만으로 시작 시 값과 현재 값이 같다고 입증하지 않는다. OS 환경 우선·캐시·파일 교체 가능성을 구분해야 한다.
다른 Python 프로세스의 Settings나 현재 Codex 환경을 이 PID의 값으로 사용하지 않았다. get_settings/ensure_directories도 호출하지 않았다.

실제 경로·TTL을 확인하려면 사용자가 당시 비밀값을 제외한 실행 설정/시작 로그를 제공해야 한다. 확인 경로가 없으면 NOT VERIFIED를 유지한 채 새 서버의 사용할 경로를 별도로 확정해야 한다.
프로세스 메모리 덤프·토큰 추출·인증 우회 방식은 사용하지 않는다.

CaptureStore의 실제 삭제 위험:
1. authorize/bootstrap의 cleanup이 만료 Capture를 삭제할 수 있다.
2. close는 메모리에 등록된 Capture를 제거하고 세션을 비운다.
3. 새 인스턴스가 marker 디렉터리를 처음 초기화할 때 기존 관리 PNG/TMP를 삭제할 수 있다. 남은 파일을 자동 등록하지 않는다.
4. 따라서 서버가 돌아가는 동안의 TTL, 정상 종료, 재시작 후 최초 Capture 접근 모두 보존 위험이 있다. 기존 정책은 변경하지 않는다.

## 6. 사용자 승인 요청용 백업 계약 — 아직 생성하지 않음

권장 새 위치:
`C:\Users\USER\VisionInsight_CaptureBackup_A3_2_20261021_<실행시각>_<고유8자리>\`

프로젝트 밖이고 CaptureStore 관리/TTL 경로 밖이다. 실행 때 존재하지 않는 새 이름만 선택하며 충돌하면 중단한다. 이 문서 작성 시 폴더도 만들지 않았다.

승인할 파일 대상은1절의 **정확한 PNG4개**, 총2,378,872bytes다.
메타데이터 대상은 백업 폴더에 새로 만드는 다음2개 문서로 한정한다.
- backup_manifest.json: 작업 ID·검증 UTC시각·각 원본 절대 경로/Capture ID/파일명/크기/파일 시각/1920×480/복사 전후·백업 SHA256/정확한 백업 경로/개별 상태/전체 상태.
- capture_traceability.json: 이번4개에 대해 서버 저장 JSONL에서 추출한 검사 ID/image_id/영상ID/프레임/source_revision/ROI/Crop 경로·해시/매니페스트 경로/RIG ID·상태·회차/관련 이벤트 코드와 소스 파일 해시/관측 시각.

기존 원본 JSONL·RIG 전체·Crop/매니페스트 파일을 추가 복사하거나 원본 상태를 변경하는 승인은 이 계획에 포함하지 않는다.
매니페스트의 owner 및 쿠키/CSRF/API 키/인증 토큰/작업자 개인정보는 추적성 파일에서 제외한다. 메타데이터는 관측 스냅샷이지 인증·세션 복원 자료가 아니다.

### 승인 후 실행 순서

1. 사용자에게 Chrome 조작/추가 검사/세션 갱신을 잠시 멈추도록 요청한다. 서버는 종료하지 않는다. 이것으로 TTL 삭제가 원자적으로 차단된다고 주장하지 않는다.
2.4개 모두 현재 존재하는지 확인한다. 파일 누락·해시/크기 변경이면 이전 목록으로 성공 처리하지 않고 중단·보고한다. 새 Capture가 추가됐다면 임의로 범위를 늘리지 않는다.
3. 각 원본의 이름/크기/SHA256을 복사 직전에 수집하고 exclusive 새 백업 파일로 **원본 바이트 그대로** 쓴다. PNG decode/encode·이동·이름 변경·원본 쓰기는 하지 않는다.
4. 복사 후 원본 전체를 다시 읽어 SHA256을 계산하고 백업 파일의 SHA256/크기도 전수 확인한다.
5. `원본 복사 전 = 원본 복사 후 = 백업` SHA256, 크기,4개 건수/명칭을 모두 확인한다. 복사 중 원본이 사라지거나 바뀌면 실패다. 백업이 남았다는 이유만으로 삼중 검증 PASS를 주지 않는다.
6. 식별·크기·mtime도 전후 대조하고 일시적인 경로 교체가 탐지되면 완료 처리하지 않는다. 경쟁 중 모든 변경을 완벽히 차단하는 파일 잠금/서버 중단은 이번 계약에 없다.
7. 추적성 근거 JSONL/RIG의 읽기 전후 해시와4개 연결을 확인한다. 메타데이터가 불안정하면 전체 완료를 보류하며 임의 조합하지 않는다.
8. manifest/traceability를 새 파일로 기록하고 재파싱한다. 성공 조건을 전부 충족한 경우에만 BACKUP_PASS다. 실패 시 부분 백업을 원본에 복원하거나 삭제 정리하지 않고 실제 남은 개수와 오류를 보고한다.

## 7. 재시작 위험 판정 및 후속 승인

- **현재 BLOCKED**: 전체 프레임4개의 외부 백업이 미실행이고, 열린 그룹의 계속 작업 필요 여부/활성 세션/실제 설정이 미확인이다.
- **백업 후 PARTIAL 가능**: 전체 PNG 보존이 완료돼도 세션·미완료 제품·수동 대기의 영향이 처리되지 않으면 SAFE로 바꾸지 않는다.
- **SAFE 전제**: 파일 보호 완료, 사용자가 계속할 검사/수동 검토 영향과 옛 세션 접근 소실을 확인, 실제 사용 경로 확정, 작업 중 요청 없음 확인, 재시작 자체를 별도 승인.

세션 연속성이 반드시 필요한 기존 그룹이 남아 있으면 재시작을 계속 보류한다. 백업을 근거로 새 세션에 과거 권한을 복구하거나 RIG를 초기화하지 않는다.
Shadow Metrics 활성화·모델 startup 로드·새 Capture/실제 검사1건·Google 호출은 각 승인 범위가 별개다. 이번 조사로 어느 것도 승인됐다고 간주하지 않는다.

## 8. 실행·보존 범위

백업 **NOT STARTED**. 서버/설정/모델/정책/DB를 조작하지 않았다. API 호출·신규 Grab·실추론·Google·PostgreSQL 연결0회다.
기존 JSONL/RIG는 원본 바이트 직접 읽기만 했으며 조사 도중3개 파일의 바이트 변화는 없었다. PNG 분석은 메모리 decode·배열 비교만 수행했다.
관련 코드·현재 Capture4개·연결 Crop/매니페스트·검사/로그/RIG 등21개 파일의 조사 전후 SHA256을 대조해 변경0을 확인했다. 전체 운영 자산이나 PostgreSQL 내용을 직접 검증한 것으로 확대하지 않는다.
실행 중 세션에 접근하기 위해 읽기 API를 호출하거나 상태 저장소의 lock 파일을 열지 않았다.
새로 작성한 것은 이 보고서뿐이다. 승인 전에 백업 폴더/manifest/Sidecar를 만들지 않았다.
