"""Verificarea săptămânală a regulilor de clasare adăugate pe 25.11 (cupe, ligi secunde la cornere, cornere marți–joi,
cluburi mari, favorit după victorie la scor), pe meciuri jucate DUPĂ ce regula a intrat în Robot (în afara eșantionului).

Pentru fiecare regulă: randamentul la cota de închidere Superbet al selecțiilor marcate de regulă față de restul din aceeași
categorie. Regula se OPREȘTE singură dacă datele noi o contrazic clar (z ≤ −1,5 pe cel puțin MIN_N selecții marcate) și
rămâne pornită altfel. Decizia se ia o dată pe săptămână; documentul se publică la fiecare rulare."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from betpredict.store import repo

START = "2026-11-25T00:00:00Z"   # regulile au intrat în Robot pe 25.11: de aici încolo e date noi
MIN_N = 30                        # sub atât selecții marcate nu decidem nimic
Z_OFF = -1.5                      # contrazisă clar → oprită
Z_OK = 1.0                        # în direcția așteptată → confirmată
STATE_OFF = "rules.off"
STATE_WEEK = "rules.check.week"
FAV_ODDS = (1.25, 1.70)


def _legs(conn: sqlite3.Connection, now: datetime) -> List[SimpleNamespace]:
    """Selecțiile recomandate (REC + combinația cu cornere) decontate la cotele de închidere, cluburi, ziua, după START."""
    from betpredict.builder import rec_monitor as RM
    from betpredict.builder import super_tickets as ST

    hi = (now - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        rows = conn.execute(
            """SELECT s.match_id, s.market_name, s.outcome, MAX(s.price), m.ft_home, m.ft_away, m.ht_home, m.ht_away,
                      m.corners_home, m.corners_away, m.kickoff_utc, l.name, m.league_id, m.home_name, m.away_name, m.home_id, m.away_id
               FROM sb_offer_close s JOIN match m ON m.id=s.match_id LEFT JOIN league l ON l.id=m.league_id
               WHERE m.status='finished' AND m.ft_home IS NOT NULL AND m.kickoff_utc>=? AND m.kickoff_utc<?
               GROUP BY s.match_id, s.market_name, s.outcome""", (START, hi)).fetchall()
    except sqlite3.OperationalError:
        return []
    out: List[SimpleNamespace] = []
    for mid, mn, oc, price, fh, fa, hh, ha, ch, ca, ko, lg, lid, hn, an, hid, aid in rows:
        if not price or price <= 1 or RM.is_intl_league(lg) or RM.is_night(ko):
            continue
        key, lo, hi_ = RM._key(mn, oc, ST.REC, (1.40, 1.60))
        if key is None or not lo <= price <= hi_:
            continue
        won = RM.settle(mn, oc, fh, fa, hh, ha, ch, ca)
        if won is None:
            continue
        if key == RM.COMBO:
            market, sel = "bb", "Peste 0.5 goluri; Peste 7.5 cornere"
        else:
            market, sel = ST.REC[key][0], ST.REC[key][1]
        out.append(SimpleNamespace(match_id=mid, market=market, selection=sel, odds=float(price), won=bool(won), league=lg,
                                   league_id=lid, kickoff_utc=ko, home=hn, away=an, home_id=hid, away_id=aid, extra={}))
    favs = [c for c in out if c.market == "1x2" and c.selection in ("HOME", "AWAY")]
    if favs:
        margins = ST.last_margins(conn, [(c.home_id if c.selection == "HOME" else c.away_id, c.kickoff_utc) for c in favs])
        for c in favs:
            c.extra["last_margin"] = margins.get((c.home_id if c.selection == "HOME" else c.away_id, c.kickoff_utc))
    return out


def _rules() -> List[Tuple[str, str, Callable, Callable, int]]:
    from betpredict.builder import super_tickets as ST

    fav = lambda c: c.market == "1x2" and c.selection in ("HOME", "AWAY") and FAV_ODDS[0] <= c.odds <= FAV_ODDS[1]  # noqa: E731
    big = lambda c: bool(ST.BIG_CLUBS.match(((c.home if c.selection == "HOME" else c.away) or "").strip()))  # noqa: E731
    return [
        ("cup", "Cupele naționale mai rar", lambda c: True, ST.is_cup, -1),
        ("corner2nd", "Cornere preferate în ligile secunde", ST.is_corner_combo, ST.is_corner_2nd, +1),
        ("midweek", "Cornere evitate marți–joi", ST.is_corner_combo, ST.is_midweek, -1),
        ("bigclub", "Favoriții din cluburile mari preferați", fav, big, +1),
        ("blowout", "Favorit după o victorie la 3+ goluri evitat", fav, lambda c: (c.extra.get("last_margin") or 0) >= 3, -1),
    ]


def _mean_var(xs: List[float]) -> Tuple[float, float]:
    if not xs:
        return 0.0, 0.0
    m = sum(xs) / len(xs)
    v = sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1)
    return m, v


def evaluate(conn: sqlite3.Connection, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    legs = _legs(conn, now)
    out = []
    for name, label, pop, flag, sign in _rules():
        p = [c for c in legs if pop(c)]
        f = [(c.odds - 1) if c.won else -1.0 for c in p if flag(c)]
        r = [(c.odds - 1) if c.won else -1.0 for c in p if not flag(c)]
        mf, vf = _mean_var(f)
        mr, vr = _mean_var(r)
        diff = mf - mr
        se = math.sqrt(vf / max(1, len(f)) + vr / max(1, len(r))) if f and r else 0.0
        z = sign * diff / se if se > 0 else 0.0
        status = "proba" if len(f) < MIN_N or len(r) < MIN_N else "oprita" if z <= Z_OFF else "confirmata" if z >= Z_OK else "neclar"
        out.append({"rule": name, "label": label, "n": len(f), "n_rest": len(r), "roi": round(mf, 4) if f else None,
                    "roi_rest": round(mr, 4) if r else None, "diff": round(diff, 4), "z": round(z, 2), "status": status})
    return out


def off_rules(conn: sqlite3.Connection) -> Set[str]:
    try:
        return set(json.loads(repo.get_state(conn, STATE_OFF) or "[]"))
    except (sqlite3.Error, ValueError, TypeError):
        return set()


def weekly_update(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """O dată pe săptămână (săptămâna ISO): oprește regulile contrazise clar și repornește cele care nu mai sunt contrazise."""
    now = now or datetime.now(timezone.utc)
    week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
    try:
        if repo.get_state(conn, STATE_WEEK) == week:
            return None
    except sqlite3.Error:
        return None
    res = evaluate(conn, now)
    off = sorted(r["rule"] for r in res if r["status"] == "oprita")
    repo.set_state(conn, STATE_OFF, json.dumps(off))
    repo.set_state(conn, STATE_WEEK, week)
    return {"week": week, "off": off, "rules": res}


def doc(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    try:
        week = repo.get_state(conn, STATE_WEEK)
    except sqlite3.Error:
        week = None
    return {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "since": START, "checked_week": week, "min_n": MIN_N,
            "off": sorted(off_rules(conn)), "rules": evaluate(conn, now)}
