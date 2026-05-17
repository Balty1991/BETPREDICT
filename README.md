# ⚽ BetPredict Pro

Platformă de analiză sportivă cu predicții ML, value bets și scoruri live.
Găzduire gratuită pe **GitHub Pages** · Date din **BSD API v2** · Zero costuri de server.

---

## 🚀 Setup în 5 pași

### 1. Creează repository-ul GitHub

```
betpredict-pro/   ← numele repo
```
- Go to github.com → New repository
- Name: `betpredict-pro` (sau orice altceva)
- **Public** (necesar pentru GitHub Pages gratuit)
- Upload toate fișierele din acest arhiv

---

### 2. Adaugă API Key în GitHub Secrets

1. Mergi la repo → **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `BSD_API_KEY`
4. Value: cheia ta de la [sports.bzzoiro.com](https://sports.bzzoiro.com)
5. Click **Add secret**

> **Obține API key gratuit** de la: https://sports.bzzoiro.com/dashboard/

---

### 3. Activează GitHub Pages

1. Settings → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` → folder: `/ (root)`
4. Save

Site-ul va fi disponibil la: `https://USERNAME.github.io/betpredict-pro/`

---

### 4. Rulează primul fetch manual

1. Actions → **📊 Fetch Daily Data** → **Run workflow**
2. Așteptați ~30 secunde
3. Verifică că fișierele din `data/` au fost actualizate

---

### 5. Verifică workflows-urile automate

| Workflow | Frecvență | Ce face |
|---|---|---|
| `fetch_daily.yml` | Zilnic 06:00 | Predicții, meciuri, cote, clasamente, value bets |
| `fetch_live.yml` | La 5 minute | Scoruri live |

> ⚠️ GitHub Actions cron poate întârzia până la 10 minute față de ora setată.

---

## 📁 Structura proiectului

```
betpredict-pro/
├── .github/
│   └── workflows/
│       ├── fetch_daily.yml     # Daily data pipeline
│       └── fetch_live.yml      # Live scores (every 5 min)
├── data/
│   ├── predictions.json        # ML predictions (CatBoost)
│   ├── matches_today.json      # Today's matches
│   ├── live.json               # Live scores
│   ├── best_odds.json          # Best odds per bookmaker
│   ├── value_bets.json         # Calculated EV+ opportunities
│   └── standings.json          # League tables
├── src/
│   ├── fetch_daily.py          # Main data fetcher
│   └── fetch_live.py           # Live scores fetcher
├── index.html                  # SPA Frontend
└── README.md
```

---

## ⚙️ Configurare ligi urmărite

Editează `src/fetch_daily.py`, secțiunea `LEAGUES`:

```python
LEAGUES = {
    23: "Superliga României",   # ← Adaugă/șterge ligi după preferință
    1:  "Premier League",
    7:  "Champions League",
    3:  "La Liga",
    4:  "Serie A",
    5:  "Bundesliga",
    6:  "Ligue 1",
    # ... adaugă orice ligă din lista BSD
}
```

**ID-uri ligi disponibile** (BSD API):
| ID | Ligă | Țară |
|---|---|---|
| 1 | Premier League | England |
| 2 | Liga Portugal | Portugal |
| 3 | La Liga | Spain |
| 4 | Serie A | Italy |
| 5 | Bundesliga | Germany |
| 6 | Ligue 1 | France |
| 7 | Champions League | Europe |
| 8 | Europa League | Europe |
| 10 | Eredivisie | Netherlands |
| 23 | Superliga | Romania |
| 27 | World Cup 2026 | International |

---

## 📊 Tabs aplicație

| Tab | Conținut |
|---|---|
| **⚽ Azi** | Predicții ML pentru meciurile de azi: 1X2, xG, BTTS, O2.5, Confidence |
| **🔴 Live** | Scoruri live cu xG, posesie, șuturi, goluri/cartonașe |
| **💎 Value** | Value Bets sortate după EV: probabilitate, cotă best, Kelly fraction |
| **🏆 Top** | Clasamente top 8 echipe per ligă |

---

## 💡 Formule de calcul

### Expected Value (EV)
```
EV = (probabilitate_ML × cota_best) − 1
Threshold: EV > 5%
```

### Kelly Criterion (fracție din bankroll)
```
Kelly = (prob × odd − 1) / (odd − 1)
Limitat la max 25% per pariu (anti-overbet)
```

---

## 🔧 Troubleshooting

**GitHub Actions nu rulează?**
- Verifică că `BSD_API_KEY` e setat în Secrets
- Mergi la Actions → Enable workflows (dacă sunt dezactivate)

**`data/predictions.json` rămâne gol?**
- Rulează manual: `python src/fetch_daily.py` (cu `BSD_API_KEY` setat în mediu)
- Verifică output-ul pentru erori 401/403

**Frontend arată "—" pretutindeni?**
- Asigură-te că fișierele din `data/` au structura corectă
- Deschide DevTools → Console pentru erori

---

## 📱 PWA (opțional)

Pentru a adăuga pe Home Screen Android, adaugă în `<head>` din `index.html`:
```html
<link rel="manifest" href="manifest.json">
```
Și creează `manifest.json` — la cerere.

---

## 📄 Licență

Proiect personal pentru uz educațional. Pariurile sportive implică riscuri financiare.
