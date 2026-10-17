/**
 * Inspection and Gemini Agent API service
 */

import { apiClient } from './client';
import type {
  InspectionResponse,
  InspectionListResponse,
  ImageListResponse,
} from '../types/inspection';
import type { AgentReport } from '../types/agent';

/**
 * Fetch list of registered neutral image IDs from FastAPI backend
 */
export async function getInspectionImages(): Promise<ImageListResponse> {
  return apiClient.request<ImageListResponse>('/inspections/images');
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
  imageId: string
): Promise<InspectionResponse> {
  return apiClient.request<InspectionResponse>('/inspections', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      product_id: productId,
      image_id: imageId,
    }),
  });
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
