"""Profil selectabil. Nu înlocuiește biletele implicite și nu relaxează pragurile.

Preferințe: doar fotbal, cotă pe selecție ≥ 1.40, piețe Peste/Sub și Șansă Dublă,
maximum 4 selecții, un singur eveniment pe meci. Piramida din profil țintește ~2.00,
maximum 5 pași și o bancă de 10 unități de simulare — nu lei și nu banca implicită.
Dacă nu există selecții cu EV onest pozitiv, rezultatul este „fără recomandare”.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence

PREFERINTE: Dict[str, Any] = {
    "id": "preferinte",
    "sport": "football",
    "min_leg_odds": 1.40,
    "markets": ("over_under", "double_chance"),
    "max_legs": 4,
    "min_ev": 0.0,
    "pyramid": {
        "target_odds": 2.0,
        "band": [1.85, 2.2],
        "max_legs": 4,
        "max_steps": 5,
        "start_bank_units": 10.0,
        "min_leg_odds": 1.40,
    },
}


def _ev(c) -> float:
    if getattr(c, "ev_honest", None) is not None:
        return float(c.ev_honest)
    p = getattr(c, "p_honest", None)
    if p is None:
        p = getattr(c, "p", None)
    if p is None:
        return -1.0
    return float(p) * float(c.odds) - 1


def explain_empty(pool: Sequence, profile: Dict[str, Any] = PREFERINTE) -> str:
    n = len(pool)
    if not n:
        return "Fără recomandare: nu există selecții în pool."
    markets = set(profile["markets"])
    low = sum(1 for c in pool if float(c.odds) < profile["min_leg_odds"])
    other = sum(1 for c in pool if c.market not in markets)
    neg = sum(1 for c in pool if c.market in markets and float(c.odds) >= profile["min_leg_odds"] and _ev(c) <= profile["min_ev"])
    return (
        f"Fără recomandare în profilul {profile['id']}: {n} selecții, "
        f"{other} în afara Peste/Sub și Șansă Dublă, {low} sub cota {profile['min_leg_odds']:.2f}, "
        f"{neg} cu EV onest ≤ {profile['min_ev']}. Pragurile nu se relaxează."
    )


def select_profile(pool: Sequence, profile: Dict[str, Any] = PREFERINTE) -> Dict[str, Any]:
    """Un singur bilet sau no_bet. Nu pune 1X2 împreună cu șansă dublă: piețele profilului exclud 1X2."""
    markets = set(profile["markets"])
    best: Dict[Any, Any] = {}
    dropped_same_match = 0
    for c in pool:
        if getattr(c, "sport", "football") != profile["sport"]:
            continue
        if c.market not in markets or float(c.odds) < profile["min_leg_odds"]:
            continue
        if _ev(c) <= profile["min_ev"]:
            continue
        if getattr(c, "healthy", True) is False:
            continue
        prev = best.get(c.match_id)
        if prev is None or _ev(c) > _ev(prev):
            if prev is not None:
                dropped_same_match += 1
            best[c.match_id] = c
        else:
            dropped_same_match += 1
    ranked = sorted(best.values(), key=_ev, reverse=True)[: int(profile["max_legs"])]
    if not ranked:
        return {"status": "no_bet", "reason": explain_empty(pool, profile), "legs": [], "same_match_dropped": dropped_same_match}
    # adaugă cât EV-ul biletului rămâne strict pozitiv; nu umple până la 4 cu prețul EV-ului
    legs: List[Any] = []
    for c in ranked:
        trial = legs + [c]
        p = math.prod(float(getattr(x, "p_honest", getattr(x, "p"))) for x in trial)
        o = math.prod(float(x.odds) for x in trial)
        if p * o - 1 <= profile["min_ev"]:
            continue
        legs = trial
    if not legs:
        return {"status": "no_bet", "reason": explain_empty(pool, profile), "legs": [], "same_match_dropped": dropped_same_match}
    p = math.prod(float(getattr(x, "p_honest", getattr(x, "p"))) for x in legs)
    o = math.prod(float(x.odds) for x in legs)
    leagues = [getattr(c, "league_id", None) for c in legs]
    known = [i for i in leagues if i is not None]
    return {
        "status": "pick",
        "reason": f"Profil {profile['id']}: {len(legs)} selecții, cotă {o:.2f}, EV onest {p * o - 1:+.1%}. Nu este o garanție.",
        "legs": legs,
        "total_odds": o,
        "p": p,
        "ev": p * o - 1,
        "same_match_dropped": dropped_same_match,
        "same_league": len(known) != len(set(known)),
        "pyramid": profile["pyramid"],
    }
