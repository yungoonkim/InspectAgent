import { test, expect } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { createGrabBudget, requireEmptyCaptureDirectory } from './capturePolicy.mjs';
import { calculateViewportMapping } from '../src/utils/coordinateTransforms.ts';

const output = process.env.VISION_E2E_OUTPUT;
const preflight = JSON.parse(readFileSync(path.join(output, 'preflight.json'), 'utf8'));
const capturesDirectory = path.resolve('..', 'data/outputs/captures');
const budget = createGrabBudget(preflight.video.source_revision);
const save = (name, value) => writeFileSync(path.join(output, name), JSON.stringify(value, null, 2));
let context;
let page;
let capture;
let reference;
let roi;
let sessionPosts = 0;
const requests = [];
const errors = [];

async function chooseObservedRoi() {
  return page.locator('video.video-element').evaluate(async element => {
    const { detectBottleEdges } = await import('/src/utils/bottleEdges.ts');
    const surface = document.createElement('canvas');
    surface.width = element.videoWidth; surface.height = element.videoHeight;
    const drawing = surface.getContext('2d');
    drawing.drawImage(element, 0, 0);
    const size = surface.height;
    const candidates = [];
    for (let left = 0; left + size <= surface.width; left += Math.floor(size / 2)) {
      const result = detectBottleEdges(drawing.getImageData(left, 0, size, size));
      if (result.assessment.outer.status !== 'SUCCESS' || !result.outer.length) continue;
      const points = result.outer.flat();
      const minimumX = Math.min(...points.map(point => point.x)) + left;
      const maximumX = Math.max(...points.map(point => point.x)) + left;
      const minimumY = Math.min(...points.map(point => point.y));
      const maximumY = Math.max(...points.map(point => point.y));
      const margin = Math.ceil(Math.max(maximumX - minimumX, maximumY - minimumY) * 0.08);
      const startX = Math.max(0, Math.floor(minimumX) - margin);
      const startY = Math.max(0, Math.floor(minimumY) - margin);
      candidates.push({ x:startX, y:startY,
        width:Math.min(surface.width, Math.ceil(maximumX) + margin) - startX,
        height:Math.min(surface.height, Math.ceil(maximumY) + margin) - startY,
        observedBounds:{minimumX,maximumX,minimumY,maximumY},
        distance:Math.abs((minimumX + maximumX) / 2 - surface.width / 2) });
    }
    candidates.sort((first, second) => first.distance - second.distance);
    return { frame:Math.floor(element.currentTime * 30), time:element.currentTime,
      paused:element.paused, seeking:element.seeking, roi:candidates[0] ?? null };
  });
}

async function dragHandle(name, targetX, targetY, box, mapping) {
  const handle = page.locator(`.roi-handle-${name}`);
  const bounds = await handle.boundingBox();
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + mapping.offsetX + targetX * mapping.scaleX,
    box.y + mapping.offsetY + targetY * mapping.scaleY, {steps:4});
  await page.mouse.up();
}

test.describe.configure({ mode:'serial' });
test.beforeAll(async ({ browser }) => {
  requireEmptyCaptureDirectory(capturesDirectory);
  context = await browser.newContext({ viewport:{width:1600,height:1000}, serviceWorkers:'block' });
  expect(await context.cookies()).toEqual([]);
  page = await context.newPage();
  page.on('pageerror', error => errors.push(error.name));
  let issuedResolve;
  const issued = new Promise(resolve => { issuedResolve = resolve; });
  page.on('response', async response => {
    if (new URL(response.url()).pathname !== '/api/videos/VID-000003/grab' || response.request().method() !== 'POST') return;
    if (response.status() !== 201) { issuedResolve(null); return; }
    const metadata = await response.json();
    capture = metadata;
    issuedResolve(metadata);
  });
  await context.routeWebSocket('**/*', socket => socket.close());
  await context.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const apiPath = url.pathname.replace(/^\/api(?=\/)/, '');
    const entry = { method:request.method(), path:url.pathname, forwarded:false };
    requests.push(entry);
    try {
      if (!['http://localhost:5173','http://127.0.0.1:8000'].includes(url.origin)) throw new Error('EXTERNAL_NETWORK');
      if (entry.method === 'POST') {
        if (apiPath === '/capture-sessions') {
          requireEmptyCaptureDirectory(capturesDirectory);
          if (sessionPosts >= preflight.maxSessionPosts) throw new Error('SESSION_POST_LIMIT');
          sessionPosts++;
        } else if (apiPath === '/videos/VID-000003/grab') {
          requireEmptyCaptureDirectory(capturesDirectory);
          const headers = await request.allHeaders();
          if (!headers['x-capture-csrf']) throw new Error('CSRF_HEADER_MISSING');
          budget.claim(request.postDataJSON());
          writeFileSync(path.join(output,'grab-attempt.json'), JSON.stringify({ attempts:budget.attempts,
            video_id:'VID-000003', frame:request.postDataJSON().frame_index, startedAt:new Date().toISOString() }), {flag:'wx'});
        } else throw new Error('UNAPPROVED_WRITE');
      } else if (!['GET','HEAD'].includes(entry.method)) throw new Error('UNAPPROVED_WRITE');
      else if (apiPath.startsWith('/captures/') || apiPath.startsWith('/reinspection-groups/')) {
        const ownCapture = capture ?? await issued;
        if (!ownCapture || ![`/captures/${ownCapture.capture_id}`, `/captures/${ownCapture.capture_id}/image`,
          `/reinspection-groups/by-capture/${ownCapture.capture_id}`].includes(apiPath)) throw new Error('OTHER_OWNER_RESOURCE');
      } else if (url.pathname.startsWith('/api/') || url.origin === 'http://127.0.0.1:8000') {
        if (!/^\/(?:health|videos(?:\/VID-000003(?:\/stream)?)?|inspections(?:\/images(?:\/IMG-BOTTLE-[A-Z0-9-]+\/file)?)?)$/.test(apiPath)) {
          throw new Error('UNAPPROVED_READ');
        }
      }
      entry.forwarded = true;
      await route.continue();
    } catch (error) { entry.reason = error.message; await route.abort('blockedbyclient'); }
  });
  await page.goto('http://localhost:5173/');
  await page.getByLabel('LiveView 영상 선택').selectOption('VID-000003');
  await expect(page.getByLabel('LiveView 영상 선택')).toHaveValue('VID-000003');
  const video = page.locator('video.video-element');
  await expect(video).toHaveAttribute('src', /\/videos\/VID-000003\/stream$/);
  await expect.poll(() => video.evaluate(element => element.readyState >= 2 && element.duration === 16
    && element.videoWidth === 1920 && element.videoHeight === 480)).toBe(true);
  await page.getByRole('button', {name:'Pause',exact:true}).click();
  let selection = await chooseObservedRoi();
  for (let sample = 1; !selection.roi && sample <= 4; sample++) {
    await page.getByTitle('비디오 위치 탐색 (Seek)',{exact:true}).fill(String(preflight.video.duration_seconds * sample / 5));
    await expect.poll(() => video.evaluate(element => element.seeking)).toBe(false);
    selection = await chooseObservedRoi();
  }
  expect(selection.paused && !selection.seeking).toBe(true);
  expect(selection.roi, 'No fully observed bottle contour; stop without Grab').not.toBeNull();
  await expect(page.locator('.scrubber-row')).toContainText(`[Frame ${selection.frame} / 479]`);
  save('observed-selection.json', selection);
  await page.screenshot({path:path.join(output,'before-capture.png'),fullPage:true});
  budget.select(selection.frame);
  const grabResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/videos/VID-000003/grab'
    && response.request().method() === 'POST');
  await page.getByRole('button',{name:'ROI 선택',exact:true}).click();
  expect((await grabResponse).status()).toBe(201);
  expect(await issued).not.toBeNull();
  expect(capture.capture_id).toMatch(/^CAP-[a-f0-9]{32}$/);
  expect(capture.video_id).toBe('VID-000003');
  expect(capture.frame_index).toBe(selection.frame);
  expect(capture.source_revision).toBe(preflight.video.source_revision);
  save('capture.json', capture);
  await expect(page.locator('img.frozen-frame-layer')).toBeVisible();
  const overlay = page.locator('.roi-overlay-container');
  const box = await overlay.boundingBox();
  const mapping = calculateViewportMapping(box.width, box.height, 1920, 480);
  const initial = await page.locator('.roi-bounding-box').evaluate(element => ({
    right:parseFloat(element.style.left)+parseFloat(element.style.width),
    bottom:parseFloat(element.style.top)+parseFloat(element.style.height) }));
  const wanted = selection.roi;
  await dragHandle('se', Math.max((initial.right-mapping.offsetX)/mapping.scaleX,wanted.x+wanted.width),
    Math.max((initial.bottom-mapping.offsetY)/mapping.scaleY,wanted.y+wanted.height),box,mapping);
  await dragHandle('nw',wanted.x,wanted.y,box,mapping);
  await dragHandle('se',wanted.x+wanted.width,wanted.y+wanted.height,box,mapping);
  const styled = await page.locator('.roi-bounding-box').evaluate(element => ({left:parseFloat(element.style.left),
    top:parseFloat(element.style.top),width:parseFloat(element.style.width),height:parseFloat(element.style.height)}));
  roi = { x:Math.round((styled.left-mapping.offsetX)/mapping.scaleX), y:Math.round((styled.top-mapping.offsetY)/mapping.scaleY),
    width:Math.round(styled.width/mapping.scaleX), height:Math.round(styled.height/mapping.scaleY) };
  for (const field of ['x','y','width','height']) expect(Math.abs(roi[field]-wanted[field])).toBeLessThanOrEqual(1);
  await page.getByRole('button',{name:'Grab (Crop 반영)',exact:true}).click();
  await expect(page.getByRole('button',{name:'Grab + 저장 ROI',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'병 테두리 OFF',exact:true})).toBeEnabled();
  await expect(page.locator(`.meta-pill-value[title="${capture.capture_id}"]`)).toBeVisible();
  reference = await page.evaluate(async ({capture,roi}) => {
    const { detectBottleEdges } = await import('/src/utils/bottleEdges.ts');
    const response = await fetch(`/api/captures/${capture.capture_id}/image`,{credentials:'include'});
    if (!response.ok) throw new Error('OWN_CAPTURE_READ_FAILED');
    const bytes = await response.arrayBuffer();
    const bitmap = await createImageBitmap(new Blob([bytes],{type:'image/png'}));
    const surface = new OffscreenCanvas(roi.width,roi.height);
    const drawing = surface.getContext('2d');
    drawing.drawImage(bitmap,roi.x,roi.y,roi.width,roi.height,0,0,roi.width,roi.height);
    const pixels = drawing.getImageData(0,0,roi.width,roi.height);
    const gray = [];
    for (let index=0;index<pixels.data.length;index+=4) gray.push((pixels.data[index]*9798+pixels.data[index+1]*19235+pixels.data[index+2]*3735+16384)>>15);
    const total = gray.reduce((sum,value)=>sum+value,0);
    const mean = total/gray.length;
    const std = Math.sqrt(gray.reduce((sum,value)=>sum+(value-mean)**2,0)/gray.length);
    gray.sort((first,second)=>first-second);
    const median = (gray[Math.floor((gray.length-1)/2)]+gray[Math.floor(gray.length/2)])/2;
    const checksum = async data => [...new Uint8Array(await crypto.subtle.digest('SHA-256',data))].map(value=>value.toString(16).padStart(2,'0')).join('');
    const edges = detectBottleEdges(pixels);
    bitmap.close();
    return { capture_sha256:await checksum(bytes), crop_rgba_sha256:await checksum(pixels.data), roi,
      independentRoi:{mean,median,std,pixels:gray.length,areaRatio:1},
      assessment:edges.assessment, regions:edges.regions, outerSegments:edges.outer.length, rimSegments:edges.rim.length };
  },{capture,roi});
  save('measurements.json',reference);
  expect(budget.attempts).toBe(1);
});

test.afterEach(async ({},info) => {
  if (page && !page.isClosed()) await page.screenshot({path:info.outputPath('screen.png'),fullPage:true});
  save('safety.json',{sessionPosts,grabAttempts:budget.attempts,
    grabPosts:requests.filter(entry=>entry.forwarded&&entry.method==='POST'&&entry.path==='/api/videos/VID-000003/grab').length,
    requests,pageErrors:errors,captureId:capture?.capture_id??null,
    actualInspectionPosts:requests.filter(entry=>entry.forwarded && entry.method==='POST' && /inspect|analyze|review/.test(entry.path)).length});
});
test.afterAll(async () => {
  await context?.close();
});

test('TC-04 approved single Capture: actual Edge rendering and zoom/pan',async ({},info) => {
  const canvas = page.locator('canvas.precision-canvas');
  await canvas.evaluate(element=>{window.edgeOffPixels=element.getContext('2d').getImageData(0,0,element.width,element.height).data;});
  const toggle = page.getByRole('button',{name:/^병 테두리 (ON|OFF)$/});
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed','true');
  const details = page.locator('details.bottle-edge-information');
  await details.locator('summary').click();
  const labels = {SUCCESS:'성공 (기하 조건)',UNCERTAIN:'불확실',FAILED:'실패'};
  await expect(details.locator('summary')).toContainText(`외곽: ${labels[reference.assessment.outer.status]}`);
  await expect(details.locator('summary')).toContainText(`내부 림 후보: ${labels[reference.assessment.rim.status]}`);
  const colors = await canvas.evaluate(element=>{
    const current=element.getContext('2d').getImageData(0,0,element.width,element.height).data;
    const counts={green:0,yellow:0};
    for(let index=0;index<current.length;index+=4){
      if(current[index]===window.edgeOffPixels[index]&&current[index+1]===window.edgeOffPixels[index+1]&&current[index+2]===window.edgeOffPixels[index+2])continue;
      for(const [name,target] of [['green',[34,197,94]],['yellow',[250,204,21]]]){
        if(Math.abs(current[index]-target[0])+Math.abs(current[index+1]-target[1])+Math.abs(current[index+2]-target[2])<=32) counts[name]++;
      }
    }
    return counts;
  });
  if(reference.outerSegments)expect(colors.green).toBeGreaterThan(0);
  if(reference.rimSegments)expect(colors.yellow).toBeGreaterThan(0);
  save('edge-rendering.json',{colors,outerSegments:reference.outerSegments,rimSegments:reference.rimSegments,
    anatomicalAccuracy:'NOT_VERIFIED',alignment:'SCREENSHOT_REQUIRES_VISUAL_REVIEW'});
  await page.getByRole('button',{name:'200%',exact:true}).click();
  await canvas.scrollIntoViewIfNeeded();
  const box=await canvas.boundingBox();
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
  await page.mouse.down();
  await page.mouse.move(box.x+box.width/2+24,box.y+box.height/2+18,{steps:4});
  await page.mouse.up();
  await expect(toggle).toHaveAttribute('aria-pressed','true');
  await expect(details.locator('summary')).toContainText(`외곽: ${labels[reference.assessment.outer.status]}`);
  await page.screenshot({path:info.outputPath('edge-on-zoom-pan.png'),fullPage:true});
  await toggle.click();
  await expect(details).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('TC-05 same Capture: region GV and independent whole-Crop statistics',async ()=>{
  await page.getByRole('button',{name:'100% Reset',exact:true}).click();
  await page.getByRole('button',{name:'병 테두리 OFF',exact:true}).click();
  const details=page.locator('details.bottle-edge-information');
  await details.locator('summary').click();
  const cards=details.locator('.edge-region-statistics .edge-measurement-card');
  await expect(cards).toHaveCount(4);
  for(const [index,name] of ['roi','body','rim','background'].entries()){
    const expected=reference.regions[name];
    const text=await cards.nth(index).innerText();
    expect(text).not.toMatch(/NaN|Infinity/);
    if(!expected){expect(text).toContain('계산 불가');continue;}
    const values=text.match(/GV: ([\d.]+) \/ ([\d.]+) \/ ([\d.]+)/);
    expect(values).not.toBeNull();
    for(const [offset,field] of ['mean','median','std'].entries()){
      const actual=Number(values[offset+1]);
      expect(actual).toBeGreaterThanOrEqual(0);expect(actual).toBeLessThanOrEqual(255);
      expect(actual).toBeCloseTo(expected[field],2);
      if(name==='roi')expect(actual).toBeCloseTo(reference.independentRoi[field],2);
    }
    const area=text.match(/([\d,]+) px · ROI 면적의 ([\d.]+)%/);
    expect(area).not.toBeNull();
    expect(Number(area[1].replaceAll(',',''))).toBe(expected.pixels);
    expect(Number(area[2])).toBeCloseTo(expected.areaRatio*100,2);
  }
  await expect(page.locator(`.meta-pill-value[title="${capture.capture_id}"]`)).toBeVisible();
  expect(budget.attempts).toBe(1);
  expect(requests.filter(entry=>entry.forwarded&&entry.method==='POST'&&entry.path!=='/api/capture-sessions')).toHaveLength(1);
  expect(errors).toEqual([]);
});
