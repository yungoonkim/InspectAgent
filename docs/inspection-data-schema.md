# Vision 검사 데이터 스키마 및 식별자 명세 (`docs/inspection-data-schema.md`)

> Day5 Step3 B-1-DB: ROI preset/version/명시 승인/활성 binding은 PostgreSQL에서 관리합니다.
> [ROI 관리 API 계약](roi-postgresql-api.md)을 참조하세요. 캡처 세션과 관리 Bearer는 별개이며,
> Draft 저장은 AUTO 승인·활성화가 아닙니다. 기존 검사/Agent JSONL 스키마는 변경하지 않았습니다.
> ROI→PatchCore 연결은 미구현이고 중복 정규화 문제는 미해결입니다.

> Day5 Step 2 Phase B: 영상/캡처는 기존 검사와 별도 식별자를 사용합니다.
> `video_id + source_revision + frame_index`로 PNG를 획득하고 서버 발급 `capture_id`로 조회합니다.
> Grab은 `image_id`나 `inspection_id`를 발급하지 않으며 검사 JSONL을 기록하지 않습니다.
> 요청·응답·세션·TTL·오류 및 AUTO/MANUAL 인수 계약은
> [영상·Grab 구현 문서](day5-step2-phaseb-video-grab-implementation.md)를 참조하세요.

> Day 4 Step 3 추가 API: `POST /analyze/{inspection_id}`. AnalysisResponse는 DiagnosisResult를
> 재사용하고 analysis_id, inspection_result, final_result, final_reason_code, UTC timestamp를 추가합니다.
> 판정 필드는 저장 기록에서 가져오며 구형 기록의 누락 필드는 null입니다.
> 오류는 `{"detail":{"analysis_status":"FAILED","error_code":"..."}}` 형식입니다.
> 요청·응답 예시, HTTP 상태 및 생명주기는 [Step 3 API 문서](day4-step3-api.md)를 참조하세요.

> **프로젝트:** VisionInsight — MVTec AD Bottle 기반 Vision 검사 이상 진단 AI Agent  
> **문서 버전:** 1.0.0 (Day 1 완료 기준)  
> **상태:** 활성 (Active)

---

## 1. 핵심 식별자 및 분리 원칙

| 식별자 | 형식 예시 | 역할 및 성격 |
|---|---|---|
| **`product_id`** | `ABCD1541` | 대상 제품(병)을 식별하는 고유 번호. 동일 제품 재검사 시에도 동일하게 유지됨. |
| **`inspection_id`** | `INSP-000001` | 개별 검사 실행 단위의 고유 식별자. 재검사 시마다 항상 새로 발급되며 충돌 방지됨. |
| **`image_id`** | `IMG-BOTTLE-0001` | **정답 누출 방지용 중립 이미지 식별자**. 원본 파일 경로의 정답 레이블을 은닉함. |

> [!IMPORTANT]
> **정답 정보 격리 원칙 (`AGENTS.md` 준수)**
> 원본 경로(`broken_large`, `contamination` 등)에 포함된 정답 라벨은 서버 내부 레지스트리에서만 관리하며, **Agent 도구 및 외부 API에는 오직 `IMG-BOTTLE-XXXX` 형식의 중립 식별자만 전달**합니다. `ground_truth` 마스크는 운영 코드에서 일절 읽지 않습니다.

---

## 2. 제품 판정(Result)과 영상 품질(Quality)의 엄격한 분리

| 구분 | 관리 필드 | 허용 값 | 설명 |
|---|---|---|---|
| **제품 판정** | `result` | `OK`, `NG`, `UNKNOWN` | Vision 검사 모듈이 제품의 외관 결함(파손, 오염 등)을 판정한 결과. **Day 1 단계에서는 실제 분류기가 없으므로 `UNKNOWN` 고정.** |
| **영상 품질** | `quality_status` | `NORMAL`, `WARNING_LOW_BRIGHTNESS`, `WARNING_HIGH_BRIGHTNESS` | 촬영 환경의 조명 및 획득 영상 품질 상태. **제품 불량(NG)과 절대 혼동하지 않음.** |

> [!CAUTION]
> 조명 환경 저하(밝기 감소) 경고가 발생하더라도 **"조명 장치 고장"으로 단정하지 않으며**, 관측된 사실(밝기 지표)과 진단 가설을 분리하여 보고합니다.

---

## 3. 시간 필드 규격

- **형식:** ISO 8601 표준 포맷
- **시간대:** 한국 표준시 KST (`+09:00`) 명시
- **예시:** `2026-10-13T18:35:00.123456+09:00`

---

## 4. API 명세: `POST /inspections`

### 4.1 요청 (Request)
- **Method & Path:** `POST /inspections`
- **Content-Type:** `application/json`

```json
{
  "product_id": "ABCD1541",
  "image_id": "IMG-BOTTLE-0001"
}
```

- `product_id` (string, 필수): 제품 식별자
- `image_id` (string, 필수): 서버가 허용한 중립 이미지 ID. 임의의 파일 경로(Path Traversal)는 거부됨.

### 4.2 응답 (Response - HTTP 201 Created)

```json
{
  "inspection_id": "INSP-000001",
  "product_id": "ABCD1541",
  "image_id": "IMG-BOTTLE-0001",
  "status": "COMPLETED",
  "result": "UNKNOWN",
  "timestamp": "2026-10-13T18:35:00.123456+09:00",
  "image_metadata": {
    "filename": "000.png",
    "width": 900,
    "height": 900,
    "channels": 3
  }
}
```

### 4.3 오류 응답
- **HTTP 400 Bad Request:** 허용되지 않은 `image_id` 요청 시 (`Invalid or disallowed image_id`)
- **HTTP 404 Not Found:** 매핑된 이미지 파일이 디스크에 존재하지 않는 경우
- **HTTP 422 Unprocessable Entity:** OpenCV 디코딩 실패 또는 이미지 손상

---

## 5. 저장 경로 및 보존 규칙

```text
InspectAgent/
├── dataset/bottle/               # 원본 데이터셋 (읽기 전용, 덮어쓰기/수정 절대 금지)
│   ├── train/good/
│   └── test/{good, broken_large, broken_small, contamination}/
├── data/
│   ├── outputs/                  # 검사 산출물 저장 디렉토리 (.gitignore)
│   │   ├── injected/             # 오류 주입 테스트 이미지
│   │   └── {product_id}_{inspection_id}_{result}.png
│   ├── logs/                     # 실행 및 이벤트 로그 (.gitignore)
│   ├── inspections.jsonl         # (Day 2 예정) 검사 실행 레코드
│   └── inspection_logs.jsonl     # (Day 2 예정) 이벤트 로그 레코드
```

## 6. Day 4 Step 1: Agent 조회 도구 계약

`backend.agent.InspectionTools(storage: InspectionStorageBase)`에 저장소를 주입합니다.
도구는 검사 실행, 이미지 로드, 추론, 파일 쓰기를 수행하지 않습니다.
Day 4 Step 2의 진단 초안·최종 결과·Trace·근거 검증 계약은
[day4-step2-agent.md](day4-step2-agent.md)에 정의하며 구현 모델은 `backend/agent/schemas.py`입니다.
아래 계약은 Agent 조회 도구에 적용하며 위의 Day 1 API 예시를 변경하지 않습니다.

| 메서드 | 저장소 호출 | 반환 data |
|---|---|---|
| `get_inspection_result(inspection_id: str)` | `get_inspection(inspection_id)` | 허용된 검사 레코드 객체 |
| `get_execution_logs(inspection_id: str)` | `get_inspection`, `get_logs` | 허용된 이벤트 객체 목록 |
| `analyze_image_quality(inspection_id: str)` | `get_inspection` | 저장된 품질 상태·밝기·크기·기준치 기록 여부 |
| `get_inspection_history(product_id: str, limit: int = 5)` | `list_inspections(limit=1000, product_id=product_id)` | 동일 제품의 허용된 검사 레코드 목록 |

모든 반환값은 JSON 직렬화 가능한 다음 구조입니다.

```json
{"ok": false, "error": "NOT_FOUND", "data": null, "metadata": {}}
```

- `ok`: 도구 조회의 성공 여부이며 검사 프로그램의 `status`와 독립적입니다.
- `error`: 성공 시 null. `INVALID_ARGUMENT`, `NOT_FOUND`, `STORAGE_ERROR`, `DATA_UNAVAILABLE`만 반환하며 예외 메시지는 제외합니다.
- `DATA_UNAVAILABLE`: 검사 존재 확인 후 로그가 없거나, 제품 이력이 없거나, 조회 레코드의 검사 ID가 일치하지 않는 경우입니다. 로그 부재는 `data=[]`, `metadata.inspection_exists=true`로 표시합니다.
- 검사 ID는 `INSP-`와 6~12자리 숫자, 제품 ID는 ASCII 영숫자로 시작하는 영숫자·`_`·`-` 1~64자로 제한합니다. 경로, 공백, 제어 문자, 알려진 평가 클래스 문자열은 거부합니다.
- `limit`는 bool을 제외한 정수 1~20이며 기본값은 5입니다.

검사 반환 필드는 `inspection_id`, `product_id`, 중립 `image_id`, `timestamp`,
`timestamp_status`, `status`, `result`, `image_quality_status`, `defect_detection_status`,
`final_result`, `final_reason_code`, `anomaly_score`, `decision_threshold`,
`inference_time_ms`, `decision_confidence`, `model_version`, `metrics`입니다.
`metrics`는 `mean`, `std`, `min`, `max`, `width`, `height`, `channels`만 포함합니다.
`decision_confidence`와 `model_version`은 저장된 metrics에서 허용된 열거값만 추출합니다.
현재 허용 모델명은 `PatchCore`, `PatchCore-ResNet18-180Train`, `patchcore_bottle_v1_180`입니다.
새 모델명은 명시적으로 허용 목록에 등록해야 합니다.

로그는 시각·시각 유효성·수준·단계·이벤트 코드와 허용 지표만 반환합니다.
자유 문자열인 `message`, `source`, 파일명, 에러 문자열, 원본 metrics는 반환하지 않습니다.
로그 metrics의 허용 범위는 밝기·크기·모델 점수·임계값·추론 시간과 판정 관련 열거값입니다.
임의 문자열, bool형 수치, 음수, NaN/Infinity는 null로 처리합니다.
밝기 통계는 0~255, 크기는 양의 정수 100000 이하로 제한합니다.
누락·미허용 필드는 null이며 기존 판정은 다시 계산하지 않습니다.

타임스탬프는 시간대가 있는 ISO 8601 값만 인정하고 UTC로 정규화합니다.
로그는 유효 시각 오름차순, 이력은 내림차순으로 안정 정렬합니다.
동일 시각의 순서는 저장소 반환 순서를 유지합니다.
잘못된 시각·시간대 없는 시각·누락 시각은 null과 `INVALID_OR_MISSING`으로 표시하고
유효 시각 뒤에 저장소 반환 순서대로 배치합니다. 실제 발생 순서를 추정하지 않습니다.
JSONL 조회부는 누락 시각을 빈 문자열로 읽어 Pydantic의 현재 시각 기본값 생성을 방지합니다.
쓰기 동작이나 기존 파일은 변경하지 않습니다.

이력은 저장소가 반환한 최대 1000개 후보 안에서 정렬하고 그 뒤 limit를 적용합니다.
`ordering_scope=RETURNED_STORAGE_CANDIDATES`, `global_latest_guaranteed=false`이며,
`scan_limit_reached`는 조회 상한 도달 여부입니다. 상한 밖에 더 최신 시각이 있을 수 있습니다.
`candidate_count`, `invalid_timestamp_count`도 반환합니다.
현재 저장소의 손상 행 건너뛰기 정책 때문에 원본 전체의 완전성은 보장할 수 없습니다.

영상 품질 도구는 저장된 `metrics.applied_thresholds.low_threshold/high_threshold`가
유효한 숫자 쌍(0 ≤ low ≤ high ≤ 255)이면 해당 두 값만 반환하고 `RECORDED`로 표시합니다.
없으면 `brightness_thresholds=null`, `threshold_status=NOT_RECORDED`입니다.
현재 설정을 과거 검사 기준치로 사용하지 않습니다. `physical_cause_confirmed=false`이며
합성 주입 정보나 제품의 실제 평가 정답은 제공하지 않습니다.

### 6.1 실제 도구 실행 예시 (가짜 저장소)

다음은 `tests/test_agent_tools.py`의 `make_record()`와 `make_log()`를 반환하는
가짜 저장소를 주입하여 실행한 응답입니다. 운영 검사 실행이나 실측 로그를 뜻하지 않습니다.

`get_inspection_result("INSP-000001")`:

```json
{
  "ok": true, "error": null,
  "data": {
    "inspection_id": "INSP-000001", "product_id": "PROD-001", "image_id": "IMG-BOTTLE-0001",
    "timestamp": "2026-10-15T01:00:00+00:00", "timestamp_status": "VALID",
    "status": "COMPLETED", "result": "OK", "image_quality_status": "NORMAL",
    "defect_detection_status": "COMPLETED", "final_result": "OK", "final_reason_code": "ALL_CHECKS_PASSED",
    "anomaly_score": 32.2679, "decision_threshold": 34.1442, "inference_time_ms": null,
    "decision_confidence": "HIGH", "model_version": "PatchCore",
    "metrics": {"mean": 138.37, "std": 92.08, "min": 0, "max": 255, "width": 900, "height": 900, "channels": 3}
  },
  "metadata": {}
}
```

`get_execution_logs("INSP-000001")`:

```json
{
  "ok": true, "error": null,
  "data": [{
    "timestamp": "2026-10-15T01:00:00+00:00", "timestamp_status": "VALID",
    "level": "INFO", "stage": "load", "event_code": "IMAGE_LOADED",
    "metrics": {
      "anomaly_score": null, "decision_threshold": null, "inference_time_ms": null,
      "max": null, "mean": null, "min": null, "std": null,
      "channels": null, "height": null, "width": 900,
      "decision_confidence": null, "model_version": null, "defect_detection_status": null,
      "image_quality_status": null, "final_result": null, "final_reason_code": null, "result": null
    }
  }],
  "metadata": {
    "inspection_exists": true, "ordering": "TIMESTAMP_ASC_INVALID_LAST_STABLE",
    "invalid_timestamp_count": 0, "messages_included": false
  }
}
```

`analyze_image_quality("INSP-000001")`:

```json
{
  "ok": true, "error": null,
  "data": {
    "inspection_id": "INSP-000001", "image_quality_status": "NORMAL",
    "metrics": {"mean": 138.37, "std": 92.08, "min": 0, "max": 255, "width": 900, "height": 900, "channels": 3},
    "brightness_thresholds": null, "threshold_status": "NOT_RECORDED"
  },
  "metadata": {"measurement_source": "STORED_RECORD", "physical_cause_confirmed": false}
}
```

`get_inspection_history("PROD-001")`:

```json
{
  "ok": true, "error": null,
  "data": [{
    "inspection_id": "INSP-000001", "product_id": "PROD-001", "image_id": "IMG-BOTTLE-0001",
    "timestamp": "2026-10-15T01:00:00+00:00", "timestamp_status": "VALID",
    "status": "COMPLETED", "result": "OK", "image_quality_status": "NORMAL",
    "defect_detection_status": "COMPLETED", "final_result": "OK", "final_reason_code": "ALL_CHECKS_PASSED",
    "anomaly_score": 32.2679, "decision_threshold": 34.1442, "inference_time_ms": null,
    "decision_confidence": "HIGH", "model_version": "PatchCore",
    "metrics": {"mean": 138.37, "std": 92.08, "min": 0, "max": 255, "width": 900, "height": 900, "channels": 3}
  }],
  "metadata": {
    "ordering": "TIMESTAMP_DESC_INVALID_LAST_STABLE", "scan_limit": 1000,
    "candidate_count": 1, "scan_limit_reached": false,
    "ordering_scope": "RETURNED_STORAGE_CANDIDATES", "global_latest_guaranteed": false,
    "invalid_timestamp_count": 0
  }
}
```
