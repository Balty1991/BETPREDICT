/**
 * BetPredict — Context Engine UI v1
 * Afișare non-invazivă pentru câmpurile produse de src/context_engine.py.
 * Nu modifică datele, scorurile, cardurile sau motorul Python.
 */
(function(){
  'use strict';
  const VERSION = 'ctx1';

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
      .ctxe-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
      .ctxe-title{font-size:8px;font-weight:900;letter-spacing:.45px;text-transform:uppercase;color:var(--t3)}
      .ctxe-pill{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border-radius:999px;border:1px solid var(--br);font-size:8px;font-weight:900;letter-spacing:.35px;text-transform:uppercase;white-space:nowrap}
      .ctxe-pill.on{background:var(--gd);border-color:rgba(0,232,122,.25);color:var(--green)}
      .ctxe-pill.mid{background:var(--od);border-color:rgba(255,184,48,.25);color:var(--gold)}
      .ctxe-pill.off{background:rgba(255,255,255,.035);border-color:var(--br);color:var(--t2)}
      .ctxe-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin-bottom:8px}
      .ctxe-box{background:rgba(255,255,255,.035);border:1px solid var(--br);border-radius:10px;padding:7px 5px;min-width:0;text-align:center}
      .ctxe-l{font-size:7px;color:var(--t3);font-weight:900;text-transform:uppercase;letter-spacing:.3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .ctxe-v{font-family:'Space Mono',monospace;font-size:12px;font-weight:900;color:var(--text);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .ctxe-v.g{color:var(--green)}.ctxe-v.o{color:var(--gold)}.ctxe-v.b{color:var(--blue)}.ctxe-v.r{color:var(--red)}.ctxe-v.dim{color:var(--t2)}
      .ctxe-strip{display:flex;align-items:center;gap:8px;border:1px solid var(--br);border-radius:10px;background:rgba(255,255,255,.025);padding:8px;margin-bottom:8px}
      .ctxe-gauge{width:42px;height:42px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;background:conic-gradient(var(--green) var(--ctxe-deg,0deg),rgba(255,255,255,.07) 0deg);position:relative}
      .ctxe-gauge:after{content:'';position:absolute;inset:5px;border-radius:50%;background:var(--s1);border:1px solid var(--br)}
      .ctxe-gauge span{position:relative;z-index:1;font-family:'Space Mono',monospace;font-size:10px;font-weight:900;color:var(--green)}
      .ctxe-copy{min-width:0;flex:1}
      .ctxe-main{font-family:'Syne',sans-serif;font-size:13px;font-weight:900;letter-spacing:.1px;text-transform:uppercase;color:var(--text);line-height:1.15}
      .ctxe-sub{font-size:9px;color:var(--t2);line-height:1.35;margin-top:3px}
      .ctxe-row-title{font-size:8px;font-weight:900;letter-spacing:.35px;text-transform:uppercase;color:var(--t3);margin:8px 0 5px}
      .ctxe-chips{display:flex;gap:4px;flex-wrap:wrap}
      .ctxe-chip{display:inline-flex;align-items:center;gap:4px;border:1px solid var(--br);border-radius:999px;padding:3px 7px;font-size:8px;font-weight:900;letter-spacing:.25px;text-transform:uppercase;background:rgba(255,255,255,.025);color:var(--t2)}
      .ctxe-chip.good{border-color:rgba(0,232,122,.22);background:rgba(0,232,122,.055);color:var(--green)}
      .ctxe-chip.warn{border-color:rgba(255,184,48,.22);background:rgba(255,184,48,.055);color:var(--gold)}
      .ctxe-chip.bad{border-color:rgba(255,61,90,.22);background:rgba(255,61,90,.055);color:var(--red)}
      .ctxe-chip.info{border-color:rgba(74,158,255,.22);background:rgba(74,158,255,.055);color:var(--blue)}
      .ctxe-factor-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin-top:6px}
      .ctxe-factor{border:1px solid var(--br);border-radius:9px;background:rgba(255,255,255,.025);padding:7px;min-width:0}
      .ctxe-factor-top{display:flex;align-items:center;justify-content:space-between;gap:5px;margin-bottom:4px}
      .ctxe-factor-name{font-size:8px;font-weight:900;letter-spacing:.3px;text-transform:uppercase;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .ctxe-factor-conf{font-family:'Space Mono',monospace;font-size:9px;font-weight:900;color:var(--blue)}
      .ctxe-factor-line{font-size:8px;color:var(--t3);font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .ctxe-note{font-size:9px;color:var(--t2);line-height:1.35;margin-top:8px;padding:7px;border-radius:9px;background:rgba(255,255,255,.03);border:1px solid var(--br)}
      .ctxe-note b{color:var(--text)}
      @media(max-width:380px){.ctxe-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:5px}.ctxe-factor-grid{grid-template-columns:1fr}.ctxe-main{font-size:12px}.ctxe-strip{padding:7px}.ctxe-gauge{width:38px;height:38px}}
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
    const deg = Math.max(0, Math.min(360, cc*360));
    return `<div class="md-section" id="md-context-engine">
      <div class="ctxe-head"><div class="ctxe-title">Context Engine Matematic</div><span class="ctxe-pill ${pillCls}">${esc(status)}</span></div>
      <div class="ctxe-strip">
        <div class="ctxe-gauge" style="--ctxe-deg:${deg}deg"><span>${esc(pct(cc))}</span></div>
        <div class="ctxe-copy"><div class="ctxe-main">${esc(bestText(p))}</div><div class="ctxe-sub">Contextul ajustează probabilitățile din date deja colectate: formă, H2H, standings/xGd, arbitru, manageri, vreme și odds movement.</div></div>
      </div>
      <div class="ctxe-grid">
        <div class="ctxe-box"><div class="ctxe-l">Context</div><div class="ctxe-v ${cc>0?'g':'dim'}">${esc(pct(cc))}</div></div>
        <div class="ctxe-box"><div class="ctxe-l">SmartBet Base</div><div class="ctxe-v b">${esc(f1(base))}</div></div>
        <div class="ctxe-box"><div class="ctxe-l">SmartBet Nou</div><div class="ctxe-v ${score>=75?'g':score>=60?'b':score>=45?'o':'r'}">${esc(f1(score))}</div></div>
        <div class="ctxe-box"><div class="ctxe-l">Boost</div><div class="ctxe-v ${n(boost,0)>0?'g':'dim'}">${esc(pp(boost))}</div></div>
      </div>
      <div class="ctxe-row-title">Verdicte context</div>
      <div class="ctxe-chips">${renderVerdictChips(p.ctx_verdicts)}</div>
      <div class="ctxe-row-title">Probabilități ajustate</div>
      <div class="ctxe-chips">${renderProbChips(p)}</div>
      <div class="ctxe-row-title">Factori utilizați</div>
      ${renderFactors(p.ctx_factors)}
      <div class="ctxe-note"><b>Regulă sigură:</b> dacă nu există date contextuale, scorul rămâne pe formula de bază. Contextul doar adaugă explicație și boost controlat, nu ascunde meciuri.</div>
    </div>`;
  }

  function install(){
    addCss();
    if(window.__bpContextEngineUiV1) return;
    const prev = window.renderLeagueStrengthBlock;
    if(typeof prev !== 'function') return;
    window.__bpContextEngineUiV1 = true;
    window.renderLeagueStrengthBlock = function(p){
      return renderContextEngineBlock(p) + prev(p);
    };
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once:true});
  else install();
})();
