import assert from 'node:assert/strict';
import test from 'node:test';
import { canUseCapture, MANUAL_DEFAULT } from '../src/utils/reinspectionState.ts';

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
