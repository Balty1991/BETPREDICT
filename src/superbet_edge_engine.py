#!/usr/bin/env python3
"""
superbet_edge_engine.py — BetPredict v7 Superbet Edge Watchlist
=================================================================

Superbet NU e in feed-ul de bookmakeri urmariti de BSD API (compare_odds_cache.json
are ~80 case, Superbet nu e printre ele). Deci motorul Sharp-Value clasic
(sharp_value_engine.py, care recomanda "best odds" cross-book) nu e utilizabil
direct — recomanda cote la book-uri unde utilizatorul nu are cont.

Acest motor rezolva situatia reala: joci pe UN SINGUR bookmaker (Superbet),
banca mica (~500 lei), bilete Acumulator (nu single bet). In loc sa compare
cota Superbet (necunoscuta sistemului) direct cu pretul BRUT Pinnacle (un book
de retail nu poate depasi structural marja ~0% a lui Pinnacle in mod repetat),
calculeaza cota TIPICA la care Superbet ar pretui de obicei (fair Pinnacle
ajustat cu marja lor reala, calibrata din cote verificate manual) si cere un
prag PESTE aia — o anomalie reala, nu doar marja lor normala.

Fluxul de folosire:
  1. Pipeline-ul genereaza watchlist-ul + 2-3 bilete sugerate (legs cu prag,
     nu cu cota Superbet reala — aia nu exista in date).
  2. Utilizatorul deschide Superbet, verifica fiecare picior la prag inainte
     sa-l bage pe bilet manual.

Output: data/superbet_edge_signals.json
Ruleaza standalone: python3 src/superbet_edge_engine.py
"""
from __future__ import annotations
import json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
    RO_TZ = ZoneInfo("Europe/Bucharest")
except Exception:
    RO_TZ = timezone(timedelta(hours=3))  # fallback aproximativ (ora de vara)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from sharp_value_engine import MARKET_OUTCOMES, STEAM_MIN_SHORTENING, _sharp_fair_probs

try:
    from analytics_core import safe_float
except Exception:
    def safe_float(v, d=0.0):
        try:
            x = float(v); return d if x != x else x
        except Exception:
            return d

# ---- Config ------------------------------------------------------------------
# GRESEALA CORECTATA: pana acum threshold = pret_corect_Pinnacle x (1+min_ev) — cerea ca
# Superbet (book de retail, marja ~6-9%) sa depaseasca pretul unui book cu marja ~0
# (Pinnacle). Structural aproape imposibil — de-aia pragul parea tot mai "umflat" fata
# de realitate cand cream bufferul. Fix: reperul e cota TIPICA Superbet (fair Pinnacle
# ajustat cu marja lor reala, calibrata din observatii), nu Pinnacle brut. Cerem edge
# doar PESTE cota lor tipica — adica o anomalie reala (mispricing), nu sa bata un book
# fara marja.
DEFAULT_MARGIN_FACTOR = 1.00   # fara date: presupunem Superbet ~= pretul corect (neutru)
DEFAULT_EDGE_REQUIRED = 0.10   # fallback daca jurnalul de calibrare e insuficient
CALIBRATION_EDGE_REQUIRED = 0.05   # edge cerut PESTE cota tipica Superbet calibrata
CALIBRATION_MIN_SAMPLES = 3        # sub atat, nu e statistic suficient — foloseste fallback
MARGIN_FACTOR_FLOOR = 0.80     # clamp — un outlier sa nu distorsioneze prea mult
MARGIN_FACTOR_CEIL = 1.05
WINDOW_DAYS = 10          # orizont de zile pentru watchlist (aliniat cu smart_accumulator)
THRESH_MIN = 1.30         # sub asta, cota corecta e prea mica pt. payout util intr-un acumulator
THRESH_MAX = 4.50         # peste asta, prag prea incert / piata prea subtire
MAX_PER_LEAGUE = 2
BANKROLL_LEI = 500.0      # banca implicita — ajustabil, doar orientativ pt. stake_amount_lei
TICKET_STAKE_PCT = {"Sigur": 2.0, "Echilibrat": 1.5, "Riscant": 0.75, "Cotă mare": 0.4}  # % din banca / bilet

MARKET_LABELS = {
    "1x2": "Rezultat final", "btts": "Ambele echipe marchează",
    "over_under_15": "Over/Under 1.5", "over_under_25": "Over/Under 2.5",
    "over_under_35": "Over/Under 3.5",
}
OUTCOME_LABELS = {
    "HOME": "Gazde", "DRAW": "Egal", "AWAY": "Deplasare",
    "YES": "Da", "NO": "Nu", "OVER": "Peste", "UNDER": "Sub",
}
CONFIDENCE_BY_SRC = {"pinnacle": "ridicat", "marathon": "mediu", "betfair": "mediu", "1xbet": "mediu"}


def _load(name: str, default: Any = None) -> Any:
    try:
        with open(os.path.join(DATA, name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _atomic_write(name: str, obj: Any) -> None:
    p = os.path.join(DATA, name)
    fd, tmp = tempfile.mkstemp(dir=DATA, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _parse_dt(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _data_confidence_index() -> Dict[str, Dict[str, Any]]:
    dc = _load("data_confidence.json", {}) or {}
    return dc.get("by_event", {}) if isinstance(dc, dict) else {}


def _calibration() -> Tuple[float, float, Dict[str, Any]]:
    """Returneaza (margin_factor, edge_required, meta) din observatii reale.
    margin_factor: unde tinde sa fie cota TIPICA Superbet fata de pretul corect
    Pinnacle (ex: 0.93 = Superbet ofera de obicei ~93% din pretul corect).
    edge_required: cat trebuie sa depaseasca Superbet PROPRIA ei cota tipica ca
    sa conteze drept semnal (nu doar marja lor normala). Cu jurnal gol/insuficient
    (n<CALIBRATION_MIN_SAMPLES), foloseste fallback-urile DEFAULT_*."""
    cal = _load("superbet_manual_calibration.json", {}) or {}
    obs = cal.get("observations") or []
    gaps = [safe_float(o.get("gap_pct")) for o in obs if o.get("gap_pct") is not None]
    meta = {"n_observations": len(gaps), "source": "default"}
    if len(gaps) < CALIBRATION_MIN_SAMPLES:
        return DEFAULT_MARGIN_FACTOR, DEFAULT_EDGE_REQUIRED, meta
    avg_gap_pct = sum(gaps) / len(gaps)
    margin_factor = min(MARGIN_FACTOR_CEIL, max(MARGIN_FACTOR_FLOOR, 1.0 + avg_gap_pct / 100.0))
    meta.update({"source": "calibrat_din_observatii", "avg_gap_pct": round(avg_gap_pct, 2),
                 "margin_factor": round(margin_factor, 4),
                 "n_positive_gap": sum(1 for g in gaps if g > 0)})
    return round(margin_factor, 4), CALIBRATION_EDGE_REQUIRED, meta


def _time_label(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    try:
        local = dt.astimezone(RO_TZ)
        return local.strftime("%d.%m %H:%M")
    except Exception:
        return dt.strftime("%d.%m %H:%M")


def build_watchlist(margin_factor: float, edge_required: float) -> List[Dict[str, Any]]:
    compare = _load("compare_odds_cache.json", {}) or {}
    dc_idx = _data_confidence_index()
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=WINDOW_DAYS)

    rows: List[Dict[str, Any]] = []
    for ev in (compare.get("results") or compare.get("events") or []):
        dt = _parse_dt(ev.get("event_date"))
        if not dt or dt < now or dt > cutoff:
            continue
        dc = dc_idx.get(str(ev.get("event_id")))
        if dc is not None and dc.get("tier") == "INSUFICIENT":
            continue

        meta = {k: ev.get(k) for k in ("event_id", "home_team", "away_team", "league", "event_date")}
        for market, mobj in ev.get("markets", {}).items():
            labels = MARKET_OUTCOMES.get(market)
            if not labels:
                continue
            outcomes = mobj.get("outcomes", {})
            if not all(oc in outcomes for oc in labels):
                continue
            fair = _sharp_fair_probs(market, outcomes)
            if not fair:
                continue
            fair_probs, sharp_src = fair
            if sharp_src == "consensus_median":
                continue  # doar preturi dintr-o singura sursa sharp reala, nu mediana soft

            for oc in labels:
                p = fair_probs.get(oc)
                if not p or p <= 0:
                    continue
                fair_odds = 1.0 / p
                if not (THRESH_MIN <= fair_odds <= THRESH_MAX):
                    continue
                expected_odds = fair_odds * margin_factor   # cota TIPICA Superbet (calibrata)
                threshold = expected_odds * (1.0 + edge_required)
                n_short = sum(1 for b in outcomes[oc].get("bookmakers", [])
                              if (b.get("movement") or "").upper() == "SHORTENING")
                steam = n_short >= STEAM_MIN_SHORTENING

                rows.append({
                    **meta,
                    "event_time_label": _time_label(dt),
                    "market": market, "market_label": MARKET_LABELS.get(market, market),
                    "outcome": oc, "outcome_label": OUTCOME_LABELS.get(oc, oc),
                    "fair_prob_pct": round(p * 100, 1),
                    "fair_odds": round(fair_odds, 2),
                    "expected_superbet_odds": round(expected_odds, 2),
                    "threshold_odds": round(threshold, 2),
                    "sharp_source": sharp_src,
                    "confidence": CONFIDENCE_BY_SRC.get(sharp_src, "mediu"),
                    "steam_confirmed": steam,
                    "n_shortening": n_short,
                })

    # Marcheaza cel mai bun picior per meci (scor: prob + incredere + steam) — cand un meci
    # are mai multe piete candidate, utilizatorul stie imediat pe care sa se uite primul.
    best_per_event: Dict[Any, Dict[str, Any]] = {}
    for r in rows:
        cur = best_per_event.get(r["event_id"])
        if cur is None or _score(r) > _score(cur):
            best_per_event[r["event_id"]] = r
    for r in rows:
        r["recommended"] = best_per_event.get(r["event_id"]) is r

    rows.sort(key=lambda r: (-r["steam_confirmed"], r["threshold_odds"]))
    return rows


def _score(r: Dict[str, Any]) -> float:
    return (r["fair_prob_pct"] * 0.6
            + (15 if r["confidence"] == "ridicat" else 5)
            + (12 if r["steam_confirmed"] else 0))


def _pick_legs(pool: List[Dict[str, Any]], min_legs: int, max_legs: int,
              min_prob: float) -> List[Dict[str, Any]]:
    legs: List[Dict[str, Any]] = []
    used_events, league_count = set(), {}
    for r in sorted(pool, key=_score, reverse=True):
        if len(legs) >= max_legs:
            break
        if r["fair_prob_pct"] < min_prob:
            continue
        eid = r["event_id"]
        if eid in used_events:
            continue
        lg = r.get("league") or "?"
        if league_count.get(lg, 0) >= MAX_PER_LEAGUE:
            continue
        legs.append(r)
        used_events.add(eid)
        league_count[lg] = league_count.get(lg, 0) + 1
    return legs if len(legs) >= min_legs else []


def _make_ticket(label: str, legs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not legs:
        return None
    combined_threshold = 1.0
    combined_prob = 1.0
    for l in legs:
        combined_threshold *= l["threshold_odds"]
        combined_prob *= l["fair_prob_pct"] / 100.0
    stake_pct = TICKET_STAKE_PCT.get(label, 1.0)
    risk_note = (" ⚠️ Risc ridicat — variance mare, multe picioare pot pica ușor; "
                 "miză mică, doar din bani pe care îți permiți să-i pierzi."
                 if label in ("Riscant", "Cotă mare") else "")
    return {
        "label": label,
        "legs": [{k: leg[k] for k in (
            "event_id", "home_team", "away_team", "league", "event_date", "event_time_label",
            "market", "market_label", "outcome", "outcome_label", "fair_prob_pct", "fair_odds",
            "expected_superbet_odds", "threshold_odds", "confidence", "steam_confirmed")}
            for leg in legs],
        "combined_threshold_odds": round(combined_threshold, 2),
        "combined_probability_pct": round(combined_prob * 100, 2),
        "n_legs": len(legs),
        "stake_pct_of_bankroll": stake_pct,
        "stake_amount_lei": round(BANKROLL_LEI * stake_pct / 100, 1),
        "instructions": (f"Verifică fiecare picior în Superbet: cota trebuie să fie ≥ pragul indicat. "
                          f"Dacă un picior e sub prag, scoate-l din bilet sau înlocuiește-l cu altul din watchlist. "
                          f"Miză sugerată: {stake_pct}% din bancă (~{round(BANKROLL_LEI * stake_pct / 100, 1)} lei "
                          f"la o bancă de {int(BANKROLL_LEI)} lei).{risk_note}"),
    }


def build_suggested_tickets(pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tickets = []
    t1 = _make_ticket("Sigur", _pick_legs(pool, 2, 3, min_prob=65.0))
    if t1:
        tickets.append(t1)
    t2 = _make_ticket("Echilibrat", _pick_legs(pool, 3, 4, min_prob=52.0))
    if t2:
        tickets.append(t2)
    t3 = _make_ticket("Riscant", _pick_legs(pool, 5, 6, min_prob=40.0))
    if t3:
        tickets.append(t3)
    t4 = _make_ticket("Cotă mare", _pick_legs(pool, 7, 9, min_prob=30.0))
    if t4:
        tickets.append(t4)
    return tickets


def main() -> int:
    margin_factor, edge_required, cal_meta = _calibration()
    watchlist = build_watchlist(margin_factor, edge_required)
    # doar picioare cu incredere buna intra in biletele sugerate (nu cele "mediu" izolate cu prob mica)
    ticket_pool = [r for r in watchlist if r["confidence"] in ("ridicat", "mediu")]
    tickets = build_suggested_tickets(ticket_pool)

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "superbet_edge_engine_v2",
        "bookmaker": "superbet",
        "methodology": (
            "Superbet nu e in feed-ul de bookmakeri urmariti. Reperul NU mai e pretul brut "
            "Pinnacle (marja ~0%, un book de retail nu-l poate depasi structural) — e cota "
            "TIPICA Superbet, calibrata din cote reale verificate manual: expected_odds = "
            "fair_odds_Pinnacle x margin_factor. Threshold = expected_odds x (1+edge_required) "
            "= cota minima ca sa conteze drept anomalie reala (mispricing), nu doar marja lor normala. "
            f"Calibrare curenta: {cal_meta['n_observations']} cote reale verificate manual "
            + (f"(marja medie observata {cal_meta.get('avg_gap_pct')}%, {cal_meta.get('n_positive_gap')} din "
               f"{cal_meta['n_observations']} pozitive) -> margin_factor {cal_meta.get('margin_factor')}, "
               f"edge cerut peste cota tipica {round(edge_required * 100, 1)}%. "
               if cal_meta["source"] == "calibrat_din_observatii" else
               f"(sub {CALIBRATION_MIN_SAMPLES} — insuficient, folosit fallback neutru margin_factor "
               f"{DEFAULT_MARGIN_FACTOR}, edge {round(edge_required * 100, 1)}%). ")
            + "Se recalibreaza automat pe masura ce trimiti mai multe cote reale verificate. "
              "Verificare manuala tot obligatorie in aplicatia Superbet — pragul e un filtru, nu o garantie."
        ),
        "config": {"margin_factor": margin_factor, "edge_required_pct": round(edge_required * 100, 2),
                   "calibration_source": cal_meta["source"], "calibration": cal_meta,
                   "window_days": WINDOW_DAYS,
                   "threshold_range": [THRESH_MIN, THRESH_MAX], "bankroll_lei": BANKROLL_LEI},
        "summary": {"n_watchlist": len(watchlist),
                    "n_steam_confirmed": sum(1 for r in watchlist if r["steam_confirmed"]),
                    "n_suggested_tickets": len(tickets)},
        "watchlist": watchlist,
        "suggested_tickets": tickets,
    }
    _atomic_write("superbet_edge_signals.json", out)

    print(f"[superbet_edge] watchlist={len(watchlist)} "
          f"(steam={out['summary']['n_steam_confirmed']}) | bilete sugerate={len(tickets)}")
    for t in tickets:
        print(f"  {t['label']}: {t['n_legs']} legs | prag combinat {t['combined_threshold_odds']} "
              f"| prob combinata {t['combined_probability_pct']}% | miza {t['stake_amount_lei']} lei")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
