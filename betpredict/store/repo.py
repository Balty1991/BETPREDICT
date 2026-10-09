"""Operații de scriere/citire pe schema SQLite (idempotente)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _upsert(conn: sqlite3.Connection, table: str, row: Dict[str, Any], key: str = "id", keep_existing: Iterable[str] = ()) -> None:
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    keep = set(keep_existing)
    updates = ",".join(
        f"{c}=COALESCE(excluded.{c}, {table}.{c})" if c in keep else f"{c}=excluded.{c}"
        for c in cols if c != key
    )
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT({key}) DO UPDATE SET {updates}"
    conn.execute(sql, [row[c] for c in cols])


def upsert_league(conn: sqlite3.Connection, league: Dict[str, Any]) -> None:
    row = {"id": league["id"], "name": league.get("name"), "country": league.get("country"), "updated_at": now_iso()}
    _upsert(conn, "league", row, keep_existing=("name", "country"))


def upsert_team(conn: sqlite3.Connection, team_id: Optional[int], name: Optional[str], league_id: Optional[int] = None) -> None:
    if team_id is None:
        return
    _upsert(conn, "team", {"id": team_id, "name": name, "league_id": league_id}, keep_existing=("name", "league_id"))


def upsert_match(conn: sqlite3.Connection, match: Dict[str, Any]) -> None:
    if match.get("id") is None or not match.get("kickoff_utc"):
        return
    _upsert(conn, "match", match, keep_existing=("xg_home", "xg_away", "home_name", "away_name", "league_id", "season_id"))
    # dacă ora de start se mută peste miezul nopții (RO), predicțiile urmează meciul în ziua lui,
    # ca jurnalul/statisticile (p.day) să coincidă cu pagina zilei (după kickoff_utc).
    from betpredict.timeutil import ro_date_of
    d = ro_date_of(match["kickoff_utc"])
    if d is not None:
        conn.execute("UPDATE prediction SET day=? WHERE match_id=? AND day IS NOT NULL AND day<>?",
                     (d.isoformat(), match["id"], d.isoformat()))


def insert_odds(conn: sqlite3.Connection, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    cols = ["match_id", "market", "line", "period", "outcome", "decimal", "opening_decimal",
            "previous_decimal", "movement", "source", "observed_at"]
    before = conn.total_changes
    conn.executemany(
        f"INSERT OR IGNORE INTO odds_snapshot ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
        [[r.get(c) for c in cols] for r in rows],
    )
    return conn.total_changes - before


def upsert_provider_predictions(conn: sqlite3.Connection, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    cols = ["match_id", "source", "market", "line", "selection", "probability", "model_version", "fetched_at"]
    conn.executemany(
        f"INSERT INTO provider_prediction ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) "
        "ON CONFLICT(match_id, source, market, line, selection) DO UPDATE SET "
        "probability=excluded.probability, model_version=excluded.model_version, fetched_at=excluded.fetched_at",
        [[r.get(c) for c in cols] for r in rows],
    )
    return len(rows)


def latest_odds(conn: sqlite3.Connection, match_ids: List[int]) -> Dict[int, Dict[str, Dict[str, float]]]:
    """Ultima cotă observată pe (meci, piață+linie, rezultat)."""
    out: Dict[int, Dict[str, Dict[str, float]]] = {}
    if not match_ids:
        return out
    q = ",".join("?" for _ in match_ids)
    rows = conn.execute(
        f"""
        SELECT o.match_id, o.market, o.line, o.period, o.outcome, o.decimal, o.opening_decimal, o.movement
        FROM odds_snapshot o
        JOIN (SELECT match_id, market, line, period, outcome, MAX(observed_at) AS mx
              FROM odds_snapshot WHERE match_id IN ({q})
              GROUP BY match_id, market, line, period, outcome) last
          ON o.match_id=last.match_id AND o.market=last.market AND o.line=last.line
         AND o.period=last.period AND o.outcome=last.outcome AND o.observed_at=last.mx
        """,
        match_ids,
    ).fetchall()
    for r in rows:
        mk = market_key(r["market"], r["line"], r["period"])
        out.setdefault(r["match_id"], {}).setdefault(mk, {})[r["outcome"]] = r["decimal"]
    return out


def market_key(market: str, line: float, period: str = "FT") -> str:
    key = market if not line else f"{market}_{line:g}"
    return key if period in (None, "", "FT") else f"{key}_{period}"


def get_state(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM ingest_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO ingest_state(key, value, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value, now_iso()),
    )
