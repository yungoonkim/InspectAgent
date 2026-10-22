# A-3-2-B Sidecar 버전 필수화 및 격리 회귀

작성일: 2026-10-21. **버전 검증 수정·격리 검증 PASS. 운영 활성화·서버 재시작은 미실시이며 별도 승인 대기.**

## 1. 원인과 최소 수정

`backend/quality_shadow_metrics.py:62`의 `ShadowResult.schema_version`과 다음 줄의 `algorithm_version`에 각각 상수 기본값이 있었다.
Pydantic `model_validate`는 입력에 두 필드가 없으면 validator 실행 전에 기본값을 채웠다.
따라서 `ShadowStore.read`가 읽은 실제 저장 JSON이나 `publish`의 외부 입력에서 버전이 누락돼도 정상으로 수락됐다.
저장 경로에 버전 문자열이 있다는 사실은 JSON 자체의 버전 존재를 입증하지 않는다.

수정은 같은 모듈의 세 줄 변경에 한정한다.
- `ShadowResult`: 두 Literal 필드의 기본값을 제거해 필수 입력으로 만든다.
- `finish`: 내부 생성 시 `schema_version=SCHEMA_VERSION`, `algorithm_version=ALGORITHM_VERSION`을 명시한다.
- 정상 계산과 `failed_result` 모두 기존 `finish`를 사용하므로 성공·부분 실패·전체 실패 결과에 버전이 들어간다.

지원 값과 비교 방식은 기존 Literal 그대로다.
- schema_version: 정확히 `quality-shadow-v1`
- algorithm_version: 정확히 `opencv-original-exact-variance-v1`

새 버전명, 문자열 trim, 대체값, 과거 파일 마이그레이션은 도입하지 않았다.
계산식·분모 정책·수치·단위·처리 방식·출력 경로·멱등성 키는 변경하지 않았다.

## 2. 생성·저장·재조회 경로

1. 원본 PNG를 기존 방식으로 검증하고 `measure_pixels` 또는 `failed_result`가 `finish`를 호출한다.
2. 내부 생성 함수는 두 버전을 명시해 `ShadowResult`를 만든다.
3. `ShadowStore.publish`는 기존대로 전체 모델을 재검증한다. 버전이 누락·잘못된 입력은 잠금/디렉터리 생성 전에 거부된다.
4. 기존 완성 파일은 `read`에서 원본 JSON을 파싱한 뒤 같은 필수 모델로 검증한다. 누락된 버전을 보완하지 않는다.
5. 저장은 기존 exclusive TMP → JSON/flush/fsync/close → `os.link` 원자적 무덮어쓰기 발행 그대로다.
6. 동일 키의 기존 파일이 정상이고 계측 내용이 같으면 재사용한다. 시각/elapsed 차이만 제외하는 기존 정책을 유지한다.
7. 기존 JSON의 버전이 없거나 잘못되면 `SHADOW_RESULT_CONFLICT`다. Worker도 기존 결과 재사용/재계산/자동 복구하지 않으며 충돌 카운터로 관측한다.

기존 `quality_shadow_store.py`, `quality_shadow_worker.py`, Grab 저장 연결 코드는 수정하지 않았다.
원본 파일을 읽기 과정에서 다시 쓰거나 버전을 채워 넣지 않는다. 손상·내용 충돌도 원래 무덮어쓰기 정책을 따른다.

## 3. 실제 변경 파일

- `backend/quality_shadow_metrics.py`: `ShadowResult`, `finish`만 수정.
- `tests/test_quality_shadow_versions.py`: 합성 PNG/임시 저장소 기반 신규 75건.
- `tests/test_quality_shadow_integration.py`: 버전 검증 실패가 원 검사 응답/JSONL/이벤트/RIG에 전파되지 않는 3건 추가.
- 이 문서.

이전 사용자 변경과 A-3-1/A-3-2 파일은 그대로 보존했다. `backend/config.py`, 실제 `.env`, Gemini 설정을 수정하지 않았다.

## 4. 테스트 실행 및 결과

최초 실패 4건을 **수정 전에 다시 실행**해 같은 실패를 확인했다. 테스트의 기대 조건을 완화하거나 xfail로 바꾸지 않았다.

| 실행 | PASS | FAIL | ERROR | SKIP | 증거 디렉터리 |
|---|---:|---:|---:|---:|---|
| 수정 전 원래 4건 재현 | 0 | 4 | 0 | 0 | a3-2b-before-20261021-01 |
| 수정 후 동일 4건 | 4 | 0 | 0 | 0 | a3-2b-four-after-20261021-01 |
| 최종 관련 회귀 | **235** | **0** | **0** | **0** | a3-2b-regression-20261021-01 |

모든 증거는 `data/outputs/quality-shadow-validation/` 하위에 있다.
각 실행의 `backend.xml`, `pytest.log`, `safety.json`을 보존했다. 최종 실행에는 `selection.json`도 있다.
4건은 최종 235건에 포함되므로 별도 합산하지 않는다. 최종 JUnit 시간26.701초.

| 최종 실행 파일 | 통과 수 |
|---|---:|
| test_quality_shadow_activation_readiness.py | 11 |
| test_quality_shadow_versions.py | 75 |
| test_quality_shadow_metrics.py | 25 |
| test_quality_shadow_store.py | 17 |
| test_quality_shadow_worker.py | 8 |
| test_quality_shadow_integration.py | 18 |
| test_grab_inspection.py | 35 |
| test_reinspection_workflow.py | 46 |
| 합계 | **235** |

버전 테스트는 모델 검증/발행 입력/실제 JSON 재조회 각각에서 누락, 양쪽 누락, null, 빈 문자열, 공백/탭/개행, 정수, 실수, bool, 배열, 객체, 지원하지 않는 값을 거부하는지 확인한다.
정상·부분·실패 내부 생성, 필수 JSON Schema, 정상 저장/재조회/멱등성, 누락 파일의 중복 요청/Worker 재사용 거부와 원본 바이트 보존도 검증했다.
기존 저장 회귀는 실제 Windows 임시 파일시스템의 hard-link 무덮어쓰기, OS lock/스레드 경합, 발행 직전 경쟁, 부분 쓰기/권한/디스크/미지원 파일시스템 실패를 포함한다.
Worker 계산1+대기1, 포화/중복/종료, OFF에서 Worker·Sidecar 미생성, 원 판정·품질 경고 우선순위·저장 실패 경로는 기존 격리 테스트로 확인했다.

### 재실행 명령

Miniconda Prompt에서 `conda activate vision-insight` 후 프로젝트 루트에서 실행한다.
아래 output은 **아직 존재하지 않는 새 이름**으로 지정한다. 환경변수 설정은 이 테스트 프로세스 내부에만 적용된다.

```bat
python -B -c "import json,os; from pathlib import Path; os.environ.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',QUALITY_SHADOW_ENABLED='false',VISION_REVIEW_LIVE_ENABLED='false'); from scripts.safe_regression_backend import run_tests; output=Path('data/outputs/quality-shadow-validation/a3-2b-new-unique-run').resolve(); output.mkdir(parents=True,exist_ok=False); selection=['tests/test_quality_shadow_activation_readiness.py','tests/test_quality_shadow_versions.py','tests/test_quality_shadow_metrics.py','tests/test_quality_shadow_store.py','tests/test_quality_shadow_worker.py','tests/test_quality_shadow_integration.py','tests/test_grab_inspection.py','tests/test_reinspection_workflow.py']; (output/'selection.json').write_text(json.dumps(selection,indent=2),encoding='utf-8'); raise SystemExit(run_tests(output,selection))"
```

실제 .env는 읽지 않는다. 기존 runner의 임시 경로 주입과 네트워크·운영 쓰기·실제 모델 차단을 그대로 사용했다.

## 5. 운영 보호 검증

코드 수정 전 읽기 전용 프로세스 확인에서 기존 Uvicorn PID21796은 reload=false였다.
프로세스 환경을 변경하거나 실행 중 모듈을 hot patch하지 않았다. 디스크 코드 수정과 서버 적용은 다르다.

보호 증거: `data/outputs/quality-shadow-validation/a3-2b-20261021-protection-01/`.
- `protection-before.json`: 이번 작업 시작 기준선183개.
- **`protection-final.json`을 최종 판정으로 사용**: 승인한 `quality_shadow_metrics.py`만 변경, 예상 외 변경0.
- 나머지182개 불변: 사용자 config/기존 결정·품질·Grab·main·store·worker 코드, 검사/이벤트 JSONL, Capture PNG4개, 영속 Crop PNG82개와 매니페스트, RIG/Vision 저장 상태 등.
- 82개는 이번에 존재한 전체 영속 Grab PNG 수다. 과거 A-2의60개 분석 표본과 동일한 집계라고 표현하지 않는다.
- 초기 `protection-after.json`/`protection-result.json`은 PowerShell JSON 배열을 중첩 배열로 집계한 **검증 도구 오류**가 있어 무효다. 이를 변경/불변의 근거로 사용하지 않는다. 올바른183개 원본 기준선을 Python으로 읽어 파일별 SHA256을 재계산한 최종 파일로 확인했다. 초기 산출물도 삭제하지 않았다.

최종 테스트 안전 카운터: forbidden_io/network/real_prediction/real_load/real_gemini_api_calls 모두0, warnings0.
실제 서버 요청·시작·종료·재시작, 신규 운영 Grab/Capture, PatchCore 실제 로드/추론, Google 호출/외부 이미지 전송은0회다.
PostgreSQL은 연결하지 않았으므로 DB 내용 불변성은 직접 검증하지 않았다.
실제 `.env`는 열람/수정하지 않았다. Gemini config 파일 해시 불변과 기존 설정 기본값 회귀를 확인했으며 실행 중 서버의 비공개 환경값을 열람한 것은 아니다.

## 6. Phase 2 준비 상태와 남은 위험

**버전 필수성 차단은 해결됐고 코드·격리 검증 게이트는 PASS다. Phase 2는 사용자 별도 승인 및 현장 사전 게이트 확인 대기다.**

기본 OFF와 원 판정/API/JSONL 계약을 유지한다. 이번 수정은 품질 분류 기준이 아니고 실제 촬영 품질 정확도 개선을 입증하지 않는다.
운영 출력 volume의 권한/공간/하드링크 지원, 재시작 직전 최신 Capture 백업, 세션·RIG 영향, 단일 worker 조건은 실제 전환 직전에 다시 확인해야 한다.
메모리 큐 유실·native 계산 hard timeout 미보장·queue/I/O 개별 시간 미계측·전원 장애 내구성 한계는 그대로 남는다.

기존 readiness 보고서의18 PASS/4 FAIL 및 NOT READY는 수정 전의 역사적 결과다. 이번 문서가 버전 결함 해결 후의 격리 검증 결과를 추가한다. 과거 보고서나 운영 Sidecar를 일괄 수정하지 않았다.
별도 승인 없이 QUALITY_SHADOW_ENABLED=true를 설정하거나 서버를 재시작하지 않는다. 실제 제한 검사 및 Google 호출 승인도 서로 별개다.
