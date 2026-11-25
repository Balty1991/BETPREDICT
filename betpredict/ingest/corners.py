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


BLIND_DAYS = 30
BLIND_MIN_N = 5      # câte meciuri terminate (cu citire încercată) trebuie să aibă liga ca să decidem
BLIND_MIN_COV = 0.5  # sub atât din meciurile ligii au cornere în BSD: selecțiile cu cornere de acolo nu se pot deconta


def blind_leagues(conn: sqlite3.Connection, now: Optional[datetime] = None, days: int = BLIND_DAYS,
                  min_n: int = BLIND_MIN_N, min_cov: float = BLIND_MIN_COV) -> set:
    """Ligile la care BSD nu dă cornere (25.11: Cupa Portugaliei 1/16, Liga Portugal 2 0/28, Parva Liga 0/25, Ligue 3 2/27):
    o selecție „0.5 goluri + 7.5 cornere” de acolo rămâne nedecontată pentru totdeauna și ține biletul în așteptare.
    Doar meciurile la care cornerele s-au cerut deja (``corner_fetch``), ca o ligă încă necitită să nu fie scoasă degeaba."""
    now = now or datetime.now(timezone.utc)
    lo = canon_utc((now - timedelta(days=days)).isoformat())
    hi = canon_utc((now - timedelta(hours=6)).isoformat())
    try:
        rows = conn.execute(
            """SELECT m.league_id, COUNT(*), SUM(m.corners_home IS NOT NULL AND m.corners_away IS NOT NULL)
               FROM match m JOIN corner_fetch f ON f.match_id = m.id
               WHERE m.status='finished' AND m.league_id IS NOT NULL AND m.kickoff_utc >= ? AND m.kickoff_utc < ?
               GROUP BY m.league_id""", (lo, hi)).fetchall()
    except sqlite3.Error:
        return set()
    return {lg for lg, n, k in rows if n >= min_n and (k or 0) / n < min_cov}
