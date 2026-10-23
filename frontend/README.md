# VisionInsight Frontend

React·TypeScript·Vite 기반 영상/정적 이미지 검사 UI입니다. 전체 설치·제출 리소스·DB·Gemini 설정은 [프로젝트 README](../README.md#8-로컬-개발-환경-및-실행-가이드)를 참조하세요.

## 실행 환경

- 잠금된 Vite 8.3.4의 Node 요구사항: **`^20.19.0 || >=22.12.0`**. 지원 범위의 Node LTS와 함께 제공되는 npm을 사용하고 실제 버전을 기록합니다.
- `package.json`과 `package-lock.json`을 함께 보존합니다. 프로젝트에 `engines`/`packageManager` 고정은 없습니다.
- `node_modules/`는 제출 ZIP에 없어도 됩니다. `npm ci`로 재설치하고, Vite가 devDependency이므로 `--omit=dev`를 사용하지 않습니다.

## Windows CMD 설치·실행

아래는 **후속 독립 환경에서 실행할 절차이며 2026-10-23 문서 보완 작업에서는 설치·빌드·기동을 실행하지 않았습니다.** 기존 실행 서버·프로필·Capture 경로를 공유하지 마세요.

```cmd
cd /d "<압축 해제한 InspectAgent 경로>\frontend"
node --version
npm --version
npm ci
npm run dev
```

- 브라우저: `http://localhost:5173`.
- Backend는 프로젝트 루트의 별도 CMD에서 `127.0.0.1:8000`으로 실행합니다. 이미 서버가 있으면 중복 기동·종료·재시작하지 마세요.
- PowerShell 정책으로 npm 스크립트가 차단되면 CMD나 `npm.cmd`를 사용합니다.
- `'vite'을 찾을 수 없음`은 의존성 미설치·설치 실패·devDependency 제외·잘못된 디렉터리 등의 가능성이 있습니다. 실제 설치 로그를 확인하며 전역 Vite 설치나 잠금 파일 삭제로 우회하지 않습니다.

## API·정적 자산·보안

- `src/api/client.ts`: `VITE_API_BASE_URL` 또는 `/api`.
- `vite.config.ts`: 포트 5173 고정(`strictPort`), `/api` → `http://127.0.0.1:8000`, Origin → `http://localhost:5173`.
- 포트/호스트 변경 시 API 주소·CORS·쿠키·Origin을 함께 검증합니다. 격리 포트 사용 방법은 루트 README에 있습니다.
- Favicon: `index.html` → `public/visioninsight.svg`. HTML은 Google Fonts에 외부 요청을 보내므로 인터넷 없는 환경에서는 글꼴 표시가 달라질 수 있습니다.
- Gemini API 키·DB 관리 토큰은 `VITE_` 변수나 프론트엔드 번들에 넣지 않습니다.
- 페이지 진입 시 Capture 세션 bootstrap이 발생합니다. 운영 서버에서 F5나 기존 E2E를 무해한 읽기 전용 동작으로 가정하지 않습니다.

## 후속 검증 명령과 범위

```cmd
npm run build
```

2026-10-23 Judge/RIG 수정 이후 TypeScript 검사·Vite 빌드는 **격리된 최신 소스 사본에서 PASS**했습니다. 프론트엔드 모의 회귀는 19개 스크립트 145 PASS / 0 FAIL / 0 SKIP입니다. 기존 제출 ZIP은 갱신하지 않았으므로 이 결과를 그 ZIP의 최신 소스 반영이나 실제 브라우저 E2E 성공으로 취급하지 않습니다. `dist/`만 별도 정적 서버에 배치하면 API 라우팅도 따로 검증해야 합니다.

- `npm run lint`: Oxlint. 이번 작업에서는 실행하지 않았습니다.
- `npm run test:e2e:readonly`: 기존 서버·브라우저 세션 요청을 포함합니다. 기본 포트 5173/8000으로 접근하므로 이번 단계에서 실행하지 않습니다.
- `npm run test:e2e:edge-gv:capture`: 별도 승인이 필요한 실제 Capture 검증 경로입니다. 일반 설치·제출 확인에 실행하지 않습니다.
- E2E를 재현하려면 `scripts/`, `playwright/`, `playwright.*.config.mjs`도 필요합니다. 기본 UI 기동에 Playwright 브라우저 설치는 필요하지 않습니다.
- 캐시 자동 정리 초안의 검증 미실시 상태와 과거 테스트 수치는 [개선 이력](../docs/progress/visioninsight-improvement-log.md)과 구분합니다.

## 현재 기능 및 한계

LiveView·MANUAL Grab/ROI·정적 검사·Heatmap·Zoom/Pan·Pixel Inspector·Edge/GV·Judge/Agent UI가 구현되어 있습니다. AUTO 연속 검사·실제 PLC 제어·Cloud Run 운영 배포는 완료된 기능이 아닙니다. Judge·Agent는 명시적으로 실행하며 서버 판정을 덮어쓰지 않습니다. 신규 `judge-assisted-v1` 그룹은 1차 검사 한 건 이후 선택적 Gemini Judge와 3차 작업자 확인을 지원하며, Judge 미실행·비활성·실패여도 수동 확인할 수 있습니다. 기존 그룹은 레거시 3회 정책과 이력을 유지합니다. UI 연동과 모의 검증은 실제 서버 반영·LIVE 호출·브라우저 E2E와 구분합니다. **A-3-2는 PARTIAL**입니다.
