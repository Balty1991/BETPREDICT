# Strategie Accumulator + Piramidă (v8)

## Scop
Maximizăm **valoarea așteptată (EV)** și disciplina de miză pe ce oferă deja BSD API + pipeline-ul ML v6 — **fără** a pretinde acuratețe falsă sau profit garantat.

## Ce generează pipeline-ul zilnic

| Fișier | Motor | Conținut |
|---|---|---|
| `data/accumulators.json` | `src/accumulator_engine.py` | Singles verzi + acca scurtă + benzi **50× / 100×+** |
| `data/claude_accumulators.json` | același motor (schema UI) | Compatibil cu tab-ul Accumulators existent |
| `data/pyramid_plans.json` | `src/pyramid_staking.py` | Scară de mize **2 → 5 → 10** cu reinvestment |
| `data/pyramid_assistant.json` | `src/pyramid_assistant.py` | Pool pe trepte (cotă ~1.30 / risc combo) |
| `data/pyramid_state.json` | `src/pyramid_tracker.py` | Tracker paper + regulă retragere |

## Filtre stricte (de ce)

Pentru **multi-leg** (acca / longshot):
1. **Grad A+ sau A** — un picior B înmulțește eroarea pe tot biletul.
2. **Consens TOTAL** (sau PARTIAL cu score ≥ 0.75) — dezacord BSD/ML = skip.
3. **`publication_eligible` + performance guard** — piețe cu ROI real negativ (ex. under35 pe n mare) sunt excluse.
4. **EV calibrat ≥ 0** pentru value; pentru longshot paper tolerăm ≥ −2%.
5. **Corelație**: 1 picior / meci, ≤1 ligă / bilet pe longshot.
6. **Cote Superbet** când matching-ul reușește (`executable: true`); altfel cote cross-book etichetate `paper_only` / non-executabile.

## Scară 2 → 5 → 10 (reinvestment)

```
Pas 1: miză 2 unități pe un pick „verde” (A+/A + consens, cotă ~1.25–1.55)
  WIN  → Pas 2: miză 5 unități pe ALT meci
  WIN  → Pas 3: miză 10 unități
  LOSS → STOP seria; revii la Pas 1. Nu „recupera” cu miză mai mare.
```

Plafoane:
- max **12%** din bancă pe un pas
- stop-loss serie ≈ **10 unități**
- status implicit: **PAPER_ONLY** până trackerul arată edge flat-stake

Compunerea pe trepte **nu creează edge** — doar reformulează variance-ul.  
P(ajungi la pasul N) ≈ (win-rate real)^N — vezi `series_survival_probability` în JSON.

## Accumulators 50–100+

Sunt etichetate **paper_only / LOTERIE**. Un singur picior greșit = bilet mort.  
Miza recomandată: simbolică (fracțiune din unitate), nu bankroll.

## Cum rulezi

1. Secret `BSD_API_KEY` în GitHub Actions (obligatoriu pentru date live).
2. Actions → **Fetch Daily Data** → Run workflow.
3. După rulare verifică:
   - `data/accumulators.json`
   - `data/pyramid_plans.json`
4. Pe site (GitHub Pages): butonul verde **🎫** (stânga jos) deschide panoul Accumulators / Scară.

Dry-run local (fără API):
```bash
python3 src/accumulator_engine.py --dry-run
python3 src/pyramid_staking.py --dry-run
python3 -m unittest tests.test_accumulator_engine -v
```

## Avertisment

Pariurile sportive implică **risc de pierdere a banilor**.  
Calibrarea și filtrele reduc greșelile sistematice; **nu elimină** variance-ul și nu garantează profit.
