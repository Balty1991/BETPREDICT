/**
 * BetPredict — Context Engine UI v3 Top Compact
 * Afișare compactă/collapsible pentru câmpurile produse de src/context_engine.py.
 * Nu modifică datele, scorurile, cardurile sau motorul Python.
 */
(function(){
  'use strict';
  const VERSION = 'ctx3';

  const FACTOR_LABELS = {
    form: 'Formă',
    h2h: 'H2H',
    xgd: 'Standings/xGd',
    referee: 'Arbitru',
    manager: 'Manageri',
    weather: 'Vreme',
    odds_movement: 'Odds movement'
  };
  const MARKET_LABELS = {
    homeWin: '1',
    draw: 'X',
    awayWin: '2',
    over25: 'O2.5',
    over15: 'O1.5',
    btts: 'BTTS',
    under25: 'U2.5',
    under35: 'U3.5'
  };

  function addCss(){
    if(document.getElementById('bp-context-engine-ui-css')) return;
    const st = document.createElement('style');
    st.id = 'bp-context-engine-ui-css';
    st.textContent = `
      #md-context-engine.ctxe-compact{padding:12px 12px 10px!important;margin-top:10px!important}
      .ctxe-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:7px}
      .ctxe-title{font-size:8px;font-weight:900;letter-spacing:.45px;text-transform:uppercase;color:var(--t3)}
      .ctxe-pill{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border-radius:999px;border:1px solid var(--br);font-size:8px;font-weight:900;letter-spacing:.35px;text-transform:uppercase;white-space:nowrap}
      .ctxe-pill.on{background:var(--gd);border-color:rgba(0,232,122,.25);color:var(--green)}
      .ctxe-pill.mid{background:var(--od);border-color:rgba(255,184,48,.25);color:var(--gold)}
      .ctxe-pill.off{background:rgba(255,255,255,.035);border-color:var(--br);color:var(--t2)}
      .ctxe-summary{display:grid;grid-template-columns:1.08fr .92fr .92fr .92fr;gap:6px;margin-bottom:7px}
      .ctxe-box{background:rgba(255,255,255,.035);border:1px solid var(--br);border-radius:10px;padding:6px 5px;min-width:0;text-align:center}
      .ctxe-l{font-size:7px;color:var(--t3);font-weight:900;text-transform:uppercase;letter-spacing:.3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .ctxe-v{font-family:'Space Mono',monospace;font-size:11px;font-weight:900;color:var(--text);margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .ctxe-v.g{color:var(--green)}.ctxe-v.o{color:var(--gold)}.ctxe-v.b{color:var(--blue)}.ctxe-v.r{color:var(--red)}.ctxe-v.dim{color:var(--t2)}
      .ctxe-quick{display:flex;align-items:center;justify-content:space-between;gap:7px;border:1px solid var(--br);border-radius:10px;background:rgba(255,255,255,.025);padding:7px 8px;margin-bottom:7px}
      .ctxe-main{font-family:'Syne',sans-serif;font-size:12px;font-weight:900;letter-spacing:.1px;text-transform:uppercase;color:var(--text);line-height:1.12;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .ctxe-sub{font-size:8px;color:var(--t2);line-height:1.25;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .ctxe-boost{font-family:'Space Mono',monospace;font-size:11px;font-weight:900;color:var(--green);white-space:nowrap;flex-shrink:0}
      .ctxe-details{border:1px solid var(--br);border-radius:10px;background:rgba(255,255,255,.018);overflow:hidden}
      .ctxe-details summary{list-style:none;cursor:pointer;padding:7px 9px;font-size:8px;font-weight:900;letter-spacing:.35px;text-transform:uppercase;color:var(--blue);display:flex;align-items:center;justify-content:space-between;gap:8px}
      .ctxe-details summary::-webkit-details-marker{display:none}
      .ctxe-details summary:after{content:'+';font-family:'Space Mono',monospace;font-size:12px;color:var(--t2);line-height:1}
      .ctxe-details[open] summary:after{content:'−'}
      .ctxe-details-body{padding:0 8px 8px}
      .ctxe-row-title{font-size:8px;font-weight:900;letter-spacing:.35px;text-transform:uppercase;color:var(--t3);margin:7px 0 5px}
      .ctxe-chips{display:flex;gap:4px;flex-wrap:wrap}
      .ctxe-chip{display:inline-flex;align-items:center;gap:4px;border:1px solid var(--br);border-radius:999px;padding:3px 7px;font-size:8px;font-weight:900;letter-spacing:.25px;text-transform:uppercase;background:rgba(255,255,255,.025);color:var(--t2)}
      .ctxe-chip.good{border-color:rgba(0,232,122,.22);background:rgba(0,232,122,.055);color:var(--green)}
      .ctxe-chip.warn{border-color:rgba(255,184,48,.22);background:rgba(255,184,48,.055);color:var(--gold)}
      .ctxe-chip.bad{border-color:rgba(255,61,90,.22);background:rgba(255,61,90,.055);color:var(--red)}
      .ctxe-chip.info{border-color:rgba(74,158,255,.22);background:rgba(74,158,255,.055);color:var(--blue)}
      .ctxe-factor-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px;margin-top:5px}
      .ctxe-factor{border:1px solid var(--br);border-radius:9px;background:rgba(255,255,255,.025);padding:6px;min-width:0}
      .ctxe-factor-top{display:flex;align-items:center;justify-content:space-between;gap:5px;margin-bottom:3px}
      .ctxe-factor-name{font-size:8px;font-weight:900;letter-spacing:.3px;text-transform:uppercase;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .ctxe-factor-conf{font-family:'Space Mono',monospace;font-size:9px;font-weight:900;color:var(--blue)}
      .ctxe-factor-conf.good{color:var(--green)}.ctxe-factor-conf.warn{color:var(--gold)}.ctxe-factor-conf.bad{color:var(--red)}
      .ctxe-factor-line{font-size:8px;color:var(--t3);font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .ctxe-note{font-size:8.5px;color:var(--t2);line-height:1.3;margin-top:7px;padding:6px;border-radius:9px;background:rgba(255,255,255,.03);border:1px solid var(--br)}
      .ctxe-note b{color:var(--text)}
      @media(max-width:390px){
        #md-context-engine.ctxe-compact{padding:10px 10px 8px!important}
        .ctxe-summary{grid-template-columns:repeat(4,minmax(0,1fr));gap:4px}
        .ctxe-box{padding:5px 3px;border-radius:9px}
        .ctxe-v{font-size:10px}.ctxe-l{font-size:6.6px}
        .ctxe-main{font-size:11px}.ctxe-sub{font-size:7.5px}.ctxe-boost{font-size:10px}
        .ctxe-factor-grid{grid-template-columns:1fr}
      }
    `;
    document.head.appendChild(st);
  }

  function esc(v){
    if(typeof window.esc === 'function') return window.esc(v);
    return String(v ?? '—').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }
  function n(v,def=null){
    if(v===null || v===undefined || v==='') return def;
    const x = Number(v);
    return Number.isFinite(x) ? x : def;
  }
  function f1(v){
    const x=n(v,null);
    if(x===null) return '—';
    return Number.isInteger(x) ? String(x) : x.toFixed(1);
  }
  function f2(v){
    const x=n(v,null);
    if(x===null) return '—';
    return x.toFixed(2);
  }
  function pct(v){
    const x=n(v,null);
    if(x===null) return '—';
    return x<=1 ? `${Math.round(x*100)}%` : `${Math.round(x)}%`;
  }
  function pp(v){
    const x=n(v,null);
    if(x===null) return '—';
    return `${x>0?'+':''}${x.toFixed(2)}`;
  }
  function prob(v){
    const x=n(v,null);
    if(x===null) return '—';
    return `${Math.round(x*100)}%`;
  }
  function confClass(cc){
    cc=n(cc,0)||0;
    if(cc>=0.55) return 'on';
    if(cc>0) return 'mid';
    return 'off';
  }
  function verdictClass(v){
    v=String(v||'').toUpperCase();
    if(v==='PARIAZA') return 'good';
    if(v==='RISC') return 'warn';
    return 'bad';
  }
  function scoreClass(score){
    score=n(score,0)||0;
    if(score>=75) return 'g';
    if(score>=60) return 'b';
    if(score>=45) return 'o';
    return 'r';
  }
  function bestText(p){
    const best=p?.ctx_best_verdict;
    if(!best) return 'fără verdict principal';
    return MARKET_LABELS[best] || best;
  }
  function hasContext(p){
    return !!(p && (p._context_engine || p.context_confidence!==undefined || p.ctx_verdicts || p.ctx_factors));
  }
  function factorLine(f){
    const parts=[];
    if(n(f?.m_H,null)!==null) parts.push(`1×${f2(f.m_H)}`);
    if(n(f?.m_D,null)!==null) parts.push(`X×${f2(f.m_D)}`);
    if(n(f?.m_A,null)!==null) parts.push(`2×${f2(f.m_A)}`);
    return parts.length ? parts.join(' · ') : 'fără 1X2 direct';
  }
  function renderFactors(factors){
    if(!factors || typeof factors!=='object') return '<div class="ctxe-note">Nu există breakdown pe factori pentru această predicție.</div>';
    const rows=Object.entries(factors).filter(([,v])=>v && typeof v==='object');
    if(!rows.length) return '<div class="ctxe-note">Nu există breakdown pe factori pentru această predicție.</div>';
    return `<div class="ctxe-factor-grid">${rows.map(([k,v])=>{
      const c=n(v.conf,0)||0;
      const cls=c>=0.55?'good':c>0?'warn':'bad';
      return `<div class="ctxe-factor">
        <div class="ctxe-factor-top"><div class="ctxe-factor-name">${esc(FACTOR_LABELS[k]||k)}</div><div class="ctxe-factor-conf ${cls}">${esc(pct(c))}</div></div>
        <div class="ctxe-factor-line">${esc(factorLine(v))}</div>
      </div>`;
    }).join('')}</div>`;
  }
  function renderVerdictChips(verdicts){
    if(!verdicts || typeof verdicts!=='object') return '<span class="ctxe-chip bad">fără verdicte context</span>';
    const priority = Object.entries(verdicts).filter(([,v])=>String(v).toUpperCase()==='PARIAZA');
    const risk = Object.entries(verdicts).filter(([,v])=>String(v).toUpperCase()==='RISC');
    const chosen = priority.length ? priority : risk.slice(0,4);
    if(!chosen.length) return '<span class="ctxe-chip bad">toate piețele EVITĂ</span>';
    return chosen.slice(0,6).map(([k,v])=>`<span class="ctxe-chip ${verdictClass(v)}">${esc(MARKET_LABELS[k]||k)} · ${esc(v)}</span>`).join('');
  }
  function renderProbChips(p){
    const items = [
      ['1', p.ctx_home_win], ['X', p.ctx_draw], ['2', p.ctx_away_win],
      ['O1.5', p.ctx_over15], ['O2.5', p.ctx_over25], ['BTTS', p.ctx_btts], ['U2.5', p.ctx_under25], ['U3.5', p.ctx_under35]
    ].filter(([,v])=>n(v,null)!==null);
    if(!items.length) return '<span class="ctxe-chip bad">probabilități context lipsă</span>';
    return items.map(([k,v])=>`<span class="ctxe-chip info">${esc(k)} ${esc(prob(v))}</span>`).join('');
  }

  function renderContextEngineBlock(p){
    if(!hasContext(p)) return '';
    const cc = n(p.context_confidence,0)||0;
    const base = n(p.smartbet_score_base,null);
    const score = n(p.smartbet_score,null);
    const boost = n(p.smartbet_context_boost,null);
    const pillCls = confClass(cc);
    const status = cc>=0.55 ? 'context puternic' : (cc>0 ? 'context parțial' : 'fără context');
    return `<div class="md-section ctxe-compact" id="md-context-engine">
      <div class="ctxe-head"><div class="ctxe-title">Context Engine Matematic</div><span class="ctxe-pill ${pillCls}">${esc(status)}</span></div>
      <div class="ctxe-summary">
        <div class="ctxe-box"><div class="ctxe-l">Context</div><div class="ctxe-v ${cc>0?'g':'dim'}">${esc(pct(cc))}</div></div>
        <div class="ctxe-box"><div class="ctxe-l">Base</div><div class="ctxe-v b">${esc(f1(base))}</div></div>
        <div class="ctxe-box"><div class="ctxe-l">Nou</div><div class="ctxe-v ${scoreClass(score)}">${esc(f1(score))}</div></div>
        <div class="ctxe-box"><div class="ctxe-l">Boost</div><div class="ctxe-v ${n(boost,0)>0?'g':'dim'}">${esc(pp(boost))}</div></div>
      </div>
      <div class="ctxe-quick">
        <div style="min-width:0"><div class="ctxe-main">${esc(bestText(p))}</div><div class="ctxe-sub">Detalii extinse sub buton; bloc compact pentru telefon.</div></div>
        <div class="ctxe-boost">${esc(pct(cc))}</div>
      </div>
      <details class="ctxe-details">
        <summary>Detalii context + factori</summary>
        <div class="ctxe-details-body">
          <div class="ctxe-row-title">Verdicte context</div>
          <div class="ctxe-chips">${renderVerdictChips(p.ctx_verdicts)}</div>
          <div class="ctxe-row-title">Probabilități ajustate</div>
          <div class="ctxe-chips">${renderProbChips(p)}</div>
          <div class="ctxe-row-title">Factori utilizați</div>
          ${renderFactors(p.ctx_factors)}
          <div class="ctxe-note"><b>Regulă sigură:</b> dacă nu există date contextuale, scorul rămâne pe formula de bază. Contextul adaugă explicație și boost controlat, fără să ascundă meciuri.</div>
        </div>
      </details>
    </div>`;
  }

  function install(){
    addCss();
    window.renderContextEngineBlock = renderContextEngineBlock;
    window.__bpContextEngineUiV3 = true;
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once:true});
  else install();
})();
