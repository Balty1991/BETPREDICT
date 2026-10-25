# Biletele lui Ștefan: cum adaug bilete noi

## Varianta 1 (preferată): linkul de share Superbet
- Alin: Statistici › Biletele lui Ștefan › „+ Adaugă link de bilet Superbet” → se deschide un issue „Bilet Ștefan” pe GitHub;
  lipește linkul (`https://superbet.onelink.me/...`) sau codul biletului (`8939-BBNST0`) și trimite.
- Asistentul: adaugă linkul pe un rând nou în `data/stefan_links.txt` (commit pe main).
- Pipeline-ul (`stefan_links.sync`, la daily/refresh): linkul se rezolvă **o singură dată** (GET onelink cu UA de browser →
  `deep_link_sub1` base64 → `ticket_id`), apoi biletul se cere din API-ul public Supersocial
  (`content-preview/rosuperbetsport/public/ticket?ticket_id=`) **cel mult o dată pe rulare**, doar cât e activ (status 1).
  Statusuri Superbet: 1 activ, 3 pierdut, 7 câștigat, 8 cashout. Datele stau în DB (`stefan_sb`, `stefan_sb_link`).
- Fiecare selecție se decontează și din rezultatele noastre (meciul căutat după nume, −2/+3 zile de la prima citire);
  meciurile din ligi pe care nu le avem rămân „meci negăsit” și contează doar statusul Superbet.

## Varianta 2: capturi

Fișierul `data/stefan_tickets.json` ține selecțiile reale ale lui Ștefan (Supersocial). La fiecare rulare, pipeline-ul
(`betpredict/experimental/stefan.py`) le decontează din rezultatele noastre și publică `api/stefan.json`.
Cardul „Biletele lui Ștefan” din Statistici › Sumar citește fișierul publicat.

## Pași (asistentul, la fiecare set de capturi)
1. `git pull --rebase origin main`.
2. Adaugi câte un obiect nou în `tickets` (nu modifici biletele vechi, doar `status_shown` / `result_shown` dacă o captură nouă arată rezultatul):
```json
{"id": "s-AAAA-LL-ZZ-x", "posted": "AAAA-LL-ZZ", "posted_note": "„1z” pe captura din ...",
 "status_shown": "won|lost|pending", "badge": "10W", "total_odds": 67.86, "legs_total": 11, "more_hidden": 10, "note": null,
 "legs": [{"home": "Randers FC", "away": "Brondby", "market": "H1C_3_6", "odds": 1.55, "kickoff": null, "result_shown": "won"}]}
```
3. Doar ce se vede pe captură. Câmp necitibil = `null`. Selecțiile ascunse („+N mai mult”) nu se inventează: le notezi în `more_hidden`.
4. `kickoff` = ISO UTC dacă se vede ora (`"2026-10-25T14:00:00Z"`), altfel `null`. Atunci meciul se caută după nume
   între `posted` −2 zile și +3 zile.
5. `python -m pytest -q tests/v3/test_stefan.py`, commit, PR, merge.

## Chei de piață
| cheie | pe Superbet | decontare |
|---|---|---|
| `H1C_3_6` | Bet Builder: cornere R1 Peste 2.5 + Sub 6.5 | 3–6 cornere în R1 |
| `G14` / `G15` / `G25` | Interval goluri 1-4 / 1-5 / 2-5 | total goluri în interval |
| `EACH_C3` | Fiecare echipă peste 2.5 cornere - Da | gazde ≥3 și oaspeți ≥3 cornere |
| `NEXT10_C05` | Următoarele 10 min: cornere Peste 0.5 (live) | `nesettlabil`: nu avem cornere pe minut |
| `BB_H1O05_O15` | Bet Builder „Peste 0.5;Peste 1.5” = Prima repriză total goluri Peste 0.5 + Total goluri Peste 1.5 | ≥1 gol în R1 și ≥2 în meci |
| `H1O05` / `O15` / `O25` | Prima repriză Peste 0.5 / Total goluri Peste 1.5 / 2.5 | din scor |

O piață nouă: adaugi cheia în `markets` (JSON), apoi în `LABELS` + `settle()` din `stefan.py`, plus un test.

## Ce arată rezultatul
- `result`: `won` / `lost` / `pending` / `nesettlabil` / `negasit` (meciul nu e în baza noastră).
- `implied` = (1/cotă)/1.05. Ștefan are plus doar dacă procentul lovit trece constant peste el, pe zeci de selecții.
- `model_p` / `model_ev`: șansa robotului (urmărirea Stil; la intervale de goluri, Poisson din modelul de goluri).
  `model_pick` = robotul ar fi luat selecția (EV ≥ 0 la cota lui Ștefan).
