import type { InspectionResponse } from '../types/inspection';

function finiteValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function inspectionQualitySummary(inspection: InspectionResponse | null) {
  const mean = finiteValue(inspection?.metrics?.mean);
  const thresholds = inspection?.metrics?.applied_thresholds;
  const lower = finiteValue(thresholds?.low_threshold);
  const upper = finiteValue(thresholds?.high_threshold);
  const meanLabel = mean === null ? '— (측정값 없음)' : mean.toFixed(2);
  const criteria = !inspection ? '—'
    : lower !== null || upper !== null
      ? `검사 응답 기준 · 하한 ${lower?.toFixed(1) ?? '미제공'} / 상한 ${upper?.toFixed(1) ?? '미제공'}`
      : '현재 운영 밝기 하한 125.0 (안내값 · 검사별 적용 기준은 API 미제공)';
  let reason = '검사 결과 없음';
  if (inspection) {
    switch (inspection.image_quality_status) {
      case 'WARNING_LOW_BRIGHTNESS':
        reason = `ROI 전체 평균 GV ${meanLabel} · 서버 저밝기 경고. 제품 불량이나 조명 고장 확정은 아닙니다.`;
        break;
      case 'WARNING_HIGH_BRIGHTNESS':
        reason = `ROI 전체 평균 GV ${meanLabel} · 서버 고밝기 경고. 제품 불량 확정은 아닙니다.`;
        break;
      case 'NORMAL':
        reason = '서버 영상 품질 NORMAL · 제품 결함 여부는 PatchCore 모델 소견과 별도입니다.';
        break;
      case 'ERROR':
        reason = '영상 품질 평가 오류 · 정상 품질로 간주하지 않습니다.';
        break;
      default:
        reason = '영상 품질 상태 미확인';
    }
  }
  return { meanLabel, criteria, reason, modelVerdict: inspection?.result ?? '—' };
}
