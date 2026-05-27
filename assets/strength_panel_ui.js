/**
 * strength_panel_ui.js — BetPredict Pro v6.1
 * ===========================================
 * Panou vizual Attack/Defense Strength + Analiză Poisson
 *
 * Ce face:
 * - Injectează un panou "⚡ Forță & Poisson" în fiecare card de semnal
 *   din secțiunea SmartBet, afișând:
 *     • Attack Strength / Defense Strength (bare comparative)
 *     • λ Goluri Așteptate (Home vs Away, model Poisson)
 *     • Scor Poisson (cel mai probabil scor calculat matematic)
 *     • Tendința formei (↑ în creștere / ↓ în declin / → stabil)
 * - Injectează un panou sumar în Dashboard cu top matches
 *
 * Arhitectura:
 * - Citește data/signals_v6.json (care conține lambda_home/away din
 *   rolling_features_engine.py prin compute_signals_v6.py)
 * - Folosește MutationObserver pentru a detecta cardurile .sig-card
 *   după ce betpredict_20.js le randează
 * - Potrivire card ↔ semnal prin text (home_team + away_team)
 * - Nu modifică codul existent — injectează adiacent
 */
(function () {
  'use strict';

  const SP_VERSION = '6.1';
  const SP_DATA_URL = 'data/signals_v6.json';
  const DEBUG = false;
  const log = (...a) => DEBUG && console.log('[sp_ui]', ...a);

  // ============================================================
  // CSS
  // ============================================================
  const CSS = `
    .sp-panel {
      background: rgba(15,23,42,0.55);
      border: 1px solid rgba(255,255,255,0.07);
      border-radius: 8px;
      padding: 10px 12px;
      margin-top: 8px;
    }
    .sp-title {
      font-size: 9px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .5px;
      color: #475569;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .sp-title-icon { font-size: 11px; }
    .sp-teams-grid {
      display: grid;
      grid-template-columns: 1fr auto 1fr;
      gap: 6px;
      align-items: center;
      margin-bottom: 8px;
    }
    .sp-team-label {
      font-size: 9px;
      font-weight: 700;
      color: #94a3b8;
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: .3px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .sp-bar-row {
      display: flex;
      align-items: center;
      gap: 5px;
      margin-bottom: 3px;
    }
    .sp-bar-lbl {
      font-size: 9px;
      color: #475569;
      width: 24px;
      flex-shrink: 0;
      font-weight: 600;
    }
    .sp-bar-wrap {
      flex: 1;
      height: 5px;
      background: rgba(255,255,255,0.06);
      border-radius: 3px;
      overflow: hidden;
    }
    .sp-bar-fill {
      height: 100%;
      border-radius: 3px;
    }
    .sp-bar-atk { background: linear-gradient(90deg,#10b981,#059669); }
    .sp-bar-def { background: linear-gradient(90deg,#3b82f6,#2563eb); }
    .sp-bar-val {
      font-size: 9px;
      color: #94a3b8;
      width: 28px;
      text-align: right;
      flex-shrink: 0;
    }
    .sp-vs-badge {
      background: rgba(100,116,139,0.2);
      border-radius: 50%;
      width: 22px;
      height: 22px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 8px;
      font-weight: 700;
      color: #64748b;
      text-align: center;
      flex-shrink: 0;
      align-self: center;
    }
    .sp-team-right .sp-bar-row { flex-direction: row-reverse; }
    .sp-team-right .sp-bar-lbl { text-align: right; }
    .sp-team-right .sp-bar-val { text-align: left; }
    .sp-footer {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      padding-top: 8px;
      border-top: 1px solid rgba(255,255,255,0.05);
      font-size: 10px;
    }
    .sp-lambda-badge {
      display: flex;
      align-items: center;
      gap: 4px;
      color: #94a3b8;
    }
    .sp-lambda-val {
      font-weight: 700;
      color: #e2e8f0;
      font-size: 11px;
    }
    .sp-lambda-sep { color: #475569; }
    .sp-poisson-score {
      background: rgba(16,185,129,0.12);
      border: 1px solid rgba(16,185,129,0.25);
      color: #10b981;
      padding: 1px 7px;
      border-radius: 5px;
      font-weight: 800;
      font-size: 11px;
      letter-spacing: .5px;
    }
    .sp-trend-up   { color: #10b981; font-weight: 700; }
    .sp-trend-down { color: #ef4444; font-weight: 700; }
    .sp-trend-neutral { color: #475569; }
    .sp-trend-wrap { display: flex; align-items: center; gap: 5px; color: #64748b; font-size: 10px; }
    .sp-data-note { font-size: 8.5px; color: #334155; margin-top: 4px; }

    /* Dashboard summary panel */
    .sp-dash-panel {
      background: linear-gradient(135deg,rgba(16,185,129,.06),rgba(59,130,246,.04));
      border: 1px solid rgba(16,185,129,.18);
      border-radius: 12px;
      padding: 14px;
      margin: 0 0 14px 0;
    }
    .sp-dash-title {
      font-size: 11px;
      font-weight: 700;
      color: #10b981;
      text-transform: uppercase;
      letter-spacing: .5px;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .sp-dash-row {
      display: grid;
      grid-template-columns: 1fr auto auto auto;
      gap: 8px;
      padding: 6px 0;
      border-bottom: 1px solid rgba(255,255,255,0.04);
      font-size: 10px;
      align-items: center;
    }
    .sp-dash-row:last-child { border-bottom: none; }
    .sp-dash-match { color: #cbd5e1; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .sp-dash-lam { color: #94a3b8; }
    .sp-dash-score {
      background: rgba(16,185,129,0.12);
      color: #10b981;
      padding: 1px 5px;
      border-radius: 4px;
      font-weight: 700;
      font-size: 10px;
    }
    .sp-dash-trend { font-size: 11px; }
    html[data-theme="light"] .sp-panel {
      background: rgba(248,250,252,0.8);
      border-color: rgba(0,0,0,0.08);
    }
    html[data-theme="light"] .sp-team-label,
    html[data-theme="light"] .sp-bar-val { color: #64748b; }
    html[data-theme="light"] .sp-lambda-val { color: #1e293b; }
    html[data-theme="light"] .sp-dash-match { color: #334155; }
  `;

  function injectCSS() {
    if (document.getElementById('sp-ui-css')) return;
    const s = document.createElement('style');
    s.id = 'sp-ui-css';
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  function esc(v) {
    if (v == null) return '';
    return String(v)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function n1(v) { return v != null ? Number(v).toFixed(1) : '—'; }
  function n2(v) { return v != null ? Number(v).toFixed(2) : '—'; }

  // ============================================================
  // STARE GLOBALĂ
  // ============================================================

  const sp = {
    loaded: false,
    signals: [],
    // Index: "home_team|away_team" -> primul semnal pentru acel meci
    matchIdx: {},
    enhanced: new WeakSet(),
  };

  // ============================================================
  // ÎNCĂRCARE DATE
  // ============================================================

  async function loadData() {
    try {
      const resp = await fetch(SP_DATA_URL + '?v=' + Date.now());
      const data = await resp.json();
      sp.signals = data.signals || [];
      sp.matchIdx = buildMatchIndex(sp.signals);
      sp.loaded = true;
      log('Încărcate', sp.signals.length, 'semnale, indexate', Object.keys(sp.matchIdx).length, 'meciuri');
      run();
    } catch (e) {
      log('Eroare încărcare:', e);
    }
  }

  function buildMatchIndex(signals) {
    const idx = {};
    for (const sig of signals) {
      if (!sig._has_poisson_data) continue;
      const key = makeKey(sig.home_team, sig.away_team);
      if (!idx[key]) {
        idx[key] = sig; // Primul semnal per meci (orice market)
      }
    }
    return idx;
  }

  function makeKey(home, away) {
    return (home || '').trim().toLowerCase() + '|' + (away || '').trim().toLowerCase();
  }

  // ============================================================
  // TREND INDICATOR
  // ============================================================

  function trendIcon(trend) {
    const t = Number(trend) || 0;
    if (t > 0.3) return `<span class="sp-trend-up">↑</span>`;
    if (t < -0.3) return `<span class="sp-trend-down">↓</span>`;
    return `<span class="sp-trend-neutral">→</span>`;
  }

  function trendLabel(trend, name) {
    const t = Number(trend) || 0;
    const icon = trendIcon(trend);
    const cls = t > 0.3 ? 'sp-trend-up' : (t < -0.3 ? 'sp-trend-down' : 'sp-trend-neutral');
    return `<span class="${cls}">${icon} ${esc(name)} ${t > 0 ? '+' : ''}${t.toFixed(1)}</span>`;
  }

  // ============================================================
  // BAR RENDERER
  // ============================================================

  function bar(value, maxVal, type) {
    // maxVal = 2.5 (strength > 2.5 = excepțional)
    const pct = Math.min(100, Math.round((value / maxVal) * 100));
    return `
      <div class="sp-bar-row">
        <span class="sp-bar-lbl">${type === 'atk' ? 'ATK' : 'DEF'}</span>
        <div class="sp-bar-wrap">
          <div class="sp-bar-fill sp-bar-${type}" style="width:${pct}%"></div>
        </div>
        <span class="sp-bar-val">${n2(value)}</span>
      </div>`;
  }

  // ============================================================
  // RENDER PANOU CARD
  // ============================================================

  function renderPanel(sig) {
    const lh = sig.lambda_home;
    const la = sig.lambda_away;
    const hAtk = sig.h_attack_str;
    const aDef = sig.a_defense_str;
    const aDef2 = sig.a_defense_str;
    const aAtk = sig.a_attack_str;
    const hDef = sig.h_defense_str;
    const hTrend = sig.h_form_trend;
    const aTrend = sig.a_form_trend;
    const pscore = sig.poisson_score || '—';

    const maxStr = 2.5;

    // Nota calitate date dacă n_matches e mic
    const hHome = sig.h_form_pts_10 != null ? '' : '?';

    return `
      <div class="sp-panel">
        <div class="sp-title">
          <span class="sp-title-icon">⚡</span>
          Forță Echipe · Model Poisson
        </div>
        <div class="sp-teams-grid">
          <div class="sp-team-left">
            <div class="sp-team-label">${esc(sig.home_team)}</div>
            ${bar(hAtk || 1, maxStr, 'atk')}
            ${bar(hDef || 1, maxStr, 'def')}
          </div>
          <div class="sp-vs-badge">vs</div>
          <div class="sp-team-right">
            <div class="sp-team-label" style="text-align:right">${esc(sig.away_team)}</div>
            ${bar(aAtk || 1, maxStr, 'atk')}
            ${bar(aDef2 || 1, maxStr, 'def')}
          </div>
        </div>
        <div class="sp-footer">
          <div class="sp-lambda-badge">
            λ <span class="sp-lambda-val">${n1(lh)}</span>
            <span class="sp-lambda-sep">—</span>
            <span class="sp-lambda-val">${n1(la)}</span>
          </div>
          <span class="sp-poisson-score">${esc(pscore)}</span>
          <div class="sp-trend-wrap">
            ${trendLabel(hTrend, (sig.home_team || '').split(' ')[0])}
            <span class="sp-trend-neutral"> · </span>
            ${trendLabel(aTrend, (sig.away_team || '').split(' ')[0])}
          </div>
        </div>
      </div>`;
  }

  // ============================================================
  // INJECTARE ÎN CARDURI SIG-CARD
  // ============================================================

  function tryEnhanceCard(card) {
    if (sp.enhanced.has(card)) return;
    if (!sp.loaded) return;

    const txt = card.textContent || '';

    // Potrivire semnal prin text: caută home_team + away_team
    let matched = null;
    for (const [key, sig] of Object.entries(sp.matchIdx)) {
      const [home, away] = key.split('|');
      if (home && away && txt.toLowerCase().includes(home) && txt.toLowerCase().includes(away)) {
        matched = sig;
        break;
      }
    }

    if (!matched) return;

    sp.enhanced.add(card);

    const panel = document.createElement('div');
    panel.innerHTML = renderPanel(matched);
    card.appendChild(panel.firstElementChild);
    log('Enhanced card:', matched.home_team, 'vs', matched.away_team);
  }

  // ============================================================
  // DASHBOARD PANEL
  // ============================================================

  function renderDashPanel() {
    if (!sp.loaded || !Object.keys(sp.matchIdx).length) return '';

    const matchData = Object.values(sp.matchIdx).slice(0, 8);
    if (!matchData.length) return '';

    const rows = matchData.map((sig) => {
      const lh = sig.lambda_home != null ? n1(sig.lambda_home) : '—';
      const la = sig.lambda_away != null ? n1(sig.lambda_away) : '—';
      const pscore = sig.poisson_score || '—';
      const hTrend = trendIcon(sig.h_form_trend);
      const aTrend = trendIcon(sig.a_form_trend);
      const match = `${sig.home_team || '?'} vs ${sig.away_team || '?'}`;
      return `
        <div class="sp-dash-row">
          <span class="sp-dash-match" title="${esc(match)}">${esc(match)}</span>
          <span class="sp-dash-lam">λ ${lh} — ${la}</span>
          <span class="sp-dash-score">${esc(pscore)}</span>
          <span class="sp-dash-trend">${hTrend}${aTrend}</span>
        </div>`;
    }).join('');

    return `
      <div class="sp-dash-panel" id="sp-dash-panel">
        <div class="sp-dash-title">
          ⚡ Analiză Forță & Poisson · Goluri Așteptate
        </div>
        ${rows}
        <div class="sp-data-note">
          λ = goluri așteptate (model Poisson Attack/Defense Strength · ultimele 10 meciuri)
        </div>
      </div>`;
  }

  function injectDashPanel() {
    if (document.getElementById('sp-dash-panel')) return;
    const dashBody = document.getElementById('dash-body');
    if (!dashBody) return;
    const html = renderDashPanel();
    if (!html) return;
    const wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    const panel = wrapper.firstElementChild;
    if (!panel) return;
    // Inserare după panoul v6 dacă există, altfel la final
    const v6Panel = document.getElementById('v6-dash-panel');
    if (v6Panel && v6Panel.nextSibling) {
      dashBody.insertBefore(panel, v6Panel.nextSibling);
    } else if (v6Panel) {
      v6Panel.parentNode.insertBefore(panel, v6Panel.nextSibling);
    } else if (dashBody.firstChild) {
      dashBody.insertBefore(panel, dashBody.firstChild);
    } else {
      dashBody.appendChild(panel);
    }
    log('Dashboard panel injected');
  }

  // ============================================================
  // SCAN & OBSERVE
  // ============================================================

  function scanCards() {
    if (!sp.loaded) return;
    const cards = document.querySelectorAll('.sig-card:not([data-sp-done])');
    cards.forEach((card) => {
      card.setAttribute('data-sp-done', '1');
      tryEnhanceCard(card);
    });
  }

  let _scanTimer = null;
  function scheduleScan(delay) {
    clearTimeout(_scanTimer);
    _scanTimer = setTimeout(() => {
      scanCards();
      injectDashPanel();
    }, delay || 200);
  }

  function run() {
    scheduleScan(100);

    // Observer pentru sbBody (SmartBet tab)
    const sbBody = document.getElementById('sb-body');
    const dashBody = document.getElementById('dash-body');
    const root = document.getElementById('app') || document.body;

    const obs = new MutationObserver(() => {
      scheduleScan(150);
    });

    if (sbBody) obs.observe(sbBody, { childList: true, subtree: true });
    if (dashBody) obs.observe(dashBody, { childList: true, subtree: false });

    // Fallback: mai scanăm după 2s (pentru lazy-render)
    setTimeout(() => {
      scanCards();
      injectDashPanel();
    }, 2000);

    // Re-scan la navigare tab
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-tab],[onclick*="showTab"],[onclick*="sec-"]');
      if (btn) scheduleScan(300);
    });
  }

  // ============================================================
  // INIT
  // ============================================================

  function init() {
    injectCSS();
    loadData();
    log('strength_panel_ui v' + SP_VERSION + ' init');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    // DOM gata — aşteptăm un tick pentru a fi siguri că restul script-urilor au rulat
    setTimeout(init, 0);
  }

  // API public pentru debugging
  window.SP_UI = { data: () => sp, scan: scanCards, version: SP_VERSION };

})();
