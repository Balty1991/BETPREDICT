# 🔍 Audit complet BetPredict + Plan strategie v7

**Data:** 2026-07-17 · **Autor:** analiză tehnică · **Scope:** întreaga platformă, cu focus pe motorul de predicții și profitabilitate reală.

---

## 0. Rezumat executiv (verdictul în 6 rânduri)

Platforma este **impresionantă ca inginerie** (50+ module, 90+ fișiere de date, pipeline orar pe GitHub Actions, date foarte bogate: 17 bookmakeri, xG, shotmap, lineup, arbitri, Polymarket). **Dar din punct de vedere al profitului, dovezile reale spun clar: nu are edge.**

| Metrică reală (din datele tale) | Valoare | Ce înseamnă |
|---|---|---|
| ROI global (36 pariuri settle-uite) | **−8.2%** | Pierdere netă |
| AUC mediu modele ML | **0.583** | Aproape ghicire (0.5 = monedă) |
| CLV mediu (417 picks) | **−1.35%** | **Piața te bate constant** |
| Beat rate vs. cota de închidere | **33.3%** | Sub jumătate = fără edge |
| Îmbunătățire v6 *out-of-sample* | **+0.0 pp** | Calibrarea nu aduce nimic real |

**Concluzia cheie:** problema nu e "mai multă calibrare / mai multe modele". Problema e **paradigma**: încerci să *prezici mai bine decât piața* cu un model slab. Soluția profitabilă e să **recoltezi edge-ul care există deja în datele tale** (prețul sharp Pinnacle, mișcarea cotelor, arbitrajele între 17 bookmakeri). Am construit și rulat un prototip care face exact asta: `src/sharp_value_engine.py` → a găsit deja **10 value bets, 99 semnale steam și 2 arbitraje garantate** pe datele de azi.

---

## 1. Cum funcționează predicțiile ACUM (arhitectura reală)

```
BSD API v2 ──► fetch_daily.py ──► predictions.json (BSD + Poisson/Dixon-Coles)
                                        │
        ┌───────────────────────────────┤
        ▼                               ▼
   ml_ensemble.py                 value_bets.py
   (CatBoost+LGBM+sklearn+Poisson) (edge = model_prob − market_prob)
        │                               │
        ▼                               ▼
   calibration_engine.py (Isotonic/Shift per market)
        ▼
   adaptive_thresholds.py (praguri din ROI istoric)
        ▼
   consensus_engine.py (acord BSD/ML/Poisson)
        ▼
   compute_signals_v6.py ──► signals.json / signals_v6.json ──► Frontend (6 taburi)
```

**Cum se calculează un pariu "value" azi:**
1. Se estimează o probabilitate a modelului (`model_probability`) din BSD + Poisson + ML.
2. Se compară cu probabilitatea implicită a cotei (`market_probability = 1/cotă` de-vig-uit).
3. `edge = model_prob − market_prob`. Dacă edge > prag → semnal value.
4. Se aplică calibrare (Isotonic), scor SmartBet, grad A+/A/B, Kelly.

**Problema fundamentală a acestui flux:** pasul 1 presupune că modelul tău știe adevărul mai bine decât piața. Datele arată că **nu** (AUC 0.583, CLV −1.35%). Deci "edge"-ul calculat la pasul 3 este în mare parte **iluzoriu** — e diferența dintre un model prost și o piață eficientă, nu o oportunitate.

---

## 2. Auditul brutal — cu dovezi din propriile date

### 2.1 🔴 Modelele ML sunt aproape random
- `avg_auc = 0.583` pe 942 sample-uri de antrenare. Un AUC bun pentru fotbal e 0.65–0.75. 0.583 = model care abia depășește aruncatul monedei.
- Consecință: orice "probabilitate a modelului" pe care se bazează value bets are zgomot mare.

### 2.2 🔴 Stratul v6 (calibrare/consens/ensemble) nu aduce profit real
Din `v6_backtest_report.json`, testul **out-of-sample onest** (antrenat pe primele 21 pariuri, evaluat pe ultimele 15):

| | v5 | v6 |
|---|---|---|
| ROI | −24.93% | **−24.93%** |
| Win rate | 40.0% | 40.0% |
| Δ ROI | — | **+0.0 pp** |

Numărul din README care spune "v6 = +20.46% ROI, 69% win rate" este **in-sample** — calibratorii au fost antrenați chiar pe pariurile pe care sunt testați. Este **overfitting clasic**, nu performanță reală. Documentul chiar admite: *"OPTIMIST — calibratorii au fost antrenați pe aceste date."*

### 2.3 🔴 Calibrarea rulează pe eșantioane invalide statistic
`calibration_health.json`: toate cele 6 markete = `NO_DATA` (n între 4 și 8, prag minim 10). Totuși aceste calibratoare **downgradează 57 din 58 de semnale** (`v6_health → n_downgraded: 57, n_aplus: 0`). Practic o funcție antrenată pe 6 exemple decide agresiv asupra tuturor pariurilor. Asta e periculos: introduce bias, nu îl corectează.

### 2.4 🔴 CLV negativ = dovada finală că nu există edge
`clv_tracker.json`: `avg_clv_pct = −1.35%`, `market_beat_rate = 33.3%`, `proxy_warning = true`.
CLV (Closing Line Value) este **singurul indicator care prezice profitul pe termen lung**. Un jucător cu edge real bate cota de închidere >50% din timp și are CLV pozitiv. Tu ești la 33% și negativ → pe termen lung, pierdere garantată matematic.

### 2.5 🟠 Eșantion mult prea mic pentru orice concluzie
36 pariuri settle-uite. Toate segmentările ("by_market", "by_strategy") au `label: "sample mic"`. ROI-uri de tip "+21% veyra_engine" pe 4 pariuri sunt zgomot pur, nu strategie.

### 2.6 🟠 Complexitate care ascunde, nu ajută
90+ fișiere JSON, motoare care se suprapun (`supreme_engine_v5` = copie a `ev_signals_v2`; `predictions.json` 3.4MB; `v2_enrichment_cache.json` 12MB). Multă suprafață de întreținere, dar niciun modul nu produce edge dovedit. Bogăția de date (shotmap, lineup, arbitri) e colectată dar **nefolosită în decizia de pariere**.

### 2.7 🟢 Ce e bun și trebuie păstrat
- Infrastructura de colectare date (17 bookmakeri, Pinnacle, Polymarket, mișcare cote) — **aur nefolosit**.
- Pipeline orar automat, gratuit, atomic writes.
- `clv_tracker` și `risk_shield` (bankroll/circuit-breaker) — fundații bune.
- Poisson/Dixon-Coles corect implementat în `analytics_core.py`.

---

## 3. Cauza rădăcină: paradigma greșită

> **Azi:** "Modelul meu crede X% → dacă piața dă mai puțin, pariez." (predict-to-beat)
> **Problema:** modelul tău e mai slab decât piața. Pierzi.

> **Nou:** "Bookmaker-ul SHARP (Pinnacle) știe adevărul. Dacă un book SOFT greșește prețul în favoarea mea, pariez acolo." (harvest-the-edge)
> **De ce funcționează:** nu te bazezi pe predicția ta, ci pe **ineficiența dintre bookmakeri** — un edge dovedit statistic prin CLV pozitiv.

Aceasta este singura schimbare care contează. Restul planului derivă din ea.

---

## 4. 🚀 Strategia nouă unică: Sharp-Value Engine v7 (deja prototipată)

Am scris și rulat `src/sharp_value_engine.py` pe datele tale reale. Trei surse de profit, **toate independente de calitatea modelului tău**:

### Sursă 1 — SHARP-VALUE (nucleul profitului)
Pinnacle are marja cea mai mică și e cel mai eficient book din lume. De-vig-uind cotele Pinnacle obții **probabilitatea corectă**. Când un book soft (bet365, betano, 1xbet...) oferă o cotă mai mare decât cota corectă → **EV pozitiv real**, care se traduce în CLV pozitiv.

```
p_corect = no_vig(Pinnacle)
EV = p_corect × (cota_soft − 1) − (1 − p_corect)
Pariezi doar dacă EV ≥ 2% ȘI cota e proaspătă (< 15 min)
```

### Sursă 2 — STEAM / DROP
Când cota se scurtează (SHORTENING) la ≥4 bookmakeri simultan = banii sharp au intrat. Prinzi mișcarea la book-ul soft care încă nu s-a ajustat.

### Sursă 3 — ARBITRAJ / MIDDLE
Cu 17 bookmakeri, uneori `Σ(1/cea_mai_bună_cotă) < 1` → **profit garantat** indiferent de rezultat.

### 📊 Dovada pe datele de AZI (rulare reală, nu teorie)
```
32 evenimente scanate → 10 value bets (EV mediu 10.1%) | 99 steam | 2 ARBITRAJE
  ARB  Henan FC vs Qingdao Hainiu | over/under 1.5 | profit GARANTAT +2.98%
  ARB  Halmstads BK vs BK Häcken  | 1x2          | profit GARANTAT +0.50%
  VALUE Botev Vratsa vs Cherno More | DRAW | bet 2.85@bet365 vs corect 2.665 | EV +6.9% | STEAM
  VALUE Bolívar vs Grêmio | AWAY | bet 4.81@1xbet vs corect 4.50 | EV +7.0% | STEAM
```
Arbitrajele sunt **bani reali fără risc de model**. Value-urile confirmate de steam sunt cele mai fiabile.

> ⚠️ Filtru necesar în producție: EV-uri uriașe pe outsideri (ex: 35% pe cotă 7.0) sunt de obicei cote stale/erori de fresh — motorul le semnalează, dar trebuie plafonat EV la ~15% și verificat `updated_at` al cotei. Sweet-spot-ul real: EV 2–10% pe piețe lichide.

---

## 5. Plan de implementare pe faze (roadmap concret)

### Faza 1 — Fundația măsurării adevărate (săptămâna 1) 🎯 PRIORITATE MAXIMĂ
1. **CLV real, nu proxy.** Loghează cota la momentul pariului ȘI cota de închidere (Pinnacle) pentru fiecare selecție. Fără CLV real, nu știi niciodată dacă o strategie merge. `clv_tracker` există deja — trebuie hrănit cu closing odds reale din `best_odds.json`.
2. **Paper-trading log separat** pentru fiecare strategie (sharp-value / steam / arb), miză fixă 1u, ≥200 pariuri înainte de orice concluzie.

### Faza 2 — Integrarea Sharp-Value Engine (săptămâna 2)
3. Adaugă `sharp_value_engine.py` în `fetch_daily.yml` (după `compare_odds`). Deja rulează standalone.
4. Extinde inputul de la 32 evenimente prioritare la toate cele 551 din `best_odds.json` (pentru arbitraje mai ales — acolo e volum).
5. Tab UI nou "💰 SHARP" care arată: value bets vs. Pinnacle, steam alerts live, arbitraje cu calculator de mize.

### Faza 3 — Retragerea stratului iluzoriu (săptămâna 3)
6. **Oprește** downgrade-ul automat din calibrarea pe n<10 (introduce bias). Rulează calibrarea doar când n≥30 per market.
7. Repoziționează ML-ul: nu ca sursă de "probabilitate adevărată", ci ca **tiebreaker cu pondere mică** (max 15%) când sharp-value și ML sunt de acord.
8. Deduplică motoarele redundante (`supreme_engine_v5` ≡ `ev_signals_v2`).

### Faza 4 — Edge-uri avansate (luna 2+)
9. **Polymarket vs. bookmaker divergence:** când mulțimea sharp de pe Polymarket diferă >5pp de book-urile soft → semnal (ai deja `polymarket.json`).
10. **Micro-nișe ineficiente:** ligile mici (Australia, U19, ligi asiatice) au book-i soft mai des greșiți. Filtrează sharp-value pe ligi cu `market_depth` slab dar cu Pinnacle prezent.
11. **Referee/lineup edge pe Over/Under:** ai `referee_stats.json` (medii cartonașe/goluri per arbitru) și `lineup_intelligence.json`. Un arbitru cu medie mare de goluri + ambele echipe cu atac titular = edge specific pe Over, unde book-urile soft nu ajustează pentru arbitru.

---

## 6. Alte upgrade-uri de profitabilitate

| Upgrade | Impact | Efort |
|---|---|---|
| **Kelly fracționat pe CLV, nu pe edge model** | mizezi mai mult unde ai edge dovedit | mic |
| **Line shopping automat** (pariază mereu la cea mai bună cotă din 17) | +2–4% ROI "gratis" doar din cotă mai bună | mic |
| **Stop calibrare pe n<30** | elimină bias fals | mic |
| **Circuit breaker pe drawdown** (ai `risk_state.json`) | protejează bankroll-ul | există deja |
| **Backtest onest doar out-of-sample** ca standard | oprești auto-amăgirea | mediu |
| **Closing-line logging** | activează CLV real = busola ta | mediu |

---

## 7. Management de risc & realism (obligatoriu)

- **Nicio strategie nu e validă sub 200 de pariuri paper-traded cu CLV pozitiv.**
- Arbitrajul e cel mai sigur profit, dar: limite de miză la book-uri, conturi restricționate, cote care dispar în secunde. Realist: profit mic dar constant, necesită execuție rapidă.
- Sharp-value funcționează, dar book-urile soft îți limitează contul dacă câștigi constant. E un joc de volum + discreție.
- Fără avantaj de execuție (viteză, multiple conturi), edge-ul teoretic se erodează. Onestitate: aceasta e o platformă de *asistență la decizie*, nu o mașină de bani automată.

---

## 8. Următorul pas recomandat

**Cel mai mare ROI pe efort:** activează **CLV real (Faza 1)** + integrează **Sharp-Value Engine (Faza 2)**. Împreună îți dau, pentru prima dată, un edge *măsurabil* și *dovedit*, în loc de un scor SmartBet care arată bine dar pierde bani. Motorul e deja scris și testat — trebuie doar conectat la pipeline și la UI.

> Fișier livrat: `src/sharp_value_engine.py` (rulabil acum: `python3 src/sharp_value_engine.py`)
> Output: `data/sharp_value_signals.json`

---

## 9. ✅ Status implementare (livrat, testat)

Tot planul a fost implementat, integrat în pipeline și verificat end-to-end.

| Fază | Livrabil | Fișier | Status |
|---|---|---|---|
| **1** | CLV real logger + paper-trading ledger | `src/sharp_clv_logger.py` → `data/sharp_paper_trades.json` | ✅ rulează |
| **2** | Sharp-Value Engine v2 (value/steam/arbitraj/polymarket, 551 ev., filtre anti-zgomot) | `src/sharp_value_engine.py` → `data/sharp_value_signals.json` | ✅ 8 value, 3 arb |
| **3a** | Calibrare: prag shift 5→20 + shrinkage empiric-Bayes | `src/calibration_engine.py` | ✅ downgrade 60→0, A+ 0→14 |
| **3b** | ML repoziționat tiebreaker 50%→15% | `src/compute_signals_v6.py` | ✅ |
| **4** | Referee/formă Over-Under edge (merge 2 surse arbitri) | `src/referee_ou_edge.py` → `data/referee_ou_edge.json` | ✅ robust |
| **5a** | Integrare pipeline (3 pași noi + commit paths) | `.github/workflows/fetch_daily.yml` | ✅ |
| **5b** | UI overlay "💰 SHARP" (6 taburi) | `assets/sharp_ui.js` + `index.html` | ✅ browser-tested |
| — | Teste unitare noi (devig/arb/settle/index) | `tests/test_v7_sharp.py` | ✅ 48/48 green |

**Verificare cheie (măsurată, nu presupusă):** fix-ul de calibrare a transformat
`downgraded 60 → 0` și `A+ 0 → 14, A 0 → 20` — semnalele nu mai sunt distruse de
calibrare pe eșantioane invalide statistic. Suita de teste: 48/48. UI testat în
Chromium (buton flotant + drawer + toate taburile randează fără erori console).

### Cum evoluează de aici (fără intervenție)
Pipeline-ul rulează orar. La fiecare rulare:
- `sharp_clv_logger` acumulează CLV real (deschidere vs. închidere) — după ~100
  trade-uri settle-uite cu CLV pozitiv, strategia e **dovedită**, nu presupusă.
- calibratoarele rămân `identity` până la n≥20/market, apoi shift-ul cu shrinkage
  se activează gradual (fără șocuri de overfitting).
- arbitrajele și value bets apar/dispar dinamic în tabul SHARP.
