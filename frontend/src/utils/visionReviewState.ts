import type { InspectionResponse } from '../types/inspection';
import type { VisionReview } from '../types/visionReview';

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
    && ['LIVE', 'FAKE_TEST'].includes(review.analysis_mode);
}
