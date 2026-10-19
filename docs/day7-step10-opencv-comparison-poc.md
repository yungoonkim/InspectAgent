# Day 7 Step 10 — OpenCV 비교 PoC 계획 및 상태

## 상태: NOT EXECUTED (P1)

이번 사용자의 후속 지시는 P0 자동화 검증에 범위를 한정했다. 실제 이미지 OpenCV 실험은 실행하지 않았다. PatchCore 운영 결과나 final_result에 OpenCV 출력을 연결하지 않았다.

## 후보 접근

병 입구/Rim이 충분히 해상도 있게 ROI에 포함될 때만 독립 실험 모듈에서 다음을 비교할 수 있다.

1. 입력 BGR/RGB 계약과 실제 Crop SHA256을 기록한다.
2. grayscale, 제한적 조명 보정, Gaussian blur 후 edge/contour 또는 Hough circle 후보를 계산한다.
3. 검출 원 중심 `(cx, cy)`, 반경, 반경 분산, contour circularity `4πA/P²`, 중심 편차, 원주 각도별 edge 연속률을 수치로 기록한다.
4. Polar unwrap을 적용할 때 실제로 검출한 링을 기준으로만 각도별 대비/끊김을 평가한다. 자동 검출이 안정적이지 않으면 `UNKNOWN/UNDETERMINED`로 종료한다.
5. overlay는 격리된 실험 출력 경로에만 저장하고 원본 Crop을 수정하지 않는다.
6. 각 결과는 `experiment_only` provenance, OpenCV 버전, 파라미터, 처리시간과 함께 보존한다. 기준 치수의 출처가 없는 circularity/동심도 값은 합격/불합격 임계값으로 사용하지 않는다.

## 필요한 승인/데이터

- 승인된 실제 병 입구 Crop ID/해시와 사용 목적.
- 라벨을 쓰는 정량 비교라면 외부 평가 정답을 project runtime에서 가져오지 말고 별도 승인된 독립 평가 경계와 데이터 매핑 제공. 이번 단계에서는 `../evaluation_private/` 접근 금지.
- 같은 이미지의 PatchCore 저장 결과와 비교 시 checkpoint fingerprint/threshold/실제 실행 provenance가 있어야 하며, 저장 결과를 새 추론값으로 간주하지 않는다.
- 조명/반사/해상도/기울기 조건과 실패 처리 사전 정의.
- OpenCV 측정치로 운영 판정, 밝기 125.0, PatchCore threshold 34.1442를 변경하지 않는 별도 승인.

## 향후 결과 스키마

`image_id`, `image_sha256`, `source`, `crop_width/height`, `opencv_version`, `parameters`, `detected_contours/circles`, `geometry_metrics`, `reference_basis`, `status (MEASURED/UNKNOWN/ERROR)`, `reason`, `overlay_path`, `elapsed_ms`. 실제 파일 경로는 외부 노출하지 않고 중립 ID를 사용한다.

## 제한

이번에는 OpenCV 계산·overlay 생성·실제 Crop 열람을 하지 않았다. 따라서 검출 수치·좌표·성능·PatchCore 대비 우위를 보고할 값이 없다. 본 문서는 계획이지 PoC 구현 완료 보고가 아니다.
