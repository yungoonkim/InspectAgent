export type VisionClassification = 'DEFECT_SUSPECTED' | 'QUALITY_ISSUE' | 'NO_VISIBLE_DEFECT' | 'INCONCLUSIVE' | 'ANALYSIS_FAILED';

interface VisionReviewIdentity {
  vision_review_id: string;
  inspection_id: string;
  capture_id: string;
  reinspection_group_id: string | null;
  image_sha256: string;
  model_requested: string;
  model_resolved: string;
  visible_observations: string[];
  limitations: string[];
  recommended_operator_action: string;
  failure_code: string | null;
  created_at: string;
  analysis_mode: 'LIVE' | 'FAKE_TEST';
  http_attempts?: number | null;
  consent_confirmed_at?: string | null;
  provider_http_status?: number | null;
}

export interface LegacyVisionReview extends VisionReviewIdentity {
  prompt_version: 'bottle-independent-vision-v1';
  classification: VisionClassification;
}

export interface VisionJudgeReview extends VisionReviewIdentity {
  prompt_version: 'bottle-vision-judge-a-v1';
  image_id: string;
  analysis_status: 'COMPLETED' | 'ANALYSIS_FAILED';
  judge_verdict: 'OK' | 'NG' | 'REINSPECT' | null;
  judge_rationale: string;
  defect_locations: string[];
}

export type VisionReview = LegacyVisionReview | VisionJudgeReview;

export interface VisionReviewResponse {
  available: boolean;
  review: VisionReview | null;
  capabilities: { enabled: boolean; live_enabled: boolean; analysis_mode: string; reason: string; model_requested: string;
    result_contract?: 'VISION_JUDGE_A_V1'; consent_policy?: 'PER_REQUEST_CROP_V1' };
}
