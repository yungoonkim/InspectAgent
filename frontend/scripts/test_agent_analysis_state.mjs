import assert from 'node:assert/strict';
import test from 'node:test';
import {agentFailureMessage, liveAnalysisLabel} from '../src/utils/agentAnalysisState.ts';

test('never verified, failed, running and completed live states remain distinct', () => {
  assert.equal(liveAnalysisLabel('NOT_VERIFIED'), 'LIVE NOT YET VERIFIED');
  assert.equal(liveAnalysisLabel('FAILED'), 'LIVE ANALYSIS FAILED');
  assert.equal(liveAnalysisLabel('RUNNING'), 'LIVE ANALYSIS RUNNING');
  assert.equal(liveAnalysisLabel('COMPLETED'), 'LIVE ANALYSIS COMPLETED');
});
test('only missing-key code is described as missing credentials', () => {
  assert.match(agentFailureMessage('MISSING_API_KEY', 503), /API Key/);
  for (const code of ['STORAGE_ERROR','TOOL_CAPACITY_EXCEEDED','INVALID_MODEL_CONFIG','AGENT_CONFIG_CHANGED']) {
    assert.doesNotMatch(agentFailureMessage(code, 503), /API Key/);
    assert.match(agentFailureMessage(code, 503), new RegExp(code));
  }
});
test('provider failure remains unknown instead of inventing a 404 root cause', () => {
  assert.match(agentFailureMessage('GEMINI_REQUEST_FAILED', 502), /미확정/);
  assert.doesNotMatch(agentFailureMessage('GEMINI_REQUEST_FAILED', 502), /404/);
});
test('all timeout codes prohibit automatic retry', () => {
  for (const code of ['GEMINI_TIMEOUT','AGENT_TIMEOUT','TOOL_TIMEOUT']) assert.match(agentFailureMessage(code, 504), /자동 재시도하지/);
});
test('untrusted provider text never becomes a UI error message', () => {
  assert.doesNotMatch(agentFailureMessage('Bearer PRIVATE_PROMPT', 500), /PRIVATE_PROMPT|Bearer/);
});

test('existing reports and report storage failures never claim new live completion', () => {
  assert.match(agentFailureMessage('AGENT_REPORT_EXISTS', 409), /기존 보고서를 보존/);
  assert.match(agentFailureMessage('AGENT_REPORT_STORAGE_FAILED', 503), /완료로 처리하지/);
  assert.match(agentFailureMessage('AGENT_REPORT_STORAGE_FAILED', 503), /자동 재호출하지/);
});
