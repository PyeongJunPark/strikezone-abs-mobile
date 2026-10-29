const {test} = require('node:test');
const assert = require('node:assert/strict');
const {FixedZone} = require('../ui/fixed-zone.js');
const frame = (index=3) => ({frame_index:index,image_width:800,image_height:700,
  pose:{status:'ok',confidence:.8,top_y:300,bottom_y:500,keypoints:{}}});
test('rectangle remains fixed when later pose changes and is not shown before reference',()=>{
 const s=new FixedZone('v');s.lock(frame(),100,200,10,null,30);s.start();
 const later=frame(15);later.pose.top_y=1;
 assert.deepEqual(s.visible(later).bbox_xyxy,[100,300,200,500]);
 assert.equal(s.visible(frame(2)),null);assert.equal(s.visible(frame(31)),null);
 const copy=s.snapshot();copy.zone.bbox_xyxy[0]=999;
 assert.equal(s.snapshot().zone.bbox_xyxy[0],100);
});
test('missing pose rejects lock; manual correction is explicitly unvalidated',()=>{
 const s=new FixedZone('v'),f=frame();f.pose={status:'missing'};
 assert.throws(()=>s.lock(f,100,200,10));assert.equal(s.zone,null);
 s.lock(f,100,200,10,[250,450]);assert.equal(s.zone.confidence,null);assert.equal(s.zone.validated,false);
});
test('rejects release boundary, nonfinite, inverted and offscreen geometry',()=>{
 for(const [l,r,release,height] of [[100,200,3,null],[100,200,4.5,null],[-1,200,10,null],[200,100,10,null],[100,900,10,null],[NaN,200,10,null],[100,200,10,[500,400]],[100,200,10,[0,Infinity]]]) {
  const s=new FixedZone('v');assert.throws(()=>s.lock(frame(),l,r,release,height));assert.equal(s.zone,null);
 }
});
test('failed replacement clears old ready zone',()=>{
 const s=new FixedZone('v');s.lock(frame(),100,200,10);
 assert.throws(()=>s.lock(frame(10),100,200,10));assert.equal(s.zone,null);
});
test('missing later pose preserves reference; camera/scene changes cancel',()=>{
 for(const reason of ['camera_moved','scene_changed']){
  const s=new FixedZone('v');s.lock(frame(),100,200,10);const f=frame(12);f.pose.status='missing';
  assert.ok(s.visible(f));s.invalidate(reason);assert.equal(s.visible(f),null);assert.equal(s.reason,reason);
 }
});
test('next pitch resets; start and finish require valid transitions',()=>{
 const s=new FixedZone('v');assert.throws(()=>s.start());s.lock(frame(),100,200,10);const id=s.zone.pitch_id;
 assert.throws(()=>s.finish());s.start();assert.throws(()=>s.lock(frame(),100,200,10));s.finish();
 s.reset();assert.equal(s.zone,null);s.lock(frame(),100,200,10);assert.notEqual(s.zone.pitch_id,id);
});
test('size changes invalidate a fixed zone',()=>{
 const s=new FixedZone('v');s.lock(frame(),100,200,10);const f=frame(12);f.image_width=900;
 assert.equal(s.visible(f),null);assert.equal(s.reason,'image_size_changed');
});
test('automatic lock activates only at confirmation and does not claim release',()=>{
 const s=new FixedZone('v');s.autoLock(frame(3),100,200,{onset_frame_index:4,confirmed_frame_index:6},20);
 assert.equal(s.state,'tracking');assert.equal(s.visible(frame(5)),null);
 assert.ok(s.visible(frame(6)));assert.equal(s.zone.reference_frame_index,3);
 assert.equal(s.zone.release_frame,null);assert.equal(s.zone.lock_source,'automatic_motion_onset');
});
