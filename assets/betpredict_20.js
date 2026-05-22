/* BETPREDICT 2.0 — CLV, Pyramid Assistant, AI Insight, Market Value, Heatmap */
(function(){
  'use strict';
  const API={clv:null,pyramid:null,insights:null,alerts:null,heatmap:null,signals:null};
  const PYR_KEY='bp20.pyramid.sessions.v1';
  const PYR_ACTIVE_KEY='bp20.pyramid.activeId';
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
  function pickKey(s){return `${s?.event_id||''}|${String(s?.market||'').toLowerCase()}`;}
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
  function pendingSelection(sess){return (sess?.selections||[]).find(x=>x.status==='PENDING')||null;}
  function stepSelection(sess,step){return (sess?.selections||[]).find(x=>Number(x.step)===Number(step)&&x.status==='PENDING')||null;}
  function calcStake(sess){
    const pend=pendingSelection(sess); if(pend)return Number(pend.stake)||Number(sess.base_stake)||10;
    const done=(sess?.selections||[]).filter(x=>x.status==='WIN').sort((a,b)=>Number(a.step)-Number(b.step));
    const last=done[done.length-1];
    if(last)return Number(last.return_amount)||((Number(last.stake)||0)*(Number(last.odds)||1));
    return Number(sess?.base_stake)||10;
  }
  function compactPick(s,step,stake){
    const odds=Number(s.odds??s.market_odds??s.best_odds??0)||0;
    return {
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
    if(!sess || ['cancelled'].includes(sess.status)){
      return `<div class="bp20-session bp20-session-empty"><div class="bp20-session-head"><div><b>Piramidă activă</b><small>Alege un eveniment din lista de mai jos pentru a bloca Pasul curent.</small></div><span class="bp20-session-pill">Local</span></div></div>`;
    }
    const selections=(sess.selections||[]).slice().sort((a,b)=>Number(a.step)-Number(b.step));
    const pend=pendingSelection(sess);
    const stake=calcStake(sess);
    const winCount=selections.filter(x=>x.status==='WIN').length;
    const totalReturn=selections.reduce((a,x)=>a+(Number(x.return_amount)||0),0);
    const expected=pend?(Number(pend.potential_return)||0):stake;
    const progress=Math.min(100,Math.max(0,winCount/Math.max(1,Number(sess.steps)||1)*100));
    return `<div class="bp20-session"><div class="bp20-session-head"><div><b>Piramida activă</b><small>Pas ${esc(sess.current_step)}/${esc(sess.steps)} · ${esc(sessionStatusLabel(sess))}</small></div><span class="bp20-session-pill">${esc(sess.status==='active'?'În lucru':sessionStatusLabel(sess))}</span></div><div class="bp20-session-grid"><div><b>${money(stake)}</b><small>Miză curentă</small></div><div><b>${money(expected)}</b><small>Retur estimat</small></div><div><b>${winCount}/${esc(sess.steps)}</b><small>Pași câștigați</small></div></div><div class="bp20-progress mini"><i style="width:${progress}%"></i></div>${selections.length?`<div class="bp20-session-lines">${selections.map(renderSelectionLine).join('')}</div>`:''}${pend?`<div class="bp20-session-actions"><button class="bp20-action win" onclick="window.bp20SettlePyramid('WIN')">✅ WIN</button><button class="bp20-action lost" onclick="window.bp20SettlePyramid('LOST')">❌ LOST</button><button class="bp20-action cash" onclick="window.bp20SettlePyramid('CASHOUT')">💰 CASHOUT</button><button class="bp20-action void" onclick="window.bp20SettlePyramid('VOID')">↩ VOID</button></div>`:''}${sess.status!=='active'?`<div class="bp20-session-actions"><button class="bp20-action" onclick="window.bp20ResetPyramid()">Start piramidă nouă</button></div>`:`<div class="bp20-session-actions subtle"><button class="bp20-action" onclick="window.bp20ResetPyramid()">Reset sesiune</button></div>`}</div>`;
  }

  window.bp20ChoosePyramid=function(key){
    const pick=BP20_PICK_CACHE[String(key)];
    if(!pick){alert('Nu găsesc evenimentul. Fă refresh și încearcă din nou.');return;}
    let sess=activeSession();
    const steps=Number(localStorage.getItem('bp20.pyramid.steps')||5);
    const uiStep=Number(localStorage.getItem('bp20.pyramid.step')||1);
    const avg=Number(localStorage.getItem('bp20.pyramid.avg')||1.30);
    const base=Number(localStorage.getItem('bp20.pyramid.stake')||10);
    if(!sess || sess.status!=='active'){
      sess={id:Date.now(),created_at:new Date().toISOString(),status:'active',steps,target_avg:avg,base_stake:base,current_step:uiStep,selections:[]};
    }
    const pend=pendingSelection(sess);
    if(pend){
      const ok=confirm('Ai deja un eveniment în așteptare pe piramida activă. Îl înlocuim cu acesta?');
      if(!ok)return;
      sess.selections=(sess.selections||[]).filter(x=>x.status!=='PENDING');
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
    const pend=pendingSelection(sess); if(!pend){alert('Nu există eveniment în așteptare de validat.');return;}
    const st=String(status||'').toUpperCase();
    pend.settled_at=new Date().toISOString();
    if(st==='WIN'){
      pend.status='WIN'; pend.return_amount=(Number(pend.stake)||0)*(Number(pend.odds)||1);
      if(Number(pend.step)>=Number(sess.steps)){sess.status='completed';}
      else{sess.current_step=Number(pend.step)+1; localStorage.setItem('bp20.pyramid.step',String(sess.current_step));}
    }else if(st==='LOST'){
      pend.status='LOST'; pend.return_amount=0; sess.status='lost';
    }else if(st==='VOID'){
      pend.status='VOID'; pend.return_amount=Number(pend.stake)||0;
    }else if(st==='CASHOUT'){
      const raw=prompt('Suma cashout în lei:', String((Number(pend.potential_return)||0).toFixed(2)));
      if(raw===null)return;
      const val=Number(String(raw).replace(',','.'));
      if(!Number.isFinite(val)||val<0){alert('Sumă invalidă.');return;}
      pend.status='CASHOUT'; pend.return_amount=val; sess.status='cashout';
    }
    sess.updated_at=new Date().toISOString();
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
      const sess=activeSession(); const pend=pendingSelection(sess);
      const label=pend?'Schimbă pick-ul':'Alege pentru pas';
      action=`<div class="bp20-pick-actions"><button class="bp20-choose" onclick="window.bp20ChoosePyramid(${jsArg(key)})">${label}</button></div>`;
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
    const list=currentPyramidList(step);
    const progress=Math.min(100,Math.max(0,(step-1)/Math.max(1,steps)*100));
    return `<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">🧱 Pyramid Assistant</div><div class="bp20-sub">alegi → blochezi → validezi WIN/LOST → treci la pasul următor</div></div><span class="bp20-pill">Pas ${step}/${steps}</span></div><div class="bp20-form"><div class="bp20-field"><label>Pași</label><select id="bp20-steps"><option ${steps===3?'selected':''}>3</option><option ${steps===5?'selected':''}>5</option><option ${steps===7?'selected':''}>7</option></select></div><div class="bp20-field"><label>Pas curent</label><select id="bp20-step">${Array.from({length:Math.max(steps,7)},(_,i)=>i+1).filter(x=>x<=steps).map(x=>`<option ${x===step?'selected':''}>${x}</option>`).join('')}</select></div><div class="bp20-field"><label>Cotă medie</label><input id="bp20-avg" type="number" step="0.01" value="${avg.toFixed(2)}"></div><div class="bp20-field"><label>Miză inițială</label><input id="bp20-stake" type="number" step="1" value="${stake.toFixed(0)}"></div></div><div class="bp20-progress"><i style="width:${progress}%"></i></div>${renderActivePyramid()}<div class="bp20-list bp20-reco-list">${list.length?list.map(x=>pickCard(x,'pyramid')).join(''):'<div class="bp20-empty">Nu există opțiuni suficient de stabile pentru pasul ales.</div>'}</div></div>`;
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
    const steps=$('bp20-steps'), step=$('bp20-step'), avg=$('bp20-avg'), stake=$('bp20-stake');
    if(steps)steps.onchange=()=>{localStorage.setItem('bp20.pyramid.steps',steps.value);const ses=activeSession();if(ses&&ses.status==='active'&&!pendingSelection(ses)){ses.steps=Number(steps.value)||ses.steps;ses.current_step=Math.min(Number(ses.current_step)||1,ses.steps);upsertSession(ses);}else{localStorage.setItem('bp20.pyramid.step','1');}renderCommandCenter();};
    if(step)step.onchange=()=>{localStorage.setItem('bp20.pyramid.step',step.value);const ses=activeSession();if(ses&&ses.status==='active'&&!pendingSelection(ses)){ses.current_step=Number(step.value)||ses.current_step;upsertSession(ses);}renderCommandCenter();};
    if(avg)avg.onchange=()=>{localStorage.setItem('bp20.pyramid.avg',avg.value);const ses=activeSession();if(ses&&ses.status==='active'&&!pendingSelection(ses)){ses.target_avg=Number(avg.value)||ses.target_avg;upsertSession(ses);}};
    if(stake)stake.onchange=()=>{localStorage.setItem('bp20.pyramid.stake',stake.value||'10');const ses=activeSession();if(ses&&ses.status==='active'&&!(ses.selections||[]).length){ses.base_stake=Number(stake.value)||ses.base_stake;upsertSession(ses);renderCommandCenter();}};
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
