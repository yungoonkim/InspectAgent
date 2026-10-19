# Step 11 — OpenCV 실제 이미지 검사 상태

**DEFERRED / NOT TESTED**.

사용자의 최신 우선순위에 따라 실제 Crop→검사·로그·Heatmap→신규 Diagnostic 보고서→독립 Vision→동일 검사 UI 연결을 먼저 수행했다.
기존 untracked 초안 `scripts/experiments/opencv_rim_inspection.py`는 보존했으며 이번 핵심 개발에서 실행·확장·API 연결하지 않았다.

따라서 이번 작업의 원·윤곽·원형도·끊김 실측값이나 OpenCV overlay 실험 결과는 **없다**. 실험적 기능을 실제 제품 NG/OK 판정에 적용하지 않았다.

후속 별도 범위에서 승인된 PNG와 SHA256, 합성 원/미검출 사례, 검출 좌표·실측 특징·불확실 사유·overlay를 격리 저장하는 최소 검증이 필요하다. 검출되지 않는 이미지에는 UNKNOWN/UNDETERMINED를 유지해야 한다.
PatchCore 비교는 동일 이미지와 독립 정답/조건이 확보된 뒤 설계한다. 라벨 없이 정확도·Recall을 계산하거나 원본 final_result와 결합하지 않는다.

핵심 연결 결과 및 현재 남은 승인 사항은 `docs/day7-step11-real-inspection-ui-flow.md`와 `docs/day7-step11-gemini-vision-live-integration.md`를 참조한다.
