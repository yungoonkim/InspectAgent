# VisionInsight 제출 ZIP 패키징 가이드 및 체크리스트

> **문서 목적:** 개발 프로젝트를 다른 PC에 공유하거나 과제로 제출할 때, **무엇을 포함하고 제외할지**, 어떻게 무결성·보안·재현성을 검증할지 정하는 작업 기준서.
>
> 작성 기준: **2026-10-23**. 현재 개발 저장소의 실시간 파일 목록을 직접 전수 조사한 문서는 아니다. 아래 항목은 기존 정적 점검·ZIP 검증 보고서와 알려진 프로젝트 구조를 근거로 작성했으며, **후속 기능 변경 때는 최신 소스/README/코드 참조 경로를 우선**한다.

## 0. 한눈에 보는 결론

- **넣는다:** 실행 소스, 의존성 잠금 파일, 설치·실행 안내, 안전한 설정 예제, PatchCore Checkpoint+Metadata, 실제 등록 영상 및 정적 검사에 필요한 이미지, Quality Shadow **운영 코드**, 필요한 DB 마이그레이션.
- **조건부로 넣는다:** 검사 이력·Grab Crop+Image Manifest·Heatmap·RIG·Gemini 저장 보고서·Shadow Sidecar·발표 자료 등. 실제 시연 기능에 필요한 범위와 데이터 공유 가능성을 확인한다.
- **넣지 않는다:** 실사용 `.env`, `.env.roi-db.local`, 비밀번호·API 키·토큰·ADC/서비스 계정 인증 파일, 브라우저 프로필/세션, 실행 캐시, `node_modules`, Python 가상환경, 비공개 평가 자료, 기존 ZIP 및 임시 파일.
- **가장 중요한 규칙:** 원본 데이터·기존 ID·파일명을 고치지 않고, **새 ZIP만 별도 디렉터리에 생성**한다. ZIP 생성 성공과 실제 실행 성공은 서로 다른 판정이다.

## 1. 기준 경로와 버전 관리

| 항목 | 기준 또는 처리 |
|---|---|
| 개발 저장소 | `C:\Users\USER\AI-NativeAgent\Project\InspectAgent` |
| 권장 ZIP 외부 출력 폴더 | `C:\Users\USER\VisionInsight_Submissions\` |
| 권장 ZIP 이름 | `VisionInsight_Final_Submission_YYYYMMDD[_vN].zip` |
| ZIP 내부 최상위 폴더 | `InspectAgent/` 한 개 |
| 기준 README | ZIP에 실제 포함된 `InspectAgent/README.md` |
| 기준 소스 | **압축 생성 시점의 최신 개발본**. 예전 HTML 시안·스크린샷·과거 ZIP으로 대체하지 않음 |

### 2026-10-23에 확인된 *기존* 성공 패키지 참고값

- 경로: `C:\Users\USER\VisionInsight_Submissions\VisionInsight_Final_Submission_20261023.zip`
- 크기: **182,457,277바이트** (약 **174.00 MiB**)
- 파일: **666개** (소스·리소스 665개 + 패키징 매니페스트 1개)
- SHA256: `4e155f13d526dfaa6bd7cd77a11ba98a0dd50f35c777e97700951690ed1409d7`
- 당시 ZIP CRC·경로 안전성·원본/ZIP 해시·주요 제출 리소스 검증: PASS
- **주의:** 이 해시와 파일 수는 **그때 생성된 ZIP에만** 적용된다. 이후 Gemini Judge 복구나 Retry 정책 개편 등 코드를 수정했다면 이 ZIP은 변경 전 버전이다. 새 제출본은 **새 파일명·새 SHA256**을 기록하고 다시 검증한다. 당시 독립 설치·실행 검증은 별도로 남아 있었다.

## 2. 반드시 포함 — REQUIRED / DEMO_REQUIRED

> 아래는 역할 중심 목록이다. **실제 하위 경로는 최신 코드의 로더·설정·README로 확인**한다. 확인하지 않은 모델·영상·Dataset 파일명을 추측해서 만들거나 변경하지 않는다.

| 분류 | 대상 | 확인할 사항 |
|---|---|---|
| REQUIRED | `backend/` 소스·라우터·서비스·설정 모듈 | FastAPI 실행 및 내부 import에 필요한 모든 로컬 모듈 포함 |
| REQUIRED | `frontend/src/`, `frontend/public/`, `frontend/index.html` 등 | React 화면, UI·이미지·폰트·정적 자산 누락 없음 |
| REQUIRED | `frontend/package.json`, `frontend/package-lock.json` | `npm ci`로 동일 의존성 설치 가능; 잠금 파일 반드시 포함 |
| REQUIRED | Vite, TypeScript 등 프론트엔드 빌드 설정 | 최신 소스에서 사용하는 실제 설정 파일 포함 |
| REQUIRED | `requirements-prod.txt`, `requirements.txt` 및 실제 사용하는 나머지 requirements 파일 | **기존 보고서는 requirements 3개 포함**. 세 번째 파일명은 실제 저장소에서 확인. PyTorch 등 설치 절차와 호환되어야 함 |
| REQUIRED | `README.md`, `frontend/README.md`, 관련 실행/문제 해결 문서 | Windows 설치, Python/Node 요구 버전, 서버 기동, 환경변수 설명, 미완료 기능 고지 |
| REQUIRED | `.env.example` 등 **비밀값 없는** 설정 예제 | 빈 값 또는 placeholder만 허용; 실사용 비밀번호·토큰 금지 |
| REQUIRED | 실제 앱이 사용하는 DB 스키마·마이그레이션 | ROI DB 관리 기능 시연을 주장할 경우 DB 생성·마이그레이션·초기화 지침까지 필요 |
| REQUIRED | 검사·로그·Capture·Gemini·RIG·Quality Shadow의 **실행 코드** | 파일이 Git ignored/untracked인지와 무관하게 실제 import·기동 참조 기준으로 선정 |
| DEMO_REQUIRED | PatchCore **Checkpoint + Metadata** | 모델 로더 경로 유효, 두 파일의 모델 체크포인트 SHA256 일치 |
| DEMO_REQUIRED | 등록 영상 `VID-000001`~`VID-000003` 실제 파일 및 메타데이터 | 실제 등록 경로·해시·프레임 수 등 참조 일치 |
| DEMO_REQUIRED | 정적 이미지 검사에 필요한 Dataset PNG 및 등록/주입 이미지 | 예전 검증 패키지는 Dataset PNG **292장 + 주입 이미지 1장** 포함. 다음 버전에서는 실제 로더·이미지 ID에 따라 확인 |
| REQUIRED | 최신 기능과 호환되는 테스트·설정·리소스 로딩 관련 파일 | 검증용 패키징에는 테스트가 권장; 실행 자체에 불필요한 거대한 산출물은 조건부 |

**유의:** 모델·영상·Dataset은 Git에서 ignored일 수 있다. `git ls-files`나 `git archive`만으로 ZIP을 만들면 빠질 수 있으므로 **실제 파일 존재·필요성·해시를 별도로 검사**한다.

## 3. 시연 목적에 따라 포함 — OPTIONAL / CONDITIONAL

| 대상 | 포함할 때 | 주의점 |
|---|---|---|
| 검사 이력 JSONL 및 연결 로그 | 저장 검사 이력 조회를 실제로 시연할 때 | 이미지/로그/검사 ID 참조를 함께 검증하고 민감 데이터 제거 여부 심사 |
| 영구 Grab Crop와 **Image Manifest** `.json` | 기존 Grab 이미지 및 출처·해시를 재현해야 할 때 | `IMG-GRAB-<UUID>.png`와 같은 stem의 `.json`을 쌍으로 취급; 서로 떨어뜨리지 않음 |
| Heatmap Overlay / NPZ / 메타데이터 | 과거 검사 Heatmap 화면을 시연할 때 | Inspection ID, Image ID, Sidecar 메타데이터 및 Overlay 경로가 모두 연결되어야 함 |
| RIG 및 작업자 수동 확인 이력 | 과거 재검사 그룹/수동 결과를 시연할 때 | 과거 정책 의미 유지; Session/Capture 권한까지 자동 복구된다고 가정 금지 |
| Gemini Judge / Diagnostic Agent **저장 결과** | 과거 저장 결과 조회 시연이 필요하고 공유 가능한 경우 | `FAKE_TEST`·LIVE 여부 표시 유지; 새 Google 호출과 혼동 금지 |
| Quality Shadow 지표 Sidecar | 품질 계측 검증 시연/분석 증거가 필요할 때 | 운영 모듈은 필수, **과거 Sidecar 데이터는 조건부**; 버전·검사·해시 연결 확인 |
| 과제 기획안·발표 PPT·개선 이력 및 테스트 보고서 | 교수/평가자가 요구하거나 설명 자료가 유익할 때 | 최종 발표자료는 현재 구현 상태와 일치해야 함 |
| 테스트 코드·작은 고정 테스트 픽스처 | 제3자 검증/재현성이 필요할 때 | 공유 제한·가짜 인증값·고정 토큰 문자열을 검토하고 실제 비밀은 제거 |
| 새 UI HTML 시안 3종 | **별도의 디자인 시안**으로 제출 요구가 있을 때 | 실제 React에 적용되지 않았다면 앱 구현 기능으로 혼동되게 넣지 않음 |

### 재현성 판단 기준

- **앱 실행 시연**: 소스 + 의존성 파일 + 모델·영상·입력 이미지 + 설정 안내가 우선.
- **저장된 과거 결과 시연**: 관련 검사 JSONL + Crop/Manifest + Heatmap + 로그 + RIG 등 **참조 체인을 함께** 점검.
- **ROI DB 기능 시연**: DB 마이그레이션뿐 아니라 **안전한 데모 DB 구성법**이 필요. 운영 DB 접속정보·실제 비밀번호나 관리자 토큰을 ZIP에 넣지 않는다.
- **Gemini LIVE 시연**: API 키는 사용자가 자신의 PC에서 **별도 환경변수로 설정**한다. ZIP에 키를 넣지 않으며, 비용·승인·모델 접근 조건을 안내한다.

## 4. 반드시 제외 — EXCLUDE

### 4.1 비밀정보 / 개인정보 / 외부 인증

- 실사용 `.env`, `.env.local`, `.env.production`, `.env.roi-db.local` 및 기타 **실제 값이 들어간** 환경 파일. 허용 예외는 내용을 검토한 `.env.example` 등 안전한 예제만.
- Gemini/Google API Key, DB 비밀번호, 관리 토큰, 세션 비밀키, Webhook Secret, 실제 사용자 토큰.
- Google ADC 사용자 인증 캐시, 서비스 계정 JSON/PEM/P12 비밀키, `application_default_credentials.json`, 브라우저 로그인·쿠키·프로필.
- 기기/사용자 식별 정보, 회사·학교 내부 정보, 비공개 평가 Dataset 및 승인받지 않은 제3자 데이터.
- 파일 이름만 검사하지 말고 **소스·테스트·문서 안에 하드코딩된 인증정보도 검사**. 기존 `tests/roi_restart_probe.py:39`의 고정 인증 문자열은 공유 적합성을 별도 점검하되 실제 값은 로그에 출력하지 않는다.

### 4.2 실행 환경 / 생성물 / 중첩 파일

- `.git/`, `.venv/`, `venv/`, Conda 환경, `frontend/node_modules/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`.
- Vite 캐시, 임시 빌드 캐시, 브라우저 캐시·Playwright/Chrome 프로필, `coverage/`, 생성된 임시 로그·덤프, 설치 캐시.
- 이전 제출 ZIP, 다운로드 ZIP, `*.partial`, `*.tmp`, 재압축 작업용 staging 파일, 중첩 ZIP.
- 운영 중인 Capture Session 및 세션 쿠키/CSRF 토큰 파일, 임시 Capture·브라우저 로컬 상태, 운영 서버 PID 파일.
- `../evaluation_private/` 및 공유 권한이 불분명한 개인/외부 자료.
- `frontend/dist/`는 **소스에서 `npm run build`로 재생성하는 제출**에서는 일반적으로 제외 가능. 평가 요구가 정적 배포 산출물인 경우에만 별도로 포함 여부 결정.

> **중요:** ZIP에서 제외한다는 것은 **원본 개발 PC의 파일을 삭제하라는 뜻이 아니다.** 파일 이동·정리·이름 변경·일괄 마이그레이션을 실행하지 않는다.

## 5. 절대 변경하면 안 되는 구조

1. 영구 Grab 이미지: `IMG-GRAB-<UUID>.png`.
2. 동일 stem의 **Image Manifest**: `IMG-GRAB-<UUID>.json` (PWA Manifest와 무관).
3. `image_id` ↔ `inspection_id` ↔ `capture_id` ↔ 영상/프레임/ROI 매핑.
4. 기존 검사 JSONL, 로그, RIG, Heatmap, Shadow Sidecar의 ID·SHA256·경로 관계.
5. PatchCore Checkpoint·Metadata, 등록 영상·Dataset의 원본 파일명 및 바이트 내용.
6. 서버 최종 판정과 Gemini 독립 참고 의견을 구분하는 계약. Gemini 결과가 저장된 원본 `final_result`를 덮어써서는 안 됨.

## 6. Gemini Judge·Retry 정책 개편 후 재패키징 조건

**현재 소스가 실제로 변경되었다는 보고를 확인한 경우에만 아래를 적용한다.** 제안된 개편을 이미 구현됐다고 가정하지 않는다.

- Gemini Judge 회귀 수정 후: 수정된 Backend·Frontend·설정 예제·README·관련 테스트 파일을 모두 반영하고, 서버 LIVE 활성화 조건을 문서에 정확히 기록한다. **실제 키/승인 토큰은 제외**한다.
- 신규 Retry 3회 정책 제거 후: 관련 RIG 저장소·API·UI·TypeScript 타입·검사 정책 버전·회귀 테스트·마이그레이션(있는 경우)을 같이 반영한다. **RIG 저장소 전체나 과거 기록을 삭제해서는 안 된다.**
- 이전 ZIP의 SHA256과 파일 수를 새 ZIP의 결과로 복사하지 않는다.
- 최신 소스가 바뀌었다면 기존 성공 ZIP은 **그 당시 버전의 보관본**이다. 제출하려는 것은 최신 소스 기준 **별도 파일명으로 새로 패키징·검증**한다.
- 보고서/README/PPT에서 "3회 Retry 제거 완료", "Gemini LIVE 검증 완료" 같은 표현은 **실제 구현·테스트 증거가 있을 때만** 사용한다.

## 7. 권장 패키징 절차 (원본 보존)

### 7.1 패키징 전

- [ ] 기준 Git 커밋/작업 트리 상태를 확인하고 현재 수정사항을 기록한다(임의 reset/clean 금지).
- [ ] 현재 애플리케이션의 **실제 import/참조 경로**를 조사한다. 미추적/ignored 실행 코드와 대용량 리소스가 있는지 확인한다.
- [ ] 이번 제출에서 보여줄 시연 시나리오(신규 검사 / 저장 결과 / ROI DB / Gemini 등)를 정한다.
- [ ] 포함 파일 Allowlist와 제외 경로 Denylist를 만든다. `git archive`만 의존하지 않는다.
- [ ] `.env.example`의 값이 비어 있거나 placeholder인지 확인한다.
- [ ] 최신 README의 Windows/Python/Node/npm/Conda 요구사항과 실행 명령을 확인한다.
- [ ] Checkpoint·영상·Dataset·Shadow 코드·DB 마이그레이션 등 필수 리소스 존재 및 원본 SHA256을 확인한다.

### 7.2 ZIP 생성

1. 개발 저장소 외부에 **새로운 빈 staging 폴더**를 만든다.
2. 선정된 파일만 상대 디렉터리 구조를 유지해 `InspectAgent/` 아래에 복사한다.
3. 링크·경로 이탈·중복(대소문자 충돌 포함)·실사용 비밀 파일 포함 여부를 검사한다.
4. 각 파일의 **상대경로, 크기, SHA256**을 기록하는 `packaging-manifest`를 만든다. 매니페스트는 개인정보·인증정보를 포함하지 않는다.
5. 원본 파일의 바이트 내용을 변경하지 않고 새 ZIP을 생성한다. 기존 ZIP은 덮어쓰지 않는다.
6. 오류가 나면 partial 결과물을 제출하지 않는다. 재시도 전 오류 원인과 남은 임시 파일을 확인한다.

### 7.3 ZIP 검사

- [ ] ZIP 자체를 읽을 수 있고 CRC 무결성 테스트가 PASS다.
- [ ] 모든 내부 경로가 `InspectAgent/` 아래이며, 절대경로·`..`·심볼릭 링크 탈출이 없다.
- [ ] 의도하지 않은 중복 경로·중첩 ZIP·캐시·인증 파일이 없다.
- [ ] 파일 수와 상대경로 목록이 매니페스트에 일치한다.
- [ ] 매니페스트의 모든 파일 SHA256이 ZIP 내부 파일 및 기준 원본 파일과 같다.
- [ ] Checkpoint와 Metadata의 해시가 맞다.
- [ ] 등록 영상 3개와 등록 메타데이터가 맞다.
- [ ] Dataset·추가 이미지가 코드에서 참조하는 경로에 있다.
- [ ] README·requirements·npm lock·Shadow 운영 모듈이 포함됐다.
- [ ] 비밀정보 검사 결과가 PASS다. 단순 파일명 검사와 실제 내용 검사의 범위를 구분해 보고한다.
- [ ] 완성 ZIP의 **절대경로/바이트 크기/SHA256/파일 수/검증 시각**을 기록한다.

## 8. 압축 해제 후 독립 실행 검증

> 무결성이 PASS여도 실행 가능성까지 증명된 것은 아니다. 기존 실행 중인 Backend(예: 8000)·Frontend(예: 5173)와 충돌하거나 운영 데이터를 만지지 않도록 **완전히 격리된 검증 디렉터리·Python 환경·포트**를 사용한다.

### 8.1 프론트엔드

```cmd
cd frontend
node --version
npm --version
npm ci
npm run build
```

- **Node 요구 버전은 실제 `package.json` / Vite 요구사항을 기준**으로 한다. 이전 보고 당시 Vite 8.3.4의 Node 요구사항은 `^20.19.0 || >=22.12.0`이었다.
- `node_modules`가 ZIP에 없는 것은 오류가 아니다. `npm ci`가 성공하는지 확인한다.

### 8.2 백엔드

별도 Python 3.11 가상환경/Conda 환경을 준비하고 **ZIP 안의 최신 README를 따라** 설치한다. 기존 안내 예시는 다음과 같다.

```cmd
python -m pip install -r requirements-prod.txt -r requirements.txt
python -m pip check
```

- 다른 requirements 파일이나 CPU PyTorch 설치 조건이 최신 README에 추가됐다면 해당 내용을 우선한다.
- 기존 Conda 환경이나 글로벌 Python 설치 상태로 성공을 대체하지 않는다.

### 8.3 기동과 기능 확인

- [ ] Backend import/기동 및 기본 Health API 확인(별도 포트, `--reload` 금지, `--workers 1`).
- [ ] Frontend 표시 및 격리 Backend API 주소 연결 확인.
- [ ] 모델·파일 경로 로딩 시 누락 여부 확인(실추론은 별도 테스트 범위).
- [ ] 신규 Grab·PatchCore·Gemini LIVE·DB 쓰기·세션 소유권 검사는 **테스트 환경이 안전하게 격리되고 명시적으로 허용된 경우에만** 실행.
- [ ] 실제로 하지 않은 검사는 **NOT_TESTED**, 환경 제한으로 못 한 검사는 **BLOCKED**로 표시. PASS로 꾸미지 않는다.

## 9. 작업자용 읽기 전용 확인 명령 (Windows PowerShell)

아래 예시는 **이미 생성된 ZIP을 수정하지 않는다**. 경로는 실제 최종 ZIP으로 바꾼다.

```powershell
$zip = 'C:\Users\USER\VisionInsight_Submissions\VisionInsight_Final_Submission_20261023.zip'
Test-Path -LiteralPath $zip
Get-Item -LiteralPath $zip | Select-Object FullName, Length, LastWriteTime
Get-FileHash -LiteralPath $zip -Algorithm SHA256
python -m zipfile -t $zip
```

> 위 명령은 기본적인 ZIP 테스트만 제공한다. **전체 비밀정보 스캔, 파일별 SHA256 교차검증, 런타임 재현성 검증을 대신하지 않는다.** 실제 ZIP 파일명과 기준 해시가 바뀌면 변경된 값을 사용한다.

## 10. 최종 승인 기준

| 상태 | 의미 | 제출 관점 |
|---|---|---|
| `ZIP_READY_FOR_ISOLATED_VALIDATION` | ZIP 구성·무결성 검증 완료 | **실행 확인 전 상태** |
| `READY_FOR_SUBMISSION` | 요구된 독립 실행 및 시연 검증까지 충족, 차단 문제 없음 | 제출 가능 |
| `READY_WITH_LIMITATIONS` | 핵심 실행은 되지만 미검증/제약이 명확히 문서화됨 | 과제 요구사항과 대조해 판단 |
| `NEEDS_FIX` | 필수 파일·설치·빌드·보안 문제 존재 | 수정 및 새 ZIP 검증 필요 |
| `BLOCKED` | 환경·자료·승인 부재로 판단 불가 | 차단 이유 해소 필요 |

### 제출 차단으로 취급할 사항

- 필수 Checkpoint/Metadata·영상·Dataset 누락으로 앱/시연 불가.
- npm lock, 주요 로컬 소스, Python requirements 누락으로 재설치 불가.
- 실제 API 키·DB 비밀번호·세션 토큰 등 공유해서는 안 되는 값 노출.
- 매니페스트·SHA256 불일치 또는 손상된 ZIP.
- 과제에서 요구한 기능을 구현했다고 문서화했으나 실행본에는 없거나 재현되지 않음.

### 제약 고지로 충분할 수 있는 사항 (과제 요구사항에 따라 달라짐)

- Gemini LIVE는 별도 키·승인·요금 및 외부 네트워크가 필요하여 실행하지 않음.
- 미구현 AUTO 흐름·Cloud Run 배포는 개발 범위 밖으로 명시.
- 과거 운영 세션·DB를 공유하지 않아 이전 검사 기록 복원은 제한됨.
- 특정 Windows/Python/Node 버전·CPU/GPU 조건이 필요함.

## 11. 제출 직전 최종 체크리스트

- [ ] **최신 소스**와 ZIP 버전이 동일하다. 기능 수정이 있었다면 새 ZIP을 생성했다.
- [ ] ZIP 내부 `InspectAgent/` 구조와 필수 파일이 맞다.
- [ ] 모델 Checkpoint+Metadata, 등록 영상 3개, 필요한 Dataset이 있다.
- [ ] npm lock, Python requirements, 최신 README, 안전한 `.env.example`, Shadow 운영 코드가 있다.
- [ ] 실사용 `.env`·인증 파일·캐시·중첩 ZIP·비공개 자료가 없다.
- [ ] 필요한 과거 결과 시연은 Crop/Manifest/Heatmap/로그/RIG의 **연결 관계를 검증**했다.
- [ ] ZIP CRC 및 원본·ZIP 매니페스트 SHA256 검증에 성공했다.
- [ ] 격리된 환경에서 `npm ci`·빌드·Python 설치·기본 Backend/Frontend 연결을 테스트했다.
- [ ] 모델 실추론, Gemini LIVE, DB는 검증 범위를 정확히 표시했다.
- [ ] README와 PPT의 **실제 구현/설계/미완료** 표기가 일치한다.
- [ ] 과제 플랫폼의 ZIP 크기 한도, 제출 요구 서류(PPT/기획안 등), 업로드 성공 여부를 확인했다.
- [ ] 제출 ZIP의 **파일명·SHA256·크기·생성 시각·검증 결과**를 별도로 보관했다.

## 12. 패키징 결과 보고서 양식

```markdown
# VisionInsight 제출 패키징 결과

- 기준 개발본/커밋: 
- 패키징 날짜: 
- ZIP 절대경로: 
- ZIP 파일명: 
- 크기(byte): 
- 내부 파일 개수: 
- ZIP SHA256: 
- ZIP 최상위 폴더: InspectAgent/

## 포함 검증
- Backend / Frontend / npm lock / requirements: PASS | FAIL
- 모델 Checkpoint + Metadata: PASS | FAIL
- 등록 영상 3개: PASS | FAIL
- Dataset 및 참조 이미지: PASS | FAIL
- README / 설정 예제 / Shadow 코드: PASS | FAIL
- 과거 이력·Crop·Heatmap·RIG(선택 시): PASS | FAIL | NOT_INCLUDED

## 보안·무결성
- 실제 .env·키·토큰 제외: PASS | FAIL | PARTIAL
- ZIP CRC / 경로 안전성 / 중복: PASS | FAIL
- 원본 ↔ 매니페스트 ↔ ZIP SHA256: PASS | FAIL

## 독립 검증
- npm ci / build: PASS | FAIL | NOT_TESTED
- Python pip install / pip check: PASS | FAIL | NOT_TESTED
- Backend·Frontend·기본 API: PASS | FAIL | NOT_TESTED
- PatchCore 실추론 / Gemini LIVE / DB: PASS | FAIL | NOT_TESTED

## 제약 및 미검증 사항
- 

## 최종 판정
ZIP_READY_FOR_ISOLATED_VALIDATION | READY_FOR_SUBMISSION |
READY_WITH_LIMITATIONS | NEEDS_FIX | BLOCKED
```

---

**관리 원칙:** 이 문서는 제출할 때마다 사용하는 기준서이다. 실제 ZIP은 매번 **현재 소스와 최신 실행 경로**를 기준으로 새로 검사한다. 기존 모델·영상·Crop·Image Manifest·검사/RIG 데이터의 물리적 이름 변경·이동·마이그레이션은 별도 명시적 승인 없이는 하지 않는다.
