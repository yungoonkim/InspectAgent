# Step 11 — 최신 Capture 4개 백업 확인 및 안전한 개발 재개 계획

## 현재 상태

2026-10-19 읽기 전용 조사 결과다. 백업은 아직 실행하지 않았다. 서버 종료·시작·재시작, backend 코드 변경, 모델 로드·추론, Gemini API 요청 및 이미지 외부 전송도 수행하지 않았다.

`netstat -ano -p tcp`에서 `127.0.0.1:8000 LISTENING 25328`을 확인했다. 현재 PNG 4개는 점검 전후 파일 개수와 SHA256이 동일했다. 각 PNG와 연결되는 capture_id를 `data/inspections.jsonl`에서 검색했지만 해당 기록은 발견되지 않았다. Frame Index/ROI/연결 Inspection ID는 별도의 승인된 런타임 metadata 없이는 UNKNOWN이다. 운영 세션 토큰을 가져오거나 Capture를 재등록하지 않았다.

## 원본 목록

공통 원본 디렉터리(아래 파일명을 붙인 경로가 정확한 원본 경로):

`C:\Users\USER\AI-NativeAgent\Project\InspectAgent\data\outputs\captures\`

| PNG 파일명 / Capture ID | bytes | SHA256 |
|---|---:|---|
| `CAP-0e821e45b4d04984ad7f56f3dd3decf8.png` | 775553 | `4bbff87d5eae08d9b9b31e873bfc6275b10a4b2b6149cbb6804d9632f775955f` |
| `CAP-14543e2caf6d4ee58ad1fdd91bd6ff14.png` | 777166 | `bda88e853d4a28093441317eebf6ec8393652e7125957599a1e41bcd53310d09` |
| `CAP-411dbfc718be42ef91885ca243ecb465.png` | 784387 | `cf948eebae9fe8c865a3e25fb19570fcb2ab4faf03d9d9bdfd570c59b78bc363` |
| `CAP-db609379922a4b4e883cd894931923e1.png` | 780672 | `e5a0d231486bae29eb5c660e45acbddb78c99e6e5f87c0c5f13e57945b9db044` |

Capture ID는 파일명에서 `.png`를 제외한 값이다. 총 3,117,778 bytes다.

## 기존 백업 포함 여부

| 확인한 기존 백업 디렉터리 | 실제 PNG 개수 | 최신 4개와 이름 일치 | 최신 4개와 실제 바이트 SHA256 일치 |
|---|---:|---:|---:|
| `C:\Users\USER\VisionInsight_GrabBackup_Step9_20261018\` | 6 | 0 | 0 |
| `C:\Users\USER\VisionInsight_GrabBackup_20261018\` | 3 | 0 | 0 |

두 manifest와 실제 PNG 해시를 읽기 전용으로 조사했다. 기존 백업 파일·manifest는 변경하지 않았다. 사용자 홈 전체의 다른 백업 폴더 검색은 접근 거부되어 위 두 승인된 경로만 확인했다. 따라서 다른 위치의 백업 존재 여부까지 부정하지 않는다.

## 제안하는 신규 백업 — 승인 전 미실행

대상 디렉터리:

`C:\Users\USER\VisionInsight_GrabBackup_Step11_20261019\`

점검 시 이 경로는 없었다. 실행 직전 다시 검사하고 이미 존재하면 덮어쓰지 않고 중단한다. 원본 4개를 이름 그대로 복사하며, 새 `backup_manifest.json`에 원본/백업 경로, Capture ID, bytes, 3개 SHA256(원본 전/원본 후/백업), 검증 시각, 연결 metadata의 UNKNOWN 상태를 기록한다. 키·세션 소유자·인증정보는 기록하지 않는다.

실행 절차:

1. 사용자가 백업 중 Grab/검사/분석을 잠시 수행하지 않는다. 서버는 계속 실행한다.
2. 원본 PNG 집합·크기·수정 시각·해시 및 검사/로그 JSONL 해시를 baseline으로 기록한다. 신규/삭제/변경을 감시한다.
3. 원본을 읽기 전용으로 열고 짧은 복사 동안 쓰기·삭제 공유를 허용하지 않는다. 열기 실패 시 중단하며 서버나 ACL을 바꾸지 않는다.
4. 목적지는 신규 파일 생성 모드로만 쓴다. 기존 파일과 이름이 충돌하면 중단한다.
5. 원본 전 = 원본 후 = 백업 SHA256을 모든 PNG에 대해 검증한다. PNG 집합 변화·원본 변경·JSONL 변경이 있으면 성공으로 보고하지 않는다.
6. 모든 검증이 통과한 경우에만 manifest 상태를 VERIFIED로 확정하고 서버 종료 가능 여부를 보고한다. 중간 실패 파일은 원본을 건드리지 않고 새 디렉터리 안에서 미완료로 남겨 원인을 보고한다.

아직 최신 4개 백업이 없으므로 현재는 **안전한 서버 종료를 권고할 수 없다**.

## 서버 종료와 Capture 복구 범위

기존 FastAPI lifespan 종료는 `captures.close()`를 호출한다 (`backend/main.py:63-65`). `CaptureStore.close()`는 관리 중인 capture마다 `_remove()`를 실행하고 PNG를 unlink한다 (`backend/capture_store.py:93-99, 224-228`). reload도 이 종료 경로를 거칠 수 있다.

백업 검증 완료 후 사용자가 서버를 실행한 원래 콘솔에서 Ctrl+C를 한 번 눌러 정상 종료하고 종료 완료를 기다린다. Codex는 kill/restart를 수행하지 않는다. 이후 netstat와 프로세스 조회로 listener 및 reload 감시 프로세스 종료를 확인한 뒤 backend 편집을 재개한다.

백업은 PNG 바이트 보존이다. 종료로 사라진 CaptureStore 메모리 세션·CSRF·Capture 등록을 복원하는 것은 아니다. 백업 PNG를 임의로 운영 Capture로 재등록하지 않는다. 저장된 검사에 이미 연결된 영속 Crop과 현재 미연결 임시 Capture를 구분한다.

## `--reload` 없는 개발 실행 제안

최초 백업·정상 종료·코드 수정·오프라인 테스트가 완료된 뒤 사용자가 필요할 때 단일 worker로 실행한다:

```powershell
Set-Location C:\Users\USER\AI-NativeAgent\Project\InspectAgent
conda activate vision-insight
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

`--reload`를 생략하면 파일 수정이 서버 자동 재시작을 유발하지 않는다. 변경 코드 반영은 사용자가 명시적으로 재시작할 때만 이루어진다. 정상 종료 자체의 임시 Capture 삭제 정책은 그대로이므로 새 Capture에 대해서도 재시작 전 백업 검증이 필요하다.

기존 startup은 ENABLE_PATCHCORE=true일 때 모델을 미리 로드한다 (`backend/main.py:56-60`). 모델 로드 없는 오프라인 개발 서버가 필요하면 사용자 실행 셸에서만 `$env:ENABLE_PATCHCORE = 'false'`를 설정하는 별도 개발 실행을 검토한다. 이 상태에서는 실제 PatchCore 검사가 불가능하다. 실제 검사용 모델 활성화는 별도 확인 후 수행하며 `.env`나 기존 모델 정책을 수정하지 않는다. 위 명령은 계획이며 이번 작업에서 실행하지 않았다.

## 기능 개발 인계 상태

우선 목표는 실제 이미지 검사 → 로그 저장 → 독립 AI 보고서 → UI 연결이다. 자동화 러너/CDP 복구는 후순위다.

- 실제 INSP-001652 저장 Crop의 PNG SHA256은 기존 provenance와 일치함을 읽기 전용으로 확인했다. `59.76 < 125.0` 품질 경고가 모델 NG(40.1631 > 34.1442)보다 우선하여 final REINSPECT가 된 정책을 유지한다.
- `scripts/experiments/opencv_rim_inspection.py` 독립 초안이 작성되어 있다. Backend 감시 디렉터리 밖이며 서버에는 연결하지 않았다. **아직 실행·테스트하지 않았고 실제 측정 수치는 없다.** 초안을 완료 기능으로 취급하지 않는다.
- Gemini 공식 문서의 Argon 모델/이미지/구조화 출력 및 설치 SDK를 읽기 전용으로 조사했다. Production LIVE 어댑터·API·UI 수정은 서버 안전 종료 게이트를 기다린다. 실제 Provider 요청은 0회다.
- backend 파일은 수정하지 않았다. 검사/로그 JSONL·Capture·Crop·Sidecar·모델·DB·기존 백업에 쓰기 작업을 수행하지 않았다.

## 승인 후 실행 결과

2026-10-19 02:11:43 UTC(11:11:43 KST)에 승인된 4개 PNG 백업과 3중 SHA256 검증을 완료했다. 외부 `backup_manifest.json`의 상태는 VERIFIED다. 이후 읽기 전용 산출물 감사 중 Capture 폴더가 승인된 4개 대신 새 PNG 1개로 바뀐 것을 확인했다. 기존 4개 백업은 재검증했으며 모두 정상이다. 새 Capture는 추가 승인 없이 백업하지 않았다. 현재 서버 종료 가능 여부는 새 Capture의 보존 여부까지 반영해야 한다.

상세 연결/보존 확인과 새 Capture 정보는 `docs/day7-step11-capture-backup-and-artifact-preservation.md`에 기록했다.
