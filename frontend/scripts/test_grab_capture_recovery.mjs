import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import React from 'react';
import ts from 'typescript';
import * as recovery from '../src/utils/reinspectionRecovery.ts';
import * as workflow from '../src/utils/reinspectionState.ts';
import * as grab from '../src/utils/grabInspectionState.ts';
import * as quality from '../src/utils/inspectionQualitySummary.ts';

const require=createRequire(import.meta.url);
const compiled=ts.transpileModule(readFileSync(new URL('../src/components/GrabInspectionPanel.tsx',import.meta.url),'utf8'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}});
const crop={captureId:'CAP-NEW',videoId:'VID-SYNTHETIC',sourceRevision:'a'.repeat(64),frameIndex:20,
  roi:{x:10,y:20,width:40,height:40},width:40,height:40};
const metadata={capture_id:crop.captureId,video_id:crop.videoId,source_revision:crop.sourceRevision,
  frame_index:crop.frameIndex,width:1920,height:480,status:'CAPTURED'};
const missing={status:404,data:{detail:{error_code:'REINSPECTION_GROUP_NOT_FOUND'}}};
const forbidden=()=>assert.fail('No inspection, model, Gemini, real API or manual-review writes');
function nodes(element){
  if(Array.isArray(element))return element.flatMap(nodes);
  return element&&typeof element==='object'?[element,...nodes(element.props?.children)]:[];
}
function text(element){
  if(Array.isArray(element))return element.map(text).join(' ');
  return typeof element==='string'||typeof element==='number'?String(element):element&&typeof element==='object'?text(element.props?.children):'';
}
function panel(savedGroup=null){
  const hooks=[];let cursor=0;let effects=[];
  const hints=new Map([[recovery.PENDING_CAPTURE_HINT_KEY,'CAP-OLD'],['unrelated','KEEP']]);
  if(savedGroup)hints.set(recovery.GROUP_HINT_KEY,savedGroup.group_id);
  const requests=[];const controls={confirm:true,captureFailure:null,allowManual:false,manualRequests:[]};
  const effect=(callback,dependencies)=>{
    const index=cursor++;const previous=hooks[index];
    if(!previous||dependencies.some((value,offset)=>value!==previous.dependencies[offset])){
      effects.push(()=>{previous?.cleanup?.();hooks[index]={dependencies,cleanup:callback()};});
    }
  };
  const fakeReact={...React,useEffect:effect,useLayoutEffect:effect,
    useState:initial=>{const index=cursor++;if(!(index in hooks))hooks[index]={value:initial};
      return [hooks[index].value,value=>{hooks[index].value=value;}];},
    useRef:initial=>{const index=cursor++;if(!(index in hooks))hooks[index]={current:initial};return hooks[index];},
  };
  const dependencies={react:fakeReact,'react/jsx-runtime':require('react/jsx-runtime'),
    '../utils/reinspectionRecovery':recovery,'../utils/reinspectionState':workflow,
    '../utils/grabInspectionState':grab,'../utils/inspectionQualitySummary':quality,
    '../api/inspection':{createGrabInspection:forbidden,getInspection:forbidden,
      saveManualReview:async (group,result,operator,reason)=>{
        if(!controls.allowManual)return forbidden();
        controls.manualRequests.push({result,operator,reason,inspectionId:group.current_inspection_id});
        return {...group,version:group.version+1,status:result==='HOLD'?'MANUAL_REVIEW_REQUIRED':'MANUAL_REVIEWED',
          manual_reviews:[...group.manual_reviews,{review_id:'REV-SYNTHETIC',result,operator_id:operator,reason,timestamp:'SYNTHETIC_TIME'}]};
      },
      getCaptureReinspectionGroup:async identifier=>{requests.push(['CAPTURE_GROUP',identifier]);
        if(identifier==='CAP-OLD')throw {status:404,data:{detail:{error_code:'CAPTURE_NOT_FOUND'}}};throw missing;},
      getReinspectionGroup:async identifier=>{requests.push(['GROUP',identifier]);if(savedGroup)return savedGroup;throw missing;},
    },
    '../api/video':{getCaptureMetadata:async identifier=>{requests.push(['CAPTURE',identifier]);
      if(controls.captureFailure)throw controls.captureFailure;return metadata;}},
  };
  const exports={};
  runInNewContext(compiled.outputText,{exports,fetch:forbidden,crypto:{randomUUID:()=> 'SYNTHETIC'},
    window:{confirm:()=>controls.confirm},localStorage:{getItem:key=>hints.get(key)??null,
      setItem:(key,value)=>hints.set(key,value),removeItem:key=>hints.delete(key)},
    require:name=>{assert.ok(Object.hasOwn(dependencies,name));return dependencies[name];}});
  const props={crop:null,enabled:true,manualMode:true,currentInspection:null,onSelectionStart:()=>1,onInspectionChange:forbidden};
  const render=()=>{cursor=0;effects=[];const tree=exports.GrabInspectionPanel(props);for(const callback of effects)callback();return tree;};
  const button=label=>nodes(render()).find(node=>node.type==='button'&&text(node)===label);
  const settle=async()=>{for(let count=0;count<8;count++)await Promise.resolve();return render();};
  return {render,button,settle,props,hints,requests,controls};
}

test('actual Grab panel recovers a new Capture after an old pending-session 404 only after explicit new-product confirmation',async()=>{
  const view=panel();view.render();await view.settle();
  assert.equal(view.button('Grab 이미지 검사').props.disabled,true);
  assert.match(text(view.render()),/이전 대기 Capture CAP-OLD 복원 실패/);
  view.props.crop=crop;view.render();
  view.button('저장 그룹 새로 조회').props.onClick();await view.settle();
  assert.match(text(view.render()),/현재 Capture CAP-NEW의 소유권/);
  assert.equal(view.requests.filter(([,identifier])=>identifier==='CAP-OLD').length,1);
  assert.equal(view.button('Grab 이미지 검사').props.disabled,true);
  view.controls.confirm=false;
  view.button('새 제품 검사 시작').props.onClick();await view.settle();
  assert.equal(view.button('Grab 이미지 검사').props.disabled,true);
  view.controls.confirm=true;
  view.button('새 제품 검사 시작').props.onClick();await view.settle();
  assert.equal(view.button('Grab 이미지 검사').props.disabled,false);
  assert.deepEqual([...view.hints],[['unrelated','KEEP']]);
});

test('actual current Capture 404 and API 500 do not unlock the inspection',async()=>{
  for(const status of [404,500]){
    const view=panel();view.render();await view.settle();view.props.crop=crop;
    view.controls.captureFailure={status,data:{detail:{error_code:'CAPTURE_NOT_FOUND'}}};
    view.button('저장 그룹 새로 조회').props.onClick();await view.settle();
    assert.equal(view.button('Grab 이미지 검사').props.disabled,true);
    assert.match(text(view.render()),/현재 Capture CAP-NEW 상태 조회 실패/);
    assert.ok(text(view.render()).includes(`HTTP ${status}`));
  }
});

test('a restored terminal RIG is not replaced by an unused new Capture',async()=>{
  const group={group_id:'RIG-EXISTING',product_id:'PRODUCT',attempt_count:3,remaining_attempts:0,
    status:'MANUAL_REVIEWED',attempts:[],failed_attempts:[],manual_reviews:[]};
  const before=structuredClone(group);const view=panel(group);
  view.hints.delete(recovery.PENDING_CAPTURE_HINT_KEY);
  view.render();await view.settle();view.props.crop=crop;
  view.button('저장 그룹 새로 조회').props.onClick();await view.settle();
  assert.equal(view.button('Grab 이미지 검사').props.disabled,true);
  assert.match(text(view.render()),/MANUAL_REVIEWED/);
  assert.equal(view.hints.get(recovery.GROUP_HINT_KEY),group.group_id);
  assert.deepEqual(group,before);
});

for(const result of ['HOLD','MANUAL_OK','MANUAL_NG']){
  test(`judge-assisted first REINSPECT supports explicit ${result} without any Judge call`,async()=>{
    const group={workflow_policy:'judge-assisted-v1',group_id:'RIG-ASSISTED',product_id:'PRODUCT',version:1,
      current_inspection_id:'INSP-SYNTHETIC',attempt_count:1,remaining_attempts:null,max_attempts:null,
      status:'MANUAL_REVIEW_REQUIRED',attempts:[{inspection_id:'INSP-SYNTHETIC',attempt_number:1,
        result:'OK',final_result:'REINSPECT',input_provenance:{capture_id:'CAP-FIRST'}}],failed_attempts:[],manual_reviews:[]};
    const original=structuredClone(group);const view=panel(group);
    view.hints.delete(recovery.PENDING_CAPTURE_HINT_KEY);view.controls.allowManual=true;
    view.render();await view.settle();
    assert.match(text(view.render()),/3차 작업자 최종 확인/);
    assert.doesNotMatch(text(view.render()),/한도 도달|검사 1 \/ 3|남은 null/);
    assert.equal(view.button('수동 확인 저장').props.disabled,true);
    const field=label=>nodes(view.render()).find(node=>node.props?.['aria-label']===label);
    field('작업자 표시명').props.onChange({target:{value:'SYNTHETIC_OPERATOR'}});
    field('수동 판단 사유').props.onChange({target:{value:'SYNTHETIC_REASON'}});
    field('수동 결과').props.onChange({target:{value:result}});
    assert.equal(view.button('수동 확인 저장').props.disabled,false);
    view.button('수동 확인 저장').props.onClick();await view.settle();
    assert.deepEqual(view.controls.manualRequests,[{result,operator:'SYNTHETIC_OPERATOR',reason:'SYNTHETIC_REASON',inspectionId:'INSP-SYNTHETIC'}]);
    assert.match(text(view.render()),new RegExp(result));
    assert.deepEqual(group,original);
  });
}
