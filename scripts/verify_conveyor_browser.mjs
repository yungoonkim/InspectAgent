import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { readFile, writeFile, mkdir, stat } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { join, resolve } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

const [videoArgument, browserArgument, evidenceArgument, streamArgument, pageArgument] = process.argv.slice(2);
if (!videoArgument || !browserArgument || !evidenceArgument) {
  throw new Error('Usage: node verify_conveyor_browser.mjs VIDEO BROWSER ISOLATED_EVIDENCE_DIR');
}
const videoPath = resolve(videoArgument);
const browserPath = resolve(browserArgument);
const evidencePath = resolve(evidenceArgument);
const profilePath = join(evidencePath, 'chrome-profile');
const resultPath = join(evidencePath, 'browser_validation.json');
if (Boolean(streamArgument) !== Boolean(pageArgument)) throw new Error('Provide both loopback stream and verification page URLs');
for (const argument of [streamArgument, pageArgument].filter(Boolean)) {
  const parsed = new URL(argument);
  if (parsed.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(parsed.hostname) || parsed.username || parsed.password) {
    throw new Error('Only explicit loopback HTTP verification URLs are allowed');
  }
}
await mkdir(profilePath);
const videoSize = (await stat(videoPath)).size;
const requests = [];
const results = { status: 'BROWSER_NOT_TESTED', requests, blockedExternalRequests: [], checks: {} };
results.streamUrl = streamArgument ?? null;
results.browserHttp = [];
const server = createServer((request, response) => {
  const entry = { method: request.method, url: request.url, range: request.headers.range ?? null, userAgent: request.headers['user-agent'] ?? null };
  requests.push(entry);
  if (request.url === '/') {
    entry.status = 200;
    response.writeHead(200, { 'Content-Type': 'text/html', 'Cache-Control': 'no-store' });
    response.end(`<!doctype html><title>Local video verification</title>
      <video id="clip" controls muted preload="auto" width="960"></video>
      <script>
        window.videoEvents = [];
        const video = document.getElementById('clip');
        for (const eventName of ['loadedmetadata','loadeddata','playing','pause','seeking','seeked','ended','error']) {
          video.addEventListener(eventName, () => window.videoEvents.push({
            event: eventName, currentTime: video.currentTime, clock: performance.now(),
            error: video.error ? {code: video.error.code, message: video.error.message} : null
          }));
        }
        video.src = '/clip.mp4';
      </script>`);
    return;
  }
  if (request.url !== '/clip.mp4' || !['GET', 'HEAD'].includes(request.method)) {
    entry.status = 404;
    response.writeHead(404).end();
    return;
  }
  let start = 0;
  let end = videoSize - 1;
  if (request.headers.range) {
    const match = /^bytes=(\d+)-(\d*)$/.exec(request.headers.range);
    if (!match) {
      entry.status = 416;
      response.writeHead(416, { 'Content-Range': `bytes */${videoSize}` }).end();
      return;
    }
    start = Number(match[1]);
    end = match[2] ? Math.min(Number(match[2]), end) : end;
    if (start > end || start >= videoSize) {
      entry.status = 416;
      response.writeHead(416, { 'Content-Range': `bytes */${videoSize}` }).end();
      return;
    }
  }
  entry.status = request.headers.range ? 206 : 200;
  const headers = {
    'Content-Type': 'video/mp4',
    'Accept-Ranges': 'bytes',
    'Content-Length': end - start + 1,
    'Cache-Control': 'no-store',
  };
  if (entry.status === 206) headers['Content-Range'] = `bytes ${start}-${end}/${videoSize}`;
  entry.responseHeaders = headers;
  response.writeHead(entry.status, headers);
  if (request.method === 'HEAD') response.end();
  else createReadStream(videoPath, { start, end }).pipe(response);
});
await new Promise(resolveListen => server.listen(0, '127.0.0.1', resolveListen));
const baseUrl = `http://127.0.0.1:${server.address().port}`;
let browser;
let websocket;
let browserStderr = '';
let nextIdentifier = 0;
const pending = new Map();

function command(method, params = {}) {
  const identifier = ++nextIdentifier;
  return new Promise((resolveCommand, rejectCommand) => {
    const timer = setTimeout(() => {
      pending.delete(identifier);
      rejectCommand(new Error(`CDP timeout: ${method}`));
    }, 15000);
    pending.set(identifier, {
      resolve: value => { clearTimeout(timer); resolveCommand(value); },
      reject: error => { clearTimeout(timer); rejectCommand(error); },
    });
    websocket.send(JSON.stringify({ id: identifier, method, params }));
  });
}

async function evaluate(expression) {
  const result = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}

const snapshot = `(() => {
  const video = document.getElementById('clip');
  const quality = video.getVideoPlaybackQuality();
  return { width: video.videoWidth, height: video.videoHeight,
    duration: Number.isFinite(video.duration) ? video.duration : null,
    currentTime: video.currentTime, paused: video.paused, ended: video.ended,
    readyState: video.readyState, networkState: video.networkState,
    decodedFrames: quality.totalVideoFrames, droppedFrames: quality.droppedVideoFrames,
    canPlayMp4v: video.canPlayType('video/mp4; codecs="mp4v.20.9"'),
    canPlayH264: video.canPlayType('video/mp4; codecs="avc1.640028"'),
    error: video.error ? {code: video.error.code, message: video.error.message} : null };
})()`;

const frameProbe = `(() => {
  const video = document.getElementById('clip');
  const canvas = document.createElement('canvas'); canvas.width=1920; canvas.height=480;
  const context = canvas.getContext('2d'); context.drawImage(video,0,0);
  const pixels=context.getImageData(0,0,1920,480).data;
  let minimum=255, maximum=0, checksum=2166136261;
  for(let index=0;index<pixels.length;index+=4) {
    minimum=Math.min(minimum,pixels[index]); maximum=Math.max(maximum,pixels[index]);
    checksum=Math.imul(checksum ^ pixels[index],16777619) >>> 0;
  }
  return {minimum,maximum,checksum,currentTime:video.currentTime};
})()`;

async function seek(seconds) {
  const outcome = await evaluate(`new Promise(resolveSeek => {
    const video = document.getElementById('clip');
    let seekingSeen = false;
    const seeking = () => {seekingSeen = true;};
    const finish = () => {
      clearTimeout(timer); video.removeEventListener('seeking',seeking);
      resolveSeek({time: video.currentTime, seekingSeen, seekedSeen: true});
    };
    const timer = setTimeout(() => {
      video.removeEventListener('seeking',seeking); video.removeEventListener('seeked',finish);
      resolveSeek({timeout: true, seekingSeen, seekedSeen: false});
    }, 5000);
    video.addEventListener('seeking', seeking, {once: true});
    video.addEventListener('seeked', finish, {once: true});
    video.currentTime = ${seconds};
  })`);
  await delay(100);
  return {requestedTime: seconds, ...outcome, frame: await evaluate(frameProbe), state: await evaluate(snapshot)};
}

try {
  browser = spawn(browserPath, [
    '--headless=new', '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
    `--user-data-dir=${profilePath}`, '--no-first-run', '--no-default-browser-check',
    '--disable-background-networking', '--disable-component-update', '--disable-sync',
    '--disable-extensions', '--disable-default-apps', '--metrics-recording-only',
    '--autoplay-policy=no-user-gesture-required', '--disable-breakpad',
    '--proxy-server=http://127.0.0.1:9', '--proxy-bypass-list=127.0.0.1;localhost',
    '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1', 'about:blank',
  ], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
  let launchError;
  browser.on('error', error => { launchError = error; });
  browser.stderr.on('data', chunk => { browserStderr += chunk.toString(); });
  let debuggingPort;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (launchError) throw launchError;
    try {
      debuggingPort = Number((await readFile(join(profilePath, 'DevToolsActivePort'), 'utf8')).split('\n')[0]);
      break;
    } catch { await delay(100); }
  }
  if (!debuggingPort) throw new Error('Chrome debugging endpoint did not initialize');
  const target = await (await fetch(`http://127.0.0.1:${debuggingPort}/json/new?about:blank`, { method: 'PUT' })).json();
  websocket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolveOpen, rejectOpen) => {
    websocket.addEventListener('open', resolveOpen, { once: true });
    websocket.addEventListener('error', rejectOpen, { once: true });
  });
  websocket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const callbacks = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) callbacks.reject(new Error(JSON.stringify(message.error)));
      else callbacks.resolve(message.result);
    }
    if (message.method === 'Fetch.requestPaused') {
      const { requestId, request } = message.params;
      const allowed = request.url.startsWith(`${baseUrl}/`) || request.url === streamArgument || request.url === pageArgument || (pageArgument && request.url === new URL('/favicon.ico', pageArgument).href);
      if (!allowed) results.blockedExternalRequests.push(request.url);
      command(allowed ? 'Fetch.continueRequest' : 'Fetch.failRequest',
        allowed ? { requestId } : { requestId, errorReason: 'BlockedByClient' }).catch(() => {});
    }
    if (message.method === 'Network.responseReceived') {
      const {response} = message.params;
      if (response.url === streamArgument || response.url === `${baseUrl}/clip.mp4`) {
        results.browserHttp.push({url: response.url, status: response.status, headers: response.headers});
      }
    }
  });
  results.browserVersion = await command('Browser.getVersion');
  await command('Page.enable');
  await command('Runtime.enable');
  await command('Network.enable');
  await command('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
  await command('Emulation.setDeviceMetricsOverride', { width: 1000, height: 400, deviceScaleFactor: 1, mobile: false });
  results.navigation = await command('Page.navigate', { url: pageArgument ?? baseUrl });
  if (results.navigation.errorText) throw new Error(results.navigation.errorText);
  await evaluate(`new Promise(async resolveLoad => {
    for (let attempt = 0; attempt < 70; attempt += 1) {
      const video = document.getElementById('clip');
      if (video && (video.error || video.readyState >= 2)) {resolveLoad(true); return;}
      await new Promise(resolveDelay => setTimeout(resolveDelay, 100));
    }
    resolveLoad(false);
  })`);
  results.page = await evaluate(`({url: location.href, readyState: document.readyState, hasVideo: Boolean(document.getElementById('clip'))})`);
  if (!results.page.hasVideo) throw new Error('The local verification page did not load');
  results.initial = await evaluate(snapshot);
  results.initialFrame = results.initial.width > 0 ? await evaluate(frameProbe) : {minimum: 0, maximum: 0, checksum: null};
  results.checks.initialDisplay = results.initialFrame.maximum > results.initialFrame.minimum && results.initial.decodedFrames > 0;
  results.checks.metadata = results.initial.width === 1920 && results.initial.height === 480 && Math.abs(results.initial.duration - 8) < 0.05;
  results.initialEvents = await evaluate('window.videoEvents');
  results.checks.loadedmetadata = results.initialEvents.some(event => event.event === 'loadedmetadata');
  const firstScreenshot = await command('Page.captureScreenshot', { format: 'png' });
  await writeFile(join(evidencePath, 'browser-first.png'), Buffer.from(firstScreenshot.data, 'base64'), { flag: 'wx' });
  results.playAttempt = await evaluate(`document.getElementById('clip').play().then(() => ({started: true})).catch(error => ({started: false, name: error.name, message: error.message}))`);
  if (!results.initial.error && results.playAttempt.started) {
    await delay(600);
    results.playing = await evaluate(snapshot);
    await evaluate(`document.getElementById('clip').pause()`);
    results.paused = await evaluate(snapshot);
    await delay(400);
    results.pauseAfterWait = await evaluate(snapshot);
    results.checks.play = results.playing.currentTime > results.initial.currentTime && results.playing.decodedFrames > 0;
    results.checks.pause = results.paused.paused && results.pauseAfterWait.paused && results.paused.currentTime === results.pauseAfterWait.currentTime;
    results.seeks = [];
    for (const seconds of [0, 2, 4, 6, 7.9]) results.seeks.push(await seek(seconds));
    results.checks.seeks = results.seeks.every(outcome => outcome.seekingSeen && outcome.seekedSeen && Math.abs(outcome.time - outcome.requestedTime) < 0.05 && outcome.frame.maximum > outcome.frame.minimum && !outcome.state.error);
    results.checks.seekFrameUpdates = new Set(results.seeks.map(outcome => outcome.frame.checksum)).size === results.seeks.length;
    await evaluate(`document.getElementById('clip').play()`);
    await delay(700);
    results.ending = await evaluate(snapshot);
    results.checks.ended = results.ending.ended;
    await seek(7.8);
    await evaluate(`document.getElementById('clip').loop = true; document.getElementById('clip').play()`);
    await delay(700);
    results.looping = await evaluate(snapshot);
    results.checks.loop = results.looping.currentTime < 1 && !results.looping.ended;
    await evaluate(`document.getElementById('clip').pause()`);
    results.pixelProbe = await evaluate(frameProbe);
    results.checks.display = results.pixelProbe.maximum > results.pixelProbe.minimum;
    results.events = await evaluate('window.videoEvents');
    results.checks.playingEvent = results.events.some(event => event.event === 'playing');
    results.checks.endedEvent = results.events.some(event => event.event === 'ended');
    results.checks.secondPlayback = results.events.filter(event => event.event === 'playing').length >= 2 && results.looping.decodedFrames > results.ending.decodedFrames;
    results.checks.noDecodeErrors = !results.looping.error && !results.events.some(event => event.event === 'error');
    const invalidRange = await fetch(streamArgument ?? `${baseUrl}/clip.mp4`, {headers: {Range: `bytes=${videoSize}-`}});
    results.invalidRange = {status: invalidRange.status, contentRange: invalidRange.headers.get('content-range'), client: 'Node fetch, not browser'};
    await invalidRange.arrayBuffer();
    results.checks.http416 = results.invalidRange.status === 416;
    results.status = Object.values(results.checks).every(Boolean) ? 'BROWSER_PASS' : 'BROWSER_FAIL';
  } else {
    results.status = 'BROWSER_FAIL';
    results.notTested = ['display', 'currentTime progression', 'pause', 'middle seek', 'last seek', 'ended', 'loop'];
  }
  const screenshot = await command('Page.captureScreenshot', { format: 'png' });
  await writeFile(join(evidencePath, 'browser.png'), Buffer.from(screenshot.data, 'base64'), { flag: 'wx' });
} catch (error) {
  results.harnessError = { name: error.name, message: error.message };
} finally {
  if (websocket && websocket.readyState === WebSocket.OPEN) {
    await command('Browser.close').catch(() => {});
    websocket.close();
  }
  if (browser && browser.exitCode === null) {
    await Promise.race([new Promise(resolveExit => browser.once('exit', resolveExit)), delay(3000)]);
    if (browser.exitCode === null) browser.kill();
  }
  results.browserProcessExited = !browser || browser.exitCode !== null;
  server.closeAllConnections();
  await new Promise(resolveClose => server.close(resolveClose));
  results.localServerClosed = !server.listening;
  await writeFile(join(evidencePath, 'browser_stderr.txt'), browserStderr, { flag: 'wx' });
  await writeFile(resultPath, JSON.stringify(results, null, 2), { flag: 'wx' });
}
console.log(JSON.stringify(results, null, 2));
