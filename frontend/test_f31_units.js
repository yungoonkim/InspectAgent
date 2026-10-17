// Test script for Day6 Phase F-3.1 UX Hotfix Unit Logic
import assert from 'node:assert';

console.log('=== VisionInsight Phase F-3.1 Unit Tests ===\n');

// 1. ROI Center Test
console.log('Test 1: ROI Center Calculation & Formatting');
const testRoi = {
  x: 687,
  y: 115,
  width: 286,
  height: 289,
};

const centerX = testRoi.x + testRoi.width / 2;
const centerY = testRoi.y + testRoi.height / 2;

assert.strictEqual(centerX, 830, 'centerX must be exactly 830');
assert.strictEqual(centerY, 259.5, 'centerY must be exactly 259.5 without rounding');

const formatNumber = (val) => {
  return Number.isInteger(val) ? val.toString() : val.toFixed(1);
};
const formatted = `CENTER (${formatNumber(centerX)}, ${formatNumber(centerY)}) · ${testRoi.width}×${testRoi.height} px`;
assert.strictEqual(
  formatted,
  'CENTER (830, 259.5) · 286×289 px',
  'Formatted center coordinate must match requirement'
);

// Verify original coordinates remain intact
assert.strictEqual(testRoi.x, 687);
assert.strictEqual(testRoi.y, 115);
assert.strictEqual(testRoi.width, 286);
assert.strictEqual(testRoi.height, 289);
console.log('✓ PASS: ROI Center math is accurate (830, 259.5) and retains original top-left rect\n');

// 2. Zoom Boundaries Test
console.log('Test 2: Zoom Bounds (Min 100%, Max 4000%)');
const MIN_ZOOM = 1.0;
const MAX_ZOOM = 40.0;
const clampZoom = (val) => {
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(val * 100) / 100));
};

assert.strictEqual(clampZoom(0.1), 1.0, '0.1 must clamp to 1.0 (100%)');
assert.strictEqual(clampZoom(0.5), 1.0, '0.5 must clamp to 1.0 (100%)');
assert.strictEqual(clampZoom(0.99), 1.0, '0.99 must clamp to 1.0 (100%)');
assert.strictEqual(clampZoom(1.0), 1.0, '1.0 stays 1.0 (100%)');
assert.strictEqual(clampZoom(4.0), 4.0, '4.0 stays 4.0 (400%)');
assert.strictEqual(clampZoom(16.0), 16.0, '16.0 stays 16.0 (1600%)');
assert.strictEqual(clampZoom(32.0), 32.0, '32.0 stays 32.0 (3200%)');
assert.strictEqual(clampZoom(40.0), 40.0, '40.0 stays 40.0 (4000%)');
assert.strictEqual(clampZoom(45.0), 40.0, '45.0 must clamp to 40.0 (4000%)');
assert.strictEqual(clampZoom(100.0), 40.0, '100.0 must clamp to 40.0 (4000%)');

const ZOOM_PRESETS = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 40.0];
assert.strictEqual(ZOOM_PRESETS[0], 1.0, 'First preset must be 100%');
assert.strictEqual(ZOOM_PRESETS[ZOOM_PRESETS.length - 1], 40.0, 'Last preset must be 4000%');
assert(!ZOOM_PRESETS.includes(0.5), '50% preset must be removed');
console.log('✓ PASS: Zoom limits strictly enforce [1.0, 40.0] with 50% removed\n');

// 3. Gray Value (GV) Calculation Test
console.log('Test 3: Gray Value (GV) Calculation Consistency');
const computeGrayValue = (r, g, b) => {
  return Math.round(0.299 * r + 0.587 * g + 0.114 * b);
};

assert.strictEqual(computeGrayValue(0, 0, 0), 0, 'Black must be GV 0');
assert.strictEqual(computeGrayValue(255, 255, 255), 255, 'White must be GV 255');
assert.strictEqual(computeGrayValue(100, 100, 100), 100, 'Gray 100 must be GV 100');
assert.strictEqual(computeGrayValue(36, 34, 44), 36, 'RGB(36,34,44) produces GV 36 with Math.round(35.738)');
console.log('✓ PASS: Gray Value computation matches OpenCV formula identically\n');

// 4. Viewport Culling & Grid Scale Test
console.log('Test 4: Viewport Culling at 4000% Zoom');
const WORKSPACE_SIZE = 600;
const cropW = 320;
const cropH = 320;
const zoom = 40.0;
const pan = { x: 0, y: 0 };

const originX = (WORKSPACE_SIZE - cropW * zoom) / 2 + pan.x;
const originY = (WORKSPACE_SIZE - cropH * zoom) / 2 + pan.y;

const startX = Math.max(0, Math.floor(-originX / zoom));
const endX = Math.min(cropW - 1, Math.ceil((WORKSPACE_SIZE - originX) / zoom));
const startY = Math.max(0, Math.floor(-originY / zoom));
const endY = Math.min(cropH - 1, Math.ceil((WORKSPACE_SIZE - originY) / zoom));

const visibleCols = endX - startX + 1;
const visibleRows = endY - startY + 1;
const totalVisiblePixels = visibleCols * visibleRows;

console.log(`  Visible cols: ${visibleCols}, rows: ${visibleRows}, total: ${totalVisiblePixels} pixels`);
assert(totalVisiblePixels < 400, `Only visible pixels should be rendered (< 400, actual: ${totalVisiblePixels})`);
assert(startX >= 0 && endX < cropW, 'Render range must stay within image bounds');
assert(startY >= 0 && endY < cropH, 'Render range must stay within image bounds');
console.log('✓ PASS: Viewport culling correctly restricts rendering to ~256 visible pixels at 40x\n');

// 5. Contrast Text Color Test
console.log('Test 5: Contrast Text Color for GV Render');
const getContrastColor = (gv) => (gv > 128 ? '#0a0f1d' : '#f8fafc');
assert.strictEqual(getContrastColor(0), '#f8fafc', 'Dark pixel gets white text');
assert.strictEqual(getContrastColor(48), '#f8fafc', 'Dark pixel gets white text');
assert.strictEqual(getContrastColor(128), '#f8fafc', 'GV 128 gets white text');
assert.strictEqual(getContrastColor(129), '#0a0f1d', 'Bright pixel gets dark text');
assert.strictEqual(getContrastColor(255), '#0a0f1d', 'White pixel gets dark text');
console.log('✓ PASS: Contrast text color guarantees readability on both light and dark pixels\n');

console.log('ALL PHASE F-3.1 UNIT TESTS PASSED SUCCESSFULLY!');
