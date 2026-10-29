/* Decorative motion only: no provider calls, freight state, or service-status changes. */
(() => {
  function createController({raf, caf, reduce, enabled, hidden, write}) {
    const records = new Set();
    let frame = 0;
    const quiet = () => reduce() || !enabled() || hidden();
    const neutral = record => {
      record.x = record.y = record.targetX = record.targetY = 0;
      write(record.element, 0, 0);
    };
    function tick() {
      frame = 0;
      if (quiet()) { records.forEach(neutral); return; }
      let moving = false;
      records.forEach(record => {
        if (!record.visible) { neutral(record); return; }
        record.x += (record.targetX - record.x) * .18;
        record.y += (record.targetY - record.y) * .18;
        if (Math.abs(record.x-record.targetX) < .005) record.x=record.targetX;
        if (Math.abs(record.y-record.targetY) < .005) record.y=record.targetY;
        write(record.element,record.x,record.y);
        moving ||= record.x!==record.targetX || record.y!==record.targetY;
      });
      if (moving) frame=raf(tick);
    }
    const wake = () => { if (!frame && !quiet()) frame=raf(tick); };
    return {
      add(element) { const r={element,x:0,y:0,targetX:0,targetY:0,visible:true};records.add(r);return r; },
      point(record,x,y) { if (quiet() || !record.visible) { neutral(record);return; } record.targetX=Math.max(-1,Math.min(1,x));record.targetY=Math.max(-1,Math.min(1,y));wake(); },
      leave(record) {record.targetX=record.targetY=0;wake();},
      visible(record,value) {record.visible=value;if(!value)neutral(record);},
      sync() {if(frame)caf(frame);frame=0;records.forEach(neutral);},
      destroy() {this.sync();records.clear();},
    };
  }
  globalThis.CreatureMotion={createController};
  if (typeof document==='undefined')return;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const preference=()=>document.documentElement.dataset.atmosphere!=='off';
  const timers=new Map();
  const controller=createController({
    raf:requestAnimationFrame,caf:cancelAnimationFrame,
    reduce:()=>reduced.matches,enabled:preference,hidden:()=>document.hidden,
    write(element,x,y) {
      element.style.setProperty('--creature-x',`${(x*5).toFixed(2)}px`);
      element.style.setProperty('--creature-y',`${(y*4).toFixed(2)}px`);
      element.style.setProperty('--creature-rx',`${(-y*6).toFixed(2)}deg`);
      element.style.setProperty('--creature-ry',`${(x*8).toFixed(2)}deg`);
      element.style.setProperty('--gaze-x',`${(x*3).toFixed(2)}px`);
      element.style.setProperty('--gaze-y',`${(y*2).toFixed(2)}px`);
    },
  });
  const observer=new IntersectionObserver(entries=>entries.forEach(entry=>{
    const record=entry.target._creatureRecord;
    if(record)controller.visible(record,entry.isIntersecting);
    entry.target.classList.toggle('creature-paused',!entry.isIntersecting);
  }));
  function awaken(element) {
    if(reduced.matches || !preference() || document.hidden)return;
    clearTimeout(timers.get(element));
    element.classList.remove('creature-awake');
    void element.offsetWidth;
    element.classList.add('creature-awake');
    timers.set(element,setTimeout(()=>{element.classList.remove('creature-awake');timers.delete(element);},2400));
  }
  function sync() {
    controller.sync();
    timers.forEach((id,element)=>{clearTimeout(id);element.classList.remove('creature-awake');});timers.clear();
    document.body.classList.toggle('creature-still',reduced.matches || !preference() || document.hidden);
    const modal=document.querySelector('dialog[open]');
    document.querySelectorAll('[data-motion-creature]').forEach(element=>{
      element.classList.toggle('creature-modal-paused',Boolean(modal&&!modal.contains(element)));
    });
  }
  function bind(root=document) {
    root.querySelectorAll('.provider-scene,.pipeline-stage,.brain-buddy,.brain-sigil,.yard-egg').forEach(element=>{
      if(element.dataset.motionCreature)return;
      element.dataset.motionCreature='true';
      const record=controller.add(element);element._creatureRecord=record;
      observer.observe(element);
      element.addEventListener('pointermove',event=>{
        if(event.pointerType==='touch')return;
        const box=element.getBoundingClientRect();
        controller.point(record,(event.clientX-box.left)/box.width*2-1,(event.clientY-box.top)/box.height*2-1);
      },{passive:true});
      element.addEventListener('pointerleave',()=>controller.leave(record),{passive:true});
      element.addEventListener('focus',()=>{if(element.matches(':focus-visible')){element.classList.add('creature-focused');awaken(element);}});
      element.addEventListener('blur',()=>{element.classList.remove('creature-focused');controller.leave(record);});
      element.addEventListener('click',()=>awaken(element));
    });
    sync();
  }
  Object.assign(globalThis.CreatureMotion,{bind,awaken});
  document.addEventListener('visibilitychange',sync);
  reduced.addEventListener('change',sync);
  new MutationObserver(sync).observe(document.documentElement,{subtree:true,attributes:true,attributeFilter:['data-atmosphere','open']});
})();
