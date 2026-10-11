# Laboratorul de strategii (11.10.2026)

- 38229 meciuri football-data cu cote de deschidere+închidere; 3776 configurații (6 seturi de piețe × 7 benzi de cotă × 2 chei × drift × ligi × 5 ținte × acumulator/N−1/N−2/N−3).
- Selecție cu piața de deschidere fără marjă; preț = închidere (1X2 medie reală, restul derivate Poisson cu overround 1.05 măsurat pe oferta Superbet); rezultat real.
- Antrenare 252 runde (2021–2024), test 185 runde (2024–2026).
- Pozitive în test: 405/3204; în ambele perioade: 55 (așteptat din noroc: 47.5); semnificative t>2: 0.

| țintă | strategii | ROI median test | % pozitive |
|---|---|---|---|
| 50 | 808 | -41.2% | 12% |
| 100 | 760 | -56.8% | 21% |
| 500 | 596 | -93.2% | 10% |
| 1000 | 572 | -98.2% | 7% |
| 2000 | 468 | -100.0% | 12% |

Super bilete (o strategie pe țintă, max 20 selecții medii):

- favoriti_1x2|1.25-1.60|value|drift|all|T50|acca: test n=81, lovit 2.5%, ROI +58% ± 111%; antrenare ROI +103%
- sansa_dubla|1.60-2.60|p|drift|all|T100|acca: test n=141, lovit 1.4%, ROI +74% ± 124%; antrenare ROI +93%
- sigure_mix|1.40-2.00|value|drift|all|T500|acca: test n=147, lovit 0.7%, ROI +447% ± 546%; antrenare ROI +270%
- favoriti_1x2|1.25-1.60|value|nodrift|all|T1000|N-3: test n=72, lovit 9.7%, ROI +7% ± 93%; antrenare ROI +48%

Neacoperit: combinații în același meci cu cornere (Superbet nu publică istoric de prețuri Bet Builder); istoricul BSD/robot are doar câteva zile — prea puțin pentru backtest. Filtrul de drift e aproximat live prin price_suspect.
