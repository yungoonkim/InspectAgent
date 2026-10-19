export type LiveAnalysisStatus = 'NOT_VERIFIED' | 'RUNNING' | 'FAILED' | 'COMPLETED';

export function liveAnalysisLabel(status: LiveAnalysisStatus): string {
  return {
    NOT_VERIFIED: 'LIVE NOT YET VERIFIED', RUNNING: 'LIVE ANALYSIS RUNNING',
    FAILED: 'LIVE ANALYSIS FAILED', COMPLETED: 'LIVE ANALYSIS COMPLETED',
  }[status];
}

export function agentFailureMessage(code: unknown, status?: number): string {
  if (code === 'AGENT_REPORT_EXISTS') return '기존 보고서를 보존했습니다. 기존 보고서 조회를 이용하세요. 새 유료 분석은 실행되지 않았습니다. (AGENT_REPORT_EXISTS)';
  if (code === 'AGENT_REPORT_STORAGE_FAILED') return 'AI 분석 보고서 저장·조회에 실패했습니다. 완료로 처리하지 않습니다. 자동 재호출하지 말고 서버 저장 상태를 확인하세요. (AGENT_REPORT_STORAGE_FAILED)';
  if (code === 'MISSING_API_KEY') return 'Gemini API Key가 설정되지 않았습니다. 기존 보고서 조회를 이용하세요. (MISSING_API_KEY)';
  if (code === 'GEMINI_TIMEOUT' || code === 'AGENT_TIMEOUT' || code === 'TOOL_TIMEOUT') {
    return `Gemini 진단 제한 시간을 초과했습니다. 자동 재시도하지 않습니다. (${code})`;
  }
  if (code === 'GEMINI_REQUEST_FAILED') {
    return 'Gemini 진단 요청 실패 (GEMINI_REQUEST_FAILED). 원인은 미확정입니다. 서버의 correlation_id, stage, exception_class, http_status, provider_code를 확인하세요.';
  }
  const infrastructure = ['STORAGE_ERROR', 'TOOL_CAPACITY_EXCEEDED', 'INVALID_MODEL_CONFIG', 'AGENT_CONFIG_CHANGED'];
  if (typeof code === 'string' && infrastructure.includes(code)) return `진단 서비스 또는 설정을 확인하세요. (${code})`;
  return `AI 진단 실행 실패. 검증된 보고서가 생성되지 않았습니다.${Number.isInteger(status) ? ` (HTTP ${status})` : ''}`;
}
