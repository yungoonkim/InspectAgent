import type { CropData } from '../types/roi';
import type { ReinspectionGroup } from '../types/reinspection';
import type { CaptureMetadata } from '../types/video';

export const GROUP_HINT_KEY = 'visioninsight.manual-reinspection-group';
export const PENDING_CAPTURE_HINT_KEY = 'visioninsight.manual-reinspection-pending-capture';

export type RecoveryProblem = { kind: 'GROUP_NOT_FOUND' | 'CAPTURE_OR_SESSION' | 'CONFLICT' | 'SERVER' | 'UNKNOWN'; message: string };

export function recoveryProblem(error: unknown): RecoveryProblem {
  const failure = error as { status?: number; data?: { detail?: { error_code?: string } } } | null;
  const status = failure?.status;
  const code = failure?.data?.detail?.error_code;
  if (status === 404 && code === 'REINSPECTION_GROUP_NOT_FOUND') {
    return { kind: 'GROUP_NOT_FOUND', message: 'HTTP 404 · 이전 그룹이 없거나 현재 세션에서 접근할 수 없습니다. 기록은 삭제하지 않습니다. 새 제품이면 새 Capture로 [새 제품 검사 시작]을 선택하세요. 같은 제품이면 기존 그룹 접근 복구가 필요합니다.' };
  }
  if (status === 401 || status === 403 || (status === 404 && code === 'CAPTURE_NOT_FOUND')) {
    return { kind: 'CAPTURE_OR_SESSION', message: `HTTP ${status} · Capture 또는 세션 접근을 확인할 수 없습니다. 새 Grab 후 저장 그룹을 다시 조회하세요. 자동 검사나 그룹 초기화는 하지 않습니다.` };
  }
  if (status === 409) return { kind: 'CONFLICT', message: 'HTTP 409 · 그룹 처리 충돌입니다. 검사하지 말고 저장 그룹을 다시 조회하세요.' };
  if (typeof status === 'number' && status >= 500) return { kind: 'SERVER', message: `HTTP ${status} · 서버 조회 오류입니다. 검사 차단을 유지합니다. 서버 상태 확인 후 다시 조회하세요.` };
  return { kind: 'UNKNOWN', message: '그룹 또는 Capture 확인 실패 · 검사 차단을 유지합니다. 연결과 저장 그룹을 다시 확인하세요.' };
}

export function canPrepareNewProduct(blocked: boolean, problem: RecoveryProblem | null): boolean {
  return !blocked || problem?.kind === 'GROUP_NOT_FOUND' || problem?.kind === 'CAPTURE_OR_SESSION';
}

export function clearWorkflowHints(storage: Pick<Storage, 'removeItem'>): void {
  storage.removeItem(GROUP_HINT_KEY);
  storage.removeItem(PENDING_CAPTURE_HINT_KEY);
}

export async function prepareNewProductCapture(crop: CropData, confirmed: boolean, lookup: {
  capture: (identifier: string) => Promise<CaptureMetadata>;
  group: (identifier: string) => Promise<ReinspectionGroup>;
}): Promise<ReinspectionGroup | null> {
  if (!confirmed) throw new Error('NEW_PRODUCT_CONFIRMATION_REQUIRED');
  return getVerifiedCaptureGroup(crop, lookup);
}

export async function getVerifiedCaptureGroup(crop: CropData, lookup: {
  capture: (identifier: string) => Promise<CaptureMetadata>;
  group: (identifier: string) => Promise<ReinspectionGroup>;
}): Promise<ReinspectionGroup | null> {
  const metadata = await lookup.capture(crop.captureId);
  const roi = crop.roi;
  if (metadata.capture_id !== crop.captureId || metadata.video_id !== crop.videoId
    || metadata.source_revision !== crop.sourceRevision || metadata.frame_index !== crop.frameIndex
    || metadata.status !== 'CAPTURED' || !Number.isInteger(metadata.width) || !Number.isInteger(metadata.height)
    || ![roi.x, roi.y, roi.width, roi.height].every(Number.isInteger)
    || roi.x < 0 || roi.y < 0 || roi.width <= 0 || roi.height <= 0
    || roi.x + roi.width > metadata.width || roi.y + roi.height > metadata.height
    || crop.width !== roi.width || crop.height !== roi.height) throw new Error('CAPTURE_SOURCE_MISMATCH');
  try {
    const group = await lookup.group(crop.captureId);
    if (group.status !== 'RECOVERY_REQUIRED'
      && ![...group.attempts, ...group.failed_attempts].some(attempt => attempt.input_provenance.capture_id === crop.captureId)) {
      throw new Error('REINSPECTION_GROUP_CAPTURE_MISMATCH');
    }
    return group;
  } catch (error) {
    if (recoveryProblem(error).kind !== 'GROUP_NOT_FOUND') throw error;
    return null;
  }
}

export async function restoreCurrentCaptureWorkflow(crop: CropData, currentGroup: ReinspectionGroup | null,
  hints: { groupId: string | null; pendingCaptureId: string | null }, lookup: {
    capture: (identifier: string) => Promise<CaptureMetadata>;
    group: (identifier: string) => Promise<ReinspectionGroup>;
    savedGroup: (identifier: string) => Promise<ReinspectionGroup>;
  }): Promise<{ group: ReinspectionGroup | null; needsNewProductConfirmation: boolean }> {
  const captureGroup = await getVerifiedCaptureGroup(crop, lookup);
  if (captureGroup) return { group: captureGroup, needsNewProductConfirmation: false };
  const identifier = currentGroup?.group_id ?? hints.groupId;
  if (identifier) {
    try {
      return { group: await lookup.savedGroup(identifier), needsNewProductConfirmation: false };
    } catch (error) {
      if (recoveryProblem(error).kind !== 'GROUP_NOT_FOUND') throw error;
      if (currentGroup) throw error;
    }
  }
  if (hints.pendingCaptureId === crop.captureId) throw new Error('PENDING_CAPTURE_RESULT_UNRESOLVED');
  return { group: null, needsNewProductConfirmation: !!(identifier || hints.pendingCaptureId) };
}
