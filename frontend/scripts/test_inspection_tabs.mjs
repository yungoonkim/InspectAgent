import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import React from 'react';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const source = readFileSync(new URL('../src/components/InspectionTabs.tsx', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
} });
const forbidden = () => assert.fail('Tab selection must not call an API or inspection action');

function nodes(element) {
  if (Array.isArray(element)) return element.flatMap(nodes);
  if (!element || typeof element !== 'object') return [];
  return [element, ...nodes(element.props?.children)];
}

function tabs() {
  const hooks = [];
  let cursor = 0;
  const focused = [];
  const fakeReact = { ...React,
    useState: initial => {
      const index = cursor++;
      if (!(index in hooks)) hooks[index] = initial;
      return [hooks[index], value => { hooks[index] = value; }];
    },
    useRef: initial => {
      const index = cursor++;
      if (!(index in hooks)) hooks[index] = { current: initial };
      return hooks[index];
    },
  };
  const exports = {};
  runInNewContext(compiled.outputText, { exports, fetch: forbidden, require: name => {
    if (name === 'react') return fakeReact;
    if (name === 'react/jsx-runtime') return require(name);
    assert.fail(`Unexpected dependency ${name}`);
  } });
  const props = {
    grabPanel: React.createElement('section', { 'data-source': 'LIVEVIEW_GRAB', onInspect: forbidden },
      React.createElement('input', { value: 'GRAB-PRODUCT' })),
    judgePanel: React.createElement('section', { 'data-source': 'JUDGE', onRequest: forbidden },
      React.createElement('input', { type: 'checkbox', checked: true })),
    staticImagePanel: React.createElement('section', { 'data-source': 'REGISTERED STATIC IMAGE', onInspect: forbidden },
      React.createElement('input', { value: 'HISTORY-EDIT-IN-PROGRESS' })),
  };
  const render = () => {
    cursor = 0;
    const tree = exports.InspectionTabs(props);
    for (const button of nodes(tree).filter(node => node.props?.role === 'tab')) {
      button.props.ref.current = { focus: () => focused.push(button.props.id) };
    }
    return tree;
  };
  const buttons = () => nodes(render()).filter(node => ['grab-inspection-tab', 'static-inspection-tab'].includes(node.props?.id));
  const panels = () => nodes(render()).filter(node => ['grab-inspection-panel', 'static-inspection-panel'].includes(node.props?.id));
  const stageButtons = () => nodes(render()).filter(node => ['patchcore-inspection-tab', 'judge-inspection-tab'].includes(node.props?.id));
  const stagePanels = () => nodes(render()).filter(node => ['patchcore-inspection-panel', 'judge-inspection-panel'].includes(node.props?.id));
  return { props, render, buttons, panels, stageButtons, stagePanels, focused };
}

test('Grab is the default tab and both panels are mounted with accessible relationships', () => {
  const view = tabs();
  assert.deepEqual(view.buttons().map(button => button.props['aria-selected']), [true, false]);
  assert.deepEqual(view.panels().map(panel => panel.props.hidden), [false, true]);
  for (const [index, button] of view.buttons().entries()) {
    const panel = view.panels()[index];
    assert.equal(button.props['aria-controls'], panel.props.id);
    assert.equal(panel.props['aria-labelledby'], button.props.id);
  }
});

test('switching tabs only hides panels without replacing their mounted subtree or draft inputs', () => {
  const view = tabs();
  const original = view.panels();
  for (const target of [1, 0, 1, 0]) {
    view.buttons()[target].props.onClick();
    assert.equal(view.buttons()[target].props['aria-selected'], true);
    assert.equal(view.panels()[target].props.hidden, false);
    for (const [index, panel] of view.panels().entries()) {
      assert.equal(panel.type, original[index].type);
      assert.equal(panel.key, original[index].key);
      if (index === 1) assert.equal(panel.props.children, original[index].props.children);
    }
    assert.equal(view.props.staticImagePanel.props.children.props.value, 'HISTORY-EDIT-IN-PROGRESS');
    assert.equal(view.props.grabPanel.props.children.props.value, 'GRAB-PRODUCT');
  }
});

test('new Grab props update the hidden Grab panel without changing the static selection or source', () => {
  const view = tabs();
  view.buttons()[1].props.onClick();
  const staticPanel = view.props.staticImagePanel;
  view.props.grabPanel = React.createElement('section', {
    'data-source': 'LIVEVIEW_GRAB', 'data-inspection-id': 'INSP-SYNTHETIC-NEW', onInspect: forbidden,
  });
  assert.equal(view.stagePanels()[0].props.children.props['data-inspection-id'], 'INSP-SYNTHETIC-NEW');
  assert.equal(view.panels()[0].props.hidden, true);
  assert.equal(view.panels()[1].props.children, staticPanel);
  view.buttons()[0].props.onClick();
  assert.equal(view.stagePanels()[0].props.children.props['data-source'], 'LIVEVIEW_GRAB');
  assert.equal(view.panels()[1].props.children.props['data-source'], 'REGISTERED STATIC IMAGE');
});

test('arrow and Home/End keys select and focus tabs without invoking inspection actions', () => {
  const view = tabs();
  let prevented = 0;
  for (const [index, key, selected] of [[0, 'ArrowRight', 1], [1, 'ArrowRight', 0],
    [0, 'End', 1], [1, 'Home', 0], [0, 'ArrowLeft', 1]]) {
    view.buttons()[index].props.onKeyDown({ key, preventDefault: () => { prevented++; } });
    assert.equal(view.buttons()[selected].props.tabIndex, 0);
    assert.equal(view.focused.at(-1), view.buttons()[selected].props.id);
  }
  assert.equal(prevented, 5);
  view.buttons()[1].props.onKeyDown({ key: 'Tab', preventDefault: forbidden });
  assert.equal(view.buttons()[1].props['aria-selected'], true);
});

test('PatchCore is the default Grab stage and Judge is mounted once in the same tab area', () => {
  const view = tabs();
  assert.deepEqual(view.stageButtons().map(button => button.props['aria-selected']), [true, false]);
  assert.deepEqual(view.stagePanels().map(panel => panel.props.hidden), [false, true]);
  assert.equal(nodes(view.render()).filter(node => node.props?.['data-source'] === 'JUDGE').length, 1);
  for (const [index, button] of view.stageButtons().entries()) {
    assert.equal(button.props['aria-controls'], view.stagePanels()[index].props.id);
    assert.equal(view.stagePanels()[index].props['aria-labelledby'], button.props.id);
  }
});

test('subtab and outer-tab round trips retain both stage subtrees and consent without actions', () => {
  const view = tabs();
  const original = view.stagePanels();
  for (const stage of [1, 0, 1]) {
    view.stageButtons()[stage].props.onClick();
    view.buttons()[1].props.onClick();
    view.buttons()[0].props.onClick();
    assert.equal(view.stageButtons()[stage].props['aria-selected'], true);
    assert.equal(view.stagePanels()[stage].props.hidden, false);
    for (const [index, panel] of view.stagePanels().entries()) {
      assert.equal(panel.type, original[index].type);
      assert.equal(panel.key, original[index].key);
      assert.equal(panel.props.children, original[index].props.children);
    }
    assert.equal(view.props.judgePanel.props.children.props.checked, true);
  }
});

test('Grab subtab keyboard selection is independent of the outer tab', () => {
  const view = tabs();
  for (const [index, key, next] of [[0, 'ArrowRight', 1], [1, 'Home', 0], [0, 'End', 1], [1, 'ArrowLeft', 0]]) {
    let prevented = false;
    view.stageButtons()[index].props.onKeyDown({ key, preventDefault: () => { prevented = true; } });
    assert.equal(prevented, true);
    assert.equal(view.stageButtons()[next].props['aria-selected'], true);
    assert.equal(view.focused.at(-1), view.stageButtons()[next].props.id);
    assert.equal(view.buttons()[0].props['aria-selected'], true);
  }
});
