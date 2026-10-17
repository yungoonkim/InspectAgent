# Day5 Step 3 Phase B-1-DB — PostgreSQL ROI Persistence

## 1. 판정과 독립 승인

2026-10-17 결과: **전체 작업 PARTIAL**.

- PostgreSQL ROI 저장·버전·승인·활성화 기능은 구현했고 실제 PostgreSQL 신규테스트 **최종55 PASS / 0 FAIL / 0 SKIP**다.
- 앱 새프로세스 및 DB컨테이너 재시작 후 영속성 확인도PASS다.
- 전체회귀를1회만 실행하여 **1274 PASS / 1 FAIL / 51 SKIP / 경고2건 / 26.40초**를 얻었다. 실제모델 제외로 비어 있는 선행JSONL에 의존하는 기존Day2 테스트1건이 실패했다. 전체FAIL0으로 완료 선언하지 않는다.
- **PatchCore 전처리 문제: UNRESOLVED / 변경 없음. ROI→PatchCore 연결: NOT IMPLEMENTED.** 이번에는 모델 구성을 다시 로딩하지도 않았다.

사용자는 전처리 게이트와 분리한 DB구현을 명시 승인했다. 이전B-1 BLOCKED 기록은 삭제하지 않고 기술 스택 문서에 이번 독립 작업 상태를 추가했다. PostgreSQL을 SQLite/Firestore로 대체하지 않았다.

## 2. 사전 감사

AGENTS·AUTO/MANUAL 명세·기술 결정·PhaseA·B-1 중단·Step2 PhaseB 문서를 확인했다. 최우선 명세의 영상미구현/1175PASS 문구와 현재Step2 코드/1268PASS 기록은 과거상태 차이로 구분했다. 확정된 자동·수동 UX는 변경하지 않았다.

환경은 Python3.11.16/Miniconda vision-insight, FastAPI0.143.0, pytest9.1.1이다. Docker CLI29.1.5가 이미 있었지만 Desktop/엔진은정지 상태였다. 기존Docker Desktop을 시작했으며 설치·관리자설정·PATH 변경은 하지 않았다. 발견한 기존3개frontend 컨테이너는 모두종료 상태였고 변경/기동하지 않았다. 일반설치위치의PostgreSQL과PATH psql/pg_ctl, SQLAlchemy/Alembic/psycopg 배포는 발견되지 않았다. 개인 디렉터리 무차별검색은 하지 않았다.

기존ProductRegistry는 없다. 기존검사는product_id 문자열을 보관한다. 신규ROI는 명시적 환경설정 등록목록으로 제품을 제한하고, 기존검사·이미지Registry는 변경하지 않았다.

## 3. PostgreSQL 실행·보존·권한

- 실제서버 **PostgreSQL17.11 (Debian17.11-1.pgdg12+2)**.
- [Docker 공식 postgres 이미지](https://hub.docker.com/_/postgres)의17-bookworm을받아 실제digest로고정했다.
- 이미지: `postgres:17-bookworm@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826`.
- 컨테이너 `visioninsight-roi-postgres`, loopback포트 `127.0.0.1:55432`, 독립볼륨 `visioninsight-roi-pgdata`.
- 개발DB `visioninsight_roi`, 독립테스트DB `visioninsight_roi_test`.
- 역할: bootstrap은이전전용컨테이너초기화용, `vi_roi_migrator`는개발DB DDL, `vi_roi_app`은runtime DML, `vi_roi_test`는테스트DB/테스트스키마전용이다. 개발·테스트DB의PUBLIC CONNECT를제거했다.
- runtime은4테이블SELECT, preset/version/approval INSERT, preset head_version UPDATE, activebinding INSERT/UPDATE만허용한다. DDL/DELETE/과거version수정권한은없다. 실제권한조회로4테이블의SELECT=true/DELETE=false를확인했다.
- 임의테스트ROI는개발DB에남기지않았다. 종료확인시개발preset수0건이며 승인/활성기본설정도자동생성하지않았다.

새실행시재현순서(기존구성에서prepare/initialize를다시실행하지않는다):

```text
python -m pip install -r requirements-db.txt
python -B scripts/setup_roi_database.py prepare
docker compose --env-file .env.roi-db.local -f compose.roi-db.yaml up -d --wait
python -B scripts/setup_roi_database.py initialize
python -B -m alembic -c alembic.ini upgrade head
python -B scripts/setup_roi_database.py grants
```

실제명령은vision-insight Python과설치된Docker의절대경로를사용했다. 재시작은 `docker restart visioninsight-roi-postgres`, 정지는같은compose의stop을사용한다. 볼륨삭제/down-v는하지않았다. 로컬개발용DB는종료시실행상태로유지한다. Docker Desktop을처음시작한상태이며사용자가불필요하면기존도구의정지절차를선택할수있다.

## 4. 설정·비밀 관리

`scripts/setup_roi_database.py prepare`가난수비밀번호/관리토큰을 `.env.roi-db.local`에생성한다. 이미있으면덮어쓰지않는다. 파일은기존.gitignore의.env.*및.dockerignore의*.local에해당하며Git추적/이미지복사대상이아니다. 실제값은명령출력/문서/테스트결과에기록하지않았다.

필수키는 VISIONINSIGHT_DATABASE_URL / VISIONINSIGHT_MIGRATION_URL / VISIONINSIGHT_TEST_DATABASE_URL / VISIONINSIGHT_ROI_ADMIN_TOKEN이다. 제품은 VISIONINSIGHT_ROI_PRODUCT_IDS에중립ID를쉼표로명시등록한다. 현재개발기본값은빈목록이므로임의제품요청을거부한다.

ROI_MIN_SIZE기본32, ROI_ENVIRONMENT=local, ROI_ORIGINS는localhost/127.0.0.1:5173이다. 실제필드에는VISIONINSIGHT_접두사를사용한다. 실행환경의ENVIRONMENT도local이어야관리API를허용한다. 루트.env와전용.env.roi-db.local을읽되os환경변수가우선하며전용파일이루트파일보다우선한다. 비밀필드는SecretStr로repr를가린다. .env.example에는placeholder만넣었다.

## 5. 실제 의존성·파일

신규직접의존성은SQLAlchemy2.0.52/Alembic1.20.0/psycopg3.3.6(binary동일버전)이다. 추가하위의존성은greenlet3.5.6/Mako1.4.3이다. `requirements-db.txt`에고정하고개발requirements가참조하게했다. 기존Dockerfile은requirements-prod.txt만COPY하므로운영requirements에는동일핀을직접기록해누락된파일참조를피했고Dockerfile은수정하지않았다. 기존Python/torch/OpenCV/Agent패키지를업데이트하지않았다. `pip check`: **No broken requirements found**. 스크립트경로가PATH에없다는pip안내는PATH영구변경없이 `python -m alembic`으로처리한다.

| 파일 | 구현책임 |
|---|---|
| backend/db.py | PostgreSQL전용engine·pool·session·SecretStr설정 |
| backend/roi_models.py | preset/version/approval/activebinding 모델 |
| backend/roi_repository.py | DB행잠금·버전/승인/활성전환·safe view |
| backend/roi_schemas.py | 엄격입력·범위·좌표·오류 |
| backend/roi_api.py | 관리인증·영상검증·8개API·모델독립앱factory |
| backend/main.py | router등록/사용한ROI engine종료만추가 |
| alembic.ini / migrations/env.py / script.py.mako / versions/0001_roi_persistence.py | 명시적초기migration |
| compose.roi-db.yaml / scripts/setup_roi_database.py | 로컬전용DB·비밀생성·역할/권한 |
| scripts/run_roi_offline_tests.py | 외부통신·보호파일쓰기·실모델실행차단테스트래퍼 |
| tests/test_roi_schemas.py / tests/test_roi_postgresql.py / tests/roi_restart_probe.py | 단위·실DB·앱/컨테이너재시작검증 |
| requirements-db.txt / requirements.txt / requirements-prod.txt / .env.example | 최소의존성·placeholder설정 |
| docs/roi-postgresql-api.md / 본보고서 / 기술결정문서 / 데이터스키마링크 | 계약·상태인수인계 |

운영기존backend/config.py, inspection.py, storage.py, vision.py, Agent, ImageRegistry, CaptureStore, VideoFileSource의로직은이번에수정하지않았다. ROI모듈만별도import한새프로세스에서torch/vision/inferencer가로드되지않음을테스트했다.

## 6. 데이터 모델과 제약

1. roi_presets: 서버발급ROI-UUID, 적용범위, head_version, 생성시각. preset ID+scope복합unique.
2. roi_preset_versions: (presetID,version)복합PK, 불변좌표, version생성시각. 양수·경계check/trigger.
3. roi_approvals: version참조복합FK, 명시승인시각. version좌표와승인상태를분리한다.
4. roi_active_bindings: video/revision/product/width/height복합PK, 승인version복합FK, preset동일범위FK, binding_revision과수정시각.

version/approval UPDATE·DELETE는DBtrigger로거부한다. preset범위/생성시각은변경할수없고head는1씩증가한다. 새좌표는새Draftversion이고기존승인/활성version을몰래바꾸지않는다. 승인없는active삽입과다른범위binding은FK로차단한다. 같은범위활성행은정확히하나다.

새version은preset행잠금+expected_version, 활성전환은DB의transaction advisory lock+복합PK+expected_active_revision으로직렬화한다. 동시2요청에서한요청성공/다른요청409, active행1개를실제PG로확인했다. flush후강제예외rollback에서도이전active를유지한다. commit실패를주입해201이아닌정제된503/저장행0건을검증했다.

Alembic 초기revision은0001_roi_persistence다. 앱시작시create_all하지않는다. 새테스트스키마upgrade, 데이터있는스키마재upgrade, metadata drift0을확인했다. 이력삭제를수반하는downgrade는명시거부한다. migration접속문자열은config에하드코딩하지않고오류는정제한다.

## 7. API·인가·검증

8개경로는별도 [API계약](roi-postgresql-api.md)에정리했다. /active는동적ID앞에등록한다. 모든조회/변경은local관리Bearer인증을요구하며CaptureStore쿠키를영속owner로사용하지않는다. 토큰상수시간비교·미설정차단·Origin허용목록·loopback/forwarded거부를구현했다. 기존main라우터실제mount와CORS preflight도테스트했다.

기존VideoFileSource의등록entry와파일SHA검증을재사용하고영상frame은읽지않는다. VID-000001/승인SHA/1920×480/30FPS/240프레임등록을대조했다. 승인H.264로실제metadata검증후테스트DB Draft저장도확인했다.

좌표는원본픽셀/좌상단/정수/반개구간이다. bool/float/문자열/extra/음수/0/최소미달/경계초과/크기불일치/revision불일치/미등록video·product를거부한다. 경계접촉은허용한다. 좌표적합이병전체포함/모델성능을의미하지않으며테스트ROI는운영적합ROI가아니다. 실제승인ROI는자동등록하지않았다.

## 8. 실행 결과·실패 이력

| 단계 | 실제결과 |
|---|---|
| 최초신규실행 | 21 PASS/28 ERROR. 기존pytest공용temp샌드박스권한문제 |
| 전용temp첫재시도 | 21 PASS/1 ERROR. parent디렉터리미생성 |
| 격리경로정상후 | 49 PASS |
| commit실패보강중 | 52 PASS/1 FAIL. yield dependency종료시DB예외정제누락재현 |
| dependency종료예외처리수정후 | 54 PASS/0 FAIL/0 SKIP,6.84초 |
| 관련Agent/검사/영상/저장/신규회귀 | 473 PASS/0 FAIL/6 SKIP,13.35초 |
| 전체tests수집·실행 **정확히1회** | **1274 PASS/1 FAIL/51 SKIP/경고2건,26.40초** |
| main관리라우터/CORS보강후최종신규 | **55 PASS/0 FAIL/0 SKIP,7.62초** |
| pip check | PASS |

카운트는서로중복되므로합산하지않는다. 전체회귀 당시신규54개였으며그후main관리라우터통합1개를추가해최종신규55개다. 전체를추가실행하지않았으므로최종55개를포함한새전체수치라고표현하지않는다.

전체실패1건은 `tests/test_day2_integration.py:267`의test_10_all_jsonl_lines_valid_json이다. 해당테스트는선행API검사로채워진공유JSONL이비어있지않음을가정한다. 이번래퍼는실PatchCore로딩을pytest.skip하고외부통신/운영쓰기차단을적용하므로선행실모델검사들이제외돼JSONL이0행이었다. 기존테스트·기대값을약화하거나가짜레코드를심어PASS로바꾸지않았다. DB/API/마이그레이션실패로분류하지않되**실제전체FAIL1은그대로유지**한다.

51 SKIP은기존T03주입fixture부재4개와이번**실모델실행금지정책47개**로구분한다. 기존4개사유는그대로다. 모델제외47개를기존SKIP해결이나실제모델회귀PASS로표시하지않는다. 임포트의timm/anomalib경고2건은기존경고다.

전체재실행은이번허용1회를이미사용했다. 다음승인에서는실추론없는명시적Mock/JSONL준비fixture로기존테스트의선행데이터의존성을분리한후전체회귀추가1회를검토해야한다. 운영코드나기존테스트를임의수정하지않았다.

실제명령:

```text
python -B -m pytest tests/test_roi_schemas.py tests/test_roi_postgresql.py -q --tb=short -p no:cacheprovider --basetemp=data/outputs/roi-db-validation/new-tests-04
python -B scripts/run_roi_offline_tests.py regression-01 <보고서의관련테스트목록> -q --tb=short -rs
python -B scripts/run_roi_offline_tests.py full-01 tests -q --tb=short -rs
python -B scripts/run_roi_offline_tests.py new-tests-final tests/test_roi_schemas.py tests/test_roi_postgresql.py -q --tb=short -rs
python -m pip check
```

실제Python은 `C:/Users/USER/miniconda3/envs/vision-insight/python.exe`다. 관련목록은test_inspections/storage/video_source/capture_store/video_api/agent_service/agent_tools/agent_day5_counterexamples/agent_history_comparison/agent_t06_isolation/agent_error_policy와신규2파일이다.

## 9. 앱·DB 재시작 영속성

신규테스트는실PostgreSQL의격리UUID schema에v1/v2를생성해v2승인/활성후engine을dispose하고**새Python프로세스의FastAPI앱**으로두version과active를조회해PASS했다. 메모리캐시재조회가아니다.

별도tests.roi_restart_probe로실제H.264등록에맞는테스트preset/v1/v2를테스트DB에만만들었다. 연결/앱종료→전용Docker컨테이너restart(볼륨유지)→새프로세스/연결/앱→두version/승인/active확인 **PASS**. 이후이번소유테스트schema만삭제했고비밀없는restart.json을남겼다. 다른DB/볼륨은초기화·삭제하지않았다.

증거는 Git무시경로 `data/outputs/roi-db-validation/`의new-tests.xml, regression-01/results.xml, full-01/results.xml, new-tests-final/results.xml, restart.json이다. 전체JUnit:tests1326/failures1/errors0/skipped51/time26.377초. pytest임시캡처는이번소유전용경로에만있고기존캡처를삭제하지않았다.

## 10. 보호·남은 작업

검증범위의기존216파일을시작/종료SHA256으로비교했다. 이번허용변경은main.py,두requirements,.env.example,기술결정문서,데이터스키마링크의6개이며나머지210개는동일했다. 추가소스/계약파일은18개다. 기존발표·다른에이전트코드·운영JSONL·모델·승인영상보존을확인했다. 이번변경범위 git diff --check exit0 및신규18개no-index 공백오류진단0건이며LF→CRLF안내만있다. 테스트DB의이번UUID schema 잔존0건을확인했다.

실Gemini0회, 실제PatchCore추론/모델로딩0회, 운영검사/Grab/READY/실E2E생성0건. 모델/전처리/34.1442/운영JSONL/이미지Registry/승인영상/기존CaptureStore자료/GT/기존발표·병렬작업을변경하지않았다. 금지평가경로는목록도조회하지않았다. Git add/commit/push/reset0건. Docker Desktop/전용PostgreSQL기동과최소DB패키지추가외Python/시스템변경은없다.

PatchCore문제는UNRESOLVED,ROI검사연결은NOT IMPLEMENTED다. DB설정승인은실제모델적합성인증이아니며B-2의전처리안전성·입력snapshot/TTL·crop/중립image_id·검사provenance·JSONL연결은별도승인이필요하다. PostgreSQL만으로영상/PNG공유저장·다중replica세션이해결되지않는다. CloudRun/CloudSQL/과금설정은없다.

현재새로운ROI관리기능은실DB검증됐지만전체회귀1FAIL이남아**Phase B-1-DB 전체PARTIAL**로보고하고중단한다. 추가전체회귀및B-2구현은사용자승인을기다린다.
