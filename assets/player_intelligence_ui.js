/**
 * BetPredict — Player Intelligence + Player Impact UI v4
 * UI non-invaziv pentru data/player_intelligence.json + data/player_impact.json.
 * Nu schimbă motorul Python, scorurile sau structura cardurilor.
 */
(function(){
  'use strict';
  const VERSION = 'pi4';
  const PLAYER_DATA_URL = 'data/player_intelligence.json';
  const IMPACT_DATA_URL = 'data/player_impact.json';

  let playerPayload = null;
  let impactPayload = null;
  let playerLoadPromise = null;
  let impactLoadPromise = null;

  function addCss(){
    if(document.getElementById('bp-player-intelligence-ui-css')) return;
    const st = document.createElement('style');
    st.id = 'bp-player-intelligence-ui-css';
    st.textContent = `
      .pi-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
      .pi-title{font-size:9px;font-weight:800;letter-spacing:.45px;text-transform:uppercase;color:var(--t3)}
      .pi-pill{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border-radius:999px;border:1px solid rgba(74,158,255,.28);background:rgba(74,158,255,.07);font-size:8px;font-weight:800;letter-spacing:.35px;text-transform:uppercase;color:var(--blue);white-space:nowrap}
      .pi-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
      .pi-team{border:1px solid var(--br);border-radius:12px;background:rgba(255,255,255,.025);padding:8px;min-width:0}
      .pi-team-top{display:flex;align-items:center;justify-content:space-between;gap:7px;margin-bottom:7px}
      .pi-team-name{font-size:10px;font-weight:800;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .pi-team-meta{font-size:8px;color:var(--t3);font-weight:800;text-transform:uppercase;letter-spacing:.25px;white-space:nowrap}
      .pi-list{display:flex;flex-direction:column;gap:6px}
      .pi-player{border:1px solid rgba(255,255,255,.07);border-radius:10px;background:rgba(255,255,255,.025);padding:7px;min-width:0}
      .pi-p-top{display:flex;align-items:flex-start;justify-content:space-between;gap:7px;margin-bottom:5px}
      .pi-p-name{font-size:10px;font-weight:800;color:var(--text);line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .pi-p-sub{font-size:8px;color:var(--t2);font-weight:800;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .pi-pos{font-family:var(--ff-mono);font-size:8px;font-weight:800;color:var(--green);border:1px solid rgba(0,232,122,.22);background:rgba(0,232,122,.055);border-radius:999px;padding:2px 6px;white-space:nowrap}
      .pi-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:4px;margin-top:5px}
      .pi-k{background:rgba(255,255,255,.03);border:1px solid var(--br);border-radius:8px;padding:4px 3px;text-align:center;min-width:0}
      .pi-v{font-family:var(--ff-mono);font-size:10px;font-weight:800;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .pi-l{font-size:6.8px;color:var(--t3);font-weight:800;letter-spacing:.25px;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .pi-tags{display:flex;gap:4px;flex-wrap:wrap;margin-top:6px}
      .pi-tag{display:inline-flex;align-items:center;border:1px solid var(--br);border-radius:999px;padding:2px 6px;font-size:7.5px;font-weight:800;letter-spacing:.2px;text-transform:uppercase;color:var(--t2);background:rgba(255,255,255,.025);white-space:nowrap}
      .pi-tag.g{border-color:rgba(0,232,122,.22);background:rgba(0,232,122,.055);color:var(--green)}
      .pi-tag.o{border-color:rgba(255,184,48,.22);background:rgba(255,184,48,.055);color:var(--gold)}
      .pi-tag.b{border-color:rgba(74,158,255,.22);background:rgba(74,158,255,.055);color:var(--blue)}
      .pi-empty{font-size:9px;color:var(--t2);line-height:1.35;border:1px solid var(--br);border-radius:10px;background:rgba(255,255,255,.025);padding:8px}
      .pi-note{font-size:8.5px;color:var(--t2);line-height:1.35;margin-top:7px;padding:6px;border-radius:9px;background:rgba(255,255,255,.03);border:1px solid var(--br)}
      .pi-note b{color:var(--text)}

      .pim-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
      .pim-title{font-size:9px;font-weight:800;letter-spacing:.45px;text-transform:uppercase;color:var(--t3)}
      .pim-pill{display:inline-flex;align-items:center;padding:4px 9px;border-radius:999px;border:1px solid var(--br);font-size:8px;font-weight:800;letter-spacing:.35px;text-transform:uppercase;white-space:nowrap;color:var(--t2);background:rgba(255,255,255,.035)}
      .pim-pill.on{border-color:rgba(0,232,122,.24);background:rgba(0,232,122,.06);color:var(--green)}
      .pim-pill.warn{border-color:rgba(255,184,48,.24);background:rgba(255,184,48,.06);color:var(--gold)}
      .pim-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;margin-bottom:8px}
      .pim-box{background:rgba(255,255,255,.03);border:1px solid var(--br);border-radius:9px;padding:6px 4px;text-align:center;min-width:0}
      .pim-l{font-size:7px;color:var(--t3);font-weight:800;letter-spacing:.25px;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .pim-v{font-family:var(--ff-mono);font-size:11px;font-weight:800;color:var(--text);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .pim-v.g{color:var(--green)}.pim-v.o{color:var(--gold)}.pim-v.b{color:var(--blue)}.pim-v.r{color:var(--red)}.pim-v.dim{color:var(--t2)}
      .pim-teams{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:7px}
      .pim-team{border:1px solid var(--br);border-radius:10px;background:rgba(255,255,255,.025);padding:7px;min-width:0}
      .pim-team-top{display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:6px}
      .pim-team-name{font-size:9.5px;font-weight:800;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .pim-team-score{font-family:var(--ff-mono);font-size:12px;font-weight:800;color:var(--blue)}
      .pim-player{display:flex;align-items:center;justify-content:space-between;gap:6px;border-top:1px solid rgba(255,255,255,.055);padding-top:5px;margin-top:5px}
      .pim-player:first-of-type{border-top:0;padding-top:0;margin-top:0}
      .pim-player-name{font-size:8.5px;font-weight:800;color:var(--t2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
      .pim-player-score{font-family:var(--ff-mono);font-size:9px;font-weight:800;color:var(--green);white-space:nowrap}
      .pim-note{font-size:8.5px;color:var(--t2);line-height:1.35;margin-top:7px;padding:6px;border-radius:9px;background:rgba(255,255,255,.03);border:1px solid var(--br)}
      .pim-details{border:1px solid var(--br);border-radius:10px;background:rgba(255,255,255,.025);overflow:hidden;margin-top:7px}
      .pim-details summary{list-style:none;cursor:pointer;padding:7px 8px;font-size:8.5px;font-weight:800;letter-spacing:.3px;text-transform:uppercase;color:var(--t2);display:flex;align-items:center;justify-content:space-between;-webkit-tap-highlight-color:transparent}
      .pim-details summary::-webkit-details-marker{display:none}
      .pim-details summary:after{content:'+';font-family:var(--ff-mono);color:var(--t3);font-size:13px}.pim-details[open] summary:after{content:'−';color:var(--green)}
      .pim-details-body{padding:7px;border-top:1px solid var(--br)}
      .pim-compact{padding:9px 10px!important}
      .pim-compact-row{display:flex;align-items:center;justify-content:space-between;gap:8px}
      .pim-compact-msg{font-size:8.5px;color:var(--t2);line-height:1.35;margin-top:6px}
      @media(max-width:420px){.pi-grid,.pim-teams{grid-template-columns:1fr}.pi-team{padding:7px}.pi-stats{grid-template-columns:repeat(4,minmax(0,1fr));gap:3px}.pi-p-name{font-size:9.5px}.pim-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}
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
  function f1(v){
    const n = Number(v);
    if(!Number.isFinite(n)) return '—';
    return Number.isInteger(n) ? String(n) : n.toFixed(1);
  }
  function pp(v){
    const n = Number(v);
    if(!Number.isFinite(n)) return '—';
    return `${n>0?'+':''}${n.toFixed(2)}`;
  }
  function pct(v){
    const n = Number(v);
    if(!Number.isFinite(n)) return '—';
    return n<=1 ? `${Math.round(n*100)}%` : `${Math.round(n)}%`;
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

  async function loadPlayerData(){
    if(playerPayload) return playerPayload;
    if(playerLoadPromise) return playerLoadPromise;
    playerLoadPromise = fetch(PLAYER_DATA_URL, {cache:'no-store'})
      .then(r=>r.ok ? r.json() : null)
      .then(d=>{ playerPayload = d || {results:[], summary:{}}; window.__bpPlayerIntelligenceData = playerPayload; return playerPayload; })
      .catch(()=>{ playerPayload = {results:[], summary:{}, error:true}; window.__bpPlayerIntelligenceData = playerPayload; return playerPayload; });
    return playerLoadPromise;
  }
  async function loadImpactData(){
    if(impactPayload) return impactPayload;
    if(impactLoadPromise) return impactLoadPromise;
    impactLoadPromise = fetch(IMPACT_DATA_URL, {cache:'no-store'})
      .then(r=>r.ok ? r.json() : null)
      .then(d=>{ impactPayload = d || {results:[], summary:{}}; window.__bpPlayerImpactData = impactPayload; return impactPayload; })
      .catch(()=>{ impactPayload = {results:[], summary:{}, error:true}; window.__bpPlayerImpactData = impactPayload; return impactPayload; });
    return impactLoadPromise;
  }
  function getPlayerPayload(){ return playerPayload || window.__bpPlayerIntelligenceData || {results:[], summary:{}}; }
  function getImpactPayload(){ return impactPayload || window.__bpPlayerImpactData || {results:[], summary:{}}; }

  function playersForTeam(teamId){
    const tid = String(teamId || '');
    if(!tid) return [];
    const rows = Array.isArray(getPlayerPayload().results) ? getPlayerPayload().results : [];
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
    const d = getPlayerPayload();
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

  function impactForPrediction(p){
    if(!p) return null;
    if(p.player_impact && typeof p.player_impact === 'object') return p.player_impact;
    const eid = String(p?.event?.id ?? p?.event_id ?? '');
    if(!eid) return null;
    const rows = Array.isArray(getImpactPayload().results) ? getImpactPayload().results : [];
    return rows.find(r=>String(r.event_id)===eid) || null;
  }
  function topPlayersHtml(team){
    const players = Array.isArray(team?.top_players) ? team.top_players.slice(0,4) : [];
    if(!players.length) return `<div class="pim-note">Top players lipsesc pentru această echipă.</div>`;
    return players.map(pl=>`<div class="pim-player"><span class="pim-player-name">${esc(pl.name || '—')}</span><span class="pim-player-score">${esc(f1(pl.score))}</span></div>`).join('');
  }
  function impactStatus(impact){
    if(!impact || !impact.available) return ['warn','date insuficiente'];
    const a = String(impact.alignment || 'neutral');
    if(a === 'supports_main_side') return ['on','susține predicția'];
    if(a === 'contradicts_main_side') return ['warn','contrazice predicția'];
    return ['warn','neutru'];
  }
  function renderPlayerImpactBlock(p){
    const impact = impactForPrediction(p);
    if(!impact) return '';
    const [cls, label] = impactStatus(impact);
    const h = impact.home || {};
    const a = impact.away || {};
    const adj = impact.adjustment_pp || {};
    const before = p?.smartbet_score_before_player_impact ?? impact.smartbet_before;
    const bonus = p?.player_impact_bonus ?? impact.smartbet_bonus ?? impact.smartbet_bonus;
    const after = p?.smartbet_score ?? impact.smartbet_after;
    const available = !!impact.available;
    const partial = !!impact.partial || String(impact.alignment||'') === 'partial_squad_data' || (available && num(impact.reliability,0) < 0.45);

    if(!available){
      return `<div class="md-section pim-compact" id="md-player-impact">
        <div class="pim-compact-row">
          <div class="pim-title">Player Impact Engine</div>
          <span class="pim-pill warn">date insuficiente</span>
        </div>
        <div class="pim-compact-msg">Nu există lot indexat complet pentru acest meci. Impactul nu modifică SmartBet.</div>
      </div>`;
    }

    if(partial){
      return `<div class="md-section pim-compact" id="md-player-impact">
        <div class="pim-compact-row">
          <div class="pim-title">Player Impact Engine</div>
          <span class="pim-pill warn">date parțiale</span>
        </div>
        <div class="pim-summary" style="margin-top:8px;margin-bottom:0">
          <div class="pim-box"><div class="pim-l">Lot 1</div><div class="pim-v b">${esc(f1(h.score))}</div></div>
          <div class="pim-box"><div class="pim-l">Lot 2</div><div class="pim-v b">${esc(f1(a.score))}</div></div>
          <div class="pim-box"><div class="pim-l">Reliability</div><div class="pim-v dim">${esc(pct(impact.reliability))}</div></div>
          <div class="pim-box"><div class="pim-l">Bonus SB</div><div class="pim-v dim">0.00</div></div>
        </div>
        <div class="pim-compact-msg">Există squad basic, dar nu suficiente stats/market/player detail. Îl afișez informativ, fără bonus agresiv.</div>
      </div>`;
    }

    return `<div class="md-section" id="md-player-impact">
      <div class="pim-head"><div class="pim-title">Player Impact Engine</div><span class="pim-pill ${cls}">${esc(label)}</span></div>
      <div class="pim-summary">
        <div class="pim-box"><div class="pim-l">Lot 1</div><div class="pim-v b">${esc(f1(h.score))}</div></div>
        <div class="pim-box"><div class="pim-l">Lot 2</div><div class="pim-v b">${esc(f1(a.score))}</div></div>
        <div class="pim-box"><div class="pim-l">Delta</div><div class="pim-v ${num(impact.delta_score,0)>=0?'g':'r'}">${esc(pp(impact.delta_score))}</div></div>
        <div class="pim-box"><div class="pim-l">Reliability</div><div class="pim-v ${num(impact.reliability,0)>0?'g':'dim'}">${esc(pct(impact.reliability))}</div></div>
        <div class="pim-box"><div class="pim-l">Adj 1</div><div class="pim-v ${num(adj.home,0)>0?'g':'dim'}">${esc(pp(adj.home))}pp</div></div>
        <div class="pim-box"><div class="pim-l">Adj X</div><div class="pim-v dim">${esc(pp(adj.draw))}pp</div></div>
        <div class="pim-box"><div class="pim-l">Adj 2</div><div class="pim-v ${num(adj.away,0)>0?'g':'dim'}">${esc(pp(adj.away))}pp</div></div>
        <div class="pim-box"><div class="pim-l">Bonus SB</div><div class="pim-v ${num(bonus,0)>0?'g':'dim'}">${esc(pp(bonus))}</div></div>
      </div>
      <div class="pim-note"><b>SmartBet:</b> ${esc(f1(before))} → ${esc(f1(after))}. Bonusul este plafonat și se aplică doar când lotul susține direcția principală.</div>
      <details class="pim-details">
        <summary>Top players folosiți în calcul</summary>
        <div class="pim-details-body">
          <div class="pim-teams">
            <div class="pim-team"><div class="pim-team-top"><div class="pim-team-name">${esc(impact.home_team || 'Acasă')}</div><div class="pim-team-score">${esc(f1(h.score))}</div></div>${topPlayersHtml(h)}</div>
            <div class="pim-team"><div class="pim-team-top"><div class="pim-team-name">${esc(impact.away_team || 'Deplasare')}</div><div class="pim-team-score">${esc(f1(a.score))}</div></div>${topPlayersHtml(a)}</div>
          </div>
        </div>
      </details>
    </div>`;
  }
  function install(){
    addCss();
    if(window.__bpPlayerIntelligenceUiV2) return;
    window.__bpPlayerIntelligenceUiV2 = true;

    const prevEnsure = window.ensureDetailData;
    if(typeof prevEnsure === 'function'){
      window.ensureDetailData = async function(){
        await prevEnsure.apply(this, arguments);
        await Promise.all([loadPlayerData(), loadImpactData()]);
      };
    }else{
      Promise.all([loadPlayerData(), loadImpactData()]);
    }

    const prevTeams = window.renderTeamsBlock;
    if(typeof prevTeams === 'function'){
      window.renderTeamsBlock = function(homeId, awayId, homeName, awayName){
        const base = prevTeams.apply(this, arguments);
        return base + renderPlayerIntelligenceBlock(homeId, awayId, homeName, awayName);
      };
    }

    const prevContextEngine = window.renderContextEngineBlock;
    if(typeof prevContextEngine === 'function'){
      window.renderContextEngineBlock = function(p){
        const base = prevContextEngine.apply(this, arguments);
        return base + renderPlayerImpactBlock(p);
      };
    }else{
      // Fallback rar: dacă asset-ul Context Engine nu s-a încărcat, păstrăm impactul înainte de League Strength.
      const prevLeagueStrength = window.renderLeagueStrengthBlock;
      if(typeof prevLeagueStrength === 'function'){
        window.renderLeagueStrengthBlock = function(p){
          return renderPlayerImpactBlock(p) + prevLeagueStrength.apply(this, arguments);
        };
      }
    }
  }

  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, {once:true});
  else install();
})();
