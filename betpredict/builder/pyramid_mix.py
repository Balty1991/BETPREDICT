"""Piramide suplimentare cu selecții Robot + Supersocial, pe piste/bănci separate.

Pista Mix 1.40 urmărește o probabilitate mai mare pe pas. Pista Mix 2.5×5 păstrează ținta
mare, dar nu umple cota cu selecții repetitive: folosește prețuri reale, probabilități prudente,
diversificare pe familie/meci/ligă și se oprește dacă nu găsește valoare minimă.
"""

from __future__ import annotations

import itertools
import math
import sqlite3
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.builder import pyramid as P
from betpredict.builder.pool import Cand
from betpredict.builder import pyramid_risk as PR


RULES_MIX140: Dict[str, Any] = {
    **P.RULES_140,
    "target_odds": 1.40,
    "band": [1.35, 1.45],
    "max_legs": 1,
    "fallback_legs": 2,
    "min_leg_p": 0.68,
    "min_p": 0.66,
    "min_ev": 0.0,
    "leg_odds": [1.04, 1.40],
    "drift_max": 0.05,
    "start_bank": 2.0,
    "max_steps": 20,
    "suggest_at": 4,
    "variant": "pmix140",
    "alt_variant": "pmix140_alt",
    "min_ss_samples": 100,
    "min_ss_lift": 1.0,
}
KEY_MIX140 = "pyramidmix140.day."

RULES_MIX25: Dict[str, Any] = {
    **P.RULES_140,
    "target_odds": 2.5,
    "band": [2.50, 3.125],
    "min_legs": 1,
    "max_legs": 4,
    "fallback_legs": None,
    "min_leg_p": 0.42,
    "min_p": 0.42,
    "min_ev": 0.02,
    "leg_odds": [1.15, 3.0],
    "drift_max": 0.05,
    "no_night": True,
    "start_bank": 2.0,
    "max_steps": 5,
    "suggest_at": 5,
    "variant": "pmix25",
    "alt_variant": "pmix25_alt",
    "min_ss_samples": 100,
    "min_ss_lift": 1.0,
    "max_per_family": 1,
    "max_per_league": 2,
}
KEY_MIX25 = "pyramidmix25.day."


def mixed_candidates(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None) -> List[Cand]:
    """Candidați jucabili, numai cu cote Superbet curente; Supersocial intră doar după istoric suficient și lift ≥ 1."""
    from betpredict.experimental import supersocial as SS

    now = now or datetime.now(timezone.utc)
    core_markets = {("1x2", 0.0), ("draw_no_bet", 0.0), ("btts", 0.0)}
    core = [
        c for c in P.load_pool(conn, day, now, min_odds=1.04)
        if (c.market, float(c.line or 0.0)) in core_markets
        and c.healthy and c.odds_source == "superbet" and c.p is not None
    ]

    # Boost-uri obișnuite cu EV pozitiv sunt prețuri reale; Super Cota nu intră aici.
    boosts = [c for c in P.boost_cands(conn, day, now) if c.odds_source == "superbet" and c.ev > 0]

    lift = SS.key_lift(conn)
    league_lift = SS.league_lift(conn, lift)
    min_n = max(100, int(getattr(SS, "LIFT_MIN_N", 30)))
    min_lift = 1.0
    names = {r[0]: r[1] for r in conn.execute("SELECT id, name FROM league")}
    social: List[Cand] = []
    for c in PR.offer_pool(conn, day, now):
        lf = lift.get(c.selection)
        if c.odds_source != "superbet" or not lf or lf.get("n", 0) < min_n or lf.get("lift", 0) < min_lift:
            continue
        lg = league_lift.get((c.selection, c.league_id))
        p_real = SS.realistic_p({"key": c.selection, "odds": c.odds, "league_f": lg[0] if lg else 1.0}, lift)
        # Supersocial: probabilitatea prudentă înlocuiește scorul brut al modelului în selector.
        c.p = p_real
        c.p_market = p_real
        c.ev = p_real * c.odds - 1
        c.league = c.league or names.get(c.league_id)
        social.append(c)
    return core + boosts + social


def build_mix140_day(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None) -> Dict[str, Any]:
    rel = P.reliability(conn)

    def picker(_pool: List[Cand], rules: Dict[str, Any]) -> Dict[str, Any]:
        return P.pick_pyramid_140(mixed_candidates(conn, day, now), rules, rel)

    return P._build_track_day(conn, day, now, False, "pyramidmix140", KEY_MIX140, RULES_MIX140, picker, "pmix140")


def _market_family(c: Cand) -> str:
    return PR.fam(c)


def pick_mix25(pool: List[Cand], rules: Dict[str, Any] = RULES_MIX25, rel: Optional[Dict] = None) -> Dict[str, Any]:
    """Optimizează șansa prudentă a unui bilet de cotă 2.50–3.125, fără repetarea familiilor pe același bilet."""
    lo, hi = rules["band"]
    leg_lo, leg_hi = rules["leg_odds"]
    by_match: Dict[int, List[Tuple[Cand, float]]] = {}
    for c in pool:
        if c.odds_source != "superbet" or not (leg_lo <= c.odds <= leg_hi) or not c.playable:
            continue
        if not c.healthy or c.p is None or (rules.get("no_night") and PR.night_kickoff(c.kickoff_utc)):
            continue
        if c.market != "ss" and not c.healthy:
            continue
        q = P.q_leg(c, rel)
        if q < rules["min_leg_p"] or q * c.odds <= 1.0:
            continue
        by_match.setdefault(c.match_id, []).append((c, q))

    # Păstrează numai câteva alternative bune pe meci; rezultă un spațiu de căutare mic și explicit.
    candidates: List[Tuple[Cand, float]] = []
    for options in by_match.values():
        options.sort(key=lambda x: (x[1], x[1] * x[0].odds), reverse=True)
        candidates.extend(options[:3])
    candidates.sort(key=lambda x: (x[1], x[1] * x[0].odds), reverse=True)
    candidates = candidates[:36]

    found = []
    for n in range(1, min(rules["max_legs"], len(candidates)) + 1):
        for combo in itertools.combinations(candidates, n):
            legs = [x[0] for x in combo]
            if len({c.match_id for c in legs}) != n:
                continue
            families = [_market_family(c) for c in legs]
            if len(set(families)) != n:  # nu se multiplică același tip de pariu pe bilet
                continue
            leagues = [c.league_id for c in legs if c.league_id is not None]
            if any(count > rules["max_per_league"] for count in Counter(leagues).values()):
                continue
            odds = math.prod(c.odds for c in legs)
            if not (lo <= odds <= hi):
                continue
            p = math.prod(x[1] for x in combo)
            ev = p * odds - 1
            if p < rules["min_p"] or ev < rules["min_ev"]:
                continue
            if not any(c.market == "ss" for c in legs) or not any(c.market != "ss" for c in legs):
                continue  # Mix 2.5×5 înseamnă amestec efectiv, nu doar două surse în același pool
            # Prioritatea este șansa de câștig; apoi EV și mai puține selecții.
            found.append((legs, p, odds, ev))

    if not found:
        return {"status": "no_bet", "main": None, "alternatives": [],
                "reason": (f"Azi pauză la Piramida Mix 2.5×5: nu există bilet la cota {lo:.2f}–{hi:.3f} "
                           f"cu șansă prudentă ≥{rules['min_p']:.0%} și EV ≥{rules['min_ev']:+.0%}. Nu forțăm selecții.")}
    found.sort(key=lambda x: (round(x[1], 6), x[3], -len(x[0])), reverse=True)
    legs, p, odds, ev = found[0]
    return {"status": "pick", "main": (legs, p), "alternatives": [],
            "reason": (f"Mix Robot + Supersocial: {len(legs)} selecții din meciuri diferite și familii distincte, "
                       f"cotă {odds:.2f}, șansă prudentă {p:.0%}, EV estimat {ev:+.1%}. Miză de start fixă; "
                       "șansa reală poate diferi de estimare.")}


def build_mix25_day(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None) -> Dict[str, Any]:
    rel = P.reliability(conn)

    def picker(_pool: List[Cand], rules: Dict[str, Any]) -> Dict[str, Any]:
        return pick_mix25(mixed_candidates(conn, day, now), rules, rel)

    return P._build_track_day(conn, day, now, False, "pyramidmix25", KEY_MIX25, RULES_MIX25, picker, "pmix25")
