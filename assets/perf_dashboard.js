/* perf_dashboard.js — Acuratețe / Performance Dashboard v1.0 */
(function(){
'use strict';

const ML={
  homeWin:'Home Win',draw:'Draw',awayWin:'Away Win',
  btts:'BTTS',over15:'Over 1.5',over25:'Over 2.5',over35:'Over 3.5',
  under25:'Under 2.5',under35:'Under 3.5'
};

let _historyBets=[];
let _historyLimit=80;
let _dailyStats=[];
let _dailyLimit=14;

const SC={GREEN:'#00e87a',YELLOW:'#fbbf24',RED:'#ff3d5a'};

function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function fmt1(v){return(v==null||isNaN(+v))?'—':(+v).toFixed(1);}
function fmt2(v){return(v==null||isNaN(+v))?'—':(+v).toFixed(2);}
function fmt3(v){return(v==null||isNaN(+v))?'—':(+v).toFixed(3);}
function fmtPct(v){return(v==null||isNaN(+v))?'—':(+v>=0?'+':'')+((+v).toFixed(1))+'%';}
function fmtPctPlain(v){return(v==null||isNaN(+v))?'—':(+v).toFixed(1)+'%';}
function mktLabel(k){return ML[k]||k;}

function roiColor(v){
  if(v==null||isNaN(+v))return'var(--t2)';
  return(+v>=0)?'#00e87a':'#ff3d5a';
}
function wrColor(v){
  if(v==null||isNaN(+v))return'var(--t2)';
  return(+v>=55)?'#00e87a':(+v>=45)?'#fbbf24':'#ff3d5a';
}
function statusColor(s){
  if(!s)return'var(--t2)';
  const u=String(s).toUpperCase();
  return SC[u]||'var(--t2)';
}

/* ── SVG bar chart (pure SVG, 300×140 viewBox) ─────────────────────── */
function svgBarChart(items){
  if(!items||!items.length)return'<svg viewBox="0 0 300 140" style="width:100%"><text x="150" y="75" text-anchor="middle" font-size="10" fill="var(--t2)">Fără date</text></svg>';
  const W=300,H=140,PAD_L=8,PAD_R=8,PAD_T=24,PAD_B=28;
  const plotW=W-PAD_L-PAD_R;
  const plotH=H-PAD_T-PAD_B;
  const vals=items.map(i=>+i.value||0);
  const maxV=Math.max(...vals.map(Math.abs),0.01);
  const barW=Math.floor(plotW/items.length)-2;
  const zeroY=PAD_T+plotH/2;
  let bars='';
  let labels='';
  let axisLabels='';
  items.forEach((item,idx)=>{
    const x=PAD_L+idx*(plotW/items.length)+(plotW/items.length-barW)/2;
    const v=+item.value||0;
    const pct=v/maxV;
    const barH=Math.abs(pct)*plotH/2;
    const y=v>=0?zeroY-barH:zeroY;
    const color=item.color||(v>=0?'#00e87a':'#ff3d5a');
    bars+=`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW}" height="${Math.max(barH,1).toFixed(1)}" fill="${esc(color)}" rx="2"/>`;
    const lblY=v>=0?y-3:y+barH+10;
    const sign=v>=0?'+':'';
    labels+=`<text x="${(x+barW/2).toFixed(1)}" y="${lblY.toFixed(1)}" text-anchor="middle" font-size="7" fill="${esc(color)}" font-weight="700">${sign}${fmt1(v)}%</text>`;
    const short=String(item.label||'').replace('Home Win','H.Win').replace('Away Win','A.Win').replace('Over ','O').replace('Under ','U').replace(' ','');
    axisLabels+=`<text x="${(x+barW/2).toFixed(1)}" y="${(H-6).toFixed(1)}" text-anchor="middle" font-size="6.5" fill="var(--t2)">${esc(short)}</text>`;
  });
  const zLine=`<line x1="${PAD_L}" y1="${zeroY.toFixed(1)}" x2="${W-PAD_R}" y2="${zeroY.toFixed(1)}" stroke="var(--br)" stroke-width="0.5"/>`;
  return`<svg viewBox="0 0 ${W} ${H}" style="width:100%;overflow:visible">${zLine}${bars}${labels}${axisLabels}</svg>`;
}

/* ── Calibration mini bar chart ─────────────────────────────────────── */
function svgCalibMini(bins){
  if(!bins||!bins.length)return'<svg viewBox="0 0 200 55" style="width:100%"><text x="100" y="30" text-anchor="middle" font-size="9" fill="var(--t2)">Fără date</text></svg>';
  const W=200,H=55,PAD_L=4,PAD_R=4,PAD_T=14,PAD_B=16;
  const plotW=W-PAD_L-PAD_R;
  const plotH=H-PAD_T-PAD_B;
  const barW=Math.floor(plotW/bins.length)-1;
  let bars='',labels='',axisLbls='';
  bins.forEach((bin,idx)=>{
    const ap=+bin.actual_pct||0;
    const barH=Math.max((ap/100)*plotH,1);
    const x=PAD_L+idx*(plotW/bins.length)+(plotW/bins.length-barW)/2;
    const y=PAD_T+plotH-barH;
    const color=ap>=50?'#00e87a':'#4a9eff';
    bars+=`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW}" height="${barH.toFixed(1)}" fill="${esc(color)}" rx="1"/>`;
    if(ap>0){labels+=`<text x="${(x+barW/2).toFixed(1)}" y="${(y-2).toFixed(1)}" text-anchor="middle" font-size="5.5" fill="${esc(color)}" font-weight="700">${ap.toFixed(0)}%</text>`;}
    axisLbls+=`<text x="${(x+barW/2).toFixed(1)}" y="${(H-2).toFixed(1)}" text-anchor="middle" font-size="5" fill="var(--t2)">${esc(bin.label||'')}</text>`;
  });
  const baseLine=`<line x1="${PAD_L}" y1="${(PAD_T+plotH).toFixed(1)}" x2="${W-PAD_R}" y2="${(PAD_T+plotH).toFixed(1)}" stroke="var(--br)" stroke-width="0.5"/>`;
  return`<svg viewBox="0 0 ${W} ${H}" style="width:100%;overflow:visible">${baseLine}${bars}${labels}${axisLbls}</svg>`;
}

/* ── Sections renderers ─────────────────────────────────────────────── */

function renderKPIRow(health,thresholds,calibration,backtest){
  const overall=thresholds?.overall||{};
  const calib=calibration?.overall||{};
  const oos=backtest?.out_of_sample?.overall||{};
  const wrV=overall.overall_win_rate_pct;
  const nEval=overall.n_total_settled;
  const brierPre=calib.avg_brier_pre;
  const brierPost=calib.avg_brier_post;
  const brierDisp=brierPost!=null?fmt3(brierPost):'—';
  const modelVer=health?.model_version||backtest?.model_version||'—';
  return`<div class="pd-kpi-row">
  <div class="pd-kpi"><div class="pd-kpi-v" style="color:${wrColor(wrV)}">${fmtPctPlain(wrV)}</div><div class="pd-kpi-l">Win Rate %</div></div>
  <div class="pd-kpi"><div class="pd-kpi-v" style="color:var(--blue)">${nEval!=null?nEval:'—'}</div><div class="pd-kpi-l">Evaluat total</div></div>
  <div class="pd-kpi"><div class="pd-kpi-v" style="color:var(--pur)">${brierDisp}</div><div class="pd-kpi-l">Brier score (post-calib)</div></div>
  <div class="pd-kpi"><div class="pd-kpi-v" style="color:var(--gold);font-size:13px">${esc(modelVer)}</div><div class="pd-kpi-l">Versiune model</div></div>
</div>`;
}

function renderExtraRow(health,thresholds,calibration){
  const overall=thresholds?.overall||{};
  const calib=calibration?.overall||{};
  const hs=health?.overall||{};
  const roi=overall.overall_roi_pct;
  const bestMkt=overall.best_market;
  const bestRoi=overall.best_market_roi;
  const brierPre=calib.avg_brier_pre;
  const brierPost=calib.avg_brier_post;
  let brierImprovePct='—';
  if(brierPre!=null&&brierPost!=null&&brierPre>0){
    brierImprovePct=fmtPctPlain(((brierPre-brierPost)/brierPre)*100);
  }
  const sysStatus=hs.status||'—';
  const sysColor=statusColor(sysStatus);
  return`<div class="pd-extra-row">
  <div class="pd-extra"><span style="color:${roiColor(roi)}">${fmtPct(roi)}</span><span>ROI Global</span></div>
  <div class="pd-extra"><span style="color:var(--gold)">${bestMkt?esc(mktLabel(bestMkt)):'—'}${bestRoi!=null?' · '+fmtPct(bestRoi):''}</span><span>Cea mai bună piață</span></div>
  <div class="pd-extra"><span style="color:var(--pur)">${brierImprovePct!=='—'?'+'+brierImprovePct:brierImprovePct}</span><span>Îmbunătățire Brier %</span></div>
  <div class="pd-extra"><span style="color:${sysColor};font-weight:800">${esc(sysStatus)}</span><span>Status sistem</span></div>
</div>`;
}

function renderBacktestSummary(backtest){
  const oos=backtest?.out_of_sample?.overall||{};
  const wrV6=oos.v6_win_rate_pct;
  const roiV6=oos.v6_roi_pct;
  const kept=oos.n_v6_kept;
  const filtered=oos.n_skipped_by_v6;
  return`<div class="pd-section-title">📈 Backtest Out-of-Sample</div>
<div class="pd-bt-grid">
  <div class="pd-bt-card"><div class="pd-bt-v" style="color:${wrColor(wrV6)}">${fmtPctPlain(wrV6)}</div><div class="pd-bt-l">Win Rate v6</div></div>
  <div class="pd-bt-card"><div class="pd-bt-v" style="color:${roiColor(roiV6)}">${fmtPct(roiV6)}</div><div class="pd-bt-l">ROI v6</div></div>
  <div class="pd-bt-card"><div class="pd-bt-v" style="color:var(--blue)">${kept!=null?kept:'—'}</div><div class="pd-bt-l">Pariuri păstrate</div></div>
  <div class="pd-bt-card"><div class="pd-bt-v" style="color:var(--gold)">${filtered!=null?filtered:'—'}</div><div class="pd-bt-l">Filtrate v6</div></div>
</div>`;
}

function renderHealthRow(health){
  const layers=health?.layers||{};
  const order=['ml_ensemble','calibration','adaptive_thresholds','consensus','signals_v6'];
  const layerNames={ml_ensemble:'ML Ensemble',calibration:'Calibration',adaptive_thresholds:'Adaptive Thresholds',consensus:'Consensus',signals_v6:'Signals v6'};
  let html='<div class="pd-section-title">🧠 Status componente ML</div><div class="pd-health-row">';
  for(const key of order){
    const layer=layers[key];
    if(!layer)continue;
    const st=layer.status||'UNKNOWN';
    const col=statusColor(st);
    const issues=(layer.issues||[]).slice(0,3);
    const issuesHtml=issues.map(i=>`<div class="pd-health-issue">⚠ ${esc(i)}</div>`).join('');
    html+=`<div class="pd-health-badge" style="border-color:${col}22;background:${col}0a">
  <div class="pd-health-top">
    <div class="pd-health-dot" style="background:${col}"></div>
    <div class="pd-health-name">${esc(layerNames[key]||key)}</div>
    <div class="pd-health-status" style="color:${col}">${esc(st)}</div>
  </div>${issuesHtml}</div>`;
  }
  html+='</div>';
  return html;
}

function renderMarketCharts(thresholds){
  const byMkt=thresholds?.by_market||{};
  const entries=Object.entries(byMkt).filter(([,v])=>v?.stats?.n>=3);
  if(!entries.length)return'<div class="pd-empty">Fără date de piață disponibile.</div>';

  const wrItems=entries.map(([k,v])=>({label:mktLabel(k),value:v.stats?.win_rate_pct||0,color:wrColor(v.stats?.win_rate_pct)}));
  const roiItems=entries.map(([k,v])=>({label:mktLabel(k),value:v.stats?.roi_pct||0,color:roiColor(v.stats?.roi_pct)}));

  return`<div class="pd-section-title">📊 Performanță per piață</div>
<div class="pd-chart-grid">
  <div class="pd-chart-card"><div class="pd-chart-label">Win Rate % per piață</div>${svgBarChart(wrItems)}</div>
  <div class="pd-chart-card"><div class="pd-chart-label">ROI % per piață</div>${svgBarChart(roiItems)}</div>
</div>`;
}

function renderMarketStatsTable(thresholds){
  const byMkt=thresholds?.by_market||{};
  const entries=Object.entries(byMkt).filter(([,v])=>v?.stats?.n>=1)
    .sort((a,b)=>(b[1].stats?.roi_pct||0)-(a[1].stats?.roi_pct||0));
  if(!entries.length)return'';
  let rows='';
  for(const [k,v] of entries){
    const s=v.stats||{};
    const wr=s.win_rate_pct;
    const roi=s.roi_pct;
    rows+=`<div class="pd-mkt-stat">
  <div class="pd-mkt-name">${esc(mktLabel(k))}</div>
  <div class="pd-mkt-nums">
    <span style="color:${wrColor(wr)}">${fmtPctPlain(wr)} WR</span>
    <span class="pd-mkt-sep">·</span>
    <span class="pd-mkt-n">${s.wins||0}W/${s.losses||0}L (${s.n||0})</span>
    <span class="pd-mkt-sep">·</span>
    <span style="color:${roiColor(roi)}">${fmtPct(roi)} ROI</span>
  </div>
</div>`;
  }
  return`<div class="pd-section-title">📋 Statistici per piață</div><div class="pd-mkt-stats-grid">${rows}</div>`;
}

function renderCalibrationGrid(calibration){
  const markets=calibration?.markets||{};
  const entries=Object.entries(markets);
  if(!entries.length)return'';
  let cards='';
  for(const [key,mkt] of entries){
    const pre=mkt.pre||{};
    const post=mkt.post||{};
    const imp=mkt.improvement||{};
    const curve=mkt.calibration_curve||[];
    const bins=curve.filter(b=>b.n>0&&b.actual_avg!=null).map(b=>({
      label:`${Math.round((b.range_lo||0)*100)}-${Math.round((b.range_hi||0)*100)}`,
      actual_pct:(b.actual_avg||0)*100,
      n:b.n
    }));
    const brierPre=pre.brier;
    const brierPost=post.brier;
    const bias=pre.bias;
    const improved=imp.improved;
    const delta=imp.brier_delta;
    const nSamples=mkt.n_samples||0;
    const brierColor=brierPost!=null&&brierPost<0.2?'#00e87a':brierPost!=null&&brierPost<0.25?'#fbbf24':'#ff3d5a';
    const biasColor=bias!=null&&Math.abs(bias)<0.05?'#00e87a':bias!=null&&Math.abs(bias)<0.1?'#fbbf24':'#ff3d5a';
    const deltaColor=improved?'#00e87a':'#ff3d5a';
    const miniChart=bins.length?svgCalibMini(bins):'';
    cards+=`<div class="pd-calib-card">
  <div class="pd-calib-head"><div class="pd-calib-name">${esc(mktLabel(key))}</div><div class="pd-calib-n">n=${nSamples}</div></div>
  <div class="pd-calib-kpis">
    <div><div class="pd-ck-v" style="color:${brierColor}">${fmt3(brierPost)}</div><div class="pd-ck-l">Brier Post</div></div>
    <div><div class="pd-ck-v" style="color:${biasColor}">${bias!=null?(+bias>=0?'+':'')+fmt3(bias):'—'}</div><div class="pd-ck-l">Bias</div></div>
    <div><div class="pd-ck-v" style="color:${deltaColor}">${delta!=null?((improved?'−':'+')+(Math.abs(delta)).toFixed(3)):'—'}</div><div class="pd-ck-l">ΔBrier</div></div>
  </div>${miniChart}</div>`;
  }
  return`<div class="pd-section-title">🎯 Calibrare per piață</div><div class="pd-calib-grid">${cards}</div>`;
}

function renderDailyStats(journal){
  const raw=(journal?.results||[]).filter(r=>r.status==='settled'&&r.result);
  if(!raw.length)return'';
  // Deduplicate same event+market from multiple strategies
  const dedupMap=new Map();
  for(const r of raw){
    const k=String(r.event_id||r.home_team+'_'+r.away_team)+'|'+(r.market_canonical||r.market||'');
    if(!dedupMap.has(k))dedupMap.set(k,r);
  }
  const settled=[...dedupMap.values()];
  const byDay=new Map();
  for(const b of settled){
    const k=histDateKey(b.event_date);
    if(!k)continue;
    if(!byDay.has(k))byDay.set(k,{n:0,w:0,l:0,profit:0,stake:0,ts:new Date(b.event_date).getTime()});
    const d=byDay.get(k);
    const odds=+b.odds||0;
    const isWin=b.result==='WIN';
    d.n++;
    d.stake+=1;
    if(isWin){d.w++;d.profit+=(odds>0?odds-1:0);}
    else{d.l++;d.profit+=-1;}
  }
  const days=[...byDay.entries()].map(([k,v])=>({date:k,...v})).sort((a,b)=>b.ts-a.ts);
  const totals=days.reduce((acc,d)=>({n:acc.n+d.n,w:acc.w+d.w,l:acc.l+d.l,profit:acc.profit+d.profit,stake:acc.stake+d.stake}),{n:0,w:0,l:0,profit:0,stake:0});
  const initialLimit=14;
  _dailyStats=days;
  _dailyLimit=initialLimit;
  const rows=renderDailyRows(days,initialLimit);
  const moreLine=days.length>initialLimit?`<div class="pd-empty">+${days.length-initialLimit} zile · <button id="pd-day-show-all" type="button" class="pd-link">Vezi toate</button></div>`:'';
  const totalsWinPct=totals.n>0?(totals.w/totals.n*100):null;
  const totalsRoi=totals.stake>0?(totals.profit/totals.stake*100):null;
  const totalsRow=`<div class="pd-tr pd-day-totals"><div>TOTAL</div><div style="font-family:var(--ff-mono)">${totals.n}</div><div style="font-family:var(--ff-mono);color:#00e87a">${totals.w}</div><div style="font-family:var(--ff-mono);color:#ff3d5a">${totals.l}</div><div style="font-family:var(--ff-mono);color:${wrColor(totalsWinPct)}">${fmtPctPlain(totalsWinPct)}</div><div style="font-family:var(--ff-mono);color:${roiColor(totalsRoi)};font-weight:800">${fmtPct(totalsRoi)}</div><div style="font-family:var(--ff-mono);color:${roiColor(totals.profit)}">${totals.profit>=0?'+':''}${totals.profit.toFixed(2)} u</div></div>`;
  const header=`<div class="pd-tr pd-th pd-day-th"><div>Data</div><div>Total</div><div>W</div><div>L</div><div>Win%</div><div>ROI%</div><div>P/L</div></div>`;
  return`<div class="pd-section-title">📊 Statistici per zi (${days.length} zile)</div>
<div class="pd-day-note">Calculat la 1 unitate/pariu · ROI = profit / total mizat</div>
<div class="pd-table-wrap"><div class="pd-table pd-table-daily">${header}${totalsRow}<div id="pd-day-rows">${rows}</div></div></div>
<div id="pd-day-more">${moreLine}</div>`;
}

function renderDailyRows(days,limit){
  const showAll=limit==='all'||limit>=days.length;
  const slice=showAll?days:days.slice(0,limit);
  return slice.map(d=>{
    const winPct=d.n>0?(d.w/d.n*100):null;
    const roi=d.stake>0?(d.profit/d.stake*100):null;
    return`<div class="pd-tr">
  <div style="font-family:var(--ff-mono);font-size:9px">${esc(d.date)}</div>
  <div style="font-family:var(--ff-mono)">${d.n}</div>
  <div style="font-family:var(--ff-mono);color:#00e87a">${d.w}</div>
  <div style="font-family:var(--ff-mono);color:#ff3d5a">${d.l}</div>
  <div style="font-family:var(--ff-mono);color:${wrColor(winPct)}">${fmtPctPlain(winPct)}</div>
  <div style="font-family:var(--ff-mono);color:${roiColor(roi)};font-weight:800">${fmtPct(roi)}</div>
  <div style="font-family:var(--ff-mono);color:${roiColor(d.profit)}">${d.profit>=0?'+':''}${d.profit.toFixed(2)} u</div>
</div>`;
  }).join('');
}

function bindDailyShowAll(){
  const btn=document.getElementById('pd-day-show-all');
  if(btn)btn.onclick=()=>{
    _dailyLimit='all';
    const el=document.getElementById('pd-day-rows');
    if(el)el.innerHTML=renderDailyRows(_dailyStats,_dailyLimit);
    const moreEl=document.getElementById('pd-day-more');
    if(moreEl)moreEl.innerHTML='';
  };
}

function bindMatchToggle(){
  const btn=document.getElementById('pd-match-toggle');
  const tbl=document.getElementById('pd-match-table');
  if(!btn||!tbl)return;
  btn.onclick=()=>{
    const opening=tbl.style.display==='none';
    tbl.style.display=opening?'':'none';
    const arrow=btn.querySelector('.pd-section-arrow');
    if(arrow)arrow.textContent=opening?'▲':'▼';
    btn.setAttribute('aria-expanded',String(opening));
    try{localStorage.setItem('pd.match.open',opening?'1':'0');}catch(_){}
  };
}

function renderMatchDetail(journal){
  const settled=(journal?.results||[]).filter(r=>r.status==='settled'&&r.result);
  if(!settled.length)return'<div class="pd-empty">Niciun pariu decontat disponibil.</div>';

  // Sort by date desc, deduplicate by event_id+market (same bet from multiple strategies)
  const dedupMap=new Map();
  for(const r of settled){
    const k=String(r.event_id||r.home_team+'_'+r.away_team)+'|'+(r.market_canonical||r.market||'');
    if(!dedupMap.has(k))dedupMap.set(k,r);
  }
  const sorted=[...dedupMap.values()].sort((a,b)=>new Date(b.event_date)-new Date(a.event_date));
  _historyBets=sorted;
  _historyLimit=80;

  // Group by event_id for the score-summary view (top compact block)
  const byEv=new Map();
  for(const b of sorted){
    const k=String(b.event_id||b.home_team+'_'+b.away_team);
    if(!byEv.has(k))byEv.set(k,{home:b.home_team,away:b.away_team,league:b.league,date:b.event_date,score:b.score_ft||'?',actual1x2:b.actual_1x2,btts:b.actual_btts,bets:[]});
    byEv.get(k).bets.push(b);
  }
  const events=Array.from(byEv.values()).sort((a,b2)=>new Date(b2.date)-new Date(a.date));

  // Score + checkmarks table (Grafana style)
  const MKTS=[['homeWin','Win'],['over15','O1.5'],['over25','O2.5'],['under35','U3.5'],['btts','BTTS']];
  const evRows=events.slice(0,50).map(ev=>{
    const dateFmt=ev.date?new Date(ev.date).toLocaleString('ro-RO',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'—';
    const checks=MKTS.map(([mkt,lbl])=>{
      const bet=ev.bets.find(b=>b.market_canonical===mkt||b.market===mkt);
      if(!bet)return`<div class="pd-ck pd-ck-na">—</div>`;
      const win=bet.result==='WIN';
      return`<div class="pd-ck ${win?'pd-ck-win':'pd-ck-loss'}" title="${esc(mkt)}">${win?'✓':'✗'}</div>`;
    }).join('');
    const confBet=ev.bets.find(b=>b.model_probability);
    const conf=confBet?fmtPctPlain(confBet.model_probability*100):'—';
    return`<div class="pd-ev-row">
  <div class="pd-ev-info">
    <div class="pd-ev-score">${esc(ev.score)}</div>
    <div class="pd-ev-meta"><span class="pd-ev-match">${esc(ev.home)}–${esc(ev.away)}</span><span class="pd-ev-lg">${esc(ev.league||'—')}</span><span class="pd-ev-date">${dateFmt}</span></div>
  </div>
  <div class="pd-ev-conf">${conf}</div>
  <div class="pd-ev-checks">${checks}</div>
</div>`;
  }).join('');

  const evHeader=`<div class="pd-ev-hdr">
  <div class="pd-ev-info"><span>Meci · Scor</span></div>
  <div class="pd-ev-conf">Prob</div>
  <div class="pd-ev-checks">${MKTS.map(([,l])=>`<div class="pd-ck-hdr">${l}</div>`).join('')}</div>
</div>`;

  // Filter options
  const uniqueDates=[...new Set(sorted.map(b=>histDateKey(b.event_date)).filter(Boolean))];
  const uniqueLeagues=[...new Set(sorted.map(b=>b.league).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ro'));
  const uniqueMarkets=[...new Set(sorted.map(b=>b.market_label||b.market).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ro'));
  const filterBar=`<div class="pd-filter-bar">
    <select id="pd-flt-date" aria-label="Filtru dată"><option value="">📅 Toate datele</option>${uniqueDates.map(d=>`<option value="${esc(d)}">${esc(d)}</option>`).join('')}</select>
    <select id="pd-flt-league" aria-label="Filtru ligă"><option value="">🏆 Toate ligile</option>${uniqueLeagues.map(l=>`<option value="${esc(l)}">${esc(l)}</option>`).join('')}</select>
    <select id="pd-flt-market" aria-label="Filtru piață"><option value="">📊 Toate piețele</option>${uniqueMarkets.map(m=>`<option value="${esc(m)}">${esc(m)}</option>`).join('')}</select>
    <select id="pd-flt-result" aria-label="Filtru rezultat"><option value="">✓ Toate</option><option value="WIN">WIN</option><option value="LOST">LOST</option></select>
    <input id="pd-flt-search" type="search" placeholder="🔎 Caută echipă..." aria-label="Caută echipă">
    <button id="pd-flt-reset" type="button">↺ Reset</button>
  </div>`;

  const betHeader=`<div class="pd-tr pd-th"><div>Data</div><div>Ligă</div><div>Meci</div><div>Piață</div><div>Cotă</div><div>Prob</div><div>Scor</div><div>Rez.</div></div>`;
  const initial=renderHistoryRows(sorted,_historyLimit);

  const evOpen=localStorage.getItem('pd.match.open')==='1';
  return`<button type="button" class="pd-section-toggle" id="pd-match-toggle" aria-expanded="${evOpen}">📋 Match Detail — ${sorted.length} pariuri decontate<span class="pd-section-arrow">${evOpen?'▲':'▼'}</span></button>
<div class="pd-ev-table" id="pd-match-table" style="${evOpen?'':'display:none'}">${evHeader}${evRows}</div>
<div class="pd-section-title" style="margin-top:16px">📅 Istoric complet pariuri (<span id="pd-hist-count">${sorted.length}</span>/${sorted.length})</div>
${filterBar}
<div class="pd-table-wrap"><div class="pd-table pd-table-detail">${betHeader}<div id="pd-hist-rows">${initial.rows}</div></div></div><div id="pd-hist-more">${initial.more}</div>`;
}

function histDateKey(iso){
  if(!iso)return '';
  try{return new Date(iso).toLocaleDateString('ro-RO',{day:'2-digit',month:'2-digit',year:'numeric'});}catch{return '';}
}

function renderHistoryRows(bets,limit){
  const total=bets.length;
  const showAll=limit==='all'||limit>=total;
  const slice=showAll?bets:bets.slice(0,limit);
  const rows=slice.map(b=>{
    const isWin=b.result==='WIN';
    const rc=isWin?'#00e87a':'#ff3d5a';
    const dateFmt=b.event_date?new Date(b.event_date).toLocaleString('ro-RO',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'—';
    const score=b.score_ft||'—';
    return`<div class="pd-tr">
  <div class="pd-td-date">${dateFmt}</div>
  <div class="pd-td-lg">${esc((b.league||'—').substring(0,14))}</div>
  <div class="pd-td-match" title="${esc(b.home_team+' vs '+b.away_team)}">${esc(b.home_team||'—')} – ${esc(b.away_team||'—')}</div>
  <div>${esc(b.market_label||b.market||'—')}</div>
  <div style="font-family:var(--ff-mono);color:var(--pur)">${fmt2(b.odds)}</div>
  <div style="font-family:var(--ff-mono)">${fmtPctPlain((b.model_probability||0)*100)}</div>
  <div style="font-family:var(--ff-mono);font-weight:700">${score}</div>
  <div style="color:${rc};font-weight:800">${b.result||'—'}</div>
</div>`;
  }).join('');
  const remaining=total-slice.length;
  const more=remaining>0?`<div class="pd-empty">+${remaining} înregistrări suplimentare · <button id="pd-show-all" type="button" class="pd-link">Vezi toate</button></div>`:(total===0?'<div class="pd-empty">Niciun rezultat pentru filtrele curente.</div>':'');
  return {rows,more};
}

function applyHistoryFilters(){
  const v=id=>{const el=document.getElementById(id);return el?String(el.value||''):'';};
  const dFlt=v('pd-flt-date');
  const lFlt=v('pd-flt-league');
  const mFlt=v('pd-flt-market');
  const rFlt=v('pd-flt-result');
  const qFlt=v('pd-flt-search').toLowerCase().trim();
  const filtered=_historyBets.filter(b=>{
    if(dFlt && histDateKey(b.event_date)!==dFlt)return false;
    if(lFlt && b.league!==lFlt)return false;
    if(mFlt && (b.market_label||b.market||'')!==mFlt)return false;
    if(rFlt && b.result!==rFlt)return false;
    if(qFlt){
      const hay=`${b.home_team||''} ${b.away_team||''}`.toLowerCase();
      if(!hay.includes(qFlt))return false;
    }
    return true;
  });
  const cnt=document.getElementById('pd-hist-count');
  if(cnt)cnt.textContent=filtered.length;
  const rowsEl=document.getElementById('pd-hist-rows');
  const moreEl=document.getElementById('pd-hist-more');
  const out=renderHistoryRows(filtered,_historyLimit);
  if(rowsEl)rowsEl.innerHTML=out.rows;
  if(moreEl)moreEl.innerHTML=out.more;
  bindShowAllBtn();
}

function bindShowAllBtn(){
  const btn=document.getElementById('pd-show-all');
  if(btn)btn.onclick=()=>{_historyLimit='all';applyHistoryFilters();};
}

function bindHistoryFilters(){
  ['pd-flt-date','pd-flt-league','pd-flt-market','pd-flt-result'].forEach(id=>{
    const el=document.getElementById(id);
    if(el)el.addEventListener('change',applyHistoryFilters);
  });
  const search=document.getElementById('pd-flt-search');
  if(search)search.addEventListener('input',()=>{
    clearTimeout(window._pdSearchDeb);
    window._pdSearchDeb=setTimeout(applyHistoryFilters,150);
  });
  const reset=document.getElementById('pd-flt-reset');
  if(reset)reset.onclick=()=>{
    ['pd-flt-date','pd-flt-league','pd-flt-market','pd-flt-result'].forEach(id=>{const el=document.getElementById(id);if(el)el.value='';});
    const s=document.getElementById('pd-flt-search');if(s)s.value='';
    _historyLimit=80;
    applyHistoryFilters();
  };
  bindShowAllBtn();
}

function renderUpdatedAt(health,thresholds){
  const ts=health?.updated_at||thresholds?.updated_at;
  if(!ts)return'';
  let disp='—';
  try{disp=new Date(ts).toLocaleString('ro-RO');}catch(e){}
  return`<div class="pd-upd">Actualizat: ${esc(disp)}</div>`;
}

/* ── Main entry point ─────────────────────────────────────────────── */
function skeletonHTML(){
  return `<div class="pd-skel">
    <div class="pd-skel-row tall"></div>
    <div class="pd-skel-row"></div>
    <div class="pd-skel-row tall"></div>
    <div class="pd-skel-row"></div>
    <div class="pd-skel-row tall"></div>
  </div>`;
}

window.loadPerf=async function loadPerf(force){
  if(!window.S)window.S={loaded:{}};
  if(!window.S.loaded)window.S.loaded={};
  if(window.S.loaded.perf && !force)return;
  window.S.loaded.perf=1;

  const body=document.getElementById('perf-body');
  if(!body)return;
  body.innerHTML=skeletonHTML();

  const bv=Date.now();
  const fetchJ=url=>fetch(url+'?bpv='+bv,{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(r.status);return r.json();}).catch(()=>null);

  try{
    const [health,thresholds,calibration,backtest,journal]=await Promise.all([
      fetchJ('data/v6_health.json'),
      fetchJ('data/adaptive_thresholds.json'),
      fetchJ('data/calibration_report.json'),
      fetchJ('data/v6_backtest_report.json'),
      fetchJ('data/selection_journal.json')
    ]);

    // Empty-state guards per section: data files exist dar pot fi goale
    if(!health && !thresholds && !calibration && !backtest && !journal){
      throw new Error('niciun fișier de date disponibil');
    }

    let html='';
    html+=renderKPIRow(health,thresholds,calibration,backtest);
    html+=renderExtraRow(health,thresholds,calibration);
    html+=renderBacktestSummary(backtest);
    html+=renderHealthRow(health);
    html+=renderMarketCharts(thresholds);
    html+=renderMarketStatsTable(thresholds);
    html+=renderCalibrationGrid(calibration);
    html+=renderDailyStats(journal);
    html+=renderMatchDetail(journal);
    html+=renderUpdatedAt(health,thresholds);

    body.innerHTML=html;
    bindHistoryFilters();
    bindDailyShowAll();
    bindMatchToggle();
  }catch(err){
    console.error('[perf_dashboard] Error:',err);
    const updMin=(()=>{try{const t=Number(localStorage.getItem('bp.lastPerfTs')||0);if(!t)return null;return Math.round((Date.now()-t)/60000);}catch(_){return null;}})();
    body.innerHTML=`<div class="pd-err">
      <div class="pd-err-ic">⏳</div>
      <div class="pd-err-t">Datele se sincronizează</div>
      <div class="pd-err-s">${updMin!=null?`Ultima actualizare: ${updMin} min în urmă · `:''}${esc(String(err))}</div>
      <button type="button" class="pd-err-btn" onclick="window.S.loaded.perf=0;window.loadPerf(true);">↻ Reîncearcă</button>
    </div>`;
  }
  try{localStorage.setItem('bp.lastPerfTs',String(Date.now()));}catch(_){}
};

})();
