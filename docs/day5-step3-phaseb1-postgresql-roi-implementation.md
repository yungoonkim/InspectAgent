# Day5 Step 3 Phase B-1 — 전처리 안전 게이트 중단 보고

## 1. 최종 상태와 실제 수행 범위

- 확인일: 2026-10-17.
- **상태: BLOCKED — 실제 로드한 모델 구성과 소스 호출 경로에서 중복 ImageNet 정규화를 확인했다.**
- 사용자 Phase 0 규칙은 문제가 없음을 충분히 확인한 경우에만 이후 구현을 진행하도록 요구한다. 따라서 **PostgreSQL 환경 구성·패키지 설치·ROI 저장소/API/마이그레이션 구현에 진입하지 않았다.**
- 이 파일명은 요청된 결과 보고서 경로다. PostgreSQL 구현 성공 보고서라는 의미가 아니다.
- 기존 전처리·가중치·34.1442·판정 정책은 수정하지 않았다. 모델 구성 로딩은 했지만 **실제 PatchCore 이미지 추론·predict·검사 기록 생성은 하지 않았다.**

## 2. 필수 문서·기존 상태 확인

아래 필수 문서는 모두 존재하며 확인했다.

1. `AGENTS.md`
2. `docs/visioninsight-auto-manual-inspection-spec.md`
3. `docs/visioninsight-tech-stack-decisions.md`
4. `docs/day5-step3-phasea-roi-patchcore-audit.md`
5. `docs/day5-step2-phaseb-video-grab-implementation.md`

최우선 AUTO/MANUAL 문서에는 영상/Grab 미구현 및 1175 PASS라는 과거 상태가 남아 있다. 현재 코드와 Step 2 Phase B 보고서는 VideoFileSource/Grab/CaptureStore 및 전체1268 PASS를 기록한다. 기능 요구사항은 변경하지 않고 이 상태 차이를 구분한다.

PostgreSQL은 사용자가 선택한 정식 관계형 DB다. SQLite/Firestore 대체 구현은 하지 않았다. SQLAlchemy/Alembic은 기존 결정 문서에서 권장 후보이며 이번에 채택·설치됐다고 기록하지 않는다. 영속 ROI 소유권에 임시 캡처 세션을 사용하던 Phase A 후보는 이번 사용자 지침에 따라 폐기 대상이며, 관리 인증/승인 경계는 재개 후 설계해야 한다.

작업 루트는 `C:\Users\USER\AI-NativeAgent\Project\InspectAgent`다. 시작 Git 변경·미추적 목록과 코드/문서/모델/영상/운영 JSONL 등 기존213파일의 SHA256을 기록했다. 기존 Agent·발표·임시 회귀·다른 에이전트 변경을 되돌리지 않았다.

## 3. 전처리 호출 그래프 — CONFIRMED

### 3.1 서버 및 외부 wrapper

- `backend/inspection.py:404`: 기본 cv2.imread 결과를 사용한다. 기존 경로는 BGR3 이미지다.
- `backend/inspection.py:508`: 같은 배열로 inferencer.predict(image)를 호출한다.
- `backend/ml/patchcore_inferencer.py:135`: ndarray BGR→RGB→PIL, grayscale ndarray→RGB, 파일/PIL 입력도RGB로 변환한다.
- `backend/ml/patchcore_inferencer.py:53`: Resize256×256→ToImage→float32(scale=True)→**ImageNet Normalize**.
- `backend/ml/patchcore_inferencer.py:157`: batch 차원을 추가해 `[1,3,256,256]`를 만든다.
- `backend/ml/patchcore_inferencer.py:178`: **전체 Lightning model**을 호출한다. 내부 feature model을 직접 호출하는 구조가 아니다.

uint8 입력은 scale 변환 후0~1 범위가 되고 외부 Normalize가 적용된다. 이 결과는 이미 정규화된 RGB Tensor이며 raw0~1 Tensor가 아니다.

### 3.2 설치 라이브러리의 실제 모델 호출

다음 파일은 현재 `vision-insight` 환경의 소스를 읽어 확인했다. 인터넷 문서의 다른 버전을 추정한 것이 아니다.

- `%CONDA_PREFIX%/Lib/site-packages/anomalib/models/components/base/anomalib_module.py:246`: forward 정의.
- 같은 파일`:270`: 활성 pre_processor에 batch 전달 → 내부 feature model → post_processor.
- `anomalib/pre_processing/pre_processor.py:151`, `:164`: forward에서 **export_transform** 실행.
- `anomalib/models/image/patchcore/lightning_model.py:182`, `:223`: 기본 Resize256+ImageNet Normalize 구성.

즉 현재 경로는 다음과 같다.

```text
uint8 BGR
  → RGB / Resize256 / float32 0~1
  → 외부 ImageNet Normalize
  → [1,3,256,256]
  → Lightning forward
  → 활성 PreProcessor.export_transform
  → 내부 Resize256 / ImageNet Normalize
  → 내부 PatchCore feature model
  → post_processor
```

## 4. 실제 로드한 구성 확인 — 이미지 추론 없음

### 방법

Miniconda vision-insight Python의 stdin 진단으로 기존 PatchCoreInferencer를 CPU에 구성 로딩했다. 새 inference 구현·모델 수정·데이터셋 읽기는 하지 않았다.

```text
C:/Users/USER/miniconda3/envs/vision-insight/python.exe -B -
```

진단 프로세스에 한해 HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE을 설정하고 socket connect/connect_ex를 차단했다. 추가 다운로드 없이 기존 자산으로 로딩했다. 실수로 추론하지 않도록 **Patchcore.forward를 프로세스 메모리의 예외 발생 guard로 잠시 대체**하고 로딩 후 구성 repr만 출력했다. 디스크의 라이브러리/모델/운영 소스는 변경하지 않았다. guard는 별도 프로세스 종료와 함께 사라진다.

성공적으로 완료·출력 확보한 진단의 exit code는0, 실행 시간 약8.20초였다. 이는 **모델 구성 확인 명령 시간이지 추론 latency가 아니다**. 초기 진단 시도에서는 완료 결과를 확보하지 못해 이를 별도 PASS 근거로 사용하지 않고, 결과를 확보한 아래 구성을 근거로 삼는다.

### 확인 결과

| 항목 | 실제 출력 |
|---|---|
| model type | Patchcore |
| memory bank | [9216,384] |
| training flag | false |
| external Resize | 256×256, bilinear, antialias=True |
| external dtype/scale | ToDtype(scale=True), 소스상 float32 |
| external Normalize | mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225] |
| internal preprocessor | **PreProcessor, 활성 객체 존재** |
| internal transform | Resize256, antialias=True + **동일 Normalize** |
| internal export_transform | Resize256, antialias=False + **동일 Normalize** |
| guarded Patchcore forward 호출 | **0회** |
| 차단된 네트워크 connect 시도 | **0회** |
| metadata calibrated_threshold | **34.1442** |

판정은 “이번에 두 Normalize에 이미지를 통과시켰다”가 아니라, **실제 로딩 상태와 기존 실행 코드가 두 Normalize를 순서대로 호출하도록 구성돼 있다**는 확인이다. 전체 forward를 실행하지 않고도 해당 중복 호출 계약을 특정할 수 있다.

확인한 체크포인트 SHA256은 로딩 전후 동일했다.

```text
4b239d28e72c63bf782cd1d31981d7f4362c591e7c23164e4c0ac8b5e99b52a3
```

이는 기존 승인 metadata의 hash와 일치한다. 원본/캡처/ROI 이미지 입력, score, anomaly_map, OK/NG 결과는 생성하지 않았다. timm 및 anomalib deprecation 경고2건은 진단 import 경고이며 pytest 신규 결과가 아니다.

## 5. 원인·입력 의미·영향

**확인한 원인:** 외부 wrapper가 정규화된 Tensor를 만들면서, 내부 PreProcessor를 유지한 전체 Lightning 모델을 호출한다. 현재 활성 export_transform에도 같은 Normalize가 있다. 내부 normalization을 별도로 꺼 주는 코드가 wrapper의 load/predict에 없다.

0~1 RGB 성분을 u, mean을 m, std를 s라 하면:

```text
외부 정규화 결과 z = (u - m) / s
내부 feature model에 전달되는 경로의 값 = (z - m) / s
```

두 번째 연산은 항등 변환이 아니다. 학습된 feature 거리·score/calibration 해석에 영향을 줄 수 있다. 각 입력의 수치 변화나 평가 성능 영향은 실제 추론을 하지 않아 **NOT TESTED**다.

현재 학습 코드 `scripts/train_patchcore.py:122`는 기본 Patchcore를 만들고, 설치 라이브러리의 `PreProcessor.on_train_batch_start`는 학습batch에 transform을 적용한다. Patchcore.training_step(`anomalib/models/image/patchcore/lightning_model.py:239`, `:255`)은 내부 self.model(batch.image)를 직접 호출한다. 현재 소스에서 학습 입력 경로와 서버 전체-forward 경로가 다름을 확인했다. 과거 학습 시점의 모든 코드/라이브러리 실행 상태까지 복원한 것은 아니다.

현재 calibration 코드 `scripts/calibrate_threshold.py:52`, `:69`도 같은 inferencer.predict를 사용한다. 따라서 **현재 코드를 그대로 실행하면** 같은 중복 경로를 사용한다. 하지만 저장된34.1442의 과거 산출 당시 transform fingerprint는 metadata에 없어, 과거 보정이 어느 실행 상태와 완전히 일치했는지 이번 확인만으로 확정하지 않는다.

정규화를 하나 제거하면 기존 점수와34.1442의 관계가 바뀔 수 있다. 따라서 한 줄 수정이라도 과거 판정·평가를 그대로 유효하다고 주장할 수 없다. **전처리·모델·threshold·Day4 완료 기록을 수정하지 않았다.**

## 6. 안전 게이트 적용과 미진행 범위

사용자 Phase0 중단 규칙과 기술 스택 결정 문서의 재개 규칙에 따라 여기서 구현을 중단했다. PostgreSQL 기능은 문제와 무관하게 따로 구현해도 된다고 임의 해석하지 않았다.

| 요청 영역 | 상태 |
|---|---|
| 전처리 소스/로드 구성 확인 | **완료, 중복 경로 확인** |
| PostgreSQL/Docker 실제 설치·버전·접속 조사 | **NOT TESTED — 안전 게이트 이후 단계 미진입** |
| SQLAlchemy/Alembic/psycopg 설치·채택 | **미수행** |
| PostgreSQL 이미지 pull/컨테이너·계정·volume 생성 | **0건** |
| ROI DB 테이블·제약·migration | **미구현** |
| Draft/Approved/Active·원자적 전환 | **미구현** |
| ROI 관리 인증·권한·API | **미구현** |
| 실제 PostgreSQL 통합·동시성·재시작 영속성 | **NOT TESTED** |
| 기존 검사/Grab/Agent 회귀 | **미실행** |
| 전체 pytest | **미실행** |
| pip check | **미실행**, 의존성 설치/변경0건 |

의존성 파일 requirements.txt/requirements-prod.txt에는 PostgreSQL/SQLAlchemy/Alembic 명시가 없음을 확인했지만, 이것이 현재 환경에 패키지가 전혀 설치되지 않았다는 증거는 아니다. Docker/PostgreSQL이 없다거나 동작하지 않는다고 단정하지 않는다. 접속 문자열/비밀번호/개인 환경 설정 값은 열거·출력하지 않았다.

최근 전체 pytest **1268 PASS / 0 FAIL / 4 SKIP / 경고2건**은 Step2 PhaseB의 이전 기록이다. 이번 실행치로 재사용하지 않는다. 이번에 새로운 pytest PASS/FAIL/SKIP 수를 만들지 않았다.

## 7. 필요한 별도 승인·재개안

### 우선 승인 사항

1. **전처리 수정 설계의 별도 승인:** 외부 wrapper와 내부 pre_processor 중 어디에서 단 한 번 정규화할지 선택하고 기존 학습·calibration 경로와 맞추는 최소안을 설계해야 한다.
2. **검증 범위의 별도 승인:** 수정 전후 transform 진입값 비교·허용 정상 데이터의 최소 추론·기존 calibration 해석을 확인할 범위가 필요하다. 이번에는 실제 추론을 승인받지 않았으므로 수행하지 않았다.
3. **기존 threshold34.1442 보호:** 기존 경로와 수치 호환을 확보할 수 없다면 자동으로 새 threshold를 산출하지 않는다. 영향 보고 후 별도 의사결정이 필요하다. 재학습/GT평가를 필수로 단정하지도 않는다.
4. **DB 작업 독립 재개 여부:** 전처리 문제가 보류된 동안 PostgreSQL ROI 설정 인프라만 독립 진행하려면, 이번 안전 게이트와 분리해서 진행해도 된다는 명시적 재승인이 필요하다.

### 최소 수정 후보(아직 미수정)

- `backend/ml/patchcore_inferencer.py`의 transform/load/predict 경계가 검토 대상이다. 외부 Normalize만 제거하는 안 또는 내부 전처리와의 역할을 명시하는 안을 학습/보정 계약과 대조해야 한다. 내부 core만 직접 호출하는 안은 post_processor/output 계약을 바꿀 수 있어 단순 우회로 권장하지 않는다.
- 전처리 수정 시 `tests/test_patchcore_inferencer.py`의 shape/score 존재 확인만으로는 부족하다. Normalize 실행 횟수·core 직전 Tensor 의미·경로별 동등성 회귀가 필요하다.
- 수정 검증 전후 모델/checkpoint hash, 기존 판정 우선순위, T05/T06 null·UNKNOWN·SKIPPED, Agent Evidence/판정 불변을 별도로 유지해야 한다.

DB 구현 재개 시 PostgreSQL만 사용하고 기존 JSONL은 유지한다. preset/version/명시 승인/active binding을 구분하고 source revision·원본 크기·product 범위의 활성 유일성·트랜잭션을 검증해야 한다. **임시 capture session을 영구 owner로 채택하지 않는다.** 로컬 운영자 권한 경계, 독립 테스트 DB, 명시 migration, 재시작 영속성부터 승인된 범위에서 구현한다. 이 목록은 현재 구현 결과가 아니다.

## 8. Phase B-2 인수 계약과 제한

지금은 Phase B-2 착수 준비가 완료되지 않았다. 전처리 게이트와 DB 기능 검증이 모두 선행해야 한다.

향후 AUTO는 PostgreSQL의 **저장·승인·활성화된 정확한 version**을 원본 좌표/영상 revision/제품 범위로 조회해야 한다. MANUAL은 사용자 ROI를 공통 서비스에 전달한다. 실제 Crop→PatchCore 연결과 제품 도착/Pause/Play는 이번에도 구현하지 않았다.

향후 검사 추적은 inspection_id, 입력 종류/capture_id 또는image_id, 원본 무결성, preset ID/version/좌표 snapshot, 모델 식별, 실제 시작/완료 시각을 남겨야 한다. 이번에 JSONL schema를 변경하거나 검사 결과를 PostgreSQL로 이전하지 않았다.

Cloud Run/Cloud SQL/과금/배포는 수행하지 않았다. PostgreSQL 선택은 공유 PNG·영상·분산 세션 문제를 해결하지 않는다는 기존 기술 결정은 유지한다.

## 9. 파일 변경·보호·종료

이번 신규 파일은 이 보고서1개이며, 기존 수정은 `docs/visioninsight-tech-stack-decisions.md`의 확인된 중복/게이트 BLOCKED/DB 미구현 상태 반영뿐이다. 기존 PhaseA/Day4/Step2 검증 기록은 덮어쓰지 않았다.

운영backend/tests/의존성/모델/전처리/threshold/승인영상/기존검사·Agent JSONL/캡처/READY/실E2E/발표/다른 에이전트 변경을 수정하지 않았다. 종료 보호 hash213개를 비교한 결과, 허용한 기술 스택 문서1개만 변경되고 나머지212개는 동일했다. 해당 범위에 추가된 파일은 이 보고서1개다. 기존 Git 변경·미추적 자산은 보존했다.

두 문서의 scoped `git diff --check`는 exit0이었다. 두 문서가 untracked임을 고려해 각각 `git diff --no-index --check -- NUL <문서>`로도 확인했으며 공백 오류 진단은 없었다. no-index의exit1은 새 문서/NUL 차이 반환이며 성공exit0으로 보고하지 않는다. LF→CRLF 안내와 공백 오류는 구분한다. 기존 발표 문서의 전체 공백 문제는 손대지 않았다.

실제Gemini API0회, 실제PatchCore 이미지추론0회, 신규검사/Grab/READY/실E2E0건, GT·외부평가 경로 열람/목록/복사0건, Git add/commit/push/reset0건. Python/Conda 패키지·시스템PATH·레지스트리·Docker·DB·클라우드 변경0건이다.

**전처리 또는 DB 작업 재개에 대한 사용자 승인을 기다리고 종료한다.**
