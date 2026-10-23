import assert from 'node:assert/strict';
import test from 'node:test';
import { canUseCapture, grabInspectionDisabled, inspectionProgress } from '../src/utils/reinspectionState.ts';
import { canPrepareNewProduct, clearWorkflowHints, GROUP_HINT_KEY, PENDING_CAPTURE_HINT_KEY,
  prepareNewProductCapture, recoveryProblem, restoreCurrentCaptureWorkflow } from '../src/utils/reinspectionRecovery.ts';

const crop = { captureId:'CAP-NEW', videoId:'VID-000001', frameIndex:200, sourceRevision:'a'.repeat(64),
  roi:{x:10,y:20,width:278,height:278}, width:278,height:278 };
const metadata = {capture_id:crop.captureId,video_id:crop.videoId,frame_index:crop.frameIndex,
  source_revision:crop.sourceRevision,width:1920,height:480,status:'CAPTURED'};
const group = {group_id:'RIG-EXISTING',product_id:'ABCD1541',version:1,status:'RETRY_ALLOWED',attempt_count:1,
  remaining_attempts:2,attempts:[{input_provenance:{capture_id:'CAP-PREVIOUS'}}],failed_attempts:[],manual_reviews:[]};
const missing = {status:404,data:{detail:{error_code:'REINSPECTION_GROUP_NOT_FOUND'}}};
const button = {enabled:true,hasCrop:true,busy:false,restoring:false,blocked:false,captureAllowed:true,completed:false,productId:'ABCD1541'};

test('current Capture recovery never queries a stale pending Capture or silently abandons history', async () => {
  const calls = [];
  const recovered = await restoreCurrentCaptureWorkflow(crop,null,
    {groupId:'RIG-OLD',pendingCaptureId:'CAP-OLD'}, {
      capture:async identifier=>{calls.push(['CAPTURE',identifier]);return metadata;},
      group:async identifier=>{calls.push(['CAPTURE_GROUP',identifier]);throw missing;},
      savedGroup:async identifier=>{calls.push(['GROUP',identifier]);throw missing;},
    });
  assert.deepEqual(calls,[['CAPTURE',crop.captureId],['CAPTURE_GROUP',crop.captureId],['GROUP','RIG-OLD']]);
  assert.deepEqual(recovered,{group:null,needsNewProductConfirmation:true});
});

test('fresh verified Capture without old hints permits first inspection after a successful lookup', async () => {
  const recovered=await restoreCurrentCaptureWorkflow(crop,null,{groupId:null,pendingCaptureId:null},{
    capture:async()=>metadata,group:async()=>{throw missing;},savedGroup:async()=>assert.fail('No old group lookup'),
  });
  assert.equal(recovered.needsNewProductConfirmation,false);
  assert.equal(grabInspectionDisabled({...button,captureAllowed:canUseCapture(recovered.group,crop.captureId,false)}),false);
});

test('saved active or terminal groups remain authoritative even when the current Capture is unused', async () => {
  for(const status of ['RETRY_ALLOWED','MANUAL_REVIEW_REQUIRED','MANUAL_REVIEWED','COMPLETED']){
    const saved={...group,status,attempt_count:status==='RETRY_ALLOWED'?1:3,remaining_attempts:status==='RETRY_ALLOWED'?2:0};
    const before=structuredClone(saved);
    const recovered=await restoreCurrentCaptureWorkflow(crop,saved,{groupId:saved.group_id,pendingCaptureId:'CAP-OLD'},{
      capture:async()=>metadata,group:async()=>{throw missing;},savedGroup:async()=>saved,
    });
    assert.equal(recovered.group,saved);
    assert.equal(canUseCapture(recovered.group,crop.captureId,false),false);
    assert.equal(canUseCapture(recovered.group,crop.captureId,true),status==='RETRY_ALLOWED');
    assert.deepEqual(saved,before);
  }
});

test('a claimed Capture restores the server group and cannot be inspected twice', async () => {
  const claimed={...group,attempts:[{input_provenance:{capture_id:crop.captureId}}]};
  const recovered=await restoreCurrentCaptureWorkflow(crop,null,{groupId:'RIG-OLD',pendingCaptureId:'CAP-OLD'},{
    capture:async()=>metadata,group:async()=>claimed,savedGroup:async()=>assert.fail('Current claim takes precedence'),
  });
  assert.equal(recovered.group,claimed);
  assert.equal(canUseCapture(recovered.group,crop.captureId,true),false);
});

test('current-session failures and unresolved pending results never become a new inspection', async () => {
  for(const status of [401,403,404,500]){
    await assert.rejects(restoreCurrentCaptureWorkflow(crop,null,{groupId:null,pendingCaptureId:'CAP-OLD'},{
      capture:async()=>{throw {status,data:{detail:{error_code:'CAPTURE_NOT_FOUND'}}};},
      group:async()=>assert.fail('No group lookup before ownership verification'),savedGroup:async()=>assert.fail('No fallback'),
    }));
  }
  await assert.rejects(restoreCurrentCaptureWorkflow(crop,null,{groupId:null,pendingCaptureId:crop.captureId},{
    capture:async()=>metadata,group:async()=>{throw missing;},savedGroup:async()=>assert.fail('No old group'),
  }),/PENDING_CAPTURE_RESULT_UNRESOLVED/);
});

test('a known group is not abandoned after 404 or a server error', async () => {
  for(const error of [missing,{status:500}]){
    await assert.rejects(restoreCurrentCaptureWorkflow(crop,group,{groupId:group.group_id,pendingCaptureId:null},{
      capture:async()=>metadata,group:async()=>{throw missing;},savedGroup:async()=>{throw error;},
    }),value=>value===error);
  }
});

test('confirmed stale group 404 permits GET-only verification of a new Capture then first inspection', async () => {
  assert.equal(canPrepareNewProduct(true,recoveryProblem(missing)),true);
  const calls = [];
  const restored = await prepareNewProductCapture(crop,true,{
    capture:async identifier => {calls.push(['GET_CAPTURE',identifier]);return metadata;},
    group:async identifier => {calls.push(['GET_CAPTURE_GROUP',identifier]);throw missing;},
  });
  assert.equal(restored,null);
  assert.deepEqual(calls,[['GET_CAPTURE',crop.captureId],['GET_CAPTURE_GROUP',crop.captureId]]);
  assert.equal(canUseCapture(restored,crop.captureId,false),true);
  assert.equal(grabInspectionDisabled({...button,captureAllowed:canUseCapture(restored,crop.captureId,false)}),false);
});

test('fresh product transition requires explicit confirmation before any server query', async () => {
  const forbidden = async () => {assert.fail('No query before confirmation');};
  await assert.rejects(prepareNewProductCapture(crop,false,{capture:forbidden,group:forbidden}),/NEW_PRODUCT_CONFIRMATION_REQUIRED/);
});

test('valid existing Capture group is restored without resetting count or manual history', async () => {
  const existing = {...group,attempts:[{input_provenance:{capture_id:crop.captureId}}],manual_reviews:[{result:'HOLD'}]};
  const before = structuredClone(existing);
  const restored = await prepareNewProductCapture(crop,true,{capture:async()=>metadata,group:async()=>existing});
  assert.equal(restored,existing);
  assert.deepEqual(restored,before);
  assert.equal(canUseCapture(restored,crop.captureId,true),false);
});

for (const status of [401,403,409,500,503]) {
  test(`HTTP ${status} preserves inspection blocking until the current Capture is separately verified`, async () => {
    const error = {status,data:{detail:{error_code:status===500?'SERVER_ERROR':'REINSPECTION_GROUP_NOT_FOUND'}}};
    assert.notEqual(recoveryProblem(error).kind,'GROUP_NOT_FOUND');
    assert.equal(canPrepareNewProduct(true,recoveryProblem(error)),status===401||status===403);
    await assert.rejects(prepareNewProductCapture(crop,true,{capture:async()=>metadata,group:async()=>{throw error;}}),value=>value===error);
    assert.equal(grabInspectionDisabled({...button,blocked:true}),true);
  });
}

test('expired/missing Capture session and unstructured 404 fail closed before group lookup', async () => {
  for (const error of [{status:404,data:{detail:{error_code:'CAPTURE_NOT_FOUND'}}},{status:404},new Error('offline')]) {
    assert.notEqual(recoveryProblem(error).kind,'GROUP_NOT_FOUND');
    assert.equal(canPrepareNewProduct(true,recoveryProblem(error)),recoveryProblem(error).kind==='CAPTURE_OR_SESSION');
    await assert.rejects(prepareNewProductCapture(crop,true,{capture:async()=>{throw error;},group:async()=>assert.fail('No group query')}),value=>value===error);
  }
});

test('retrying lookup after a server failure can restore the actual server group and remove the button gate', async () => {
  const claimed = {...group,attempts:[{input_provenance:{capture_id:crop.captureId}}]};
  let failed = true;
  const lookup = {capture:async()=>metadata,group:async()=>{if(failed)throw {status:500};return claimed;}};
  await assert.rejects(prepareNewProductCapture(crop,true,lookup));
  failed=false;
  assert.equal(await prepareNewProductCapture(crop,true,lookup),claimed);
  assert.equal(canUseCapture(claimed,'CAP-NEXT',true),true);
  assert.equal(grabInspectionDisabled({...button,captureAllowed:canUseCapture(claimed,'CAP-NEXT',true)}),false);
});

test('ownership validation precedes no-group handling and rejects a mismatched Capture or ROI', async () => {
  for (const changes of [{capture_id:'CAP-OTHER'},{video_id:'OTHER'},{source_revision:'b'.repeat(64)},
    {frame_index:201},{width:100},{height:200},{status:'EXPIRED'}]) {
    await assert.rejects(prepareNewProductCapture(crop,true,{capture:async()=>({...metadata,...changes}),group:async()=>assert.fail('No group query')}),/CAPTURE_SOURCE_MISMATCH/);
  }
  await assert.rejects(prepareNewProductCapture(crop,true,{capture:async()=>metadata,
    group:async()=>group}),/REINSPECTION_GROUP_CAPTURE_MISMATCH/);
});

test('only the two non-authoritative workflow hints are cleared; server data are not a lookup dependency', () => {
  const entries = new Map([[GROUP_HINT_KEY,'old'],[PENDING_CAPTURE_HINT_KEY,'old-capture'],['unrelated','keep']]);
  clearWorkflowHints({removeItem:key=>entries.delete(key)});
  assert.deepEqual([...entries],[['unrelated','keep']]);
});

test('blocking and restoring states never say first inspection ready', () => {
  const state = {group:null,restoring:false,blocked:false,hasCrop:true,ready:true};
  assert.equal(inspectionProgress(state),'1차 PatchCore 검사 준비 · 신규 정책은 서버에서 확정');
  assert.match(inspectionProgress({...state,blocked:true}),/검사 차단/);
  assert.doesNotMatch(inspectionProgress({...state,restoring:true}),/최초 검사.*준비/);
});

test('existing retry still requires new Capture and same physical product confirmation', () => {
  assert.equal(canUseCapture(group,crop.captureId,false),false);
  assert.equal(canUseCapture(group,'CAP-PREVIOUS',true),false);
  assert.equal(canUseCapture(group,crop.captureId,true),true);
  for (const status of ['COMPLETED','MANUAL_REVIEW_REQUIRED','MANUAL_REVIEWED','RECOVERY_REQUIRED']) {
    assert.equal(canUseCapture({...group,status,attempt_count:3,remaining_attempts:0},crop.captureId,true),false);
  }
});

test('old session/pending Capture hint does not prevent explicit verified new-product transition', async () => {
  const problem = recoveryProblem({status:404,data:{detail:{error_code:'CAPTURE_NOT_FOUND'}}});
  assert.equal(canPrepareNewProduct(true,problem),true);
  assert.equal(grabInspectionDisabled({...button,blocked:true}),true);
  const restored = await prepareNewProductCapture(crop,true,{
    capture:async()=>metadata,group:async()=>{throw missing;},
  });
  assert.equal(restored,null);
  assert.equal(grabInspectionDisabled({...button,blocked:false,captureAllowed:canUseCapture(restored,crop.captureId,false)}),false);
});

test('new product still fails closed if the currently selected Capture session is invalid', async () => {
  for (const status of [401,403,404,500]) {
    const error = {status,data:{detail:{error_code:'CAPTURE_NOT_FOUND'}}};
    await assert.rejects(prepareNewProductCapture(crop,true,{
      capture:async()=>{throw error;},group:async()=>assert.fail('No group query before valid current Capture'),
    }),value=>value===error);
  }
});
