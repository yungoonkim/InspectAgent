import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import postcss from 'postcss';
import * as grabState from '../src/utils/grabInspectionState.ts';
import * as qualityState from '../src/utils/inspectionQualitySummary.ts';
import * as reinspectionState from '../src/utils/reinspectionState.ts';
import * as recoveryState from '../src/utils/reinspectionRecovery.ts';

const require = createRequire(import.meta.url);
const noRequest = () => assert.fail('No API or inference request during offline panel rendering');
const api = new Proxy({}, { get: () => noRequest });
const dependencies = {
  react: React,
  'react/jsx-runtime': require('react/jsx-runtime'),
  '../api/inspection': api,
  '../api/video': api,
  '../utils/grabInspectionState': grabState,
  '../utils/inspectionQualitySummary': qualityState,
  '../utils/reinspectionState': reinspectionState,
  '../utils/reinspectionRecovery': recoveryState,
};
const source = readFileSync(new URL('../src/components/GrabInspectionPanel.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
} });
function loadComponent(react = React) {
  const componentExports = {};
  runInNewContext(compiled.outputText, { exports: componentExports, require: name => {
    assert.ok(Object.hasOwn(dependencies, name), `Unexpected dependency ${name}`);
    return name === 'react' ? react : dependencies[name];
  } });
  return componentExports.GrabInspectionPanel;
}
const GrabInspectionPanel = loadComponent();

const crop = { captureId: 'CAP-SYNTHETIC-A', videoId: 'VID-000002', sourceRevision: 'a'.repeat(64), frameIndex: 45,
  roi: { x: 941, y: 128, width: 288, height: 271 }, width: 288, height: 271 };
const inspection = { inspection_id: 'INSP-SYNTHETIC-A', result: 'OK', final_result: 'REINSPECT',
  final_reason_code: 'IMAGE_QUALITY_WARNING', image_quality_status: 'WARNING_LOW_BRIGHTNESS',
  anomaly_score: 31.39, decision_threshold: 34.1442, metrics: { mean: 120.2, input_source: 'LIVEVIEW_GRAB',
    input_provenance: { capture_id: crop.captureId, video_id: crop.videoId, source_revision: crop.sourceRevision,
      frame_index: crop.frameIndex, roi: crop.roi, crop_width: crop.width, crop_height: crop.height } } };
const render = (currentInspection, currentCrop = crop) => renderToStaticMarkup(React.createElement(
  GrabInspectionPanel, { crop: currentCrop, currentInspection, enabled: true,
    onSelectionStart: noRequest, onInspectionChange: noRequest }));

test('actual MANUAL Grab component renders API mean, criteria, model and server verdict separately', () => {
  const before = structuredClone(inspection);
  const html = render(inspection);
  for (const text of ['현재 Grab 검사 상세', inspection.inspection_id, '평균 GV', '120.20', '125.0',
    'API 미제공', 'WARNING_LOW_BRIGHTNESS', 'PatchCore 모델 판정', '<strong>OK</strong>',
    '31.3900', '34.1442', '서버 최종 판정', '<strong>REINSPECT</strong>', 'IMAGE_QUALITY_WARNING']) {
    assert.ok(html.includes(text), `Missing panel value: ${text}`);
  }
  assert.deepEqual(inspection, before);
});

test('another Capture or ROI cannot show the previous inspection details', () => {
  for (const otherCrop of [{ ...crop, captureId: 'CAP-SYNTHETIC-B' },
    { ...crop, roi: { ...crop.roi, x: 942 } }, { ...crop, sourceRevision: 'b'.repeat(64) }, null]) {
    const html = render(inspection, otherCrop);
    assert.ok(!html.includes('현재 Grab 검사 상세'));
    assert.ok(!html.includes(inspection.inspection_id));
    assert.ok(!html.includes('120.20'));
  }
});

test('missing measurements and reported thresholds are displayed honestly without new classification', () => {
  const html = render({ ...inspection, result: 'NG', metrics: { ...inspection.metrics, mean: null,
    applied_thresholds: { low_threshold: 125, high_threshold: 150 } } });
  assert.ok(html.includes('측정값 없음'));
  assert.ok(html.includes('검사 응답 기준'));
  assert.ok(html.includes('상한 150.0'));
  assert.ok(html.includes('<strong>NG</strong>'));
  assert.ok(html.includes('<strong>REINSPECT</strong>'));
  assert.ok(!render(null).includes('현재 Grab 검사 상세'));
});

test('Grab uses the same explicit header, body and metric card design as the static panel', () => {
  const html = render(inspection);
  assert.match(html, /class="panel-card grab-inspection-panel"/);
  for (const className of ['panel-header', 'panel-title', 'panel-body', 'grab-panel-actions', 'grab-panel-metrics']) {
    assert.ok(html.includes(`class="${className}"`), `Missing layout ${className}`);
  }
  assert.equal([...html.matchAll(/class="meta-pill"/g)].length, 4);
  assert.equal([...html.matchAll(/<button[^>]*class="btn btn-outline"/g)].length, 2);
  assert.match(html, /data-verdict="REINSPECT"/);
  assert.match(html, /<details class="grab-panel-details"><summary>상세 정보 · 현재 Grab Crop<\/summary>/);
  assert.doesNotMatch(html, /<details[^>]*\sopen(?:=|\s|>)/);
  assert.ok(html.includes(crop.captureId));
  const staticSource = readFileSync(new URL('../src/components/InspectionPanel.tsx', import.meta.url), 'utf8');
  for (const className of ['panel-header', 'panel-title', 'panel-body', 'meta-pill']) {
    assert.ok(staticSource.includes(className), `Shared static design ${className}`);
  }
});

test('all Grab styling is scoped, uses existing dark tokens and allows narrow-width wrapping', () => {
  const css = postcss.parse(readFileSync(new URL('../src/index.css', import.meta.url), 'utf8'));
  const declarations = selector => {
    const result = {};
    css.walkRules(rule => {
      if (rule.selector.split(',').some(part => part.trim() === selector)) {
        rule.walkDecls(declaration => { result[declaration.prop] = declaration.value; });
      }
    });
    return result;
  };
  css.walkRules(rule => {
    if (!rule.selector.includes('grab-inspection-panel')) return;
    assert.ok(rule.selector.split(',').every(selector => selector.trim().startsWith('.grab-inspection-panel')));
    rule.walkDecls(declaration => assert.ok(!declaration.important));
  });
  assert.equal(declarations('.panel-card').background, 'var(--bg-card)');
  assert.equal(declarations('.panel-header').background, 'var(--bg-card-header)');
  assert.equal(declarations('.meta-pill').background, 'var(--bg-card-subtle)');
  assert.equal(declarations('.grab-inspection-panel .panel-body').gap, '14px');
  assert.equal(declarations('.grab-inspection-panel')['overflow-wrap'], 'anywhere');
  assert.equal(declarations('.grab-inspection-panel .btn')['white-space'], 'normal');
  assert.equal(declarations('.grab-inspection-panel .btn')['min-width'], '0');
  assert.equal(declarations('.grab-inspection-panel textarea').resize, 'vertical');
  assert.equal(declarations('.grab-inspection-panel select').background, 'var(--bg-input)');
  assert.equal(declarations('.grab-inspection-panel .grab-panel-metrics')['grid-template-columns'],
    'repeat(auto-fit, minmax(min(100%, 180px), 1fr))');
});

test('history and manual controls keep their labels, default HOLD and disabled policy in styled containers', () => {
  const group = { group_id: 'RIG-SYNTHETIC-LONG', product_id: 'PRODUCT', status: 'MANUAL_REVIEW_REQUIRED',
    attempt_count: 3, remaining_attempts: 0, max_attempts: 3, failed_attempts: [], manual_reviews: [],
    attempts: [{ ...inspection, attempt_number: 3, input_provenance: {
      capture_id: crop.captureId, video_id: crop.videoId, frame_index: crop.frameIndex,
    } }] };
  const before = structuredClone(group);
  for (const manualMode of [true, false]) {
    let stateIndex = 0;
    const Component = loadComponent({ ...React, useState: initial => React.useState(stateIndex++ === 1 ? group : initial) });
    const html = renderToStaticMarkup(React.createElement(Component, { crop, currentInspection: inspection,
      enabled: manualMode, manualMode, onSelectionStart: noRequest, onInspectionChange: noRequest }));
    assert.match(html, /class="grab-panel-history"/);
    assert.match(html, /class="grab-panel-attempt"/);
    assert.match(html, /<button[^>]*class="btn btn-outline"[^>]*>이미지\/Heatmap 조회<\/button>/);
    assert.ok(html.includes(group.group_id));
    assert.match(html, /<option value="HOLD" selected="">HOLD<\/option>/);
    assert.ok(html.includes('aria-label="작업자 표시명"'));
    assert.ok(html.includes('aria-label="수동 판단 사유"'));
    const fieldset = html.match(/<fieldset[^>]*>/)[0];
    assert.equal(fieldset.includes('disabled'), !manualMode);
    assert.match(html, /<button[^>]*disabled=""[^>]*>수동 확인 저장<\/button>/);
  }
  assert.deepEqual(group, before);
});
