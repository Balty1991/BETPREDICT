/**
 * BetPredict — Engine Status UI v1
 * Compact status block pentru analiza completă.
 * Nu modifică scorurile și nu atinge pipeline-ul.
 */
(function(){
  'use strict';
  const VERSION = 'es2';
  let healthPayload = null;
  let healthPromise = null;

  function addCss(){
    if(document.getElementById('bp-engine-status-css')) return;
    const st = document.createElement('style');
    st.id = 'bp-engine-status-css';
    st.textContent = `
      .es-block{border:1px solid var(--br);border-radius:13px;background:linear-gradient(180deg,rgba(255,255,255,.035),rgba(255,255,255,.018));padding:9px;margin-bottom:9px}
      .es-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:7px}
      .es-title{font-size:9px;font-weight:900;text-transform:uppercase;letter-spacing:.45px;color:var(--t3)}
      .es-pill{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;border:1px solid var(--br);background:rgba(255,255,255,.035);font-size:8px;font-weight:900;text-transform:uppercase;letter-spacing:.3px;color:var(--t2);white-space:nowrap}
      .es-pill.g{color:var(--green);border-color:rgba(0,232,122,.25);background:rgba(0,232,122,.06)}
      .es-pill.o{color:var(--gold);border-color:rgba(255,184,48,.25);background:rgba(255,184,48,.06)}
      .es-pill.r{color:var(--red);border-color:rgba(255,74,74,.25);background:rgba(255,74,74,.06)}
      .es-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}
      .es-card{border:1px solid rgba(255,255,255,.07);border-radius:10px;background:rgba(0,0,0,.12);padding:6px 5px;min-width:0}
      .es-k{font-size:7px;font-weight:900;letter-spacing:.25px;text-transform:uppercase;color:var(--t3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .es-v{font-size:10px;font-weight:900;margin-top:2px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .es-v.g{color:var(--green)}.es-v.o{color:var(--gold)}.es-v.r{color:var(--red)}.es-v.b{color:var(--blue)}.es-v.dim{color:var(--t3)}
      .es-note{margin-top:7px;font-size:8px;line-height:1.35;color:var(--t2);border-top:1px solid rgba(255,255,255,.06);padding-top:7px}
      @media(max-width:420px){.es-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.es-block{padding:8px}.es-v{font-size:9.5px}}
    `;
    document.head.appendChild(st);
  }

  function esc(v){
    if(typeof window.esc === 'function') return window.esc(v);
    return String(v ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }
  function num(v,d=0){ const n=Number(v); return Number.isFinite(n)?n:d; }
  function pct(v){ const n=num(v,null); return n===null?'—':`${Math.round(n*100)}%`; }
  function f1(v){ const n=num(v,null); return n===null?'—':n.toFixed(1); }

  async function fetchJson(url){
    try{
      const r = await fetch(url, {cache:'no-store'});
      if(!r.ok) return null;
      return await r.json();
    }catch(_){ return null; }
  }
  function ensureHealth(){
    if(healthPayload) return Promise.resolve(healthPayload);
    if(!healthPromise){
      healthPromise = fetchJson('data/v6_health.json').then(d => { healthPayload = d || {}; return healthPayload; });
    }
    return healthPromise;
  }
  ensureHealth();

  function statusClass(status){
    const s = String(status||'').toUpperCase();
    if(s === 'GREEN' || s === 'OK' || s === 'ACTIV') return 'g';
    if(s === 'YELLOW' || s === 'PARTIAL' || s === 'EXPERIMENTAL') return 'o';
    if(s === 'RED' || s === 'RISC') return 'r';
    return 'dim';
  }

  function card(label, value, cls){
    return `<div class="es-card"><div class="es-k">${esc(label)}</div><div class="es-v ${cls||''}">${esc(value)}</div></div>`;
  }

  function getV6Status(){
    const status = healthPayload?.overall?.status || '—';
    if(status === 'YELLOW') return {label:'YELLOW', cls:'o', note:'ML v6 este experimental până trece healthcheck-ul pe GREEN.'};
    if(status === 'GREEN') return {label:'GREEN', cls:'g', note:'ML v6 este stabil conform healthcheck.'};
    if(status === 'RED') return {label:'RED', cls:'r', note:'ML v6 are probleme și trebuie tratat doar informativ.'};
    return {label:'se încarcă', cls:'dim', note:'Statusul ML v6 se încarcă din v6_health.json.'};
  }

  function renderEngineStatusBlock(p){
    if(!p || typeof p !== 'object') return '';
    const v6 = getV6Status();

    const ls = p.league_strength || {};
    const lsCal = ls.calibration || {};
    const leagueOk = !!(ls.available || lsCal.version || p.league_strength_safety);
    const leagueLabel = leagueOk ? (lsCal.reason || 'calibrat') : 'fără date';

    const cc = num(p.context_confidence, 0);
    const ctxLabel = cc > 0 ? `${Math.round(cc*100)}%` : 'fără context';

    const li = p.lineup_intelligence || {};
    let lineupLabel = 'fără date';
    let lineupCls = 'dim';
    if(li.available){
      lineupLabel = li.predicted ? `predicted ${pct(li.reliability)}` : `confirmed ${pct(li.reliability)}`;
      lineupCls = li.predicted ? 'o' : 'g';
    }

    const pi = p.player_impact || {};
    let playerLabel = 'fără date';
    let playerCls = 'dim';
    if(pi.available){
      playerLabel = pi.partial ? `parțial ${pct(pi.reliability)}` : `complet ${pct(pi.reliability)}`;
      playerCls = pi.partial ? 'o' : 'g';
    }

    const emi = p.event_match_intelligence || {};
    let eventLabel = 'fără date';
    let eventCls = 'dim';
    if(emi.available){
      eventLabel = `activ ${pct(emi.reliability)}`;
      eventCls = 'g';
    }

    const overallCls = v6.cls === 'r' ? 'r' : (leagueOk && cc > 0 ? 'g' : 'o');
    const overallText = v6.label === 'YELLOW' ? 'stabil + ML exp.' : 'status engine';

    return `<div class="md-section es-block" id="md-engine-status">
      <div class="es-head"><div class="es-title">Engine Status Compact</div><span class="es-pill ${overallCls}">${esc(overallText)}</span></div>
      <div class="es-grid">
        ${card('League Safety', leagueLabel, leagueOk?'g':'dim')}
        ${card('Context', ctxLabel, cc>0?'g':'dim')}
        ${card('Lineup', lineupLabel, lineupCls)}
        ${card('Player Impact', playerLabel, playerCls)}
        ${card('Event Stats', eventLabel, eventCls)}
        ${card('ML v6', v6.label, v6.cls)}
      </div>
      <div class="es-note">${esc(v6.note)} Straturile fără date nu modifică scorul pentru meciul curent.</div>
    </div>`;
  }

  function addModalFitCss(){
    if(document.getElementById('bp-modal-fit-css')) return;
    const st = document.createElement('style');
    st.id = 'bp-modal-fit-css';
    st.textContent = `
      /* BetPredict Modal Fit v1 — rezolvă tăierea cardului în partea de jos pe Android/Chrome/Brave */
      .md-backdrop{
        padding-top:env(safe-area-inset-top,0px)!important;
        padding-bottom:calc(10px + env(safe-area-inset-bottom,0px))!important;
        align-items:flex-end!important;
      }
      .md-sheet{
        height:min(82svh,720px)!important;
        max-height:calc(100svh - 92px - env(safe-area-inset-top,0px))!important;
        margin-bottom:0!important;
      }
      @supports (height:100dvh){
        .md-sheet{
          height:min(82dvh,720px)!important;
          max-height:calc(100dvh - 92px - env(safe-area-inset-top,0px))!important;
        }
      }
      .md-body{
        padding-bottom:calc(118px + env(safe-area-inset-bottom,0px))!important;
        -webkit-overflow-scrolling:touch!important;
        overscroll-behavior:contain!important;
        scroll-padding-bottom:120px!important;
      }
      .md-panel.active::after{
        content:''!important;
        display:block!important;
        height:72px!important;
        flex:0 0 72px!important;
      }
      .md-section:last-child{
        margin-bottom:22px!important;
      }
      @media(max-height:760px){
        .md-sheet{
          height:calc(100dvh - 104px)!important;
          max-height:calc(100dvh - 104px)!important;
        }
        .md-head{padding:10px 12px 7px!important}
        .md-tabs{padding:7px 10px!important}
        .md-body{padding-top:8px!important}
        .md-section{padding:8px!important;margin-bottom:7px!important}
        .md-kpi{padding:6px 4px!important}
        .md-kpi-v{font-size:12px!important}
      }
      @media(max-width:390px){
        .md-body{padding-left:8px!important;padding-right:8px!important}
        .md-sheet{border-radius:16px 16px 0 0!important}
      }
    `;
    document.head.appendChild(st);
  }

  function install(){
    addCss();
    addModalFitCss();
    if(window.__bpEngineStatusUiV1) return;
    window.__bpEngineStatusUiV1 = true;

    const prevContext = window.renderContextEngineBlock;
    if(typeof prevContext === 'function'){
      window.renderContextEngineBlock = function(p){
        return renderEngineStatusBlock(p) + prevContext.apply(this, arguments);
      };
    }else{
      window.renderContextEngineBlock = function(p){
        return renderEngineStatusBlock(p);
      };
    }
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once:true});
  else install();
})();
