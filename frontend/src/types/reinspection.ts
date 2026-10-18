export type ManualOutcome = 'HOLD' | 'MANUAL_OK' | 'MANUAL_NG';

export interface ReinspectionAttempt {
  inspection_id: string;
  parent_inspection_id: string | null;
  attempt_number: number | null;
  anomaly_score: number | null;
  decision_threshold: number | null;
  image_quality_status: string;
  result: string;
  final_result: string;
  final_reason_code: string;
  input_provenance: { capture_id: string; video_id: string; frame_index: number };
}

export interface ReinspectionGroup {
  group_id: string;
  product_id: string;
  version: number;
  status: 'RETRY_ALLOWED' | 'COMPLETED' | 'MANUAL_REVIEW_REQUIRED' | 'MANUAL_REVIEWED' | 'RECOVERY_REQUIRED';
  attempt_count: number;
  remaining_attempts: number;
  max_attempts: number;
  current_inspection_id: string | null;
  attempts: ReinspectionAttempt[];
  failed_attempts: ReinspectionAttempt[];
  manual_reviews: { review_id: string; result: ManualOutcome; reason: string; operator_id: string; timestamp: string; authority: string }[];
}
