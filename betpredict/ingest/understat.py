"""Understat: xG istoric pe meci (top-5 ligi + RFPL), legat de tabelul ``match`` după dată și nume.

Sursă publică (nu consumă cota BSD): ``/getLeagueData/<LIGA>/<AN>`` — o cerere pe ligă × sezon.
Rulează doar în modul learn (săptămânal); sezoanele încheiate se descarcă o singură dată."""

from __future__ import annotations

import gzip
import json
import sqlite3
import time
import urllib.request
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence

URL = "https://understat.com/getLeagueData/{league}/{season}"
LEAGUES = ("EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1", "RFPL")
FIRST_SEASON = 2014
SCHEMA = """
CREATE TABLE IF NOT EXISTS us_match (
  us_id INTEGER PRIMARY KEY, league TEXT NOT NULL, season INTEGER NOT NULL, day TEXT NOT NULL,
  home TEXT NOT NULL, away TEXT NOT NULL, gh INTEGER, ga INTEGER, xg_h REAL, xg_a REAL, match_id INTEGER);
CREATE INDEX IF NOT EXISTS ix_us_match_mid ON us_match(match_id);
"""


def current_season(today: date) -> int:
    return today.year if today.month >= 7 else today.year - 1


def parse(payload: Dict[str, Any], league: str, season: int) -> List[Dict[str, Any]]:
    out = []
    for m in payload.get("dates") or []:
        if not m.get("isResult"):
            continue
        try:
            out.append({"us_id": int(m["id"]), "league": league, "season": season, "day": str(m["datetime"])[:10],
                        "home": m["h"]["title"], "away": m["a"]["title"], "gh": int(m["goals"]["h"]), "ga": int(m["goals"]["a"]),
                        "xg_h": float(m["xG"]["h"]), "xg_a": float(m["xG"]["a"])})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def fetch(league: str, season: int, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
    req = urllib.request.Request(URL.format(league=league, season=season), headers={
        "User-Agent": "Mozilla/5.0 (BetPredict personal)", "X-Requested-With": "XMLHttpRequest", "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None


def link(conn: sqlite3.Connection) -> int:
    from betpredict.ingest.superbet import name_sim

    rows = conn.execute("SELECT us_id, day, home, away, gh, ga FROM us_match WHERE match_id IS NULL").fetchall()
    cand: Dict[str, List] = {}
    n = 0
    with conn:
        for r in rows:
            d = r[1]
            if d not in cand:
                lo = (date.fromisoformat(d) - timedelta(days=1)).isoformat()
                hi = (date.fromisoformat(d) + timedelta(days=2)).isoformat()
                cand[d] = conn.execute("SELECT id, home_name, away_name, ft_home, ft_away FROM match WHERE kickoff_utc >= ? AND kickoff_utc < ?",
                                       (lo, hi)).fetchall()
            best, bs = None, 0.0
            for m in cand[d]:
                if (m[3], m[4]) != (r[4], r[5]):
                    continue  # scorul final trebuie să coincidă (și taie 90% din comparațiile de nume)
                s = min(name_sim(r[2], m[1] or ""), name_sim(r[3], m[2] or ""))
                if s > bs:
                    best, bs = m, s
            if best is not None and bs >= 0.72:
                conn.execute("UPDATE us_match SET match_id=? WHERE us_id=?", (best[0], r[0]))
                n += 1
    return n


def ingest_understat(conn: sqlite3.Connection, today: Optional[date] = None, leagues: Sequence[str] = LEAGUES,
                     first_season: int = FIRST_SEASON, pause: float = 0.5) -> Dict[str, Any]:
    today = today or date.today()
    conn.executescript(SCHEMA)
    cur = current_season(today)
    have = {(r[0], r[1]) for r in conn.execute("SELECT league, season FROM us_match GROUP BY 1, 2")}
    stats = {"requests": 0, "rows": 0, "linked": 0, "failed": 0}
    for lg in leagues:
        for s in range(first_season, cur + 1):
            if (lg, s) in have and s < cur:
                continue  # sezon încheiat, deja descărcat
            data = fetch(lg, s)
            stats["requests"] += 1
            if data is None:
                stats["failed"] += 1
                continue
            rows = parse(data, lg, s)
            with conn:
                conn.executemany("INSERT INTO us_match(us_id, league, season, day, home, away, gh, ga, xg_h, xg_a) "
                                 "VALUES (:us_id,:league,:season,:day,:home,:away,:gh,:ga,:xg_h,:xg_a) "
                                 "ON CONFLICT(us_id) DO UPDATE SET xg_h=excluded.xg_h, xg_a=excluded.xg_a, gh=excluded.gh, ga=excluded.ga",
                                 rows)
            stats["rows"] += len(rows)
            time.sleep(pause)
    stats["linked"] = link(conn)
    stats["total_linked"] = conn.execute("SELECT COUNT(*) FROM us_match WHERE match_id IS NOT NULL").fetchone()[0]
    return stats


def load_xg(conn: sqlite3.Connection) -> Dict[int, tuple]:
    try:
        return {int(r[0]): (float(r[1]), float(r[2])) for r in conn.execute(
            "SELECT match_id, xg_h, xg_a FROM us_match WHERE match_id IS NOT NULL")}
    except sqlite3.OperationalError:
        return {}
