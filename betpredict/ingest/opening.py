"""Cote de deschidere: prima cotă văzută per (meci, piață, linie, selecție, sursă), înregistrată la fiecare rulare.

Superbet: primul preț din odds_snapshot; consensus BSD: opening_decimal (dat de API). Tabelul nu se curăță la retenție,
astfel filtrul de drift (cota curentă / deschidere − 1) funcționează live, ca în laborator."""

from __future__ import annotations

import sqlite3
from typing import Dict, Optional, Tuple

SCHEMA = """CREATE TABLE IF NOT EXISTS odds_open (
  match_id INTEGER NOT NULL, market TEXT NOT NULL, line REAL NOT NULL DEFAULT 0, outcome TEXT NOT NULL,
  source TEXT NOT NULL, decimal REAL NOT NULL, first_seen TEXT NOT NULL,
  PRIMARY KEY (match_id, market, line, outcome, source))"""


def record_openings(conn: sqlite3.Connection) -> int:
    conn.execute(SCHEMA)
    before = conn.total_changes
    with conn:
        conn.execute(
            """INSERT OR IGNORE INTO odds_open (match_id, market, line, outcome, source, decimal, first_seen)
               SELECT s.match_id, s.market, s.line, s.outcome, s.source,
                      CASE WHEN s.source = 'bsd_consensus' AND s.opening_decimal IS NOT NULL THEN s.opening_decimal ELSE s.decimal END,
                      s.observed_at
               FROM odds_snapshot s
               JOIN (SELECT match_id, market, line, outcome, source, MIN(observed_at) mo FROM odds_snapshot
                     WHERE period = 'FT' GROUP BY 1, 2, 3, 4, 5) f
                 ON f.match_id = s.match_id AND f.market = s.market AND f.line = s.line AND f.outcome = s.outcome
                AND f.source = s.source AND f.mo = s.observed_at
               WHERE s.period = 'FT'""")
    return conn.total_changes - before


def opening_map(conn: sqlite3.Connection, match_ids) -> Dict[Tuple[int, str, float, str, str], float]:
    ids = list({int(m) for m in match_ids})
    if not ids:
        return {}
    conn.execute(SCHEMA)
    out: Dict[Tuple[int, str, float, str, str], float] = {}
    for i in range(0, len(ids), 500):
        ch = ids[i:i + 500]
        for r in conn.execute(f"SELECT match_id, market, line, outcome, source, decimal FROM odds_open WHERE match_id IN ({','.join('?' * len(ch))})", ch):
            out[(r[0], r[1], float(r[2] or 0), r[3], r[4])] = r[5]
    return out


def drift_of(omap, match_id: int, market: str, line: float, outcome: str, odds: float, source: Optional[str]) -> Optional[float]:
    for src in ((source,) if source else ()) + ("superbet", "bsd_consensus"):
        o = omap.get((match_id, market, float(line or 0), outcome, src))
        if o and o > 1:
            return odds / o - 1
    return None
