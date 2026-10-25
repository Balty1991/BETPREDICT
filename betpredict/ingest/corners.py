"""Cornere din BSD (/events/{id}/stats/: stats.home/away.corner_kicks, stats.first_half.home/away.corner_kicks).

Folosite la decontarea piețelor de cornere (total + prima repriză) și ca istoric pentru modelul de cornere.
Prioritate: meciurile terminate recent / cu selecții de cornere în așteptare, apoi completare (backfill) sezon curent."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from betpredict.timeutil import canon_utc

FETCH = """CREATE TABLE IF NOT EXISTS corner_fetch (match_id INTEGER PRIMARY KEY, fetched_at TEXT NOT NULL, ok INTEGER NOT NULL)"""
BACKFILL_FROM = "2025-07-01"  # 25.10: și sezonul trecut (cornere R1 aveau doar ~3.8k meciuri)


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute(FETCH)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(match)")}
    for c in ("corners_ht_home", "corners_ht_away"):
        if c not in cols:
            conn.execute(f"ALTER TABLE match ADD COLUMN {c} INTEGER")


def parse(js: Any):
    st = (js or {}).get("stats") if isinstance(js, dict) else None
    if not isinstance(st, dict):
        return None
    ck = lambda d, s: (d.get(s) or {}).get("corner_kicks") if isinstance(d, dict) else None  # noqa: E731
    h, a = ck(st, "home"), ck(st, "away")
    if h is None or a is None:
        return None
    fh = st.get("first_half") or {}
    return int(h), int(a), (None if ck(fh, "home") is None else int(ck(fh, "home"))), (None if ck(fh, "away") is None else int(ck(fh, "away")))


def collect(conn: sqlite3.Connection, client, recent_days: int = 3, backfill: int = 300, now: Optional[datetime] = None) -> Dict[str, int]:
    ensure(conn)
    now = now or datetime.now(timezone.utc)
    lo = canon_utc((now - timedelta(days=recent_days)).isoformat())
    retry = canon_utc((now - timedelta(hours=6)).isoformat())
    recent = [r[0] for r in conn.execute(
        """SELECT m.id FROM match m LEFT JOIN corner_fetch f ON f.match_id=m.id
           WHERE m.status='finished' AND m.corners_home IS NULL AND m.kickoff_utc >= ?
             AND (f.match_id IS NULL OR (f.ok=0 AND f.fetched_at < ?)) ORDER BY m.kickoff_utc DESC""", (lo, retry))]
    old = [r[0] for r in conn.execute(
        """SELECT m.id FROM match m LEFT JOIN corner_fetch f ON f.match_id=m.id
           WHERE m.status='finished' AND (m.corners_home IS NULL OR m.corners_ht_home IS NULL) AND m.kickoff_utc >= ? AND m.kickoff_utc < ?
             AND f.match_id IS NULL
           ORDER BY m.kickoff_utc DESC LIMIT ?""", (BACKFILL_FROM, lo, backfill))]
    st = {"recent": len(recent), "backfill": len(old), "ok": 0, "ht": 0}
    for mid in recent + old:
        try:
            js = client.get(f"events/{mid}/stats/")
        except Exception:  # noqa: BLE001
            js = None
        p = parse(js)
        with conn:
            if p:
                conn.execute("UPDATE match SET corners_home=?, corners_away=?, corners_ht_home=?, corners_ht_away=? WHERE id=?", (*p, mid))
                st["ok"] += 1
                st["ht"] += p[2] is not None
            conn.execute("INSERT INTO corner_fetch VALUES (?,?,?) ON CONFLICT(match_id) DO UPDATE SET fetched_at=excluded.fetched_at, ok=excluded.ok",
                         (mid, canon_utc(now.isoformat()), 1 if p else 0))
    return st
