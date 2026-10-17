# PostgreSQL ROI 관리 API — 로컬 단일 운영자 MVP

## 범위·접근

저장·버전·승인·활성화 관리만 구현한다. Crop/추론/자동 제어 API가 아니다. 기존 POST /inspections 및 CaptureStore는 유지한다. PatchCore 중복 정규화 문제는 **UNRESOLVED**다.

모든 ROI 경로는 환경변수 VISIONINSIGHT_ROI_ADMIN_TOKEN의 **Bearer 토큰**을 요구한다. 토큰은32~128자리 URL-safe 난수이며 기본 비밀값이 없다. 미설정503, 불일치401이다. ENVIRONMENT와 VISIONINSIGHT_ROI_ENVIRONMENT 모두local이어야 한다. peer와Host는loopback이어야 하며 Forwarded/X-Forwarded-For가 있으면403으로 거부한다. 공용 인터넷/리버스 프록시/Cloud Run 인증으로 사용하지 않는다.

Origin이 있으면 VISIONINSIGHT_ROI_ORIGINS와 일치해야 한다. 주 앱에서는 기존 명시적 CORS가 Authorization/Content-Type preflight를 처리한다. 토큰은 쿠키에 없고 브라우저가 자동 첨부하지 않으므로 CaptureStore 쿠키·CSRF와 독립적이다. 관리 비밀을 React bundle에 넣지 않는다. 로컬CLI는 Origin 없이도 Bearer로 접근할 수 있다. 사용자 계정/RBAC·토큰 rotation·클라우드 인증은 미구현이다.

## 엔드포인트

DB 전용 실행은 기존 모델을 import/load하지 않는 별도 factory를 사용한다.

```text
python -m uvicorn backend.roi_api:create_roi_app --factory --host 127.0.0.1 --port 8001
```

기존 main의 모델 startup 동작은 바꾸지 않았다. 이번 main router 검증은 ASGI 요청으로 했으며 기존 main 서버를 실제로 기동해 PatchCore를 로딩한 검증이 아니다. 위 전용 앱은 관리 CLI용이며 React UI/클라우드 인증 서버가 아니다.

| Method | 경로 | 응답 |
|---|---|---|
| GET | /roi-presets?limit=50 | 최신version 목록, limit1~100 |
| POST | /roi-presets | Draft 생성201 |
| GET | /roi-presets/active | 정확한 적용 범위의 활성version200, 없으면404 |
| GET | /roi-presets/{roi_config_id} | 최신version200 |
| GET | /roi-presets/{roi_config_id}/versions?offset=0&limit=50 | total_versions와 과거version 목록 |
| POST | /roi-presets/{roi_config_id}/versions | 새 Draft version201 |
| POST | /roi-presets/{roi_config_id}/approve | 명시 승인200, 동일version 재승인은 멱등 |
| POST | /roi-presets/{roi_config_id}/activate | 승인version 활성화200 |

정적 /active를 동적ID보다 먼저 등록한다. 새 검사ID/Grab/PNG는 만들지 않는다.

## 생성 요청 예시 — 형식 예시, 실제 승인 ROI 아님

```json
{
  "video_id": "VID-000001",
  "source_revision": "f1c5a12ee25672bfb8241311ecd16f7fefb7e549cb43a44a81bb4858ea9f9a2d",
  "source_width": 1920,
  "source_height": 480,
  "product_id": "<operator-registered-neutral-product-id>",
  "roi": {"x": 750, "y": 110, "width": 280, "height": 310}
}
```

서버는 ROI-UUID hex32를 발급한다. version/head_version=1, approved_for_auto=false, active=false, binding_revision=0이다. 원본 좌표계는 ORIGINAL_IMAGE_PIXELS_TOP_LEFT다. 응답은 적용 범위·roi·version 생성시각·승인시각을 포함하며 DB비밀·파일경로·개인세션은 제외한다. created_at은 해당 불변version 생성시각이고 승인시각은approved_at으로 분리한다.

타입은StrictInt/StrictStr, extra=forbid다. bool/float/숫자문자열을 정수로 강제 변환하지 않는다. x/y≥0, width/height>0, 원본 경계 이내, 기본최소32×32를 검사한다. 최소값은 VISIONINSIGHT_ROI_MIN_SIZE로1~256 설정 가능하며 산업/모델 적합성 기준이 아니다. 반개구간 [y:y+height,x:x+width] 계약만 정의하며 실제crop은 수행하지 않는다.

영상은 기존 VideoFileSource.entry/verified_path로 허용ID·경로·실제SHA를 검증한다. decoder/프레임read는 사용하지 않는다. revision·원본해상도는 등록값과 같아야 한다. 기존 코드에는 ProductRegistry가 없고 기존 검사API는 product_id 문자열을 받는다. 신규 ROI만 **VISIONINSIGHT_ROI_PRODUCT_IDS의 명시적 운영자 등록 목록**으로 제한한다. 기본 빈 목록은 모든 생성/승인/활성화를 거부하며 기존 검사API의 제품 계약은 변경하지 않는다. product_id는 이미지·ROI ID가 아니다.

## 버전·승인·활성화

```json
{"expected_version": 1, "roi": {"x": 800, "y": 100, "width": 300, "height": 300}}
```

새version은 항상미승인이다. 기존 승인·좌표는 그대로 보존한다. 새Draft를 만들었다고 이전 활성version이 자동 교체되지는 않는다. preset의 적용 범위는 불변이며 다른영상/제품/revision은 새preset으로 만든다.

```json
{"version": 2}
```

위approve는 **운영상 설정 사용 승인**이지 모델성능·병전체포함 인증이 아니다. 관리자 판단으로만 실행한다. 초기 운영DB에 개발자가 임의로 승인한 ROI는 없다.

```json
{"version": 2, "expected_active_revision": 0}
```

첫 활성화는expected_active_revision=0이다. 이후 조회된binding_revision을 제시해야 하며 오래된 값은409다. 활성범위는 video_id+source_revision+product_id+source_width+source_height다. 같은 범위의 다른preset 활성화도 같은revision을 공유한다. 미승인version은409, 조회는 정확히 하나 또는404이며 첫 번째 임의 선택을 하지 않는다.

/active는 위 적용 범위5개를 query로 받는다. 현재 영상파일/revision/해상도/제품 등록도 다시 확인하므로 영상 교체 후 이전 설정을 자동 적용하지 않는다. 과거preset/versions 조회는 역사기록 열람을 허용한다.

## 오류·트랜잭션

형식은 기존스타일 `{"detail":{"error_code":"..."}}`다.422는ROI_INPUT_INVALID/ROI_BOUNDS_INVALID/ROI_SOURCE_SIZE_MISMATCH/ROI_PRODUCT_NOT_REGISTERED,409는ROI_VERSION_CONFLICT/ROI_ACTIVE_CONFLICT/ROI_APPROVAL_REQUIRED/ROI_SOURCE_REVISION_MISMATCH/ROI_DATABASE_CONFLICT,503은ROI_DATABASE_UNAVAILABLE 등이다. 영상 오류는 기존VideoError 코드/상태를 재사용한다.

요청별SQLAlchemy session/transaction을 사용하고 **commit 성공 이후** HTTP 성공을 반환한다. commit실패는rollback·정제된503이며 내부SQL/driver예외를 반환하지 않는다. 입력오류도 원본body를 echo하지 않는다.

새버전은preset 행잠금+expected_version+복합PK로 보호한다. 활성화는 적용범위SHA256의64bit PostgreSQL transaction advisory lock+복합PK+낙관적revision을 사용한다. 메모리락만으로 유일성을 보장하지 않는다. 승인FK와 preset scope 복합FK가 미승인·오적용을 차단한다. version·approval의UPDATE/DELETE 및 preset범위 변경은DB trigger로 거부한다.

승인취소·비활성화·삭제·다중관리자 계정 API는 이번 범위에 포함하지 않았다. 저장/수정/승인/활성은 서로 다른 행동이다.

## B-2 인수

향후 내부 검사서비스가 활성version을 읽을 때 적용범위·승인을 검증하고 roi_config_id/version/좌표/원본 크기를 불변 snapshot으로 가져간다. capture_id 소유권/TTL 검증은 별도로 유지한다. 같은검사에 DB최신version을 중간에 재조회해 교체하지 않는다. 기존 검사JSONL에 provenance를 연결하는 변경과 실제Crop→PatchCore는 미구현이다.
