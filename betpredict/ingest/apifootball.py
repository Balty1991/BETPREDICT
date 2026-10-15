"""API-Football (plan gratuit): cornere, cartonașe și absenți pe meci, unde BSD nu le are.

Planul gratuit (verificat 15.10.2026): 100 de cereri pe zi; interogările pe sezonul curent (ligă + sezon) sunt blocate,
dar cele pe dată (azi, ieri) și pe meci (statistici, evenimente, echipe de start, accidentări) merg.

Pași, cu buget mic pe rulare și plafon zilnic:
  1. ``fixtures?date=`` pentru ieri și azi → legăm meciurile lor de ale noastre (oră ±3h, nume de echipe);
  2. ``fixtures/statistics?fixture=`` pentru meciurile terminate fără cornere sau cartonașe în baza noastră
     (decontare Stil Supersocial și istoric pentru modelele de cornere și cartonașe);
  3. ``injuries?fixture=`` pentru meciurile care încep în curând, păstrate în ``af_injury`` (informativ).
Fără cheie (``APIFOOTBALL_KEY``) nu face nimic."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from betpredict.timeutil import canon_utc

BASE = "https://v3.football.api-sports.io/"
DAILY_CAP = 90          # din 100: rămâne loc pentru verificări manuale
PER_RUN = 25
MIN_SIM = 0.65

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS af_fixture (match_id INTEGER PRIMARY KEY, fixture_id INTEGER NOT NULL, linked_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS af_usage (day TEXT PRIMARY KEY, n INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS af_done (fixture_id INTEGER NOT NULL, kind TEXT NOT NULL, at TEXT NOT NULL, ok INTEGER NOT NULL, "
    "PRIMARY KEY (fixture_id, kind))",
    "CREATE TABLE IF NOT EXISTS af_injury (match_id INTEGER PRIMARY KEY, home INTEGER NOT NULL, away INTEGER NOT NULL, "
    "players_json TEXT, fetched_at TEXT NOT NULL)",
)


def ensure(conn: sqlite3.Connection) -> None:
    for s in SCHEMA:
        conn.execute(s)
    from betpredict.ingest.cards import ensure as ensure_cards
    from betpredict.ingest.corners import ensure as ensure_corners

    ensure_corners(conn)
    ensure_cards(conn)


class Client:
    def __init__(self, key: str, conn: sqlite3.Connection, today: date, per_run: int = PER_RUN):
        self.key, self.conn, self.day, self.left = key, conn, today.isoformat(), per_run

    def used(self) -> int:
        r = self.conn.execute("SELECT n FROM af_usage WHERE day=?", (self.day,)).fetchone()
        return r[0] if r else 0

    def can(self) -> bool:
        return self.left > 0 and self.used() < DAILY_CAP

    def get(self, path: str) -> Optional[Dict[str, Any]]:
        if not self.can():
            return None
        import requests

        self.left -= 1
        with self.conn:
            self.conn.execute("INSERT INTO af_usage VALUES (?,1) ON CONFLICT(day) DO UPDATE SET n=n+1", (self.day,))
        try:
            r = requests.get(BASE + path, headers={"x-apisports-key": self.key}, timeout=20)
            js = r.json()
        except Exception:  # noqa: BLE001
            return None
        if js.get("errors"):
            return None
        return js


def _sim(a: str, b: str) -> float:
    from betpredict.ingest.superbet import name_sim

    return name_sim(a, b)


def link(conn: sqlite3.Connection, fixtures: List[Dict[str, Any]], now: datetime) -> int:
    """Leagă meciurile API-Football de ale noastre: oră ±3h, o echipă sigură și cealaltă plauzibilă."""
    n = 0
    for f in fixtures:
        try:
            fid = int(f["fixture"]["id"])
            kick = datetime.fromisoformat(str(f["fixture"]["date"]).replace("Z", "+00:00")).astimezone(timezone.utc)
            home, away = f["teams"]["home"]["name"], f["teams"]["away"]["name"]
        except (KeyError, TypeError, ValueError):
            continue
        lo, hi = canon_utc((kick - timedelta(hours=3)).isoformat()), canon_utc((kick + timedelta(hours=3)).isoformat())
        best, score = None, 0.0
        for m in conn.execute("SELECT id, home_name, away_name FROM match WHERE kickoff_utc BETWEEN ? AND ?", (lo, hi)):
            a, b = _sim(home, m["home_name"] or ""), _sim(away, m["away_name"] or "")
            s = (a + b) / 2 if max(a, b) >= 0.9 and min(a, b) >= 0.3 else 0.0
            if s > score:
                best, score = m, s
        if best is not None and score >= MIN_SIM:
            conn.execute("INSERT INTO af_fixture VALUES (?,?,?) ON CONFLICT(match_id) DO UPDATE SET fixture_id=excluded.fixture_id",
                         (best["id"], fid, canon_utc(now.isoformat())))
            n += 1
    return n


def parse_stats(js: Dict[str, Any]) -> Optional[Tuple[Optional[int], Optional[int], Optional[int], Optional[int]]]:
    """(cornere gazde, cornere oaspeți, cartonașe gazde, cartonașe oaspeți) din fixtures/statistics; primul e gazda."""
    resp = js.get("response") or []
    if len(resp) != 2:
        return None

    def val(team: Dict[str, Any], name: str) -> Optional[int]:
        for s in team.get("statistics") or []:
            if s.get("type") == name:
                v = s.get("value")
                return 0 if v is None else int(v) if str(v).isdigit() else None
        return None

    h, a = resp
    ch, ca = val(h, "Corner Kicks"), val(a, "Corner Kicks")
    yh, ya, rh, ra = val(h, "Yellow Cards"), val(a, "Yellow Cards"), val(h, "Red Cards"), val(a, "Red Cards")
    cards_h = None if yh is None else yh + (rh or 0)
    cards_a = None if ya is None else ya + (ra or 0)
    if ch is None and cards_h is None:
        return None
    return ch, ca, cards_h, cards_a


def parse_injuries(js: Dict[str, Any], home_team_id: Optional[int]) -> Tuple[int, int, List[Dict[str, Any]]]:
    h = a = 0
    players = []
    for x in js.get("response") or []:
        tid = (x.get("team") or {}).get("id")
        p = x.get("player") or {}
        side = "home" if tid == home_team_id else "away"
        h += side == "home"
        a += side == "away"
        players.append({"side": side, "name": p.get("name"), "type": p.get("type"), "reason": p.get("reason")})
    return h, a, players


def collect(conn: sqlite3.Connection, key: Optional[str] = None, now: Optional[datetime] = None,
            per_run: int = PER_RUN, client: Optional[Client] = None) -> Dict[str, Any]:
    key = key if key is not None else os.environ.get("APIFOOTBALL_KEY", "")
    if not key and client is None:
        return {"skipped": "fără APIFOOTBALL_KEY"}
    now = now or datetime.now(timezone.utc)
    ensure(conn)
    cl = client or Client(key, conn, now.date(), per_run)
    st: Dict[str, Any] = {"linked": 0, "stats": 0, "injuries": 0}
    stamp = canon_utc(now.isoformat())
    # 1. legarea: ieri și azi, o dată la 6 ore pe zi
    home_ids: Dict[int, Optional[int]] = {}
    for d in (now.date() - timedelta(days=1), now.date()):
        kind = f"date:{d.isoformat()}"
        prev = conn.execute("SELECT at FROM af_done WHERE fixture_id=0 AND kind=?", (kind,)).fetchone()
        if prev and prev[0] > canon_utc((now - timedelta(hours=6)).isoformat()):
            continue
        js = cl.get(f"fixtures?date={d.isoformat()}")
        if js is None:
            continue
        with conn:
            st["linked"] += link(conn, js.get("response") or [], now)
            conn.execute("INSERT INTO af_done VALUES (0,?,?,1) ON CONFLICT(fixture_id, kind) DO UPDATE SET at=excluded.at", (kind, stamp))
        for f in js.get("response") or []:
            try:
                home_ids[int(f["fixture"]["id"])] = int(f["teams"]["home"]["id"])
            except (KeyError, TypeError, ValueError):
                pass
        if home_ids:
            with conn:
                for fid, tid in home_ids.items():
                    conn.execute("INSERT INTO af_done VALUES (?,?,?,1) ON CONFLICT(fixture_id, kind) DO UPDATE SET at=excluded.at",
                                 (fid, f"home:{tid}", stamp))
    # 2. statistici pentru meciurile terminate fără cornere sau cartonașe (ultimele 2 zile)
    lo = canon_utc((now - timedelta(days=2)).isoformat())
    rows = conn.execute(
        """SELECT m.id, f.fixture_id FROM match m JOIN af_fixture f ON f.match_id=m.id
           LEFT JOIN af_done d ON d.fixture_id=f.fixture_id AND d.kind='stats'
           WHERE m.status='finished' AND m.kickoff_utc >= ? AND (m.corners_home IS NULL OR m.cards_home IS NULL)
             AND (d.fixture_id IS NULL OR (d.ok=0 AND d.at < ?))
           ORDER BY m.kickoff_utc DESC""", (lo, canon_utc((now - timedelta(hours=3)).isoformat()))).fetchall()
    for r in rows:
        if not cl.can():
            break
        js = cl.get(f"fixtures/statistics?fixture={r['fixture_id']}")
        p = parse_stats(js) if js else None
        with conn:
            if p:
                ch, ca, yh, ya = p
                conn.execute("""UPDATE match SET corners_home=COALESCE(corners_home, ?), corners_away=COALESCE(corners_away, ?),
                                cards_home=COALESCE(cards_home, ?), cards_away=COALESCE(cards_away, ?) WHERE id=?""",
                             (ch, ca, yh, ya, r["id"]))
                st["stats"] += 1
            conn.execute("INSERT INTO af_done VALUES (?, 'stats', ?, ?) ON CONFLICT(fixture_id, kind) DO UPDATE SET at=excluded.at, ok=excluded.ok",
                         (r["fixture_id"], stamp, 1 if p else 0))
    # 3. absenți pentru meciurile din următoarele 12 ore aflate pe biletele în joc (cele mai apropiate întâi)
    hi = canon_utc((now + timedelta(hours=12)).isoformat())
    rows = conn.execute(
        """SELECT DISTINCT m.id, f.fixture_id, m.kickoff_utc FROM match m JOIN af_fixture f ON f.match_id=m.id
           JOIN ticket_leg tl ON tl.match_id=m.id JOIN ticket t ON t.id=tl.ticket_id
           WHERE t.status='pending' AND m.kickoff_utc > ? AND m.kickoff_utc <= ?
             AND NOT EXISTS (SELECT 1 FROM af_injury i WHERE i.match_id=m.id AND i.fetched_at > ?)
           ORDER BY m.kickoff_utc""", (stamp, hi, canon_utc((now - timedelta(hours=6)).isoformat()))).fetchall()
    for r in rows:
        if not cl.can():
            break
        js = cl.get(f"injuries?fixture={r['fixture_id']}")
        if js is None:
            continue
        hrow = conn.execute("SELECT kind FROM af_done WHERE fixture_id=? AND kind LIKE 'home:%'", (r["fixture_id"],)).fetchone()
        tid = int(hrow[0].split(":")[1]) if hrow else None
        h, a, players = parse_injuries(js, tid)
        with conn:
            conn.execute("INSERT INTO af_injury VALUES (?,?,?,?,?) ON CONFLICT(match_id) DO UPDATE SET home=excluded.home, "
                         "away=excluded.away, players_json=excluded.players_json, fetched_at=excluded.fetched_at",
                         (r["id"], h, a, json.dumps(players, ensure_ascii=False), stamp))
        st["injuries"] += 1
    st["used_today"] = cl.used()
    return st
