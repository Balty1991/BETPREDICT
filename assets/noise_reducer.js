/*
 * noise_reducer.js — reduce zgomotul vizual din lista de predicții.
 * Estompează cardurile cu date puține (steluțe de încredere <= prag), ca să nu
 * pui aceeași bază pe ele ca pe cele cu date fiabile. Nu le ascunde — rămân
 * vizibile pentru explorare, doar sunt vizual retrase.
 *
 * Nu necesită build React: se agață de aria-label-ul steluțelor
 * ("N din 5 stele încredere") pe care le randează deja EventListCard.
 * Se încarcă din index.html ca <script src="assets/noise_reducer.js">.
 */
(function () {
  'use strict';

  // Carduri cu ACEST număr de stele sau mai puțin = "date puține" -> estompate.
  // 1 stea = scor <25, 2 stele = 25-40 (vezi confStars din EventListCard).
  var STAR_THRESHOLD = 2;
  var DIM_OPACITY = '0.42';
  var DIM_GRAYSCALE = '0.35';
  var MARK = 'data-noise-dimmed';

  function starCountFrom(el) {
    var lbl = el.getAttribute('aria-label') || '';
    var m = lbl.match(/(\d+)\s*din\s*5/i);
    return m ? parseInt(m[1], 10) : null;
  }

  // Găsește containerul cardului pornind de la span-ul cu steluțe.
  function cardFor(starEl) {
    try {
      var c = starEl.closest('[class*="rounded-[26px]"]');
      if (c) return c.parentElement || c;
    } catch (e) { /* selector cu paranteze nesuportat -> fallback */ }
    var el = starEl, hops = 0;
    while (el && el.parentElement && hops < 8) {
      el = el.parentElement; hops++;
      var cls = el.className ? String(el.className) : '';
      if (cls.indexOf('rounded') > -1) return el;
    }
    return starEl.parentElement || starEl;
  }

  function dim(card) {
    if (card.getAttribute(MARK) === '1') return;
    card.setAttribute(MARK, '1');
    card.style.opacity = DIM_OPACITY;
    card.style.filter = 'grayscale(' + DIM_GRAYSCALE + ')';
    card.style.transition = 'opacity .2s ease, filter .2s ease';
  }

  function undim(card) {
    if (card.getAttribute(MARK) !== '1') return;
    card.removeAttribute(MARK);
    card.style.opacity = '';
    card.style.filter = '';
  }

  function apply() {
    var stars = document.querySelectorAll('[aria-label*="din 5 stele"]');
    for (var i = 0; i < stars.length; i++) {
      var n = starCountFrom(stars[i]);
      if (n == null) continue;
      var card = cardFor(stars[i]);
      if (!card) continue;
      if (n <= STAR_THRESHOLD) dim(card);
      else undim(card); // dacă un card urcă peste prag, îl readucem la normal
    }
  }

  var scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(function () { scheduled = false; apply(); });
  }

  function init() {
    apply();
    try {
      var obs = new MutationObserver(schedule);
      obs.observe(document.body, { childList: true, subtree: true });
    } catch (e) { /* fallback: reaplicare periodică */ setInterval(apply, 1500); }
    window.addEventListener('scroll', schedule, { passive: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
