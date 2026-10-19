import { test as base, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const preflight = JSON.parse(readFileSync(path.join(process.env.VISION_E2E_OUTPUT, 'preflight.json'), 'utf8'));
const hasSession = preflight.authenticatedSessionProvided;
const test = base.extend({
  safety: [async ({ context, page, browser }, use, info) => {
    const blocked = [];
    const forwarded = [];
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push({ name: error.name }));
    await context.routeWebSocket('**/*', socket => socket.close());
    await context.route('**/*', async route => {
      const request = route.request();
      const url = new URL(request.url());
      const method = request.method();
      const entry = { method, path: url.pathname };
      const local = ['http://localhost:5173', 'http://127.0.0.1:8000'].includes(url.origin);
      const apiPath = url.pathname.replace(/^\/api(?=\/)/, '');
      let reason = null;
      if (!local) reason = 'EXTERNAL_NETWORK';
      else if (!['GET', 'HEAD'].includes(method)) reason = apiPath === '/capture-sessions' ? 'SESSION_BOOTSTRAP_BLOCKED' : 'UNEXPECTED_WRITE';
      else if (/^\/videos\/VID-(?!000003(?:\/|$))/.test(apiPath)) reason = 'NON_TARGET_VIDEO';
      else if (/^\/(?:captures|reinspection-groups|capture-sessions)(?:\/|$)/.test(apiPath)) reason = 'SESSION_TTL_SIDE_EFFECT_GUARD';
      else if (!hasSession && /^\/inspections\/[^/]+\/(?:input-image|anomaly-map|vision-review)(?:\/|$)/.test(apiPath)) {
        const identifier = apiPath.split('/')[2];
        const publicMap = /\/anomaly-map(?:\/|$)/.test(apiPath) && identifier === preflight.publicInspectionId;
        if (!publicMap) reason = 'NO_APPROVED_OWNER_SESSION';
      } else if (/^\/analyze(?:\/|$)/.test(apiPath)) reason = 'LIVE_ANALYSIS_FORBIDDEN';
      if (!reason && (url.pathname.startsWith('/api/') || url.origin === 'http://127.0.0.1:8000')) {
        const allowed = /^\/(?:health|videos(?:\/VID-000003(?:\/stream)?)?|inspections(?:\/images(?:\/IMG-[A-Z0-9-]+\/file)?|\/INSP-\d+(?:\/(?:input-image|agent-report|vision-review|anomaly-map(?:\/overlay\.png)?))?)?)$/;
        if (!allowed.test(apiPath)) reason = 'UNLISTED_API';
      }
      if (reason) { blocked.push({ ...entry, reason }); await route.abort('blockedbyclient'); return; }
      forwarded.push(entry);
      await route.continue();
    });
    await use({ blocked, forwarded, pageErrors });
    if (!page.isClosed()) await page.screenshot({ path: info.outputPath('screen.png'), fullPage: true });
    const evidence = { browser: browser.version(), blocked, forwarded, pageErrors,
      forwardedWrites: forwarded.filter(entry => !['GET', 'HEAD'].includes(entry.method)).length,
      visualReviewRequired: ['Image/Heatmap/Edge pixel alignment and anatomical correctness', 'Favicon small-tab appearance'],
      annotations: info.annotations };
    writeFileSync(info.outputPath('safety.json'), JSON.stringify(evidence, null, 2));
    expect(evidence.forwardedWrites).toBe(0);
    expect(blocked.filter(entry => ['UNEXPECTED_WRITE', 'LIVE_ANALYSIS_FORBIDDEN', 'UNLISTED_API'].includes(entry.reason))).toEqual([]);
    expect(pageErrors).toEqual([]);
  }, { auto: true }],
});

async function selectVideo(page) {
  await page.goto('/');
  const selector = page.getByLabel('LiveView 영상 선택');
  await expect(selector.locator('option[value="VID-000003"]')).toHaveCount(1);
  await selector.selectOption('VID-000003');
  await expect(selector).toHaveValue('VID-000003');
  const video = page.locator('video.video-element');
  await expect(video).toHaveAttribute('src', /\/videos\/VID-000003\/stream$/);
  await expect.poll(() => video.evaluate(element => ({ width: element.videoWidth, height: element.videoHeight,
    duration: element.duration, ready: element.readyState >= 2 }))).toEqual({ width:1920, height:480, duration:16, ready:true });
  await expect(page.locator('.video-overlay-fps')).toHaveText('30.00 FPS · 1920×480');
  await expect(page.locator('.video-wrapper').locator('..').getByText('VID-000003', { exact: true })).toBeVisible();
  return video;
}

async function queryStored(page, identifier) {
  await page.getByRole('tab', { name:'정적 이미지 검사', exact:true }).click();
  await page.getByLabel('검사 ID 조회 입력', { exact:true }).fill(identifier);
  const pending = page.waitForResponse(response => new URL(response.url()).pathname === `/api/inspections/${identifier}`
    && response.request().method() === 'GET');
  await page.getByRole('button', { name:'조회', exact:true }).click();
  const response = await pending;
  expect(response.status()).toBe(200);
  const record = await response.json();
  expect(record.inspection_id).toBe(identifier);
  await expect(page.getByLabel('표시 중 검사 결과')).toContainText(identifier);
  return record;
}

async function loadViewer(page, info, edgeOnly = false) {
  const target = preflight.requestedInspection;
  if (edgeOnly) {
    test.skip(!target || target.source !== 'LIVEVIEW_GRAB', 'Requested saved Grab inspection missing; no substitute data created');
    if (!hasSession) {
      const eligibility = { requestedInspection:target.inspection_id, requestedSource:target.source,
        ownerSessionProvided:false, protectedCropRequested:false, newCaptureCreated:false,
        publicInspection:preflight.publicInspectionId, publicImageLoaded:false, publicEdgeEnabled:null };
      if (preflight.publicInspectionId) {
        const publicRecord = await queryStored(page, preflight.publicInspectionId);
        expect(publicRecord.metrics?.input_source).not.toBe('LIVEVIEW_GRAB');
        await page.locator('.source-mode-selector').getByRole('button').filter({ hasText:'정적 검사 이미지' }).click();
        await expect(page.locator('canvas.precision-canvas')).toBeVisible();
        const edgeButton = page.getByRole('button', { name:/^병 테두리 (ON|OFF)$/ });
        await expect(edgeButton).toBeDisabled();
        eligibility.publicImageLoaded = true;
        eligibility.publicEdgeEnabled = await edgeButton.isEnabled();
        eligibility.publicImageId = publicRecord.image_id;
        eligibility.publicMean = publicRecord.metrics?.mean ?? null;
        await page.screenshot({ path:info.outputPath('public-image-edge-unavailable.png'), fullPage:true });
      }
      writeFileSync(info.outputPath('edge-gv-eligibility.json'), JSON.stringify(eligibility, null, 2));
      info.annotations.push({ type:'access-limitation', description:'Public static image is real and accessible, but production Edge is Grab-only. No source relabeling, cookie extraction, synthetic Capture or private image injection.' });
      test.skip(true, 'No approved owner session for stored Grab; accessible static image has Edge disabled by production design. Requires a legitimate same-session Crop, not an ownership bypass.');
    }
  }
  const identifier = hasSession && target ? target.inspection_id : preflight.publicInspectionId;
  if (!identifier && preflight.publicDataErrors.length) throw new Error(`Stored map API failed: ${JSON.stringify(preflight.publicDataErrors)}`);
  test.skip(!identifier, 'No publicly accessible real stored inspection is available in this isolated Chrome session');
  const imageResponse = hasSession && target?.inspection_id === identifier && target.source === 'LIVEVIEW_GRAB'
    ? page.waitForResponse(response => new URL(response.url()).pathname === `/api/inspections/${identifier}/input-image`) : null;
  const record = await queryStored(page, identifier);
  if (imageResponse) {
    const response = await imageResponse;
    test.skip([401, 403, 404].includes(response.status()), `Stored Crop owner access unavailable: HTTP ${response.status()}; no session recovery or new Capture`);
    expect(response.status()).toBe(200);
  }
  if (identifier !== target?.inspection_id) info.annotations.push({ type:'data-source', description:`Public stored inspection ${identifier}; not ${preflight.requestedId}` });
  const source = page.locator('.source-mode-selector').getByRole('button').filter({ hasText: record.metrics?.input_source === 'LIVEVIEW_GRAB' ? 'Grab 검사 이미지' : '정적 검사 이미지' });
  await source.click();
  await expect(page.locator('canvas.precision-canvas')).toBeVisible();
  await expect(page.locator('.verdict-overlay-card')).toContainText(identifier);
  return record;
}

async function pan(page) {
  const canvas = page.locator('canvas.precision-canvas');
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 36, box.y + box.height / 2 + 24, { steps:4 });
  await page.mouse.up();
  return { canvas, box };
}

test.beforeEach(async ({ page }) => { await selectVideo(page); });

test('TC-01 VID-000003 actual playback, Pause, Seek and Frame controls', async ({ page }, info) => {
  const video = page.locator('video.video-element');
  const snapshots = [];
  const verifyFrame = async (frame, step) => {
    await expect.poll(() => video.evaluate(element => element.seeking)).toBe(false);
    await expect.poll(() => video.evaluate(element => Math.floor(element.currentTime * 30))).toBe(frame);
    await expect(page.locator('.scrubber-row')).toContainText(`[Frame ${frame} / 479]`);
    const time = await video.evaluate(element => element.currentTime);
    expect(time).toBeGreaterThanOrEqual(frame / 30);
    expect(time).toBeLessThan((frame + 1) / 30);
    snapshots.push({ step, frame, time, ui:await page.locator('.scrubber-row').innerText() });
    writeFileSync(info.outputPath('frame-roundtrip.json'), JSON.stringify({ video_id:'VID-000003', snapshots }, null, 2));
  };
  await video.evaluate(element => {
    window.frameEvents = [];
    for (const name of ['seeking','seeked','timeupdate','play','pause','ended']) element.addEventListener(name, () => {
      window.frameEvents.push({ event:name, time:element.currentTime, paused:element.paused, seeking:element.seeking });
    });
  });
  try {
  await expect(page.locator('link[rel="icon"]')).toHaveAttribute('href', '/visioninsight.svg');
  if (await video.evaluate(element => element.paused)) await page.getByRole('button', { name:'Play', exact:true }).click();
  const initial = await video.evaluate(element => element.currentTime);
  await expect.poll(() => video.evaluate(element => element.currentTime)).toBeGreaterThan(initial);
  await page.getByRole('button', { name:'Pause', exact:true }).click();
  await expect.poll(() => video.evaluate(element => element.paused)).toBe(true);
  await page.getByTitle('비디오 위치 탐색 (Seek)', { exact:true }).fill('4');
  await verifyFrame(120, 'seek-4s');
  await page.getByRole('button', { name:'+1 Frame', exact:true }).click();
  await verifyFrame(121, 'plus-one');
  await page.getByRole('button', { name:'-1 Frame', exact:true }).click();
  await verifyFrame(120, 'minus-one');
  await page.getByTitle('비디오 위치 탐색 (Seek)', { exact:true }).fill('0');
  await verifyFrame(0, 'first-frame');
  await page.getByRole('button', { name:'-1 Frame', exact:true }).click();
  await verifyFrame(0, 'clamp-first');
  await page.getByRole('button', { name:'+1 Frame', exact:true }).click();
  await verifyFrame(1, 'first-plus-one');
  await page.getByRole('button', { name:'-1 Frame', exact:true }).click();
  await verifyFrame(0, 'back-to-first');
  await page.getByTitle('비디오 위치 탐색 (Seek)', { exact:true }).fill('16');
  await verifyFrame(479, 'last-frame');
  await page.getByRole('button', { name:'+1 Frame', exact:true }).click();
  await verifyFrame(479, 'clamp-last');
  await page.getByRole('button', { name:'-1 Frame', exact:true }).click();
  await verifyFrame(478, 'last-minus-one');
  await page.getByRole('button', { name:'+1 Frame', exact:true }).click();
  await verifyFrame(479, 'back-to-last');
  await page.getByTitle('비디오 위치 탐색 (Seek)', { exact:true }).fill('4');
  await verifyFrame(120, 'before-resume');
  await page.getByRole('button', { name:'Play', exact:true }).click();
  await expect.poll(() => video.evaluate(element => element.currentTime)).toBeGreaterThan(4.02);
  await page.getByRole('button', { name:'+1 Frame', exact:true }).click();
  await expect.poll(() => video.evaluate(element => element.paused)).toBe(true);
  await expect.poll(() => video.evaluate(element => element.seeking)).toBe(false);
  await verifyFrame(await video.evaluate(element => Math.floor(element.currentTime * 30)), 'step-during-playback');
  await page.getByRole('button', { name:'Play', exact:true }).click();
  await expect.poll(() => video.evaluate(element => element.paused)).toBe(false);
  await page.getByRole('button', { name:'Pause', exact:true }).click();
  await expect.poll(() => video.evaluate(element => element.paused)).toBe(true);
  await verifyFrame(await video.evaluate(element => Math.floor(element.currentTime * 30)), 'pause-after-resume');
  await expect(page.locator('#live-video-source')).toHaveValue('VID-000003');
  } finally {
    writeFileSync(info.outputPath('media-events.json'), JSON.stringify(await page.evaluate(() => window.frameEvents), null, 2));
  }
});

test('TC-02 outer/inner inspection tabs preserve stored ID without new analysis', async ({ page, safety }) => {
  const identifier = preflight.requestedInspection?.inspection_id ?? preflight.publicInspectionId;
  if (identifier) await queryStored(page, identifier);
  const initialWrites = safety.blocked.filter(entry => entry.method === 'POST').length;
  await page.getByRole('tab', { name:'Grab 이미지 검사', exact:true }).click();
  await expect(page.locator('#patchcore-inspection-panel')).toBeVisible();
  await page.getByRole('tab', { name:'2차 · Gemini Judge', exact:true }).click();
  await expect(page.locator('#judge-inspection-panel')).toBeVisible();
  await expect(page.locator('#patchcore-inspection-panel')).toBeHidden();
  if (identifier) await expect(page.locator('#judge-inspection-panel')).toContainText(identifier);
  await page.getByRole('tab', { name:'정적 이미지 검사', exact:true }).click();
  if (identifier) await expect(page.getByLabel('검사 ID 조회 입력', { exact:true })).toHaveValue(identifier);
  await page.getByRole('tab', { name:'Grab 이미지 검사', exact:true }).click();
  await expect(page.locator('#judge-inspection-panel')).toBeVisible();
  await page.getByRole('tab', { name:'1차 · PatchCore 검사', exact:true }).click();
  expect(safety.blocked.filter(entry => entry.method === 'POST').length).toBe(initialWrites);
});

test('TC-03 stored Heatmap, Zoom, Pan, Reset and raw Pixel Inspector', async ({ page }, info) => {
  const record = await loadViewer(page, info);
  const heatmap = page.getByRole('button', { name:/^Heatmap (ON|OFF)$/ });
  await expect(heatmap).toBeEnabled();
  if ((await heatmap.innerText()).includes('ON')) await heatmap.click();
  const plain = await page.locator('canvas.precision-canvas').screenshot();
  await heatmap.click();
  await expect(heatmap).toHaveText('Heatmap ON');
  const overlay = await page.locator('canvas.precision-canvas').screenshot();
  expect(plain.equals(overlay)).toBe(false);
  await page.screenshot({ path:info.outputPath('heatmap-on.png'), fullPage:true });
  await expect(page.locator('.verdict-location-notice')).toContainText('실제 결함 위치가 검증된 결과는 아닙니다');
  await heatmap.click();
  await page.getByRole('button', { name:'200%', exact:true }).click();
  await expect(page.getByRole('button', { name:'200%', exact:true })).toHaveClass(/active/);
  const beforePan = await page.locator('canvas.precision-canvas').screenshot();
  await pan(page);
  expect(beforePan.equals(await page.locator('canvas.precision-canvas').screenshot())).toBe(false);
  await page.getByRole('button', { name:'Pan Reset', exact:true }).click();
  expect(beforePan.equals(await page.locator('canvas.precision-canvas').screenshot())).toBe(true);
  await page.getByRole('button', { name:'100% Reset', exact:true }).click();
  await expect(page.getByRole('button', { name:'100%', exact:true })).toHaveClass(/active/);
  const canvas = page.locator('canvas.precision-canvas');
  const box = await canvas.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page.locator('.rgb-val')).toHaveText(/RGB\(\d+, \d+, \d+\)/);
  await expect(page.locator('.gv-val')).toHaveText(/^\d+$/);
  const first = await page.locator('.coord-val').innerText();
  await page.mouse.move(box.x + box.width / 2 + 20, box.y + box.height / 2);
  await expect(page.locator('.coord-val')).not.toHaveText(first);
  const values = (await page.locator('.rgb-val').innerText()).match(/\d+/g).map(Number);
  expect(values.every(value => value >= 0 && value <= 255)).toBe(true);
  const gray = Number(await page.locator('.gv-val').innerText());
  expect(gray).toBe(Math.round(values[0]*0.299 + values[1]*0.587 + values[2]*0.114));
  const coordinates = (await page.locator('.coord-val').innerText()).match(/\d+/g).map(Number);
  const pixel = await page.evaluate(async ({ record, coordinates }) => {
    const url = record.metrics?.input_source === 'LIVEVIEW_GRAB'
      ? `/api/inspections/${record.inspection_id}/input-image`
      : `/api/inspections/images/${record.image_id}/file`;
    const response = await fetch(url, { credentials:'include' });
    if (!response.ok) throw new Error('Stored source PNG unavailable');
    const bitmap = await createImageBitmap(await response.blob());
    const surface = new OffscreenCanvas(bitmap.width, bitmap.height);
    const context = surface.getContext('2d');
    context.drawImage(bitmap, 0, 0);
    const color = [...context.getImageData(coordinates[0], coordinates[1], 1, 1).data].slice(0, 3);
    bitmap.close();
    return color;
  }, { record, coordinates });
  expect(values).toEqual(pixel);
  info.annotations.push({ type:'visual-review-required', description:`Heatmap alignment for ${record.inspection_id}; DOM checks and render changes do not prove spatial or defect accuracy` });
});

test('TC-04 pixel-derived bottle Edge state and zoom/pan overlay persistence', async ({ page }, info) => {
  await loadViewer(page, info, true);
  const toggle = page.getByRole('button', { name:/^병 테두리 (ON|OFF)$/ });
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  const details = page.locator('details.bottle-edge-information');
  await details.locator('summary').click();
  await expect(details.locator('summary')).toHaveText(/외곽: (성공 \(기하 조건\)|불확실|실패) \/ 내부 림 후보: (성공 \(기하 조건\)|불확실|실패)/);
  await expect(details).toContainText('원·누락 구간을 보완하지 않습니다');
  const before = await details.locator('summary').innerText();
  await page.getByRole('button', { name:'200%', exact:true }).click();
  await pan(page);
  await expect(details.locator('summary')).toHaveText(before);
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await page.screenshot({ path:info.outputPath('edge-on-zoom-pan.png'), fullPage:true });
  await toggle.click();
  await expect(details).toHaveCount(0);
  info.annotations.push({ type:'visual-review-required', description:'Green observed outer contour / yellow rim candidates; uncertain or failed detection is valid, anatomical correctness requires image review' });
});

test('TC-05 region GV statistics and safe unavailable-mask representation', async ({ page }, info) => {
  const record = await loadViewer(page, info, true);
  await page.getByRole('button', { name:/^병 테두리 OFF$/ }).click();
  const details = page.locator('details.bottle-edge-information');
  await details.locator('summary').click();
  const cards = details.locator('.edge-region-statistics .edge-measurement-card');
  await expect(cards).toHaveCount(4);
  for (const [index, label] of ['A · 전체 ROI', 'B · 외곽 내부 후보', 'C · 닫힌 림 후보 내부', 'D · 외곽 바깥 후보'].entries()) {
    const card = cards.nth(index);
    await expect(card).toContainText(label);
    const text = await card.innerText();
    expect(text).not.toMatch(/NaN|Infinity/);
    if (text.includes('계산 불가')) { expect(index).not.toBe(0); continue; }
    const statistics = text.match(/GV: ([\d.]+) \/ ([\d.]+) \/ ([\d.]+)/);
    expect(statistics).not.toBeNull();
    for (const value of statistics.slice(1).map(Number)) { expect(value).toBeGreaterThanOrEqual(0); expect(value).toBeLessThanOrEqual(255); }
    const area = text.match(/([\d,]+) px · ROI 면적의 ([\d.]+)%/);
    expect(area).not.toBeNull();
    expect(Number(area[1].replaceAll(',', ''))).toBeGreaterThan(0);
    expect(Number(area[2])).toBeGreaterThanOrEqual(0);
    expect(Number(area[2])).toBeLessThanOrEqual(100);
    if (index === 0) expect(Number(statistics[1])).toBeCloseTo(record.metrics.mean, 2);
  }
  await expect(details).toContainText('영역별 GV에는 125.0을 적용하지 않으며');
});
