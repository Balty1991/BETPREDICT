"""Bilete lungi din Interval goluri 2–6.

Pe 34.603 meciuri cu scor pe pauză, 2–6 a ieșit în 72,6%. Prima repriză sub 3,5 taie
doar 2,2 puncte și se cotează la ~1,02, sub 4,5 la 1,00. Nu se adaugă pe bilet: nu
apropie cota și nu se vinde ca o combinație. 20 de selecții pe la 1,28 fac ~140,
30 fac ~1.600.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from betpredict.builder.pool import Cand
from betpredict.builder.v4tickets import insert_ticket
from betpredict.store import repo
from betpredict.timeutil import canon_utc

HIST_P = 0.726
KIND = "acca_interval"
SIZES = (20, 30)
LEAGUE_CAP = 3


def interval_hit(selection: str, h: int, a: int) -> Optional[bool]:
    if "-" not in (selection or ""):
        return None
    lo_s, _, hi_s = selection.partition("-")
    try:
        lo, hi = int(lo_s), int(hi_s)
    except ValueError:
        return None
    return lo <= h + a <= hi


def build_interval_26(conn: sqlite3.Connection, today: date, days_ahead: int = 6,
                      now: Optional[datetime] = None, rebuild: bool = False) -> Dict[str, Any]:
    pending = [r[0] for r in conn.execute(
        "SELECT id FROM ticket WHERE variant IN ('i20','i30') AND status='pending' AND day>=?",
        (today.isoformat(),))]
    if pending and not rebuild:
        return {"skipped_existing": len(pending), "tickets": 0}
    end = (today + timedelta(days=days_ahead)).isoformat() + "T23:59:59Z"
    now_s = canon_utc((now or datetime.now(timezone.utc)).isoformat())
    taken = {r[0] for r in conn.execute(
        """SELECT DISTINCT l.match_id FROM ticket_leg l JOIN ticket t ON t.id=l.ticket_id
           WHERE t.status='pending' AND t.variant NOT IN ('i20','i30')""")}
    rows = conn.execute(
        """SELECT o.match_id, o.price, o.ref, m.kickoff_utc, m.home_name, m.away_name, m.league_id, l.name
           FROM sb_offer o JOIN match m ON m.id=o.match_id LEFT JOIN league l ON l.id=m.league_id
           WHERE o.market_name='Interval goluri' AND o.outcome='2-6'
             AND o.price BETWEEN 1.15 AND 1.70 AND m.kickoff_utc>? AND m.kickoff_utc<=?""",
        (now_s, end)).fetchall()
    best: Dict[int, Any] = {}
    for r in rows:
        mid = r[0]
        if mid in taken:
            continue
        cur = best.get(mid)
        if cur is None or r[1] > cur[1]:
            best[mid] = r
    ordered = sorted(best.values(), key=lambda r: (r[3] or "", r[0]))
    groups = _take(ordered)
    created = repo.now_iso()
    ids: List[int] = []
    with conn:
        for i in pending:
            conn.execute("UPDATE ticket SET status='replaced' WHERE id=?", (i,))
        for n, legs in groups:
            total = 1.0
            for c in legs:
                total *= c.odds
            p = HIST_P ** len(legs)
            variant = "i20" if n <= 24 else "i30"
            reasons = [
                f"{len(legs)} meciuri, fiecare cu intervalul 2–6 goluri. Produs {total:.0f}.",
                "Pe 34.603 meciuri terminate, 2–6 a ieșit în 72,6%. Cota corectă ar fi ~1,38; Superbet dă în medie 1,28.",
                "Prima repriză sub 3,5 a ieșit în 96,7% și se cotează la 1,02. Sub 4,5 e 99,3%, cotă 1,00. Nu urcă biletul.",
                f"Dacă fiecare meci iese ca în istoric, biletul iese în {p:.2%}. Marja se înmulțește de {len(legs)} ori.",
            ]
            tid = insert_ticket(
                conn, KIND, variant, round(total, 2), legs, 0.05, reasons, today, created, {},
                {"honest": True, "risk_acknowledged": True, "board": "interval26",
                 "label": f"Interval 2–6 · {len(legs)} meciuri",
                 "leg_reasons": [{"m": c.match_id, "s": c.selection, "r": list(c.extra.get("reasons") or [])} for c in legs]})
            if tid:
                ids.append(tid)
    return {"tickets": len(ids), "ids": ids, "pool": len(ordered)}


def _take(rows: List[Any]) -> List[tuple]:
    """Un bilet de 20 și, dacă mai rămân, unul de 30. Maxim 3 meciuri pe ligă."""
    out = []
    rest = list(rows)
    for n in SIZES:
        legs, leagues = [], {}
        used = set()
        for r in rest:
            lid = r[6]
            if leagues.get(lid, 0) >= LEAGUE_CAP:
                continue
            legs.append(_cand(r))
            leagues[lid] = leagues.get(lid, 0) + 1
            used.add(r[0])
            if len(legs) == n:
                break
        if len(legs) < n:
            if n == SIZES[0] and len(legs) >= 20:
                out.append((len(legs), legs))
            break
        out.append((n, legs))
        rest = [r for r in rest if r[0] not in used]
    return out


def _cand(r: Any) -> Cand:
    mid, price, _ref, kick, home, away, lid, league = r
    return Cand(
        prediction_id=-int(mid), match_id=int(mid), league_id=lid, league=league, kickoff_utc=kick or "",
        home=home, away=away, market="interval", line=0.0, selection="2-6", odds=float(price),
        p=HIST_P, ev=HIST_P * float(price) - 1, grade="B", confidence=1, odds_source="superbet",
        extra={"p_adj": HIST_P, "reasons": ["Interval 2–6 goluri. Istoric: 72,6% din meciuri."]},
    )
