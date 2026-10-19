import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { detectBottleEdges } from '../src/utils/bottleEdges.ts';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../src/components/BottleEdgeDetails.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
}});
const exports = {};
runInNewContext(compiled.outputText, { exports, require: dependency => {
  assert.equal(dependency, 'react/jsx-runtime');
  return require(dependency);
}, fetch: () => assert.fail('External IO forbidden') });

test('details distinguish outer/rim state, unavailable statistics, unverified anatomy and unchanged server criterion', () => {
  const edges = detectBottleEdges({ width:24, height:24, data:new Uint8ClampedArray(24*24*4) });
  const before = structuredClone(edges);
  const html = renderToStaticMarkup(React.createElement(exports.BottleEdgeDetails, { edges }));
  for (const text of ['외곽: 실패', '내부 림 후보: 실패', 'A · 전체 ROI', 'B · 외곽 내부 후보',
    'C · 닫힌 림 후보 내부', 'D · 외곽 바깥 후보', '계산 불가', '정확도는 미검증', '125.0을 적용하지 않으며']) {
    assert.ok(html.includes(text), text);
  }
  assert.equal((html.match(/계산 불가 —/g) ?? []).length, 3);
  assert.ok(html.includes('0.00 / 0.00 / 0.00'));
  assert.deepEqual(edges, before);
  const imageView = readFileSync(new URL('../src/components/ImageView.tsx', import.meta.url), 'utf8');
  assert.match(imageView, /<BottleEdgeDetails edges=\{bottleEdges\}/);
  assert.match(imageView, /edgePixels === targetImageData\) drawBottleEdges\(ctx, bottleEdges, originX, originY, zoom\)/);
});

test('favicon references a local blue/white eye SVG without changing the header brand or legacy asset', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(html, /rel="icon" type="image\/svg\+xml" href="\/visioninsight\.svg"/);
  const icon = readFileSync(new URL('../public/visioninsight.svg', import.meta.url), 'utf8');
  assert.match(icon, /viewBox="0 0 36 36"/);
  assert.match(icon, /#0284c7/);
  assert.match(icon, /#38bdf8/);
  assert.match(icon, /stroke="#fff"/);
  assert.match(icon, /circle cx="12" cy="12" r="3"/);
  assert.doesNotMatch(icon, /<script|https?:\/\/(?!www\.w3\.org)/);
  const header = readFileSync(new URL('../src/components/Header.tsx', import.meta.url), 'utf8');
  assert.match(header, /<Eye size=\{20\} strokeWidth=\{2\.5\}/);
});
