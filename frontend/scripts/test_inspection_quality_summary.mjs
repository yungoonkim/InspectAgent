import assert from 'node:assert/strict';
import test from 'node:test';
import { inspectionQualitySummary } from '../src/utils/inspectionQualitySummary.ts';

const inspection = {
  inspection_id: 'INSP-SYNTHETIC-QUALITY', result: 'OK', final_result: 'REINSPECT',
  final_reason_code: 'IMAGE_QUALITY_WARNING', image_quality_status: 'WARNING_LOW_BRIGHTNESS',
  anomaly_score: 31.39, decision_threshold: 34.1442, metrics: { mean: 120.2 },
};

test('existing API mean and model opinion stay separate from server REINSPECT', () => {
  const before = structuredClone(inspection);
  const details = inspectionQualitySummary(inspection);
  assert.equal(details.meanLabel, '120.20');
  assert.equal(details.modelVerdict, 'OK');
  assert.match(details.reason, /저밝기/);
  assert.match(details.criteria, /125\.0/);
  assert.match(details.criteria, /안내값.*API 미제공/);
  assert.deepEqual(inspection, before);
});

test('actual response thresholds take priority over the operational guidance', () => {
  const details = inspectionQualitySummary({ ...inspection, metrics: { mean: 131,
    applied_thresholds: { low_threshold: 126, high_threshold: 151 } } });
  assert.equal(details.criteria, '검사 응답 기준 · 하한 126.0 / 상한 151.0');
  assert.doesNotMatch(details.criteria, /125\.0/);
});

test('zero and threshold equality display measurements without classifying them again', () => {
  assert.equal(inspectionQualitySummary({ ...inspection, metrics: { mean: 0 } }).meanLabel, '0.00');
  const boundary = inspectionQualitySummary({ ...inspection, image_quality_status: 'NORMAL',
    result: 'NG', final_result: 'NG', metrics: { mean: 125 } });
  assert.equal(boundary.meanLabel, '125.00');
  assert.equal(boundary.modelVerdict, 'NG');
  assert.match(boundary.reason, /NORMAL/);
});

test('missing and invalid measurements are not fabricated or coerced to zero', () => {
  for (const mean of [undefined, null, NaN, Infinity, '120.2']) {
    assert.equal(inspectionQualitySummary({ ...inspection, metrics: { mean } }).meanLabel, '— (측정값 없음)');
  }
  assert.equal(inspectionQualitySummary(null).criteria, '—');
  assert.equal(inspectionQualitySummary(null).modelVerdict, '—');
});

test('changing the selected record replaces quality and model information together', () => {
  const details = inspectionQualitySummary({ ...inspection, inspection_id: 'INSP-SYNTHETIC-OTHER',
    result: 'NG', image_quality_status: 'WARNING_HIGH_BRIGHTNESS', metrics: { mean: 170 } });
  assert.equal(details.meanLabel, '170.00');
  assert.equal(details.modelVerdict, 'NG');
  assert.match(details.reason, /고밝기/);
  assert.doesNotMatch(details.reason, /120\.20/);
  assert.match(inspectionQualitySummary({ ...inspection, image_quality_status: 'ERROR' }).reason, /오류/);
});
