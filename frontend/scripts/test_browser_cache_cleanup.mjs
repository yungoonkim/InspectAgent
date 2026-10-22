import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { link, mkdir, mkdtemp, readFile, rename, rm, symlink, unlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { CHROME_CACHE_PATHS, createOwnedBrowserRun, watchOwnedBrowser, finishOwnedBrowser,
  cleanupOwnedBrowserCaches, createCacheCleaner } from './browser_cache_cleanup.mjs';

async function fixture(context) {
  const temporary = await mkdtemp(path.join(tmpdir(), 'visioninsight-cache-test-'));
  context.after(async () => {
    assert.equal(path.dirname(path.resolve(temporary)), path.resolve(tmpdir()));
    assert.ok(path.basename(temporary).startsWith('visioninsight-cache-test-'));
    await rm(temporary, { recursive: true });
  });
  const scope = await createOwnedBrowserRun(temporary);
  const browser = new EventEmitter();
  browser.pid = 12345;
  browser.spawnargs = ['FAKE_BROWSER', `--user-data-dir=${scope.profileDirectory}`];
  browser.kill = () => assert.fail('Cleanup must never kill a browser');
  watchOwnedBrowser(scope, browser);
  const evidence = { status: 'PASS', passed: 1, failed: 0, skipped: 0, evidencePath: scope.directory };
  await writeFile(path.join(scope.directory, 'result.json'), JSON.stringify(evidence));
  await writeFile(path.join(scope.directory, 'browser-stderr.txt'), 'FAKE TEST');
  await writeFile(path.join(scope.directory, 'synthetic-imageview.png'), 'FAKE SCREENSHOT');
  for (const relative of CHROME_CACHE_PATHS) {
    await mkdir(path.join(scope.directory, relative), { recursive: true });
    await writeFile(path.join(scope.directory, relative, 'cache-data'), 'FAKE CACHE');
  }
  const protectedPaths = ['backend.xml', 'pytest.log', 'summary.json', 'safety.json', 'protection.json',
    'protected-before.json', 'inspection.jsonl', 'IMG-GRAB-synthetic.png', 'IMG-GRAB-synthetic.json',
    'chrome-profile/Default/Cookies', 'chrome-profile/Default/History',
    'chrome-profile/Default/Sessions/session_1', 'chrome-profile/Default/Preferences',
    'chrome-profile/Crashpad/report.dmp'];
  for (const relative of protectedPaths) {
    await mkdir(path.dirname(path.join(scope.directory, relative)), { recursive: true });
    await writeFile(path.join(scope.directory, relative), `PROTECTED ${relative}`);
  }
  const protectedBytes = new Map();
  for (const relative of [...protectedPaths, 'result.json', 'browser-stderr.txt', 'synthetic-imageview.png']) {
    protectedBytes.set(relative, await readFile(path.join(scope.directory, relative)));
  }
  return { temporary, scope, browser, evidence, protectedBytes,
    exit: (code = 0, signal = null) => browser.emit('exit', code, signal) };
}

async function assertPreserved(view) {
  for (const [relative, bytes] of view.protectedBytes) {
    assert.deepEqual(await readFile(path.join(view.scope.directory, relative)), bytes);
  }
}

test('normal exit removes only exact Chrome caches and preserves evidence and profile state', async context => {
  const view = await fixture(context);
  view.exit();
  const originalExitCode = process.exitCode;
  const result = await cleanupOwnedBrowserCaches(view.scope);
  assert.equal(result.status, 'SUCCESS');
  assert.equal(result.removedFiles, CHROME_CACHE_PATHS.length);
  assert.equal(result.reclaimedBytes, CHROME_CACHE_PATHS.length * Buffer.byteLength('FAKE CACHE'));
  for (const relative of CHROME_CACHE_PATHS) {
    await assert.rejects(readFile(path.join(view.scope.directory, relative, 'cache-data')), { code: 'ENOENT' });
  }
  await assertPreserved(view);
  assert.equal(process.exitCode, originalExitCode);
});

test('failed test retains all caches even after a normal browser exit', async context => {
  const view = await fixture(context);
  view.exit();
  const failed = { ...view.evidence, status: 'FAIL', failed: 1 };
  await writeFile(path.join(view.scope.directory, 'result.json'), JSON.stringify(failed));
  const result = await cleanupOwnedBrowserCaches(view.scope);
  assert.equal(result.reason, 'TEST_NOT_SUCCESSFUL');
  assert.equal(result.removedFiles, 0);
  assert.equal(await readFile(path.join(view.scope.directory, CHROME_CACHE_PATHS[0], 'cache-data'), 'utf8'), 'FAKE CACHE');
  assert.deepEqual(JSON.parse(await readFile(path.join(view.scope.directory, 'result.json'), 'utf8')), failed);
});

test('active browser and unconfirmed timeout never permit cleanup or force termination', async context => {
  const view = await fixture(context);
  assert.equal((await cleanupOwnedBrowserCaches(view.scope)).status, 'SKIPPED');
  const result = await finishOwnedBrowser(view.scope, () => Promise.reject(new Error('FAKE CDP FAILURE')), 1);
  assert.equal(result.exited, false);
  assert.equal(result.reason, 'BROWSER_EXIT_UNCONFIRMED');
  assert.equal((await cleanupOwnedBrowserCaches(view.scope)).removedFiles, 0);
  await assertPreserved(view);
});

test('graceful close waits for the watched owned process exit', async context => {
  const view = await fixture(context);
  const result = await finishOwnedBrowser(view.scope, () => view.exit(), 100);
  assert.deepEqual(result, { exited: true, code: 0, signal: null });
  assert.equal((await cleanupOwnedBrowserCaches(view.scope)).status, 'SUCCESS');
});

for (const [label, code, signal] of [['crash', 1, null], ['signal', null, 'SIGTERM']]) {
  test(`${label} exit preserves caches`, async context => {
    const view = await fixture(context);
    view.exit(code, signal);
    assert.equal((await cleanupOwnedBrowserCaches(view.scope)).status, 'SKIPPED');
    await assertPreserved(view);
  });
}

test('process error cannot be disguised by a subsequent zero exit', async context => {
  const view = await fixture(context);
  view.browser.emit('error', new Error('FAKE PROCESS ERROR'));
  view.exit();
  assert.equal((await cleanupOwnedBrowserCaches(view.scope)).status, 'SKIPPED');
});

test('parent paths, forged scopes and historical directories are rejected', async context => {
  const view = await fixture(context);
  view.exit();
  for (const candidate of [{ directory: view.temporary }, { ...view.scope },
    { directory: path.join(view.temporary, '../outside') }]) {
    assert.equal((await cleanupOwnedBrowserCaches(candidate)).reason, 'RUN_NOT_OWNED');
  }
  await assertPreserved(view);
});

test('another test run stays untouched', async context => {
  const view = await fixture(context);
  const other = await createOwnedBrowserRun(view.temporary);
  await mkdir(path.join(other.directory, CHROME_CACHE_PATHS[0]), { recursive: true });
  const otherFile = path.join(other.directory, CHROME_CACHE_PATHS[0], 'other-cache');
  await writeFile(otherFile, 'OTHER RUN');
  view.exit();
  assert.equal((await cleanupOwnedBrowserCaches(view.scope)).status, 'SUCCESS');
  assert.equal(await readFile(otherFile, 'utf8'), 'OTHER RUN');
});

test('junction or symbolic directory link blocks cleanup without following its target', async context => {
  const view = await fixture(context);
  const cache = path.join(view.scope.directory, CHROME_CACHE_PATHS[0]);
  await unlink(path.join(cache, 'cache-data'));
  await rm(cache);
  const external = path.join(view.temporary, 'other-owned-fixture');
  await mkdir(external);
  await writeFile(path.join(external, 'must-stay'), 'LINK TARGET');
  await symlink(external, cache, process.platform === 'win32' ? 'junction' : 'dir');
  view.exit();
  assert.equal((await cleanupOwnedBrowserCaches(view.scope)).reason, 'LINK_PATH_REJECTED');
  assert.equal(await readFile(path.join(external, 'must-stay'), 'utf8'), 'LINK TARGET');
  await assertPreserved(view);
});

test('replaced run directory fails ownership verification', async context => {
  const view = await fixture(context);
  const renamed = view.scope.directory + '-original';
  await rename(view.scope.directory, renamed);
  await mkdir(view.scope.directory);
  view.exit();
  assert.equal((await cleanupOwnedBrowserCaches(view.scope)).reason, 'RUN_REPLACED');
  assert.equal(await readFile(path.join(renamed, CHROME_CACHE_PATHS[0], 'cache-data'), 'utf8'), 'FAKE CACHE');
});

test('hardlinked cache file is preserved', async context => {
  const view = await fixture(context);
  const cacheFile = path.join(view.scope.directory, CHROME_CACHE_PATHS[0], 'cache-data');
  await link(cacheFile, path.join(view.temporary, 'outside-hardlink'));
  view.exit();
  assert.equal((await cleanupOwnedBrowserCaches(view.scope)).reason, 'NONREGULAR_OR_HARDLINK_REJECTED');
  assert.equal(await readFile(cacheFile, 'utf8'), 'FAKE CACHE');
});

test('protected evidence accidentally inside cache blocks the complete cleanup plan', async context => {
  const view = await fixture(context);
  await writeFile(path.join(view.scope.directory, CHROME_CACHE_PATHS[0], 'result.json'), 'EVIDENCE');
  view.exit();
  const result = await cleanupOwnedBrowserCaches(view.scope);
  assert.equal(result.reason, 'PROTECTED_FILE_IN_CACHE');
  assert.equal(result.removedFiles, 0);
  await assertPreserved(view);
});

test('missing or invalid evidence never enables cleanup', async context => {
  const view = await fixture(context);
  view.exit();
  await unlink(path.join(view.scope.directory, 'synthetic-imageview.png'));
  assert.equal((await cleanupOwnedBrowserCaches(view.scope)).status, 'SKIPPED');
  await writeFile(path.join(view.scope.directory, 'synthetic-imageview.png'), 'FAKE SCREENSHOT');
  await writeFile(path.join(view.scope.directory, 'result.json'), 'invalid');
  assert.equal((await cleanupOwnedBrowserCaches(view.scope)).removedFiles, 0);
});

test('unregistered browser or different profile is rejected', async context => {
  const view = await fixture(context);
  const other = await createOwnedBrowserRun(view.temporary);
  assert.throws(() => watchOwnedBrowser(other, view.browser), /BROWSER_NOT_OWNED/);
  assert.equal((await cleanupOwnedBrowserCaches(other)).reason, 'NORMAL_BROWSER_EXIT_NOT_CONFIRMED');
});

test('shared or still-running Vite cache is preserved', async context => {
  const view = await fixture(context);
  const shared = path.join(view.temporary, 'shared-vite');
  await mkdir(shared);
  await writeFile(path.join(shared, 'bundle.js'), 'SHARED');
  view.exit();
  for (const options of [{ includeVite: true, viteClosed: false, viteCacheDirectory: view.scope.viteCacheDirectory },
    { includeVite: true, viteClosed: true, viteCacheDirectory: shared }]) {
    assert.equal((await cleanupOwnedBrowserCaches(view.scope, options)).reason, 'VITE_OWNERSHIP_OR_EXIT_UNCONFIRMED');
  }
  assert.equal(await readFile(path.join(shared, 'bundle.js'), 'utf8'), 'SHARED');
});

test('only a future owned and closed Vite cache can be removed', async context => {
  const view = await fixture(context);
  await mkdir(view.scope.viteCacheDirectory);
  await writeFile(path.join(view.scope.viteCacheDirectory, 'bundle.js'), 'FAKE VITE');
  view.exit();
  assert.equal((await cleanupOwnedBrowserCaches(view.scope, { includeVite: true, viteClosed: true,
    viteCacheDirectory: view.scope.viteCacheDirectory })).removedFiles, 9);
  await assertPreserved(view);
});

test('already removed caches can be cleaned again without force or errors', async context => {
  const view = await fixture(context);
  view.exit();
  assert.equal((await cleanupOwnedBrowserCaches(view.scope)).status, 'SUCCESS');
  const repeated = await cleanupOwnedBrowserCaches(view.scope);
  assert.equal(repeated.status, 'SUCCESS');
  assert.equal(repeated.removedFiles, 0);
});

test('partial deletion failure stops further work and reports only actual removed bytes', async context => {
  const view = await fixture(context);
  view.exit();
  let calls = 0;
  const cleaner = createCacheCleaner({ removeFile: async target => {
    calls++;
    if (calls === 2) throw Object.assign(new Error('FAKE PERMISSION FAILURE'), { code: 'EACCES' });
    await unlink(target);
  } });
  const originalExitCode = process.exitCode;
  const result = await cleaner(view.scope);
  assert.equal(result.status, 'FAILED');
  assert.equal(result.reason, 'EACCES');
  assert.equal(result.removedFiles, 1);
  assert.equal(result.reclaimedBytes, Buffer.byteLength('FAKE CACHE'));
  assert.equal(calls, 2);
  assert.equal(process.exitCode, originalExitCode);
  await assertPreserved(view);
});

test('harness saves evidence before cleanup and does not force-kill an uncertain process', async () => {
  const source = await readFile(new URL('./test_step4_browser.mjs', import.meta.url), 'utf8');
  assert.ok(source.indexOf("await writeFile(path.join(summary.evidencePath, 'result.json')")
    < source.indexOf('cleanup = await cleanupOwnedBrowserCaches'));
  assert.ok(source.indexOf('await finishOwnedBrowser') < source.indexOf('cdp?.close()'));
  assert.ok(source.includes('viteCacheDirectory: ownedRun.viteCacheDirectory'));
  assert.ok(!source.includes('browser.kill('));
});
