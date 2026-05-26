/**
 * v6_ui.js - BetPredict Pro v6.0 UI Enhancer
 * ============================================
 * Modul self-contained care augmenteaza UI-ul cu date v6:
 *   - Badge UPGRADED/DOWNGRADED pe fiecare semnal
 *   - Consensus tier (TOTAL/PARTIAL/DIVERGENT)
 *   - Probabilitate calibrata + ML prob alaturi de BSD
 *   - SmartBet Score v6 + Grade A+
 *   - Panou nou pe Dashboard cu metrici calibrare
 *
 * Nu modifica codul existent — hookuieste in DOM dupa ce render-urile
 * originale au scris cartile, observa schimbarile si injecteaza UI v6.
 *
 * Urmeaza acelasi pattern ca smartbet_verdict_ui.js / context_engine_ui.js.
 */
(function() {
  'use strict';

  const V6_VERSION = '6.0';
  const DEBUG = false;
  const log = (...a) => DEBUG && console.log('[v6_ui]', ...a);

  // ============================================================
  // CSS INJECTION
  // ============================================================
  const CSS = `
    /* === FIX v6.2: Match detail modal scroll === */
    .md-sheet > #md-content{display:contents !important}
    .md-sheet{display:flex !important;flex-direction:column !important;overflow:hidden !important}
    .md-sheet .md-head{flex-shrink:0 !important}
    .md-sheet .md-tabs{flex-shrink:0 !important}
    .md-sheet .md-body{
      flex:1 1 auto !important;
      min-height:0 !important;
      overflow-y:auto !important;
      overflow-x:hidden !important;
      -webkit-overflow-scrolling:touch !important;
      overscroll-behavior:contain !important;
      touch-action:pan-y !important;
    }
    .md-sheet .md-panel{touch-action:auto !important}
    .md-sheet .md-body::after{
      content:"";display:block;height:max(24px, env(safe-area-inset-bottom, 24px))
    }

    /* === FIX v6.3: Multi-market signals panel === */
    .v6-multi-panel{background:linear-gradient(135deg,rgba(251,191,36,.10),rgba(139,92,246,.06));border:1px solid rgba(251,191,36,.35);border-radius:12px;padding:12px;margin:0 0 12px 0}
    .v6-multi-title{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;color:#fbbf24;letter-spacing:.5px;text-transform:uppercase;margin-bottom:10px}
    .v6-multi-title::before{content:"🎯";font-size:14px}
    .v6-multi-row{display:grid;grid-template-columns:1fr auto;gap:8px;padding:8px 10px;border-radius:8px;background:rgba(15,23,42,.5);margin-bottom:6px;border-left:3px solid rgba(139,92,246,.5)}
    .v6-multi-row-best{border-left-color:#10b981;background:rgba(16,185,129,.08)}
    .v6-multi-market{font-weight:700;color:#e5e7eb;font-size:12px}
    .v6-multi-strategy{font-size:9.5px;color:#94a3b8;text-transform:uppercase;letter-spacing:.3px;margin-top:2px}
    .v6-multi-meta{display:flex;flex-direction:column;align-items:flex-end;gap:2px;font-size:11px}
    .v6-multi-prob{color:#10b981;font-weight:700}
    .v6-multi-edge{color:#fbbf24;font-weight:600;font-size:10px}

    /* === FIX v6.4: SmartBet v6 score replacement === */
    .v6-sb-replaced{animation:v6-sb-fade .4s ease}
    @keyframes v6-sb-fade{from{opacity:0.3}to{opacity:1}}

    /* === FIX v6.6: Top Recommendation Ranking Badges === */
    .v6-rank-badge{
      position:absolute;top:10px;left:10px;width:28px;height:28px;
      border-radius:50%;display:flex;align-items:center;justify-content:center;
      font-weight:800;font-size:14px;z-index:6;pointer-events:none;
      font-family:var(--ff-body);line-height:1;
    }
    .v6-rank-1{
      background:linear-gradient(135deg,#10b981,#059669);color:white;
      border:2px solid rgba(16,185,129,.95);
      box-shadow:0 0 14px rgba(16,185,129,.65),0 2px 6px rgba(0,0,0,.4);
      animation:v6-rank-pulse 2.5s ease-in-out infinite;
    }
    .v6-rank-2{
      background:linear-gradient(135deg,#fbbf24,#d97706);color:#1f2937;
      border:2px solid rgba(251,191,36,.95);
      box-shadow:0 0 10px rgba(251,191,36,.55),0 2px 6px rgba(0,0,0,.4);
    }
    .v6-rank-3{
      background:linear-gradient(135deg,#94a3b8,#475569);color:white;
      border:2px solid rgba(148,163,184,.75);
      box-shadow:0 0 8px rgba(148,163,184,.35),0 2px 6px rgba(0,0,0,.4);
    }
    @keyframes v6-rank-pulse{
      0%,100%{transform:scale(1);box-shadow:0 0 14px rgba(16,185,129,.65),0 2px 6px rgba(0,0,0,.4)}
      50%{transform:scale(1.12);box-shadow:0 0 22px rgba(16,185,129,.9),0 2px 8px rgba(0,0,0,.5)}
    }

    .v6-badge{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700;letter-spacing:.3px;text-transform:uppercase;margin-left:6px;vertical-align:middle}
    .v6-badge-upgraded{background:linear-gradient(135deg,#10b981,#059669);color:white;box-shadow:0 0 8px rgba(16,185,129,.4)}
    .v6-badge-downgraded{background:linear-gradient(135deg,#ef4444,#b91c1c);color:white;box-shadow:0 0 8px rgba(239,68,68,.3)}
    .v6-badge-adjusted{background:linear-gradient(135deg,#f59e0b,#d97706);color:white}
    .v6-badge-unchanged{background:rgba(100,116,139,.3);color:#cbd5e1}
    .v6-badge-newml{background:linear-gradient(135deg,#8b5cf6,#6d28d9);color:white;box-shadow:0 0 8px rgba(139,92,246,.4)}

    .v6-grade{display:inline-block;padding:2px 7px;border-radius:8px;font-size:10px;font-weight:800;margin-left:4px}
    .v6-grade-Aplus{background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#1f2937;box-shadow:0 0 10px rgba(251,191,36,.5)}
    .v6-grade-A{background:#10b981;color:white}
    .v6-grade-B{background:#3b82f6;color:white}
    .v6-grade-C{background:#6b7280;color:white}
    .v6-grade-D{background:#9ca3af;color:white}
    .v6-grade-E{background:#dc2626;color:white}

    .v6-consensus{display:inline-flex;align-items:center;gap:4px;padding:2px 6px;border-radius:6px;font-size:9px;font-weight:600;margin-left:4px;vertical-align:middle}
    .v6-consensus-TOTAL{background:rgba(16,185,129,.18);color:#10b981;border:1px solid rgba(16,185,129,.4)}
    .v6-consensus-PARTIAL{background:rgba(59,130,246,.18);color:#60a5fa;border:1px solid rgba(59,130,246,.4)}
    .v6-consensus-DIVERGENT{background:rgba(245,158,11,.18);color:#fbbf24;border:1px solid rgba(245,158,11,.4)}
    .v6-consensus-CONTRADICTORIU{background:rgba(239,68,68,.2);color:#f87171;border:1px solid rgba(239,68,68,.4)}

    .v6-prob-row{display:flex;gap:8px;align-items:center;font-size:11px;color:#9ca3af;margin-top:4px;flex-wrap:wrap}
    .v6-prob-row .v6-prob-item{display:inline-flex;align-items:center;gap:3px}
    .v6-prob-row .v6-prob-label{color:#6b7280;font-weight:500}
    .v6-prob-row .v6-prob-value{color:#e5e7eb;font-weight:700;font-variant-numeric:tabular-nums}
    .v6-prob-row .v6-prob-cal{color:#fbbf24}
    .v6-prob-row .v6-prob-ml{color:#8b5cf6}
    .v6-prob-row .v6-prob-delta{font-size:9px;font-weight:600;padding:1px 4px;border-radius:3px}
    .v6-prob-row .v6-prob-delta-pos{background:rgba(16,185,129,.2);color:#10b981}
    .v6-prob-row .v6-prob-delta-neg{background:rgba(239,68,68,.2);color:#f87171}

    .v6-dash-panel{background:linear-gradient(135deg,rgba(139,92,246,.1),rgba(59,130,246,.08));border:1px solid rgba(139,92,246,.3);border-radius:14px;padding:16px;margin:12px 0;box-shadow:0 4px 20px rgba(139,92,246,.1)}
    .v6-dash-title{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:700;color:#a78bfa;letter-spacing:.5px;text-transform:uppercase;margin-bottom:12px}
    .v6-dash-title::before{content:"🧠";font-size:16px}
    .v6-dash-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px}
    .v6-dash-cell{background:rgba(15,23,42,.55);border:1px solid rgba(139,92,246,.2);border-radius:10px;padding:10px;text-align:center}
    .v6-dash-cell-value{font-size:20px;font-weight:800;color:#e5e7eb;font-variant-numeric:tabular-nums}
    .v6-dash-cell-label{font-size:9.5px;color:#94a3b8;text-transform:uppercase;letter-spacing:.4px;margin-top:3px}
    .v6-dash-cell-good .v6-dash-cell-value{color:#10b981}
    .v6-dash-cell-warn .v6-dash-cell-value{color:#fbbf24}
    .v6-dash-cell-bad .v6-dash-cell-value{color:#ef4444}

    .v6-calibration-list{margin-top:10px;display:flex;flex-direction:column;gap:6px}
    .v6-cal-row{display:flex;justify-content:space-between;align-items:center;background:rgba(15,23,42,.4);padding:7px 10px;border-radius:8px;font-size:11px}
    .v6-cal-market{font-weight:700;color:#e5e7eb;font-family:var(--ff-mono)}
    .v6-cal-bias{font-variant-numeric:tabular-nums;font-weight:600}
    .v6-cal-bias-good{color:#10b981}
    .v6-cal-bias-warn{color:#fbbf24}
    .v6-cal-bias-bad{color:#ef4444}
    .v6-cal-meta{color:#94a3b8;font-size:10px}

    .v6-ml-block{background:rgba(139,92,246,.06);border:1px solid rgba(139,92,246,.2);border-radius:10px;padding:10px;margin:8px 0}
    .v6-ml-title{font-size:11px;font-weight:700;color:#a78bfa;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;display:flex;align-items:center;gap:6px}
    .v6-ml-title::before{content:"🤖";font-size:12px}
    .v6-ml-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px}
    .v6-ml-stat{text-align:center;background:rgba(15,23,42,.5);padding:6px;border-radius:6px}
    .v6-ml-stat-label{font-size:9px;color:#94a3b8;text-transform:uppercase;letter-spacing:.3px}
    .v6-ml-stat-value{font-size:14px;font-weight:700;color:#e5e7eb;font-variant-numeric:tabular-nums;margin-top:2px}

    .v6-tier-pill{display:inline-flex;align-items:center;gap:3px;padding:2px 7px;border-radius:8px;font-size:9px;font-weight:700}
    .v6-tier-pill::before{content:"●";font-size:7px}

    .v6-toast{position:fixed;top:60px;right:12px;background:rgba(15,23,42,.95);border:1px solid rgba(139,92,246,.4);color:#e5e7eb;padding:10px 14px;border-radius:10px;font-size:12px;z-index:10000;box-shadow:0 8px 24px rgba(0,0,0,.4);opacity:0;transition:opacity .3s;pointer-events:none}
    .v6-toast.show{opacity:1}

    .v6-health-bar{display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:10px;margin-bottom:10px;font-size:11.5px;font-weight:600}
    .v6-health-bar-GREEN{background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.4);color:#10b981}
    .v6-health-bar-YELLOW{background:rgba(245,158,11,.10);border:1px solid rgba(245,158,11,.4);color:#fbbf24}
    .v6-health-bar-RED{background:rgba(239,68,68,.10);border:1px solid rgba(239,68,68,.4);color:#f87171}
    .v6-health-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;box-shadow:0 0 8px currentColor;animation:v6-pulse 2.5s ease-in-out infinite}
    @keyframes v6-pulse{0%,100%{opacity:1}50%{opacity:.5}}
    .v6-health-message{flex:1;letter-spacing:.2px}
    .v6-health-counts{display:flex;gap:6px;font-size:10px;opacity:.85}
    .v6-health-counts span{padding:1px 6px;border-radius:6px;background:rgba(15,23,42,.5)}

    .v6-bt-panel{background:linear-gradient(135deg,rgba(16,185,129,.08),rgba(59,130,246,.06));border:1px solid rgba(16,185,129,.3);border-radius:14px;padding:14px;margin:12px 0}
    .v6-bt-title{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:700;color:#10b981;letter-spacing:.5px;text-transform:uppercase;margin-bottom:10px}
    .v6-bt-title::before{content:"🔬";font-size:16px}
    .v6-bt-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:10px}
    .v6-bt-cell{background:rgba(15,23,42,.55);border:1px solid rgba(16,185,129,.2);border-radius:10px;padding:10px}
    .v6-bt-cell-title{font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;font-weight:700}
    .v6-bt-cell-roi-row{display:flex;justify-content:space-between;font-size:11px;margin:2px 0;font-variant-numeric:tabular-nums}
    .v6-bt-cell-label{color:#94a3b8}
    .v6-bt-cell-v5{color:#cbd5e1;font-weight:700}
    .v6-bt-cell-v6{color:#10b981;font-weight:800}
    .v6-bt-delta{font-size:18px;font-weight:800;text-align:center;margin-top:6px;padding:4px;border-radius:6px;background:rgba(16,185,129,.12);color:#10b981}
    .v6-bt-delta.neg{background:rgba(239,68,68,.12);color:#f87171}
    .v6-bt-method{font-size:10px;color:#94a3b8;margin-top:8px;padding:6px;background:rgba(15,23,42,.4);border-radius:6px;line-height:1.4}

    .v6-history-section{margin-top:14px}
    .v6-history-toggle{display:flex;align-items:center;justify-content:space-between;cursor:pointer;padding:8px 12px;background:rgba(15,23,42,.5);border:1px solid rgba(139,92,246,.3);border-radius:10px;font-size:12px;font-weight:700;color:#a78bfa;user-select:none}
    .v6-history-toggle::after{content:"▼";transition:transform .2s}
    .v6-history-toggle.open::after{transform:rotate(180deg)}
    .v6-history-list{max-height:0;overflow:hidden;transition:max-height .3s;margin-top:6px}
    .v6-history-list.open{max-height:600px;overflow-y:auto}
    .v6-history-filters{display:flex;gap:4px;flex-wrap:wrap;margin:8px 0;padding:6px;background:rgba(15,23,42,.4);border-radius:8px}
    .v6-history-filter{padding:3px 8px;border-radius:6px;font-size:10px;font-weight:600;background:rgba(15,23,42,.6);color:#94a3b8;cursor:pointer;border:1px solid transparent;user-select:none}
    .v6-history-filter.active{background:rgba(139,92,246,.25);color:#e5e7eb;border-color:rgba(139,92,246,.5)}
    .v6-history-row{display:grid;grid-template-columns:1fr;gap:4px;padding:8px 10px;border-radius:8px;background:rgba(15,23,42,.45);margin-bottom:4px;font-size:11px}
    .v6-history-row-win{border-left:3px solid #10b981}
    .v6-history-row-loss{border-left:3px solid #ef4444}
    .v6-history-row-skipped{border-left:3px solid #fbbf24;opacity:.85}
    .v6-history-event{font-weight:700;color:#e5e7eb;font-size:11.5px}
    .v6-history-meta{font-size:10px;color:#94a3b8;display:flex;gap:8px;flex-wrap:wrap}
    .v6-history-meta span{font-variant-numeric:tabular-nums}
    .v6-history-meta .pos{color:#10b981}
    .v6-history-meta .neg{color:#f87171}
    .v6-history-meta .arrow{color:#fbbf24}
    .v6-history-empty{text-align:center;padding:20px;color:#94a3b8;font-size:11px}
  `;

  function injectCSS() {
    if (document.getElementById('v6-ui-css')) return;
    const s = document.createElement('style');
    s.id = 'v6-ui-css';
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  // ============================================================
  // STATE & DATA LOADING
  // ============================================================
  const v6 = {
    calibration: null,
    adaptive: null,
    consensus: null,
    ml: null,
    signalsV6: null,
    health: null,
    backtest: null,
    loaded: false,
    enhancedSignals: 0,
    historyFilter: 'all',
    _activeEid: null,
  };

  async function fetchSafe(url) {
    try {
      const r = await fetch(url + '?_=' + Date.now());
      if (!r.ok) return null;
      return await r.json();
    } catch (e) {
      log('fetch failed', url, e);
      return null;
    }
  }

  async function loadV6Data() {
    const [cal, adapt, cons, ml, sv6, health, bt] = await Promise.all([
      fetchSafe('data/calibration_report.json'),
      fetchSafe('data/adaptive_thresholds.json'),
      fetchSafe('data/consensus.json'),
      fetchSafe('data/ml_predictions.json'),
      fetchSafe('data/signals_v6.json'),
      fetchSafe('data/v6_health.json'),
      fetchSafe('data/v6_backtest_report.json'),
    ]);
    v6.calibration = cal;
    v6.adaptive = adapt;
    v6.consensus = cons;
    v6.ml = ml;
    v6.signalsV6 = sv6;
    v6.health = health;
    v6.backtest = bt;
    v6.loaded = true;
    log('Loaded:', { cal: !!cal, adapt: !!adapt, cons: !!cons, ml: !!ml, sv6: !!sv6, health: !!health, bt: !!bt });
    window.V6 = v6;
  }

  // ============================================================
  // HELPERS
  // ============================================================
  const esc = (s) => String(s ?? '').replace(/[<>&"]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]));
  const n2 = (x) => (typeof x === 'number' ? x.toFixed(2) : '—');
  const pct = (x) => (typeof x === 'number' ? (x * 100).toFixed(1) + '%' : '—');

  function gradeClass(g) {
    if (g === 'A+') return 'v6-grade-Aplus';
    return 'v6-grade-' + (g || 'E');
  }

  function statusBadge(status) {
    if (!status) return '';
    const map = {
      UPGRADED: { c: 'v6-badge-upgraded', t: '⬆ UPGRADED', tip: 'EV calibrat creste vs original' },
      DOWNGRADED: { c: 'v6-badge-downgraded', t: '⬇ DOWNGRADED', tip: 'EV calibrat e negativ — atentie' },
      ADJUSTED: { c: 'v6-badge-adjusted', t: '↔ ADJUSTED', tip: 'Mici modificari de la calibrare' },
      UNCHANGED: { c: 'v6-badge-unchanged', t: '= UNCHANGED', tip: 'Calibrarea nu schimba semnalul' },
      NEW_ML: { c: 'v6-badge-newml', t: '✨ NEW ML', tip: 'Semnal generat de ML, nu de BSD' },
    };
    const x = map[status];
    if (!x) return '';
    return `<span class="v6-badge ${x.c}" title="${x.tip}">${x.t}</span>`;
  }

  function gradeBadge(g) {
    if (!g) return '';
    return `<span class="v6-grade ${gradeClass(g)}" title="Grad v6 (calibrat)">${esc(g)}</span>`;
  }

  function consensusBadge(tier, score) {
    if (!tier) return '';
    const scoreStr = score != null ? ` ${(score * 100).toFixed(0)}%` : '';
    return `<span class="v6-consensus v6-consensus-${tier}" title="Acord intre BSD/ML/Poisson">${tier}${scoreStr}</span>`;
  }

  function probRow(sig) {
    const parts = [];
    const adj = typeof sig.adj_prob === 'number' ? sig.adj_prob / 100 : null;
    const cal = sig.calibrated_prob;
    const ml = sig.ml_prob;

    if (adj != null) {
      parts.push(`<span class="v6-prob-item"><span class="v6-prob-label">BSD</span><span class="v6-prob-value">${(adj * 100).toFixed(1)}%</span></span>`);
    }
    if (typeof ml === 'number') {
      parts.push(`<span class="v6-prob-item"><span class="v6-prob-label">ML</span><span class="v6-prob-value v6-prob-ml">${(ml * 100).toFixed(1)}%</span></span>`);
    }
    if (typeof cal === 'number') {
      parts.push(`<span class="v6-prob-item"><span class="v6-prob-label">CAL</span><span class="v6-prob-value v6-prob-cal">${(cal * 100).toFixed(1)}%</span></span>`);
      if (adj != null) {
        const delta = (cal - adj) * 100;
        if (Math.abs(delta) > 1) {
          const cls = delta > 0 ? 'v6-prob-delta-pos' : 'v6-prob-delta-neg';
          const sign = delta > 0 ? '+' : '';
          parts.push(`<span class="v6-prob-delta ${cls}">${sign}${delta.toFixed(1)}pp</span>`);
        }
      }
    }
    if (typeof sig.ev_calibrated === 'number') {
      const evCalPct = sig.ev_calibrated * 100;
      const evColor = evCalPct > 0 ? '#10b981' : '#ef4444';
      parts.push(`<span class="v6-prob-item"><span class="v6-prob-label">EV cal</span><span class="v6-prob-value" style="color:${evColor}">${evCalPct > 0 ? '+' : ''}${evCalPct.toFixed(1)}%</span></span>`);
    }
    if (!parts.length) return '';
    return `<div class="v6-prob-row">${parts.join('')}</div>`;
  }

  // ============================================================
  // ENHANCE SIGNAL CARDS
  // ============================================================
  function enhanceCard(card, sig) {
    if (!card || card.dataset.v6Enhanced === '1') return;
    if (!sig || !sig._v6_enhanced) return;

    // Adauga badge status + grade + consensus pe headerul/titlul cardului
    const titleEl = card.querySelector('.mt, .sig-title, h3, h4, .signal-title, [class*="title"]');
    const targetEl = titleEl || card;

    const badges = [
      statusBadge(sig._v6_status),
      gradeBadge(sig.quality_grade_v6),
      consensusBadge(sig.consensus_tier, sig.consensus_score),
    ].filter(Boolean).join(' ');

    if (badges && !card.querySelector('.v6-badge')) {
      const badgeContainer = document.createElement('span');
      badgeContainer.innerHTML = badges;
      badgeContainer.style.display = 'inline-flex';
      badgeContainer.style.gap = '4px';
      badgeContainer.style.flexWrap = 'wrap';
      badgeContainer.style.marginLeft = '6px';
      targetEl.appendChild(badgeContainer);
    }

    // Adauga randul de probabilitati
    const pRow = probRow(sig);
    if (pRow && !card.querySelector('.v6-prob-row')) {
      const div = document.createElement('div');
      div.innerHTML = pRow;
      card.appendChild(div.firstElementChild);
    }

    card.dataset.v6Enhanced = '1';
    v6.enhancedSignals++;
  }

  function buildSignalIndex() {
    const sigs = (window.S && (window.S.signals && window.S.signals.signals)) || [];
    const arr = Array.isArray(sigs) ? sigs : ((window.S?.signals?.signals) || []);
    const idx = {};
    // Suporta signals.json cu structura {signals:[...]} sau direct array
    const list = Array.isArray(window.S?.signals)
      ? window.S.signals
      : (window.S?.signals?.signals || []);

    for (const s of list) {
      if (!s) continue;
      const key = `${s.event_id}__${s.market}`;
      idx[key] = s;
    }
    return idx;
  }

  function scanAndEnhance() {
    if (!v6.loaded) return;

    const signalIdx = buildSignalIndex();
    if (!Object.keys(signalIdx).length) return;

    // Caut card-uri de semnale prin pattern-uri uzuale
    // Strategie: matched semnal prin event-id si market din date-attributes sau text
    const candidates = document.querySelectorAll(
      '.sig-card, .signal-card, .vb-card, .smartbet-card, ' +
      '[data-event-id], [data-eid], [data-signal-id], ' +
      '.match-card, .pick-card, .top-card, .strat-card, .sb-card, ' +
      '.card[data-eid], .card[data-event]'
    );

    // Atasare prin data attributes (cele mai robuste)
    candidates.forEach((card) => {
      if (card.dataset.v6Enhanced === '1') return;
      const eid = card.dataset.eventId || card.dataset.eid || card.dataset.event || card.dataset.signalId;
      const market = card.dataset.market;
      if (eid && market) {
        const sig = signalIdx[`${eid}__${market}`];
        if (sig) enhanceCard(card, sig);
      }
    });

    // Fallback: cauta prin clase si text continut pentru match
    // (folosit cand cardurile nu au data-attributes)
    if (v6.enhancedSignals < Object.keys(signalIdx).length / 2) {
      tryEnhanceByText(signalIdx);
    }
  }

  function tryEnhanceByText(signalIdx) {
    // Suport pentru chestie inline render — cauta in tot DOM cele care contin nume echipa + market
    const allSignals = Object.values(signalIdx);
    if (!allSignals.length) return;

    // Pentru fiecare card, incercam sa-l identificam prin text
    const cards = document.querySelectorAll('[class*="card"], [class*="signal"], [class*="pick"], [class*="strat"]');
    for (const card of cards) {
      if (card.dataset.v6Enhanced === '1') continue;
      const txt = card.textContent || '';
      if (txt.length < 20 || txt.length > 500) continue;

      // Cauta primul semnal al carui home_team + away_team apar in text
      const match = allSignals.find((s) =>
        s && s.home_team && s.away_team &&
        txt.includes(s.home_team) && txt.includes(s.away_team)
      );
      if (match) enhanceCard(card, match);
    }
  }

  // ============================================================
  // DASHBOARD V6 PANEL
  // ============================================================
  function buildHealthBar() {
    if (!v6.health) return '';
    const overall = v6.health.overall || {};
    const status = overall.status || 'GREEN';
    const message = overall.message || '';
    const n_green = overall.n_green || 0;
    const n_yellow = overall.n_yellow || 0;
    const n_red = overall.n_red || 0;
    return `
      <div class="v6-health-bar v6-health-bar-${status}" title="Click pentru detalii in console: V6UI.data().health">
        <div class="v6-health-dot"></div>
        <div class="v6-health-message">v6 Pipeline: <strong>${esc(status)}</strong> · ${esc(message)}</div>
        <div class="v6-health-counts">
          <span title="Layere GREEN">🟢 ${n_green}</span>
          <span title="Layere YELLOW">🟡 ${n_yellow}</span>
          <span title="Layere RED">🔴 ${n_red}</span>
        </div>
      </div>
    `;
  }

  function buildBacktestPanel() {
    if (!v6.backtest) return '';
    const bt = v6.backtest;
    const oos = (bt.out_of_sample && bt.out_of_sample.overall) || {};
    const isample = (bt.in_sample && bt.in_sample.overall) || {};

    if (!oos.n_total && !isample.n_total) return '';

    const oosV5 = oos.v5_roi_pct || 0;
    const oosV6 = oos.v6_roi_pct || 0;
    const oosDelta = oos.roi_delta_pp || 0;
    const isV5 = isample.v5_roi_pct || 0;
    const isV6 = isample.v6_roi_pct || 0;
    const isDelta = isample.roi_delta_pp || 0;

    const netImpact = oos.net_units_impact || 0;
    const lossesAvoided = oos.skipped_losses_avoided || 0;
    const winsLost = oos.skipped_wins_lost || 0;

    return `
      <div class="v6-bt-panel">
        <div class="v6-bt-title">Backtest v5 vs v6 · Dovada empirica</div>
        <div class="v6-bt-grid">
          <div class="v6-bt-cell">
            <div class="v6-bt-cell-title">Out-of-Sample (test honest)</div>
            <div class="v6-bt-cell-roi-row"><span class="v6-bt-cell-label">v5 ROI:</span><span class="v6-bt-cell-v5">${oosV5 > 0 ? '+' : ''}${oosV5.toFixed(2)}%</span></div>
            <div class="v6-bt-cell-roi-row"><span class="v6-bt-cell-label">v6 ROI:</span><span class="v6-bt-cell-v6">${oosV6 > 0 ? '+' : ''}${oosV6.toFixed(2)}%</span></div>
            <div class="v6-bt-delta ${oosDelta < 0 ? 'neg' : ''}">${oosDelta > 0 ? '+' : ''}${oosDelta.toFixed(2)}pp</div>
            <div class="v6-bt-cell-roi-row" style="margin-top:6px;font-size:10px">
              <span class="v6-bt-cell-label">n test:</span><span>${oos.n_v5_kept || 0} → ${oos.n_v6_kept || 0}</span>
            </div>
          </div>
          <div class="v6-bt-cell">
            <div class="v6-bt-cell-title">In-Sample (toate pariurile)</div>
            <div class="v6-bt-cell-roi-row"><span class="v6-bt-cell-label">v5 ROI:</span><span class="v6-bt-cell-v5">${isV5 > 0 ? '+' : ''}${isV5.toFixed(2)}%</span></div>
            <div class="v6-bt-cell-roi-row"><span class="v6-bt-cell-label">v6 ROI:</span><span class="v6-bt-cell-v6">${isV6 > 0 ? '+' : ''}${isV6.toFixed(2)}%</span></div>
            <div class="v6-bt-delta ${isDelta < 0 ? 'neg' : ''}">${isDelta > 0 ? '+' : ''}${isDelta.toFixed(2)}pp</div>
            <div class="v6-bt-cell-roi-row" style="margin-top:6px;font-size:10px">
              <span class="v6-bt-cell-label">n total:</span><span>${isample.n_total || 0}</span>
            </div>
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:8px;font-size:11px">
          <div style="flex:1;padding:8px;background:rgba(16,185,129,.1);border-radius:8px;text-align:center;color:#10b981">
            <div style="font-weight:700;font-size:14px">${lossesAvoided}</div>
            <div style="font-size:9.5px;color:#86efac">LOSS-uri evitate</div>
          </div>
          <div style="flex:1;padding:8px;background:rgba(239,68,68,.08);border-radius:8px;text-align:center;color:#f87171">
            <div style="font-weight:700;font-size:14px">${winsLost}</div>
            <div style="font-size:9.5px;color:#fca5a5">WIN-uri ratate</div>
          </div>
          <div style="flex:1;padding:8px;background:rgba(59,130,246,.1);border-radius:8px;text-align:center;color:#60a5fa">
            <div style="font-weight:700;font-size:14px">${netImpact > 0 ? '+' : ''}${netImpact.toFixed(1)}u</div>
            <div style="font-size:9.5px;color:#93c5fd">NET impact</div>
          </div>
        </div>
        <div class="v6-bt-method">
          <strong>Out-of-sample</strong> = calibratori antrenati pe primii 60% pariuri cronologic, testati pe ultimii 40% (nevazuti).<br>
          <strong>In-sample</strong> = calibratori curenti aplicati pe toate. Optimist (overfit) dar util pentru istoric individual.
        </div>
      </div>
    `;
  }

  function filterHistory(history, filter) {
    if (filter === 'all') return history;
    if (filter === 'saved') return history.filter(h => h.verdict_v6 === 'SKIPPED_BY_V6' && h.result === 'LOSS');
    if (filter === 'missed') return history.filter(h => h.verdict_v6 === 'SKIPPED_BY_V6' && h.result === 'WIN');
    if (filter === 'kept') return history.filter(h => h.verdict_v6 === 'KEPT' || h.verdict_v6 === 'KEPT_LOWER_EV');
    if (filter === 'wins') return history.filter(h => h.result === 'WIN');
    if (filter === 'losses') return history.filter(h => h.result === 'LOSS');
    return history;
  }

  function renderHistoryRow(h) {
    const isSkipped = h.verdict_v6 === 'SKIPPED_BY_V6';
    const cls = isSkipped ? 'v6-history-row-skipped' :
                (h.result === 'WIN' ? 'v6-history-row-win' : 'v6-history-row-loss');
    const profitV5Cls = h.profit_v5 > 0 ? 'pos' : 'neg';
    const profitV5Str = (h.profit_v5 > 0 ? '+' : '') + h.profit_v5.toFixed(2) + 'u';

    let v6Str = '';
    if (isSkipped) {
      const saved = h.result === 'LOSS';
      v6Str = `<span class="${saved ? 'pos' : 'neg'}">${saved ? '✓ salvat' : '✗ ratat'} ${(-h.profit_v5 > 0 ? '+' : '')}${(-h.profit_v5).toFixed(2)}u</span>`;
    } else {
      v6Str = `<span class="${profitV5Cls}">${profitV5Str}</span>`;
    }

    const probV5Pct = (h.prob_v5 * 100).toFixed(0);
    const probV6Pct = (h.prob_v6 * 100).toFixed(0);
    const probArrow = Math.abs(h.prob_v5 - h.prob_v6) > 0.04 ?
      `<span class="arrow">→ ${probV6Pct}%</span>` : '';

    const date = h.event_date ? h.event_date.slice(0, 10) : '';

    return `
      <div class="v6-history-row ${cls}">
        <div class="v6-history-event">${esc(h.home_team)} vs ${esc(h.away_team)}</div>
        <div class="v6-history-meta">
          <span>${esc(date)}</span>
          <span>${esc(h.market_label || h.market)}</span>
          <span>@${h.odds.toFixed(2)}</span>
          <span>${probV5Pct}% ${probArrow}</span>
          <span style="color:${h.result === 'WIN' ? '#10b981' : '#f87171'};font-weight:700">${h.result}</span>
          ${v6Str}
          <span style="color:#a78bfa;font-size:9px">${esc(h.verdict_v6)}</span>
        </div>
      </div>
    `;
  }

  function buildHistorySection() {
    if (!v6.backtest || !v6.backtest.history) return '';
    const history = v6.backtest.history.slice().reverse();  // recent first

    const totalCount = history.length;
    const filtered = filterHistory(history, v6.historyFilter);

    const filters = [
      { id: 'all', label: `Toate (${totalCount})` },
      { id: 'saved', label: `✓ Salvate` },
      { id: 'missed', label: `✗ Ratate` },
      { id: 'kept', label: `Păstrate` },
      { id: 'wins', label: `WIN` },
      { id: 'losses', label: `LOSS` },
    ];

    const filtersHtml = filters.map(f => `
      <span class="v6-history-filter ${v6.historyFilter === f.id ? 'active' : ''}" data-filter="${f.id}">${esc(f.label)}</span>
    `).join('');

    const rows = filtered.length
      ? filtered.slice(0, 50).map(renderHistoryRow).join('')
      : `<div class="v6-history-empty">Niciun pariu cu filtrul curent</div>`;

    const moreCount = filtered.length > 50 ? filtered.length - 50 : 0;
    const moreText = moreCount > 0 ? `<div class="v6-history-empty">+${moreCount} pariuri (afișate primele 50)</div>` : '';

    return `
      <div class="v6-history-section">
        <div class="v6-history-toggle" id="v6-history-toggle">
          📜 Istoric pariuri (${totalCount}) · v5 vs v6
        </div>
        <div class="v6-history-list" id="v6-history-list">
          <div class="v6-history-filters">${filtersHtml}</div>
          ${rows}
          ${moreText}
        </div>
      </div>
    `;
  }

  function attachHistoryHandlers() {
    const toggle = document.getElementById('v6-history-toggle');
    const list = document.getElementById('v6-history-list');
    if (toggle && list && !toggle.dataset.bound) {
      toggle.dataset.bound = '1';
      toggle.addEventListener('click', () => {
        toggle.classList.toggle('open');
        list.classList.toggle('open');
      });
    }
    document.querySelectorAll('.v6-history-filter').forEach(btn => {
      if (btn.dataset.bound) return;
      btn.dataset.bound = '1';
      btn.addEventListener('click', () => {
        v6.historyFilter = btn.dataset.filter;
        // Re-render
        const panel = document.getElementById('v6-dash-panel');
        if (panel) {
          panel.innerHTML = buildDashV6Panel();
          attachHistoryHandlers();
        }
      });
    });
  }

  function buildDashV6Panel() {
    if (!v6.calibration && !v6.adaptive && !v6.signalsV6) return '';

    const cal = v6.calibration || {};
    const adapt = v6.adaptive || {};
    const sv6 = v6.signalsV6 || {};
    const adaptOverall = adapt.overall || {};
    const sum = sv6.summary || {};

    const overall = cal.overall || {};
    const nCalibrators = overall.n_markets_calibrated || 0;
    const biggestBiasMarket = overall.biggest_bias_market;
    const biggestBiasValue = overall.biggest_bias_value_pp;
    const avgBrierPre = overall.avg_brier_pre;
    const avgBrierPost = overall.avg_brier_post;
    const brierImprovement = (avgBrierPre && avgBrierPost)
      ? ((avgBrierPre - avgBrierPost) / avgBrierPre * 100).toFixed(0)
      : null;

    const cells = [];
    cells.push({ v: sum.upgraded ?? '—', l: 'Upgraded', cls: 'v6-dash-cell-good' });
    cells.push({ v: sum.downgraded ?? '—', l: 'Downgraded', cls: 'v6-dash-cell-bad' });
    cells.push({ v: sum.quality_aplus ?? '—', l: 'Grad A+', cls: 'v6-dash-cell-good' });
    cells.push({ v: nCalibrators, l: 'Calibratoare', cls: '' });
    if (brierImprovement != null) {
      cells.push({ v: brierImprovement + '%', l: 'Brier ↓', cls: 'v6-dash-cell-good' });
    }
    if (adaptOverall.overall_roi_pct != null) {
      const roi = adaptOverall.overall_roi_pct;
      cells.push({
        v: (roi > 0 ? '+' : '') + roi + '%',
        l: 'ROI istoric',
        cls: roi > 0 ? 'v6-dash-cell-good' : 'v6-dash-cell-bad',
      });
    }

    const cellsHtml = cells.map((c) => `
      <div class="v6-dash-cell ${c.cls}">
        <div class="v6-dash-cell-value">${esc(c.v)}</div>
        <div class="v6-dash-cell-label">${esc(c.l)}</div>
      </div>
    `).join('');

    const markets = cal.markets || {};
    const calList = Object.keys(markets).map((m) => {
      const md = markets[m] || {};
      const pre = md.pre || {};
      const bias = pre.bias != null ? (pre.bias * 100) : null;
      const biasCls = bias == null ? '' : (
        Math.abs(bias) < 5 ? 'v6-cal-bias-good' :
        Math.abs(bias) < 15 ? 'v6-cal-bias-warn' : 'v6-cal-bias-bad'
      );
      const biasStr = bias == null ? '—' : (bias > 0 ? '+' : '') + bias.toFixed(1) + 'pp';
      return `
        <div class="v6-cal-row">
          <span class="v6-cal-market">${esc(m)}</span>
          <span class="v6-cal-meta">${esc(md.type)} · n=${md.n_samples}</span>
          <span class="v6-cal-bias ${biasCls}">bias ${biasStr}</span>
        </div>
      `;
    }).join('');

    const biggestBiasInfo = biggestBiasMarket ? `
      <div style="margin-top:10px;padding:8px;background:rgba(239,68,68,.08);border-left:3px solid #ef4444;border-radius:6px;font-size:11px;color:#fca5a5">
        ⚠ Cel mai mare bias: <strong>${esc(biggestBiasMarket)}</strong> · ${biggestBiasValue > 0 ? '+' : ''}${biggestBiasValue}pp (predict ${biggestBiasValue > 0 ? 'mai mult' : 'mai putin'} decat real)
      </div>` : '';

    return `
      ${buildHealthBar()}
      <div class="v6-dash-panel">
        <div class="v6-dash-title">ML Engine v${V6_VERSION} · Status</div>
        <div class="v6-dash-grid">${cellsHtml}</div>
        ${calList ? `<div class="v6-calibration-list">${calList}</div>` : ''}
        ${biggestBiasInfo}
      </div>
      ${buildBacktestPanel()}
      ${buildHistorySection()}
    `;
  }

  function injectDashPanel() {
    if (document.getElementById('v6-dash-panel')) return;
    const dashBody = document.getElementById('dash-body');
    if (!dashBody) return;

    const html = buildDashV6Panel();
    if (!html) return;

    const wrapper = document.createElement('div');
    wrapper.id = 'v6-dash-panel';
    wrapper.innerHTML = html;

    // Inserare la inceput (sus de tot)
    if (dashBody.firstChild) {
      dashBody.insertBefore(wrapper, dashBody.firstChild);
    } else {
      dashBody.appendChild(wrapper);
    }
    attachHistoryHandlers();
    log('Dash panel injected');
  }

  // ============================================================
  // MATCH DETAIL ENHANCEMENT (Engine tab)
  // ============================================================
  function enhanceMatchDetail() {
    const mdContent = document.getElementById('md-content');
    if (!mdContent) return;

    const eid = v6._activeEid;
    if (!eid) {
      log('enhanceMatchDetail: no active eid');
      return;
    }

    injectMlEnsembleBlock(mdContent, eid);
    injectMultiMarketPanel(mdContent, eid);
    replaceSmartBetWithV6(mdContent, eid);
  }

  function injectMlEnsembleBlock(mdContent, eid) {
    if (mdContent.querySelector('.v6-ml-block')) return;

    const mlResults = (v6.ml && v6.ml.results) || [];
    const mlMatch = mlResults.find((r) => Number(r.event_id) === Number(eid));
    if (!mlMatch) return;

    const consResults = (v6.consensus && v6.consensus.results) || [];
    const consMatch = consResults.find((r) => Number(r.event_id) === Number(eid));

    const probs = mlMatch.ml_probabilities || {};
    const stats = [];
    if (typeof probs.homeWin === 'number') stats.push({ l: 'Home', v: (probs.homeWin * 100).toFixed(0) + '%' });
    if (typeof probs.draw === 'number') stats.push({ l: 'Draw', v: (probs.draw * 100).toFixed(0) + '%' });
    if (typeof probs.awayWin === 'number') stats.push({ l: 'Away', v: (probs.awayWin * 100).toFixed(0) + '%' });

    const statsHtml = stats.map((s) => `
      <div class="v6-ml-stat">
        <div class="v6-ml-stat-label">${esc(s.l)}</div>
        <div class="v6-ml-stat-value">${esc(s.v)}</div>
      </div>
    `).join('');

    const consTier = consMatch?.markets?.homeWin?.tier;
    const consScore = consMatch?.overall_match_consensus;

    const html = `
      <div class="v6-ml-block">
        <div class="v6-ml-title">ML Ensemble v${V6_VERSION} 
          ${consTier ? consensusBadge(consTier, consScore) : ''}
        </div>
        <div class="v6-ml-grid">${statsHtml}</div>
      </div>
    `;

    const enginePanel = mdContent.querySelector('.md-panel[data-panel="engine"]');
    if (enginePanel) {
      const div = document.createElement('div');
      div.innerHTML = html;
      enginePanel.insertBefore(div.firstElementChild, enginePanel.firstChild);
    }
  }

  function injectMultiMarketPanel(mdContent, eid) {
    if (mdContent.querySelector('.v6-multi-panel')) return;

    const sigsObj = window.S?.signals;
    const allSignals = Array.isArray(sigsObj)
      ? sigsObj
      : (sigsObj?.signals || []);
    const matchSignals = allSignals.filter(s =>
      s && Number(s.event_id) === Number(eid)
    );

    if (matchSignals.length === 0) {
      log('injectMultiMarketPanel: no signals for eid', eid);
      return;
    }

    matchSignals.sort((a, b) => {
      const sa = a.smartbet_score_v6 ?? a.smartbet_score ?? 0;
      const sb = b.smartbet_score_v6 ?? b.smartbet_score ?? 0;
      if (sb !== sa) return sb - sa;
      return (b.edge_pp || 0) - (a.edge_pp || 0);
    });

    const rowsHtml = matchSignals.map((s, idx) => {
      const isBest = idx === 0;
      const prob = s.calibrated_prob != null ? s.calibrated_prob : ((s.adj_prob || 0) / 100);
      const probPct = (prob * 100).toFixed(1) + '%';
      const edgePct = (s.edge_pp || 0).toFixed(1);
      const oddsStr = s.odds ? `@${Number(s.odds).toFixed(2)}` : '';
      const evRaw = (s.ev_calibrated ?? s.ev ?? 0);
      const evPct = (evRaw * 100).toFixed(1);
      const sbV6 = s.smartbet_score_v6 ?? s.smartbet_score ?? 0;
      const gradeV6 = s.quality_grade_v6 ?? s.quality_grade ?? '';
      const strategyLabel = s.strategy_label || s.strategy || '';

      return `
        <div class="v6-multi-row ${isBest ? 'v6-multi-row-best' : ''}">
          <div>
            <div class="v6-multi-market">${esc(s.market_label || s.market)} ${gradeBadge(gradeV6)}</div>
            <div class="v6-multi-strategy">${esc(strategyLabel)} · SB ${Math.round(sbV6)}</div>
          </div>
          <div class="v6-multi-meta">
            <span class="v6-multi-prob">${probPct} ${oddsStr}</span>
            <span class="v6-multi-edge">Edge +${edgePct}pp · EV ${evPct > 0 ? '+' : ''}${evPct}%</span>
          </div>
        </div>
      `;
    }).join('');

    const intro = matchSignals.length > 1
      ? `Sistemul gaseste valoare pe <strong>${matchSignals.length} markete</strong> pentru acest meci. Pariul cu cel mai mare scor este marcat verde.`
      : `Pariu unic recomandat pentru acest meci.`;

    const html = `
      <div class="v6-multi-panel">
        <div class="v6-multi-title">Toate pariurile valoroase (${matchSignals.length})</div>
        <div style="font-size:11px;color:#cbd5e1;margin-bottom:8px;line-height:1.4">${intro}</div>
        ${rowsHtml}
      </div>
    `;

    const mdBody = mdContent.querySelector('.md-body') || mdContent;
    const div = document.createElement('div');
    div.innerHTML = html;
    mdBody.insertBefore(div.firstElementChild, mdBody.firstChild);
    log('injectMultiMarketPanel: injected for eid', eid, 'with', matchSignals.length, 'signals');
  }

  function replaceSmartBetWithV6(mdContent, eid) {
    const sigsObj = window.S?.signals;
    const allSignals = Array.isArray(sigsObj) ? sigsObj : (sigsObj?.signals || []);
    const matchSignals = allSignals.filter(s =>
      s && Number(s.event_id) === Number(eid) && s.smartbet_score_v6 != null
    );

    if (matchSignals.length === 0) return;

    matchSignals.sort((a, b) => (b.smartbet_score_v6 || 0) - (a.smartbet_score_v6 || 0));
    const best = matchSignals[0];
    const v6Score = Math.round(best.smartbet_score_v6);
    const v6Grade = best.quality_grade_v6 || '';

    mdContent.querySelectorAll('.md-kpi').forEach(kpi => {
      const label = kpi.querySelector('.md-kpi-l');
      if (label && label.textContent.trim().toLowerCase().includes('smartbet')) {
        const val = kpi.querySelector('.md-kpi-v');
        if (val && !val.dataset.v6Replaced) {
          const oldVal = val.textContent.trim();
          val.textContent = v6Score;
          val.dataset.v6Replaced = '1';
          val.dataset.v6Old = oldVal;
          val.classList.add('v6-sb-replaced');
          val.title = `v6 (calibrat): ${v6Score} ${v6Grade}\nv5 (original): ${oldVal}`;
        }
      }
    });

    mdContent.querySelectorAll('.sbs').forEach(sbs => {
      if (sbs.dataset.v6Replaced) return;
      const fi = sbs.querySelector('.sbs-fi');
      const v = sbs.querySelector('.sbs-v');
      if (fi && v) {
        fi.style.width = v6Score + '%';
        v.textContent = v6Score;
        sbs.dataset.v6Replaced = '1';
        sbs.title = `SmartBet v6 (calibrat): ${v6Score} ${v6Grade}`;
      }
    });
  }

  // ============================================================
  // MONKEY-PATCH openMatchDetail + switchMatchTab
  // ============================================================
  function hookOpenMatchDetail() {
    if (typeof window.openMatchDetail !== 'function') return false;
    if (window.openMatchDetail.__v6Hooked) return true;

    const original = window.openMatchDetail;
    window.openMatchDetail = async function(eid) {
      v6._activeEid = eid;
      log('openMatchDetail hook: active eid =', eid);
      const result = await original.apply(this, arguments);
      setTimeout(() => {
        try { enhanceMatchDetail(); } catch(e) { log('enhance err', e); }
      }, 100);
      setTimeout(() => {
        try { enhanceMatchDetail(); } catch(e) { log('enhance err', e); }
      }, 500);
      return result;
    };
    window.openMatchDetail.__v6Hooked = true;
    log('openMatchDetail hooked');
    return true;
  }

  function hookSwitchMatchTab() {
    if (typeof window.switchMatchTab !== 'function') return false;
    if (window.switchMatchTab.__v6Hooked) return true;

    const original = window.switchMatchTab;
    window.switchMatchTab = function(tab) {
      const result = original.apply(this, arguments);
      setTimeout(() => {
        try { enhanceMatchDetail(); } catch(e) { log('enhance err', e); }
      }, 100);
      return result;
    };
    window.switchMatchTab.__v6Hooked = true;
    log('switchMatchTab hooked');
    return true;
  }

  // ============================================================
  // TOAST NOTIFICATION
  // ============================================================
  function showToast(msg, ms = 3000) {
    let toast = document.querySelector('.v6-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.className = 'v6-toast';
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => toast.classList.remove('show'), ms);
  }

  // ============================================================
  // MUTATION OBSERVER + INITIALIZATION
  // ============================================================
  let scanScheduled = false;
  // ============================================================
  // FIX v6.7: Deduplicate bp20-insight blocks
  // (workaround pentru duplicate cauzat de patchSigCard din betpredict_20.js)
  // ============================================================
  function dedupBp20Blocks() {
    document.querySelectorAll('.sig-card').forEach(card => {
      const insights = card.querySelectorAll('.bp20-insight');
      if (insights.length > 1) {
        for (let i = 1; i < insights.length; i++) insights[i].remove();
      }
      const badges = card.querySelectorAll('.bp20-badges');
      if (badges.length > 1) {
        for (let i = 1; i < badges.length; i++) badges[i].remove();
      }
    });
  }

  // ============================================================
  // FIX v6.6: TOP RECOMMENDATIONS RANKING BADGES
  // ============================================================
  function getSigScore(sig) {
    if (typeof window.marketSignalScore === 'function') {
      return window.marketSignalScore(sig) || 0;
    }
    return sig.smartbet_score_v6 ?? sig.smartbet_score ?? 0;
  }

  // Cauta cardul "real" plecand de la elementul clickabil (poate fi buton)
  function findParentCard(el) {
    let current = el;
    const cardSelectors = [
      '.sig-card', '.sig-row', '.value-card', '.match-card',
      '.team-card', '.results-row', '.vb-card', '.smartbet-card',
      '.pick-card', '.top-card', '.card'
    ];
    // Daca elementul insusi e card, returneaza-l
    for (const sel of cardSelectors) {
      if (el.matches(sel)) return el;
    }
    // Altfel urca in DOM pana gasesti un card sau ajunge la 5 nivele
    let depth = 0;
    while (current && depth < 6) {
      current = current.parentElement;
      if (!current) break;
      for (const sel of cardSelectors) {
        if (current.matches(sel)) return current;
      }
      // Fallback: orice element cu inaltime > 120px care nu e <section>
      const h = current.offsetHeight || 0;
      if (h > 120 && current.tagName !== 'SECTION' && current.tagName !== 'BODY') {
        return current;
      }
      depth++;
    }
    return null;
  }

  function markTopRecommendations() {
    const sigsObj = window.S?.signals;
    const allSignals = Array.isArray(sigsObj)
      ? sigsObj
      : (sigsObj?.signals || []);
    if (!allSignals.length) return;

    // Cel mai bun signal per eveniment
    const bestPerEvent = {};
    for (const s of allSignals) {
      if (!s || !s.event_id) continue;
      const score = getSigScore(s);
      const current = bestPerEvent[s.event_id];
      if (!current || score > getSigScore(current)) {
        bestPerEvent[s.event_id] = s;
      }
    }

    const ranked = Object.values(bestPerEvent)
      .sort((a, b) => getSigScore(b) - getSigScore(a))
      .slice(0, 3);
    if (!ranked.length) return;

    const rankMap = {};
    ranked.forEach((sig, idx) => { rankMap[String(sig.event_id)] = { rank: idx + 1, sig }; });

    // Sterge badge-urile vechi
    document.querySelectorAll('.v6-rank-badge').forEach(b => b.remove());
    document.querySelectorAll('[data-v6-ranked]').forEach(c => { delete c.dataset.v6Ranked; });

    // Track ce carduri am etichetat deja (evita dublu badge pentru acelasi card)
    const taggedCards = new WeakSet();

    document.querySelectorAll('[onclick*="openMatchDetail"]').forEach(clickEl => {
      const onclick = clickEl.getAttribute('onclick') || '';
      const m = onclick.match(/openMatchDetail\(['"]?([^'")\s]+)['"]?\)/);
      if (!m) return;
      const eid = m[1];
      const ranking = rankMap[eid];
      if (!ranking) return;

      // Gaseste cardul real (poate fi parinte daca clickEl e doar buton)
      const card = findParentCard(clickEl);
      if (!card || taggedCards.has(card)) return;
      if (card.dataset.v6Ranked === '1') return;

      const cs = getComputedStyle(card);
      if (cs.position === 'static') card.style.position = 'relative';

      const badge = document.createElement('div');
      badge.className = `v6-rank-badge v6-rank-${ranking.rank}`;
      const { sig } = ranking;
      const score = Math.round(getSigScore(sig));
      const lbl = sig.market_label || sig.market || '';
      badge.innerHTML = ranking.rank === 1 ? '✓' : String(ranking.rank);
      badge.title = ranking.rank === 1
        ? `Cel mai sigur pariu al zilei: ${lbl} (SB ${score})`
        : `Recomandare #${ranking.rank}: ${lbl} (SB ${score})`;

      card.appendChild(badge);
      card.dataset.v6Ranked = '1';
      taggedCards.add(card);
    });

    log('Ranked:', ranked.map(s =>
      `#${rankMap[String(s.event_id)].rank} ${s.home_team||'?'} vs ${s.away_team||'?'} SB=${Math.round(getSigScore(s))}`
    ));
  }

  function scheduleScan() {
    if (scanScheduled) return;
    scanScheduled = true;
    setTimeout(() => {
      scanScheduled = false;
      try {
        scanAndEnhance();
        injectDashPanel();
        enhanceMatchDetail();
        dedupBp20Blocks();
        markTopRecommendations();
      } catch (e) {
        log('scan error', e);
      }
    }, 200);
  }

  function setupObserver() {
    const targets = ['sec-dash', 'sec-meciuri', 'sec-smartbet', 'sec-value', 'sec-live', 'sec-top']
      .map((id) => document.getElementById(id))
      .filter(Boolean);

    if (!targets.length) {
      setTimeout(setupObserver, 500);
      return;
    }

    const obs = new MutationObserver((mutations) => {
      let hasContent = false;
      for (const m of mutations) {
        if (m.addedNodes && m.addedNodes.length) {
          hasContent = true;
          break;
        }
      }
      if (hasContent) scheduleScan();
    });

    targets.forEach((t) => {
      obs.observe(t, { childList: true, subtree: true });
    });

    // FIX v6.5: Observam .md-backdrop (exista din start in HTML static),
    // nu #md-content care e creat dinamic la deschidere modal.
    const mdBackdrop = document.querySelector('.md-backdrop');
    if (mdBackdrop) {
      obs.observe(mdBackdrop, { childList: true, subtree: true });
      log('Observer attached to .md-backdrop');
    } else {
      // Fallback: observ body daca backdrop nu exista inca
      obs.observe(document.body, { childList: true, subtree: false });
    }

    log('Observer attached to', targets.length, 'sections');
  }

  // ============================================================
  // PUBLIC API
  // ============================================================
  window.V6UI = {
    refresh: () => scheduleScan(),
    data: () => v6,
    version: V6_VERSION,
    activeEid: () => v6._activeEid,
    forceEnhance: () => { try { enhanceMatchDetail(); } catch(e) { console.error(e); } },
    stats: () => ({
      enhanced: v6.enhancedSignals,
      loaded: v6.loaded,
      activeEid: v6._activeEid,
      openMatchDetailHooked: !!(window.openMatchDetail && window.openMatchDetail.__v6Hooked),
      switchMatchTabHooked: !!(window.switchMatchTab && window.switchMatchTab.__v6Hooked),
      ml: !!v6.ml,
      calibration: !!v6.calibration,
      consensus: !!v6.consensus,
      adaptive: !!v6.adaptive,
      signalsV6: !!v6.signalsV6,
      health: !!v6.health,
      backtest: !!v6.backtest,
    }),
  };

  // ============================================================
  // INIT
  // ============================================================
  async function init() {
    injectCSS();
    await loadV6Data();
    setupObserver();
    scheduleScan();

    // Hook-uri (asteapta functiile sa fie definite global)
    let hookAttempts = 0;
    const hookInterval = setInterval(() => {
      hookAttempts++;
      const h1 = hookOpenMatchDetail();
      const h2 = hookSwitchMatchTab();
      if ((h1 && h2) || hookAttempts > 30) {
        clearInterval(hookInterval);
        log('Hooks status: openMatchDetail=' + h1 + ', switchMatchTab=' + h2);
      }
    }, 500);

    // Re-scan periodic (cazuri unde S nu e gata la load)
    let retries = 0;
    const retryInterval = setInterval(() => {
      retries++;
      scheduleScan();
      if (retries > 20 || v6.enhancedSignals > 0) {
        clearInterval(retryInterval);
      }
    }, 800);

    log('v6_ui initialized, version', V6_VERSION);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
