import { createHash, randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { existingCaptureFiles, requireCaptureApproval, requireEmptyCaptureDirectory } from '../playwright/capturePolicy.mjs';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.dirname(frontend);
const output = path.join(root, 'data/outputs/playwright-capture-edge-gv',
  `${new Date().toISOString().replace(/[:.]/g, '-')}-${randomUUID().slice(0, 8)}`);
mkdirSync(output, { recursive:true });
const save = (name, value) => writeFileSync(path.join(output, name), JSON.stringify(value, null, 2), { flag:'wx' });
const digest = filename => createHash('sha256').update(readFileSync(filename)).digest('hex');
const protectedFiles = new Map();
const capturesDirectory = path.join(root, 'data/outputs/captures');
console.log(`Evidence: ${output}`);
try {
  requireCaptureApproval(process.argv.slice(2));
  for (const [url, json] of [['http://localhost:5173/', false], ['http://127.0.0.1:8000/health', true]]) {
    const response = await fetch(url, { signal:AbortSignal.timeout(5_000), redirect:'error' });
    if (!response.ok || (json && (await response.json()).status !== 'ok')) throw new Error('EXISTING_SERVER_UNAVAILABLE');
  }
  const entries = existingCaptureFiles(capturesDirectory);
  const paths = ['data/inspections.jsonl', 'data/inspection_logs.jsonl',
    'data/outputs/videos/bottle_conveyor_mixed_ok_ng_16s_h264_1920x480.mp4'].map(relative => path.join(root, relative));
  for (const name of entries) paths.push(path.join(capturesDirectory, name));
  for (const filename of paths) if (existsSync(filename)) protectedFiles.set(filename, digest(filename));
  save('capture-preservation.json', { existingFiles:entries, action:'No session bootstrap or Grab before preservation gate',
    runtimeExpiry:'UNKNOWN: live expiry is memory-only; Capture authorize/bootstrap calls cleanup',
    observedAt:new Date().toISOString() });
  requireEmptyCaptureDirectory(capturesDirectory);
  const response = await fetch('http://127.0.0.1:8000/videos', { signal:AbortSignal.timeout(5_000), redirect:'error' });
  if (!response.ok) throw new Error('VIDEO_CATALOG_UNAVAILABLE');
  const entriesForVideo = (await response.json()).videos.filter(video => video.video_id === 'VID-000003');
  if (entriesForVideo.length !== 1) throw new Error('WRONG_VIDEO');
  const video = entriesForVideo[0];
  if (video.width !== 1920 || video.height !== 480 || video.fps !== 30 || video.frame_count !== 480 || video.duration_seconds !== 16
    || video.source_revision !== 'bcdf19620579a60b4d7211f6cb7e2db948336b240b0ac78114c18bb2359ef7d5') throw new Error('WRONG_VIDEO');
  save('preflight.json', { video, maxGrabPosts:1, retries:0, maxSessionPosts:4, freshContext:true });
  const child = spawn(process.execPath, [path.join(frontend, 'node_modules/@playwright/test/cli.js'),
    'test', '--config', 'playwright.capture.config.mjs'], { cwd:frontend, windowsHide:true, stdio:'inherit',
    env:{ ...process.env, VISION_E2E_OUTPUT:output, VISION_E2E_ONE_CAPTURE_APPROVED:'true' } });
  process.exitCode = await new Promise((resolve, reject) => {
    child.once('error', reject); child.once('exit', code => resolve(code ?? 1));
  });
} catch (error) {
  save('blocked.json', { status:'BLOCKED', reason:error.message,
    tests:[{id:'TC-04',status:'BLOCKED'},{id:'TC-05',status:'BLOCKED'}], sessionPosts:0, grabPosts:0 });
  console.error(`BLOCKED: ${error.message}`);
  process.exitCode = 1;
} finally {
  const files = [...protectedFiles].map(([filename, before]) => {
    const after = existsSync(filename) ? digest(filename) : null;
    return { path:path.relative(root,filename), before, after, unchanged:before === after };
  });
  save('protection.json', { files, unchanged:files.every(file => file.unchanged) });
  if (files.some(file => !file.unchanged)) process.exitCode = 1;
}
