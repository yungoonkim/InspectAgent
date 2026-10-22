# A-3 이미지 품질 Shadow Metrics 설계·격리 검증

작성일: 2026-10-21. **설계 및 합성 입력 사전 검증 완료 / 운영 계측 연결 미구현·승인 대기.**

**안전 보류:** 시작 git status에는 없던 `backend/config.py` 변경(49추가/11삭제)이 종료 점검에서 발견됐다. 본 작업은 이 파일에 패치를 적용하지 않았다. 변경 주체·의도는 UNKNOWN이며 되돌리거나 덮어쓰지 않았다. 아래 해시 검증은 기준선 생성 이후의 불변성만 입증한다. 사용자 확인 전 운영 적용 준비 완료로 선언하지 않는다.

125~150 밝기 범위, PatchCore 34.1442, 기존 품질 경고→REINSPECT 및 모든 검사·RIG·수동·Gemini 기록을 유지한다.
아래 계약은 적용 제안이며 운영 API/JSONL 스키마를 지금 변경하지 않는다. 촬영 품질 정답이 없으므로 Accuracy/Recall/Precision 개선을 주장하지 않는다.

## 1. 재사용한 근거와 이번 검증의 경계

- A-1: `docs/a1-image-quality-baseline-analysis.md`, `data/outputs/quality-analysis/a1-baseline-20261020-verified/`.
- A-2: `docs/a2-image-quality-experimental-results.md`, `data/outputs/quality-analysis/a2-experiments-20261020/`.
- A-2 저장 Crop 60개, 원본 포함 합성 비교 600행, ROI 281행/범위 외 19건 제외 결과를 재사용했다. 60개 PNG를 다시 계측하거나 영상을 재생성하지 않았다.
- INSP-001695: 원래 mean 116.09 → 사방 10px 확장 133.83. 동일 기존 픽셀은 보존되고 추가 11,240픽셀의 mean은 249.77이었다. 품질 정상/제품 정상의 증거는 아니다.
- +10px 변경의 mean 절대 변화 중앙값 약16, P10 약1, P25 약4. 고정96창의 변화0은 같은 픽셀을 재측정한 결과이지 병 영역 대표성의 입증이 아니다.
- A-2 확인용 그룹의 정규화 Tenengrad 비율: 밝기 절반1.0017 / 합성 blur2 0.4984 / 해상도 절반2.6297. 노출·흐림·스케일의 효과를 분리해야 한다.
- Gray207 전경 후보는 원본38/60만 계산 가능했고 밝기 절반에서는60/60 실패했다. **v1에는 전경 분할을 도입하지 않는다.**
- 이번 신규 결과는 결정적 합성 uint8 입력과 A-2 계산 함수 재사용에 한정한다. 실제 검사·API·소유권·worker·Sidecar 저장의 통합 검증은 수행하지 않았다.

## 2. 현재 실제 경로와 향후 최소 삽입 지점

| 단계 | 코드 및 확인 사실 |
|---|---|
| 프레임 | `backend/video_source.py:168`에서 검증된 영상의 요청 frame_index까지 OpenCV 순차 디코딩. BGR uint8 원본 해상도 |
| Capture | `backend/video_api.py:150` → CaptureStore. 전체 프레임 PNG이며 ROI Crop과 다름 |
| Crop | `backend/grab_inspection.py:158` 이후 `frame[y:y+h,x:x+w].copy()`. Resize/Padding 없음. 검사 입력 PNG를 영속 저장 |
| 출처 | `grab_inspection_inputs/IMG-GRAB-*.json`에 image_id/owner/crop_sha256. 검사 metrics.input_provenance에 영상·프레임·ROI·원본/Crop 해시 연결 |
| 기존 품질 | `backend/inspection.py:469` → `backend/vision.py:40` BGR→Gray. 전체 픽셀 mean/std/min/max를 소수 둘째 자리로 반올림 |
| 기존 경고 | `backend/vision.py:217`: 반올림 mean <125 또는 >150만 경고. 경계125/150 포함 NORMAL. std/min/max는 판정 조건 아님 |
| 모델 | `backend/inspection.py:514` predict는 품질 분석 뒤 실행. 모델의 RGB/256×256/Normalize 입력과 이번 원본 Crop 통계는 구분 |
| 판정 | `backend/decision.py`: 파이프라인 실패 ERROR → 품질 경고 REINSPECT → 모델 미완료/UNKNOWN REINSPECT → 모델 NG/OK. Shadow와 연결 금지 |
| 영속화 | `backend/inspection.py:662` 검사 저장, 663 이벤트 로그 저장. 하나의 원자적 트랜잭션은 아님 |
| RIG | `backend/reinspection_store.py:219` 이후 저장 검사·종료 이벤트 확인, attempt_count/current_inspection_id 갱신, Capture COMMITTED, 상태 파일 저장 후241 return |
| Heatmap | 실제 PatchCore map의 별도 NPZ/JSON/Overlay. 분위수·미분 통계와 무관하며 마스킹/수정하지 않음 |

향후 **GrabInspectionRuntime.inspect에서 ReinspectionStore.execute가 성공적으로 반환한 뒤** post-commit Shadow 작업을 예약하는 지점이 가장 작다.
품질 계산 직후나 ProvenanceStorage.save_inspection 내부에 저장 작업을 끼우면 이후 이벤트/RIG 저장 실패를 완료된 Shadow 검사로 오인할 수 있어 권하지 않는다.
idempotent 재요청에서 같은 검사가 반환될 수 있으므로 Shadow도 별도 멱등성을 가져야 한다.
원래 execute가 예외를 내거나 검사가 FAILED/ERROR이면 그 실패를 그대로 보존하고 신규 작업을 예약하지 않는다.

## 3. 공통 입력·좌표·정밀도 계약

1. v1 범위는 서버가 검증한 **LIVEVIEW_GRAB의 영속 Crop PNG**다. 클라이언트 경로/배열/출처 플래그를 신뢰하지 않는다. 정적 이미지는 기존 경로 유지, 확대 적용은 별도 승인.
2. 서버 검사 레코드 → 중립 image_id → 관리 경로 → PNG signature/decode/dtype/크기 → 매니페스트와 provenance의 SHA256 대조를 한다. 읽은 동일 바이트를 검증·디코딩해 TOCTOU를 줄인다.
3. 검사 ID·이미지 ID·SHA256·원본 Crop 폭/높이를 결합한다. **ID나 해시는 소유권 증명이 아니다.** 조회는 기존 session/owner 검증을 그대로 적용한다. owner/token은 계측 JSON/API/로그에 노출하지 않는다.
4. BGR uint8 3채널, 좌상단(0,0), x가 열/y가 행, `[x0,x1)×[y0,y1)` 반열린 정수 픽셀. v1 한도는 현재 Grab 원본 프레임 한도에 맞춰 폭≤1920, 높이≤1080. 3×3 미만/잘못된 채널·dtype는 입력 거부.
5. Gray는 `cv2.COLOR_BGR2GRAY`의 uint8 결과. 리사이즈·패딩·감마·CLAHE·노출 보정·denoise·모델 정규화 없음. **ImageView600×600/Zoom/Pan은 계산과 무관.**
6. 통계와 미분은 float64. JSON에는 유한 수치만 저장하며 중간 반올림하지 않는다. 기존 mean과 비교할 때만 `round(shadow.mean_gv,2)==기존 metrics.mean`을 요구한다. 기존 저장 mean은 대체하지 않는다.
7. 라이브러리 버전과 코드 revision/fingerprint는 향후 worker 배포 manifest에 고정한다. 소스 픽셀 해시와 코드 버전을 혼동하지 않는다. 같은 버전·환경에서 수치 재현, measured_at/elapsed_ms는 재현 비교에서 제외한다.

## 4. 후보 A: 영역별 밝기

| 필드 | 정의·단위 |
|---|---|
| mean_gv | 원본 Gray 모든 픽셀 산술평균, GV |
| p10_gv / p25_gv | 전체 픽셀 `np.percentile(...,[10,25],method="linear")`, GV |
| center_mean_gv | 아래 중심 사각형의 평균, GV. 병 영역 평균이라는 이름 사용 금지 |
| edge_mean_gv | 전체 Crop에서 중심 사각형을 뺀 모든 픽셀 평균, GV. 실제 배경 정답 아님 |
| edge_minus_center_gv | 가장자리 평균−중심 평균, GV; 음수 허용, 범위[-255,255] |

**추천: QUARTER_INSET_MIN_SIDE_8.** W,H에 대해 `x0=W//4, y0=H//4, x1=W-W//4, y1=H-H//4`.
각 축 약50%, 면적 약25%이며 홀수 크기의 반올림은 위 식으로 고정한다. 실제 center_xyxy를 기록한다.
중심 픽셀 수 `(x1-x0)*(y1-y0)`, 가장자리 수 `W*H-center_pixels`. 면적 가중 평균으로 전체 mean이 복원돼야 한다.

| 방식 | 장점 | 한계·실패 |
|---|---|---|
| 고정96×96 | 같은 영상 위치/중심을 보존한 ROI 확장에는 같은 픽셀을 비교 | 이미지별 상대 면적 상이, 림/편심 병을 놓침. W/H<96이면 **null**, 조용히 축소하지 않음 |
| 비율 중심(추천) | 여러 Crop 크기에 동일한 기하 규칙 | ROI 확대 시 측정 픽셀이 달라져 불변이 아님. 중심을 병으로 간주할 수 없음 |

고정96은 A-2 비교 근거로만 남기고 v1 필수 저장 계약에는 포함하지 않는다. A-2 코드가 작은 영상에서 `min(96,H,W)`로 축소하는 것과 구분한다.
W/H 중 하나<8이면 center/edge/difference는 null, `TOO_SMALL_FOR_CENTER`. 전체 mean/P10/P25는 유효 입력에서 계속 계산한다.
최소8은 중심과 주변에 여러 픽셀을 확보하기 위한 **제안된 공학적 제한**이지 촬영 품질 합격선이 아니다. 운영 적용 전 사용자 승인 대상이다.
전경/배경 분할은 `NOT_REQUESTED`. 향후 분할 실패 시 전경 통계는 null로 두며 중심 사각형을 병 마스크의 대체값으로 채우지 않는다.

## 5. 후보 B: 선명도·대비

| 필드 | 정확한 계산 |
|---|---|
| gray_variance | 전체 Gray 모집단 분산(ddof=0), GV². 대비에 대한 기술 통계 |
| raw_tenengrad | Sobel x/y `ksize=3, CV_64F, scale=1, delta=0, BORDER_REFLECT_101`; 전체 `mean(Gx²+Gy²)`, Sobel GV² |
| normalized_tenengrad | raw_tenengrad / gray_variance, 무차원 비율. 같은 원본 해상도에서만 비교 |

미분 후 경계 픽셀을 포함한다. 스케일·ROI 크기·배경·노이즈 영향이 있으므로 입력 폭/높이와 처리 방식을 필수 기록한다.
정규화 분모 `gray_variance < 1.0 GV²`이면 null/`LOW_GRAY_VARIANCE`; 정확히1은 계산한다.
이는 표준편차가1 Gray code 미만인 거의 단색 영상에서 작은 분모를 피하는 **보수적 수치 안정화 제안**이다. 실제 저조도/흐림 기준이 아니며 A-2의 `>1e-12` 유효 조건과 구분한다. 임계값의 실증적 최적성은 미검증이며 승인 전 고정 적용하지 않는다.
계산 결과 NaN/Inf이면 해당 값 null/`NON_FINITE`. 검정·흰색 단색의 mean/분산/Raw=0은 실제 측정값이고 normalized만 null이다.
밝기 절반과 합성 Blur의 민감도는 A-2 별도 결과로 기록하며 이 지표만으로 실제 Blur/품질 정상/불량을 확정하지 않는다.

## 6. 버전·저장 계약과 API 호환성

### 6.1 권장 구조

별도 JSON 루트 `quality_observability` 아래 다음 구조를 사용한다. 구체적 Draft Pydantic/JSON Schema는 격리 probe와 최종 검증 폴더에 있다.

| 필드 | 계약 |
|---|---|
| version / mode | `experimental-v1` / `SHADOW_ONLY` |
| source | inspection_id, image_id, crop_sha256(원본 PNG 바이트64자리 소문자 hex), width,height, coordinate_system |
| processing | Gray변환/resize NONE/Sobel설정/ddof0/분모하한1.0/중심규칙/실제 center_xyxy/segmentation NOT_REQUESTED |
| metrics | 위9개 필드. 각각 `{value, unit, status, reason}`. 미측정은 value=null이며 사유 필수 |
| status | 9개 모두 유효 `MEASURED`, 일부만 유효 `MEASURED_PARTIALLY`, 모두 미측정 `NOT_MEASURED` |
| measured_at / elapsed_ms | UTC offset 포함 시각 / 유한 비음수 순수 계측 시간(ms) |

leaf status는 `MEASURED` 또는 `NOT_MEASURED`. reason은 null 또는 `TOO_SMALL_FOR_CENTER`, `LOW_GRAY_VARIANCE`, `NON_FINITE`, `TIMEOUT`, `MODULE_EXCEPTION`.
상위/leaf 상태는 수치 유효성 설명이지 `quality_status`나 검사 성공 여부가 아니다. 추가 필드는 거부한다. final_result/quality_status/judge_verdict 등의 판정 필드는 이 구조에 넣지 않는다.
단위는 GV, GV_SQUARED, SOBEL_GV_SQUARED, RATIO로 필드별 고정한다. JSON 직렬화는 `allow_nan=False` 및 Pydantic finite validation을 모두 적용한다.
source의 영상/frame/ROI/RIG는 기존 검사 provenance/그룹 이력을 조회해 연결한다. 복제 owner나 별도의 RIG 횟수를 새 구조에 저장하지 않는다.
합성 예시는 `INSP-999999`, `IMG-SYNTHETIC-A3`이며 **실제 검사 저장 결과가 아니다.** 값 없는 실검사 예시 수치를 만들어 넣지 않았다.

### 6.2 저장 방식 비교

| 방식 | 장점 | 위험 |
|---|---|---|
| 기존 JSONL metrics에 추가 | 한번의 조회로 접근 가능 | 과거 행 재기록 금지와 충돌, 검사/로그/RIG 저장 오류 경계 확장, Agent/클라이언트 계약 영향 |
| 별도 Sidecar(추천) | 기존 기록 불변, 버전별 독립 검증/중단/실패 처리 | 별도 인증 조회·누락 상태·원자적 저장·고아/중복 관리 필요 |

향후 경로 제안: `OUTPUT_DIR/quality_observability/experimental-v1/{inspection_id}/{crop_sha256}.json`.
서버 생성 ID만 허용하고 경로 해석/링크/디렉터리 이탈을 차단한다. source tuple과 내용 검증을 생략하지 않는다.
동일 key=(version,inspection_id,image_id,crop_sha256,processing policy)는 단일 결과만 발행한다. 같은 hash를 가진 다른 검사도 합치지 않는다.
OS lock, 같은 디렉터리의 exclusive 임시 파일, flush/fsync, 기존 파일 존재 확인 후 **덮어쓰지 않는 원자적 발행**이 필요하다. 일반 `os.replace`만으로 덮어쓰기 방지를 주장하지 않는다.
동일 key/내용이면 재사용, 충돌·손상은 정제된 별도 Shadow 오류로 보고하고 기존 결과를 덮어쓰지 않는다. 완성 파일이 없는 부분 쓰기를 성공으로 반환하지 않는다.
프로세스 종료 시 임시 쓰기만 남을 수 있으나 이번 단계에서 어떤 파일도 정리하지 않는다. 계측 저장 실패는 원래 inspection API 성공을 실패로 바꾸지 않는다.

### 6.3 API

현재 `backend/storage.py:82` InspectionRecord는 `extra="ignore"`, metrics는 Dict[str,Any]. 새 top-level 필드를 넣으면 유실될 수 있다.
`backend/main.py:184` 응답 및 프론트 metrics도 확장 가능하지만 엄격 클라이언트·Agent evidence 계약까지 안전하다는 뜻은 아니다.
따라서 v1은 기존 검사 응답/JSONL **변경0**, 추후 승인 시 별도 읽기 전용 `/inspections/{inspection_id}/quality-observability` endpoint를 제안한다(현재 미구현).
인증은 기존 Grab 조회와 동일하고 unauthorized/missing/source mismatch를 숨겨 우회하지 않는다. 권한 있는 기존 검사에서 Sidecar가 없으면 `NOT_AVAILABLE`로 표현하며 검사 실패나 품질 NORMAL로 간주하지 않는다. 조회만으로 계측/모델/Google 재실행 금지.
`backend/agent/tools.py:80`은 지표 allowlist를 사용한다. 이번 계측을 Diagnostic Fact Catalog/Gemini로 자동 노출하지 않는다. Heatmap·UI 기능도 그대로 유지한다.

## 7. 실패 안전성

| 상황 | 설계된 처리 | 이번 검증 수준 |
|---|---|---|
| 3×3 미만/손상/채널·dtype 오류 | 작업 입력 거부, 원 검사 보존. 신뢰할 source가 없으면 가짜 Sidecar 생성 금지 | 합성 배열 오류 처리 검증; PNG 손상 worker 통합 미실행 |
| 중심 계산 불가(<8) | 중심/가장자리/차이 null, 전체/미분 중 유효한 값 유지 | 합성 검증 |
| ROI가 원본 프레임 밖 | 기존 서버 경계 검증 유지, 임의 clip/pad 금지 | 기존 코드 확인; 신규 API 미실행 |
| 병이 ROI 경계에 접촉 | 기하 중심 통계는 계산 가능하나 병 분할 성공을 주장하지 않음 | A-2 경계 실패 테스트 재사용 |
| 전경/배경 분할 실패 | v1 미사용. 향후 foreground=null, 중심 통계로 대체 금지 | A-2 실패 테스트 재사용 |
| 완전 검정/흰색/극저조도 | 실제 mean/raw/분산 기록, 작은 분모 normalized=null. 품질 경고 해제 금지 | 합성 단색/단일 미세 픽셀 검증 |
| NaN/Inf | 해당 leaf=null/NON_FINITE, 잘못된 입력/JSON 거부 | 합성·스키마 검증 |
| 시간 초과/모듈 예외 | 수치 전부 미수신이면 null 및 TIMEOUT/MODULE_EXCEPTION, 원 검사 상태 불변 | **실패 envelope만 검증**, worker 강제중단 미구현 |
| 쓰기 권한/디스크/원자 발행 실패 | 정제된 Shadow 전용 진단; 저장 성공으로 표시 금지. 기존 검사/이벤트/RIG 수정 금지 | 설계만, 운영 저장 실패 주입 미실행 |
| 원래 검사/로그/RIG 실패 | 원래 오류/RECOVERY_REQUIRED 보존, Shadow 실패로 치환하거나 성공으로 위장 금지 | 원 코드 저장 순서 확인; 통합 미실행 |

향후 실행 모델은 **검사/RIG commit 이후 별도의 bounded worker**를 권장한다. 순수 계산 worker1개, 대기 작업1개를 잠정 상한으로 제안하며 초과 시 Shadow만 `NOT_AVAILABLE` 및 별도 진단을 남긴다.
worker에는 검증된 이미지 사본/최소 식별자만 전달하고 FastAPI main/CaptureStore/비밀 설정을 import하지 않는다. 필요 메모리/worker 부하 상한은 운영 전 실측해야 한다.
`asyncio.wait_for(to_thread(...))`만으로 native OpenCV 실행이 취소된다고 주장하지 않는다. hard timeout이 필요하면 지속 실행 전용 계산 프로세스를 사용하고 **그 worker만** 종료·교체하는 설계에 별도 승인이 필요하다.
soft deadline 방식이라면 늦은 결과 폐기와 슬롯 유지가 필요하며 hard CPU 중단 보장과 다르다. 무한 큐/무제한 새 스레드/자동 재계측/기존 성공 Sidecar 교체를 허용하지 않는다.
실패를 기록할 저장소도 고장 나면 원래 결과를 보존하고 Shadow는 조회 시 NOT_AVAILABLE로 취급한다. 원본 inspection_logs.jsonl에 새 오류를 추가해 기존 이력을 바꾸지 않는다.

## 8. 비용 실측과 수락 기준 제안

이번 합성 벤치마크: Python3.11.16/OpenCV5.0.0/NumPy2.4.6, OpenCV1스레드, 크기별 결정적 난수 uint8 BGR.
warmup1회 뒤30회. Gray변환·분위수·A/B 계산·Draft 검증 포함, PNG decode/hash/파일 IO/큐/worker IPC 제외.
A-2 재사용 sharpness 함수는 Laplacian도 계산하므로 이 결과를 최적화된 미래 전용 worker 비용으로 단정하지 않는다.

| 원본 입력 | median ms | P95 ms | max ms |
|---|---:|---:|---:|
| 96×96 | 0.36 | 0.50 | 0.61 |
| 160×160 | 1.04 | 1.26 | 1.34 |
| 280×280 | 3.00 | 3.73 | 3.94 |
| 512×512 | 10.03 | 10.74 | 11.09 |
| 1920×1080 | 79.61 | 84.17 | 88.09 |

A-2 실제60개에서 별도 성분 P95는 global통계0.94ms, raw/normalized sharpness1.77ms였다. 미리 Gray 변환된 별도 성분 벤치마크이므로 이번 수치와 합산하거나 속도 향상률로 비교하지 않는다.
**잠정 계산 예산 제안**: 측정 P95의3배를 다음5ms로 올림하면 280급15ms / 512급35ms / 최대 입력255ms. 이는 부하·호스트 편차를 위한 제안된 여유이며 보장된 SLA/실측 timeout 임계값이 아니다.
적용 환경에서 decode/hash/IPC/파일저장까지 분리 측정한 뒤 worker deadline/큐 정책을 승인해야 한다. 검사 응답 지연과 순수 계측 시간을 별도로 보고한다.

| 수락 항목 | 기준 |
|---|---|
| 재현성 | 같은 바이트·크기·버전에서 metrics/processing 동일. 시각/시간 제외 |
| mean 호환 | 원본 BGR2GRAY 후 소수2자리 비교 시 기존 analyze_brightness와 일치 |
| 좌표 | 원본 반열린 정수 창, 중심+가장자리 픽셀수 합=전체, 가중 mean 복원. 디스플레이 변환 없음 |
| 유효성 | null+reason 규칙/단위/범위/유한성/집계 status 검증. 작은 분모 경계1.0 명시 |
| 추적성 | 서버 검사/매니페스트/같은 PNG 바이트 SHA256/크기 일치, 합성 ID는 운영 저장 금지 |
| 실패 격리 | worker·저장·시간 실패 주입 후 기존 응답/JSONL/로그/RIG/수동/Judge 동일. **운영 연결 후 필수, 현재 미검증** |
| 멱등·권한 | 중복·동시 key/다른 이미지/다른 session/원자 저장/부분 파일 거부. **미래 통합 테스트 필요** |
| 성능 | 배포 호스트에서 크기별 baseline 재측정, 위 예산 승인 후 적용. 계산·대기·IO 별도 기록 |
| 보호 | 전후 파일집합+SHA256 비교. DB 미접속 시 DB 내용 불변성 직접 검증 주장 금지 |

## 9. 이번 실행 결과·중간 차단

- 신규 설계 테스트25개 + 기존 A-1/A-2 합성 회귀37개: **64 PASS / 0 FAIL / 0 SKIP**.
- 최종 증거: `data/outputs/quality-analysis/a3-shadow-design-validation-20261021-final-tests/unit-tests.xml`, `unit-safety.json`.
- 계산 비용: `data/outputs/quality-analysis/a3-shadow-design-validation-20261021-verified/benchmark.json`.
- 최종 계약 JSON Schema: `data/outputs/quality-analysis/a3-shadow-design-validation-20261021-final-tests/contract-schema.json`.
- 합성 JSON 예시: `data/outputs/quality-analysis/a3-shadow-design-validation-20261021-verified/synthetic-example.json`. 당시 draft schema보다 최종 schema/현재 코드의 크기 상한이 우선한다.
- 최초 benchmark는 Windows platform 조회가 NUL 쓰기 시도로 엄격 IO guard에 차단되어 종료됐다. 결과 폴더를 보존하고 메타정보를 sys.platform으로 바꾼 새 폴더에서 재측정했다.
- 초기 pytest도 기본 임시 파일/log의 NUL 접근, 이후 JUnit hostname 조회의 NUL 접근이 차단됐다. 중간60개 assertion 통과는 종료 성공이 아니므로 최종 결과로 쓰지 않는다.
- 최종 runner는 OS uname만 guard 설치 전 캐싱하고 pytest capture=sys, 임시/log/JUnit을 격리 폴더로 지정했다. guard/기존 보호 정책은 완화하지 않았다. 최종 network_attempts=0, blocked_io=0.
- 보호 파일의 샌드박스 해시 preflight에서 Anomaly Map 등252개 PermissionError가 발견됐다. ACL을 바꾸거나 오류를 무시하지 않았고 승인된 읽기 전용 실행으로 전후 해시를 비교했다. 최종 비교 결과는 `a3-shadow-design-validation-20261021/protection-final.json`: **638개 불변, 변경0, 읽기 미검증0**, 최종 guard network_attempts=0/blocked_io=0이다.
- 단, config의 최종 수정시각은2026-10-21 00:29:29 UTC, 최초 보호 기준선 파일 생성은00:31:53 UTC였다. 따라서 config가 기준선 이후 불변이었다는 사실과 시작 git status 대비 변경됐다는 사실은 양립한다. **작업 전체 구간의 운영 코드 불변은 확정할 수 없다.** 본 작업에서 발견한 뒤 추가 구현/운영 작업을 중단했고 이 안전 메모만 반영했다. 변경 원인은 사용자 확인 필요다.
- Capture PNG는 점검 시4개. 어떤 API도 호출하지 않았다. PostgreSQL은 연결하지 않았으므로 내용 불변성은 NOT VERIFIED.

재실행(CMD Miniconda Prompt, 출력은 반드시 존재하지 않는 고유한 새 폴더):

```bat
conda activate vision-insight
python -B scripts/experiments/validate_quality_shadow_design.py --output data/outputs/quality-analysis/a3-new-measurement
python -B scripts/experiments/validate_quality_shadow_design.py --output data/outputs/quality-analysis/a3-new-tests --tests-only
python -B scripts/experiments/validate_quality_shadow_design.py --output data/outputs/quality-analysis/a3-new-measurement --verify-only
```

첫/마지막 명령은 보호 파일 읽기 권한이 있는 계정에서 수행하며 미검증 파일이 있으면 중단한다. 기존 증거 디렉터리 재사용·덮어쓰기 금지.

## 10. 승인 후 최소 구현·검증·롤백 계획

**현재 이 절의 파일은 수정/생성하지 않았다.**

1. 신규 순수 `backend/quality_observability.py`: 위 수학·검증 계약만 구현, decision/model/Gemini/DB 미참조. A-2 전체 실험 measure를 운영 import하지 않는다.
2. 신규 `backend/quality_observability_store.py`: 검증된 서버 경로, 멱등 key/OS lock/원자적 no-overwrite Sidecar. Source 변경/손상은 기존 검사를 재실행하지 않고 Shadow 거부.
3. 신규 `backend/quality_observability_worker.py`: bounded post-commit 예약/timeout/독립 진단. 프로세스 방식과 강제 worker 종료 권한은 명시 승인 후 구현.
4. `backend/grab_inspection.py`: execute 성공 반환 이후에만 예약, 원래 record/return/예외는 그대로. 재요청 반환에도 key 멱등성 적용. RIG 로직 자체 변경 금지.
5. `backend/config.py`: 별도 Shadow enabled 기본false 및 승인된 계산 자원 설정. 기존125/150·34.1442·Agent/Vision timeout은 불변.
6. `backend/main.py`: 승인 시 worker 수명주기 연결만. 별도 GET을 추가한다면 기존 소유권 검사 재사용 및 `docs/inspection-data-schema.md` 계약 추가가 필요하다. 현재 API/문서는 미변경.
7. 1차는 서버 계측만. UI/Agent 노출은 후속 승인으로 분리한다. 프론트엔드나 기존 quality warning 필드에 연결하지 않는다.
8. 격리 테스트에서 원 검사 성공/실패,125/150 경계, 모델OK/NG/UNKNOWN/ERROR, logs/RIG commit 실패, worker/IO 실패·timeout·큐 초과·동시요청·해시변경·권한을 검증한다. Fake inferencer만 사용하고 운영 데이터를 쓰지 않는다.
9. 운영 활성화 전 기존 JSONL·Crop·Anomaly·로그·RIG·수동·Gemini 및 최신 Capture의 보호 범위·해시를 확인한다. 새 Capture가 이전 백업에 포함됐다고 가정하지 않는다. 필요한 외부 백업은 별도 승인받는다.
10. 롤백은 Shadow flag 비활성화 + 예약 중단이며 기존 Sidecar/검사 이력은 보존한다. 이 코드 삭제/과거 파일 복원/품질 기준 변경이 아니다. 프로세스 설정 반영을 위한 서버 재시작은 사용자가 직접 승인·실행한다.

### 서버와 Capture 안전 조건

이번 읽기 전용 확인 시 포트8000 LISTEN 및 이름/명령으로 식별되는 Uvicorn/backend.main 프로세스가 관찰되지 않았다. 이후 상태가 같다고 보장하지 않으며 서버를 시작하지 않았다.
실제 구현 직전에 **반드시 다시 확인**한다. Uvicorn --reload는 backend뿐 아니라 감시 경로의 `.py` 변경으로 재시작될 수 있으므로 실행 중이면 실험 코드도 안전하다고 가정하지 않는다.
`backend/main.py:66` 종료 시 captures.close, `backend/capture_store.py:224`는 관리 PNG/메모리 세션을 정리한다.
동일 모듈의 `_directory`는 고아 관리 파일을 제거할 수 있고 `bootstrap/authorize`는 TTL cleanup을 호출한다. 따라서 GET/세션 발급도 보존 점검의 대체가 아니다.
재시작하면 정상 세션/CSRF/Capture 등록은 소실될 수 있다. 영속 Crop 존재만으로 owner를 복원하거나 검사 접근을 허용하지 않는다.
사용자 승인 없이 서버 시작/종료/재시작, Capture 복원/삭제, 기존 소유권 변경을 수행하지 않는다.

### 다음 승인 요청의 범위

- **승인 필요:** 추천 기하 중심 규칙(최소8), 정규화 분모하한1.0, version/schema/Sidecar key와 경로, Shadow-only scope.
- **승인 필요:** 기본false feature flag, worker/timeout/큐·자원 정책, 저장·조회 API 범위와 소유권 테스트, 배포 호스트 성능 수락 기준.
- **별도 승인 필요:** 실행 중 서버 코드 변경 및 사용자의 재시작/최신 Capture 백업. 실제 새 Grab·모델·Google 요청은 이 설계 승인에 포함되지 않는다.
- **이번에 하지 않은 것:** 운영 지표 연결, 운영 Sidecar 기록, 신규 경고/최종 판정 적용, 과거 검사 재계측/재판정, DB 접속, 실제 결함/촬영 품질 정확도 평가.
