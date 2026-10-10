"""football-data.co.uk: cote istorice de deschidere și închidere (medie/maxim), cornere, cartonașe și scor la pauză.

Rulează săptămânal (modul learn). Se folosesc cotele Avg/Max, nu Pinnacle: după 23.07.2025 coloanele PS* nu mai sunt
fiabile. Meciurile se leagă de tabelul ``match`` după dată (±1 zi) și similaritatea numelor (aceleași reguli ca la
Superbet). Pentru meciurile legate se completează cornerele, cartonașele și scorul la pauză, dacă lipsesc."""

from __future__ import annotations

import csv
import io
import sqlite3
import time
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from betpredict.store import repo

BASE = "https://www.football-data.co.uk/mmz4281/{season}/{div}.csv"
DIVS = ("E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "D1", "D2", "I1", "I2", "SP1", "SP2", "F1", "F2", "N1", "B1", "P1", "T1", "G1")
COLS = {  # coloana DB → coloana CSV
    "avg_h": "AvgH", "avg_d": "AvgD", "avg_a": "AvgA", "max_h": "MaxH", "max_d": "MaxD", "max_a": "MaxA",
    "avgc_h": "AvgCH", "avgc_d": "AvgCD", "avgc_a": "AvgCA", "maxc_h": "MaxCH", "maxc_d": "MaxCD", "maxc_a": "MaxCA",
    "avg_o25": "Avg>2.5", "avg_u25": "Avg<2.5", "avgc_o25": "AvgC>2.5", "avgc_u25": "AvgC<2.5",
    "fthg": "FTHG", "ftag": "FTAG", "hthg": "HTHG", "htag": "HTAG", "hc": "HC", "ac": "AC", "hy": "HY", "ay": "AY",
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS fd_match (
  div TEXT NOT NULL, season TEXT NOT NULL, day TEXT NOT NULL, home TEXT NOT NULL, away TEXT NOT NULL,
  referee TEXT, match_id INTEGER, """ + ", ".join(f"{c} REAL" for c in COLS) + """,
  PRIMARY KEY (div, season, day, home, away));
CREATE INDEX IF NOT EXISTS ix_fd_match_mid ON fd_match(match_id);
"""


def seasons_for(today: date, n: int = 3) -> List[str]:
    y = today.year if today.month >= 7 else today.year - 1
    return [f"{(y - i) % 100:02d}{(y - i + 1) % 100:02d}" for i in range(n)]


def _num(x: Optional[str]) -> Optional[float]:
    try:
        return float(x) if x not in (None, "") else None
    except ValueError:
        return None


def _day(s: str) -> Optional[str]:
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def parse_csv(text: str, div: str, season: str) -> List[Dict[str, Any]]:
    out = []
    for r in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        d = _day(r.get("Date") or "")
        if not d or not r.get("HomeTeam") or not r.get("AwayTeam"):
            continue
        row = {"div": div, "season": season, "day": d, "home": r["HomeTeam"].strip(), "away": r["AwayTeam"].strip(),
               "referee": (r.get("Referee") or "").strip() or None}
        for c, k in COLS.items():
            row[c] = _num(r.get(k))
        out.append(row)
    return out


def fetch(div: str, season: str, timeout: float = 30.0) -> Optional[str]:
    req = urllib.request.Request(BASE.format(season=season, div=div), headers={"User-Agent": "Mozilla/5.0 (BetPredict personal)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None


def link_matches(conn: sqlite3.Connection) -> int:
    from betpredict.ingest.superbet import name_sim

    rows = conn.execute("SELECT rowid, day, home, away FROM fd_match WHERE match_id IS NULL").fetchall()
    if not rows:
        return 0
    days = sorted({r["day"] for r in rows})
    cand: Dict[str, List[sqlite3.Row]] = {}
    for d in days:
        lo = (date.fromisoformat(d) - timedelta(days=1)).isoformat()
        hi = (date.fromisoformat(d) + timedelta(days=2)).isoformat()
        cand[d] = conn.execute("SELECT id, home_name, away_name FROM match WHERE kickoff_utc >= ? AND kickoff_utc < ?", (lo, hi)).fetchall()
    n = 0
    with conn:
        for r in rows:
            best, bs = None, 0.0
            for m in cand.get(r["day"], []):
                s = min(name_sim(r["home"], m["home_name"] or ""), name_sim(r["away"], m["away_name"] or ""))
                if s > bs:
                    best, bs = m, s
            if best is not None and bs >= 0.72:
                conn.execute("UPDATE fd_match SET match_id=? WHERE rowid=?", (best["id"], r["rowid"]))
                n += 1
        # completează scorul la pauză și cornerele lipsă în match (pentru modelul de cornere / reprize)
        conn.execute("""UPDATE match SET
              ht_home = COALESCE(ht_home, (SELECT CAST(f.hthg AS INTEGER) FROM fd_match f WHERE f.match_id = match.id)),
              ht_away = COALESCE(ht_away, (SELECT CAST(f.htag AS INTEGER) FROM fd_match f WHERE f.match_id = match.id)),
              corners_home = COALESCE(corners_home, (SELECT CAST(f.hc AS INTEGER) FROM fd_match f WHERE f.match_id = match.id)),
              corners_away = COALESCE(corners_away, (SELECT CAST(f.ac AS INTEGER) FROM fd_match f WHERE f.match_id = match.id))
            WHERE id IN (SELECT match_id FROM fd_match WHERE match_id IS NOT NULL)""")
    return n


def ingest_footballdata(conn: sqlite3.Connection, today: Optional[date] = None, divs: Sequence[str] = DIVS,
                        seasons: Optional[Sequence[str]] = None, pause: float = 1.0, fetcher=fetch) -> Dict[str, Any]:
    conn.executescript(SCHEMA)
    today = today or date.today()
    seasons = list(seasons or seasons_for(today))
    st: Dict[str, Any] = {"files": 0, "rows": 0, "missing": []}
    done_key = "fd.done"
    done = set((repo.get_state(conn, done_key) or "").split(",")) - {""}
    cur = seasons_for(today, 1)[0]
    cols = ["div", "season", "day", "home", "away", "referee"] + list(COLS)
    for season in seasons:
        for div in divs:
            tag = f"{season}/{div}"
            if season != cur and tag in done:
                continue  # sezoanele încheiate se descarcă o singură dată
            text = fetcher(div, season)
            if not text:
                st["missing"].append(tag)
                continue
            rows = parse_csv(text, div, season)
            with conn:
                for r in rows:
                    conn.execute(f"INSERT INTO fd_match({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
                                 f"ON CONFLICT(div, season, day, home, away) DO UPDATE SET "
                                 + ", ".join(f"{c}=excluded.{c}" for c in cols[5:]),
                                 [r[c] for c in cols])
            st["files"] += 1
            st["rows"] += len(rows)
            if season != cur:
                done.add(tag)
            time.sleep(pause)
    with conn:
        repo.set_state(conn, done_key, ",".join(sorted(done)))
    st["linked"] = link_matches(conn)
    st["missing"] = st["missing"][:10]
    return st
