/* BETPREDICT 2.0 — Pyramid Session v8: safe VOID + visible pending slip */
(function(){
  'use strict';

  const API={signals:null,clv:null,pyramid:null,insights:null,alerts:null,heatmap:null,journal:null,results:null};
  const PYR_KEY='bp20.pyramid.sessions.v8';
  const PYR_ACTIVE_KEY='bp20.pyramid.activeId.v8';
  const PYR_MODE_KEY='bp20.pyramid.selectMode.v8';
  const PICK_CACHE={};
  let renderTimer=null;
  let lastAction={key:'',ts:0};

  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const num=v=>{if(v===null||v===undefined||v==='')return null; const n=Number(String(v).replace(',','.')); return Number.isFinite(n)?n:null;};
  const nf=(v,d=1)=>{const n=num(v); return n!==null?n.toFixed(d):'—';};
  const pct=v=>{const n=num(v); return n!==null?`${n>=0?'+':''}${n.toFixed(1)}%`:'—';};
  const prob=v=>{const n=num(v); return n!==null?`${n.toFixed(1)}%`:'—';};
  const money=v=>{const n=num(v); return n!==null?`${n.toFixed(2).replace('.',',')} lei`:'—';};
  const fetchJ=p=>fetch(p+'?bp20v8='+Date.now(),{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(new Error(String(r.status))));
  const statusOf=v=>String(v||'PENDING').toUpperCase();
  const scoreOf=s=>Number(s?.display_score??s?.market_signal_score??s?.pyramid_ready_score??s?.smartbet_score_v6??s?.smartbet_score??0)||0;
  const sigs=()=>API.signals?.signals||[];

  function dateTime(iso){
    try{if(!iso)return '—'; const d=new Date(iso); if(isNaN(d))return '—'; return d.toLocaleDateString('ro-RO',{day:'2-digit',month:'2-digit'})+' · '+d.toLocaleTimeString('ro-RO',{hour:'2-digit',minute:'2-digit'});}catch{return '—';}
  }
  function toOdds(v){
    const n=num(v); return n&&n>1?n:null;
  }
  function targetOdds(){
    const n=num(localStorage.getItem('bp20.pyramid.avg')); return n&&n>1?n:1.30;
  }
  function baseStake(){
    const n=num(localStorage.getItem('bp20.pyramid.stake')); return n&&n>0?n:10;
  }
  function stepsCount(){
    const n=parseInt(localStorage.getItem('bp20.pyramid.steps')||'5',10); return [3,5,7].includes(n)?n:5;
  }
  function uiStep(){
    const n=parseInt(localStorage.getItem('bp20.pyramid.step')||'1',10); return Math.max(1,Math.min(7,Number.isFinite(n)?n:1));
  }
  function selectMode(){
    const v=String(localStorage.getItem(PYR_MODE_KEY)||'auto').toLowerCase(); return ['auto','1','2','3'].includes(v)?v:'auto';
  }
  function maxLegsForMode(mode=selectMode()){
    return mode==='auto'?3:Math.max(1,Math.min(3,parseInt(mode,10)||1));
  }
  function combinedOdds(rows){
    return (rows||[]).reduce((acc,x)=>acc*(toOdds(x.odds)||1),1);
  }
  function keyFor(s){
    return `${s?.event_id||s?.id||''}|${String(s?.market||s?.market_label||'').toLowerCase().replace(/\s+/g,'')}`;
  }
  function insightFor(s){
    return s?.ai_insight || API.insights?.by_signal?.[`${s?.event_id}|${s?.market}`]?.insight || '';
  }
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

  function getSessions(){try{const v=JSON.parse(localStorage.getItem(PYR_KEY)||'[]'); return Array.isArray(v)?v:[];}catch{return [];}}
  function saveSessions(arr){localStorage.setItem(PYR_KEY,JSON.stringify((arr||[]).slice(-40)));}
  function activeSession(){
    const id=localStorage.getItem(PYR_ACTIVE_KEY); if(!id)return null;
    return getSessions().find(x=>String(x.id)===String(id))||null;
  }
  function upsertSession(sess){
    const arr=getSessions();
    const i=arr.findIndex(x=>String(x.id)===String(sess.id));
    if(i>=0)arr[i]=sess; else arr.push(sess);
    saveSessions(arr);
    localStorage.setItem(PYR_ACTIVE_KEY,String(sess.id));
  }
  function createSession(){
    const st=baseStake();
    const sess={
      id:Date.now(), created_at:new Date().toISOString(), updated_at:new Date().toISOString(),
      status:'active', steps:stepsCount(), current_step:uiStep(), completed_steps:0,
      target_odds:targetOdds(), base_stake:st, current_stake:st,
      select_mode:selectMode(), max_legs:maxLegsForMode(), selections:[]
    };
    upsertSession(sess);
    return sess;
  }
  function normalizeSession(sess){
    if(!sess)return null;
    sess.status=String(sess.status||'active').toLowerCase();
    sess.steps=Number(sess.steps||stepsCount())||5;
    sess.current_step=Number(sess.current_step||uiStep())||1;
    sess.target_odds=targetOdds();
    sess.select_mode=selectMode();
    sess.max_legs=maxLegsForMode(sess.select_mode);
    sess.base_stake=num(sess.base_stake)||baseStake();
    sess.current_stake=num(sess.current_stake)||sess.base_stake;
    sess.selections=Array.isArray(sess.selections)?sess.selections:[];
    // v8 keeps VOID rows visible, but excludes them from cumulative odds.
    return sess;
  }
  function currentStepRows(sess,includeSettled=true){
    const step=Number(sess?.current_step||uiStep());
    return (sess?.selections||[]).filter(x=>Number(x.step)===step && (includeSettled || statusOf(x.status)==='PENDING'));
  }
  function pendingRows(sess){return currentStepRows(sess,true).filter(x=>statusOf(x.status)==='PENDING');}
  function calcStake(sess){return num(sess?.current_stake) || num(sess?.base_stake) || baseStake();}
  function completedSteps(sess){
    if(Number.isFinite(Number(sess?.completed_steps)))return Number(sess.completed_steps)||0;
    return new Set((sess?.selections||[]).filter(x=>statusOf(x.status)==='WIN').map(x=>String(x.step))).size;
  }
  function stepState(sess){
    const pend=pendingRows(sess);
    const combo=combinedOdds(pend);
    const target=num(sess?.target_odds)||targetOdds();
    const missing=combo>=target?1:(target/(combo||1));
    const hit=pend.length>0 && combo>=target;
    return {pend,combo,target,missing,hit};
  }

  function compactPick(s,sess){
    const odds=toOdds(s.odds??s.market_odds??s.best_odds) || 1;
    return {
      key:keyFor(s), step:Number(sess.current_step)||1, status:'PENDING', selected_at:new Date().toISOString(),
      event_id:s.event_id||s.id||'', home_team:s.home_team||'', away_team:s.away_team||'', league:s.league||'', event_date:s.event_date||'',
      market:s.market||'', market_label:s.market_label||s.market||'', adj_prob:s.adj_prob??null,
      odds, stake:calcStake(sess), score:scoreOf(s), pyramid_ready_score:Number(s.pyramid_ready_score||0)||0,
      insight:insightFor(s)||''
    };
  }
  function findPick(rawKey){
    const key=decodeURIComponent(String(rawKey||''));
    if(PICK_CACHE[key])return {key,pick:PICK_CACHE[key]};
    const pool=[...currentPyramidList(uiStep()),...sigs()];
    const pick=pool.find(x=>keyFor(x)===key);
    return {key,pick};
  }
  function debouncedAction(key){
    const now=Date.now();
    if(lastAction.key===key && now-lastAction.ts<550)return false;
    lastAction={key,ts:now}; return true;
  }

  window.bp20PickForStep=function(rawKey){
    const {key,pick}=findPick(rawKey);
    if(!debouncedAction('pick:'+key))return;
    if(!pick){alert('Nu găsesc evenimentul. Închide tabul și redeschide aplicația.');return;}
    let sess=normalizeSession(activeSession())||createSession();
    if(sess.status!=='active')sess=createSession();
    sess=normalizeSession(sess);
    const rows=pendingRows(sess);
    if(rows.some(x=>String(x.key)===key)){alert('Evenimentul este deja selectat pentru pasul curent.');return;}
    if(rows.some(x=>String(x.event_id)===String(pick.event_id||pick.id))){alert('Ai deja acest meci pe pasul curent. Alege alt eveniment.');return;}
    if(rows.length>=sess.max_legs){alert(`Ai atins limita de ${sess.max_legs} eveniment(e) pentru acest pas.`);return;}
    sess.selections.push(compactPick(pick,sess));
    sess.updated_at=new Date().toISOString();
    upsertSession(sess);
    renderCommandCenter();
  };

  window.bp20AutoPickPyramid=function(){
    if(!debouncedAction('auto'))return;
    let sess=normalizeSession(activeSession())||createSession();
    if(sess.status!=='active')sess=createSession();
    sess=normalizeSession(sess);
    const existing=pendingRows(sess);
    if(existing.length>=sess.max_legs){alert(`Ai deja ${existing.length}/${sess.max_legs} evenimente pe pasul curent.`);return;}
    const target=num(sess.target_odds)||targetOdds();
    const slots=sess.max_legs-existing.length;
    const existingCombo=combinedOdds(existing);
    const pool=currentPyramidList(sess.current_step)
      .filter(p=>!existing.some(x=>String(x.key)===keyFor(p)))
      .filter(p=>!existing.some(x=>String(x.event_id)===String(p.event_id||p.id)))
      .filter(p=>toOdds(p.odds??p.market_odds??p.best_odds)>1)
      .sort((a,b)=>(Number(b.pyramid_ready_score||scoreOf(b))-Number(a.pyramid_ready_score||scoreOf(a))));
    let best=null;
    function product(arr){return arr.reduce((acc,p)=>acc*(toOdds(p.odds??p.market_odds??p.best_odds)||1),1);}
    function avgScore(arr){return arr.length?arr.reduce((a,p)=>a+Number(p.pyramid_ready_score||scoreOf(p)||0),0)/arr.length:0;}
    function rec(start,chosen){
      if(chosen.length){
        const total=existingCombo*product(chosen);
        const hit=total>=target;
        const overshoot=Math.max(0,total-target);
        const gap=Math.max(0,target-total);
        // Prefer target hit, high quality, fewer legs, low overshoot.
        const score=(hit?100000:0)+avgScore(chosen)*25-chosen.length*45-overshoot*300-gap*900;
        if(!best||score>best.score)best={chosen,total,score,hit};
      }
      if(chosen.length>=slots)return;
      for(let i=start;i<pool.length;i++)rec(i+1,chosen.concat(pool[i]));
    }
    rec(0,[]);
    if(!best){alert('Nu am găsit selecții suficient de bune pentru completare.');return;}
    for(const p of best.chosen){
      if(pendingRows(sess).length>=sess.max_legs)break;
      sess.selections.push(compactPick(p,sess));
      if(combinedOdds(pendingRows(sess))>=target && sess.select_mode==='auto')break;
    }
    sess.updated_at=new Date().toISOString();
    upsertSession(sess);
    renderCommandCenter();
  };

  window.bp20SettlePyramid=function(status){
    if(!debouncedAction('settle:'+status))return;
    const sess=normalizeSession(activeSession()); if(!sess){alert('Nu există piramidă activă.');return;}
    const rows=pendingRows(sess); if(!rows.length){alert('Nu există selecții în așteptare pentru pasul curent.');return;}
    const st=statusOf(status);
    const stake=calcStake(sess), combo=combinedOdds(rows), stepReturn=stake*combo, now=new Date().toISOString();
    if(st==='VOID'){
      const last=rows[rows.length-1];
      if(last){
        last.status='VOID';
        last.settled_at=now;
        last.void_reason='manual_last_leg';
        last.return_amount=0;
      }
      sess.updated_at=now;
      upsertSession(sess);
      renderCommandCenter();
      return;
    }
    rows.forEach((x,i)=>{x.status=st;x.settled_at=now;x.combined_odds=combo;x.step_leg_count=rows.length;x.step_stake=stake;x.step_return_amount=i===0?stepReturn:0;});
    if(st==='WIN'){
      sess.completed_steps=(Number(sess.completed_steps)||0)+1;
      sess.current_stake=stepReturn;
      if(Number(sess.current_step)>=Number(sess.steps)){sess.status='completed';}
      else{sess.current_step=Number(sess.current_step)+1; localStorage.setItem('bp20.pyramid.step',String(sess.current_step));}
    }else if(st==='LOST'){
      sess.status='lost';
      sess.current_stake=0;
    }else if(st==='CASHOUT'){
      const raw=prompt('Suma cashout în lei:', String(stepReturn.toFixed(2)));
      if(raw===null)return;
      const val=num(raw);
      if(val===null||val<0){alert('Sumă invalidă.');return;}
      rows.forEach((x,i)=>{x.status='CASHOUT';x.step_return_amount=i===0?val:0;});
      sess.status='cashout'; sess.cashout_amount=val; sess.current_stake=val;
    }
    sess.updated_at=now; upsertSession(sess); renderCommandCenter();
  };

  window.bp20VoidSelection=function(rawKey){
    const key=decodeURIComponent(String(rawKey||''));
    if(!debouncedAction('void-one:'+key))return;
    const sess=normalizeSession(activeSession());
    if(!sess){alert('Nu există piramidă activă.');return;}
    const row=pendingRows(sess).find(x=>String(x.key)===key);
    if(!row){alert('Selecția nu mai este în așteptare.');return;}
    row.status='VOID';
    row.settled_at=new Date().toISOString();
    row.void_reason='manual_selected_leg';
    row.return_amount=0;
    sess.updated_at=new Date().toISOString();
    upsertSession(sess);
    renderCommandCenter();
  };

  window.bp20ResetPyramid=function(){
    if(!debouncedAction('reset'))return;
    const sess=activeSession();
    if(sess&&String(sess.status||'').toLowerCase()==='active'){
      const ok=confirm('Sigur resetezi piramida activă?');
      if(!ok)return;
      sess.status='cancelled'; sess.updated_at=new Date().toISOString(); upsertSession(sess);
    }
    localStorage.removeItem(PYR_ACTIVE_KEY);
    localStorage.setItem('bp20.pyramid.step','1');
    renderCommandCenter();
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
    else if(mk==='1'||mk.includes('home'))win=hs>as;
    else if(mk==='2'||mk.includes('away'))win=as>hs;
    else if(mk==='x'||mk.includes('draw'))win=hs===as;
    if(win===null)return null;
    return {status:win?'WIN':'LOST',score:`${hs}-${as}`,reason:`Auto: scor final ${hs}-${as}`};
  }
  function settlementForSelection(sel){
    const eid=String(sel.event_id||''), mk=marketKey(sel.market||sel.market_label);
    const jr=journalRows().find(r=>String(r.event_id)===eid && String(r.status||'').toLowerCase()==='settled' && (!mk || marketKey(r.market||r.market_label||r.market_canonical).includes(mk) || mk.includes(marketKey(r.market||r.market_label||r.market_canonical))));
    if(jr&&jr.result)return {status:String(jr.result).toUpperCase()==='WIN'?'WIN':'LOST',score:jr.score_ft||jr.actual_score||'',reason:jr.settlement_reason||'Auto din jurnal'};
    const rr=resultRows().find(r=>String(r.id||r.event_id)===eid && /finished|ft|ended/i.test(String(r.status||r.period||'')));
    return rr?calcResultFromScore(sel,rr):null;
  }
  function autoValidateActiveSession(showAlert=false){
    const sess=normalizeSession(activeSession()); if(!sess||sess.status!=='active')return false;
    const rows=pendingRows(sess); if(!rows.length)return false;
    let changed=false;
    rows.forEach(x=>{
      const res=settlementForSelection(x);
      if(res){x.status=res.status;x.actual_score=res.score;x.auto_reason=res.reason;x.auto_checked_at=new Date().toISOString();changed=true;}
    });
    if(!changed){if(showAlert)alert('Încă nu există rezultat final pentru selecțiile din pasul curent.');return false;}
    const pendingStill=pendingRows(sess);
    if(pendingStill.length){upsertSession(sess); if(showAlert)alert('Am actualizat ce am găsit, dar pasul nu este complet finalizat.'); return true;}
    const stepRows=currentStepRows(sess,true).filter(x=>statusOf(x.status)!=='VOID');
    if(!stepRows.length){
      sess.updated_at=new Date().toISOString();
      upsertSession(sess);
      if(showAlert)alert('Toate selecțiile de pe pas sunt VOID. Adaugă alt eveniment pentru acest pas.');
      return true;
    }
    const lost=stepRows.some(x=>statusOf(x.status)==='LOST');
    const stake=calcStake(sess), combo=combinedOdds(stepRows), stepReturn=stake*combo;
    if(lost){sess.status='lost';sess.current_stake=0;}
    else{sess.completed_steps=(Number(sess.completed_steps)||0)+1;sess.current_stake=stepReturn;if(Number(sess.current_step)>=Number(sess.steps)){sess.status='completed';}else{sess.current_step=Number(sess.current_step)+1;localStorage.setItem('bp20.pyramid.step',String(sess.current_step));}}
    sess.updated_at=new Date().toISOString(); upsertSession(sess);
    if(showAlert)alert(lost?'Pas validat automat: LOST.':'Pas validat automat: WIN. Am trecut la pasul următor.');
    return true;
  }
  window.bp20CheckPyramidResults=function(){refreshSettlementData(true);};
  async function refreshSettlementData(showAlert=false){
    try{
      const [journal,results]=await Promise.all([
        fetchJ('data/selection_journal.json').catch(()=>API.journal||{results:[]}),
        fetchJ('data/recent_results.json').catch(()=>API.results||{results:[]})
      ]);
      API.journal=journal; API.results=results;
      const changed=autoValidateActiveSession(showAlert);
      renderCommandCenter();
      if(showAlert&&!changed)alert('Încă nu există rezultat final pentru selecțiile din pasul curent.');
    }catch(e){if(showAlert)alert('Nu am putut verifica rezultatele acum.');}
  }

  function clvBadge(s){
    if(s?.clv_reliable && s.clv_beat_pct!=null)return `<span class="bp20-badge ${Number(s.clv_beat_pct)>=0?'good':'bad'}">CLV ${pct(s.clv_beat_pct)}</span>`;
    return `<span class="bp20-badge warn">${esc(s?.clv_badge||'CLV Tracking')}</span>`;
  }
  function pyramidBadge(s){const v=Number(s?.pyramid_ready_score||0);return v?`<span class="bp20-badge ${v>=75?'good':'warn'}">Pyramid ${nf(v,0)}/100</span>`:'';}
  function liveBadge(s){return s?.live_value_label?`<span class="bp20-badge good">${esc(s.live_value_label)} · EV ${pct(s.live_value_ev_pct)}</span>`:'';}
  function insightBadge(s){return insightFor(s)?`<span class="bp20-badge good">AI Insight</span>`:'';}
  function badgesFor(s){return `<div class="bp20-badges">${clvBadge(s)}${pyramidBadge(s)}${liveBadge(s)}${insightBadge(s)}</div>`;}
  function renderCLV(){
    const s=API.clv?.summary||{}, r=API.clv?.rolling_30d||{};
    const reliable=num(r.reliable_n??s.reliable_n)??0, rate=num(r.market_beat_rate??s.market_beat_rate), avg=num(r.avg_clv_pct??s.avg_clv_pct);
    const sample=num(r.total_picks??s.total_picks??s.tracked_open)??0;
    const ok=reliable>=20;
    return `<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">📈 CLV Validation</div><div class="bp20-sub">autoritate matematică: cota publicată vs closing line</div></div><span class="bp20-pill">${ok?'MARKET BEAT':'TRACKING'}</span></div><div class="bp20-grid"><div class="bp20-kpi"><div class="bp20-kv ${ok&&rate>=70?'bp20-klv':'bp20-kwarn'}">${ok&&rate!=null?nf(rate,0)+'%':'Tracking'}</div><div class="bp20-kl">Market Beat</div></div><div class="bp20-kpi"><div class="bp20-kv ${ok&&avg>=0?'bp20-klv':'bp20-kwarn'}">${ok&&avg!=null?pct(avg):`${reliable} reliable`}</div><div class="bp20-kl">Avg CLV</div></div><div class="bp20-kpi"><div class="bp20-kv">${ok?String(reliable):`${sample} sample`}</div><div class="bp20-kl">Reliable</div></div></div><div class="bp20-row"><div class="bp20-note">${ok?'Sample suficient pentru citirea Market Beat Rate.':'CLV este în modul Tracking: acumulăm linii de închidere. Nu îl folosim ca dovadă finală până nu există minimum 20 linii reliable.'}</div></div></div>`;
  }
  function currentPyramidList(step){
    const pool=API.pyramid?.current_step_pool||{};
    const list=pool[String(step)]||pool['1']||[];
    if(list.length)return list.slice(0,12);
    return sigs().slice().sort((a,b)=>scoreOf(b)-scoreOf(a)).slice(0,12);
  }
  function renderSelectionLine(x){
    const st=statusOf(x.status);
    const cls=st==='WIN'?'good':st==='LOST'?'bad':st==='CASHOUT'?'warn':st==='VOID'?'warn':'info';
    const label=st==='PENDING'?'PENDING':st;
    const encoded=encodeURIComponent(String(x.key||''));
    const action=st==='PENDING'?`<button type="button" class="bp20-row-void" data-bp20-void-one="${esc(encoded)}" onclick="window.bp20VoidSelection('${esc(encoded)}')">VOID</button>`:'';
    return `<div class="bp20-session-line ${st==='VOID'?'is-void':''}"><div><b>Pas ${esc(x.step)}</b> · ${esc(x.home_team)} vs ${esc(x.away_team)}<small>${dateTime(x.event_date)} · ${esc(x.market_label)} · @${esc(x.odds??'—')}</small></div><div class="bp20-line-actions"><span class="${cls}">${esc(label)}</span>${action}</div></div>`;
  }
  function renderActivePyramid(){
    const sess=normalizeSession(activeSession());
    if(!sess||sess.status==='cancelled'){
      return `<div class="bp20-session bp20-session-empty"><div class="bp20-session-head"><div><b>Piramidă activă</b><small>Setezi cota totală a pasului. Robotul alege automat 1-3 evenimente pe baza scorului, probabilității și cotei necesare.</small></div><span class="bp20-session-pill">Local</span></div><div class="bp20-session-actions"><button type="button" class="bp20-action win" data-bp20-auto="1" onclick="window.bp20AutoPickPyramid()">🤖 Alege automat</button></div></div>`;
    }
    const rows=currentStepRows(sess,true);
    const pend=pendingRows(sess);
    const voidCount=rows.filter(x=>statusOf(x.status)==='VOID').length;
    const stake=calcStake(sess);
    const combo=combinedOdds(pend);
    const expected=pend.length?stake*combo:stake;
    const target=num(sess.target_odds)||targetOdds();
    const progress=Math.max(0,Math.min(100,pend.length?combo/target*100:0));
    const targetLine=!pend.length?(voidCount?`${voidCount} VOID · adaugă alt eveniment pentru pas`:'Așteaptă selecție'):(combo>=target?`${pend.length} selecții active · Țintă atinsă @${target.toFixed(2)}`:`${pend.length} selecții active · Mai trebuie ~@${(target/combo).toFixed(2)}`);
    const headerStatus=sess.status==='active'?'ACTIVĂ':sessionLabel(sess.status);
    return `<div class="bp20-session"><div class="bp20-session-head"><div><b>Piramida activă</b><small>Pas ${esc(sess.current_step)}/${esc(sess.steps)} · <span class="bp20-active-word">${esc(headerStatus)}</span></small></div><span class="bp20-session-pill">${sess.status==='active'?'AUTO TRACKING':esc(headerStatus)}</span></div><div class="bp20-session-grid"><div><b>${money(stake)}</b><small>MIZĂ CURENTĂ</small></div><div><b>@${pend.length?combo.toFixed(2):'—'}</b><small>COTĂ PAS</small></div><div class="wide"><b>${money(expected)}</b><small>RETUR ESTIMAT</small></div></div><div class="bp20-session-target"><span>${sess.select_mode==='auto'?'ROBOT AUTO 1-3':'SELECȚIE MANUALĂ'}</span><b>${esc(targetLine)}</b><i style="width:${progress}%"></i></div>${rows.length?`<div class="bp20-session-lines">${rows.map(renderSelectionLine).join('')}</div>`:''}${sess.status==='active'?`<div class="bp20-session-actions"><button type="button" class="bp20-action win" data-bp20-auto="1" onclick="window.bp20AutoPickPyramid()">🤖 Auto completează</button><button type="button" class="bp20-action check" data-bp20-check="1" onclick="window.bp20CheckPyramidResults()">🔄 Verifică rezultate</button></div>`:''}${pend.length?`<div class="bp20-session-actions"><button type="button" class="bp20-action win" data-bp20-settle="WIN">✅ WIN PAS</button><button type="button" class="bp20-action lost" data-bp20-settle="LOST">❌ LOST PAS</button><button type="button" class="bp20-action cash" data-bp20-settle="CASHOUT">💰 CASHOUT</button><button type="button" class="bp20-action void" data-bp20-settle="VOID">↩ VOID ULTIMUL</button></div>`:''}<div class="bp20-session-actions subtle"><button type="button" class="bp20-action" data-bp20-reset="1" onclick="window.bp20ResetPyramid()">Reset sesiune</button></div></div>`;
  }
  function sessionLabel(st){
    return ({completed:'FINALIZATĂ',lost:'PIERDUTĂ',cashout:'CASHOUT',cancelled:'ANULATĂ',active:'ACTIVĂ'}[String(st||'').toLowerCase()]||String(st||'—').toUpperCase());
  }
  function pickCard(s,mode='pyramid'){
    const key=keyFor(s); PICK_CACHE[key]=s;
    const encoded=encodeURIComponent(key);
    const sess=normalizeSession(activeSession());
    const pend=pendingRows(sess);
    const already=pend.some(x=>String(x.key)===key);
    const full=sess&&sess.status==='active'&&pend.length>=sess.max_legs;
    const combo=combinedOdds(pend);
    const label=already?'Selectat':(full?'Limită atinsă':(pend.length?(combo>=targetOdds()?'Adaugă extra':'Adaugă la pas'):'Alege pentru pas'));
    const insight=compactInsight(insightFor(s),s);
    const action=mode==='pyramid'?`<div class="bp20-pick-actions"><button type="button" class="bp20-choose ${already?'is-selected':''}" data-bp20-pick="${esc(encoded)}" ${already||full?'disabled':''} onclick="window.bp20PickForStep('${esc(encoded)}')">${label}</button></div>`:'';
    return `<div class="bp20-pick"><div><div class="bp20-match">${esc(s.home_team)} vs ${esc(s.away_team)}</div><div class="bp20-meta">${dateTime(s.event_date)} · ${esc(s.league||'—')}</div><div class="bp20-rec">${esc(s.market_label||s.market)} · ${prob(s.adj_prob)} · @${esc(s.odds??'—')}</div>${insight?`<div class="bp20-insight">${insight}</div>`:''}${badgesFor(s)}${action}</div><div class="bp20-score">${nf(mode==='pyramid'?s.pyramid_ready_score:scoreOf(s),0)}<small>${mode==='pyramid'?'ready':'score'}</small></div></div>`;
  }
  function renderPyramid(){
    const sess=normalizeSession(activeSession());
    const steps=sess&&sess.status==='active'?Number(sess.steps):stepsCount();
    const step=sess&&sess.status==='active'?Number(sess.current_step):uiStep();
    const mode=sess&&sess.status==='active'?String(sess.select_mode||selectMode()):selectMode();
    const target=targetOdds();
    const stake=baseStake();
    const progress=Math.max(0,Math.min(100,(step-1)/Math.max(1,steps)*100));
    const list=currentPyramidList(step);
    return `<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">🧱 Pyramid Assistant</div><div class="bp20-sub">alegi 1-3 evenimente → blochezi pasul → validezi biletul ca WIN/LOST</div></div><span class="bp20-pill">Pas ${step}/${steps}</span></div><div class="bp20-form bp20-form-pyramid"><div class="bp20-field"><label>Pași</label><select id="bp20-steps"><option ${steps===3?'selected':''}>3</option><option ${steps===5?'selected':''}>5</option><option ${steps===7?'selected':''}>7</option></select></div><div class="bp20-field"><label>Pas curent</label><select id="bp20-step">${Array.from({length:steps},(_,i)=>i+1).map(x=>`<option ${x===step?'selected':''}>${x}</option>`).join('')}</select></div><div class="bp20-field bp20-field-wide"><label>Selecție</label><select id="bp20-legs"><option value="auto" ${mode==='auto'?'selected':''}>AUTO 1-3</option><option value="1" ${mode==='1'?'selected':''}>1 fix</option><option value="2" ${mode==='2'?'selected':''}>2 max</option><option value="3" ${mode==='3'?'selected':''}>3 max</option></select></div><div class="bp20-field"><label>Cotă pas țintă</label><input id="bp20-avg" type="number" step="0.01" value="${target.toFixed(2)}"></div><div class="bp20-field"><label>Miză inițială</label><input id="bp20-stake" type="number" step="1" value="${stake.toFixed(0)}"></div></div><div class="bp20-progress"><i style="width:${progress}%"></i></div>${renderActivePyramid()}<div class="bp20-list bp20-reco-list">${list.length?list.map(x=>pickCard(x,'pyramid')).join(''):'<div class="bp20-empty">Nu există opțiuni suficient de stabile pentru pasul ales.</div>'}</div></div>`;
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
    const sess=normalizeSession(activeSession()); if(sess&&sess.status==='active')upsertSession(sess);
    let root=$('bp20-root');
    if(!root){root=document.createElement('div');root.id='bp20-root';root.className='bp20-root';const anchor=$('dash-body')||dash.lastElementChild;dash.insertBefore(root,anchor);}
    root.innerHTML=renderCLV()+renderPyramid()+renderAlerts()+renderHeatmap();
    bindControls();
  }
  function bindControls(){
    const steps=$('bp20-steps'), step=$('bp20-step'), avg=$('bp20-avg'), stake=$('bp20-stake'), legs=$('bp20-legs');
    const canChange=()=>{const s=activeSession();return !s||String(s.status).toLowerCase()!=='active'||pendingRows(s).length===0;};
    if(steps)steps.onchange=()=>{localStorage.setItem('bp20.pyramid.steps',steps.value);const s=activeSession();if(s&&canChange()){s.steps=Number(steps.value)||s.steps;s.current_step=Math.min(Number(s.current_step)||1,s.steps);upsertSession(s);}else localStorage.setItem('bp20.pyramid.step','1');renderCommandCenter();};
    if(step)step.onchange=()=>{localStorage.setItem('bp20.pyramid.step',step.value);const s=activeSession();if(s&&canChange()){s.current_step=Number(step.value)||s.current_step;upsertSession(s);}renderCommandCenter();};
    if(legs)legs.onchange=()=>{localStorage.setItem(PYR_MODE_KEY,legs.value);const s=activeSession();if(s&&String(s.status).toLowerCase()==='active'){s.select_mode=legs.value;s.max_legs=maxLegsForMode(legs.value);upsertSession(s);}renderCommandCenter();};
    if(avg)avg.onchange=()=>{localStorage.setItem('bp20.pyramid.avg',avg.value);const s=activeSession();if(s&&String(s.status).toLowerCase()==='active'){s.target_odds=targetOdds();upsertSession(s);}renderCommandCenter();};
    if(stake)stake.onchange=()=>{localStorage.setItem('bp20.pyramid.stake',stake.value||'10');const s=activeSession();if(s&&String(s.status).toLowerCase()==='active'&&!(s.selections||[]).length){s.base_stake=baseStake();s.current_stake=s.base_stake;upsertSession(s);}renderCommandCenter();};
  }
  function renderTopInsights(){
    const smart=$('sec-smartbet'); if(!smart||$('bp20-insights'))return;
    const top=sigs().slice().sort((a,b)=>scoreOf(b)-scoreOf(a)).filter(s=>insightFor(s)).slice(0,3);
    const div=document.createElement('div');div.id='bp20-insights';div.className='bp20-root';
    div.innerHTML=`<div class="bp20-card"><div class="bp20-head"><div><div class="bp20-title">🧠 AI Reasoning — Top Picks</div><div class="bp20-sub">o propoziție clară pentru decizie rapidă</div></div><span class="bp20-pill">5 secunde</span></div><div class="bp20-list">${top.length?top.map(x=>pickCard(x,'score')).join(''):'<div class="bp20-empty">Insight-urile apar după rularea workflow-ului.</div>'}</div></div>`;
    const anchor=$('sb-body')||smart.lastElementChild; smart.insertBefore(div,anchor);
  }
  function patchSigCard(){
    if(typeof window.sigCard!=='function'||window.sigCard.__bp20v8)return;
    const original=window.sigCard;
    window.sigCard=function(sig){
      let html=original.apply(this,arguments);
      const extra=badgesFor(sig)+(insightFor(sig)?`<div class="bp20-insight">${esc(insightFor(sig))}</div>`:'');
      html=html.replace('<div class="md-open-row">', extra+'<div class="md-open-row">');
      html=html.replace('<div class="sig-score-lbl">SmartBet</div>','<div class="sig-score-lbl">Signal</div>');
      return html;
    };
    window.sigCard.__bp20v8=true;
  }
  function bindGlobalActions(){
    if(window.__bp20v8Bound)return; window.__bp20v8Bound=true;
    document.addEventListener('click',ev=>{
      const pick=ev.target.closest('[data-bp20-pick]');
      if(pick){ev.preventDefault();ev.stopPropagation();if(!pick.disabled)window.bp20PickForStep(pick.getAttribute('data-bp20-pick'));return;}
      const auto=ev.target.closest('[data-bp20-auto]');
      if(auto){ev.preventDefault();ev.stopPropagation();window.bp20AutoPickPyramid();return;}
      const check=ev.target.closest('[data-bp20-check]');
      if(check){ev.preventDefault();ev.stopPropagation();window.bp20CheckPyramidResults();return;}
      const voidOne=ev.target.closest('[data-bp20-void-one]');
      if(voidOne){ev.preventDefault();ev.stopPropagation();window.bp20VoidSelection(voidOne.getAttribute('data-bp20-void-one'));return;}
      const settle=ev.target.closest('[data-bp20-settle]');
      if(settle){ev.preventDefault();ev.stopPropagation();window.bp20SettlePyramid(settle.getAttribute('data-bp20-settle'));return;}
      const reset=ev.target.closest('[data-bp20-reset]');
      if(reset){ev.preventDefault();ev.stopPropagation();window.bp20ResetPyramid();}
    },true);
  }
  function renderSoon(){clearTimeout(renderTimer); renderTimer=setTimeout(()=>{patchSigCard();renderCommandCenter();renderTopInsights();},160);}
  async function loadData(){
    const [signals,clv,pyramid,insights,alerts,heatmap,journal,results]=await Promise.all([
      fetchJ('data/signals.json').catch(()=>({signals:[]})),
      fetchJ('data/clv_tracker.json').catch(()=>({summary:{},rolling_30d:{},by_event_market:{}})),
      fetchJ('data/pyramid_assistant.json').catch(()=>({current_step_pool:{}})),
      fetchJ('data/ai_insights.json').catch(()=>({by_signal:{}})),
      fetchJ('data/live_value_alerts.json').catch(()=>({alerts:[]})),
      fetchJ('data/performance_heatmap.json').catch(()=>({summary:{},leagues:{},cells:[]})),
      fetchJ('data/selection_journal.json').catch(()=>({results:[]})),
      fetchJ('data/recent_results.json').catch(()=>({results:[]}))
    ]);
    Object.assign(API,{signals,clv,pyramid,insights,alerts,heatmap,journal,results});
  }
  async function init(){
    bindGlobalActions();
    await loadData().catch(()=>{});
    patchSigCard(); renderCommandCenter(); renderTopInsights();
    const mo=new MutationObserver(renderSoon);
    ['dash-body','sb-body','sec-dash','sec-smartbet'].forEach(id=>{const el=$(id); if(el)mo.observe(el,{childList:true,subtree:false});});
    const oldGo=window.go;
    if(typeof oldGo==='function'&&!oldGo.__bp20v8){window.go=function(){const r=oldGo.apply(this,arguments);renderSoon();return r;}; window.go.__bp20v8=true;}
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshSettlementData(false);});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
