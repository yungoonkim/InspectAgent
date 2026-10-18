# Day 7 Step 8.1 — 산업현장형 재검사 UX 진행 상황

## 2026-10-19 최종 상태: COMPLETE (코드 및 안전 회귀)

사용자가 새 Capture 6개를 별도 백업하고 서버를 종료한 뒤 구현을 재개했다. 수정 전 port 8000 LISTEN 및 backend.main/Uvicorn/reload 감시 프로세스가 없음을 확인했다. 서버를 직접 시작·종료·재시작하지 않았다.

- **구현 및 오프라인 검증 완료:** 동일 video_id/source_revision/원본 해상도에서 Play/Pause/Seek/Frame Step/Grab/REINSPECT 이후 ROI 유지. 다른 프레임 Grab에 기존 ROI 적용. 명시적 Reset 및 소스 변경 시 무효화. 이전 Frozen Frame·늦은 Grab 응답 차단.
- 같은 녹화 프레임 재획득은 신규 광학 정보가 아님을 안내한다. 서버도 기존 재검사 그룹 안에서 같은 frame_index 또는 Capture PNG SHA256의 재사용을 409로 거부한다. 기존 Capture idempotent 조회는 새 검사로 계산하지 않는다.
- 최초 1회+추가 2회, 동일 제품 확인, 수동 확인 허용 시점, 원본 final_result 및 판정 정책은 변경하지 않았다. 조기 HOLD/수동 확인은 여전히 **미구현·별도 승인 대상**이다.
- 동일 Crop Vision 의견과 새 Capture PatchCore 재검사를 구분했다. Vision LIVE는 비활성이다.
- 최종 안전 회귀: Backend **567 PASS / 0 FAIL / 10 SKIP**, Frontend **39 PASS**, Chrome Mock **50 PASS**(ROI 신규 8 포함), TypeScript/Build/Lint 성공, 기존 lint 경고 6개. 실제 모델/Provider 검증이 아니다.
- 보호 운영 자산 **80개 SHA256 불변**. 이전 사전 감사 86개와 차이 나는 6개는 사용자 서버 종료 전 임시 Capture이며 이번 수정으로 삭제한 것이 아니다. 운영 백업을 수정하거나 세션에 재등록하지 않았다.
- 실제 Gemini/외부 Provider 전송/PatchCore 로드·추론 **0회**. 현재 알려진 실패 테스트는 없다.
- **남은 확인:** 실제 사용자 Chrome UX 확인만 남았다. 재개 복구 세션에서 정적 코드·문서 검토를 마쳤으며, 이번에는 코드를 수정하거나 검증 러너를 다시 실행하지 않았다.

최종 증거: `data/outputs/safe-regression/20261018-225800-d19e47a0/summary.json`, `safety.json`, `protected-before.json` 및 단계별 로그.
구체적 수정 파일·중간 실패 및 재개 절차는 [통합 인계 문서](day7-step8-1-step9-handoff.md)를 참조한다.

---

# 이전 사전 감사 기록 — 아래 BLOCKED는 재개 이전 상태

## 상태: BLOCKED — 운영 서버 자동 재시작 위험, 구현 전 사용자 확인 필요

이번 실행은 읽기 전용 코드·운영 자료 감사와 이 문서 작성까지만 수행했다. ROI UX 운영 코드·테스트·설정을 수정하지 않았고 서버를 종료·재시작하지 않았다. 기존 Step 8의 519 PASS / 10 SKIP, Frontend 34 PASS, Chrome 35 PASS는 **이전 결과**이며 이번 신규 검증 결과가 아니다.

## 1. 실행 환경과 중단 근거

- 점검 시점 서버 PID **22212**, `127.0.0.1:8000` LISTEN.
- 프로세스 명령에서 `backend.main`, `--reload`, `--reload-dir backend`를 확인했다. 인증정보나 전체 명령줄은 출력하지 않았다.
- 현재 임시 Capture PNG는 **6개**다. 기존 백업 3개가 이 새 자료까지 보호한다고 가정할 수 없다.
- `backend/capture_store.py:224`의 `close()`는 관리 중인 PNG를 제거한다. `:61`의 `_directory()`도 저장소 초기화 시 기존 관리 PNG를 정리한다.
- 따라서 백엔드 Python 파일 수정은 자동 재시작과 캡처 소실을 유발할 수 있다. 사용자 확인 전에 백엔드 파일을 수정하지 않는다. 진행 중 화면 상태를 임의로 바꾸지 않기 위해 프론트엔드 수정도 보류했다.

## 2. 원본 캡처 목록과 무결성

원본 디렉터리: `C:\Users\USER\AI-NativeAgent\Project\InspectAgent\data\outputs\captures\`.
아래 Capture ID에 `.png`를 붙인 파일이 각각 존재한다. 서버 Capture API는 TTL 정리를 유발할 수 있어 호출하지 않고 디스크와 기존 검사 provenance를 읽기 전용으로 대조했다.

| Capture ID | 연결 검사 | 프레임 | ROI (x,y,w,h) | PNG SHA256 |
|---|---|---:|---|---|
| CAP-07ffc3e9811145e885686e77fdbe48ba | INSP-001661 | 93 | 986,115,294,284 | 3f10cf9c03c128ca9f0ad5766ec526d970f90ac05aeb666873494cb2e5bfa05b |
| CAP-5bffd678a52d401bb87c71be75299862 | INSP-001662 | 101 | 1058,121,287,276 | 3fa847df73fcb1466a8ecd5db467bd8b3125153fbc0a10df32b46c118db070a0 |
| CAP-6923ec6a277049a081141c201547f4f2 | INSP-001657 | 64 | 751,124,278,272 | 79d445bfca9f64facdcc5a36a2f97dba916c5208ab86716dcb6e05d8e0cbe59f |
| CAP-8f92698205f044738fe3e6eb4c9d453c | INSP-001658 | 52 | 646,124,293,274 | 6dc0fba3322dfab992f40ade76ea07d7b5a2fbf71f1a968f6718948b3146798a |
| CAP-ac74f8548ed442e48eaa6f6bec8a01fa | INSP-001660 | 82 | 895,120,282,280 | 3668e46a5e184ae222da5fc60ef8a807088b391725202bfbdf19ad46e13263a6 |
| CAP-cbebac192ec2405b82b89e893ca55408 | 미확인 / UNKNOWN | UNKNOWN | UNKNOWN | 458f33736f4819904e6e1d6f4096515a82603e3e8cb542739b4f68722e24fe37 |

기존 저장 기록에서 연결이 확인된 5건의 video_id는 VID-000001이다. 마지막 1건은 대응 검사 provenance가 없어 프레임이나 ROI를 추정하지 않았다.

연결 검사 5건의 원본 Capture 해시와 영속 Crop 해시는 모두 저장 provenance와 일치했다. 영속 Crop은 `data/outputs/grab_inspection_inputs/IMG-GRAB-*.png`이며 다음을 확인했다.

| 검사 | 영속 Crop 파일명 | 크기 | SHA256 |
|---|---|---|---|
| INSP-001657 | IMG-GRAB-b46dc76e52d84cfcb6812766eba5c1fd.png | 278×272 | 5c3c31558c6f9de967969900a5a1b94de9d209c9bcf13c2ac95fdc2946ee9d13 |
| INSP-001658 | IMG-GRAB-cf7945be12f745ce8b2781ee7abc25e8.png | 293×274 | 0edcbf416b225541b79a4eb030e4d733fbd037310baab8cc68433e581df9f50b |
| INSP-001660 | IMG-GRAB-15c0c322b0384d8a818604b6d5c64ce0.png | 282×280 | 7bd6ebaf56ac0bbfd7235e754d0b614f4a19f876ef589631554565bea58828ea |
| INSP-001661 | IMG-GRAB-fed9f6ebff4b41818a943cf79609cb03.png | 294×284 | 5285eb1f2b06458af1c41ef55f1ca47e580159880f970ecd746f6e836a07def2 |
| INSP-001662 | IMG-GRAB-5699c22c805f4e268684f25bd071510a.png | 287×276 | 1f0323085b96f81d8c865df5aacff1662e6d75bf7579509e647d377471bffff7 |

점검 기준선은 운영 자산 **86개**다. 캡처 경로 7개 파일은 PNG 6개와 관리 marker 1개이며, 영속 Grab 입력 경로 18개, Anomaly Map 경로 33개, 재검사 이력 경로 2개 파일을 포함한다. 나머지 보호 대상은 기존 검사·로그·모델·보고서·영상·설정 및 보호 코드다. 전체 경로별 해시 증거는 `data/outputs/safe-regression/step8-1-step9-preflight/protected-before.json`에 있다. 이미지나 운영 파일을 새로 복사·이동·삭제하지 않았다.

## 3. 현재 ROI 수명과 실제 동작

근거: `frontend/src/App.tsx:129`, `:141`, `:204`, `:215`, `:273`, `:310`; `frontend/src/components/LiveView.tsx:63` 이후; `RoiOverlay.tsx`와 `utils/coordinateTransforms.ts`.

- 좌표는 원본 이미지 픽셀의 x/y/width/height다. Overlay는 화면 좌표를 원본 좌표로 변환하고 경계를 제한한다.
- Play, Seek, Frame Step, Restart, 프레임 변경은 `invalidateRoiIfActive()`에서 `onToggleRoi(currentFrame, false)`를 호출한다.
- **주의:** App의 `handleToggleRoi()`는 `isPaused=false`이면 경고를 설정하고 바로 반환한다. 따라서 함수 이름만 보고 ROI가 실제 초기화된다고 결론 내릴 수 없다. 숫자 ROI는 남고, 오류 안내 및 이전 Frozen Frame 표시가 유지될 수 있는 흐름이다.
- EDITING 상태의 Grab은 현재 영상에서 재획득하지 않고 기존 동결 Capture를 클라이언트에서 Crop해 APPLIED로 바꾼다.
- APPLIED 상태에서 같은 프레임 Grab은 기존 Crop을 유지하고 신규 Capture를 만들지 않는다.
- 다른 프레임을 Grab하면 Crop을 지우고 ROI 상태를 NO_ROI로 바꾼 뒤 전체 프레임을 획득한다. 숫자 ROI 자체가 즉시 기본값으로 덮어써지는 것은 아니지만, 사용 가능한 ROI/Crop 상태는 해제돼 재적용 동작이 필요하다.
- 검사 결과 REINSPECT 자체가 ROI 사각형을 재설정하지는 않는다. 재검사 안내와 새 프레임 획득 경로의 상태 전이가 반복 ROI 작업을 유도한다.
- 명시적 Reset은 DEFAULT_ROI/NO_ROI로 초기화한다. AUTO 전환도 NO_ROI로 바꾸지만 AUTO 기능은 이번에 변경하지 않는다.

## 4. 변경 예정 계약 — NOT IMPLEMENTED

1. ROI의 기하학적 설정 수명과 동결 Capture/Crop 수명을 분리한다.
2. video_id/source_revision/원본 width/height가 같은 동안 Play/Pause/Seek/Step/Grab/REINSPECT에서 ROI를 유지한다. 키가 달라지거나 경계를 벗어나면 무효화한다.
3. Live 영상 위 ROI와 동결 프레임 편집 표시를 구분한다. ROI를 유지했다고 병을 추적한다고 표현하지 않는다.
4. 사용자가 새 Grab을 명시적으로 선택했을 때만 새 영상을 획득하고, 유효한 기존 ROI를 그 새 Capture에 정확히 적용한다.
5. 녹화 영상의 동일 프레임/동일 이미지 재획득은 새 광학 정보가 아님을 알린다. 같은 PNG에 새 Capture ID만 붙여 유효한 재검사로 표현하거나 기존 재사용 제한을 우회하지 않는다.
6. 같은 저장 Crop에 대한 Vision 보조 의견은 새 Grab·새 PatchCore 추론·새 INSP·재검사 횟수 증가가 없는 별도 동작이다.

## 5. 기존 그룹·수동 결과 확인 및 조기 확인 제안

`RIG-19913ea13eea4501b6d55780e3c72bd4`에서 INSP-001660/001661/001662, 완료 횟수 3, MANUAL_REVIEWED, 별도 MANUAL_NG 기록을 확인했다. 원본 검사 3건은 모두 REINSPECT다. 이 파일을 수정하지 않았다.

`backend/reinspection_store.py`는 3회 완료 후 MANUAL_REVIEW_REQUIRED일 때만 수동 확인을 허용한다. 조기 HOLD나 수동 확인을 허용하도록 변경하지 않았다.

별도 승인 후보는 엔진 결과를 바꾸지 않는 조기 `REQUEST_OPERATOR_REVIEW` 이벤트와 운영자 대기 상태다. 그 요청이 추론 횟수/그룹 종료/기존 HOLD와 어떤 관계인지 먼저 정해야 한다. 현재 HOLD가 수동 확인 결과라는 사실을 유지하며, 조기 보류 요청을 같은 의미로 조용히 추가하지 않는다.

## 6. 이번 검증 및 재개 조건

- 신규 테스트/기존 안전 러너/Chrome/Build/Lint: **미실행**. 아직 구현하지 않았으며 사용자 실행 중 서버·캡처를 건드리지 않았다.
- 실제 Gemini API/Provider 요청, 실제 PatchCore 로드·추론: **각 0회**. 서버 API도 호출하지 않았다.
- 운영 JSONL·재검사·수동 확인·모델·기존 백업·PostgreSQL: 수정 없음.
- 작성 파일: 이 문서와 Step 9 사전 감사 문서. 해시 증거는 별도 안전 점검 디렉터리다.

재개 전에는 **현재 새 PNG 6개**를 기존 백업과 구분되는 새 외부 디렉터리에 덮어쓰기 없이 백업하고 SHA256·연결 메타데이터를 검증하는 절차가 권장된다. 외부 백업은 아직 실행하지 않았다. 사용자 확인 후 사용자가 서버를 정상 종료해야 한다. 필요한 화면 상태를 먼저 기록하고, 세션은 종료 후 복구되지 않을 수 있음을 유의한다.

백업·종료 확인을 받기 전에는 실제 Chrome 신규 동작 검증이나 소스 변경을 진행하지 않는다.
