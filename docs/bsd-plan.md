# Notă de memorie: planul BSD = **Football API Unlimited** (din 11.10.2026)

- Plan: Unlimited (founder, $2/lună), aceeași cheie (secret `BSD_API_KEY`); workflow: `BSD_PLAN=unlimited` → fără cotă zilnică locală și fără blocările locale ale endpointurilor plătite.
- Sondaj în Actions (`scripts/bsd_probe.py`, 11.10.2026): `/odds/comparison/` 200 (mediană 25 case/meci, Pinnacle pe 27/40 meciuri), `/odds/?bookmaker_slug=pinnacle` 200 (4,583 rânduri, cu `opening_decimal_odds`), `/odds/best/` 200 (319 evenimente), `/events/{id}/lineups/` 200 (formații + `unavailable_players`), `/injuries/` 404. 60 de cereri consecutive: toate 200, fără antete de limită (~0.4 s/cerere).
- ATENȚIE: pe Unlimited `/odds/` fără filtru întoarce rânduri PE CASĂ, nu „consensus”; consensul îl calculăm noi (mediana caselor) din `/odds/comparison/` — vezi `betpredict/ingest/multibook.py`.
- Surse în `odds_snapshot`: `bsd_consensus` (mediană), `bsd:pinnacle`, `bsd_best` (cea mai bună cotă). No-vig: consens amestecat cu Pinnacle (w=0.75; football-data 2023–26: LogLoss 1X2 la închidere 0.97223 → 0.97168 doar Pinnacle). CLV benchmark: închiderea Pinnacle fără marjă (`prediction.clv_pin`).
- Plafoane per rulare: daily 6,000 · refresh 900 · closing 250 cereri; context 48 h/400 echipe (daily), 24 h/250 (refresh).
