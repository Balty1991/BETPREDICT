"""Paper tracking of pre-kickoff steam. Shortened prices are recorded, never used to place a bet."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

SHORTEN, DRIFT = -0.02, 0.02


def _bucket(move: Optional[float]) -> Optional[str]:
    if move is None:
        return None
    if move <= SHORTEN:
        return "shortened"
    if move >= DRIFT:
        return "drifted"
    return "flat"


def steam_doc(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Settled Superbet picks split by whether the price shortened or drifted from the open. Paper only."""
    from betpredict.ingest.opening import opening_map
    from betpredict.robot.markets import market_key

    try:
        rows = conn.execute(
            """SELECT p.match_id, p.market, p.line, p.selection, p.odds_shown, p.odds_source, p.result, p.profit_1u
               FROM prediction p
               WHERE p.result IN ('won','lost') AND p.odds_shown > 1 AND p.odds_source = 'superbet'"""
        ).fetchall()
    except sqlite3.Error:
        rows = []
    opens = opening_map(conn, [r["match_id"] for r in rows]) if rows else {}
    groups: Dict[str, List[float]] = {"shortened": [], "drifted": [], "flat": []}
    for r in rows:
        key = (r["match_id"], market_key(r["market"], r["line"] or 0.0), float(r["line"] or 0.0), r["selection"], "superbet")
        # opening_map keys are (match, market, line, outcome, source); market there is the raw market name
        opened = opens.get((r["match_id"], r["market"], float(r["line"] or 0.0), r["selection"], "superbet"))
        if not opened or opened <= 1:
            continue
        bucket = _bucket(r["odds_shown"] / opened - 1)
        if bucket:
            groups[bucket].append((r["profit_1u"] or 0.0, 1.0 if r["result"] == "won" else 0.0))

    def pack(xs: List) -> Dict[str, Any]:
        if not xs:
            return {"n": 0, "hit": None, "roi": None}
        return {"n": len(xs), "hit": round(sum(y for _, y in xs) / len(xs), 4),
                "roi": round(sum(p for p, _ in xs) / len(xs), 4)}

    return {"paper": True, "live": False,
            "note": "Doar pe hârtie. Cota scurtată față de deschidere față de cota care a fugit. Nu filtrează biletele live.",
            "shortened": pack(groups["shortened"]), "drifted": pack(groups["drifted"]), "flat": pack(groups["flat"])}
