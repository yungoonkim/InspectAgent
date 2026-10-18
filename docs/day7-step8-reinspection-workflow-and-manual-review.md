# Day 7 Step 8 — REINSPECT 감사 및 재검사·수동 확인 설계

## 상태와 범위

**최신 상태: COMPLETE — 사용자 캡처 백업·서버 정상 종료 확인 후 MANUAL 재검사·개발용 수동 확인 구현 및 오프라인 회귀 완료. 실제 PatchCore/Gemini 실행은 별도 승인 대기.**

아래 A~S는 최초 PARTIAL 종료 시점의 감사·설계 기록이다. 당시에는 코드·테스트를 수정하지 않았다. **현재 구현·검증 결과는 T 이후에 기록**하며, A~S의 PROPOSED/NOT IMPLEMENTED 표시는 당시 상태다. 기존 검사 기록·모델·판정 정책은 재개 후에도 변경하지 않았다.

### 구현 적용을 보류한 근거

- 실행 중인 Python 프로세스 PID **28464**에서 `backend.main`, `--reload`, `--reload-dir backend`가 확인됐다. PID는 점검 시점 값이며 이후 달라질 수 있다.
- 운영 `data/outputs/captures/`에 PNG **3개**가 존재한다. 캡처 내용을 추가 생성하거나 삭제하지 않았다.
- `backend/main.py:60`의 lifespan 종료 처리는 `captures.close()`를 호출한다. `backend/capture_store.py:224`의 `close()`는 관리 중인 캡처 PNG를 삭제한다.
- 재시작 후 처음 캡처 저장소에 접근하는 경우에도 `backend/capture_store.py:61`의 `_directory()`가 기존 관리 캡처를 정리한다.
- 따라서 백엔드 Python 파일을 수정하면 자동 재시작을 통해 기존 캡처/세션이 사라질 수 있다. 단순히 서버를 직접 종료하지 않는 것만으로 보호 조건을 충족하지 못한다.
- 사용자에게 필요한 이미지 보존 후 서버를 직접 종료할지, 현재 서버를 유지하고 감사·설계만 받을지 확인을 요청했다. 확인 전에는 자동 재시작을 유발할 파일을 수정하지 않는다.
- **영속 Crop 입력 PNG와 임시 전체 프레임 Capture PNG는 별개**다. 이번에 확인된 재시작 삭제 경로는 후자다. 영속 Crop이 남더라도 기존 세션 소실로 접근이 제한될 수 있다.

## A. REINSPECT 반복 원인 분석

**CONFIRMED:** 영상 품질은 모델 입력 Tensor가 아니라 서버에서 PNG를 읽은 **원본 Crop 전체**에서 계산된다.

호출 경로:

`GrabInspectionRuntime.inspect()` → 원본 프레임의 half-open ROI Crop → PNG 저장 → 요청 전용 ImageRegistry → `execute_inspection_workflow()` → `cv2.imread()` → `analyze_image()` → `analyze_brightness()` → `evaluate_image_quality()` → 별도 PatchCore 추론 → 기존 Decision Layer.

근거:

- `backend/grab_inspection.py:167`: ROI 영역을 그대로 복사한다. Padding, 배경 제외 또는 병 영역 분할을 하지 않는다.
- `backend/inspection.py:410`: PNG를 OpenCV로 읽는다.
- `backend/inspection.py:469`: 원본 이미지의 품질을 분석한다.
- `backend/inspection.py:514`: 이후 동일 원본 이미지를 기존 Inferencer에 전달한다. 모델 내부 Resize/Normalize는 품질 통계 산출 이후다.
- `backend/vision.py:40`: BGR→Gray 변환 후 전체 픽셀의 평균·표준편차·최솟값·최댓값을 계산한다. 평균은 소수점 둘째 자리로 반올림한다.
- `backend/vision.py:240`: 반올림된 평균이 하한보다 작으면 `WARNING_LOW_BRIGHTNESS`다.

어두운 배경과 병 내부 픽셀도 통계에 포함된다. 다만 객체 마스크를 사용하지 않았으므로 각 영역이 평균에 기여한 비율은 **UNKNOWN**이다. 낮은 평균이 실제 조명 장치 고장을 의미하지 않는다.

## B. INSP-001652의 실제 통계와 판정 경로

기존 검사 JSONL 및 해당 검사 로그만 필터링해 조회하고, 연결된 영속 Crop PNG를 읽기 전용으로 디코딩했다. 실제 모델을 로드하거나 추론하지 않았다.

| 항목 | 확인값 |
|---|---|
| 검사 / 제품 | INSP-001652 / ABCD1541 |
| 입력 종류 | LIVEVIEW_GRAB |
| Capture | CAP-3c483952db514e27832d9a69f573672f |
| 원본 영상 / 프레임 | VID-000001 / 59 |
| 원본 크기 | 1920×480 |
| ROI | x=700, y=122, width=284, height=272 |
| 실제 Crop | **284×272**, uint8 BGR 3채널 |
| 모델 입력 크기 기록 | 256×256 |
| 저장 Gray 통계 | mean=59.76, std=26.31, min=22, max=254 |
| PNG에서 재확인한 평균 / 표준편차 | 59.760278583264295 / 26.309855723017 |
| Gray=0 비율 | 0% |
| Gray<32 비율 | 약 7.8306% |
| 당시 품질 하한 | **125.0** — ANALYSIS_COMPLETED 로그 설명의 수치로 확인 |
| 이상 점수 / 고정 임계값 | 40.16313171386719 / 34.1442 |
| 모델 기본 결과 | NG |
| 품질 | WARNING_LOW_BRIGHTNESS |
| 파이프라인 / 추론 상태 | COMPLETED / COMPLETED |
| 최종 판정 / 사유 | REINSPECT / IMAGE_QUALITY_WARNING |

Crop SHA256: `8eaca8529474f2493b2e854937186dc4ed34afabaa3a561cd036a1a4da8ca2a7`. 저장된 provenance의 해시와 일치했다.

사용자 설명의 약 286×272와 달리 실제 저장 크기는 **284×272**다. 새 검사 결과가 아니라 기존 검사와 원본 픽셀의 감사 결과다.

**CONFIRMED:** `59.76 < 125.0`이 경고의 직접적인 수치 조건이다. 코드 경로상 Padding은 없고, 해당 Crop의 Gray 최솟값도 22여서 검은색 0 Padding으로 평균이 낮아졌다는 근거는 없다.

임계값 출처는 `backend/config.py:74`의 설정값이며 환경설정으로 바꿀 수 있다. 기존 `data/baseline_brightness.json`의 정적 이미지 집계 평균은 136.34다. 이 기록과 설정 주석은 정적 Bottle 밝기 범위에 맞춘 개발 정책임을 뒷받침하지만 **125.0 자체를 도출한 공식 계산식이나 영상 Crop 검증 기록은 확인되지 않았다**. 당시 하한은 로그로 확인됐으나 당시 상한은 이 저밝기 분기의 로그만으로 확정하지 않는다.

## C. NG와 REINSPECT 우선순위

`backend/decision.py:28`의 정책을 변경하지 않았다.

1. 파이프라인 실패 → ERROR.
2. 영상 품질이 NORMAL이 아님 → REINSPECT. 기본 모델 NG보다 우선한다.
3. 모델 미완료 또는 UNKNOWN → REINSPECT.
4. 품질 NORMAL + 기본 모델 NG → NG.
5. 품질 NORMAL + 기본 모델 OK → OK.

정상/불량의 실제 정답과 무관하게 저밝기 조건이면 두 경우 모두 REINSPECT가 될 수 있다. 이번에는 제품의 실제 정답을 확인하지 않았다. Heatmap의 붉은색도 결함 확정 근거가 아니다.

**주의:** 기존 코드에서는 모델 추론 실패가 파이프라인 전체 FAILED와 다를 수 있으며 REINSPECT/DEFECT_DETECTION_UNAVAILABLE로 저장될 수도 있다. 재검사 횟수는 final_result만 보고 증가시키면 안 된다.

## D. 추가 개발 및 수정 파일

이번 작성 파일은 이 보고서뿐이다. 기존 운영 코드와 테스트는 변경하지 않았다. 테스트 산출물은 `data/outputs/safe-regression/step8-audit-20261018/`에만 생성했다.

후속 최소 변경 후보:

- 신규 `backend/reinspection_store.py`: 그룹·요청 예약·별도 수동 확인 이력의 영속 저장과 OS 파일 잠금.
- 신규 `backend/reinspection_api.py`: 세션/Origin/CSRF 보호 조회·재검사·수동 확인 계약.
- `backend/grab_inspection.py`, `backend/main.py`: 기존 추론 경로 재사용과 그룹별 실행 예약 연결. 엔진·정책은 변경하지 않는다.
- `frontend/src/api/inspection.ts`, 관련 타입, `GrabInspectionPanel.tsx`: 그룹 복원·카운터·명시적 동일 제품 확인·수동 확인.
- `InspectionPanel.tsx`: 현재 결과의 출처와 정적 이미지 입력 컨트롤의 출처 표시를 분리.
- 신규 격리 테스트 및 기존 안전 러너의 추가 테스트 등록.

## E. 그룹 및 검사 이력 연결 — PROPOSED

서버 발급 불투명 그룹 ID, 최초/현재/parent inspection_id, product_id, 적용 영상/revision, 각 Capture/frame/ROI, 시도 번호, 최대 횟수 3, 결과 스냅샷, 워크플로우 상태를 **별도 저장소**에 둔다. 기존 Inspection JSONL 과거 행은 변경하지 않는다.

같은 product_id 문자열을 같은 물리적 병으로 간주하지 않는다. 재검사 시 사용자의 `same_product_confirmed=true`, 현재 parent 검사 ID와 예상 그룹 버전, 새로운 Capture ID를 요구한다. 서버는 제품·영상·revision·소유 범위를 재검증한다. 실제 물리적 동일성은 사용자 확인이며 자동 추적 검증이 아니다.

INSP-001652를 최초 검사로 편입하는 기능을 구현한다면, 세션 소유권과 원본 provenance 확인 및 사용자 명시적 선택 후 별도 링크만 생성해야 한다. 기록을 소급 수정하거나 이미 만료된 캡처를 새 캡처로 위장하지 않는다.

## F. 최초 1회 + 추가 2회 제한 — NOT IMPLEMENTED

완료된 시도 1~3만 계산한다. 각 시도는 신규 inspection_id를 갖는다. 성공적으로 저장된 검사와 로그, COMPLETED 파이프라인·모델 상태, 유한한 anomaly_score를 확인한 후에만 완료 횟수를 증가시킨다.

- REINSPECT이고 3회 미만: 새로운 Capture/ROI로 다음 시도 허용.
- OK/NG: 그룹 종료, 추가 재검사 거부.
- 3회 모두 REINSPECT: MANUAL_REVIEW_REQUIRED로 전환.
- ERROR/추론 실패/API 실패: 완료 횟수 증가 없음. 별도 실패 시도/예약 정보는 보존한다.
- 조회·Heatmap·Gemini·새로고침은 검사 실행이 아니므로 횟수에 포함하지 않는다.

새 그룹 시작은 별도의 명시적 새 제품 동작으로 분리해야 한다. 제품의 물리적 동일성을 시스템이 검증할 수 있다는 주장은 하지 않는다.

## G. 서버 동시성·영속성 — 설계만, 검증 전

현재 `backend/grab_inspection.py:100`은 인메모리 Lock과 요청 내용별 `_attempts`를 사용한다. 동일 요청의 중복 실행 방지에는 도움이 되지만 재시작 영속성·프로세스 간 그룹 횟수·다른 ROI를 사용한 동일 Capture 재사용까지 보장하지 않는다.

후속 파일 기반 저장을 채택한다면 다음을 모두 구현·검증해야 한다.

1. 모든 관련 Worker가 공유하는 동일 영속 경로에서 OS 배타 파일 Lock 획득. 잠금 실패 시 Provider/모델 호출 없이 409.
2. 그룹 버전·상태·parent·한도·Capture 사용 여부·idempotency key를 Lock 안에서 재검증.
3. 실행 예약과 Capture 사용 예약을 추론 전에 영속 기록. 임시 파일 fsync 후 원자적 교체로 상태 저장.
4. 성공 후 검사·로그의 실제 저장을 확인하고 결과 링크를 확정. 동일 key 재전송은 기존 결과를 반환하거나 진행 중/결과 불확실 오류로 거부한다.
5. 검사 JSONL 저장과 그룹 저장은 별도 자원이므로 단순 atomic replace만으로 교차 저장소 원자성이 생기지 않는다. 프로세스 중단 후 예약만 남으면 자동 재추론하지 않고, 기존 검사 링크와 커밋 여부를 대조하는 복구 정책이 필요하다. 확인 불가 상태는 실패 폐쇄한다.
6. 동일 Capture의 다른 ROI/다른 그룹 재사용도 막을 영속 사용 색인이 필요하다.
7. 새 프로세스, 동시 요청, 저장 실패, 중간 크래시를 Fake로 검증하기 전 안전성을 선언하지 않는다.

이 방식은 단일 머신 공유 파일 시스템용 MVP 후보다. Cloud Run 다중 replica의 별도 파일 시스템에서는 안전한 공유 영속 트랜잭션 저장소가 필요하다. 기존 PostgreSQL ROI 데이터/스키마는 이번 감사에서 건드리지 않았다.

## H. 작업자 수동 확인 — PROPOSED

별도 append-only 확인 이력에 group_id, 전체 검사 링크, 결과 MANUAL_OK/MANUAL_NG/HOLD, 작업자 표시명, 사유, 서버 시각, 확인 버전을 저장한다. 화면 기본 선택은 HOLD이며 저장은 명시적 확인 후에만 한다.

현재 캡처 세션은 임시 소유권 수단이지 작업자 인증이 아니다. 최소 로컬 MVP는 Origin/CSRF/세션으로 접근을 보호하되 작업자 ID를 **자기신고한 개발용 수동 확인 기록**으로 표시해야 한다. 인증된 품질 승인, 모델 자체 판정 또는 PLC 제어로 표현하지 않는다. 실제 작업자 승인에는 별도 인증/역할 설계가 필요하다.

HOLD는 추가 확인 대기이며 OK가 아니다. 기존 확인 이력도 덮어쓰지 않는 정책이 필요하다.

## I. 원본 final_result 불변

수동 MANUAL_NG가 저장되더라도 원본 검사 3개의 REINSPECT는 그대로 유지해야 한다. 수동 확인을 엔진 NG로 치환하지 않는다. 이번 감사에서는 INSP-001652의 원본 판정과 모든 운영 자산을 읽기 전용으로 취급했다.

## J. React UI — 감사 결과 / 구현 보류

- `frontend/src/components/InspectionPanel.tsx:172`에서는 Grab 결과에 EXPERIMENTAL LIVEVIEW_GRAB 배지를 표시하지만 `:196`에서는 REGISTERED STATIC IMAGE 문구를 고정 표시한다. 정적 입력 컨트롤 안내와 현재 결과의 출처가 한 화면에서 혼동될 수 있는 문제를 확인했다. 수정은 보류했다.
- 현재 GrabInspectionPanel에는 영속 그룹·횟수·수동 확인 UI가 없다.
- 후속 구현에서는 서버 카운터만 표시하고 localStorage에는 그룹의 조회용 식별자만 저장한다. 횟수나 권한을 브라우저 값에서 신뢰하지 않는다.
- 명시적 동일 제품 확인, 새 Capture 이후 재검사 활성화, HOLD 기본값, 사유·작업자 표시명 검증, 오래된 응답 차단, 진행 중 클릭 방지, 이력별 이미지/Heatmap 조회가 필요하다.
- 기존 캡처 세션은 만료·서버 재시작 시 유효하지 않을 수 있다. 영속 그룹이 유지되는 것과 만료된 세션으로 접근 가능한 것은 다르다. 재인증/접근 복구 정책 없이 복원 성공을 주장하지 않는다.

## K. 향후 Gemini Vision 계약 — 문서 설계만

기존 Diagnostic Agent는 Function Calling으로 검사 기록·로그·이력을 진단한다. 향후 Vision은 실제 Crop 이미지를 입력받아 독립적인 시각적 의견을 제공하는 별도 기능이다.

허용 후보 분류: DEFECT_SUSPECTED / QUALITY_ISSUE / NO_VISIBLE_DEFECT / INCONCLUSIVE / ANALYSIS_FAILED.

DEFECT_SUSPECTED는 확정 NG가 아니며 NO_VISIBLE_DEFECT도 확정 OK가 아니다. 서버 확정 판정과 작업자 기록을 변경할 수 없다. 입력 Capture/검사/이미지 무결성, 응답 출처, 모델·요청·실패 진단을 별도로 추적해야 한다. 이번에는 호출 코드, Mock 성공 UI, SDK 설정 변경을 추가하지 않았다. 기존 502 원인과 SDK 내부 재전송 위험도 해결된 것으로 취급하지 않는다.

## L. 이번 신규 테스트

신규 Backend/Frontend/Chrome 테스트는 작성하지 않았다. 재검사·수동 확인 기능이 미구현이므로 해당 시나리오의 PASS를 주장하지 않는다.

후속 필수 Fake 검증은 사용자 요청의 24개 항목에 더해, 프로세스 간 Lock, 재시작 후 횟수·Capture 중복 색인, JSONL 저장 후 그룹 저장 실패, 예약 직후 크래시, 세션 만료 후 실패 폐쇄, 수동 이력 수정 충돌을 포함해야 한다. 실 모델·Gemini·운영 저장소를 사용해서는 안 된다.

## M. 실제 실행한 기존 격리 회귀

```powershell
& C:/Users/USER/miniconda3/envs/vision-insight/python.exe -B scripts/safe_regression_backend.py backend --output data/outputs/safe-regression/step8-audit-20261018 tests/test_grab_inspection.py tests/test_vision.py::test_analyze_brightness_basic tests/test_vision.py::test_quality_evaluation_decoupled_from_defect_inspection tests/test_vision.py::test_configurable_brightness_thresholds tests/test_day3_5_step4_5.py::test_determine_final_verdict_rule2_quality_warning tests/test_day3_5_step4_5.py::test_determine_final_verdict_rule2_quality_warning_with_product_ng tests/test_day3_5_step4_5.py::test_determine_final_verdict_rule4_product_ng tests/test_day3_5_step4_5.py::test_determine_final_verdict_rule5_all_checks_passed
```

결과: **42 PASS / 0 FAIL / 0 SKIP**, pytest 2.74초, 기존 anyio import 관련 PytestAssertRewriteWarning 1건. Grab Fake 통합 35건과 품질·판정 단위 테스트 7건이다.

안전 계측: forbidden_io=0, network=0, real_prediction=0, real_load=0. 실제 운영 경로는 테스트 출력 디렉터리로 격리했고 네트워크·모델 경로는 기존 안전 러너가 차단했다.

전체 안전 러너·Frontend·Chrome·TypeScript·Build·Lint는 이번에 실행하지 않았다. 기존 475 PASS/10 SKIP, Frontend 29 PASS, Chrome 28 PASS와 Lint 경고 6건은 이전 Step 7 실행 기록이며 이번 결과가 아니다.

## N. 운영 자산 SHA256 비교

점검 시작 스냅샷은 **56개 파일**이다. 보호 대상에는 기존 검사/로그 JSONL, 공식 모델, 기존 Sidecar, Agent 보고서, 영상, 캡처 PNG, 영속 Grab Crop 입력, .env, 기존 Inferencer/Decision 코드가 포함된다. 민감한 설정값은 출력하지 않았다.

최종 비교는 **PASS: unchanged=true, files=56**이다. 실행 증거는 `data/outputs/safe-regression/step8-audit-20261018/protected-before.json`, `backend.xml`, `safety.json`, `protection.json`에 있다. 이번 보고서 대상 `git diff --check`도 오류 없이 종료했다. 최종 `git status`에서 기존 `.tmp_measurement_regressions/`의 접근 거부 경고가 발생했으며, 해당 디렉터리는 수정·복원·삭제하지 않았다.

## O. 실제 Gemini API 호출

**0회.** 분석 POST, 연결 테스트, Vision 통합을 실행하지 않았다.

## P. 실제 PatchCore 추론

**0회.** 모델 로드도 0회다. 사용자가 이전 Chrome에서 수행한 INSP-001652 실제 검사와 이번 Fake 테스트는 별개다.

## Q. 남은 위험 및 미완료

- 운영 서버 자동 재시작과 기존 캡처 삭제 위험에 대한 사용자 조율이 먼저 필요하다.
- 재검사 영속 저장·서버 한도·동시성·수동 확인·React 연결은 미구현이다.
- 입력 분포 차이, 이중 Normalize, calibration 및 영상 Crop threshold의 적합성은 미해결이다.
- 저밝기 전체 평균 정책이 영상 Crop에서 반복 경고를 만들 가능성은 있지만, 오류라고 단정하거나 임계값을 바꾸지 않는다.
- 같은 제품 확인은 사용자 진술이며 물리적 제품 추적이 아니다.
- 수동 확인은 인증된 공장 승인 체계가 아니며 향후 인증 설계가 필요하다.

## R. 최종 상태

**PARTIAL.** 원인 감사·기존 격리 테스트는 완료했지만, 기존 캡처를 삭제할 수 있는 실행 환경을 확인해 구현 적용을 중단했다. 새 기능이 완료됐다는 주장을 하지 않는다. Git add/commit/push/reset/restore/clean은 실행하지 않았다.

## S. 사용자 다음 절차 및 Chrome 검증

1. 현재 필요한 Capture/ImageView 이미지를 먼저 보존한다. 서버 종료나 캡처 세션 재생성은 기존 임시 Capture를 삭제할 수 있다.
2. 사용자가 서버를 직접 종료하고, 보존 여부와 개발 재개 가능 상태를 알려준다. 현재 자동 재시작 서버를 유지한다면 백엔드 구현은 계속 보류한다.
3. 이후 서버가 중지된 환경에서 재검사·수동 확인을 구현하고 격리 Fake 테스트 및 기존 안전 러너를 검증한다. 실제 모델/Gemini 호출은 하지 않는다.
4. 구현 검증 후 사용자 Chrome에서 새 제품 시작 → 새 Grab → 1/3 → 동일 제품 확인 후 새 Capture로 2/3, 3/3 → 한도 및 수동 HOLD 기본값·사유 저장·새로고침 복원을 검증하는 절차를 확정한다.
5. 실제 모델 검사는 별도 사용자 승인/수동 실행 범위로 남긴다. 개발 단계에서 3회 실제 추론을 자동 수행하지 않는다.

## T. 재개 구현 완료 기록

### 실행 환경과 보호 범위

사용자가 PNG 3개를 외부 백업한 뒤 서버를 정상 종료했다. 수정 직전 읽기 전용 OS 조회에서 **8000번 LISTEN 0개 / uvicorn 또는 backend.main Python 프로세스 0개**를 확인했다. 백업을 CaptureStore에 재등록하지 않았고 사용자 서버를 시작·종료·재시작하지 않았다.

이번 시작 기준선은 **53개 운영 자산**이다. 최초 감사의 56개와 다른 이유는 사용자 서버 종료 전에 백업한 임시 PNG 3개가 별도 수명주기를 갖기 때문이다. 이미 종료된 서버의 임시 세션을 복원했다고 주장하지 않는다. 이번 검증 전후 53개 해시는 일치했다.

### 실제 구현 파일

| 파일 | 변경 이유 |
|---|---|
| `backend/reinspection_store.py` | 별도 영속 그룹·요청 예약·Capture 사용 색인·수동 이력, 원자적 저장, OS 파일 Lock |
| `backend/grab_inspection.py` | 기존 검사 경로를 저장소 실행권 아래 재사용, 엄격한 연속성 필드·신규 metrics 링크 |
| `backend/main.py` | 그룹 조회, Capture 기준 읽기 전용 복구 조회, 수동 확인 API 및 안전한 오류 응답 |
| `frontend/src/types/reinspection.ts` | 그룹/시도/수동 결과 계약 |
| `frontend/src/utils/reinspectionState.ts` | 신규 Capture·동일 제품 확인·한도·종료 상태 검사, HOLD 기본값 |
| `frontend/src/api/inspection.ts` | 기존 Grab 요청 확장 및 그룹/수동 확인 API |
| `frontend/src/components/GrabInspectionPanel.tsx` | 서버 횟수, 새로고침 복원, 명시적 연속성, 실패 폐쇄, 수동 확인·시도별 이미지/Heatmap 조회 |
| `frontend/src/components/InspectionPanel.tsx` | 현재 결과의 Grab/정적 출처와 정적 입력 컨트롤 설명 분리 |
| `frontend/src/App.tsx` | MANUAL 모드 권한과 현재 ROI 적용 상태를 분리해 새로고침 후 수동 확인 가능하게 함 |
| `tests/test_reinspection_workflow.py` | 신규 Fake 검증 44건, Windows 저장 충돌·200회 원자적 스냅샷 검증 포함 |
| `tests/test_grab_inspection.py` | 기존 중복 검사 회귀 1건을 새 정책에 맞게 변경: 같은 Capture의 다른 ROI도 409, 추가 추론 없음 |
| `frontend/scripts/test_reinspection_state.mjs` | 신규 단위 검증 5건 |
| `frontend/scripts/grab_browser_cases.mjs` | 기존 8건을 보존하고 재검사·수동 확인 Mock E2E 7건 추가 |
| `scripts/safe_regression_backend.py` | 신규 테스트 등록, 향후 운영 재검사 이력도 해시 보호 범위에 포함 |
| `scripts/run_safe_regression.ps1` | 신규 Frontend 단위 테스트를 기존 안전 실행기에 추가 |
| `docs/inspection-data-schema.md` | 추가 계약과 기존 스키마 불변 원칙 명시 |
| 이 보고서 | 감사 기록을 유지하면서 재개 구현·검증·운영 한계 추가 |

### 저장 구조와 검사 연결

기본 저장 경로는 `OUTPUT_DIR/reinspection_history/state.json`이며, 기본 OUTPUT_DIR에서는 `data/outputs/reinspection_history/state.json`이다. 서버 시작 시 운영 파일을 만들거나 과거 검사 JSONL을 이전하지 않는다.

- `groups`: `RIG-<32자리 UUID hex>`별 product/video/revision/해상도, 최초·현재 검사, parent 체인, 완료·실패 시도, 버전, 상태, 수동 확인 이력.
- `captures`: Capture별 예약/확정 상태·그룹·요청 fingerprint·실제 inspection_id. 세션 소유자 내부 식별 정보는 외부 조회에서 제거한다.
- `requests`: 소유 범위별 idempotency request ID와 Capture 연결. 같은 request ID를 다른 Capture에 쓰면 409.
- 신규 Inspection에만 `metrics.reinspection` 링크를 추가한다. 최상위 Inspection 스키마나 과거 행은 변경하지 않는다. 기본 모델 result, final_result, final_reason_code도 그대로다.
- 기존 INSP-001652를 자동 편입·재검사하거나 백업 이미지를 운영 세션에 재등록하지 않는다. 새 Capture에서 새 그룹을 시작한다.

### 완료 횟수와 상태 전이

완료 횟수는 파이프라인 COMPLETED, 모델 COMPLETED, 유한한 anomaly_score, 확정된 OK/NG/REINSPECT 및 실제 검사·완료 로그 저장 확인을 모두 충족해야 증가한다. 실패는 `failed_attempts`에 별도 기록되며 `attempt_number=null`이다.

`RETRY_ALLOWED` → 새 Capture로 재검사 → OK/NG이면 `COMPLETED`, 세 번째 REINSPECT이면 `MANUAL_REVIEW_REQUIRED`.

서버가 최대 횟수 3을 고정하며 클라이언트는 바꿀 수 없다. 같은 Capture로 ROI만 변경해도 새 추론은 거부한다. 정확히 같은 성공 요청은 기존 inspection_id를 반환하며 새 검사·로그·Sidecar를 생성하지 않는다. API 실패나 저장 실패가 자동 재추론을 유발하지 않는다.

### 잠금·원자성·부분 실패

`ReinspectionStore.locked()`는 Windows `msvcrt.locking` 또는 POSIX `flock`의 비차단 OS Lock을 사용한다. 영속 경로를 공유하는 프로세스가 동일 `workflow.lock`을 사용하며, Lock은 예약부터 기존 검사/로그 저장과 그룹 확정까지 유지된다. 다른 Grab 실행은 즉시 **409 REINSPECTION_BUSY**이며 일반 검사 조회·ImageView·Heatmap·Agent에는 이 Lock을 걸지 않는다.

추론 전 RESERVED/RECOVERY_REQUIRED를 fsync 저장하고, 결과 확인 후 COMMITTED로 확정한다. 상태 JSON은 임시 파일을 fsync한 뒤 `os.replace`로 교체한다. 예외·Timeout에도 OS Lock은 해제된다. 두 프로세스의 실제 파일 잠금 충돌 및 해제, 두 동시 Fake POST 중 1개만 추론 진입을 검증했다.

반복 검증에서 Windows 이력 저장 중 `PermissionError`, `errno=13`, `winerror=5`를 실제 확인했다. 파일 접근을 방해한 외부 프로세스/원인 자체는 UNKNOWN이다. Windows 파일 교체의 WinError 5/32/33에만 `os.replace`를 최대 4회, 총 대기 120ms로 제한 재시도한다. **이미지 획득·검사·모델 호출을 다시 실행하는 재시도가 아니다.** 영구 실패 시 기존 상태를 보존하고 503/RECOVERY_REQUIRED로 실패 폐쇄한다. 일시/영구 충돌 주입 및 200회 연속 저장·조회 검증을 추가했다.

**교차 저장소 트랜잭션이 생긴 것은 아니다.** 검사 JSONL이 저장됐으나 그룹 확정에 실패하거나 프로세스가 중단되면 예약 상태가 남아 후속 실행을 막는다. 이 경우 `RECOVERY_REQUIRED`이며 원본 검사·로그와의 운영자 대조가 필요하다. 자동 복구/자동 재추론은 구현하지 않았다. 예약 직후 유효성 검사 등에서 실패하여 모델 실행이 시작되지 않았음을 확인할 수 있을 때만 예약을 되돌린다.

현재는 로컬 단일 서버 프로세스의 CaptureStore/검사 저장소 계약을 유지한다. 워크플로우 Lock 자체는 프로세스 간 보호하지만 **다중 Worker 전체 앱의 Capture 세션 공유, 기존 검사 ID/JSONL 동시성, 서로 다른 머신/replica는 별도 검증 범위**다. 공유 경로가 다른 replica에서 안전하다고 주장하지 않는다. 파일 원자성은 로컬 파일 시스템의 정상 동작을 전제로 하며 전원 장애 내구성까지 검증하지 않았다.

### 실제 API 계약

| Method | 경로 | 동작 |
|---|---|---|
| POST | `/captures/{capture_id}/inspect` | 최초 또는 명시적 재검사. 기존 검사 응답 계약 유지, 신규 metrics 링크 추가 |
| GET | `/reinspection-groups/{group_id}` | 서버 카운터·전체 이력·수동 확인 조회, 추론 없음 |
| GET | `/reinspection-groups/by-capture/{capture_id}` | 응답 소실 후 읽기 전용 그룹 확인, 새 Capture 발급/추론 없음 |
| POST | `/reinspection-groups/{group_id}/manual-reviews` | 별도 개발용 수동 확인, 원본 검사 변경 없음 |

첫 검사 요청은 기존 `product_id`, `source_revision`, `roi`를 사용한다. UI는 별도의 UUID hex `request_id`도 전송한다. 재검사에는 다음 필드를 추가한다.

```json
{
  "group_id": "RIG-0123456789abcdef0123456789abcdef",
  "parent_inspection_id": "INSP-000001",
  "expected_version": 1,
  "same_product_confirmed": true,
  "request_id": "1123456789abcdef0123456789abcdef"
}
```

위 식별자는 형식 예시이며 실제 실행 결과가 아니다. 서버는 세션 소유권, 제품·영상·revision·원본 크기, 현재 parent와 그룹 버전을 검증한다. 물리적 동일 제품 여부는 사용자 명시적 진술이며 영상 추적이 아니다. 새로운 제품 그룹 시작은 별도 버튼이며 새로고침·실패로 자동 그룹 초기화하지 않는다.

변경 요청은 기존 Capture 세션, 허용 Origin, CSRF가 필요하다. GET도 세션 소유권을 확인하며 Origin이 있으면 허용 목록을 검사한다. 동일 출처 GET에서 Origin이 생략될 수 있어 GET에는 Origin 필수 조건을 적용하지 않는다. GET은 임시 Capture를 조회/재등록하지 않고 별도 저장 이력만 읽는다.

대표 오류: 422 엄격한 타입·추가 필드·사유 검증, 401/403 기존 세션/CSRF/Origin, 404 그룹·소유권 없음, 409 REINSPECTION_BUSY / CAPTURE_ALREADY_USED / IDEMPOTENCY_CONFLICT / REINSPECTION_CONTINUITY_REQUIRED / REINSPECTION_SOURCE_MISMATCH / REINSPECTION_GROUP_CLOSED / REINSPECTION_VERSION_CONFLICT / MANUAL_REVIEW_NOT_ALLOWED / REINSPECTION_RECOVERY_REQUIRED, 503 REINSPECTION_STORAGE_UNAVAILABLE / REINSPECTION_RECORD_MISSING / REINSPECTION_COMMIT_UNCONFIRMED. 내부 파일 경로나 예외 원문은 오류 응답에 넣지 않는다.

### 수동 확인과 화면 동작

3회 REINSPECT 이후 HOLD가 기본값인 확인 화면이 열린다. operator_id, 비어 있지 않은 사유, request_id, expected_version이 필요하며 결과는 HOLD/MANUAL_OK/MANUAL_NG만 허용한다. boolean 버전, 임의 필드, 빈/공백 사유, 제어 문자를 거부한다.

확인 기록에는 서버 시각·review_id·전체 inspection_id 목록과 `DEVELOPMENT_SELF_DECLARED_NOT_AUTHENTICATED` 권한 표시를 저장한다. HOLD는 대기 상태를 유지하고 후속 명시적 확인을 추가할 수 있다. MANUAL_OK/NG는 그룹 수동 확인을 종료하며 과거 확인 이력은 유지한다. 원본 3개의 final_result는 계속 REINSPECT다. 인증된 공장 품질 승인이나 PLC 제어가 아니다.

UI는 서버 응답의 횟수·남은 횟수·경고·원본 모델 결과와 최종 서버 결과를 분리 표시한다. 동일 제품 체크와 새 Capture 없이는 재검사를 실행할 수 없다. 진행 중 버튼을 막고, 실패 시 자동 재시도하지 않는다. localStorage에는 그룹/응답 소실 시 Capture 조회용 식별자만 저장하며 횟수나 권한을 신뢰하지 않는다. 늦은 검사 응답은 그룹 이력으로 보존하되 다른 Crop의 ImageView/Heatmap에 적용하지 않는다. 이력 조회에도 selection version과 Capture/그룹 출처 대조를 적용한다.

새로고침은 기존 세션이 유효할 때 서버 이력을 복원한다. 세션 만료·서버 재시작 후에는 그룹 파일은 유지되더라도 접근이 실패 폐쇄될 수 있다. 지속 사용자 인증/소유권 복구는 미구현이며 새 세션을 과거 작업자로 위장하지 않는다. ImageView의 Zoom/Pan·RGB/GV·Heatmap 좌표 변환 코드는 수정하지 않았다.

### 실제 테스트 결과

실행 명령:

```powershell
& C:/Users/USER/miniconda3/envs/vision-insight/python.exe -B scripts/safe_regression_backend.py backend --output data/outputs/safe-regression/step8-bounded-atomic-write tests/test_reinspection_workflow.py tests/test_grab_inspection.py
node --test frontend/scripts/test_reinspection_state.mjs
node frontend/scripts/test_step4_browser.mjs "C:/Program Files/Google/Chrome/Application/chrome.exe" data/outputs/safe-regression/step8-grab-browser-final --grab
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_safe_regression.ps1
```

| 범위 | PASS | FAIL | SKIP | 근거 |
|---|---:|---:|---:|---|
| 신규 Backend + 기존 Grab 집중 검증 | 79 | 0 | 0 | 신규 44 + 기존 35, pytest 18.76초 |
| 신규 Frontend 단위 | 5 | 0 | 0 | Capture/연속성/한도/HOLD |
| Grab Chrome Mock 집중 | 15 | 0 | 0 | 기존 8 + 신규 7 |
| 안전 러너 Backend | **519** | **0** | **10** | pytest 31.15초, 기존 anyio 경고 1 |
| 안전 러너 Frontend | **34** | **0** | **0** | 신규 5 포함 |
| 안전 러너 Chrome Mock | **35** | **0** | **0** | ImageView 12 + Agent 8 + Grab 15 |
| TypeScript / Build / Lint | 성공 | 0 | 0 | 기존 무관한 Lint 경고 6건 유지 |

첫 집중 실행에서는 오류 래핑을 반영하지 않은 테스트 기대값 1건이 실패했다. 공용 503 코드 검증으로 수정해 통과했다. 첫 확장 Chrome 실행에서는 새 C/D/E Mock의 지도 조회를 허용하지 않은 Fixture 정규식 1건이 실패했고, 허용된 합성 ID 범위로만 수정했다. 외부 요청을 열어 해결하지 않았다. 최종 집중 실행과 안전 러너 결과는 위 표와 같다.

이후 최종 반복 안전 러너 `20261018-213253-6302da5b`에서는 Backend 512 PASS / 4 FAIL / 10 SKIP이 발생했다. 실패한 임시 JSONL 3개 검사·18개 로그는 확정돼 있었지만 그룹은 예약 상태로 남아 추가 추론이 차단됐다. 진단용 임시 테스트 계측으로 WinError 5를 확인한 뒤 제거했고, 위 파일 교체 제한 재시도 및 회귀 3건을 추가했다. 진단 중 발생한 FAIL/ERROR 기록은 삭제하지 않았다. 최종 개선 후 집중 79 PASS와 안전 러너 519 PASS로 재검증했으며, 과거 중간 PASS만으로 완료를 선언하지 않는다.

10 SKIP은 Windows 심볼릭 링크 권한 1, 실제 checkpoint/추론 제외 6, 빈 격리 저장소 조회 사례 1, 실 데이터셋 workflow 2다. 실제 모델 테스트를 활성화하거나 SKIP을 PASS로 바꾸지 않았다. 일반 전체 pytest는 별도로 실행하지 않았다.

최종 안전 러너 증거: `data/outputs/safe-regression/20261018-214027-d3e836ab/summary.json`, `backend.xml`, `safety.json`, `protection.json`.

**운영 자산 53개 unchanged=true, forbidden_io=0, network=0, real_prediction=0, real_load=0, real_gemini_api_calls=0.** 사용자 종료 후 새로 잡은 기준선과 비교한 결과이며, 이전에 사용자가 실행한 실 모델 검사와 혼동하지 않는다. PostgreSQL 접속·데이터 변경, 운영 그룹·수동 확인 생성, 운영 JSONL append, 백업 재등록, 모델/밝기 기준/34.1442/Normalize/Calibration/Decision 정책 변경, Git 변경 명령은 모두 없었다.

### Gemini Vision 및 남은 위험

K의 향후 계약은 그대로 문서 설계만 유지한다. 실제 Crop을 입력받는 Vision과 기존 Function Calling Diagnostic Agent를 혼동하지 않는다. DEFECT_SUSPECTED/QUALITY_ISSUE/NO_VISIBLE_DEFECT/INCONCLUSIVE/ANALYSIS_FAILED는 의견 분류이며 원본 최종 판정을 바꿀 수 없다. 호출 코드·Mock 성공 UI·SDK 설정을 추가하지 않았다.

실제 Crop 성능, 이중 정규화, calibration/threshold 적합성, Gemini 502 원인과 SDK 재전송 문제는 미해결이다. 재검사 횟수 제한으로 이 문제들이 해결됐다고 주장하지 않는다. 수동 확인은 개발용 자기신고이고, 운영 인증·크래시 후 자동 복구·다중 replica는 별도 과제다.

### 사용자 Chrome 검증 계획 — 실제 추론 별도 승인 후

1. 사용자가 직접 기존 vision-insight 환경의 서버를 시작한다. Codex는 이번에 서버를 시작하지 않았다. 외부 백업 PNG나 옛 Capture ID를 재등록하지 않는다.
2. MANUAL에서 새 제품 검사 시작 → Pause → 새 Grab 및 ROI 적용 → 검사. 새 RIG/INSP/CAP 링크, 점수·원본 모델 결과·품질·서버 최종 판정을 확인한다.
3. REINSPECT이면 새 Capture를 만들고 동일 제품 재검사 확인을 체크한다. 기존 Capture/미확인 상태에서는 실행 불가여야 한다. OK/NG이면 종료되므로 억지로 3회 시나리오를 만들지 않는다.
4. 최대 3회의 완료 검사가 모두 REINSPECT일 때만 작업자 확인 화면, HOLD 기본값, 사유/표시명 필수, 네 번째 검사 차단을 확인한다. 실제 추론 허용 횟수는 별도 사용자 승인을 받아야 한다.
5. 유효 세션에서 새로고침 후 같은 그룹의 횟수와 이력을 조회한다. 시도별 이미지/Heatmap, RGB/GV 불변, 등록 정적 이미지 전환 시 출처·이전 지도 제거를 확인한다.
6. HOLD를 저장한 뒤 필요한 경우 명시적인 MANUAL_OK/NG를 별도로 저장하고 모든 원본 final_result가 유지되는지 확인한다. 개발용 기록을 실제 공장 승인으로 해석하지 않는다.

**구현과 오프라인 검증 상태: COMPLETE. 실제 사용자 Chrome/실 모델 검증은 NOT TESTED, Gemini Vision 통합은 NOT IMPLEMENTED. 추가 실제 검사나 Gemini 호출 없이 사용자 승인을 기다린다.**
