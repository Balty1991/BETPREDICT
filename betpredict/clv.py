"""Linia de închidere (closing line) și CLV.

* ``odds_taken`` = cota la care Robotul a publicat selecția prima dată (nu se mai schimbă);
* cota de închidere = ultima cotă observată ÎNAINTE de start, din ACEEAȘI sursă (Superbet sau consensul
  BSD). Pentru Superbet, închiderea e validă doar dacă meciul a fost citit în ultimele 3 h înainte de start
  (refresh orar + captura de la :50);
* ``CLV = cota luată / cota de închidere − 1``: pozitiv = am „bătut piața” (cota a scăzut după publicare).
  E cel mai rapid indicator că un segment are valoare reală — se stabilizează în zile, ROI-ul în luni.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from betpredict.timeutil import canon_utc

CLOSE_VALID_H = 3.0
LOOKBACK_DAYS = 10


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s[:19]).replace(tzinfo=timezone.utc)


class Closing:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.ext = {r["match_id"]: (r["checked_at"], r["detail_at"]) for r in conn.execute(
            "SELECT match_id, checked_at, detail_at FROM ext_event WHERE source='superbet'")}

    def price(self, match_id: int, market: str, line: float, outcome: str, source: str, kickoff: str) -> Optional[float]:
        if source == "superbet":
            chk, det = self.ext.get(match_id, (None, None))
            seen = chk if market == "1x2" else det
            if not seen or (_dt(kickoff) - _dt(seen)).total_seconds() / 3600 > CLOSE_VALID_H:
                return None
        r = self.conn.execute(
            """SELECT decimal FROM odds_snapshot WHERE match_id=? AND source=? AND market=? AND line=? AND period='FT'
               AND outcome=? AND substr(observed_at,1,19) <= ? ORDER BY observed_at DESC LIMIT 1""",
            (match_id, source, market, float(line or 0.0), outcome, kickoff[:19])).fetchone()
        return float(r[0]) if r else None


def backfill_taken(conn: sqlite3.Connection, since_day: str) -> int:
    """Predicțiile vechi (dinainte de coloana ``odds_taken``): cota de consens de la momentul creării."""
    rows = conn.execute(
        """SELECT p.id, p.match_id, p.market, p.line, p.selection, p.created_at FROM prediction p
           WHERE p.odds_taken IS NULL AND p.odds_shown IS NOT NULL AND p.odds_source='bsd_consensus'
             AND p.shown_on_page != 'legacy' AND p.day >= ? AND p.created_at IS NOT NULL""", (since_day,)).fetchall()
    n = 0
    with conn:
        for r in rows:
            o = conn.execute(
                """SELECT decimal FROM odds_snapshot WHERE match_id=? AND source='bsd_consensus' AND market=? AND line=?
                   AND period='FT' AND outcome=? AND substr(observed_at,1,19) <= ? ORDER BY observed_at DESC LIMIT 1""",
                (r["match_id"], r["market"], float(r["line"] or 0.0), r["selection"], r["created_at"][:19])).fetchone()
            if o:
                conn.execute("UPDATE prediction SET odds_taken=?, odds_taken_source='bsd_consensus', odds_taken_at=? WHERE id=?",
                             (o[0], r["created_at"], r["id"]))
                n += 1
    return n


def compute_clv(conn: sqlite3.Connection, now: Optional[datetime] = None, since_day: Optional[str] = None) -> Dict[str, Any]:
    from betpredict.robot import STATS_SINCE

    now = now or datetime.now(timezone.utc)
    now_s = canon_utc(now.isoformat())
    lo = canon_utc((now - timedelta(days=LOOKBACK_DAYS)).isoformat())
    stats = {"backfilled": backfill_taken(conn, since_day or STATS_SINCE), "predictions": 0, "legs": 0, "tickets": 0}
    cl = Closing(conn)
    rows = conn.execute(
        """SELECT p.id, p.match_id, p.market, p.line, p.selection, p.odds_taken, p.odds_taken_source, m.kickoff_utc
           FROM prediction p JOIN match m ON m.id = p.match_id
           WHERE p.clv IS NULL AND p.odds_taken IS NOT NULL AND m.kickoff_utc <= ? AND m.kickoff_utc >= ?
             AND p.shown_on_page != 'legacy'""", (now_s, lo)).fetchall()
    with conn:
        for r in rows:
            c = cl.price(r["match_id"], r["market"], r["line"], r["selection"], r["odds_taken_source"] or "bsd_consensus", r["kickoff_utc"])
            if c:
                conn.execute("UPDATE prediction SET closing_odds=?, clv=? WHERE id=?", (c, round(r["odds_taken"] / c - 1, 4), r["id"]))
                stats["predictions"] += 1
        legs = conn.execute(
            """SELECT tl.rowid AS rid, tl.ticket_id, tl.match_id, tl.market, tl.selection, tl.odds, tl.odds_source,
                      p.odds_source AS psrc, m.kickoff_utc
               FROM ticket_leg tl JOIN ticket t ON t.id = tl.ticket_id JOIN match m ON m.id = tl.match_id
               LEFT JOIN prediction p ON p.id = tl.prediction_id
               WHERE tl.closing_odds IS NULL AND t.status != 'replaced' AND m.kickoff_utc <= ? AND m.kickoff_utc >= ?""",
            (now_s, lo)).fetchall()
        touched = set()
        for l in legs:
            market, _, line_s = (l["market"] or "").partition("|")
            src = l["odds_source"] or l["psrc"] or "bsd_consensus"
            c = cl.price(l["match_id"], market, float(line_s or 0.0), l["selection"], src, l["kickoff_utc"])
            if c:
                conn.execute("UPDATE ticket_leg SET closing_odds=? WHERE rowid=?", (c, l["rid"]))
                stats["legs"] += 1
                touched.add(l["ticket_id"])
        for tid in touched | {r[0] for r in conn.execute("SELECT id FROM ticket WHERE clv IS NULL AND status != 'replaced' AND created_at >= ?", (lo,))}:
            ls = conn.execute("SELECT odds, closing_odds, result FROM ticket_leg WHERE ticket_id=?", (tid,)).fetchall()
            act = [x for x in ls if x["result"] != "void"]
            if act and all(x["closing_odds"] for x in act):
                v = math.prod(x["odds"] for x in act) / math.prod(x["closing_odds"] for x in act) - 1
                conn.execute("UPDATE ticket SET clv=? WHERE id=?", (round(v, 4), tid))
                stats["tickets"] += 1
    return stats


def clv_summary(values) -> Dict[str, Any]:
    vs = [v for v in values if v is not None]
    if not vs:
        return {"n": 0, "avg": None, "beat_rate": None}
    m = sum(vs) / len(vs)
    sd = (sum((v - m) ** 2 for v in vs) / max(1, len(vs) - 1)) ** 0.5
    return {"n": len(vs), "avg": round(m, 4), "beat_rate": round(sum(1 for v in vs if v > 0) / len(vs), 4),
            "se": round(sd / math.sqrt(len(vs)), 4) if len(vs) > 1 else None}
