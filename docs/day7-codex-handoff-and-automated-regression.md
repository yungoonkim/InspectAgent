# Day7 Step4 Codex 인수인계 및 안전 자동 회귀 검증

작성일: 2026-10-18. 발표 예정: 2026-10-20.

## 1. 결론

**인수인계 감사·재현 결함 수정·안전 러너 구축: COMPLETE. 최종 실행: PASS WITH SKIP.**

- Backend: **303 PASS / 0 FAIL / 10 SKIP**, 7.81초.
- Frontend Node TAP: **21 PASS / 0 FAIL / 0 SKIP**, 118.5229ms.
- 실제 설치된 Chrome의 격리 Mock ImageView E2E: **12 PASS / 0 FAIL / 0 SKIP**.
- TypeScript / lint / production build: 종료 코드 0. lint 경고 6건은 남아 있다.
- 운영 보호 대상 26개 파일 전후 SHA256 및 파일 집합 동일.
- 실제 PatchCore checkpoint 로딩·추론 **0회**, 실제 Gemini 요청 **0회**, PostgreSQL 접속·변경 **0건**.

이것은 **실제 모델 품질, 실제 결함 위치 정확도, 전체 애플리케이션 E2E, Cloud Run 배포의 승인**이 아니다. Normalize/Calibration 및 threshold 34.1442 문제는 변경하지 않았다. 전체 pytest도 실행하지 않았다.

최종 증거 디렉터리:

`data/outputs/safe-regression/20261018-150637-041356f2/`

`summary.json`, `backend.xml`, `pytest.log`, `safety.json`, `protection.json`, 각 단계 로그 및 `browser/step4-browser-8AaTBE/result.json`에 실제 결과가 있다. Chrome 버전은 **Chrome/155.0.8059.82**다. 테스트 결과·임시 합성 이미지·새 Chrome 프로필은 이 격리 출력 아래에만 생성했다. 원본 MVTec 이미지를 복제하지 않았다.

## 2. 작업 전 상태와 범위

루트 AGENTS.md, AUTO/MANUAL 확정 명세, 기술 스택 문서, Step4 보고서, 기존 전처리 감사 및 현재 구현을 확인했다. backend/frontend/tests/scripts/docs 하위에 추가 적용 AGENTS.md는 없었다.

작업 시작부터 Agent API/service, inspection.py, main.py, App, InspectionPanel, AgentPanel, ImageView, CSS 등에 Gemini의 미커밋 변경이 있었고 Sidecar 모듈·Step4 테스트도 미추적 상태였다. **Git HEAD와의 전체 diff를 이번 Codex 수정으로 간주하지 않는다.** 시작 시 287개 기존 파일을 해시로 기록하고 비교했다. 기존 파일 중 이번 범위의 5개만 변경됐고 나머지 282개는 동일하며 삭제는 없었다.

병렬로 새로 나타난 Gemini QA/발표 문서도 수정하지 않았다. `.tmp_measurement_regressions`, 기존 잠금/READY, PPT, 기존 E2E 기록을 보존했다. Git add/commit/push/reset/restore/clean은 모두 0건이다.

## 3. 실제 Step4 코드 확인 A–L

| 항목 | 독립 확인 결과 | 근거·제한 |
|---|---|---|
| A. 동일 predict 결과에서 score/map | CONFIRMED | `backend/ml/patchcore_inferencer.py:159`의 단일 model 호출 반환에서 score/map 추출. `backend/inspection.py:514`의 동일 pred를 사용. 실제 모델 실행 대신 Mock 호출 수 검증 |
| B. capture_anomaly_map=false | PASS | `backend/main.py:170` 기본 False. 기존 요청 필드만 보내도 201, Mock predict 1회, Sidecar 없음. 기존 판정 함수 변경 없음 |
| C. 900×900 ↔ 256×256 | PASS, 표시 기하학 범위 | 비대칭 피크·픽셀 중심·실제 PNG 크기·원본과 동일 Canvas draw rectangle 검증. 결함 위치의 정확도 PASS는 아님 |
| D. 전체 공간 전처리 | CONFIRMED, 정적 범위 | 외부 Resize 및 내부 export_transform/모델 코어/맵 생성 코드와 공식 checkpoint 구성 확인. 아래 5절 참조 |
| E. 검사/이미지/크기 연결 | 수정 후 PASS | API에서 기존 InspectionRecord의 inspection_id, image_id, metrics width/height와 대조. 고아/다른 이미지/다른 크기의 맵은 404 |
| F. 부분 저장·불일치 | 결함 재현, 보완 후 PASS | 기존 개별 replace와 덮어쓰기 위험을 commit-last·no-clobber·rollback·체크섬 검증으로 보완. 강제 전원 차단 내구성은 미검증 |
| G. GET의 읽기 전용성 | 결함 재현, 보완 후 PASS | 누락 PNG를 GET이 재생성하던 동작 제거. 디렉터리도 생성하지 않음. 실제 모델 진입·운영 쓰기 차단 하에서 조회 검증 |
| H. 동일 Zoom/Pan | PASS | 실 ImageView Canvas drawImage의 원본/Overlay 목적 사각형이 100/200/400/800/1600/3200/4000% 및 실제 포인터 Pan 후 동일 |
| I. Inspector 원본 RGB/GV | PASS, 합성 표본 | Heatmap ON/투명도 변경 후 RGB(20,40,60), GV36 유지. 원본 offscreen ImageData 사용 |
| J. INSP-001391 가짜 맵 | 수정 후 PASS | 저장/조회 거부 및 프론트 fixture 판별. LIVE provenance를 붙여도 해당 ID에는 맵 요청·표시 안 함 |
| K. Map 없는 과거 검사 | PASS | 메타데이터/PNG 모두 404 MAP_NOT_AVAILABLE. 브라우저 토글 비활성, 자동 생성·재추론 없음 |
| L. 늦은 Heatmap 응답 | 수정 후 PASS | 검사·이미지 ID를 렌더 단계부터 묶고 이전 JSON/PNG/오류 콜백을 무효화. 늦은 static PNG도 새 이미지 덮어쓰기 금지 |

## 4. Gemini 보고서와 불일치 및 수정

### 4.1 재현 증거

수정 전 `data/outputs/safe-regression/reproduce-03/backend.xml`에서 다음 **6 FAIL**을 재현했다.

1. PNG를 제거한 뒤 GET하면 PNG가 새로 생겼다.
2. 같은 ID를 다시 저장해도 기존 bundle을 덮어썼다.
3. JSON inspection_id가 요청 ID와 달라도 그대로 반환했다.
4. 앞 공백, 뒤 공백, 마지막 개행이 붙은 ID 3종을 허용했다.

추가 검토에서 API의 InspectionRecord 대조 누락, bundle 전체 원자성 부재, 프론트 metadata/실 PNG 크기 대조 누락과 stale render 위험을 확인했다. 초기 격리 러너 자체의 실패도 숨기지 않았다: 하드코딩된 상대 Agent 보고서 경로의 쓰기를 안전 가드가 차단했고, cwd 격리 후 운영 저장 보고서를 기대하던 2개 테스트가 404로 실패했다. 운영 코드는 바꾸지 않고 테스트용 합성 보고서를 격리 cwd에 준비해 해결했다.

### 4.2 Backend 변경

- `backend/anomaly_map_store.py:47`: ID별 exclusive lock, 임시 bundle 작성, 기존 파일 존재 시 저장 거부, hard-link no-clobber 게시, **JSON을 마지막 commit marker로 게시**. 정상 예외 시 이번 호출이 게시한 파일만 rollback한다.
- `backend/anomaly_map_store.py:121`: ID, neutral image ID, schema, 공간 메타데이터, 파일명/크기/shape/dtype/finite 및 PNG 디코딩을 검증한다. NPZ는 allow_pickle=False, 압축 해제 크기 제한을 적용한다. 신규 schema 1.1.0은 NPZ/PNG SHA256을 필수 검증한다.
- 완전하고 유효한 1.0.0 bundle은 읽기만 지원한다. 누락·변조·불완전 bundle을 고쳐 쓰지 않고 unavailable로 처리한다.
- `backend/main.py:659`, `backend/main.py:687`: 메타데이터와 기존 검사 ID/이미지 ID/원본 크기를 연결한다. PNG endpoint도 같은 연결을 확인한다.
- threshold가 없는 저장 요청에는 null을 유지한다. 임의로 34.1442를 Sidecar에 만들어 넣지 않는다. 운영 threshold 자체는 그대로다.

**보고 정정:** 저장은 현재도 동기 호출이다. 기존의 개별 임시 파일 replace가 3개 파일 전체의 원자적 트랜잭션을 뜻하지 않았다. 이번 commit-last 설계도 DB ACID나 fsync 기반 전원 차단 내구성을 의미하지 않는다. 프로세스 강제 종료 시 부분 파일/lock이 남아 unavailable이 될 수 있으며 자동 덮어쓰기·GET 복구 대신 별도 확인이 필요하다. hard-link 지원이 없는 파일시스템에서는 저장이 안전하게 실패하고 판정은 보존된다.

### 4.3 Frontend 변경

- `frontend/src/utils/step4ImageState.ts:19`: Mock fixture 판별, 검사/이미지 identity 비교, metadata와 실제 원본/PNG 크기 대조, 비동기 취소 처리를 분리했다.
- `frontend/src/components/ImageView.tsx:121`: 기존 이미지·Inspector·Heatmap 상태를 실제 선택 소스와 연결한다. effect cleanup 전 렌더에서도 이전 검사의 이미지/맵을 재사용하지 않는다.
- source·loading·overview/focus 전환으로 Canvas가 재생성돼도 그리기와 wheel handler가 다시 연결되게 보완했다.
- 기존 원본과 Overlay의 동일 목적 사각형 그리기, Pixel Inspector의 원본 데이터 조회 방식은 유지했다. UI 전체 재설계는 하지 않았다.

## 5. 공간 정합성 근거와 한계

### 5.1 전체 실제 소스 경로

```text
cv2.imread → BGR ndarray
→ wrapper.predict: BGR→RGB / PIL
→ 외부 Resize(256,256) / ToImage / float32 scale / Normalize
→ 전체 AnomalibModule.forward
→ PreProcessor.forward → export_transform
→ 내부 Resize(256,256) / Normalize
→ PatchcoreModel.forward → 특징 추출·embedding·거리
→ anomaly map interpolate(input spatial size) / Gaussian blur
→ post_processor → wrapper가 반환한 2D map
→ Sidecar의 원본 크기 RGBA PNG
→ ImageView의 원본과 동일한 drawImage 목적 사각형
```

설치 환경의 다음 소스도 읽었다. 아래 SITE는 vision-insight 환경의 Lib/site-packages다.

- `backend/ml/patchcore_inferencer.py:58`, `backend/ml/patchcore_inferencer.py:159`: 외부 Compose와 단일 forward.
- `SITE/anomalib/models/components/base/anomalib_module.py:246`: pre_processor → core → post_processor.
- `SITE/anomalib/pre_processing/pre_processor.py:98`, `SITE/anomalib/pre_processing/pre_processor.py:151`: exportable transform 생성과 실제 호출.
- `SITE/anomalib/pre_processing/utils/transform.py:51`: Resize antialias 비활성화 및 존재하는 CenterCrop 변환. 이 유틸리티가 CenterCrop을 지원한다는 사실과 **현재 설정에 Crop이 있다는 주장**은 다르다.
- `SITE/anomalib/models/image/patchcore/torch_model.py:116`, `:158`: tiler 기본 None. 코드상 tiler가 있다면 분기할 수 있으나 wrapper가 이를 설정하지 않는다.
- `SITE/anomalib/models/image/patchcore/anomaly_map.py:61`: 입력 크기 업샘플과 Gaussian blur. 특징 반응 자체가 공간적으로 퍼지므로 결함 마스크와 같지 않다.

공식 checkpoint는 **모델 객체 생성/torch.load/pickle 실행 없이** ZIP의 data.pkl opcode만 다시 읽었다. SHA256은 `4b239d28e72c63bf782cd1d31981d7f4362c591e7c23164e4c0ac8b5e99b52a3`다. opcode 위치 25161 이후 pre_processor 설정은 Compose, Resize [256,256], bilinear, Normalize이고 CenterCrop/Pad/Flip 설정이 없다. export_transform 생성의 antialias 차이는 공간 Crop/Pad/Flip 추가가 아니다.

이 근거는 공식 파일·현재 소스의 정적 계약이다. **현재 별도 실행 중인 서버의 메모리 모델이나 환경변수로 교체된 checkpoint의 동적 transform까지 검증한 것은 아니다.** 실제 checkpoint 로딩 없이 그 한계를 넘어 PASS라고 하지 않는다. Normalize 중복은 별개 문제로 그대로 남아 있다.

### 5.2 픽셀 경계와 실제 테스트

픽셀 edge 좌표는 half-open 범위로 대응하고, map 픽셀 중심은 다음과 같이 대응한다.

```text
original_center = (map_index + 0.5) * original_size / map_size - 0.5
```

기존 보고의 `index*900/256`은 edge와 픽셀 중심을 구분하지 않는다. 900×900만 보는 대칭 중심 테스트로 x/y 전치나 비정사각 비율 오류를 충분히 검출할 수 없다.

`tests/test_anomaly_map_regression.py:96`은 map[y=57,x=203]의 비대칭 피크를 실제 저장·PNG 디코딩하여 **900×900 / 640×360 / 1920×480** 모두 검사한다. x/y 방향, 원본 PNG shape, raw NPZ 좌표와 픽셀 중심 기대값 대비 피크 오차 ≤1.1 pixel을 확인했다. 이것은 보간된 이산 샘플의 검사 허용치이지, 실제 결함 위치 오차가 1.1 pixel 이하라는 의미가 아니다. 사각형 원본은 x/y 축별 비율이 다르므로 신규 메타데이터는 axis_aligned_resize다.

Chrome에서는 실제 ImageView의 Canvas drawImage 호출을 관측하여 원본/Overlay 목적 사각형이 전 줌 preset 및 실제 CDP 포인터 Pan 후 일치하는지 확인했다. 투명도 변경과 RGB/GV 불변성도 실제 캔버스 픽셀로 확인했다. 합성 map·합성 정적 이미지에 대한 **표시 변환**의 검증이며, 실제 모델의 localization 품질이나 원본 해상도 수준의 결함 검출 능력은 NOT TESTED다.

Gemini 보고의 ‘원본 raw feature-distance map’, ‘1픽셀도 오차 없음’, ‘100% 보장’은 근거 범위를 넘는다. 실제 반환 map에는 내부 post_processor가 관여할 수 있고 저장 시 float32 변환·NaN/Inf 치환도 수행한다. 이는 Ground Truth가 아닌 현 모델의 상대적 반응 시각화다.

## 6. 안전 자동화 러너

기본 명령:

```powershell
.\scripts\run_safe_regression.ps1
```

이번 Windows 세션은 실행 정책 때문에 위 직접 실행이 PSSecurityException으로 차단됐다. 시스템 정책을 변경하지 않고 **해당 자식 PowerShell 프로세스에만** 적용한 실제 실행 명령은 다음과 같다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_safe_regression.ps1
```

Python과 Chrome이 기본 위치에 없으면 `-Python <vision-insight-python.exe> -Browser <기존-chrome.exe>`로 지정할 수 있다. 설치·다운로드·시스템 PATH 변경은 하지 않는다.

`scripts/run_safe_regression.ps1:21`은 각 외부 프로세스 종료 코드와 pytest XML/Node TAP/브라우저 JSON을 확인한다. 결과 누락·안전 가드 위반도 FAIL이다. 실패가 하나라도 있으면 exit 1, 필수 성공과 명시적 제외가 함께 있으면 **PASS WITH SKIP**, 제외 없이 모두 성공했을 때만 PASS다. 초기 실제 실패 실행에서도 exit 1을 확인했으며 실패를 ALL PASS로 덮지 않았다.

### 6.1 Backend 격리

`scripts/safe_regression_backend.py:37`은 실행별 고유 디렉터리와 환경변수로 JSONL, map, capture, video, test-data, temp, matplotlib 출력 등을 격리한다. `.env` 자동 로딩을 끄고 실제 DB URL/API key 설정을 전달하지 않는다.

- 실제 checkpoint 대신 로드 불가능한 stub 파일을 지정하고 model loader를 SKIP, 실제 predict를 AssertionError로 차단한다.
- MVTec/test_data/models/private 경로 읽기·목록 조회, 실제 checkpoint 열기, 실행 디렉터리 밖 파일 쓰기·삭제·이동을 Python audit hook으로 차단한다.
- 실제 네트워크/DB socket connect, HTTPX 실제 전송, genai.Client 생성을 차단한다. ASGI/MockTransport만 사용한다. Windows asyncio의 표준 socketpair self-pipe는 허용한다.
- 기존 Agent의 상대 저장 경로도 고유 실행 cwd 안으로 들어가게 한다. 운영 보고서 파일을 읽지 않고, 필요한 두 ID의 응답은 명시적 SYNTHETIC_TEST_ONLY fixture로 준비한다. 실제 저장 보고서의 내용 검증으로 해석하지 않는다.
- `tests/safe_image_api_fixtures.py:9`는 관련 Step4/이미지 API 테스트 자체에도 합성 900×900 이미지·Registry·JSONL·map·Mock-only predictor를 제공한다. 해당 테스트를 직접 선택하더라도 운영 Registry/JSONL을 사용하지 않는다.

최종 safety.json의 forbidden_io/network/real_prediction/real_load는 모두 0이다. 이 가드는 테스트 프로세스의 Python 경로를 보호하는 다층 장치이지 악의적 native 코드까지 막는 OS 보안 경계라는 주장은 하지 않는다.

### 6.2 Browser 격리

기존 Chrome, 신규 임시 프로필, localhost 임시 Vite middleware와 실제 ImageView 컴포넌트를 사용한다. 설정 파일 및 .env를 읽지 않는 configFile:false/envFile:false 구성이다. 합성 Image/metadata 응답만 허용하며 실제 백엔드로 proxy하지 않는다. 서버도 모든 API 요청·POST를 거부한다.

샌드박스 내부 실행에서는 Chrome GPU subprocess가 종료돼 CDP timeout이 발생했다. 승인된 샌드박스 외부 실행에서 확인했으며 GPU 보호를 해제하는 임의 옵션이나 브라우저 설치로 우회하지 않았다. 외부 호스트 해석을 차단하고 localhost/127.0.0.1만 허용했다. 기존 개인 프로필·서버 프로세스를 건드리지 않고 이번에 생성한 브라우저/서버만 종료한다.

콘솔에는 Vite client의 **CSP에 의해 차단된 localhost HMR 연결** 및 Canvas readback 성능 안내가 기록된다. 애플리케이션 예외·실제 API 전송 성공으로 숨기지 않았다. 테스트용 HMR 잡음이며 운영 페이지 콘솔이 깨끗함을 입증한 결과는 아니다.

## 7. 실제 실행 명령과 결과

### 7.1 최종 러너가 호출한 그룹

```text
vision-insight/python.exe -B scripts/safe_regression_backend.py snapshot --output <RUN>
vision-insight/python.exe -B scripts/safe_regression_backend.py backend --output <RUN>
node --test --test-reporter=tap frontend/scripts/test_image_transform.mjs frontend/test_f31_units.js frontend/scripts/test_step4_regression.mjs
frontend/node_modules/.bin/tsc.cmd -b
npm.cmd run lint
npm.cmd run build
node frontend/scripts/test_step4_browser.mjs <기존 Chrome 절대경로> <RUN>/browser
vision-insight/python.exe -B scripts/safe_regression_backend.py verify --output <RUN>
```

backend helper는 아래 11개 파일에 대해 `pytest -q -rs --tb=short -p no:cacheprovider --basetemp <RUN>/pytest --junitxml <RUN>/backend.xml --log-file <RUN>/pytest.log`를 실행한다.

| Backend 모듈 | PASS | FAIL | SKIP |
|---|---:|---:|---:|
| test_inspection_anomaly_map | 9 | 0 | 0 |
| test_anomaly_map_regression | 30 | 0 | 1 |
| test_inspection_image_file | 8 | 0 | 0 |
| test_inspections | 4 | 0 | 7 |
| test_storage | 6 | 0 | 2 |
| test_agent_tools | 76 | 0 | 0 |
| test_agent_service | 81 | 0 | 0 |
| test_agent_day5_counterexamples | 36 | 0 | 0 |
| test_agent_reporting_integration | 30 | 0 | 0 |
| test_day7_step2_agent_offline_mock | 13 | 0 | 0 |
| test_agent_day7_error_observability | 10 | 0 | 0 |
| **합계** | **303** | **0** | **10** |

SKIP 10건: Windows symlink 생성 권한 부재 1, 실제 모델 로딩 제외 6, 모델 실행 선행 데이터가 없는 구형 검사 조회 테스트 1, 실제 데이터셋이 없는 storage workflow 2. 이들을 PASS로 바꾸지 않았다. PostgreSQL/전체 모델 통합/E2E 실제 Gemini 테스트는 선택하지 않았다. pytest 경고 1건은 사전 import된 anyio의 assert-rewrite 경고다.

추가 집중 검증: `focused-standalone-01`에서 Sidecar/이미지 API 3개 파일 **47 PASS / 0 FAIL / 1 SKIP**, 4.25초. 저장 실패·중복·동시 게시·legacy 읽기·체크섬·공간 metadata 변조·Mock predict 1회·판정 보존·path traversal 검증을 포함한다.

Frontend 21 TAP case는 신규 helper/실 좌표 유틸 테스트 19개와 기존 스크립트 파일 2개의 Node test 집계다. 기존 스크립트 내부 console 문구의 테스트 개수를 더하여 중복 집계하지 않았다. 기존 GV 단순 수식 복제 테스트에만 의존하지 않고 생산용 computeGrayValue/ROI mapping/clamp 및 실제 ImageView를 추가 검증했다. 모든 RGB 조합에서 OpenCV 정수 구현과 bit-identical임을 주장하지 않는다.

품질 명령은 TypeScript 0 error, build 성공(최종 Vite build 388ms), lint exit 0이다. lint는 AgentPanel의 기존 effect 경고 1건과 ImageView의 state-in-effect/exhaustive-deps 경고 5건이 남는다. 무관한 Agent 코드를 수정하거나 lint 규칙을 약화하지 않았다.

### 7.2 실제 Chrome Mock E2E 12개

1. 실제 Canvas에 Heatmap 표시, 원본 Pixel Inspector 유지.
2. 투명도 변경에 따른 Canvas 픽셀 변화 및 원본 RGB/GV 불변.
3. 100~4000% 전 preset과 포인터 Pan 후 원본/Overlay 실제 목적 사각형 동일.
4. 저장 OK/NG/REINSPECT 표시가 서버 fixture 값과 동일.
5. 새 검사 이미지 로딩 중 이전 화면 숨김, 다른 image_id metadata 거부.
6. 늦게 도착한 JSON/정적 PNG/Overlay PNG가 최신 검사 덮어쓰기 금지.
7. 원본 크기와 PNG 실제 크기 각각의 불일치 차단.
8. Map 없는 과거 검사 404 및 토글 비활성.
9. Mock NG는 LIVE provenance가 붙어도 map 요청 차단.
10. loading 뒤 Canvas 재생성과 native wheel 동작.
11. Capture overview → focus 전환 후 원본 합성 crop 이미지 복귀.
12. 금지 API/POST가 mock 경계를 통과하지 않음.

LiveView 영상 재생·실제 Grab·ROI editor 전체를 이 Mock E2E로 검증했다고 하지 않는다. 마지막 소스 전환은 합성 capture/crop props로 검증했다. 사용자 Chrome에서 이미 확인한 Step3/3.1 결과도 이번 신규 실행으로 합산하지 않았다.

## 8. 운영 자산과 판정 보호

운영 fingerprint 대상은 .env, 공식/기존 실험 checkpoint와 metadata, threshold/전처리/decision 소스, data 직속 JSONL, 운영 logs/Agent 보고서/영상/Sidecar의 파일 집합이다. 최종 26개 파일은 unchanged:true다. 해시 계산은 파일 bytes 읽기이며 모델 역직렬화·실행이 아니다. 등록된 MVTec 원본 픽셀이나 Ground Truth는 해시 목적으로도 읽지 않았다.

- 원본/모델/threshold/Normalize/Calibration/결정적 final_result: 변경 없음.
- 기존 운영 JSONL/Agent Evidence/기존 Sidecar: 추가·수정·삭제 없음.
- 실제 모델 로딩/forward: 0회. Mock predict만 검사 요청별 1회.
- 실제 Gemini: 0회. 운영 검사 API에 자동 요청: 0회.
- PostgreSQL 접속/migration/Docker 조작/Volume 변경: 0건. ROI 데이터는 조회하지도 않았다.
- 외부 Ground Truth 및 evaluation_private 접근·목록 조회: 0건.
- 기존 H.264/VideoFileSource/CaptureStore/기존 캡처 PNG: 수정 없음.

Mock 실패 주입 시 score45/threshold34.1442/NG/COMPLETED가 유지되고 predict는 1회였다. 이 검증은 Sidecar 실패가 기존 판정을 변조하지 않는다는 뜻이지, 실제 모델 NG가 타당하다는 검증은 아니다.

기존 전체 pytest 수치는 과거 실행 기록이다. 이번 선택 회귀 303 PASS를 전체 pytest 결과 또는 전처리 문제 해결로 표현하지 않는다.

## 9. 이번 생성·수정 파일

기존 작업 상태 위 최소 수정 5개:

- `backend/anomaly_map_store.py`: Sidecar 게시·무결성·읽기 전용 조회.
- `backend/main.py`: Sidecar와 InspectionRecord의 identity/크기 연결.
- `frontend/src/components/ImageView.tsx`: stale source/map 차단, 크기 검증, remount 처리.
- `tests/test_inspection_anomaly_map.py`: 격리 fixture 사용 및 유효한 검사-record seed.
- `tests/test_inspection_image_file.py`: 기존 운영 이미지 대신 독립 합성 fixture 사용.

신규 8개:

- `scripts/run_safe_regression.ps1`: 단일 명령 러너·정확한 집계·실패 종료 코드.
- `scripts/safe_regression_backend.py`: 오프라인 격리·Mock-only 가드·자산 fingerprint.
- `tests/safe_image_api_fixtures.py`: 독립 API fixture.
- `tests/test_anomaly_map_regression.py`: 신규 31개 사례.
- `frontend/src/utils/step4ImageState.ts`: identity/metadata/비동기 수명 관리.
- `frontend/scripts/test_step4_regression.mjs`: 신규 19개 Node 단위 사례.
- `frontend/scripts/test_step4_browser.mjs`: 설치된 Chrome의 Mock ImageView E2E.
- 본 보고서.

이외 고유 run 출력과 무시되는 frontend dist/빌드 캐시가 생성됐다. 기존 산출물을 삭제하지 않았다. 이번 파일만 git diff --check 및 신규 파일 no-index --check로 확인했으며 공백 오류는 없었다. LF/CRLF 안내는 공백 오류와 구분했다.

## 10. 사용자의 Chrome 수동 확인 순서

1. 현재 사용 중인 서버를 강제 종료하지 말고 변경 소스를 반영한 개발 서버인지 먼저 확인한다.
2. 기존 저장 검사를 조회하여 해당 image_id/inspection_id와 원본 해상도를 확인한다. Map 없는 검사는 비활성 안내가 정상이다.
3. INSP-001391 Mock NG에서 판정/fixture 표시는 유지되고 Heatmap은 비활성인지 확인한다.
4. 이미 유효한 map이 있는 검사만 조회하여 ON/OFF, 10~100% 투명도, 100~4000% 확대·Pan·Reset을 확인한다.
5. 동일 원본 픽셀에서 Heatmap ON/OFF에도 RGB/GV가 같은지 확인한다. 빠른 검사 전환 시 이전 이미지/맵이 재출현하지 않아야 한다.
6. Capture/Registered 전환 및 overview/focus를 확인한다. 원본 PNG가 ROI/픽셀 조회의 기준이다.
7. 실제 신규 map 생성은 **사용자가 별도로 실제 검사 실행을 선택하는 단계**다. Codex 러너는 Inspect/Gemini 버튼을 운영 서버에서 누르지 않는다. 새 모델 실행 결과의 공간 위치를 검증된 결함 정답으로 해석하지 않는다.

## 11. 발표 전 남은 위험과 종료

- 기존 Normalize/Calibration/threshold 신뢰성 문제는 UNRESOLVED다. 이번 작업에서 변경·재계산하지 않았다.
- 실제 모델의 score/map 동시 반환은 코드와 Mock으로 확인했으며 새 실제 모델 실행 및 defect localization 품질 검증은 하지 않았다.
- InspectionPanel의 검사 결과 조회 자체는 요청 순서 역전 방어가 별도로 필요할 수 있다. 이번에는 Step4의 ImageView 내부 stale JSON/PNG를 보완했으며, 패널/Agent 전체의 비동기 흐름을 재설계하지 않았다. 빠른 중첩 조회는 별도 승인·검증 대상이다.
- 원본 image_id가 동일하고 크기도 같은데 실제 원본 bytes를 외부에서 교체하는 경우를 기존 Sidecar metadata만으로 판별할 수 없다. 원본 불변 Registry 계약을 유지해야 한다. 원본 콘텐츠 hash 연결은 후속 검토 사항이다.
- bundle 강제 종료/전원 차단 복구, 특수 파일시스템 hard-link 지원, Windows symlink 공격의 실제 생성 테스트, 운영 인증/배포 환경은 별도 검증 대상이다.
- lint 경고 6건, 테스트 HMR CSP 콘솔 잡음, 선택 회귀의 10 SKIP을 숨기지 않는다. 브라우저 자동화 권한/Windows 실행 정책에 따라 러너 환경 승인이 필요할 수 있다.

**새 기능·실제 모델 검사·Gemini 호출·ROI 연결·Cloud Run 배포로 진행하지 않고 여기서 종료한다. 다음 작업은 사용자 승인을 기다린다.**
