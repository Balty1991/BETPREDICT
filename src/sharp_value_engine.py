#!/usr/bin/env python3
"""
sharp_value_engine.py  — BetPredict v7 flagship strategy (v2)
=============================================================

Schimbare de paradigma fata de v6: NU incercam sa "prezicem mai bine decat
piata" cu un model slab (AUC 0.583, CLV -1.35%). HARVESTAM edge-ul care exista
DEJA in datele colectate.

Patru surse de profit, toate independente de calitatea modelului nostru:

  1. SHARP-VALUE  — Pinnacle no-vig = probabilitate corecta. Cand un book soft
     ofera o cota mai mare decat cota corecta => EV pozitiv REAL (=> CLV pozitiv).
     [sursa: compare_odds_cache.json — adancime per-bookmaker]

  2. STEAM / DROP — cota se scurteaza (SHORTENING) la >=N book-i simultan =>
     banii sharp au intrat. Prindem miscarea devreme.
     [sursa: compare_odds_cache.json]

  3. ARBITRAJ    — cu 17 book-i, uneori Sum(1/best_odds) < 1 => profit garantat.
     [sursa: best_odds.json — 551 evenimente, cel mai mare volum]

  4. POLYMARKET DIVERGENCE — multimea sharp de pe Polymarket difera >5pp de
     book-urile soft => semnal de piata independent.
     [sursa: polymarket.json + best_odds.json]

Filtre anti-zgomot (v2):
  - EV plafonat la MAX_EV (cote stale/erori dau EV fals urias pe outsideri)
  - Filtru outlier: best price nu poate fi mult peste al 2-lea best (linie stale)
  - Freshness: cote arbitraj mai vechi de STALE_HOURS sunt ignorate

Output: data/sharp_value_signals.json
Ruleaza standalone:  python3 src/sharp_value_engine.py
"""
from __future__ import annotations
import json, os, sys, tempfile
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, ROOT)

try:
    from analytics_core import normalize_no_vig, kelly_fraction, safe_float
except Exception:
    def safe_float(v, d=0.0):
        try:
            x = float(v); return d if x != x else x
        except Exception:
            return d
    def normalize_no_vig(odds, min_valid=2):
        implied = [(1.0/o if (o and o > 1.01) else None) for o in odds]
        valid = [p for p in implied if p]
        if len(valid) < min_valid:
            return [None]*len(odds)
        m = sum(valid)
        return [None if p is None else p/m for p in implied]
    def kelly_fraction(p, o, fraction=0.25, cap=0.08):
        p = max(0.0, min(1.0, p)); o = safe_float(o)
        if p <= 0 or o <= 1.01:
            return 0.0
        b = o - 1.0
        return round(max(0.0, min(cap, ((p*b-(1-p))/b)*fraction)), 6)

# ---- Config ----------------------------------------------------------------
SHARP_BOOKS = ["pinnacle", "marathon", "betfair", "1xbet"]
SYNTHETIC = {"consensus", "oddssafari-consensus"}

MIN_EV = 0.02              # 2% EV minim vs pretul sharp
MAX_EV = 0.15             # peste 15% EV = aproape sigur cota stale/eroare -> ignoram
OUTLIER_RATIO = 1.25      # best price > 1.25x al 2-lea best => linie suspecta
STEAM_MIN_SHORTENING = 4
ARB_MARGIN = 0.9985       # Sum(1/odds) sub asta => arbitraj real (buffer rotunjiri)
STALE_HOURS = 36          # cote mai vechi de atat inainte de start = ignorate la arb
POLY_DIVERGENCE_PP = 5.0  # divergenta minima Polymarket vs book (puncte procentuale)
KELLY_FRACTION = 0.25
KELLY_CAP = 0.05

MARKET_OUTCOMES = {
    "1x2": ["HOME", "DRAW", "AWAY"],
    "btts": ["YES", "NO"],
    "over_under_15": ["OVER", "UNDER"],
    "over_under_25": ["OVER", "UNDER"],
    "over_under_35": ["OVER", "UNDER"],
}
# best_odds.json foloseste outcome-uri lowercase
BESTODDS_OUTCOMES = {
    "1x2": ["HOME", "DRAW", "AWAY"],
    "btts": ["yes", "no"],
    "over_under_15": ["over", "under"],
    "over_under_25": ["over", "under"],
    "over_under_35": ["over", "under"],
    "double_chance": ["1X", "12", "X2"],
}


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


# ============================================================
# SURSA 1+2: SHARP-VALUE + STEAM (din compare_odds_cache — adancime per-book)
# ============================================================
def _book_odds_map(outcome_obj: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for b in outcome_obj.get("bookmakers", []):
        slug = b.get("bookmaker_slug") or b.get("bookmaker")
        o = safe_float(b.get("decimal_odds"), 0.0)
        if slug and o > 1.01:
            out[slug] = {"odds": o, "movement": (b.get("movement") or "").upper()}
    return out


def _sharp_fair_probs(market: str, outcomes: Dict[str, Any]
                      ) -> Optional[Tuple[Dict[str, float], str]]:
    labels = MARKET_OUTCOMES.get(market)
    if not labels:
        return None
    per_outcome = {oc: _book_odds_map(outcomes.get(oc, {})) for oc in labels}
    for sharp in SHARP_BOOKS:
        if all(sharp in per_outcome[oc] for oc in labels):
            odds = [per_outcome[oc][sharp]["odds"] for oc in labels]
            probs = normalize_no_vig(odds)
            if all(p is not None for p in probs):
                return {oc: probs[i] for i, oc in enumerate(labels)}, sharp
    # fallback: consensus median al book-ilor reali
    odds = []
    for oc in labels:
        real = [v["odds"] for slug, v in per_outcome[oc].items() if slug not in SYNTHETIC]
        if not real:
            return None
        odds.append(median(real))
    probs = normalize_no_vig(odds)
    if all(p is not None for p in probs):
        return {oc: probs[i] for i, oc in enumerate(labels)}, "consensus_median"
    return None


def _soft_prices_sorted(outcome_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    prices = []
    for b in outcome_obj.get("bookmakers", []):
        slug = b.get("bookmaker_slug") or b.get("bookmaker")
        if slug in SYNTHETIC:
            continue
        o = safe_float(b.get("decimal_odds"), 0.0)
        if o > 1.01:
            prices.append({"book": slug, "odds": o,
                           "movement": (b.get("movement") or "").upper()})
    prices.sort(key=lambda x: x["odds"], reverse=True)
    return prices


def scan_sharp_value(compare: Dict[str, Any]) -> Tuple[List, List]:
    value_signals, steam_signals = [], []
    for ev in (compare.get("results") or compare.get("events") or []):
        meta = {k: ev.get(k) for k in ("event_id", "home_team", "away_team",
                                       "league", "event_date")}
        for market, mobj in ev.get("markets", {}).items():
            labels = MARKET_OUTCOMES.get(market)
            if not labels:
                continue
            outcomes = mobj.get("outcomes", {})
            if not all(oc in outcomes for oc in labels):
                continue
            fair = _sharp_fair_probs(market, outcomes)
            fair_probs, sharp_src = fair if fair else (None, None)

            for oc in labels:
                oobj = outcomes.get(oc, {})
                soft = _soft_prices_sorted(oobj)
                if not soft:
                    continue
                best = soft[0]
                n_short = sum(1 for b in oobj.get("bookmakers", [])
                              if (b.get("movement") or "").upper() == "SHORTENING")
                steamed = n_short >= STEAM_MIN_SHORTENING
                if steamed:
                    steam_signals.append({**meta, "market": market, "outcome": oc,
                                          "n_shortening": n_short,
                                          "best_odds": best["odds"], "best_book": best["book"],
                                          "note": "Bani sharp au intrat — cota se scurteaza"})
                if not (fair_probs and oc in fair_probs):
                    continue
                # filtru outlier: best price nu poate fi mult peste al 2-lea best
                if len(soft) >= 2 and best["odds"] > OUTLIER_RATIO * soft[1]["odds"]:
                    continue
                p = fair_probs[oc]
                ev_val = p * (best["odds"] - 1.0) - (1.0 - p)
                if not (MIN_EV <= ev_val <= MAX_EV):
                    continue
                k = kelly_fraction(p, best["odds"], KELLY_FRACTION, KELLY_CAP)
                value_signals.append({
                    **meta, "market": market, "outcome": oc,
                    "sharp_source": sharp_src,
                    "fair_prob_pct": round(p * 100, 1),
                    "fair_odd": round(1.0 / p, 3) if p > 0 else None,
                    "bet_odds": best["odds"], "bet_book": best["book"],
                    "ev_pct": round(ev_val * 100, 2),
                    "edge_pp": round((p - (1.0 / best["odds"])) * 100, 2),
                    "kelly_pct": round(k * 100, 2),
                    "steam_confirmed": steamed,
                })
    return value_signals, steam_signals


# ============================================================
# SURSA 3: ARBITRAJ (din best_odds.json — 551 evenimente)
# ============================================================
def scan_arbitrage(best_odds: Dict[str, Any]) -> List[Dict[str, Any]]:
    arbs = []
    now = datetime.now(timezone.utc)
    for r in (best_odds.get("results") or []):
        market = r.get("market")
        labels = BESTODDS_OUTCOMES.get(market)
        if not labels or market == "double_chance":  # DC nu e mutual exclusiv complet
            continue
        legs = {}
        stale = False
        for o in r.get("best_odds", []):
            oc = str(o.get("outcome"))
            odd = safe_float(o.get("decimal_odds"), 0.0)
            if oc in labels and odd > 1.01:
                dt = _parse_dt(o.get("updated_at"))
                if dt and (now - dt).total_seconds() / 3600.0 > STALE_HOURS:
                    stale = True
                legs[oc] = {"odds": odd, "book": o.get("bookmaker_slug"),
                            "updated_at": o.get("updated_at")}
        if stale or not all(oc in legs for oc in labels):
            continue
        inv = sum(1.0 / legs[oc]["odds"] for oc in labels)
        if inv < ARB_MARGIN:
            roi = round((1.0 / inv - 1.0) * 100, 2)
            arbs.append({
                "event_id": r.get("event_id"), "home_team": r.get("home_team"),
                "away_team": r.get("away_team"), "league": r.get("league_name"),
                "event_date": r.get("event_date"), "market": market,
                "type": "ARBITRAGE", "guaranteed_roi_pct": roi,
                "legs": [{"outcome": oc, "book": legs[oc]["book"],
                          "odds": legs[oc]["odds"],
                          "stake_pct": round(100.0 / legs[oc]["odds"] / inv, 2)}
                         for oc in labels]})
    return arbs


# ============================================================
# SURSA 4: POLYMARKET DIVERGENCE
# ============================================================
def _best_odds_index(best_odds: Dict[str, Any]) -> Dict[Tuple[Any, str], Dict[str, Any]]:
    idx = {}
    for r in (best_odds.get("results") or []):
        eid = r.get("event_id")
        market = r.get("market")
        for o in r.get("best_odds", []):
            idx[(eid, market, str(o.get("outcome")).lower())] = {
                "odds": safe_float(o.get("decimal_odds"), 0.0),
                "book": o.get("bookmaker_slug")}
    return idx


def scan_polymarket_divergence(poly: Dict[str, Any],
                               best_idx: Dict) -> List[Dict[str, Any]]:
    out = []
    # mapare piata polymarket -> (best_odds market, outcome_poly, outcome_bestodds)
    checks = [
        ("btts", "yes", "btts", "yes"),
        ("over_under", "over_25", "over_under_25", "over"),
        ("over_under", "under_25", "over_under_25", "under"),
        ("over_under", "over_15", "over_under_15", "over"),
    ]
    for r in (poly.get("results") or []):
        d = r.get("data", {})
        eid = r.get("event_id")
        markets = d.get("markets", {})
        meta = {k: r.get(k) for k in ("event_id", "home_team", "away_team",
                                      "league", "event_date")}
        for pm_market, pm_key, bo_market, bo_oc in checks:
            p_poly = markets.get(pm_market, {}).get(pm_key)
            if p_poly is None:
                continue
            bo = best_idx.get((eid, bo_market, bo_oc))
            if not bo or bo["odds"] <= 1.01:
                continue
            p_book = 1.0 / bo["odds"]  # implicit (cu marja)
            diff_pp = (safe_float(p_poly) - p_book) * 100
            if diff_pp >= POLY_DIVERGENCE_PP:
                # Polymarket crede MAI probabil decat pretul book -> value pe book
                ev_val = safe_float(p_poly) * (bo["odds"] - 1.0) - (1.0 - safe_float(p_poly))
                out.append({**meta, "market": bo_market, "outcome": bo_oc,
                            "poly_prob_pct": round(safe_float(p_poly) * 100, 1),
                            "book_implied_pct": round(p_book * 100, 1),
                            "divergence_pp": round(diff_pp, 1),
                            "bet_odds": bo["odds"], "bet_book": bo["book"],
                            "ev_vs_poly_pct": round(ev_val * 100, 2),
                            "note": "Polymarket (multime sharp) vede mai multa valoare decat book-ul soft"})
    return out


def main() -> int:
    compare = _load("compare_odds_cache.json", {})
    best_odds = _load("best_odds.json", {})
    poly = _load("polymarket.json", {})

    value, steam = scan_sharp_value(compare)
    arbs = scan_arbitrage(best_odds)
    best_idx = _best_odds_index(best_odds)
    poly_div = scan_polymarket_divergence(poly, best_idx)

    value.sort(key=lambda s: (s["steam_confirmed"], s["ev_pct"]), reverse=True)
    steam.sort(key=lambda s: s["n_shortening"], reverse=True)
    arbs.sort(key=lambda s: s["guaranteed_roi_pct"], reverse=True)
    poly_div.sort(key=lambda s: s["divergence_pp"], reverse=True)

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "sharp_value_engine_v7",
        "methodology": "Pinnacle no-vig = pret corect. Value = book soft > pret corect. "
                       "Steam = scurtare multi-book. Arbitraj = Sum(implicite) < 1. "
                       "Polymarket divergence = multime sharp vs book soft.",
        "config": {"min_ev_pct": MIN_EV * 100, "max_ev_pct": MAX_EV * 100,
                   "sharp_books": SHARP_BOOKS, "steam_min_shortening": STEAM_MIN_SHORTENING,
                   "poly_divergence_pp": POLY_DIVERGENCE_PP},
        "summary": {
            "value_signals": len(value),
            "steam_signals": len(steam),
            "arbitrage_ops": len(arbs),
            "polymarket_divergence": len(poly_div),
            "avg_value_ev_pct": round(sum(s["ev_pct"] for s in value) / len(value), 2)
                                 if value else 0.0,
        },
        "value_signals": value,
        "steam_signals": steam,
        "arbitrage": arbs,
        "polymarket_divergence": poly_div,
    }
    _atomic_write("sharp_value_signals.json", out)

    s = out["summary"]
    print(f"[sharp_value] value={s['value_signals']} (EV mediu {s['avg_value_ev_pct']}%) | "
          f"steam={s['steam_signals']} | arb={s['arbitrage_ops']} | "
          f"poly_div={s['polymarket_divergence']}")
    for v in value[:6]:
        print(f"  VALUE {v['home_team']} v {v['away_team']} | {v['market']}/{v['outcome']} "
              f"| {v['bet_odds']}@{v['bet_book']} vs fair {v['fair_odd']} | EV +{v['ev_pct']}%"
              f"{' | STEAM' if v['steam_confirmed'] else ''}")
    for a in arbs[:5]:
        print(f"  ARB   {a['home_team']} v {a['away_team']} | {a['market']} "
              f"| profit garantat +{a['guaranteed_roi_pct']}%")
    for p in poly_div[:4]:
        print(f"  POLY  {p['home_team']} v {p['away_team']} | {p['market']}/{p['outcome']} "
              f"| poly {p['poly_prob_pct']}% vs book {p['book_implied_pct']}% (+{p['divergence_pp']}pp)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
