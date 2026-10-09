# BETPREDICT 3.0 — Contractul de date (JSON publicat pentru site)

> Versiune contract: **v1** (`schema` din fiecare fișier). Sursa: pachetul Python `betpredict/`
> rulat în GitHub Actions. Site-ul (React, gh-pages) **doar citește** aceste fișiere statice.
> Browserul nu apelează niciodată API-ul BSD autentificat și nu are cheia.

Toate căile sunt relative la rădăcina site-ului (ex. `./api/days/2026-10-09.json`).
Câmpurile marcate `?` pot lipsi sau fi `null`. Orele sunt **UTC ISO-8601** (`...Z`);
„ziua” (`date`) este **ziua din România** (Europe/Bucharest). Probabilitățile sunt **0–1**,
cotele sunt **zecimale**. Toate fișierele au `schema` și `generated_at`.

## 0. Index

| Fișier | Conținut | Actualizare |
|---|---|---|
| `api/meta.json` | stare pipeline, versiune model, cotă API rămasă, ziua curentă | la fiecare rulare |
| `api/days/index.json` | lista zilelor disponibile | la fiecare rulare |
| `api/days/<YYYY-MM-DD>.json` | toate meciurile zilei + predicțiile Robotului + context + rezultate | orar (ziua curentă, ±2 zile), la decontare |
| `api/tickets/<YYYY-MM-DD>.json` | biletele Robotului (~50/~100/~500+, variante) pentru zi | 03:15 RO + decontare |
| `api/tickets/today.json` | copie a zilei curente | idem |
| `api/tickets/history.json` | ultimele 90 de zile de bilete (fără detalii de context) | la decontare |
| `api/pyramid/state.json` | propunerea zilei ~2.00 (sau „AZI NU”), alternative, run curent, istoric | 03:15 RO + decontare |
| `api/stats/summary.json` | sumar, pe piață/ligă/cotă/grad/pagină, bilete, piramidă, recomandări | la decontare |
| `api/stats/daily.json` | serie pe zile | la decontare |
| `api/stats/monthly.json` | serie pe luni | la decontare |
| `api/stats/calibration.json` | diagrame de calibrare pe piață + ECE | la decontare |
| `api/stats/learning.json` | „Ce a învățat Robotul” + raport walk-forward | săptămânal (luni) |

Datele vechi din `./data/*.json` rămân publicate pentru UI-ul actual până la migrarea completă.

## 1. Tipuri comune

### Market / selecție
| `market` | `line` | `selection` | Etichetă (RO) |
|---|---|---|---|
| `1x2` | `null` | `HOME` / `DRAW` / `AWAY` | 1 / X / 2 |
| `double_chance` | `null` | `1X` / `12` / `X2` | 1X / 12 / X2 |
| `draw_no_bet` | `null` | `HOME` / `AWAY` | DNB 1 / DNB 2 |
| `over_under` | `0.5`…`4.5` | `OVER` / `UNDER` | Peste/Sub 2.5 |
| `btts` | `null` | `YES` / `NO` | GG / NG |

Cheia compactă a unei piețe (folosită în dicționare `odds` / probabilități): `1x2`,
`double_chance`, `draw_no_bet`, `btts`, `over_under_2.5` (piață + `_` + linie, fără zerouri inutile).

### `Team`
```json
{ "id": 42, "name": "Arsenal", "logo": "https://sports.bzzoiro.com/img/team/42/" }
```

### `League`
```json
{ "id": 17, "name": "Premier League", "country": "England", "logo": "https://sports.bzzoiro.com/img/league/17/" }
```

### `Prediction` (unitatea jurnalului — salvată în DB **înainte** de publicare)
```json
{
  "id": 123456,                       // id stabil din DB; cheie pentru „+ bilet” și statistici
  "match_id": 215479,
  "market": "over_under", "line": 2.5, "selection": "OVER",
  "label": "Peste 2.5",               // etichetă RO gata de afișat
  "p": 0.612,                         // probabilitatea finală (calibrată) a Robotului
  "p_model": 0.598,                   // Dixon-Coles/ELO înainte de blend/calibrare
  "p_bsd": 0.57,                      // ? probabilitatea BSD
  "p_market": 0.55,                   // ? probabilitate no-vig din cota de consens
  "odds": 1.82,                       // cota afișată (≥ min_odds); null dacă nu există cotă
  "odds_source": "bsd_consensus",
  "fair_odds": 1.63,                  // 1/p
  "edge": 0.063,                      // p − 1/odds
  "ev": 0.114,                        // p·odds − 1
  "value": true,                      // ev > 0
  "grade": "A",                       // A/B/C/D (încredere combinată: p, acord surse, calitate ligă, calibrare)
  "confidence": 78,                   // 0–100
  "is_pick": true,                    // predicția principală a meciului (max. 1 pe meci)
  "market_healthy": true,             // piața are calibrare bună (altfel nu intră în bilete)
  "reasons": ["Forma gazdelor: 2.3 pct/meci (ultimele 10)", "H2H: 4/5 meciuri peste 2.5"],
  "result": null,                     // null (în așteptare) | "won" | "lost" | "void" | "half_won" | "half_lost"
  "profit": null,                     // profit la 1 unitate după decontare
  "model_version": "robot-v1",
  "created_at": "2026-10-09T00:16:02Z"
}
```

## 2. `api/days/<date>.json`
```json
{
  "schema": "betpredict.day.v1",
  "date": "2026-10-09", "timezone": "Europe/Bucharest",
  "generated_at": "...", "model_version": "robot-v1",
  "min_odds": 1.15, "odds_source": "bsd_consensus",
  "count": 214,
  "markets": ["1x2","double_chance","draw_no_bet","over_under_1.5","over_under_2.5","over_under_3.5","btts"],
  "matches": [ Match, ... ]           // sortate după kickoff
}
```

### `Match`
```json
{
  "id": 215479,
  "kickoff_utc": "2026-10-09T18:45:00Z",
  "status": "notstarted",            // notstarted | inprogress | 1st_half | 2nd_half | finished | postponed | cancelled | unresolved ...
  "league": League, "home": Team, "away": Team,
  "round": "Regular season · Matchday 8",
  "score": { "ft": [2, 1], "ht": [1, 0] },      // ? doar după start
  "odds": { "1x2": {"HOME": 1.85, "DRAW": 3.6, "AWAY": 4.2}, "over_under_2.5": {"OVER": 1.9, "UNDER": 1.9} },
  "odds_movement": { "1x2": {"HOME": {"open": 1.95, "now": 1.85, "dir": "SHORTENING"}} },  // ?
  "bsd_probabilities": { "1x2": {"HOME": 0.48, "DRAW": 0.27, "AWAY": 0.25} },
  "model": {                          // ? matricea Robotului
    "lambda_home": 1.62, "lambda_away": 1.05,
    "elo_home": 1612, "elo_away": 1540,
    "most_likely_score": "1-0",
    "top_scores": [{"score": "1-0", "p": 0.12}]
  },
  "context": {                        // ? tot ce s-a putut colecta (Free plan)
    "form": { "home": Form, "away": Form },
    "h2h": { "total": 12, "home_wins": 5, "draws": 4, "away_wins": 3, "avg_goals": 2.6,
             "over25_rate": 0.58, "btts_rate": 0.5,
             "recent": [{"date": "2025-03-01", "home": "A", "away": "B", "score": "2-1"}] },
    "standings": { "home": {"position": 3, "points": 18, "played": 8}, "away": {"position": 11, "points": 9, "played": 8}, "zone_home": "ucl", "zone_away": null },
    "absences": { "home": [{"player": "X", "status": "injured", "return": "2026-10-20"}], "away": [] }
  },
  "predictions": [ Prediction, ... ], // toate piețele cu cotă ≥ min_odds (sau fără cotă), sortate după grad/p
  "pick_id": 123456                   // ? id-ul predicției principale
}
```

### `Form`
```json
{ "last": 10, "played": 10, "w": 6, "d": 2, "l": 2, "gf": 18, "ga": 9, "ppm": 2.0, "sequence": "WWDLW",
  "venue": { "played": 5, "ppm": 2.4 } }
```

## 3. `api/tickets/<date>.json` (și `today.json`)
```json
{
  "schema": "betpredict.tickets.v1",
  "date": "2026-10-09", "generated_at": "...",
  "targets": [50, 100, 500],
  "tickets": [ Ticket, ... ],
  "notes": ["Bilet de cotă ~100: șansă realistă ~1%."]
}
```

### `Ticket`
```json
{
  "id": 9012,
  "kind": "acca_100",                 // acca_50 | acca_100 | acca_500 | pyramid
  "variant": "echilibrat",            // echilibrat | valoare | ancora_surpriza | goluri | principal | alternativa
  "variant_label": "Echilibrat",
  "created_by": "robot",
  "date": "2026-10-09", "created_at": "...",
  "target_odds": 100, "total_odds": 104.3,
  "p_ticket": 0.0112,                 // probabilitatea estimată (cu penalizare de corelație)
  "ev": 0.168,                        // p_ticket·total_odds − 1
  "status": "pending",                // pending | won | lost | void
  "settled_legs": 3, "legs_count": 9,
  "effective_odds": 104.3,            // după void-uri (cota pe void = 1.00)
  "legs": [ {
      "prediction_id": 123456, "match_id": 215479,
      "kickoff_utc": "...", "league": "Premier League",
      "home": "Arsenal", "away": "Chelsea",
      "market": "1x2", "line": null, "selection": "HOME", "label": "1",
      "odds": 1.85, "p": 0.6, "grade": "A",
      "result": null,                 // null | won | lost | void | half_won | half_lost
      "score": "2-1"                  // ? după final
  } ],
  "reasons": ["Probabilitate maximă la cota-țintă", "9 ligi diferite"]
}
```

## 4. `api/tickets/history.json`
```json
{ "schema": "betpredict.tickets_history.v1", "generated_at": "...",
  "tickets": [ Ticket fără `reasons` ] }   // ultimele 90 de zile, cele mai noi primele
```

## 5. `api/pyramid/state.json`
```json
{
  "schema": "betpredict.pyramid.v1", "generated_at": "...", "date": "2026-10-09",
  "rules": { "target_odds": 2.0, "band": [1.85, 2.2], "max_legs": 4, "min_p": 0.5, "min_ev": -0.03,
             "start_bank": 100, "withdraw_steps": [3, 5, 7], "withdraw_pct": 0.3,
             "target_multiple": 8, "target_withdraw_pct": 0.5 },
  "today": {
    "status": "pick",                 // pick | no_bet
    "reason": "Combinație p=0.56, EV=+3%",   // pentru no_bet: de ce „AZI NU”
    "main": Ticket,                   // ? kind = pyramid, variant = principal
    "alternatives": [ Ticket ]        // 0–2, variant = alternativa
  },
  "run": {                            // run-ul curent (paper, cu regulile implicite)
    "id": 3, "start_date": "2026-10-05", "status": "active",
    "step": 2, "bank": 392.0, "start_bank": 100, "withdrawn": 0.0
  },
  "history": [ { "date": "2026-10-08", "ticket_id": 9000, "odds": 1.98, "p": 0.55,
                 "result": "won", "status": "pick" } ],   // ultimele 120 de zile, inclusiv zilele no_bet
  "runs": [ { "id": 2, "start_date": "...", "end_date": "...", "steps": 4, "max_bank": 1500, "withdrawn": 330, "status": "lost" } ],
  "reach_probability": [ {"step": 1, "p": 0.55}, {"step": 2, "p": 0.3} ]   // din rezultatele reale ale piramidei
}
```
Frontend-ul poate recalcula banca cu setările utilizatorului folosind `history` (rezultate pe zi).

## 6. `api/stats/summary.json`
```json
{
  "schema": "betpredict.stats.v1", "generated_at": "...",
  "scope": "robot",                   // doar predicțiile Robotului (nu cele legacy)
  "overall": { "n": 1200, "won": 700, "lost": 480, "void": 20, "pending": 85,
               "win_rate": 0.593, "roi_pct": -1.2, "profit": -14.4,
               "avg_odds": 1.74, "avg_p": 0.61, "brier": 0.231, "logloss": 0.65 },
  "picks": { ...aceleași câmpuri, doar `is_pick` },
  "value": { ...aceleași câmpuri, doar `value` = true },
  "by_market":   [ { "key": "over_under_2.5", ...câmpuri overall } ],
  "by_league":   [ { "key": "17", "name": "Premier League", ... } ],   // top 40 după n
  "by_odds_band":[ { "key": "1.15-1.30", ... } ],
  "by_grade":    [ { "key": "A", ... } ],
  "by_p_band":   [ { "key": "0.60-0.70", ... } ],
  "tickets": [ { "kind": "acca_100", "variant": "echilibrat", "n": 20, "won": 0, "lost": 19, "void": 0, "pending": 1, "roi_pct": -100.0, "profit": -19.0 } ],
  "pyramid": { "days": 30, "picks": 22, "no_bet": 8, "won": 12, "lost": 10, "win_rate": 0.545, "runs": 6, "best_step": 4 },
  "legacy": { "n": 500, "win_rate": 0.68, "roi_pct": -1.73 },        // jurnalul vechi, pentru comparație
  "recommendations": [ { "severity": "warn", "text": "Over 2.5: ECE 0.14 pe n=86 → exclus din bilete.", "evidence": {"n": 86, "ece": 0.14} } ]
}
```

## 7. `api/stats/daily.json` / `monthly.json`
```json
{ "schema": "betpredict.stats_series.v1", "generated_at": "...",
  "rows": [ { "key": "2026-10-08", "n": 210, "won": 120, "lost": 85, "void": 5,
              "win_rate": 0.585, "roi_pct": -2.1, "profit": -4.4,
              "picks": { "n": 40, "won": 26, "roi_pct": 3.2 },
              "tickets": { "n": 12, "won": 1, "profit": 41.0 } } ] }
```

## 8. `api/stats/calibration.json`
```json
{ "schema": "betpredict.calibration.v1", "generated_at": "...",
  "markets": [ { "key": "1x2", "n": 900, "ece": 0.031, "healthy": true,
                 "bins": [ { "lo": 0.5, "hi": 0.6, "n": 120, "p_avg": 0.55, "hit_rate": 0.57 } ] } ] }
```

## 9. `api/stats/learning.json`
```json
{ "schema": "betpredict.learning.v1", "generated_at": "...",
  "model": { "version": "robot-v1", "trained_at": "...", "matches": 61234, "half_life_days": 180 },
  "walk_forward": [ { "fold": "2026-08", "n": 3100, "logloss_1x2": 0.98, "baseline_1x2": 1.05,
                      "logloss_ou25": 0.68, "baseline_ou25": 0.69 } ],
  "params": { "blend": { "1x2": { "model": 0.35, "bsd": 0.2, "market": 0.45 } },
              "excluded_markets": ["btts"], "league_penalty": { "123": 0.8 } },
  "log": [ { "run_at": "...", "change_type": "blend_weights", "market": "1x2",
             "before": "...", "after": "...", "evidence": {"n": 600} } ]
}
```

## 10. `api/meta.json`
```json
{ "schema": "betpredict.meta.v1", "generated_at": "...", "day": "2026-10-09",
  "model_version": "robot-v1", "app_version": "3.0.0a0",
  "status": "ok",                     // ok | degraded (cota API aproape epuizată / pas eșuat) | stale
  "quota": { "effective_remaining": 4100, "daily_quota": 7500, "exhausted": false },
  "last_steps": { "daily": "...", "refresh": "...", "settle": "...", "learn": "..." },
  "warnings": [] }
```

## Reguli
- Cota minimă afișată/folosită în bilete: `min_odds` (1.15). Predicțiile fără cotă apar cu `odds: null`, nu intră în bilete.
- O predicție publicată nu dispare: după kickoff este înghețată; doar `result`/`profit` se completează.
- Contract stabil: câmpuri noi se pot adăuga; câmpurile existente nu se redenumesc fără `schema` nou.
