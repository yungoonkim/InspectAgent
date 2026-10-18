import assert from 'node:assert/strict';

export const roiHarnessSource = `
import React from 'react';
import {createRoot} from 'react-dom/client';
import {App} from '/src/App.tsx';
import '/src/index.css';
const times=new WeakMap(),pauses=new WeakMap();
Object.defineProperty(HTMLMediaElement.prototype,'currentTime',{get(){return times.get(this)||0;},set(value){times.set(this,value);this.dispatchEvent(new Event('timeupdate'));},configurable:true});
Object.defineProperty(HTMLMediaElement.prototype,'paused',{get(){return pauses.get(this)||false;},configurable:true});
HTMLMediaElement.prototype.play=function(){pauses.set(this,false);return Promise.resolve();};
HTMLMediaElement.prototype.pause=function(){pauses.set(this,true);};
const setAttribute=Element.prototype.setAttribute;
Element.prototype.setAttribute=function(name,value){if(this instanceof HTMLVideoElement&&name==='src'){this.dataset.mockSrc=String(value);return;}return setAttribute.call(this,name,value);};
const canvas=document.createElement('canvas');canvas.width=1920;canvas.height=480;
const context=canvas.getContext('2d');const image=context.createImageData(1920,480);
for(let row=0;row<480;row++)for(let column=0;column<1920;column++){const offset=(row*1920+column)*4;image.data.set([column%256,row%256,(column+row)%256,255],offset);}
context.putImageData(image,0,0);
const NativeImage=window.Image;const nativeSrc=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');
window.Image=function(){const result=new NativeImage();Object.defineProperty(result,'src',{set(url){if(String(url).includes('/input-image')){const crop=document.createElement('canvas');crop.width=320;crop.height=320;crop.getContext('2d').drawImage(canvas,800,80,320,320,0,0,320,320);nativeSrc.set.call(result,crop.toDataURL());}else nativeSrc.set.call(result,url);}});return result;};
const grabs=[],inspections=[],blocked=[],cropPixels=[];let group=null;
const getImageData=CanvasRenderingContext2D.prototype.getImageData;
CanvasRenderingContext2D.prototype.getImageData=function(...args){const result=getImageData.apply(this,args);if(this.canvas.width===320&&this.canvas.height===320)cropPixels.push(Array.from(result.data.slice(0,4)));return result;};
const video={video_id:'VID-000001',source_revision:'a'.repeat(64),width:1920,height:480,fps:30,frame_count:240,duration_seconds:8,codec:'h264',frame_index_min:0,frame_index_max:239};
function pngResponse(value){const bytes=Uint8Array.from(atob(value.split(',')[1]),character=>character.charCodeAt(0));return new Response(bytes,{headers:{'Content-Type':'image/png'}});}
window.fetch=async(input,options={})=>{
 const url=new URL(typeof input==='string'?input:input.url,location.href);
 if(url.origin!==location.origin)throw Error('External request forbidden');
 const name=url.pathname.replace(/^\\/api/,'');
 if(name==='/health')return Response.json({status:'ok'});
 if(name==='/capture-sessions')return Response.json({csrf_token:'MOCK',session_ttl_seconds:3600});
 if(name==='/videos')return Response.json({videos:[video]});
 if(name==='/inspections/images')return Response.json({image_ids:['IMG-MOCK'],sample_ids:[],total_images:1});
 if(name==='/inspections')return Response.json({inspections:[],total:0});
 if(name==='/inspections/INSP-001396/agent-report')return Response.json({detail:{error_code:'REPORT_NOT_AVAILABLE'}},{status:404});
 if(name==='/videos/VID-000001/grab'){const body=JSON.parse(options.body);grabs.push(body);return Response.json({...video,capture_id:'CAP-MOCK-'+grabs.length,frame_index:body.frame_index,created_at:'MOCK',image_url:'MOCK'});}
 if(name.match(/^\\/captures\\/CAP-MOCK-\\d+\\/image$/)){const index=Number(name.split('/')[2].split('-').at(-1))-1;const updated=document.createElement('canvas');updated.width=1920;updated.height=480;const brush=updated.getContext('2d');brush.drawImage(canvas,0,0);brush.fillStyle='rgb('+grabs[index].frame_index%256+',0,0)';brush.fillRect(0,0,1,1);return pngResponse(updated.toDataURL());}
 if(name.match(/^\\/captures\\/CAP-MOCK-\\d+\\/inspect$/)){
  inspections.push(JSON.parse(options.body));const payload=inspections.at(-1);const captureId=name.split('/')[2];
  const result={inspection_id:'INSP-MOCK-ROI',image_id:'IMG-GRAB-MOCK',product_id:payload.product_id,final_result:'REINSPECT',result:'NG',anomaly_score:40,decision_threshold:34.1442,image_quality_status:'WARNING_LOW_BRIGHTNESS',final_reason_code:'IMAGE_QUALITY_WARNING',metrics:{reinspection:{group_id:'RIG-MOCK-ROI'},input_source:'LIVEVIEW_GRAB',anomaly_map_available:false,input_provenance:{capture_id:captureId,video_id:video.video_id,source_revision:video.source_revision,frame_index:grabs.at(-1).frame_index,roi:payload.roi,crop_width:payload.roi.width,crop_height:payload.roi.height,crop_sha256:'c'.repeat(64)}}};
  group={group_id:'RIG-MOCK-ROI',product_id:payload.product_id,version:1,status:'RETRY_ALLOWED',attempt_count:1,remaining_attempts:2,max_attempts:3,current_inspection_id:result.inspection_id,attempts:[{...result,attempt_number:1,input_provenance:result.metrics.input_provenance}],failed_attempts:[],manual_reviews:[]};return Response.json(result);
 }
 if(name==='/reinspection-groups/RIG-MOCK-ROI')return Response.json(group);
 if(name==='/inspections/INSP-MOCK-ROI/anomaly-map')return Response.json({detail:{error_code:'MAP_NOT_AVAILABLE'}},{status:404});
 if(name==='/inspections/INSP-MOCK-ROI/vision-review')return Response.json({available:false,review:null,capabilities:{enabled:false,live_enabled:false,analysis_mode:'DISABLED',reason:'VISION_LIVE_DISABLED',model_requested:'gemini-4-argon'}});
 blocked.push(name);throw Error('Non-Mock backend request forbidden '+name);
};
window.step81={ready:true,grabs,inspections,blocked,cropPixels,expected:()=>Array.from(image.data.slice((80*1920+800)*4,(80*1920+800)*4+4))};
createRoot(document.getElementById('root')).render(<App/>);
`;

export async function runRoiChecks({check,evaluate,waitFor}) {
  const click = text => evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.trim()===${JSON.stringify(text)}).click()`);
  const roiBox = () => evaluate("(()=>{const style=document.querySelector('.roi-bounding-box').style;return [style.left,style.top,style.width,style.height];})()");
  let rectangle;
  await check('initial ROI is explicitly selected against a Mock source frame',async()=>{
    await waitFor("document.querySelector('video')!==null");await click('Pause');await click('ROI 선택');
    await waitFor("document.querySelector('.roi-bounding-box')!==null");
    rectangle=await roiBox();assert.equal(await evaluate('window.step81.grabs.length'),1);
  });
  await check('ROI Crop uses exact unscaled original pixels and no extra Grab',async()=>{
    await evaluate("document.querySelector('.grab-cta-button').click()");
    await waitFor("document.body.textContent.includes('320×320') && document.body.textContent.includes('CAP-MOCK-1')");
    assert.equal(await evaluate('window.step81.grabs.length'),1);
    assert.deepEqual(await evaluate('window.step81.cropPixels.at(-1)'),[32,80,112,255]);
    assert.deepEqual(await roiBox(),rectangle);
  });
  await check('Fake REINSPECT retains ROI and exposes disabled same-image second opinion',async()=>{
    await click('Grab 이미지 검사');await waitFor("document.body.textContent.includes('검사 1 / 3')");
    assert.deepEqual(await roiBox(),rectangle);
    await waitFor("document.body.textContent.includes('VISION_LIVE_DISABLED')");
    assert.ok(await evaluate("[...document.querySelectorAll('button')].find(button=>button.textContent==='현재 Crop Gemini 2차 분석').disabled"));
  });
  await check('Play and Pause preserve geometry and do not retain stale frozen image',async()=>{
    await click('Play');assert.deepEqual(await roiBox(),rectangle);
    assert.equal(await evaluate("document.querySelector('.frozen-frame-layer')!==null"),false);
    await click('Pause');assert.deepEqual(await roiBox(),rectangle);
  });
  await check('Seek and Frame Step preserve original ROI coordinates',async()=>{
    await evaluate("const range=document.querySelector('input[type=range]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(range,'2');range.dispatchEvent(new Event('input',{bubbles:true}));range.dispatchEvent(new Event('change',{bubbles:true}));");
    await click('+1 Frame');assert.deepEqual(await roiBox(),rectangle);
  });
  await check('next frame Grab applies saved ROI to a distinct Capture without editing',async()=>{
    await evaluate("document.querySelector('.grab-cta-button').click()");
    await waitFor("document.body.textContent.includes('CAP-MOCK-2') && document.body.textContent.includes('기존 ROI 320×320px 적용')");
    assert.equal(await evaluate('window.step81.grabs.length'),2);
    assert.deepEqual(await roiBox(),rectangle);
    assert.equal(await evaluate('window.step81.inspections.length'),1);
  });
  await check('same recorded frame is not minted into another Capture or inspection',async()=>{
    await evaluate("document.querySelector('.grab-cta-button').click()");
    await waitFor("document.body.textContent.includes('같은 프레임은 새 광학 정보가 아닙니다')");
    assert.equal(await evaluate('window.step81.grabs.length'),2);
    assert.equal(await evaluate('window.step81.inspections.length'),1);
  });
  await check('only explicit ROI reset clears the retained selection',async()=>{
    await click('ROI 초기화');await waitFor("document.querySelector('.roi-bounding-box')===null");
    assert.deepEqual(await evaluate('window.step81.blocked'),[]);
  });
}
