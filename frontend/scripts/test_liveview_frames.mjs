import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import React from 'react';
import ts from 'typescript';
import * as frames from '../src/utils/videoFrames.ts';
import * as coordinates from '../src/utils/coordinateTransforms.ts';

const require = createRequire(import.meta.url);
const forbidden = () => assert.fail('No API, Grab, inference or Gemini requests permitted');
function nodes(element) {
  if (Array.isArray(element)) return element.flatMap(nodes);
  return element && typeof element === 'object' ? [element, ...nodes(element.props?.children)] : [];
}
function mount() {
  const hooks = [];
  let cursor = 0;
  const callbacks = [];
  const react = { ...React, useRef:initial => {
    const index = cursor++;
    if (!(index in hooks)) hooks[index] = { current:initial };
    return hooks[index];
  }, useState:initial => {
    const index = cursor++;
    if (!(index in hooks)) hooks[index] = { value:initial };
    return [hooks[index].value, value => { hooks[index].value = typeof value === 'function' ? value(hooks[index].value) : value; }];
  } };
  const compiled = ts.transpileModule(readFileSync(new URL('../src/components/LiveView.tsx', import.meta.url), 'utf8'), {
    compilerOptions:{ module:ts.ModuleKind.CommonJS, target:ts.ScriptTarget.ES2022, jsx:ts.JsxEmit.ReactJSX, esModuleInterop:true },
  });
  const exports = {};
  runInNewContext(compiled.outputText, { exports, console, fetch:forbidden, require:dependency => {
    if (dependency === 'react') return react;
    if (dependency === 'react/jsx-runtime' || dependency === 'lucide-react') return require(dependency);
    if (dependency === '../utils/videoFrames') return frames;
    if (dependency === '../utils/coordinateTransforms') return coordinates;
    assert.equal(dependency, './RoiOverlay');
    return { RoiOverlay:() => null };
  } });
  const props = { video:{ video_id:'VID-000003', width:1920, height:480, fps:30, frame_count:480, duration_seconds:16 },
    streamUrl:'/api/videos/VID-000003/stream', isGrabbing:false, mode:'MANUAL', error:null, capture:null, imageBlobUrl:null,
    roi:{x:800,y:80,width:320,height:320}, roiState:'APPLIED', cropMessage:null, onChangeRoi:forbidden, onResetRoi:forbidden,
    onGrab:frame => callbacks.push(['GRAB_CALLBACK_ONLY',frame]),
    onToggleRoi:(frame,paused) => callbacks.push(['ROI_CALLBACK_ONLY',frame,paused]) };
  const render = () => { cursor = 0; return exports.LiveView(props); };
  const videoNode = () => nodes(render()).find(node => node.type === 'video');
  let time = 0;
  let seekCount = 0;
  const media = { paused:true, seeking:false, get currentTime() { return time; }, set currentTime(value) {
    seekCount++;
    time = Math.floor(value * 1_000_000) / 1_000_000;
    this.seeking = true;
  }, pause() { this.paused = true; }, async play() { this.paused = false; } };
  videoNode().props.ref.current = media;
  videoNode().props.onPause();
  const button = title => nodes(render()).find(node => node.type === 'button' && node.props.title === title);
  const complete = () => { media.seeking = false; videoNode().props.onSeeked(); videoNode().props.onTimeUpdate(); };
  const seek = value => { nodes(render()).find(node => node.props?.title === '비디오 위치 탐색 (Seek)').props.onChange({target:{value:String(value)}}); complete(); };
  const step = delta => { button(delta > 0 ? '1프레임 앞으로 (+1 Frame)' : '1프레임 뒤로 (-1 Frame)').props.onClick(); complete(); };
  const grab = () => nodes(render()).find(node => node.type === 'button' && /현재 프레임을 Grab/.test(node.props.title)).props.onClick();
  return { media, callbacks, videoNode, render, seek, step, complete, button, grab, seekCount:() => seekCount };
}

test('all 480 selected frames round-trip through microsecond-quantized media time without boundary drift', () => {
  for (let frame = 0; frame < 480; frame++) {
    const target = frames.selectVideoFrame(frame, 30, 480);
    const quantized = Math.floor(target.time * 1_000_000) / 1_000_000;
    assert.equal(frames.frameAtTime(quantized, 30, 480), frame);
    assert.ok(quantized >= frame / 30 && quantized < (frame+1) / 30);
  }
  assert.equal(frames.selectVideoFrame(-1,30,480).frame,0);
  assert.equal(frames.selectVideoFrame(480,30,480).frame,479);
  assert.equal(frames.frameAtTime(16,30,480),479);
  assert.equal(frames.frameAtTime(8.2,30,480),246);
  assert.equal(frames.frameAtTime(8.199999,30,480),245);
});

test('real LiveView handlers select 120 -> 121 -> 120 and pass the same frame to Grab/ROI callbacks', () => {
  const view = mount();
  view.seek(4);
  view.grab();
  view.step(1);
  view.grab();
  view.step(-1);
  view.grab();
  view.button('ROI 재수정 모드로 전환').props.onClick();
  assert.deepEqual(view.callbacks, [['GRAB_CALLBACK_ONLY',120],['GRAB_CALLBACK_ONLY',121],['GRAB_CALLBACK_ONLY',120],['ROI_CALLBACK_ONLY',120,true]]);
  assert.equal(frames.frameAtTime(view.media.currentTime,30,480),120);
});

test('first/last frame clamps use actual in-range media time and preserve the selected Grab index', () => {
  const view = mount();
  view.seek(0);
  const firstCount = view.seekCount();
  view.step(-1); view.grab();
  assert.equal(view.seekCount(),firstCount);
  view.seek(16);
  const lastCount = view.seekCount();
  view.step(1); view.grab();
  assert.equal(view.seekCount(),lastCount);
  view.step(-1); view.grab();
  view.step(1); view.grab();
  assert.deepEqual(view.callbacks.map(entry => entry[1]), [0,479,478,479]);
  assert.ok(view.media.currentTime < 16);
});

test('rapid steps use the integer selection and reject Grab until the final seek is complete', () => {
  const view = mount(); view.seek(4);
  view.button('1프레임 앞으로 (+1 Frame)').props.onClick();
  view.button('1프레임 앞으로 (+1 Frame)').props.onClick();
  view.grab();
  assert.deepEqual(view.callbacks, []);
  view.videoNode().props.onTimeUpdate();
  view.complete(); view.grab();
  assert.deepEqual(view.callbacks, [['GRAB_CALLBACK_ONLY',122]]);
});

test('pausing and stepping during playback sample current media time, not a stale timeupdate index', () => {
  const view = mount();
  view.media.currentTime = 6.2;
  view.media.seeking = false;
  view.media.paused = false;
  view.step(1); view.grab();
  assert.equal(view.media.paused, true);
  assert.deepEqual(view.callbacks, [['GRAB_CALLBACK_ONLY',187]]);
  view.media.paused = false;
  view.media.currentTime = 8.21;
  view.media.seeking = false;
  view.grab();
  assert.equal(view.media.paused, true);
  assert.equal(view.callbacks[1][1],246);
});
