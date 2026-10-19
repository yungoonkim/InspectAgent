# Step 10 PARTIAL 복구 감사 — 2026-10-19

## 결론 및 실행 게이트

**PARTIAL 유지 / 현재 CodexSandboxOffline 계정에서 전체 P0 재실행은 BLOCKED.**

이번 작업은 읽기 전용 조사와 이 문서 작성까지 수행했다. 기존 Python/TypeScript/테스트/러너는 변경하지 않았다. 새 테스트 실행, 브라우저 실행, 서버 시작·종료·재시작, ACL 변경, 관리자 권한 상승은 모두 0회다. 실제 PatchCore 로드·추론, Gemini Provider 요청, 이미지 외부 전송도 모두 0회다.

| 문제 | 확인 수준 | 분류 및 다음 단계 |
|---|---|---|
| 안전 러너 snapshot 실패 | 현재 실행 계정의 파일 읽기/ACL 조회 거부 CONFIRMED. 해당 파일의 상세 DACL은 조회 거부로 UNKNOWN | 사용자 개입 필요. 일반 USER 계정에서 읽기 전용 접근 확인. 보호 검사를 우회하지 않음 |
| Chrome CDP timeout | 다섯 그룹의 GPU 프로세스 반복 종료 및 browser FATAL CONFIRMED. 그 하위 원인의 정확한 권한 조건은 UNKNOWN | 추가 증거 필요. 동일 버전의 일반 USER 환경에서 단일 mock 그룹 검증 필요 |
| Uvicorn PID/포트 불일치 | 현재 netstat에서 PID 25328 LISTENING 확인. 이전 Get-NetTCPConnection 실패가 숨겨진 사실 CONFIRMED | 서버 재시작 불필요. 부모·자식 상세와 콘솔 로그는 현 계정에서 접근 불가 |

## 기존 작업 및 테스트 증거

작업 시작의 `git status --short`:

- 기존 `.tmp_measurement_regressions/`
- `tests/test_day10_decision_matrix.py`
- `docs/day7-step10-inspection-accuracy-and-decision-qa.md`
- `docs/day7-step10-full-ui-automation-matrix.md`
- `docs/day7-step10-opencv-comparison-poc.md`
- `docs/visioninsight-development-effort-evidence.md`

위 파일은 모두 untracked였다. `git diff --stat`와 `git diff --name-only`는 tracked 변경을 보고하지 않았다. 이는 untracked 내용이 없다는 의미가 아니다. 기존 파일은 보존했다.

이전 세션에서 보고한 89 PASS는 신규 실제 판정 함수 8개 조합과 Grab/reinspection Fake 회귀이며, 54 PASS는 Vision Fake와 동일한 판정 함수 8개 조합을 포함한다. 따라서 두 숫자를 합산하여 143개의 독립 테스트라고 주장하지 않는다. 당시 명령 출력 및 Step10 문서가 근거이며, 격리 temp 디렉터리 자체는 JUnit PASS 보고서가 아니다. 이번에는 해당 테스트를 다시 실행하지 않았다.

저장된 10월 18일 증거는 독립적으로 읽었다:

- `data/outputs/safe-regression/20261018-225800-d19e47a0/backend.xml`: 577 cases, 0 failures, 0 errors, 10 skipped, 49.966초 → **567 PASS**.
- 같은 경로의 `summary.json`: Frontend 39 PASS, Chrome Mock 12+8+15+8+7=50 PASS, TypeScript/Build/Lint 성공, lint 6 warnings.
- `protection.json`: 당시 80개 파일 unchanged=true.
- 10 SKIP: Windows symlink 권한 1, 실제 모델 제외 정책 6, 조회용 검사 없음 1, 격리 dataset fixture 없음 2. 이번에 사유나 정책을 변경하지 않았다.

이전 Step10의 89/54/39 PASS 및 TypeScript/Build/Lint 결과는 과거 실행이다. 이번 새 테스트 결과는 **미실행**이다.

## 안전 러너 권한 실패

실패 대상은 `data/outputs/inspection_anomaly_maps/INSP-001650.json`이다. 기존 traceback은 `scripts/safe_regression_backend.py:39`의 `path.read_bytes()`에서 Python `PermissionError [Errno 13]`을 보고했다. 10월 19일 runner는 snapshot 전에 실패하여 `data/outputs/safe-regression/20261019-102005-ff7e7178/summary.json`에 runner/offline-safety 실패를 남겼고 backend/browser 단계는 시작하지 않았다.

이번 읽기 전용 확인:

- 실제 명령 계정: `DESKTOP-6NSMR7D\CodexSandboxOffline`. Windows Administrator role=false.
- 파일 metadata 조회는 가능했다. JSON 크기 1159 bytes, 일반 Archive 파일, LinkType 없음.
- `Get-Acl` 및 `icacls`는 해당 JSON에서 Access Denied. `icacls` exit code 5.
- `.NET File.Open(Read, FileShare.ReadWrite | FileShare.Delete)`도 `UnauthorizedAccessException`, HRESULT `0x80070005`로 실패했다. 광범위한 공유 모드로 열어도 같은 접근 거부이므로, 일반적인 exclusive-sharing 충돌이라는 근거는 없다. 다른 프로세스의 파일 handle을 직접 조사한 결과는 아니다.
- 같은 inspection의 overlay PNG도 ACL 조회가 거부됐다. 즉 JSON parser나 내용 손상만의 문제가 아니다.
- 부모 `inspection_anomaly_maps` 디렉터리는 Owner=USER, inheritance 활성 상태이며 CodexSandboxUsers의 상속 Allow Modify 규칙이 있었다. 해당 파일의 DACL은 읽지 못했으므로 부모 규칙만으로 파일의 상속·명시적 거부 여부를 확정할 수 없다.
- 10월 18일 run 디렉터리 Owner는 USER, 실패한 10월 19일 Chrome run Owner는 CodexSandboxOffline이었다. 이전 프로세스의 실제 token은 당시 기록에 없어 확정하지 않았다.

이 파일은 보호 대상에 포함되는 것이 정상이다. `protected_snapshot()`은 모델, 원본 판정 코드, 운영 JSONL/로그, Capture/Crop, Anomaly Map, 재검사/Vision 상태 등 변경 금지 자산의 SHA256을 계산한다 (`scripts/safe_regression_backend.py:30-40`). 하나라도 읽지 못하면 snapshot이 실패하는 동작을 유지해야 한다.

**최소 방안:** 소스나 ACL 수정 없이 일반 USER의 비관리자 PowerShell에서 현재 파일의 ACL/해시 읽기를 먼저 확인한다. 그 계정에서도 실패하면 파일 소유자가 ACL 및 파일 생성 당시 보안 조건을 추가 조사해야 한다. 이번 승인에는 ACL 변경이 포함되지 않는다. 파일 제외·복사·교체·보호 검사 비활성화로 PASS를 만들지 않는다.

## Chrome CDP 실패

다음 기존 산출물의 `result.json`과 `browser-stderr.txt`를 읽었다:

| 그룹 | 디렉터리 | 결과 |
|---|---|---|
| base | `data/outputs/day10-chrome-mock-20261019/base/step4-browser-iVdfwl/` | 0 PASS / 1 harness failure |
| agent | `data/outputs/day10-chrome-mock-20261019/agent/step4-browser-Anlt0N/` | 0 PASS / 1 harness failure |
| grab | `data/outputs/day10-chrome-mock-20261019/grab/step4-browser-zMRW11/` | 0 PASS / 1 harness failure |
| roi | `data/outputs/day10-chrome-mock-20261019/roi/step4-browser-oC4nUf/` | 0 PASS / 1 harness failure |
| vision | `data/outputs/day10-chrome-mock-20261019/vision/step4-browser-VMmASe/` | 0 PASS / 1 harness failure |

공통 로그:

1. 고유한 DevTools port가 열렸다.
2. `Browser.getVersion`이 응답했다. WebSocket/CDP 연결 자체는 이루어졌다.
3. GPU child가 각 그룹에서 6회 `exit_code=-1073741790` (`0xC0000022`)로 종료됐다.
4. `FATAL ... GPU process isn't usable. Goodbye.`가 발생했다.
5. pending `Page.enable`은 15초 후 timeout 처리됐다. UI test case는 시작하지 않았다.

로그에는 encryption 불가, registry access denied, GPU persistent cache sharing 오류도 동반됐다. 어느 자원/보안 규칙이 GPU child 종료를 직접 유발했는지는 이 로그만으로 특정할 수 없다. sandbox 계정 실행 환경 차이는 SUSPECTED이며, Chrome 버전 교체나 timeout 증가는 근거 있는 해결책이 아니다.

현재 Node는 v24.11.0, bundled undici 7.16.0이다. 하네스는 Playwright가 아니라 Node WebSocket/fetch로 CDP를 직접 사용한다. 현재와 10월 18일 성공 기록의 Chrome은 모두 **155.0.8059.82**다. 과거 Node 버전은 artifact에 기록되지 않아 비교 불가다.

프로필 경로는 그룹별 mkdtemp 하위 `chrome-profile`, debug port는 0(임의 배정)이다 (`frontend/scripts/test_step4_browser.mjs:233, 285-305`). 기존 사용자의 Chrome 프로필을 재사용하지 않았다. 기존 실행은 순차였고 모든 그룹에 다른 profile/DevTools port가 있으므로 공용 프로필이나 그룹 병렬 실행 충돌의 증거는 없다. cache 공유 오류 하나만으로 사용자 Chrome 세션 충돌이라고 단정할 수 없다.

`connectCdp`는 browser exit/socket close 시 pending 요청을 즉시 실패시키지 않고 타이머를 기다린다 (`frontend/scripts/test_step4_browser.mjs:182-214`). 따라서 browser FATAL이 최종적으로 Page.enable timeout처럼 보일 수 있다. 후보 최소 개선은 pending CDP 요청에 owned-browser exit를 연결해 초기 crash를 바로 진단하는 것이다. 이번에는 수정하지 않았다.

**재실행 영향 사전 고지:** 단일 base mock 실행은 새 evidence 디렉터리, 임시 Chrome 프로필/캐시, 임의 localhost debug/mock HTTP port를 만든다. 운영 백엔드에는 연결하지 않도록 구성돼 있다. 기존 harness finally는 자체 생성한 browser process에 `browser.kill()`을 호출한다 (`:502-505`). 사용자 Chrome은 대상으로 삼지 않지만, 이번의 Chrome 강제 종료 금지와 충돌할 여지가 있어 현재 하네스를 그대로 재실행하지 않았다. 재개 시 자체 테스트 프로세스 정리 범위를 승인하거나 graceful 종료로 최소 수정하는 게이트가 필요하다. `--no-sandbox` 추가 등 브라우저 보호 완화는 제안하지 않는다.

## Uvicorn PID/포트 정정

이전 보고의 “PID 25328 --reload 존재, port 8000 LISTEN 없음”은 신뢰할 수 없는 조회 결과였다.

- 현 계정에서 `Get-NetTCPConnection -LocalPort 8000 -ErrorAction Stop`은 CIM `HRESULT 0x80041003` access denied를 반환했다.
- 이전 명령의 `-ErrorAction SilentlyContinue`는 이 오류를 숨겨 빈 결과가 마치 포트 부재처럼 보이게 했다.
- 이번 `netstat.exe -ano -p tcp`는 exit code 0이며 **`127.0.0.1:8000 LISTENING 25328`**을 보여 준다.
- `Get-Process`로 PID 25328/13092가 현존함을 확인했다. 반면 `Get-CimInstance Win32_Process`가 거부되어 parent/child ID, 현재 command line/worker 수는 새로 확정하지 못했다. 기존 command-line 기록을 새 조회 결과로 표시하지 않는다.
- 과거 시간대에 listener가 잠시 내려갔는지는 기존 로그가 없어 UNKNOWN이다. 현재 결과만으로 과거 모든 순간의 상태를 추정하지 않는다.
- 이 작업에서 접근 가능한 서버 stdout/stderr 저장 파일은 찾지 못했다. `data/logs`에는 `.gitkeep`만 있었다. 다른 사용자의 콘솔에 붙거나 내용을 가져오지 않았다.

shutdown/reload 위험은 실제 코드에 있다: FastAPI lifespan 종료는 `captures.close()`를 호출하고 (`backend/main.py:63-65`), `CaptureStore.close()`는 메모리가 관리하는 capture마다 `_remove()`를 호출하여 PNG를 unlink한다 (`backend/capture_store.py:93-99, 224-228`). 따라서 서버 종료가 필요한 복구로 취급하지 않는다. Capture PNG는 이번 조사에서 4개, 파일 크기 약 775–784KB로 존재했다. 새로 생성됐거나 기존 백업에 포함됐는지는 이번에 확인하지 않았다.

## 보호 자산 및 변경 범위

- 신규 전후 **전체** 보호 hash 검증은 여전히 미완료다. 이전 80개 unchanged 결과를 현재 결과로 재사용하지 않는다.
- 현재 JSON과 overlay의 읽기 권한이 해결되지 않으면 전체 snapshot은 계속 FAIL이어야 한다.
- 소스, 운영 JSONL, Capture/Crop/Sidecar, 재검사/수동 이력, 모델/DB/백업에 대한 쓰기 작업은 수행하지 않았다.
- 기존 untracked Step10 파일은 보존했다. 신규 변경은 이 감사 문서뿐이다. 코드 변경이 없어 테스트 재실행은 하지 않았다.

## 사용자 개입 후 구체적인 재개 순서

일반 USER의 **비관리자** PowerShell에서 수행할 후보 절차다. 이번 Codex 작업에서는 실행하지 않았다.

1. `whoami` 및 아래 읽기 전용 명령으로 운영 JSON 접근을 확인한다. ACL 변경 명령을 실행하지 않는다.

   ```powershell
   Set-Location C:\Users\USER\AI-NativeAgent\Project\InspectAgent
   Get-Acl -LiteralPath data/outputs/inspection_anomaly_maps/INSP-001650.json
   Get-FileHash -LiteralPath data/outputs/inspection_anomaly_maps/INSP-001650.json -Algorithm SHA256
   netstat.exe -ano -p tcp | Select-String ':8000\s'
   ```

2. 접근이 성공하고 기존 보호 정책을 그대로 적용할 수 있으면 **snapshot만 먼저** 실행한다. 고유 output 경로를 만들고 출력 디렉터리 외에는 쓰지 않는다. snapshot은 파일 해시를 계산하며 모델을 역직렬화하지 않는다.

   ```powershell
   $auditRun = Join-Path 'data/outputs/safe-regression' ('recovery-' + [guid]::NewGuid().ToString('N'))
   New-Item -ItemType Directory -Path $auditRun | Out-Null
   & "$env:USERPROFILE/miniconda3/envs/vision-insight/python.exe" -B scripts/safe_regression_backend.py snapshot --output $auditRun
   ```

3. 실패 시 그 지점에서 중단한다. 성공 시 browser process 정리 승인/수정 게이트를 확인한 뒤 base mock만 먼저 실행한다. 새 프로필/격리 출력 범위는 위에 기술했다.

   ```powershell
   node frontend/scripts/test_step4_browser.mjs 'C:/Program Files/Google/Chrome/Application/chrome.exe' --output "$auditRun/browser-base"
   ```

4. base가 통과하면 기존 PASS 테스트의 중복 재실행을 최소화하며 `--agent`, `--grab`, `--roi`, `--vision` 그룹을 순차 실행한다. 새 backend 전체 safety counters가 필요한 시점에는 기존 러너의 network/model 차단과 출력 격리를 유지한다. 이후 같은 baseline에 `verify --output $auditRun`을 적용한다. 전체 one-command runner는 모든 게이트가 충족됐을 때만 실행한다:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_safe_regression.ps1
   ```

실행 중 운영 자산 변경/보호 읽기 실패/Chrome fatal이 발생하면 즉시 중단하며 판정은 FAIL/PARTIAL로 유지한다. 서버 재시작이나 Capture 복구는 이 절차에 포함하지 않는다.

## 발표 전 남은 범위

P0 완료를 아직 선언할 수 없다. 사용자 정상 계정에서 보호 snapshot과 base Chrome mock이 먼저 성공해야 한다. 그 후 나머지 mock UI 및 최종 보호 hash 비교가 필요하다. 실제 Chrome에서 ROI 유지/새 Capture/시도 1–3/수동 HOLD·NG/Heatmap/Pixel Inspector/Vision disabled와 출처 표시의 수동 확인도 남아 있다. 모델 결함 Recall, 실제 NORMAL→OK/NG 모델 E2E, Gemini Vision LIVE는 별도 승인·평가 범위로 계속 미검증이다.
