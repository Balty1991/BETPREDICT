"""``api/days/<YYYY-MM-DD>.json`` — un fișier mic pe zi (ziua din România)."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from betpredict import __version__
from betpredict.config import MIN_ODDS, img_url
from betpredict.store.repo import latest_odds, market_key
from betpredict.timeutil import ro_day_bounds_utc

DAY_SCHEMA = "betpredict.day.v1"


def _provider_probs(conn: sqlite3.Connection, match_ids: List[int]) -> Dict[int, Dict[str, Dict[str, float]]]:
    out: Dict[int, Dict[str, Dict[str, float]]] = {}
    if not match_ids:
        return out
    q = ",".join("?" for _ in match_ids)
    for r in conn.execute(
        f"SELECT match_id, market, line, selection, probability FROM provider_prediction "
        f"WHERE source='bsd' AND match_id IN ({q})",
        match_ids,
    ):
        out.setdefault(r["match_id"], {}).setdefault(market_key(r["market"], r["line"]), {})[r["selection"]] = r["probability"]
    return out


def build_day(conn: sqlite3.Connection, day: date) -> Dict[str, Any]:
    start, end = ro_day_bounds_utc(day)
    rows = conn.execute(
        """SELECT m.*, l.name AS league_name, l.country AS league_country
           FROM match m LEFT JOIN league l ON l.id = m.league_id
           WHERE m.kickoff_utc >= ? AND m.kickoff_utc < ?
           ORDER BY m.kickoff_utc, m.id""",
        (start, end),
    ).fetchall()
    ids = [r["id"] for r in rows]
    odds = latest_odds(conn, ids)
    probs = _provider_probs(conn, ids)
    matches = []
    for r in rows:
        score = None
        if r["ft_home"] is not None and r["ft_away"] is not None:
            score = {"ft": [r["ft_home"], r["ft_away"]],
                     "ht": [r["ht_home"], r["ht_away"]] if r["ht_home"] is not None else None}
        matches.append({
            "id": r["id"],
            "kickoff_utc": r["kickoff_utc"],
            "status": r["status"],
            "league": {"id": r["league_id"], "name": r["league_name"], "country": r["league_country"],
                       "logo": img_url("league", r["league_id"])},
            "home": {"id": r["home_id"], "name": r["home_name"], "logo": img_url("team", r["home_id"])},
            "away": {"id": r["away_id"], "name": r["away_name"], "logo": img_url("team", r["away_id"])},
            "score": score,
            "odds": odds.get(r["id"], {}),
            "bsd_probabilities": probs.get(r["id"], {}),
        })
    return {
        "schema": DAY_SCHEMA,
        "date": day.isoformat(),
        "timezone": "Europe/Bucharest",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app_version": __version__,
        "min_odds": MIN_ODDS,
        "odds_source": "bsd_consensus",
        "count": len(matches),
        "matches": matches,
    }


def write_day(conn: sqlite3.Connection, day: date, out_root: Path) -> Path:
    payload = build_day(conn, day)
    days_dir = Path(out_root) / "api" / "days"
    days_dir.mkdir(parents=True, exist_ok=True)
    path = days_dir / f"{day.isoformat()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    _update_index(days_dir)
    return path


def _update_index(days_dir: Path) -> None:
    days = sorted(p.stem for p in days_dir.glob("????-??-??.json"))
    (days_dir / "index.json").write_text(json.dumps({"days": days}, separators=(",", ":")), encoding="utf-8")
