/* Small, escaped text renderer. Route figures always come from the checked solver result. */
(() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
  const inline = text => escape(text).replace(/\*\*([^*\n]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`\n]+)`/g,'<code>$1</code>');
  function textMarkup(text) {
    const blocks=[];let paragraph=[],items=[],listType='';
    const flushParagraph=()=>{if(paragraph.length)blocks.push('<p>'+paragraph.map(inline).join('<br>')+'</p>');paragraph=[];};
    const flushList=()=>{if(items.length)blocks.push(`<${listType}>${items.map(item=>'<li>'+inline(item)+'</li>').join('')}</${listType}>`);items=[];listType='';};
    for(const line of String(text ?? '').replace(/\r\n?/g,'\n').split('\n')) {
      const trimmed=line.trim();
      if(!trimmed){flushParagraph();flushList();continue;}
      const list=trimmed.match(/^(?:([-*])\s+|\d+[.)]\s+)(.+)$/);
      if(list){flushParagraph();const type=list[1]?'ul':'ol';if(listType&&listType!==type)flushList();listType=type;items.push(list[2]);continue;}
      flushList();
      const heading=trimmed.match(/^#{1,4}\s+(.+)$/);
      if(heading){flushParagraph();blocks.push('<h4>'+inline(heading[1])+'</h4>');continue;}
      paragraph.push(trimmed);
    }
    flushParagraph();flushList();return blocks.join('');
  }
  const number = value => value != null && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
  const count = value => number(value)?.toLocaleString('en-GB') ?? '—';
  const money = value => number(value) == null ? '—' : new Intl.NumberFormat('en-GB',{style:'currency',currency:'GBP',maximumFractionDigits:0}).format(Number(value));
  const town = value => String(value ?? '').toLowerCase().replace(/\b\w/g,c=>c.toUpperCase());
  function time(value) {if(!value)return 'At base';const date=new Date(value);return Number.isNaN(date.valueOf())?'Confirm time':date.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',timeZone:'Europe/London'});}
  function excerpt(text) {
    const clean=String(text).trim();
    if(clean.length<=320)return clean;
    const sentences=clean.match(/.*?[.!?](?=\s|$)|.+$/gs)||[clean];
    let result='';
    for(const sentence of sentences){if((result+' '+sentence).trim().length>320)break;result=(result+' '+sentence).trim();if(result.length>100)break;}
    return result || clean.slice(0,300).replace(/\s+\S*$/,'')+'…';
  }
  function planMarkup(text,plan) {
    const summary=plan.summary||{},routes=Array.isArray(plan.routes)?plan.routes:[];
    const active=routes.filter(route=>route.legs?.length),idle=routes.filter(route=>!route.legs?.length);
    const overview=excerpt(text);
    const cards=active.map(route=>{
      const places=[route.base];
      route.legs.forEach(leg=>{if(places.at(-1)!==leg.origin)places.push(leg.origin);places.push(leg.destination);});
      if(places.at(-1)!==route.base)places.push(route.base);
      return `<section class="reply-route"><div class="reply-route-heading"><h4>${escape(route.vehicle_type)}</h4><span>Home <strong>${escape(time(route.return_at))}</strong> UK</span></div><p class="reply-route-path">${places.map(place=>escape(town(place))).join(' <span aria-hidden="true">→</span> ')}</p><div class="reply-route-meta"><span>${count(route.legs.length)} loads</span><span>${count(route.loaded_miles)} mi loaded</span><span>${count(route.empty_miles)} mi empty</span><span class="reply-surplus">${money(route.estimated_surplus_gbp)} est. surplus</span></div><details class="reply-costs"><summary>Load IDs & costs</summary><p>${route.legs.map(leg=>escape(leg.load_id)).join(' · ')}<br>Revenue ${money(route.revenue_gbp)} · Estimated cost ${money(route.estimated_cost_gbp)}</p></details></section>`;
    }).join('');
    const parked=idle.length?`<details class="reply-idle"><summary>${count(idle.length)} ${idle.length===1?'vehicle stays':'vehicles stay'} at base</summary><ul>${idle.map(route=>`<li><strong>${escape(route.vehicle_type)}</strong> — ${escape(route.reason||'No feasible loop for these constraints.')}</li>`).join('')}</ul></details>`:'';
    const reasoning=String(text).trim()!==overview?`<details class="reply-reasoning"><summary>Read the AI explanation</summary>${textMarkup(text)}</details>`:'';
    return `<div class="reply-plan"><div class="reply-overview">${textMarkup(overview)}</div><dl class="reply-totals"><div><dt>Loads</dt><dd>${count(summary.matched_loads)}</dd></div><div><dt>Empty miles</dt><dd>${count(summary.empty_miles)}</dd></div><div><dt>Est. surplus</dt><dd>${money(summary.estimated_surplus_gbp)}</dd></div></dl><div class="reply-routes">${cards}</div>${parked}${reasoning}<p class="reply-review">Estimated routes · ${plan.source==='demo'?'synthetic demo':'loadboard scenario'} · review before dispatch.</p></div>`;
  }
  globalThis.BrainReplies={textMarkup,planMarkup};
})();
