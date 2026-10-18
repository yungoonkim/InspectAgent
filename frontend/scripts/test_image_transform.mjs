// Verification script for ImageView transform math
// Corresponds to Test 1 through Test 12 in VisionInsight Day 7 Step 3.1

import assert from 'node:assert';
import {
  viewportToImagePixel,
  computeWheelTransform,
  computeButtonTransform,
} from '../src/utils/imageTransform.ts';

console.log('--- Starting Image Transform Unit Tests ---');

// Test 1: Registered Static Image Pointer Zoom In
// Conditions: Viewport 600x600, Image 900x900, Zoom 100%, Pan (0,0), Pointer (420, 250)
{
  const current = { zoom: 1.0, pan: { x: 0, y: 0 } };
  const targetW = 900;
  const targetH = 900;
  const pointerX = 420;
  const pointerY = 250;

  // Pixel below pointer before zoom
  const before = viewportToImagePixel(pointerX, pointerY, targetW, targetH, current.zoom, current.pan);
  assert.strictEqual(Math.round(before.imgX), 570, 'Test 1: before imgX must be 570');
  assert.strictEqual(Math.round(before.imgY), 400, 'Test 1: before imgY must be 400');
  assert.strictEqual(before.isOverImage, true, 'Test 1: pointer must be over image');

  // Zoom In (deltaY = -100) -> 200%
  const next = computeWheelTransform({
    currentTransform: current,
    deltaY: -100,
    pointerX,
    pointerY,
    targetW,
    targetH,
  });

  assert.strictEqual(next.zoom, 2.0, 'Test 1: next zoom must be 2.0 (200%)');
  assert.strictEqual(next.pan.x, -120, 'Test 1: next pan.x must be -120');
  assert.strictEqual(next.pan.y, 50, 'Test 1: next pan.y must be 50');

  // Pixel below pointer after zoom must remain identical (570, 400)
  const after = viewportToImagePixel(pointerX, pointerY, targetW, targetH, next.zoom, next.pan);
  assert.strictEqual(Math.round(after.imgX), 570, 'Test 1: after imgX must remain 570');
  assert.strictEqual(Math.round(after.imgY), 400, 'Test 1: after imgY must remain 400');
  console.log('✓ Test 1 Passed: Pointer zoom in anchors exactly to pixel (570, 400), pan = (-120, 50)');
}

// Test 2: Continuous Zoom In (100% -> 200% -> 400% -> 800% -> 1600% -> 3200% -> 4000%)
{
  let current = { zoom: 1.0, pan: { x: 0, y: 0 } };
  const targetW = 900;
  const targetH = 900;
  const pointerX = 420;
  const pointerY = 250;

  const expectedZooms = [2.0, 4.0, 8.0, 16.0, 32.0, 40.0];
  for (const expectedZoom of expectedZooms) {
    current = computeWheelTransform({
      currentTransform: current,
      deltaY: -100,
      pointerX,
      pointerY,
      targetW,
      targetH,
    });
    assert.strictEqual(current.zoom, expectedZoom, `Test 2: zoom level must step to ${expectedZoom}`);
    const pos = viewportToImagePixel(pointerX, pointerY, targetW, targetH, current.zoom, current.pan);
    assert.strictEqual(Math.round(pos.imgX), 570, `Test 2 at ${expectedZoom}: imgX must be 570`);
    assert.strictEqual(Math.round(pos.imgY), 400, `Test 2 at ${expectedZoom}: imgY must be 400`);
  }
  console.log('✓ Test 2 Passed: Continuous zoom in (100% to 4000%) strictly preserves anchored pixel (570, 400)');
}

// Test 3: Center Directed Zoom Out from High Magnification (3200% -> 1600% -> 800% -> 400% -> 200% -> 100%)
{
  let current = { zoom: 32.0, pan: { x: -3200, y: 1500 } };
  const targetW = 900;
  const targetH = 900;

  let prevPanMagnitude = Math.hypot(current.pan.x, current.pan.y);
  const zoomLevels = [16.0, 8.0, 4.0, 2.0, 1.0];

  for (const expectedZoom of zoomLevels) {
    current = computeWheelTransform({
      currentTransform: current,
      deltaY: 100, // Zoom out
      pointerX: 420, // Should NOT anchor to pointer, but to center!
      pointerY: 250,
      targetW,
      targetH,
    });

    assert.strictEqual(current.zoom, expectedZoom, `Test 3: zoom must decrease to ${expectedZoom}`);
    const panMagnitude = Math.hypot(current.pan.x, current.pan.y);
    assert.ok(panMagnitude <= prevPanMagnitude, `Test 3: pan offset must shrink towards center (prev: ${prevPanMagnitude}, now: ${panMagnitude})`);
    prevPanMagnitude = panMagnitude;
  }
  console.log('✓ Test 3 Passed: Zoom out shrinks pan offset proportionally towards viewport center');
}

// Test 4: Reaching 100% Resets Pan to (0, 0)
{
  const current = { zoom: 2.0, pan: { x: -120, y: 50 } };
  const targetW = 900;
  const targetH = 900;

  const next = computeWheelTransform({
    currentTransform: current,
    deltaY: 100, // Zoom out to 1.0
    pointerX: 100,
    pointerY: 100,
    targetW,
    targetH,
  });

  assert.strictEqual(next.zoom, 1.0, 'Test 4: zoom must be 1.0');
  assert.strictEqual(next.pan.x, 0, 'Test 4: pan.x must be 0 at 100%');
  assert.strictEqual(next.pan.y, 0, 'Test 4: pan.y must be 0 at 100%');
  console.log('✓ Test 4 Passed: 100% reset on zoom out restores pan to (0, 0)');
}

// Test 5: Button Zoom is Centered and Ignores Pointer Position
{
  const current = { zoom: 1.0, pan: { x: 0, y: 0 } };
  const next = computeButtonTransform({
    currentTransform: current,
    targetZoom: 2.0,
  });

  assert.strictEqual(next.zoom, 2.0, 'Test 5: zoom is 2.0');
  assert.strictEqual(next.pan.x, 0, 'Test 5: pan remains (0,0) when zooming from center');

  // Zooming with existing pan scales pan by ratio around center
  const withPan = { zoom: 2.0, pan: { x: 100, y: -50 } };
  const nextWithPan = computeButtonTransform({
    currentTransform: withPan,
    targetZoom: 4.0,
  });
  assert.strictEqual(nextWithPan.zoom, 4.0, 'Test 5: zoom is 4.0');
  assert.strictEqual(nextWithPan.pan.x, 200, 'Test 5: pan.x scaled by 2x');
  assert.strictEqual(nextWithPan.pan.y, -100, 'Test 5: pan.y scaled by 2x');
  console.log('✓ Test 5 Passed: Toolbar button zoom scales purely around viewport center');
}

// Test 6: Capture Crop (279x272) Pointer Zoom In on Real Pixel
{
  const current = { zoom: 1.0, pan: { x: 0, y: 0 } };
  const targetW = 279;
  const targetH = 272;

  // Origin for 279x272 at 1.0: (600 - 279)/2 = 160.5, (600 - 272)/2 = 164
  // Let pointer be at (200, 200), which is inside the image
  const pointerX = 200;
  const pointerY = 200;

  const before = viewportToImagePixel(pointerX, pointerY, targetW, targetH, current.zoom, current.pan);
  assert.strictEqual(before.isOverImage, true, 'Test 6: (200, 200) is inside 279x272 crop');

  const next = computeWheelTransform({
    currentTransform: current,
    deltaY: -100,
    pointerX,
    pointerY,
    targetW,
    targetH,
  });

  assert.strictEqual(next.zoom, 2.0, 'Test 6: zoom must be 2.0');
  const after = viewportToImagePixel(pointerX, pointerY, targetW, targetH, next.zoom, next.pan);
  assert.strictEqual(Math.round(after.imgX), Math.round(before.imgX), 'Test 6: imgX preserved on crop');
  assert.strictEqual(Math.round(after.imgY), Math.round(before.imgY), 'Test 6: imgY preserved on crop');
  console.log('✓ Test 6 Passed: Capture ROI Crop preserves local pixel coordinate under pointer');
}

// Test 7: Pointer Over Black Padding around Crop -> Center Zoom Fallback
{
  const current = { zoom: 1.0, pan: { x: 0, y: 0 } };
  const targetW = 279;
  const targetH = 272;

  // Pointer at (50, 50) is in black padding (image starts at x=160.5, y=164)
  const pointerX = 50;
  const pointerY = 50;

  const before = viewportToImagePixel(pointerX, pointerY, targetW, targetH, current.zoom, current.pan);
  assert.strictEqual(before.isOverImage, false, 'Test 7: (50, 50) is in black padding');

  const next = computeWheelTransform({
    currentTransform: current,
    deltaY: -100,
    pointerX,
    pointerY,
    targetW,
    targetH,
  });

  assert.strictEqual(next.zoom, 2.0, 'Test 7: zoom is 2.0');
  // Fallback to center zoom: pan should remain (0,0) when zooming from (0,0) center
  assert.strictEqual(next.pan.x, 0, 'Test 7: pan.x remains 0 (no jump towards padding)');
  assert.strictEqual(next.pan.y, 0, 'Test 7: pan.y remains 0 (no jump towards padding)');
  console.log('✓ Test 7 Passed: Padding zoom falls back safely to viewport center without coordinate glitch');
}

// Test 10: Boundary Clamping at 100% and 4000%
{
  const atMax = { zoom: 40.0, pan: { x: 100, y: -100 } };
  const nextMax = computeWheelTransform({
    currentTransform: atMax,
    deltaY: -100, // Zoom in beyond max
    pointerX: 300,
    pointerY: 300,
    targetW: 900,
    targetH: 900,
  });
  assert.strictEqual(nextMax.zoom, 40.0, 'Test 10: zoom stays at 40.0');
  assert.strictEqual(nextMax.pan.x, 100, 'Test 10: pan.x unchanged');
  assert.strictEqual(nextMax.pan.y, -100, 'Test 10: pan.y unchanged');

  const atMin = { zoom: 1.0, pan: { x: 0, y: 0 } };
  const nextMin = computeWheelTransform({
    currentTransform: atMin,
    deltaY: 100, // Zoom out beyond min
    pointerX: 300,
    pointerY: 300,
    targetW: 900,
    targetH: 900,
  });
  assert.strictEqual(nextMin.zoom, 1.0, 'Test 10: zoom stays at 1.0');
  assert.strictEqual(nextMin.pan.x, 0, 'Test 10: pan.x stays at 0');
  assert.strictEqual(nextMin.pan.y, 0, 'Test 10: pan.y stays at 0');
  console.log('✓ Test 10 Passed: Boundary zoom clamping strictly prevents drift or jump at 100% and 4000%');
}

console.log('--- ALL IMAGE TRANSFORM UNIT TESTS PASSED (100%) ---');
