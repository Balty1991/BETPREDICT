/* BETPREDICT Product Upgrade — Basic Mode, CLV Trust Layer, Smart Filters */
(function(){
  'use strict';
  const KEY='betpredict.view.mode.v2';
  const API={signals:null,clv:null,context:null,broadcasts:null,bsdPreds:null};
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  const num=(v)=>{if(v===null||v===undefined||v==='')return null;const n=Number(v);return Number.isFinite(n)?n:null};
  const nf=(v,d=1)=>{const n=num(v);return n!==null?n.toFixed(d):'—'};
  const pct=v=>{const n=num(v);return n!==null?`${n>=0?'+':''}${n.toFixed(1)}%`:'—'};
  const prob=v=>{const n=Number(v);return Number.isFinite(n)?`${n.toFixed(1)}%`:'—'};
  const time=iso=>{try{if(!iso)return'—';const d=new Date(iso);if(isNaN(d))return'—';return d.toLocaleDateString('ro-RO',{day:'2-digit',month:'2-digit'})+' · '+d.toLocaleTimeString('ro-RO',{hour:'2-digit',minute:'2-digit'});}catch{return'—'}};
  const fetchJ=p=>fetch(p+'?bpv='+Date.now(),{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status));
  const teamLogoHtml=(id,cls='tlogo-sm')=>typeof window.teamLogo==='function'?window.teamLogo(id,cls):`<span class="${cls}"></span>`;

  function setMode(mode){
    mode=mode==='analytic'?'analytic':'basic';
    localStorage.setItem(KEY,mode);
    document.body.classList.toggle('bp-basic',mode==='basic');
    document.body.classList.toggle('bp-analytic',mode==='analytic');
    document.querySelectorAll('.bp-mode-toggle b').forEach(b=>b.textContent=mode==='basic'?'Basic':'Analytic');
    renderAllSoon();
  }
  function getMode(){return localStorage.getItem(KEY)==='analytic'?'analytic':'basic'}
  function injectToggle(){
    const hdr=document.querySelector('.hdr-r');
    if(!hdr || document.querySelector('.bp-mode-toggle'))return;
    const btn=document.createElement('button');
    btn.type='button';btn.className='bp-mode-toggle';btn.innerHTML='<span class="bp-mode-dot"></span><b>Basic</b>';
    btn.title='Comută Basic / Analytic';
    btn.addEventListener('click',()=>setMode(getMode()==='basic'?'analytic':'basic'));
    hdr.insertBefore(btn,hdr.firstChild);
  }

  function marketScore(sig){
    const direct=Number(sig.display_score ?? sig.market_signal_score);
    if(Number.isFinite(direct)&&direct>0)return Math.round(direct);
    const v6=Number(sig.smartbet_score_v6);
    if(Number.isFinite(v6)&&v6>0)return Math.round(v6);
    const old=Number(sig.smartbet_score);
    if(Number.isFinite(old)&&old>0)return Math.round(old);
    const p=Number(sig.adjusted_prob ?? sig.adj_prob ?? sig.model_probability ?? 0);
    const edge=Number(sig.edge_pp ?? sig.edge_nv_pp ?? 0);
    const evRaw=String(sig.ev_pct ?? sig.edge_pct ?? '0').replace('%','');
    const ev=Number(evRaw);
    let score=(p*0.68)+(Math.max(0,edge)*2.1)+(Math.max(0,ev)*0.75);
    if(sig.odds_real)score+=4;
    if(String(sig.consensus_tier||'').includes('TOTAL'))score+=4;
    return Math.max(1,Math.min(100,Math.round(score)));
  }
  function grade(score){return score>=90?'A+':score>=82?'A':score>=74?'B':score>=66?'C':score>=55?'D':'E'}
  function scoreColor(score){return score>=82?'#00e87a':score>=70?'#fbbf24':score>=55?'#60a5fa':'#fb7185'}
  function normMarket(m){return String(m||'').toLowerCase().replace(/[^a-z0-9]/g,'')}
  function ctxFor(eventId){
    const by=API.context?.by_event||{};
    return by[String(eventId)]||{};
  }
  function clvMarket(market){
    const key=normMarket(market);
    const by=API.clv?.by_market||{};
    return by[market]||by[key]||by[canonicalMarket(key)]||null;
  }
  function canonicalMarket(key){
    if(key.includes('over15'))return'over15'; if(key.includes('over25'))return'over25'; if(key.includes('under35'))return'under35'; if(key.includes('btts'))return'btts'; if(key.includes('home'))return'homeWin'; if(key==='x'||key.includes('draw'))return'draw'; if(key.includes('away'))return'awayWin'; return key;
  }
  function clvTag(sig){
    const row=clvMarket(sig.market);
    const reliable=Number(row?.reliable_n||0);
    if(!row||reliable<20)return '<span class="bp-tag warn">CLV Tracking</span>';
    const rate=(num(row.clv_positive_rate)??0)*100;
    const avg=num(row.avg_clv_pct);
    const cls=avg!==null&&avg>=0.5&&rate>=50?'good':avg!==null&&avg<0?'bad':'warn';
    return `<span class="bp-tag ${cls}">CLV ${pct(avg)} · ${nf(rate,0)}%</span>`;
  }
  function contextTag(c){
    const s=Number(c.context_score);
    if(!Number.isFinite(s))return '<span class="bp-tag warn">Context neutru</span>';
    const cls=s>=75?'good':s>=60?'warn':'bad';
    return `<span class="bp-tag ${cls}">Context ${Math.round(s)}/100</span>`;
  }
  function pickReasonHtml(sig,c){
    const parts=[];
    const edge=Number(sig.edge_pp); if(Number.isFinite(edge)&&edge>0)parts.push(`edge ${nf(edge,1)}pp`);
    const ev=String(sig.ev_pct||'').trim(); if(ev)parts.push(`EV ${ev}`);
    if(c&&c.summary)parts.push(c.summary);
    const reason=parts[0]||'probabilitate și cotă în zona acceptată';
    const risk=(parts.find(x=>/risc|absen|accident|meteo|gazon|lineup|volatil|probabil|incert/i.test(x))||'fără abatere majoră semnalată');
    const verdict=`execuție doar dacă piața păstrează cota ${sig.odds??'afișată'}`;
    return `<b>Motiv:</b> ${esc(reason)}<br><b>Risc:</b> ${esc(risk)}<br><b>Verdict:</b> ${esc(verdict)}.`;
  }
  function signalSort(a,b){return marketScore(b)-marketScore(a) || Number(b.edge_pp||0)-Number(a.edge_pp||0)}

  function renderCLVWidget(){
    const s=API.clv?.summary||{}, r30=API.clv?.rolling_30d||{}, diag=API.clv?.diagnosis||{};
    const reliable=Number(s.reliable_n ?? r30.reliable_n ?? 0);
    const proxyWarn=!!s.proxy_warning || reliable<20;
    const rate=!proxyWarn ? num(r30.clv_positive_rate ?? s.clv_positive_rate) : null;
    const avg=!proxyWarn ? num(r30.avg_clv_pct ?? s.avg_clv_pct) : null;
    const n=num(r30.total_picks ?? s.total_picks ?? s.tracked_open)??0;
    const ratePct=rate!==null?rate*100:null;
    const headline=proxyWarn?'Tracking':(ratePct!=null?`${nf(ratePct,0)}%`:'Tracking');
    const ok=!proxyWarn && ((avg??-999)>=0 || (ratePct??0)>=50);
    const label=proxyWarn?'CLV pornit: acumulăm closing line reliable':(n?`Modelul a bătut piața în ultimele 30 zile`:'CLV tracker pregătit pentru validare');
    const note=n?`${reliable}/${n} linii reliable. ${proxyWarn?'Nu îl folosim ca dovadă finală până nu există minimum 20 linii reliable. ':''}${diag.short||diag.label||''}`:'Rulează workflow-ul ca să se construiască istoricul CLV.';
    const avgText=proxyWarn?`${reliable} reliable`:pct(avg);
    return `<div class="bp-clv-grid"><div class="bp-clv-main"><div class="bp-clv-number" style="color:${ok?'#00e87a':'#fbbf24'}">${headline}</div><div class="bp-clv-label">${esc(label)}</div><div class="bp-clv-note">${esc(note)}</div></div><div class="bp-mini-kpis"><div class="bp-mini-kpi"><div class="bp-mini-v">${avgText}</div><div class="bp-mini-l">Reliable</div></div><div class="bp-mini-kpi"><div class="bp-mini-v">${nf(s.roi_flat_pct,1)}%</div><div class="bp-mini-l">ROI Flat</div></div><div class="bp-mini-kpi"><div class="bp-mini-v">${n||'0'}</div><div class="bp-mini-l">Sample</div></div></div></div>`;
  }
  function renderTrustRow(signals){
    const top=signals.filter(s=>marketScore(s)>=75).length;
    const oddsReal=signals.filter(s=>s.odds_real).length;
    const ctxGood=signals.filter(s=>Number(ctxFor(s.event_id).context_score)>=70).length;
    return `<div class="bp-trust-row"><div class="bp-trust"><div class="bp-trust-v">${top}</div><div class="bp-trust-l">Score ≥75</div></div><div class="bp-trust"><div class="bp-trust-v">${oddsReal}</div><div class="bp-trust-l">Cote reale</div></div><div class="bp-trust"><div class="bp-trust-v">${ctxGood}</div><div class="bp-trust-l">Context OK</div></div></div>`;
  }
  function broadcastHtml(eid){
    const by=API.broadcasts?.by_event||{};
    const chs=(by[String(eid)]||[]).filter(c=>c.name);
    if(!chs.length)return'';
    const names=chs.slice(0,3).map(c=>esc(c.name)).join(' · ');
    return`<div class="bp-broadcast">📺 ${names}${chs.length>3?` +${chs.length-3}`:''}</div>`;
  }
  function bsdConsensusTag(eid){
    const preds=API.bsdPreds?.results||[];
    const p=preds.find(r=>String(r.event_id)===String(eid));
    if(!p)return'';
    if(p.consensus_level==='strong')return'<span class="bp-tag good">🤝 API Strong</span>';
    if(p.consensus_level==='moderate')return'<span class="bp-tag">🤝 API OK</span>';
    return'';
  }
  function renderPick(sig){
    const c=ctxFor(sig.event_id), score=marketScore(sig);
    const onclick=sig.event_id?` onclick="openMatchDetail('${String(sig.event_id).replace(/'/g,'')}')"`:'';
    return `<div class="bp-pick"${onclick}><div class="bp-pick-main"><div style="display:flex;gap:7px;align-items:center;margin-bottom:5px">${teamLogoHtml(sig.home_team_id)}${teamLogoHtml(sig.away_team_id)}<div class="bp-meta" style="margin:0">${time(sig.event_date)} · ${esc(sig.league||'—')}</div></div>${broadcastHtml(sig.event_id)}<div class="bp-match">${esc(sig.home_team)} vs ${esc(sig.away_team)}</div><div class="bp-rec">${esc(sig.market_label||sig.market||'—')} · ${prob(sig.adj_prob)}</div><div class="bp-explain">${pickReasonHtml(sig,c)}</div><div class="bp-tags">${sig._ev_negative?'<span class="bp-tag bad">⚠ EV Negativ</span>':''}${clvTag(sig)}${contextTag(c)}${bsdConsensusTag(sig.event_id)}<span class="bp-tag">Cotă ${esc(sig.odds ?? '—')}</span></div></div><div class="bp-score-box"><div class="bp-score" style="color:${scoreColor(score)}">${score}</div><div class="bp-score-l">${grade(score)} score</div><div class="bp-odd">@${esc(sig.odds ?? '—')}</div></div></div>`;
  }
  function renderBasicDashboard(){
    const sigs=(API.signals?.signals||[]).slice().sort(signalSort);
    const best=sigs.filter(s=>Number(s.adj_prob)>=70 && Number(s.odds)>=1.15 && !s._ev_negative).slice(0,5);
    const s=API.clv?.summary||{}, r30=API.clv?.rolling_30d||{};
    const reliable=Number(s.reliable_n??r30.reliable_n??0);
    const proxyWarn=!!s.proxy_warning||reliable<20;
    const clvBadge=proxyWarn?'tracking':`${reliable} reliable`;
    return `<div class="bp-upgrade-root"><div class="bp-u-stack">
      <details class="nd-accordion">
        <summary class="nd-accordion-sum"><span class="nd-accordion-icon">📈</span>Trust Layer CLV<span class="nd-accordion-badge">${clvBadge}</span></summary>
        <div class="nd-accordion-body" style="padding-top:10px">${renderCLVWidget()}</div>
      </details>
      <details class="nd-accordion">
        <summary class="nd-accordion-sum"><span class="nd-accordion-icon">🎯</span>Decision Center<span class="nd-accordion-badge">${best.length} semnale · Basic Mode</span></summary>
        <div class="nd-accordion-body" style="padding-top:8px">${renderTrustRow(sigs)}<div class="bp-basic-list">${best.length?best.map(renderPick).join(''):'<div class="bp-empty">Nu există semnale care trec pragul Basic Mode.</div>'}</div></div>
      </details>
    </div></div>`;
  }
  function injectDashboard(){
    const body=$('dash-body'); if(!body)return;
    const sigCount=(API.signals?.signals||[]).length;
    const stamp=[API.signals?.updated_at||'',API.clv?.updated_at||'',API.context?.updated_at||'',sigCount,getMode()].join('|');
    const root=body.querySelector('.bp-upgrade-root');
    if(root && body.dataset.bpUpgradeStamp===stamp)return;
    const html=renderBasicDashboard();
    if(!root)body.insertAdjacentHTML('afterbegin',html);
    else root.outerHTML=html;
    body.dataset.bpUpgradeStamp=stamp;
  }

  const filters={
    all:{label:'Toate',fn:s=>true},
    pyramid:{label:'Pyramid 1-3',fn:s=>Number(s.adj_prob)>=85 && Number(s.odds)>=1.25 && Number(s.odds)<=1.45},
    over15:{label:'Safe Over 1.5',fn:s=>String(s.market)==='over15' && Number(s.adj_prob)>=76},
    value:{label:'Value Edge',fn:s=>Number(s.edge_pp)>=5 && Number(s.odds)>=1.2},
    clv:{label:'CLV Confirmed',fn:s=>{const r=clvMarket(s.market);return r&&Number(r.avg_clv_pct)>=0&&Number(r.clv_positive_rate)>=0.5}},
    context:{label:'Context OK',fn:s=>Number(ctxFor(s.event_id).context_score)>=70},
    evpos:{label:'EV Pozitiv',fn:s=>!s._ev_negative && Number(s.ev_pct||0)>=0}
  };
  let activeFilter='all';
  function renderSmartFilter(){
    const host=$('sec-smartbet'); if(!host)return;
    if(!host.querySelector('.bp-smartbar')){
      const after=$('sb-strat-grid')||host.querySelector('.sec-sub');
      const html='<div class="bp-smartbar"><div class="bp-smartbar-title">⚙️ Smart Filter — strategii pregătite</div><div class="bp-smartchips">'+Object.entries(filters).map(([k,f])=>`<button type="button" class="bp-smartchip" data-bpf="${k}">${esc(f.label)}</button>`).join('')+'</div><div class="bp-filter-note">Filtrează automat după probabilitate, cotă, edge, CLV și context.</div></div><div class="bp-filter-result"></div>';
      after.insertAdjacentHTML('afterend',html);
      host.querySelectorAll('.bp-smartchip').forEach(b=>b.addEventListener('click',()=>{activeFilter=b.dataset.bpf; renderSmartFilter();}));
    }
    host.querySelectorAll('.bp-smartchip').forEach(b=>b.classList.toggle('a',b.dataset.bpf===activeFilter));
    const all=(API.signals?.signals||[]).slice().sort(signalSort);
    const f=filters[activeFilter]||filters.all;
    const list=all.filter(f.fn).slice(0,8);
    const result=host.querySelector('.bp-filter-result');
    if(result){
      result.innerHTML=activeFilter==='all'?'':`<div class="bp-basic-list" style="padding:0">${list.length?list.map(renderPick).join(''):'<div class="bp-empty">Niciun meci nu îndeplinește criteriul '+esc(f.label)+'.</div>'}</div>`;
    }
  }

  function patchOldScores(){
    if(typeof window.sigCard==='function' && !window.sigCard.__bpPatched){
      const original=window.sigCard;
      window.sigCard=function(sig){
        sig=Object.assign({},sig,{display_score:marketScore(sig),market_signal_score:marketScore(sig),display_grade:grade(marketScore(sig))});
        return original(sig).replace(/<div class="sig-score"([^>]*)>[^<]*<\/div>\s*<div class="sig-score-lbl">SmartBet<\/div>/,`<div class="sig-score"$1>${marketScore(sig)}</div><div class="sig-score-lbl">Signal</div>`);
      };
      window.sigCard.__bpPatched=true;
    }
  }

  async function loadData(){
    const [signals,clv,context,broadcasts,bsdPreds]=await Promise.all([
      API.signals?Promise.resolve(API.signals):fetchJ('data/signals.json').catch(()=>({signals:[]})),
      API.clv?Promise.resolve(API.clv):fetchJ('data/clv_tracker.json').catch(()=>({summary:{},by_market:{},rolling_30d:{},diagnosis:{}})),
      API.context?Promise.resolve(API.context):fetchJ('data/context_scores.json').catch(()=>({by_event:{}})),
      API.broadcasts?Promise.resolve(API.broadcasts):fetchJ('data/broadcasts.json').catch(()=>({by_event:{}})),
      API.bsdPreds?Promise.resolve(API.bsdPreds):fetchJ('data/bsd_event_predictions.json').catch(()=>({results:[]})),
    ]);
    API.signals=signals; API.clv=clv; API.context=context; API.broadcasts=broadcasts; API.bsdPreds=bsdPreds;
  }
  let renderTimer=null;
  function renderAllSoon(){clearTimeout(renderTimer);renderTimer=setTimeout(()=>{patchOldScores(); injectDashboard(); renderSmartFilter();},140)}
  async function init(){
    injectToggle(); setMode(getMode());
    await loadData().catch(()=>{});
    patchOldScores(); injectDashboard(); renderSmartFilter();
    const mo=new MutationObserver(()=>renderAllSoon());
    ['dash-body','sb-body'].forEach(id=>{const el=$(id); if(el)mo.observe(el,{childList:true});});
    const oldGo=window.go;
    if(typeof oldGo==='function'&&!oldGo.__bpUpgrade){
      window.go=function(tab){const r=oldGo.apply(this,arguments); setTimeout(()=>{injectDashboard(); renderSmartFilter();},160); return r;};
      window.go.__bpUpgrade=true;
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
