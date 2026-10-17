# Day5 Step 3 Phase B-2B — PatchCore A/B 실험 입력 게이트 중단

작성일: 2026-10-17. **최종 상태: BLOCKED**.

## 1. 결론과 실제 수행 범위

요청의 선정 기준을 모두 만족한다고 확인할 수 있는 **기존 승인된 독립 정상 개발 이미지 3~5장**을 확보하지 못했다. 사용자 중단 조건 1·2에 따라 **모델 로딩 및 실제 추론 전에 중단**했다.

이는 프로젝트에 이미지가 물리적으로 없다는 결론이 아니다. 확인한 허용 메타데이터·fixture·등록 코드에서 이번 용도에 적합한 3~5건의 승인된 입력 목록을 입증하지 못했다는 뜻이다. 평가용 이미지, 학습/Calibration 이미지, 합성 fixture로 임의 대체하지 않았다.

- 공식 모델 로딩: **0회**.
- 전체 모델 forward: **0회 / 상한 15회**.
- 이미지 디코딩·Tensor 전처리·A/B 점수 계산: **0회**.
- 실제 검사 API·Gemini 호출·PostgreSQL 접속: **0회**.
- 실험 스크립트·신규 테스트·측정 결과 파일: **미생성**.
- 신규 파일: 이 중단 보고서 **1개**.

**전처리 문제는 UNRESOLVED, threshold provenance는 PROVENANCE_PARTIAL을 유지한다.** B-2B 실험 COMPLETE나 모델 문제 해결로 보고하지 않는다.

## 2. 확인한 문서와 현재 상태

다음 파일이 모두 존재함을 확인하고 관련 설계·안전 정책·감사 결과를 읽었다.

- `AGENTS.md`
- `docs/visioninsight-auto-manual-inspection-spec.md`
- `docs/visioninsight-tech-stack-decisions.md`
- `docs/day5-step3-phasea-roi-patchcore-audit.md`
- `docs/day5-step3-phaseb2a-patchcore-preprocessing-audit.md`
- `docs/day5-step3-phaseb1-db-postgresql-roi-completion.md`
- `docs/day5-step3-phaseb1-db-regression-fix.md`

AUTO는 저장·승인·활성 ROI, MANUAL은 사용자 ROI를 사용해 동일 모델·판정 정책으로 수렴한다는 요구사항을 유지했다. 영상·Grab·PostgreSQL 기능과 과거 모델 전처리 감사는 이번 입력 선정 게이트와 구분했다.

작업 전 `git status --short`에서 기존 Agent/DB/영상/테스트/발표 자료 등의 수정·미추적 파일을 확인했고 복원·삭제하지 않았다. 현재 `backend/ml/patchcore_inferencer.py`, 학습·Calibration 코드 및 기존 모델 테스트를 읽기 전용으로 확인했다. 모델 모듈이나 ImageRegistry를 인스턴스화하지 않았다.

이전 공식 회귀는 **1276 PASS / 0 FAIL / 51 SKIP**이며 이번에 새로 실행한 결과가 아니다. 이번에는 단위·모델 통합·PostgreSQL·전체 pytest를 모두 실행하지 않았다.

## 3. 공식 자산 — CONFIRMED

| 항목 | 확인값 |
|---|---|
| 공식 checkpoint | `models/patchcore/patchcore_bottle.ckpt` |
| SHA256 | `4b239d28e72c63bf782cd1d31981d7f4362c591e7c23164e4c0ac8b5e99b52a3` |
| metadata | `models/patchcore/model_metadata.json` |
| 고정 threshold | **34.1442** |
| 기록된 분할 | 학습180 / 독립Calibration29 / seed42 |

metadata와 파일 무결성만 확인했다. 공식 checkpoint를 역직렬화하거나 모델을 생성하지 않았다. 209장 실험용 checkpoint는 추론·비교에 사용하지 않았다. 기존 정적 평가값을 이번 실험 결과로 사용하지 않았다.

## 4. 입력 선정 조사 및 중단 근거

### 4.1 분할 metadata — CONFIRMED

`models/patchcore/dataset_split.json`의 파일명 집합만 Python 표준 라이브러리로 읽었다. 원본 이미지 디렉터리 또는 평가 데이터를 탐색·디코딩하지 않았다.

| 항목 | 확인 결과 |
|---|---:|
| random_seed | 42 |
| metadata total_count | 209 |
| 고유 train_files | 180 |
| 고유 val_files | 29 |
| 두 집합의 교집합 | 0 |
| 두 집합의 합집합 | 209 |

즉 metadata에 명시된 정상 원천209건 중 학습/Calibration 모두에 속하지 않는 잔여 목록은 없다. **다른 곳에 독립 개발 이미지가 전혀 없다고 증명한 것은 아니다.**

관련 코드 근거:

- `scripts/train_patchcore.py:57`: 학습/검증 목록 분리 및 개수·비중복 검사.
- `scripts/calibrate_threshold.py:46`: val_files29건을 대상으로 하는 기존 Calibration 경로.

### 4.2 기존 자산별 판정

| 확인 대상 | 근거 | 이번 실험 사용 판단 |
|---|---|---|
| 기존 모델 테스트의 SAMPLE_IMAGE | `tests/test_patchcore_inferencer.py:11`; split metadata상 학습 집합에 포함 | **제외: 학습 중복**. 실제 이미지는 열지 않음 |
| 기존 T03 생성 경로 | `scripts/generate_t03_fault.py:74`는 위 학습 원천을 사용 | **제외: 학습 원천의 파생·품질 주입물**. 독립 정상 개발 이미지로 인정하지 않음 |
| 공개 시나리오 목록 | `test_data/scenarios_public.json`은 T01/T03/T05/T06 실행용 중립 ID와 설명 제공 | **승인 불충분**. 정상 출처·content hash·분할 제외·실험 allowlist를 입증하지 못함 |
| 기존 합성 모델 테스트 | `tests/test_patchcore_inferencer.py:47`, `tests/test_patchcore_inferencer.py:57`의 메모리 배열/PIL 이미지 | **대체하지 않음**. 형식 테스트 fixture이지 승인된 독립 정상 제품 이미지라는 증거가 아님 |
| 모델 학습/Calibration 이외 평가 이미지 | 이번 사용자 요청에서 평가 데이터 사용 금지 | **탐색·선정·사용하지 않음** |
| 컨베이어/Grab/ROI | 이번 실험 입력 범위에서 제외 | **사용하지 않음** |

공개 시나리오의 `IMG-BOTTLE-0084` 등은 **실험 승인 후보로 확정한 ID가 아니다**. 중립 이름 또는 standard_inspection 설명만으로 정상 제품·비중복·비평가 데이터라고 추정하지 않았다. 다른 시나리오의 실제 라벨을 찾아 정상 샘플을 고르는 방식도 사용하지 않았다.

### 4.3 Registry와 provenance의 차이 — CONFIRMED

`backend/inspection.py:95`의 ImageRegistry.refresh는 정렬된 이미지 경로에서 중립 ID를 부여한다. `backend/inspection.py:115`는 dataset 전체 PNG 탐색 코드다. 등록 자체에는 승인된 정상 개발 데이터 여부, 실험 허가 또는 train/Calibration 제외 증명이 없다.

따라서 현재 registry를 실행해 전체 원본·클래스 폴더를 탐색하지 않았다. 기존 ID를 임의로 안전한 실험 allowlist로 간주하지 않았고, 공개 metadata에서 확인할 수 없는 원본 출처는 **UNKNOWN**으로 남겼다.

docs/scripts/tests/test_data 범위에서 기존 manifest/registry/allowlist/fixture 이름의 메타데이터 후보도 확인했으나, 위 조건을 충족하는 3~5건의 명시적 승인 manifest는 확보하지 못했다. 관련 없는 개인 경로나 평가 원본을 추가 탐색하지 않았다.

## 5. A/B 경로와 검증 상태

| 항목 | 상태 | 설명 |
|---|---|---|
| Path A 외부 Normalize | CONFIRMED, 소스 기준 | `backend/ml/patchcore_inferencer.py:52`의 외부 Compose 및 Normalize |
| Path A 전체 Lightning 호출 | CONFIRMED, 소스 기준 | `backend/ml/patchcore_inferencer.py:178` |
| 내부 export_transform Normalize | 기존 B-2A 감사의 CONFIRMED | 이번에 모델 로딩·호출로 재계측하지 않음 |
| Path A 실제 Normalize 호출 수 | NOT TESTED | 소스상 예상2회와 이번 실행 관측값을 구분 |
| Path B 구성 | NOT IMPLEMENTED | 외부 Normalize만 제거하는 실험 후보를 아직 만들지 않음 |
| Path B 실제 Normalize 호출 수 | NOT TESTED | 단일화 성공이라고 보고하지 않음 |
| 기존 wrapper/Path A 동등성 | NOT TESTED | Baseline forward 실행 전 중단 |
| Tensor 통계 | NOT TESTED | 원본 shape, dtype, min/max/mean/std, backbone 입력 모두 미측정 |
| core/post 후 score | NOT TESTED | 모델 실행 없음 |
| threshold 교차 | NOT TESTED | score가 없어 판단 불가 |
| 모델 상태의 추론 전후 불변성 | NOT TESTED | 모델을 생성하지 않았으며 파일 무결성과 구분 |

결과값을0으로 채운 가짜 score 표나 score_comparison.json을 생성하지 않았다. 호출 횟수0은 실제 실행 부재를 뜻하며 anomaly score0이라는 뜻이 아니다. Path B가 기술적 입력 계약에 적합하다는 결론도 이번에는 내리지 않는다.

## 6. 재개에 필요한 사용자 입력·승인

### 필수: 독립 정상 개발 이미지3~5건의 명시적 allowlist

다음 정보를 제공하거나 해당 manifest를 승인해야 한다.

1. 실제 서버 관리 **중립 image_id 3~5개**. 존재하지 않는 ID를 개발자가 임의로 만들고 승인된 것으로 취급하지 않는다.
2. 각 ID가 기존 승인된 정상 개발 이미지임을 보여 주는 출처 근거. 평가 정답 파일이나 결함 폴더 분류로 대체하지 않는다.
3. 학습180·Calibration29와 원천이 겹치지 않고 평가용도 아니라는 근거. 파일명 차이만으로 내용 중복이 없다고 단정하지 않는다.
4. 기존 허용 metadata와 승인된 ID만으로 안전하게 실제 파일을 해석할 방법. 전체 dataset/클래스 폴더 scan이 필요하지 않아야 한다.
5. 가능하다면 입력 content hash와 사용 범위. 원본 경로나 라벨은 Agent/API/기본 실험 결과에 노출하지 않는다.

현재 확인한 metadata로는 구체적인3~5개를 추천할 근거가 없어, 승인 요청용 ID 목록을 임의 생성하지 않았다.

위 데이터를 제공하기 어렵다면 **중립 합성 입력으로 대체할지 별도 승인**이 필요하다. 이는 실제품 정상 개발 이미지 실험과 다른 범위이며, 승인 전 생성하거나 실행하지 않는다. 학습/Calibration/평가 이미지를 금지 조건을 우회해 쓰는 방안은 제안하지 않는다.

### 데이터 승인 후에만 수행할 예정인 절차

- 단일 공식 모델 로딩, CPU/eval/inference_mode, process·결과 경로 격리.
- 기존 wrapper 재사용 Path A의 동등성을 먼저 검증하고, 사전에 dtype/환경에 근거한 수치 허용오차를 정한다. 이번에는 오차나 동등성 PASS를 선언하지 않는다.
- Path B는 외부 Normalize만 제거하고 decode/색변환/Resize/scale/내부 전처리/후처리/모델 상태를 동일하게 둔다.
- 최대5장 × A/B 각1회 + Baseline 동등성 추가1회라면 최대11회로 설계할 수 있다. 모델 로딩 중 추가 forward가 발생할 수 있는 구현도 사전 계수·차단하여 **전체 상한15회**를 넘기지 않는다. 이번 실제 호출은0회다.
- Normalize 실제 호출 수, backbone 전 Tensor 및 core/post 후 score를 구분해 기록한다. 관측용 hook이 값을 바꾸지 않는지도 확인한다.
- 모든 결과는 승인 후 새 실험 전용 출력에만 저장하고 운영 ID/JSONL/DB와 연결하지 않는다.

## 7. 통계·threshold·후속 단계의 한계

이번에는 실측이 없어 score 절대/상대 차이·threshold 교차·입력 적합성·기존 점수 영향 모두 **NOT TESTED**다. 기존34.1442의 재사용 가능성은 결정하지 않았다.

재개 후 소수 정상 이미지에서 score 변화가 관찰되더라도 Precision/Recall/AUROC, 전체 정상 분포, 최적 threshold 또는 영상 ROI 성능은 판단할 수 없다. Path B 점수가 낮거나 A/B 판정이 같아도 새 경로의 우수성 또는 threshold 통계적 유효성의 증거가 되지 않는다.

Calibration29건의 후속 검증 필요 여부는 아직 결정할 실측 근거가 없다. 필요시 별도 단계로 **29건, 기존/후보 각1회로 최대58회 및 허용된 별도 Baseline 예산**을 명시해 승인받아야 한다. 이는 이번 상한15회를 확장하는 요청이 아니라 완전히 별도 작업의 제안이다. 기존 split 보존, 평가 데이터 분리, 운영 metadata 미변경, threshold 재계산 없음이 기본이며 재보정은 추가 승인 사항이다. 이번에는 Calibration 전체·일부 모두 사용하지 않았다.

기존 모델과 공식 전처리를 보존하고, 승인된 데이터로 비교 증거를 확보한 뒤 전처리 수정 여부를 판단한다. ROI 공통 검사 연결·AUTO·React 구현은 시작하지 않는다.

## 8. 보호·검증 결과

기존 파일236개의 시작 SHA256을 기록하고 종료 시 비교했다. 대상은 기존 소스/테스트/문서/모델/운영 JSONL/영상/병렬 작업 파일이며, 데이터셋 원본을 대량으로 읽거나 해싱하지 않았다. 실제 비교 결과 **기존236개 파일의 hash 변경0건, 누락0건, 추가는 이 보고서1개**였다. 공식 checkpoint hash도 위 기록과 일치했다.

- 모델 가중치/checkpoint/메모리 뱅크/threshold/운영 전처리: 변경 없음. 모델 로딩·추론·저장 없음.
- 운영 검사·로그 JSONL 및 Agent 기록: 쓰기 없음. 검사 ID 발급·검사 API 호출 없음.
- PostgreSQL ROI: 접속·변경 없음. Docker 컨테이너/Volume 조작 없음.
- VideoFileSource/Grab/CaptureStore/원본PNG/H.264: 변경·입력 사용 없음.
- Ground Truth/금지 외부 평가 경로: 파일·디렉터리 접근 없음. 데이터 선정을 위해 평가 라벨을 사용하지 않음.
- 실제 Gemini API 요청: **0회**.
- Git add/commit/push/reset/clean/restore: **0건**.
- 패키지 설치·환경 업데이트·네트워크 API 요청: **0건**.
- pytest: **실행하지 않음**. 데이터 게이트에서 중단했으므로 A/B 테스트 성공으로 보고하지 않음.

실행 명령은 읽기 전용 Git 상태, 관련 소스·문서·공개 시나리오 metadata 검색, `python -B -`의 JSON 집합 대조, 파일 SHA256 비교 및 신규 보고서 공백 검사뿐이다. 실제 학습/Calibration 스크립트를 실행하지 않았다. 기존 발표 자료나 다른 에이전트 변경을 정리하지 않았다.

신규 보고서의 `git diff --no-index --check -- NUL <보고서>`는 공백 오류 진단이 없었고, 별도 줄 끝 공백 검사도0건이었다. exit1은 빈 파일과 신규 보고서의 차이이며 공백 오류가 아니다. LF→CRLF 안내만 있었고, 무관한 발표 문서의 공백은 검사·수정하지 않았다.

## 9. 최종 요청

**학습180·Calibration29·평가 데이터와 분리된, 정상 출처가 확인되는 개발 이미지3~5건의 중립 image_id allowlist와 이번 추론 사용 승인을 제공해 주세요.** 또는 별도 범위로 중립 합성 입력 사용을 명시 승인해 주세요.

입력 게이트가 해소되기 전에는 모델을 로드하지 않고 여기서 종료한다. **B-2B는 BLOCKED이며 전처리 문제 해결이나 실험 COMPLETE가 아니다.**
