"""Conexiune SQLite + migrații versionate prin ``PRAGMA user_version``."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path
from typing import Callable, Dict, List, Union

SCHEMA_VERSION = 4

TABLES = (
    "league", "season", "team", "match", "match_stats", "odds_snapshot", "team_form",
    "availability", "feature_row", "provider_prediction", "prediction", "ticket", "ticket_leg",
    "pyramid_run", "pyramid_step", "model_registry", "learning_log", "ingest_state",
    "match_context", "match_model", "ext_event", "team_alias", "sb_offer", "bb_suggestion",
)


def _schema_v1(conn: sqlite3.Connection) -> None:
    sql = resources.files("betpredict.store").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.executescript(sql)


def _schema_v2(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS match_context (
          match_id     INTEGER PRIMARY KEY,
          context_json TEXT NOT NULL,      -- formă, H2H, clasament, absențe (vezi docs/data-contract.md)
          updated_at   TEXT
        );
        CREATE TABLE IF NOT EXISTS match_model (
          match_id      INTEGER PRIMARY KEY,
          model_version TEXT,
          lambda_home   REAL, lambda_away REAL,
          elo_home      REAL, elo_away REAL,
          extra_json    TEXT,
          updated_at    TEXT
        );
        ALTER TABLE prediction ADD COLUMN p_bsd REAL;
        ALTER TABLE prediction ADD COLUMN is_pick INTEGER DEFAULT 0;
        ALTER TABLE prediction ADD COLUMN day TEXT;
        CREATE INDEX IF NOT EXISTS ix_pred_day ON prediction(day);
        CREATE INDEX IF NOT EXISTS ix_pred_match ON prediction(match_id);
        ALTER TABLE ticket ADD COLUMN day TEXT;
        CREATE INDEX IF NOT EXISTS ix_ticket_day ON ticket(day);
        """
    )


def _schema_v3(conn: sqlite3.Connection) -> None:
    """Superbet (cote jucabile) + linia de închidere (CLV)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ext_event (
          match_id    INTEGER NOT NULL,
          source      TEXT NOT NULL,           -- superbet
          ext_id      TEXT NOT NULL,
          score       REAL,
          method      TEXT,                    -- alias | nume | nume+alias
          ext_name    TEXT,
          matched_at  TEXT,
          checked_at  TEXT,                    -- ultima citire bulk (1X2) înainte de start
          detail_at   TEXT,                    -- ultima citire completă (toate piețele) înainte de start
          PRIMARY KEY (match_id, source),
          UNIQUE (source, ext_id)
        );
        CREATE TABLE IF NOT EXISTS team_alias (
          source       TEXT NOT NULL,
          ext_team_id  TEXT NOT NULL,
          team_id      INTEGER NOT NULL,
          ext_name     TEXT,
          learned_at   TEXT,
          PRIMARY KEY (source, ext_team_id)
        );
        CREATE INDEX IF NOT EXISTS ix_odds_src ON odds_snapshot(match_id, source, observed_at);
        ALTER TABLE prediction ADD COLUMN odds_taken REAL;
        ALTER TABLE prediction ADD COLUMN odds_taken_source TEXT;
        ALTER TABLE prediction ADD COLUMN odds_taken_at TEXT;
        ALTER TABLE ticket_leg ADD COLUMN odds_source TEXT;
        ALTER TABLE ticket_leg ADD COLUMN closing_odds REAL;
        ALTER TABLE ticket ADD COLUMN clv REAL;
        """
    )


# Migrațiile viitoare se adaugă aici, în ordine, fără a modifica cele vechi.
def _schema_v4(conn: sqlite3.Connection) -> None:
    """v4: oferta Superbet brută (piețe speciale + combinații Bet Builder) + sugestiile Bet Builder urmărite (experimental)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sb_offer (
            match_id INTEGER NOT NULL, market_id INTEGER, market_name TEXT NOT NULL, outcome TEXT NOT NULL,
            line TEXT, price REAL NOT NULL, observed_at TEXT NOT NULL,
            PRIMARY KEY (match_id, market_name, outcome));
        CREATE TABLE IF NOT EXISTS bb_suggestion (
            id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER NOT NULL, day TEXT, legs_json TEXT NOT NULL,
            label TEXT NOT NULL, p_joint REAL NOT NULL, fair_odds REAL NOT NULL, min_odds REAL NOT NULL,
            sb_price REAL, ev REAL, source TEXT, created_at TEXT NOT NULL, result TEXT, settled_at TEXT,
            UNIQUE (match_id, label));
        """
    )


MIGRATIONS: List[Callable[[sqlite3.Connection], None]] = [_schema_v1, _schema_v2, _schema_v3, _schema_v4]


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
