const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync(new URL('../src/load_quoting_swarm/web_assets/brain-replies.js','file://'+__filename),'utf8');
const scope={Intl,Date};vm.runInNewContext(source,scope);
const {textMarkup,planMarkup}=scope.BrainReplies;

test('formats headings, paragraphs, emphasis and separate ordered/unordered lists',()=>{
 const html=textMarkup('## Plan\n\n**Home by 18:00.**\nAll times UK.\n\n- First truck\n- Second truck\n\n1. Review\n2. Approve');
 assert.match(html,/<h4>Plan<\/h4>/);
 assert.match(html,/<strong>Home by 18:00\.<\/strong><br>All times UK\./);
 assert.match(html,/<ul><li>First truck<\/li><li>Second truck<\/li><\/ul>/);
 assert.match(html,/<ol><li>Review<\/li><li>Approve<\/li><\/ol>/);
});
test('escapes model HTML and does not create unsafe links',()=>{
 const html=textMarkup('<img src=x onerror="steal()">\n**<script>bad()</script>**\n[unsafe](javascript:steal())');
 assert.doesNotMatch(html,/<img|<script|<a\s/);
 assert.match(html,/&lt;img/);
 assert.match(html,/<strong>&lt;script&gt;bad\(\)&lt;\/script&gt;<\/strong>/);
});
const route={vehicle_type:'7.5t Rigid',base:'MANCHESTER',return_at:'2026-10-30T14:15:00+00:00',loaded_miles:88,empty_miles:0,revenue_gbp:600,estimated_cost_gbp:250,estimated_surplus_gbp:350,legs:[{load_id:'LOOP-201',origin:'MANCHESTER',destination:'LEEDS'},{load_id:'LOOP-202',origin:'LEEDS',destination:'MANCHESTER'}]};
const plan={source:'demo',summary:{matched_loads:2,empty_miles:0,estimated_surplus_gbp:350},routes:[route]};
test('route cards use solver data and keep a long explanation in a disclosure',()=>{
 const text='The rigid has a paying trip home. '+('This is additional explanation. '.repeat(20));
 const html=planMarkup(text,plan);
 assert.match(html,/<h4>7.5t Rigid<\/h4>/);
 assert.match(html,/Home <strong>14:15<\/strong> UK/);
 assert.match(html,/Manchester <span aria-hidden="true">→<\/span> Leeds <span aria-hidden="true">→<\/span> Manchester/);
 assert.match(html,/£350 est\. surplus/);
 assert.match(html,/<details class="reply-reasoning">/);
 assert.match(html,/Revenue £600 · Estimated cost £250/);
 assert.equal((html.match(/class="reply-route"/g)||[]).length,1);
});
test('unmatched vehicles and unsafe town labels remain explicit and escaped',()=>{
 const html=planMarkup('No match.',{...plan,routes:[{...route,base:'<svg onload=bad()>',vehicle_type:'<img>',legs:route.legs},{vehicle_type:'Artic',legs:[],reason:'No feasible return load.'}]});
 assert.doesNotMatch(html,/<svg|<img/);
 assert.match(html,/1 vehicle stays at base/);
 assert.match(html,/No feasible return load\./);
});
test('missing financial figures are never presented as zero',()=>{
 const html=planMarkup('Review.',{...plan,routes:[{...route,estimated_cost_gbp:null,revenue_gbp:undefined,estimated_surplus_gbp:null}]});
 assert.match(html,/Revenue — · Estimated cost —/);
 assert.match(html,/— est\. surplus/);
});
