import assert from 'node:assert/strict';
import test from 'node:test';
import { detectBottleEdges, drawBottleEdges } from '../src/utils/bottleEdges.ts';
import { calculateOrigin } from '../src/utils/imageTransform.ts';

function bottle(width=144,height=128,centerX=72,centerY=64,radius=42,exposure=1,notch=false){
  const data=new Uint8ClampedArray(width*height*4);
  for(let row=0;row<height;row++) for(let column=0;column<width;column++){
    const distance=Math.hypot(column-centerX,row-centerY);
    let value=235;
    if(distance<=radius) value=distance<radius*0.6?16:distance<radius*0.86?95:40;
    if(notch&&column>centerX&&Math.abs(row-centerY)<(column-centerX)*0.8) value=235;
    const index=(row*width+column)*4;
    data[index]=data[index+1]=data[index+2]=Math.round(value*exposure);data[index+3]=255;
  }
  return {width,height,data};
}

test('pixel-derived body and supported inner rim are found at different positions and sizes',()=>{
  for(const image of [bottle(),bottle(180,150,105,68,49),bottle(100,110,43,59,29)]){
    const before=image.data.slice();
    const result=detectBottleEdges(image);
    assert.equal(result.status,'SUCCESS');
    assert.ok(result.outer.length>100&&result.rim.length>54);
    assert.ok(result.statistics.bodyMean<result.statistics.backgroundMean);
    assert.ok(result.statistics.rimSupport>=0.8);
    assert.deepEqual(image.data,before);
  }
});

test('translating a bottle translates its measured contour rather than fitting a fixed circle',()=>{
  const first=detectBottleEdges(bottle());
  const second=detectBottleEdges(bottle(144,128,79,69));
  const shifted=new Set(first.outer.map(segment=>JSON.stringify(segment.map(point=>({x:point.x+7,y:point.y+5})))));
  assert.equal(second.outer.filter(segment=>shifted.has(JSON.stringify(segment))).length,second.outer.length);
});

test('clipped and low-contrast inputs are uncertain, not product decisions or invented complete circles',()=>{
  for(const image of [bottle(100,110,6,55,42),bottle(144,128,72,64,42,0.08),bottle(144,128,72,64,42,1,true)]){
    const result=detectBottleEdges(image);
    assert.notEqual(result.status,'SUCCESS');
    assert.ok(result.reasons.length>0);
    assert.ok(!Object.hasOwn(result,'final_result'));
    for(const segment of result.outer) assert.ok(!segment.every(point=>point.x===0));
  }
});

test('uniform, blank and invalid images fail without fallback outline or rim',()=>{
  for(const image of [{width:64,height:64,data:new Uint8ClampedArray(64*64*4)},
    {width:2,height:2,data:new Uint8ClampedArray(16)},{width:64,height:64,data:new Uint8ClampedArray(2)}]){
    const result=detectBottleEdges(image);
    assert.equal(result.status,'FAILED');
    assert.deepEqual(result.outer,[]);assert.deepEqual(result.rim,[]);
  }
});

test('overlay shares original pixel coordinates with image zoom/pan and never writes image or Heatmap data',()=>{
  const result=detectBottleEdges(bottle());
  for(const zoom of [1,4,40]){
    const origin=calculateOrigin(result.width,result.height,zoom,{x:19,y:-23});
    const moves=[];const colors=[];
    const context={save(){},restore(){},beginPath(){},rect(){},clip(){},stroke(){},
      moveTo:(...point)=>moves.push(point),lineTo(){},set strokeStyle(value){colors.push(value);}};
    drawBottleEdges(context,result,origin.x,origin.y,zoom);
    assert.deepEqual(moves[0],[origin.x+result.outer[0][0].x*zoom,origin.y+result.outer[0][0].y*zoom]);
    assert.deepEqual(colors,['#22c55e','#facc15']);
  }
});

test('outer and inner candidate have independent closure and geometry, not confidence probabilities', () => {
  const result = detectBottleEdges(bottle());
  assert.equal(result.assessment.outer.status, 'SUCCESS');
  assert.equal(result.assessment.outer.closed, true);
  assert.equal(result.assessment.outer.components, 1);
  assert.ok(result.assessment.outer.circularity > 0 && result.assessment.outer.circularity < 1);
  assert.ok(Math.abs(result.assessment.outer.referenceRadius - 42) < 1);
  assert.ok(result.assessment.outer.radialRms < 1);
  assert.equal(result.assessment.rim.status, 'SUCCESS');
  assert.equal(result.assessment.rim.coverage, 1);
  assert.equal(result.assessment.rim.largestGapDegrees, 0);
  assert.ok(!Object.hasOwn(result, 'confidence'));
});

test('clipping, missing rim arcs, reflection-like notches and low contrast do not fabricate region statistics', () => {
  const images = [bottle(100,110,6,55,42), bottle(144,128,72,64,42,0.08)];
  for (const image of images) {
    const result = detectBottleEdges(image);
    assert.notEqual(result.assessment.outer.status, 'SUCCESS');
    assert.equal(result.regions.body, null);
    assert.equal(result.regions.background, null);
    assert.equal(result.regions.rim, null);
    assert.ok(result.regions.roi);
  }
  const image = bottle();
  for (let row = 0; row < image.height; row++) for (let column = 0; column < image.width; column++) {
    if (column > 72 && Math.abs(row - 64) < (column - 72) * 0.5 && Math.hypot(column-72,row-64) < 36) {
      const offset = (row * image.width + column) * 4;
      image.data[offset] = image.data[offset+1] = image.data[offset+2] = 16;
    }
  }
  const result = detectBottleEdges(image);
  assert.equal(result.assessment.outer.status, 'SUCCESS');
  assert.equal(result.assessment.rim.status, 'UNCERTAIN');
  assert.ok(result.assessment.rim.largestGapDegrees > 0);
  assert.ok(result.assessment.rim.coverage < 1);
  assert.equal(result.regions.rim, null);
  assert.equal(result.assessment.rim.circularity, null);
  assert.ok(result.regions.body && result.regions.background);
});

test('area statistics use original pixels, correct medians and population deviation with exhaustive body/background masks', () => {
  const result = detectBottleEdges(bottle());
  const { roi, body, rim, background } = result.regions;
  assert.equal(body.pixels + background.pixels, roi.pixels);
  assert.equal(body.areaRatio + background.areaRatio, 1);
  assert.ok(Math.abs((body.mean * body.pixels + background.mean * background.pixels) / roi.pixels - roi.mean) < 1e-10);
  assert.equal(background.mean, 235);
  assert.equal(background.median, 235);
  assert.equal(background.std, 0);
  assert.equal(rim.mean, 16);
  assert.equal(rim.median, 16);
  assert.equal(rim.std, 0);
  assert.ok(rim.pixels < body.pixels);
  assert.equal(roi.mean, result.statistics.roiMean);
  const data = new Uint8ClampedArray(24 * 24 * 4);
  for (let index = 0; index < 576; index++) {
    const value = index < 288 ? 20 : 21;
    data[index*4] = data[index*4+1] = data[index*4+2] = value;
    data[index*4+3] = 255;
  }
  const uniform = detectBottleEdges({width:24,height:24,data});
  assert.equal(uniform.status, 'FAILED');
  assert.deepEqual(uniform.regions.roi, { mean:20.5, median:20.5, std:0.5, pixels:576, areaRatio:1 });
  assert.equal(uniform.regions.body, null);
});

test('colored ROI measurements match OpenCV integer grayscale rather than the segmentation rounding approximation', () => {
  const data = new Uint8ClampedArray(24 * 24 * 4);
  for (let index = 0; index < 576; index++) {
    const color = index % 2 ? [12, 121, 93] : [251, 72, 3];
    data.set([...color, 255], index * 4);
  }
  const expected = [12*9798+121*19235+93*3735, 251*9798+72*19235+3*3735]
    .map(sum => (sum + 16384) >> 15);
  const result = detectBottleEdges({width:24,height:24,data});
  assert.equal(result.regions.roi.mean, (expected[0]+expected[1])/2);
  assert.equal(result.regions.roi.median, (expected[0]+expected[1])/2);
});

test('geometric deviation increases for irregular observed shapes without inventing an acceptance threshold', () => {
  const circle = detectBottleEdges(bottle());
  const irregular = detectBottleEdges(bottle(144,128,72,64,42,1,true));
  assert.ok(irregular.assessment.outer.radialRms > circle.assessment.outer.radialRms);
  assert.ok(irregular.assessment.outer.circularity < circle.assessment.outer.circularity);
  assert.ok(!Object.hasOwn(irregular, 'final_result'));
});
