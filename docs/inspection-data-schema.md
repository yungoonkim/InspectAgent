# Vision 검사 데이터 스키마 및 식별자 명세 (`docs/inspection-data-schema.md`)

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
