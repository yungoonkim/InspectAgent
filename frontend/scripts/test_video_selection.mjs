import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { runInNewContext } from 'node:vm';
import test from 'node:test';
import React from 'react';
import ts from 'typescript';
import * as lifetime from '../src/utils/roiLifetime.ts';
import * as coordinates from '../src/utils/coordinateTransforms.ts';
import * as frames from '../src/utils/videoFrames.ts';

const require=createRequire(import.meta.url);
const forbidden=()=>assert.fail('No actual API, Grab, inspection, model or Gemini calls');
const videos=[['VID-000002',240],['VID-000001',240],['VID-000003',480]].map(([video_id,frame_count])=>({
  video_id,frame_count,width:1920,height:480,fps:30,duration_seconds:frame_count/30,
  source_revision:video_id.repeat(7).slice(0,64),stream_url:`/videos/${video_id}/stream`,
}));
function nodes(element){
  if(Array.isArray(element))return element.flatMap(nodes);
  return element&&typeof element==='object'?[element,...nodes(element.props?.children)]:[];
}
function mount(filename,name,dependencies,props={}){
  const hooks=[];let cursor=0;let effects=[];
  const memo=(callback,dependencies)=>{
    const index=cursor++;const previous=hooks[index];
    if(!previous||dependencies.some((value,offset)=>value!==previous.dependencies[offset]))hooks[index]={dependencies,value:callback};
    return hooks[index].value;
  };
  const fakeReact={...React,useCallback:memo,
    useState:initial=>{const index=cursor++;if(!(index in hooks))hooks[index]={value:initial};
      return [hooks[index].value,value=>{hooks[index].value=typeof value==='function'?value(hooks[index].value):value;}];},
    useRef:initial=>{const index=cursor++;if(!(index in hooks))hooks[index]={current:initial};return hooks[index];},
    useEffect:(callback,dependencies)=>{
      const index=cursor++;const previous=hooks[index];
      if(!previous||dependencies.some((value,offset)=>value!==previous.dependencies[offset]))effects.push(()=>{
        previous?.cleanup?.();hooks[index]={dependencies,cleanup:callback()};
      });
    },
  };
  const compiled=ts.transpileModule(readFileSync(new URL(filename,import.meta.url),'utf8'),{compilerOptions:{
    module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022,esModuleInterop:true,
  }});
  const exports={};
  runInNewContext(compiled.outputText,{exports,console,fetch:forbidden,setInterval:()=>1,clearInterval:()=>{},
    require:module=>{
      if(module==='react')return fakeReact;
      if(module==='react/jsx-runtime')return require(module);
      assert.ok(Object.hasOwn(dependencies,module),`Unexpected dependency ${module}`);
      return dependencies[module];
    }});
  const render=()=>{cursor=0;effects=[];const tree=exports[name](props);for(const effect of effects)effect();return tree;};
  const settle=async()=>{for(let count=0;count<8;count++)await Promise.resolve();return render();};
  return {render,settle};
}
function application(){
  const slots={};const dependencies={};const requests=[];
  for(const name of ['Header','WorkflowStepper','LiveView','ImageView','InspectionPanel','GrabInspectionPanel','InspectionTabs','AgentPanel','VisionReviewPanel']){
    slots[name]=()=>null;dependencies[`./components/${name}`]={[name]:slots[name]};
  }
  Object.assign(dependencies,{
    './api/video':{checkHealth:async()=>true,ensureCaptureSession:async()=> 'OFFLINE_ONLY',
      getVideos:async()=>{requests.push('GET_VIDEOS');return {videos};},getVideoStreamUrl:identifier=>`/api/videos/${identifier}/stream`,
      grabFrame:forbidden,fetchCaptureImageBlob:forbidden},
    './utils/imageCropper':{loadImageFromUrl:forbidden,cropExactPixels:forbidden},
    './utils/coordinateTransforms':coordinates,'./utils/roiLifetime':lifetime,
  });
  const view=mount('../src/App.tsx','App',dependencies);
  const component=name=>nodes(view.render()).find(node=>node.type===slots[name]);
  const select=identifier=>nodes(view.render()).find(node=>node.type==='select').props.onChange({target:{value:identifier}});
  return {...view,component,select,requests};
}

test('all three server videos are selectable while the existing default remains unchanged',async()=>{
  const view=application();view.render();await view.settle();
  assert.equal(view.component('LiveView').props.video.video_id,'VID-000002');
  assert.equal(nodes(view.render()).filter(node=>node.type==='option').length,3);
  for(const video of videos){
    view.select(video.video_id);
    assert.equal(view.component('LiveView').props.video,video);
    assert.equal(view.component('LiveView').props.streamUrl,`/api/videos/${video.video_id}/stream`);
  }
  assert.deepEqual(view.requests,['GET_VIDEOS']);
});

test('source switching resets stale ROI/selection but preserves the server-owned reinspection group',async()=>{
  const view=application();view.render();await view.settle();
  const tabs=view.component('InspectionTabs');
  const group={group_id:'RIG-SYNTHETIC',attempt_count:3,status:'MANUAL_REVIEW_REQUIRED'};
  tabs.props.grabPanel.props.onGroupChange(group);
  const oldVersion=tabs.props.staticImagePanel.props.getSelectionVersion();
  view.component('LiveView').props.onChangeRoi({x:100,y:100,width:100,height:100});
  const beforeKey=view.component('LiveView').key;
  view.select('VID-000003');
  const live=view.component('LiveView');
  assert.notEqual(live.key,beforeKey);
  assert.equal(live.props.video.frame_count,480);
  assert.equal(live.props.roiState,'NO_ROI');
  assert.equal(live.props.roi.width,320);
  assert.equal(live.props.capture,null);
  assert.equal(view.component('InspectionTabs').props.judgePanel.props.reinspectionGroup,group);
  tabs.props.staticImagePanel.props.onInspectionChange({inspection_id:'INSP-STALE'},oldVersion);
  assert.equal(view.component('InspectionTabs').props.staticImagePanel.props.currentInspection,null);
  view.select('VID-INVALID');
  assert.equal(view.component('LiveView').props.video.video_id,'VID-000003');
});

test('16-second playback, Pause, Seek and ROI use frame 479 without making a Grab API request',()=>{
  const actions=[];
  const props={video:videos[2],streamUrl:'/api/videos/VID-000003/stream',isGrabbing:false,
    onGrab:frame=>actions.push(['GRAB_CALLBACK_ONLY',frame]),mode:'MANUAL',error:null,capture:null,imageBlobUrl:null,
    roi:{x:800,y:80,width:320,height:320},roiState:'APPLIED',cropMessage:null,
    onChangeRoi:forbidden,onResetRoi:forbidden,onToggleRoi:(frame,paused)=>actions.push(['ROI_CALLBACK_ONLY',frame,paused])};
  const view=mount('../src/components/LiveView.tsx','LiveView',{'lucide-react':require('lucide-react'),
    '../utils/coordinateTransforms':coordinates,'../utils/videoFrames':frames,'./RoiOverlay':{RoiOverlay:()=>null}},props);
  const videoElement={paused:false,currentTime:0,pause(){this.paused=true;},async play(){this.paused=false;}};
  const tree=view.render();
  nodes(tree).find(node=>node.type==='video').props.ref.current=videoElement;
  nodes(tree).find(node=>node.props?.title==='일시정지 (Pause)').props.onClick();
  assert.equal(videoElement.paused,true);
  const slider=nodes(view.render()).find(node=>node.props?.title==='비디오 위치 탐색 (Seek)');
  assert.equal(slider.props.max,16);
  slider.props.onChange({target:{value:'16'}});
  nodes(view.render()).find(node=>node.props?.title==='현재 프레임을 Grab하고 저장 ROI를 적용합니다. 같은 녹화 프레임은 새 정보가 아닙니다.').props.onClick();
  assert.deepEqual(actions,[['GRAB_CALLBACK_ONLY',479]]);
  assert.ok(videoElement.currentTime >= 479 / 30 && videoElement.currentTime < 16);
});
