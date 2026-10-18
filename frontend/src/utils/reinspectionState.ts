import type { ReinspectionGroup } from '../types/reinspection';

export const MANUAL_DEFAULT = 'HOLD' as const;

export function canUseCapture(group: ReinspectionGroup | null, captureId: string | undefined, confirmed: boolean): boolean {
  if (!captureId) return false;
  if (!group) return true;
  return confirmed && group.status === 'RETRY_ALLOWED' && group.attempt_count < 3 && group.remaining_attempts > 0
    && ![...group.attempts, ...group.failed_attempts].some(attempt => attempt.input_provenance.capture_id === captureId);
}
