import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import React from 'react';
import ts from 'typescript';
import * as quality from '../src/utils/inspectionQualitySummary.ts';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../src/components/InspectionPanel.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022, esModuleInterop: true,
} });
const forbidden = () => assert.fail('No real API, model or Agent call in component state tests');

function nodes(element) {
  if (Array.isArray(element)) return element.flatMap(nodes);
  if (!element || typeof element !== 'object') return [];
  return [element, ...nodes(element.props?.children)];
}

function text(element) {
  if (Array.isArray(element)) return element.map(text).join('');
  if (typeof element === 'string' || typeof element === 'number') return String(element);
  return element && typeof element === 'object' ? text(element.props?.children) : '';
}

function inspection(identifier, grab = true) {
  return { inspection_id: identifier, image_id: grab ? 'IMG-GRAB-SYNTHETIC' : 'IMG-STATIC-SYNTHETIC',
    provenance: grab ? 'LIVEVIEW_GRAB' : 'LIVE_INSPECTION', result: 'OK', final_result: 'REINSPECT',
    image_quality_status: 'WARNING_LOW_BRIGHTNESS', final_reason_code: 'IMAGE_QUALITY_WARNING',
    anomaly_score: 31, decision_threshold: 34.1442, metrics: { mean: 120,
      ...(grab ? { input_source: 'LIVEVIEW_GRAB' } : {}) } };
}

function panel(initial, getRecord = forbidden, createRecord = forbidden) {
  const hooks = [];
  let cursor = 0;
  let selection = 0;
  const fakeReact = { ...React, useEffect: () => {},
    useState: initialValue => {
      const position = cursor++;
      if (!(position in hooks)) hooks[position] = typeof initialValue === 'function' ? initialValue() : initialValue;
      return [hooks[position], update => {
        hooks[position] = typeof update === 'function' ? update(hooks[position]) : update;
      }];
    },
    useRef: initialValue => {
      const position = cursor++;
      if (!(position in hooks)) hooks[position] = { current: initialValue };
      return hooks[position];
    },
  };
  const props = { currentInspection: initial, onRunAgent: forbidden,
    getSelectionVersion: () => selection,
    onSelectionStart: () => { props.currentInspection = null; return ++selection; },
    onInspectionChange: (record, version) => {
      if (version === undefined || version === selection) props.currentInspection = record;
    },
  };
  const dependencies = { react: fakeReact, 'react/jsx-runtime': require('react/jsx-runtime'),
    'lucide-react': require('lucide-react'), '../utils/inspectionQualitySummary': quality,
    '../api/inspection': { getInspection: getRecord, getInspectionImages: forbidden,
      getRecentInspections: forbidden, createInspection: createRecord } };
  const exports = {};
  runInNewContext(compiled.outputText, { exports, console, require: name => {
    assert.ok(Object.hasOwn(dependencies, name), `Unexpected dependency ${name}`);
    return dependencies[name];
  } });
  const render = () => { cursor = 0; return exports.InspectionPanel(props); };
  return { render, props,
    input: () => nodes(render()).find(node => node.props?.['aria-label'] === '검사 ID 조회 입력'),
    query: () => nodes(render()).find(node => node.props?.title === '기존 저장된 검사 결과 조회').props.onClick(),
    inspect: () => nodes(render()).find(node => node.props?.title === '선택한 등록 이미지로 FastAPI PatchCore 신규 검사 실행').props.onClick(),
    select: record => { selection++; props.currentInspection = record; },
  };
}

test('new Grab result automatically synchronizes the query input with the displayed inspection', () => {
  const view = panel(inspection('INSP-SYNTHETIC-A'));
  assert.equal(view.input().props.value, 'INSP-SYNTHETIC-A');
  view.select(inspection('INSP-SYNTHETIC-B'));
  assert.equal(view.input().props.value, 'INSP-SYNTHETIC-B');
  assert.match(text(view.render()), /표시 중 검사 ID: INSP-SYNTHETIC-B · 신규 Grab 검사 결과/);
});

test('editing a historical ID survives a new Grab event and is labelled separately', () => {
  const view = panel(inspection('INSP-SYNTHETIC-A'));
  view.input().props.onChange({ target: { value: 'INSP-SYNTHETIC-HISTORY' } });
  view.select(inspection('INSP-SYNTHETIC-B'));
  assert.equal(view.input().props.value, 'INSP-SYNTHETIC-HISTORY');
  assert.match(text(view.render()), /표시 중 검사 ID: INSP-SYNTHETIC-B/);
  assert.match(text(view.render()), /조회 입력값 편집 중 · 표시 중 검사 결과와 별도/);
});

test('manual historical lookup uses the typed ID then resumes automatic synchronization', async () => {
  const calls = [];
  const historical = inspection('INSP-SYNTHETIC-HISTORY', false);
  const view = panel(inspection('INSP-SYNTHETIC-A'), async identifier => { calls.push(identifier); return historical; });
  view.input().props.onChange({ target: { value: historical.inspection_id } });
  await view.query();
  assert.deepEqual(calls, [historical.inspection_id]);
  assert.equal(view.input().props.value, historical.inspection_id);
  assert.equal(view.props.currentInspection.provenance, 'STORED_RESULT');
  assert.match(text(view.render()), /표시 중 검사 ID: INSP-SYNTHETIC-HISTORY · 저장 결과 조회/);
  assert.match(text(view.render()), /현재 결과 SOURCE: REGISTERED STATIC IMAGE/);
  view.select(inspection('INSP-SYNTHETIC-B'));
  assert.equal(view.input().props.value, 'INSP-SYNTHETIC-B');
  assert.match(text(view.render()), /현재 결과 SOURCE: EXPERIMENTAL LIVEVIEW_GRAB/);
});

test('late historical query response cannot replace a newer Grab or discard the draft', async () => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const view = panel(inspection('INSP-SYNTHETIC-A'), () => pending);
  view.input().props.onChange({ target: { value: 'INSP-SYNTHETIC-HISTORY' } });
  const completion = view.query();
  view.select(inspection('INSP-SYNTHETIC-B'));
  finish(inspection('INSP-SYNTHETIC-HISTORY', false));
  await completion;
  assert.equal(view.props.currentInspection.inspection_id, 'INSP-SYNTHETIC-B');
  assert.equal(view.input().props.value, 'INSP-SYNTHETIC-HISTORY');
});

test('static and Grab results retain their own execution and image source labels', () => {
  const view = panel(inspection('INSP-SYNTHETIC-STATIC', false));
  assert.equal(view.input().props.value, 'INSP-SYNTHETIC-STATIC');
  assert.match(text(view.render()), /신규 등록 이미지 검사 결과/);
  view.select({ ...inspection('INSP-SYNTHETIC-STORED-GRAB'), provenance: 'STORED_RESULT' });
  assert.equal(view.input().props.value, 'INSP-SYNTHETIC-STORED-GRAB');
  assert.match(text(view.render()), /저장 결과 조회/);
  assert.match(text(view.render()), /현재 결과 SOURCE: EXPERIMENTAL LIVEVIEW_GRAB/);
  assert.doesNotMatch(text(view.render()), /신규 Grab 검사 결과/);
});

test('registered image execution still uses the static API and publishes its own source and inspection ID', async () => {
  const calls = [];
  const result = inspection('INSP-SYNTHETIC-STATIC-NEW', false);
  const view = panel(inspection('INSP-SYNTHETIC-GRAB'), forbidden, async (...parameters) => {
    calls.push(parameters);
    return result;
  });
  await view.inspect();
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], ['ABCD1541', 'IMG-BOTTLE-0001', false]);
  assert.equal(view.props.currentInspection.inspection_id, result.inspection_id);
  assert.equal(view.props.currentInspection.provenance, 'LIVE_INSPECTION');
  assert.equal(view.input().props.value, result.inspection_id);
  assert.match(text(view.render()), /현재 결과 SOURCE: REGISTERED STATIC IMAGE/);
  assert.match(text(view.render()), /신규 등록 이미지 검사 결과/);
  assert.doesNotMatch(text(view.render()), /EXPERIMENTAL LIVEVIEW_GRAB/);
});
