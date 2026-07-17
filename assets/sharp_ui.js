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

  var state = { signals: null, ref: null, clv: null, tab: "value", open: false };

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
    ".sh-kpi-v{font:900 18px/1 ui-monospace,monospace;color:#e5eef9}.sh-kpi-k{font:700 9px/1 system-ui;color:#64748b;text-transform:uppercase;margin-top:5px}";

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

  function renderValue() {
    var arr = (state.signals && state.signals.value_signals) || [];
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

  function renderBody() {
    switch (state.tab) {
      case "value": return renderValue();
      case "steam": return renderSteam();
      case "arb": return renderArb();
      case "poly": return renderPoly();
      case "ref": return renderRef();
      case "clv": return renderCLV();
      default: return "";
    }
  }

  var TABS = [
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
      b.addEventListener("click", function () { state.tab = b.getAttribute("data-tab"); draw(); });
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
    Promise.all([fetchJSON(SIGNALS_URL), fetchJSON(REF_URL), fetchJSON(CLV_URL)]).then(function (r) {
      state.signals = r[0]; state.ref = r[1]; state.clv = r[2];
      build();
      if (state.open) draw();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  window.SharpUI = { data: function () { return state; }, refresh: boot };
})();
