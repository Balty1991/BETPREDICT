"""``api/stats/robot.json``: tot ce afișează secțiunea „Robotul” din Statistici.

Combină (doar citire, fără a atinge modelul): informațiile modelului activ (``learn.learning_doc``),
backtestul walk-forward v2 (``docs/backtest/robot-v2-backtest.json``), pragurile pe piață,
jurnalul de învățare și programul de reantrenare (luni 03:45 UTC, vezi workflow-ul v3).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from betpredict.publish.day import MODEL_LABEL, write_json
from betpredict.robot import MODEL_VERSION, ROBOT_VERSION, STATS_SINCE

ROBOT_SCHEMA = "betpredict.robot.v1"
# Eticheta afișată a modelului. Cheia din DB (``MODEL_VERSION`` = robot-v1) rămâne neschimbată:
# filtrează jurnalul și statisticile Robotului 3.0; motorul de calcul este însă v2 (LightGBM + Dixon-Coles).
MODEL_ENGINE = "LightGBM + Dixon-Coles (stacking), calibrat, tras spre piață"
BACKTEST_PATH = Path(__file__).resolve().parents[2] / "docs" / "backtest" / "robot-v2-backtest.json"
RETRAIN_WEEKDAY = 0  # luni
RETRAIN_UTC = time(3, 45)

# cheile backtestului → cheile pieței din aplicație
BT_MARKETS = [("1x2", "1x2", "Rezultat final (1X2)"), ("double_chance", "double_chance", "Șansă dublă"),
              ("dnb", "draw_no_bet", "Egal = pariu returnat"), ("ou_1.5", "over_under_1.5", "Peste/Sub 1.5"),
              ("ou_2.5", "over_under_2.5", "Peste/Sub 2.5"), ("ou_3.5", "over_under_3.5", "Peste/Sub 3.5"),
              ("btts", "btts", "Ambele marchează")]


def model_label(version: Optional[str] = None) -> str:
    """Eticheta afișată: versiunea campionului v2 (din registru) dacă există, altfel ``MODEL_LABEL``."""
    if isinstance(version, str) and version.startswith("robot-v") and version != MODEL_VERSION:
        return version
    return MODEL_LABEL


def next_retrain(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    d = now.date()
    for i in range(8):
        cand = datetime.combine(d + timedelta(days=i), RETRAIN_UTC, tzinfo=timezone.utc)
        if cand.weekday() == RETRAIN_WEEKDAY and cand > now:
            return cand
    return datetime.combine(d + timedelta(days=7), RETRAIN_UTC, tzinfo=timezone.utc)


def _metrics(block: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not block or not block.get("n"):
        return None
    return {k: block.get(k) for k in ("n", "logloss", "brier", "ece")}


def _roi(block: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not block or not block.get("n"):
        return None
    return {k: block.get(k) for k in ("n", "roi", "hit", "avg_odds", "se")}


def backtest_summary(path: Path = BACKTEST_PATH) -> Optional[Dict[str, Any]]:
    try:
        bt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    mo, wm, roi = bt.get("model_only", {}), bt.get("with_market", {}), bt.get("roi", {})
    rows: List[Dict[str, Any]] = []
    for bkey, mkey, title in BT_MARKETS:
        rows.append({
            "key": mkey, "title": title,
            "v1": _metrics(mo.get("v1", {}).get(bkey)),
            "v2": _metrics(mo.get("v2", {}).get(bkey)),
            "market": _metrics(wm.get("market", {}).get(bkey)),
            "v2_market": _metrics(wm.get("v2_market", {}).get(bkey)),
            "roi_rec": _roi(roi.get("v2_market", {}).get(bkey, {}).get("rec")),
            "roi_ev3": _roi(roi.get("v2_market", {}).get(bkey, {}).get("ev>3%")),
        })
    return {"generated_at": bt.get("generated_at"), "history_matches": bt.get("history_matches"),
            "eval_from": bt.get("eval_from"), "odds_matches": bt.get("odds_matches"),
            "odds_from": (bt.get("odds_from") or "")[:10] or None, "markets": rows}


def thresholds(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    from betpredict.robot.params import DEFAULT_THRESHOLDS  # noqa: PLC0415 — doar citire

    learned = params.get("thresholds") or {}
    out = []
    for key in list(DEFAULT_THRESHOLDS) + [k for k in learned if k not in DEFAULT_THRESHOLDS]:
        cur = dict(DEFAULT_THRESHOLDS.get(key, {}))
        if key in learned and isinstance(learned[key], dict):
            cur.update(learned[key])
        out.append({"key": key, "min_ev": cur.get("min_ev"), "source": cur.get("source", "backtest"),
                    "n": cur.get("n"), "roi": cur.get("roi"),
                    "blocked_leagues": len(cur.get("blocked_leagues") or [])})
    return out


def build_robot_doc(conn: sqlite3.Connection, now: Optional[datetime] = None, days_ahead: Optional[int] = None) -> Dict[str, Any]:
    from betpredict.learn import learning_doc  # noqa: PLC0415

    now = now or datetime.now(timezone.utc)
    learn = learning_doc(conn)
    model = dict(learn.get("model") or {})
    label = model_label(model.get("version"))
    model["version"] = label
    bt = backtest_summary()
    log = list(learn.get("log") or [])
    if bt and bt.get("generated_at"):
        log.append({"run_at": bt["generated_at"], "change_type": "backtest_v2", "market": None, "league_id": None,
                    "before": "robot-v1", "after": label,
                    "evidence": {"matches": bt.get("history_matches"), "eval_from": bt.get("eval_from"),
                                 "odds_matches": bt.get("odds_matches")}})
    nr = next_retrain(now)
    return {
        "schema": ROBOT_SCHEMA, "model_label": label, "db_key": MODEL_VERSION, "robot_version": ROBOT_VERSION,
        "engine": MODEL_ENGINE, "stats_since": STATS_SINCE, "days_ahead": days_ahead,
        "model": model, "backtest": bt, "thresholds": thresholds(learn.get("params") or {}),
        "params_updated_at": (learn.get("params") or {}).get("updated_at"),
        "excluded_markets": (learn.get("params") or {}).get("excluded_markets") or [],
        "walk_forward": learn.get("walk_forward") or [], "log": log[:100],
        "schedule": {"retrain": "luni, 03:45 UTC", "next_retrain_utc": nr.isoformat(),
                     "daily": "00:15 UTC", "refresh": "în fiecare oră la :20"},
    }


def publish_robot(conn: sqlite3.Connection, out_root: Path, now: Optional[datetime] = None,
                  days_ahead: Optional[int] = None) -> Dict[str, Any]:
    doc = build_robot_doc(conn, now, days_ahead)
    write_json(out_root / "api" / "stats" / "robot.json", doc)
    return doc
