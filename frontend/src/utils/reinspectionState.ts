import type { ReinspectionGroup } from '../types/reinspection';

export const MANUAL_DEFAULT = 'HOLD' as const;

export function grabInspectionDisabled(state: {
  enabled: boolean; hasCrop: boolean; busy: boolean; restoring: boolean;
  blocked: boolean; captureAllowed: boolean; completed: boolean; productId: string;
}): boolean {
  return !state.enabled || !state.hasCrop || state.busy || state.restoring || state.blocked
    || !state.captureAllowed || state.completed || !state.productId.trim();
}

export function inspectionProgress(state: {
  group: ReinspectionGroup | null; restoring: boolean; blocked: boolean; hasCrop: boolean; ready: boolean;
}): string {
  if (state.restoring) return '서버 저장 그룹 확인 중 · 검사 대기';
  if (state.blocked) return '그룹/Capture 상태 확인 실패 · 검사 차단';
  if (state.group) return `${state.group.group_id} · 검사 ${state.group.attempt_count} / 3 · 남은 ${state.group.remaining_attempts}회 · ${state.group.status}`;
  if (!state.hasCrop) return '새 Grab ROI Crop 대기';
  return state.ready ? '최초 검사 1 / 3 준비' : '최초 검사 입력·모드 확인 필요';
}

export function canUseCapture(group: ReinspectionGroup | null, captureId: string | undefined, confirmed: boolean): boolean {
  if (!captureId) return false;
  if (!group) return true;
  return confirmed && group.status === 'RETRY_ALLOWED' && group.attempt_count < 3 && group.remaining_attempts > 0
    && ![...group.attempts, ...group.failed_attempts].some(attempt => attempt.input_provenance.capture_id === captureId);
}
