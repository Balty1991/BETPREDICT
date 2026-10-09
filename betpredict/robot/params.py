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
