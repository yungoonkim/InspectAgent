import assert from 'node:assert/strict';
import test from 'node:test';
import { cropIdentity, isGrabInspectionMatching, GRAB_LIMITATION } from '../src/utils/grabInspectionState.ts';

const crop = { captureId: 'CAP-SYNTHETIC', videoId: 'VID-000001', sourceRevision: 'a'.repeat(64), frameIndex: 120,
  roi: { x: 17, y: 21, width: 160, height: 96 }, width: 160, height: 96 };
const result = { metrics: { input_source: 'LIVEVIEW_GRAB', input_provenance: {
  capture_id: crop.captureId, video_id: crop.videoId, source_revision: crop.sourceRevision, frame_index: crop.frameIndex,
  crop_width: 160, crop_height: 96, roi: crop.roi,
} } };

test('Grab identity includes capture revision frame and the complete half-open ROI', () => {
  assert.equal(cropIdentity(null), '');
  for (const changes of [{ captureId: 'CAP-OTHER' }, { sourceRevision: 'b'.repeat(64) }, { frameIndex: 121 },
    { roi: { ...crop.roi, x: 18 } }, { roi: { ...crop.roi, height: 95 } }]) {
    assert.notEqual(cropIdentity(crop), cropIdentity({ ...crop, ...changes }));
  }
});

test('only an exact server source match can publish a Grab inspection result', () => {
  assert.equal(isGrabInspectionMatching(result, crop), true);
  for (const changes of [{ capture_id: 'CAP-OTHER' }, { video_id: 'VID-OTHER' }, { frame_index: 121 },
    { source_revision: 'b'.repeat(64) }, { crop_width: 161 }, { roi: { ...crop.roi, y: 22 } }]) {
    assert.equal(isGrabInspectionMatching({ metrics: { ...result.metrics,
      input_provenance: { ...result.metrics.input_provenance, ...changes } } }, crop), false);
  }
  assert.equal(isGrabInspectionMatching({ metrics: {} }, crop), false);
});

test('experimental disclaimer explicitly avoids claiming Crop calibration or detection validation', () => {
  assert.ok(GRAB_LIMITATION.includes('실험적'));
  assert.ok(GRAB_LIMITATION.includes('임계값 보정 및 검출 성능은 별도로 검증되지 않았습니다'));
});
