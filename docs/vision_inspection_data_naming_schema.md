# Vision 검사 데이터 식별자·파일명·로그 스키마 설계

> 프로젝트: MVTec AD Bottle 기반 Vision 검사 이상 진단 AI Agent  
> 문서 목적: 검사 기록, 이미지, 로그를 일관되게 연결하기 위한 초기 데이터 명세  
> 상태: 초안 (MVP 개발 기준, 변경 가능)

## 1. 핵심 결정 사항

- **제품번호(Product ID)**: 제품을 식별하는 번호. 예: `ABCD1541`
- **검사 ID(Inspection ID)**: 개별 검사 실행을 고유하게 식별하는 값. 예: `INSP-000001`
- **검사 결과(Result)**: 검사 프로그램이 판정한 `OK`, `NG` 또는 검사 실패를 뜻하는 `ERROR`.
- **권장 이미지 파일명**: `{product_id}_{inspection_id}_{result}.png`
- **로그 연결 키**: `inspection_id`
- **데이터 저장**: MVP는 `inspections.jsonl`, `inspection_logs.jsonl` 사용. 운영 환경에서는 DB 전환 가능.

**중요:** 제품번호와 검사 ID는 다르다. 동일한 제품을 재검사해도 검사 ID는 새로 발급한다.

## 2. 파일명 예시와 재검사 처리

```text
ABCD1541_INSP-000001_NG.png
ABCD1541_INSP-000002_OK.png
ABCD1542_INSP-000003_NG.png
```

위 두 개의 `ABCD1541` 이미지는 같은 제품에 대한 서로 다른 검사 실행이다. `inspection_id`가 다르므로 파일이 덮어써지지 않는다.

### 파일명 설계 규칙

1. `product_id`와 `inspection_id`에는 파일명 구분자인 `_`를 사용하지 않는 것을 기본 규칙으로 한다.
2. 이미지 확장자는 원본 형식에 맞춰 저장한다. MVTec AD 원본이 PNG라면 **PNG 유지**를 권장한다. 불필요한 JPEG 재압축은 피한다.
3. 이미지 파일명의 `OK` / `NG`는 **실제 검사 모듈의 예측 결과**를 반영한다. 원본 데이터셋의 정답을 예측으로 위장하지 않는다.
4. 검사 실행 자체가 실패해 판정할 수 없으면 `ERROR`를 사용한다. `ERROR`를 제품 불량 `NG`와 구분한다.
5. 파일명은 사람의 확인용이며, 프로그램은 `inspection_id`와 `image_path` 필드로 데이터를 연결한다.
6. 검사 결과를 나중에 정정할 가능성이 있다면 파일명 변경에 의존하지 말고 **JSONL의 검사 결과 필드**를 기준으로 삼는다. 원본 파일 경로는 별도로 유지한다.

## 3. 권장 디렉터리 구조

```text
project/
├── dataset/
│   └── bottle/                    # MVTec AD 원본 데이터, 수정하지 않음
│       ├── train/
│       ├── test/
│       └── ground_truth/
├── data/
│   ├── images/                    # 검사 시 저장한 이미지 사본
│   │   ├── ABCD1541_INSP-000001_NG.png
│   │   └── ABCD1541_INSP-000002_OK.png
│   ├── inspections.jsonl         # 검사 실행 단위 기록
│   └── inspection_logs.jsonl     # 실행 중 발생한 이벤트 기록
├── evaluation/
│   ├── ground_truth_mapping.json # 정답 라벨/마스크 연결 정보, 추론 시 사용 금지
│   └── injection_answers.json    # 오류 주입 정답, Agent에 전달하지 않음
├── backend/
└── frontend/
```

`dataset/`의 원본 파일은 보존한다. MVTec AD의 원본 라벨·마스크와 검사 프로그램의 예측값을 명확히 구분한다.

## 4. inspections.jsonl: 검사 기록 형식

**JSONL(JSON Lines)**은 JSON 객체를 한 줄에 하나씩 기록하는 텍스트 파일이다. 검사 실행 하나당 레코드 한 줄을 추가한다.

### 필드 정의

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `inspection_id` | string | O | 고유 검사 실행 ID |
| `product_id` | string | O | 제품 식별번호(프로젝트에서 부여한 가상 번호 가능) |
| `product_type` | string | O | 예: `bottle` |
| `timestamp` | string | O | ISO 8601 형식의 검사 시각, 시간대 포함 |
| `result` | string | O | `OK`, `NG`, `ERROR` 중 하나 |
| `image_path` | string | O | 검사 이미지의 상대 경로 |
| `source_image_path` | string | O | MVTec 원본 이미지 경로 |
| `anomaly_score` | number/null | 선택 | Vision 모듈이 계산한 이상 점수, 미계산 시 `null` |
| `processing_time_ms` | number/null | 선택 | 실제 실행 시간, 미측정 시 `null` |

### 예시 (`inspections.jsonl`)

```jsonl
{"inspection_id":"INSP-000001","product_id":"ABCD1541","product_type":"bottle","timestamp":"2026-10-13T10:00:00+09:00","result":"NG","image_path":"data/images/ABCD1541_INSP-000001_NG.png","source_image_path":"dataset/bottle/test/broken_large/000.png","anomaly_score":0.87,"processing_time_ms":140}
{"inspection_id":"INSP-000002","product_id":"ABCD1541","product_type":"bottle","timestamp":"2026-10-13T10:05:00+09:00","result":"OK","image_path":"data/images/ABCD1541_INSP-000002_OK.png","source_image_path":"dataset/bottle/train/good/000.png","anomaly_score":0.12,"processing_time_ms":132}
```

> 위 점수·처리 시간·경로는 **형식 설명용 예시**다. 실제 구현에서는 Vision 모듈과 실행 환경에서 측정한 값을 기록한다.

## 5. inspection_logs.jsonl: 이벤트 로그 형식

검사 실행 중 발생한 이벤트는 한 줄에 하나씩 기록한다. 하나의 검사 ID에 여러 로그가 연결된다.

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `inspection_id` | string | O | 검사 기록을 연결하는 키 |
| `timestamp` | string | O | ISO 8601, 시간대 포함 |
| `level` | string | O | `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `event` | string | O | 기계가 읽기 쉬운 이벤트 코드 |
| `message` | string | 선택 | 사람이 읽는 상세 메시지 |
| `metrics` | object | 선택 | 밝기 등 측정값 |
| `source` | string | 선택 | `vision`, `api`, `test_injector` 등 |

### 예시 (`inspection_logs.jsonl`)

```jsonl
{"inspection_id":"INSP-000001","timestamp":"2026-10-13T10:00:00+09:00","level":"INFO","event":"INSPECTION_STARTED","message":"Inspection started","source":"vision"}
{"inspection_id":"INSP-000001","timestamp":"2026-10-13T10:00:00.120+09:00","level":"INFO","event":"IMAGE_LOADED","message":"Bottle image loaded","source":"vision"}
{"inspection_id":"INSP-000001","timestamp":"2026-10-13T10:00:00.220+09:00","level":"WARN","event":"BRIGHTNESS_LOW","message":"Mean brightness below reference","metrics":{"mean_brightness":89.5,"reference_mean":147.2},"source":"vision"}
{"inspection_id":"INSP-000001","timestamp":"2026-10-13T10:00:00.350+09:00","level":"INFO","event":"INSPECTION_COMPLETED","message":"Inspection result: NG","source":"vision"}
```

**주의:** 이미지 밝기가 낮다는 측정 사실만으로 실제 조명 장치가 고장 났다고 단정할 수 없다.

## 6. 검사 ID 생성 규칙

- 기본 형식: `INSP-000001`, `INSP-000002`, …
- 로컬 단일 프로세스 MVP에서는 파일 또는 DB의 마지막 번호를 기반으로 발급할 수 있다.
- 병렬 처리나 여러 서버로 확장하면 충돌 방지를 위해 UUID/ULID 또는 DB 고유키 방식으로 변경한다.
- 같은 제품의 재검사는 `product_id`를 유지하고 **새로운 `inspection_id`**를 발급한다.
- 최초 검사 시각과 이벤트 시각은 실제 프로그램이 생성하며, 시간대(`+09:00` 등)를 명시한다.

## 7. Agent 조회 도구: 첫 3개

### 7.1 `get_inspection_result(inspection_id: str)`

**입력:** `inspection_id`  
**반환:** 검사 ID, 제품번호, 판정, 이미지 경로, 이상 점수, 검사 시각

```json
{"inspection_id":"INSP-000001","product_id":"ABCD1541","result":"NG","image_path":"data/images/ABCD1541_INSP-000001_NG.png","anomaly_score":0.87,"timestamp":"2026-10-13T10:00:00+09:00"}
```

### 7.2 `get_inspection_logs(inspection_id: str)`

**입력:** `inspection_id`  
**반환:** 해당 검사의 로그 목록(시간순 정렬)

```json
{"inspection_id":"INSP-000001","logs":[{"timestamp":"2026-10-13T10:00:00.220+09:00","level":"WARN","event":"BRIGHTNESS_LOW","message":"Mean brightness below reference"}]}
```

### 7.3 `get_inspection_history(product_id: str, limit: int = 10)`

**입력:** `product_id`, 조회 개수 `limit`  
**반환:** 해당 제품의 최근 검사 이력(검사 ID, 시각, 판정)

```json
{"product_id":"ABCD1541","inspections":[{"inspection_id":"INSP-000002","result":"OK"},{"inspection_id":"INSP-000001","result":"NG"}]}
```

### 사용 흐름

1. 사용자: “`ABCD1541` 제품에서 발생한 NG를 분석해 줘.”
2. Agent → `get_inspection_history("ABCD1541")`: 여러 검사 실행 확인.
3. Agent → `get_inspection_result("INSP-000001")`: NG 검사 상세 확인.
4. Agent → `get_inspection_logs("INSP-000001")`: 같은 검사에 속한 이벤트 조회.
5. Agent: 관측 결과와 로그를 근거로 가능한 검사 이상 및 추가 점검 사항 보고. 근거가 부족하면 원인 불명으로 명시.

**설계상의 주의:** `get_inspection_history`는 동일 `product_id`에 대한 이력만 반환한다. 같은 설비에서 발생한 전체 추세 분석은 이후 별도 도구로 확장한다.

## 8. MVTec AD와 평가 데이터의 구분

- MVTec AD 이미지의 파일명·경로·불량 마스크는 원본 데이터의 일부이다.
- 프로젝트에서 부여한 `product_id`는 **실제 생산 제품의 시리얼 번호가 아닌 가상 식별자**이다.
- 이미지의 실제 정답 라벨과 검사 모듈의 **예측 결과**는 별도 필드/파일로 관리한다.
- 오류 주입 방식(예: 밝기 40% 감소, 이미지 위치 이동)은 평가용 별도 파일에서 관리하며 Agent 조회 도구의 결과에 섞지 않는다.
- 테스트에서 `NG` 이미지와 `WARN` 로그가 동시에 존재해도 실제 설비 고장과 제품 불량의 인과관계가 증명된 것은 아니다.

## 9. 구현 및 검증 체크리스트

- [ ] `product_id`와 `inspection_id`를 분리하는 규칙을 확정했다.
- [ ] 재검사 시 새 `inspection_id`가 생성되고 이미지 파일이 덮어써지지 않는다.
- [ ] 이미지 파일명 규칙과 경로 규칙을 코드에서 동일하게 적용한다.
- [ ] `inspections.jsonl`에 검사 실행당 정확히 하나의 검사 레코드를 기록한다.
- [ ] `inspection_logs.jsonl`에 검사 ID별 이벤트를 기록한다.
- [ ] 이미지·검사 기록·로그를 `inspection_id`로 연결할 수 있다.
- [ ] 세 가지 Agent 도구가 명세대로 JSON을 반환한다.
- [ ] 원본 MVTec 이미지와 정답 마스크를 보존하고 추론에 정답이 유출되지 않는다.
- [ ] 실제 실행 기록, 합성 이벤트, 평가 정답을 구분해 표시한다.
- [ ] 경고 로그만으로 실제 고장 원인을 단정하지 않는다.

## 10. GitHub · MCP 연동을 위한 문서 관리 권장 사항

- 이 파일은 저장소의 `docs/inspection-data-schema.md`에 보관한다.
- 프로젝트 개요는 `README.md`, 전체 개발 계획은 `docs/project-plan.md`, 도구 호출 명세는 `docs/agent-tools.md`로 분리해도 좋다.
- 파일 경로와 함수명, JSON 필드명을 구체적으로 기록하면 IDE의 AI 코딩 도구나 MCP를 통해 접근 가능한 파일 도구가 명세를 참고해 구현하기 수월하다.
- **Markdown 파일을 저장하는 것만으로 MCP가 자동 연결되는 것은 아니다.** 향후 사용할 MCP 서버 또는 도구가 해당 저장소/파일에 접근할 권한이 있어야 한다.
- 설계가 바뀌면 문서와 구현을 함께 갱신하고 Git 커밋으로 변경 이력을 관리한다.

---

**한 줄 요약:** 사람에게는 `제품번호_검사ID_판정.png`라는 읽기 쉬운 파일명을 제공하고, 시스템과 Agent는 `inspection_id`를 기준으로 검사 이미지·결과·실행 로그를 연결한다.
