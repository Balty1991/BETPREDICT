"""Parametrii învățați ai Robotului (blend, calibrare, piețe excluse, penalizări pe ligă).

Stocați în ``ingest_state['robot.params']`` (JSON); actualizați de ``learn`` săptămânal."""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Any, Dict

from betpredict.store import repo

KEY = "robot.params"

DEFAULT_BLEND = {"model": 0.40, "bsd": 0.20, "market": 0.40}

DEFAULT_PARAMS: Dict[str, Any] = {
    "blend": {},                 # market_key → {model, bsd, market}; lipsă = DEFAULT_BLEND
    "calibration": {},           # market_key → {"a": 1.0, "b": 0.0, "n": 0}
    "excluded_markets": [],      # chei de piață cu calibrare proastă → nu intră în bilete
    "league_penalty": {},        # str(league_id) → multiplicator 0.5–1.0 pe încredere
    "min_edge_value": 0.0,
    "bsd_weight": {},            # market_key → pondere BSD în spațiul logit (învățată din rezultate)
    "thresholds": {},            # market_key → {"min_ev", "blocked_leagues", "n", "roi", "source"}
    "updated_at": None,
}


def load_params(conn: sqlite3.Connection) -> Dict[str, Any]:
    raw = repo.get_state(conn, KEY)
    params = json.loads(json.dumps(DEFAULT_PARAMS))
    if raw:
        try:
            params.update(json.loads(raw))
        except ValueError:
            pass
    return params


def save_params(conn: sqlite3.Connection, params: Dict[str, Any]) -> None:
    params = dict(params)
    params["updated_at"] = repo.now_iso()
    with conn:
        repo.set_state(conn, KEY, json.dumps(params, ensure_ascii=False))


def blend_weights(params: Dict[str, Any], mkey: str) -> Dict[str, float]:
    group = mkey.split("_")[0] if mkey.startswith("over_under") else mkey
    b = params.get("blend", {})
    return dict(b.get(mkey) or b.get(group) or DEFAULT_BLEND)


def logit(p: float) -> float:
    p = min(1 - 1e-6, max(1e-6, p))
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def calibrate(params: Dict[str, Any], mkey: str, p: float) -> float:
    c = params.get("calibration", {}).get(mkey)
    if not c:
        return p
    return sigmoid(c.get("a", 1.0) * logit(p) + c.get("b", 0.0))


DEFAULT_BSD_WEIGHT = 0.10

# Praguri inițiale (din backtest-ul walk-forward pe cote pre-meci curate, vezi docs/robot-v2-backtest.md);
# înlocuite săptămânal de pragurile învățate din rezultatele reale (learn.adaptive_thresholds).
# Backtest (iun.–aug. 2026, 1.501 meciuri cu cote pre-meci curate): nicio piață nu are ROI pozitiv
# semnificativ; 1X2 e cea mai slabă (EV>0 → ROI −11%), GG / Peste 1.5 ≈ 0. Pragurile cer deci o
# valoare minimă mai mare acolo unde dovezile sunt negative.
DEFAULT_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "1x2": {"min_ev": 0.05, "source": "backtest"},
    "double_chance": {"min_ev": 0.02, "source": "backtest"},
    "draw_no_bet": {"min_ev": 0.03, "source": "backtest"},
    "over_under_1.5": {"min_ev": 0.01, "source": "backtest"},
    "over_under_2.5": {"min_ev": 0.03, "source": "backtest"},
    "over_under_3.5": {"min_ev": 0.03, "source": "backtest"},
    "btts": {"min_ev": 0.01, "source": "backtest"},
}


def bsd_weight(params: Dict[str, Any], mkey: str) -> float:
    group = "over_under" if mkey.startswith("over_under") else mkey
    w = params.get("bsd_weight", {})
    return float(w.get(mkey, w.get(group, DEFAULT_BSD_WEIGHT)))


def threshold_ok(params: Dict[str, Any], mkey: str, league_id, ev) -> bool:
    from betpredict.segments import BOOST_EV, segment_action

    seg = segment_action(params, league_id, mkey)
    if seg == "off":  # segment ligă × piață oprit de învățarea săptămânală (CLV/ROI negativ)
        return False
    th = params.get("thresholds", {}).get(mkey) or DEFAULT_THRESHOLDS.get(mkey)
    if not th:
        return True
    if league_id is not None and int(league_id) in set(th.get("blocked_leagues", [])):
        return False
    if ev is None:
        return True
    return ev >= float(th.get("min_ev", 0.0)) - (BOOST_EV if seg == "boost" else 0.0)
