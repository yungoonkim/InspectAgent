# A-3-2 서버 재시작 전 최종 안전 확인

점검일2026-10-21. 백업 재검증 시각06:00:56 UTC(15:00:56 KST).
**재시작 안전성: PARTIAL. 파일 보존 차단은 해결됐으나 현재 요청·세션·실행 경로의 확인과 사용자 승인이 남았다.**
이번 문서는 재시작·Shadow ON·실검사 승인이 아니다. 새로 작성한 것은 이 문서뿐이다.

## 1. 현재 프로세스·포트

| 항목 | 읽기 전용 확인 결과 |
|---|---|
| 서버 | PID21796 python.exe 존재, 127.0.0.1:8000 LISTEN의 실제 소유 PID도21796 |
| 실행 파일 | C:\Users\USER\miniconda3\envs\vision-insight\python.exe |
| 명령 | -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1 |
| worker/reload | 명시적 workers1, --reload 없음. 부모PID28268에도 reload 인자 없음 |
| 시작 시각 | 2026-10-21 00:49:44.098758 UTC, 이전 조사와 동일 |
| 교체 여부 | 관측한 PID와 시작 시각이 같아 이전 조사 이후 서버 교체·재시작의 증거 없음 |
| 실제 CWD | NOT VERIFIED. 실행 파일 위치·WMI 명령으로 작업 디렉터리를 추정하지 않음 |
| 추가 옵션 | --app-dir/--env-file 옵션 없음. 프로젝트 설정 코드의 자체 .env 읽기는 별개 |

프로세스 메모리·비밀 환경·쿠키를 읽거나 debug endpoint를 추가하지 않았다. netstat/CIM 조회만 했다.
현재 디스크의 config/main/Grab/Shadow 파일은 프로세스 생성 이후 수정됐으므로 최신 코드가 현재 서버에 적용됐다고 주장하지 않는다.
실행 중 모듈/캐시/Shadow 스레드의 상태는 직접 검증하지 않았다.

## 2. OUTPUT_DIR 및 설정 출처

요청에 따라 현재 .env에서는 OUTPUT_DIR/CAPTURE_DIR/TTL/세션 수명/Shadow 설정의 허용된5개 이름만 선별했다. API 키·Gemini 인증 값·기타 비밀값은 출력하거나 보고서에 저장하지 않았다.

| 설정 | 현재 디스크 .env | 코드 기본값 |
|---|---|---|
| OUTPUT_DIR | data/outputs | data/outputs |
| CAPTURE_DIR | 명시 없음 | data/outputs/captures |
| CAPTURE_TTL_SECONDS | 명시 없음 | 1800 |
| CAPTURE_SESSION_SECONDS | 명시 없음 | 3600 |
| QUALITY_SHADOW_ENABLED | 명시 없음 | false |

.env 수정 시각은2026-10-21 00:31:15 UTC로 현재 프로세스 시작 이전이다. 이것만으로 시작 시 내용·현재 캐시 값·OS override의 부재를 입증하지 못한다.
Pydantic Settings는 init > OS 환경 > .env > file secrets > 기본값 순이며, Fallback은 OS/기본값을 사용한다.
get_settings는 lru_cache이고 ensure_directories도 실행하므로 이번 점검에서는 호출하지 않았다.

**실제 서버의 유효 OUTPUT_DIR/CAPTURE_DIR/TTL/Shadow flag는 NOT VERIFIED**다. 현재 Codex 환경이나 별도 Python의 Settings를 실행 중 PID의 값으로 대신하지 않았다.
안전한 공개 설정 조회 API/현재 메모리 값을 확인하는 지원 경로는 이번 범위에서 확인하지 못했다. 새 권한·프로세스 메모리 추출로 보완하지 않는다.

확인된 디스크 기본 경로:
- OUTPUT_DIR: `C:\Users\USER\AI-NativeAgent\Project\InspectAgent\data\outputs`
- CAPTURE_DIR: `C:\Users\USER\AI-NativeAgent\Project\InspectAgent\data\outputs\captures`

둘 다 상대 설정이면 PROJECT_ROOT에 결합되며 서로 독립된 설정이다. 프로세스 CWD와 혼동하지 않는다.
향후 Sidecar는 `<유효 OUTPUT_DIR>/quality_shadow_metrics/quality-shadow-v1/opencv-original-exact-variance-v1/<inspection_id>/<crop_sha256>.json`이다.
기본 Shadow 디렉터리는 현재 없다. 다른 활성 OUTPUT_DIR에도 없다는 증거는 아니다.

위험 평가: 다른 OUTPUT_DIR로 시작하면 과거 파일이 삭제되지는 않아도 기존 검사 입력/Sidecar/RIG를 다른 위치에서 찾게 되어 누락처럼 보일 수 있다. 재시작 전에 사용자가 기존 실행 설정의 경로 override와 앞으로 사용할 경로를 확인해야 한다.
현재 서버의 정확한 값을 끝내 확인할 수 없다면 NOT VERIFIED를 유지하고, 사용자에게 새 실행 경로를 명시적으로 확인받아야 한다.

## 3. Capture 세션 지속성과 영구 자료

코드 근거: backend/capture_store.py의 `_sessions`, `_captures`, `_directory`, cleanup/authorize/bootstrap/close.

- 세션/CSRF/만료와 Capture 등록(owner/metadata/expiry/digest)은 메모리다. Capture ID만으로 접근 권한을 인정하지 않는다.
- 파일의 owner 연관 기록이나 백업은 유효한 세션 쿠키를 대체하지 않는다. 정상 요청도 기존 owner 일치 검증을 거친다.
- 종료 close는 등록 Capture를 제거하고 세션을 비운다. 새 Store의 marker 디렉터리 최초 초기화는 기존 관리 PNG/TMP도 정리할 수 있다.
- TTL은 등록 record.expires<=현재 시각일 때 cleanup 대상으로, 세션은 session.expires>현재 시각인 것만 유지한다. authorize/bootstrap이 cleanup을 호출한다.
- 파일 시각/존재로 현재 메모리 등록·실제 만료·세션 생존을 추정하지 않는다. 활성 세션은 **NOT VERIFIED**다.
- 백업 PNG를 세션/owner와 함께 안전하게 복구하는 공식 지원 기능은 확인되지 않았다. 자동 복원·강제 owner 변경은 하지 않는다.
- 영속 Crop/manifest/검사 JSONL/이벤트/Heatmap/RIG/수동/Gemini 자료는 임시 Capture와 별개다. 재시작 후에도 파일은 남지만 옛 세션의 비공개 자료 접근은 자동 복원되지 않는다.

검사하지 않은 ROI 선택·아직 Grab하지 않은 프레임·미저장 입력·수동 판정 초안은 백업 대상4개의 PNG와 다르다. 브라우저 새로고침/재초기화로 잃을 수 있으므로 사용자 확인이 필요하다.
이번에 Capture 조회/세션 발급 API를 호출하지 않았다. 읽기처럼 보이는 인증 조회로 TTL 정리를 유발하지 않는다.

## 4. RIG 영구 상태와 실행 중 요청의 구분

`data/outputs/reinspection_history/state.json`을 직접 읽었다. 상태 SHA256은 `a41ff20e12d462aa4f0ca78b4ccc7f19c16bf31814f456f23e8bcf237218056b`로 이전과 같으며 읽는 동안 변하지 않았다.

| 영구 상태 | 수 |
|---|---:|
| RETRY_ALLOWED | 41 |
| MANUAL_REVIEW_REQUIRED | 1 |
| MANUAL_REVIEWED | 3 |
| COMPLETED | 22 |
| 총 그룹 | 67 |
| Capture claim COMMITTED | 78 |
| RESERVED / RECOVERY_REQUIRED | 0 / 0 |

현재4개 Capture claim은 모두 COMMITTED로 INSP-001735/1736/1737/1738에 연결된다. 앞3개는1/3 재검사 가능,1738은1/3에서 정상 종료된 그룹이다.
과거 수동 대기는 INSP-001666, RIG-f36e0c4408f54cc1901629be1fa555d0의3/3 상태다.
**41+1은 현재 실행 중 요청 수가 아니라 저장된 워크플로우 상태다.** RESERVED0도 메모리의 처리 중 요청·비동기 Gemini/Shadow 작업 부재를 증명하지 않는다.
현재 요청/진행 중 비동기 작업은 **NOT VERIFIED**다. 소켓 연결 수·프로세스 CPU·파일 mtime만으로 idle을 확정하지 않는다.
API의 RIG lock/쓰기 경로를 호출하거나 상태를 완료/초기화하지 않았다.

## 5. 백업4/4 재검증 — VERIFIED

위치: `C:\Users\USER\VisionInsight_CaptureBackup_A3_2_20261021_142237_24e23498`.
manifest.json/backup_verification.json을 읽고 실제 백업 PNG·현재 원본·영속 Crop을 다시 해시했다. 복사/수정/재생성은 하지 않았다.

| 검사 | 전체 PNG 바이트 | 원본/백업/사전 기준 | 영속 ROI |
|---|---:|---|---|
| INSP-001735 | 590546 | PASS | PASS |
| INSP-001736 | 596987 | PASS | PASS |
| INSP-001737 | 596697 | PASS | PASS |
| INSP-001738 | 594642 | PASS | PASS |

백업4개·총2,378,872bytes, 크기·해시 일치. 최초 삼중 비교 기록도 모두 일치하며 manifest 자체의 해시도 verification과 일치했다.
verification에 기록된 보호29개 파일의 현재 SHA256 변경0을 확인했다. 메모리 상태나 DB 내용의 불변성을 검증한 것은 아니다.
현재4개 이외 새 Capture가 생기면 그 파일은 이 백업에 포함됐다고 가정하지 않는다. 재시작 직전 목록 재확인이 필요하다.

## 6. 사용자 수동 확인 체크리스트

**현재 화면을 육안으로 확인하고 응답해 주세요. 확인 목적으로 새로고침·Grab·검사·AI 실행·수동 저장 버튼을 누르지 않습니다.**

- [ ] Grab/검사 로딩·진행 표시가 없고 현재 결과의 검사 ID가 확정돼 있다.
- [ ] 아직 검사하지 않은 Capture/미저장 ROI/유지할 Pause 프레임이 없다. 있다면 무엇을 유지해야 하는지 알린다.
- [ ] 동일 제품 재검사 요청이 실행 중이지 않고 계속해야 할 현재 RIG가 없다. 있다면 그룹 ID/회차만 알린다.
- [ ] 수동 검토의 작업자/사유/판정 입력 초안을 작성 중이지 않다. 개인정보를 보고할 필요는 없다.
- [ ] Gemini Judge/Diagnostic 실행 중 표시도 없다. 새 분석은 누르지 않는다.
- [ ] 현 세션을 계속 유지할 필요가 없고, 새 정상 세션에서 옛 그룹/비공개 Crop에 접근하지 못할 수 있음을 수락한다.
- [ ] 기존 실행 환경의 저장 경로 override 여부와 앞으로 사용할 OUTPUT_DIR/CAPTURE_DIR를 확인한다. 키/쿠키/전체 환경변수 목록은 보내지 않는다.

필요한 작업이나 세션 연속성이 남아 있으면 재시작을 보류한다. 데이터 손실을 감수하라고 자동 간주하거나 원래 작업을 대신 완료하지 않는다.

## 7. Shadow Metrics 코드 준비 및 재시작 필요성

**Shadow Metrics 코드 준비: READY(격리 검증 기준).**
버전 필수화와 finish의 명시적 두 버전을 정적으로 재확인했다. 기존235 PASS/0 FAIL/0 SKIP XML과 안전 로그를 재사용했으며 이번 테스트 재실행은0회다.
기본 false, ON일 때 lifespan에서 전용 Worker1개 생성, 계산1+대기1, post-commit 이후 예약, 기존 판정/API/JSONL 분리는 유지된다.
계측/발행 실패는 기존 검사 성공을 바꾸지 않는다. 실제 Worker 기동/원본 Crop 연결/파일 발행은 아직 실환경 미검증이다.

실제 ON과 새 코드 적용에는 **재시작이 필요**하다. OS set/.env 변경은 이미 실행 중인 캐시·lifespan에 자동 적용되지 않는다. 지원되는 hot reload/강제 캐시 갱신은 사용하지 않는다.
단일 worker/no-reload 정책을 유지한다. 시작 시 기존 ENABLE_PATCHCORE=true 경로가 모델을 preload할 수 있으므로 서버 시작 승인에 이 로드도 포함돼야 한다.
메모리 큐 유실·native hard timeout 미보장·종료 join1초·이미 발행 중 결과 완료 가능성은 그대로다.

## 8. 별도 승인 후 명령과 재시작 후 확인

**체크리스트 완료·경로 확인·최신 Capture 보호 확인·사용자 재시작 승인 후에만** 진행한다.
사용자가 기존 서버 터미널에서 Ctrl+C로 정상 종료하고, 기존 비공개 Gemini 설정을 유지하는 같은 Miniconda Prompt에서 실행한다. 기존 서버가 실행 중이면 아래 Uvicorn을 중복 기동하지 않는다.

```bat
cd /d C:\Users\USER\AI-NativeAgent\Project\InspectAgent
conda activate vision-insight
set "QUALITY_SHADOW_ENABLED=true"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

.env/config/전역 환경은 변경하지 않고 해당 CMD 실행 환경만 설정한다. Gemini 키나 다른 모델/timeout 설정을 다시 지정·출력하지 않는다.
활성화 전에 미래 실행 환경의 경로를 확인할 필요가 있으면, 사용자 승인 후 같은 Prompt에서 아래 **새 프로세스 미리보기**를 사용할 수 있다. 실행 중 옛 서버 값의 증거는 아니다. get_settings/서버/모델을 시작하지 않고 선택된 비밀 아닌 값만 표시한다.

```bat
python -B -c "from pathlib import Path; from backend.config import PROJECT_ROOT, Settings; settings=Settings(); capture_path=Path(settings.CAPTURE_DIR); print('OUTPUT_DIR=',settings.absolute_output_path); print('CAPTURE_DIR=',capture_path if capture_path.is_absolute() else PROJECT_ROOT/capture_path); print('QUALITY_SHADOW_ENABLED=',settings.QUALITY_SHADOW_ENABLED)"
```

재시작 후 사용자 새 정상 세션, 기존 자료 파일 보존/정상 접근 제한, 새 설정의 저장 경로를 확인한다. 옛 owner를 복원하지 않는다.
첫 실검사는 별도 범위 승인 후 새 Capture최대1개·PatchCore 추론최대1회·새 Inspection1건으로 제한한다. JSONL/로그/Crop/매니페스트/해당 Heatmap/RIG와 신규 Sidecar의 ID/hash/크기/Mean 일치를 검증한다.
null+사유는 실제로 발생한 값만 보고하며 품질 경고/판정을 억지로 만들지 않는다. Sidecar가 없으면 성공으로 간주하지 않는다.
Google/외부 이미지 전송은 별도 승인 없이는0회이며 Judge/Diagnostic 버튼을 누르지 않는다.

롤백도 최신 Capture 보호·사용자 정상 종료 승인이 선행된다. 새 실행 전에 `set "QUALITY_SHADOW_ENABLED=false"`를 명시하고 같은 Uvicorn 명령을 사용한다. 단순 변수 제거만 하면 .env의 값이 다시 적용될 수 있다.
기존 Sidecar/검사/PNG/RIG는 지우거나 덮어써 되돌리지 않는다.

## 9. 최종 상태·남은 승인

| 항목 | 상태 |
|---|---|
| 재시작 안전성 | PARTIAL: 파일 보호 해결, 사용자 작업·세션 결정과 경로 확인 대기 |
| Capture 백업 | VERIFIED 4/4 |
| 영속 ROI/RIG | VERIFIED, 현재 처리 중 상태와 구분 |
| 활성 세션 | NOT VERIFIED |
| 진행 중 요청/비동기 작업 | NOT VERIFIED |
| 실제 실행 OUTPUT_DIR/CWD | NOT VERIFIED |
| Shadow 코드 | READY, 실제 운영 활성화 미실시 |
| 재시작 필요 | 새 코드·ON 적용에 필요하지만 아직 미승인 |

새 미보존 Capture나 처리 중 요청이 확인되면 BLOCKED로 재분류하고 중단한다.
사용자 체크리스트 응답과 경로 결정이 완료돼 승인 가능한 위험 상태가 되면 READY로 재평가할 수 있다. 지금 기술적으로 재시작 가능하다는 이유만으로 READY라 하지 않는다.
재시작/Shadow ON, 모델 preload/제한 실검사, Google 호출은 각각 승인 범위를 구분한다.

## 10. 이번 작업의 안전 경계

서버 API·시작/종료/재시작·Shadow 활성화·새 Grab/Capture·실제 모델 로드/추론·Google·DB 연결0회다.
백업 재복사·파일 삭제/이동·기존 운영 코드/설정/JSONL/RIG 수정은 하지 않았다. 허용된 .env 경로 설정만 선별 확인했고 비밀값은 출력·기록하지 않았다.
현재 브라우저 화면을 Codex가 확인한 것으로 보고하지 않는다. 문서 작성 후 추가 실행 없이 사용자 승인을 기다린다.
