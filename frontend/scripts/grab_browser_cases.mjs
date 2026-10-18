import assert from 'node:assert/strict';

export const grabHarnessSource = `
import React, { useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { GrabInspectionPanel } from '/src/components/GrabInspectionPanel.tsx';
import { ImageView } from '/src/components/ImageView.tsx';
import '/src/index.css';

function pixels(width, height, color) {
  const canvas=document.createElement('canvas'); canvas.width=width; canvas.height=height;
  const context=canvas.getContext('2d'); context.fillStyle=color; context.fillRect(0,0,width,height);
  return {url:canvas.toDataURL('image/png'),imageData:context.getImageData(0,0,width,height)};
}
const source=pixels(160,96,'rgb(20, 40, 60)');
const overlay=pixels(160,96,'rgb(230, 10, 20)');
const NativeImage=window.Image;
const nativeSrc=Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');
const seenImages=[];
window.Image=function() {
  const image=new NativeImage();
  Object.defineProperty(image,'src',{set(url) {
    const value=String(url); seenImages.push(value);
    if(value.startsWith('data:image/png')) { nativeSrc.set.call(image,value); return; }
    if(value.match(/\\/inspections\\/INSP-SYNTHETIC-[A-Z]\\/input-image$/)) { nativeSrc.set.call(image,source.url); return; }
    if(value.match(/\\/inspections\\/INSP-SYNTHETIC-[A-Z]\\/anomaly-map\\/overlay.png$/)) { nativeSrc.set.call(image,overlay.url); return; }
    throw new Error('Unexpected synthetic image URL');
  }});
  return image;
};
const jobs=[];
const groups={};
const records={};
const reviews=[];
const blocked=[];
const drawCalls=[];
const originalDraw=CanvasRenderingContext2D.prototype.drawImage;
CanvasRenderingContext2D.prototype.drawImage=function(image,...rectangle) {
  if(this.canvas.classList.contains('precision-canvas')) { drawCalls.push({rectangle,alpha:this.globalAlpha}); if(drawCalls.length>2) drawCalls.shift(); }
  return originalDraw.call(this,image,...rectangle);
};
window.fetch=(input,options={})=> {
  const url=new URL(typeof input==='string'?input:input.url,location.href);
  const method=options.method||'GET';
  if(url.origin!==location.origin) throw new Error('External request forbidden');
  if(method==='POST' && url.pathname==='/api/capture-sessions') return Promise.resolve(new Response(JSON.stringify({csrf_token:'SYNTHETIC',session_ttl_seconds:3600}),{headers:{'Content-Type':'application/json'}}));
  if(method==='POST' && url.pathname.match(/^\\/api\\/captures\\/CAP-SYNTHETIC-[A-Z]\\/inspect$/)) {
    return new Promise(resolve=>jobs.push({body:JSON.parse(options.body),path:url.pathname,resolve}));
  }
  const groupMatch=url.pathname.match(/^\\/api\\/reinspection-groups\\/(RIG-SYNTHETIC-[A-Z])$/);
  if(method==='GET' && groupMatch && groups[groupMatch[1]]) return Promise.resolve(Response.json(groups[groupMatch[1]]));
  const reviewMatch=url.pathname.match(/^\\/api\\/reinspection-groups\\/(RIG-SYNTHETIC-[A-Z])\\/manual-reviews$/);
  if(method==='POST' && reviewMatch) {
    const body=JSON.parse(options.body); const group=groups[reviewMatch[1]];
    reviews.push(body); group.manual_reviews.push({...body,review_id:'REV-SYNTHETIC-'+reviews.length,timestamp:'SYNTHETIC',authority:'DEVELOPMENT_SELF_DECLARED_NOT_AUTHENTICATED'});
    group.version++; if(body.result!=='HOLD')group.status='MANUAL_REVIEWED';
    return Promise.resolve(Response.json(group));
  }
  const recordMatch=url.pathname.match(/^\\/api\\/inspections\\/(INSP-SYNTHETIC-[A-Z])$/);
  if(method==='GET' && recordMatch && records[recordMatch[1]]) return Promise.resolve(Response.json(records[recordMatch[1]]));
  const match=url.pathname.match(/^\\/api\\/inspections\\/(INSP-SYNTHETIC-[A-Z])\\/anomaly-map$/);
  if(method==='GET' && match) return Promise.resolve(new Response(JSON.stringify({schema_version:'1.1.0',inspection_id:match[1],image_id:'IMG-GRAB-'+match[1],
    model_name:'MOCK_TEST_ONLY',original_image_width:160,original_image_height:96,anomaly_map_width:256,anomaly_map_height:256,localization_available:true,available:true}),{headers:{'Content-Type':'application/json'}}));
  blocked.push({method,path:url.pathname}); throw new Error('Non-Mock transport forbidden');
};
window.step7={jobs,groups,records,reviews,blocked,drawCalls,seenImages,ready:false};
function makeCrop(suffix) { return {cropBlobUrl:source.url,imageData:source.imageData,width:160,height:96,roi:{x:17,y:21,width:160,height:96},
  captureId:'CAP-SYNTHETIC-'+suffix,videoId:'VID-000001',sourceRevision:'a'.repeat(64),frameIndex:120+suffix.charCodeAt(0)-65,createdAt:'SYNTHETIC'}; }
function Harness() {
  const [crop,setCrop]=useState(makeCrop('A'));
  const [inspection,setInspection]=useState(null);
  const [enabled,setEnabled]=useState(true);
  const [panelVersion,setPanelVersion]=useState(0);
  const version=useRef(0);
  const start=()=>{version.current++;setInspection(null);return version.current;};
  window.step7.select=suffix=>{start();setCrop(makeCrop(suffix));};
  window.step7.setEnabled=setEnabled;
  window.step7.remount=()=>setPanelVersion(value=>value+1);
  window.step7.fail=index=>jobs[index].resolve(Response.json({detail:{error_code:'MOCK_FAILURE'}},{status:503}));
  window.step7.reply=(index,suffix,verdict='OK')=>{
    const current=makeCrop(suffix); const job=jobs[index];
    const groupId=job.body.group_id||'RIG-SYNTHETIC-'+suffix;
    const group=groups[groupId]||{group_id:groupId,product_id:job.body.product_id,version:0,status:'RETRY_ALLOWED',attempt_count:0,remaining_attempts:3,max_attempts:3,current_inspection_id:null,attempts:[],failed_attempts:[],manual_reviews:[]};
    const result={inspection_id:'INSP-SYNTHETIC-'+suffix,image_id:'IMG-GRAB-INSP-SYNTHETIC-'+suffix,final_result:verdict,result:verdict==='REINSPECT'?'NG':verdict,anomaly_score:verdict==='REINSPECT'?40:20,decision_threshold:34.1442,
      image_quality_status:verdict==='REINSPECT'?'WARNING_LOW_BRIGHTNESS':'NORMAL',final_reason_code:verdict==='REINSPECT'?'IMAGE_QUALITY_WARNING':'ALL_CHECKS_PASSED',
      metrics:{reinspection:{group_id:groupId},input_source:'LIVEVIEW_GRAB',input_provenance:{capture_id:current.captureId,video_id:current.videoId,source_revision:current.sourceRevision,frame_index:current.frameIndex,roi:current.roi,crop_width:160,crop_height:96}}};
    group.attempt_count++;group.remaining_attempts=3-group.attempt_count;group.version++;group.current_inspection_id=result.inspection_id;
    group.status=verdict==='REINSPECT'?(group.attempt_count===3?'MANUAL_REVIEW_REQUIRED':'RETRY_ALLOWED'):'COMPLETED';
    if(group.status!=='RETRY_ALLOWED')group.remaining_attempts=0;
    group.attempts.push({...result,attempt_number:group.attempt_count,input_provenance:result.metrics.input_provenance});
    groups[groupId]=group;records[result.inspection_id]=result;
    job.resolve(Response.json(result));
  };
  window.step7.ready=true;
  return <><GrabInspectionPanel key={panelVersion} crop={crop} enabled={enabled} onSelectionStart={start} onInspectionChange={(result,capturedVersion)=>{if(capturedVersion===version.current)setInspection(result);}}/>
    <ImageView capture={null} imageBlobUrl={null} cropData={crop} isLoading={false} error={null} currentInspection={inspection}/></>;
}
createRoot(document.getElementById('root')).render(<Harness/>);
`;

export async function runGrabChecks({ check, evaluate, waitFor, cdp }) {
  const clickInspect = () => evaluate("[...document.querySelectorAll('button')].find(button=>button.textContent.trim()==='Grab 이미지 검사').click()");
  await check('Grab UI shows Capture/ROI and experimental provenance, never auto-inspects', async () => {
    assert.ok(await evaluate("document.body.textContent.includes('CAP-SYNTHETIC-A') && document.body.textContent.includes('실험적')"));
    assert.equal(await evaluate('window.step7.jobs.length'), 0);
  });
  await check('double click issues only one Mock inspection POST with server ROI contract', async () => {
    await evaluate("const button=[...document.querySelectorAll('button')].find(button=>button.textContent.trim()==='Grab 이미지 검사'); button.click(); button.click();");
    await waitFor('window.step7.jobs.length===1');
    assert.equal(await evaluate('window.step7.jobs.length'), 1);
    assert.deepEqual(await evaluate('window.step7.jobs[0].body.roi'), { x:17,y:21,width:160,height:96 });
    assert.equal(await evaluate("'path' in window.step7.jobs[0].body"), false);
  });
  await check('changing Capture rejects the previous pending result and heatmap', async () => {
    await evaluate("window.step7.select('B')");
    await evaluate("window.step7.reply(0,'A')");
    await waitFor("document.body.textContent.includes('RIG-SYNTHETIC-A')");
    assert.equal(await evaluate("window.step7.seenImages.some(url=>url.endsWith('/INSP-SYNTHETIC-A/input-image'))"), false);
    await evaluate("[...document.querySelectorAll('button')].find(button=>button.textContent==='새 제품 검사 시작').click()");
    await waitFor("[...document.querySelectorAll('button')].some(button=>button.textContent.trim()==='Grab 이미지 검사' && !button.disabled)");
    assert.equal(await evaluate("document.body.textContent.includes('INSP-SYNTHETIC-A')"), false);
  });
  await check('current Grab inspection loads the server Crop and the matching map', async () => {
    await clickInspect();
    await waitFor('window.step7.jobs.length===2');
    await evaluate("window.step7.reply(1,'B')");
    await waitFor("[...document.querySelectorAll('button')].some(button=>button.textContent==='Heatmap OFF' && !button.disabled)");
    assert.ok(await evaluate("document.body.textContent.includes('LIVEVIEW GRAB CROP')"));
    assert.ok(await evaluate("window.step7.seenImages.some(url=>url.endsWith('/INSP-SYNTHETIC-B/input-image'))"));
  });
  await check('Grab heatmap preserves original RGB/GV and shares non-square draw coordinates under zoom', async () => {
    await evaluate("[...document.querySelectorAll('button')].find(button=>button.textContent==='Heatmap OFF').click()");
    await waitFor("[...document.querySelectorAll('button')].some(button=>button.textContent==='Heatmap ON')");
    await evaluate("const canvas=document.querySelector('.precision-canvas'); const rect=canvas.getBoundingClientRect(); canvas.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,clientX:rect.left+rect.width/2,clientY:rect.top+rect.height/2}));");
    await waitFor("document.body.textContent.includes('RGB(20, 40, 60)')");
    assert.deepEqual(await evaluate('window.step7.drawCalls.map(call=>call.rectangle)'), [[220,252,160,96],[220,252,160,96]]);
    await evaluate("[...document.querySelectorAll('button')].find(button=>button.textContent.trim()==='200%').click()");
    await waitFor('window.step7.drawCalls.at(-1).rectangle[2]===320');
    const rectangles=await evaluate('window.step7.drawCalls.map(call=>call.rectangle)');
    assert.deepEqual(rectangles[0],rectangles[1]);
  });
  await check('Grab input and overlay remain aligned during actual browser pointer Pan', async () => {
    await evaluate("document.querySelector('.precision-canvas').scrollIntoView({block:'center'})");
    const rectangle = await evaluate("(()=>{const bounds=document.querySelector('.precision-canvas').getBoundingClientRect();return {x:bounds.left+bounds.width/2,y:bounds.top+bounds.height/2};})()");
    const before = await evaluate('window.step7.drawCalls.at(-1).rectangle');
    await cdp.send('Input.dispatchMouseEvent', {type:'mousePressed',x:rectangle.x,y:rectangle.y,button:'left',clickCount:1});
    await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
    await cdp.send('Input.dispatchMouseEvent', {type:'mouseMoved',x:rectangle.x+15,y:rectangle.y+10,button:'left',buttons:1});
    await waitFor(`window.step7.drawCalls.at(-1).rectangle[0]!==${before[0]}`);
    await cdp.send('Input.dispatchMouseEvent', {type:'mouseReleased',x:rectangle.x+15,y:rectangle.y+10,button:'left',clickCount:1});
    const rectangles = await evaluate('window.step7.drawCalls.map(call=>call.rectangle)');
    assert.deepEqual(rectangles[0],rectangles[1]);
  });
  await check('Capture source switch cannot retain an old result overlay and no request escaped Mock transport', async () => {
    await evaluate("window.step7.select('A')");
    await evaluate("[...document.querySelectorAll('button')].find(button=>button.textContent==='새 제품 검사 시작').click()");
    await waitFor("!document.body.textContent.includes('INSP-SYNTHETIC-B')");
    assert.deepEqual(await evaluate('window.step7.blocked'), []);
  });
  await check('non-manual or unapplied source disables Grab inspection without issuing a request', async () => {
    await evaluate('window.step7.setEnabled(false)');
    await waitFor("[...document.querySelectorAll('button')].some(button=>button.textContent.trim()==='Grab 이미지 검사' && button.disabled)");
    assert.equal(await evaluate('window.step7.jobs.length'), 2);
  });
  await check('workflow first REINSPECT shows 1/3 and the preserved brightness warning', async () => {
    await evaluate("window.step7.setEnabled(true);window.step7.select('C')");
    await clickInspect();
    await waitFor('window.step7.jobs.length===3');
    await evaluate("window.step7.reply(2,'C','REINSPECT')");
    await waitFor("document.body.textContent.includes('검사 1 / 3') && document.body.textContent.includes('WARNING_LOW_BRIGHTNESS')");
  });
  await check('retry requires a new Capture and explicit same-product confirmation', async () => {
    await evaluate("window.step7.select('D')");
    assert.ok(await evaluate("[...document.querySelectorAll('button')].find(button=>button.textContent.trim()==='Grab 이미지 검사').disabled"));
    await evaluate("document.querySelector('[aria-label=\"동일 제품 재검사 확인\"]').click()");
    await clickInspect();
    await waitFor('window.step7.jobs.length===4');
    assert.equal(await evaluate('window.step7.jobs[3].body.same_product_confirmed'), true);
    assert.equal(await evaluate('window.step7.jobs[3].body.parent_inspection_id'), 'INSP-SYNTHETIC-C');
    await evaluate("window.step7.reply(3,'D','REINSPECT')");
    await waitFor("document.body.textContent.includes('검사 2 / 3')");
  });
  await check('third REINSPECT transitions to manual review with HOLD as default', async () => {
    await evaluate("window.step7.select('E')");
    await evaluate("document.querySelector('[aria-label=\"동일 제품 재검사 확인\"]').click()");
    await clickInspect();
    await waitFor('window.step7.jobs.length===5');
    await evaluate("window.step7.reply(4,'E','REINSPECT')");
    await waitFor("document.body.textContent.includes('MANUAL_REVIEW_REQUIRED')");
    assert.equal(await evaluate("document.querySelector('[aria-label=\"수동 결과\"]').value"), 'HOLD');
    assert.ok(await evaluate("[...document.querySelectorAll('button')].find(button=>button.textContent==='수동 확인 저장').disabled"));
  });
  await check('component reload restores server count without a new inspection', async () => {
    await evaluate('window.step7.remount()');
    await waitFor("document.body.textContent.includes('검사 3 / 3')");
    assert.equal(await evaluate('window.step7.jobs.length'), 5);
    assert.ok(await evaluate("document.querySelector('[aria-label=\"수동 결과\"]').value==='HOLD'"));
  });
  await check('HOLD saves only a development review and preserves all engine REINSPECT verdicts', async () => {
    await evaluate(`const input=document.querySelector('[aria-label="작업자 표시명"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'MOCK_OPERATOR');input.dispatchEvent(new Event('input',{bubbles:true}));
      const reason=document.querySelector('[aria-label="수동 판단 사유"]');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(reason,'MOCK TEST: pending visual review');reason.dispatchEvent(new Event('input',{bubbles:true}));`);
    await waitFor("![...document.querySelectorAll('button')].find(button=>button.textContent==='수동 확인 저장').disabled");
    await evaluate("[...document.querySelectorAll('button')].find(button=>button.textContent==='수동 확인 저장').click()");
    await waitFor('window.step7.reviews.length===1');
    assert.equal(await evaluate('window.step7.reviews[0].result'), 'HOLD');
    assert.ok(await evaluate("window.step7.groups['RIG-SYNTHETIC-C'].attempts.every(attempt=>attempt.final_result==='REINSPECT')"));
    assert.equal(await evaluate('window.step7.jobs.length'), 5);
  });
  await check('explicit MANUAL_NG is separate from original engine verdict and prevents more attempts', async () => {
    await evaluate("const select=document.querySelector('[aria-label=\"수동 결과\"]');select.value='MANUAL_NG';select.dispatchEvent(new Event('change',{bubbles:true}));");
    await evaluate("[...document.querySelectorAll('button')].find(button=>button.textContent==='수동 확인 저장').click()");
    await waitFor("document.body.textContent.includes('MANUAL_REVIEWED')");
    assert.equal(await evaluate('window.step7.reviews.length'), 2);
    assert.deepEqual(await evaluate("window.step7.groups['RIG-SYNTHETIC-C'].manual_reviews.map(review=>review.result)"), ['HOLD','MANUAL_NG']);
    assert.ok(await evaluate("window.step7.groups['RIG-SYNTHETIC-C'].attempts.every(attempt=>attempt.final_result==='REINSPECT')"));
  });
  await check('failed inspection is not auto-retried or presented as a successful count', async () => {
    await evaluate("[...document.querySelectorAll('button')].find(button=>button.textContent==='새 제품 검사 시작').click();window.step7.select('F')");
    await clickInspect();
    await waitFor('window.step7.jobs.length===6');
    await evaluate('window.step7.fail(5)');
    await waitFor("document.body.textContent.includes('MOCK_FAILURE')");
    assert.equal(await evaluate('window.step7.jobs.length'), 6);
    assert.ok(await evaluate("[...document.querySelectorAll('button')].find(button=>button.textContent==='Grab 이미지 검사').disabled"));
    assert.deepEqual(await evaluate('window.step7.blocked'), []);
  });
}
