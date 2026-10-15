"""Cartonașe pe meci din BSD (/events/{id}/incidents/: incidentele de tip „card”, gazde/oaspeți).

Se numără fiecare cartonaș arătat (galben, al doilea galben, roșu), ca la piața Superbet „Total cartonașe”.
Folosite la decontarea piețelor de cartonașe și ca istoric pentru modelul de cartonașe. Meciurile din ligile
football-data primesc oricum cartonașele galbene la legare (``footballdata.link_matches``)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from betpredict.timeutil import canon_utc

FETCH = "CREATE TABLE IF NOT EXISTS card_fetch (match_id INTEGER PRIMARY KEY, fetched_at TEXT NOT NULL, ok INTEGER NOT NULL)"
BACKFILL_FROM = "2026-07-01"


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute(FETCH)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(match)")}
    for c in ("cards_home", "cards_away"):
        if c not in cols:
            conn.execute(f"ALTER TABLE match ADD COLUMN {c} INTEGER")


def parse(js: Any) -> Optional[Tuple[int, int]]:
    """(cartonașe gazde, cartonașe oaspeți) sau None dacă incidentele lipsesc / meciul nu are final."""
    if isinstance(js, dict):
        inc = js.get("incidents") if isinstance(js.get("incidents"), list) else js.get("results")
    else:
        inc = js
    if not isinstance(inc, list) or not inc:
        return None
    if not any(i.get("type") == "period" and i.get("text") in ("FT", "AET", "AP") for i in inc if isinstance(i, dict)):
        return None  # fără final: incidentele pot fi incomplete
    h = a = 0
    for i in inc:
        if isinstance(i, dict) and i.get("type") == "card":
            if i.get("is_home"):
                h += 1
            else:
                a += 1
    return h, a


def collect(conn: sqlite3.Connection, client, recent_days: int = 3, backfill: int = 300, now: Optional[datetime] = None) -> Dict[str, int]:
    ensure(conn)
    now = now or datetime.now(timezone.utc)
    lo = canon_utc((now - timedelta(days=recent_days)).isoformat())
    retry = canon_utc((now - timedelta(hours=6)).isoformat())
    recent = [r[0] for r in conn.execute(
        """SELECT m.id FROM match m LEFT JOIN card_fetch f ON f.match_id=m.id
           WHERE m.status='finished' AND m.cards_home IS NULL AND m.kickoff_utc >= ?
             AND (f.match_id IS NULL OR (f.ok=0 AND f.fetched_at < ?)) ORDER BY m.kickoff_utc DESC""", (lo, retry))]
    old = [r[0] for r in conn.execute(
        """SELECT m.id FROM match m LEFT JOIN card_fetch f ON f.match_id=m.id
           WHERE m.status='finished' AND m.cards_home IS NULL AND m.kickoff_utc >= ? AND m.kickoff_utc < ? AND f.match_id IS NULL
           ORDER BY m.kickoff_utc DESC LIMIT ?""", (BACKFILL_FROM, lo, backfill))]
    st = {"recent": len(recent), "backfill": len(old), "ok": 0}
    for mid in recent + old:
        try:
            js = client.get(f"events/{mid}/incidents/")
        except Exception:  # noqa: BLE001
            js = None
        p = parse(js)
        with conn:
            if p:
                conn.execute("UPDATE match SET cards_home=?, cards_away=? WHERE id=?", (*p, mid))
                st["ok"] += 1
            conn.execute("INSERT INTO card_fetch VALUES (?,?,?) ON CONFLICT(match_id) DO UPDATE SET fetched_at=excluded.fetched_at, ok=excluded.ok",
                         (mid, canon_utc(now.isoformat()), 1 if p else 0))
    return st
