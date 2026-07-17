#!/usr/bin/env python3
"""
sharp_value_engine.py  — BetPredict v7 flagship strategy
=========================================================

Ideea centrala (schimbare de paradigma fata de v6):
  NU incercam sa "prezicem mai bine decat piata" cu un model ML slab
  (AUC 0.583, CLV -1.35%). In schimb HARVESTAM edge-ul care exista DEJA
  in datele colectate: pretul bookmaker-ului sharp (Pinnacle) ca "adevar",
  vs. bookmaker-ii soft care gresesc pretul.

Trei surse de profit, toate independente de calitatea modelului nostru:

  1. SHARP-VALUE  — Pinnacle no-vig = probabilitate corecta. Cand un book
     soft ofera o cota mai mare decat cota corecta => EV pozitiv REAL,
     demonstrabil prin CLV. Aceasta este singura metoda dovedita statistic
     de a bate pariurile pe termen lung.

  2. STEAM / DROP — cand cota se scurteaza (SHORTENING) la multi bookmaker-i
     simultan, banii sharp au intrat. Prindem miscarea devreme, inainte ca
     book-ul soft sa se ajusteze.

  3. ARBITRAJ / MIDDLE — cu 17 bookmakeri per eveniment, uneori suma
     probabilitatilor implicite ale celor mai bune cote < 1 => profit
     garantat indiferent de rezultat.

Input:  data/compare_odds_cache.json  (odds per-bookmaker, adancime completa)
        data/best_odds.json           (best price per outcome, 551 evenimente)
Output: data/sharp_value_signals.json

Ruleaza standalone:  python3 src/sharp_value_engine.py
"""
from __future__ import annotations
import json, os, sys, tempfile
from datetime import datetime, timezone
from statistics import median
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

# analytics_core e in root
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
# Bookmaker-i "sharp" in ordinea increderii. Pinnacle = etalon aur.
SHARP_BOOKS = ["pinnacle", "marathon", "betfair", "1xbet"]
# Consensus-uri agregate (nu sunt bookmaker-i reali de pariat)
SYNTHETIC = {"consensus", "oddssafari-consensus"}

MIN_EV = 0.02          # 2% EV minim vs. pretul sharp
MIN_SHARP_BOOKS = 1    # cati sharp books minim pentru o ancora de incredere
STEAM_MIN_SHORTENING = 4  # cati book-i trebuie sa scurteze pentru semnal steam
KELLY_FRACTION = 0.25
KELLY_CAP = 0.05

# Seturile de outcome-uri mutual exclusive per piata (pentru de-vig si arbitraj)
MARKET_OUTCOMES = {
    "1x2": ["HOME", "DRAW", "AWAY"],
    "btts": ["YES", "NO"],
    "over_under_15": ["OVER", "UNDER"],
    "over_under_25": ["OVER", "UNDER"],
    "over_under_35": ["OVER", "UNDER"],
}


def _load(name: str) -> Any:
    p = os.path.join(DATA, name)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


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


def _book_odds_map(outcome_obj: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """slug -> {odds, movement} pentru un outcome."""
    out = {}
    for b in outcome_obj.get("bookmakers", []):
        slug = b.get("bookmaker_slug") or b.get("bookmaker")
        o = safe_float(b.get("decimal_odds"), 0.0)
        if slug and o > 1.01:
            out[slug] = {"odds": o, "movement": b.get("movement") or ""}
    return out


def _sharp_fair_probs(market: str, outcomes: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """
    Probabilitatea corecta (no-vig) derivata din bookmaker-ul sharp.
    Preferam Pinnacle; daca lipseste, cel mai bun sharp disponibil;
    fallback = consensus median al TUTUROR book-ilor reali.
    """
    labels = MARKET_OUTCOMES.get(market)
    if not labels:
        return None

    # 1) incearca fiecare sharp book: are cota pe TOATE outcome-urile?
    per_outcome_books = {oc: _book_odds_map(outcomes.get(oc, {})) for oc in labels}

    for sharp in SHARP_BOOKS:
        if all(sharp in per_outcome_books[oc] for oc in labels):
            odds = [per_outcome_books[oc][sharp]["odds"] for oc in labels]
            probs = normalize_no_vig(odds)
            if all(p is not None for p in probs):
                return {oc: probs[i] for i, oc in enumerate(labels)}, sharp  # type: ignore

    # 2) fallback: consensus median al book-ilor reali (non-sintetici)
    odds = []
    for oc in labels:
        real = [v["odds"] for slug, v in per_outcome_books[oc].items()
                if slug not in SYNTHETIC]
        if not real:
            return None
        odds.append(median(real))
    probs = normalize_no_vig(odds)
    if all(p is not None for p in probs):
        return {oc: probs[i] for i, oc in enumerate(labels)}, "consensus_median"  # type: ignore
    return None


def _best_soft_price(outcome_obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Cea mai mare cota oferita de un book REAL (exclude sinteticele)."""
    best = None
    for b in outcome_obj.get("bookmakers", []):
        slug = b.get("bookmaker_slug") or b.get("bookmaker")
        if slug in SYNTHETIC:
            continue
        o = safe_float(b.get("decimal_odds"), 0.0)
        if o > 1.01 and (best is None or o > best["odds"]):
            best = {"book": slug, "odds": o, "movement": b.get("movement") or ""}
    return best


def analyze_event(ev: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    value_signals, steam_signals, arbs = [], [], []
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
        if fair:
            fair_probs, sharp_src = fair
        else:
            fair_probs, sharp_src = None, None

        # ---- ARBITRAJ: suma implicitelor celor mai bune cote < 1 ----
        best_prices = {oc: _best_soft_price(outcomes.get(oc, {})) for oc in labels}
        if all(best_prices[oc] for oc in labels):
            inv = sum(1.0 / best_prices[oc]["odds"] for oc in labels)
            if inv < 0.9985:  # margine de siguranta pentru rotunjiri
                roi = round((1.0 / inv - 1.0) * 100, 2)
                arbs.append({**meta, "market": market, "type": "ARBITRAGE",
                             "guaranteed_roi_pct": roi,
                             "legs": [{"outcome": oc, "book": best_prices[oc]["book"],
                                       "odds": best_prices[oc]["odds"],
                                       "stake_pct": round(100.0/best_prices[oc]["odds"]/inv, 2)}
                                      for oc in labels]})

        # ---- VALUE + STEAM per outcome ----
        for oc in labels:
            oobj = outcomes.get(oc, {})
            best = _best_soft_price(oobj)
            if not best:
                continue

            # STEAM: cati book-i scurteaza cota
            n_short = sum(1 for b in oobj.get("bookmakers", [])
                          if (b.get("movement") or "").upper() == "SHORTENING")
            if n_short >= STEAM_MIN_SHORTENING:
                steam_signals.append({**meta, "market": market, "outcome": oc,
                                      "n_shortening": n_short,
                                      "best_odds": best["odds"], "best_book": best["book"],
                                      "note": "Bani sharp au intrat — cota se scurteaza la multi book-i"})

            # VALUE vs. sharp fair
            if fair_probs and oc in fair_probs:
                p = fair_probs[oc]
                ev_val = p * (best["odds"] - 1.0) - (1.0 - p)
                if ev_val >= MIN_EV:
                    fair_odd = round(1.0 / p, 3) if p > 0 else None
                    k = kelly_fraction(p, best["odds"], KELLY_FRACTION, KELLY_CAP)
                    value_signals.append({
                        **meta, "market": market, "outcome": oc,
                        "sharp_source": sharp_src,
                        "fair_prob_pct": round(p * 100, 1),
                        "fair_odd": fair_odd,
                        "bet_odds": best["odds"], "bet_book": best["book"],
                        "ev_pct": round(ev_val * 100, 2),
                        "edge_pp": round((p - (1.0 / best["odds"])) * 100, 2),
                        "kelly_pct": round(k * 100, 2),
                        "steam_confirmed": n_short >= STEAM_MIN_SHORTENING,
                    })
    return {"value": value_signals, "steam": steam_signals, "arbs": arbs}


def main() -> int:
    try:
        compare = _load("compare_odds_cache.json")
    except Exception as e:
        print(f"[sharp_value] FATAL: nu pot citi compare_odds_cache.json: {e}")
        return 1

    events = compare.get("results") or compare.get("events") or []
    all_value, all_steam, all_arbs = [], [], []
    for ev in events:
        r = analyze_event(ev)
        all_value += r["value"]
        all_steam += r["steam"]
        all_arbs += r["arbs"]

    # ranking: EV, apoi confirmare steam
    all_value.sort(key=lambda s: (s["steam_confirmed"], s["ev_pct"]), reverse=True)
    all_steam.sort(key=lambda s: s["n_shortening"], reverse=True)
    all_arbs.sort(key=lambda s: s["guaranteed_roi_pct"], reverse=True)

    out = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "sharp_value_engine_v7",
        "methodology": "Pinnacle no-vig = pret corect. Value = book soft > pret corect. "
                       "Steam = scurtare multi-book. Arbitraj = suma implicite < 1.",
        "config": {"min_ev_pct": MIN_EV * 100, "sharp_books": SHARP_BOOKS,
                   "steam_min_shortening": STEAM_MIN_SHORTENING},
        "summary": {
            "events_scanned": len(events),
            "value_signals": len(all_value),
            "steam_signals": len(all_steam),
            "arbitrage_ops": len(all_arbs),
            "avg_value_ev_pct": round(sum(s["ev_pct"] for s in all_value) / len(all_value), 2)
                                 if all_value else 0.0,
        },
        "value_signals": all_value,
        "steam_signals": all_steam,
        "arbitrage": all_arbs,
    }
    _atomic_write("sharp_value_signals.json", out)

    s = out["summary"]
    print(f"[sharp_value] {s['events_scanned']} evenimente | "
          f"{s['value_signals']} value (EV mediu {s['avg_value_ev_pct']}%) | "
          f"{s['steam_signals']} steam | {s['arbitrage_ops']} arbitraje")
    for v in all_value[:8]:
        print(f"  VALUE  {v['home_team']} vs {v['away_team']} | {v['market']}/{v['outcome']} "
              f"| bet {v['bet_odds']}@{v['bet_book']} vs fair {v['fair_odd']} "
              f"| EV +{v['ev_pct']}% | Kelly {v['kelly_pct']}%"
              f"{' | STEAM' if v['steam_confirmed'] else ''}")
    for a in all_arbs[:5]:
        print(f"  ARB    {a['home_team']} vs {a['away_team']} | {a['market']} "
              f"| profit garantat +{a['guaranteed_roi_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
