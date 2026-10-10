"""``api/stats/journal.json`` — jurnalul plat al predicțiilor Robotului 3.0 (precalculat pentru pagina Statistici).

Pagina Statistici nu mai descarcă fișierele zilelor (~0,5 MB/zi): primește aici doar câmpurile necesare,
compact (coloane + rânduri, meciurile o singură dată). Aceleași reguli ca în frontend:
doar ``MODEL_VERSION``/``shown_on_page='predictii'``, zile ≥ ``STATS_SINCE``, cu cotă.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

from betpredict.publish.day import write_json
from betpredict.robot import MODEL_VERSION, ROBOT_VERSION, STATS_SINCE, is_recommended
from betpredict.robot.markets import label_ro

JOURNAL_SCHEMA = "betpredict.journal.v1"
COLS = ["date", "match_id", "market", "label", "odds", "p", "result", "profit", "grade", "src"]
SRC = {0: "predicții", 1: "principală", 2: "recomandată"}


def market_id(market: str, line: Any) -> str:
    """Aceeași cheie ca frontend-ul: ``over_under_2.5``; fără linie → doar piața."""
    if not line:
        return market
    return f"{market}_{float(line):g}"


def build_journal(conn: sqlite3.Connection, today: date, days_back: int = 60) -> Dict[str, Any]:
    lo = max(STATS_SINCE, (today - timedelta(days=days_back)).isoformat())
    hi = today.isoformat()
    rows = conn.execute(
        """SELECT p.day, p.match_id, p.market, p.line, p.selection, p.odds_shown, p.p_calibrated, p.ev, p.grade,
                  p.reasons_json, p.result, p.profit_1u, p.is_pick,
                  m.home_name, m.away_name, m.league_id, m.ft_home, m.ft_away, l.name AS league_name
           FROM prediction p JOIN match m ON m.id = p.match_id LEFT JOIN league l ON l.id = m.league_id
           WHERE p.model_version = ? AND p.shown_on_page = 'predictii' AND p.day >= ? AND p.day <= ?
                 AND p.odds_shown IS NOT NULL
           ORDER BY p.day, m.kickoff_utc, p.match_id, p.id""",
        (MODEL_VERSION, lo, hi),
    ).fetchall()
    matches: Dict[str, List[Any]] = {}
    out: List[List[Any]] = []
    for r in rows:
        try:
            healthy = bool(json.loads(r["reasons_json"] or "{}").get("healthy", True))
        except ValueError:
            healthy = True
        mid = r["match_id"]
        if str(mid) not in matches:
            score = f"{r['ft_home']}-{r['ft_away']}" if r["ft_home"] is not None and r["ft_away"] is not None else None
            league = r["league_name"] or (f"Liga #{r['league_id']}" if r["league_id"] else "Ligă necunoscută")
            matches[str(mid)] = [r["home_name"] or "Gazde", r["away_name"] or "Oaspeți", league, score]
        rec = is_recommended(r["p_calibrated"], r["odds_shown"], r["ev"], r["grade"], healthy, _top(r))
        src = 2 if rec else 1 if r["is_pick"] else 0
        p = r["p_calibrated"]
        out.append([r["day"], mid, market_id(r["market"], r["line"]), label_ro(r["market"], r["line"] or 0.0, r["selection"]),
                    r["odds_shown"], round(p, 4) if p is not None else None, r["result"] or "pending",
                    round(r["profit_1u"], 4) if r["profit_1u"] is not None else None, r["grade"], src])
    return {"schema": JOURNAL_SCHEMA, "since": STATS_SINCE, "robot_version": ROBOT_VERSION, "model_version": MODEL_VERSION,
            "from": lo, "to": hi, "cols": COLS, "src": SRC, "matches": matches, "rows": out}


def publish_journal(conn: sqlite3.Connection, out_root: Path, today: date) -> Path:
    return write_json(Path(out_root) / "api" / "stats" / "journal.json", build_journal(conn, today))


def _top(r) -> bool:
    try:
        return bool(json.loads(r["reasons_json"] or "{}").get("top", True))
    except (ValueError, KeyError, IndexError):
        return True
