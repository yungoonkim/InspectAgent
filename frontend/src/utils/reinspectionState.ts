import type { ReinspectionGroup } from '../types/reinspection';

export const MANUAL_DEFAULT = 'HOLD' as const;

export function isJudgeAssisted(group: ReinspectionGroup | null): boolean {
  return group?.workflow_policy === 'judge-assisted-v1';
}

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
  if (isJudgeAssisted(state.group)) {
    const group = state.group!;
    const next = group.status === 'INSPECTION_FAILED' ? '1차 검사 실패 · 새 Capture로 기술적 복구'
      : group.status === 'RECOVERY_REQUIRED' ? '저장 확정 미확인 · 검사 및 수동 확인 차단'
      : group.status === 'COMPLETED' ? '1차 판정 유지 · 추가 확인 필수 아님'
      : group.status === 'MANUAL_REVIEWED' ? '작업자 확인 저장 완료 · 1차 판정 불변'
      : '2차 Judge 선택 · 3차 작업자 확인';
    return `${group.group_id} · 1차 검사 ${group.attempt_count}건 · ${group.status} · ${next}`;
  }
  if (state.group?.workflow_policy !== undefined) return '지원하지 않는 검사 정책 · 서버 상태 확인 필요';
  if (state.group) return `${state.group.group_id} · 레거시 검사 ${state.group.attempt_count} / 3 · 남은 ${state.group.remaining_attempts}회 · ${state.group.status}`;
  if (!state.hasCrop) return '새 Grab ROI Crop 대기';
  return state.ready ? '1차 PatchCore 검사 준비 · 신규 정책은 서버에서 확정' : '최초 검사 입력·모드 확인 필요';
}

export function canUseCapture(group: ReinspectionGroup | null, captureId: string | undefined, confirmed: boolean): boolean {
  if (!captureId) return false;
  if (!group) return true;
  const used = [...group.attempts, ...group.failed_attempts].some(attempt => attempt.input_provenance.capture_id === captureId);
  if (isJudgeAssisted(group)) return !used && group.status === 'INSPECTION_FAILED'
    && group.attempt_count === 0 && group.attempts.length === 0 && group.current_inspection_id === null;
  if (group.workflow_policy !== undefined) return false;
  return confirmed && group.status === 'RETRY_ALLOWED' && group.attempt_count < 3
    && group.remaining_attempts !== null && group.remaining_attempts > 0
    && !used;
}
