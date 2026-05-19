/**
 * BetPredict Pro — Match Data Pack UI (Pasul 25)
 * Injectează un bloc suplimentar în Match Detail fără să rescrie index.html.
 */
(function () {
  const DATA_URL = "data/match_data_pack.json?v=pas25";
  let pack = null;
  let byPair = new Map();
  let byId = new Map();

  const css = `
    .bp-mdp-card{margin:14px 22px 96px;border:1px solid rgba(56,189,248,.20);border-radius:20px;background:linear-gradient(180deg,rgba(13,23,42,.96),rgba(8,15,29,.96));box-shadow:0 12px 40px rgba(0,0,0,.28);overflow:hidden}
    .bp-mdp-head{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid rgba(148,163,184,.12)}
    .bp-mdp-title{font-weight:900;letter-spacing:.08em;text-transform:uppercase;color:#dbeafe;font-size:13px}
    .bp-mdp-badge{font:800 11px/1 ui-monospace,monospace;color:#38bdf8;background:rgba(56,189,248,.10);border:1px solid rgba(56,189,248,.24);padding:6px 9px;border-radius:999px}
    .bp-mdp-tabs{display:flex;gap:8px;overflow:auto;padding:12px 14px;border-bottom:1px solid rgba(148,163,184,.10)}
    .bp-mdp-tab{flex:0 0 auto;border:1px solid rgba(148,163,184,.16);background:rgba(15,23,42,.84);color:#94a3b8;border-radius:999px;padding:8px 11px;font-weight:800;font-size:11px;letter-spacing:.06em;text-transform:uppercase}
    .bp-mdp-tab.active{color:#e0f2fe;border-color:rgba(56,189,248,.45);background:rgba(37,99,235,.20)}
    .bp-mdp-body{padding:14px 16px;color:#cbd5e1}
    .bp-mdp-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
    .bp-mdp-box{border:1px solid rgba(148,163,184,.12);border-radius:14px;background:rgba(15,23,42,.60);padding:11px}
    .bp-mdp-k{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.08em;font-weight:900;margin-bottom:5px}
    .bp-mdp-v{font:900 18px/1.1 ui-monospace,monospace;color:#e5eef9}
    .bp-mdp-muted{color:#94a3b8;font-size:13px;line-height:1.45}
    .bp-mdp-row{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px solid rgba(148,163,184,.09);font-size:13px}
    .bp-mdp-row:last-child{border-bottom:0}
    .bp-mdp-list{display:flex;flex-direction:column;gap:8px}
    .bp-mdp-player{display:grid;grid-template-columns:32px 1fr auto;align-items:center;gap:10px;border:1px solid rgba(148,163,184,.12);border-radius:13px;background:rgba(15,23,42,.58);padding:8px}
    .bp-mdp-avatar{width:32px;height:32px;border-radius:50%;object-fit:cover;background:rgba(148,163,184,.16)}
    .bp-mdp-pill{font:800 11px/1 ui-monospace,monospace;border-radius:999px;padding:5px 7px;background:rgba(16,185,129,.12);color:#34d399;border:1px solid rgba(16,185,129,.22)}
    .bp-mdp-timeline{display:flex;flex-direction:column;gap:8px}
    .bp-mdp-event{display:grid;grid-template-columns:44px 1fr;gap:10px;align-items:start;border:1px solid rgba(148,163,184,.12);border-radius:13px;background:rgba(15,23,42,.58);padding:9px}
    .bp-mdp-minute{font:900 13px/1 ui-monospace,monospace;color:#60a5fa}
    @media(max-width:560px){.bp-mdp-card{margin:12px 22px 90px}.bp-mdp-grid{grid-template-columns:1fr}.bp-mdp-title{font-size:12px}}
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
  function num(v,d=2){ return (v===null||v===undefined||v==="") ? "—" : Number(v).toFixed(d).replace(/\.0+$/,""); }

  async function load(){
    try{
      const r=await fetch(DATA_URL,{cache:"no-store"});
      if(!r.ok) return;
      pack=await r.json();
      for(const row of (pack.results||[])){
        if(row.event_id) byId.set(String(row.event_id), row);
        byPair.set(pairKey(row.home_team,row.away_team), row);
      }
    }catch(e){ console.warn("Match Data Pack load failed", e); }
  }

  function findMatch(){
    const nodes=[...document.querySelectorAll("h1,h2,h3,.modal-title,.drawer-title,[class*='title']")];
    for(const n of nodes){
      const t=(n.textContent||"").trim();
      if(!/\s+vs\s+/i.test(t)) continue;
      const clean=t.replace(/\s+/g," ");
      const parts=clean.split(/\s+vs\s+/i);
      if(parts.length<2) continue;
      const h=parts[0].replace(/^.*?([A-ZĂÂÎȘȚ0-9][\s\S]*)$/,"$1").trim();
      const a=parts.slice(1).join(" vs ").trim();
      const direct=byPair.get(pairKey(h,a));
      if(direct) return {row:direct,node:n};
      for(const row of (pack?.results||[])){
        if(norm(t).includes(norm(row.home_team)) && norm(t).includes(norm(row.away_team))) return {row,node:n};
      }
    }
    return null;
  }

  function closestPanel(node){
    let el=node;
    let best=null;
    while(el && el!==document.body){
      const st=getComputedStyle(el);
      const rect=el.getBoundingClientRect();
      if(rect.width>260 && rect.height>180 && (st.position==="fixed" || st.position==="absolute" || el.scrollHeight>window.innerHeight*.45)){
        best=el;
      }
      el=el.parentElement;
    }
    return best || node.parentElement || document.body;
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

  function renderStats(row){
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
    if(!top.length) return `<div class="bp-mdp-muted">Player-stats indisponibil momentan. Pentru pre-match este normal; se populează mai ales live/post-match.</div>`;
    return `<div class="bp-mdp-list">${top.map(p=>`
      <div class="bp-mdp-player">
        <img class="bp-mdp-avatar" src="${esc(p.image_url||"")}" onerror="this.style.display='none'">
        <div><b>${esc(p.short_name||p.name)}</b><div class="bp-mdp-muted">${esc(p.position||"—")} · ${p.minutes_played??0} min · xG ${num(p.expected_goals)} · xA ${num(p.expected_assists)}</div></div>
        <span class="bp-mdp-pill">${num(p.rating,1)}</span>
      </div>`).join("")}</div>`;
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
      <div class="bp-mdp-row"><span>Unavailable players</span><b>${esc(JSON.stringify(lineup.unavailable_players||{}).slice(0,70))}</b></div>
      <div class="bp-mdp-box"><div class="bp-mdp-k">AI preview</div><div class="bp-mdp-muted">${esc(ai.text||"AI preview indisponibil pentru acest meci.")}</div></div>
      <div class="bp-mdp-box" style="margin-top:10px"><div class="bp-mdp-k">Funfacts</div>${facts.length?facts.slice(0,4).map(f=>`<div class="bp-mdp-muted">• ${esc(f.sentence||f.text||JSON.stringify(f))}</div>`).join(""):`<div class="bp-mdp-muted">Funfacts indisponibil.</div>`}</div>`;
  }

  function bodyFor(row, tab){
    if(tab==="stats") return renderStats(row);
    if(tab==="players") return renderPlayers(row);
    if(tab==="timeline") return renderTimeline(row);
    return renderMeta(row);
  }

  function inject(row,node){
    const host=closestPanel(node);
    if(!host) return;
    const old=host.querySelector(".bp-mdp-card");
    if(old && old.dataset.eventId===String(row.event_id)) return;
    if(old) old.remove();

    const card=document.createElement("section");
    card.className="bp-mdp-card";
    card.dataset.eventId=String(row.event_id);
    card.innerHTML=`<div class="bp-mdp-head">
      <div class="bp-mdp-title">📦 Match Data Pack</div>
      <div class="bp-mdp-badge">${row.player_stats?.count||0} players · ${row.incidents?.count||0} events</div>
    </div>
    <div class="bp-mdp-tabs">
      <button class="bp-mdp-tab active" data-tab="stats">Stats</button>
      <button class="bp-mdp-tab" data-tab="players">Players</button>
      <button class="bp-mdp-tab" data-tab="timeline">Timeline</button>
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
      if(found) inject(found.row, found.node);
    },120);
  }

  addCss();
  load().then(tick);
  new MutationObserver(tick).observe(document.documentElement,{childList:true,subtree:true,characterData:true});
  setInterval(tick,1500);
})();
