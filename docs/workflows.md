# Workflow-uri GitHub Actions (v3)

| Workflow | Declanșare | Ora (Europe/Bucharest, EEST/EET) |
|---|---|---|
| `betpredict_v3.yml` daily | cron `15 0 * * *` | 03:15 vara / 02:15 iarna |
| `betpredict_v3.yml` refresh | cron `20 1-23 * * *` | la :20 în fiecare oră (fără 03:20 vara / 02:20 iarna, acoperit de daily) |
| `betpredict_v3.yml` learn | cron `45 3 * * 1` | luni 06:45 vara / 05:45 iarna |
| `ci.yml` | push pe main/`v3/**` (fără `data/**`, `models/**`), PR | — |
| `android-apk.yml` | push/PR pe `mobile/**` | — |
| `fetch_history_full.yml` | doar manual | rebuild `data/warehouse` (folosit de v3 la import istoric/backtest) |
| `cleanup.yml` | doar manual | șterge exclusiv `data/debug/*.json` > 7 zile; gardă care pică dacă ar atinge altceva |

Șterse la curățenia din 2026-10-09 (pipeline-ul v2 legacy, înlocuit de `betpredict_v3.yml`):
`claude_analysis.yml`, `predict_historical.yml`, `train_historical_weekly.yml`, `ml_train.yml`,
`fetch_daily.yml`, `fetch_v8_tickets.yml`, `superbet_recon.yml`. Scripturile din `src/` rămân în repo;
fișierele legacy din `data/` rămân înghețate (UI-ul le citește doar ca fallback).
