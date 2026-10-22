# A-1 실제 이미지 품질 기준선 분석 — 2026-10-20

## 1. 상태와 재실행

**A-1 오프라인 측정 완료. A-2 운영 적용은 미실시이며 별도 승인 대상이다.**
제품 정상/불량 정답과 촬영 품질 정상/불량 정답은 확보하지 않았으므로 검출 정확도, 품질 분류 정확도, 임계값의 타당성을 확정하지 않는다.

최종 근거: `data/outputs/quality-analysis/a1-baseline-20261020-verified/`

```bat
conda activate vision-insight
python -B scripts/experiments/analyze_quality_baseline.py --output data/outputs/quality-analysis/a1-baseline-새로운고유이름
```

출력 경로는 `data/outputs/quality-analysis/` 아래의 **존재하지 않는 새 폴더**여야 한다. 기존 출력 덮어쓰기 금지.
서버/API/모델/DB를 사용하지 않는 로컬 파일 분석이다. 서버 설정과 자격 증명을 읽지 않는다.
`sys.addaudithook`으로 네트워크 연결, `.env`/ground_truth/evaluation_private 열람, 분석 폴더 밖 Python 파일 변경을 차단한다.
수치 지표용 후보 상수(207, HSV 200/40, 디지털 포화 1/254)는 **실험 정의**이며 새 품질 판정 기준이 아니다.

산출물:
- `results.json`: 60개 Crop 전체 지표·히스토그램·분할 후보·원본/영상 표본·손실·ROI 민감도·합성 스트레스.
- `inspection-metrics.csv`: 검사/이미지/영상/Capture/해시·ROI·기존 판정 및 주요 지표. CSV의 partitions 열은 JSON이다.
- `INSP-001695-partitions.png`, `INSP-001702-partitions.png`, `INSP-001704-partitions.png`: 분할 후보 비교. 초록색은 실험 마스크이며 결함 표시가 아니다.
- `case-histograms.png`: 세 사례의 GV 히스토그램. 빨강 125·주황 150은 기존 기준선이다.
- 각 사례의 `stress-*.png`: 원본과 분리된 디지털 변화 사본. 실제 저노출/흐림 촬영 자료가 아니다.
- `protection-before.json`, `protection.json`: 읽은 보호 자산의 SHA256 전후 검증.

## 2. 실제 코드 경로

| 단계 | 확인한 구현 |
|---|---|
| 영상 디코딩 | `backend/video_source.py:168`: SHA256/revision·형식·크기 확인 후 OpenCV VideoCapture로 0번부터 요청 frame_index까지 순차 read. 1920×480 BGR uint8 프레임 |
| Grab | `backend/video_api.py:150`, `backend/capture_store.py:143`: 정상 세션/CSRF를 검증하고 전체 원본 프레임을 PNG로 저장. ROI는 후속 inspect 입력이며 이 API는 ROI Crop을 저장하는 API가 아님 |
| ROI Crop | `backend/grab_inspection.py:158`: `frame[y:y+height, x:x+width].copy()` 후 PNG 저장. 원본 영상 픽셀·반열린 구간. Resize/Padding 없음 |
| 영속 입력 | `OUTPUT_DIR/grab_inspection_inputs/IMG-GRAB-*.png` 및 `.json`. JSON은 image_id/owner/crop_sha256. 검사 metrics provenance에는 Capture/영상/프레임/ROI/해시 연결 |
| 품질 분석 | `backend/inspection.py:469` → `backend/vision.py:42`: 원본 Crop의 BGR→Gray 후 모든 픽셀 mean/std/min/max. 병 내부·배경·반사·그림자를 모두 포함 |
| PatchCore | 품질 계산 뒤 `backend/inspection.py:514`에서 predict. Inferencer는 RGB 변환, 256×256 resize, ImageNet normalize. 이 모델 변환 이미지는 기존 품질 계산의 입력이 아님 |
| 기록 | inspection JSONL metrics에 mean/std/min/max, 품질 상태·점수·판정·provenance. 별도 이벤트 JSONL에 검사 ID로 연결 |

현재 품질 경고는 **소수 둘째 자리로 반올림한 mean만** 사용한다.
mean < 125 → WARNING_LOW_BRIGHTNESS, mean > 150 → WARNING_HIGH_BRIGHTNESS, 경계 125/150 포함 → NORMAL.
std/min/max는 저장하지만 품질 판정 조건에 쓰지 않는다. 흐림/선명도/포화/분할은 운영 품질 경고에 사용하지 않는다.
반올림에 의한 극근접 경계 효과가 있을 수 있으나 이번 116.09 vs 128.06 차이를 설명하는 원인은 아니다.

`backend/decision.py:32`의 기존 우선순위는 실패 ERROR → 품질 경고 REINSPECT → 모델 미완료/UNKNOWN REINSPECT → 정상 품질에서 모델 NG/OK다.
PatchCore threshold 34.1442, Normalize/Calibration, RIG/수동 판정은 전혀 변경하지 않았다.
설정 기본값 125/150과 기존 저장 품질 상태의 대조는 했지만, 현재 서버 프로세스 환경변수를 별도로 조회하지 않았다.

## 3. 실제 분석 범위와 제외

- 저장 Grab 기록 78건 중 VID-000002 28건, VID-000003 32건: **60개 Crop 전수 분석**.
- 18건은 VID-000001이므로 이번 두 영상 비교 범위에서 제외. 해당 18건이 손상/실패했다는 뜻은 아니다.
- 대상 60건은 ID 중복 없이 PNG SHA256 = provenance = 입력 매니페스트, 해당 영상 hash/revision, 동일 프레임 ROI와 PNG의 모든 픽셀, 기존 mean 2자리 값이 모두 일치했다.
- 같은 60건의 기존 품질 함수를 명시적 125/150으로 재계산한 품질 상태 불일치: **0건**. 새 Inspection은 생성하지 않았다.
- 영상 2개 각각 등간격 9프레임: 총 18개 전체 프레임/컨베이어 띠(행 107:414) 통계.
- 실제 제작 원본 12장: 제작 manifest의 중립적 VIDEO-SRC ID와 SHA256 확인. 900×900 원본 전체 GV 평균 범위 134.73~138.37.
- 원본 정답 폴더명을 분석 출력·Agent 입력으로 전달하지 않았다. source_id/hash만 출력하고 결함 라벨/ground_truth는 사용하지 않았다.
- 원본 12장, 실제 저장 Crop 60개, 프레임 표본 및 기존 인코딩 중간 영상 1개는 서로 역할이 다르다. 이미지 개수를 독립 제품 표본 수로 합산하지 않는다.

## 4. 영상 생성과 분포

두 영상 모두 밝은 배경이며 1920×480, 30fps, H.264다. VID-000002는 회색 배경 VID-000001과 다르다.
VID-000002의 등록 파일과 기존 line-free control SHA256은 동일하다.

| 항목 | VID-000002 | VID-000003 |
|---|---|---|
| 재생 | 8초/240프레임 | 16초/480프레임 |
| 병 원본/변환 | 같은 12장, 외곽 alpha·260px resize·회전·여백·그림자 | 동일 계열 |
| 배경 | 기본 GV 255에 노이즈·가장자리 음영, 검은 선/줄무늬 제거 | 일정한 흰색 255, 선/줄무늬 없음 |
| 간격/속도 | 350px / 252px/s | 380px / 168px/s |
| 인코딩 | MP4V render→MP4V clean→H.264 CRF18 | raw BGR→H.264 CRF18, yuv420p |
| 전체 프레임 mean(9표본) | 114.54~121.24 | 125.36~126.86 |
| 컨베이어 띠 mean(9표본) | 149.33~159.80 | 165.10~167.46 |
| 실제 검사 ROI mean(모든 저장 표본) | 93.32~127.66 | 108.67~128.83 |
| 기존 결과 | 27 REINSPECT / 1 OK | 12 REINSPECT / 17 OK / 3 NG |

선택된 ROI/병/회차가 서로 다르므로 결과 비율은 품질 알고리즘 정확도도 모델 검출 정확도도 아니다.
두 영상은 같은 프레임 번호라도 같은 병 위치/시간이 아니므로 영상 간 PSNR/SSIM을 계산하지 않았다.
병 내부는 불투명한 원본 픽셀로 합성한다. 배경을 밝히면 실제 유리 내부까지 물리적으로 밝아지는 시뮬레이션이 아니다.

## 5. 실제 세 사례

모두 VID-000003이다. 표의 모델 점수/판정은 **과거 실제 저장값**이며 이번에 추론하지 않았다.

| 검사 ID | 프레임 | ROI x,y,w,h | 모델 점수/소견 | mean / std | 저밝기(<125) | 밝음(≥200) | 기존 품질 → 최종 |
|---|---:|---|---|---|---|---|---|
| INSP-001695 | 5 | 1574,129,271,271 | 30.6361 / OK | 116.09 / 82.79 | 68.77% | 28.23% | LOW → REINSPECT |
| INSP-001704 | 455 | 666,119,293,276 | 28.5076 / OK | 128.06 / 87.82 | 62.85% | 34.96% | NORMAL → OK |
| INSP-001702 | 183 | 666,119,293,276 | 42.1664 / NG | 127.25 / 88.88 | 62.33% | 34.86% | NORMAL → NG |

각각 PNG SHA256:
- INSP-001695: `cd50e5e6bac711d7e1f95f8041140315e7172fe6feb3e2ee433ee92927c99147`
- INSP-001704: `be66c9b904c2be661eb3f15fddd244592347a009d158807bcf35b1e166044460`
- INSP-001702: `cd317783175a7a2f73e3671d94c4fab2e8dfafaa503cb48118814233a8b869e8`

Image ID/Capture ID는 results.json/CSV에 저장했다. 입력 manifest의 owner 값은 출력하지 않는다.
세 사례 각각의 실제 이벤트는 INSPECTION_STARTED / IMAGE_LOADED / ANALYSIS_COMPLETED /
INFERENCE_STARTED / INFERENCE_COMPLETED / INSPECTION_COMPLETED의 6건이다. 실제 로그를 센 결과이며 모든 검사에 6건이라고 가정하지 않았다.

### 평균 차이의 정량적 설명

Gray <207의 어두운 군과 나머지 밝은 군으로 나눈 실험:

| 검사 | 어두운 군 mean | 밝은 군 mean | 밝은 군 면적비 |
|---|---:|---:|---:|
| INSP-001695 | 68.15 | 242.21 | 27.54% |
| INSP-001704 | 67.45 | 244.14 | 34.31% |

전체 평균 차이 +11.9695 GV를 695 기준 가중평균으로 분해하면 구성비 변화 +11.7702, 어두운 군 평균 변화 −0.4621, 밝은 군 평균 변화 +0.6614 GV다.
**수치상 항등식이며 실제 병 분할 정답이나 물리적 노출 차이를 증명하는 것은 아니다.**

동일 이미지 조건을 확인하기 위해 같은 영상 프레임에서 ROI를 각 변 10px씩 확대/축소했다. 새로운 Grab은 실행하지 않았다.

| 같은 프레임의 참조 검사 | 10px 축소 | 저장 ROI | 10px 확대 | 추가 픽셀 mean |
|---|---:|---:|---:|---:|
| INSP-001695 | 96.77 | 116.09 | 133.83 | 249.77 |
| INSP-001704 | 109.51 | 128.06 | 143.77 | 251.65 |
| INSP-001702 | 108.85 | 127.25 | 143.04 | 251.43 |

확대 시 기존 ROI의 모든 픽셀을 유지하며 추가 픽셀은 세 사례 모두 100% GV≥200이었다. 노출이나 기존 병 픽셀을 바꾸지 않고 배경 추가만으로 평균이 125를 넘었다.
전체 ROI mean의 배경 비율 민감도를 직접 확인한 것이다. **배경을 늘려 품질 기준을 통과시키도록 권고하는 것은 아니다.**
확대/축소 ROI의 PatchCore 추론이나 새로운 서버 최종 판정은 실행하지 않았다.

## 6. 분할 후보와 한계

- Gray <207, Otsu 어두운 클래스, HSV 저채도/높은 V 배경 후보, 닫힌 최대 Gray 외곽의 네 후보를 비교했다.
- 앞 세 방법은 전체 픽셀을 두 군으로 나눈다. 그림자·반사·병 내부의 흰 영역을 오분류할 수 있어 실제 병 마스크가 아니다.
- 닫힌 외곽 후보가 이미지 경계에 닿으면 계산 불가로 표시한다. 누락된 윤곽을 원이나 완전한 외곽으로 보완하지 않는다.
- 외곽 후보 38건은 영역 통계를 계산했고, 22건은 경계 접촉으로 계산 불가다. INSP-001695도 계산 불가이며 미검출 영역을 채우지 않았다.
- INSP-001704의 닫힌 외곽 안쪽 mean은 67.46, 바깥은 244.15다. INSP-001702는 66.93/244.18이다.
- 수치 confidence는 도입하지 않고 `NOT_CALIBRATED_NO_SEGMENTATION_GROUND_TRUTH`로 표시했다. C단계 형상/결함 검사는 구현하지 않았다.
- 비교 이미지 한 사례를 육안 확인했으나 분할 정확도는 NOT VERIFIED다. 독립적인 마스크 정답과 검증이 필요하다.

## 7. 밝기 이외 지표

Laplacian은 OpenCV CV_64F/ksize=3의 분산이다. Tenengrad는 Sobel ksize=3의 Gx²+Gy² 전체 픽셀 평균이다.
Gray std, p95−p05/p99−p01, ≤1/≥254 디지털 포화율도 측정했다.

| 검사 | Laplacian 분산 | Tenengrad | p95−p05 | ≥254 비율 |
|---|---:|---:|---:|---:|
| INSP-001695 | 811.52 | 4818.51 | 217 | 0.0449% |
| INSP-001704 | 910.09 | 4477.03 | 217 | 0.0049% |
| INSP-001702 | 804.92 | 4818.88 | 219 | 0.0198% |

이미지 내용이 다르므로 이 값의 크기를 정상/불량 또는 촬영 품질 순위로 해석하면 안 된다.
특히 695와 1702는 Tenengrad가 거의 같아도 기존 모델 소견이 다르다. 이 지표는 결함 분류기가 아니다.

**합성 스트레스 시험(실제 촬영 품질 정답이 아님)**:
- Gaussian sigma=2에서 695의 mean은 116.09→116.10으로 거의 같지만 Laplacian은 811.52→68.58, Tenengrad는 4818.51→2494.40으로 감소했다.
- 1704도 mean 128.06→128.09인 반면 Laplacian은 910.09→58.73이었다. mean만으로 이런 밝기 불변 blur를 식별할 수 없다.
- 디지털 절반 게인에서 695의 Laplacian은 208.55까지 감소했다. 감소 원인은 blur에만 한정되지 않고 대비에도 의존한다.
- 디지털 1.8배 클리핑에서 세 사례의 ≥254 비율은 30.07~36.65%였다. 실제 과노출/결함 라벨이 아니다.
- 전체 프레임 Laplacian 약 7200은 제목·프레임 외곽 등에도 지배되므로 병 ROI의 약 734~1567과 직접 비교하지 않는다.
- 900×900 원본 Laplacian 255.92~555.44와 축소 ROI도 스케일/영역이 달라 수치 크기로 화질 개선·열화를 판단할 수 없다.

## 8. 대응이 확인된 인코딩 손실

VID-000002는 기존 `bright_no_lines.clean.mp4`(MP4V)→`bright_no_lines_control.mp4`(H.264)의 실제 변환 경로를 코드로 확인했다.
최종 control과 등록 영상의 hash, 해상도/FPS/프레임 수 일치 및 프레임 번호 보존 변환을 확인한 뒤 대응되는 9프레임의 같은 벨트 띠를 비교했다.

- Gray MAE: 0.576~0.761 GV
- PSNR: 45.12~47.29 dB
- SSIM: 0.99166~0.99446（Gray、11×11 Gaussian、sigma1.5、境界5px除外）
- mean 차이: +0.00258~+0.04272 GV

**확인한 마지막 H.264 변환의 mean 변화는 사례의 약 12 GV 차이보다 작다.**
MP4V 생성 전 raw 픽셀은 저장되어 있지 않아 그 이전의 합성/두 차례 MP4V 압축 손실은 분리하지 못했다.
VID-000003은 raw pre-encode 프레임이 없어 PSNR/SSIM을 계산하지 않았으며 NOT VERIFIED다.
MVTec 원본과 영상 ROI도 resize/회전/alpha/배경/영역이 달라 PSNR/SSIM을 계산하지 않았다.
확인한 프레임→PNG→재로딩→Crop 구간은 60건 전체 픽셀이 일치하여 추가 손실이 관찰되지 않았다.

## 9. 검증과 보호

단위 테스트(합성 배열만 사용):

```bat
set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -B -m pytest tests/test_quality_baseline_analysis.py -q -p no:cacheprovider --basetemp data/outputs/quality-analysis/a1-tests-新規名 --junitxml=data/outputs/quality-analysis/a1-tests-新規名.xml
```

기존 GV 일치, 상수 이미지의 유한값, 분할 가중평균, 닫힌 외곽 실패 시 null, 합성 blur 반응, PSNR/SSIM의 알려진 입력값, 기존125/150 경계를 검증했다.
최종 결과는 **12 PASS / 0 FAIL / 0 SKIP**다. 증거: `data/outputs/quality-analysis/a1-final-unit-tests-20261020.xml`.
초기 8개 테스트도 통과했고 이후 경계값 테스트 4개를 추가해 재실행했다. 전체 브라우저/모델 테스트는 하지 않았다.

최초 sandbox 실행 `a1-baseline-20261020/`에서는 308파일 불변을 확인했지만 Anomaly Map 240파일에 PermissionError가 발생해 보호 검증 미완료로 실패 처리했다. 첫 증거도 그대로 남겼다.
ACL 변경이나 오류 무시 없이 승인된 사용자 권한으로 새 폴더 `a1-baseline-20261020-verified/`에 재실행했다.
최종 **548파일 SHA256 전후 일치, 변경/소실 0, 미검증 파일 0**이다.
대상은 Inspection/이벤트 JSONL, Capture, 영속 Crop/metadata, Anomaly Map, RIG/수동 확인, Judge/Agent 저장 결과, 영상, 모델, backend, frontend/src, migration 및 선택한 원본 12장이다.
기존 `.env`·비밀값·평가 마스크는 읽지 않았다. PostgreSQL 연결은 0회이며 실제 DB 스냅샷 불변성은 NOT VERIFIED다. 파일 해시로 DB 내용을 증명했다고 주장하지 않는다.
네트워크 시도0, Google0, Grab0, PatchCore 로드/추론0, 서버 조작0이다. 운영 품질/판정 코드는 변경하지 않았다.

## 10. A-2 제안과 미확정 사항

상세 내용은 [A-2 개선안](a2-image-quality-improvement-proposal.md)에 정리했다. 우선순위:
1. 기존 ROI mean을 유지하며 출처가 연결된 영역 통계와 ROI 구성 안정성을 **shadow 계측**한다. 영역별로 기존125를 그대로 적용하지 않는다.
2. 같은 ROI/스케일의 실제 촬영 blur·노출 대조 데이터를 확보하여 Laplacian/Tenengrad와 국부 대비를 검증한다.
3. 실제 노출 라벨과 반사 위치가 있는 데이터로 디지털 포화/국부 정보 손실 후보를 평가한다.

현재 근거만으로 새로운 threshold, NORMAL 분류기, 최종 판정 우선순위를 확정할 수 없다.
실제 카메라의 저노출·motion blur 정답, 수동 병 마스크 정답, 대응 raw encoder 입력 및 독립적인 정상 촬영 집단이 부족하다.
이번 세 사례만 통과시키는 낮은 threshold, 경고 무시, 마스크로 Heatmap 반응을 없애는 처리, C단계 형상 검사는 하지 않는다.
