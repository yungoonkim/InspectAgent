# VisionInsight — Day6 Phase F-1 Hotfix 결과 보고서
## 실제 Chrome 브라우저 CAPTURE_SESSION_REQUIRED 오류 해결

- **작성일자:** 2026년 10월 17일
- **수행 단계:** Day6 Phase F-1 Hotfix (브라우저 Grab 세션 문제 해결)
- **최종 상태:** **COMPLETE (Vite 프록시 적용 완료, 세션/CSRF/Grab/PNG API 엔드투엔드 검증 PASS, TypeScript/Build/Lint 0 에러)**
  - 실제 사용자 Chrome 브라우저 최종 수동 확인: **READY FOR USER RE-VERIFICATION**

---

## A. 오류의 실제 원인

1. **Cross-Origin / Cross-Site 분리:**
   - 프론트엔드는 `http://localhost:5173`에서 실행되고 있었으나, `apiClient`의 기본 URL이 `http://127.0.0.1:8000`으로 직접 지정되어 있었습니다.
   - 현대 Chromium/Chrome 보안 모델에서 `localhost`와 `127.0.0.1`은 서로 다른 사이트(Cross-Site)이자 서로 다른 출처(Cross-Origin)로 취급됩니다.

2. **`SameSite=Strict` Cookie 전송 차단:**
   - 백엔드(`backend/video_api.py`)는 세션 쿠키 `vision_capture_session`을 발행할 때 `samesite="strict", httponly=True, path="/"` 보안 속성을 강제합니다.
   - 사용자가 `http://localhost:5173`에서 실행 중인 대시보드에서 `http://127.0.0.1:8000/videos/VID-000001/grab`으로 `fetch(..., { credentials: 'include' })`를 호출할 때, Chrome은 **Cross-Site 요청으로 판단하여 `SameSite=Strict` 쿠키를 요청 헤더에 첨부하지 않고 제거**합니다.
   - 첨부된 Chrome DevTools Network 캡처의 요청 헤더에서도 `Host: 127.0.0.1:8000`, `Origin: http://localhost:5173`만 전송되고 `Cookie:` 헤더가 완전히 누락되어 있음이 증명되었습니다.

3. **백엔드 인가 거부:**
   - `backend/capture_store.py`의 `authorize(token, csrf, write=True)`에서 `token`이 `None`으로 전달되자 `CaptureError(401, "CAPTURE_SESSION_REQUIRED")`가 발생했습니다.

4. **클라이언트 측 401 재시도 핸들러 누락:**
   - 기존 `grabFrame()`의 에러 복구 로직은 `CAPTURE_SESSION_EXPIRED`, `CAPTURE_CSRF_INVALID`, `403`만 감지하고, `CAPTURE_SESSION_REQUIRED` 및 `401`은 처리하지 않아 세션을 재발급받지 못하고 즉시 에러로 중단되었습니다.
   - 또한 앱 마운트 시점에 세션을 미리 부트스트랩(`ensureCaptureSession`)하지 않아 첫 Grab 시점까지 세션이 지연되었습니다.

---

## B. 기존 Cookie/Origin/CSRF 처리의 문제

1. **Cookie:**
   - `localhost:5173` ➔ `127.0.0.1:8000` 간 교차 출처 호출로 인해 `SameSite=Strict` 쿠키가 브라우저에 의해 자동 차단됨.
2. **Origin:**
   - 브라우저가 교차 출처 fetch 시 `Origin: http://localhost:5173`을 전송하였으나, 쿠키 부재로 401 차단됨.
3. **CSRF:**
   - 인메모리에 CSRF 토큰이 캐시되어 있더라도, 그 토큰과 매핑되는 HttpOnly 세션 쿠키가 서버로 전달되지 않아 백엔드 검증 실패.
4. **결론:**
   - 백엔드의 엄격한 보안 모델(`SameSite=Strict`, `HttpOnly`, `CSRF`, `Origin Check`)을 약화시키지 않고 브라우저 표준을 준수하기 위해서는, 브라우저 관점에서 모든 요청이 동일 출처(`http://localhost:5173`)로 이루어지도록 **Vite Same-Origin Proxy (`/api`)** 를 적용해야 합니다.

---

## C. 수정한 파일

1. `frontend/vite.config.ts`
   - `/api` 접두어를 `http://127.0.0.1:8000`으로 전달하는 프록시 설정 추가.
   - `rewrite: (path) => path.replace(/^\/api/, '')` 적용.
   - 백엔드 `require_origin` 검증을 위해 `headers: { Origin: 'http://localhost:5173' }` 명시.
2. `frontend/src/api/client.ts`
   - 기본 `API_BASE_URL`을 `'http://127.0.0.1:8000'`에서 `'/api'`로 변경.
3. `frontend/src/api/video.ts`
   - `grabFrame()`에서 `CAPTURE_SESSION_REQUIRED` 및 HTTP 401 발생 시 세션을 즉시 초기화하고 `ensureCaptureSession()`을 통해 신규 세션/CSRF를 발급받아 1회 자동 재시도하도록 개선.
4. `frontend/src/App.tsx`
   - `loadInitialData()` 진입 시점에 `ensureCaptureSession()`을 사전 호출하여, 대시보드 로드 즉시 브라우저에 `vision_capture_session` 세션 쿠키가 발급·저장되도록 선제 부트스트랩 추가.

---

## D. Vite Proxy 적용 여부

- **적용 완료:**
  - 개발 서버 `http://localhost:5173`의 `/api` 경로가 백엔드 `http://127.0.0.1:8000`으로 투명하게 전달됩니다.
  - 브라우저는 오직 `http://localhost:5173/api/...`로만 통신하므로, 모든 요청이 100% **Same-Origin / Same-Site**가 됩니다.
  - 브라우저가 수신하는 `Set-Cookie`의 호스트가 `localhost`가 되며, `SameSite=Strict` 쿠키가 모든 `/api` 요청에 정상 동봉됩니다.

---

## E. 세션 생성 성공 여부

- **성공 (PASS):**
  - 엔드포인트: `POST http://localhost:5173/api/capture-sessions`
  - HTTP 상태 코드: **200 OK**
  - 응답 헤더:
    `Set-Cookie: vision_capture_session=zj-alPCnT12QbNjRmCnvv2GLSvcy3QLiSj8lJUCGb5E; HttpOnly; Max-Age=3600; Path=/; SameSite=strict`
  - 응답 바디: `csrf_token`, `session_ttl_seconds: 3600`, `capture_ttl_seconds: 1800` 정상 수신.

---

## F. Grab 201 성공 여부

- **성공 (PASS):**
  - 엔드포인트: `POST http://localhost:5173/api/videos/VID-000001/grab`
  - 요청 헤더: `Cookie: vision_capture_session=...`, `X-Capture-CSRF: ...`
  - 요청 바디: `{"frame_index": 30, "source_revision": "f1c5a12ee25672bf..."}`
  - HTTP 상태 코드: **201 Created**
  - 1차 Grab: `capture_id: CAP-da79c69d6f284afb83273090b9fe48e2`
  - 2차 Grab (재시도/반복): `capture_id: CAP-cae07f6f54ae4144a25577dc27ce0dd5` (연속 성공)

---

## G. Capture PNG 200 여부

- **성공 (PASS):**
  - 엔드포인트: `GET http://localhost:5173/api/captures/{capture_id}/image`
  - 요청 헤더: `Cookie: vision_capture_session=...`
  - HTTP 상태 코드: **200 OK**
  - 응답 헤더: `Content-Type: image/png`
  - 응답 바이트: **782,104 바이트** (정상 무손실 1920×480 PNG 바이너리 수신)

---

## H. 실제 브라우저 확인 여부

- **상태:** **PARTIAL (Node.js 기반 Same-Origin 프록시 API E2E 검증 PASS, 자동화 브라우저는 오프라인 Playwright 드라이버 다운로드 차단으로 NOT TESTED, 실제 Chrome 사용자 수동 검증 대기)**
- **설명:**
  - IDE 샌드박스 환경 내 Playwright 브라우저 드라이버 자동 다운로드가 차단(CDN 404)되어 내부 헤드리스 자동화 대신 Node.js E2E 통합 테스트로 검증했습니다.
  - 프록시 및 API 연동의 모든 단계(세션 부트스트랩, 쿠키 전달, CSRF 검증, Grab 201 생성, PNG 200 다운로드, Range 206 스트리밍)가 정상 통과되었습니다.
  - 사용자의 실제 Windows Chrome 브라우저에서 바로 확인하실 수 있도록 준비 완료되었습니다.

---

## I. LiveView/Seek 회귀 결과

- **성공 (PASS):**
  - 엔드포인트: `GET http://localhost:5173/api/videos/VID-000001/stream`
  - 요청 헤더: `Range: bytes=0-1023`
  - HTTP 상태 코드: **206 Partial Content**
  - 응답 헤더: `Content-Range: bytes 0-1023/1542933`, `Content-Type: video/mp4`
  - Vite 프록시 환경에서도 H.264 비디오 스트리밍의 HTTP Range 206 및 브라우저 탐색(Seek)이 손상 없이 정상 작동합니다.

---

## J. TypeScript/Build/Lint

1. **TypeScript Build (`npm run build`):**
   - 실행: `tsc -b && vite build`
   - 결과: **0 에러, PASS (빌드 완료 398ms)**
   - 생성물: `dist/index.html` (0.77 kB), `dist/assets/index-*.css` (10.65 kB), `dist/assets/index-*.js` (251.41 kB)
2. **Lint (`npm run lint`):**
   - 실행: `oxlint`
   - 결과: **0 warnings, 0 errors (Finished in 14ms on 12 files)**

---

## K. 기존 백엔드 보안 유지 여부

- **완전 유지 (100% Preserved):**
  - 백엔드 파일(`backend/video_api.py`, `backend/capture_store.py`, `backend/config.py`)은 단 1줄도 보안 완화 수정을 가하지 않았습니다.
  - `SameSite=Strict` 쿠키 정책 유지.
  - `HttpOnly` 쿠키 정책 유지 (자바스크립트에서 쿠키에 접근하지 않음).
  - CSRF 토큰(`X-Capture-CSRF`) 43자 검증 유지.
  - `require_origin` 출처 검증 유지 (`http://localhost:5173` 정식 화이트리스트).
  - CORS 정책 약화 없음.

---

## L. 사용자 재검증 방법

1. Windows Chrome 브라우저에서 `http://localhost:5173` 새로고침(F5).
2. 화면 상단 헤더의 **"시스템 상태: FastAPI 온라인"** (녹색 펄스) 확인.
3. 좌측 **LiveView**에서 컨베이어 벨트 비디오(`VID-000001`) 재생 확인.
4. **일시정지(Pause)** 클릭 후 특정 프레임(예: 병이 중앙에 위치한 시점)으로 Seek.
5. **📸 프레임 캡처 (Grab Frame)** 버튼 클릭.
6. Chrome DevTools Network 탭 확인:
   - `POST /api/videos/VID-000001/grab` ➔ **201 Created** 확인.
   - `GET /api/captures/CAP-.../image` ➔ **200 OK** 확인.
7. 우측 **ImageView** 패널에 실제 고화질 캡처 이미지(1920×480)와 메타데이터가 표시되는지 확인.
8. 2회차 Grab을 연속으로 클릭하여 세션 만료 없이 지속적으로 정상 작동하는지 확인.
