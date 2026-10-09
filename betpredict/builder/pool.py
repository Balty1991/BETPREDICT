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

# ponderea modelului în probabilitatea prudentă (restul = piața fără marjă)
SHRINK_MODEL_WEIGHT = 0.5


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
    p_market: Optional[float] = None  # probabilitatea pieței fără marjă (no-vig), dacă există
    odds_source: Optional[str] = None  # „bsd_consensus” = cotă reală; None/legacy = fără sursă verificată

    @property
    def p_mkt(self) -> float:
        """Probabilitatea pieței: no-vig dacă o avem, altfel cota implicită minus ~5% marjă."""
        if self.p_market is not None and 0 < self.p_market < 1:
            return self.p_market
        return min(0.97, (1.0 / self.odds) / 1.05)

    @property
    def p_adj(self) -> float:
        """Probabilitate prudentă: modelul tras spre piață (shrink învățat pe piață) + corecția
        tipului de selecție învățată din rezultate (vezi ``builder.optimizer``)."""
        from betpredict.builder import optimizer

        return optimizer.leg_p(self.p, self.p_market, self.odds, self.market, self.line or 0.0)

    @property
    def safety(self) -> dict:
        from betpredict.builder import optimizer

        return optimizer.safety(self.p, self.confidence)

    @property
    def ev_adj(self) -> float:
        return self.p_adj * self.odds - 1

    @property
    def logp_adj(self) -> float:
        return math.log(max(1e-6, self.p_adj))

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
    from betpredict.builder import optimizer

    optimizer.load_strategy(conn)  # strategia de bilete învățată (shrink, corecții, filtre)
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
                        r["grade"] or "D", r["confidence"] or 0, healthy, p_market=r["p_market_novig"],
                        odds_source=r["odds_source"]))
    return out


def ticket_probability(legs: List[Cand], adjusted: bool = False) -> float:
    """Probabilitatea biletului prin Monte Carlo cu incertitudine pe probabilități (factor comun
    pe ligă și pe ora de start) — vezi ``builder.optimizer.ticket_eval``.
    ``adjusted=True`` folosește probabilitatea prudentă (model tras spre piață)."""
    from betpredict.builder import optimizer

    return optimizer.ticket_probability(legs, adjusted=adjusted)
