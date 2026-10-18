import assert from 'node:assert/strict';
import { calculateViewportMapping, screenToImageCoords, imageToScreenRect, clampRoiRect,
  computeGrayValue, computeRoiCenter } from '../src/utils/coordinateTransforms.ts';
import test from 'node:test';
import {
  isAnomalyMapCompatible,
  isFixtureInspection,
  isInspectionImageCurrent,
  startInspectionHeatmapLoad,
} from '../src/utils/step4ImageState.ts';
import {
  computeButtonTransform,
  computeWheelTransform,
  imagePixelToViewport,
  viewportToImagePixel,
} from '../src/utils/imageTransform.ts';

const inspection = {
  inspection_id: 'INSP-SYNTHETIC-A',
  image_id: 'IMG-SYNTHETIC-A',
  provenance: 'STORED_RESULT',
};
const metadata = {
  schema_version: '1.0',
  inspection_id: inspection.inspection_id,
  image_id: inspection.image_id,
  model_name: 'SYNTHETIC_TEST_ONLY',
  anomaly_score: null,
  decision_threshold: null,
  original_image_width: 12,
  original_image_height: 8,
  anomaly_map_width: 3,
  anomaly_map_height: 2,
  localization_available: true,
  available: true,
};
const source = { inspectionId: inspection.inspection_id, imageId: inspection.image_id, width: 12, height: 8 };
const overlayDimensions = { width: 12, height: 8 };

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function settleCallbacks() {
  await new Promise((resolve) => setImmediate(resolve));
}

function createLoadHarness(target = inspection) {
  const response = deferred();
  const images = [];
  const available = [];
  const requests = [];
  let unavailable = 0;
  const cancel = startInspectionHeatmapLoad(target, {
    getMetadata: (inspectionId) => {
      requests.push(inspectionId);
      return response.promise;
    },
    getOverlayUrl: (inspectionId) => `/synthetic/${encodeURIComponent(inspectionId)}/overlay.png`,
    createImage: () => {
      const image = { naturalWidth: 12, naturalHeight: 8, onload: null, onerror: null, src: '', crossOrigin: null };
      images.push(image);
      return image;
    },
    onAvailable: (resultMetadata, imageElement) => available.push({ metadata: resultMetadata, imageElement }),
    onUnavailable: () => { unavailable++; },
  });
  return { response, images, available, requests, cancel, unavailable: () => unavailable };
}

test('a pending inspection cannot reuse the previous static image before effect cleanup', () => {
  assert.equal(isInspectionImageCurrent(inspection, source), true);
  assert.equal(isInspectionImageCurrent({ ...inspection, inspection_id: 'INSP-SYNTHETIC-B' }, source), false);
  assert.equal(isInspectionImageCurrent({ ...inspection, image_id: 'IMG-SYNTHETIC-B' }, source), false);
  assert.equal(isInspectionImageCurrent(null, source), false);
  assert.equal(isInspectionImageCurrent(inspection, null), false);
});

test('valid metadata accepts original-size PNG even when model map resolution differs', () => {
  assert.equal(isAnomalyMapCompatible(inspection, metadata, source, overlayDimensions), true);
  assert.equal(isAnomalyMapCompatible(inspection, metadata, source, { width: 3, height: 2 }), false);
});

test('metadata from another inspection or image is rejected', () => {
  assert.equal(isAnomalyMapCompatible(inspection, { ...metadata, inspection_id: 'INSP-SYNTHETIC-B' }), false);
  assert.equal(isAnomalyMapCompatible(inspection, { ...metadata, image_id: 'IMG-SYNTHETIC-B' }), false);
  assert.equal(isAnomalyMapCompatible(null, metadata), false);
  assert.equal(isAnomalyMapCompatible(inspection, null), false);
});

test('both source dimensions and both decoded PNG dimensions must match metadata', () => {
  for (const dimensions of [{ width: 13, height: 8 }, { width: 12, height: 9 }, { width: 0, height: 8 }]) {
    assert.equal(isAnomalyMapCompatible(inspection, metadata, dimensions, overlayDimensions), false);
    assert.equal(isAnomalyMapCompatible(inspection, metadata, source, dimensions), false);
  }
});

test('invalid dimensions and unavailable localization are rejected', () => {
  for (const dimension of [0, -1, 0.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, '12', undefined]) {
    for (const field of ['original_image_width', 'original_image_height', 'anomaly_map_width', 'anomaly_map_height']) {
      assert.equal(isAnomalyMapCompatible(inspection, { ...metadata, [field]: dimension }), false);
    }
  }
  assert.equal(isAnomalyMapCompatible(inspection, { ...metadata, available: false }), false);
  assert.equal(isAnomalyMapCompatible(inspection, { ...metadata, localization_available: false }), false);
  assert.equal(isAnomalyMapCompatible(inspection, { ...metadata, localization_available: 'true' }), false);
});

test('known mock NG ID and recorded fixture provenance always prohibit a heatmap', () => {
  for (const target of [
    { ...inspection, inspection_id: 'INSP-001391', provenance: 'LIVE_INSPECTION' },
    { ...inspection, provenance: 'RECORDED_TEST_FIXTURE' },
  ]) {
    assert.equal(isFixtureInspection(target), true);
    assert.equal(isAnomalyMapCompatible(target, { ...metadata, inspection_id: target.inspection_id }), false);
    const harness = createLoadHarness(target);
    assert.deepEqual(harness.requests, []);
    assert.deepEqual(harness.images, []);
    assert.equal(harness.unavailable(), 1);
    harness.cancel();
  }
  assert.equal(isFixtureInspection(inspection), false);
});

test('cancelled metadata success cannot create an overlay or update availability', async () => {
  const harness = createLoadHarness();
  harness.cancel();
  harness.response.resolve(metadata);
  await settleCallbacks();
  assert.deepEqual(harness.images, []);
  assert.deepEqual(harness.available, []);
  assert.equal(harness.unavailable(), 0);
});

test('cancelled metadata failure cannot replace the current status', async () => {
  const harness = createLoadHarness();
  harness.cancel();
  harness.response.reject(new Error('synthetic delayed error'));
  await settleCallbacks();
  assert.deepEqual(harness.available, []);
  assert.equal(harness.unavailable(), 0);
});

test('late PNG onload and onerror callbacks after cancellation do nothing', async () => {
  const harness = createLoadHarness();
  harness.response.resolve(metadata);
  await settleCallbacks();
  assert.equal(harness.images.length, 1);
  const lateOnload = harness.images[0].onload;
  const lateOnerror = harness.images[0].onerror;
  harness.cancel();
  lateOnload();
  lateOnerror();
  assert.deepEqual(harness.available, []);
  assert.equal(harness.unavailable(), 0);
});

test('invalid metadata never requests a PNG', async () => {
  const harness = createLoadHarness();
  harness.response.resolve({ ...metadata, image_id: 'IMG-SYNTHETIC-B' });
  await settleCallbacks();
  assert.deepEqual(harness.images, []);
  assert.equal(harness.unavailable(), 1);
});

test('valid metadata and PNG publish availability together', async () => {
  const harness = createLoadHarness();
  harness.response.resolve(metadata);
  await settleCallbacks();
  assert.deepEqual(harness.available, []);
  assert.equal(harness.images[0].crossOrigin, 'anonymous');
  assert.equal(harness.images[0].src, '/synthetic/INSP-SYNTHETIC-A/overlay.png');
  harness.images[0].onload();
  assert.deepEqual(harness.available, [{ metadata, imageElement: harness.images[0] }]);
  assert.equal(harness.unavailable(), 0);
  harness.cancel();
});

test('a decoded PNG of the wrong source size is never published', async () => {
  const harness = createLoadHarness();
  harness.response.resolve(metadata);
  await settleCallbacks();
  harness.images[0].naturalWidth = 3;
  harness.images[0].naturalHeight = 2;
  harness.images[0].onload();
  assert.deepEqual(harness.available, []);
  assert.equal(harness.unavailable(), 1);
});

test('current metadata and PNG errors report unavailability', async () => {
  const metadataFailure = createLoadHarness();
  metadataFailure.response.reject(new Error('synthetic missing sidecar'));
  await settleCallbacks();
  assert.equal(metadataFailure.unavailable(), 1);
  const imageFailure = createLoadHarness();
  imageFailure.response.resolve(metadata);
  await settleCallbacks();
  imageFailure.images[0].onerror();
  assert.deepEqual(imageFailure.available, []);
  assert.equal(imageFailure.unavailable(), 1);
});

test('old metadata and an old heatmap selection fail identity checks on a new render', () => {
  const nextInspection = { ...inspection, inspection_id: 'INSP-SYNTHETIC-B', image_id: 'IMG-SYNTHETIC-B' };
  assert.equal(isInspectionImageCurrent(nextInspection, source), false);
  assert.equal(isAnomalyMapCompatible(nextInspection, metadata, source, overlayDimensions), false);
  assert.equal(isInspectionImageCurrent(nextInspection, {
    inspectionId: inspection.inspection_id,
    imageId: inspection.image_id,
  }), false);
});

test('a newer heatmap remains available after older metadata and PNG callbacks arrive', async () => {
  const pendingMetadata = createLoadHarness();
  const pendingImage = createLoadHarness();
  pendingImage.response.resolve(metadata);
  await settleCallbacks();
  const nextInspection = { ...inspection, inspection_id: 'INSP-SYNTHETIC-B', image_id: 'IMG-SYNTHETIC-B' };
  const current = createLoadHarness(nextInspection);
  pendingMetadata.cancel();
  pendingImage.cancel();
  current.response.resolve({ ...metadata, inspection_id: nextInspection.inspection_id, image_id: nextInspection.image_id });
  await settleCallbacks();
  current.images[0].onload();
  pendingMetadata.response.resolve(metadata);
  pendingImage.images[0].onload();
  pendingImage.images[0].onerror();
  await settleCallbacks();
  assert.equal(current.available.length, 1);
  assert.deepEqual(pendingMetadata.available, []);
  assert.deepEqual(pendingImage.available, []);
  assert.equal(pendingImage.unavailable(), 0);
});

test('real transform helpers preserve source coordinates through zoom and pan', () => {
  const initial = { zoom: 1, pan: { x: 0, y: 0 } };
  const before = viewportToImagePixel(420, 250, 900, 900, initial.zoom, initial.pan);
  const next = computeWheelTransform({
    currentTransform: initial, deltaY: -100, pointerX: 420, pointerY: 250, targetW: 900, targetH: 900,
  });
  const after = viewportToImagePixel(420, 250, 900, 900, next.zoom, next.pan);
  assert.deepEqual(after, before);
  assert.deepEqual(imagePixelToViewport(after.imgX, after.imgY, 900, 900, next.zoom, next.pan), { x: 420, y: 250 });
  assert.deepEqual(computeButtonTransform({ currentTransform: next, targetZoom: 1 }), initial);
});

test('production ROI mapping round-trips through letterbox and pillarbox viewports', () => {
  const roi = { x: 750, y: 110, width: 280, height: 310 };
  for (const dimensions of [[600, 600], [1000, 200]]) {
    const mapping = calculateViewportMapping(...dimensions, 1920, 480);
    const rectangle = imageToScreenRect(roi, mapping);
    assert.deepEqual(screenToImageCoords(rectangle.left, rectangle.top, mapping), { x: 750, y: 110 });
    assert.deepEqual(screenToImageCoords(rectangle.left + rectangle.width, rectangle.top + rectangle.height, mapping), { x: 1030, y: 420 });
  }
});

test('production ROI clamp preserves bounds and half-open right/bottom edges', () => {
  assert.deepEqual(clampRoiRect({ x: -1, y: -3, width: 280, height: 310 }), { x: 0, y: 0, width: 280, height: 310 });
  assert.deepEqual(clampRoiRect({ x: 1910, y: 470, width: 80, height: 60 }), { x: 1840, y: 420, width: 80, height: 60 });
  assert.deepEqual(computeRoiCenter({ x: 687, y: 115, width: 286, height: 289 }), { centerX: 830, centerY: 259.5 });
});

test('production GV reads source channels rather than interpolated overlay colors', () => {
  assert.equal(computeGrayValue(20, 40, 60), 36);
  assert.equal(computeGrayValue(255, 0, 0), 76);
  assert.equal(computeGrayValue(0, 255, 0), 150);
  assert.equal(computeGrayValue(0, 0, 255), 29);
  assert.equal(computeGrayValue(0, 0, 0), 0);
  assert.equal(computeGrayValue(255, 255, 255), 255);
});
