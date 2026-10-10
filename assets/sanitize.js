/*
 * sanitize.js – validare şi sanitizare a datelor
 *
 * Strat intermediar care verifică existenţa şi tipul variabilelor
 * esenţiale înainte de randare în interfaţă. Elimină intrările cu
 * câmpuri lipsă, non-numerice sau cu EV negativ demonstrat.
 */
(function () {
  'use strict';

  function isNumber(n) {
    return n !== null && n !== undefined && !isNaN(Number(n));
  }

  function normalize(val, min, max) {
    let num = Number(val);
    if (!Number.isFinite(num)) num = 0;
    if (min !== null && min !== undefined && num < min) num = min;
    if (max !== null && max !== undefined && num > max) num = max;
    return num;
  }

  /**
   * Sanitizează signals.json.
   * Elimină intrările fără adj_prob, odds, ev_pct numerice.
   * Marchează selecţiile cu EV negativ cu flag _ev_negative.
   */
  function sanitizeSignalsData(data) {
    if (!data || !Array.isArray(data.signals)) return data;
    const cleaned = [];
    for (const sig of data.signals) {
      if (!isNumber(sig.adj_prob) || !isNumber(sig.odds)) continue;
      const s = Object.assign({}, sig);
      s.adj_prob = normalize(s.adj_prob, 0, 100);
      s.odds     = normalize(s.odds, 1.01, null);
      // ev_pct may arrive as a percentage string like '12.1%' — parse it but keep display string intact
      const evNum = parseFloat(String(s.ev_pct ?? '0').replace('%', ''));
      if (!isNumber(s.edge_pp)) s.edge_pp = 0;
      if (Number.isFinite(evNum) && evNum < 0) s._ev_negative = true;
      cleaned.push(s);
    }
    data.signals = cleaned;
    return data;
  }

  /**
   * Sanitizează predictions.json.
   * Elimină predicţiile cu probabilităţi invalide sau scor 0-0 fallback fals
   * (eveniment neînceput, mai mult de 5 minute în viitor).
   */
  function sanitizePredictionsData(data) {
    if (!data) return data;
    const arr = data.predictions || data.matches || data.results;
    if (!Array.isArray(arr)) return data;
    const now = Date.now();
    const cleaned = arr.filter(p => {
      if (!p) return false;
      if (!p.home_team && !p.event?.home_team) return false;
      if (!p.away_team && !p.event?.away_team) return false;
      const pH = Number(p.blended_home ?? p.home_win_probability ?? 0);
      const pD = Number(p.blended_draw ?? p.draw_probability ?? 0);
      const pA = Number(p.blended_away ?? p.away_win_probability ?? 0);
      if (pH > 0 || pD > 0 || pA > 0) {
        const sum = pH + pD + pA;
        if (sum < 0.5 || sum > 1.6) return false;
      }
      // Scor 0-0 ca fallback fals: eveniment neînceput dar scorul e 0-0
      const sc = String(p.score_prob || p.predicted_score || '').trim();
      if (/^0[-:]0$/.test(sc) && p.event_date) {
        try {
          if (new Date(p.event_date).getTime() > now + 300000) return false;
        } catch (_) {}
      }
      return true;
    });
    if (data.predictions) data.predictions = cleaned;
    else if (data.matches) data.matches = cleaned;
    else if (data.results) data.results = cleaned;
    return data;
  }

  /**
   * Sanitizează value_bets.json.
   * Elimină intrările fără cotă reală sau cu EV negativ.
   */
  function sanitizeValueBetsData(data) {
    if (!data) return data;
    const arr = data.value_bets || data.bets || data.results;
    if (!Array.isArray(arr)) return data;
    const cleaned = arr.filter(vb => {
      if (!vb) return false;
      const odds = Number(vb.odds ?? vb.best_odds ?? vb.market_odds ?? 0);
      if (!Number.isFinite(odds) || odds < 1.01) return false;
      if (isNumber(vb.ev_pct) && Number(vb.ev_pct) < 0) return false;
      if (!isNumber(vb.ev_pct) && isNumber(vb.edge_pp) && Number(vb.edge_pp) < 0) return false;
      return true;
    });
    if (data.value_bets) data.value_bets = cleaned;
    else if (data.bets) data.bets = cleaned;
    else if (data.results) data.results = cleaned;
    return data;
  }

  /**
   * Sanitizează recent_results.json.
   * Elimină rezultatele cu scoruri invalide sau evenimentele marcate
   * ca finalizate dar cu data în viitor (>2h).
   */
  function sanitizeResultsData(data) {
    if (!data || !Array.isArray(data.results)) return data;
    const now = Date.now();
    data.results = data.results.filter(r => {
      if (!r) return false;
      const hs = Number(r.home_score ?? r.home_goals ?? NaN);
      const as_ = Number(r.away_score ?? r.away_goals ?? NaN);
      if (!isNaN(hs) && (!Number.isFinite(hs) || hs < 0)) return false;
      if (!isNaN(as_) && (!Number.isFinite(as_) || as_ < 0)) return false;
      const finished = /finished|ft|ended/i.test(String(r.status ?? r.period ?? ''));
      if (finished && r.event_date) {
        try {
          if (new Date(r.event_date).getTime() > now + 7200000) return false;
        } catch (_) {}
      }
      return true;
    });
    return data;
  }

  window.sanitizeSignalsData     = sanitizeSignalsData;
  window.sanitizePredictionsData = sanitizePredictionsData;
  window.sanitizeValueBetsData   = sanitizeValueBetsData;
  window.sanitizeResultsData     = sanitizeResultsData;
})();
