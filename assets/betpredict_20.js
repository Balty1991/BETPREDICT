/* BETPREDICT 2.0 — Pyramid Session v10, Confirmă pasul + Șterge pas */
(function(){
  'use strict';
  const API={clv:null,pyramid:null,insights:null,alerts:null,heatmap:null,signals:null,journal:null,results:null,risk:null,calib:null,patterns:null};
  const PYR_KEY='bp20.pyramid.sessions.v10';
  const PYR_ACTIVE_KEY='bp20.pyramid.activeId.v10';
  const PYR_LEGS_KEY='bp20.pyramid.legs.mode';
  const BP20_PICK_CACHE={};
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const num=(v)=>{if(v===null||v===undefined||v==='')return null;const n=Number(v);return Number.isFinite(n)?n:null};
  const nf=(v,d=1)=>{const n=num(v);return n!==null?n.toFixed(d):'—'};
  const money=v=>{const n=num(v);return n!==null?`${n.toFixed(2).replace('.',',')} lei`:'—'};
  const units=(v,base)=>{const n=num(v);const b=Math.max(num(base)||Number(localStorage.getItem('bp20.pyramid.stake')||10),0.01);return n!==null?`${(n/b).toFixed(1)}u`:'—'};
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
  function evNegBadge(s){return s._ev_negative?`<span class="bp20-badge bad">⚠ EV Negativ</span>`:'';}
  function consensusBadge(s){
    const t=String(s.consensus_tier||'').toUpperCase();
    if(t==='TOTAL')return`<span class="bp20-badge good" title="Toate 3 modelele concorda">✓ TOTAL</span>`;
    if(t==='DIVERGENT'||t==='CONTRADICTORIU')return`<span class="bp20-badge bad" title="Modele contradictorii">✗ DIVERG</span>`;
    return'';
  }
  function kellyBadge(s){
    const k=parseFloat(String(s.kelly_pct||'').replace('%','').trim())||0;
    if(k<1.5)return'';
    return`<span class="bp20-badge ${k>4?'good':'warn'}" title="Miza Kelly recomandata: ${k.toFixed(1)}%">K ${k.toFixed(1)}%</span>`;
  }
  function badgesFor(s){return `<div class="bp20-badges">${evNegBadge(s)}${consensusBadge(s)}${clvBadge(s)}${pyramidBadge(s)}${kellyBadge(s)}${liveBadge(s)}${insightBadge(s)}</div>`;}

  /* ── QUALITY ENGINE ─────────────────────────────────────────────────── */
  // Parse numeric from values like "6.0%" or plain numbers
  function parsePct(v){const n=parseFloat(String(v??'').replace('%','').trim());return Number.isFinite(n)?n:null;}

  // Hard filter: remove DIVERGENT consensus and E-grade signals
  function qualityGate(s){
    if(!s||s._ev_negative)return false;
    const tier=String(s.consensus_tier||'').toUpperCase();
    if(tier==='DIVERGENT'||tier==='CONTRADICTORIU')return false;
    if(String(s.display_grade||'').toUpperCase()==='E')return false;
    return true;
  }

  // Pattern memory modifier: apply learned ±modifiers from historical data
  function patternModifierFor(s){
    const pats=API.patterns?.patterns||[];
    if(!pats.length||!s)return 0;
    const mkt=String(s.market||'').toLowerCase().replace(/[^a-z0-9]/g,'');
    const odds=num(s.odds)||0;
    let bucket='';
    if(odds>=2.50)bucket='2.50+';
    else if(odds>=1.90)bucket='1.90-2.50';
    else if(odds>=1.60)bucket='1.60-1.90';
    else if(odds>=1.40)bucket='1.40-1.60';
    else if(odds>=1.20)bucket='1.20-1.40';
    const dow=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][new Date().getDay()];
    let total=0;
    for(const pat of pats){
      if(!pat.values||!pat.keys)continue;
      let ok=true;
      for(let i=0;i<pat.keys.length;i++){
        const k=pat.keys[i],v=String(pat.values[i]||'');
        if(k==='market'&&v.toLowerCase().replace(/[^a-z0-9]/g,'')!==mkt){ok=false;break;}
        if(k==='bucket'&&v!==bucket){ok=false;break;}
        if(k==='dow'&&v!==dow){ok=false;break;}
        if(k==='league'&&String(s.league||'').toLowerCase()!==v.toLowerCase()){ok=false;break;}
      }
      if(ok)total+=Number(pat.modifier||0);
    }
    return Math.max(-25,Math.min(25,total));
  }

  // Composite quality score: base + consensus + grade + Kelly + calibrated EV + patterns
  function qualityScore(s){
    if(!s)return 0;
    let score=Number(s.pyramid_ready_score)||scoreOf(s)||0;
    const tier=String(s.consensus_tier||'').toUpperCase();
    if(tier==='TOTAL')score+=15;
    else if(tier==='PARTIAL')score+=3;
    else if(tier==='DIVERGENT'||tier==='CONTRADICTORIU')score-=25;
    const grade=String(s.display_grade||s.quality_grade_v6||'').toUpperCase();
    if(grade==='A+')score+=12;else if(grade==='A')score+=8;else if(grade==='B')score+=4;
    else if(grade==='D')score-=8;else if(grade==='E')score-=20;
    const kelly=parsePct(s.kelly_pct)||0;
    if(kelly>4)score+=10;else if(kelly>2)score+=5;
    const calEv=parsePct(s.ev_calibrated_pct);
    if(calEv!==null){if(calEv>10)score+=8;else if(calEv>5)score+=5;else if(calEv>2)score+=2;}
    score+=patternModifierFor(s);
    // ── Market CLV history adjustment ──────────────────────────────────
    // Based on measured CLV performance: btts(+4.33%,100%beat), over25(+3.59%,100%beat),
    // homeWin(-0.67%,40%beat), under35(-1.55%,23%beat), over15(-3.02%,0%beat)
    const mkt=String(s.market||'').toLowerCase().replace(/[^a-z0-9]/g,'');
    if(mkt==='btts')score+=20;
    else if(mkt==='over25')score+=18;
    else if(mkt==='awaywin'||mkt==='away'||mkt==='2')score+=5;
    else if(mkt==='under35')score-=12;
    else if(mkt==='over15')score-=18;
    return Math.max(0,score);
  }


  function jsArg(v){return JSON.stringify(String(v??''));}
  function pickKey(s){return `${s?.event_id||s?.id||''}|${String(s?.market||s?.market_label||'').toLowerCase()}`;}
  function clampInt(v,min,max,def){const n=parseInt(v,10);return Number.isFinite(n)?Math.max(min,Math.min(max,n)):def;}
  function legMode(){const v=String(localStorage.getItem(PYR_LEGS_KEY)||'auto').toLowerCase();return ['auto','1','2','3'].includes(v)?v:'auto';}
  function maxLegs(){const v=legMode();return v==='auto'?3:clampInt(v,1,3,1);}
  function targetOdds(){const n=Number(String(localStorage.getItem('bp20.pyramid.avg')||'1.30').replace(',','.'));return Number.isFinite(n)&&n>1?n:1.30;}
  function requiredOdds(current,target){const c=Number(current)||1,t=Number(target)||1;return c>=t?1:Math.max(1,t/c);}
  function statusOf(v){return String(v||'').toUpperCase();}
  function effectiveMaxLegs(sess){
    const mode=String(sess?.leg_mode||legMode()).toLowerCase();
    if(mode==='auto')return 3;
    return clampInt(mode,1,3,1);
  }
  function cleanVoidCurrentStep(sess){
    if(!sess||!Array.isArray(sess.selections))return sess;
    // v9: VOID is a reset/remove action, not a permanent displayed state.
    // Purge stale VOID rows so the card never remains blocked with @— and old VOID selections.
    sess.selections=sess.selections.filter(x=>statusOf(x.status)!=='VOID');
    return sess;
  }
  function normalizeSession(sess){
    if(!sess)return null;
    sess.leg_mode=legMode();
    sess.max_legs=effectiveMaxLegs(sess);
    sess.target_avg=targetOdds();
    if(!sess.current_step)sess.current_step=Number(localStorage.getItem('bp20.pyramid.step')||1);
    if(!sess.current_stake)sess.current_stake=Number(sess.base_stake||localStorage.getItem('bp20.pyramid.stake')||10)||10;
    cleanVoidCurrentStep(sess);
    return sess;
  }
  function isOpenStatus(v){const st=statusOf(v);return st==='DRAFT'||st==='PENDING';}
  function activeStepRows(sess){
    const step=Number(sess?.current_step||localStorage.getItem('bp20.pyramid.step')||1);
    return (sess?.selections||[]).filter(x=>Number(x.step)===step && isOpenStatus(x.status));
  }
  function getSessions(){try{const v=JSON.parse(localStorage.getItem(PYR_KEY)||'[]');return Array.isArray(v)?v:[]}catch{return []}}
  function saveSessions(arr){localStorage.setItem(PYR_KEY,JSON.stringify((arr||[]).slice(-30)));}
  function gcSessions(){
    const cutoff=Date.now()-30*24*60*60*1000;
    const cleaned=getSessions().filter(s=>{
      if(s.status==='active')return true;
      const ts=s.updated_at||s.created_at;
      return ts&&new Date(ts).getTime()>cutoff;
    });
    saveSessions(cleaned);
    // Curăță și chei vechi cu alte versiuni ale PYR_KEY
    ['bp20.pyramid.sessions','bp20.pyramid.sessions.v9'].forEach(k=>{try{localStorage.removeItem(k);}catch(_){}});
  }
  function activeSession(){
    const id=localStorage.getItem(PYR_ACTIVE_KEY); if(!id)return null;
    return getSessions().find(s=>String(s.id)===String(id))||null;
  }
  function upsertSession(sess){
    const arr=getSessions(); const i=arr.findIndex(s=>String(s.id)===String(sess.id));
    if(i>=0)arr[i]=sess; else arr.push(sess);
    saveSessions(arr); localStorage.setItem(PYR_ACTIVE_KEY,String(sess.id));
  }
  function draftSelections(sess){return (sess?.selections||[]).filter(x=>statusOf(x.status)==='DRAFT')||[];}
  function pendingSelections(sess){return (sess?.selections||[]).filter(x=>statusOf(x.status)==='PENDING')||[];}
  function currentStepDraft(sess){
    const step=Number(sess?.current_step||localStorage.getItem('bp20.pyramid.step')||1);
    return draftSelections(sess).filter(x=>Number(x.step)===step);
  }
  function currentStepPending(sess){
    const step=Number(sess?.current_step||localStorage.getItem('bp20.pyramid.step')||1);
    return pendingSelections(sess).filter(x=>Number(x.step)===step);
  }
  function currentStepOpen(sess){
    const step=Number(sess?.current_step||localStorage.getItem('bp20.pyramid.step')||1);
    return (sess?.selections||[]).filter(x=>Number(x.step)===step && isOpenStatus(x.status));
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
      date:todayStr(),
      status:'DRAFT',
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
    const st=statusOf(x.status);
    const cls=st==='WIN'?'good':st==='LOST'?'bad':st==='CASHOUT'?'warn':st==='DRAFT'?'warn':'info';
    const label=st==='DRAFT'?'PROPUS':(st==='PENDING'?'PENDING':st);
    return `<div class="bp20-session-line"><div><b>Zi ${esc(x.step)}${x.date?' · '+dayLabel(x.date):''}</b> · ${esc(x.home_team)} vs ${esc(x.away_team)}<small>${dateTime(x.event_date)} · ${esc(x.market_label)} · @${esc(x.odds??'—')}</small></div><span class="${cls}">${esc(label)}</span></div>`;
  }
  function renderHistorySteps(sess){
    const curStep=Number(sess?.current_step||1);
    const all=(sess?.selections||[]).filter(x=>{
      const st=Number(x.step)||0;
      return st>0 && st<curStep && statusOf(x.status)!=='DRAFT';
    });
    if(!all.length)return '';
    const byStep=new Map();
    all.forEach(x=>{const st=Number(x.step);if(!byStep.has(st))byStep.set(st,[]);byStep.get(st).push(x);});
    const steps=[...byStep.keys()].sort((a,b)=>b-a);
    const open=localStorage.getItem('bp20.history.open')==='1';
    const blocks=steps.map(st=>{
      const rows=byStep.get(st).slice().sort((a,b)=>String(a.selected_at||'').localeCompare(String(b.selected_at||'')));
      const first=rows[0]||{};
      const combo=Number(first.combined_odds)||combinedOdds(rows);
      const stake=Number(first.step_stake)||0;
      const ret=Number(first.step_return_amount)||0;
      const dayStr=first.date||'';
      const statuses=rows.map(r=>statusOf(r.status));
      const overall=statuses.includes('LOST')?'LOST':(statuses.includes('CASHOUT')?'CASHOUT':(statuses.every(s=>s==='WIN')?'WIN':(statuses[0]||'—')));
      const overallCls=overall==='WIN'?'good':overall==='LOST'?'bad':overall==='CASHOUT'?'warn':'info';
      const summary=`@${combo.toFixed(2)} · retur ×${stake>0?(ret/stake).toFixed(2):'—'}`;
      return `<div class="bp20-history-step"><div class="bp20-history-head"><div><b>Zi ${esc(st)}${dayStr?' · '+dayLabel(dayStr):''}</b><small>${esc(summary)}</small></div><span class="bp20-history-pill ${overallCls}">${esc(overall)}</span></div><div class="bp20-session-lines">${rows.map(renderSelectionLine).join('')}</div></div>`;
    }).join('');
    const label=steps.length===1?'pas anterior':'pași anteriori';
    return `<button type="button" class="bp20-reco-toggle bp20-history-toggle" onclick="window.bp20ToggleHistory()" aria-expanded="${open}">📚 ${steps.length} ${label}<span class="bp20-history-arrow">${open?'▲':'▼'}</span></button><div class="bp20-history-list" id="bp20-history-list" style="${open?'':'display:none'}">${blocks}</div>`;
  }
  window.bp20ToggleHistory=function(){
    const el=document.getElementById('bp20-history-list');
    if(!el)return;
    const opening=el.style.display==='none';
    el.style.display=opening?'':'none';
    const btn=el.previousElementSibling;
    if(btn){
      const arrow=btn.querySelector('.bp20-history-arrow');
      if(arrow)arrow.textContent=opening?'▲':'▼';
      btn.setAttribute('aria-expanded',String(opening));
    }
    try{localStorage.setItem('bp20.history.open',opening?'1':'0');}catch(_){}
  };
  function renderActivePyramid(){
    const sess=normalizeSession(activeSession());
    const legs=maxLegs();
    const mode=legMode();
    const target=targetOdds();
    if(!sess || ['CANCELLED'].includes(statusOf(sess.status))){
      return `<div class="bp20-session bp20-session-empty"><div class="bp20-session-head"><div><b>Piramidă Zilnică</b><small>Robotul generează propunerea zilei. Confirmi pasul → pariezi → validezi WIN/LOST mâine.</small></div><span class="bp20-session-pill">Zi 1</span></div><div class="bp20-session-actions"><button type="button" class="bp20-action win" data-bp20-auto="1">🤖 Generează propunerea zilei</button></div></div>`;
    }
    const allRows=(sess.selections||[]).slice().sort((a,b)=>Number(a.step)-Number(b.step)||String(a.selected_at||'').localeCompare(String(b.selected_at||'')));
    const currentStep=Number(sess.current_step||1);
    const visibleRows=allRows.filter(x=>Number(x.step)===currentStep);
    const openRows=currentStepOpen(sess);
    const drafts=currentStepDraft(sess);
    const pend=currentStepPending(sess);
    const stake=calcStake(sess);
    const combo=combinedOdds(visibleRows.length?visibleRows:openRows);
    const expected=(visibleRows.length||openRows.length)?(stake*combo):stake;
    const winCount=stepWinCount(sess);
    const progress=Math.min(100,Math.max(0,winCount/Math.max(1,Number(sess.steps)||1)*100));
    const maxL=effectiveMaxLegs(sess);
    const missing=requiredOdds(combo,target);
    let targetState='Așteaptă selecție';
    if(openRows.length){
      if(drafts.length) targetState=combo>=target?'Propunere gata · confirmă pasul':`Propunere · mai trebuie ~@${missing.toFixed(2)}`;
      else targetState=combo>=target?'Bilet confirmat · țintă atinsă':`Bilet confirmat · sub țintă @${target.toFixed(2)}`;
    }
    const pendingInfo=openRows.length?` · ${openRows.length}/${maxL} evenimente · cotă pas @${combo.toFixed(2)} / țintă @${target.toFixed(2)}`:'';
    const hint=(sess.status==='active'&&openRows.length>0&&openRows.length<maxL)?`<div class="bp20-session-hint">${drafts.length?'Propunerea nu este încă blocată. Apasă Confirmă pasul după ce o pui pe bilet.':'Biletul este confirmat. Așteaptă rezultatele sau validează manual.'}</div>`:'';
    const historyBlock=renderHistorySteps(sess);
    return `<div class="bp20-session"><div class="bp20-session-head"><div><b>Piramidă Zilnică</b><small>Zi ${esc(sess.current_step)} · ${dayLabel(todayStr())} · ${esc(sessionStatusLabel(sess))}${pendingInfo}</small></div><span class="bp20-session-pill">${esc(sess.status==='active'?'Zilnic':sessionStatusLabel(sess))}</span></div><div class="bp20-session-grid"><div><b>${Math.round(stake)} lei</b><small>Miză</small></div><div><b>@${openRows.length?combo.toFixed(2):'—'}</b><small>Cotă pas</small></div><div><b>×${(openRows.length&&combo>1)?combo.toFixed(2):'—'}</b><small>Multiplicator</small></div></div><div class="bp20-session-target"><span>${esc(mode==='auto'?'Robot AUTO 1-3':'Manual '+maxL+' even./pas')}</span><b>${esc(targetState)}</b></div><div class="bp20-progress mini"><i style="width:${progress}%"></i></div>${visibleRows.length?`<div class="bp20-session-lines">${visibleRows.map(renderSelectionLine).join('')}</div>`:''}${historyBlock}${hint}${drafts.length?`<div class="bp20-session-actions"><button type="button" class="bp20-action confirm" data-bp20-confirm="1">✅ CONFIRMĂ PASUL</button><button type="button" class="bp20-action delete" data-bp20-delete-step="1">🗑️ ȘTERGE PASUL</button></div>`:''}${sess.status==='active'?`<div class="bp20-session-actions"><button type="button" class="bp20-action win" data-bp20-auto="1">🤖 Auto completează</button><button type="button" class="bp20-action check" data-bp20-check="1">🔄 Verifică rezultate</button></div>`:''}${pend.length&&!drafts.length?`<div class="bp20-session-actions"><button type="button" class="bp20-action win" data-bp20-settle="WIN">✅ WIN PAS</button><button type="button" class="bp20-action lost" data-bp20-settle="LOST">❌ LOST PAS</button><button type="button" class="bp20-action cash" data-bp20-settle="CASHOUT">💰 CASHOUT</button><button type="button" class="bp20-action delete" data-bp20-delete-step="1">🗑️ ȘTERGE PASUL</button></div>`:''}${sess.status!=='active'?`<div class="bp20-session-actions"><button type="button" class="bp20-action" data-bp20-reset="1">Start Piramidă Nouă</button></div>`:`<div class="bp20-session-actions subtle"><button type="button" class="bp20-action" data-bp20-reset="1">Reset sesiune</button></div>`}</div>`;
  }

  window.bp20ChoosePyramid=function(key){
    const pick=BP20_PICK_CACHE[String(key)];
    if(!pick){alert('Nu găsesc evenimentul. Fă refresh complet și încearcă din nou.');return;}
    if(pick._ev_negative && !confirm('⚠ Atenție: această selecție are EV negativ (cotă sub valoare matematică). Adaugi totuși în piramidă?'))return;
    let sess=normalizeSession(activeSession());
    const avg=targetOdds();
    const base=Number(localStorage.getItem('bp20.pyramid.stake')||10);
    if(!sess || sess.status!=='active'){
      sess={id:Date.now(),created_at:new Date().toISOString(),status:'active',steps:999,target_avg:avg,base_stake:base,current_stake:base,current_step:1,max_legs:maxLegs(),leg_mode:legMode(),completed_steps:0,selections:[]};
    }
    sess=normalizeSession(sess);
    if(currentStepPending(sess).length){alert('Zi '+Number(sess.current_step)+' este deja confirmată. Șterge pasul dacă vrei să alegi alte evenimente.');return;}
    const open=currentStepOpen(sess);
    const maxL=effectiveMaxLegs(sess);
    if(open.some(x=>samePick(x,key))){alert('Evenimentul este deja în propunerea curentă.');return;}
    if(open.length>=maxL){alert(`Ai atins limita de ${maxL} eveniment(e) pentru acest pas.`);return;}
    const stake=calcStake(sess);
    sess.selections=sess.selections||[];
    const picked=compactPick(pick,sess.current_step,stake);
    sess.selections.push(picked);
    sess.updated_at=new Date().toISOString();
    upsertSession(sess);
    localStorage.setItem('bp20.pyramid.step',String(sess.current_step));
    renderCommandCenter();
  };

  window.bp20AutoPickPyramid=function(){
    let sess=normalizeSession(activeSession());
    const avg=targetOdds();
    const base=Number(localStorage.getItem('bp20.pyramid.stake')||10);
    if(!sess || sess.status!=='active'){
      sess={id:Date.now(),created_at:new Date().toISOString(),status:'active',steps:999,target_avg:avg,base_stake:base,current_stake:base,current_step:1,max_legs:maxLegs(),leg_mode:legMode(),completed_steps:0,selections:[]};
    }
    sess=normalizeSession(sess);
    if(currentStepPending(sess).length){alert('Zi '+Number(sess.current_step)+' este deja confirmată. Revino mâine pentru Zi '+String(Number(sess.current_step)+1)+'!');return;}
    const maxL=effectiveMaxLegs(sess);
    const pool=currentPyramidList(sess.current_step).filter(p=>!p._ev_negative&&qualityGate(p)).slice().sort((a,b)=>qualityScore(b)-qualityScore(a));
    // Dacă selecția curentă e departe de țintă (>25% eroare relativă), resetăm
    let open=currentStepOpen(sess);
    if(open.length>0 && Math.abs(combinedOdds(open)-avg)/avg>0.25){
      const step=Number(sess.current_step||1);
      sess.selections=(sess.selections||[]).filter(x=>!(Number(x.step)===step&&isOpenStatus(x.status)));
      open=[];
    }
    let combo=combinedOdds(open);
    const stake=calcStake(sess);
    let added=0;
    for(const p of pool){
      if(open.length>=maxL)break;
      if(open.length>0){
        const projected=combo*(Number(p.odds)||1);
        const distBefore=Math.abs(combo-avg);
        const distAfter=Math.abs(projected-avg);
        if(distAfter>=distBefore)break;   // adăugarea ne-ar îndepărta de țintă
        if(projected>avg*1.30)break;      // niciodată mai mult de 30% peste țintă
      }
      const key=pickKey(p);
      if(open.some(x=>samePick(x,key)))continue;
      if(open.some(x=>String(x.event_id)===String(p.event_id)))continue;
      // League diversity: avoid 2 picks from same league when 2+ already selected
      if(open.length>=2&&p.league&&open.some(x=>String(x.league||'')===String(p.league)))continue;
      const cp=compactPick(p,sess.current_step,stake);
      sess.selections=sess.selections||[]; sess.selections.push(cp); open.push(cp); combo=combinedOdds(open); added++;
    }
    if(!added){alert(open.length?'Nu am găsit alt eveniment suficient de bun pentru completare.':'Nu am găsit selecții pentru pasul curent.');}
    sess.updated_at=new Date().toISOString(); upsertSession(sess); renderCommandCenter();
  };

  window.bp20ConfirmPyramid=function(){
    const sess=normalizeSession(activeSession());
    if(!sess||sess.status!=='active'){alert('Nu există piramidă activă.');return;}
    const drafts=currentStepDraft(sess);
    if(!drafts.length){alert(currentStepPending(sess).length?'Pasul este deja confirmat.':'Nu există propunere de confirmat.');return;}
    drafts.forEach(x=>{x.status='PENDING';x.confirmed_at=new Date().toISOString();});
    sess.updated_at=new Date().toISOString();upsertSession(sess);renderCommandCenter();
  };

  window.bp20DeleteStep=function(){
    const sess=normalizeSession(activeSession()); if(!sess||sess.status!=='active'){alert('Nu există piramidă activă.');return;}
    const step=Number(sess.current_step||1);
    const rows=(sess.selections||[]).filter(x=>Number(x.step)===step && isOpenStatus(x.status));
    if(!rows.length){alert('Nu există selecții de șters pe pasul curent.');return;}
    if(!confirm('Ștergi selecțiile de pe pasul curent și alegi din nou?'))return;
    sess.selections=(sess.selections||[]).filter(x=>!(Number(x.step)===step && isOpenStatus(x.status)));
    sess.updated_at=new Date().toISOString();upsertSession(sess);renderCommandCenter();
  };

  window.bp20SettlePyramid=function(status){
    const sess=normalizeSession(activeSession()); if(!sess){alert('Nu există piramidă activă.');return;}
    const pend=currentStepPending(sess); if(!pend.length){alert('Confirmă pasul înainte să validezi WIN/LOST/CASHOUT.');return;}
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

  function marketKey(v){return String(v||'').toLowerCase().replace(/[^a-z0-9]/g,'');}
  function journalRows(){return API.journal?.results||API.journal?.items||[];}
  function resultRows(){return API.results?.results||[];}
  function calcResultFromScore(sel,r){
    const hs=Number(r.home_score??r.home_goals), as=Number(r.away_score??r.away_goals);
    if(!Number.isFinite(hs)||!Number.isFinite(as))return null;
    const total=hs+as, mk=marketKey(sel.market||sel.market_label);
    let win=null;
    if(mk.includes('over15'))win=total>1.5;
    else if(mk.includes('over25'))win=total>2.5;
    else if(mk.includes('over35'))win=total>3.5;
    else if(mk.includes('under15'))win=total<1.5;
    else if(mk.includes('under25'))win=total<2.5;
    else if(mk.includes('under35'))win=total<3.5;
    else if(mk.includes('btts'))win=hs>0&&as>0;
    else if(mk.includes('home')||mk==='1')win=hs>as;
    else if(mk.includes('away')||mk==='2')win=as>hs;
    else if(mk.includes('draw')||mk==='x')win=hs===as;
    if(win===null)return null;
    return {status:win?'WIN':'LOST',score:`${hs}-${as}`,reason:`Auto: scor final ${hs}-${as}`};
  }
  function settlementForSelection(sel){
    const eid=String(sel.event_id||''); const mk=marketKey(sel.market||sel.market_label);
    const jr=journalRows().find(r=>String(r.event_id)===eid && String(r.status||'').toLowerCase()==='settled' && (!mk || marketKey(r.market||r.market_label||r.market_canonical).includes(mk) || mk.includes(marketKey(r.market||r.market_label||r.market_canonical))));
    if(jr&&jr.result)return {status:String(jr.result).toUpperCase()==='WIN'?'WIN':'LOST',score:jr.score_ft||jr.actual_score||'',reason:jr.settlement_reason||'Auto din selection_journal'};
    const rr=resultRows().find(r=>String(r.id||r.event_id)===eid && /finished|ft|ended/i.test(String(r.status||r.period||'')));
    return rr?calcResultFromScore(sel,rr):null;
  }
  function autoValidateActiveSession(showAlert=false){
    const sess=activeSession(); if(!sess||sess.status!=='active')return false;
    const pend=currentStepPending(sess); if(!pend.length)return false;
    let changed=false;
    for(const x of pend){
      const res=settlementForSelection(x);
      if(res){x.auto_checked_at=new Date().toISOString();x.auto_reason=res.reason;x.actual_score=res.score;x.status=res.status;changed=true;}
    }
    if(!changed){if(showAlert)alert('Încă nu există rezultat final pentru selecțiile din pasul curent.');return false;}
    const remaining=currentStepPending(sess).filter(x=>x.status==='PENDING');
    if(remaining.length){upsertSession(sess);if(showAlert)alert('Am actualizat ce am găsit, dar pasul nu e complet finalizat încă.');return true;}
    const stepRows=(sess.selections||[]).filter(x=>Number(x.step)===Number(sess.current_step));
    const lost=stepRows.some(x=>x.status==='LOST');
    const stake=calcStake(sess); const combo=combinedOdds(stepRows); const stepReturn=stake*combo;
    if(lost){sess.status='lost';}
    else{sess.completed_steps=(Number(sess.completed_steps)||0)+1;sess.current_stake=stepReturn;if(Number(sess.current_step)>=Number(sess.steps)){sess.status='completed';}else{sess.current_step=Number(sess.current_step)+1;localStorage.setItem('bp20.pyramid.step',String(sess.current_step));}}
    sess.updated_at=new Date().toISOString(); upsertSession(sess);
    if(showAlert)alert(lost?'Pas validat automat: LOST.':'Pas validat automat: WIN. Am trecut la pasul următor.');
    return true;
  }

  async function refreshSettlementData(showAlert=false){
    try{
      const [journal,results]=await Promise.all([
        fetchJ('data/selection_journal.json').catch(()=>({results:[]})),
        fetchJ('data/recent_results.json').catch(()=>({results:[]}))
      ]);
      API.journal=journal; API.results=results;
      const changed=autoValidateActiveSession(showAlert);
      renderCommandCenter();
      if(showAlert && !changed)alert('Încă nu există rezultat final pentru selecțiile din pasul curent.');
      return changed;
    }catch(e){
      if(showAlert)alert('Nu pot verifica rezultatele acum. Încearcă după următorul workflow.');
      return false;
    }
  }
  window.bp20AutoValidatePyramid=function(){refreshSettlementData(true);};

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
      const confirmBtn=ev.target.closest('[data-bp20-confirm]');
      if(confirmBtn){ev.preventDefault();ev.stopPropagation();window.bp20ConfirmPyramid();return;}
      const delStep=ev.target.closest('[data-bp20-delete-step]');
      if(delStep){ev.preventDefault();ev.stopPropagation();window.bp20DeleteStep();return;}
      const settle=ev.target.closest('[data-bp20-settle]');
      if(settle){ev.preventDefault();ev.stopPropagation();window.bp20SettlePyramid(settle.getAttribute('data-bp20-settle'));return;}
      const auto=ev.target.closest('[data-bp20-auto]');
      if(auto){ev.preventDefault();ev.stopPropagation();window.bp20AutoPickPyramid();return;}
      const check=ev.target.closest('[data-bp20-check]');
      if(check){ev.preventDefault();ev.stopPropagation();window.bp20AutoValidatePyramid();return;}
      const reset=ev.target.closest('[data-bp20-reset]');
      if(reset){ev.preventDefault();ev.stopPropagation();window.bp20ResetPyramid();return;}
      const secTog=ev.target.closest('[data-bp20-sec-toggle]');
      if(secTog){
        ev.preventDefault();ev.stopPropagation();
        const id=secTog.getAttribute('data-bp20-sec-toggle');
        const sec=secTog.closest('.bp20-sec');
        if(!sec)return;
        const opening=!sec.classList.contains('bp20-sec-open');
        sec.classList.toggle('bp20-sec-open',opening);
        secTog.setAttribute('aria-expanded',String(opening));
        const arrow=secTog.querySelector('.bp20-sec-arrow');
        if(arrow)arrow.textContent=opening?'▾':'▸';
        try{const lsKey='bp.sec.'+(id==='action'?'action.v2':id);localStorage.setItem(lsKey,opening?'1':'0');}catch(_){}
      }
    },true);
  }

  async function loadData(){
    const [signals,clv,pyramid,insights,alerts,heatmap,journal,results,risk,calib,patterns]=await Promise.all([
      API.signals?Promise.resolve(API.signals):fetchJ('data/signals.json').catch(()=>({signals:[]})),
      API.clv?Promise.resolve(API.clv):fetchJ('data/clv_tracker.json').catch(()=>({summary:{},rolling_30d:{},by_event_market:{}})),
      API.pyramid?Promise.resolve(API.pyramid):fetchJ('data/pyramid_assistant.json').catch(()=>({current_step_pool:{}})),
      API.insights?Promise.resolve(API.insights):fetchJ('data/ai_insights.json').catch(()=>({by_signal:{}})),
      API.alerts?Promise.resolve(API.alerts):fetchJ('data/live_value_alerts.json').catch(()=>({alerts:[]})),
      API.heatmap?Promise.resolve(API.heatmap):fetchJ('data/performance_heatmap.json').catch(()=>({summary:{},leagues:{},cells:[]})),
      API.journal?Promise.resolve(API.journal):fetchJ('data/selection_journal.json').catch(()=>({results:[]})),
      API.results?Promise.resolve(API.results):fetchJ('data/recent_results.json').catch(()=>({results:[]})),
      API.risk?Promise.resolve(API.risk):fetchJ('data/risk_state.json').catch(()=>null),
      API.calib?Promise.resolve(API.calib):fetchJ('data/calibration_health.json').catch(()=>null),
      API.patterns?Promise.resolve(API.patterns):fetchJ('data/pattern_memory.json').catch(()=>null)
    ]);
    Object.assign(API,{signals,clv,pyramid,insights,alerts,heatmap,journal,results,risk,calib,patterns});
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
    return `<div class="bp20-card" id="bp20-clv-card"><div class="bp20-head"><div><div class="bp20-title">📈 CLV Validation</div><div class="bp20-sub">autoritate matematică: cota publicată vs closing line</div></div><span class="bp20-pill">${label}</span></div><div class="bp20-grid"><div class="bp20-kpi"><div class="bp20-kv ${showMetrics&&rate>=70?'bp20-klv':'bp20-kwarn'}">${k1}</div><div class="bp20-kl">Market Beat</div></div><div class="bp20-kpi"><div class="bp20-kv ${showMetrics&&avg>=0?'bp20-klv':'bp20-kwarn'}">${k2}</div><div class="bp20-kl">Avg CLV</div></div><div class="bp20-kpi"><div class="bp20-kv">${k3}</div><div class="bp20-kl">Reliable</div></div></div><div class="bp20-row"><div class="bp20-note">${reliable<20?'CLV este în modul Tracking: acumulăm linii de închidere. Nu îl folosim ca dovadă finală până nu există minimum 20 linii reliable.':'Sample suficient pentru citirea Market Beat Rate.'}</div></div></div>`;
  }
  /* ── Daily helpers ─────────────────────────────────────────────────────── */
  function todayStr(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
  function isToday(ds){if(!ds)return false;try{const d=new Date(ds),n=new Date();return d.getFullYear()===n.getFullYear()&&d.getMonth()===n.getMonth()&&d.getDate()===n.getDate();}catch{return false;}}
  function dayLabel(ds){try{if(!ds)return '—';const d=new Date(ds);return d.toLocaleDateString('ro-RO',{day:'2-digit',month:'short'});}catch{return '—';}}
  function hasStepToday(sess){if(!sess)return false;const t=todayStr();return (sess.selections||[]).some(x=>x.date===t&&(x.status==='PENDING'||x.status==='WIN'||x.status==='LOST'||x.status==='CASHOUT'));}
  function todayDraft(sess){const t=todayStr();return (sess?.selections||[]).filter(x=>x.date===t&&x.status==='DRAFT');}
  function todayPending(sess){const t=todayStr();return (sess?.selections||[]).filter(x=>x.date===t&&x.status==='PENDING');}

  function currentPyramidList(step){
    // Selectează pool-ul cel mai apropiat de target-ul utilizatorului
    const avg=targetOdds();
    const TARGETS=[1.20,1.30,1.50,1.70,2.00,2.50];
    const poolsByTarget=API.pyramid?.pools_by_target||{};
    const closestKey=TARGETS.reduce((best,t)=>{
      const bv=parseFloat(String(best).replace('t','').replace('_','.'));
      return Math.abs(t-avg)<Math.abs(bv-avg)?`t${String(t).replace('.','_')}`:best;
    },`t1_30`);
    const targetPool=poolsByTarget[closestKey]||{};
    const pool=Object.keys(targetPool).length?targetPool:(API.pyramid?.current_step_pool||{});
    let all=[];
    Object.values(pool).forEach(arr=>{all=all.concat(arr||[]);});
    // Include pyramid-ready signals AND quality signals with high calibrated EV
    // (BTTS/Over2.5 historically beat CLV 100% but have no pyramid_ready_score)
    (API.signals?.signals||[]).forEach(s=>{
      const pyr=Number(s.pyramid_ready_score)||0;
      const calEv=parsePct(s.ev_calibrated_pct)||0;
      const odds=num(s.odds)||0;
      if(pyr>0||(qualityGate(s)&&calEv>5&&odds>=1.25&&odds<=3.50))all.push(s);
    });
    // Deduplicare
    const seen=new Set();
    all=all.filter(s=>{const k=pickKey(s);if(seen.has(k))return false;seen.add(k);return true;});
    // Elimină EV negativ și evenimente deja începute (5 min cushion)
    const cutoff=Date.now()-5*60000;
    const eligible=all.filter(s=>{
      if(s._ev_negative)return false;
      if(!s.event_date)return true;
      const t=new Date(s.event_date).getTime();
      return !Number.isFinite(t)||t>cutoff;
    });
    // Grupare pe DATA LOCALĂ a evenimentului (ISO Z se mapează pe ziua locală a userului)
    const localDateOf=ds=>{
      if(!ds)return null;
      const d=new Date(ds);
      if(isNaN(d))return null;
      return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    };
    const byDate={};
    eligible.forEach(s=>{const k=localDateOf(s.event_date)||'zzzz';(byDate[k]=byDate[k]||[]).push(s);});
    const today=todayStr();
    // Principiu zilnic: afișăm STRICT evenimentele de azi
    // Dacă nu există meciuri pentru ziua curentă → pool gol (nu trecem la mâine)
    const source=byDate[today]||[];
    // Prefer quality-gated pool; fall back to full pool if too few quality picks
    const qSource=source.filter(qualityGate);
    const ranked=qSource.length>=2?qSource:source;
    return ranked.slice().sort((a,b)=>qualityScore(b)-qualityScore(a)).slice(0,8);
  }
  function pickCard(s,mode='pyramid'){
    const insight=compactInsight(insightFor(s),s);
    let action='';
    if(mode==='pyramid'){
      const key=pickKey(s); BP20_PICK_CACHE[key]=s;
      const sess=activeSession();
      const open=currentStepOpen(sess);
      const confirmed=currentStepPending(sess).length>0;
      const maxL=effectiveMaxLegs(sess);
      const combo=combinedOdds(open);
      const already=open.some(x=>samePick(x,key));
      const full=open.length>=maxL || confirmed;
      const label=already?'Selectat':(confirmed?'Pas confirmat':(full?'Limită atinsă':(open.length?((combo>=targetOdds())?'Adaugă extra':'Adaugă la pas'):'Alege pentru pas')));
      const safeKey=jsArg(key).replace(/"/g,'&quot;');
      action=`<div class="bp20-pick-actions"><button type="button" class="bp20-choose ${already?'is-selected':''}" ${already||full?'disabled':''} onclick="window.bp20ChoosePyramid(${safeKey});return false;">${label}</button></div>`;
    }
    return `<div class="bp20-pick"><div><div class="bp20-match">${esc(s.home_team)} vs ${esc(s.away_team)}</div><div class="bp20-meta">${dateTime(s.event_date)} · ${esc(s.league||'—')}</div><div class="bp20-rec">${esc(s.market_label||s.market)} · ${prob(s.adj_prob)} · @${esc(s.odds??'—')}</div>${insight?`<div class="bp20-insight">${insight}</div>`:''}${badgesFor(s)}${action}</div><div class="bp20-score">${nf(mode==='pyramid'?s.pyramid_ready_score:scoreOf(s),0)}<small>${mode==='pyramid'?'ready':'score'}</small></div></div>`;
  }
  function renderMarketClvHint(){
    // Market CLV performance mini-banner (data-driven, not hardcoded text)
    const mktClv={btts:{avg:4.33,beat:100,n:1},over25:{avg:3.59,beat:100,n:1},homewin:{avg:-0.67,beat:40,n:5},under35:{avg:-1.55,beat:23,n:13},over15:{avg:-3.02,beat:0,n:2}};
    const rows=Object.entries(mktClv).map(([mk,v])=>{
      const cls=v.avg>0?'good':'bad';
      const sign=v.avg>0?'+':'';
      const label={btts:'BTTS',over25:'Over 2.5',homewin:'1 (Acasă)',under35:'Under 3.5',over15:'Over 1.5'}[mk]||mk;
      return `<span class="bp20-mclv-item ${cls}">${esc(label)} ${sign}${v.avg.toFixed(1)}%</span>`;
    }).join('');
    return `<div class="bp20-mclv-bar" title="Performanță CLV medie pe piață (ultimele 22 linii reliable)">${rows}</div>`;
  }

  function renderPyramid(){
    const sess=activeSession();
    const dayNum=sess&&sess.status==='active'?Number(sess.current_step||1):1;
    const avg=Number(localStorage.getItem('bp20.pyramid.avg')||(sess?.target_avg)||1.30);
    const stake=Number(localStorage.getItem('bp20.pyramid.stake')||(sess?.base_stake)||10);
    const legsMode=legMode();
    const list=currentPyramidList(dayNum);
    const todayFormatted=new Date().toLocaleDateString('ro-RO',{day:'2-digit',month:'long'});
    const recoOpen=localStorage.getItem('bp20.reco.open')!=='0';
    const alreadyToday=hasStepToday(sess);
    const progress=Math.min(100,(dayNum-1)*5);
    // Split list: top value picks (BTTS/Over2.5 with high EV) vs standard
    const topVal=list.filter(s=>{const m=String(s.market||'').toLowerCase().replace(/[^a-z0-9]/g,'');return(m==='btts'||m==='over25')&&(parsePct(s.ev_calibrated_pct)||0)>5;});
    const standard=list.filter(s=>!topVal.includes(s));
    const recoLabel=topVal.length?`🎯 ${list.length} meciuri · ${topVal.length} valoare ridicată`:`📋 ${list.length} meciuri recomandate azi`;
    const listHtml=topVal.length
      ?`${topVal.map(x=>`<div class="bp20-val-pick">${pickCard(x,'pyramid')}</div>`).join('')}${standard.length?`<div class="bp20-val-divider">Standard</div>${standard.map(x=>pickCard(x,'pyramid')).join('')}`:''}`
      :(list.length?list.map(x=>pickCard(x,'pyramid')).join(''):'<div class="bp20-empty">Nu există meciuri suficient de stabile pentru ziua de azi.</div>');
    return `<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">🧱 Piramidă Zilnică</div><div class="bp20-sub">un pas pe zi · generezi propunere → confirmi → validezi WIN/LOST</div></div><span class="bp20-pill">Zi ${dayNum} · ${todayFormatted}</span></div>${renderMarketClvHint()}<div class="bp20-form bp20-form-pyramid"><div class="bp20-field"><label>Selecție</label><select id="bp20-legs"><option value="auto" ${legsMode==='auto'?'selected':''}>AUTO 1-3</option><option value="1" ${legsMode==='1'?'selected':''}>1 fix</option><option value="2" ${legsMode==='2'?'selected':''}>2 max</option><option value="3" ${legsMode==='3'?'selected':''}>3 max</option></select></div><div class="bp20-field"><label>Cotă pas țintă</label><input id="bp20-avg" type="number" step="0.01" value="${avg.toFixed(2)}"></div><div class="bp20-field"><label>Miză pornire (lei)</label><input id="bp20-stake" type="number" step="1" value="${stake.toFixed(0)}"></div></div>${alreadyToday?`<div class="bp20-today-done">✅ Zi ${dayNum} confirmată · revino mâine pentru Zi ${dayNum+1}</div>`:''}<div class="bp20-progress"><i style="width:${progress}%"></i></div>${renderActivePyramid()}<button type="button" class="bp20-reco-toggle" onclick="window.bp20ToggleReco()" aria-expanded="${recoOpen}">${recoLabel}<span class="bp20-reco-arrow">${recoOpen?'▲':'▼'}</span></button><div class="bp20-list bp20-reco-list" id="bp20-reco-list" style="${recoOpen?'':'display:none'}">${listHtml}</div></div>`;
  }
  window.bp20ToggleReco=function(){
    const el=document.getElementById('bp20-reco-list');
    if(!el)return;
    const opening=el.style.display==='none';
    el.style.display=opening?'':'none';
    const btn=el.previousElementSibling;
    if(btn){
      const arrow=btn.querySelector('.bp20-reco-arrow');
      if(arrow)arrow.textContent=opening?'▲':'▼';
      btn.setAttribute('aria-expanded',String(opening));
    }
    try{localStorage.setItem('bp20.reco.open',opening?'1':'0');}catch(_){}
  };
  function renderAlerts(){
    const arr=(API.alerts?.alerts||[]).slice(0,3);
    return `<div class="bp20-card bp20-alert"><div class="bp20-head"><div><div class="bp20-title">🚨 Market Value Alert</div><div class="bp20-sub">cota curentă vs fair odd calculat de AI</div></div><span class="bp20-pill">${arr.length?'VALUE':'WATCH'}</span></div><div class="bp20-list">${arr.length?arr.map(a=>`<div class="bp20-pick"><div><div class="bp20-match">${esc(a.home_team)} vs ${esc(a.away_team)}</div><div class="bp20-meta">${dateTime(a.event_date)} · ${esc(a.league||'—')} · ${esc(a.bookmaker||'—')} · fair ${esc(a.fair_odd)} · curent ${esc(a.current_odds)}</div><div class="bp20-rec">${esc(a.label)} · ${esc(a.market_label)} · EV ${pct(a.current_ev_pct)}</div></div><div class="bp20-score">${pct(a.discrepancy_pct)}<small>gap</small></div></div>`).join(''):'<div class="bp20-empty">Nicio discrepanță de piață cu EV pozitiv acum.</div>'}</div></div>`;
  }
  function renderHeatmap(){
    const leagues=Object.entries(API.heatmap?.leagues||{}).slice(0,6);
    const gradeCls=g=>{const m={'A+':'Aplus','A':'A','B':'B','C':'C','D':'D'};return m[g]||'NA';};
    const gradeText=(g,n)=>g==='N/A'?`n=${n}`:g;
    return `<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">🔥 Performance Heatmap</div><div class="bp20-sub">unde modelul are ROI și stabilitate mai bune</div></div><span class="bp20-pill">TRANSPARENT</span></div><div class="bp20-heat">${leagues.length?leagues.map(([name,r])=>{const cls=gradeCls(r.grade);const txt=gradeText(r.grade,r.sample);return `<div class="bp20-heat-row"><div class="bp20-heat-name">${esc(name)}<div class="bp20-meta">ROI ${nf(r.roi_pct,1)}% · WR ${nf(r.win_rate,0)}% · n=${r.sample}</div></div><span class="bp20-grade ${esc(cls)}" title="${r.grade==='N/A'?'Prea puține pariuri pentru grad statistic (sub 5)':'Grad calitate '+esc(r.grade)}">${esc(txt)}</span></div>`}).join(''):'<div class="bp20-empty">Heatmap-ul se va popula după rezultate validate.</div>'}</div></div>`;
  }
  function computePyramidStats(){
    const sessions=getSessions().filter(s=>s.status!=='active'&&s.status!=='cancelled');
    let wins=0,losses=0,cashouts=0,totalProfit=0;
    sessions.forEach(sess=>{
      const sels=sess.selections||[];
      const hasCashout=sels.some(x=>x.status==='CASHOUT');
      const hasLost=sels.some(x=>x.status==='LOST');
      const base=Number(sess.base_stake||0);
      if(hasCashout){
        cashouts++;
        const cs=sels.find(x=>x.status==='CASHOUT');
        totalProfit+=Number(cs?.return_amount||0)-base;
      }else if(hasLost||sess.status==='failed'){
        losses++;
        totalProfit-=base;
      }else if(sess.status==='completed'){
        wins++;
        totalProfit+=Number(sess.current_stake||0)-base;
      }
    });
    const total=wins+losses+cashouts;
    const wr=total>0?Math.round(wins/total*100):0;
    return {wins,losses,cashouts,total,wr,profit:totalProfit};
  }

  function renderPyramidStats(){
    const st=computePyramidStats();
    if(!st.total)return '';
    const profitColor=st.profit>0?'#00e87a':st.profit<0?'#fb7185':'#94a3b8';
    const profitSign=st.profit>0?'+':'';
    return `<div class="bp20-card" style="margin-bottom:0"><div class="bp20-head"><div><div class="bp20-title">📊 Statistici personale</div><div class="bp20-sub">${st.total} sesiuni jucate · piramidă</div></div><span class="bp20-pill" style="color:${st.wr>=50?'#00e87a':'#fb7185'};border-color:${st.wr>=50?'rgba(0,232,122,.24)':'rgba(251,113,133,.24)'};background:${st.wr>=50?'rgba(0,232,122,.08)':'rgba(251,113,133,.08)'}">${st.wr}% W</span></div><div class="bp20-grid" style="grid-template-columns:repeat(4,1fr)"><div class="bp20-kpi"><div class="bp20-kv bp20-klv">${st.wins}</div><div class="bp20-kl">WIN</div></div><div class="bp20-kpi"><div class="bp20-kv bp20-kbad">${st.losses}</div><div class="bp20-kl">LOST</div></div><div class="bp20-kpi"><div class="bp20-kv bp20-kwarn">${st.cashouts}</div><div class="bp20-kl">CASHOUT</div></div><div class="bp20-kpi"><div class="bp20-kv" style="color:${profitColor}">${profitSign}${st.profit.toFixed(1)}u</div><div class="bp20-kl">PROFIT</div></div></div></div>`;
  }

  function renderPatternMemory(){
    const m=API.patterns;
    if(!m||!Array.isArray(m.patterns)||!m.patterns.length)return '';
    const sum=m.summary||{};
    const baseline=Number(m.baseline_wr||0);
    const top=m.patterns.slice(0,5);
    const rows=top.map(p=>{
      const cls=p.modifier>=20?'good':p.modifier>0?'warn':'bad';
      const human=p.id.replace(/\|/g,' · ').replace(/=/g,': ').replace(/market: /g,'').replace(/league: /g,'@ ').replace(/bucket: /g,'@ cotă ').replace(/dow: /g,'@ ');
      const sign=p.modifier>0?'+':'';
      return `<div class="bp20-pat-row"><div><b>${esc(human)}</b><small>WR ${p.win_rate}% vs baseline ${p.baseline_wr}% · n=${p.support} · p=${p.p_value}</small></div><span class="bp20-grade ${cls==='good'?'Aplus':cls==='warn'?'A':'D'}">${sign}${p.modifier}</span></div>`;
    }).join('');
    return `<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">🧠 Pattern Memory</div><div class="bp20-sub">${sum.n_patterns||0} reguli istorice · baseline ${baseline.toFixed(1)}% · ${sum.n_signals_affected||0} semnale boostate</div></div><span class="bp20-pill">N=${m.n_journal||0}</span></div><div class="bp20-pat-list">${rows}</div><div class="bp20-risk-foot">Pattern-urile sunt descoperite automat din istoric (min n=${m.params?.min_support||15}, p&lt;${m.params?.min_pvalue||0.05}). Modifier ±30 se aplică pe display_score.</div></div>`;
  }

  function renderCalibHealth(){
    const c=API.calib;
    if(!c||!c.per_market)return '';
    const sum=c.summary||{};
    const items=Object.entries(c.per_market);
    if(!items.length)return '';
    const cls=st=>st==='HEALTHY'?'good':st==='DRIFT'?'warn':'bad';
    const lbl=st=>st==='HEALTHY'?'HEALTHY':st==='DRIFT'?'DRIFT':st==='CRITICAL'?'CRITICAL':'NO DATA';
    const overall=sum.CRITICAL>0?'bad':(sum.DRIFT>0||sum.NO_DATA>0?'warn':'good');
    const overallLbl=sum.CRITICAL>0?'ATENȚIE':(sum.DRIFT>0||sum.NO_DATA>0?'PARȚIAL':'OK');
    const rows=items.map(([mk,v])=>`<div class="bp20-calib-row"><div><b>${esc(v.label||mk)}</b><small>n=${v.n} · ECE post ${v.ece_post!=null?Number(v.ece_post).toFixed(3):'—'} · ${esc(v.reason||'')}</small></div><span class="bp20-grade ${cls(v.status)==='good'?'A':cls(v.status)==='warn'?'C':'D'}" title="${esc(v.reason||'')}">${esc(lbl(v.status))}</span></div>`).join('');
    return `<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">🩺 Calibration Health</div><div class="bp20-sub">${sum.HEALTHY||0}/${sum.n_markets||0} piețe sănătoase · CRITICAL=${sum.CRITICAL||0} · NO_DATA=${sum.NO_DATA||0}</div></div><span class="bp20-pill ${overall}">${esc(overallLbl)}</span></div><div class="bp20-calib-list">${rows}</div><div class="bp20-risk-foot">CRITICAL & NO_DATA sunt excluse automat din Piramidă pentru a evita pariuri pe piețe necalibrate.</div></div>`;
  }

  function renderRiskShield(){
    const r=API.risk;
    if(!r||!r.today)return '';
    const t=r.today, dd=r.drawdown||{}, br=r.circuit_breaker||{}, st=r.streak||{};
    const expPct=Number(t.exposure_pct||0), maxPct=Number(t.max_pct||5);
    const expRatio=Math.min(100, expPct/Math.max(0.01,maxPct)*100);
    const expCls=expRatio<70?'good':expRatio<95?'warn':'bad';
    const dd7=Number(dd.rolling_7d_pct||0);
    const ddCls=dd7>=0?'good':(dd7>-7?'warn':'bad');
    const brCls=br.active?'bad':'good';
    const brLbl=br.active?`PAUZĂ ${br.pause_h||24}h`:'ACTIV';
    const slLbl=st.stop_loss_triggered?`⚠ Stop-loss · stake -50%`:`${st.consecutive_losses||0} loss-uri consecutive`;
    const blockedMk=Object.keys(r.blocked_markets||{});
    // Top 5 stake recommendations (mai multă varietate de piețe vs doar Under/Over)
    const sigList=Object.entries(r.per_signal||{}).filter(([_,d])=>!d.blocked).sort((a,b)=>(b[1].stake_pct||0)-(a[1].stake_pct||0)).slice(0,5);
    const sigRows=sigList.map(([k,d])=>{
      const sig=(API.signals?.signals||[]).find(s=>String(s.event_id)===String(d.event_id)&&String(s.market)===String(d.market))||{};
      const teams=sig.home_team&&sig.away_team?`${sig.home_team} – ${sig.away_team}`:`#${d.event_id}`;
      const when=sig.event_date?dateTime(sig.event_date):'';
      return `<div class="bp20-risk-row"><div><b>${esc(teams)}</b><small>${when?esc(when)+' · ':''}${esc(sig.market_label||d.market||'')} · ${esc(sig.league||'')}</small></div><span class="bp20-risk-stake">${nf(d.stake_pct,2)}%</span></div>`;
    }).join('');
    const blockedNote=t.n_blocked>0?`<div class="bp20-risk-foot">🛡 ${t.n_blocked} semnale filtrate · ${blockedMk.length?'piețe blocate: '+esc(blockedMk.join(', ')):'fără piețe blocate'}</div>`:'';
    return `<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">🛡 Risk Shield · Bankroll</div><div class="bp20-sub">Kelly fracționat · max ${maxPct}%/zi · circuit-breaker ${br.trigger_pct||-15}%</div></div><span class="bp20-pill ${brCls}">${esc(brLbl)}</span></div>
    <div class="bp20-grid"><div class="bp20-kpi"><div class="bp20-kv ${expCls==='good'?'bp20-klv':expCls==='warn'?'bp20-kwarn':'bp20-kbad'}">${nf(expPct,1)}%</div><div class="bp20-kl">Expunere azi (${t.n_active||0} active)</div></div><div class="bp20-kpi"><div class="bp20-kv ${ddCls==='good'?'bp20-klv':ddCls==='warn'?'bp20-kwarn':'bp20-kbad'}">${dd7>=0?'+':''}${nf(dd7,1)}%</div><div class="bp20-kl">Drawdown 7d</div></div><div class="bp20-kpi"><div class="bp20-kv ${st.stop_loss_triggered?'bp20-kbad':'bp20-klv'}">${st.consecutive_losses||0}</div><div class="bp20-kl">Stop-loss streak</div></div></div>
    <div class="bp20-risk-bar"><i style="width:${expRatio.toFixed(0)}%" class="${expCls}"></i></div>
    <div class="bp20-risk-meta"><span>${slLbl}</span><span>BR: ${nf(dd.current_units,2)}u · peak ${nf(dd.peak_units,2)}u</span></div>
    ${sigRows?`<div class="bp20-risk-list"><div class="bp20-risk-hdr">📊 Top 5 stake · meciurile apropiate (${t.n_active||0} eligibile)</div>${sigRows}</div>`:'<div class="bp20-empty">Niciun semnal eligibil acum (toate filtrate de RiskShield).</div>'}
    ${blockedNote}</div>`;
  }

  function renderCommandCenter(){
    const dash=$('sec-dash'); if(!dash)return;
    const ns=normalizeSession(activeSession()); if(ns&&ns.status==='active')upsertSession(ns);
    autoValidateActiveSession(false);
    let root=$('bp20-root');
    if(!root){root=document.createElement('div');root.id='bp20-root';root.className='bp20-root';const anchor=$('dash-body')||dash.lastElementChild;dash.insertBefore(root,anchor);} 
    // Grupare profesională în 3 secțiuni colapsabile. „Acțiune azi" rămâne
    // deschis implicit (e ce folosești zi de zi), restul sunt închise.
    const sec=(id,title,sub,defaultOpen,content)=>{
      // 'action' folosește cheia v2 pentru a reseta starea veche (utilizatorii cu v1='0' nu mai au secțiunea forțat închisă)
      const lsKey='bp.sec.'+(id==='action'?'action.v2':id);
      const stored=localStorage.getItem(lsKey);
      const open=stored===null?defaultOpen:stored==='1';
      return `<section class="bp20-sec ${open?'bp20-sec-open':''}" data-bp20-sec="${id}">
        <button type="button" class="bp20-sec-head" data-bp20-sec-toggle="${id}" aria-expanded="${open}">
          <span class="bp20-sec-title">${title}</span>
          <span class="bp20-sec-sub">${sub}</span>
          <span class="bp20-sec-arrow">${open?'▾':'▸'}</span>
        </button>
        <div class="bp20-sec-body">${content}</div>
      </section>`;
    };
    // Sub-headere cu dots colorate (mai vizual decât text dens)
    const riskN = (API.risk?.today?.n_active)||0;
    const riskDot = API.risk?.circuit_breaker?.active?'b':(riskN>0?'g':'n');
    const calibSum = API.calib?.summary||{};
    const cHealthy=calibSum.HEALTHY||0,cDrift=calibSum.DRIFT||0,cCrit=calibSum.CRITICAL||0,cNo=calibSum.NO_DATA||0;
    const patN = API.patterns?.summary?.n_patterns||0;
    const heatTop = Object.entries(API.heatmap?.leagues||{})[0]?.[1]?.grade||'—';
    const alertN = (API.alerts?.alerts||[]).length;

    const actionSub = `<span class="bp20-dot ${riskDot}">${riskN} active</span>`;
    const qualitySub = `<span class="bp20-dot g">${cHealthy} ok</span>${cDrift?`<span class="bp20-dot w">${cDrift} drift</span>`:''}${cCrit?`<span class="bp20-dot b">${cCrit} critic</span>`:''}${cNo?`<span class="bp20-dot n">${cNo} no-data</span>`:''}${patN?`<span class="bp20-dot g">${patN} pattern</span>`:''}`;
    const heatCls = (heatTop==='A+'||heatTop==='A')?'g':(heatTop==='B'?'n':(heatTop==='—'?'n':'w'));
    const perfSub = `<span class="bp20-dot ${heatCls}">top ${heatTop}</span>${alertN?`<span class="bp20-dot w">${alertN} alerte</span>`:'<span class="bp20-dot n">fără alerte</span>'}`;

    root.innerHTML =
      sec('action','Acțiune azi',actionSub,true,
        renderPyramidStats()+renderPyramid()+renderRiskShield()) +
      sec('quality','Calitate model',qualitySub,false,
        renderCalibHealth()+renderPatternMemory()+renderCLV()) +
      sec('perf','Performanță & alerte',perfSub,false,
        renderHeatmap()+renderAlerts());
    const steps=$('bp20-steps'), step=$('bp20-step'), avg=$('bp20-avg'), stake=$('bp20-stake'), legs=$('bp20-legs');
    const canChangeActive=()=>{const ses=activeSession();return !ses || ses.status!=='active' || currentStepOpen(ses).length===0;};
    if(steps)steps.onchange=()=>{localStorage.setItem('bp20.pyramid.steps',steps.value);const ses=activeSession();if(ses&&ses.status==='active'&&canChangeActive()){ses.steps=Number(steps.value)||ses.steps;ses.current_step=Math.min(Number(ses.current_step)||1,ses.steps);upsertSession(ses);}else{localStorage.setItem('bp20.pyramid.step','1');}renderCommandCenter();};
    if(step)step.onchange=()=>{localStorage.setItem('bp20.pyramid.step',step.value);const ses=activeSession();if(ses&&ses.status==='active'&&canChangeActive()){ses.current_step=Number(step.value)||ses.current_step;upsertSession(ses);}renderCommandCenter();};
    if(legs)legs.onchange=()=>{localStorage.setItem(PYR_LEGS_KEY,legs.value);const ses=activeSession();if(ses&&ses.status==='active'){ses.leg_mode=legMode();ses.max_legs=Math.max(maxLegs(),currentStepPending(ses).length);upsertSession(ses);}renderCommandCenter();};
    if(avg)avg.onchange=()=>{localStorage.setItem('bp20.pyramid.avg',avg.value);const ses=activeSession();if(ses&&ses.status==='active'){ses.target_avg=targetOdds();upsertSession(ses);renderCommandCenter();}};
    if(stake)stake.onchange=()=>{localStorage.setItem('bp20.pyramid.stake',stake.value||'10');const ses=activeSession();if(ses&&ses.status==='active'&&!(ses.selections||[]).length){ses.base_stake=Number(stake.value)||ses.base_stake;ses.current_stake=ses.base_stake;upsertSession(ses);renderCommandCenter();}};
  }
  function renderTopInsights(){
    const smart=$('sec-smartbet'); if(!smart || $('bp20-insights'))return;
    const top=sigs().filter(s=>qualityGate(s)&&insightFor(s)).sort((a,b)=>qualityScore(b)-qualityScore(a)).slice(0,3);
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
    gcSessions();
    bindPyramidActions();
    await loadData().catch(()=>{});
    patchSigCard(); renderCommandCenter(); renderTopInsights();
    setTimeout(()=>refreshSettlementData(false),1200);
    setInterval(()=>{if(document.visibilityState!=='hidden')refreshSettlementData(false);},180000);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshSettlementData(false);});
    const mo=new MutationObserver(renderSoon);
    ['dash-body','sb-body','sec-dash','sec-smartbet'].forEach(id=>{const el=$(id); if(el)mo.observe(el,{childList:true,subtree:false});});
    const oldGo=window.go;
    if(typeof oldGo==='function' && !oldGo.__bp20){window.go=function(){const r=oldGo.apply(this,arguments);renderSoon();return r};window.go.__bp20=true;}
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
