"use strict";
const $ = (id) => document.getElementById(id);
let fleet;
const el = (tag, text) => { const node = document.createElement(tag); node.textContent = text; return node; };
async function post(url, payload) {
  const response = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed");
  return result;
}
function trucks() {
  $("truck-list").replaceChildren(...fleet.trucks.filter(t => $("dispatcher").value === "all" || String(t.dispatcher_id) === $("dispatcher").value).map(t => el("div", `${t.truck_id} · ${t.vehicle} · ${t.status === "HOME" ? "Home " + t.home_at : "Needs manual dispatch"} · ${t.loads.length} planned loads · £${t.summary.profit_gbp.toFixed(2)} projected profit`)));
}
async function refresh() {
  const response = await fetch("/fleet_results.json");
  if (!response.ok) throw new Error("Fleet feature unavailable; HB_ENABLE_CHAIN=1 is required.");
  fleet = await response.json();
  const k = fleet.kpis;
  $("kpis").replaceChildren(...[[k.trucks,"Trucks"],[k.trucks_home_on_time,"Planned home on time"],[k.decisions_escalated,"Exception decisions"],[k.tempting_illegal_avoided,"Tempting illegal options avoided"],["£"+k.profit_planned_gbp.toLocaleString(),"Projected profit"]].map(([v,label])=>{const d=el("div","");d.className="card";d.append(el("strong",String(v)),el("span",label));return d;}));
  $("market").textContent = `Diesel ${fleet.meta.diesel_ppl}p/L · ${fleet.meta.market?.source || fleet.meta.market_source}. Illustrative dispatchers needed: ${k.illustrative_dispatchers_needed} (display-only). ${k.illustrative_caption}`;
  $("exceptions").replaceChildren(...fleet.exceptions.map(item=>{
    const article=el("article","");article.append(el("strong",`${item.truck_id} · ${item.reason}`),el("p",item.detail));
    if(item.resolution){article.append(el("p",`${item.resolution.status} · ${item.resolution.manager}`));return article;}
    for(const [label,action] of [["Approve legal plan / acknowledge","APPROVE"],["Escalate","ESCALATE"]]){
      const button=el("button",label);button.addEventListener("click",async()=>{try{
        const manager=$("manager").value.trim();if(!manager)throw new Error("Enter your manager identity.");
        await post("/api/chain/decision",{exception_id:item.exception_id,action,manager});await refresh();
      }catch(e){$("status").textContent=e.message;}});article.append(button);
    }return article;
  }));
  if($("dispatcher").options.length===1)for(const id of [...new Set(fleet.trucks.map(t=>t.dispatcher_id))].sort((a,b)=>a-b)){const option=el("option",String(id));option.value=id;$("dispatcher").append(option);}
  trucks();$("status").textContent=`Simulation loaded · ${Object.keys(fleet.ledger || {}).length} ledger entries. No broker booking.`;
}
$("dispatcher").addEventListener("change",trucks);
$("commit").addEventListener("click",async()=>{try{const result=await post("/api/fleet",{commit:true});await refresh();$("status").textContent=`${result.label}: ${result.events.length} policy ledger entries confirmed.`;}catch(e){$("status").textContent=e.message;}});
refresh().catch(e=>{$("status").textContent=e.message;$("commit").disabled=true;});
