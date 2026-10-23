import assert from 'node:assert/strict';
import test from 'node:test';
import { canUseCapture, inspectionProgress, MANUAL_DEFAULT } from '../src/utils/reinspectionState.ts';

const group = { status: 'RETRY_ALLOWED', attempt_count: 1, remaining_attempts: 2,
  attempts: [{ input_provenance: { capture_id: 'CAP-FIRST' } }], failed_attempts: [] };

test('first inspection requires a Capture, not a fabricated default', () => {
  assert.equal(canUseCapture(null, undefined, false), false);
  assert.equal(canUseCapture(null, 'CAP-NEW', false), true);
});
test('same physical product confirmation is explicit and Capture must be new', () => {
  assert.equal(canUseCapture(group, 'CAP-NEW', false), false);
  assert.equal(canUseCapture(group, 'CAP-NEW', true), true);
  assert.equal(canUseCapture(group, 'CAP-FIRST', true), false);
});
test('even failed Capture is not silently reused for another inference', () => {
  assert.equal(canUseCapture({ ...group, failed_attempts: [{ input_provenance: { capture_id: 'CAP-FAILED' } }] }, 'CAP-FAILED', true), false);
});
test('third attempt and terminal/manual/recovery states prohibit further inspection', () => {
  for (const status of ['COMPLETED', 'MANUAL_REVIEW_REQUIRED', 'MANUAL_REVIEWED', 'RECOVERY_REQUIRED']) {
    assert.equal(canUseCapture({ ...group, status }, 'CAP-NEW', true), false);
  }
  assert.equal(canUseCapture({ ...group, attempt_count: 3, remaining_attempts: 0 }, 'CAP-NEW', true), false);
});
test('manual default is HOLD, never automatic operator approval', () => {
  assert.equal(MANUAL_DEFAULT, 'HOLD');
});

test('judge-assisted inspection has no Retry quota and never repeats a completed Capture', () => {
  const assisted = { ...group, group_id: 'RIG-SYNTHETIC', workflow_policy: 'judge-assisted-v1',
    status: 'MANUAL_REVIEW_REQUIRED', max_attempts: null, remaining_attempts: null };
  assert.equal(canUseCapture(assisted, 'CAP-NEW', true), false);
  assert.equal(canUseCapture(assisted, 'CAP-FIRST', true), false);
  const label = inspectionProgress({ group: assisted, restoring: false, blocked: false, hasCrop: true, ready: false });
  assert.match(label, /2차 Judge 선택/);
  assert.doesNotMatch(label, /\/ 3|남은|null/);
  assert.match(inspectionProgress({ group: { ...assisted, status: 'COMPLETED' }, restoring: false, blocked: false, hasCrop: true, ready: false }), /추가 확인 필수 아님/);
  assert.match(inspectionProgress({ group: { ...assisted, status: 'MANUAL_REVIEWED' }, restoring: false, blocked: false, hasCrop: true, ready: false }), /확인 저장 완료/);
  assert.doesNotMatch(inspectionProgress({ group: null, restoring: false, blocked: false, hasCrop: true, ready: true }), /1 \/ 3/);
});

test('only a failed first-stage inspection can recover using another verified Capture', () => {
  const failed = { ...group, workflow_policy: 'judge-assisted-v1', status: 'INSPECTION_FAILED',
    current_inspection_id: null, attempt_count: 0, attempts: [], remaining_attempts: null, max_attempts: null,
    failed_attempts: [{ input_provenance: { capture_id: 'CAP-FAILED' } }] };
  assert.equal(canUseCapture(failed, 'CAP-NEW', false), true);
  assert.equal(canUseCapture(failed, 'CAP-FAILED', false), false);
  assert.equal(canUseCapture({ ...failed, status: 'RECOVERY_REQUIRED' }, 'CAP-NEW', false), false);
  assert.equal(canUseCapture({ ...failed, attempt_count: 1 }, 'CAP-NEW', false), false);
  assert.equal(canUseCapture({ ...failed, workflow_policy: 'UNKNOWN_POLICY' }, 'CAP-NEW', true), false);
});
