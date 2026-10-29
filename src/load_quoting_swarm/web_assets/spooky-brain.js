/* Spooky Brain: dispatch calculation UI and event-driven provider scenes. */
(() => {
  const el = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const gbp = (v) => new Intl.NumberFormat('en-GB', {style:'currency',currency:'GBP',maximumFractionDigits:0}).format(v);
  const town = (v) => String(v).toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
  const clock = (v) => v ? new Date(v).toLocaleTimeString('en-GB', {hour:'2-digit',minute:'2-digit',timeZone:'Europe/London'}) : 'At base';
  let conversation = [], extraConstraints = {};
  let plan = null, selected = 0, busy = false, staticPlans = null, objective = 'balanced';
  const providers = [
    ['aws','AWS','The pumpkin power station','Infrastructure','Hosts the backend when deployed on AWS. Hosting is separate from the per-load analysis trace. The local app cannot verify cloud infrastructure status.'],
    ['crewai','CrewAI','The workflow weaver','Idle','Organises ingestion and route grouping in the live load-analysis flow. The loop planner checks constraints after Parasail interprets the dispatch conversation.'],
    ['you','You.com','The research ghost','Idle','Researches diesel prices and route restrictions. Citations and evidence appear in the API trace.'],
    ['parasail','Parasail','The zombie brain','Idle','Understands Spooky Brain conversations and explains verified truck loops. Also powers fleet-fit, pricing and risk specialists in load analysis.'],
    ['one','One','The skeleton gatekeeper','Idle','Human approval handoff in the analysis flow. A recommendation never books a load or sends a message by itself.']
  ];
  const sceneArt = (id) => globalThis.SpookyArt.scene(id);
  function buildScenes() {
    el('provider-scenes').innerHTML = providers.map(([id,name,role,status,description]) => `<button type="button" class="provider-scene" data-provider="${id}" aria-pressed="false" aria-label="${name}: ${role}. ${status}">${sceneArt(id)}<span class="scene-service"><b>${name}</b><span class="service-state">${status}</span></span><span class="scene-role">${role}</span><span class="scene-light"></span></button>`).join('');
    document.querySelectorAll('.provider-scene').forEach(button => {
      button.addEventListener('pointermove', event => {
        const r = button.getBoundingClientRect();
        button.style.setProperty('--torch-x', `${event.clientX-r.left}px`);
        button.style.setProperty('--torch-y', `${event.clientY-r.top}px`);
      });
      button.addEventListener('click', () => {
        document.querySelectorAll('.provider-scene').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
        const p = providers.find(p => p[0] === button.dataset.provider);
        el('provider-description').textContent = `${p[1]} · ${p[4]}`;
      });
    });
    document.querySelectorAll('.pipeline-stage').forEach(stage => {
      const id = stage.dataset.stage;
      stage.insertAdjacentHTML('afterbegin', `<div class="pipeline-haunt">${sceneArt(`pipeline-${id}`)}</div>`);
    });
  }
  globalThis.SpookyServices = {
    reset(recorded) {
      document.querySelectorAll('.provider-scene').forEach(b => {
        b.classList.remove('working','complete','service-failed','awaiting-human');
        b.dataset.recorded = recorded ? 'true' : 'false';
        const provider=providers.find(p=>p[0]===b.dataset.provider);b.setAttribute('aria-label',`${provider[1]}: ${provider[2]}. ${provider[3]}`);
        b.querySelector('.service-state').textContent = b.dataset.provider === 'aws' ? 'Infrastructure' : 'Idle';
      });
    },
    stage(name, status) {
      const button = document.querySelector(`.provider-scene[data-provider="${name}"]`);
      if (!button) return;
      button.classList.remove('working','complete','service-failed','awaiting-human');
      const prefix = button.dataset.recorded === 'true' ? 'Replay · ' : '';
      button.classList.add(status === 'active' ? (name === 'one' ? 'awaiting-human' : 'working') : status === 'failed' ? 'service-failed' : 'complete');
      button.setAttribute('aria-label', `${name === 'you' ? 'You.com' : providers.find(p=>p[0]===name)?.[1] || name}: ${prefix}${status === 'active' ? (name==='one'?'Awaiting human':'Working') : status === 'failed' ? 'Failed' : 'Complete'}`);
      button.querySelector('.service-state').textContent = prefix + (status === 'active' ? (name === 'one' ? 'Awaiting human' : 'Working') : status === 'failed' ? 'Failed' : 'Complete');
    }
  };
  function message(text, user = false, source = 'brain', replyPlan = null) {
    const node = document.createElement('div');
    node.className = user ? 'user-message' : 'brain-message';
    node.innerHTML = `<span class="message-author">${user ? 'YOU' : source === 'calculation' ? 'CALCULATED SCENARIO' : 'SPOOKY BRAIN'}</span><div class="message-body">${replyPlan ? globalThis.BrainReplies.planMarkup(text, replyPlan) : globalThis.BrainReplies.textMarkup(text)}</div>`;
    conversation.push({role:user?'user':'assistant',content:String(text).slice(0,2000)});
    conversation=conversation.slice(-12);
    el('brain-messages').append(node);
    const log=el('brain-messages');
    log.scrollTop=user ? log.scrollHeight : Math.max(0,node.offsetTop-10);
  }
  function mapSvg(route) {
    const legs = route?.legs || [];
    if (!legs.length) return `<div class="base-rest"><span aria-hidden="true">⌂</span><strong>${route ? town(route.base) : 'Home base'}</strong><p>${esc(route?.reason || 'No loops in this scenario.')}</p></div>`;
    const width = 720, height = 265, base = {x:80,y:132};
    const stopNames = [...new Set(legs.flatMap(l => [l.origin,l.destination]).filter(t => t !== route.base))];
    // Operational sequence diagram: each town has one node; both ends share the base.
    const points = {[route.base]:base};
    stopNames.forEach((t,i) => {
      const angle = stopNames.length === 1 ? 0 : -Math.PI/2 + i * Math.PI*1.6/stopNames.length;
      points[t] = stopNames.length === 1 ? {x:560,y:132} : {x:400+190*Math.cos(angle),y:135+85*Math.sin(angle)};
    });
    let paths = '', position = route.base, step = 0;
    function line(a,b,empty,label) {
      const p=points[a],q=points[b];
      const lift = (step++ % 2 === 0 ? 1 : -1) * 70;
      const d = a === b ? `M${p.x} ${p.y}c-65 -100 80 -100 16 -3` : `M${p.x} ${p.y}Q${(p.x+q.x)/2} ${(p.y+q.y)/2-lift} ${q.x} ${q.y}`;
      const cx = a === b ? p.x+10 : (p.x+q.x)/2, cy = a === b ? p.y-73 : (p.y+q.y)/2-lift/2;
      paths += `<path d="${d}" class="${empty?'map-empty':'map-loaded'}" marker-end="url(#arrow-${empty?'empty':'loaded'})"/><text x="${cx}" y="${cy-8}" text-anchor="middle" class="map-leg-label">${esc(label)}</text>`;
    }
    legs.forEach((l,i) => {
      if (l.empty_before_miles > 0) line(position,l.origin,true,`${l.empty_before_miles} mi empty`);
      line(l.origin,l.destination,false,`${i+1} · ${l.loaded_miles} mi loaded`);
      position=l.destination;
    });
    if(position !== route.base) line(position,route.base,true,`${route.home_empty_miles} mi home`);
    const nodes = Object.entries(points).map(([name,p]) => `<g><circle cx="${p.x}" cy="${p.y}" r="${name===route.base?19:9}" class="${name===route.base?'map-base':'map-stop'}"/>${name===route.base?`<text x="${p.x}" y="${p.y+5}" text-anchor="middle" class="map-home">⌂</text>`:''}<text x="${p.x}" y="${p.y+39}" text-anchor="middle" class="map-town">${esc(town(name))}</text><text x="${p.x}" y="${p.y+55}" text-anchor="middle" class="map-note">${name===route.base?'START + RETURN':'PICKUP / DELIVERY'}</text></g>`).join('');
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(route.vehicle_id)} closed loop: ${esc([route.base,...legs.map(l=>l.destination),...(legs.at(-1)?.destination===route.base?[]:[route.base])].join(' to '))}"><defs><marker id="arrow-loaded" markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto"><path d="m0 0 6 3-6 3" fill="none" stroke="#b85b31"/></marker><marker id="arrow-empty" markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto"><path d="m0 0 6 3-6 3" fill="none" stroke="#9b9389"/></marker></defs>${paths}${nodes}<text x="698" y="25" text-anchor="end" class="map-caption">${esc(route.vehicle_type.toUpperCase())} / ${esc(route.vehicle_id.replace('DEMO-',''))}</text><text x="698" y="246" text-anchor="end" class="map-note">HOME ${clock(route.return_at)} UK · REVIEW REQUIRED</text></svg>`;
  }
  function render() {
    const s = plan.summary;
    selected = Math.min(selected, plan.routes.length-1);
    el('loop-map').innerHTML = mapSvg(plan.routes[selected]);
    el('loop-metrics').innerHTML = [[s.matched_loads,'loads connected'],[`${s.loaded_pct}%`,'miles carrying freight'],[`${s.empty_miles} mi`,'empty, including home'],[gbp(s.estimated_surplus_gbp),'estimated surplus']].map(([v,l])=>`<div><strong>${esc(v)}</strong><span>${esc(l)}</span></div>`).join('');
    el('loop-count').textContent = `${s.vehicles_planned} / ${plan.routes.length} vehicles matched`;
    el('fleet-loops').innerHTML = plan.routes.map((r,i) => `<details class="fleet-loop ${i===selected?'selected':''}" ${i===selected?'open':''}><summary data-route="${i}"><span class="truck-key">${String(i+1).padStart(2,'0')}</span><span class="truck-title"><b>${esc(r.vehicle_type)}</b><small>${esc(r.vehicle_id)} · ${esc(town(r.base))} base</small></span><span class="truck-route">${r.legs.length ? `${r.legs.length} loads · home ${clock(r.return_at)}`:'Stays at base'}<small>${r.loaded_miles} loaded / ${r.empty_miles} empty mi</small></span><span class="route-status">${r.legs.length?'Review loop':'At base'}</span></summary><div class="loop-stops">${r.legs.map((l,j)=>`<div class="loop-stop"><span>${j+1}</span><p><b>${esc(town(l.origin))} → ${esc(town(l.destination))}</b><small>${esc(l.load_id)} · ${clock(l.pickup_at)}–${clock(l.delivered_at)} UK · ${gbp(l.revenue_gbp)}${l.empty_before_miles?' · '+l.empty_before_miles+' mi empty to pickup':''}</small></p></div>`).join('')}${r.legs.length?`<div class="loop-stop home-stop"><span>⌂</span><p><b>Back to ${esc(town(r.base))} · ${clock(r.return_at)} UK</b><small>${r.home_empty_miles} mi empty home · ${gbp(r.estimated_cost_gbp)} estimated operating cost</small></p></div><p class="loop-review">Review required: payload, equipment, ULEZ, road times and driver duty. This suggestion does not reserve or book loads.</p>`:`<p class="loop-review">${esc(r.reason)}</p>`}</div></details>`).join('');
    el('plan-assumptions').innerHTML = `<p>${esc(plan.explanation)}</p><ul>${plan.assumptions.map(a=>`<li>${esc(a)}</li>`).join('')}</ul><p>${plan.input_loads} input loads · ${plan.source==='demo'?'Purpose-built synthetic loop fixture':'Current loadboard, excluding recorded manager decisions'}.</p>`;
    el('plan-date').value = plan.options.date;
    if ([...el('plan-base').options].some(o=>o.value===plan.options.base)) el('plan-base').value = plan.options.base;
    else {
      const option = document.createElement('option'); option.value=plan.options.base; option.textContent=town(plan.options.base); el('plan-base').append(option); el('plan-base').value=option.value;
    }
    el('plan-return').value = plan.options.return_by;
    objective = plan.options.objective;
    el('plan-source').value = plan.source;
    el('sidebar-loops').textContent = plan.summary.vehicles_planned;
    el('sidebar-loaded').textContent = `${plan.summary.loaded_miles} mi`;
    el('sidebar-empty').textContent = `${plan.summary.empty_miles} mi`;
    extraConstraints = Object.fromEntries(Object.entries(plan.options).filter(([key])=>!['base','date','return_by','objective'].includes(key)));
    renderConstraints();
  }
  function renderConstraints() {
    const chips=[];
    if(extraConstraints.vehicle_ids?.length)chips.push('Selected vehicles only');
    if(extraConstraints.exclude_towns?.length)chips.push('No stops in '+extraConstraints.exclude_towns.map(town).join(', '));
    if(extraConstraints.max_empty_miles!=null)chips.push(`Max ${extraConstraints.max_empty_miles} empty mi / truck`);
    if(extraConstraints.start_time && extraConstraints.start_time!=='06:00')chips.push('Start '+extraConstraints.start_time+' UK');
    if(extraConstraints.max_driving_hours && extraConstraints.max_driving_hours!==9)chips.push(`Max ${extraConstraints.max_driving_hours}h driving`);
    el('brain-constraints').innerHTML=chips.map(c=>`<span>${esc(c)}</span>`).join('')+(chips.length?'<button type="button" id="clear-brain-constraints">Clear extra limits ×</button>':'');
  }
  function activity(on) {
    el('brain-activity').hidden=!on;
    document.body.classList.toggle('ai-thinking',on);
  }
  function configureBrain() {
    const staticMode=typeof state!=='undefined'&&state.deploymentMode==='static-demo';
    const configured=typeof state!=='undefined'&&state.brain?.configured;
    el('brain-ai-status').textContent=staticMode?'STATIC PREVIEW':configured?'PARASAIL AI':'CONNECT AI';
    el('brain-ai-status').classList.toggle('connected',Boolean(configured&&!staticMode));
    el('brain-mode-note').textContent=staticMode?'Static route previews · run the backend for real AI chat':configured?'Parasail understands · route solver checks · you approve':'Real AI chat needs server-side Parasail credentials.';
    if(staticMode){el('crew-analyze').textContent='Replay recorded analysis ↗';el('brain-prompt').placeholder='This static preview has no AI backend. Use the controls to explore routes.';}
  }
  async function calculate(prompt='', initial=false) {
    if(busy)return;
    const history=conversation.slice(-10);
    busy=true; ['brain-send','plan-date','plan-base','plan-return','plan-source'].forEach(id=>el(id).disabled=true);
    el('brain-form').setAttribute('aria-busy','true');
    if(prompt)message(prompt,true);
    const body={...extraConstraints,prompt,history,source:el('plan-source').value,date:el('plan-date').value,base:el('plan-base').value,return_by:el('plan-return').value,objective};
    const aiRequest=Boolean(prompt)&&!(typeof state!=='undefined'&&state.deploymentMode==='static-demo');
    if(aiRequest){activity(true);globalThis.SpookyServices.reset(false);if(state.brain?.configured)globalThis.SpookyServices.stage('parasail','active');}
    try {
      let result, answer=null;
      if(typeof state !== 'undefined' && state.deploymentMode==='static-demo') {
        if(prompt)throw Error('Real AI chat requires the Python backend. This static preview never pretends to understand a message. Use the date, base and home-time controls to explore its calculated scenarios.');
        if(!staticPlans){const response=await fetch('api/plans');if(!response.ok)throw Error('Static loop scenarios are unavailable. Start the Python backend.');staticPlans=await response.json();}
        const key=[body.source,body.date,body.base,body.objective,body.return_by].join('|');
        result=staticPlans[key];
        if(!result)throw Error('Static route previews support 29–31 October, fleet/London/Manchester/Bristol bases and 18:00 or 20:00 returns. Other constraints need the backend.');
        if(body.source==='loadboard' && result.routes.some(r=>r.legs.some(l=>state.loads.some(x=>String(x.load_id)===l.load_id&&['BOOKED','PASSED'].includes(x.ledger?.status))))) {plan=null;el('loop-metrics').innerHTML='';el('fleet-loops').innerHTML='';el('loop-count').textContent='Recalculation required';throw Error('A load in this static scenario has a manager decision. Run the backend to recalculate without it.');}
      } else {
        const response=await fetch(prompt?'api/brain':'api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const data=await response.json();if(!response.ok)throw Error(data.error || 'Unable to calculate loops.');
        if(prompt){
          globalThis.SpookyServices.stage('parasail','done');
          el('brain-mode-note').textContent=`Parasail · ${data.ai.model} · ${data.ai.usage.requests} AI calls · checked calculations`;
          if(data.type==='clarification'){message(data.message+(data.unsupported?.length?'\n\nTo clarify:\n'+data.unsupported.map(item=>'- '+item).join('\n'):''));return;}
          result=data.plan;answer=data.message;
        } else result=data;
      }
      plan=result;selected=Math.max(0,result.routes.findIndex(r=>r.legs.length));render();
      const summary=plan.summary;
      message(answer || `${initial?'Scenario ready:':'Recalculated:'} ${summary.matched_loads} loads, ${summary.vehicles_planned} vehicle loops, ${summary.empty_miles} estimated empty miles. Every planned vehicle returns to base. ${plan.source==='demo'?'This is the six-load synthetic demo.':'Using the current loadboard.'} ${initial?'Tell me what you would like to change.':'All suggestions need human review.'}`,false,answer?'brain':'calculation',answer?plan:null);
    } catch(error) {
      if(aiRequest)globalThis.SpookyServices.stage('parasail','failed');
      message(error.message);
      if(prompt&&!el('brain-prompt').value.trim())el('brain-prompt').value=prompt;
      if(!plan)el('loop-map').innerHTML='<div class="base-rest"><strong>Planner unavailable</strong><p>Check the dispatch request or backend, then calculate again.</p></div>';
    } finally {
      busy=false;activity(false);['brain-send','plan-date','plan-base','plan-return','plan-source'].forEach(id=>el(id).disabled=false);el('brain-form').removeAttribute('aria-busy');
    }
  }
  function bindEasterEggs() {
    const found=new Set();
    const clues=['I smell a profitable backhaul.','A good brain always gets you home.','Psst. Three stowaways are hiding below.','Zero empty thoughts. Fewer empty miles.'];
    let poke=0;
    document.querySelectorAll('.brain-buddy').forEach(button=>button.addEventListener('click',()=>{
      el('buddy-whisper').textContent=clues[poke++%clues.length];
      button.classList.remove('buddy-awake');void button.offsetWidth;button.classList.add('buddy-awake');
    }));
    document.querySelectorAll('[data-egg]').forEach(button=>{
      const key=button.dataset.egg;
      button.innerHTML=sceneArt(key==='ghost'?'you':key==='spider'?'crewai':'aws');
      button.addEventListener('click',()=>{
        found.add(key);button.classList.add('caught');button.setAttribute('aria-pressed','true');
        el('sidebar-hunt').textContent=`${found.size} / 3 stowaways found`;
        el('yard-progress').textContent=found.size===3?'All ghouls home. Secret night shift complete.':'Found the '+key+'! '+found.size+' / 3 aboard.';
        if(found.size===3){el('haunted-yard').classList.add('all-aboard');el('buddy-whisper').textContent='All ghouls accounted for. Now that’s a closed loop.';}
      });
    });
  }
  document.addEventListener('DOMContentLoaded', () => {
    document.documentElement.dataset.workspaceSection='brain-workspace';
    document.querySelector('.planner-jump').classList.add('section-active');
    buildScenes();
    bindEasterEggs();
    globalThis.CreatureMotion?.bind();
    el('brain-constraints').addEventListener('click',event=>{if(!busy&&event.target.closest('#clear-brain-constraints')){extraConstraints={};calculate();}});
    document.querySelectorAll('.nav-item').forEach(button=>button.addEventListener('click',()=>el('loadboard').scrollIntoView({block:'start'})));
    const sectionObserver=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){
      document.documentElement.dataset.workspaceSection=entry.target.id;
      document.querySelectorAll('.planner-jump,.section-jump').forEach(link=>link.classList.toggle('section-active',link.getAttribute('href')==='#'+entry.target.id));
      document.querySelectorAll('.nav-item').forEach(button=>{const active=entry.target.id==='loadboard'&&button.dataset.view===state.view;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
      const labels={'brain-workspace':'Spooky Brain','night-crew':'The night crew','loadboard':state.view==='decisions'?'Decision ledger':'Loadboard','haunted-yard':'The haunted lay-by'};
      document.querySelector('#view-label').textContent=labels[entry.target.id];
    }}),{rootMargin:'-10% 0px -65% 0px'});
    ['brain-workspace','night-crew','loadboard','haunted-yard'].forEach(id=>sectionObserver.observe(el(id)));
    const scenesObserver = new IntersectionObserver(entries=>entries.forEach(e=>e.target.classList.toggle('scene-paused',!e.isIntersecting)));
    document.querySelectorAll('.provider-scene,.pipeline-stage').forEach(s=>scenesObserver.observe(s));
    document.addEventListener('visibilitychange',()=>document.body.classList.toggle('services-paused',document.hidden));
    el('brain-form').addEventListener('submit',event=>{event.preventDefault();if(busy)return;const prompt=el('brain-prompt').value.trim();el('brain-prompt').value='';calculate(prompt);});
    el('brain-prompt').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();el('brain-form').requestSubmit();}});
    document.querySelectorAll('[data-brain-prompt]').forEach(b=>b.addEventListener('click',()=>calculate(b.dataset.brainPrompt)));
    ['plan-date','plan-base','plan-return','plan-source'].forEach(id=>el(id).addEventListener('change',()=>calculate()));
    el('fleet-loops').addEventListener('click',event=>{const summary=event.target.closest('[data-route]');if(!summary)return;event.preventDefault();selected=+summary.dataset.route;render();});
    el('crew-analyze').addEventListener('click',()=>{if(typeof state!=='undefined'&&state.deploymentMode==='static-demo'&&state.recordedRunLoadId){analyzeLoad(String(state.recordedRunLoadId));return;}const load=typeof selectedLoad==='function'?selectedLoad():null;if(load)analyzeLoad(String(load.load_id));else message('Select a load in the loadboard below to inspect its service analysis.');});
    document.addEventListener('haulage-ready',()=>{configureBrain();calculate('',true);},{once:true});
    document.addEventListener('haulage-decision',()=>{if(el('plan-source').value==='loadboard')calculate();});
  });
})();
