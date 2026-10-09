"""Import idempotent al jurnalului vechi (``data/selection_journal.json`` +
``data/performance_summary.json``) în schema nouă, ca istoric (``shown_on_page='legacy'``)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from betpredict.ingest.normalize import as_float, as_int
from betpredict.timeutil import canon_utc
from betpredict.store.repo import now_iso, upsert_league, upsert_match, upsert_team

# piața veche → (piață, linie, selecție)
LEGACY_MARKETS: Dict[str, Tuple[str, float, str]] = {
    "homeWin": ("1x2", 0.0, "HOME"),
    "draw": ("1x2", 0.0, "DRAW"),
    "awayWin": ("1x2", 0.0, "AWAY"),
    "over05": ("over_under", 0.5, "OVER"),
    "over15": ("over_under", 1.5, "OVER"),
    "over25": ("over_under", 2.5, "OVER"),
    "over35": ("over_under", 3.5, "OVER"),
    "under15": ("over_under", 1.5, "UNDER"),
    "under25": ("over_under", 2.5, "UNDER"),
    "under35": ("over_under", 3.5, "UNDER"),
    "under45": ("over_under", 4.5, "UNDER"),
    "btts": ("btts", 0.0, "YES"),
    "bttsNo": ("btts", 0.0, "NO"),
    "dc1x": ("double_chance", 0.0, "1X"),
    "dc12": ("double_chance", 0.0, "12"),
    "dcx2": ("double_chance", 0.0, "X2"),
}

RESULT_MAP = {"WIN": "won", "LOSS": "lost", "VOID": "void", "PUSH": "void", "HALF_WIN": "half_won", "HALF_LOSS": "half_lost"}


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def import_selection_journal(conn: sqlite3.Connection, path: Path) -> Dict[str, int]:
    data = _load(path)
    rows = (data or {}).get("results") if isinstance(data, dict) else data
    stats = {"rows": 0, "inserted": 0, "skipped_market": 0, "skipped_invalid": 0, "matches": 0}
    if not isinstance(rows, list):
        return stats
    with conn:
        for r in rows:
            if not isinstance(r, dict):
                continue
            stats["rows"] += 1
            mk = LEGACY_MARKETS.get(str(r.get("market_canonical") or r.get("market") or ""))
            match_id = as_int(r.get("event_id"))
            if not mk:
                stats["skipped_market"] += 1
                continue
            if match_id is None or not r.get("event_date"):
                stats["skipped_invalid"] += 1
                continue
            market, line, selection = mk
            settled = str(r.get("status") or "") == "settled"
            if r.get("league_id") is not None:
                upsert_league(conn, {"id": as_int(r.get("league_id")), "name": r.get("league")})
            upsert_team(conn, as_int(r.get("home_team_id")), r.get("home_team"), as_int(r.get("league_id")))
            upsert_team(conn, as_int(r.get("away_team_id")), r.get("away_team"), as_int(r.get("league_id")))
            existing = conn.execute("SELECT 1 FROM match WHERE id=?", (match_id,)).fetchone()
            if not existing:
                upsert_match(conn, {
                    "id": match_id,
                    "league_id": as_int(r.get("league_id")),
                    "kickoff_utc": canon_utc(r.get("event_date")),
                    "home_id": as_int(r.get("home_team_id")),
                    "away_id": as_int(r.get("away_team_id")),
                    "home_name": r.get("home_team"),
                    "away_name": r.get("away_team"),
                    "status": "finished" if settled and r.get("home_score") is not None else None,
                    "ft_home": as_int(r.get("home_score")),
                    "ft_away": as_int(r.get("away_score")),
                    "updated_at": now_iso(),
                })
                stats["matches"] += 1
            odds = as_float(r.get("odds"))
            p = as_float(r.get("model_probability"))
            result = RESULT_MAP.get(str(r.get("result") or "").upper()) if settled else None
            cur = conn.execute(
                """INSERT OR IGNORE INTO prediction
                   (match_id, market, line, period, selection, p_model, odds_shown, odds_source, ev,
                    confidence, reasons_json, model_version, created_at, shown_on_page, result,
                    settled_at, profit_1u, legacy_key)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    match_id, market, line, "FT", selection, p, odds, "legacy",
                    round(p * odds - 1, 4) if (p is not None and odds) else None,
                    as_float(r.get("score")),
                    json.dumps({"settlement_reason": r.get("settlement_reason"), "strategy_label": r.get("strategy_label"),
                                "source": r.get("source")}, ensure_ascii=False),
                    f"legacy:{r.get('strategy') or 'unknown'}",
                    r.get("first_seen_at") or r.get("event_date"),
                    "legacy",
                    result,
                    r.get("settled_at"),
                    as_float(r.get("profit_units")) if result else None,
                    r.get("key") or f"legacy|{match_id}|{r.get('strategy')}|{r.get('market')}",
                ),
            )
            stats["inserted"] += cur.rowcount
    return stats


def import_performance_summary(conn: sqlite3.Connection, path: Path) -> bool:
    data = _load(path)
    if not isinstance(data, dict):
        return False
    stamp = data.get("updated_at") or now_iso()
    exists = conn.execute(
        "SELECT 1 FROM learning_log WHERE change_type='legacy_performance_snapshot' AND run_at=?", (stamp,)
    ).fetchone()
    if exists:
        return False
    evidence = {k: data.get(k) for k in ("overall", "by_strategy", "by_market", "journal", "notes", "_pipeline_version")}
    with conn:
        conn.execute(
            "INSERT INTO learning_log(run_at, change_type, before, after, evidence_json) VALUES (?,?,?,?,?)",
            (stamp, "legacy_performance_snapshot", None, None, json.dumps(evidence, ensure_ascii=False)),
        )
    return True


def import_legacy(conn: sqlite3.Connection, data_dir: Path) -> Dict[str, Any]:
    journal = import_selection_journal(conn, data_dir / "selection_journal.json")
    summary = import_performance_summary(conn, data_dir / "performance_summary.json")
    return {"selection_journal": journal, "performance_summary_imported": summary}


def legacy_overview(conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """SELECT COUNT(*) n, SUM(result='won') w, SUM(result='lost') l, SUM(profit_1u) profit
           FROM prediction WHERE shown_on_page='legacy' AND result IN ('won','lost')"""
    ).fetchone()
    if not row or not row["n"]:
        return None
    return {"settled": row["n"], "won": row["w"], "lost": row["l"],
            "win_rate": round(row["w"] / row["n"], 4), "profit_units": round(row["profit"] or 0, 2),
            "roi_pct": round(100 * (row["profit"] or 0) / row["n"], 2)}
