import type { InspectionResponse } from '../types/inspection';
import type { VisionReview, VisionReviewResponse } from '../types/visionReview';
import type { ReinspectionGroup } from '../types/reinspection';

export function canRequestVisionReview(response: VisionReviewResponse | undefined, consent: boolean): boolean {
  return !!response?.capabilities.enabled && !response.available
    && response.capabilities.result_contract === 'VISION_JUDGE_A_V1'
    && response.capabilities.consent_policy === 'PER_REQUEST_CROP_V1'
    && (!response.capabilities.live_enabled || consent);
}

export function visionInputKey(inspection: InspectionResponse | null): string {
  const source = inspection?.metrics?.input_provenance;
  return inspection?.metrics?.input_source === 'LIVEVIEW_GRAB' && inspection.final_result === 'REINSPECT' && source?.crop_sha256
    ? JSON.stringify([inspection.inspection_id, source.capture_id, source.crop_sha256]) : '';
}

export function matchesVisionInput(review: VisionReview, inspection: InspectionResponse): boolean {
  const source = inspection.metrics?.input_provenance;
  return !!visionInputKey(inspection) && review.inspection_id === inspection.inspection_id
    && review.capture_id === source?.capture_id && review.image_sha256 === source?.crop_sha256
    && review.reinspection_group_id === (inspection.metrics?.reinspection?.group_id ?? null)
    && ['LIVE', 'FAKE_TEST'].includes(review.analysis_mode)
    && judgeOutcome(review) !== 'INVALID'
    && (review.prompt_version !== 'bottle-vision-judge-a-v1' || review.image_id === inspection.image_id);
}

export function judgeOutcome(review: VisionReview): 'OK' | 'NG' | 'REINSPECT' | 'ANALYSIS_FAILED' | 'LEGACY_OPINION' | 'INVALID' {
  if (review.prompt_version === 'bottle-independent-vision-v1') {
    return ['DEFECT_SUSPECTED', 'QUALITY_ISSUE', 'NO_VISIBLE_DEFECT', 'INCONCLUSIVE', 'ANALYSIS_FAILED'].includes(review.classification)
      ? 'LEGACY_OPINION' : 'INVALID';
  }
  if (review.prompt_version !== 'bottle-vision-judge-a-v1') return 'INVALID';
  if (review.analysis_status === 'ANALYSIS_FAILED') {
    return review.judge_verdict === null && !!review.failure_code ? 'ANALYSIS_FAILED' : 'INVALID';
  }
  if (review.analysis_status !== 'COMPLETED' || review.failure_code !== null) return 'INVALID';
  return review.judge_verdict !== null && ['OK', 'NG', 'REINSPECT'].includes(review.judge_verdict) ? review.judge_verdict : 'INVALID';
}

export function manualReviewLabel(group: ReinspectionGroup | null, inspection: InspectionResponse): string {
  if (!group || group.group_id !== inspection.metrics?.reinspection?.group_id
    || !group.attempts.some(attempt => attempt.inspection_id === inspection.inspection_id)) {
    return '미조회 · 기존 재검사 패널에서 서버 이력을 확인하세요';
  }
  const latest = group.manual_reviews.at(-1);
  return latest ? `${latest.result} · 개발용 수동 확인 · ${latest.timestamp}`
    : group.workflow_policy === 'judge-assisted-v1'
      ? `미실시 · ${group.status} · 3차 작업자 확인 가능 · Gemini 실행은 필수 아님`
      : `미실시 · ${group.status} · 레거시 3회 후 확인 정책 유지`;
}
