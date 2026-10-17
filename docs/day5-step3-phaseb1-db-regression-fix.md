# Day5 Step 3 Phase B-1-DB-R — JSONL 테스트 격리 회귀 보완

작성일: 2026-10-17. 상태: **COMPLETE**.

- PostgreSQL ROI 기능이나 운영 코드를 변경하지 않고 기존 실패 테스트의 데이터 준비 책임만 분리했다.
- 전체 pytest를 이번 작업에서 **정확히 1회** 실행했다: **1276 PASS / 0 FAIL / 51 SKIP, 25.56초**.
- PatchCore 중복 정규화: **UNRESOLVED / 변경 없음**. ROI → PatchCore 연결: **NOT IMPLEMENTED**.
- 실제 PatchCore 모델 로딩·추론 및 Gemini API 요청은 수행하지 않았다. 모델 관련 SKIP은 회귀 PASS를 의미하지 않는다.

## 1. 확인한 문서 및 변경 경계

AGENTS.md와 다음 문서를 읽고 현재 구현을 대조했다.

- `docs/visioninsight-auto-manual-inspection-spec.md`
- `docs/visioninsight-tech-stack-decisions.md`
- `docs/day5-step3-phasea-roi-patchcore-audit.md`
- `docs/day5-step3-phaseb1-db-postgresql-roi-completion.md`
- `docs/roi-postgresql-api.md`

작업 전 `git status --short`에는 Agent, 영상·DB 모듈, 설정·의존성, 발표 자료 등 다른 단계의 수정 및 미추적 파일이 이미 있었다. 이를 되돌리지 않았다. pytest.ini, pyproject.toml, setup.cfg, 루트 및 tests의 conftest.py는 현재 프로젝트에 없었다. 기존 격리 실행기 `scripts/run_roi_offline_tests.py`를 수정하지 않고 재사용했다.

이번 변경은 다음 두 파일뿐이다.

| 파일 | 변경 이유 |
|---|---|
| `tests/test_day2_integration.py:270` | 해당 테스트 전용 function-scope fixture로 임시 JSONL을 직접 준비 |
| `docs/day5-step3-phaseb1-db-regression-fix.md` | 실패 근거, 수정 및 실제 검증 결과 기록 |

운영 FastAPI, storage, 검사 엔진, Agent, PostgreSQL 스키마·마이그레이션·관리 권한 및 기존 테스트 실행 정책은 변경하지 않았다.

## 2. 최초 실패의 실제 근거

정확한 테스트: `tests/test_day2_integration.py::test_10_all_jsonl_lines_valid_json`.

수정 전 함수 정의는 267행, 전체 실행 실패 assertion은 280행이었다. 이전 전체 실행 증거 `data/outputs/roi-db-validation/full-01/results.xml`에 기록된 traceback은 다음과 같다.

```text
tests\test_day2_integration.py:280: in test_10_all_jsonl_lines_valid_json
    assert len(insp_lines) > 0
E   assert 0 > 0
E    +  where 0 = len([])
```

이전 결과는 **1274 PASS / 1 FAIL / 51 SKIP / 경고 2건, 26.40초**이며, JUnit 기준 총 1326건이다. 과거 보고를 원인으로 간주하지 않고 해당 JUnit 및 테스트·저장소 구현을 직접 확인했다.

### 기대 데이터와 조회 경로

기존 테스트는 fixture나 저장 작업 없이 `get_settings()`에서 다음 공유 경로를 얻었다.

- `settings.absolute_inspections_path`: `INSPECTIONS_FILE`
- `settings.absolute_inspection_logs_path`: `INSPECTION_LOGS_FILE`

경로 해석은 `backend/config.py:118`, `backend/config.py:124`, 설정 캐시는 `backend/config.py:277`에 있다. 이전 전체 실행에서는 두 경로가 `data/outputs/roi-db-validation/full-01/` 아래 JSONL을 가리켰다. 운영 `data/inspections.jsonl`과는 별개다.

기대 사항은 파일 존재, 비어 있지 않은 줄, 모든 줄의 `json.loads()` 성공 및 검사·로그 필수 키 존재였다. 하지만 테스트 자신이 이 데이터를 만들지 않았다.

### 테스트 순서 의존성: CONFIRMED

앞선 `test_02`부터 `test_09`는 API 검사를 수행해 공유 JSONL에 기록이 생기는 경로를 갖는다. `client` fixture는 TestClient만 만들며, 이 테스트의 JSONL을 준비하지 않는다.

`backend/main.py:452`에서 저장소를 얻어 빈 파일이 생성될 수 있고, `backend/main.py:453`에서 실제 inferencer를 구한 뒤 `backend/main.py:455`의 검사 워크플로를 호출한다. 기존 오프라인 정책은 실제 모델 로딩 시 SKIP하므로 이 선행 테스트들은 검사 기록을 쓰기 전에 제외된다. 이전 JUnit에서도 이 선행 8건이 모델 제외 사유로 SKIP된 것을 확인했다.

`JsonlInspectionStorage`는 `backend/storage.py:207`에서 저장 파일을 준비하지만, 실제 줄 추가는 `backend/storage.py:225`의 `save_inspection()` 및 `backend/storage.py:248`의 `save_log()`가 담당한다. 따라서 파일 존재만으로 검사 레코드 존재가 보장되지 않는다.

중요한 시간 구분: 이전 전체 실행 디렉터리의 JSONL은 실행 종료 후에는 검사 6줄, 로그 30줄이었다. 이는 뒤에서 실행된 다른 테스트의 기록이다. **실패 시점에 검사 줄이 0개였다는 traceback과 모순되지 않으며, 현재 그 파일이 비어 있다고 주장하지 않는다.**

### PostgreSQL 변경과의 관계

해당 테스트에는 PostgreSQL, ROI repository 또는 migration 호출이 없다. 확인한 원인은 **테스트 자체의 fixture 누락 및 다른 테스트의 공유 JSONL 쓰기에 대한 암묵적 의존**이다. 실제 모델 제외 정책이 이 기존 결함을 드러냈다. PostgreSQL 저장·조회 기능의 직접 회귀나 DB 오류, 설정 경로 충돌을 원인으로 볼 근거는 발견하지 않았다.

## 3. 수정 전 단독 재현

운영 파일과 분리한 새 실행 디렉터리에서 먼저 실패를 재현했다. 이 단일 테스트는 모델 추론을 호출하지 않는다.

| 실행 증거 디렉터리 | 준비 상태 | 결과 | pytest 시간 |
|---|---|---|---|
| `db-r-before-single` | 새 격리 경로, JSONL 없음 | 0 PASS / 1 FAIL / 0 SKIP | 1.25초 |
| `db-r-before-empty` | 두 빈 JSONL만 준비 | 0 PASS / 1 FAIL / 0 SKIP | 1.22초 |

첫 실행은 원래 273행 `assert insp_path.exists()`에서 실패했다.

```text
E   AssertionError: inspections.jsonl must exist
E   assert False
```

빈 파일 실험은 일회성 메모리 pytest plugin에서 실행기 설정 이후의 테스트 전용 경로만 touch했다. 테스트 소스·운영 데이터는 수정하지 않았다. 이 실행은 이전 전체 결과와 동일하게 원래 280행의 `assert 0 > 0`으로 실패했다. 해당 실험에는 메모리에 등록한 plugin의 assert-rewrite 경고 1건이 있었으며, 제품 코드 경고나 최종 회귀 실패가 아니다.

이 두 재현으로 선행 파일·데이터가 없으면 단독 실행이 불가능함을 확인한 **후에만** fixture를 수정했다.

## 4. 최소 수정 및 데이터 흐름

### 수정 전

```text
다른 API 테스트 → 공유 JSONL 쓰기(모델 SKIP 시 실행되지 않음)
                         ↓
test_10 → get_settings()의 공유 JSONL 조회 → 파일 없음 또는 0줄 FAIL
```

### 수정 후

```text
test_10의 tmp_path
  → 전용 JsonlInspectionStorage
  → Pydantic InspectionRecord / InspectionLogRecord 각 2건 준비
  → 실제 save_inspection()/save_log() 직렬화
  → 해당 임시 파일만 조회 → 모든 JSONL 줄 파싱 및 필수 키 검증
```

`serialization_jsonl_paths` fixture는 function-scope이며 전역 설정, 전역 storage singleton, 다른 테스트 또는 API 호출을 사용하지 않는다. 합성 ID와 명시적인 `source="test_fixture"` 및 합성 데이터 설명을 사용한다. 원본 이미지, 검사 결과, Ground Truth 또는 운영 ID를 복사하지 않는다.

fixture는 스키마상 `UNKNOWN / NORMAL / COMPLETED / SKIPPED / REINSPECT / DEFECT_DETECTION_UNAVAILABLE` 레코드를 구성한다. 이는 직렬화 검증을 위한 합성 데이터이며 실제 검사·모델 점수·관측 로그라고 주장하지 않는다. 검사 엔진을 실행하거나 서버 판정 규칙을 바꾸지 않는다.

기존 파일 존재, nonempty, JSON 파싱 및 키 assertion을 모두 유지했다. 검사와 로그 각각 **정확히 2줄**이라는 assertion을 추가해 준비 데이터와 검증 대상의 정합성도 확인한다. SKIP 추가, assertion 삭제 또는 예외 무시는 없다.

이 테스트가 보장하는 범위는 독립된 JSONL 저장·파싱 계약이다. 실제 검사 API가 생성한 레코드의 모델 통합 검증을 대체하지 않는다. 같은 파일의 기존 API·동시성 테스트는 그대로 보존했으며 실제 모델 필요 항목은 기존 정책에 따라 SKIP된다.

## 5. 실행 명령 및 검증 결과

환경: Miniconda `vision-insight`, Python 3.11.16, FastAPI 0.143.0, pytest 9.1.1. 별도 환경 또는 패키지를 설치하지 않았다.

공통 명령 형식:

```powershell
& 'C:/Users/USER/miniconda3/envs/vision-insight/python.exe' -B scripts/run_roi_offline_tests.py <run-name> <test-path-or-nodeid> -q --tb=short -rs
```

실행기는 각 run-name에 대해 새 `data/outputs/roi-db-validation/<run-name>/`를 사용하며 기존 증거를 덮어쓰지 않는다. 운영 JSONL·캡처 경로와 분리하고, 실제 모델 로딩·추론 및 외부 통신을 차단한다. 테스트 및 DB fixture는 ASGI/Mock transport 또는 localhost PostgreSQL만 사용한다.

| 범위 / run-name | PASS | FAIL | SKIP | pytest 시간 |
|---|---:|---:|---:|---:|
| 수정 후 단일 / `db-r-single-fixed` | 1 | 0 | 0 | 1.20초 |
| 새 프로세스·새 경로 재실행 / `db-r-single-repeat2` | 1 | 0 | 0 | 1.21초 |
| 새 프로세스·새 경로 재실행 / `db-r-single-repeat3` | 1 | 0 | 0 | 1.18초 |
| 같은 파일 / `db-r-file-fixed` | 2 | 0 | 10 | 1.30초 |
| JSONL·Agent 조회 및 정책 / `db-r-related-fixed` | 354 | 0 | 0 | 4.82초 |
| 검사·영상·캡처 / `db-r-inspection-video-fixed` | 95 | 0 | 6 | 4.34초 |
| 실제 PostgreSQL ROI / `db-r-postgresql-fixed` | 55 | 0 | 0 | 7.46초 |
| 전체 tests, 이번 작업 1회 / `db-r-full` | **1276** | **0** | **51** | **25.56초** |

중복 nodeid를 `--keep-duplicates`와 함께 전달한 `db-r-repeat-fixed` 실험도 1 PASS / 0 FAIL / 0 SKIP, 1.18초였으나 실제 수집은 1건이었다. 이를 3회 반복 검증으로 계산하지 않았다. 위 독립 3회는 서로 다른 프로세스·디렉터리의 실제 실행 결과다. 범위별 결과에는 중복 테스트가 있으므로 전체 수치에 합산하지 않는다.

### 관련 실행의 실제 파일 목록

- `db-r-related-fixed`: `tests/test_storage.py`, `tests/test_agent_tools.py`, `tests/test_agent_history_comparison.py`, `tests/test_agent_service.py`, `tests/test_agent_day5_counterexamples.py`, `tests/test_agent_warning_policy_integration.py`, `tests/test_agent_error_policy.py`, `tests/test_agent_t06_isolation.py`.
- `db-r-inspection-video-fixed`: `tests/test_inspections.py`, `tests/test_video_source.py`, `tests/test_capture_store.py`, `tests/test_video_api.py`.
- `db-r-postgresql-fixed`: `tests/test_roi_schemas.py`, `tests/test_roi_postgresql.py`.

전체 실행 명령:

```powershell
& 'C:/Users/USER/miniconda3/envs/vision-insight/python.exe' -B scripts/run_roi_offline_tests.py db-r-full tests -q --tb=short -rs
```

JUnit `db-r-full/results.xml`: **tests=1327, failures=0, errors=0, skipped=51, time=25.542초**. pytest 터미널 요약 시간은 25.56초다. 수정 대상은 전체 실행에서도 PASS다.

이전 전체 1326건 이후 기존 PostgreSQL 작업에서 main 라우터/CORS 통합 테스트 1건이 추가돼 현재 총 1327건이다. 따라서 PASS 증가 2건은 기존 FAIL 1건의 해결과 이미 추가된 테스트 1건을 포함한다. 이번 작업에서 테스트 수를 임의로 늘려 실패를 숨긴 것이 아니다.

## 6. 51 SKIP의 정확한 구성

| 사유 | 건수 |
|---|---:|
| 실제 PatchCore 로딩·추론 금지, normalization UNRESOLVED | 47 |
| 기존 T03 주입 이미지 fixture 없음 | 4 |

기존 4건은 다음과 같다.

- `tests/test_day3_5_integration.py:221`: No injected images registered. Run generate_t03_fault.py first.
- `tests/test_day3_5_step4.py:147`: No fault-injected images found.
- `tests/test_day3_5_step4_5.py:173`: T03 injected image not present.
- `tests/test_day3_5_step4_5.py:258`: T03 injected image not present.

fixture를 생성하거나 이 SKIP을 PASS로 바꾸지 않았다. 같은 파일의 10 SKIP, 검사·영상 범위의 6 SKIP도 실제 모델 제외 정책이며 위 전체 47건의 일부다. 이전 보고의 경고 2건은 과거 결과로 유지한다. 이번 최종 pytest 요약에는 경고 건수가 보고되지 않았으며 경고 필터를 변경하지 않았다.

## 7. PostgreSQL·운영 자산 보호

실제 PostgreSQL 테스트는 기존 `visioninsight_roi_test` DB와 `vi_roi_test` 계정만 사용했다. fixture가 UUID 기반 `roi_test_*` schema를 새로 만들고 기존 migration을 적용한 뒤 **그 fixture가 만든 schema만** 제거한다. migration 파일·관리 정책·DB 스키마 정의는 변경하지 않았다. 전체 DB 초기화, 기존 ROI 삭제, 컨테이너 restart/delete 또는 volume 삭제는 수행하지 않았다.

개발 DB는 작업 전후 `SET TRANSACTION READ ONLY`로 네 ROI 테이블을 조회해 정렬된 전체 행의 SHA256과 건수를 비교했다. 네 테이블 모두 작업 전후 **0건 / 동일 SHA256**이었다. 빈 배열 fingerprint는 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`다. 원래 개발 데이터가 비어 있었다는 뜻이며, 이번에 삭제한 것이 아니다. 테스트 후 남은 `roi_test_*` schema는 0개였다. DB 연결 문자열·비밀번호는 출력하지 않았다.

기존 컨테이너 `visioninsight-roi-postgres`와 volume `visioninsight-roi-pgdata`는 조작하지 않았다. 이 작업에서 DB 재시작 영속성을 새로 검증했다는 주장도 하지 않는다.

작업 전 수집한 기존 파일 **234개**의 SHA256을 재검사했다. 변경은 승인된 `tests/test_day2_integration.py` 1개뿐이고 누락은 0개였다. 이후 이 보고서 1개를 새로 추가했다. 운영 backend, 모델, 기존 영상·생성 스크립트, 기존 문서·발표 자료 및 병렬 작업 파일은 원래 작업 트리 상태를 유지했다.

운영 JSONL SHA256 전후 동일:

| 파일 | SHA256 |
|---|---|
| `data/inspections.jsonl` | `73d2783d3ee783ef3ea06002c989725e877aabb5d7ce1689fcd5132f5a3b3b68` |
| `data/inspection_logs.jsonl` | `bd316512f429823180b13796caa7a350f665eeccabbdbfb443e92c8e739ee5b9` |

공식 checkpoint와 H.264 영상 SHA256도 기존 값과 동일했다. threshold `34.1442`, 외부·내부 Normalize 및 최종 판정 우선순위는 변경하지 않았다. 기존 캡처 PNG를 삭제·수정하지 않았다.

- 실제 Gemini API 요청: **0회**.
- 실제 PatchCore 추론·calibration·재학습: **0회**.
- 외부 Ground Truth 열람·목록 조회·복사·수정: **0건**.
- Git add/commit/push/reset/clean/restore: **0건**.
- PostgreSQL/SQLAlchemy/Alembic 신규 설치·업데이트: **0건**.

## 8. 환경 및 Git 검사

`python -m pip check`: **No broken requirements found.**

`git diff --check -- tests/test_day2_integration.py`: exit 0, 공백 오류 없음. Git의 LF → CRLF 안내는 공백 검사 실패가 아니다. 신규 보고서는 `git diff --no-index --check -- NUL <보고서>`로 검사했으며 공백 오류 진단이 없었다. 이 명령의 exit 1은 빈 파일과 신규 보고서의 차이 때문이며 공백 오류로 분류하지 않는다. 다른 에이전트 발표 문서에 대한 전체 diff 검사나 수정·복원은 하지 않았다. 기존 Git 변경 목록과 이번 두 파일을 구분했다.

테스트 증거는 각 실행 디렉터리의 `results.xml`에 남아 있으며 Git 무시 대상이다. 일회성 실패 재현 로그도 보존했다. 이 보고서의 결과는 이전 1268 PASS 또는 이전 1274 PASS / 1 FAIL을 재사용한 수치가 아니라 이번 실행의 실측 결과다.

## 9. 다음 단계 조건 및 한계

이번 회귀 보완의 완료 기준은 충족했다: 원인 확인, 독립 fixture, 단독 반복 PASS, 관련 회귀 PASS, 전체 0 FAIL 및 운영 자산 보존이다. PostgreSQL ROI 관리 기능과 기존 Mock/저장소/영상 회귀를 진행할 수 있는 상태다.

그러나 **PatchCore 중복 정규화 문제는 여전히 UNRESOLVED**다. 실제 모델 점수, calibration 호환성, threshold 재사용 가능성 및 영상 ROI 성능은 이번 검증 대상이 아니다. 47건의 모델 제외가 유지되므로 실제 모델 회귀 완료로 해석하면 안 된다.

Step 3 Phase B-2의 ROI → PatchCore 연결은 별도 사용자 승인 및 전처리 문제에 대한 안전한 후속 결정 이후에만 진행한다. 실제 ROI Crop, 추론 연결, 자동 검사, React 또는 Gemini 확장은 시작하지 않고 여기서 종료한다.
