# VisionInsight — PatchCore 전처리 A/B 실험 보류 및 재개 인수인계서

> **작성 기준일:** 2026-10-17  
> **프로젝트:** VisionInsight — MVTec Bottle 기반 비전 검사 및 Gemini 근거 기반 진단  
> **대상 작업:** Day5 Step 3 Phase B-2A / B-2B / B-2B-R  
> **현재 결론:** **A/B 기술 측정 확보 / 실행기 최종 보호 검사 BLOCKED / 전처리 문제 UNRESOLVED**  
> **우선순위 변경:** 2026-10-20(화) 발표 전에는 정적 이미지 검사·Agent 중심의 풀스택 MVP 및 React 시연 화면 구축을 우선한다. 본 이슈는 별도 명시적 승인 때 재개한다.

## 1. 이 문서의 목적과 사용 방법

이 문서는 현재까지 확인된 사실, 측정값, 보호 이벤트, 미완료 검증, 재개 조건을 남기는 **작업 인수인계·보류 기록**이다. 기존 실행 보고서나 코드를 덮어쓰지 않으며, 앞으로 다른 에이전트(Codex, Antigravity/Gemini 등)가 작업할 때 문맥을 되찾을 기준으로 활용한다.

- **보관 권장 경로:** `docs/visioninsight-patchcore-ab-deferred-handoff.md`
- **기존 감사:** `docs/day5-step3-phaseb2a-patchcore-preprocessing-audit.md`
- **기존 입력 게이트 중단:** `docs/day5-step3-phaseb2b-patchcore-ab-experiment.md`
- **실제 합성 A/B 결과:** `docs/day5-step3-phaseb2b-r-synthetic-ab-results.md`
- **검사 화면 설계:** `docs/visioninsight-auto-manual-inspection-spec.md`
- **기술 스택:** `docs/visioninsight-tech-stack-decisions.md`

**증거 수준 주의:** 본 문서의 실제 수치·수행 내역은 사용자가 전달한 **Codex 완료 보고**에 기반한다. 이 문서 작성 과정에서 모델 추론, 소스 코드 재검사, 네트워크 접근, 테스트 재실행은 하지 않았다. 이후 작업자는 저장소의 원본 보고서·로그·측정 JSON을 읽어 검증해야 한다.

## 2. 의사결정 요약

| 항목 | 결정·상태 |
|---|---|
| 공식 모델 | `models/patchcore/patchcore_bottle.ckpt` 보존 |
| 고정 임계값 | `34.1442` **변경 금지** |
| 공식 운영 전처리 | 현재 이중 Normalize 경로 **변경하지 않음** |
| A/B 실험 | 중립 합성 입력 3종으로 측정은 확보했으나 최종 보호 검사에서 **STOPPED/exit 1** |
| 원인 규명 | 일부 결과 확보. 소켓 시도 1건의 당시 원인은 **미확정** |
| 단일 Normalize 도입 | 기술 후보일 뿐 **운영 적용 승인 없음** |
| Threshold 재사용 | 단일 Normalize 후보에 대한 통계적 유효성 **미검증** |
| ROI→PatchCore | **연결 보류** |
| 2026-10-20 발표 MVP | **기존 정적 이미지 검사 + Gemini Agent 시연** 중심, 프론트/영상 UI 통합을 우선 |

## 3. 배경 및 이전 단계

### 3.1 Phase B-2A: 전처리 경로 읽기 전용 감사

| 경로 | 현행 코드상 Normalize 횟수 | 확실성 |
|---|---:|---|
| 학습 | 1회 | 현행 코드 확인. **과거 실제 학습 실행 횟수는 LIKELY** |
| 독립 정상 Calibration | 2회 | 현행 wrapper 경로 확인. 당시 실행 fingerprint 불충분 |
| 운영 추론 | 2회 | 외부 전처리 + 전체 Lightning 모델 내부 `pre_processor.export_transform` |

- 이중 정규화의 외부 위치: `backend/ml/patchcore_inferencer.py:56` (직전 감사 보고 기준).
- 전체 Lightning 모델 forward에서 내부 Normalize가 다시 적용된다.
- Threshold `34.1442` provenance: **PROVENANCE_PARTIAL** — 180장 학습/29장 독립 정상 calibration 분할, 산출식 등은 문서화됐으나 당시 실행 경로 fingerprint가 불충분하다.
- 학습 1회 vs calibration/운영 2회라는 **현행 코드 경로 불일치**는 위험 신호이나, 과거 실제 score 영향의 크기·방향은 감사만으로 결론 내리지 않았다.

### 3.2 Phase B-2B: 실제 정상 이미지 선정 게이트

- 공식 정상 209장 메타데이터는 학습 180장 + calibration 29장으로 모두 배정되어, 학습·calibration 양쪽에서 독립된 정상 개발 이미지 3~5장을 확보할 수 없었다.
- 기존 모델 테스트 이미지도 학습 집합에 포함돼 있었다.
- 따라서 데이터 선정 게이트에서 **BLOCKED**. 모델 forward **0회**, 기존 자산 변경 **0건**.
- 사용자가 중립 합성 이미지를 사용한 제한적 진단 실험을 별도 승인하여 B-2B-R로 진행했다.

## 4. Phase B-2B-R: 실행 결과

### 4.1 입력과 실행 환경

| 항목 | 보고된 사실 |
|---|---|
| SYN-001 | 256×256 균일 회색 |
| SYN-002 | 256×256 수평 밝기 gradient |
| SYN-003 | 256×256 결정적 색상 패턴 |
| 모델 | 공식 checkpoint만 사용; 로딩 1회 |
| 실행 | CPU float32, Backbone 입력 `[1,3,256,256]` |
| 실제 PatchCore forward | **7회** / 승인 상한 **12회** |
| Path A | 기존 외부 Normalize + 내부 Normalize, 실제 **2회** |
| Path B | 외부 Normalize 없음 + 내부 Normalize, 실제 **1회** |
| Baseline 검증 | SYN-001에서 기존 운영 wrapper와 Path A의 **입력 Tensor·score·anomaly map 정확히 일치** |
| 별도 단위 테스트 | `tests/test_patchcore_synthetic_ab.py` **9 PASS**, 모델 forward 없음 |
| 전체 pytest | **이 작업에서 재실행하지 않음** |

### 4.2 실제 관측 anomaly score

| 합성 입력 | Path A: 2회 | Path B: 1회 | 절대 차이 | Codex 보고 상대 차이 | 임계값 34.1442 교차 |
|---|---:|---:|---:|---:|---|
| SYN-001 | 15.432871 | 13.714252 | 1.718619 | 11.1361% | 없음 |
| SYN-002 | 32.270653 | 17.488588 | 14.782064 | 45.8065% | 없음 |
| SYN-003 | 61.259308 | 22.713743 | 38.545565 | 62.9220% | **있음** |

- SYN-003의 **교차**는 기존 threshold와 수치적으로 비교했을 때 A/B가 서로 다른 쪽에 놓인다는 의미뿐이다. **정상/불량 판정이나 정확도 평가가 아니다.**
- SYN-002 Backbone 입력 통계 중 최솟값~최댓값: Path A **−11.366392 ~ 9.928890**, Path B **−2.117904 ~ 2.640000**.
- Path B는 **시험한 합성 입력 범위에서** 모델 내부 전처리의 dtype·shape·scale 계약을 만족했다는 보고다. 실제 병 영상 ROI나 운영 전처리 전반에 대한 검증은 아니다.
- 두 경로의 score가 달라지는 것은 관측됐다. **Path B score가 낮다는 사실은 성능 향상의 증거가 아니다.**
- 합성 이미지 3장으로는 Recall/Precision/AUROC, 실제 정상 분포, threshold 통계적 타당성, 영상 ROI 검사 성능을 평가할 수 없다.

## 5. 미해결 보호 계측 이벤트 — 최우선 재개 게이트

**Codex 최종 결과: `PARTIAL`, 실험 실행기 `STOPPED / exit 1`.**

- 실험의 점수와 Tensor 측정은 확보했지만, 실행기 **최종 보호 검사**에서 **차단된 socket 시도 1건**을 발견했다.
- 이후 모델 추론은 추가 실행하지 않았다.
- 별도의 **import-only 재현**에서는 `urllib3`의 IPv6 기능 확인 probe와 관련된 차단 시도를 관측했다.
- **중요:** 그 import-only 관측과 **원래 A/B 실험 실행 중 차단 이벤트의 인과관계는 확인되지 않았다.** 따라서 해당 이벤트를 단순 정상 probe 또는 악성 연결로 단정하지 않는다.
- 이 이벤트의 구체적 stack trace, 시도된 endpoint/주소, 발생 시각·프로세스 문맥, 실행기 guard 정책 및 라이브러리 import chain은 원본 보고서와 격리 로그에서 확인해야 한다. **여기에 확인되지 않은 사실을 채워 넣지 말 것.**

### 재개 전에 필요한 승인/진단

1. **읽기 전용 사건 분류:** 기존 보호 로그와 stack trace, import chain을 먼저 분석한다.
2. import-only와 실험 실행 시도를 별개로 취급하며 동일 원인인지 입증한다.
3. 필요한 경우 모델 forward 없이, 명시적 허용 범위의 **격리된 재현**만 설계한다.
4. **네트워크 차단을 끄거나 임의 allowlist를 넓혀서 PASS를 만들지 않는다.** 실제 외부 송신이 필요한 변경은 추가 승인 대상이다.
5. 진단 결과에 따라 안전하게 계측을 보완할지 결정한다. 해당 판단 없이 새로운 A/B forward를 재실행하지 않는다.

## 6. 무결성 및 보존 결과 (Codex 보고 기준)

| 보호 대상 | 확인 결과 |
|---|---|
| 공식 모델·checkpoint | 변경 0건, 모델 상태 fingerprint 전후 동일 |
| 운영 PatchCore 전처리 | 변경 0건 |
| threshold `34.1442` | 변경 0건 |
| 운영 검사/로그 JSONL | 변경 0건 |
| PostgreSQL 접속·ROI 데이터 | 접속 0회 / 변경 0건 |
| 실제 Gemini API 호출 | 0회 |
| Ground Truth 및 평가 데이터 접근 | 0건 |
| Git add/commit/push/reset | 0건 |
| 기존 파일 | 기존 **237개 파일 SHA256 동일** (보고 기준) |

신규 산출물:

- `scripts/experiments/compare_patchcore_synthetic_ab.py`
- `tests/test_patchcore_synthetic_ab.py` — 9 PASS, 모델 호출 없음
- `docs/day5-step3-phaseb2b-r-synthetic-ab-results.md`
- 격리된 실험 측정 JSON 및 요약 문서 (정확한 경로는 기존 보고서 참조)

**기준 회귀 이력:** 직전 PostgreSQL ROI 회귀 수정 단계에서 전체 pytest **1276 PASS / 0 FAIL / 51 SKIP**. 이번 실험에서 전체 pytest를 재실행한 결과가 아님. 당시 51 SKIP은 모델 제외 47건 + T03 fixture 부재 4건.

## 7. 현재 시스템에서 안전하게 이어갈 수 있는 발표 전 작업

발표일은 **2026-10-20(화)**이며 발표 MVP는 **기존 정적 이미지 검사·Gemini Agent 시연**을 핵심으로 한다. 별도로 **React/TypeScript 프론트 화면을 먼저 가시화**하고 기존 FastAPI의 검증된 API를 단계적으로 연결한다.

### 발표 전 우선순위

1. React/TypeScript UI 뼈대와 실제 브라우저 실행 — 가장 먼저 눈으로 볼 수 있는 결과 확보.
2. 기존 서버 **등록 정적 이미지 검사** API 연결 및 결정적 OK/NG/REINSPECT/ERROR 결과 표시. 새 모델 경로나 threshold를 도입하지 않는다. 실제 inference를 실행하려면 해당 위험과 데모 범위를 분리해 명시적으로 판단한다.
3. **기존 검사 ID의 Gemini Function Calling 분석 결과** 조회/표시 — 과거 검증된 응답을 사용한 재현 가능한 폴백도 준비하며, 실제 Gemini 호출 여부를 명확히 표시한다.
4. 기존 H.264 LiveView 재생/일시정지와 서버 Grab API 연결 — 영상에서 얻은 실제 capture PNG와 식별자 표시.
5. 시간이 허용될 경우 ImageView ROI 선택 UI와 AUTO 상태 전환을 **UI/Grab 시뮬레이션** 범위에서 구현. 실제 ROI→PatchCore 연결은 검증·승인 전까지 보류.
6. 발표 전 기능 동결·시연 리허설·PPT 구현 상태 일치·실패 시 폴백 확보.

**금지할 오인:** UI가 만들어졌다고 ROI 추론·자동 최종 검사·클라우드 배포가 완료된 것이 아니다. 기존 정적 이미지 검사와 별개로, 영상 Grab 또는 AUTO Pause 동작만 확인했다면 **검사는 미연결**이라고 표시한다. 합성 score를 실제 제품 검사 결과처럼 보여주지 않는다.

### UI 작업 에이전트에 넘길 보호 계약

- 문서 `docs/visioninsight-auto-manual-inspection-spec.md`와 기존 API 경로/요청/세션 계약을 우선 읽는다.
- H.264 소스 `VID-000001`, 기존 `/videos/.../stream`, `/videos/.../grab`, `/captures/...` 계약을 **변경하지 않고 활용**한다.
- React 화면은 플레이어/Grab/서버 결과를 표시하되 사용자가 승인하지 않은 ROI 좌표나 제품 트리거 프레임을 임의의 운영 기본값으로 확정하지 않는다.
- 모델 전처리, checkpoint, threshold 34.1442, JSONL, PostgreSQL schema는 수정하지 않는다.
- UI에서 **실제 서버 데이터 / 미연결 / 샘플·데모 표시**를 명확히 구별한다.

## 8. 발표 이후 작업 재개 권장 순서 (검증 게이트)

### Gate 1 — 보호 계측 사건 분류

- 원본 격리 실험 보고서·코드·계측 로그를 읽는다.
- 차단된 socket 이벤트의 실제 발생 경로와 차단 정책을 확인한다.
- 외부 네트워크 접근을 허용하지 않고도 필요한 안전 측정을 달성할 수 있는지 판단한다.
- 결과는 `CONFIRMED / LIKELY / UNKNOWN`으로 나눠 기록한다.

### Gate 2 — 비교 입력의 대표성 보완

- 중립 합성 이미지 3종은 순수 기술 비교로만 활용한다.
- 공식 학습 180장 및 calibration 29장과 중복되지 않는 **승인된 개발용 정상 이미지**가 새로 확보되면 그 출처·중복 근거를 검증한다.
- 적합한 이미지가 없다면 데이터 확보 계획을 수립하고 추측해서 원본 평가 데이터를 사용하지 않는다.
- 독립 calibration 29장 사용은 목적·범위·실험 횟수 등을 제시하고 **별도 승인**을 받는다.

### Gate 3 — Threshold 및 모델 호환성 결정

- 학습/운영 전처리 일관성 및 기존 34.1442의 provenance를 분석한다.
- 단일 Normalize 경로에서 기존 threshold의 **재사용 가능성을 검증하기 전까지 운영 적용하지 않는다.**
- 필요 시 교정/재보정 방법을 별도로 설계·승인한다. 정상 데이터 기반 재설정과 불량 평가에 따른 튜닝을 혼동하지 않는다.
- 새 입력 계약·전처리 수정 및 회귀 검증은 사용자 승인 후 별도 단계로 수행한다.

### Gate 4 — ROI→PatchCore 통합

- AUTO와 MANUAL이 동일한 **서버 공통 ROI Crop→전처리→검사→기존 판정** 경로를 사용하도록 한다.
- PostgreSQL `roi_presets`, `roi_preset_versions`, `roi_approvals`, `roi_active_bindings`와 승인·활성 상태를 검사 적용 전에 검증한다.
- source revision/SHA·원본 크기·ROI 픽셀 좌표·버전·검사 ID provenance를 보존한다.
- 캡처 세션 TTL 및 영구 ROI 소유권을 혼동하지 않는다.
- 영상 프레임/브라우저 Grab/서버 Crop 간 원본 픽셀 정합성과 실제 Bottle ROI 모델 적합성을 별도 실험한다.
- AUTO 반복 루프당 중복 검사 방지, 검사 종료 후 영상 재생, ERROR 시 HOLD, Gemini 비동기 처리 등을 별도 E2E 검증한다.

## 9. 다음 에이전트에게 전달할 재개 체크리스트

- [ ] 이전 B-2A, B-2B, B-2B-R 보고서 및 실험 JSON/코드를 원문 그대로 확인했다.
- [ ] 현재 작업 브랜치와 `git status --short`를 확인하고 병렬 작업을 보호한다.
- [ ] 모델/checkpoint/threshold/운영 JSONL/PostgreSQL 자료의 변경 여부를 검사한다.
- [ ] 소켓 차단 이벤트와 import-only `urllib3` IPv6 probe의 인과관계를 **검증 전 단정하지 않는다**.
- [ ] 새로운 모델 forward 또는 외부 데이터 접근은 사용자로부터 명시적 범위 승인을 받는다.
- [ ] 단일 정규화 score가 낮다는 이유로 정확도 개선을 주장하지 않는다.
- [ ] 실제 정상 이미지 사용 여부 및 calibration 29장 사용 승인 여부를 분명히 기록한다.
- [ ] 운영 전처리 교체, threshold 변경, ROI 실제 검사 연결은 각각 별도 승인 단계로 진행한다.
- [ ] 새로운 실험 결과를 기존 검사 기록이나 발표 성능 수치에 덮어쓰지 않는다.

## 10. 후속 담당자에게 가장 먼저 전달할 문장

> VisionInsight의 PostgreSQL ROI 저장/승인/활성화와 영상 Grab API는 별도 구현돼 있다. PatchCore 합성 A/B 실험에서는 Normalize 2회/1회가 실제로 확인됐고 3종 합성 이미지의 anomaly score가 달라졌지만, 실험 실행기의 최종 보호 검사에서 원인 미확정 socket 시도가 차단되어 작업 상태는 PARTIAL/STOPPED다. 공식 checkpoint와 threshold 34.1442, 운영 전처리는 변경하지 않았다. **현재는 2026-10-20 발표를 위한 React 풀스택 데모가 우선**이며, 이 전처리 이슈의 재개는 보호 사건 분류와 데이터/실험 범위 승인 이후로 한정한다.

---

**상태 라벨 최종 정리:** `EXPERIMENT_DATA_OBTAINED` / `SECURITY_GUARD_BLOCKED` / `MODEL_PREPROCESSING_UNRESOLVED` / `ROI_MODEL_INTEGRATION_NOT_IMPLEMENTED` / `DEFERRED_UNTIL_POST_PRESENTATION`.
