/* BETPREDICT 2.0 — CLV, Pyramid Assistant, AI Insight, Market Value, Heatmap */
(function(){
  'use strict';
  const API={clv:null,pyramid:null,insights:null,alerts:null,heatmap:null,signals:null};
  const PYR_KEY='bp20.pyramid.sessions.v2';
  const PYR_ACTIVE_KEY='bp20.pyramid.activeId.v2';
  const PYR_LEGS_KEY='bp20.pyramid.legs';
  const BP20_PICK_CACHE={};
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const num=(v)=>{if(v===null||v===undefined||v==='')return null;const n=Number(v);return Number.isFinite(n)?n:null};
  const nf=(v,d=1)=>{const n=num(v);return n!==null?n.toFixed(d):'—'};
  const money=v=>{const n=num(v);return n!==null?`${n.toFixed(2).replace('.',',')} lei`:'—'};
  const pct=v=>{const n=num(v);return n!==null?`${n>=0?'+':''}${n.toFixed(1)}%`:'—'};
  const prob=v=>{const n=Number(v);return Number.isFinite(n)?`${n.toFixed(1)}%`:'—'};
  const dateTime=iso=>{try{if(!iso)return'—';const d=new Date(iso);if(isNaN(d))return'—';return d.toLocaleDateString('ro-RO',{day:'2-digit',month:'2-digit'})+' · '+d.toLocaleTimeString('ro-RO',{hour:'2-digit',minute:'2-digit'});}catch{return'—'}};
  const fetchJ=p=>fetch(p+'?bp20='+Date.now(),{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status));
  const scoreOf=s=>Number(s?.display_score??s?.market_signal_score??s?.pyramid_ready_score??s?.smartbet_score_v6??s?.smartbet_score??0)||0;
  const sigs=()=>API.signals?.signals||[];
  const insightFor=s=>s.ai_insight || API.insights?.by_signal?.[`${s.event_id}|${s.market}`]?.insight || '';
  function compactInsight(raw,s={}){
    const t=String(raw||'').replace(/\s+/g,' ').trim();
    if(!t)return '';
    let clean=t.replace(/^Recomandăm\s+[^.]+?\s+deoarece\s+/i,'').replace(/^Recomandăm\s+/i,'');
    clean=clean.replace(/;?\s+iar\s+/gi,' · ').replace(/,\s+iar\s+/gi,' · ');
    const parts=clean.split(/\s*[·;]\s*/).map(x=>x.trim()).filter(Boolean);
    const reason=(parts[0]||clean).replace(/\.$/,'');
    const riskPart=parts.find(x=>/risc|absen|accident|meteo|gazon|lineup|volatil|probabil|incert/i.test(x));
    const risk=(riskPart&&riskPart!==reason?riskPart:'fără abatere majoră semnalată');
    const market=esc(s.market_label||s.market||'selecția');
    return `<b>Motiv:</b> ${esc(reason)}<br><b>Risc:</b> ${esc(risk)}<br><b>Verdict:</b> ${market} rămâne eligibilă la cota afișată.`;
  }
  const clvFor=s=>{
    const eid=String(s.event_id||''), mk=String(s.market||'').toLowerCase().replace(/_/g,'');
    const by=API.clv?.by_event_market||{};
    for(const [k,v] of Object.entries(by)){if(k.startsWith(eid+'|') && k.toLowerCase().replace(/_/g,'').includes(mk))return v;}
    return null;
  };
  function badgeClass(v){const n=Number(v);return Number.isFinite(n)?(n>0?'good':n<0?'bad':'warn'):'warn'}
  function clvBadge(s){
    const row=clvFor(s)||{};
    const reliable=Boolean(s.clv_reliable||row.clv_reliable);
    const v=s.clv_beat_pct??(reliable?row.clv_pct:null);
    if(!reliable || v===null || v===undefined || v==='')return `<span class="bp20-badge warn">${esc(s.clv_badge||'CLV Tracking')}</span>`;
    return `<span class="bp20-badge ${badgeClass(v)}">${Number(v)>=0?'CLV Beat':'CLV Risk'} ${pct(v)}</span>`;
  }
  function pyramidBadge(s){const v=Number(s.pyramid_ready_score||0);return v?`<span class="bp20-badge ${v>=75?'good':'warn'}">Pyramid ${nf(v,0)}/100</span>`:'';}
  function liveBadge(s){return s.live_value_label?`<span class="bp20-badge good">${esc(s.live_value_label)} · EV ${pct(s.live_value_ev_pct)}</span>`:'';}
  function insightBadge(s){return insightFor(s)?`<span class="bp20-badge good">AI Insight</span>`:'';}
  function badgesFor(s){return `<div class="bp20-badges">${clvBadge(s)}${pyramidBadge(s)}${liveBadge(s)}${insightBadge(s)}</div>`;}


  function jsArg(v){return JSON.stringify(String(v??''));}
  function pickKey(s){return `${s?.event_id||s?.id||''}|${String(s?.market||s?.market_label||'').toLowerCase()}`;}
  function clampInt(v,min,max,def){const n=parseInt(v,10);return Number.isFinite(n)?Math.max(min,Math.min(max,n)):def;}
  function maxLegs(){return clampInt(localStorage.getItem(PYR_LEGS_KEY)||1,1,3,1);}
  function getSessions(){try{const v=JSON.parse(localStorage.getItem(PYR_KEY)||'[]');return Array.isArray(v)?v:[]}catch{return []}}
  function saveSessions(arr){localStorage.setItem(PYR_KEY,JSON.stringify((arr||[]).slice(-30)));}
  function activeSession(){
    const id=localStorage.getItem(PYR_ACTIVE_KEY); if(!id)return null;
    return getSessions().find(s=>String(s.id)===String(id))||null;
  }
  function upsertSession(sess){
    const arr=getSessions(); const i=arr.findIndex(s=>String(s.id)===String(sess.id));
    if(i>=0)arr[i]=sess; else arr.push(sess);
    saveSessions(arr); localStorage.setItem(PYR_ACTIVE_KEY,String(sess.id));
  }
  function pendingSelections(sess){return (sess?.selections||[]).filter(x=>x.status==='PENDING')||[];}
  function pendingSelection(sess){return pendingSelections(sess)[0]||null;}
  function currentStepPending(sess){
    const step=Number(sess?.current_step||localStorage.getItem('bp20.pyramid.step')||1);
    return pendingSelections(sess).filter(x=>Number(x.step)===step);
  }
  function samePick(a,b){return String(a?.key||`${a?.event_id||''}|${a?.market||''}`)===String(b||'');}
  function combinedOdds(rows){return (rows||[]).reduce((acc,x)=>acc*(Number(x.odds)||1),1);}
  function calcStake(sess){return Number(sess?.current_stake??sess?.base_stake??localStorage.getItem('bp20.pyramid.stake')??10)||10;}
  function stepWinCount(sess){
    if(Number.isFinite(Number(sess?.completed_steps)))return Number(sess.completed_steps)||0;
    const won=new Set((sess?.selections||[]).filter(x=>x.status==='WIN').map(x=>String(x.step)));
    return won.size;
  }
  function compactPick(s,step,stake){
    const odds=Number(s.odds??s.market_odds??s.best_odds??0)||0;
    const key=pickKey(s);
    return {
      key,
      step:Number(step)||1,
      status:'PENDING',
      selected_at:new Date().toISOString(),
      event_id:s.event_id||s.id||'',
      home_team:s.home_team||'', away_team:s.away_team||'', league:s.league||'', event_date:s.event_date||'',
      market:s.market||'', market_label:s.market_label||s.market||'', adj_prob:s.adj_prob??null,
      odds:odds||null, stake:Number(stake)||0, potential_return:odds?((Number(stake)||0)*odds):0,
      score:scoreOf(s), pyramid_ready_score:Number(s.pyramid_ready_score||0)||0,
      insight:insightFor(s)||''
    };
  }
  function sessionStatusLabel(sess){
    const m={active:'ACTIVĂ',completed:'FINALIZATĂ',lost:'PIERDUTĂ',cashout:'CASHOUT',cancelled:'ANULATĂ'};
    return m[sess?.status]||'—';
  }
  function renderSelectionLine(x){
    const cls=x.status==='WIN'?'good':x.status==='LOST'?'bad':x.status==='CASHOUT'?'warn':x.status==='VOID'?'warn':'info';
    return `<div class="bp20-session-line"><div><b>Pas ${esc(x.step)}</b> · ${esc(x.home_team)} vs ${esc(x.away_team)}<small>${dateTime(x.event_date)} · ${esc(x.market_label)} · @${esc(x.odds??'—')}</small></div><span class="${cls}">${esc(x.status)}</span></div>`;
  }
  function renderActivePyramid(){
    const sess=activeSession();
    const legs=maxLegs();
    if(!sess || ['cancelled'].includes(sess.status)){
      return `<div class="bp20-session bp20-session-empty"><div class="bp20-session-head"><div><b>Piramidă activă</b><small>Alege 1-${legs} evenimente din lista de mai jos pentru Pasul curent. Cota totală se calculează automat.</small></div><span class="bp20-session-pill">Local</span></div></div>`;
    }
    const selections=(sess.selections||[]).slice().sort((a,b)=>Number(a.step)-Number(b.step)||String(a.selected_at||'').localeCompare(String(b.selected_at||'')));
    const pend=currentStepPending(sess);
    const stake=calcStake(sess);
    const combo=combinedOdds(pend);
    const expected=pend.length?(stake*combo):stake;
    const winCount=stepWinCount(sess);
    const progress=Math.min(100,Math.max(0,winCount/Math.max(1,Number(sess.steps)||1)*100));
    const maxL=Number(sess.max_legs||legs)||1;
    const pendingInfo=pend.length?` · ${pend.length}/${maxL} evenimente · cotă totală @${combo.toFixed(2)}`:'';
    const hint=(sess.status==='active'&&pend.length>0&&pend.length<maxL)?`<div class="bp20-session-hint">Mai poți adăuga ${maxL-pend.length} eveniment(e) pe același pas sau poți valida biletul acum.</div>`:'';
    return `<div class="bp20-session"><div class="bp20-session-head"><div><b>Piramida activă</b><small>Pas ${esc(sess.current_step)}/${esc(sess.steps)} · ${esc(sessionStatusLabel(sess))}${pendingInfo}</small></div><span class="bp20-session-pill">${esc(sess.status==='active'?'În lucru':sessionStatusLabel(sess))}</span></div><div class="bp20-session-grid"><div><b>${money(stake)}</b><small>Miză curentă</small></div><div><b>@${pend.length?combo.toFixed(2):'—'}</b><small>Cotă pas</small></div><div><b>${money(expected)}</b><small>Retur estimat</small></div></div><div class="bp20-progress mini"><i style="width:${progress}%"></i></div>${selections.length?`<div class="bp20-session-lines">${selections.map(renderSelectionLine).join('')}</div>`:''}${hint}${pend.length?`<div class="bp20-session-actions"><button type="button" class="bp20-action win" data-bp20-settle="WIN">✅ WIN PAS</button><button type="button" class="bp20-action lost" data-bp20-settle="LOST">❌ LOST PAS</button><button type="button" class="bp20-action cash" data-bp20-settle="CASHOUT">💰 CASHOUT</button><button type="button" class="bp20-action void" data-bp20-settle="VOID">↩ VOID</button></div>`:''}${sess.status!=='active'?`<div class="bp20-session-actions"><button type="button" class="bp20-action" data-bp20-reset="1">Start piramidă nouă</button></div>`:`<div class="bp20-session-actions subtle"><button type="button" class="bp20-action" data-bp20-reset="1">Reset sesiune</button></div>`}</div>`;
  }

  window.bp20ChoosePyramid=function(key){
    const pick=BP20_PICK_CACHE[String(key)];
    if(!pick){alert('Nu găsesc evenimentul. Fă refresh complet și încearcă din nou.');return;}
    let sess=activeSession();
    const steps=Number(localStorage.getItem('bp20.pyramid.steps')||5);
    const uiStep=Number(localStorage.getItem('bp20.pyramid.step')||1);
    const avg=Number(localStorage.getItem('bp20.pyramid.avg')||1.30);
    const base=Number(localStorage.getItem('bp20.pyramid.stake')||10);
    const legs=maxLegs();
    if(!sess || sess.status!=='active'){
      sess={id:Date.now(),created_at:new Date().toISOString(),status:'active',steps,target_avg:avg,base_stake:base,current_stake:base,current_step:uiStep,max_legs:legs,completed_steps:0,selections:[]};
    }
    sess.max_legs=Number(sess.max_legs||legs)||legs;
    const pend=currentStepPending(sess);
    if(pend.some(x=>samePick(x,key))){alert('Evenimentul este deja selectat pentru pasul curent.');return;}
    if(pend.length>=Number(sess.max_legs||1)){
      alert(`Ai atins limita de ${sess.max_legs} eveniment(e) pentru acest pas. Validează biletul sau folosește VOID/Reset.`);
      return;
    }
    const stake=calcStake(sess);
    sess.selections=sess.selections||[];
    sess.selections.push(compactPick(pick,sess.current_step,stake));
    sess.updated_at=new Date().toISOString();
    upsertSession(sess);
    localStorage.setItem('bp20.pyramid.step',String(sess.current_step));
    renderCommandCenter();
  };

  window.bp20SettlePyramid=function(status){
    const sess=activeSession(); if(!sess){alert('Nu există piramidă activă.');return;}
    const pend=currentStepPending(sess); if(!pend.length){alert('Nu există evenimente în așteptare de validat.');return;}
    const st=String(status||'').toUpperCase();
    const now=new Date().toISOString();
    const stake=calcStake(sess);
    const combo=combinedOdds(pend);
    const stepReturn=stake*combo;
    pend.forEach((x,i)=>{x.settled_at=now; x.combined_odds=combo; x.step_leg_count=pend.length; x.step_stake=stake; x.step_return_amount=i===0?stepReturn:0;});
    if(st==='WIN'){
      pend.forEach(x=>{x.status='WIN'; x.return_amount=0;});
      sess.completed_steps=(Number(sess.completed_steps)||0)+1;
      sess.current_stake=stepReturn;
      if(Number(sess.current_step)>=Number(sess.steps)){sess.status='completed';}
      else{sess.current_step=Number(sess.current_step)+1; localStorage.setItem('bp20.pyramid.step',String(sess.current_step));}
    }else if(st==='LOST'){
      pend.forEach(x=>{x.status='LOST'; x.return_amount=0;});
      sess.status='lost';
    }else if(st==='VOID'){
      pend.forEach(x=>{x.status='VOID'; x.return_amount=0;});
      sess.current_stake=stake;
    }else if(st==='CASHOUT'){
      const raw=prompt('Suma cashout în lei:', String(stepReturn.toFixed(2)));
      if(raw===null)return;
      const val=Number(String(raw).replace(',','.'));
      if(!Number.isFinite(val)||val<0){alert('Sumă invalidă.');return;}
      pend.forEach((x,i)=>{x.status='CASHOUT'; x.return_amount=i===0?val:0;});
      sess.cashout_amount=val; sess.status='cashout';
    }
    sess.updated_at=now;
    upsertSession(sess); renderCommandCenter();
  };

  window.bp20ResetPyramid=function(){
    const sess=activeSession();
    if(sess && sess.status==='active'){
      const ok=confirm('Sigur resetezi piramida activă? Sesiunea va rămâne în istoric local ca anulată.');
      if(!ok)return;
      sess.status='cancelled'; sess.updated_at=new Date().toISOString(); upsertSession(sess);
    }
    localStorage.removeItem(PYR_ACTIVE_KEY); localStorage.setItem('bp20.pyramid.step','1'); renderCommandCenter();
  };

  function bindPyramidActions(){
    if(window.__bp20PyramidActionsBound)return;
    window.__bp20PyramidActionsBound=true;
    document.addEventListener('click',ev=>{
      const choose=ev.target.closest('[data-bp20-choose]');
      if(choose){ev.preventDefault();ev.stopPropagation();if(!choose.disabled)window.bp20ChoosePyramid(choose.getAttribute('data-bp20-choose'));return;}
      const settle=ev.target.closest('[data-bp20-settle]');
      if(settle){ev.preventDefault();ev.stopPropagation();window.bp20SettlePyramid(settle.getAttribute('data-bp20-settle'));return;}
      const reset=ev.target.closest('[data-bp20-reset]');
      if(reset){ev.preventDefault();ev.stopPropagation();window.bp20ResetPyramid();}
    },true);
  }

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
    const reliable=num(r.reliable_n??s.reliable_n)??0, rate=num(r.market_beat_rate??s.market_beat_rate), avg=num(r.avg_clv_pct??s.avg_clv_pct);
    const sample=num(r.total_picks??s.total_picks??s.tracked_open)??0;
    const label=reliable>=20?'MARKET BEAT':'TRACKING';
    const showMetrics=reliable>=20;
    const k1=showMetrics&&rate!==null?nf(rate,0)+'%':'Tracking';
    const k2=showMetrics&&avg!==null?pct(avg):`${reliable} reliable`;
    const k3=showMetrics?String(reliable):`${sample} sample`;
    return `<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">📈 CLV Validation</div><div class="bp20-sub">autoritate matematică: cota publicată vs closing line</div></div><span class="bp20-pill">${label}</span></div><div class="bp20-grid"><div class="bp20-kpi"><div class="bp20-kv ${showMetrics&&rate>=70?'bp20-klv':'bp20-kwarn'}">${k1}</div><div class="bp20-kl">Market Beat</div></div><div class="bp20-kpi"><div class="bp20-kv ${showMetrics&&avg>=0?'bp20-klv':'bp20-kwarn'}">${k2}</div><div class="bp20-kl">Avg CLV</div></div><div class="bp20-kpi"><div class="bp20-kv">${k3}</div><div class="bp20-kl">Reliable</div></div></div><div class="bp20-row"><div class="bp20-note">${reliable<20?'CLV este în modul Tracking: acumulăm linii de închidere. Nu îl folosim ca dovadă finală până nu există minimum 20 linii reliable.':'Sample suficient pentru citirea Market Beat Rate.'}</div></div></div>`;
  }
  function currentPyramidList(step){
    const pool=API.pyramid?.current_step_pool||{}; return (pool[String(step)]||[]).slice(0,5);
  }
  function pickCard(s,mode='pyramid'){
    const insight=compactInsight(insightFor(s),s);
    let action='';
    if(mode==='pyramid'){
      const key=pickKey(s); BP20_PICK_CACHE[key]=s;
      const sess=activeSession();
      const pend=currentStepPending(sess);
      const maxL=Number(sess?.max_legs||maxLegs())||1;
      const already=pend.some(x=>samePick(x,key));
      const full=pend.length>=maxL;
      const label=already?'Selectat':(full?'Limită atinsă':(maxL>1&&pend.length?'Adaugă la pas':'Alege pentru pas'));
      action=`<div class="bp20-pick-actions"><button type="button" class="bp20-choose ${already?'is-selected':''}" data-bp20-choose="${esc(key)}" ${already||full?'disabled':''}>${label}</button></div>`;
    }
    return `<div class="bp20-pick"><div><div class="bp20-match">${esc(s.home_team)} vs ${esc(s.away_team)}</div><div class="bp20-meta">${dateTime(s.event_date)} · ${esc(s.league||'—')}</div><div class="bp20-rec">${esc(s.market_label||s.market)} · ${prob(s.adj_prob)} · @${esc(s.odds??'—')}</div>${insight?`<div class="bp20-insight">${insight}</div>`:''}${badgesFor(s)}${action}</div><div class="bp20-score">${nf(mode==='pyramid'?s.pyramid_ready_score:scoreOf(s),0)}<small>${mode==='pyramid'?'ready':'score'}</small></div></div>`;
  }
  function renderPyramid(){
    const sess=activeSession();
    const storedSteps=Number(localStorage.getItem('bp20.pyramid.steps')||5);
    const steps=sess&&sess.status==='active'?Number(sess.steps||storedSteps):storedSteps;
    const step=sess&&sess.status==='active'?Number(sess.current_step||1):Number(localStorage.getItem('bp20.pyramid.step')||1);
    const avg=Number(localStorage.getItem('bp20.pyramid.avg')||(sess?.target_avg)||1.30);
    const stake=Number(localStorage.getItem('bp20.pyramid.stake')||(sess?.base_stake)||10);
    const legs=Number(localStorage.getItem(PYR_LEGS_KEY)||(sess?.max_legs)||1);
    const list=currentPyramidList(step);
    const progress=Math.min(100,Math.max(0,(step-1)/Math.max(1,steps)*100));
    return `<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">🧱 Pyramid Assistant</div><div class="bp20-sub">alegi 1-3 evenimente → blochezi pasul → validezi biletul ca WIN/LOST</div></div><span class="bp20-pill">Pas ${step}/${steps}</span></div><div class="bp20-form bp20-form-pyramid"><div class="bp20-field"><label>Pași</label><select id="bp20-steps"><option ${steps===3?'selected':''}>3</option><option ${steps===5?'selected':''}>5</option><option ${steps===7?'selected':''}>7</option></select></div><div class="bp20-field"><label>Pas curent</label><select id="bp20-step">${Array.from({length:Math.max(steps,7)},(_,i)=>i+1).filter(x=>x<=steps).map(x=>`<option ${x===step?'selected':''}>${x}</option>`).join('')}</select></div><div class="bp20-field"><label>Evenimente/pas</label><select id="bp20-legs"><option value="1" ${legs===1?'selected':''}>1</option><option value="2" ${legs===2?'selected':''}>2</option><option value="3" ${legs===3?'selected':''}>3</option></select></div><div class="bp20-field"><label>Cotă medie</label><input id="bp20-avg" type="number" step="0.01" value="${avg.toFixed(2)}"></div><div class="bp20-field"><label>Miză inițială</label><input id="bp20-stake" type="number" step="1" value="${stake.toFixed(0)}"></div></div><div class="bp20-progress"><i style="width:${progress}%"></i></div>${renderActivePyramid()}<div class="bp20-list bp20-reco-list">${list.length?list.map(x=>pickCard(x,'pyramid')).join(''):'<div class="bp20-empty">Nu există opțiuni suficient de stabile pentru pasul ales.</div>'}</div></div>`;
  }
  function renderAlerts(){
    const arr=(API.alerts?.alerts||[]).slice(0,3);
    return `<div class="bp20-card bp20-alert"><div class="bp20-head"><div><div class="bp20-title">🚨 Market Value Alert</div><div class="bp20-sub">cota curentă vs fair odd calculat de AI</div></div><span class="bp20-pill">${arr.length?'VALUE':'WATCH'}</span></div><div class="bp20-list">${arr.length?arr.map(a=>`<div class="bp20-pick"><div><div class="bp20-match">${esc(a.home_team)} vs ${esc(a.away_team)}</div><div class="bp20-meta">${dateTime(a.event_date)} · ${esc(a.league||'—')} · ${esc(a.bookmaker||'—')} · fair ${esc(a.fair_odd)} · curent ${esc(a.current_odds)}</div><div class="bp20-rec">${esc(a.label)} · ${esc(a.market_label)} · EV ${pct(a.current_ev_pct)}</div></div><div class="bp20-score">${pct(a.discrepancy_pct)}<small>gap</small></div></div>`).join(''):'<div class="bp20-empty">Nicio discrepanță de piață cu EV pozitiv acum.</div>'}</div></div>`;
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
    const steps=$('bp20-steps'), step=$('bp20-step'), avg=$('bp20-avg'), stake=$('bp20-stake'), legs=$('bp20-legs');
    const canChangeActive=()=>{const ses=activeSession();return !ses || ses.status!=='active' || currentStepPending(ses).length===0;};
    if(steps)steps.onchange=()=>{localStorage.setItem('bp20.pyramid.steps',steps.value);const ses=activeSession();if(ses&&ses.status==='active'&&canChangeActive()){ses.steps=Number(steps.value)||ses.steps;ses.current_step=Math.min(Number(ses.current_step)||1,ses.steps);upsertSession(ses);}else{localStorage.setItem('bp20.pyramid.step','1');}renderCommandCenter();};
    if(step)step.onchange=()=>{localStorage.setItem('bp20.pyramid.step',step.value);const ses=activeSession();if(ses&&ses.status==='active'&&canChangeActive()){ses.current_step=Number(step.value)||ses.current_step;upsertSession(ses);}renderCommandCenter();};
    if(legs)legs.onchange=()=>{localStorage.setItem(PYR_LEGS_KEY,legs.value);const ses=activeSession();if(ses&&ses.status==='active'&&canChangeActive()){ses.max_legs=Number(legs.value)||1;upsertSession(ses);}renderCommandCenter();};
    if(avg)avg.onchange=()=>{localStorage.setItem('bp20.pyramid.avg',avg.value);const ses=activeSession();if(ses&&ses.status==='active'&&canChangeActive()){ses.target_avg=Number(avg.value)||ses.target_avg;upsertSession(ses);}};
    if(stake)stake.onchange=()=>{localStorage.setItem('bp20.pyramid.stake',stake.value||'10');const ses=activeSession();if(ses&&ses.status==='active'&&!(ses.selections||[]).length){ses.base_stake=Number(stake.value)||ses.base_stake;ses.current_stake=ses.base_stake;upsertSession(ses);renderCommandCenter();}};
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
    bindPyramidActions();
    await loadData().catch(()=>{});
    patchSigCard(); renderCommandCenter(); renderTopInsights();
    const mo=new MutationObserver(renderSoon);
    ['dash-body','sb-body','sec-dash','sec-smartbet'].forEach(id=>{const el=$(id); if(el)mo.observe(el,{childList:true,subtree:false});});
    const oldGo=window.go;
    if(typeof oldGo==='function' && !oldGo.__bp20){window.go=function(){const r=oldGo.apply(this,arguments);renderSoon();return r};window.go.__bp20=true;}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
