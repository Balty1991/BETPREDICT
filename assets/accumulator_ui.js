/**
 * accumulator_ui.js — Accumulators + Pyramid Staircase overlay
 * ============================================================
 * Surfaces data/accumulators.json and data/pyramid_plans.json with
 * green confidence badges. Non-invasive: floating panel + optional
 * injection into Sharp drawer when open.
 *
 * Honesty: longshot 50×/100× tickets are labeled PAPER / lottery.
 */
(function () {
  "use strict";
  var ACC_URL = "data/accumulators.json?v=v8";
  var PLAN_URL = "data/pyramid_plans.json?v=v8";
  var state = { acc: null, plans: null, open: false, tab: "tickets" };

  var CSS = ""
    + "#acc-fab{position:fixed;left:16px;bottom:88px;z-index:99997;width:52px;height:52px;border-radius:50%;"
    + "border:none;cursor:pointer;background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff;font-size:20px;"
    + "box-shadow:0 8px 22px rgba(34,197,94,.4);display:flex;align-items:center;justify-content:center}"
    + "#acc-fab .acc-badge{position:absolute;top:-4px;right:-4px;background:#0ea5e9;color:#fff;font:800 10px/1 ui-monospace,monospace;"
    + "min-width:18px;height:18px;border-radius:9px;display:flex;align-items:center;justify-content:center;padding:0 4px}"
    + "#acc-drawer{position:fixed;inset:0;z-index:99999;background:rgba(2,6,23,.72);backdrop-filter:blur(4px);"
    + "display:none;align-items:flex-end;justify-content:center}"
    + "#acc-drawer.on{display:flex}"
    + "#acc-sheet{width:100%;max-width:680px;height:88vh;background:linear-gradient(180deg,#0b1220,#070d18);"
    + "border:1px solid rgba(34,197,94,.3);border-radius:20px 20px 0 0;display:flex;flex-direction:column;overflow:hidden}"
    + ".acc-head{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid rgba(148,163,184,.12)}"
    + ".acc-title{font:900 13px/1 system-ui;letter-spacing:.04em;color:#bbf7d0;text-transform:uppercase}"
    + ".acc-x{background:rgba(148,163,184,.14);border:none;color:#cbd5e1;width:34px;height:34px;border-radius:9px;cursor:pointer}"
    + ".acc-tabs{display:flex;gap:6px;padding:10px;border-bottom:1px solid rgba(148,163,184,.1);overflow-x:auto}"
    + ".acc-tab{border:1px solid rgba(148,163,184,.16);background:rgba(15,23,42,.7);color:#94a3b8;border-radius:999px;"
    + "padding:8px 12px;font:800 11px/1 system-ui;cursor:pointer;white-space:nowrap}"
    + ".acc-tab.active{color:#052e16;background:#4ade80;border-color:#4ade80}"
    + ".acc-body{flex:1;min-height:0;overflow-y:auto;padding:12px;-webkit-overflow-scrolling:touch}"
    + ".acc-card{border:1px solid rgba(148,163,184,.14);border-radius:14px;background:rgba(15,23,42,.6);padding:11px 12px;margin-bottom:9px}"
    + ".acc-card.green{border-left:3px solid #22c55e}.acc-card.paper{border-left:3px solid #f59e0b}.acc-card.safe{border-left:3px solid #38bdf8}"
    + ".acc-match{font:800 13px/1.3 system-ui;color:#e5eef9}"
    + ".acc-note{font:600 11px/1.45 system-ui;color:#94a3b8;padding:4px 2px 10px}"
    + ".acc-pill{font:800 10.5px/1 ui-monospace,monospace;padding:5px 8px;border-radius:8px;background:rgba(15,23,42,.85);"
    + "border:1px solid rgba(148,163,184,.16);color:#cbd5e1;display:inline-flex;margin:3px 4px 0 0}"
    + ".acc-pill.g{color:#4ade80;border-color:rgba(74,222,128,.45)}.acc-pill.y{color:#fbbf24;border-color:rgba(251,191,36,.4)}"
    + ".acc-pill.b{color:#38bdf8;border-color:rgba(56,189,248,.4)}.acc-pill.r{color:#f87171;border-color:rgba(248,113,113,.35)}"
    + ".acc-leg{display:flex;justify-content:space-between;gap:8px;font:700 11px/1.35 ui-monospace,monospace;color:#bae6fd;"
    + "background:rgba(34,197,94,.07);padding:6px 8px;border-radius:7px;margin-top:5px}"
    + ".acc-empty{text-align:center;color:#64748b;padding:28px 12px;font:600 13px/1.5 system-ui}"
    + ".acc-green-badge{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:999px;font:800 10px/1 system-ui;"
    + "background:rgba(34,197,94,.18);color:#4ade80;border:1px solid rgba(34,197,94,.45);margin-left:6px}"
    + ".acc-step{border:1px dashed rgba(148,163,184,.25);border-radius:12px;padding:10px;margin:8px 0;background:rgba(15,23,42,.45)}";

  function injectCSS() {
    if (document.getElementById("acc-ui-css")) return;
    var s = document.createElement("style");
    s.id = "acc-ui-css";
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>\"']/g, function (c) {
      return ({ "&": "&", "<": "<", ">": ">", "\"": """, "'": "&#39;" })[c];
    });
  }

  function pill(t, c) { return "<span class=\"acc-pill " + (c || "") + "\">" + esc(t) + "</span>"; }

  function fetchJSON(url) {
    return fetch(url, { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }

  function ticketCount() {
    var by = (state.acc && state.acc.tickets_by_period) || {};
    var n = 0;
    Object.keys(by).forEach(function (k) { n += (by[k] || []).length; });
    return n + ((state.acc && state.acc.green_singles) || []).length;
  }

  function renderTicket(t) {
    var cls = t.green_ticket ? "green" : (t.paper_only ? "paper" : "safe");
    var legs = (t.legs || []).map(function (l) {
      return "<div class=\"acc-leg\"><span>" + esc(l.home_team) + " – " + esc(l.away_team)
        + " · " + esc(l.market_label || l.market)
        + (l.green_badge ? " <span class=\"acc-green-badge\">🟢 GREEN</span>" : "")
        + "</span><span>@" + esc(l.odds) + "</span></div>";
    }).join("");
    return "<div class=\"acc-card " + cls + "\">"
      + "<div class=\"acc-match\">" + esc(t.label) + (t.green_ticket ? " <span class=\"acc-green-badge\">🟢 GREEN</span>" : "") + "</div>"
      + "<div>" + pill(t.n_legs + " legs", "b") + pill("@" + t.combined_odds, "g")
      + pill("prob " + t.combined_probability_pct + "%")
      + (t.executable ? pill("executabil Superbet", "g") : pill("paper / verifică cotă", "y"))
      + (t.paper_only ? pill("LOTERIE", "y") : "")
      + "</div>"
      + legs
      + "<div class=\"acc-note\">" + esc(t.disclaimer || "") + "</div>"
      + "</div>";
  }

  function renderTickets() {
    var d = state.acc;
    if (!d) return "<div class=\"acc-empty\">accumulators.json încă nu e generat — rulează pipeline-ul zilnic.</div>";
    var html = "<div class=\"acc-note\">" + esc(d.note || "") + "</div>";
    var singles = d.green_singles || [];
    if (singles.length) {
      html += "<div class=\"acc-card green\"><div class=\"acc-match\">Singles verzi (max confidence)</div>";
      singles.slice(0, 8).forEach(function (l) {
        html += "<div class=\"acc-leg\"><span>" + esc(l.home_team) + " – " + esc(l.away_team)
          + " · " + esc(l.market_label || l.market)
          + " <span class=\"acc-green-badge\">🟢 " + esc(l.quality_grade_v6 || "A") + "</span></span>"
          + "<span>@" + esc(l.odds) + " · " + esc(l.probability) + "%</span></div>";
      });
      html += "</div>";
    }
    var by = d.tickets_by_period || {};
    var periods = ["7", "10", "30"];
    var any = false;
    periods.forEach(function (p) {
      var tks = by[p] || [];
      if (!tks.length) return;
      any = true;
      html += "<div class=\"acc-note\">Fereastră " + p + " zile · " + tks.length + " bilete</div>";
      tks.forEach(function (t) { html += renderTicket(t); });
    });
    if (!any && !singles.length) {
      html += "<div class=\"acc-empty\">Niciun bilet după filtrele stricte (A+/A, consens, EV). Asta e OK — mai bine gol decât forțat.</div>";
    }
    return html;
  }

  function renderPlans() {
    var d = state.plans;
    if (!d) return "<div class=\"acc-empty\">pyramid_plans.json încă lipsește.</div>";
    var html = "<div class=\"acc-note\">" + esc(d.risk_warning || "") + "</div>";
    (d.how_to_use || []).forEach(function (line) {
      html += "<div class=\"acc-note\">" + esc(line) + "</div>";
    });
    (d.plans || []).forEach(function (plan) {
      html += "<div class=\"acc-card safe\"><div class=\"acc-match\">" + esc(plan.name) + "</div>"
        + pill("survival " + (plan.series_survival_probability != null ? (plan.series_survival_probability * 100).toFixed(2) + "%" : "–"), "y")
        + (plan.series_one_in ? pill("≈1 din " + plan.series_one_in, "y") : "")
        + pill(plan.execution_status || "PAPER_ONLY", "r");
      (plan.steps || []).forEach(function (st) {
        var c = st.candidate || {};
        html += "<div class=\"acc-step\"><strong>Pas " + esc(st.step) + "</strong> · miză "
          + esc(st.stake_units) + "u (" + esc(st.stake_lei) + " lei)"
          + (st.green_badge ? " <span class=\"acc-green-badge\">🟢 GREEN</span>" : "")
          + "<div class=\"acc-leg\"><span>" + esc(c.home_team || "—") + " – " + esc(c.away_team || "")
          + " · " + esc(c.market_label || c.market || st.status || "")
          + "</span><span>@" + esc(c.odds || "–") + "</span></div>"
          + "<div class=\"acc-note\">P(ajungere aici)="
          + (st.survival_probability_to_here != null ? (st.survival_probability_to_here * 100).toFixed(2) + "%" : "–")
          + " · " + esc(st.if_loss_action || "") + "</div></div>";
      });
      html += "<div class=\"acc-note\">" + esc(plan.disclaimer || "") + "</div></div>";
    });
    return html;
  }

  function renderBody() {
    return state.tab === "plans" ? renderPlans() : renderTickets();
  }

  function draw() {
    var drawer = document.getElementById("acc-drawer");
    if (!drawer) return;
    drawer.querySelector(".acc-tabs").innerHTML =
      "<button class=\"acc-tab" + (state.tab === "tickets" ? " active" : "") + "\" data-tab=\"tickets\">🎟️ Accumulators</button>"
      + "<button class=\"acc-tab" + (state.tab === "plans" ? " active" : "") + "\" data-tab=\"plans\">🔺 Scară 2→5→10</button>";
    drawer.querySelector(".acc-body").innerHTML = renderBody();
    drawer.querySelectorAll(".acc-tab").forEach(function (b) {
      b.addEventListener("click", function () { state.tab = b.getAttribute("data-tab"); draw(); });
    });
  }

  function build() {
    injectCSS();
    if (document.getElementById("acc-drawer")) return;
    var fab = document.createElement("button");
    fab.id = "acc-fab";
    fab.title = "Accumulators + Pyramid Staircase";
    fab.innerHTML = "🎟️<span class=\"acc-badge\" id=\"acc-fab-n\">0</span>";
    document.body.appendChild(fab);

    var drawer = document.createElement("div");
    drawer.id = "acc-drawer";
    drawer.innerHTML =
      "<div id=\"acc-sheet\">"
      + "<div class=\"acc-head\"><div class=\"acc-title\">Accumulators + Scară 2→5→10</div>"
      + "<button class=\"acc-x\" id=\"acc-close\">✕</button></div>"
      + "<div class=\"acc-tabs\"></div><div class=\"acc-body\"></div></div>";
    document.body.appendChild(drawer);

    fab.addEventListener("click", function () {
      drawer.classList.add("on"); state.open = true; draw();
    });
    drawer.addEventListener("click", function (e) { if (e.target === drawer) drawer.classList.remove("on"); });
    document.getElementById("acc-close").addEventListener("click", function () { drawer.classList.remove("on"); });
  }

  function boot() {
    Promise.all([fetchJSON(ACC_URL), fetchJSON(PLAN_URL)]).then(function (r) {
      state.acc = r[0]; state.plans = r[1];
      build();
      var n = ticketCount();
      var badge = document.getElementById("acc-fab-n");
      if (badge) badge.textContent = String(n);
      if (state.open) draw();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  window.AccumulatorUI = { refresh: boot, data: function () { return state; } };
})();
