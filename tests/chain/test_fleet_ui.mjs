import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../../src/load_quoting_swarm/chain/fleet.js', import.meta.url), 'utf8');
function app({fail = false} = {}) {
  const nodes = new Map();
  const node = () => ({textContent:'', value:'all', options:[{}], children:[], listeners:{},
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; },
    addEventListener(name, fn) { this.listeners[name] = fn; }});
  const get = (id) => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
  const requests = [];
  const fixture = {meta:{diesel_ppl:199.22,market:{source:'synthetic-demo'}},ledger:{},
    kpis:{trucks:1,trucks_home_on_time:0,decisions_escalated:1,tempting_illegal_avoided:0,profit_planned_gbp:10,illustrative_dispatchers_needed:1,illustrative_caption:'Illustrative only'},
    trucks:[{truck_id:'T-001',vehicle:'HGV',status:'ESCALATED',loads:[],summary:{profit_gbp:10},dispatcher_id:1}],
    exceptions:[{exception_id:'x',truck_id:'T-001',reason:'NEEDS_HUMAN',detail:'<script>unsafe</script>',resolution:null}]};
  const context = vm.createContext({document:{getElementById:get,createElement:node},fetch:async(url,options)=>{requests.push({url,options});return {ok:!fail,json:async()=>options?{events:[],label:'Policy auto-booking (simulation)'}:fixture};}});
  vm.runInContext(source,context);
  return {get,requests,settled:()=>new Promise(resolve=>setImmediate(resolve))};
}

test('UI reads the fleet_results contract and inserts exception text safely',async()=>{
  const a=app();await a.settled();assert.equal(a.requests[0].url,'/fleet_results.json');
  const card=a.get('exceptions').children[0];assert.equal(card.children[1].textContent,'<script>unsafe</script>');
  assert.match(a.get('market').textContent,/Illustrative.*display-only/);
});
test('UI requires explicit manager identity before exception approval',async()=>{
  const a=app();await a.settled();a.get('manager').value='';
  await a.get('exceptions').children[0].children[2].listeners.click();
  assert.equal(a.requests.length,1);assert.match(a.get('status').textContent,/manager identity/);
});
test('disabled feature disables commit control',async()=>{
  const a=app({fail:true});await a.settled();assert.equal(a.get('commit').disabled,true);
});
