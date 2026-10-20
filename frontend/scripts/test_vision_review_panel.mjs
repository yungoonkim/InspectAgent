import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import React from 'react';
import ts from 'typescript';
import postcss from 'postcss';
import * as visionState from '../src/utils/visionReviewState.ts';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../src/components/VisionReviewPanel.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
} });
const forbidden = () => assert.fail('No network, inference or unapproved Judge request in offline tests');

function nodes(element) {
  if (Array.isArray(element)) return element.flatMap(nodes);
  if (!element || typeof element !== 'object') return [];
  return [element, ...nodes(element.props?.children)];
}

function text(element) {
  if (Array.isArray(element)) return element.map(text).join(' ');
  if (typeof element === 'string' || typeof element === 'number') return String(element);
  return element && typeof element === 'object' ? text(element.props?.children) : '';
}

function inspection(suffix = 'A') {
  return { inspection_id: `INSP-SYNTHETIC-${suffix}`, image_id: `IMG-SYNTHETIC-${suffix}`,
    final_result: 'REINSPECT', metrics: { input_source: 'LIVEVIEW_GRAB',
      input_provenance: { capture_id: `CAP-SYNTHETIC-${suffix}`, crop_sha256: (suffix === 'A' ? 'a' : 'b').repeat(64) },
      reinspection: { group_id: `RIG-SYNTHETIC-${suffix}` } } };
}

function response(input, verdict = null, mode = 'LIVE') {
  const review = verdict ? {
    vision_review_id: 'VREV-SYNTHETIC', inspection_id: input.inspection_id, image_id: input.image_id,
    capture_id: input.metrics.input_provenance.capture_id, image_sha256: input.metrics.input_provenance.crop_sha256,
    reinspection_group_id: input.metrics.reinspection.group_id, prompt_version: 'bottle-vision-judge-a-v1',
    judge_verdict: verdict === 'ANALYSIS_FAILED' ? null : verdict,
    analysis_status: verdict === 'ANALYSIS_FAILED' ? 'ANALYSIS_FAILED' : 'COMPLETED',
    failure_code: verdict === 'ANALYSIS_FAILED' ? 'VISION_TIMEOUT' : null,
    analysis_mode: mode, model_requested: 'OFFLINE_MODEL', model_resolved: 'OFFLINE_RESOLVED_MODEL',
    judge_rationale: 'SYNTHETIC rationale', defect_locations: ['SYNTHETIC upper rim'],
    visible_observations: ['SYNTHETIC observation'], limitations: ['SYNTHETIC limitation'],
    recommended_operator_action: 'SYNTHETIC operator check', created_at: 'SYNTHETIC_TIME',
    http_attempts: 1, provider_http_status: verdict === 'ANALYSIS_FAILED' ? 504 : 200,
  } : null;
  return { available: !!review, review, capabilities: { enabled: true, live_enabled: mode === 'LIVE',
    analysis_mode: mode, model_requested: 'OFFLINE_MODEL', reason: 'SYNTHETIC_TEST_ONLY',
    result_contract: 'VISION_JUDGE_A_V1', consent_policy: 'PER_REQUEST_CROP_V1' } };
}

function panel(initial = inspection(), read = async () => response(initial), create = forbidden, readInspection = forbidden) {
  const hooks = [];
  const requests = { get: [], post: [] };
  const inspectionReads = [];
  let cursor = 0;
  let effects = [];
  const useEffect = (effect, dependencies) => {
    const index = cursor++;
    const previous = hooks[index];
    if (!previous || dependencies.some((value, offset) => value !== previous.dependencies[offset])) {
      effects.push(() => {
        previous?.cleanup?.();
        hooks[index] = { dependencies, cleanup: effect() };
      });
    }
  };
  const fakeReact = { ...React, useEffect, useLayoutEffect: useEffect,
    useState: initialValue => {
      const index = cursor++;
      if (!(index in hooks)) hooks[index] = { value: initialValue };
      return [hooks[index].value, value => { hooks[index].value = value; }];
    },
    useRef: initialValue => {
      const index = cursor++;
      if (!(index in hooks)) hooks[index] = { current: initialValue };
      return hooks[index];
    },
  };
  const dependencies = { react: fakeReact, 'react/jsx-runtime': require('react/jsx-runtime'),
    '../utils/visionReviewState': visionState,
    '../api/inspection': {
      getInspection: identifier => { inspectionReads.push(identifier); return readInspection(identifier); },
    },
    '../api/visionReview': {
      getVisionReview: identifier => { requests.get.push(identifier); return read(identifier); },
      createVisionReview: (...parameters) => { requests.post.push(parameters); return create(...parameters); },
    },
  };
  const exports = {};
  runInNewContext(compiled.outputText, { exports, fetch: forbidden, crypto: { randomUUID: () => 'OFFLINE-REQUEST' },
    require: name => {
      assert.ok(Object.hasOwn(dependencies, name), `Unexpected dependency ${name}`);
      return dependencies[name];
    },
  });
  const props = { inspection: initial, reinspectionGroup: null };
  const render = () => {
    cursor = 0;
    effects = [];
    const tree = exports.VisionReviewPanel(props);
    for (const effect of effects) effect();
    return tree;
  };
  const consent = () => nodes(render()).find(node => node.props?.['aria-label'] === '현재 Crop Google 전송 동의');
  const button = () => nodes(render()).find(node => node.type === 'button');
  const settle = async () => { for (let count = 0; count < 12; count++) await Promise.resolve(); return render(); };
  const historyButton = () => nodes(render()).find(node => node.type === 'button' && text(node) === '이전 회차 Gemini 결과 보기');
  return { render, consent, button, historyButton, settle, requests, inspectionReads, props };
}

test('eligible Judge preserves consent on rerender without a repeated GET or automatic POST', async () => {
  const view = panel();
  view.render();
  await view.settle();
  assert.equal(view.button().props.disabled, true);
  view.consent().props.onChange({ target: { checked: true } });
  for (let count = 0; count < 5; count++) {
    assert.equal(view.consent().props.checked, true);
    assert.equal(view.button().props.disabled, false);
  }
  assert.deepEqual(view.requests, { get: ['INSP-SYNTHETIC-A'], post: [] });
});

test('a different inspection, Capture or image hash never inherits the preceding consent', async () => {
  const first = inspection();
  for (const changes of [inspection('B'), { ...first, metrics: { ...first.metrics,
    input_provenance: { ...first.metrics.input_provenance, crop_sha256: 'c'.repeat(64) } } },
  { ...first, metrics: { ...first.metrics,
    input_provenance: { ...first.metrics.input_provenance, capture_id: 'CAP-NEW' } } }]) {
    const view = panel(first, async () => response(first));
    view.render(); await view.settle();
    view.consent().props.onChange({ target: { checked: true } });
    view.props.inspection = changes;
    view.render(); await view.settle();
    assert.equal(view.consent().props.checked, false);
    assert.equal(view.button().props.disabled, true);
    view.button().props.onClick();
    assert.deepEqual(view.requests.post, []);
  }
});

test('an explicit confirmed request uses the selected ID once and keeps primary verdict and source separate', async () => {
  const input = inspection();
  const before = structuredClone(input);
  const view = panel(input, async () => response(input), async () => response(input, 'NG', 'FAKE_TEST'));
  view.render(); await view.settle();
  view.consent().props.onChange({ target: { checked: true } });
  view.button().props.onClick();
  await view.settle();
  assert.deepEqual(view.requests.post, [[input.inspection_id, 'OFFLINEREQUEST', true]]);
  const tree = view.render();
  const verdict = nodes(tree).find(node => node.props?.className === 'judge-verdict');
  assert.equal(text(verdict), 'NG');
  assert.match(text(tree), /1차 서버 판정 REINSPECT/);
  assert.match(text(tree), /FAKE_TEST · 실제 Google 판정 아님/);
  assert.match(text(tree), /SYNTHETIC rationale/);
  assert.match(text(tree), /분석 한계/);
  assert.match(text(tree), /OFFLINE_RESOLVED_MODEL/);
  assert.equal(view.button().props.disabled, true);
  view.button().props.onClick(); await view.settle();
  assert.equal(view.requests.post.length, 1);
  assert.deepEqual(input, before);
});

for (const language of ['ko', 'en']) {
  test(`MOCK TEST: ${language} stored Judge explanations render unchanged without a new request`, async () => {
    const input = inspection();
    const before = structuredClone(input);
    const saved = response(input, 'NG', 'FAKE_TEST');
    if (language === 'ko') Object.assign(saved.review, {
      visible_observations: ['MOCK TEST: 위쪽 테두리에 불연속 경계가 관찰됩니다.'],
      defect_locations: ['MOCK TEST: 이미지 위쪽 입구 테두리'],
      judge_rationale: 'MOCK TEST: 손상이 의심되지만 실제 결함을 확정하지 않습니다.',
      limitations: ['MOCK TEST: 합성 응답이며 검출 정확도가 검증되지 않았습니다.'],
      recommended_operator_action: 'MOCK TEST: 작업자가 제품을 직접 확인하세요.',
    });
    const savedBefore = structuredClone(saved);
    const view = panel(input, async () => saved);
    view.render(); await view.settle();
    for (let count = 0; count < 3; count++) {
      const rendered = text(view.render());
      for (const field of ['visible_observations', 'defect_locations', 'limitations']) {
        for (const value of saved.review[field]) assert.ok(rendered.includes(value));
      }
      assert.ok(rendered.includes(saved.review.judge_rationale));
      assert.ok(rendered.includes(saved.review.recommended_operator_action));
      assert.match(rendered, /1차 서버 판정 REINSPECT/);
      assert.match(rendered, /FAKE_TEST · 실제 Google 판정 아님/);
      assert.equal(view.button().props.disabled, true);
    }
    assert.deepEqual(saved, savedBefore);
    assert.deepEqual(input, before);
    assert.deepEqual(view.requests, { get: [input.inspection_id], post: [] });
  });
}

test('a late result from another Crop cannot appear in the selected Judge', async () => {
  const first = inspection();
  const second = inspection('B');
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const view = panel(first, async identifier => response(identifier === first.inspection_id ? first : second), () => pending);
  view.render(); await view.settle();
  view.consent().props.onChange({ target: { checked: true } });
  view.button().props.onClick();
  view.props.inspection = second;
  view.render(); await view.settle();
  finish(response(first, 'NG'));
  await view.settle();
  assert.match(text(view.render()), /INSP-SYNTHETIC-B/);
  assert.doesNotMatch(text(view.render()), /SYNTHETIC rationale/);
  assert.equal(view.consent().props.checked, false);
  assert.equal(view.button().props.disabled, true);
});

test('an in-flight confirmed request blocks duplicate clicks and displays only its simulated new LIVE result', async () => {
  const input = inspection();
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const view = panel(input, async () => response(input), () => pending);
  view.render(); await view.settle();
  view.consent().props.onChange({ target: { checked: true } });
  view.button().props.onClick();
  view.button().props.onClick();
  assert.equal(view.requests.post.length, 1);
  assert.equal(view.button().props.disabled, true);
  finish(response(input, 'OK'));
  await view.settle();
  assert.match(text(view.render()), /신규 LIVE 응답\s+· COMPLETED/);
  assert.equal(text(nodes(view.render()).find(node => node.props?.className === 'judge-verdict')), 'OK');
  assert.equal(input.final_result, 'REINSPECT');
  assert.equal(view.requests.post.length, 1);
});

test('recorded success, recorded failure and Fake data keep distinct status labels', async () => {
  const input = inspection();
  for (const [mode, verdict, expected] of [['LIVE', 'OK', '저장 LIVE 응답 조회'],
    ['LIVE', 'ANALYSIS_FAILED', 'LIVE ANALYSIS FAILED'], ['FAKE_TEST', 'NG', 'FAKE_TEST · 실제 분석 아님']]) {
    const view = panel(input, async () => response(input, verdict, mode));
    view.render(); await view.settle();
    assert.ok(text(view.render()).includes(expected));
    if (verdict === 'ANALYSIS_FAILED') {
      assert.match(text(view.render()), /실패 · 판정 없음/);
      assert.match(text(view.render()), /VISION_TIMEOUT/);
    }
    assert.deepEqual(view.requests.post, []);
  }
});

test('a wrong saved image is rejected and noneligible inputs show guidance without calling an API', async () => {
  const view = panel(inspection(), async () => response(inspection('B'), 'OK'));
  view.render(); await view.settle();
  assert.match(text(view.render()), /VISION_REVIEW_SOURCE_MISMATCH/);
  assert.equal(view.button().props.disabled, true);
  for (const input of [null, { ...inspection(), final_result: 'OK' }]) {
    const empty = panel(input, forbidden);
    assert.match(text(empty.render()), /REINSPECT 검사를 선택하세요/);
    assert.deepEqual(empty.requests, { get: [], post: [] });
  }
});

test('Judge details are collapsed, cards are separated and CSS is dark, scoped and wrapping-safe', async () => {
  const input = inspection();
  const view = panel(input, async () => response(input, 'REINSPECT', 'FAKE_TEST'));
  view.render(); await view.settle();
  const tree = view.render();
  assert.equal(tree.props.className, 'panel-card vision-judge-panel');
  const details = nodes(tree).find(node => node.type === 'details');
  assert.ok(!details.props.open);
  assert.ok(text(details).includes(input.metrics.input_provenance.crop_sha256));
  assert.equal(nodes(tree).filter(node => node.props?.className === 'judge-evidence-card').length, 3);
  const css = postcss.parse(readFileSync(new URL('../src/index.css', import.meta.url), 'utf8'));
  const styles = {};
  css.walkRules(rule => {
    if (!rule.selector.includes('vision-judge-panel')) return;
    assert.ok(rule.selector.split(',').every(selector => selector.trim().startsWith('.vision-judge-panel')));
    styles[rule.selector] = {};
    rule.walkDecls(declaration => {
      assert.ok(!declaration.important);
      styles[rule.selector][declaration.prop] = declaration.value;
    });
  });
  assert.equal(styles['.vision-judge-panel']['overflow-wrap'], 'anywhere');
  assert.equal(styles['.vision-judge-panel .btn']['white-space'], 'normal');
  assert.equal(styles['.vision-judge-panel .judge-summary-grid']['grid-template-columns'],
    'repeat(auto-fit, minmax(min(100%, 180px), 1fr))');
  assert.ok(Object.values(styles).some(values => values.background === 'var(--bg-card-subtle)'));
});

function retryChain() {
  const inputs = ['A', 'B', 'C'].map(suffix => {
    const input = inspection(suffix);
    input.metrics.reinspection.group_id = 'RIG-SYNTHETIC-CHAIN';
    return input;
  });
  const group = { group_id: 'RIG-SYNTHETIC-CHAIN', status: 'MANUAL_REVIEW_REQUIRED',
    attempt_count: 3, max_attempts: 3, remaining_attempts: 0,
    current_inspection_id: inputs[2].inspection_id, manual_reviews: [], failed_attempts: [],
    attempts: inputs.map((input, index) => ({ inspection_id: input.inspection_id, attempt_number: index + 1,
      final_result: input.final_result, input_provenance: input.metrics.input_provenance })) };
  return { inputs, group };
}

test('MOCK TEST: original saved Judge remains accessible across retries, tab rerenders and MANUAL_NG', async () => {
  const { inputs, group } = retryChain();
  const original = structuredClone(inputs);
  const saved = response(inputs[0], 'NG');
  const view = panel(inputs[0], async identifier => identifier === inputs[0].inspection_id ? saved
    : response(inputs.find(input => input.inspection_id === identifier)), forbidden,
  async identifier => inputs.find(input => input.inspection_id === identifier));
  view.props.reinspectionGroup = group;
  view.render(); await view.settle();
  assert.equal(text(nodes(view.render()).find(node => node.props?.className === 'judge-verdict')), 'NG');
  assert.equal(view.historyButton(), undefined);
  for (const selected of inputs.slice(1)) {
    view.props.inspection = selected;
    view.render(); await view.settle();
    assert.match(text(view.render()), /현재 회차 Gemini Judge 미실행/);
    view.historyButton().props.onClick();
    view.render(); await view.settle();
    const histories = nodes(view.render()).filter(node => node.props?.['data-testid'] === 'vision-history-result');
    const first = histories.find(node => text(node).includes(inputs[0].inspection_id));
    assert.match(text(first), /NG/);
    assert.match(text(first), /저장 LIVE 응답 조회/);
    assert.match(text(first), /OFFLINE_RESOLVED_MODEL/);
    assert.match(text(first), /SYNTHETIC_TIME/);
    assert.match(text(first), /SYNTHETIC rationale/);
    assert.ok(text(first).includes(inputs[0].metrics.input_provenance.crop_sha256));
    assert.equal(nodes(view.render()).find(node => node.props?.className === 'judge-inspection-id').props.children[1].props.children,
      selected.inspection_id);
    assert.equal(view.consent().props.checked, false);
  }
  view.props.reinspectionGroup = { ...group, status: 'MANUAL_REVIEWED', manual_reviews: [{ result: 'MANUAL_NG', timestamp: 'MOCK_MANUAL_TIME' }] };
  for (let count = 0; count < 3; count++) view.render();
  assert.match(text(view.render()), /MANUAL_NG/);
  assert.match(text(view.render()), /현재 회차 Gemini Judge 미실행/);
  assert.equal(nodes(view.render()).filter(node => node.props?.['data-testid'] === 'vision-history-result').length, 2);
  assert.match(text(view.render()), /이전 회차에 저장된 Gemini Judge 결과 없음/);
  assert.deepEqual(view.requests.post, []);
  assert.deepEqual(inputs, original);
  assert.equal(group.attempt_count, 3);
  assert.deepEqual(group.manual_reviews, []);
});

test('MOCK TEST: prior review access errors and identity mismatches fail closed instead of showing unexecuted', async () => {
  for (const failure of ['ACCESS_DENIED', 'REVIEW_HASH', 'INSPECTION_GROUP', 'INSPECTION_CAPTURE']) {
    const { inputs, group } = retryChain();
    const view = panel(inputs[2], async identifier => {
      const input = inputs.find(input => input.inspection_id === identifier);
      if (identifier !== inputs[0].inspection_id) return response(input);
      if (failure === 'ACCESS_DENIED') throw new Error('403');
      const output = response(input, 'NG');
      if (failure === 'REVIEW_HASH') output.review.image_sha256 = 'wrong';
      return output;
    }, forbidden, async identifier => {
      const input = structuredClone(inputs.find(input => input.inspection_id === identifier));
      if (identifier === inputs[0].inspection_id) {
        if (failure === 'INSPECTION_GROUP') input.metrics.reinspection.group_id = 'OTHER_GROUP';
        if (failure === 'INSPECTION_CAPTURE') input.metrics.input_provenance.capture_id = 'OTHER_CAPTURE';
      }
      return input;
    });
    view.props.reinspectionGroup = group;
    view.render(); await view.settle();
    view.historyButton().props.onClick(); view.render(); await view.settle();
    const first = nodes(view.render()).filter(node => node.props?.['data-testid'] === 'vision-history-result')[0];
    assert.match(text(first), /이전 회차 기록 조회 실패/);
    assert.doesNotMatch(text(first), /SYNTHETIC rationale|저장된 Gemini Judge 결과 없음/);
    assert.deepEqual(view.requests.post, []);
  }
});

test('MOCK TEST: stale historical responses never cross inspection/group selection or transfer consent', async () => {
  const { inputs, group } = retryChain();
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const other = inspection('OTHER');
  const view = panel(inputs[2], async identifier => identifier === inputs[0].inspection_id ? pending
    : response(identifier === other.inspection_id ? other : inputs.find(input => input.inspection_id === identifier)), forbidden,
  async identifier => inputs.find(input => input.inspection_id === identifier));
  view.props.reinspectionGroup = group;
  view.render(); await view.settle();
  view.historyButton().props.onClick(); view.render(); await view.settle();
  view.props.inspection = other;
  view.render(); await view.settle();
  finish(response(inputs[0], 'NG')); await view.settle();
  assert.equal(view.historyButton(), undefined);
  assert.doesNotMatch(text(view.render()), /SYNTHETIC rationale|INSP-SYNTHETIC-A/);
  assert.equal(view.consent().props.checked, false);
  assert.deepEqual(view.requests.post, []);
});

test('MOCK TEST: historical Fake, failed and legacy results retain their source and are never converted to current verdicts', async () => {
  const { inputs, group } = retryChain();
  for (const kind of ['FAKE_TEST', 'ANALYSIS_FAILED', 'LEGACY']) {
    const stored = response(inputs[0], kind === 'ANALYSIS_FAILED' ? kind : 'OK', kind === 'FAKE_TEST' ? kind : 'LIVE');
    if (kind === 'LEGACY') stored.review = { ...stored.review, prompt_version: 'bottle-independent-vision-v1', classification: 'NO_VISIBLE_DEFECT' };
    const view = panel(inputs[2], async identifier => identifier === inputs[0].inspection_id ? stored
      : response(inputs.find(input => input.inspection_id === identifier)), forbidden,
    async identifier => inputs.find(input => input.inspection_id === identifier));
    view.props.reinspectionGroup = group;
    view.render(); await view.settle();
    view.historyButton().props.onClick(); view.render(); await view.settle();
    const first = nodes(view.render()).filter(node => node.props?.['data-testid'] === 'vision-history-result')[0];
    assert.ok(text(first).includes(kind === 'FAKE_TEST' ? 'FAKE_TEST · 실제 Google 판정 아님'
      : kind === 'ANALYSIS_FAILED' ? '실패 · 판정 없음' : '과거 관찰 의견 · Judge 판정 아님'));
    assert.match(text(view.render()), /현재 회차 Gemini Judge 미실행/);
    assert.deepEqual(view.requests.post, []);
  }
});
