/**
 * Inspection and Gemini Agent API service
 */

import { apiClient } from './client';
import { ensureCaptureSession } from './video';
import type { CropData } from '../types/roi';
import type {
  InspectionResponse,
  InspectionListResponse,
  ImageListResponse,
} from '../types/inspection';
import type { AgentReport } from '../types/agent';
import type { ManualOutcome, ReinspectionGroup } from '../types/reinspection';

/**
 * Fetch list of registered neutral image IDs from FastAPI backend
 */
export async function getInspectionImages(): Promise<ImageListResponse> {
  return apiClient.request<ImageListResponse>('/inspections/images');
}

/**
 * Construct binary URL for a registered neutral image without leaking filesystem paths
 */
export function getInspectionImageUrl(imageId: string): string {
  return `${apiClient.getBaseUrl()}/inspections/images/${encodeURIComponent(imageId)}/file`;
}

export function getGrabInspectionImageUrl(inspectionId: string): string {
  return `${apiClient.getBaseUrl()}/inspections/${encodeURIComponent(inspectionId)}/input-image`;
}

export async function createGrabInspection(crop: CropData, productId: string,
  workflow?: { group: ReinspectionGroup | null; sameProductConfirmed: boolean; requestId: string }): Promise<InspectionResponse> {
  const csrf = await ensureCaptureSession();
  return apiClient.request<InspectionResponse>(`/captures/${encodeURIComponent(crop.captureId)}/inspect`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Capture-CSRF': csrf },
    body: JSON.stringify({ product_id: productId, source_revision: crop.sourceRevision, roi: crop.roi,
      ...(workflow ? { group_id: workflow.group?.group_id ?? null,
        parent_inspection_id: workflow.group?.current_inspection_id ?? null,
        expected_version: workflow.group?.version ?? null,
        same_product_confirmed: workflow.sameProductConfirmed, request_id: workflow.requestId } : {}),
    }),
  });
}

export async function getReinspectionGroup(groupId: string): Promise<ReinspectionGroup> {
  return apiClient.request<ReinspectionGroup>(`/reinspection-groups/${encodeURIComponent(groupId)}`);
}

export async function getCaptureReinspectionGroup(captureId: string): Promise<ReinspectionGroup> {
  return apiClient.request<ReinspectionGroup>(`/reinspection-groups/by-capture/${encodeURIComponent(captureId)}`);
}

export async function saveManualReview(group: ReinspectionGroup, result: ManualOutcome, operatorId: string,
  reason: string, requestId: string): Promise<ReinspectionGroup> {
  const csrf = await ensureCaptureSession();
  return apiClient.request<ReinspectionGroup>(`/reinspection-groups/${encodeURIComponent(group.group_id)}/manual-reviews`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Capture-CSRF': csrf },
    body: JSON.stringify({ expected_version: group.version, request_id: requestId,
      result, operator_id: operatorId, reason }),
  });
}

/**
 * Fetch binary PNG blob for a registered neutral image
 */
export async function fetchInspectionImageBlob(imageId: string): Promise<Blob> {
  const url = getInspectionImageUrl(imageId);
  const response = await fetch(url, { credentials: 'include' });
  if (!response.ok) {
    throw new Error(`정적 이미지 로드 실패 (HTTP ${response.status})`);
  }
  return response.blob();
}

/**
 * Fetch recent inspection records from storage
 */
export async function getRecentInspections(limit = 50): Promise<InspectionListResponse> {
  return apiClient.request<InspectionListResponse>(`/inspections?limit=${limit}`);
}

/**
 * Fetch single existing inspection record by inspection_id
 */
export async function getInspection(inspectionId: string): Promise<InspectionResponse> {
  return apiClient.request<InspectionResponse>(`/inspections/${inspectionId}`);
}

/**
 * Trigger new inspection on FastAPI backend for a registered neutral image_id
 */
export async function createInspection(
  productId: string,
  imageId: string,
  captureAnomalyMap: boolean = false
): Promise<InspectionResponse> {
  return apiClient.request<InspectionResponse>('/inspections', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      product_id: productId,
      image_id: imageId,
      capture_anomaly_map: captureAnomalyMap,
    }),
  });
}

export interface AnomalyMapMetadata {
  schema_version: string;
  inspection_id: string;
  image_id: string;
  model_name: string;
  anomaly_score: number | null;
  decision_threshold: number | null;
  original_image_width: number;
  original_image_height: number;
  anomaly_map_width: number;
  anomaly_map_height: number;
  range?: {
    min: number;
    max: number;
    mean: number;
  };
  localization_available: boolean;
  available?: boolean;
  overlay_url?: string;
}

/**
 * Read-only fetch of stored PatchCore anomaly map metadata
 * Returns 404 if no sidecar was captured for this inspection. Never triggers ML inference.
 */
export async function getInspectionAnomalyMap(
  inspectionId: string
): Promise<AnomalyMapMetadata> {
  return apiClient.request<AnomalyMapMetadata>(
    `/inspections/${encodeURIComponent(inspectionId)}/anomaly-map`
  );
}

/**
 * URL for transparent anomaly map overlay PNG
 */
export function getInspectionAnomalyMapOverlayUrl(inspectionId: string): string {
  return `${apiClient.getBaseUrl()}/inspections/${encodeURIComponent(inspectionId)}/anomaly-map/overlay.png`;
}

/**
 * Read-only fetch of previously stored or recorded Gemini Agent report
 * Never triggers live Gemini API calls
 */
export async function getStoredAgentReport(inspectionId: string): Promise<AgentReport> {
  return apiClient.request<AgentReport>(`/inspections/${inspectionId}/agent-report`);
}

/**
 * Trigger live Gemini Function Calling diagnosis for an existing inspection
 * Requires user confirmation; may take 20-30 seconds
 */
export async function runAgentAnalysis(inspectionId: string): Promise<AgentReport> {
  return apiClient.request<AgentReport>(`/analyze/${inspectionId}`, {
    method: 'POST',
  });
}
