// Unit-level DOM stub: tests the page's handlers, without controlling a browser.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
function page(automatic=null){
 const template=fs.readFileSync(path.join(__dirname,'../ui/fixed-zone.html'),'utf8');
 const state=fs.readFileSync(path.join(__dirname,'../ui/fixed-zone.js'),'utf8');
 const elements={};
 function element(id='') {return {id,_value:'',get value(){return this._value;},set value(v){this._value=String(v);},checked:false,disabled:false,style:{},children:[],attributes:{},textContent:'',
   setAttribute(k,v){this.attributes[k]=v;},replaceChildren(){this.children=[];this.value='';},
   append(child){this.children.push(child);if(id==='recommend'&&this.children.length===1)this.value=String(child.value);},click(){this.onclick?.();}};}
 for(const match of template.matchAll(/id="([^"]+)"/g))elements[match[1]]=element(match[1]);
 const frames=[0,1,2,3].map(i=>({frame_index:i,image_width:800,image_height:700,preview:'',
   pose:i===3?{status:'missing',reason:'no_detection',keypoints:{},top_y:null,bottom_y:null}:
   {status:'ok',confidence:.9,top_y:300+i,bottom_y:500+i,keypoints:{}}}));
 const data={video_id:'test',frames,automatic,input_manifest_sha256:'input',model_sha256:'model',config:{threshold:.5,release_frame:2,zone_x:[100,200]}};
 const ctx=vm.createContext({structuredClone,console,setInterval:()=>1,clearInterval:()=>{},setTimeout:()=>{},
   document:{getElementById:id=>elements[id],createElement:()=>element(),createElementNS:()=>element()}});
 const scripts=[...template.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
 vm.runInContext(scripts[0].replace('/*__STATE__*/',state),ctx);
 vm.runInContext(scripts[1].replace('/*__DATA__*/',JSON.stringify(data)),ctx);
 return {elements,ctx,result:()=>JSON.parse(vm.runInContext('JSON.stringify(payload())',ctx))};
}
test('page handlers choose recommendation, lock, scrub missing pose, complete and reset',()=>{
 const p=page(),e=p.elements;
 assert.equal(p.result().selection_frame,1);
 e.lock.onclick();assert.equal(p.result().state,'ready');const box=p.result().zone.bbox_xyxy;
 e.start.onclick();e.seek.value='3';e.seek.oninput();assert.deepEqual(p.result().zone.bbox_xyxy,box);
 e.finish.onclick();assert.equal(p.result().state,'completed');e.reset.onclick();assert.equal(p.result().zone,null);
});
test('editing geometry cancels; manual height must be explicitly enabled',()=>{
 const p=page(),e=p.elements;e.lock.onclick();e.left.value='120';e.left.onchange();
 assert.equal(p.result().zone,null);e.seek.value='3';e.seek.oninput();e.lock.onclick();assert.equal(p.result().zone,null);
 e.seek.value='0';e.seek.oninput();e.manual.checked=true;e.manual.onchange();e.top.value='200';e.bottom.value='450';
 e.lock.onclick();assert.equal(p.result().zone.method,'manual-height-and-width');
 e.camera.onclick();assert.equal(p.result().zone,null);
});
test('automatic mode waits for confirmation then locks previous pose without button click',()=>{
 const p=page({status:'ok',reference_frame_index:1,event:{onset_frame_index:2,confirmed_frame_index:3}}),e=p.elements;
 assert.equal(p.result().zone,null);e.seek.value='2';e.seek.oninput();assert.equal(p.result().zone,null);
 e.seek.value='3';e.seek.oninput();assert.equal(p.result().state,'tracking');
 assert.equal(p.result().zone.reference_frame_index,1);e.reset.onclick();e.seek.oninput();assert.equal(p.result().zone,null);
});
