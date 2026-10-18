import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { access, mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { createServer as createHttpServer } from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer as createViteServer } from 'vite';
import react from '@vitejs/plugin-react';
import { agentHarnessSource, runAgentChecks } from './agent_browser_cases.mjs';
import { grabHarnessSource, runGrabChecks } from './grab_browser_cases.mjs';
import { visionHarnessSource, runVisionChecks } from './vision_browser_cases.mjs';
import { roiHarnessSource, runRoiChecks } from './roi_browser_cases.mjs';

const agentMode = process.argv.includes('--agent');
const grabMode = process.argv.includes('--grab');
const visionMode = process.argv.includes('--vision');
const roiMode = process.argv.includes('--roi');

const outputFlag = process.argv.indexOf('--output');
const browserArgument = outputFlag < 0 && process.argv[3] ? process.argv[2] : null;
const requestedOutput = outputFlag >= 0 ? process.argv[outputFlag + 1] : process.argv[3] || process.argv[2];

async function findChrome() {
  const candidates = [
    browserArgument,
    process.env.STEP4_CHROME_PATH,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      await access(candidate);
      return candidate;
    } catch {}
  }
  return null;
}

const harnessSource = `
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ImageView } from '/src/components/ImageView.tsx';
import '/src/index.css';

const imageJobs = [];
const metadataJobs = [];
const blockedRequests = [];
const drawCalls = [];
const nativeDrawImage = CanvasRenderingContext2D.prototype.drawImage;
CanvasRenderingContext2D.prototype.drawImage = function (image, ...rectangle) {
  if (this.canvas.classList.contains('precision-canvas')) {
    drawCalls.push({ rectangle, alpha: this.globalAlpha });
    if (drawCalls.length > 2) drawCalls.shift();
  }
  return nativeDrawImage.call(this, image, ...rectangle);
};
const NativeImage = window.Image;
const nativeSource = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');

window.Image = function () {
  const image = new NativeImage();
  let requestedSource = '';
  Object.defineProperty(image, 'src', {
    get: () => requestedSource,
    set: (url) => {
      requestedSource = String(url);
      if (requestedSource.startsWith('data:image/png')) {
        nativeSource.set.call(image, requestedSource);
        return;
      }
      const sourceMatch = requestedSource.match(/\\/inspections\\/images\\/([^/]+)\\/file$/);
      const overlayMatch = requestedSource.match(/\\/inspections\\/([^/]+)\\/anomaly-map\\/overlay\\.png$/);
      if (!sourceMatch && !overlayMatch) throw new Error('Unexpected image URL: ' + requestedSource);
      imageJobs.push({ image, id: decodeURIComponent((sourceMatch || overlayMatch)[1]), kind: sourceMatch ? 'source' : 'overlay', released: false });
    },
  });
  return image;
};

window.fetch = (input, options = {}) => {
  const url = new URL(typeof input === 'string' ? input : input.url, location.href);
  const method = options.method || input.method || 'GET';
  const match = url.pathname.match(/^\\/api\\/inspections\\/([^/]+)\\/anomaly-map$/);
  if (method !== 'GET' || url.origin !== location.origin || !match) {
    blockedRequests.push({ url: url.pathname, method });
    return Promise.reject(new Error('Only synthetic anomaly-map GET is permitted'));
  }
  return new Promise((resolve) => metadataJobs.push({ id: decodeURIComponent(match[1]), resolve, released: false }));
};

function pixels(width, height, color) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d');
  context.fillStyle = color;
  context.fillRect(0, 0, width, height);
  return { url: canvas.toDataURL('image/png'), imageData: context.getImageData(0, 0, width, height) };
}

window.step4 = {
  ready: false,
  imageJobs,
  metadataJobs,
  blockedRequests,
  resolveMetadata(id, overrides = {}, status = 200) {
    const job = metadataJobs.find((entry) => entry.id === id && !entry.released);
    if (!job) throw new Error('No pending metadata: ' + id);
    job.released = true;
    job.resolve(new Response(JSON.stringify({
      schema_version: '1.0', inspection_id: id, image_id: 'IMG-' + id,
      model_name: 'SYNTHETIC_TEST_ONLY', anomaly_score: null, decision_threshold: null,
      original_image_width: 12, original_image_height: 8,
      anomaly_map_width: 3, anomaly_map_height: 2, localization_available: true, available: true,
      ...overrides,
    }), { status, headers: { 'Content-Type': 'application/json' } }));
  },
  releaseImage(id, kind, width = 12, height = 8, color = 'rgb(20, 40, 60)') {
    const job = imageJobs.find((entry) => entry.id === id && entry.kind === kind && !entry.released);
    if (!job) throw new Error('No pending image: ' + id + ':' + kind);
    job.released = true;
    const onload = job.image.onload;
    const onerror = job.image.onerror;
    return new Promise((resolve, reject) => {
      job.image.onload = (event) => { onload?.call(job.image, event); resolve(); };
      job.image.onerror = (event) => { onerror?.call(job.image, event); reject(new Error('Synthetic PNG failed to decode')); };
      nativeSource.set.call(job.image, pixels(width, height, color).url);
    });
  },
  heatmapButton() {
    return [...document.querySelectorAll('button')].find((button) => button.textContent.includes('Heatmap'));
  },
  snapshot() {
    const canvas = document.querySelector('canvas.precision-canvas');
    const button = this.heatmapButton();
    return {
      canvas: !!canvas,
      width: canvas?.width,
      height: canvas?.height,
      pixel: canvas ? [...canvas.getContext('2d').getImageData(300, 300, 1, 1).data] : null,
      heatmap: button?.textContent.trim(),
      disabled: button?.disabled,
      inspector: document.querySelector('.pixel-inspector-bar')?.textContent,
      text: document.body.textContent,
      drawCalls,
    };
  },
};

function Harness() {
  const [inspection, setInspection] = useState(null);
  const [loading, setLoading] = useState(false);
  const [captureProps, setCaptureProps] = useState({ capture: null, imageBlobUrl: null, cropData: null });
  window.step4.select = (id, provenance = 'STORED_RESULT') => setInspection({
    inspection_id: id, product_id: 'PRODUCT-SYNTHETIC', image_id: 'IMG-' + id,
    status: 'COMPLETED', result: 'UNKNOWN', timestamp: '2026-01-01T00:00:00Z',
    image_quality_status: 'NORMAL', metrics: {}, anomaly_score: null, inference_time_ms: null,
    model_version: null, decision_threshold: null, defect_detection_status: null,
    final_result: null, final_reason_code: null, provenance,
  });
  window.step4.setLoading = setLoading;
  window.step4.verdict = (finalResult) => setInspection((previous) => ({ ...previous, final_result: finalResult }));
  window.step4.capture = () => {
    const image = pixels(12, 8, 'rgb(60, 80, 100)');
    setCaptureProps({
      capture: { capture_id: 'CAPTURE-SYNTHETIC', video_id: 'VIDEO-SYNTHETIC', source_revision: 'synthetic', frame_index: 0, width: 12, height: 8 },
      imageBlobUrl: image.url,
      cropData: { cropBlobUrl: image.url, imageData: image.imageData, roi: { x: 2, y: 3, width: 12, height: 8 }, width: 12, height: 8, captureId: 'CAPTURE-SYNTHETIC', videoId: 'VIDEO-SYNTHETIC', sourceRevision: 'synthetic', frameIndex: 0, createdAt: '2026-01-01T00:00:00Z' },
    });
  };
  window.step4.ready = true;
  return <ImageView {...captureProps} isLoading={loading} error={null} currentInspection={inspection} />;
}

createRoot(document.getElementById('root')).render(<Harness />);
`;

async function connectCdp(websocketUrl, onEvent) {
  const socket = new WebSocket(websocketUrl);
  await once(socket, 'open');
  const pending = new Map();
  let nextId = 0;
  socket.addEventListener('message', (event) => {
    const message = JSON.parse(String(event.data));
    if (message.method) onEvent(message);
    const entry = pending.get(message.id);
    if (!entry) return;
    pending.delete(message.id);
    clearTimeout(entry.timeout);
    if (message.error) entry.reject(new Error(message.error.message));
    else entry.resolve(message.result);
  });
  return {
    send(method, params = {}) {
      const id = ++nextId;
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => { pending.delete(id); reject(new Error('CDP timeout: ' + method)); }, 15000);
        pending.set(id, { resolve, reject, timeout });
        socket.send(JSON.stringify({ id, method, params }));
      });
    },
    close() {
      for (const entry of pending.values()) {
        clearTimeout(entry.timeout);
        entry.reject(new Error('CDP closed'));
      }
      pending.clear();
      socket.close();
    },
  };
}

async function runBrowserAudit(outputRoot) {
  const summary = { stage: 'frontend-browser', status: 'PASS', passed: 0, failed: 0, skipped: 0, evidencePath: null };
  const events = [];
  const emit = (event) => {
    const result = { stage: 'frontend-browser', ...event };
    events.push(result);
    process.stdout.write(`${JSON.stringify(result)}\n`);
  };
  let vite;
  let server;
  let browser;
  let cdp;
  let browserStderr = '';
  let browserExit;
  try {
    await mkdir(outputRoot, { recursive: true });
    const runDirectory = await mkdtemp(path.join(outputRoot, 'step4-browser-'));
    summary.evidencePath = runDirectory;
    const chrome = await findChrome();
    if (!chrome) {
      summary.status = 'SKIP';
      summary.skipped = 1;
      emit({ status: 'SKIP', name: 'browser availability', details: 'Chrome/Edge not installed; no downloads attempted' });
      return;
    }
    const frontendRoot = fileURLToPath(new URL('../', import.meta.url));
    const virtualEntry = path.join(frontendRoot, 'step4-harness.tsx').replaceAll('\\', '/');
    vite = await createViteServer({
      root: frontendRoot,
      configFile: false,
      envFile: false,
      define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('/api') },
      cacheDir: path.join(runDirectory, 'vite-cache'),
      logLevel: 'silent',
      css: { postcss: { plugins: [] } },
      plugins: [{
        name: 'step4-isolated-harness',
        resolveId(id) { if (id === '/step4-harness.tsx') return virtualEntry; },
        load(id) { if (id === virtualEntry) return roiMode ? roiHarnessSource : visionMode ? visionHarnessSource : grabMode ? grabHarnessSource : agentMode ? agentHarnessSource : harnessSource; },
      }, react()],
      server: { middlewareMode: true, hmr: false, ws: false, watch: null },
      optimizeDeps: { noDiscovery: true, include: ['react', 'react-dom/client', 'lucide-react'] },
    });
    let rejectedServerRequests = 0;
    server = createHttpServer(async (request, response) => {
      try {
        if (request.method !== 'GET' || request.url.startsWith('/api/')) {
          rejectedServerRequests++;
          response.writeHead(405, { 'Content-Type': 'application/json' });
          response.end(JSON.stringify({ error: 'Synthetic browser harness rejects all backend requests' }));
          return;
        }
        if (request.url === '/') {
          const html = await vite.transformIndexHtml('/', '<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="default-src \'self\' data: blob:; script-src \'self\' \'unsafe-inline\' \'unsafe-eval\'; style-src \'self\' \'unsafe-inline\'; connect-src \'self\';"><title>Step4 synthetic ImageView</title></head><body><div id="root"></div><script type="module" src="/step4-harness.tsx"></script></body></html>');
          response.writeHead(200, { 'Content-Type': 'text/html' });
          response.end(html);
          return;
        }
        if (request.url === '/favicon.ico') { response.writeHead(204); response.end(); return; }
        vite.middlewares(request, response, () => { response.writeHead(404); response.end(); });
      } catch (error) {
        response.writeHead(500);
        response.end(String(error));
      }
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const origin = `http://127.0.0.1:${server.address().port}`;
    const profileDirectory = path.join(runDirectory, 'chrome-profile');
    browser = spawn(chrome, [
      '--headless=new', '--disable-gpu', '--disable-background-networking', '--disable-component-update',
      '--disable-sync', '--disable-default-apps', '--no-first-run', '--no-default-browser-check',
      '--disable-breakpad', '--disable-crash-reporter', `--crash-dumps-dir=${path.join(runDirectory, 'crash-dumps')}`,
      '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0',
      '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1',
      `--user-data-dir=${profileDirectory}`, 'about:blank',
    ], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'], env: { ...process.env, TEMP: runDirectory, TMP: runDirectory, TMPDIR: runDirectory } });
    browserExit = once(browser, 'exit').catch((error) => { browserStderr += String(error); });
    browser.stderr.on('data', (chunk) => { browserStderr = (browserStderr + chunk).slice(-4000); });
    let debuggerPort;
    const debuggerDeadline = Date.now() + 15000;
    while (!debuggerPort && Date.now() < debuggerDeadline) {
      if (browser.exitCode !== null) throw new Error('Chrome exited before CDP became available');
      try { debuggerPort = (await readFile(path.join(profileDirectory, 'DevToolsActivePort'), 'utf8')).split(/\r?\n/)[0]; } catch {}
      if (!debuggerPort) await new Promise((resolve) => setTimeout(resolve, 50));
    }
    assert.ok(debuggerPort, 'Chrome CDP port must become available');
    const targets = await fetch(`http://127.0.0.1:${debuggerPort}/json/list`).then((response) => response.json());
    cdp = await connectCdp(targets.find((target) => target.type === 'page').webSocketDebuggerUrl, (event) => {
      if (['Runtime.exceptionThrown', 'Log.entryAdded'].includes(event.method)) events.push(event);
    });
    summary.browserVersion = (await cdp.send('Browser.getVersion')).product;
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Log.enable');
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1200, height: 1400, deviceScaleFactor: 1, mobile: false });
    await cdp.send('Page.navigate', { url: origin });
    const evaluate = async (expression) => {
      const result = await cdp.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
      return result.result.value;
    };
    const waitFor = async (expression) => {
      const deadline = Date.now() + 15000;
      while (Date.now() < deadline) {
        if (await evaluate(`Boolean(${expression})`)) return;
        await new Promise((resolve) => setTimeout(resolve, 25));
      }
      const diagnostics = await evaluate('({url: location.href, text: document.body?.innerText?.slice(0, 600)})');
      throw new Error('Browser condition timed out: ' + expression + ' ' + JSON.stringify({ diagnostics, events }));
    };
    const check = async (name, action) => {
      await action();
      summary.passed++;
      emit({ status: 'PASS', name });
    };
    const select = async (id, provenance = 'STORED_RESULT') => {
      await evaluate(`window.step4.select(${JSON.stringify(id)}, ${JSON.stringify(provenance)})`);
      await waitFor(`window.step4.imageJobs.some(entry => entry.id === ${JSON.stringify('IMG-' + id)} && entry.kind === 'source')`);
    };
    const ready = async (id, color = 'rgb(20, 40, 60)') => {
      await evaluate(`window.step4.resolveMetadata(${JSON.stringify(id)})`);
      await waitFor(`window.step4.imageJobs.some(entry => entry.id === ${JSON.stringify(id)} && entry.kind === 'overlay')`);
      await evaluate(`window.step4.releaseImage(${JSON.stringify(id)}, 'overlay', 12, 8, 'rgb(200, 40, 20)')`);
      await evaluate(`window.step4.releaseImage(${JSON.stringify('IMG-' + id)}, 'source', 12, 8, ${JSON.stringify(color)})`);
      await waitFor('window.step4.snapshot().width === 600 && window.step4.snapshot().disabled === false');
    };
    await waitFor(roiMode ? 'window.step81?.ready' : visionMode ? 'window.step9?.ready' : grabMode ? 'window.step7?.ready' : agentMode ? 'window.step5?.ready' : 'window.step4?.ready');

    if (roiMode) {
      await runRoiChecks({ check, evaluate, waitFor, cdp });
    } else if (visionMode) {
      await runVisionChecks({ check, evaluate, waitFor, cdp });
    } else if (grabMode) {
      await runGrabChecks({ check, evaluate, waitFor, cdp });
    } else if (agentMode) {
      await runAgentChecks({ check, evaluate, waitFor });
    } else {

    await check('valid map overlays the real canvas while inspector reads original pixels', async () => {
      await select('SYNTHETIC-A');
      await ready('SYNTHETIC-A');
      assert.deepEqual((await evaluate('window.step4.snapshot()')).pixel, [20, 40, 60, 255]);
      await evaluate('window.step4.heatmapButton().click()');
      await waitFor("window.step4.snapshot().heatmap === 'Heatmap ON'");
      assert.notDeepEqual((await evaluate('window.step4.snapshot()')).pixel, [20, 40, 60, 255]);
      await evaluate("(() => { const canvas = document.querySelector('canvas.precision-canvas'); const rect = canvas.getBoundingClientRect(); canvas.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 })); })()");
      await waitFor("window.step4.snapshot().inspector.includes('RGB(20, 40, 60)')");
    });

    await check('opacity changes canvas blending, not original RGB and GV', async () => {
      const before = (await evaluate('window.step4.snapshot()')).pixel;
      await evaluate(`(() => { const slider = document.querySelector('input[type=range]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(slider, '0.1'); slider.dispatchEvent(new Event('input', {bubbles: true})); slider.dispatchEvent(new Event('change', {bubbles: true})); })()`);
      await waitFor("window.step4.snapshot().drawCalls.at(-1).alpha === 0.1");
      assert.notDeepEqual((await evaluate('window.step4.snapshot()')).pixel, before);
      assert.ok((await evaluate('window.step4.snapshot()')).inspector.includes('RGB(20, 40, 60)'));
      assert.ok((await evaluate('window.step4.snapshot()')).inspector.includes('36'));
    });

    await check('source and overlay share actual draw rectangles at every zoom and after pan', async () => {
      for (const percent of [100, 200, 400, 800, 1600, 3200, 4000]) {
        await evaluate(`[...document.querySelectorAll('.preset-btn')].find(button => button.textContent === '${percent}%').click()`);
        await waitFor(`window.step4.snapshot().drawCalls.at(-1).rectangle[2] === ${12 * percent / 100}`);
        const calls = (await evaluate('window.step4.snapshot()')).drawCalls;
        assert.deepEqual(calls[0].rectangle, calls[1].rectangle);
        assert.equal(calls[1].rectangle[3], 8 * percent / 100);
      }
      await evaluate("document.querySelector('canvas.precision-canvas').scrollIntoView({block:'center'})");
      const rectangle = await evaluate("(() => { const rect = document.querySelector('canvas.precision-canvas').getBoundingClientRect(); return {x:rect.left + rect.width/2, y:rect.top + rect.height/2, scale:rect.width/600}; })()");
      const before = (await evaluate('window.step4.snapshot()')).drawCalls[1].rectangle;
      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: rectangle.x, y: rectangle.y, button: 'left', clickCount: 1 });
      await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: rectangle.x + 15, y: rectangle.y + 10, button: 'left', buttons: 1 });
      await waitFor(`window.step4.snapshot().drawCalls.at(-1).rectangle[0] !== ${before[0]}`);
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: rectangle.x + 15, y: rectangle.y + 10, button: 'left', clickCount: 1 });
      const calls = (await evaluate('window.step4.snapshot()')).drawCalls;
      assert.deepEqual(calls[0].rectangle, calls[1].rectangle);
      assert.ok(Math.abs(calls[1].rectangle[0] - before[0] - 15 / rectangle.scale) < 0.1);
      assert.ok(Math.abs(calls[1].rectangle[1] - before[1] - 10 / rectangle.scale) < 0.1);
      await evaluate("[...document.querySelectorAll('button')].find(button => button.textContent.includes('100% Reset')).click()");
      await waitFor('window.step4.snapshot().drawCalls.at(-1).rectangle[2] === 12');
    });

    await check('stored OK, NG and REINSPECT overlays retain their exact server verdict', async () => {
      for (const verdict of ['OK', 'NG', 'REINSPECT']) {
        await evaluate(`window.step4.verdict('${verdict}')`);
        await waitFor("window.step4.metadataJobs.some(entry => entry.id === 'SYNTHETIC-A' && !entry.released)");
        await ready('SYNTHETIC-A');
        await waitFor(`document.querySelector('.verdict-badge-lg')?.textContent === '${verdict}'`);
      }
    });

    await check('pending inspection hides old static image and rejects mismatched metadata', async () => {
      await select('SYNTHETIC-B');
      assert.equal((await evaluate('window.step4.snapshot()')).canvas, false);
      await evaluate("window.step4.resolveMetadata('SYNTHETIC-B', { image_id: 'IMG-WRONG' })");
      await evaluate("window.step4.releaseImage('IMG-SYNTHETIC-B', 'source')");
      await waitFor('window.step4.snapshot().width === 600 && window.step4.snapshot().disabled === true');
      assert.equal(await evaluate("window.step4.imageJobs.some(entry => entry.id === 'SYNTHETIC-B' && entry.kind === 'overlay')"), false);
    });

    await check('late metadata and late static/overlay PNG loads cannot replace the newest inspection', async () => {
      await select('SYNTHETIC-C');
      await select('SYNTHETIC-D');
      await evaluate("window.step4.resolveMetadata('SYNTHETIC-D')");
      await waitFor("window.step4.imageJobs.some(entry => entry.id === 'SYNTHETIC-D' && entry.kind === 'overlay')");
      await select('SYNTHETIC-E');
      await ready('SYNTHETIC-E', 'rgb(70, 90, 110)');
      await evaluate("window.step4.resolveMetadata('SYNTHETIC-C')");
      await evaluate("window.step4.releaseImage('IMG-SYNTHETIC-C', 'source')");
      await evaluate("window.step4.releaseImage('IMG-SYNTHETIC-D', 'source')");
      await evaluate("window.step4.releaseImage('SYNTHETIC-D', 'overlay')");
      assert.equal(await evaluate("window.step4.imageJobs.some(entry => entry.id === 'SYNTHETIC-C' && entry.kind === 'overlay')"), false);
      const snapshot = await evaluate('window.step4.snapshot()');
      assert.deepEqual(snapshot.pixel, [70, 90, 110, 255]);
      assert.equal(snapshot.heatmap, 'Heatmap OFF');
      assert.equal(snapshot.disabled, false);
    });

    await check('source dimensions and decoded overlay PNG dimensions independently block a heatmap', async () => {
      await select('SYNTHETIC-SIZE');
      await evaluate("window.step4.resolveMetadata('SYNTHETIC-SIZE', { original_image_width: 13 })");
      await waitFor("window.step4.imageJobs.some(entry => entry.id === 'SYNTHETIC-SIZE' && entry.kind === 'overlay')");
      await evaluate("window.step4.releaseImage('SYNTHETIC-SIZE', 'overlay', 13, 8)");
      await evaluate("window.step4.releaseImage('IMG-SYNTHETIC-SIZE', 'source')");
      await waitFor('window.step4.snapshot().disabled === true');
      await select('SYNTHETIC-PNG');
      await evaluate("window.step4.resolveMetadata('SYNTHETIC-PNG')");
      await waitFor("window.step4.imageJobs.some(entry => entry.id === 'SYNTHETIC-PNG' && entry.kind === 'overlay')");
      await evaluate("window.step4.releaseImage('SYNTHETIC-PNG', 'overlay', 3, 2)");
      await evaluate("window.step4.releaseImage('IMG-SYNTHETIC-PNG', 'source')");
      await waitFor('window.step4.snapshot().disabled === true');
    });

    await check('past inspection without a stored map remains safe and disabled', async () => {
      await select('SYNTHETIC-OLD');
      await evaluate("window.step4.resolveMetadata('SYNTHETIC-OLD', {detail: {error_code: 'MAP_NOT_AVAILABLE'}}, 404)");
      await evaluate("window.step4.releaseImage('IMG-SYNTHETIC-OLD', 'source')");
      await waitFor('window.step4.snapshot().width === 600 && window.step4.snapshot().disabled === true');
      assert.equal(await evaluate("window.step4.imageJobs.some(entry => entry.id === 'SYNTHETIC-OLD' && entry.kind === 'overlay')"), false);
    });

    await check('mock NG stays blocked even with live provenance and issues no heatmap request', async () => {
      await select('INSP-001391', 'LIVE_INSPECTION');
      await evaluate("window.step4.releaseImage('IMG-INSP-001391', 'source')");
      await waitFor('window.step4.snapshot().disabled === true');
      assert.equal(await evaluate("window.step4.metadataJobs.some(entry => entry.id === 'INSP-001391')"), false);
      assert.equal((await evaluate('window.step4.snapshot()')).heatmap, 'Heatmap OFF');
      assert.ok((await evaluate('window.step4.snapshot()')).text.includes('MOCK / TEST FIXTURE'));
    });

    await check('loading remount restores drawing and the native wheel listener', async () => {
      await select('SYNTHETIC-REMOUNT');
      await ready('SYNTHETIC-REMOUNT');
      await evaluate('window.step4.setLoading(true)');
      await waitFor('!window.step4.snapshot().canvas');
      await evaluate('window.step4.setLoading(false)');
      await waitFor('window.step4.snapshot().width === 600');
      await evaluate("(() => { const canvas = document.querySelector('canvas.precision-canvas'); const rect = canvas.getBoundingClientRect(); canvas.dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: -100, clientX: rect.left + 300, clientY: rect.top + 300 })); })()");
      await waitFor("document.querySelector('.preset-btn.active')?.textContent === '200%'");
    });

    await check('capture overview to focus remount redraws the precision canvas', async () => {
      await evaluate('window.step4.capture()');
      await waitFor("window.step4.snapshot().width === 600 && window.step4.snapshot().text.includes('Product Focus (12×8px)')");
      await evaluate("[...document.querySelectorAll('.view-mode-tabs button')].find(button => button.textContent.includes('Overview')).click()");
      await waitFor('!window.step4.snapshot().canvas');
      await evaluate("[...document.querySelectorAll('.view-mode-tabs button')].find(button => button.textContent.includes('Product Focus')).click()");
      await waitFor('window.step4.snapshot().width === 600');
      assert.deepEqual((await evaluate('window.step4.snapshot()')).pixel, [60, 80, 100, 255]);
    });

    await check('no real API calls or prohibited POST requests escaped the synthetic harness', async () => {
      assert.deepEqual(await evaluate('window.step4.blockedRequests'), []);
      assert.equal(rejectedServerRequests, 0);
    });
    }
    const screenshot = await cdp.send('Page.captureScreenshot', { format: 'png' });
    await writeFile(path.join(runDirectory, 'synthetic-imageview.png'), Buffer.from(screenshot.data, 'base64'));
  } catch (error) {
    summary.status = 'FAIL';
    summary.failed++;
    process.exitCode = 1;
    emit({ status: 'FAIL', name: 'browser regression', details: String(error.stack || error) });
  } finally {
    cdp?.close();
    if (browser && browser.exitCode === null) {
      browser.kill();
      await Promise.race([browserExit, new Promise((resolve) => setTimeout(resolve, 3000))]).catch(() => {});
    }
    await vite?.close();
    if (server) {
      server.closeAllConnections();
      await new Promise((resolve) => server.close(resolve));
    }
    if (summary.evidencePath) {
      await writeFile(path.join(summary.evidencePath, 'browser-stderr.txt'), browserStderr);
      await writeFile(path.join(summary.evidencePath, 'result.json'), JSON.stringify({ ...summary, events }, null, 2));
    }
    process.stdout.write(`${JSON.stringify(summary)}\n`);
  }
}

if (!requestedOutput || requestedOutput.startsWith('--')) {
  process.stdout.write(`${JSON.stringify({ stage: 'frontend-browser', status: 'FAIL', passed: 0, failed: 1, skipped: 0, details: 'Required: BROWSER_PATH UNIQUE_EVIDENCE_DIR or --output <unique-run-directory>' })}\n`);
  process.exitCode = 1;
} else {
  await runBrowserAudit(path.resolve(requestedOutput));
}
