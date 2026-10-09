"""Pool-ul de selecții jucabile pentru o zi (din jurnal, deci deja salvate)."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import List, Optional

from betpredict.config import MIN_ODDS
from betpredict.robot import MODEL_VERSION
from betpredict.robot.markets import label_ro
from betpredict.timeutil import canon_utc


@dataclass
class Cand:
    prediction_id: int
    match_id: int
    league_id: Optional[int]
    league: Optional[str]
    kickoff_utc: str
    home: Optional[str]
    away: Optional[str]
    market: str
    line: float
    selection: str
    odds: float
    p: float
    ev: float
    grade: str
    confidence: int
    healthy: bool = True
    extra: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return label_ro(self.market, self.line or 0.0, self.selection)

    @property
    def logp(self) -> float:
        return math.log(max(1e-6, self.p))

    @property
    def logo(self) -> float:
        return math.log(self.odds)


def load_pool(conn: sqlite3.Connection, day: date, now: Optional[datetime] = None, min_odds: float = MIN_ODDS) -> List[Cand]:
    now_s = canon_utc((now or datetime.now(timezone.utc)).isoformat())
    rows = conn.execute(
        """SELECT p.*, m.kickoff_utc, m.home_name, m.away_name, m.league_id, l.name AS league_name
           FROM prediction p JOIN match m ON m.id = p.match_id LEFT JOIN league l ON l.id = m.league_id
           WHERE p.day = ? AND p.model_version = ? AND p.shown_on_page = 'predictii'
             AND p.result IS NULL AND p.odds_shown IS NOT NULL AND p.odds_shown >= ? AND m.kickoff_utc > ?""",
        (day.isoformat(), MODEL_VERSION, min_odds, now_s),
    ).fetchall()
    out = []
    for r in rows:
        try:
            healthy = bool(json.loads(r["reasons_json"] or "{}").get("healthy", True))
        except ValueError:
            healthy = True
        out.append(Cand(r["id"], r["match_id"], r["league_id"], r["league_name"], r["kickoff_utc"], r["home_name"],
                        r["away_name"], r["market"], r["line"] or 0.0, r["selection"], r["odds_shown"],
                        r["p_calibrated"], r["ev"] if r["ev"] is not None else r["p_calibrated"] * r["odds_shown"] - 1,
                        r["grade"] or "D", r["confidence"] or 0, healthy))
    return out


def ticket_probability(legs: List[Cand]) -> float:
    """Produsul probabilităților cu penalizare de corelație (aceeași ligă / aceeași oră) și shrink."""
    p = 1.0
    for c in legs:
        p *= c.p
    leagues = [c.league_id for c in legs]
    same_league_pairs = sum(leagues.count(l) - 1 for l in set(leagues) if l is not None)
    hours = [c.kickoff_utc[:13] for c in legs]
    same_hour = sum(hours.count(h) - 1 for h in set(hours))
    p *= 0.98 ** same_league_pairs * 0.995 ** same_hour
    return p * 0.97 ** max(0, len(legs) - 1) ** 0.5  # marjă de siguranță față de supraîncredere
