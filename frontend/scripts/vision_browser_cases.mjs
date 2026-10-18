import assert from 'node:assert/strict';

export const visionHarnessSource = `
import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import {VisionReviewPanel} from '/src/components/VisionReviewPanel.tsx';
import '/src/index.css';
const reads=[],posts=[],blocked=[];
const capabilities={enabled:false,live_enabled:false,analysis_mode:'DISABLED',reason:'VISION_LIVE_DISABLED_UNVERIFIED_MODEL_AND_TRANSPORT',model_requested:'gemini-4-argon'};
window.fetch=(input,options={})=>{
 const url=new URL(typeof input==='string'?input:input.url,location.href);
 if(url.origin!==location.origin)throw Error('External requests forbidden');
 if(url.pathname==='/api/capture-sessions')return Promise.resolve(Response.json({csrf_token:'MOCK',session_ttl_seconds:3600}));
 const match=url.pathname.match(/\\/inspections\\/(INSP-MOCK-[A-Z])\\/vision-review$/);
 if(match && (!options.method||options.method==='GET'))return new Promise(resolve=>reads.push({id:match[1],resolve}));
 if(match && options.method==='POST')return new Promise(resolve=>posts.push({id:match[1],body:JSON.parse(options.body),resolve}));
 blocked.push(url.pathname);throw Error('Non-Mock request forbidden');
};
function record(suffix){return {inspection_id:'INSP-MOCK-'+suffix,final_result:'REINSPECT',metrics:{input_source:'LIVEVIEW_GRAB',reinspection:{group_id:'RIG-MOCK'},input_provenance:{capture_id:'CAP-MOCK-'+suffix,crop_sha256:suffix.toLowerCase().repeat(64)}}};}
function result(suffix,classification='QUALITY_ISSUE'){const input=record(suffix);return {vision_review_id:'VREV-MOCK-'+suffix,inspection_id:input.inspection_id,capture_id:input.metrics.input_provenance.capture_id,image_sha256:input.metrics.input_provenance.crop_sha256,reinspection_group_id:'RIG-MOCK',model_requested:'gemini-4-argon',model_resolved:'MOCK_MODEL_ONLY',prompt_version:'MOCK',analysis_mode:'FAKE_TEST',classification,visible_observations:['MOCK visual observation '+suffix],limitations:['MOCK TEST not a product evaluation'],recommended_operator_action:'Human check only',failure_code:classification==='ANALYSIS_FAILED'?'VISION_TIMEOUT':null,created_at:'MOCK_TIME'};}
window.step9={ready:false,reads,posts,blocked,select:null,
 replyRead:(index,suffix,enabled=false,classification=null)=>reads[index].resolve(Response.json({available:!!classification,review:classification?result(suffix,classification):null,capabilities:{...capabilities,enabled,analysis_mode:enabled?'FAKE_TEST':'DISABLED',reason:enabled?'FAKE_TEST_ONLY':capabilities.reason}})),
 replyPost:(index,suffix,classification='QUALITY_ISSUE')=>posts[index].resolve(Response.json({available:true,review:result(suffix,classification),capabilities:{...capabilities,enabled:true,analysis_mode:'FAKE_TEST'}}))};
function Harness(){const [inspection,setInspection]=useState(record('A'));window.step9.select=suffix=>setInspection(record(suffix));window.step9.ready=true;return <VisionReviewPanel inspection={inspection}/>;}
createRoot(document.getElementById('root')).render(<Harness/>);
`;

export async function runVisionChecks({check,evaluate,waitFor}) {
  await check('production-disabled Vision never auto POSTs or claims model support',async()=>{
    await waitFor('window.step9.reads.length===1');
    await evaluate("window.step9.replyRead(0,'A')");
    await waitFor("document.body.textContent.includes('VISION_LIVE_DISABLED')");
    assert.ok(await evaluate("document.querySelector('button').disabled"));
    assert.equal(await evaluate('window.step9.posts.length'),0);
  });
  await check('late saved Vision response cannot contaminate a different inspection',async()=>{
    await evaluate("window.step9.select('B')");await waitFor('window.step9.reads.length===2');
    await evaluate("window.step9.select('C')");await waitFor('window.step9.reads.length===3');
    await evaluate("window.step9.replyRead(1,'B',true,'DEFECT_SUSPECTED');window.step9.replyRead(2,'C',true)");
    await waitFor("!document.querySelector('button').disabled");
    assert.equal(await evaluate("document.body.textContent.includes('MOCK visual observation B')"),false);
  });
  await check('explicit Fake second opinion double click produces one UUID-only request',async()=>{
    await evaluate("document.querySelector('button').click();document.querySelector('button').click()");
    await waitFor('window.step9.posts.length===1');
    assert.deepEqual(await evaluate('Object.keys(window.step9.posts[0].body)'),['request_id']);
    assert.match(await evaluate('window.step9.posts[0].body.request_id'),/^[a-f0-9]{32}$/);
  });
  await check('late Fake POST result is rejected after image switch',async()=>{
    await evaluate("window.step9.select('D')");await waitFor('window.step9.reads.length===4');
    await evaluate("window.step9.replyPost(0,'C');window.step9.replyRead(3,'D',true)");
    await waitFor("!document.querySelector('button').disabled");
    assert.equal(await evaluate("document.body.textContent.includes('MOCK visual observation C')"),false);
  });
  await check('matching Fake response is explicitly not LIVE and not a confirmed NG/OK',async()=>{
    await evaluate("document.querySelector('button').click()");await waitFor('window.step9.posts.length===2');
    await evaluate("window.step9.replyPost(1,'D','NO_VISIBLE_DEFECT')");
    await waitFor("document.body.textContent.includes('NO_VISIBLE_DEFECT')");
    assert.ok(await evaluate("document.body.textContent.includes('FAKE_TEST · 실제 분석 아님') && document.body.textContent.includes('NG/OK 확정 아님')"));
    assert.ok(await evaluate("document.querySelector('button').disabled"));
  });
  await check('saved failure restores as ANALYSIS_FAILED without paid reattempt',async()=>{
    await evaluate("window.step9.select('E')");await waitFor('window.step9.reads.length===5');
    await evaluate("window.step9.replyRead(4,'E',false,'ANALYSIS_FAILED')");
    await waitFor("document.body.textContent.includes('VISION_TIMEOUT')");
    assert.equal(await evaluate('window.step9.posts.length'),2);
    assert.deepEqual(await evaluate('window.step9.blocked'),[]);
  });
  await check('mismatched saved image hash and inspection are rejected',async()=>{
    await evaluate("window.step9.select('F')");await waitFor('window.step9.reads.length===6');
    await evaluate("window.step9.replyRead(5,'E',true,'DEFECT_SUSPECTED')");
    await waitFor("document.body.textContent.includes('VISION_REVIEW_SOURCE_MISMATCH')");
    assert.equal(await evaluate("document.querySelector('[data-testid=vision-review-result]')!==null"),false);
  });
}
