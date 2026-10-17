# VisionInsight — Day6 Phase F-1 결과 보고서
## React + TypeScript 프론트엔드 구축 및 FastAPI LiveView / Grab 실제 연동

- **작성일자:** 2026년 10월 17일
- **수행 단계:** Day6 Phase F-1 (프론트엔드 1차 수직 통합)
- **최종 상태:** **PARTIAL (구현 및 API 통합 COMPLETE, 브라우저 자동화 렌더링 NOT TESTED)**
  - 프론트엔드 React + TypeScript 구축: **COMPLETE**
  - TypeScript 타입 검사 및 Production Build: **COMPLETE (PASS, 0 에러)**
  - 린트 검사 (oxlint): **COMPLETE (PASS, 0 에러 / 0 경고)**
  - FastAPI H.264 스트리밍 연동: **COMPLETE**
  - FastAPI Grab API 및 CaptureStore 연동: **COMPLETE (201 Created, 실제 1920×480 PNG 수신)**
  - 브라우저 자동화 도구(Playwright): **NOT TESTED** (오프라인 환경 내 드라이버 CDN 404 제한)

---

## 1. React · TypeScript 기술 스택 및 환경
- **React 버전:** React 19.2.8 (`react`, `react-dom`)
- **TypeScript 버전:** TypeScript 6.0.2 (`tsc -b`)
- **빌드 도구:** Vite 8.3.4 (`@vitejs/plugin-react`)
- **아이콘 시스템:** `lucide-react` 1.59.0 (산업용 고대비 벡터 아이콘)
- **린터:** `oxlint` 1.81.0

---

## 2. 기존 디자인 시안 계승 및 UI 디자인 시스템
- **기존 디자인 참조:** `design/stitch/DesignB.html`의 5단계 워크플로우 인디케이터, 2열 분할 검사 뷰포트, 헤더 브랜딩 구조 적극 계승.
- **다크 네이비 테마 (`#0C1322` / `#0F172A`):**
  - 배경: `#080D1A` / `#0F172A`
  - 패널 카드: `#0F172A`, 테두리 `#25334D`
  - 헤더: 반투명 블러 백드롭 (`rgba(15, 23, 42, 0.85)`), 높이 64px
  - 브랜드 강조색: VisionInsight Cyan (`#4CD7F6`, `#38BDF8`)
  - 상태 표시등: Emerald (`#34D399`, 연결 정상), Amber (`#FBBF24`, 대기/경고), Coral (`#F87171`, 오류/정지)
  - 서체: Google Fonts Inter (본문) + JetBrains Mono (숫자·타임코드·ID)

---

## 3. 생성한 주요 컴포넌트 및 구조

```text
frontend/
├── src/
│   ├── api/
│   │   ├── client.ts             # 중앙 ApiClient (credentials: 'include', CSRF 및 토큰 생명주기 관리)
│   │   └── video.ts              # 비디오 목록, 스트림, 세션 부트스트랩, Grab, 캡처 이미지 조회 함수
│   ├── types/
│   │   └── video.ts              # 백엔드 backend/video_api.py와 1:1 일치하는 타입 정의
│   ├── components/
│   │   ├── Header.tsx            # 브랜드 로고, MANUAL/AUTO 탭, FastAPI 연결 펄스 표시등
│   │   ├── WorkflowStepper.tsx   # 5단계 워크플로우 진행 상태 바 (1~2단계 활성, 3~5단계 Phase F-2 준비)
│   │   ├── LiveView.tsx          # 1920×480 H.264 HTML5 비디오 플레이어, 컨트롤 바, 미세 프레임 이동, Grab CTA
│   │   ├── ImageView.tsx         # 서버 생성 실제 PNG 뷰어, 프레임/PTS/크기 메타데이터, 로딩 스피너
│   │   ├── InspectionPanel.tsx   # 결함 검사 결과 (Phase F-1: NOT RUN 명시)
│   │   └── AgentPanel.tsx        # Gemini AI Agent 진단 리포트 (Phase F-1: NOT ANALYZED 명시)
│   ├── App.tsx                   # 메인 워크스페이스 상태 오케스트레이션 및 에러 핸들링
│   ├── index.css                 # Vanilla CSS 기반 산업용 다크 네이비 디자인 시스템
│   └── main.tsx                  # React 19 진입점
├── package.json
├── tsconfig.json
└── vite.config.ts                # 포트 5173, 호스트 0.0.0.0 명시
```

---

## 4. FastAPI 백엔드 연동 및 실제 사용 API 계약

### 4-1. 백엔드 연결 설정
- **기본 URL:** `http://127.0.0.1:8000` (환경변수 `VITE_API_BASE_URL` 지원)
- **보안 및 세션 정책:**
  - `credentials: "include"` 전송으로 HttpOnly 세션 쿠키(`inspect_agent_capture_session`) 자동 유지
  - 브라우저 표준 `Origin: http://localhost:5173` 전달로 백엔드 `require_origin` 검증 통과

### 4-2. 실제 사용된 API 계약
1. `GET /health`  
   - 응답: `{"status": "ok"}` ➔ 헤더 `FastAPI: CONNECTED` (녹색 펄스 점등)
2. `GET /videos`  
   - 응답: `VideoList` ➔ `VID-000001` (1920×480, 30 FPS CFR, 240 프레임, 8.0초, H.264)
3. `GET /videos/{video_id}/stream`  
   - HTML5 `<video>` 요소의 `src`로 직접 스트리밍 바인딩, loop 재생
4. `POST /capture-sessions` (세션 부트스트랩)  
   - 요청: `Origin: http://localhost:5173`
   - 응답: 200 OK + `Set-Cookie` + `{"csrf_token": "...", "session_ttl_seconds": 3600}`
5. `POST /videos/{video_id}/grab` (프레임 캡처)  
   - 요청 헤더: `X-Capture-CSRF: <csrf_token>`, `Cookie: ...`
   - 요청 바디: `{"frame_index": 96, "source_revision": "f1c5a12ee25672bf..."}`
   - 응답: **201 Created**, `{"capture_id": "CAP-d67e...", "width": 1920, "height": 480, ...}`
6. `GET /captures/{capture_id}/image` (서버 PNG 다운로드)  
   - 요청: 세션 쿠키 포함 fetch
   - 응답: **200 OK**, `image/png` 바이너리 (760,339 바이트, `\x89PNG` 무손실 원본)
   - 클라이언트 처리: `URL.createObjectURL(blob)`로 변환하여 `<img>` 렌더링

---

## 5. 실행 및 검증 결과

### 5-1. TypeScript 타입 검사 및 Build
- 명령: `npm run build`
- 결과: **0 에러, 빌드 성공 (PASS)**
  - `dist/index.html` (0.77 kB)
  - `dist/assets/index-DyU7xtYu.css` (10.65 kB)
  - `dist/assets/index-ESEZKOiu.js` (251.28 kB)

### 5-2. 린트 검사
- 명령: `npm run lint` (`oxlint`)
- 결과: **0 warnings, 0 errors (PASS)**

### 5-3. 프론트엔드 관점 API 통합 실측 검증
Node.js 런타임 환경에서 브라우저와 동일한 헤더 및 쿠키 흐름으로 E2E 호출 체인을 검증함:
```text
1. Health check: 200 { status: 'ok' }
2. Video list: VID-000001 (FPS 30, Frames 240)
3. Bootstrap capture session (Origin: http://localhost:5173): 200 (Cookie & CSRF 수신)
4. Grab frame #96: 201 Created (CAP-d67e376bb83f4d8bad0a0a2149cda860, 1920x480)
5. Fetch captured image PNG: 200 OK, image/png, 760,339 bytes, Valid PNG Header: true
6. Repeat Grab frame #150: 201 Created (CAP-229b841715e14f9ea4a7fcbc1dabdfac, Frame 150)
ALL API INTEGRATION TESTS PASSED!
```

### 5-4. 브라우저 자동화 검증 제한
- **상태:** **NOT TESTED**
- **원인:** 환경 내부에서 Playwright 브라우저 바이너리 CDN(`azureedge.net`) 접근 시 404 차단되어 헤드리스 브라우저 자동화 서브에이전트가 실행되지 못함.
- **보고:** 실제 렌더링 화면을 눈으로 확인하지 않았으므로 브라우저 자동화 테스트는 솔직하게 `NOT TESTED`로 보고하며 임의의 캡처를 합성하지 않음.

---

## 6. 개발 서버 실행 방법

### 6-1. 백엔드 FastAPI 서버 실행
```bash
# miniconda vision-insight 환경
conda run -n vision-insight uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### 6-2. 프론트엔드 Vite 개발 서버 실행
```bash
cd frontend
npm install
npm run dev
```
- 브라우저 접속 주소: `http://localhost:5173`

---

## 7. 미구현 기능 및 다음 Phase F-2 준비 상태
- **미구현 상태 유지:**
  - 결함 검사 (Inspection): `NOT RUN` 표기 유지
  - Gemini AI Agent 진단: `NOT ANALYZED` 표기 유지
  - AUTO 모드: `AUTO 검사 연결 준비 중 — 현재는 MANUAL Grab만 지원` 안내 유지
  - 실제 PatchCore 추론 0회, Gemini API 호출 0회 엄격 유지
- **다음 Phase F-2 연동 준비:**
  - 캡처된 `capture_id`를 기반으로 ROI 영역 선택, FastAPI `/inspections` 및 Gemini `/inspections/{id}/agent-report` 연동을 위한 UI 패널 뼈대 배치 완료.
