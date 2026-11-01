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
from typing import Any, Dict, List, Optional, Sequence, Tuple

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

RULES_GOAL130: Dict[str, Any] = {
    **P.RULES_140,
    "target_odds": 1.55,
    "band": [1.50, 1.70],
    "min_legs": 1,
    "max_legs": 3,
    "fallback_legs": None,
    # Fără prag de EV pe model. Obiectivul e șansa comună fără marjă; modelul doar veto.
    "min_leg_p": 0.0,
    "min_p": 0.0,
    "min_ev": -1.0,
    "leg_odds": [1.12, 1.70],
    "drift_max": 0.02,
    "latest_hour_ro": 21,
    "start_bank": 2.0,
    "max_steps": 20,
    "suggest_at": 4,
    "variant": "pgoal130",
    "alt_variant": "pgoal130_alt",
    "min_ss_samples": 100,
    "min_ss_lift": 1.0,
    "max_per_league": 3,
}
KEY_GOAL130 = "pyramidgoal130.day."

# Explicit allowlists: this track is only for goal markets, not cards/corners or result bets.
GOAL_SS_KEYS = {
    "HO05", "AO05", "HO15", "AO15", "HG13", "AG13", "G13", "G24", "G25",
    "BB_HG13_U35", "BB_AG13_U35", "BB_HG14_U45", "BB_AG14_U45",
    "GG", "GGO25", "H1O05", "H1O15", "H2G13", "R1O15", "R1O25", "H13x2",
}


def _robot_goal_market(c: Cand) -> bool:
    if c.market == "double_chance":
        return float(c.line or 0.0) == 0.0 and c.selection == "12"
    if c.market == "btts":
        return float(c.line or 0.0) == 0.0 and c.selection in {"YES", "NO"}
    if c.market == "over_under":
        return 0.5 <= float(c.line or 0.0) <= 4.5 and c.selection in {"OVER", "UNDER"}
    if c.market in {"team_total_home", "team_total_away"}:
        return float(c.line or 0.0) in {0.5, 1.5, 2.5} and c.selection == "OVER"
    return False


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


def _variance_market(c: Cand) -> bool:
    """Cornere și cartonașe: varianță mare. Intră doar dacă istoricul le susține."""
    if c.market in {"corners", "cards"}:
        return True
    if c.market != "ss":
        return False
    from betpredict.experimental.supersocial import family as ss_family

    return ss_family(c.selection) in {"cornere", "cartonase"}


def _well_supported(c: Cand, rules: Dict[str, Any]) -> bool:
    extra = c.extra or {}
    n = extra.get("ss_n")
    lift = extra.get("ss_lift")
    return n is not None and lift is not None and n >= rules["min_ss_samples"] and lift >= rules["min_ss_lift"]


def _late_kickoff(c: Cand, latest_hour: int) -> bool:
    """Start târziu (sau noaptea) amână decontarea treptei până a doua zi."""
    if PR.night_kickoff(c.kickoff_utc):
        return True
    try:
        from zoneinfo import ZoneInfo

        k = datetime.fromisoformat((c.kickoff_utc or "").replace("Z", "+00:00"))
        if k.tzinfo is None:
            k = k.replace(tzinfo=timezone.utc)
        return k.astimezone(ZoneInfo("Europe/Bucharest")).hour >= latest_hour
    except (ValueError, KeyError):
        return False


def _model_veto(c: Cand) -> bool:
    """Modelul nu alege partea. O scoate doar când e mult sub prețul fără marjă."""
    from betpredict.model.match_select import VETO_GAP

    pm = c.p_market
    if pm is None or not (0 < pm < 1) or c.p is None:
        return False
    return float(c.p) < float(pm) - VETO_GAP


def next_check_label(now: Optional[datetime] = None) -> str:
    """Următorul slot de publicare: 00, 06, 12 sau 18, ora României."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Bucharest")
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    for hour in (0, 6, 12, 18):
        cand = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if cand > now:
            return f"Următoarea verificare: {hour:02d}:00, ora României."
    return "Următoarea verificare: 00:00, ora României."


def goal130_candidates(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None) -> List[Cand]:
    """Selecții cu preț Superbet real: piețe lichide (1X2, șansă dublă, goluri) plus Supersocial.

    Cornerele și cartonașele intră doar dacă au cel puțin 100 de rezultate și lift ≥ 1.
    """
    from betpredict.experimental import supersocial as SS

    now = now or datetime.now(timezone.utc)
    lo = RULES_GOAL130["leg_odds"][0]
    robot = [
        c for c in P.load_pool(conn, day, now, min_odds=lo)
        if c.healthy and c.odds_source == "superbet" and c.p is not None
        and (c.market in {"1x2", "double_chance", "draw_no_bet", "btts", "over_under"} or _robot_goal_market(c))
        and not _variance_market(c)
    ]
    lift = SS.key_lift(conn)
    social: List[Cand] = []
    names = {r[0]: r[1] for r in conn.execute("SELECT id, name FROM league")}
    for c in PR.offer_pool(conn, day, now):
        if c.odds_source != "superbet":
            continue
        lf = lift.get(c.selection) or {}
        c.extra = {**(c.extra or {}), "ss_n": lf.get("n") or 0, "ss_lift": lf.get("lift")}
        if _variance_market(c) and not _well_supported(c, RULES_GOAL130):
            continue
        c.league = c.league or names.get(c.league_id)
        if c.p_market is None:
            c.p_market = c.p_mkt
        social.append(c)
    return robot + social


def pick_goal130(pool: List[Cand], rules: Dict[str, Any] = RULES_GOAL130, rel: Optional[Dict] = None) -> Dict[str, Any]:
    """1–3 selecții, cotă totală 1.50–1.70, șansa comună fără marjă maximă.

    La egalitate: mai puține selecții, apoi capătul de jos al benzii, apoi ligi mari.
    ``rel`` rămâne în semnătură ca să poată fi apelat din aceeași interfață ca celelalte piste.
    """
    del rel
    lo, hi = rules["band"]
    leg_lo, leg_hi = rules["leg_odds"]
    latest = int(rules.get("latest_hour_ro") or 21)
    from betpredict.model.calib import league_group

    diag = {"pool": len(pool), "supported_market": 0, "playable_price": 0, "leg_probability": 0,
            "joint_combinations": 0, "joint_evaluated": 0, "rejected_joint_probability": 0,
            "rejected_ev": 0, "veto": 0, "drift": 0, "late": 0, "variance": 0}
    by_match: Dict[int, List[Cand]] = {}
    for c in pool:
        if c.odds_source != "superbet" or not c.healthy or c.price_suspect:
            continue
        if not (leg_lo <= c.odds <= leg_hi):
            continue
        diag["supported_market"] += 1
        if c.drift is not None and c.drift > rules["drift_max"]:
            diag["drift"] += 1
            continue
        if _late_kickoff(c, latest):
            diag["late"] += 1
            continue
        if _variance_market(c) and not _well_supported(c, rules):
            diag["variance"] += 1
            continue
        if _model_veto(c):
            diag["veto"] += 1
            continue
        diag["playable_price"] += 1
        by_match.setdefault(c.match_id, []).append(c)

    one: List[Cand] = []
    for options in by_match.values():
        options.sort(key=lambda c: (c.p_mkt, league_group(c.league_id) == "top", -c.odds), reverse=True)
        one.append(options[0])
    one.sort(key=lambda c: c.p_mkt, reverse=True)
    one = one[:24]
    diag["leg_probability"] = len(one)

    found: List[Tuple[List[Cand], float, float]] = []
    for n in range(rules["min_legs"], min(rules["max_legs"], len(one)) + 1):
        for combo in itertools.combinations(one, n):
            legs = list(combo)
            if len({c.match_id for c in legs}) != n:
                continue
            odds = math.prod(c.odds for c in legs)
            if not lo <= odds <= hi:
                continue
            p = math.prod(c.p_mkt for c in legs)
            diag["joint_combinations"] += 1
            found.append((legs, p, odds))
    diag["joint_evaluated"] = len(found)

    if not found:
        return {
            "status": "no_bet", "main": None, "alternatives": [],
            "diagnostics": diag,
            "step_p": None,
            "reason": (f"Nicio selecție azi. Nu există 1–{rules['max_legs']} selecții cu cotă totală "
                       f"{lo:.2f}–{hi:.2f} după veto-ul modelului, fără cote lungite și fără start după ora {latest}. "
                       f"Pool {diag['pool']} · eligibile {diag['leg_probability']} · în bandă {diag['joint_combinations']} "
                       f"(veto {diag['veto']}, drift {diag['drift']}, start târziu {diag['late']}). "
                       f"{next_check_label()}"),
        }

    def rank(item: Tuple[List[Cand], float, float]):
        legs, p, odds = item
        top = sum(1 for c in legs if league_group(c.league_id) == "top")
        variance = sum(1 for c in legs if _variance_market(c))
        last = max((c.kickoff_utc or "") for c in legs)
        # Șansa comună întâi. La egalitate: mai puține selecții, cota mai aproape de 1.50,
        # mai multe ligi mari, fără cornere/cartonașe, start mai devreme.
        return (-round(p, 6), len(legs), odds, -top, variance, last)

    found.sort(key=rank)
    legs, p, odds = found[0]
    return {
        "status": "pick", "main": (legs, p), "alternatives": [],
        "diagnostics": diag,
        "step_p": round(p, 4),
        "reach_cashout": round(p ** int(rules.get("suggest_at") or 4), 4),
        "reason": (f"{len(legs)} {'selecție' if len(legs) == 1 else 'selecții'}, un meci o dată · cotă {odds:.2f} "
                   f"(bandă {lo:.2f}–{hi:.2f}) · șansă fără marjă {p:.1%}. "
                   f"La {rules.get('suggest_at', 4)} pași la rând, șansa cumulată e {p ** int(rules.get('suggest_at') or 4):.1%}. "
                   "Alege șansa comună maximă; la egalitate, mai puține selecții și cota mai aproape de 1.50."),
    }


def streak_backtest(days: Sequence[Tuple[Sequence[Cand], Dict[int, str]]], rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Reia regula pe zile istorice. Un pas e câștigat doar dacă toate selecțiile alese au intrat."""
    rules = rules or RULES_GOAL130
    played: List[bool] = []
    ps: List[float] = []
    odds_l: List[float] = []
    legs_n: List[int] = []
    for pool, results in days:
        pick = pick_goal130(list(pool), rules)
        if pick["status"] != "pick" or not pick.get("main"):
            continue
        legs, p = pick["main"]
        won = all(results.get(c.prediction_id) == "won" for c in legs)
        played.append(won)
        ps.append(float(p))
        odds_l.append(math.prod(c.odds for c in legs))
        legs_n.append(len(legs))
    closed: List[int] = []
    run = 0
    for won in played:
        if won:
            run += 1
        else:
            closed.append(run)
            run = 0
    if played and played[-1]:
        closed.append(run)
    dist: Dict[int, int] = {}
    for s in closed:
        dist[s] = dist.get(s, 0) + 1
    runs_n = len(closed)
    reach: Dict[str, float] = {}
    if runs_n:
        for k in range(1, max(closed) + 1):
            reach[str(k)] = round(sum(1 for s in closed if s >= k) / runs_n, 3)
    cash = int(rules.get("suggest_at") or 4)
    ordered = sorted(closed)
    return {
        "days": len(played),
        "win_rate": round(sum(played) / len(played), 4) if played else None,
        "avg_p": round(sum(ps) / len(ps), 4) if ps else None,
        "avg_odds": round(sum(odds_l) / len(odds_l), 3) if odds_l else None,
        "avg_legs": round(sum(legs_n) / len(legs_n), 2) if legs_n else None,
        "runs": runs_n,
        "avg_steps": round(sum(closed) / runs_n, 2) if runs_n else None,
        "median_steps": ordered[runs_n // 2] if runs_n else None,
        "max_steps": max(closed) if closed else None,
        "distribution": [{"steps": k, "runs": dist[k]} for k in sorted(dist)],
        "reach_probability": reach,
        "reach_cashout": reach.get(str(cash)),
        "cashout_step": cash,
        "note": "Regula de azi, reluată pe zilele decontate: șansă comună fără marjă maximă în banda 1.50–1.70, 1–3 selecții.",
    }


def streak_backtest_doc(conn: sqlite3.Connection, days: int = 90) -> Optional[Dict[str, Any]]:
    """Backtest pe predicțiile Superbet decontate. None dacă nu există destule zile."""
    from datetime import timedelta

    since = (date.today() - timedelta(days=days)).isoformat()
    try:
        rows = conn.execute(
            """SELECT p.id, p.day, p.match_id, p.market, p.line, p.selection, p.odds_shown, p.p_calibrated,
                      p.p_market_novig, p.result, m.kickoff_utc, m.league_id, m.home_name, m.away_name
               FROM prediction p JOIN match m ON m.id = p.match_id
               WHERE p.result IN ('won','lost') AND p.odds_source = 'superbet' AND p.odds_shown >= ?
                 AND p.day >= ? AND p.p_calibrated IS NOT NULL""",
            (RULES_GOAL130["leg_odds"][0], since)).fetchall()
    except sqlite3.Error:
        return None
    by_day: Dict[str, List[Tuple[Cand, str]]] = {}
    for r in rows:
        market, line = r["market"], float(r["line"] or 0)
        if market not in {"1x2", "double_chance", "draw_no_bet", "btts", "over_under", "team_total_home", "team_total_away"}:
            continue
        c = Cand(r["id"], r["match_id"], r["league_id"], None, r["kickoff_utc"] or "", r["home_name"], r["away_name"],
                 market, line, r["selection"], r["odds_shown"], r["p_calibrated"],
                 r["p_calibrated"] * r["odds_shown"] - 1, "B", 60, True,
                 p_market=r["p_market_novig"], odds_source="superbet")
        by_day.setdefault(r["day"], []).append((c, r["result"]))
    packed = []
    for day_s in sorted(by_day):
        pool = [c for c, _ in by_day[day_s]]
        results = {c.prediction_id: res for c, res in by_day[day_s]}
        packed.append((pool, results))
    if len(packed) < 8:
        return None
    doc = streak_backtest(packed)
    doc["from"] = min(by_day)
    doc["to"] = max(by_day)
    return doc


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


def build_goal130_day(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None) -> Dict[str, Any]:
    rel = P.reliability(conn)

    def picker(_pool: List[Cand], rules: Dict[str, Any]) -> Dict[str, Any]:
        return pick_goal130(goal130_candidates(conn, day, now), rules, rel)

    return P._build_track_day(conn, day, now, False, "pyramidgoal130", KEY_GOAL130, RULES_GOAL130, picker, "pgoal130")
