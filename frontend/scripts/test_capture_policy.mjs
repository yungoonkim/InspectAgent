import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, unlinkSync, rmdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { requireCaptureApproval, requireEmptyCaptureDirectory, createGrabBudget } from '../playwright/capturePolicy.mjs';

test('Capture command requires exactly the explicit one-Capture approval flag',()=>{
  for(const argumentsList of [[],['--approve'],['--approve-one-capture','--retry']]) {
    assert.throws(()=>requireCaptureApproval(argumentsList),/EXPLICIT_ONE_CAPTURE_APPROVAL_REQUIRED/);
  }
  assert.doesNotThrow(()=>requireCaptureApproval(['--approve-one-capture']));
});

test('preflight blocks existing managed or orphan data without deleting or altering it',()=>{
  const directory=mkdtempSync(path.join(tmpdir(),'visioninsight-capture-policy-'));
  const marker=path.join(directory,'.visioninsight-captures');
  const existing=path.join(directory,'old-capture.fixture');
  try{
    assert.doesNotThrow(()=>requireEmptyCaptureDirectory(directory));
    writeFileSync(marker,'ISOLATED UNIT TEST MARKER');
    assert.doesNotThrow(()=>requireEmptyCaptureDirectory(directory));
    writeFileSync(existing,'EXISTING DATA MUST REMAIN UNCHANGED');
    assert.throws(()=>requireEmptyCaptureDirectory(directory),/EXISTING_CAPTURE_TTL_DELETION_RISK/);
    assert.equal(readFileSync(existing,'utf8'),'EXISTING DATA MUST REMAIN UNCHANGED');
  }finally{
    unlinkSync(existing);unlinkSync(marker);rmdirSync(directory);
  }
});

test('Grab budget validates observed frame and source before allowing its one attempt',()=>{
  const budget=createGrabBudget('source-revision');
  assert.throws(()=>budget.claim({frame_index:42,source_revision:'source-revision'}),/GRAB_SOURCE_MISMATCH/);
  budget.select(42);
  for(const body of [{frame_index:43,source_revision:'source-revision'},
    {frame_index:42,source_revision:'other'}, {frame_index:42,source_revision:'source-revision',unsafe:true}]) {
    assert.throws(()=>budget.claim(body),/GRAB_SOURCE_MISMATCH/);
  }
  assert.equal(budget.attempts,0);
  budget.claim({frame_index:42,source_revision:'source-revision'});
  assert.equal(budget.attempts,1);
});

test('a failed or successful first Grab cannot be retried or reset by a second selection',()=>{
  const budget=createGrabBudget('source-revision');
  budget.select(479);budget.claim({frame_index:479,source_revision:'source-revision'});
  assert.throws(()=>budget.claim({frame_index:479,source_revision:'source-revision'}),/GRAB_BUDGET_EXHAUSTED/);
  assert.throws(()=>budget.select(0),/INVALID_CAPTURE_SELECTION/);
  assert.equal(budget.attempts,1);
});

test('ordinary read-only config and command do not include Capture approval or Capture spec',()=>{
  const config=readFileSync(new URL('../playwright.readonly.config.mjs',import.meta.url),'utf8');
  const runner=readFileSync(new URL('./run_readonly_e2e.mjs',import.meta.url),'utf8');
  assert.match(config,/testMatch: 'readonly\.spec\.mjs'/);
  assert.doesNotMatch(runner,/ONE_CAPTURE_APPROVED|approve-one-capture|capture-edge-gv\.spec/);
});
