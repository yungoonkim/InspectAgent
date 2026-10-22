import { lstat, mkdir, mkdtemp, readFile, readdir, realpath, rmdir, unlink } from 'node:fs/promises';
import path from 'node:path';

export const CHROME_CACHE_PATHS = Object.freeze([
  'chrome-profile/Default/Cache', 'chrome-profile/Default/Code Cache',
  'chrome-profile/Default/GPUCache', 'chrome-profile/Default/DawnWebGPUCache',
  'chrome-profile/Default/DawnGraphiteCache', 'chrome-profile/ShaderCache',
  'chrome-profile/GrShaderCache', 'chrome-profile/GPUPersistentCache/DawnGraphiteCache',
]);

const ownedRuns = new WeakMap();
const canonical = value => process.platform === 'win32' ? path.resolve(value).toLowerCase() : path.resolve(value);
const failure = code => Object.assign(new Error(code), { code });
const identityMatches = (before, after) => before.dev === after.dev && before.ino === after.ino;

async function ordinaryPath(target, missingAllowed = false) {
  const absolute = path.resolve(target);
  const ancestors = [];
  for (let cursor = absolute; ; cursor = path.dirname(cursor)) {
    ancestors.unshift(cursor);
    if (path.dirname(cursor) === cursor) break;
  }
  let information;
  for (const ancestor of ancestors) {
    try { information = await lstat(ancestor, { bigint: true }); }
    catch (error) { if (missingAllowed && error.code === 'ENOENT') return null; throw error; }
    if (information.isSymbolicLink()) throw failure('LINK_PATH_REJECTED');
  }
  if (canonical(await realpath(absolute)) !== canonical(absolute)) throw failure('REDIRECTED_PATH_REJECTED');
  if (!information.isDirectory() && (!information.isFile() || information.nlink !== 1n)) {
    throw failure('NONREGULAR_OR_HARDLINK_REJECTED');
  }
  return information;
}

async function verifiedRun(scope) {
  const record = ownedRuns.get(scope);
  if (!record) throw failure('RUN_NOT_OWNED');
  const information = await ordinaryPath(scope.directory);
  if (!information.isDirectory() || !identityMatches(record.identity, information)) throw failure('RUN_REPLACED');
  return record;
}

export async function createOwnedBrowserRun(outputRoot) {
  const root = path.resolve(outputRoot);
  await ordinaryPath(root, true);
  await mkdir(root, { recursive: true });
  await ordinaryPath(root);
  const directory = await mkdtemp(path.join(root, 'step4-browser-'));
  const scope = Object.freeze({ directory, profileDirectory: path.join(directory, 'chrome-profile'),
    viteCacheDirectory: path.join(directory, 'vite-cache') });
  ownedRuns.set(scope, { identity: await ordinaryPath(directory), browser: null });
  return scope;
}

export function watchOwnedBrowser(scope, browser) {
  const record = ownedRuns.get(scope);
  if (!record || record.browser || !browser.spawnargs?.includes(`--user-data-dir=${scope.profileDirectory}`)) {
    throw failure('BROWSER_NOT_OWNED');
  }
  const watched = { process: browser, outcome: null, promise: null, errored: false };
  watched.promise = new Promise(resolve => {
    browser.once('exit', (code, signal) => {
      watched.outcome = { exited: true, code, signal };
      resolve(watched.outcome);
    });
    browser.once('error', () => {
      watched.errored = true;
      watched.outcome = { exited: false, reason: 'BROWSER_PROCESS_ERROR' };
      resolve(watched.outcome);
    });
  });
  record.browser = watched;
}

export async function finishOwnedBrowser(scope, requestClose, timeoutMs = 3000) {
  const record = ownedRuns.get(scope);
  if (!record?.browser) return { exited: false, reason: 'BROWSER_NOT_STARTED' };
  if (record.browser.outcome) return record.browser.outcome;
  let timer;
  try {
    if (requestClose) void Promise.resolve().then(requestClose).catch(() => {});
    return await Promise.race([record.browser.promise, new Promise(resolve => {
      timer = setTimeout(() => resolve({ exited: false, reason: 'BROWSER_EXIT_UNCONFIRMED' }), timeoutMs);
    })]);
  } finally { clearTimeout(timer); }
}

const protectedName = name => /^(IMG-GRAB-|INSP-|RIG-)/i.test(name)
  || /^(summary|safety|protection|protected-before|result|manifest|state)\.json$/i.test(name)
  || /^(Cookies|History|Sessions|Preferences|Local State)$/i.test(name)
  || /\.(png|jpe?g|xml|jsonl|npz|ckpt|log|webm|zip)$/i.test(name);

async function cachePlan(scope, relative) {
  const target = path.resolve(scope.directory, relative);
  if (!target.startsWith(scope.directory + path.sep) || ![...CHROME_CACHE_PATHS, 'vite-cache'].includes(relative)) {
    throw failure('CACHE_PATH_REJECTED');
  }
  const information = await ordinaryPath(target, true);
  if (!information) return { target, files: [], directories: [] };
  if (!information.isDirectory()) throw failure('CACHE_DIRECTORY_REQUIRED');
  const files = [];
  const directories = [];
  const pending = [target];
  while (pending.length) {
    const directory = pending.pop();
    const directoryInfo = await ordinaryPath(directory);
    directories.push({ path: directory, information: directoryInfo });
    for (const name of await readdir(directory)) {
      if (protectedName(name)) throw failure('PROTECTED_FILE_IN_CACHE');
      const entry = path.join(directory, name);
      const entryInfo = await ordinaryPath(entry);
      if (entryInfo.isDirectory()) pending.push(entry);
      else {
        if (entryInfo.size > BigInt(Number.MAX_SAFE_INTEGER)) throw failure('CACHE_SIZE_UNSUPPORTED');
        files.push({ path: entry, information: entryInfo });
      }
    }
  }
  directories.sort((left, right) => right.path.length - left.path.length);
  return { target, files, directories };
}

export function createCacheCleaner({ removeFile = unlink, removeDirectory = rmdir } = {}) {
  return async function cleanup(scope, { includeVite = false, viteClosed = false, viteCacheDirectory = null } = {}) {
    const result = { status: 'SKIPPED', reason: null, removedFiles: 0, removedDirectories: 0, reclaimedBytes: 0 };
    let deleting = false;
    try {
      const record = await verifiedRun(scope);
      if (!record.browser?.outcome?.exited || record.browser.errored
        || record.browser.outcome.code !== 0 || record.browser.outcome.signal !== null) {
        return { ...result, reason: 'NORMAL_BROWSER_EXIT_NOT_CONFIRMED' };
      }
      for (const name of ['result.json', 'browser-stderr.txt', 'synthetic-imageview.png']) {
        const information = await ordinaryPath(path.join(scope.directory, name));
        if (!information.isFile()) throw failure('EVIDENCE_NOT_SAVED');
      }
      const evidence = JSON.parse(await readFile(path.join(scope.directory, 'result.json'), 'utf8'));
      if (evidence.status !== 'PASS' || evidence.failed !== 0 || !(evidence.passed > 0)
        || canonical(evidence.evidencePath) !== canonical(scope.directory)) {
        return { ...result, reason: 'TEST_NOT_SUCCESSFUL' };
      }
      if (includeVite && (!viteClosed || viteCacheDirectory !== scope.viteCacheDirectory)) {
        return { ...result, reason: 'VITE_OWNERSHIP_OR_EXIT_UNCONFIRMED' };
      }
      const plans = [];
      for (const relative of [...CHROME_CACHE_PATHS, ...(includeVite ? ['vite-cache'] : [])]) {
        plans.push(await cachePlan(scope, relative));
      }
      deleting = true;
      for (const plan of plans) {
        for (const entry of plan.files) {
          await verifiedRun(scope);
          const current = await ordinaryPath(entry.path);
          if (!identityMatches(entry.information, current) || current.size !== entry.information.size
            || current.mtimeNs !== entry.information.mtimeNs) throw failure('CACHE_CHANGED');
          await removeFile(entry.path);
          result.removedFiles++;
          result.reclaimedBytes += Number(entry.information.size);
        }
        for (const entry of plan.directories) {
          await verifiedRun(scope);
          const current = await ordinaryPath(entry.path);
          if (!identityMatches(entry.information, current)) throw failure('CACHE_CHANGED');
          await removeDirectory(entry.path);
          result.removedDirectories++;
        }
      }
      return { ...result, status: 'SUCCESS' };
    } catch (error) {
      return { ...result, status: deleting ? 'FAILED' : 'SKIPPED', reason: error.code ?? 'CACHE_CHECK_FAILED' };
    }
  };
}

export const cleanupOwnedBrowserCaches = createCacheCleaner();
