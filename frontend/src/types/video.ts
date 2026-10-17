/**
 * VisionInsight Video & Capture Type Definitions
 * Matches backend/video_api.py schema
 */

export interface VideoMetadata {
  video_id: string;
  source_revision: string;
  width: number;
  height: number;
  fps: number;
  frame_count: number;
  duration_seconds: number;
  codec: string;
  stream_url: string;
  frame_index_min: number;
  frame_index_max: number;
}

export interface VideoListResponse {
  videos: VideoMetadata[];
}

export interface GrabRequestPayload {
  frame_index: number;
  source_revision: string;
}

export interface CaptureMetadata {
  capture_id: string;
  video_id: string;
  frame_index: number;
  source_revision: string;
  frame_timestamp_ms: number;
  timestamp_basis: string;
  pts_ms: number | null;
  width: number;
  height: number;
  image_url: string;
  created_at: string;
  expires_at: string;
  status: string;
}

export interface CaptureSessionResponse {
  csrf_token: string;
  session_ttl_seconds: number;
  capture_ttl_seconds: number;
}

export interface ApiErrorDetail {
  error_code?: string;
  message?: string;
  detail?: string | { error_code?: string };
}
