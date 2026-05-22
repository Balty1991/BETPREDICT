/* BETPREDICT 2.0 — CLV, Pyramid Assistant, AI Insight, Live Value, Heatmap */
(function(){
  'use strict';
  const API={clv:null,pyramid:null,insights:null,alerts:null,heatmap:null,signals:null};
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const nf=(v,d=1)=>{const n=Number(v);return Number.isFinite(n)?n.toFixed(d):'—'};
  const pct=v=>{const n=Number(v);return Number.isFinite(n)?`${n>=0?'+':''}${n.toFixed(1)}%`:'—'};
  const prob=v=>{const n=Number(v);return Number.isFinite(n)?`${n.toFixed(1)}%`:'—'};
  const fetchJ=p=>fetch(p+'?bp20='+Date.now(),{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status));
  const scoreOf=s=>Number(s?.display_score??s?.market_signal_score??s?.pyramid_ready_score??s?.smartbet_score_v6??s?.smartbet_score??0)||0;
  const sigs=()=>API.signals?.signals||[];
  const insightFor=s=>s.ai_insight || API.insights?.by_signal?.[`${s.event_id}|${s.market}`]?.insight || '';
  const clvFor=s=>{
    const eid=String(s.event_id||''), mk=String(s.market||'').toLowerCase().replace(/_/g,'');
    const by=API.clv?.by_event_market||{};
    for(const [k,v] of Object.entries(by)){if(k.startsWith(eid+'|') && k.toLowerCase().replace(/_/g,'').includes(mk))return v;}
    return null;
  };
  function badgeClass(v){const n=Number(v);return Number.isFinite(n)?(n>0?'good':n<0?'bad':'warn'):'warn'}
  function clvBadge(s){const v=s.clv_beat_pct??clvFor(s)?.clv_pct;return `<span class="bp20-badge ${badgeClass(v)}">CLV Beat ${pct(v)}</span>`;}
  function pyramidBadge(s){const v=Number(s.pyramid_ready_score||0);return v?`<span class="bp20-badge ${v>=75?'good':'warn'}">Pyramid ${nf(v,0)}/100</span>`:'';}
  function liveBadge(s){return s.live_value_label?`<span class="bp20-badge good">${esc(s.live_value_label)} · EV ${pct(s.live_value_ev_pct)}</span>`:'';}
  function insightBadge(s){return insightFor(s)?`<span class="bp20-badge good">AI Insight</span>`:'';}
  function badgesFor(s){return `<div class="bp20-badges">${clvBadge(s)}${pyramidBadge(s)}${liveBadge(s)}${insightBadge(s)}</div>`;}

  async function loadData(){
    const [signals,clv,pyramid,insights,alerts,heatmap]=await Promise.all([
      API.signals?Promise.resolve(API.signals):fetchJ('data/signals.json').catch(()=>({signals:[]})),
      API.clv?Promise.resolve(API.clv):fetchJ('data/clv_tracker.json').catch(()=>({summary:{},rolling_30d:{},by_event_market:{}})),
      API.pyramid?Promise.resolve(API.pyramid):fetchJ('data/pyramid_assistant.json').catch(()=>({current_step_pool:{}})),
      API.insights?Promise.resolve(API.insights):fetchJ('data/ai_insights.json').catch(()=>({by_signal:{}})),
      API.alerts?Promise.resolve(API.alerts):fetchJ('data/live_value_alerts.json').catch(()=>({alerts:[]})),
      API.heatmap?Promise.resolve(API.heatmap):fetchJ('data/performance_heatmap.json').catch(()=>({summary:{},leagues:{},cells:[]}))
    ]);
    Object.assign(API,{signals,clv,pyramid,insights,alerts,heatmap});
  }
  function renderCLV(){
    const s=API.clv?.summary||{}, r=API.clv?.rolling_30d||{};
    const reliable=Number(r.reliable_n??s.reliable_n??0), rate=Number(r.market_beat_rate??s.market_beat_rate), avg=Number(r.avg_clv_pct??s.avg_clv_pct);
    const label=reliable>=20?'MARKET BEAT':'ACUMULARE';
    return `<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">📈 CLV Validation</div><div class="bp20-sub">autoritate matematică: cota publicată vs closing line</div></div><span class="bp20-pill">${label}</span></div><div class="bp20-grid"><div class="bp20-kpi"><div class="bp20-kv ${rate>=70?'bp20-klv':'bp20-kwarn'}">${Number.isFinite(rate)?nf(rate,0)+'%':'—'}</div><div class="bp20-kl">Market Beat</div></div><div class="bp20-kpi"><div class="bp20-kv ${avg>=0?'bp20-klv':'bp20-kbad'}">${pct(avg)}</div><div class="bp20-kl">Avg CLV</div></div><div class="bp20-kpi"><div class="bp20-kv">${reliable||'—'}</div><div class="bp20-kl">Reliable</div></div></div><div class="bp20-row"><div class="bp20-note">${reliable<20?'CLV este pornit, dar încă nu are minimum 20 linii reliable. Nu îl folosim ca dovadă finală până nu strânge sample suficient.':'Sample suficient pentru citirea Market Beat Rate.'}</div></div></div>`;
  }
  function currentPyramidList(step){
    const pool=API.pyramid?.current_step_pool||{}; return (pool[String(step)]||[]).slice(0,5);
  }
  function pickCard(s,mode='pyramid'){
    const insight=insightFor(s);
    return `<div class="bp20-pick"><div><div class="bp20-match">${esc(s.home_team)} vs ${esc(s.away_team)}</div><div class="bp20-meta">${esc(s.league||'—')} · ${esc(s.event_date?new Date(s.event_date).toLocaleTimeString('ro-RO',{hour:'2-digit',minute:'2-digit'}):'—')}</div><div class="bp20-rec">${esc(s.market_label||s.market)} · ${prob(s.adj_prob)} · @${esc(s.odds??'—')}</div>${insight?`<div class="bp20-insight">${esc(insight)}</div>`:''}${badgesFor(s)}</div><div class="bp20-score">${nf(mode==='pyramid'?s.pyramid_ready_score:scoreOf(s),0)}<small>${mode==='pyramid'?'ready':'score'}</small></div></div>`;
  }
  function renderPyramid(){
    const step=Number(localStorage.getItem('bp20.pyramid.step')||1), steps=Number(localStorage.getItem('bp20.pyramid.steps')||5), avg=Number(localStorage.getItem('bp20.pyramid.avg')||1.30);
    const list=currentPyramidList(step);
    const progress=Math.min(100,Math.max(0,(step-1)/Math.max(1,steps)*100));
    return `<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">🧱 Pyramid Assistant</div><div class="bp20-sub">plan de execuție, nu doar listă de meciuri</div></div><span class="bp20-pill">Pas ${step}/${steps}</span></div><div class="bp20-form"><div class="bp20-field"><label>Pași</label><select id="bp20-steps"><option ${steps===3?'selected':''}>3</option><option ${steps===5?'selected':''}>5</option><option ${steps===7?'selected':''}>7</option></select></div><div class="bp20-field"><label>Pas curent</label><select id="bp20-step">${Array.from({length:Math.max(steps,7)},(_,i)=>i+1).filter(x=>x<=steps).map(x=>`<option ${x===step?'selected':''}>${x}</option>`).join('')}</select></div><div class="bp20-field"><label>Cotă medie</label><input id="bp20-avg" type="number" step="0.01" value="${avg.toFixed(2)}"></div></div><div class="bp20-progress"><i style="width:${progress}%"></i></div><div class="bp20-list">${list.length?list.map(x=>pickCard(x,'pyramid')).join(''):'<div class="bp20-empty">Nu există opțiuni suficient de stabile pentru pasul ales.</div>'}</div></div>`;
  }
  function renderAlerts(){
    const arr=(API.alerts?.alerts||[]).slice(0,3);
    return `<div class="bp20-card bp20-alert"><div class="bp20-head"><div><div class="bp20-title">🚨 Live Value Alert</div><div class="bp20-sub">cota actuală vs fair odd calculat de AI</div></div><span class="bp20-pill">${arr.length?'VALUE':'WATCH'}</span></div><div class="bp20-list">${arr.length?arr.map(a=>`<div class="bp20-pick"><div><div class="bp20-match">${esc(a.home_team)} vs ${esc(a.away_team)}</div><div class="bp20-meta">${esc(a.bookmaker)} · fair ${esc(a.fair_odd)} · curent ${esc(a.current_odds)}</div><div class="bp20-rec">${esc(a.label)} · ${esc(a.market_label)} · EV ${pct(a.current_ev_pct)}</div></div><div class="bp20-score">${pct(a.discrepancy_pct)}<small>gap</small></div></div>`).join(''):'<div class="bp20-empty">Nicio discrepanță live/current cu EV pozitiv acum.</div>'}</div></div>`;
  }
  function renderHeatmap(){
    const leagues=Object.entries(API.heatmap?.leagues||{}).slice(0,6);
    return `<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">🔥 Performance Heatmap</div><div class="bp20-sub">unde modelul are ROI și stabilitate mai bune</div></div><span class="bp20-pill">TRANSPARENT</span></div><div class="bp20-heat">${leagues.length?leagues.map(([name,r])=>{const g=String(r.grade||'N/A').replace('+','');return `<div class="bp20-heat-row"><div class="bp20-heat-name">${esc(name)}<div class="bp20-meta">ROI ${nf(r.roi_pct,1)}% · WR ${nf(r.win_rate,0)}% · n=${r.sample}</div></div><span class="bp20-grade ${esc(g)}">${esc(r.grade)}</span></div>`}).join(''):'<div class="bp20-empty">Heatmap-ul se va popula după rezultate validate.</div>'}</div></div>`;
  }
  function renderCommandCenter(){
    const dash=$('sec-dash'); if(!dash)return;
    let root=$('bp20-root');
    if(!root){root=document.createElement('div');root.id='bp20-root';root.className='bp20-root';const anchor=$('dash-body')||dash.lastElementChild;dash.insertBefore(root,anchor);} 
    root.innerHTML=renderCLV()+renderPyramid()+renderAlerts()+renderHeatmap();
    const steps=$('bp20-steps'), step=$('bp20-step'), avg=$('bp20-avg');
    if(steps)steps.onchange=()=>{localStorage.setItem('bp20.pyramid.steps',steps.value);localStorage.setItem('bp20.pyramid.step','1');renderCommandCenter();};
    if(step)step.onchange=()=>{localStorage.setItem('bp20.pyramid.step',step.value);renderCommandCenter();};
    if(avg)avg.onchange=()=>{localStorage.setItem('bp20.pyramid.avg',avg.value);};
  }
  function renderTopInsights(){
    const smart=$('sec-smartbet'); if(!smart || $('bp20-insights'))return;
    const top=sigs().slice().sort((a,b)=>scoreOf(b)-scoreOf(a)).filter(s=>insightFor(s)).slice(0,3);
    const div=document.createElement('div');div.id='bp20-insights';div.className='bp20-root';
    div.innerHTML=`<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">🧠 AI Reasoning — Top Picks</div><div class="bp20-sub">o propoziție clară pentru decizie rapidă</div></div><span class="bp20-pill">5 secunde</span></div><div class="bp20-list">${top.length?top.map(x=>pickCard(x,'score')).join(''):'<div class="bp20-empty">Insight-urile apar după rularea workflow-ului.</div>'}</div></div>`;
    const anchor=$('sb-body')||smart.lastElementChild;smart.insertBefore(div,anchor);
  }
  function patchSigCard(){
    if(typeof window.sigCard!=='function' || window.sigCard.__bp20)return;
    const original=window.sigCard;
    window.sigCard=function(sig){
      let html=original.apply(this,arguments);
      const extra=badgesFor(sig)+(insightFor(sig)?`<div class="bp20-insight">${esc(insightFor(sig))}</div>`:'');
      html=html.replace('<div class="md-open-row">', extra+'<div class="md-open-row">');
      html=html.replace('<div class="sig-score-lbl">SmartBet</div>','<div class="sig-score-lbl">Signal</div>');
      return html;
    };
    window.sigCard.__bp20=true;
  }
  let timer=null;
  function renderSoon(){clearTimeout(timer);timer=setTimeout(()=>{patchSigCard();renderCommandCenter();renderTopInsights();},180);}
  async function init(){
    await loadData().catch(()=>{});
    patchSigCard(); renderCommandCenter(); renderTopInsights();
    const mo=new MutationObserver(renderSoon);
    ['dash-body','sb-body','sec-dash','sec-smartbet'].forEach(id=>{const el=$(id); if(el)mo.observe(el,{childList:true,subtree:false});});
    const oldGo=window.go;
    if(typeof oldGo==='function' && !oldGo.__bp20){window.go=function(){const r=oldGo.apply(this,arguments);renderSoon();return r};window.go.__bp20=true;}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
