import { createHash, randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.dirname(frontend);
const output = path.join(root, 'data/outputs/playwright-readonly',
  `${new Date().toISOString().replace(/[:.]/g, '-')}-${randomUUID().slice(0, 8)}`);
mkdirSync(output, { recursive: true });
const save = (name, value) => writeFileSync(path.join(output, name), JSON.stringify(value, null, 2), { flag: 'wx' });
console.log(`Evidence: ${output}`);

async function get(relative) {
  const response = await fetch(`http://127.0.0.1:8000${relative}`, { signal: AbortSignal.timeout(5_000), redirect: 'error' });
  if (!response.ok) throw new Error(`PREFLIGHT_GET_FAILED:${relative}:${response.status}`);
  return response.json();
}

const protectedFiles = new Map();
const digest = filename => createHash('sha256').update(readFileSync(filename)).digest('hex');
try {
  const argumentsList = process.argv.slice(2);
  if (argumentsList.length && (argumentsList.length !== 2 || argumentsList[0] !== '--grep'
    || !['TC-01', 'TC-0[45]'].includes(argumentsList[1]))) {
    throw new Error('Only the optional filters --grep TC-01 and --grep TC-0[45] are supported');
  }
  const frontendResponse = await fetch('http://localhost:5173/', { signal: AbortSignal.timeout(5_000), redirect: 'error' });
  if (!frontendResponse.ok) throw new Error(`FRONTEND_NOT_RUNNING:${frontendResponse.status}`);
  const health = await get('/health');
  if (health.status !== 'ok') throw new Error('BACKEND_NOT_HEALTHY');
  const catalog = await get('/videos');
  const videos = catalog.videos.filter(video => video.video_id === 'VID-000003');
  if (videos.length !== 1) throw new Error('ABORT_WRONG_VIDEO:VID-000003_NOT_UNIQUE');
  const video = videos[0];
  for (const [field, expected] of Object.entries({ width: 1920, height: 480, fps: 30, frame_count: 480, duration_seconds: 16 })) {
    if (video[field] !== expected) throw new Error(`ABORT_WRONG_VIDEO:${field}`);
  }
  if (video.source_revision !== 'bcdf19620579a60b4d7211f6cb7e2db948336b240b0ac78114c18bb2359ef7d5') {
    throw new Error('ABORT_WRONG_VIDEO:SHA256');
  }
  const capturesDirectory = path.join(root, 'data/outputs/captures');
  const captures = existsSync(capturesDirectory) ? readdirSync(capturesDirectory).filter(name => name.endsWith('.png')) : [];
  const state = process.env.VISION_E2E_STORAGE_STATE;
  if (state) {
    const allowedDirectory = path.join(frontend, 'playwright/.auth') + path.sep;
    if (!path.resolve(state).startsWith(allowedDirectory) || !existsSync(state)) throw new Error('AUTH_STATE_MUST_BE_USER_SUPPLIED_IN_PLAYWRIGHT_AUTH');
    if (captures.length) throw new Error('SESSION_READS_BLOCKED:AUTHORIZE_MAY_CLEAN_UP_EXISTING_CAPTURE_PNG');
  }
  const recordsPath = path.join(root, 'data/inspections.jsonl');
  const records = readFileSync(recordsPath, 'utf8').split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line));
  const requested = process.env.VISION_E2E_INSPECTION_ID || 'INSP-001694';
  if (!/^INSP-\d{6,}$/.test(requested)) throw new Error('INVALID_INSPECTION_ID');
  const matches = records.filter(record => record.inspection_id === requested);
  if (matches.length > 1) throw new Error('DUPLICATE_INSPECTION_ID');
  const record = matches[0] ?? null;
  const recent = await get('/inspections?limit=100');
  const publicCandidates = recent.inspections.filter(item => item.metrics?.input_source !== 'LIVEVIEW_GRAB'
    && item.metrics?.model?.inference_source !== 'MOCK' && item.inspection_id !== 'INSP-001391'
    && item.anomaly_score !== null && item.provenance !== 'RECORDED_TEST_FIXTURE');
  let publicRecord = null;
  const publicDataErrors = [];
  for (const candidate of publicCandidates) {
    const response = await fetch(`http://127.0.0.1:8000/inspections/${candidate.inspection_id}/anomaly-map`,
      { signal: AbortSignal.timeout(5_000), redirect: 'error' });
    if (response.status === 404) continue;
    if (!response.ok) { publicDataErrors.push({ inspection_id:candidate.inspection_id, status:response.status }); continue; }
    const metadata = await response.json();
    if (metadata.inspection_id === candidate.inspection_id && metadata.available !== false && metadata.localization_available) {
      publicRecord = candidate;
      break;
    }
  }
  const candidates = [recordsPath, path.join(root, 'data/inspection_logs.jsonl'),
    path.join(root, 'data/outputs/videos/bottle_conveyor_mixed_ok_ng_16s_h264_1920x480.mp4'),
    ...captures.map(name => path.join(capturesDirectory, name))];
  if (record && /^IMG-GRAB-[a-f0-9]{32}$/.test(record.image_id)) {
    candidates.push(path.join(root, `data/outputs/grab_inspection_inputs/${record.image_id}.png`));
  }
  for (const filename of candidates) if (existsSync(filename)) protectedFiles.set(filename, digest(filename));
  save('preflight.json', { frontend: 'http://localhost:5173', backend: 'http://127.0.0.1:8000', video,
    requestedInspection: record ? { inspection_id: record.inspection_id, image_id: record.image_id,
      source: record.metrics?.input_source, mean: record.metrics?.mean } : null,
    requestedId: requested, publicInspectionId: publicRecord?.inspection_id ?? null,
    publicDataErrors,
    authenticatedSessionProvided: !!state, protectedFileCount: protectedFiles.size,
    policy: 'No server lifecycle commands; no response mocking; GET/HEAD only; session bootstrap blocked; no raw headers/HAR/trace' });
  const child = spawn(process.execPath, [path.join(frontend, 'node_modules/@playwright/test/cli.js'),
    'test', '--config', 'playwright.readonly.config.mjs', ...argumentsList], { cwd: frontend,
    env: { ...process.env, VISION_E2E_OUTPUT: output }, stdio: 'inherit', windowsHide: true });
  const exitCode = await new Promise((resolve, reject) => { child.once('error', reject); child.once('exit', code => resolve(code ?? 1)); });
  process.exitCode = exitCode;
} catch (error) {
  save('blocked.json', { status: 'BLOCKED', reason: error.message });
  console.error(error.message);
  process.exitCode = 1;
} finally {
  const files = [...protectedFiles].map(([filename, before]) => {
    const after = existsSync(filename) ? digest(filename) : null;
    return { path: path.relative(root, filename), before, after, unchanged: before === after };
  });
  save('protection.json', { scope: 'Inspection/log JSONL, selected saved Crop, VID-000003 and existing Capture PNG; not a full asset audit',
    files, unchanged: files.every(file => file.unchanged) });
  if (files.some(file => !file.unchanged)) { console.error('PROTECTED_DATA_CHANGED'); process.exitCode = 1; }
}
