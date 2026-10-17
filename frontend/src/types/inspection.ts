/**
 * Vision inspection data types for FastAPI backend contract
 */

export interface ImageMetadata {
  filename: string;
  width: number;
  height: number;
  channels: number;
}

export type FinalVerdict = 'OK' | 'NG' | 'REINSPECT' | 'ERROR';
export type QualityStatus = 'NORMAL' | 'WARNING_LOW_BRIGHTNESS' | 'WARNING_HIGH_BRIGHTNESS' | 'ERROR';

export interface InspectionResponse {
  inspection_id: string;
  product_id: string;
  image_id: string;
  status: 'COMPLETED' | 'FAILED' | string;
  result: 'OK' | 'NG' | 'UNKNOWN' | string;
  timestamp: string;
  image_quality_status: QualityStatus;
  metrics: Record<string, any>;
  image_metadata?: ImageMetadata;
  anomaly_score: number | null;
  inference_time_ms: number | null;
  model_version: string | null;
  decision_threshold: number | null;
  defect_detection_status: string | null;
  final_result: FinalVerdict | null;
  final_reason_code: string | null;
  provenance?: 'STORED_RESULT' | 'LIVE_INSPECTION' | 'RECORDED_TEST_FIXTURE' | 'NOT_ANALYZED';
}

export interface InspectionListResponse {
  total: number;
  inspections: InspectionResponse[];
}

export interface ImageListResponse {
  total_images: number;
  sample_ids: string[];
  image_ids: string[];
}
