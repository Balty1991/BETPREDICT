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
    .v6-cal-market{font-weight:700;color:#e5e7eb;font-family:ui-monospace,monospace}
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
    loaded: false,
    enhancedSignals: 0,
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
    const [cal, adapt, cons, ml, sv6, health] = await Promise.all([
      fetchSafe('data/calibration_report.json'),
      fetchSafe('data/adaptive_thresholds.json'),
      fetchSafe('data/consensus.json'),
      fetchSafe('data/ml_predictions.json'),
      fetchSafe('data/signals_v6.json'),
      fetchSafe('data/v6_health.json'),
    ]);
    v6.calibration = cal;
    v6.adaptive = adapt;
    v6.consensus = cons;
    v6.ml = ml;
    v6.signalsV6 = sv6;
    v6.health = health;
    v6.loaded = true;
    log('Loaded:', { cal: !!cal, adapt: !!adapt, cons: !!cons, ml: !!ml, sv6: !!sv6, health: !!health });
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
    log('Dash panel injected');
  }

  // ============================================================
  // MATCH DETAIL ENHANCEMENT (Engine tab)
  // ============================================================
  function enhanceMatchDetail() {
    const mdContent = document.getElementById('md-content');
    if (!mdContent) return;
    if (mdContent.querySelector('.v6-ml-block')) return;

    // Identificam event_id activ
    const headerEl = mdContent.querySelector('[data-eid]');
    const eid = headerEl ? parseInt(headerEl.dataset.eid) : null;
    if (!eid && !window.S?._currentEid) return;
    const targetEid = eid || window.S._currentEid;

    // Cauta predictiile ML pentru acest meci
    const mlResults = (v6.ml && v6.ml.results) || [];
    const mlMatch = mlResults.find((r) => r.event_id === targetEid);
    if (!mlMatch) return;

    const consResults = (v6.consensus && v6.consensus.results) || [];
    const consMatch = consResults.find((r) => r.event_id === targetEid);

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

    // Inserare la inceputul engine block
    const engineBlock = mdContent.querySelector('[data-md-tab="engine"]') || mdContent.firstChild;
    if (engineBlock) {
      const div = document.createElement('div');
      div.innerHTML = html;
      engineBlock.insertBefore(div.firstElementChild, engineBlock.firstChild);
    }
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
  function scheduleScan() {
    if (scanScheduled) return;
    scanScheduled = true;
    setTimeout(() => {
      scanScheduled = false;
      try {
        scanAndEnhance();
        injectDashPanel();
        enhanceMatchDetail();
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

    // Si modal de match detail
    const mdContent = document.getElementById('md-content');
    if (mdContent) {
      obs.observe(mdContent, { childList: true, subtree: true });
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
    stats: () => ({
      enhanced: v6.enhancedSignals,
      loaded: v6.loaded,
      ml: !!v6.ml,
      calibration: !!v6.calibration,
      consensus: !!v6.consensus,
      adaptive: !!v6.adaptive,
      signalsV6: !!v6.signalsV6,
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
