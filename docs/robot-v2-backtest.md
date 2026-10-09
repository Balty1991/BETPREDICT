# Robot v2 — backtest walk-forward

Generat: 2026-10-09T07:44:04Z · istoric 215,054 meciuri · evaluare OOS de la 2024-07-01 · reglaje pe 2023-07-01 → 2024-07-01 · durată 39 min.

Reproducere: `python -m betpredict backtest --db .betpredict/data.db --out backtest_v2.json` (`--quick` ≈ 7 min).

## Metodă (strict out-of-sample)

- Feature-uri secvențiale: starea de dinaintea fiecărui meci (ELO, forță EWMA general/teren, formă 5/10, odihnă, clasament din sezon, H2H, profil ligă, acoperire).
- Dixon-Coles re-estimat lunar doar pe trecut (avantaj de teren pe ligă, rho estimat, timp de înjumătățire reglat).
- LightGBM re-antrenat trimestrial pe ultimii 6 ani dinaintea foldului.
- Stacking + beta-calibrare re-estimate lunar doar pe predicțiile OOS anterioare; stacker-ul cu piața la fel (expanding).
- Pragurile adaptive se aleg doar din lunile anterioare.

Reglaje alese: ELO {'k': 14.0, 'home_adv': 60.0, 'margin': 0.6, 'new_team_offset': -60.0, 'regress': 0.2}, Dixon-Coles half-life 365 zile pe 3 ani.

## Problemă de date găsită: cote live în depozit

Cotele din `data/warehouse` pentru dec. 2025 – apr. 2026 sunt în mare parte capturate în timpul meciului (ex. Elveția–Germania 3-4 cu 1.09 la oaspeți, SUA–Belgia 2-5 cu 1.03). Logloss-ul 1X2 al pieței pe acele luni e 0.70–0.85 (imposibil pre-meci), din iunie 2026 revine la 0.96–0.99. ROI-ul și stacker-ul cu piața folosesc doar cotele din iunie 2026 încolo + filtru de plauzibilitate care nu se uită la rezultat. Rezultă doar 1,501 meciuri cu cote curate → ROI-ul are erori standard mari.

## Fără piață: iul. 2024 → oct. 2026 (v1 = robotul vechi, v2 = robotul nou)

Logloss / Brier / ECE (mai mic = mai bine).

| Piață | n | v1 | dc_v2 | gbm_raw | v2 |
|---|---|---|---|---|---|
| 1x2 | 35,973 | 1.0137 / 0.6073 / 0.013 | 1.0106 / 0.6052 / 0.003 | 0.9975 / 0.5959 / 0.009 | 0.9960 / 0.5951 / 0.005 |
| ou_1.5 | 35,973 | 0.5624 / 0.1878 / 0.028 | 0.5604 / 0.1872 / 0.022 | 0.5563 / 0.1858 / 0.006 | 0.5559 / 0.1856 / 0.004 |
| ou_2.5 | 35,973 | 0.6817 / 0.2440 / 0.032 | 0.6800 / 0.2432 / 0.029 | 0.6745 / 0.2409 / 0.009 | 0.6741 / 0.2406 / 0.007 |
| ou_3.5 | 35,973 | 0.5923 / 0.2019 / 0.027 | 0.5908 / 0.2013 / 0.024 | 0.5845 / 0.1988 / 0.006 | 0.5844 / 0.1988 / 0.005 |
| btts | 35,973 | 0.6939 / 0.2500 / 0.039 | 0.6928 / 0.2495 / 0.035 | 0.6852 / 0.2461 / 0.005 | 0.6850 / 0.2460 / 0.003 |
| dnb | 27,060 | 0.6082 / 0.2110 / 0.015 | 0.6061 / 0.2099 / 0.004 | 0.5879 / 0.2022 / 0.007 | 0.5880 / 0.2022 / 0.008 |
| double_chance | 35,973 | 0.5916 / 0.2024 / 0.013 | 0.5900 / 0.2017 / 0.003 | 0.5827 / 0.1986 / 0.009 | 0.5820 / 0.1984 / 0.005 |

## Cu piața: iun. → aug. 2026 (cote pre-meci curate)

Logloss / Brier / ECE (mai mic = mai bine).

| Piață | n | market | v1_market | v2 | v2_market |
|---|---|---|---|---|---|
| 1x2 | 1,501 | 0.9798 / 0.5832 / 0.018 | 0.9841 / 0.5853 / 0.020 | 1.0127 / 0.6051 / 0.019 | 0.9813 / 0.5841 / 0.012 |
| ou_1.5 | 1,501 | 0.5394 / 0.1781 / 0.013 | 0.5425 / 0.1794 / 0.016 | 0.5457 / 0.1805 / 0.020 | 0.5394 / 0.1782 / 0.018 |
| ou_2.5 | 1,501 | 0.6734 / 0.2403 / 0.019 | 0.6752 / 0.2412 / 0.029 | 0.6832 / 0.2449 / 0.046 | 0.6742 / 0.2407 / 0.022 |
| ou_3.5 | 1,501 | 0.6040 / 0.2078 / 0.032 | 0.6039 / 0.2078 / 0.038 | 0.6110 / 0.2110 / 0.027 | 0.6026 / 0.2072 / 0.028 |
| btts | 1,501 | 0.6810 / 0.2440 / 0.016 | 0.6809 / 0.2441 / 0.023 | 0.6824 / 0.2447 / 0.015 | 0.6800 / 0.2435 / 0.026 |
| dnb | 1,138 | 0.5692 / 0.1940 / 0.025 | 0.5728 / 0.1947 / 0.030 | 0.6062 / 0.2082 / 0.027 | 0.5705 / 0.1942 / 0.028 |
| double_chance | 1,501 | 0.5732 / 0.1944 / 0.018 | 0.5754 / 0.1951 / 0.020 | 0.5916 / 0.2017 / 0.019 | 0.5740 / 0.1947 / 0.012 |

## ROI simulat (1u plat, cote ≥ 1.15) — n / ROI ± eroare standard

| Model | Piață | EV>0 | EV>3% | EV>5% | recomandat (p≥60%, cotă≤2.20, EV>0) |
|---|---|---|---|---|---|
| v1_market | 1x2 | 988 / -8.6% ± 5.7 | 761 / -8.8% ± 6.8 | 644 / -14.4% ± 7.4 | 40 / -0.5% ± 12.4 |
| v1_market | ou_1.5 | 273 / -21.2% ± 8.6 | 134 / -22.4% ± 13.8 | 99 / -15.6% ± 17.0 | 70 / -18.5% ± 7.4 |
| v1_market | ou_2.5 | 540 / -5.6% ± 4.2 | 291 / -11.1% ± 5.7 | 183 / -7.8% ± 7.4 | 174 / +6.1% ± 5.7 |
| v1_market | ou_3.5 | 519 / -9.8% ± 5.3 | 339 / -6.6% ± 6.8 | 263 / -11.0% ± 7.8 | 103 / -1.5% ± 7.1 |
| v1_market | btts | 333 / -4.5% ± 5.3 | 144 / -6.0% ± 8.5 | 80 / -9.8% ± 11.3 | 100 / +1.7% ± 7.7 |
| v2_market | 1x2 | 716 / -11.4% ± 6.9 | 509 / -7.7% ± 8.8 | 410 / -7.1% ± 10.2 | 43 / -1.4% ± 12.4 |
| v2_market | ou_1.5 | 160 / +1.2% ± 16.4 | 90 / -2.5% ± 23.0 | 57 / -14.0% ± 27.9 | 16 / +8.9% ± 13.8 |
| v2_market | ou_2.5 | 266 / -5.6% ± 6.9 | 112 / -9.4% ± 11.3 | 63 / -5.1% ± 15.8 | 26 / -0.7% ± 15.8 |
| v2_market | ou_3.5 | 249 / -4.1% ± 7.5 | 112 / -0.8% ± 12.6 | 67 / -5.5% ± 17.2 | 78 / +5.0% ± 8.1 |
| v2_market | btts | 129 / +2.3% ± 10.8 | 53 / -6.0% ± 17.0 | 32 / -2.7% ± 23.0 | — |

Concluzie: modelul v2 e net mai precis și mai bine calibrat decât v1 pe toate piețele; combinat cu piața e la nivelul pieței (puțin mai bun pe GG și O/U 3.5). Pe eșantionul curat **nicio strategie nu are ROI pozitiv semnificativ statistic** — de aceea Robotul publică recomandări doar peste pragurile de valoare pe piață și le ajustează săptămânal din rezultatele reale. CLV: nu există încă destule cote de deschidere + închidere (snapshot-urile BSD pornesc din 7 oct. 2026).
