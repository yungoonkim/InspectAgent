import assert from 'node:assert/strict';

export const agentHarnessSource = `
import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {AgentPanel} from '/src/components/AgentPanel.tsx';
import '/src/index.css';
const jobs = [];
window.fetch = (input, options = {}) => {
  const url = new URL(typeof input === 'string' ? input : input.url, location.href);
  const method = options.method || 'GET';
  const match = method === 'GET' ? url.pathname.match(/^\\/api\\/inspections\\/([^/]+)\\/agent-report$/)
    : method === 'POST' ? url.pathname.match(/^\\/api\\/analyze\\/([^/]+)$/) : null;
  if (url.origin !== location.origin || !match) throw new Error('Only synthetic Agent transport allowed');
  return new Promise(resolve => jobs.push({method, id:match[1], resolve, done:false}));
};
window.step5 = {
  jobs, ready:false,
  reply(method, id, body, status=200) {
    const job=jobs.find(entry=>!entry.done && entry.method===method && entry.id===id);
    if(!job) throw new Error('No pending synthetic Agent request: '+method+' '+id);
    job.done=true;
    job.resolve(new Response(JSON.stringify(body), {status, headers:{'Content-Type':'application/json'}}));
  },
  report(id, provenance='RECORDED_TEST_FIXTURE') {
    return {inspection_id:id, analysis_status:'COMPLETED', provenance, overall_summary:'SYNTHETIC REPORT '+id,
      observed_facts:[], possible_causes:[], recommended_checks:[], limitations:['SYNTHETIC_ONLY'], tools_used:[]};
  },
  text:()=>document.body.textContent,
};
function Harness() {
  const [identifier,setIdentifier]=useState('INSP-001396');
  window.step5.select=setIdentifier;
  window.step5.ready=true;
  return <AgentPanel inspectionId={identifier}/>;
}
createRoot(document.getElementById('root')).render(<Harness/>);
`;

export async function runAgentChecks({check, evaluate, waitFor}) {
  const click = async text => evaluate(`[...document.querySelectorAll('button')].find(button=>button.textContent.trim()===${JSON.stringify(text)}).click()`);
  const pending = async (method, identifier) => waitFor(`window.step5.jobs.some(job=>!job.done && job.method==='${method}' && job.id==='${identifier}')`);
  const stored = async (identifier, provenance = 'RECORDED_TEST_FIXTURE') => {
    await pending('GET', identifier);
    await evaluate(`window.step5.reply('GET','${identifier}',window.step5.report('${identifier}','${provenance}'))`);
    await waitFor(`window.step5.text().includes('SYNTHETIC REPORT ${identifier}')`);
  };
  const start = async () => {
    await click('Gemini AI 진단 실행');
    await waitFor("document.querySelector('[role=dialog]')");
    await click('확인 후 AI 진단 실행');
  };
  await check('stored fixture GET never invokes a live analysis', async () => {
    await stored('INSP-001396');
    assert.ok(await evaluate("window.step5.text().includes('RECORDED TEST FIXTURE')"));
    assert.equal(await evaluate("window.step5.jobs.filter(job=>job.method==='POST').length"), 0);
  });
  await check('live failure clears the previous success and explicitly reports LIVE ANALYSIS FAILED', async () => {
    await start();
    await pending('POST', 'INSP-001396');
    await evaluate("window.step5.reply('POST','INSP-001396',{detail:{error_code:'GEMINI_REQUEST_FAILED'}},502)");
    await waitFor("window.step5.text().includes('LIVE ANALYSIS FAILED')");
    assert.equal(await evaluate("window.step5.text().includes('SYNTHETIC REPORT')"), false);
  });
  await check('one confirmed fake POST yields live completion without duplicate clicks', async () => {
    const before = await evaluate("window.step5.jobs.filter(job=>job.method==='POST').length");
    await click('Gemini AI 진단 실행');
    await waitFor("document.querySelector('[role=dialog]')");
    await evaluate("(() => {const button=[...document.querySelectorAll('button')].find(entry=>entry.textContent.trim()==='확인 후 AI 진단 실행');button.click();button.click();})()");
    await pending('POST', 'INSP-001396');
    assert.equal(await evaluate("window.step5.jobs.filter(job=>job.method==='POST').length"), before+1);
    await evaluate("window.step5.reply('POST','INSP-001396',window.step5.report('INSP-001396','LIVE_AGENT_ANALYSIS'))");
    await waitFor("window.step5.text().includes('LIVE ANALYSIS COMPLETED')");
  });
  await check('GET of a cached live report is not a new live verification', async () => {
    await click('기존 보고서 조회');
    await stored('INSP-001396', 'LIVE_AGENT_ANALYSIS');
    await waitFor("window.step5.text().includes('STORED LIVE REPORT')");
    assert.ok(await evaluate("window.step5.text().includes('LIVE NOT YET VERIFIED')"));
  });
  await check('late stored report cannot replace a newly selected inspection', async () => {
    await evaluate("window.step5.select('INSP-001390')");
    await pending('GET','INSP-001390');
    await evaluate("window.step5.select('INSP-001398')");
    await stored('INSP-001398');
    await evaluate("window.step5.reply('GET','INSP-001390',window.step5.report('INSP-001390'))");
    assert.equal(await evaluate("window.step5.text().includes('SYNTHETIC REPORT INSP-001390')"), false);
  });
  await check('late live success cannot change another inspection or its verification status', async () => {
    await start();
    await pending('POST', 'INSP-001398');
    await evaluate("window.step5.select('INSP-001391')");
    await stored('INSP-001391');
    await evaluate("window.step5.reply('POST','INSP-001398',window.step5.report('INSP-001398','LIVE_AGENT_ANALYSIS'))");
    assert.ok(await evaluate("window.step5.text().includes('SYNTHETIC REPORT INSP-001391')"));
    assert.ok(await evaluate("window.step5.text().includes('LIVE NOT YET VERIFIED')"));
  });
  await check('non-key 503 is not misdiagnosed as missing credentials', async () => {
    await start();
    await pending('POST','INSP-001391');
    await evaluate("window.step5.reply('POST','INSP-001391',{detail:{error_code:'STORAGE_ERROR'}},503)");
    await waitFor("window.step5.text().includes('STORAGE_ERROR')");
    assert.equal(await evaluate("window.step5.text().includes('API Key가 설정되지')"), false);
  });
  await check('HTTP 200 with FAILED payload never receives a live success badge', async () => {
    await start();
    await pending('POST','INSP-001391');
    await evaluate("window.step5.reply('POST','INSP-001391',{inspection_id:'INSP-001391',analysis_status:'FAILED'})");
    await waitFor("window.step5.text().includes('LIVE ANALYSIS FAILED')");
    assert.equal(await evaluate("window.step5.text().includes('LIVE ANALYSIS COMPLETED')"), false);
  });
}
