export type VisionClassification = 'DEFECT_SUSPECTED' | 'QUALITY_ISSUE' | 'NO_VISIBLE_DEFECT' | 'INCONCLUSIVE' | 'ANALYSIS_FAILED';

export interface VisionReview {
  vision_review_id: string;
  inspection_id: string;
  capture_id: string;
  reinspection_group_id: string | null;
  image_sha256: string;
  model_requested: string;
  model_resolved: string;
  prompt_version: string;
  classification: VisionClassification;
  visible_observations: string[];
  limitations: string[];
  recommended_operator_action: string;
  failure_code: string | null;
  created_at: string;
  analysis_mode: 'LIVE' | 'FAKE_TEST';
}

export interface VisionReviewResponse {
  available: boolean;
  review: VisionReview | null;
  capabilities: { enabled: boolean; live_enabled: boolean; analysis_mode: string; reason: string; model_requested: string };
}
