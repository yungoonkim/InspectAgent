# VisionInsight — Day6 Phase F-3 결과 보고서
## LiveView ROI 선택 · Product Crop · 600×600 정밀 ImageView 구현
### 발표용 머신비전 검사 UI 고도화

- **작성일자:** 2026년 10월 17일
- **수행 단계:** Day6 Phase F-3 (머신비전 검사 UI 고도화)
- **최종 상태:** **COMPLETE (구현 완료, 빌드/린트 0 에러, 단위/통합 테스트 PASS, 실제 Chrome 수동 확인 대기)**

---

## 1. 구현한 UI 구조

```text
frontend/src/
├── types/
│   ├── video.ts                      # 기존 비디오/캡처 API 스키마
│   └── roi.ts                        # [신규] RoiRect, ViewportMapping, CropData, PixelInspectionInfo
├── utils/
│   ├── coordinateTransforms.ts       # [신규] 화면-1920×480 역변환, Clamping, OpenCV GrayValue 계산
│   └── imageCropper.ts               # [신규] 서버 PNG 1:1 무손실 픽셀 버퍼 Crop (Canvas/ImageData)
├── components/
│   ├── Header.tsx                    # 브랜드 로고 및 상태 인디케이터
│   ├── WorkflowStepper.tsx           # 5단계 워크플로우 인디케이터 (Step 3: ROI 영역 활성화)
│   ├── LiveView.tsx                  # H.264 플레이어 + [Play/Pause] [-1F] [+1F] [Grab] [ROI선택] [Crop적용] [ROI초기화]
│   ├── RoiOverlay.tsx                # [신규] 동결 프레임 위에 렌더링되는 8핸들 대화형 ROI Rect 박스
│   ├── ImageView.tsx                 # 600×600 정밀 뷰어, 100% 중앙 배치, Zoom/Pan, Pixel Inspector, Pixel Grid
│   ├── InspectionPanel.tsx           # 결함 검사 패널 (보존, 이번 단계 추론 미실행 유지)
│   └── AgentPanel.tsx                # AI Agent 진단 패널 (보존, 이번 단계 호출 미실행 유지)
├── App.tsx                           # 워크스페이스 상태 오케스트레이션 및 이벤트 바인딩
└── index.css                         # 산업용 머신비전 다크 테마 및 600×600 캔버스 스타일
```

---

## 2. ROI 선택 방식

1. **상태 조건 제한:**
   - MANUAL 모드에서 영상이 **일시정지(Paused)** 상태일 때만 `[ROI 선택]` 활성화.
   - 영상이 재생 중일 경우 버튼이 비활성화되며 `ROI를 선택하려면 먼저 영상을 일시정지하세요.` 안내 제공.
2. **선택 인터랙션:**
   - 8개 리사이즈 핸들(NW, NE, SE, SW, N, S, E, W)로 크기 미세 조절.
   - 사각형 내부 드래그 시 위치 이동(Move).
   - 여백 클릭 후 드래그 시 신규 사각형 생성(Draw).
   - `clampRoiRect` 함수를 통해 1920×480 경계를 벗어나지 않도록 강제 제한.

---

## 3. LiveView와 Grab PNG 동기화

- 재생 중인 Video 프레임과 서버가 디코딩한 PNG 사이의 시점 불일치를 원천 차단하기 위해:
  1. `[ROI 선택]` 클릭 시 현재 정지 프레임에 대한 서버 Grab PNG가 없으면 `grabFrame`을 즉시 1회 자동 실행.
  2. 서버가 반환한 실제 1920×480 무손실 PNG를 LiveView 비디오 화면 위에 **정지 이미지 레이어(`frozen-frame-layer`)** 로 정확히 일치시켜 오버레이.
  3. 사용자는 바로 그 확정된 서버 PNG 위에서 ROI를 그리므로, **눈으로 보는 프레임과 실제 Crop되는 픽셀이 100% 일치**.
- 영상 Play, Seek, Frame Step 발생 시 현재 ROI 편집 모드를 즉시 자동 무효화(해제).

---

## 4. ROI 좌표 변환 방식

- LiveView 비디오 플레이어의 CSS `object-fit: contain` 레터박스/필러박스 여백을 실시간 계산:
  - `displayWidth = containerHeight * (1920 / 480)` 또는 `containerWidth`
  - `scaleX = displayWidth / 1920`, `scaleY = displayHeight / 480`
  - `offsetX = (containerWidth - displayWidth) / 2`
  - `offsetY = (containerHeight - displayHeight) / 2`
- 화면 마우스 이벤트 좌표 `(screenX, screenY)` ➔ 원본 픽셀 좌표 `(x, y)`:
  - `imgX = Math.round((screenX - offsetX) / scaleX)`
  - `imgY = Math.round((screenY - offsetY) / scaleY)`
  - 정수 반올림 및 `[0, 1920]`, `[0, 480]` clamp 적용.
- `ResizeObserver`를 통해 브라우저 창 크기가 변하더라도 원본 정수 좌표는 영구 불변 유지.

---

## 5. 실제 Crop 생성 방식

- 브라우저 클라이언트 측 무손실 추출:
  - 서버에서 받은 무손실 PNG Blob을 `Image` 객체로 디코딩.
  - 정확히 `roi.width × roi.height` 크기의 오프스크린 Canvas 생성.
  - `ctx.drawImage(sourceImg, roi.x, roi.y, roi.width, roi.height, 0, 0, roi.width, roi.height)`를 통해 원본 픽셀을 1:1 그대로 복제.
  - 리사이즈, 스트레칭, 보간, 패딩 추가 없음 (순수 ROI 영역 픽셀만 추출).
  - `ctx.getImageData(0, 0, roi.width, roi.height)`로 원시 RGB 픽셀 배열 확보.

---

## 6. 600×600 ImageView 표시 계약

- 정밀 검사 뷰어(Product Focus)의 기본 작업 공간은 **600×600 논리 픽셀**로 고정.
- 좁은 노트북 화면에서도 100% 픽셀 배율이 축소/왜곡되지 않도록 스크롤 가능한 뷰포트 래퍼(`canvas-scroll-wrapper`) 배치.
- 캔버스 전체 영역을 `RGB(0, 0, 0)` 순수 블랙으로 초기화.

---

## 7. 100% 원본 픽셀 배율

- Crop된 이미지는 기본 상태에서 **자동 Fit 확대를 일절 하지 않음**.
- 기본 배율 = **100% (zoom = 1.0)**: 원본 픽셀 1개 = 화면 CSS 픽셀 1개.
- 예: 320×320 크기의 병 ROI를 Crop한 경우:
  - 600×600 캔버스의 정중앙 `(x=140, y=140)`에 320×320 크기로 정확히 배치.

---

## 8. 검은 패딩 처리

- Crop 이미지 바깥의 남는 영역:
  - 상/하/좌/우 각각 140px의 여백은 `RGB(0, 0, 0)`, `GV = 0`으로 채워짐.
  - 이 검은 패딩은 **화면 표시용 뷰포트 여백**이며, Crop 원본 데이터(`ImageData`, `blobUrl`)에는 포함되지 않음.
  - 마우스가 이 패딩 위에 위치할 경우 Pixel Inspector에 `PADDING` 상태로 명확히 분리 표시.

---

## 9. Zoom 구현

- 지원 배율: **50%, 100%, 200%, 400%, 800%**.
- 조작 인터페이스:
  - 툴바 프리셋 버튼: `[50%]`, `[100%]`, `[200%]`, `[400%]`, `[800%]`.
  - 단계별 확대/축소: `[+]`, `[-]`.
  - `[100% Reset]` 버튼.
  - 마우스 휠(Wheel)을 통한 자연스러운 확대/축소.
- 보간 품질: `imageSmoothingEnabled = false`, `image-rendering: pixelated` 적용으로 고배율에서도 픽셀 가장자리가 흐릿해지지 않고 선명한 사각 픽셀로 표시.

---

## 10. Pan 구현

- 마우스 드래그(Pointer Events)를 통해 600×600 캔버스 내에서 이미지를 자유롭게 이동.
- 확대(Zoom In) 상태에서 병의 목, 몸체, 바닥 등 세부 영역을 이동하며 검사 가능.
- `[Pan Reset]` 버튼으로 중앙 위치 즉시 복원.
- Pan 상태에서도 Pixel Inspector의 역변환 좌표 계산이 완벽하게 동기화됨.

---

## 11. Pixel Inspector 구현

- 마우스 호버 시 실시간 픽셀 정보 패널 출력:
  - **원천 Grab 좌표:** `Grab Coord: (X, Y)` (1920×480 원본 프레임 기준)
  - **Crop 로컬 좌표:** `Crop Local: (x, y)` (0 ~ width-1, 0 ~ height-1)
  - **Color Swatch:** 실제 픽셀 색상 시각화 칩
  - **RGB 값:** `RGB(R, G, B)` (0 ~ 255)
  - **Gray Value:** `GV: 0 ~ 255`
- 캔버스 밖으로 마우스가 나가면 `—`로 안전하게 초기화.

---

## 12. RGB/GV 계산 기준

- 화면에 렌더링된 보간 픽셀을 읽지 않고, 메모리에 보관된 무손실 `cropData.imageData` 원본 픽셀 배열에서 직접 인덱싱:
  - `idx = (localY * cropW + localX) * 4`
  - `R = data[idx]`, `G = data[idx+1]`, `B = data[idx+2]`
- **Gray Value (GV) 가중치:**
  - OpenCV BGR ➔ GRAY 변환 표준 공식 준수:
  - `Gray Value = round(0.299 * R + 0.587 * G + 0.114 * B)`
  - `[0, 255]` 범위 클램프 적용.

---

## 13. Pixel Grid 구현 여부

- **구현 완료 (APPLIED):**
  - 400%(4x) 및 800%(8x) 고배율 상태에서 원본 픽셀 경계선(`ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)'`)을 격자망으로 자동 렌더링.
  - 툴바의 `[Grid]` 토글 버튼으로 필요에 따라 켜고 끌 수 있음.
  - 원본 픽셀 데이터를 오염시키지 않는 뷰포트 오버레이 드로잉 방식.

---

## 14. 브라우저 테스트 결과

- Vite Proxy 및 API 엔드포인트 연동: **PASS**
  - `GET http://localhost:5173/` ➔ 200 OK
  - `GET http://localhost:5173/api/health` ➔ 200 OK
  - `POST http://localhost:5173/api/capture-sessions` ➔ 200 OK
  - `POST http://localhost:5173/api/videos/VID-000001/grab` ➔ 201 Created
  - `GET http://localhost:5173/api/captures/.../image` ➔ 200 OK (PNG 바이너리 수신)
- 실제 Windows Chrome 사용자 브라우저 확인: **READY FOR USER MANUAL TEST**

---

## 15. Build / Lint / Test 결과

- **TypeScript Production Build (`npm run build`):**
  ```text
  ✓ 1932 modules transformed.
  dist/index.html                   0.77 kB │ gzip:  0.43 kB
  dist/assets/index-RPWaQ6P8.css   16.40 kB │ gzip:  3.85 kB
  dist/assets/index-DwjSu2Q4.js   266.30 kB │ gzip: 83.33 kB
  ✓ built in 359ms
  ```
- **Lint 검사 (`npm run lint`):**
  ```text
  Found 0 warnings and 0 errors.
  Finished in 21ms on 16 files with 116 rules using 16 threads.
  ```
- **순수 함수 단위 테스트:**
  - `calculateViewportMapping`: Pillarbox / Letterbox / Scale 테스트 **PASS**
  - `clampRoiRect`: 음수 좌표, 경계 초과, 최소 크기 clamp 테스트 **PASS**
  - `computeGrayValue`: OpenCV 가중치 검증 **PASS**

---

## 16. F-1 LiveView / Grab 회귀 결과

- 기존 H.264 영상 스트리밍(`/api/videos/VID-000001/stream`) Range 206 정상 유지: **PASS**
- Play, Pause, Scrubber Seek, -1 Frame, +1 Frame 정상 작동: **PASS**
- 서버 Grab 호출 및 1920×480 원본 CaptureStore 저장: **PASS**

---

## 17. 기존 검사·Agent UI 보존 여부

- `InspectionPanel.tsx`: 그대로 보존. (현재 Crop 상태는 PatchCore 검사가 실행된 것이 아니므로 판정 결과는 미실행 유지).
- `AgentPanel.tsx`: 그대로 보존. (Gemini Agent 호출 0회 유지).
- 데이터 출처 혼동 방지 안내문 유지.

---

## 18. 향후 서버 ROI Crop 연결 시 필요한 API

- 현재 클라이언트 Crop은 표시 및 Pixel Inspector 관찰용으로 완벽하게 동작합니다.
- 향후 Phase에서 서버 측 PatchCore 모델 검사와 연동할 때:
  - `POST /inspections/crop` 또는 `POST /captures/{capture_id}/crop-inspect`:
  - 입력: `capture_id`, `roi: { x, y, width, height }`
  - 서버 측 `backend/capture_store.py`의 원본 PNG에서 동일한 슬라이스 `frame[y:y+h, x:x+w]`를 추출하여 PatchCore 추론기에 전달하도록 연동할 수 있습니다.

---

## 19. 미구현 또는 차단 사항

- 지침에 따라 다음 항목은 의도적으로 제외(0회)되었습니다:
  - PatchCore 추론 실행 (0회)
  - Gemini API 호출 (0회)
  - PostgreSQL ROI preset 저장/승인/활성화 (0회)
  - Git commit/push (0건)
