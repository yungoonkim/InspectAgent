/**
 * VisionInsight Video & Capture API Services
 */

import { apiClient } from './client';
import type {
  VideoListResponse,
  VideoMetadata,
  CaptureSessionResponse,
  CaptureMetadata,
  GrabRequestPayload,
} from '../types/video';

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await apiClient.request<{ status: string }>('/health');
    return res.status === 'ok';
  } catch {
    return false;
  }
}

export async function getVideos(): Promise<VideoListResponse> {
  return apiClient.request<VideoListResponse>('/videos');
}

export async function getVideoMetadata(videoId: string): Promise<VideoMetadata> {
  return apiClient.request<VideoMetadata>(`/videos/${encodeURIComponent(videoId)}`);
}

export function getVideoStreamUrl(videoId: string): string {
  return `${apiClient.getBaseUrl()}/videos/${encodeURIComponent(videoId)}/stream`;
}

export async function ensureCaptureSession(): Promise<string> {
  const existingToken = apiClient.getCsrfToken();
  if (existingToken) {
    return existingToken;
  }

  const res = await apiClient.request<CaptureSessionResponse>('/capture-sessions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  apiClient.setCsrfToken(res.csrf_token, res.session_ttl_seconds);
  return res.csrf_token;
}

export async function grabFrame(
  videoId: string,
  frameIndex: number,
  sourceRevision: string
): Promise<CaptureMetadata> {
  // Ensure valid CSRF token and cookie session
  let csrfToken = await ensureCaptureSession();

  const payload: GrabRequestPayload = {
    frame_index: Math.round(frameIndex),
    source_revision: sourceRevision,
  };

  try {
    return await apiClient.request<CaptureMetadata>(
      `/videos/${encodeURIComponent(videoId)}/grab`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Capture-CSRF': csrfToken,
        },
        body: JSON.stringify(payload),
      }
    );
  } catch (err: any) {
    // If session missing, expired, or CSRF invalid (401 or 403), clear and retry once
    const errorCode = err?.data?.detail?.error_code || err?.message;
    if (
      errorCode === 'CAPTURE_SESSION_REQUIRED' ||
      errorCode === 'CAPTURE_SESSION_EXPIRED' ||
      errorCode === 'CAPTURE_CSRF_INVALID' ||
      err?.status === 401 ||
      err?.status === 403
    ) {
      apiClient.clearSession();
      csrfToken = await ensureCaptureSession();
      return apiClient.request<CaptureMetadata>(
        `/videos/${encodeURIComponent(videoId)}/grab`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Capture-CSRF': csrfToken,
          },
          body: JSON.stringify(payload),
        }
      );
    }
    throw err;
  }
}

export async function getCaptureMetadata(captureId: string): Promise<CaptureMetadata> {
  return apiClient.request<CaptureMetadata>(`/captures/${encodeURIComponent(captureId)}`);
}

export function getCaptureImageUrl(captureId: string): string {
  return `${apiClient.getBaseUrl()}/captures/${encodeURIComponent(captureId)}/image`;
}

export async function fetchCaptureImageBlob(captureId: string): Promise<Blob> {
  return apiClient.fetchBlob(`/captures/${encodeURIComponent(captureId)}/image`);
}
