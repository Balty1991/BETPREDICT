/**
 * sharp_ui.js — BetPredict v7 "SHARP" overlay
 * ============================================
 * Panou flotant non-invaziv care afiseaza strategiile v7 (harvest-the-edge):
 *   💎 VALUE      — value bets vs pretul corect Pinnacle (EV real)
 *   🔥 STEAM      — cote care se scurteaza la multi book-i (bani sharp)
 *   ⚖️ ARBITRAJ   — profit garantat intre bookmakeri
 *   🌐 POLYMARKET — divergenta multime sharp vs book soft
 *   📈 CLV        — jurnal paper-trading + CLV real per strategie
 *
 * Nu atinge codul React existent — injecteaza un buton + drawer in DOM.
 * Acelasi pattern ca match_data_pack_ui.js / v6_ui.js.
 */
(function () {
  "use strict";
  var SIGNALS_URL = "data/sharp_value_signals.json?v=v7";
  var REF_URL = "data/referee_ou_edge.json?v=v7";
  var CLV_URL = "data/sharp_paper_trades.json?v=v7";
  var SUPERBET_URL = "data/superbet_edge_signals.json?v=v7";
  var SUPERBET_HIST_URL = "data/superbet_edge_history.json?v=v7";
  var PYRAMID_URL = "data/pyramid_state.json?v=v7";
  var POOLS_URL = "data/pyramid_assistant.json?v=v7";
  var RESULTS_URL = "data/recent_results.json?v=v7";
  var UPDATE_URL = "data/update_status.json?v=v7";

  var state = { signals: null, ref: null, clv: null, superbet: null, superbetHist: null, pyramid: null,
                pools: null, results: null, updates: null,
                tab: "superbet", superbetSub: "live", open: false };

  var CSS = "" +
    "#sharp-fab{position:fixed;right:16px;bottom:88px;z-index:99998;width:56px;height:56px;border-radius:50%;" +
    "border:none;cursor:pointer;background:linear-gradient(135deg,#10b981,#059669);color:#fff;font-size:22px;" +
    "box-shadow:0 8px 24px rgba(16,185,129,.45);display:flex;align-items:center;justify-content:center}" +
    "#sharp-fab .sh-badge{position:absolute;top:-4px;right:-4px;background:#ef4444;color:#fff;font:800 10px/1 ui-monospace,monospace;" +
    "min-width:18px;height:18px;border-radius:9px;display:flex;align-items:center;justify-content:center;padding:0 4px}" +
    "#sharp-drawer{position:fixed;inset:0;z-index:99999;background:rgba(2,6,23,.72);backdrop-filter:blur(4px);" +
    "display:none;align-items:flex-end;justify-content:center}" +
    "#sharp-drawer.on{display:flex}" +
    "#sharp-sheet{width:100%;max-width:680px;height:90vh;max-height:90vh;background:linear-gradient(180deg,#0b1220,#070d18);" +
    "border:1px solid rgba(16,185,129,.25);border-radius:20px 20px 0 0;box-shadow:0 -12px 40px rgba(0,0,0,.5);" +
    "display:flex;flex-direction:column;overflow:hidden}" +
    ".sh-head{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid rgba(148,163,184,.12)}" +
    ".sh-title{font:900 14px/1 system-ui;letter-spacing:.04em;color:#d1fae5;text-transform:uppercase}" +
    ".sh-x{flex:0 0 auto;background:rgba(148,163,184,.14);border:none;color:#cbd5e1;width:34px;height:34px;border-radius:9px;cursor:pointer;font-size:16px}" +
    ".sh-tabs{flex:0 0 auto;display:flex;gap:5px;overflow-x:auto;overflow-y:hidden;padding:11px 10px;border-bottom:1px solid rgba(148,163,184,.10);" +
    "scrollbar-width:none;-webkit-overflow-scrolling:touch;scroll-snap-type:x proximity}" +
    ".sh-tabs::-webkit-scrollbar{display:none}" +
    ".sh-tab{flex:0 0 auto;scroll-snap-align:start;border:1px solid rgba(148,163,184,.16);background:rgba(15,23,42,.7);color:#94a3b8;" +
    "border-radius:999px;padding:8px 10px;font:800 11.5px/1 system-ui;cursor:pointer;white-space:nowrap}" +
    ".sh-tab.active{color:#062;background:#34d399;border-color:#34d399}" +
    ".sh-body{flex:1 1 auto;min-height:0;padding:12px;overflow-y:auto;overflow-x:hidden;-webkit-overflow-scrolling:touch}" +
    ".sh-card{border:1px solid rgba(148,163,184,.14);border-radius:14px;background:rgba(15,23,42,.6);padding:11px 12px;margin-bottom:9px}" +
    ".sh-card.steam{border-left:3px solid #f59e0b}.sh-card.value{border-left:3px solid #10b981}" +
    ".sh-card.arb{border-left:3px solid #38bdf8}.sh-card.poly{border-left:3px solid #a78bfa}" +
    ".sh-match{font:800 13px/1.3 system-ui;color:#e5eef9}" +
    ".sh-league{font:600 10px/1 system-ui;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin-top:3px}" +
    ".sh-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}" +
    ".sh-pill{font:800 10.5px/1 ui-monospace,monospace;padding:5px 8px;border-radius:8px;background:rgba(15,23,42,.85);" +
    "border:1px solid rgba(148,163,184,.16);color:#cbd5e1}" +
    ".sh-pill.g{color:#34d399;border-color:rgba(52,211,153,.4)}.sh-pill.y{color:#fbbf24;border-color:rgba(251,191,36,.4)}" +
    ".sh-pill.b{color:#38bdf8;border-color:rgba(56,189,248,.4)}.sh-pill.p{color:#c4b5fd;border-color:rgba(167,139,250,.4)}" +
    ".sh-empty{text-align:center;color:#64748b;padding:32px 12px;font:600 13px/1.5 system-ui}" +
    ".sh-note{font:600 11px/1.4 system-ui;color:#94a3b8;padding:6px 2px 12px}" +
    ".sh-legs{margin-top:8px;display:flex;flex-direction:column;gap:5px}" +
    ".sh-leg{display:flex;justify-content:space-between;font:700 11px/1 ui-monospace,monospace;color:#bae6fd;" +
    "background:rgba(56,189,248,.08);padding:6px 8px;border-radius:7px}" +
    ".sh-kpi{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px}" +
    ".sh-kpi-box{border:1px solid rgba(148,163,184,.14);border-radius:12px;background:rgba(15,23,42,.6);padding:10px;text-align:center}" +
    ".sh-kpi-v{font:900 18px/1 ui-monospace,monospace;color:#e5eef9}.sh-kpi-k{font:700 9px/1 system-ui;color:#64748b;text-transform:uppercase;margin-top:5px}" +
    ".sh-outer{border:1px solid rgba(148,163,184,.16);border-radius:14px;background:rgba(15,23,42,.4);margin-top:10px;overflow:hidden}" +
    ".sh-outer>summary{list-style:none;cursor:pointer;padding:11px 12px;font:800 12px/1.3 system-ui;color:#d1fae5;" +
    "display:flex;align-items:center;justify-content:space-between}" +
    ".sh-outer>summary::-webkit-details-marker{display:none}" +
    ".sh-outer>summary::after{content:'▸';color:#64748b;font-size:11px;margin-left:8px}" +
    ".sh-outer[open]>summary::after{content:'▾'}" +
    ".sh-outer>summary:hover{background:rgba(52,211,153,.08)}" +
    ".sh-outer-body{padding:2px 10px 10px}" +
    ".sh-ev{border:1px solid rgba(148,163,184,.12);border-radius:10px;background:rgba(15,23,42,.55);margin-bottom:6px;overflow:hidden}" +
    ".sh-ev>summary{list-style:none;cursor:pointer;padding:9px 10px;display:flex;align-items:center;justify-content:space-between;gap:8px}" +
    ".sh-ev>summary::-webkit-details-marker{display:none}" +
    ".sh-ev>summary::after{content:'▸';color:#64748b;font-size:10px;flex:0 0 auto}" +
    ".sh-ev[open]>summary::after{content:'▾'}" +
    ".sh-ev-sum-l{min-width:0;flex:1 1 auto}" +
    ".sh-ev-name{font:800 12.5px/1.3 system-ui;color:#e5eef9;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
    ".sh-ev-meta{font:600 10px/1 system-ui;color:#64748b;margin-top:2px}" +
    ".sh-ev-body{padding:0 10px 8px;display:flex;flex-direction:column;gap:5px}" +
    ".sh-leg-line{font:700 10.5px/1.4 ui-monospace,monospace;color:#cbd5e1;background:rgba(15,23,42,.7);" +
    "border-radius:7px;padding:6px 8px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}" +
    ".sh-leg-line .lg-mk{color:#e5eef9;font-weight:800;flex:1 1 auto;min-width:120px}" +
    ".sh-status{font:900 10px/1 ui-monospace,monospace;padding:2px 6px;border-radius:6px;flex:0 0 auto}" +
    ".sh-status.win{color:#34d399;background:rgba(52,211,153,.14)}" +
    ".sh-status.loss{color:#f87171;background:rgba(248,113,113,.14)}" +
    ".sh-status.pending{color:#94a3b8;background:rgba(148,163,184,.12)}" +
    ".sh-banner{border-radius:12px;padding:9px 11px;font:700 11px/1.4 system-ui;margin-bottom:10px}" +
    ".sh-banner.green{background:rgba(52,211,153,.10);border:1px solid rgba(52,211,153,.3);color:#a7f3d0}" +
    ".sh-banner.yellow{background:rgba(251,191,36,.10);border:1px solid rgba(251,191,36,.3);color:#fde68a}" +
    ".sh-banner.red{background:rgba(248,113,113,.10);border:1px solid rgba(248,113,113,.3);color:#fecaca}" +
    ".sh-inp-wrap{display:flex;flex-direction:column;gap:3px;font:700 9.5px/1 system-ui;color:#64748b;text-transform:uppercase;letter-spacing:.04em}" +
    ".sh-inp{font:800 13px/1 ui-monospace,monospace;color:#e5eef9;background:rgba(15,23,42,.85);" +
    "border:1px solid rgba(148,163,184,.24);border-radius:8px;padding:6px 8px;width:92px}" +
    ".sh-inp:focus{outline:none;border-color:rgba(52,211,153,.5)}" +
    ".sh-track{border:1px solid rgba(148,163,184,.16);border-radius:16px;background:rgba(15,23,42,.4);padding:12px;margin-bottom:14px}" +
    ".sh-track-h{font:900 13px/1.3 system-ui;color:#d1fae5;margin-bottom:8px}" +
    ".sh-mini-btn{font:800 11.5px/1 system-ui;color:#cbd5e1;background:rgba(148,163,184,.14);" +
    "border:1px solid rgba(148,163,184,.24);border-radius:9px;padding:9px 12px;cursor:pointer}" +
    ".sh-mini-btn.on{color:#062;background:#34d399;border-color:#34d399}" +
    ".sh-ev-row{display:flex;justify-content:space-between;gap:8px;font:700 10.5px/1.4 ui-monospace,monospace;" +
    "color:#cbd5e1;background:rgba(15,23,42,.7);padding:6px 8px;border-radius:7px;margin-bottom:4px;border-left:3px solid transparent}" +
    ".sh-ev-row.win{border-left-color:#34d399}.sh-ev-row.loss{border-left-color:#f87171}" +
    ".sh-card.suggest{border-left:3px solid #f59e0b}.sh-card.pending{border-left:3px solid #38bdf8}" +
    ".sh-step-strip{display:flex;gap:6px;overflow-x:auto;padding:2px 2px 10px;-webkit-overflow-scrolling:touch;scrollbar-width:none}" +
    ".sh-step-strip::-webkit-scrollbar{display:none}" +
    ".sh-step{flex:0 0 auto;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;" +
    "font:800 11px/1 ui-monospace,monospace;border:2px solid rgba(148,163,184,.25);color:#64748b;background:rgba(15,23,42,.5)}" +
    ".sh-step.win{border-color:#34d399;color:#34d399;background:rgba(52,211,153,.14)}" +
    ".sh-step.pending{border-color:#38bdf8;color:#38bdf8;background:rgba(56,189,248,.14)}" +
    ".sh-step.suggest{border-color:#f59e0b;color:#f59e0b;background:rgba(245,158,11,.14)}";

  function inject(id, css) {
    if (document.getElementById(id)) return;
    var s = document.createElement("style"); s.id = id; s.textContent = css;
    document.head.appendChild(s);
  }

  function fetchJSON(url) {
    return fetch(url, { cache: "no-store" }).then(function (r) {
      return r.ok ? r.json() : null;
    }).catch(function () { return null; });
  }

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]; }); }

  function countActive() {
    var s = state.signals || {}, r = state.ref || {};
    return ((s.value_signals || []).length) + ((s.arbitrage || []).length) +
           ((s.polymarket_divergence || []).length) + ((r.signals || []).length);
  }

  function pill(txt, cls) { return '<span class="sh-pill ' + (cls || "") + '">' + esc(txt) + "</span>"; }

  function formatAge(minutes) {
    if (minutes == null || !isFinite(minutes)) return "necunoscut";
    if (minutes < 1) return "acum";
    if (minutes < 60) return Math.round(minutes) + " min";
    return (minutes / 60).toFixed(minutes < 600 ? 1 : 0) + " h";
  }

  function renderUpdates() {
    var d = state.updates;
    if (!d) return '<div class="sh-empty">Statusul se publică după următoarea actualizare completă.</div>';
    var statusClass = d.status === "GREEN" ? "green" : (d.status === "RED" ? "red" : "yellow");
    var sources = d.sources || {};
    var cards = Object.keys(sources).map(function (key) {
      var s = sources[key] || {};
      var fresh = s.available && (s.age_minutes == null || s.age_minutes <= (key === "live" ? 30 : 150));
      return '<div class="sh-card"><div class="sh-match">' + esc(key.replace(/_/g, " ")) + '</div>' +
        '<div class="sh-row">' + pill(s.available ? (fresh ? "date disponibile" : "date întârziate") : "fișier indisponibil", fresh ? "g" : "y") +
        pill("actualizat " + formatAge(s.age_minutes) + " în urmă", fresh ? "b" : "y") +
        pill("ciclu " + (s.cadence || "—")) +
        (s.count != null ? pill(String(s.count) + " intrări") : "") + '</div></div>';
    }).join("");
    var q = d.api_quota || {};
    var quotaClass = q.status === "healthy" ? "g" : (q.status === "exhausted" ? "y" : "b");
    return '<div class="sh-banner ' + statusClass + '"><b>Stare platformă: ' + esc(d.status || "necunoscut") + '</b> · scor sănătate ' + esc(d.health_score) + '/100. Aici vezi ultima stare publicată de pipeline, nu o promisiune de bilet.</div>' +
      '<div class="sh-kpi"><div class="sh-kpi-box"><div class="sh-kpi-v">' + esc(d.workflow?.daily || "orar") + '</div><div class="sh-kpi-k">actualizare date</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + esc(d.workflow?.live || "15 minute") + '</div><div class="sh-kpi-k">actualizare live</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + esc(q.status || "—") + '</div><div class="sh-kpi-k">cotă API</div></div></div>' +
      '<div class="sh-row">' + pill("cotă API: " + (q.remaining == null ? "—" : q.remaining), quotaClass) +
      (q.reset_at ? pill("reset " + new Date(q.reset_at).toLocaleTimeString("ro-RO", {hour:"2-digit",minute:"2-digit"}), "b") : "") + '</div>' +
      '<div class="sh-note">Fluxuri: date principale ' + esc(d.workflow?.daily || "orar") + ', live ' + esc(d.workflow?.live || "15 minute") + ', îmbogățire profundă ' + esc(d.workflow?.deep_enrichment || "zilnic") + '.</div>' + cards;
  }

  function statusBadge(result, score) {
    var sc = score ? " (" + esc(score) + ")" : "";
    if (result === "WIN") return '<span class="sh-status win">✅ WIN' + sc + "</span>";
    if (result === "LOSS") return '<span class="sh-status loss">❌ LOSS' + sc + "</span>";
    return '<span class="sh-status pending">⏳ în așteptare</span>';
  }

  // Grupeaza un array de picioare (watchlist sau jurnal) dupa event_id, pastrand ordinea de aparitie.
  function groupByEvent(rows) {
    var order = [], byId = {};
    (rows || []).forEach(function (r) {
      var id = r.event_id;
      if (!byId[id]) {
        byId[id] = { event_id: id, home_team: r.home_team, away_team: r.away_team,
                     league: r.league, event_time_label: r.event_time_label, legs: [] };
        order.push(id);
      }
      byId[id].legs.push(r);
    });
    return order.map(function (id) {
      var g = byId[id];
      // picioarele recomandate (sau cu fair% mai mare) primele, ca sa fie clar ce sa iei in calcul
      g.legs.sort(function (a, b) {
        if (!!b.recommended !== !!a.recommended) return b.recommended ? 1 : -1;
        return (b.fair_prob_pct || 0) - (a.fair_prob_pct || 0);
      });
      return g;
    });
  }

  // Randeaza un bloc "watchlist completa" colapsabil: outer <details> + cate un <details> per meci.
  // Picioarele in fiecare meci sunt sortate cu cel recomandat (scor: prob+incredere+steam) primul.
  function renderEventList(rows, legLineFn, outerLabel) {
    var groups = groupByEvent(rows);
    var body = groups.map(function (g) {
      var anySteam = g.legs.some(function (l) { return l.steam_confirmed; });
      var best = g.legs[0]; // dupa sortarea din groupByEvent, primul e cel recomandat
      var bestHint = g.legs.length > 1 && best.market_label
        ? '<div class="sh-ev-meta" style="color:#34d399">⭐ recomandat: ' + esc(best.market_label) +
          (best.outcome_label ? " (" + esc(best.outcome_label) + ")" : "") +
          (best.fair_prob_pct != null ? " · fair " + best.fair_prob_pct + "%" : "") + "</div>"
        : "";
      var summary = '<div class="sh-ev-sum-l"><div class="sh-ev-name">' + esc(g.home_team) + " vs " + esc(g.away_team) + "</div>" +
        '<div class="sh-ev-meta">' + esc(g.event_time_label || "") + (g.league ? " · " + esc(g.league) : "") +
        " · " + g.legs.length + (g.legs.length === 1 ? " piață" : " piețe") + "</div>" + bestHint + "</div>" +
        (anySteam ? '<span style="font-size:13px">🔥</span>' : "");
      return '<details class="sh-ev"><summary>' + summary + '</summary>' +
        '<div class="sh-ev-body">' + g.legs.map(legLineFn).join("") + "</div></details>";
    }).join("");
    return '<details class="sh-outer"><summary>' + esc(outerLabel) + " (" + rows.length + " picioare, " + groups.length + " meciuri)</summary>" +
      '<div class="sh-outer-body">' + body + "</div></details>";
  }

  function renderValue() {
    var arr = (state.signals && state.signals.value_signals) || [];
    var gate = state.signals && state.signals.clv_gate;
    if (!arr.length && gate && gate.paused) {
      return '<div class="sh-banner yellow">⏸️ Semnalele value sunt în pauză automată: ' + esc(gate.reason || "") +
        '</div><div class="sh-note">CLV (closing line value) e cel mai cinstit predictor al profitului pe termen lung. ' +
        'Publicarea se reia automat când selecția redevine competitivă cu piața.</div>';
    }
    if (!arr.length) return '<div class="sh-empty">Niciun value bet vs. pretul Pinnacle acum.<br>Reapare pe masura ce book-urile soft gresesc preturi.</div>';
    return '<div class="sh-note">EV real vs. probabilitatea corecta (Pinnacle no-vig). Value = book soft &gt; pret corect.</div>' +
      arr.map(function (v) {
        return '<div class="sh-card value"><div class="sh-match">' + esc(v.home_team) + " vs " + esc(v.away_team) + "</div>" +
          '<div class="sh-league">' + esc(v.league || "") + " · " + esc(v.market) + " / " + esc(v.outcome) + "</div>" +
          '<div class="sh-row">' + pill("EV +" + v.ev_pct + "%", "g") + pill(v.bet_odds + " @ " + (v.bet_book || "?"), "b") +
          pill("corect " + v.fair_odd) + pill("Kelly " + v.kelly_pct + "%", "y") +
          (v.steam_confirmed ? pill("🔥 STEAM", "y") : "") + "</div></div>";
      }).join("");
  }

  function renderSteam() {
    var arr = (state.signals && state.signals.steam_signals) || [];
    if (!arr.length) return '<div class="sh-empty">Nicio miscare steam detectata.</div>';
    return '<div class="sh-note">Cote care se scurteaza la multi bookmakeri = bani sharp au intrat.</div>' +
      arr.slice(0, 40).map(function (v) {
        return '<div class="sh-card steam"><div class="sh-match">' + esc(v.home_team) + " vs " + esc(v.away_team) + "</div>" +
          '<div class="sh-league">' + esc(v.league || "") + " · " + esc(v.market) + " / " + esc(v.outcome) + "</div>" +
          '<div class="sh-row">' + pill("↓ " + v.n_shortening + " book-i", "y") +
          pill("best " + v.best_odds + " @ " + (v.best_book || "?"), "b") + "</div></div>";
      }).join("");
  }

  function renderArb() {
    var arr = (state.signals && state.signals.arbitrage) || [];
    if (!arr.length) return '<div class="sh-empty">Niciun arbitraj activ.<br>Reapare cand cotele intre book-i diverg suficient.</div>';
    return '<div class="sh-note">Profit GARANTAT indiferent de rezultat. Miza splituita conform procentelor.</div>' +
      arr.map(function (a) {
        return '<div class="sh-card arb"><div class="sh-match">' + esc(a.home_team) + " vs " + esc(a.away_team) + "</div>" +
          '<div class="sh-league">' + esc(a.league || "") + " · " + esc(a.market) + "</div>" +
          '<div class="sh-row">' + pill("profit +" + a.guaranteed_roi_pct + "%", "b") + "</div>" +
          '<div class="sh-legs">' + (a.legs || []).map(function (l) {
            return '<div class="sh-leg"><span>' + esc(l.outcome) + " @ " + esc(l.book) + "</span><span>cota " + l.odds + " · miza " + l.stake_pct + "%</span></div>";
          }).join("") + "</div></div>";
      }).join("");
  }

  function renderPoly() {
    var arr = (state.signals && state.signals.polymarket_divergence) || [];
    if (!arr.length) return '<div class="sh-empty">Nicio divergenta Polymarket semnificativa.</div>';
    return '<div class="sh-note">Multimea sharp de pe Polymarket vede mai multa valoare decat book-ul soft.</div>' +
      arr.map(function (p) {
        return '<div class="sh-card poly"><div class="sh-match">' + esc(p.home_team) + " vs " + esc(p.away_team) + "</div>" +
          '<div class="sh-league">' + esc(p.league || "") + " · " + esc(p.market) + " / " + esc(p.outcome) + "</div>" +
          '<div class="sh-row">' + pill("+" + p.divergence_pp + "pp", "p") + pill("poly " + p.poly_prob_pct + "%", "p") +
          pill("book " + p.book_implied_pct + "%") + pill(p.bet_odds + " @ " + (p.bet_book || "?"), "b") + "</div></div>";
      }).join("");
  }

  function renderRef() {
    var arr = (state.ref && state.ref.signals) || [];
    var cov = state.ref && state.ref.summary;
    if (!arr.length) {
      var note = cov && cov.coverage_note && cov.coverage_note !== "ok" ? cov.coverage_note : "Niciun edge arbitru/forma acum.";
      return '<div class="sh-empty">' + esc(note) + "</div>";
    }
    return '<div class="sh-note">Arbitru cu tendinta clara de goluri + forma echipelor confirma directia.</div>' +
      arr.map(function (s) {
        return '<div class="sh-card value"><div class="sh-match">' + esc(s.home_team) + " vs " + esc(s.away_team) + "</div>" +
          '<div class="sh-league">arbitru ' + esc(s.referee) + " · " + esc(s.referee_avg_goals) + "g/meci · " + esc(s.referee_tendency) + "</div>" +
          '<div class="sh-row">' + pill((s.outcome || "").toUpperCase() + " 2.5", "g") + pill("EV +" + s.ev_pct + "%", "g") +
          pill(s.bet_odds + " cota", "b") + pill("model " + s.model_prob_pct + "%", "y") +
          (s.lineup_confirmed ? pill("✓ lineup") : "") + "</div></div>";
      }).join("");
  }

  function renderCLV() {
    var d = state.clv;
    if (!d || !d.overall) return '<div class="sh-empty">Jurnal CLV inca gol. Se populeaza pe masura ce ruleaza pipeline-ul.</div>';
    var o = d.overall;
    var kpis = '<div class="sh-kpi">' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + (o.avg_clv_pct == null ? "–" : o.avg_clv_pct + "%") + '</div><div class="sh-kpi-k">CLV mediu</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + o.n_trades + '</div><div class="sh-kpi-k">trade-uri</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + (o.roi_pct == null ? "–" : o.roi_pct + "%") + '</div><div class="sh-kpi-k">ROI settle-uit</div></div></div>';
    var per = Object.keys(d.by_strategy || {}).map(function (k) {
      var a = d.by_strategy[k];
      return '<div class="sh-card"><div class="sh-match">' + esc(k) + "</div>" +
        '<div class="sh-row">' + pill("CLV " + (a.avg_clv_pct == null ? "–" : a.avg_clv_pct + "%"), a.avg_clv_pct > 0 ? "g" : "") +
        pill(a.n_trades + " trades") + pill("win " + (a.win_rate_pct == null ? "–" : a.win_rate_pct + "%")) +
        pill("ROI " + (a.roi_pct == null ? "–" : a.roi_pct + "%"), a.roi_pct > 0 ? "g" : "") + "</div></div>";
    }).join("");
    return '<div class="sh-note">CLV pozitiv pe &ge;100 trade-uri settle-uite = strategie dovedita. Sub atat = orientativ.</div>' + kpis + per;
  }

  function subNav() {
    var subs = [{ id: "live", label: "🎯 Live" }, { id: "monitor", label: "📊 Monitor" }];
    return '<div class="sh-row" style="margin-bottom:10px">' + subs.map(function (s) {
      return '<button class="sh-tab superbet-sub' + (state.superbetSub === s.id ? " active" : "") + '" data-sub="' + s.id + '">' + s.label + "</button>";
    }).join("") + "</div>";
  }

  function healthBanner(d) {
    var h = d.health;
    if (!h || h.status === "GREEN") return "";
    var cls = h.status === "RED" ? "red" : "yellow";
    var icon = h.status === "RED" ? "🔴" : "🟡";
    return '<div class="sh-banner ' + cls + '">' + icon + " " + esc(h.issues.join(" · ")) + "</div>";
  }

  function exposureNote(d) {
    var e = d.exposure;
    if (!e) return "";
    var txt = "Expunere sugerată azi (toate biletele): " + e.total_after_pct + "% din bancă" +
      " (plafon " + e.cap_pct + "%)";
    if (e.scale_applied < 1) txt += " — redusă automat de la " + e.total_before_pct + "%.";
    return '<div class="sh-note">💰 ' + esc(txt) + "</div>";
  }

  function renderSuperbetLive() {
    var d = state.superbet;
    if (!d || !(d.watchlist || []).length) return '<div class="sh-empty">Niciun prag calculat acum.<br>Reapare cand exista preturi sharp valide pe meciurile apropiate.</div>';
    var tickets = (d.suggested_tickets || []).map(function (t) {
      var legsHtml = (t.legs || []).map(function (l) {
        return '<div class="sh-leg"><span>' + esc(l.home_team) + " – " + esc(l.away_team) + " (" + esc(l.event_time_label || "") + ") · " +
          esc(l.market_label) + " (" + esc(l.outcome_label) + ")" + (l.steam_confirmed ? " 🔥" : "") +
          "</span><span>prag ≥ " + l.threshold_odds + "</span></div>";
      }).join("");
      return '<div class="sh-card value"><div class="sh-match">🎟️ Bilet ' + esc(t.label) + " — " + t.n_legs + " picioare</div>" +
        '<div class="sh-row">' + pill("prag combinat " + t.combined_threshold_odds, "b") +
        pill("prob " + t.combined_probability_pct + "%", "g") +
        pill("miză " + t.stake_amount_lei + " lei (" + t.stake_pct_of_bankroll + "%)", "y") + "</div>" +
        '<div class="sh-legs">' + legsHtml + "</div>" +
        '<div class="sh-note">' + esc(t.instructions) + "</div></div>";
    }).join("");
    var watchHtml = renderEventList(d.watchlist || [], function (r) {
      return '<div class="sh-leg-line"' + (r.recommended ? ' style="border:1px solid rgba(52,211,153,.35)"' : "") + '>' +
        '<span class="lg-mk">' + (r.recommended ? "⭐ " : "") + esc(r.market_label) + " (" + esc(r.outcome_label) + ")" +
        (r.steam_confirmed ? " 🔥" : "") + "</span>" +
        '<span>fair ' + r.fair_prob_pct + "%</span><span>corectă " + r.fair_odds + "</span>" +
        '<span>tipic ~' + r.expected_superbet_odds + "</span>" +
        '<span style="color:#34d399">PRAG ≥ ' + r.threshold_odds + "</span></div>";
    }, "📋 Watchlist completă");
    return healthBanner(d) + exposureNote(d) +
      '<div class="sh-note">' + esc(d.methodology || "") +
      ' Verifică manual în Superbet: dacă cota lor ≥ prag, piciorul are EV real; sub prag, îl sari. Ora e localǎ (România).</div>' +
      (tickets || '<div class="sh-empty">Niciun bilet sugerat momentan.</div>') + watchHtml;
  }

  function renderSuperbetMonitor() {
    var h = state.superbetHist;
    if (!h) return '<div class="sh-empty">Monitorul se populează pe măsură ce rulează pipeline-ul.</div>';
    var ls = h.legs_summary || {}, ts = h.tickets_summary || {}, byc = h.legs_by_confidence || {};
    var kpis = '<div class="sh-kpi">' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + (ls.win_rate_pct == null ? "–" : ls.win_rate_pct + "%") + '</div><div class="sh-kpi-k">win rate picioare</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + ls.n_settled + "/" + ls.n_logged + '</div><div class="sh-kpi-k">picioare decontate</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + (ts.roi_pct_proxy == null ? "–" : ts.roi_pct_proxy + "%") + '</div><div class="sh-kpi-k">ROI proxy bilete</div></div></div>';
    var confHtml = '<div class="sh-row">' +
      pill("ridicat: " + (byc.ridicat && byc.ridicat.win_rate_pct != null ? byc.ridicat.win_rate_pct + "% (" + byc.ridicat.n_settled + ")" : "–"), "g") +
      pill("mediu: " + (byc.mediu && byc.mediu.win_rate_pct != null ? byc.mediu.win_rate_pct + "% (" + byc.mediu.n_settled + ")" : "–"), "y") + "</div>";
    var byMarket = h.legs_by_market || {}, byLeague = h.legs_by_league || {};
    var marketHtml = Object.keys(byMarket).length
      ? '<div class="sh-row">' + Object.keys(byMarket).map(function (mk) {
          var e = byMarket[mk];
          return pill((e.label || mk) + ": " + (e.win_rate_pct == null ? "–" : e.win_rate_pct + "%") + " (" + e.n_settled + ")",
                      e.win_rate_pct != null && e.win_rate_pct >= 50 ? "g" : "y");
        }).join("") + "</div>"
      : '<div class="sh-empty">Încă nimic decontat pe piețe.</div>';
    var leagueHtml = Object.keys(byLeague).length
      ? '<div class="sh-row">' + Object.keys(byLeague).map(function (lg) {
          var e = byLeague[lg];
          return pill(lg + ": " + (e.win_rate_pct == null ? "–" : e.win_rate_pct + "%") + " (" + e.n_settled + ")",
                      e.win_rate_pct != null && e.win_rate_pct >= 50 ? "g" : "y");
        }).join("") + "</div>"
      : '<div class="sh-empty">Încă nimic decontat pe ligi.</div>';
    var legsById = h.legs || {};
    var ticketRows = Object.keys(h.tickets || {}).map(function (k) { return h.tickets[k]; })
      .sort(function (a, b) { return (b.logged_at || "").localeCompare(a.logged_at || ""); }).slice(0, 20);
    var ticketsHtml = ticketRows.length ? ticketRows.map(function (t) {
      var legKeys = t.leg_keys || [];
      var legLines = legKeys.map(function (k, i) {
        var lr = legsById[k];
        var label = (t.legs_summary && t.legs_summary[i]) || k;
        return '<div class="sh-leg-line"><span class="lg-mk">' + esc(label) + "</span>" +
          statusBadge(lr ? lr.result : null, lr ? lr.final_score : null) + "</div>";
      }).join("");
      return '<div class="sh-card"><div class="sh-match">🎟️ ' + esc(t.label) + " — " + legKeys.length + " picioare " + statusBadge(t.result) + "</div>" +
        '<div class="sh-row">' + pill("prag " + t.combined_threshold_odds, "b") +
        (t.profit_units_proxy != null ? pill("profit proxy " + t.profit_units_proxy + "u", t.profit_units_proxy > 0 ? "g" : "") : "") + "</div>" +
        '<details style="margin-top:8px"><summary style="cursor:pointer;font:700 10.5px system-ui;color:#64748b">Vezi picioarele</summary>' +
        '<div class="sh-ev-body" style="padding:6px 0 0">' + legLines + "</div></details></div>";
    }).join("") : '<div class="sh-empty">Niciun bilet decontat încă.</div>';
    var allLegs = Object.keys(legsById).map(function (k) { return legsById[k]; })
      .sort(function (a, b) { return (b.logged_at || "").localeCompare(a.logged_at || ""); });
    var legsHtml = allLegs.length
      ? renderEventList(allLegs, function (r) {
          return '<div class="sh-leg-line"><span class="lg-mk">' + esc(r.market_label || r.market || "") +
            " (" + esc(r.outcome_label || r.outcome || "") + ")</span>" + statusBadge(r.result, r.final_score) + "</div>";
        }, "🎯 Watchlist monitorizată (toate picioarele urmărite)")
      : '<div class="sh-empty">Niciun picior monitorizat încă.</div>';
    return '<div class="sh-note">Urmărește win rate-ul real al picioarelor din watchlist și al biletelor sugerate, ' +
      'decontate automat cu rezultatele finale ale meciurilor. ' + esc(ts.note || "") + "</div>" +
      kpis + '<div class="sh-note">Win rate pe nivel de încredere (sursă preț):</div>' + confHtml +
      '<div class="sh-note" style="margin-top:10px">Win rate pe tip de piață:</div>' + marketHtml +
      '<div class="sh-note" style="margin-top:10px">Win rate pe ligă (top 15 după nr. picioare):</div>' + leagueHtml +
      '<div class="sh-note" style="margin-top:10px">🎟️ Bilete recente:</div>' + ticketsHtml +
      '<div class="sh-note" style="margin-top:10px">Vezi statusul fiecărei predicții individuale, nu doar al biletelor:</div>' + legsHtml;
  }

  function renderSuperbet() {
    return subNav() + (state.superbetSub === "monitor" ? renderSuperbetMonitor() : renderSuperbetLive());
  }

  // O treaptă din istoricul unei piramide: meci, cotă, rezultat, ce s-a întâmplat cu banca.
  function pyramidHistoryRow(h) {
    var line = esc(h.home_team) + " – " + esc(h.away_team) + " · " + esc(h.market_label || h.market) +
      (h.final_score ? " (" + esc(h.final_score) + ")" : "");
    var money = h.result === "WIN"
      ? "miză " + h.stake_lei + " → " + h.bankroll_after + " lei" + (h.withdrawn_lei > 0 ? " (retras " + h.withdrawn_lei + " lei)" : "")
      : "miză " + h.stake_lei + " lei pierdută — reset";
    return '<div class="sh-leg-line"><span class="lg-mk">Pas ' + h.step + ": " + line + "</span>" +
      statusBadge(h.result) + '</div><div class="sh-note" style="margin:0 0 6px">' + esc(money) + "</div>";
  }

  function pyramidTrackCard(key, track) {
    if (!track) return "";
    var pend = track.pending;
    var pendHtml = pend
      ? '<div class="sh-card value"><div class="sh-match">🎯 Pasul ' + pend.step + " (următor): " +
        esc(pend.home_team) + " – " + esc(pend.away_team) + "</div>" +
        '<div class="sh-row">' + pill(esc(pend.market_label || pend.market)) +
        (pend.adj_prob ? pill("prob " + Math.round(pend.adj_prob) + "%", "g") : "") +
        pill("cotă Superbet " + pend.odds, "g") + pill("miză " + pend.stake_lei + " lei", "y") +
        (pend.calibration_status === "NO_DATA" ? pill("eșantion mic — prudență", "y") : "") + "</div></div>"
      : '<div class="sh-empty">Niciun candidat de încredere azi pentru pasul următor — nu forțăm o alegere proastă doar ca să existe una.</div>';
    var hist = (track.history || []).slice().reverse().slice(0, 15).map(pyramidHistoryRow).join("");
    var kpis = '<div class="sh-kpi">' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + track.step + '</div><div class="sh-kpi-k">pas curent</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + track.bankroll_lei + ' lei</div><div class="sh-kpi-k">bancă (paper)</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + track.total_withdrawn_lei + ' lei</div><div class="sh-kpi-k">retras total</div></div></div>';
    var stats = '<div class="sh-note">Cel mai departe ajuns: pasul ' + track.peak_step_reached +
      ' · resetări (pierderi): ' + track.n_resets + ' · runde complete: ' + track.n_runs_completed + '</div>';
    return '<div class="sh-card"><div class="sh-match">' + esc(track.label) + '</div>' +
      kpis + stats + pendHtml +
      (hist ? '<details style="margin-top:8px"><summary style="cursor:pointer;font:700 10.5px system-ui;color:#64748b">Istoric pași</summary>' +
        '<div class="sh-ev-body" style="padding:6px 0 0">' + hist + '</div></details>' : '') +
      '</div>';
  }

  // ============================================================
  // PIRAMIDA PERSONALA (confirmata de tine, salvata pe device)
  // ============================================================
  // Tu confirmi "Am plasat" -> se blocheaza pontul la pasul curent. Cand apare
  // rezultatul (din datele publicate), se valideaza AUTOMAT WIN/LOSS si se
  // avanseaza/reseteaza singura. Starea traieste in localStorage (doar pe telefonul tau).
  var PYR_TRACKS = [
    { key: "safe", label: "Piramidă sigură (~1.30/pas)", max: 10, poolKey: "current_step_pool" },
    { key: "risk", label: "Piramidă risc (~2.50/pas)", max: 3, poolKey: "t2_5" },
  ];
  var PYR_WITHDRAW_FROM = 5, PYR_WITHDRAW_PCT = 0.5, PYR_INITIAL = 10;

  function pyrFresh() { return { step: 0, bankroll: PYR_INITIAL, initial: PYR_INITIAL, withdrawn: 0, placed: null, history: [] }; }
  function pyrLoad(key) {
    try { var s = JSON.parse(localStorage.getItem("bp_pyr_v1_" + key)); return s && typeof s === "object" ? s : pyrFresh(); }
    catch (e) { return pyrFresh(); }
  }
  function pyrSave(key, st) { try { localStorage.setItem("bp_pyr_v1_" + key, JSON.stringify(st)); } catch (e) {} }

  function pyrSettleMkt(market, hs, as_) {
    var t = hs + as_;
    switch (market) {
      case "homeWin": return hs > as_; case "draw": return hs === as_; case "awayWin": return as_ > hs;
      case "over15": return t >= 2; case "under15": return t < 2;
      case "over25": return t >= 3; case "under25": return t < 3;
      case "over35": return t >= 4; case "under35": return t < 4;
      case "btts": return hs > 0 && as_ > 0; case "no_btts": return !(hs > 0 && as_ > 0);
      default: return null;
    }
  }
  function pyrResultFor(eid) {
    var arr = (state.results && state.results.results) || [];
    for (var i = 0; i < arr.length; i++) if (String(arr[i].id) === String(eid)) return arr[i];
    return null;
  }
  // Meci anulat/amanat/abandonat — la agentie pariul pe el devine void (cota 1.00).
  function pyrVoidFor(eid) {
    var arr = (state.results && state.results.voided) || [];
    for (var i = 0; i < arr.length; i++) if (String(arr[i].id) === String(eid)) return arr[i];
    return null;
  }
  function pyrSuggest(cfg, nextStep) {
    var pa = state.pools; if (!pa) return null;
    var pool = cfg.key === "safe"
      ? (pa.current_step_pool || {})[String(nextStep)]
      : ((pa.pools_by_target || {})["t2_5"] || {})[String(nextStep)];
    return (pool && pool.length) ? pool[0] : null;
  }
  // Un pariu plasat poate fi un singur picior sau un combo (acca) — normalizeaza la o lista de legs.
  function pyrLegsOf(p) {
    return (p.legs && p.legs.length) ? p.legs : [{ event_id: p.event_id, market: p.market, market_label: p.market_label, home_team: p.home_team, away_team: p.away_team }];
  }
  function pyrSettleIfNeeded(key, st) {
    if (!st.placed) return;
    var legs = pyrLegsOf(st.placed);
    var outcomes = [];
    for (var i = 0; i < legs.length; i++) {
      var r = pyrResultFor(legs[i].event_id);
      if (r && r.home_score != null && r.away_score != null && String(r.status || "").toLowerCase().indexOf("finish") !== -1) {
        outcomes.push({ r: r });
      } else if (pyrVoidFor(legs[i].event_id)) {
        outcomes.push({ voided: true });
      } else {
        return; // asteapta pana toate meciurile din bilet sunt terminate SAU anulate oficial
      }
    }
    var win = true, scores = [], nVoid = 0, effOdds = st.placed.odds;
    for (var j = 0; j < legs.length; j++) {
      if (outcomes[j].voided) {
        nVoid++; scores.push("anulat");
        // picior anulat intr-un combo: cota lui devine 1.00, restul biletului ramane valabil
        if (legs.length > 1 && legs[j].odds > 1) effOdds = effOdds / legs[j].odds;
        continue;
      }
      var rr = outcomes[j].r;
      var w = pyrSettleMkt(legs[j].market, +rr.home_score, +rr.away_score);
      if (w == null) { st.placed = null; pyrSave(key, st); return; }
      scores.push((+rr.home_score) + "-" + (+rr.away_score));
      if (!w) win = false;
    }
    effOdds = Math.round(effOdds * 1000) / 1000;
    var entry = { step: st.placed.step, home_team: st.placed.home_team, away_team: st.placed.away_team,
      market_label: st.placed.market_label, odds: effOdds, stake: st.placed.stake, legs: st.placed.legs,
      adj_prob: st.placed.adj_prob, final_score: scores.join(", ") };
    if (nVoid === legs.length) {
      // tot pariul anulat — miza inapoi, ramai la acelasi pas si astepti alt pont
      entry.result = "VOID"; entry.bankroll_after = st.bankroll;
    } else if (win) {
      entry.result = "WIN";
      var nb = Math.round(st.placed.stake * effOdds * 100) / 100;
      var ns = st.step + 1, wd = 0;
      if (ns >= PYR_WITHDRAW_FROM) { var profit = nb - st.initial; if (profit > 0) wd = Math.round(profit * PYR_WITHDRAW_PCT * 100) / 100; }
      st.bankroll = Math.round((nb - wd) * 100) / 100; st.withdrawn = Math.round((st.withdrawn + wd) * 100) / 100;
      st.step = ns; entry.bankroll_after = nb; entry.withdrawn_lei = wd;
    } else { entry.result = "LOSS"; st.step = 0; st.bankroll = st.initial; entry.bankroll_after = 0; }
    st.history.push(entry); st.history = st.history.slice(-100); st.placed = null;
    pyrSave(key, st);
  }

  // Sirul de trepte (1..max) cu culoare dupa stare, glisabil orizontal.
  function pyrStepStrip(cfg, st) {
    var runWins = [];
    var h = st.history || [];
    for (var i = h.length - 1; i >= 0; i--) {
      if (h[i].result === "LOSS") break;
      if (h[i].result === "WIN") runWins.unshift(h[i]);
    }
    var chips = [];
    for (var s = 1; s <= cfg.max; s++) {
      var cls = "", win = runWins.filter(function (w) { return w.step === s; })[0];
      if (win) cls = "win";
      else if (st.placed && st.placed.step === s) cls = "pending";
      else if (!st.placed && st.step + 1 === s) cls = "suggest";
      var title = win ? esc(win.home_team) + " – " + esc(win.away_team) : "";
      chips.push('<div class="sh-step ' + cls + '" title="' + title + '">' + s + '</div>');
    }
    return '<div class="sh-step-strip">' + chips.join("") + '</div>';
  }

  // Statistici pe intreg istoricul acestei piramide (toate rundele, nu doar cea curenta).
  function pyrStatsBlock(st) {
    var h = st.history || [];
    if (!h.length) return '';
    var wins = h.filter(function (x) { return x.result === "WIN"; });
    var losses = h.filter(function (x) { return x.result === "LOSS"; });
    var decided = wins.length + losses.length; // VOID nu conteaza la win rate
    var winRate = decided ? Math.round((wins.length / decided) * 100) : 0;
    var peakStep = h.reduce(function (m, x) { return x.result === "WIN" && x.step > m ? x.step : m; }, st.step);
    var lostStakes = Math.round(losses.reduce(function (s, x) { return s + (x.stake || 0); }, 0) * 100) / 100;
    var stats = '<div class="sh-kpi">' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + h.length + '</div><div class="sh-kpi-k">meciuri jucate</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + wins.length + ' / ' + losses.length + '</div><div class="sh-kpi-k">câștig / pierdere</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + winRate + '%</div><div class="sh-kpi-k">win rate</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + peakStep + '</div><div class="sh-kpi-k">pas maxim atins</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + st.withdrawn + ' lei</div><div class="sh-kpi-k">profit retras</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + lostStakes + ' lei</div><div class="sh-kpi-k">pierdut în mize</div></div>' +
      '</div>';
    return '<details class="sh-outer" style="margin-top:8px"><summary>📊 Statistici piramidă</summary>' +
      '<div class="sh-outer-body">' + stats + '</div></details>';
  }

  // Afiseaza fiecare picior al unui combo (acca) ca rand separat, reutilizand stilul din Superbet/Arb.
  function pyrLegLine(l) {
    return '<div class="sh-leg-line"><span class="lg-mk">' + esc(l.home_team) + ' – ' + esc(l.away_team) + '</span>' +
      '<span>' + esc(l.market_label || l.market) + '</span>' +
      (l.event_date ? '<span>' + esc(pyrDayLabel(l.event_date)) + '</span>' : '') +
      (l.odds ? '<span>cotă ' + l.odds + '</span>' : '') + '</div>';
  }
  function pyrLegsList(legs) { return '<div class="sh-legs">' + legs.map(pyrLegLine).join('') + '</div>'; }

  // Eticheta zilei unui eveniment — necesara de cand piramida poate sari pe
  // oferta de maine cand cea de azi s-a epuizat (nu mai e implicit "azi").
  function pyrDayLabel(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    var dayFmt = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Bucharest" });
    var timeFmt = new Intl.DateTimeFormat("ro-RO", { timeZone: "Europe/Bucharest", hour: "2-digit", minute: "2-digit" });
    var evDay = dayFmt.format(d), today = dayFmt.format(new Date()), tomorrow = dayFmt.format(new Date(Date.now() + 86400000));
    var time = timeFmt.format(d);
    if (evDay === today) return "azi " + time;
    if (evDay === tomorrow) return "mâine " + time;
    return d.toLocaleDateString("ro-RO", { day: "2-digit", month: "2-digit" }) + " " + time;
  }

  function myPyramidCard(cfg) {
    var st = pyrLoad(cfg.key);
    pyrSettleIfNeeded(cfg.key, st);
    var curStep = st.placed ? st.step + 1 : st.step;
    var curStepK = st.placed ? "pas (în așteptare)" : "pas curent";
    var kpis = '<div class="sh-kpi">' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + curStep + '</div><div class="sh-kpi-k">' + curStepK + '</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + st.bankroll + ' lei</div><div class="sh-kpi-k">banca ta</div></div>' +
      '<div class="sh-kpi-box"><div class="sh-kpi-v">' + st.withdrawn + ' lei</div><div class="sh-kpi-k">retras total</div></div></div>';
    var strip = pyrStepStrip(cfg, st);
    var mid;
    if (st.placed) {
      var p = st.placed, done = !!pyrLegsOf(p).every(function (l) { return pyrResultFor(l.event_id) || pyrVoidFor(l.event_id); });
      var titleP = (p.legs && p.legs.length) ? "Combo " + p.legs.length + " evenimente" : esc(p.home_team) + " – " + esc(p.away_team);
      mid = '<div class="sh-card pending"><div class="sh-match">⏳ Plasat — pasul ' + p.step + ': ' + titleP + '</div>' +
        (p.legs && p.legs.length ? pyrLegsList(p.legs) : '<div class="sh-row">' + pill(esc(p.market_label)) + "</div>") +
        '<div class="sh-row">' + (p.adj_prob ? pill((p.legs && p.legs.length > 1 ? "prob combinată " : "prob ") + Math.round(p.adj_prob) + "%", "g") : "") +
        (p.event_date ? pill(pyrDayLabel(p.event_date)) : "") + '</div>' +
        (done ? '<div class="sh-row" style="margin-top:8px">' + pill("cotă " + p.odds, "g") + pill("miză " + p.stake + " lei", "y") + '</div>' +
                '<div class="sh-row" style="margin-top:6px">' + pill("rezultat disponibil — se validează…", "g") + '</div>'
             : '<div class="sh-row" style="margin-top:8px">' +
               '<label class="sh-inp-wrap">cotă<input type="number" step="0.01" min="1.01" class="sh-inp" id="pyr-podds-' + cfg.key + '" value="' + p.odds + '"></label>' +
               '<label class="sh-inp-wrap">miză (lei)<input type="number" step="0.1" min="0.1" class="sh-inp" id="pyr-pstake-' + cfg.key + '" value="' + p.stake + '"></label>' +
               '</div>' +
               '<div class="sh-note" style="padding:6px 2px 0">Dacă la agenție cota sau miza reală a fost alta, corectează aici și apasă Salvează.</div>' +
               '<div class="sh-row" style="margin-top:6px">' +
               '<button class="sh-mini-btn on" data-pyr-act="edit" data-pyr-key="' + cfg.key + '">💾 Salvează cotă/miză</button>' +
               '<button class="sh-mini-btn" data-pyr-act="undo" data-pyr-key="' + cfg.key + '">Anulează (nu l-am plasat)</button>' +
               '</div>') +
        '</div>';
    } else {
      var sug = pyrSuggest(cfg, st.step + 1);
      if (st.step + 1 > cfg.max) {
        mid = '<div class="sh-card value"><div class="sh-match">🏆 Ai terminat piramida! Bancă: ' + st.bankroll + ' lei. Poți reseta pentru o rundă nouă.</div></div>';
      } else if (sug) {
        var titleS = (sug.legs && sug.legs.length) ? "Combo " + sug.legs.length + " evenimente" : esc(sug.home_team) + " – " + esc(sug.away_team);
        mid = '<div class="sh-card suggest"><div class="sh-match">🎯 Pasul ' + (st.step + 1) + ' (de plasat): ' + titleS + '</div>' +
          (sug.legs && sug.legs.length ? pyrLegsList(sug.legs) : '<div class="sh-row">' + pill(esc(sug.market_label || sug.market)) + "</div>") +
          '<div class="sh-row">' + (sug.adj_prob ? pill((sug.legs && sug.legs.length > 1 ? "prob combinată " : "prob ") + Math.round(sug.adj_prob) + "%", "g") : "") +
          (sug.event_date ? pill(pyrDayLabel(sug.event_date)) : "") + '</div>' +
          '<div class="sh-row" style="margin-top:8px">' +
          '<label class="sh-inp-wrap">cotă<input type="number" step="0.01" min="1.01" class="sh-inp" id="pyr-odds-' + cfg.key + '" value="' + sug.odds + '"></label>' +
          '<label class="sh-inp-wrap">miză (lei)<input type="number" step="0.1" min="0.1" class="sh-inp" id="pyr-stake-' + cfg.key + '" value="' + st.bankroll + '"></label>' +
          '</div>' +
          '<div class="sh-note" style="padding:6px 2px 0">Ajustează cota și miza dacă la agenția unde plasezi sunt diferite, apoi confirmă.</div>' +
          '<div class="sh-row" style="margin-top:6px"><button class="sh-mini-btn on" data-pyr-act="place" data-pyr-key="' + cfg.key + '">✅ Am plasat acest pariu</button></div></div>';
      } else {
        mid = '<div class="sh-empty">Niciun pont pentru pasul ' + (st.step + 1) + ' încă — nu forțăm o alegere proastă. ' +
          'Pipeline-ul verifică automat inclusiv oferta zilei următoare, la fiecare oră (sau apasă „🔄 Verifică actualizări acum" de sus).</div>';
      }
    }
    var hist = (st.history || []).slice().reverse().slice(0, 15).map(function (h) {
      var ic = h.result === "WIN" ? "✅" : (h.result === "VOID" ? "↩️" : "❌");
      var cls = h.result === "WIN" ? "win" : (h.result === "VOID" ? "" : "loss");
      var right = h.result === "WIN" ? "→ " + h.bankroll_after + " lei" : (h.result === "VOID" ? "void — miză înapoi" : "reset");
      var label = (h.legs && h.legs.length) ? "Combo " + h.legs.length + " ev." : esc(h.home_team) + " – " + esc(h.away_team) + " · " + esc(h.market_label);
      return '<div class="sh-ev-row ' + cls + '"><span>' + ic + " P" + h.step + " · " + label +
        " (" + h.final_score + ")</span><span>" + right + "</span></div>";
    }).join("");
    return '<div class="sh-track"><div class="sh-track-h">' + esc(cfg.label) + '</div>' + kpis + strip + mid +
      '<div class="sh-row" style="margin-top:8px">' +
      '<button class="sh-mini-btn" data-pyr-act="reset" data-pyr-key="' + cfg.key + '">↺ Resetează piramida</button>' +
      '<button class="sh-mini-btn" data-pyr-sync-act="refresh">🔄 Verifică actualizări</button>' +
      '</div>' +
      (hist ? '<details style="margin-top:8px"><summary style="cursor:pointer;font:700 10.5px system-ui;color:#64748b">Istoric pași</summary><div class="sh-ev-body" style="padding:6px 0 0">' + hist + '</div></details>' : '') +
      pyrStatsBlock(st) +
      '</div>';
  }

  function pyrHandle(act, key) {
    var st = pyrLoad(key);
    if (act === "place") {
      var cfg = PYR_TRACKS.filter(function (t) { return t.key === key; })[0];
      var sug = pyrSuggest(cfg, st.step + 1);
      if (sug) {
        var oddsEl = document.getElementById("pyr-odds-" + key);
        var stakeEl = document.getElementById("pyr-stake-" + key);
        var odds = oddsEl ? parseFloat(String(oddsEl.value).replace(",", ".")) : NaN;
        var stake = stakeEl ? parseFloat(String(stakeEl.value).replace(",", ".")) : NaN;
        if (!(odds > 1)) odds = sug.odds;
        if (!(stake > 0)) stake = st.bankroll;
        st.bankroll = stake; // banca ta = ce ai plasat efectiv, nu sugestia initiala
        st.placed = { event_id: sug.event_id, step: st.step + 1, market: sug.market, market_label: sug.market_label || sug.market,
          home_team: sug.home_team, away_team: sug.away_team, event_date: sug.event_date, odds: odds, adj_prob: sug.adj_prob, stake: stake,
          legs: (sug.legs && sug.legs.length) ? sug.legs : null };
        pyrSave(key, st);
      }
    } else if (act === "edit") {
      if (st.placed) {
        var oddsEl2 = document.getElementById("pyr-podds-" + key);
        var stakeEl2 = document.getElementById("pyr-pstake-" + key);
        var odds2 = oddsEl2 ? parseFloat(String(oddsEl2.value).replace(",", ".")) : NaN;
        var stake2 = stakeEl2 ? parseFloat(String(stakeEl2.value).replace(",", ".")) : NaN;
        if (odds2 > 1) st.placed.odds = odds2;
        if (stake2 > 0) { st.placed.stake = stake2; st.bankroll = stake2; }
        pyrSave(key, st);
      }
    } else if (act === "undo") { st.placed = null; pyrSave(key, st); }
    else if (act === "reset") { if (window.confirm("Sigur resetezi piramida " + key + "? Se pierde progresul salvat.")) pyrSave(key, pyrFresh()); }
    draw();
  }

  // Sincronizare intre telefoane/browsere prin cod copiat manual — fara cont, fara server.
  // localStorage e legat de un singur browser, deci progresul nu trece singur pe alt telefon.
  function b64EncodeUtf8(str) { return btoa(unescape(encodeURIComponent(str))); }
  function b64DecodeUtf8(str) { return decodeURIComponent(escape(atob(str))); }
  var PYR_SYNC_PREFIX = "BP1:";
  function pyrExportCode() {
    var payload = {};
    PYR_TRACKS.forEach(function (t) { payload[t.key] = pyrLoad(t.key); });
    return PYR_SYNC_PREFIX + b64EncodeUtf8(JSON.stringify(payload));
  }
  function pyrImportCode(code) {
    code = String(code || "").trim();
    if (code.indexOf(PYR_SYNC_PREFIX) !== 0) throw new Error("Cod necunoscut — verifică să-l fi copiat complet.");
    var payload = JSON.parse(b64DecodeUtf8(code.slice(PYR_SYNC_PREFIX.length)));
    PYR_TRACKS.forEach(function (t) { if (payload[t.key]) pyrSave(t.key, payload[t.key]); });
  }
  function renderPyrSync() {
    return '<details class="sh-outer" style="margin-bottom:10px">' +
      '<summary>🔄 Sincronizare piramide (alt telefon/browser)</summary>' +
      '<div class="sh-outer-body">' +
      '<div class="sh-note">Codul de mai jos conține progresul ambelor piramide de pe acest telefon. Copiază-l și lipește-l pe celălalt dispozitiv, la „cod import".</div>' +
      '<textarea id="pyr-sync-export" class="sh-inp" style="width:100%;height:56px;font-size:9.5px;font-weight:600" readonly>' + esc(pyrExportCode()) + '</textarea>' +
      '<div class="sh-row" style="margin-top:6px"><button class="sh-mini-btn on" data-pyr-sync-act="copy">📋 Copiază codul</button></div>' +
      '<div class="sh-note" style="margin-top:12px">Lipește aici un cod generat pe alt telefon — îți <b>suprascrie</b> piramidele de pe acest dispozitiv.</div>' +
      '<textarea id="pyr-sync-import" class="sh-inp" style="width:100%;height:56px;font-size:9.5px;font-weight:600" placeholder="lipește codul aici"></textarea>' +
      '<div class="sh-row" style="margin-top:6px"><button class="sh-mini-btn" data-pyr-sync-act="import">📥 Importă cod</button></div>' +
      '</div></details>';
  }
  function pyrSyncHandle(act) {
    if (act === "copy") {
      var ta = document.getElementById("pyr-sync-export");
      if (!ta) return;
      ta.select(); ta.setSelectionRange(0, 99999);
      var ok = false;
      try { if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(ta.value); ok = true; } } catch (e) {}
      if (!ok) { try { ok = document.execCommand("copy"); } catch (e2) {} }
      window.alert(ok ? "Cod copiat — lipește-l pe celălalt telefon." : "Nu am putut copia automat — codul e selectat, copiază-l manual (ține apăsat → Copiază).");
    } else if (act === "import") {
      var el = document.getElementById("pyr-sync-import");
      var code = el ? el.value : "";
      if (!code.trim()) { window.alert("Lipește mai întâi codul de pe celălalt telefon."); return; }
      if (!window.confirm("Sigur imporți? Îți suprascrie piramidele salvate pe acest telefon cu ce e în cod.")) return;
      try { pyrImportCode(code); window.alert("Import reușit."); draw(); }
      catch (e) { window.alert("Cod invalid: " + e.message); }
    } else if (act === "refresh") {
      boot();
    }
  }

  function renderPyrTargetDayNote() {
    var td = state.pools && state.pools.target_day;
    if (!td) return "";
    var dayFmt = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Bucharest" });
    var today = dayFmt.format(new Date()), tomorrow = dayFmt.format(new Date(Date.now() + 86400000));
    var label = td === today ? "azi" : (td === tomorrow ? "mâine" : td);
    return '<div class="sh-note">🗓️ Pipeline-ul analizează în acest moment oferta din: <b>' + esc(label) + "</b></div>";
  }

  function renderPyramid() {
    var hist = (state.pyramid && state.pyramid.historical_track_record) || {};
    var policy = (state.pools && state.pools.execution_policy) || (state.pyramid && state.pyramid.execution_policy) || {};
    var daily = (state.pools && state.pools.daily_analysis) || (state.pyramid && state.pyramid.daily_analysis) || {};
    var policyClass = policy.execution_enabled ? "green" : "yellow";
    var dailyHtml = '<div class="sh-banner ' + policyClass + '"><b>Analiză zilnică: ' + esc(daily.status || "în pregătire") + '</b> · ' + esc(daily.reason || policy.reason || "Așteptăm evaluarea următoarei rulări.") +
      (daily.candidate ? '<div style="margin-top:7px">Candidat analizat: <b>' + esc(daily.candidate.home_team) + ' – ' + esc(daily.candidate.away_team) + '</b> · ' + esc(daily.candidate.market_label || daily.candidate.market) + ' @' + esc(daily.candidate.odds) + '</div>' : '') + '</div>';
    return dailyHtml + '<div class="sh-note">🔒 Piramida <b>ta</b> — apeși „Am plasat" când chiar pui pariul, iar când apare rezultatul se validează automat și trece la pasul următor. Progresul e salvat doar pe acest telefon.</div>' +
      '<div class="sh-note">📐 De la pasul ' + PYR_WITHDRAW_FROM + ' se retrage automat ' + Math.round(PYR_WITHDRAW_PCT * 100) + '% din profit la fiecare câștig.</div>' +
      '<div class="sh-note">📊 Win rate istoric al picioarelor Superbet Edge decontate = ' +
      (hist.leg_win_rate_pct == null ? "–" : hist.leg_win_rate_pct + "%") + " (n=" + (hist.n_legs_settled || 0) +
      "). Compunerea pe multe trepte e statistic improbabilă — miză mică, disciplină.</div>" +
      renderPyrTargetDayNote() +
      '<div class="sh-row" style="margin-bottom:10px"><button class="sh-mini-btn" data-pyr-sync-act="refresh">🔄 Verifică actualizări acum</button></div>' +
      renderPyrSync() +
      PYR_TRACKS.map(myPyramidCard).join("");
  }

  function _renderPyramidPaperOld() {
    var d = state.pyramid;
    if (!d) return '<div class="sh-empty">Se populează pe măsură ce rulează pipeline-ul.</div>';
    var hist = d.historical_track_record || {};
    var wr = d.withdrawal_rule || {};
    var trackKeys = Object.keys(d.tracks || {});
    return '<div class="sh-note">⚠️ Tracker <b>în umbră</b> (paper) — nu știe dacă ai plasat efectiv pariul pe Superbet, ' +
      'doar arată ce s-ar fi întâmplat dacă ai fi urmat exact sugestia zilei. Nu e un istoric al banilor tăi reali.</div>' +
      '<div class="sh-note">📐 Regulă de retragere: de la pasul ' + wr.from_step + ', se retrage automat ' +
      Math.round((wr.pct_of_profit || 0) * 100) + '% din profitul acumulat la fiecare câștig.</div>' +
      '<div class="sh-note">📊 Șansă reală (nu presupusă): win rate istoric al picioarelor Superbet Edge decontate = ' +
      (hist.leg_win_rate_pct == null ? "–" : hist.leg_win_rate_pct + "%") + " (n=" + (hist.n_legs_settled || 0) +
      "). La acest ritm, compunerea pe multe trepte e statistic foarte improbabilă — vezi tab-ul Superbet → Monitor pentru cifre complete.</div>" +
      trackKeys.map(function (k) { return pyramidTrackCard(k, d.tracks[k]); }).join("");
  }

  function renderBody() {
    switch (state.tab) {
      case "value": return renderValue();
      case "steam": return renderSteam();
      case "arb": return renderArb();
      case "poly": return renderPoly();
      case "ref": return renderRef();
      case "clv": return renderCLV();
      case "superbet": return renderSuperbet();
      case "pyramid": return renderPyramid();
      case "updates": return renderUpdates();
      default: return "";
    }
  }

  var TABS = [
    { id: "superbet", label: "🎟️ Superbet" },
    { id: "pyramid", label: "🔺 Piramidă" },
    { id: "updates", label: "🔄 Actualizări" },
    { id: "value", label: "💎 Value" },
    { id: "steam", label: "🔥 Steam" },
    { id: "arb", label: "⚖️ Arb" },
    { id: "poly", label: "🌐 Poly" },
    { id: "ref", label: "🧑‍⚖️ Ref" },
    { id: "clv", label: "📈 CLV" },
  ];

  function draw() {
    var drawer = document.getElementById("sharp-drawer");
    if (!drawer) return;
    var tabsHtml = TABS.map(function (t) {
      return '<button class="sh-tab' + (state.tab === t.id ? " active" : "") + '" data-tab="' + t.id + '">' + t.label + "</button>";
    }).join("");
    drawer.querySelector(".sh-tabs").innerHTML = tabsHtml;
    drawer.querySelector(".sh-body").innerHTML = renderBody();
    drawer.querySelectorAll(".sh-tab").forEach(function (b) {
      b.addEventListener("click", function () {
        var sub = b.getAttribute("data-sub");
        if (sub) { state.superbetSub = sub; draw(); return; }
        state.tab = b.getAttribute("data-tab"); draw();
      });
    });
    drawer.querySelectorAll("[data-pyr-act]").forEach(function (b) {
      b.addEventListener("click", function () { pyrHandle(b.getAttribute("data-pyr-act"), b.getAttribute("data-pyr-key")); });
    });
    drawer.querySelectorAll("[data-pyr-sync-act]").forEach(function (b) {
      b.addEventListener("click", function () { pyrSyncHandle(b.getAttribute("data-pyr-sync-act")); });
    });
  }

  function openDrawer() {
    var drawer = document.getElementById("sharp-drawer");
    if (drawer) { drawer.classList.add("on"); state.open = true; draw(); }
  }

  function build() {
    inject("sharp-css", CSS);
    if (document.getElementById("sharp-drawer")) return;

    // Butonul flotant a fost eliminat — panoul se deschide din tabul „Sharp"
    // din meniul de sus (eveniment 'betpredict:open-sharp').
    var drawer = document.createElement("div");
    drawer.id = "sharp-drawer";
    drawer.innerHTML =
      '<div id="sharp-sheet">' +
      '<div class="sh-head"><div class="sh-title">💰 SHARP — Edge Real v7</div><button class="sh-x" id="sharp-close">✕</button></div>' +
      '<div class="sh-tabs"></div><div class="sh-body"></div></div>';
    document.body.appendChild(drawer);

    drawer.addEventListener("click", function (e) { if (e.target === drawer) drawer.classList.remove("on"); });
    document.getElementById("sharp-close").addEventListener("click", function () { drawer.classList.remove("on"); });
  }

  window.addEventListener("betpredict:open-sharp", function () {
    if (!document.getElementById("sharp-drawer")) build();
    openDrawer();
  });

  function boot() {
    Promise.all([fetchJSON(SIGNALS_URL), fetchJSON(REF_URL), fetchJSON(CLV_URL), fetchJSON(SUPERBET_URL), fetchJSON(SUPERBET_HIST_URL), fetchJSON(PYRAMID_URL), fetchJSON(POOLS_URL), fetchJSON(RESULTS_URL), fetchJSON(UPDATE_URL)]).then(function (r) {
      state.signals = r[0]; state.ref = r[1]; state.clv = r[2]; state.superbet = r[3]; state.superbetHist = r[4]; state.pyramid = r[5];
      state.pools = r[6]; state.results = r[7]; state.updates = r[8];
      build();
      if (state.open) draw();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  // Rezultatele si oferta zilei se schimba pe server (pipeline orar) — reverifica
  // periodic, ca decontarea piramidei sa se intample singura, fara sa fie nevoie
  // sa inchizi si sa redeschizi panoul.
  var PYR_AUTOREFRESH_MS = 5 * 60 * 1000;
  setInterval(boot, PYR_AUTOREFRESH_MS);

  window.SharpUI = { data: function () { return state; }, refresh: boot };
})();
