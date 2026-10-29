const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync(new URL('../src/load_quoting_swarm/web_assets/creature-motion.js','file://'+__filename),'utf8');
function scene(){
 const frames=new Map(), writes=[];let id=0,reduced=false,enabled=true,hidden=false;
 const context={};vm.runInNewContext(source,context);
 const controller=context.CreatureMotion.createController({raf(fn){frames.set(++id,fn);return id;},caf(id){frames.delete(id);},reduce:()=>reduced,enabled:()=>enabled,hidden:()=>hidden,write:(element,x,y)=>writes.push({element,x,y})});
 return {controller,frames,writes,frame(){const pending=[...frames.values()];frames.clear();pending.forEach(fn=>fn());},reduce(v){reduced=v;},enable(v){enabled=v;},hide(v){hidden=v;}};
}
test('pointer movements share one bounded loop and settle to rest',()=>{
 const s=scene(),a=s.controller.add('ghost'),b=s.controller.add('spider');
 for(let i=0;i<100;i++){s.controller.point(a,1,.5);s.controller.point(b,-.8,1);}
 assert.equal(s.frames.size,1);
 for(let i=0;i<60&&s.frames.size;i++)s.frame();
 assert.equal(s.frames.size,0);
 assert.deepEqual(s.writes.findLast(v=>v.element==='ghost'),{element:'ghost',x:1,y:.5});
 s.controller.leave(a);for(let i=0;i<60&&s.frames.size;i++)s.frame();
 assert.deepEqual(s.writes.findLast(v=>v.element==='ghost'),{element:'ghost',x:0,y:0});
});
test('reduced motion, effects off, and hidden tabs stop and neutralise motion',()=>{
 for(const stop of ['reduce','enable','hide']){
  const s=scene(),a=s.controller.add('brain');s.controller.point(a,1,1);s.frame();
  s[stop](stop!=='enable');s.controller.sync();
  assert.equal(s.frames.size,0);
  assert.deepEqual(s.writes.at(-1),{element:'brain',x:0,y:0});
  s.controller.point(a,.5,.5);assert.equal(s.frames.size,0);
 }
});
test('offscreen creatures cannot restart and pointer coordinates are bounded',()=>{
 const s=scene(),a=s.controller.add('hand');s.controller.visible(a,false);s.controller.point(a,1,1);
 assert.equal(s.frames.size,0);s.controller.visible(a,true);s.controller.point(a,99,-99);
 for(let i=0;i<60&&s.frames.size;i++)s.frame();
 assert.deepEqual(s.writes.at(-1),{element:'hand',x:1,y:-1});
 s.controller.destroy();assert.equal(s.frames.size,0);
});
