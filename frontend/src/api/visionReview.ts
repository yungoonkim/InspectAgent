import { apiClient } from './client';
import { ensureCaptureSession } from './video';
import type { VisionReviewResponse } from '../types/visionReview';

export function getVisionReview(inspectionId: string): Promise<VisionReviewResponse> {
  return apiClient.request(`/inspections/${encodeURIComponent(inspectionId)}/vision-review`);
}

export async function createVisionReview(inspectionId: string, requestId: string): Promise<VisionReviewResponse> {
  const csrf = await ensureCaptureSession();
  return apiClient.request(`/inspections/${encodeURIComponent(inspectionId)}/vision-review`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Capture-CSRF': csrf },
    body: JSON.stringify({ request_id: requestId }),
  });
}
