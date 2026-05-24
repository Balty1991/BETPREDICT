/* perf_dashboard.js — Acuratețe / Performance Dashboard v1.0 */
(function(){
'use strict';

const ML={
  homeWin:'Home Win',draw:'Draw',awayWin:'Away Win',
  btts:'BTTS',over15:'Over 1.5',over25:'Over 2.5',over35:'Over 3.5',
  under25:'Under 2.5',under35:'Under 3.5'
};

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
  <div class="pd-extra"><span style="color:${sysColor};font-weight:900">${esc(sysStatus)}</span><span>Status sistem</span></div>
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

function renderBetsTable(backtest){
  const byMkt=backtest?.out_of_sample?.by_market||{};
  const allBets=[];
  for(const [mkt,data] of Object.entries(byMkt)){
    for(const bet of (data.sample_bets||[])){
      allBets.push({...bet,_mkt:mkt});
    }
  }
  if(!allBets.length)return'<div class="pd-empty">Nicio pariere în backtest.</div>';
  const shown=allBets.slice(0,40);
  const header=`<div class="pd-tr pd-th"><div>Meci</div><div>Piață</div><div>Cotă</div><div>Prob v6</div><div>Rez.</div></div>`;
  const rows=shown.map(b=>{
    const isWin=String(b.result||'').toUpperCase()==='WIN';
    const isLoss=String(b.result||'').toUpperCase()==='LOSS';
    const resultColor=isWin?'#00e87a':isLoss?'#ff3d5a':'var(--t2)';
    const probV6=b.prob_v6!=null?fmtPctPlain(b.prob_v6*100):'—';
    return`<div class="pd-tr">
  <div class="pd-td-match" title="${esc(b.event||'')}">${esc(b.event||'—')}</div>
  <div style="font-size:9px">${esc(mktLabel(b.market||b._mkt||''))}</div>
  <div style="font-family:'Space Mono',monospace;font-size:9px">${fmt2(b.odds)}</div>
  <div style="font-family:'Space Mono',monospace;font-size:9px;color:var(--pur)">${probV6}</div>
  <div style="font-size:9px;font-weight:700;color:${resultColor}">${esc(b.result||'—')}</div>
</div>`;
  }).join('');
  const more=allBets.length>40?`<div class="pd-empty">+${allBets.length-40} pariuri suplimentare omise</div>`:'';
  return`<div class="pd-section-title">📝 Pariuri backtest (${allBets.length})</div>
<div class="pd-table-wrap"><div class="pd-table">${header}${rows}</div></div>${more}`;
}

function renderUpdatedAt(health,thresholds){
  const ts=health?.updated_at||thresholds?.updated_at;
  if(!ts)return'';
  let disp='—';
  try{disp=new Date(ts).toLocaleString('ro-RO');}catch(e){}
  return`<div class="pd-upd">Actualizat: ${esc(disp)}</div>`;
}

/* ── Main entry point ─────────────────────────────────────────────── */
window.loadPerf=async function loadPerf(){
  if(!window.S)window.S={loaded:{}};
  if(!window.S.loaded)window.S.loaded={};
  if(window.S.loaded.perf)return;
  window.S.loaded.perf=1;

  const body=document.getElementById('perf-body');
  if(!body)return;
  body.innerHTML='<div class="loader"><div class="spinner"></div>Se încarcă...</div>';

  const bv=Date.now();
  const fetchJ=url=>fetch(url+'?bpv='+bv,{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(r.status);return r.json();}).catch(()=>null);

  try{
    const [health,thresholds,calibration,backtest]=await Promise.all([
      fetchJ('data/v6_health.json'),
      fetchJ('data/adaptive_thresholds.json'),
      fetchJ('data/calibration_report.json'),
      fetchJ('data/v6_backtest_report.json')
    ]);

    let html='';
    html+=renderKPIRow(health,thresholds,calibration,backtest);
    html+=renderExtraRow(health,thresholds,calibration);
    html+=renderBacktestSummary(backtest);
    html+=renderHealthRow(health);
    html+=renderMarketCharts(thresholds);
    html+=renderMarketStatsTable(thresholds);
    html+=renderCalibrationGrid(calibration);
    html+=renderBetsTable(backtest);
    html+=renderUpdatedAt(health,thresholds);

    body.innerHTML=html;
  }catch(err){
    console.error('[perf_dashboard] Error:',err);
    body.innerHTML='<div class="empty"><div class="ei">⚠</div><div class="et">Eroare la încărcare</div><div class="es">'+esc(String(err))+'</div></div>';
  }
};

})();
