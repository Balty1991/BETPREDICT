"""O selecție Bet Builder pe meci, doar cu preț public Superbet și scor final.

Nu intră marcatori, cornere sau „conduce oricând”: pe alea nu avem decontare sigură.
Probabilitatea e grila Poisson pe λ-urile robotului. Cota și modelul trebuie să fie aproape
(±12%), altfel combinația e ori prea scumpă, ori prețul e suspect.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from betpredict.builder.pool import Cand
from betpredict.robot import MODEL_VERSION
from betpredict.timeutil import canon_utc

ODDS = (2.20, 4.50)
MARKETS = (
    "1X2 & GG",
    "Șansă dublă & GG",
    "Total goluri & GG",
    "1X2 & Interval goluri",
    "Șansă dublă & Interval goluri",
)
# 1X2 / șansă dublă & total au linia în nume: „(2.5)”, „(1.5)”…


def _pois(lam: float, n: int = 9) -> List[float]:
    p = math.exp(-lam)
    out = [p]
    for i in range(1, n):
        p *= lam / i
        out.append(p)
    out[-1] += max(0.0, 1.0 - sum(out))
    return out


def _grid(lh: float, la: float) -> List[List[float]]:
    ph, pa = _pois(lh), _pois(la)
    return [[ph[i] * pa[j] for j in range(len(pa))] for i in range(len(ph))]


def _side_ok(code: str, h: int, a: int) -> bool:
    if code == "1":
        return h > a
    if code == "2":
        return h < a
    if code == "x":
        return h == a
    if code == "1x":
        return h >= a
    if code == "x2":
        return h <= a
    if code == "12":
        return h != a
    return False


def _goals_ok(text: str, total: int) -> Optional[bool]:
    t = text.strip().lower()
    if t.startswith("peste "):
        return total > float(t.split()[1])
    if t.startswith("sub "):
        return total < float(t.split()[1])
    if "-" in t and t.replace("-", "").isdigit():
        lo, hi = t.split("-", 1)
        return int(lo) <= total <= int(hi)
    return None


def hits(market: str, outcome: str, h: int, a: int) -> Optional[bool]:
    """True/False pe scorul final. None dacă nu știm să decontăm combinația."""
    mn = market.lower()
    oc = outcome.strip()
    total = h + a
    if mn.startswith("1x2 & total goluri") or mn.startswith("șansă dublă & total goluri") or mn.startswith("sansa dubla & total goluri"):
        side, _, goals = oc.partition(" & ")
        g = _goals_ok(goals, total)
        return None if g is None else _side_ok(side.lower(), h, a) and g
    if mn in ("1x2 & gg", "șansă dublă & gg", "sansa dubla & gg"):
        side, _, gg = oc.partition(" & ")
        both = h > 0 and a > 0
        if gg.lower() == "da":
            flag = both
        elif gg.lower() == "nu":
            flag = not both
        else:
            return None
        return _side_ok(side.lower(), h, a) and flag
    if mn == "total goluri & gg":
        goals, _, gg = oc.partition(" & ")
        g = _goals_ok(goals, total)
        if g is None:
            return None
        both = h > 0 and a > 0
        if gg.lower() == "da":
            return g and both
        if gg.lower() == "nu":
            return g and not both
        return None
    if mn in ("1x2 & interval goluri", "șansă dublă & interval goluri", "sansa dubla & interval goluri"):
        side, _, band = oc.partition(" & ")
        g = _goals_ok(band, total)
        return None if g is None else _side_ok(side.lower(), h, a) and g
    return None


def joint_p(lh: float, la: float, market: str, outcome: str) -> Optional[float]:
    if not (0.2 <= lh <= 4.5 and 0.2 <= la <= 4.5):
        return None
    g = _grid(lh, la)
    p = 0.0
    known = False
    for i, row in enumerate(g):
        for j, w in enumerate(row):
            flag = hits(market, outcome, i, j)
            if flag is None:
                return None
            known = True
            if flag:
                p += w
    return p if known else None


def _priority_bb(odds: float, p: float) -> Optional[int]:
    if not (ODDS[0] <= odds <= ODDS[1]) or not (0.18 <= p <= 0.50):
        return None
    ev = p * odds - 1
    if ev < -0.12 or ev > 0.12:
        return None
    return 2 if ev >= -0.04 else 1


def load_builders(conn: sqlite3.Connection, today: date, days_ahead: int = 6,
                  now: Optional[datetime] = None) -> List[Cand]:
    """Cel mai bun Bet Builder pe meci, în orizontul biletelor."""
    start = canon_utc((now or datetime.now(timezone.utc)).isoformat())
    end_day = today + timedelta(days=days_ahead)
    qmarks = ",".join("?" for _ in MARKETS)
    rows = conn.execute(
        f"""SELECT o.match_id, o.market_name, o.outcome, o.price,
                  m.league_id, l.name AS league, m.kickoff_utc, m.home_name, m.away_name,
                  mm.lambda_home, mm.lambda_away
           FROM sb_offer o
           JOIN match m ON m.id = o.match_id
           JOIN match_model mm ON mm.match_id = m.id AND mm.model_version = ?
           LEFT JOIN league l ON l.id = m.league_id
           WHERE m.kickoff_utc >= ? AND m.kickoff_utc < ?
             AND o.price BETWEEN ? AND ?
             AND (o.market_name IN ({qmarks}) OR o.market_name LIKE '1X2 & Total goluri%'
                  OR o.market_name LIKE 'Șansă dublă & Total goluri%')""",
        (MODEL_VERSION, start, (end_day + timedelta(days=1)).isoformat(), ODDS[0], ODDS[1], *MARKETS),
    ).fetchall()
    best: Dict[int, Tuple[int, float, Cand]] = {}
    for r in rows:
        p = joint_p(r["lambda_home"], r["lambda_away"], r["market_name"], r["outcome"])
        if p is None:
            continue
        rank = _priority_bb(r["price"], p)
        if rank is None:
            continue
        cand = Cand(
            prediction_id=-int(r["match_id"]), match_id=r["match_id"], league_id=r["league_id"],
            league=r["league"], kickoff_utc=r["kickoff_utc"], home=r["home_name"], away=r["away_name"],
            market="bb", line=0.0, selection=f"{r['market_name']}|{r['outcome']}",
            odds=float(r["price"]), p=p, ev=p * float(r["price"]) - 1, grade="B", confidence=1,
            p_market=None, odds_source="superbet",
        )
        cur = best.get(r["match_id"])
        key = (rank, p * r["price"] - 1)
        if cur is None or key > (cur[0], cur[1]):
            best[r["match_id"]] = (rank, p * r["price"] - 1, cand)
    return [v[2] for v in best.values()]
