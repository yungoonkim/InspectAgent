import type { CropData } from '../types/roi';
import type { InspectionResponse } from '../types/inspection';

export const GRAB_LIMITATION = 'LiveView Grab 기반 검사는 기존 PatchCore 모델을 이용한 실험적 검사입니다. 영상 Crop에 대한 임계값 보정 및 검출 성능은 별도로 검증되지 않았습니다.';

export function cropIdentity(crop: CropData | null): string {
  return crop ? JSON.stringify([crop.captureId, crop.sourceRevision, crop.frameIndex, crop.roi]) : '';
}

export function isGrabInspectionMatching(inspection: InspectionResponse, crop: CropData): boolean {
  const source = inspection.metrics?.input_provenance;
  return inspection.metrics?.input_source === 'LIVEVIEW_GRAB' && !!source &&
    source.capture_id === crop.captureId && source.video_id === crop.videoId &&
    source.frame_index === crop.frameIndex && source.source_revision === crop.sourceRevision &&
    source.crop_width === crop.width && source.crop_height === crop.height &&
    ['x', 'y', 'width', 'height'].every(name => source.roi?.[name] === crop.roi[name as keyof typeof crop.roi]);
}
