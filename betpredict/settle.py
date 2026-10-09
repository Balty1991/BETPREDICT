"""Decontare automată: predicții → bilete → piramidă. Void la amânat/anulat/nerezolvat."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from betpredict.ingest.normalize import VOID_STATUSES
from betpredict.robot.markets import leg_factor, profit_1u, settle_selection
from betpredict.store import repo
from betpredict.timeutil import canon_utc

STALE_VOID_DAYS = 7


def settle_predictions(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, int]:
    now = now or datetime.now(timezone.utc)
    stale = canon_utc((now - timedelta(days=STALE_VOID_DAYS)).isoformat())
    rows = conn.execute(
        """SELECT p.id, p.market, p.line, p.selection, p.odds_shown, m.status, m.ft_home, m.ft_away, m.kickoff_utc
           FROM prediction p JOIN match m ON m.id = p.match_id
           WHERE p.result IS NULL AND p.shown_on_page != 'legacy'"""
    ).fetchall()
    stats = {"checked": len(rows), "settled": 0, "void": 0}
    stamp = repo.now_iso()
    with conn:
        for r in rows:
            status = (r["status"] or "").lower()
            result = None
            if status == "finished":
                result = settle_selection(r["market"], r["line"] or 0.0, r["selection"], r["ft_home"], r["ft_away"])
            elif status in VOID_STATUSES:
                result = "void"
            elif r["kickoff_utc"] and r["kickoff_utc"] < stale:
                result = "void"  # fără rezultat după 7 zile
            if result is None:
                continue
            conn.execute("UPDATE prediction SET result=?, settled_at=?, profit_1u=? WHERE id=?",
                         (result, stamp, profit_1u(result, r["odds_shown"]), r["id"]))
            stats["settled"] += 1
            stats["void"] += 1 if result == "void" else 0
    return stats


def settle_tickets(conn: sqlite3.Connection) -> Dict[str, int]:
    stats = {"tickets": 0, "won": 0, "lost": 0, "void": 0}
    stamp = repo.now_iso()
    with conn:
        conn.execute(
            """UPDATE ticket_leg SET result = (SELECT p.result FROM prediction p WHERE p.id = ticket_leg.prediction_id)
               WHERE result IS NULL AND prediction_id IS NOT NULL"""
        )
        for t in conn.execute("SELECT id, total_odds, stake FROM ticket WHERE status='pending'").fetchall():
            legs = conn.execute("SELECT odds, result FROM ticket_leg WHERE ticket_id=?", (t["id"],)).fetchall()
            if not legs:
                continue
            results = [l["result"] for l in legs]
            stake = t["stake"] or 1.0
            if any(r == "lost" for r in results):
                status, payout = "lost", 0.0
            elif all(r is not None for r in results):
                if all(r == "void" for r in results):
                    status, payout = "void", stake
                else:
                    mult = 1.0
                    for l in legs:
                        mult *= leg_factor(l["result"], l["odds"]) or 0.0
                    status, payout = "won", round(stake * mult, 2)
            else:
                continue
            conn.execute("UPDATE ticket SET status=?, payout=?, settled_at=? WHERE id=?", (status, payout, stamp, t["id"]))
            stats["tickets"] += 1
            stats[status] += 1
    return stats


def settle_all(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Dict[str, Dict[str, int]]:
    from betpredict.builder.pyramid import advance_pyramid

    out = {"predictions": settle_predictions(conn, now), "tickets": settle_tickets(conn)}
    try:
        from betpredict.clv import compute_clv

        out["clv"] = compute_clv(conn, now)
    except Exception as exc:  # noqa: BLE001 — CLV e informativ; nu oprește decontarea
        out["clv_error"] = str(exc)
    out["pyramid"] = advance_pyramid(conn)
    return out
