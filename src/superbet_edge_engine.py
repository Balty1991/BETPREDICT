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
    from superbet_live_odds import find_live_match, LIVE_MATCH_MIN_SCORE
except Exception:
    LIVE_MATCH_MIN_SCORE = 0.6
    def find_live_match(live_matches, home_team, away_team, event_dt, min_score=0.6):
        return None

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
CALIBRATION_STALE_DAYS = 7          # peste atat de zile fara observatii noi, calibrarea e considerata veche
STALE_EXTRA_CUSHION_PER_DAY = 0.005  # +0.5pp edge cerut per zi peste prag, ca siguranta suplimentara
STALE_EXTRA_CUSHION_CAP = 0.05        # dar niciodata mai mult de +5pp
WINDOW_DAYS = 10          # orizont de zile pentru watchlist (aliniat cu smart_accumulator)
THRESH_MIN = 1.30         # sub asta, cota corecta e prea mica pt. payout util intr-un acumulator
THRESH_MAX = 4.50         # peste asta, prag prea incert / piata prea subtire
MAX_PER_LEAGUE = 2
BANKROLL_LEI = 500.0      # banca implicita — ajustabil, doar orientativ pt. stake_amount_lei
TICKET_STAKE_PCT = {"Sigur": 2.0, "Echilibrat": 1.5}  # % din banca / bilet ("Riscant"/"Cotă mare" eliminate — vezi build_suggested_tickets)
# Plafon zilnic pe SUMA tuturor biletelor sugerate — aceeasi conventie (5%) ca risk_shield.py
# (max_daily_exposure_pct), desi cele doua sisteme ruleaza pe bugete separate (vezi
# _shared_risk_context). Previne ca sistemul, singur, sa recomande prea mult intr-o zi.
SELF_MAX_DAILY_EXPOSURE_PCT = 5.0

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


def _shared_risk_context() -> Dict[str, Any]:
    """Citeste risk_state.json (produs de risk_shield.py mai devreme in pipeline).
    Cele doua sisteme ruleaza pe bugete diferite (bankroll_unit=100 abstract acolo,
    BANKROLL_LEI=500 real aici) deci nu le insumam direct — dar circuit breaker-ul
    (declansat pe drawdown mare) e un semnal valabil peste tot: daca seria de
    pierderi a activat pauza acolo, e un motiv sa reduci expunerea si aici, nu doar
    in sistemul unde s-a declansat."""
    rs = _load("risk_state.json", {}) or {}
    breaker = rs.get("circuit_breaker", {}) or {}
    return {
        "ml_circuit_breaker_active": bool(breaker.get("active")),
        "ml_circuit_breaker_reason": breaker.get("reason"),
        "ml_today_exposure_pct": (rs.get("today") or {}).get("exposure_pct"),
    }


def _calibration(cal: Optional[Dict[str, Any]] = None) -> Tuple[float, float, Dict[str, Any]]:
    """Returneaza (margin_factor, edge_required, meta) din observatii reale.
    margin_factor: unde tinde sa fie cota TIPICA Superbet fata de pretul corect
    Pinnacle (ex: 0.93 = Superbet ofera de obicei ~93% din pretul corect).
    edge_required: cat trebuie sa depaseasca Superbet PROPRIA ei cota tipica ca
    sa conteze drept semnal (nu doar marja lor normala). Cu jurnal gol/insuficient
    (n<CALIBRATION_MIN_SAMPLES), foloseste fallback-urile DEFAULT_*.

    Daca jurnalul nu a mai primit observatii noi de peste CALIBRATION_STALE_DAYS,
    marcheaza "stale" si adauga un mic buffer suplimentar de siguranta (creste cu
    zilele, plafonat) — nu ignoram calibrarea veche, dar nici nu ne bazam orbeste
    pe ea pe termen nelimitat.

    `cal` e injectabil pentru teste; implicit (None) citeste jurnalul real de pe disc."""
    if cal is None:
        cal = _load("superbet_manual_calibration.json", {}) or {}
    obs = cal.get("observations") or []
    gaps = [safe_float(o.get("gap_pct")) for o in obs if o.get("gap_pct") is not None]
    updated_at = _parse_dt(cal.get("updated_at"))
    days_old = (datetime.now(timezone.utc) - updated_at).days if updated_at else None
    stale = days_old is not None and days_old > CALIBRATION_STALE_DAYS
    meta = {"n_observations": len(gaps), "source": "default", "days_old": days_old, "stale": stale}
    if len(gaps) < CALIBRATION_MIN_SAMPLES:
        return DEFAULT_MARGIN_FACTOR, DEFAULT_EDGE_REQUIRED, meta
    avg_gap_pct = sum(gaps) / len(gaps)
    raw_margin_factor = 1.0 + avg_gap_pct / 100.0
    margin_factor = min(MARGIN_FACTOR_CEIL, max(MARGIN_FACTOR_FLOOR, raw_margin_factor))
    edge_required = CALIBRATION_EDGE_REQUIRED
    if stale:
        extra = min(STALE_EXTRA_CUSHION_CAP, days_old * STALE_EXTRA_CUSHION_PER_DAY)
        edge_required += extra
        meta["stale_extra_cushion_pct"] = round(extra * 100, 2)
    meta.update({"source": "calibrat_din_observatii", "avg_gap_pct": round(avg_gap_pct, 2),
                 "margin_factor": round(margin_factor, 4),
                 "clamped": round(margin_factor, 4) != round(raw_margin_factor, 4),
                 "n_positive_gap": sum(1 for g in gaps if g > 0)})
    return round(margin_factor, 4), round(edge_required, 4), meta


def _time_label(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    try:
        local = dt.astimezone(RO_TZ)
        return local.strftime("%d.%m %H:%M")
    except Exception:
        return dt.strftime("%d.%m %H:%M")


def build_watchlist(margin_factor: float, edge_required: float,
                    compare: Optional[Dict[str, Any]] = None,
                    dc_idx: Optional[Dict[str, Any]] = None,
                    live_odds: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """`compare`/`dc_idx`/`live_odds` sunt injectabile pentru teste; implicit (None) citesc de pe disc."""
    if compare is None:
        compare = _load("compare_odds_cache.json", {}) or {}
    if dc_idx is None:
        dc_idx = _data_confidence_index()
    if live_odds is None:
        live_odds = _load("superbet_live_odds.json", {}) or {}
    live_matches = live_odds.get("matches") or []
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=WINDOW_DAYS)

    rows: List[Dict[str, Any]] = []
    for ev in (compare.get("results") or compare.get("events") or []):
        dt = _parse_dt(ev.get("event_date"))
        if not dt or dt < now or dt > cutoff:
            continue
        dc = dc_idx.get(str(ev.get("event_id")))
        # Un eveniment ABSENT din data_confidence.json nu inseamna "ok implicit" — poate
        # fi pur si simplu neprocesat inca. Tratam lipsa la fel de conservator ca INSUFICIENT.
        dc_tier = dc.get("tier") if dc is not None else "LIPSA"
        if dc_tier in ("INSUFICIENT", "LIPSA"):
            continue

        meta = {k: ev.get(k) for k in ("event_id", "home_team", "away_team", "league", "event_date")}
        live_match = find_live_match(live_matches, ev.get("home_team", ""), ev.get("away_team", ""), dt)
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

                # Cota reala Superbet, daca am gasit sigur acelasi meci in
                # superbet_live_odds.json — inlocuieste estimarea calibrata cu
                # adevarul (nu mai e nevoie ca utilizatorul sa verifice manual).
                live_price = None
                if live_match:
                    live_price = (live_match.get("markets", {}).get(market) or {}).get(oc)

                if live_price:
                    edge_actual = live_price / fair_odds - 1.0
                    if edge_actual < edge_required:
                        continue  # stim sigur ca nu e edge — nu mai afisam
                    expected_odds = live_price
                    threshold = live_price
                    odds_source = "live"
                else:
                    expected_odds = fair_odds * margin_factor   # cota TIPICA Superbet (calibrata)
                    # BUG CORECTAT (audit): cand margin_factor<1 (Superbet e de obicei sub fair —
                    # cazul masurat: avg_gap_pct=-5.81%), threshold = expected_odds*(1+5%) ajungea
                    # SUB fair_odds*(1+edge_required) — ex. fair=2.00, margin=0.94 => threshold=1.976,
                    # sub fair 2.00. Un "prag minim" mai mic decat pretul corect garanteaza EV negativ
                    # chiar daca respecti regula "cota >= prag" intocmai. Fix: threshold nu poate
                    # cobori sub fair_odds*(1+edge_required) — expected_odds (cota tipica Superbet)
                    # poate doar sa RIDICE bariera (cand Superbet plateste de obicei mai mult ca
                    # fair), niciodata sa o coboare sub valoarea corecta.
                    threshold = max(fair_odds, expected_odds) * (1.0 + edge_required)
                    odds_source = "estimare_calibrata"

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
                    "odds_source": odds_source,
                    "actual_superbet_odds": round(live_price, 2) if live_price else None,
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
            "expected_superbet_odds", "threshold_odds", "confidence", "steam_confirmed",
            "odds_source", "actual_superbet_odds")}
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
    # Biletele "Riscant" (5-6 picioare, prag 40%/picior) si "Cotă mare" (7-9 picioare,
    # prag 30%) au fost ELIMINATE după auditul din 21.07.2026: cu win rate real masurat
    # de ~46% per picior, istoricul decontat a fost 0 castigate din 12 la 6 picioare si
    # 0 din 12 la 9 picioare — matematic nu pot fi profitabile (0.46^9 ~= 0.1%).
    # Ele singure duceau ROI-ul biletelor la -65%. Putine bilete si scurte > multe si lungi.
    guard = _edge_market_guard()
    playable = [r for r in pool if not (guard.get(r.get("market"), {}).get("blocked_in_tickets"))]
    tickets = []
    t1 = _make_ticket("Sigur", _pick_legs(playable, 2, 3, min_prob=65.0))
    if t1:
        tickets.append(t1)
    # Pragul de 52% (nemodificat de la origine) e deja peste win rate-ul real masurat
    # al picioarelor jucabile (btts/over-under ~50%) — suficienta marja fara sa
    # goleasca pool-ul in zilele cu putine meciuri. L-am urcat gresit la 58% ieri,
    # fara o masuratoare care sa ceara exact atat; efect: 0 bilete azi (10 meciuri),
    # desi la 52% s-ar fi format un bilet valid din acelasi pool. Revenit la original.
    t2 = _make_ticket("Echilibrat", _pick_legs(playable, 3, 4, min_prob=52.0))
    if t2:
        tickets.append(t2)
    return tickets


def _edge_market_guard() -> Dict[str, Dict[str, Any]]:
    """Piete cu win rate real sub 50% pe picioarele decontate (n>=30) — excluse din
    bilete. Ex. la audit: 1x2 avea 41.2% real pe 51 de picioare; fiecare astfel de
    picior injumatateste sansele intregului bilet acumulator."""
    try:
        from market_performance_guard import edge_market_guard
        return edge_market_guard()
    except Exception:
        return {}


def _apply_exposure_cap(tickets: List[Dict[str, Any]], risk_ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Plafoneaza SUMA mizelor tuturor biletelor sugerate intr-o zi la SELF_MAX_DAILY_EXPOSURE_PCT
    (injumatatit daca circuit breaker-ul din sistemul ML e activ — o pauza de risc e globala,
    nu specifica unui singur sistem). Scaleaza proportional daca e depasit, ca la risk_shield.py."""
    cap = SELF_MAX_DAILY_EXPOSURE_PCT * (0.5 if risk_ctx.get("ml_circuit_breaker_active") else 1.0)
    total_before = sum(t["stake_pct_of_bankroll"] for t in tickets)
    scale = 1.0
    if total_before > cap and total_before > 0:
        scale = cap / total_before
        for t in tickets:
            t["stake_pct_of_bankroll"] = round(t["stake_pct_of_bankroll"] * scale, 3)
            t["stake_amount_lei"] = round(BANKROLL_LEI * t["stake_pct_of_bankroll"] / 100, 1)
            t["instructions"] += (f" ⚠️ Miză redusă automat ({round(scale * 100)}%) — suma tuturor "
                                   f"biletelor de azi depășea plafonul zilnic de {cap}% din bancă.")
    return {"cap_pct": cap, "total_before_pct": round(total_before, 3),
            "total_after_pct": round(min(total_before, cap), 3), "scale_applied": round(scale, 4)}


def _health_check(watchlist: List[Dict[str, Any]], tickets: List[Dict[str, Any]],
                  cal_meta: Dict[str, Any], exposure: Dict[str, Any]) -> Dict[str, Any]:
    """Stare de sanatate proprie a subsistemului Superbet Edge — celelalte health-check-uri
    din pipeline (v6_health.json, platform_monitor.json) nu stiu ca exista acest modul."""
    issues: List[str] = []
    status = "GREEN"

    def bump(level: str, msg: str) -> None:
        nonlocal status
        issues.append(msg)
        if level == "RED" or status == "RED":
            status = "RED" if level == "RED" else status
        elif level == "YELLOW" and status == "GREEN":
            status = "YELLOW"

    if not watchlist:
        bump("RED", "watchlist gol — verifică pipeline-ul (compare_odds_cache.json / data_confidence.json)")
    elif len(watchlist) < 10:
        bump("YELLOW", f"watchlist mic ({len(watchlist)} picioare) — puține meciuri eligibile azi")
    if not tickets:
        bump("YELLOW", "niciun bilet sugerat — pool insuficient de picioare cu încredere ridicată/medie")
    if cal_meta.get("n_observations", 0) < CALIBRATION_MIN_SAMPLES:
        bump("YELLOW", f"calibrare insuficientă ({cal_meta.get('n_observations', 0)} observații) — fallback neutru")
    elif cal_meta.get("stale"):
        bump("YELLOW", f"calibrare veche ({cal_meta.get('days_old')} zile) — trimite cote noi verificate")
    if cal_meta.get("clamped"):
        bump("YELLOW", "marja medie observată depășește limitele de siguranță (clamp activ) — verifică observațiile pentru outlieri")
    if exposure.get("scale_applied", 1.0) < 1.0:
        bump("YELLOW", f"expunere zilnică peste plafon — mize reduse automat la {round(exposure['scale_applied'] * 100)}%")

    return {"status": status, "issues": issues}


def main() -> int:
    margin_factor, edge_required, cal_meta = _calibration()
    live_odds = _load("superbet_live_odds.json", {}) or {}
    watchlist = build_watchlist(margin_factor, edge_required, live_odds=live_odds)
    # doar picioare cu incredere buna intra in biletele sugerate (nu cele "mediu" izolate cu prob mica)
    ticket_pool = [r for r in watchlist if r["confidence"] in ("ridicat", "mediu")]
    tickets = build_suggested_tickets(ticket_pool)
    n_live = sum(1 for r in watchlist if r.get("odds_source") == "live")

    risk_ctx = _shared_risk_context()
    exposure = _apply_exposure_cap(tickets, risk_ctx)
    health = _health_check(watchlist, tickets, cal_meta, exposure)

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
            + (f"⚠️ Calibrare veche ({cal_meta.get('days_old')} zile fără observații noi) — trimite cote "
               f"proaspete verificate pentru precizie. " if cal_meta.get("stale") else "")
            + "Se recalibreaza automat pe masura ce trimiti mai multe cote reale verificate. "
              "Verificare manuala tot obligatorie in aplicatia Superbet — pragul e un filtru, nu o garantie."
        ),
        "config": {"margin_factor": margin_factor, "edge_required_pct": round(edge_required * 100, 2),
                   "calibration_source": cal_meta["source"], "calibration": cal_meta,
                   "window_days": WINDOW_DAYS,
                   "threshold_range": [THRESH_MIN, THRESH_MAX], "bankroll_lei": BANKROLL_LEI},
        "risk_context": risk_ctx,
        "exposure": exposure,
        "health": health,
        "live_odds_meta": {
            "updated_at": live_odds.get("updated_at"),
            "n_matches_available": live_odds.get("n_matches_with_markets"),
            "fetch_error": live_odds.get("fetch_error"),
            "n_watchlist_confirmed_live": n_live,
        },
        "summary": {"n_watchlist": len(watchlist),
                    "n_steam_confirmed": sum(1 for r in watchlist if r["steam_confirmed"]),
                    "n_watchlist_live_odds": n_live,
                    "n_suggested_tickets": len(tickets)},
        "watchlist": watchlist,
        "suggested_tickets": tickets,
    }
    _atomic_write("superbet_edge_signals.json", out)

    print(f"[superbet_edge] health={health['status']} watchlist={len(watchlist)} "
          f"(steam={out['summary']['n_steam_confirmed']}, live_odds={n_live}) | bilete sugerate={len(tickets)}")
    for t in tickets:
        print(f"  {t['label']}: {t['n_legs']} legs | prag combinat {t['combined_threshold_odds']} "
              f"| prob combinata {t['combined_probability_pct']}% | miza {t['stake_amount_lei']} lei")
    if health["issues"]:
        for issue in health["issues"]:
            print(f"  [{health['status']}] {issue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
