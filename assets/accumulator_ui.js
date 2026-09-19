/**
 * accumulator_ui.js — loader for readable part slices (Fetch Daily empty-state + diagnosis).
 */
(function () {
  "use strict";
  var parts = [
    "assets/accumulator_ui.part00.js?v=v8.1",
    "assets/accumulator_ui.part01.js?v=v8.1"
  ];
  Promise.all(parts.map(function (u) {
    return fetch(u, { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("acc ui part HTTP " + r.status + " " + u);
      return r.text();
    });
  })).then(function (texts) {
    var code = texts.join("");
    var s = document.createElement("script");
    s.textContent = code;
    document.head.appendChild(s);
  }).catch(function (err) {
    console.error("[AccumulatorUI] failed to load parts", err);
  });
})();
