"""Cartonașe pe meci din BSD (/events/{id}/incidents/: incidentele de tip „card”, gazde/oaspeți).

Se numără ca la piața Superbet „Total cartonașe”: galben = 1, roșu = 2 (și roșul venit din al doilea galben = 2).
Exemplu real (Santos Laguna–Queretaro, 18.10.2026): 4 galbene + 1 roșu = 6, Sub 5.5 pierdut, deși sunt 5 cartonașe.
Folosite la decontarea piețelor de cartonașe și ca istoric pentru modelul de cartonașe. Meciurile din ligile
football-data primesc oricum cartonașele galbene la legare (``footballdata.link_matches``)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from betpredict.timeutil import canon_utc

FETCH = "CREATE TABLE IF NOT EXISTS card_fetch (match_id INTEGER PRIMARY KEY, fetched_at TEXT NOT NULL, ok INTEGER NOT NULL)"
BACKFILL_FROM = "2026-07-01"
# v2: roșul = 2. Meciurile numărate înainte (roșu = 1) din RECOUNT_FROM se renumără, cel mult RECOUNT pe rulare.
CARDS_V = 2
RECOUNT_FROM = "2026-10-01"
RECOUNT = 250
RED = ("red", "yellowred", "yellow_red", "secondyellow", "second_yellow")


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute(FETCH)
    if "v" not in {r[1] for r in conn.execute("PRAGMA table_info(card_fetch)")}:
        conn.execute("ALTER TABLE card_fetch ADD COLUMN v INTEGER")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(match)")}
    for c in ("cards_home", "cards_away"):
        if c not in cols:
            conn.execute(f"ALTER TABLE match ADD COLUMN {c} INTEGER")


def parse(js: Any) -> Optional[Tuple[int, int]]:
    """(puncte cartonașe gazde, oaspeți) — galben 1, roșu 2 — sau None dacă incidentele lipsesc / meciul nu are final."""
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
            w = 2 if str(i.get("card_type") or "").lower().replace("-", "").replace(" ", "") in RED else 1
            if i.get("is_home"):
                h += w
            else:
                a += w
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
    redo = [r[0] for r in conn.execute(
        """SELECT m.id FROM match m JOIN card_fetch f ON f.match_id=m.id
           WHERE f.ok=1 AND COALESCE(f.v, 1) < ? AND m.kickoff_utc >= ? ORDER BY m.kickoff_utc DESC LIMIT ?""",
        (CARDS_V, RECOUNT_FROM, RECOUNT))]
    st = {"recent": len(recent), "backfill": len(old), "recount": len(redo), "changed": 0, "ok": 0}
    for mid in recent + old + redo:
        try:
            js = client.get(f"events/{mid}/incidents/")
        except Exception:  # noqa: BLE001
            js = None
        p = parse(js)
        with conn:
            if p:
                before = conn.execute("SELECT cards_home, cards_away FROM match WHERE id=?", (mid,)).fetchone()
                conn.execute("UPDATE match SET cards_home=?, cards_away=? WHERE id=?", (*p, mid))
                st["ok"] += 1
                if before and before[0] is not None and tuple(before) != tuple(p):
                    resettle(conn, mid)
                    st["changed"] += 1
            elif mid in redo:
                continue  # renumărarea nu a reușit acum: păstrăm numărul vechi, încercăm la rularea următoare
            conn.execute("""INSERT INTO card_fetch (match_id, fetched_at, ok, v) VALUES (?,?,?,?) ON CONFLICT(match_id)
                            DO UPDATE SET fetched_at=excluded.fetched_at, ok=excluded.ok, v=excluded.v""",
                         (mid, canon_utc(now.isoformat()), 1 if p else 0, CARDS_V if p else None))
    return st


def resettle(conn: sqlite3.Connection, mid: int) -> None:
    """Cartonașele unui meci s-au schimbat: selecțiile de cartonașe ale meciului se decontează din nou (urmărire și bilete;
    un bilet deja închis se redeschide ca să fie decontat cu numărul corect)."""
    from betpredict.experimental.supersocial import CARD_KEYS

    keys = ",".join("?" * len(CARD_KEYS))
    try:
        conn.execute(f"UPDATE ss_track SET result=NULL WHERE match_id=? AND mkey IN ({keys})", (mid, *CARD_KEYS))
    except sqlite3.OperationalError:
        pass  # fără tabelul de urmărire
    tids = [r[0] for r in conn.execute(
        f"SELECT DISTINCT ticket_id FROM ticket_leg WHERE match_id=? AND market='ss|0' AND selection IN ({keys})", (mid, *CARD_KEYS))]
    conn.execute(f"UPDATE ticket_leg SET result=NULL WHERE match_id=? AND market='ss|0' AND selection IN ({keys})", (mid, *CARD_KEYS))
    for t in tids:
        conn.execute("UPDATE ticket SET status='pending', payout=NULL WHERE id=? AND status IN ('won','lost','void')", (t,))
