"""Conexiune SQLite + migrații versionate prin ``PRAGMA user_version``."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path
from typing import Callable, Dict, List, Union

SCHEMA_VERSION = 1

TABLES = (
    "league", "season", "team", "match", "match_stats", "odds_snapshot", "team_form",
    "availability", "feature_row", "provider_prediction", "prediction", "ticket", "ticket_leg",
    "pyramid_run", "pyramid_step", "model_registry", "learning_log", "ingest_state",
)


def _schema_v1(conn: sqlite3.Connection) -> None:
    sql = resources.files("betpredict.store").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.executescript(sql)


# Migrațiile viitoare se adaugă aici, în ordine, fără a modifica cele vechi.
MIGRATIONS: List[Callable[[sqlite3.Connection], None]] = [_schema_v1]


def connect(path: Union[str, Path]) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> int:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, migrate in enumerate(MIGRATIONS, start=1):
        if version <= current:
            continue
        with conn:
            migrate(conn)
            conn.execute(f"PRAGMA user_version = {version}")
    return conn.execute("PRAGMA user_version").fetchone()[0]


def table_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
