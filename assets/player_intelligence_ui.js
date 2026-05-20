/**
 * BetPredict — Player Intelligence UI v1
 * UI non-invaziv pentru data/player_intelligence.json.
 * Nu schimbă motorul Python, scorurile sau structura cardurilor.
 */
(function(){
  'use strict';
  const VERSION = 'pi1';
  const DATA_URL = 'data/player_intelligence.json';

  let payload = null;
  let loadPromise = null;

  function addCss(){
    if(document.getElementById('bp-player-intelligence-ui-css')) return;
    const st = document.createElement('style');
    st.id = 'bp-player-intelligence-ui-css';
    st.textContent = `
      .pi-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
      .pi-title{font-size:9px;font-weight:900;letter-spacing:.45px;text-transform:uppercase;color:var(--t3)}
      .pi-pill{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border-radius:999px;border:1px solid rgba(74,158,255,.28);background:rgba(74,158,255,.07);font-size:8px;font-weight:900;letter-spacing:.35px;text-transform:uppercase;color:var(--blue);white-space:nowrap}
      .pi-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
      .pi-team{border:1px solid var(--br);border-radius:12px;background:rgba(255,255,255,.025);padding:8px;min-width:0}
      .pi-team-top{display:flex;align-items:center;justify-content:space-between;gap:7px;margin-bottom:7px}
      .pi-team-name{font-size:10px;font-weight:900;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .pi-team-meta{font-size:8px;color:var(--t3);font-weight:800;text-transform:uppercase;letter-spacing:.25px;white-space:nowrap}
      .pi-list{display:flex;flex-direction:column;gap:6px}
      .pi-player{border:1px solid rgba(255,255,255,.07);border-radius:10px;background:rgba(255,255,255,.025);padding:7px;min-width:0}
      .pi-p-top{display:flex;align-items:flex-start;justify-content:space-between;gap:7px;margin-bottom:5px}
      .pi-p-name{font-size:10px;font-weight:900;color:var(--text);line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .pi-p-sub{font-size:8px;color:var(--t2);font-weight:800;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .pi-pos{font-family:'Space Mono',monospace;font-size:8px;font-weight:900;color:var(--green);border:1px solid rgba(0,232,122,.22);background:rgba(0,232,122,.055);border-radius:999px;padding:2px 6px;white-space:nowrap}
      .pi-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px;margin-top:5px}
      .pi-k{background:rgba(255,255,255,.03);border:1px solid var(--br);border-radius:8px;padding:4px 3px;text-align:center;min-width:0}
      .pi-v{font-family:'Space Mono',monospace;font-size:10px;font-weight:900;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .pi-l{font-size:6.8px;color:var(--t3);font-weight:900;letter-spacing:.25px;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .pi-tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:6px}
      .pi-tag{display:inline-flex;align-items:center;border:1px solid var(--br);border-radius:999px;padding:2px 6px;font-size:7.5px;font-weight:900;letter-spacing:.2px;text-transform:uppercase;color:var(--t2);background:rgba(255,255,255,.025);white-space:nowrap}
      .pi-tag.g{border-color:rgba(0,232,122,.22);background:rgba(0,232,122,.055);color:var(--green)}
      .pi-tag.o{border-color:rgba(255,184,48,.22);background:rgba(255,184,48,.055);color:var(--gold)}
      .pi-tag.b{border-color:rgba(74,158,255,.22);background:rgba(74,158,255,.055);color:var(--blue)}
      .pi-empty{font-size:9px;color:var(--t2);line-height:1.35;border:1px solid var(--br);border-radius:10px;background:rgba(255,255,255,.025);padding:8px}
      .pi-note{font-size:8.5px;color:var(--t2);line-height:1.35;margin-top:7px;padding:6px;border-radius:9px;background:rgba(255,255,255,.03);border:1px solid var(--br)}
      .pi-note b{color:var(--text)}
      @media(max-width:420px){.pi-grid{grid-template-columns:1fr}.pi-team{padding:7px}.pi-stats{grid-template-columns:repeat(4,minmax(0,1fr));gap:3px}.pi-p-name{font-size:9.5px}}
    `;
    document.head.appendChild(st);
  }

  function esc(v){
    if(typeof window.esc === 'function') return window.esc(v);
    return String(v ?? '—').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }
  function num(v, def=0){
    const n = Number(v);
    return Number.isFinite(n) ? n : def;
  }
  function fmtMoney(v){
    const n = num(v, 0);
    if(!n) return '—';
    if(n >= 1000000) return `€${(n/1000000).toFixed(n>=10000000?0:1)}M`;
    if(n >= 1000) return `€${Math.round(n/1000)}k`;
    return `€${n}`;
  }
  function avg(arr){
    const vals = arr.map(Number).filter(Number.isFinite);
    return vals.length ? vals.reduce((a,b)=>a+b,0)/vals.length : null;
  }
  function safeFixed(v, digits=1){
    const n = Number(v);
    if(!Number.isFinite(n)) return '—';
    return n.toFixed(digits);
  }
  function playerName(p){
    return p?.profile?.short_name || p?.short_name || p?.name || p?.profile?.name || '—';
  }
  function position(p){
    return p?.specific_position || p?.profile?.specific_position || p?.position || p?.profile?.position || '—';
  }
  function currentTeam(p){
    return String(p?.current_team_id || p?.profile?.current_team_id || '');
  }
  function statsSummary(p){
    const rows = Array.isArray(p?.stats_preview) ? p.stats_preview : [];
    const minutes = rows.reduce((s,r)=>s + num(r.minutes_played, 0), 0);
    const goals = rows.reduce((s,r)=>s + num(r.goals, 0), 0);
    const assists = rows.reduce((s,r)=>s + num(r.goal_assist ?? r.assists, 0), 0);
    const rating = avg(rows.map(r=>r.rating));
    return {rows: rows.length, minutes, goals, assists, rating};
  }
  async function loadData(){
    if(payload) return payload;
    if(loadPromise) return loadPromise;
    loadPromise = fetch(DATA_URL, {cache:'no-store'})
      .then(r=>r.ok ? r.json() : null)
      .then(d=>{
        payload = d || {results:[], summary:{}};
        window.__bpPlayerIntelligenceData = payload;
        return payload;
      })
      .catch(()=>{
        payload = {results:[], summary:{}, error:true};
        window.__bpPlayerIntelligenceData = payload;
        return payload;
      });
    return loadPromise;
  }
  function getPayload(){
    return payload || window.__bpPlayerIntelligenceData || {results:[], summary:{}};
  }
  function playersForTeam(teamId){
    const tid = String(teamId || '');
    if(!tid) return [];
    const rows = Array.isArray(getPayload().results) ? getPayload().results : [];
    return rows.filter(p=>currentTeam(p) === tid)
      .sort((a,b)=>{
        const sa = num(a.priority_score,0) + num(a.stats_count,0)/20 + num(a.market_value_eur,0)/1000000;
        const sb = num(b.priority_score,0) + num(b.stats_count,0)/20 + num(b.market_value_eur,0)/1000000;
        return sb - sa;
      });
  }
  function renderPlayer(p){
    const st = statsSummary(p);
    const nat = p?.national_team || {};
    const tags = [];
    if((p.availability || p.profile?.availability)) tags.push(`<span class="pi-tag g">${esc(p.availability || p.profile?.availability)}</span>`);
    if(p.national_team_available) tags.push(`<span class="pi-tag b">NT ${esc(nat.caps ?? 0)} cap</span>`);
    if(num(p.transfers_count,0)>0) tags.push(`<span class="pi-tag o">transfer ${esc(p.transfers_count)}</span>`);
    if(num(p.career_count,0)>0) tags.push(`<span class="pi-tag b">career ${esc(p.career_count)}</span>`);
    return `<div class="pi-player">
      <div class="pi-p-top">
        <div style="min-width:0;flex:1"><div class="pi-p-name">${esc(playerName(p))}</div><div class="pi-p-sub">${esc(p.nationality || p.profile?.nationality || '—')} · ${esc(fmtMoney(p.market_value_eur || p.profile?.market_value_eur))}</div></div>
        <span class="pi-pos">${esc(position(p))}</span>
      </div>
      <div class="pi-stats">
        <div class="pi-k"><div class="pi-v">${esc(st.rows || p.stats_count || 0)}</div><div class="pi-l">stats</div></div>
        <div class="pi-k"><div class="pi-v">${esc(safeFixed(st.rating,1))}</div><div class="pi-l">rating</div></div>
        <div class="pi-k"><div class="pi-v">${esc(st.goals)}</div><div class="pi-l">gol</div></div>
        <div class="pi-k"><div class="pi-v">${esc(st.assists)}</div><div class="pi-l">assist</div></div>
      </div>
      ${tags.length?`<div class="pi-tags">${tags.join('')}</div>`:''}
    </div>`;
  }
  function renderTeamPlayers(teamId, teamName){
    const rows = playersForTeam(teamId).slice(0,5);
    return `<div class="pi-team">
      <div class="pi-team-top"><div style="min-width:0"><div class="pi-team-name">${esc(teamName || '—')}</div><div class="pi-team-meta">${rows.length} jucători prioritari</div></div><span class="pi-pill">players</span></div>
      ${rows.length ? `<div class="pi-list">${rows.map(renderPlayer).join('')}</div>` : `<div class="pi-empty">Nu există încă jucători indexați pentru această echipă în Player Intelligence.</div>`}
    </div>`;
  }
  function renderPlayerIntelligenceBlock(homeId, awayId, homeName, awayName){
    const d = getPayload();
    const rows = Array.isArray(d.results) ? d.results : [];
    if(!rows.length){
      return `<div class="md-section" id="md-player-intel"><div class="pi-head"><div class="pi-title">Player Intelligence</div><span class="pi-pill">cache gol</span></div><div class="pi-empty">Player Intelligence nu este disponibil încă. Rulează Fetch Daily Data.</div></div>`;
    }
    const s = d.summary || {};
    return `<div class="md-section" id="md-player-intel">
      <div class="pi-head"><div class="pi-title">Player Intelligence</div><span class="pi-pill">${esc(d.count || rows.length)} jucători</span></div>
      <div class="pi-grid">${renderTeamPlayers(homeId, homeName)}${renderTeamPlayers(awayId, awayName)}</div>
      <div class="pi-note"><b>Cache prioritar:</b> ${esc(s.players_saved ?? rows.length)} jucători · stats ${esc(s.with_stats ?? '—')} · career ${esc(s.with_career ?? '—')} · national team ${esc(s.with_national_team ?? '—')} · transfers ${esc(s.with_transfers ?? '—')}.</div>
    </div>`;
  }

  function install(){
    addCss();
    if(window.__bpPlayerIntelligenceUiV1) return;
    window.__bpPlayerIntelligenceUiV1 = true;

    const prevEnsure = window.ensureDetailData;
    if(typeof prevEnsure === 'function'){
      window.ensureDetailData = async function(){
        await prevEnsure.apply(this, arguments);
        await loadData();
      };
    }else{
      loadData();
    }

    const prevTeams = window.renderTeamsBlock;
    if(typeof prevTeams === 'function'){
      window.renderTeamsBlock = function(homeId, awayId, homeName, awayName){
        const base = prevTeams.apply(this, arguments);
        return base + renderPlayerIntelligenceBlock(homeId, awayId, homeName, awayName);
      };
    }
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once:true});
  else install();
})();
