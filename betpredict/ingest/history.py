"""Import istoric din depozitul vechi ``data/warehouse/events_season_*.json``.

Reparații față de depozitul vechi:
  * anii greșiți (2070–2079, din parsarea „70/71”) sunt ignorați — data meciului
    (``date``) e sursa de adevăr, nu ``season_year``;
  * datele cu offset (+04:00 etc.) sunt convertite în UTC canonic;
  * meciurile viitoare / fără scor nu intră ca istoric.
Sezonul curent se completează din ``/events/?status=finished`` în ``settle``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from betpredict.ingest.normalize import as_int
from betpredict.store import repo
from betpredict.timeutil import canon_utc

STATE_KEY = "history.warehouse_imported"


def import_warehouse(conn: sqlite3.Connection, warehouse_dir: Path, min_year: int = 2012, force: bool = False) -> Dict[str, int]:
    stats = {"files": 0, "rows": 0, "inserted": 0, "skipped_future_or_noscore": 0, "skipped_bad_date": 0}
    if not force and repo.get_state(conn, STATE_KEY):
        stats["already_imported"] = 1
        return stats
    now = datetime.now(timezone.utc)
    now_s = canon_utc(now.isoformat())
    leagues: Dict[int, str] = {}
    files = sorted(Path(warehouse_dir).glob("events_season_*.json"))
    with conn:
        for f in files:
            try:
                rows = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(rows, dict):
                rows = rows.get("events") or rows.get("results") or []
            stats["files"] += 1
            batch = []
            for r in rows:
                if not isinstance(r, dict):
                    continue
                stats["rows"] += 1
                ko = canon_utc(r.get("date") or r.get("event_date"))
                if not ko or int(ko[:4]) < min_year or int(ko[:4]) > now.year + 1:
                    stats["skipped_bad_date"] += 1
                    continue
                hs, as_ = as_int(r.get("home_score")), as_int(r.get("away_score"))
                if hs is None or as_ is None or ko > now_s:
                    stats["skipped_future_or_noscore"] += 1
                    continue
                lid = as_int(r.get("league_id"))
                if lid is not None and r.get("league"):
                    leagues[lid] = r["league"]
                batch.append((
                    as_int(r.get("event_id")), as_int(r.get("season_id")), lid, ko,
                    as_int(r.get("home_team_id")), as_int(r.get("away_team_id")),
                    r.get("home_team"), r.get("away_team"), "finished", hs, as_,
                    r.get("xg_home"), r.get("xg_away"), now_s,
                ))
            before = conn.total_changes
            conn.executemany(
                """INSERT OR IGNORE INTO match (id, season_id, league_id, kickoff_utc, home_id, away_id,
                   home_name, away_name, status, ft_home, ft_away, xg_home, xg_away, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [b for b in batch if b[0] is not None],
            )
            stats["inserted"] += conn.total_changes - before
        for lid, name in leagues.items():
            repo.upsert_league(conn, {"id": lid, "name": name})
        repo.set_state(conn, STATE_KEY, now_s)
    return stats


def finished_matches(conn: sqlite3.Connection, since_utc: Optional[str] = None, until_utc: Optional[str] = None):
    q = ("SELECT id, league_id, kickoff_utc, home_id, away_id, ft_home, ft_away FROM match "
         "WHERE status='finished' AND ft_home IS NOT NULL AND ft_away IS NOT NULL "
         "AND home_id IS NOT NULL AND away_id IS NOT NULL")
    args = []
    if since_utc:
        q += " AND kickoff_utc >= ?"
        args.append(since_utc)
    if until_utc:
        q += " AND kickoff_utc < ?"
        args.append(until_utc)
    q += " ORDER BY kickoff_utc"
    return conn.execute(q, args).fetchall()
