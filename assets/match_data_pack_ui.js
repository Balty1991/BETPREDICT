/**
 * BetPredict Pro — Match Data Pack UI FIX (Pasul 25 Layout Fix)
 * Repară afișarea în Match Detail: nu mai injectează cardul lângă drawer,
 * ci în interiorul tabului Context. Elimină overflow-ul orizontal.
 */
(function () {
  const DATA_URL = "data/match_data_pack.json?v=pas25fix";
  const LIVE_URL = "data/live_intelligence.json";
  let pack = null;
  let byPair = new Map();
  let byId = new Map();
  let liveByPair = new Map();
  let liveById = new Map();

  const css = `
    #match-modal .md-sheet,
    #match-modal .md-body,
    #match-modal .md-panel{max-width:100%!important;overflow-x:hidden!important;box-sizing:border-box!important}
    #match-modal .bp-mdp-card,
    #match-modal .bp-mdp-card *{box-sizing:border-box!important}
    #match-modal .bp-mdp-card{width:100%!important;max-width:100%!important;margin:12px 0 18px!important;border:1px solid rgba(56,189,248,.20);border-radius:18px;background:linear-gradient(180deg,rgba(13,23,42,.96),rgba(8,15,29,.96));box-shadow:0 12px 34px rgba(0,0,0,.22);overflow:hidden;clear:both}
    .bp-mdp-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 14px;border-bottom:1px solid rgba(148,163,184,.12)}
    .bp-mdp-title{font-weight:900;letter-spacing:.08em;text-transform:uppercase;color:#dbeafe;font-size:12px;min-width:0}
    .bp-mdp-badge{font:800 10px/1 ui-monospace,monospace;color:#38bdf8;background:rgba(56,189,248,.10);border:1px solid rgba(56,189,248,.24);padding:6px 8px;border-radius:999px;white-space:nowrap}
    .bp-mdp-tabs{display:flex;gap:7px;overflow-x:auto;overflow-y:hidden;padding:10px 12px;border-bottom:1px solid rgba(148,163,184,.10);-webkit-overflow-scrolling:touch}
    .bp-mdp-tab{flex:0 0 auto;border:1px solid rgba(148,163,184,.16);background:rgba(15,23,42,.84);color:#94a3b8;border-radius:999px;padding:7px 9px;font-weight:800;font-size:10px;letter-spacing:.05em;text-transform:uppercase}
    .bp-mdp-tab.active{color:#e0f2fe;border-color:rgba(56,189,248,.45);background:rgba(37,99,235,.20)}
    .bp-mdp-body{padding:12px;color:#cbd5e1;max-width:100%;overflow:hidden}
    .bp-mdp-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;max-width:100%}
    .bp-mdp-box{min-width:0;border:1px solid rgba(148,163,184,.12);border-radius:13px;background:rgba(15,23,42,.60);padding:10px}
    .bp-mdp-k{font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:.08em;font-weight:900;margin-bottom:5px}
    .bp-mdp-v{font:900 17px/1.1 ui-monospace,monospace;color:#e5eef9;word-break:break-word}
    .bp-mdp-muted{color:#94a3b8;font-size:12px;line-height:1.4;min-width:0;overflow-wrap:anywhere}
    .bp-mdp-prematch{border:1px dashed rgba(96,165,250,.28);background:rgba(96,165,250,.07);border-radius:12px;padding:14px;color:#cbd5e1;margin:2px 0}
    .bp-mdp-badge-prematch{color:#fbbf24!important;background:rgba(251,191,36,.10)!important;border-color:rgba(251,191,36,.28)!important}
    .bp-mdp-row{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px solid rgba(148,163,184,.09);font-size:12px;min-width:0}
    .bp-mdp-row span{min-width:0;overflow-wrap:anywhere}
    .bp-mdp-row b{flex:0 0 auto;max-width:45%;overflow-wrap:anywhere;text-align:right}
    .bp-mdp-row:last-child{border-bottom:0}
    .bp-mdp-list{display:flex;flex-direction:column;gap:8px;max-width:100%}
    .bp-mdp-player{display:grid;grid-template-columns:30px minmax(0,1fr) auto;align-items:center;gap:9px;border:1px solid rgba(148,163,184,.12);border-radius:13px;background:rgba(15,23,42,.58);padding:8px;max-width:100%}
    .bp-mdp-avatar{width:30px;height:30px;border-radius:50%;object-fit:cover;background:rgba(148,163,184,.16)}
    .bp-mdp-pill{font:800 10px/1 ui-monospace,monospace;border-radius:999px;padding:5px 7px;background:rgba(16,185,129,.12);color:#34d399;border:1px solid rgba(16,185,129,.22)}
    .bp-mdp-timeline{display:flex;flex-direction:column;gap:8px;max-width:100%}
    .bp-mdp-event{display:grid;grid-template-columns:38px minmax(0,1fr);gap:9px;align-items:start;border:1px solid rgba(148,163,184,.12);border-radius:13px;background:rgba(15,23,42,.58);padding:9px;max-width:100%}
    .bp-mdp-minute{font:900 12px/1 ui-monospace,monospace;color:#60a5fa}
    .bp-mdp-shots{display:flex;flex-direction:column;gap:7px;max-width:100%}
    .bp-mdp-shot{display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:center;gap:8px;border:1px solid rgba(148,163,184,.10);border-radius:12px;background:rgba(15,23,42,.55);padding:8px;max-width:100%}
    .bp-mdp-shot.is-goal{border-color:rgba(52,211,153,.28);background:rgba(16,185,129,.07)}
    .bp-mdp-shot.on-target{border-color:rgba(96,165,250,.20)}
    .bp-mdp-shot-min{font:900 11px/1 ui-monospace,monospace;color:#60a5fa;text-align:center}
    .bp-mdp-shot-icon{font-size:15px;display:block;line-height:1}
    .bp-mdp-shot-name{font-size:11px;font-weight:700;color:#e2e8f0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
    .bp-mdp-shot-meta{font-size:9px;color:#64748b;margin-top:2px;overflow-wrap:anywhere}
    .bp-mdp-shot-xg{font:800 11px/1 ui-monospace,monospace;color:#94a3b8;flex-shrink:0}
    .bp-mdp-shot-xg.hi{color:#34d399}
    .bp-mdp-shot-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px}
    .bp-mdp-shot-kpi{border:1px solid rgba(148,163,184,.12);border-radius:12px;background:rgba(15,23,42,.55);padding:9px;text-align:center}
    .bp-mdp-shot-kpi b{display:block;font:900 18px/1 ui-monospace,monospace;color:#e5eef9;margin-bottom:4px}
    .bp-mdp-shot-kpi span{font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:.07em;font-weight:900}
    @media(max-width:560px){
      #match-modal .bp-mdp-card{margin:10px 0 16px!important;border-radius:16px}
      .bp-mdp-grid{grid-template-columns:1fr}
      .bp-mdp-title{font-size:11px}
      .bp-mdp-badge{font-size:9px}
      .bp-mdp-body{padding:10px}
    }
  `;

  function addCss(){
    if(document.getElementById("bp-mdp-css")) return;
    const s=document.createElement("style");
    s.id="bp-mdp-css";
    s.textContent=css;
    document.head.appendChild(s);
  }

  function norm(s){ return String(s||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-z0-9]+/g," ").trim(); }
  function pairKey(h,a){ return `${norm(h)}__${norm(a)}`; }
  function esc(s){ return String(s ?? "—").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m])); }
  function num(v,d=2){ 
    const n=Number(v);
    return (v===null||v===undefined||v===""||!Number.isFinite(n)) ? "—" : n.toFixed(d).replace(/\.0+$/,""); 
  }

  async function load(){
    try{
      const r=await fetch(DATA_URL,{cache:"no-store"});
      if(!r.ok) return;
      pack=await r.json();
      byPair = new Map(); byId = new Map();
      for(const row of (pack.results||[])){
        if(row.event_id) byId.set(String(row.event_id), row);
        byPair.set(pairKey(row.home_team,row.away_team), row);
      }
    }catch(e){ console.warn("Match Data Pack load failed", e); }
    try{
      const r2=await fetch(LIVE_URL,{cache:"no-store"});
      if(!r2.ok) return;
      const live=await r2.json();
      liveByPair = new Map(); liveById = new Map();
      for(const ev of (live.events||[])){
        if(ev.event_id) liveById.set(String(ev.event_id), ev);
        liveByPair.set(pairKey(ev.home_team,ev.away_team), ev);
      }
    }catch(e){ console.warn("Live intelligence load failed", e); }
  }

  function currentModal(){
    const m=document.getElementById("match-modal");
    if(!m || !m.classList.contains("show")) return null;
    return m;
  }

  function findMatch(){
    const modal=currentModal();
    if(!modal) return null;
    const title=modal.querySelector(".md-title");
    if(!title) return null;
    const t=(title.textContent||"").replace(/\s+/g," ").trim();
    if(!/\s+vs\s+/i.test(t)) return null;
    const parts=t.split(/\s+vs\s+/i);
    const h=parts[0].trim();
    const a=parts.slice(1).join(" vs ").trim();
    const direct=byPair.get(pairKey(h,a));
    if(direct) return {row:direct, modal};
    for(const row of (pack?.results||[])){
      if(norm(t).includes(norm(row.home_team)) && norm(t).includes(norm(row.away_team))) return {row, modal};
    }
    return null;
  }

  function targetPanel(modal){
    return modal.querySelector('.md-panel[data-panel="context"]') ||
           modal.querySelector('.md-panel.active') ||
           modal.querySelector('.md-body') ||
           modal.querySelector('#md-content');
  }

  function cleanupWrongCards(modal){
    // Elimină cardurile injectate anterior direct în sheet/body, cauza overflow-ului.
    modal.querySelectorAll(".bp-mdp-card").forEach(card=>{
      if(!card.closest(".md-panel")) card.remove();
    });
  }

  function statValue(side,key){
    const v=side?.[key];
    if(v && typeof v==="object"){
      if("actual" in v) return v.actual;
      if("pct" in v) return `${v.pct}%`;
      if("value" in v && "total" in v) return `${v.value}/${v.total}`;
    }
    return v;
  }

  function isEmptyMatchPack(row){
    const s=row.stats||{};
    const counts=(s.shotmap_count||0)+(s.momentum_count||0)+(s.xg_per_minute_count||0)+(s.average_positions_count||0);
    const players=row.player_stats?.count||0;
    const events=row.incidents?.count||0;
    const shotmap=Array.isArray(row.shotmap)?row.shotmap.length:0;
    const xgH=Number(statValue(s.home||{},"xg"))||0;
    const xgA=Number(statValue(s.away||{},"xg"))||0;
    return counts===0 && players===0 && events===0 && shotmap===0 && xgH===0 && xgA===0;
  }

  function renderEmptyPack(){
    return `<div class="bp-mdp-muted bp-mdp-prematch">
      <div style="font-weight:900;color:#93c5fd;font-size:11px;margin-bottom:4px">⏳ Date live indisponibile</div>
      Pachetul (stats, shotmap, jucători, momentum) se populează după startul meciului.<br><br>
      Pentru analiză <b>pre-match</b> folosește filele din meniul de sus: <b>FORM</b>, <b>H2H</b>, <b>LINEUPS</b>, <b>TEAMS</b>, <b>INFO</b>.
    </div>`;
  }

  function renderStats(row){
    if(isEmptyMatchPack(row))return renderEmptyPack();
    const h=row.stats?.home||{}, a=row.stats?.away||{};
    return `<div class="bp-mdp-grid">
      <div class="bp-mdp-box"><div class="bp-mdp-k">xG home</div><div class="bp-mdp-v">${esc(num(statValue(h,"xg")))}</div></div>
      <div class="bp-mdp-box"><div class="bp-mdp-k">xG away</div><div class="bp-mdp-v">${esc(num(statValue(a,"xg")))}</div></div>
      <div class="bp-mdp-box"><div class="bp-mdp-k">Shotmap</div><div class="bp-mdp-v">${row.stats?.shotmap_count||0}</div></div>
      <div class="bp-mdp-box"><div class="bp-mdp-k">xG/min</div><div class="bp-mdp-v">${row.stats?.xg_per_minute_count||0}</div></div>
      <div class="bp-mdp-box"><div class="bp-mdp-k">Momentum</div><div class="bp-mdp-v">${row.stats?.momentum_count||0}</div></div>
      <div class="bp-mdp-box"><div class="bp-mdp-k">Avg positions</div><div class="bp-mdp-v">${row.stats?.average_positions_count||0}</div></div>
    </div>
    <div class="bp-mdp-row"><span>Home dangerous attack</span><b>${esc(num(statValue(h,"dangerous_attack"),0))}</b></div>
    <div class="bp-mdp-row"><span>Away dangerous attack</span><b>${esc(num(statValue(a,"dangerous_attack"),0))}</b></div>
    <div class="bp-mdp-row"><span>Home pass accuracy</span><b>${esc(statValue(h,"pass_accuracy_pct") ?? "—")}</b></div>
    <div class="bp-mdp-row"><span>Away pass accuracy</span><b>${esc(statValue(a,"pass_accuracy_pct") ?? "—")}</b></div>`;
  }

  function renderPlayers(row){
    const ps=row.player_stats||{};
    const top=(ps.top_rating?.length?ps.top_rating:ps.players||[]).slice(0,10);
    if(!top.length) return `<div class="bp-mdp-muted">Player-stats indisponibil momentan. Pentru pre-match este normal; se populează live/post-match.</div>`;
    return `<div class="bp-mdp-list">${top.map(p=>`
      <div class="bp-mdp-player">
        <img class="bp-mdp-avatar" src="${esc(p.image_url||"")}" onerror="this.style.display='none'">
        <div><b>${esc(p.short_name||p.name)}</b><div class="bp-mdp-muted">${esc(p.position||"—")} · ${p.minutes_played??0} min · xG ${num(p.expected_goals)} · xA ${num(p.expected_assists)}</div></div>
        <span class="bp-mdp-pill">${num(p.rating,1)}</span>
      </div>`).join("")}</div>`;
  }

  function renderShotmap(row){
    const liveEv = (row.event_id && liveById.get(String(row.event_id)))
                || liveByPair.get(pairKey(row.home_team, row.away_team));
    const liveShotmap = Array.isArray(liveEv?.shotmap) ? liveEv.shotmap : [];
    const shots = liveShotmap.length ? liveShotmap : Array.isArray(row.shotmap) ? row.shotmap : [];
    const isLive = liveShotmap.length > 0;
    if(!shots.length) return `<div class="bp-mdp-muted">Shotmap indisponibil pentru acest meci. Datele apar după startul meciului (live).</div>`;
    const liveTag = isLive ? `<span style="color:#34d399;font-size:9px;font-weight:900;margin-left:6px">● LIVE</span>` : ``;
    const goals  = shots.filter(s=>s.is_goal||s.goal).length;
    const onTgt  = shots.filter(s=>s.on_target||s.is_goal||s.goal).length;
    const xgTot  = shots.reduce((acc,s)=>acc+Number(s.expected_goals||s.xg||0),0);
    return `<div style="display:flex;align-items:center;margin-bottom:8px"><span style="font-size:10px;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:.06em">Shots${liveTag}</span></div>
    <div class="bp-mdp-shot-summary">
      <div class="bp-mdp-shot-kpi"><b>${shots.length}</b><span>Șuturi</span></div>
      <div class="bp-mdp-shot-kpi"><b>${onTgt}</b><span>Pe poartă</span></div>
      <div class="bp-mdp-shot-kpi"><b>${num(xgTot)}</b><span>xG total</span></div>
    </div>
    <div class="bp-mdp-shots">${shots.slice(0,25).map(s=>{
      const isGoal = s.is_goal||s.goal;
      const onTarget = s.on_target||isGoal;
      const playerName = s.player?.name||s.player_name||s.player||"—";
      const teamName = s.team?.name||s.team_name||"";
      const shotType = s.type?.name||s.shot_type||s.situation?.name||"";
      const min = s.minute||s.min||"?";
      const xg = Number(s.expected_goals||s.xg||0);
      const icon = isGoal?"⚽":onTarget?"🎯":"·";
      const cls = isGoal?"is-goal":onTarget?"on-target":"";
      const xgCls = xg>=0.15?"hi":"";
      return `<div class="bp-mdp-shot ${cls}">
        <div><div class="bp-mdp-shot-min">${min}'</div><div class="bp-mdp-shot-icon">${icon}</div></div>
        <div><div class="bp-mdp-shot-name">${esc(playerName)}</div><div class="bp-mdp-shot-meta">${esc(teamName)}${shotType?' · '+esc(shotType):''}</div></div>
        <div class="bp-mdp-shot-xg ${xgCls}">xG ${xg>0?num(xg):"—"}</div>
      </div>`;
    }).join("")}</div>`;
  }

  function renderTimeline(row){
    const tl=row.incidents?.timeline||[];
    if(!tl.length) return `<div class="bp-mdp-muted">Nu există incidents pentru acest meci încă. Pentru pre-match este normal.</div>`;
    return `<div class="bp-mdp-timeline">${tl.slice(0,18).map(e=>`
      <div class="bp-mdp-event"><div class="bp-mdp-minute">${e.minute||0}'</div><div><b>${esc(e.type)}</b><div class="bp-mdp-muted">${esc(e.player||e.player_in||"—")} ${e.card_type?("· "+esc(e.card_type)):""}</div></div></div>`).join("")}</div>`;
  }

  function renderMeta(row){
    const m=row.metadata||{};
    const facts=m.funfacts||[];
    const ai=m.ai_preview||{};
    const lineup=row.lineups||{};
    return `<div class="bp-mdp-row"><span>Lineup status</span><b>${esc(lineup.lineup_status||"—")}</b></div>
      <div class="bp-mdp-row"><span>Home formation</span><b>${esc(lineup.home?.formation||"—")}</b></div>
      <div class="bp-mdp-row"><span>Away formation</span><b>${esc(lineup.away?.formation||"—")}</b></div>
      <div class="bp-mdp-box"><div class="bp-mdp-k">AI preview</div><div class="bp-mdp-muted">${esc(ai.text||"AI preview indisponibil pentru acest meci.")}</div></div>
      <div class="bp-mdp-box" style="margin-top:10px"><div class="bp-mdp-k">Funfacts</div>${facts.length?facts.slice(0,4).map(f=>`<div class="bp-mdp-muted">• ${esc(f.sentence||f.text||JSON.stringify(f))}</div>`).join(""):`<div class="bp-mdp-muted">Funfacts indisponibil.</div>`}</div>`;
  }

  function bodyFor(row, tab){
    if(tab==="stats") return renderStats(row);
    if(tab==="players") return renderPlayers(row);
    if(tab==="timeline") return renderTimeline(row);
    if(tab==="shots") return renderShotmap(row);
    return renderMeta(row);
  }

  function inject(row,modal){
    cleanupWrongCards(modal);
    const host=targetPanel(modal);
    if(!host) return;

    const old=host.querySelector(":scope > .bp-mdp-card");
    if(old && old.dataset.eventId===String(row.event_id)) return;
    if(old) old.remove();

    const hasShotmap = Array.isArray(row.shotmap) && row.shotmap.length > 0;
    const shotCount = hasShotmap ? row.shotmap.length : (row.stats?.shotmap_count||0);
    const isEmpty = isEmptyMatchPack(row);
    const badgeText = isEmpty ? '⏳ Pre-match · fără date live' : `${row.player_stats?.count||0} players · ${row.incidents?.count||0} events${shotCount?' · '+shotCount+' shots':''}`;
    const card=document.createElement("section");
    card.className="bp-mdp-card";
    card.dataset.eventId=String(row.event_id);
    card.innerHTML=`<div class="bp-mdp-head">
      <div class="bp-mdp-title">📦 Match Data Pack</div>
      <div class="bp-mdp-badge${isEmpty?' bp-mdp-badge-prematch':''}">${badgeText}</div>
    </div>
    <div class="bp-mdp-tabs">
      <button class="bp-mdp-tab active" data-tab="stats">Stats</button>
      <button class="bp-mdp-tab" data-tab="players">Players</button>
      <button class="bp-mdp-tab" data-tab="timeline">Timeline</button>
      <button class="bp-mdp-tab" data-tab="shots">Shots${hasShotmap?' ⚽':''}</button>
      <button class="bp-mdp-tab" data-tab="meta">Metadata</button>
    </div>
    <div class="bp-mdp-body">${bodyFor(row,"stats")}</div>`;

    card.addEventListener("click", ev=>{
      const btn=ev.target.closest(".bp-mdp-tab");
      if(!btn) return;
      card.querySelectorAll(".bp-mdp-tab").forEach(b=>b.classList.remove("active"));
      btn.classList.add("active");
      card.querySelector(".bp-mdp-body").innerHTML=bodyFor(row,btn.dataset.tab);
    });

    host.appendChild(card);
  }

  let t=null;
  function tick(){
    if(!pack) return;
    clearTimeout(t);
    t=setTimeout(()=>{
      const found=findMatch();
      if(found) inject(found.row, found.modal);
    },120);
  }

  addCss();
  load().then(tick);
  new MutationObserver(tick).observe(document.documentElement,{childList:true,subtree:true,characterData:true});
  setInterval(tick,1500);
})();
