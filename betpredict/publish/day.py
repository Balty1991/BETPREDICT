"""``api/days/<YYYY-MM-DD>.json`` — meciurile zilei (ziua din România) + predicțiile Robotului."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from betpredict import __version__
from betpredict.config import MIN_ODDS, img_url
from betpredict.robot import MODEL_VERSION, ROBOT_VERSION, is_recommended

MODEL_LABEL = "robot-v2"  # eticheta afișată (sincron cu publish.robot.MODEL_LABEL); cheia DB rămâne MODEL_VERSION
from betpredict.robot.markets import label_ro, market_key
from betpredict.store.repo import latest_odds
from betpredict.store.repo import market_key as store_market_key
from betpredict.timeutil import ro_day_bounds_utc

DAY_SCHEMA = "betpredict.day.v1"
GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


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
        out.setdefault(r["match_id"], {}).setdefault(store_market_key(r["market"], r["line"]), {})[r["selection"]] = r["probability"]
    return out


def prediction_json(r: sqlite3.Row) -> Dict[str, Any]:
    try:
        extra = json.loads(r["reasons_json"] or "{}")
    except ValueError:
        extra = {}
    line = r["line"] or 0.0
    p = r["p_calibrated"]
    return {
        "id": r["id"], "match_id": r["match_id"], "market": r["market"], "line": line or None,
        "selection": r["selection"], "label": label_ro(r["market"], line, r["selection"]),
        "p": p, "p_model": r["p_model"], "p_bsd": r["p_bsd"], "p_market": r["p_market_novig"],
        "odds": r["odds_shown"], "odds_source": r["odds_source"],
        "fair_odds": round(1 / p, 2) if p else None, "edge": r["edge"], "ev": r["ev"],
        "value": bool(r["ev"] is not None and r["ev"] > 0), "grade": r["grade"], "confidence": int(r["confidence"]) if r["confidence"] is not None else None,
        "is_pick": bool(r["is_pick"]), "market_healthy": bool(extra.get("healthy", True)),
        "recommended": is_recommended(p, r["odds_shown"], r["ev"], r["grade"], bool(extra.get("healthy", True))),
        "robot_version": ROBOT_VERSION,
        "reasons": extra.get("reasons", []), "result": r["result"], "profit": r["profit_1u"],
        "model_version": r["model_version"], "created_at": r["created_at"],
    }


def build_day(conn: sqlite3.Connection, day: date) -> Dict[str, Any]:
    from betpredict.robot.engine import odds_movement

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
    moves = odds_movement(conn, ids)
    q = ",".join("?" for _ in ids) or "NULL"
    ctx = {r["match_id"]: json.loads(r["context_json"]) for r in conn.execute(
        f"SELECT match_id, context_json FROM match_context WHERE match_id IN ({q})", ids)}
    models = {r["match_id"]: r for r in conn.execute(f"SELECT * FROM match_model WHERE match_id IN ({q})", ids)}
    preds: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for r in conn.execute(
        f"SELECT * FROM prediction WHERE match_id IN ({q}) AND model_version=? AND shown_on_page='predictii'",
        ids + [MODEL_VERSION],
    ):
        preds[r["match_id"]].append(prediction_json(r))
    matches = []
    for r in rows:
        score = None
        if r["ft_home"] is not None and r["ft_away"] is not None:
            score = {"ft": [r["ft_home"], r["ft_away"]],
                     "ht": [r["ht_home"], r["ht_away"]] if r["ht_home"] is not None else None}
        raw = {}
        try:
            raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
        except ValueError:
            pass
        mm = models.get(r["id"])
        model = None
        if mm:
            extra = json.loads(mm["extra_json"] or "{}")
            model = {"lambda_home": mm["lambda_home"], "lambda_away": mm["lambda_away"], "elo_home": mm["elo_home"],
                     "elo_away": mm["elo_away"], **extra}
        plist = sorted(preds.get(r["id"], []), key=lambda p: (not p["is_pick"], GRADE_ORDER.get(p["grade"] or "D", 4), -(p["p"] or 0)))
        pick = next((p["id"] for p in plist if p["is_pick"]), None)
        matches.append({
            "id": r["id"],
            "kickoff_utc": r["kickoff_utc"],
            "status": r["status"],
            "league": {"id": r["league_id"], "name": r["league_name"] or f"Liga #{r['league_id']}", "country": r["league_country"],
                       "logo": img_url("league", r["league_id"])},
            "home": {"id": r["home_id"], "name": r["home_name"], "logo": img_url("team", r["home_id"])},
            "away": {"id": r["away_id"], "name": r["away_name"], "logo": img_url("team", r["away_id"])},
            "round": r["round"] or raw.get("round_label"),
            "score": score,
            "odds": odds.get(r["id"], {}),
            "odds_movement": moves.get(r["id"]) or None,
            "bsd_probabilities": probs.get(r["id"], {}),
            "model": model,
            "context": ctx.get(r["id"]),
            "predictions": plist,
            "pick_id": pick,
        })
    return {
        "schema": DAY_SCHEMA,
        "date": day.isoformat(),
        "timezone": "Europe/Bucharest",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app_version": __version__,
        "model_version": MODEL_LABEL,
        "model_key": MODEL_VERSION,
        "min_odds": MIN_ODDS,
        "odds_source": "bsd_consensus",
        "count": len(matches),
        "markets": ["1x2", "double_chance", "draw_no_bet", "over_under_0.5", "over_under_1.5", "over_under_2.5",
                    "over_under_3.5", "over_under_4.5", "btts"],
        "matches": matches,
    }


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, dict) and "generated_at" not in payload:
        payload = {**payload, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
    return path


def write_day(conn: sqlite3.Connection, day: date, out_root: Path) -> Path:
    payload = build_day(conn, day)
    days_dir = Path(out_root) / "api" / "days"
    path = write_json(days_dir / f"{day.isoformat()}.json", payload)
    _update_index(days_dir)
    return path


def _update_index(days_dir: Path) -> None:
    days = sorted(p.stem for p in days_dir.glob("????-??-??.json"))
    (days_dir / "index.json").write_text(json.dumps({"schema": "betpredict.days_index.v1", "days": days}, separators=(",", ":")), encoding="utf-8")
