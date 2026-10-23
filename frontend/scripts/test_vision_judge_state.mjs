import assert from 'node:assert/strict';
import test from 'node:test';
import { canRequestVisionReview, judgeOutcome, manualReviewLabel, matchesVisionInput } from '../src/utils/visionReviewState.ts';

const inspection = { inspection_id: 'INSP-001669', image_id: 'IMG-GRAB-' + 'a'.repeat(32), final_result: 'REINSPECT',
  metrics: { input_source: 'LIVEVIEW_GRAB', reinspection: { group_id: 'RIG-MOCK' },
    input_provenance: { capture_id: 'CAP-MOCK', crop_sha256: 'a'.repeat(64) } } };
const review = { inspection_id: inspection.inspection_id, image_id: inspection.image_id, capture_id: 'CAP-MOCK',
  reinspection_group_id: 'RIG-MOCK', image_sha256: 'a'.repeat(64), prompt_version: 'bottle-vision-judge-a-v1',
  analysis_mode: 'FAKE_TEST', analysis_status: 'COMPLETED', judge_verdict: 'REINSPECT', failure_code: null };

for (const verdict of ['OK', 'NG', 'REINSPECT']) {
  test(`FAKE_TEST Judge ${verdict} remains separate from primary REINSPECT`, () => {
    const value = { ...review, judge_verdict: verdict };
    assert.equal(judgeOutcome(value), verdict);
    assert.equal(matchesVisionInput(value, inspection), true);
    assert.equal(inspection.final_result, 'REINSPECT');
    assert.equal(value.analysis_mode, 'FAKE_TEST');
  });
}

test('old server cannot receive Judge requests even if old Vision was enabled', () => {
  const response = { available: false, review: null, capabilities: { enabled: true, live_enabled: true } };
  assert.equal(canRequestVisionReview(response, true), false);
  response.capabilities.result_contract = 'VISION_JUDGE_A_V1';
  assert.equal(canRequestVisionReview(response, true), false);
  response.capabilities.consent_policy = 'PER_REQUEST_CROP_V1';
  assert.equal(canRequestVisionReview(response, false), false);
  assert.equal(canRequestVisionReview(response, true), true);
  assert.equal(canRequestVisionReview({ ...response, available: true }, true), false);
});

test('failure has no verdict and contradictory response is rejected', () => {
  const failed = { ...review, analysis_status: 'ANALYSIS_FAILED', judge_verdict: null, failure_code: 'VISION_TIMEOUT' };
  assert.equal(judgeOutcome(failed), 'ANALYSIS_FAILED');
  for (const value of [{ ...failed, judge_verdict: 'OK' }, { ...review, judge_verdict: null },
    { ...review, failure_code: 'VISION_TIMEOUT' }, { ...review, judge_verdict: 'UNKNOWN' }]) {
    assert.equal(judgeOutcome(value), 'INVALID');
    assert.equal(matchesVisionInput(value, inspection), false);
  }
});

test('legacy observation categories never become Judge verdicts', () => {
  for (const classification of ['DEFECT_SUSPECTED', 'QUALITY_ISSUE', 'NO_VISIBLE_DEFECT', 'INCONCLUSIVE', 'ANALYSIS_FAILED']) {
    assert.equal(judgeOutcome({ prompt_version: 'bottle-independent-vision-v1', classification }), 'LEGACY_OPINION');
  }
});

test('late or mismatched Judge results fail identity checks', () => {
  for (const change of [{ inspection_id: 'INSP-OTHER' }, { image_id: 'OTHER' }, { capture_id: 'OTHER' },
    { image_sha256: 'b'.repeat(64) }, { reinspection_group_id: 'OTHER' }, { analysis_mode: 'MOCK_LIVE' }]) {
    assert.equal(matchesVisionInput({ ...review, ...change }, inspection), false);
  }
});

test('manual confirmation is a separate server group record, not the Judge verdict', () => {
  const group = { group_id: 'RIG-MOCK', status: 'MANUAL_REVIEWED',
    attempts: [{ inspection_id: inspection.inspection_id }], manual_reviews: [] };
  for (const result of ['HOLD', 'MANUAL_OK', 'MANUAL_NG']) {
    group.manual_reviews = [{ result, timestamp: 'MOCK_TIME' }];
    assert.ok(manualReviewLabel(group, inspection).includes(result));
    assert.equal(inspection.final_result, 'REINSPECT');
  }
  assert.ok(manualReviewLabel({ ...group, group_id: 'OTHER' }, inspection).includes('미조회'));
  assert.ok(manualReviewLabel({ ...group, attempts: [] }, inspection).includes('미조회'));
  assert.ok(manualReviewLabel({ ...group, manual_reviews: [] }, inspection).includes('미실시'));
});

test('one judge-assisted REINSPECT exposes manual confirmation without waiting for Gemini', () => {
  const group = { workflow_policy: 'judge-assisted-v1', group_id: 'RIG-MOCK', status: 'MANUAL_REVIEW_REQUIRED',
    attempts: [{ inspection_id: inspection.inspection_id }], manual_reviews: [] };
  const label = manualReviewLabel(group, inspection);
  assert.match(label, /3차 작업자 확인 가능/);
  assert.doesNotMatch(label, /3회 후/);
  assert.equal(inspection.final_result, 'REINSPECT');
});
