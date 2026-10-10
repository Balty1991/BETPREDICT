# Surse gratuite de statistici + bilete — cercetare 11.10.2026

| Sursă | Acces din GitHub Actions | Legal | Verdict |
|---|---|---|---|
| Club Elo (api.clubelo.com) | API nu răspunde (timeout; site-ul principal 200) | permis | amânat; avem deja ELO propriu reglat walk-forward |
| football-data.co.uk | CSV, gratuit | permis (atribuire) | deja integrat (cote deschidere/închidere, HT, cornere, cartonașe) — folosit aici pentru backtest |
| openfootball (GitHub) | da | CC0 | doar rezultate — dublură cu cele 222k meciuri din DB |
| StatsBomb open data | da | licență non-comercială | doar competiții/sezoane istorice selectate, nu acoperă meciurile curente |
| Open-Meteo (vreme) | da, fără cheie | non-comercial cu atribuire | necesită coordonatele stadionului (endpoint BSD de venue = cotă); amânat |
| FBref, Transfermarkt, Sofascore, FotMob | Cloudflare/API privat | ToS interzic scraping-ul | respinse |
| Arbitri | referee_stats.json (BSD) + football-data (Anglia/Scoția) | — | folosit la piața experimentală de cartonașe |
| Mișcarea cotelor (consens BSD, deschidere → acum) | deja în DB, fără cereri în plus | — | **adoptat** (vezi mai jos) |

## Mișcarea cotelor — backtest (football-data 2021/22–2026/27, cote 1.15–3, decizie la cota de închidere)
| Piață | Mișcare | n | ROI la cota medie |
|---|---|---|---|
| 1X2 | crește > 5% | 8,292 | −7.1% ± 1.2 |
| 1X2 | stabilă | 13,678 | −4.1% ± 0.9 |
| 1X2 | scade > 5% | 10,358 | −3.7% ± 1.0 |
| Peste/Sub 2.5 | crește > 5% | 12,033 | −8.7% ± 1.0 |
| Peste/Sub 2.5 | stabilă | 28,622 | −6.2% ± 0.6 |
| Peste/Sub 2.5 | scade > 5% | 9,802 | −3.0% ± 0.9 |

Jurnalul robotului 09–10.10 (cote ≤ 3): crește > 3% n=52 ROI −35%; stabilă n=1,234 −6%; scade n=65 +10%.
Regula: selecțiile cu cota de consens crescută > 5% de la deschidere nu mai sunt „sănătoase” → nu sunt recomandate și nu intră în bilete/piramidă.
Scăderea nu primește bonus (ROI tot negativ).

## Bilete (09–10.10, selecții decontate)
| Tip | selecții | câștigate | p mediu | ROI pe selecție |
|---|---|---|---|---|
| Loterie | 11 | 73% | 59% | +67% |
| Multi-zi | 21 | 62% | 54% | +19% |
| Sigur | 17 | 71% | 78% | −11% |
| Piramidă principal | 4 | 50% | 83% | −19% |

Loteria/multi-zi au pierdut din varianță (șansă bilet 0.2–4%), nu din selecții slabe: selecțiile au câștigat peste așteptări.
Filtrul testat (doar A/B, cotă ≤ 2.20) ar fi eliminat tocmai selecțiile mai bune (+54% vs +7%) → NEADOPTAT.
Sigur/piramidă: supraestimare pe Sub 4.5 la cote 1.15–1.36 → corectată în #107 (calibrarea cozilor).
football-data: favoriți 1.15–1.40 combinați fără edge pierd doar marja (−0.1…−4% pentru 1–10 selecții), deci biletele
sigure rămân informative (miză 0), iar jocul recomandat rămân biletele de valoare.
