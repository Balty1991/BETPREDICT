/**
 * BetPredict — League Strength Safety UI (Pasul 3.2 + 3.3)
 * Patch non-invaziv: nu schimbă datele, doar afișarea în analiza completă și badge/bar SmartBet.
 */
(function(){
  'use strict';

  const VERSION = 'pas32';

  function addCss(){
    if(document.getElementById('bp-lss-ui-css')) return;
    const st=document.createElement('style');
    st.id='bp-lss-ui-css';
    st.textContent=`
      .ls-cal-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:7px}
      .ls-cal-title{font-size:8px;font-weight:900;letter-spacing:.45px;text-transform:uppercase;color:var(--t3)}
      .ls-pill{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:999px;border:1px solid var(--br);font-size:8px;font-weight:900;letter-spacing:.35px;text-transform:uppercase;white-space:nowrap}
      .ls-pill.full{background:var(--gd);border-color:rgba(0,232,122,.25);color:var(--green)}
      .ls-pill.partial{background:var(--od);border-color:rgba(255,184,48,.24);color:var(--gold)}
      .ls-pill.off{background:var(--rd);border-color:rgba(255,61,90,.24);color:var(--red)}
      .ls-cal-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-bottom:7px}
      .ls-cal-box{background:rgba(255,255,255,.035);border:1px solid var(--br);border-radius:9px;padding:6px 5px;min-width:0;text-align:center}
      .ls-cal-l{font-size:7px;color:var(--t3);font-weight:900;text-transform:uppercase;letter-spacing:.3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .ls-cal-v{font-family:'Space Mono',monospace;font-size:11px;font-weight:900;color:var(--text);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .ls-cal-v.g{color:var(--green)}.ls-cal-v.o{color:var(--gold)}.ls-cal-v.b{color:var(--blue)}.ls-cal-v.r{color:var(--red)}
      .ls-adj{display:grid;grid-template-columns:62px repeat(3,1fr);gap:4px;align-items:center;margin:6px 0}
      .ls-adj-l{font-size:8px;font-weight:900;text-transform:uppercase;letter-spacing:.35px;color:var(--t3)}
      .ls-adj-c{font-family:'Space Mono',monospace;font-size:10px;font-weight:900;text-align:center;border:1px solid var(--br);border-radius:7px;background:rgba(255,255,255,.035);padding:4px 3px;color:var(--text)}
      .ls-adj-c.pos{color:var(--green)}.ls-adj-c.neg{color:var(--red)}.ls-adj-c.neu{color:var(--t2)}
      .ls-reason{font-size:9px;color:var(--t2);line-height:1.35;margin:-1px 0 6px;padding:6px 7px;border-radius:8px;background:rgba(255,255,255,.03);border:1px solid var(--br)}
      .ls-reason b{color:var(--text)}
      .sbs.sbs-risk-high{background:rgba(255,61,90,.035)}
      .sbs-status{font-size:8px;font-weight:900;text-transform:uppercase;letter-spacing:.35px;min-width:48px;text-align:right;white-space:nowrap}
      @media(max-width:380px){.ls-cal-grid{gap:5px}.ls-adj{grid-template-columns:52px repeat(3,1fr)}.ls-adj-c{font-size:9px;padding:4px 2px}.sbs-status{display:none}}
    `;
    document.head.appendChild(st);
  }

  function e(v){
    if(typeof window.esc==='function') return window.esc(v);
    return String(v ?? '—').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }
  function n(v,def=null){
    if(v===null||v===undefined||v==='') return def;
    const x=Number(v);
    return Number.isFinite(x)?x:def;
  }
  function pp(v){
    const x=n(v,0);
    return `${x>0?'+':''}${x.toFixed(2)}pp`;
  }
  function ppClass(v){
    const x=n(v,0);
    return x>0.005?'pos':(x<-0.005?'neg':'neu');
  }
  function pctScale(v){
    const x=n(v,0);
    return `${Math.round(x*100)}%`;
  }
  function statusFromScale(scale){
    const s=n(scale,0);
    if(s>=0.999) return {label:'activ',cls:'full'};
    if(s>0) return {label:'redus',cls:'partial'};
    return {label:'oprit',cls:'off'};
  }
  function reasonLabel(reason){
    const map={
      competition_unreliable_type:'competiție instabilă / cupă / friendly',
      sample_unknown:'sample necunoscut — influență redusă',
      sample_under_4:'sample sub 4 meciuri — oprit',
      sample_4_to_7_partial:'sample 4–7 meciuri — 50%',
      sample_8_plus_full:'sample 8+ meciuri — complet'
    };
    return map[reason] || String(reason || 'calibrare disponibilă');
  }
  function signedStrength(v){
    const x=n(v,null);
    if(x===null) return '—';
    return `${x>0?'+':''}${x}`;
  }

  window.sbsColor=function(s){
    const x=n(s,0);
    return x>=75?'var(--green)':x>=60?'var(--blue)':x>=45?'var(--gold)':'var(--red)';
  };
  window.sbsStatus=function(s){
    const x=n(s,0);
    if(x>=75) return 'puternic';
    if(x>=60) return 'ok';
    if(x>=45) return 'watch';
    return 'avoid';
  };
  window.sbsClass=function(s){
    const x=n(s,0);
    if(x>=75) return 'sbs-strong';
    if(x>=60) return 'sbs-ok';
    if(x>=45) return 'sbs-watch';
    return 'sbs-risk-high';
  };
  window.gradeBadge=function(g){
    if(!g||g==='—') return '';
    const txt=String(g).trim().toUpperCase();
    const letter=(txt.match(/[A-E]/)||['E'])[0];
    return `<span class="grade g${letter}">${e(txt)}</span>`;
  };

  window.renderLeagueStrengthBlock=function(p){
    const ls=p?.league_strength||{};
    if(!ls.available) return '';
    const h=ls.home||{}, a=ls.away||{};
    const adj=ls.adjustment_pp||{};
    const raw=ls.raw_adjustment_pp||{};
    const cal=ls.calibration||{};
    const safety=p?.league_strength_safety||{};
    const scale=n(cal.scale, n(safety.scale, null));
    const reason=cal.reason || safety.reason || 'sample_unknown';
    const sampleMin=cal.sample_min ?? safety.sample_min ?? '—';
    const st=statusFromScale(scale);
    const delta=n(ls.delta_strength,0);
    const side=delta>=4?'Avantaj acasă':(delta<=-4?'Avantaj deplasare':'Echilibru');
    const leagueSize=ls.league_size ?? '—';
    const source=ls.source || 'league_metadata';
    const season=ls.season_name || ls.season_id || 'curent';

    return `<div class="md-section"><div class="md-section-title">Standings Strength Engine <span class="ls-pill ${st.cls}">${e(st.label)}</span></div>
      <div class="ls-cal-head"><div class="ls-cal-title">Safety Calibration</div><span class="ls-pill ${st.cls}">scale ${scale===null?'—':pctScale(scale)}</span></div>
      <div class="ls-reason"><b>Motiv:</b> ${e(reasonLabel(reason))}</div>
      <div class="ls-cal-grid">
        <div class="ls-cal-box"><div class="ls-cal-l">sample clasament</div><div class="ls-cal-v ${n(sampleMin,0)>=8?'g':n(sampleMin,0)>=4?'o':'r'}">${e(sampleMin)}</div></div>
        <div class="ls-cal-box"><div class="ls-cal-l">cap 1/2</div><div class="ls-cal-v b">±4pp</div></div>
        <div class="ls-cal-box"><div class="ls-cal-l">cap X</div><div class="ls-cal-v b">±2pp</div></div>
      </div>
      <div class="ls-adj">
        <div class="ls-adj-l">Final</div>
        <div class="ls-adj-c ${ppClass(adj.home)}">1 ${pp(adj.home)}</div>
        <div class="ls-adj-c ${ppClass(adj.draw)}">X ${pp(adj.draw)}</div>
        <div class="ls-adj-c ${ppClass(adj.away)}">2 ${pp(adj.away)}</div>
      </div>
      <div class="ls-adj">
        <div class="ls-adj-l">Brut</div>
        <div class="ls-adj-c ${ppClass(raw.home)}">1 ${pp(raw.home)}</div>
        <div class="ls-adj-c ${ppClass(raw.draw)}">X ${pp(raw.draw)}</div>
        <div class="ls-adj-c ${ppClass(raw.away)}">2 ${pp(raw.away)}</div>
      </div>
      <div class="md-kpis" style="margin-top:7px">
        <div class="md-kpi"><div class="md-kpi-l">${e(h.team_name||'Acasă')}</div><div class="md-kpi-v g">${e(ls.home_strength??'—')}</div></div>
        <div class="md-kpi"><div class="md-kpi-l">Delta</div><div class="md-kpi-v ${delta>=4?'g':delta<=-4?'r':'o'}">${signedStrength(ls.delta_strength)}</div></div>
        <div class="md-kpi"><div class="md-kpi-l">${e(a.team_name||'Deplasare')}</div><div class="md-kpi-v b">${e(ls.away_strength??'—')}</div></div>
      </div>
      <div class="md-row"><div class="md-row-l">Clasament</div><div class="md-row-v">${e(h.position||'—')}/${e(leagueSize)} vs ${e(a.position||'—')}/${e(leagueSize)}</div></div>
      <div class="md-row"><div class="md-row-l">PPG / GD</div><div class="md-row-v b">${e(h.ppg??'—')} / ${e(h.gd??'—')} vs ${e(a.ppg??'—')} / ${e(a.gd??'—')}</div></div>
      <div class="md-note">${e(side)} · sursă ${e(source)} · sezon ${e(season)} · UI ${VERSION}</div>
    </div>`;
  };

  window.predCard=function(p,sigIdx){
    const ev=p.event||{};
    const home=e(ev.home_team||'—'),away=e(ev.away_team||'—');
    const htId=p._home_team_id||ev.home_team_id,atId=p._away_team_id||ev.away_team_id;
    const lid=p._league_id||ev.league_id;
    const lObj=window.leagueObj?leagueObj(p):{};
    const lg=e(window.lgName?lgName(p):ev.league_name),time=window.fmtT?fmtT(ev.event_date):'';
    const probs=window.getProbs?getProbs(p):[p.blended_home,p.blended_draw,p.blended_away,false];
    const [pH,pD,pA,isB]=probs;
    const ph=pH!=null?Math.round(pH*100):null,pd=pD!=null?Math.round(pD*100):null,pa=pA!=null?Math.round(pA*100):null;
    const mx=ph!=null?Math.max(ph,pd??-1,pa??-1):-1,bi=mx<0?-1:[ph,pd,pa].indexOf(mx);
    const rec=e(p.recommended_bet||'');
    const o15=p.poisson_over15||p.over_15_probability,o25=p.poisson_over25||p.over_25_probability;
    const u35=p.poisson_under35||p.under_35_probability,btts=p.poisson_btts||p.btts_probability;
    const score=p.most_likely_score,topScores=p.top_scores||[];
    const sbRaw=n(p.smartbet_score,null);
    const hasSb=sbRaw!==null;
    const sbScore=hasSb?Math.max(0,Math.min(100,sbRaw)):0;
    const grade=p.quality_grade||'';
    const eid=String(ev.id||'');const matchSigs=(sigIdx&&sigIdx[eid])||[];
    const ctx=window.ctxFor?ctxFor(eid):null;
    const delta=p.poisson_delta;const conf=p.confidence;

    return`
    <div class="card">
      <div class="card-top">
        <div class="card-lg">
          ${window.leagueLogo?leagueLogo(lid):''}
          ${gradeBadge(grade)}
          <span>${lg}</span>
          ${delta!=null&&Math.abs(delta)>5?`<span class="delta ${delta>0?'dv':'dr'}">${delta>0?'▲':'▼'}${Math.abs(delta).toFixed(1)}pp</span>`:''}
        </div>
        <span class="card-time">${time}</span>
      </div>
      ${window.leagueStrip?leagueStrip(lObj):''}
      <div class="card-teams">
        <div class="ct-wrap">
          ${window.teamLogo?teamLogo(htId):''}
          <div class="ct-name">${home}</div>
        </div>
        <div class="cvs"><span class="vs-t">VS</span>${rec?`<span class="rec">▶ ${rec}</span>`:''}</div>
        <div class="ct-wrap aw">
          ${window.teamLogo?teamLogo(atId):''}
          <div class="ct-name aw">${away}</div>
        </div>
      </div>
      ${ph!=null&&pd!=null&&pa!=null?`
      <div class="prob-row">
        ${[['1',ph],['X',pd],['2',pa]].map(([l,v],i)=>`
          <div class="pc ${i===bi?'best':''}">
            <div class="pl">${l}</div><div class="pp">${v}%</div>
            <div class="pb" style="width:${v}%"></div>
            ${isB?'<div class="blend-dot"></div>':''}
          </div>`).join('')}
      </div>`:`<div style="padding:0 12px 9px;font-size:11px;color:var(--t3)">— fără predicție ML —</div>`}
      ${hasSb?`<div class="sbs ${window.sbsClass(sbScore)}"><span class="sbs-l">SmartBet</span><div class="sbs-tr"><div class="sbs-fi" style="width:${sbScore}%;background:${window.sbsColor(sbScore)}"></div></div><span class="sbs-v" style="color:${window.sbsColor(sbScore)}">${Number.isInteger(sbRaw)?sbRaw:sbRaw.toFixed(1)}</span><span class="sbs-status" style="color:${window.sbsColor(sbScore)}">${window.sbsStatus(sbScore)}</span></div>`:''}
      ${(o15!=null||o25!=null||u35!=null||btts!=null)?`
      <div class="mrow">
        ${o15!=null?`<span class="mt ${+o15>.75?'mt-g':'mt-x'}">O1.5 ${Math.round(+o15*100)}%</span>`:''}
        ${o25!=null?`<span class="mt ${+o25>.60?'mt-o':'mt-x'}">O2.5 ${Math.round(+o25*100)}%</span>`:''}
        ${u35!=null?`<span class="mt ${+u35>.70?'mt-b':'mt-x'}">U3.5 ${Math.round(+u35*100)}%</span>`:''}
        ${btts!=null?`<span class="mt ${+btts>.55?'mt-p':'mt-x'}">BTTS ${Math.round(+btts*100)}%</span>`:''}
      </div>`:''}
      ${ctx&&window.ctxChips?ctxChips(ctx):''}
      <div class="md-open-row"><button class="md-open" onclick="openMatchDetail('${eid}')">Analiză completă</button></div>
      ${score?`<div class="score-row"><span class="score-lbl">Scor probabil</span><span class="score-chip">${e(score)}</span>${topScores.slice(1,3).map(s=>`<span class="score-alt">${e(s.score||'')}</span>`).join('')}</div>`:''}
      ${ctx&&window.ctxPanel?ctxPanel(ctx):''}
      ${matchSigs.length&&window.STRAT_META?`<div class="strats-row">${matchSigs.slice(0,3).map(sig=>{const m=STRAT_META[sig.strategy]||{};return`<span class="strat-tag" style="background:${m.color||'var(--gd)'}18;color:${m.color||'var(--green)'};border-color:${m.color||'var(--green)'}33">${m.icon||''} ${e(sig.strategy_label||'')} ${sig.adj_prob}%</span>`;}).join('')}</div>`:''}
      ${conf!=null?`<div class="conf-row"><span class="cl">Încredere</span><div class="ctr"><div class="cf" style="width:${Math.round(conf*100)}%"></div></div><span class="cv">${Math.round(conf*100)}%</span></div>`:''}
    </div>`;
  };

  const oldRenderMatchDetail=window.renderMatchDetail;
  if(typeof oldRenderMatchDetail==='function'){
    window.renderMatchDetail=function(eid){
      const html=oldRenderMatchDetail(eid);
      const p=window.findPred?findPred(eid):null;
      const sb=n(p?.smartbet_score,null);
      if(sb===null) return html;
      const shown=Number.isInteger(sb)?String(sb):sb.toFixed(1);
      return html.replace(/<div class="md-kpi"><div class="md-kpi-l">SmartBet<\/div><div class="md-kpi-v g">.*?<\/div><\/div>/,
        `<div class="md-kpi"><div class="md-kpi-l">SmartBet</div><div class="md-kpi-v" style="color:${window.sbsColor(sb)}">${shown}</div><div class="md-kpi-l" style="margin-top:2px;color:${window.sbsColor(sb)}">${window.sbsStatus(sb)}</div></div>`);
    };
  }

  addCss();
})();
