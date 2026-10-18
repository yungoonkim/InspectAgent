import assert from 'node:assert/strict';
import test from 'node:test';
import { sourceKey, sameSource, roiFits } from '../src/utils/roiLifetime.ts';
import { visionInputKey, matchesVisionInput } from '../src/utils/visionReviewState.ts';

const video = { video_id: 'VID-000001', source_revision: 'a'.repeat(64), width: 1920, height: 480 };
const roi = { x: 800, y: 80, width: 320, height: 320 };
test('ROI lifetime ignores playback, frame index, and Capture identifier', () => {
  for (const event of ['PLAY','PAUSE','SEEK','STEP','GRAB','REINSPECT']) {
    assert.equal(sourceKey({ ...video, event, frame_index: 99, capture_id: 'CAP-NEW' }), sourceKey(video));
  }
});
test('video/revision/both source dimensions independently invalidate ROI binding', () => {
  for (const changes of [{ video_id:'OTHER' },{source_revision:'b'.repeat(64)},{width:900},{height:900}]) {
    assert.equal(sameSource(video,{...video,...changes}),false);
  }
  assert.equal(sameSource(null,video),false);
});
test('ROI validation uses strict original half-open pixel bounds', () => {
  assert.equal(roiFits(roi,video),true);
  assert.equal(roiFits({x:0,y:0,width:1920,height:480},video),true);
  for (const changes of [{x:-1},{x:0.5},{width:0},{width:2000},{height:401}]) {
    assert.equal(roiFits({...roi,...changes},video),false);
  }
});
const inspection = { inspection_id:'INSP-MOCK-A', final_result:'REINSPECT',metrics:{input_source:'LIVEVIEW_GRAB',
  reinspection:{group_id:'RIG-MOCK'},input_provenance:{capture_id:'CAP-MOCK',crop_sha256:'a'.repeat(64)}} };
const review = {inspection_id:inspection.inspection_id,capture_id:'CAP-MOCK',image_sha256:'a'.repeat(64),reinspection_group_id:'RIG-MOCK',analysis_mode:'FAKE_TEST'};
test('only eligible Grab REINSPECT has a Vision source key', () => {
  assert.ok(visionInputKey(inspection));
  assert.equal(visionInputKey(null),'');
  assert.equal(visionInputKey({...inspection,final_result:'OK'}),'');
  assert.equal(visionInputKey({...inspection,metrics:{}}),'');
});
test('inspection, Capture, hash and group must all match for a Vision opinion', () => {
  assert.equal(matchesVisionInput(review,inspection),true);
  for (const change of [{inspection_id:'OTHER'},{capture_id:'OTHER'},{image_sha256:'b'.repeat(64)},
    {reinspection_group_id:'OTHER'},{analysis_mode:'CLAIMED_SUCCESS'}]) {
    assert.equal(matchesVisionInput({...review,...change},inspection),false);
  }
});
