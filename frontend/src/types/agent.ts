/**
 * Gemini Diagnostic Agent protocol and report types matching backend schemas
 */

export interface ObservedFact {
  fact_id: string;
  evidence_id: string;
  source_tool: string;
  source_field: string;
  source_event?: string | null;
  observed_value: string | number | boolean | null;
}

export interface PossibleCause {
  cause_code: string;
  statement: string;
  evidence_refs: string[];
  is_hypothesis?: boolean;
}

export interface RecommendedCheck {
  check_code: string;
  instruction: string;
  evidence_refs: string[];
}

export interface AgentReport {
  analysis_id?: string;
  inspection_id: string;
  analysis_status: 'COMPLETED' | 'FAILED' | string;
  error_code?: string | null;
  overall_summary: string | null;
  inspection_snapshot?: Record<string, any> | null;
  observed_facts: ObservedFact[];
  possible_causes: PossibleCause[];
  recommended_checks: RecommendedCheck[];
  limitations: string[];
  tools_used: string[];
  inspection_result?: string | null;
  final_result?: string | null;
  final_reason_code?: string | null;
  timestamp?: string;
  provenance?: 'STORED_REPORT' | 'RECORDED_TEST_FIXTURE' | 'LIVE_AGENT_ANALYSIS' | 'FAKE_TEST';
}
