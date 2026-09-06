#!/usr/bin/env python3
"""
smart_accumulator.py — BetPredict v7 generator inteligent de acumulatoare
=========================================================================

Inlocuieste logica naiva de build (sortare doar dupa probabilitatea modelului,
fara control de corelatie, fara valoare vs. piata). Alimenteaza tabul
"Acumulator AI" existent scriind `data/claude_accumulators.json` cu ACEEASI
schema, dar cu bilete mult mai bune.

Reguli de selectie a picioarelor (din signals_v6.json + sharp_value_signals.json):
  1. CALITATE   — doar grad v6 A+/A/B, cu cota reala si EV calibrat >= -2%
                  (nu pariem impotriva pietei).
  2. EDGE REAL  — picioarele confirmate de Sharp-Value Engine (value vs Pinnacle
                  sau smart-money) primesc prioritate — edge care chiar exista.
  3. CORELATIE  — max 1 picior / meci, max 2 picioare / liga, diversificare piete
                  (nu 5x Under 3.5 din aceeasi tara care pica impreuna).

Tipuri de bilete (per fereastra 7/10/30 zile):
  • "Valoare sigura"      2-3 legs, prob mare + EV>=0, cota ~1.4-2.2 (highlight)
  • "Valoare echilibrata" 3-4 legs, EV combinat maxim, cota ~3-6
  • "Edge sharp"          2-4 legs, DOAR picioare confirmate sharp
  • "Long shot valoric"   pool de calitate (>=B), cota ~x50-x100 (de amuzament)

Output: data/claude_accumulators.json
Ruleaza standalone:  python3 src/smart_accumulator.py
"""
from __future__ import annotations
import json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

try:
    from analytics_core import safe_float
except Exception:
    def safe_float(v, d=0.0):
        try:
            x = float(v); return d if x != x else x
        except Exception:
            return d

try:
    from superbet_live_odds import find_live_match
except Exception:
    def find_live_match(live_matches, home_team, away_team, event_dt, min_score=0.6):
        return None

# ---- Config ----------------------------------------------------------------
MIN_GRADE_RANK = 1            # B=1, A=2, A+=3 -> acceptam >= B
MIN_EV_CAL = -0.02           # nu pariem impotriva pietei (EV calibrat sub -2% => afara)
MIN_LEG_ODDS = 1.60          # Edge v8: sub 1.60 e volum / piramidă V7
MAX_LEG_ODDS = 3.30          # peste 3.30 e zgomot
MAX_PER_LEAGUE = 1           # 1 ligă / zi pe bilet (corelație)
MAX_PER_MARKET_SHARE = 0.6   # max 60% picioare din aceeasi piata intr-un bilet
GRADE_RANK = {"A+": 3, "A": 2, "B": 1, "C": 0, "D": -1, "E": -2}
PERIODS = [("7", 7), ("10", 10), ("30", 30)]


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


_MARKET_GUARD_CACHE: Optional[Dict[str, Any]] = None


def _market_guard() -> Dict[str, Any]:
    """Verdict per piata din ROI-ul real decontat (market_performance_guard), cache-uit."""
    global _MARKET_GUARD_CACHE
    if _MARKET_GUARD_CACHE is None:
        try:
            sys.path.insert(0, HERE)
            from market_performance_guard import market_guard
            _MARKET_GUARD_CACHE = market_guard()
        except Exception:
            _MARKET_GUARD_CACHE = {}
    return _MARKET_GUARD_CACHE


def _sharp_confirmed_set() -> set:
    """(event_id, market_normalizat) care au semnal de value/steam din engine-ul sharp."""
    sv = _load("sharp_value_signals.json", {}) or {}
    out = set()
    market_map = {"1x2": None}  # 1x2 outcome-specific; tratam separat mai jos
    for s in sv.get("value_signals", []):
        out.add((s.get("event_id"), s.get("market"), s.get("outcome")))
    for s in sv.get("steam_signals", []):
        out.add((s.get("event_id"), s.get("market"), s.get("outcome")))
    return out


# maparea market-ului din signals_v6 -> (market sharp, outcome sharp)
_V6_TO_SHARP = {
    "homeWin": ("1x2", "HOME"), "draw": ("1x2", "DRAW"), "awayWin": ("1x2", "AWAY"),
    "btts": ("btts", "YES"), "no_btts": ("btts", "NO"),
    "over15": ("over_under_15", "OVER"), "under15": ("over_under_15", "UNDER"),
    "over25": ("over_under_25", "OVER"), "under25": ("over_under_25", "UNDER"),
    "over35": ("over_under_35", "OVER"), "under35": ("over_under_35", "UNDER"),
}


def _data_confidence_index() -> Dict[str, Dict[str, Any]]:
    dc = _load("data_confidence.json", {}) or {}
    return dc.get("by_event", {}) if isinstance(dc, dict) else {}


def build_leg_pool(sigs: Optional[Dict[str, Any]] = None,
                   dc_idx: Optional[Dict[str, Any]] = None,
                   live_odds: Optional[Dict[str, Any]] = None,
                   sharp: Optional[set] = None) -> List[Dict[str, Any]]:
    """`sigs`/`dc_idx`/`live_odds`/`sharp` sunt injectabile pentru teste; implicit
    (None) citesc de pe disc."""
    if sigs is None:
        sigs = _load("signals_v6.json", {}) or {}
    rows = sigs.get("signals") or (sigs if isinstance(sigs, list) else [])
    if sharp is None:
        sharp = _sharp_confirmed_set()
    if dc_idx is None:
        dc_idx = _data_confidence_index()
    if live_odds is None:
        live_odds = _load("superbet_live_odds.json", {}) or {}
    live_matches = live_odds.get("matches") or []

    pool = []
    for s in rows:
        # "odds" de aici e cea mai buna cota cross-book (best_odds.json, din BSD API) —
        # Superbet nu e in feed-ul lor. Ramane folosita ca ancora de piata pt. calculul
        # de probabilitate/edge (masoara valoare vs piata eficienta), DAR nu mai e ce
        # aratam userului — la final inlocuim cu cota REALA Superbet (sau scoatem
        # piciorul daca nu o gasim sigur, ca sa nu recomandam cote inaccesibile lui).
        odds = safe_float(s.get("odds"), 0.0)
        if odds < MIN_LEG_ODDS or odds > MAX_LEG_ODDS:
            continue
        market = s.get("market") or ""
        mk = str(market).lower()
        if mk in ("under35", "under_35", "over25", "over_25", "under25", "under_25"):
            continue
        if mk in ("over15", "over_15") and odds < 1.68:
            continue
        # Poartă de încredere în date: excludem picioarele pe meciuri cu date INSUFICIENTE
        # (amicale fără istoric/lineup/xG) — nu recomandăm pariuri neacoperite de date.
        dc = dc_idx.get(str(s.get("event_id")))
        if dc is not None and dc.get("tier") == "INSUFICIENT":
            continue
        grade = s.get("quality_grade_v6") or s.get("quality_grade") or "C"
        if GRADE_RANK.get(grade, 0) < MIN_GRADE_RANK:
            continue
        # Poarta de performanta: piete cu ROI real negativ dovedit (ex. under35 -20%
        # pe n=93 la audit) nu intra in bilete — cifrele vin din adaptive_thresholds.
        mg = _market_guard().get(str(s.get("market") or ""))
        if mg and mg.get("blocked"):
            continue
        ev_cal = s.get("ev_calibrated")
        ev_cal = safe_float(ev_cal, 0.0) if ev_cal is not None else 0.0
        if ev_cal < MIN_EV_CAL:
            continue

        # Probabilitate a MODELULUI (calibrata) — folosita doar ca ajustare minora.
        model_prob = None
        for k in ("calibrated_prob", "blend_prob", "adj_prob"):
            v = s.get(k)
            if v is not None and 0 < safe_float(v) <= 1:
                model_prob = safe_float(v); break
        if model_prob is None:
            conf = s.get("confidence")
            model_prob = safe_float(conf) / 100.0 if conf is not None and safe_float(conf) > 1 else (1.0 / odds)

        # ANCORA DE PIATA: piata (eficienta) e sursa dominanta de probabilitate,
        # nu modelul (care supra-estimeaza — vezi audit). Deflatam vig-ul (~4%).
        implied = 1.0 / odds
        market_anchor = min(0.985, implied * 0.96)
        # probabilitate REALISTA = 70% piata + 30% model (consistent cu BSD85/ML15)
        prob = 0.70 * market_anchor + 0.30 * model_prob
        prob_pct = round(max(1.0, min(99.0, prob * 100)), 2)

        market = s.get("market")
        sm, so = _V6_TO_SHARP.get(market, (None, None))
        is_sharp = (s.get("event_id"), sm, so) in sharp if sm else False
        smart_money = bool(s.get("smart_money_confirm"))

        # edge onest = probabilitate realista - implicita piata (mic, nu fantezie)
        edge_pp = round((prob - implied) * 100, 2)
        # scor de calitate al piciorului pentru sortare
        leg_score = (GRADE_RANK.get(grade, 0) * 20
                     + prob_pct * 0.4
                     + max(0.0, edge_pp) * 1.5
                     + (15 if is_sharp else 0)
                     + (8 if smart_money else 0))

        rationale_bits = [f"grad {grade}"]
        if edge_pp > 0:
            rationale_bits.append(f"edge +{edge_pp:.1f}pp")
        if is_sharp:
            rationale_bits.append("confirmat sharp (value vs Pinnacle)")
        elif smart_money:
            rationale_bits.append("smart money")
        if s.get("consensus_tier"):
            rationale_bits.append(f"consens {s.get('consensus_tier')}")

        # Cota REALA la care poti paria (Superbet) — daca nu gasim sigur meciul in
        # datele live, piciorul e inutil (nu poti obtine cota aratata), deci il scoatem
        # in loc sa aratam preturi de la case unde nu ai cont.
        if not sm:
            continue
        event_dt = _parse_dt(s.get("event_date"))
        live_match = find_live_match(live_matches, s.get("home_team", ""), s.get("away_team", ""), event_dt)
        superbet_odds = (live_match.get("markets", {}).get(sm) or {}).get(so) if live_match else None
        if not superbet_odds or superbet_odds < MIN_LEG_ODDS or superbet_odds > MAX_LEG_ODDS:
            continue
        if mk in ("over15", "over_15") and superbet_odds < 1.68:
            continue

        pool.append({
            "event_id": s.get("event_id"), "home_team": s.get("home_team"),
            "away_team": s.get("away_team"), "league": s.get("league"),
            "event_date": s.get("event_date"), "market": market,
            "market_label": s.get("market_label") or market,
            "odds": round(superbet_odds, 2), "probability": prob_pct,
            "rationale": ", ".join(rationale_bits),
            "bookmaker": "Superbet",
            "_grade": grade, "_grade_rank": GRADE_RANK.get(grade, 0),
            "_ev_cal": ev_cal, "_edge_pp": edge_pp, "_is_sharp": is_sharp,
            "_smart_money": smart_money, "_score": round(leg_score, 2),
        })
    pool.sort(key=lambda r: r["_score"], reverse=True)
    return pool


def _pick_legs(pool: List[Dict[str, Any]], min_legs: int, max_legs: int,
               min_prob: float = 0.0, sharp_only: bool = False,
               min_leg_odds: float = MIN_LEG_ODDS) -> List[Dict[str, Any]]:
    """Selecteaza picioare cu control de corelatie: 1/meci, MAX_PER_LEAGUE/liga,
    diversificare piete."""
    legs: List[Dict[str, Any]] = []
    used_events, league_count, market_count = set(), {}, {}
    for r in pool:
        if len(legs) >= max_legs:
            break
        if sharp_only and not r["_is_sharp"]:
            continue
        if r["probability"] < min_prob:
            continue
        if r["odds"] < min_leg_odds:
            continue
        eid = r["event_id"]
        if eid in used_events:
            continue
        lg = r.get("league") or "?"
        if league_count.get(lg, 0) >= MAX_PER_LEAGUE:
            continue
        mk = r.get("market")
        # diversificare piete: nu lasa o piata sa domine
        projected = len(legs) + 1
        if market_count.get(mk, 0) + 1 > max(1, int(projected * MAX_PER_MARKET_SHARE + 0.999)):
            # permite doar daca inca avem loc dupa regula share
            if projected >= 3:
                continue
        legs.append(r)
        used_events.add(eid)
        league_count[lg] = league_count.get(lg, 0) + 1
        market_count[mk] = market_count.get(mk, 0) + 1
    return legs if len(legs) >= min_legs else []


def _pick_target(pool: List[Dict[str, Any]], target_odds: float,
                 min_prob: float, max_legs: int) -> List[Dict[str, Any]]:
    """Construiește un longshot până la o cotă-țintă, fără a forța picioare.

    Dacă pool-ul nu poate atinge ținta în limita de picioare și a regulilor de
    corelație, returnează lista goală. Nu adaugă selecții slabe doar pentru a
    afișa artificial o cotă 50+/100+.
    """
    candidates = _pick_legs(pool, 4, max_legs, min_prob=min_prob)
    chosen: List[Dict[str, Any]] = []
    combined = 1.0
    for leg in candidates:
        chosen.append(leg)
        combined *= safe_float(leg.get("odds"), 1.0)
        if combined >= target_odds:
            return chosen
    return []


def _serialize(legs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{k: leg[k] for k in ("event_id", "home_team", "away_team", "league",
                                 "event_date", "market", "market_label", "odds",
                                 "probability", "rationale", "bookmaker")} for leg in legs]


def _make_ticket(label: str, legs: List[Dict[str, Any]], risk: str = "safe",
                 highlight: bool = False) -> Optional[Dict[str, Any]]:
    if not legs:
        return None
    combined_odds = 1.0
    combined_prob = 1.0
    for l in legs:
        combined_odds *= safe_float(l["odds"], 1.0)
        combined_prob *= safe_float(l["probability"], 0.0) / 100.0
    n_sharp = sum(1 for l in legs if l.get("_is_sharp"))
    avg_edge = round(sum(l.get("_edge_pp", 0.0) for l in legs) / len(legs), 1)

    # avertisment onest de corelatie / risc
    leagues = {}
    markets = {}
    for l in legs:
        leagues[l.get("league")] = leagues.get(l.get("league"), 0) + 1
        markets[l.get("market")] = markets.get(l.get("market"), 0) + 1
    concern = None
    dup_league = [k for k, v in leagues.items() if v >= 2]
    dup_market = [k for k, v in markets.items() if v >= 3]
    if dup_market:
        concern = (f"{dup_market[0]} apare pe {max(markets.values())} picioare — "
                   f"corelate (pot pica impreuna intr-o zi atipica).")
    elif dup_league:
        concern = f"2 picioare din {dup_league[0]} — usor corelate."

    return {
        "label": label, "risk_level": risk,
        "legs": _serialize(legs),
        "combined_odds": round(combined_odds, 2),
        "combined_probability_pct": round(combined_prob * 100, 4),
        "avg_edge_pp": avg_edge,
        "n_sharp_confirmed": n_sharp,
        "quality": "edge" if n_sharp else "value",
        "claude_concern": concern,
        "claude_highlight": highlight,
        "paper_only": risk == "longshot",
        "probability_warning": (
            "Longshot: probabilitatea este produsul probabilităților individuale; "
            "nu este o recomandare de miză reală."
            if risk == "longshot" else None
        ),
    }


def build_for_window(pool: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tickets: List[Dict[str, Any]] = []
    seen = set()

    def add(t: Optional[Dict[str, Any]]):
        if not t:
            return
        key = tuple(sorted((l["event_id"], l["market"]) for l in t["legs"]))
        if key in seen:
            return
        seen.add(key)
        tickets.append(t)

    # Edge v8: NU mai construim „Valoare sigură" din favorite @1.14.
    # Banca se joacă pe simple. Acca = loterie 50×/100×/200× din picioare +EV.
    add(_make_ticket("Edge sharp (confirmat piață)",
                     _pick_legs(pool, 2, 4, sharp_only=True, min_leg_odds=1.60), risk="safe"))
    add(_make_ticket("Acca 50× loterie",
                     _pick_target(pool, 50.0, min_prob=0.0, max_legs=8),
                     risk="longshot"))
    add(_make_ticket("Acca 100× loterie",
                     _pick_target(pool, 100.0, min_prob=0.0, max_legs=8),
                     risk="longshot"))
    add(_make_ticket("Acca 200× loterie",
                     _pick_target(pool, 200.0, min_prob=0.0, max_legs=8),
                     risk="longshot"))
    return tickets


def build_tickets_by_period() -> Dict[str, List[Dict[str, Any]]]:
    """Construieste tickets_by_period din signals_v6 + sharp signals.
    Reutilizabil de claude_analysis.py ca sursa unica de adevar."""
    pool = build_leg_pool()
    now = datetime.now(timezone.utc)
    by_period: Dict[str, List[Dict[str, Any]]] = {}
    for key, days in PERIODS:
        cutoff = now + timedelta(days=days)
        window = [r for r in pool if (dt := _parse_dt(r.get("event_date"))) and dt <= cutoff]
        by_period[key] = build_for_window(window)
    return by_period


def main() -> int:
    pool = build_leg_pool()
    now = datetime.now(timezone.utc)
    by_period: Dict[str, List[Dict[str, Any]]] = {}
    for key, days in PERIODS:
        cutoff = now + timedelta(days=days)
        window = [r for r in pool if (dt := _parse_dt(r.get("event_date"))) and dt <= cutoff]
        by_period[key] = build_for_window(window)

    out = {
        "updated_at": now.isoformat(),
        "source": "smart_accumulator_v7",
        "note": "Bilete construite din semnale calibrate (grad A+/A/B, EV nenegativ), "
                "confirmate de edge-ul sharp, cu control de corelatie (1/meci, 2/liga).",
        "pool_size": len(pool),
        "sharp_confirmed_in_pool": sum(1 for r in pool if r["_is_sharp"]),
        "tickets_by_period": by_period,
    }
    _atomic_write("claude_accumulators.json", out)

    print(f"[smart_acc] pool={len(pool)} legs "
          f"({out['sharp_confirmed_in_pool']} sharp-confirmate)")
    for period, tks in by_period.items():
        print(f"  perioada {period}z: {len(tks)} bilete")
        for t in tks:
            print(f"    • {t['label']}: {len(t['legs'])} legs @ {t['combined_odds']} "
                  f"| prob {t['combined_probability_pct']:.1f}% | edge {t['avg_edge_pp']}pp "
                  f"| {t['n_sharp_confirmed']} sharp{' ★' if t['claude_highlight'] else ''}")
        break  # print doar prima perioada in detaliu
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
