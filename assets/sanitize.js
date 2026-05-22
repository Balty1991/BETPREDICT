/*
 * sanitize.js – validare şi sanitizare a datelor
 *
 * În urma recomandărilor din audit este important să se verifice
 * existenţa şi tipul variabilelor esenţiale înainte de a fi afişate
 * în interfaţă. Acest modul expune funcţia globală
 * `sanitizeSignalsData` care filtrează şi normalizează semnalele
 * provenite din `data/signals.json`. Se elimină intrările cu
 * câmpuri lipsă sau non-numerice şi se corectează valori care ies
 * din intervalele acceptabile.
 */
(function() {
  'use strict';

  /**
   * Verifică dacă o valoare poate fi convertită în număr.
   * @param {any} n
   * @returns {boolean}
   */
  function isNumber(n) {
    return n !== null && n !== undefined && !isNaN(Number(n));
  }

  /**
   * Normalizează o proprietate numerică: converteşte la număr şi
   * aplică limita inferioară/superioară dacă este furnizată.
   * @param {any} val
   * @param {number|null} min
   * @param {number|null} max
   * @returns {number}
   */
  function normalize(val, min = null, max = null) {
    let num = Number(val);
    if (!Number.isFinite(num)) num = 0;
    if (min !== null && num < min) num = min;
    if (max !== null && num > max) num = max;
    return num;
  }

  /**
   * Sanitizează structura `signals.json`. Se aşteaptă un obiect cu
   * proprietatea `signals` ca listă. Intrările care nu au
   * `adj_prob`, `odds` şi `ev_pct` numerice sunt eliminate. 
   * Proprietăţile valide sunt convertite la numere şi limitate.
   * @param {Object} data
   * @returns {Object}
   */
  function sanitizeSignalsData(data) {
    if (!data || !Array.isArray(data.signals)) return data;
    // filtrăm şi normalizăm fiecare semnal
    const cleaned = [];
    for (const sig of data.signals) {
      if (!isNumber(sig.adj_prob) || !isNumber(sig.odds) || !isNumber(sig.ev_pct)) {
        continue; // omit invalid entry
      }
      const cleanSig = Object.assign({}, sig);
      cleanSig.adj_prob = normalize(cleanSig.adj_prob, 0, 100);
      cleanSig.odds     = normalize(cleanSig.odds, 1, null);
      cleanSig.ev_pct   = normalize(cleanSig.ev_pct, -100, 100);
      // edge_pp poate lipsi sau fi non-numeric – setăm 0 ca default
      if (!isNumber(cleanSig.edge_pp)) cleanSig.edge_pp = 0;
      cleaned.push(cleanSig);
    }
    // înlocuim lista originală doar dacă există modificări
    data.signals = cleaned;
    return data;
  }

  // expune funcţia la nivel global
  window.sanitizeSignalsData = sanitizeSignalsData;
})();