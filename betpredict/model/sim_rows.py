"""Date pentru simularea biletelor pe zile trecute: probabilități Robot v2 STRICT out-of-sample
(model antrenat doar înainte de perioada cu cote curate) + cotele reale pre-meci + rezultatul.

Perioada: de la ``ODDS_CLEAN_FROM`` (iunie 2026) încolo — cotele din depozit dinainte sunt live/contaminate."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from betpredict.model.backtest import ODDS_CLEAN_FROM, day_of, plausible_prematch
from betpredict.model.data import SNAP_MAP, load_snapshot_odds, load_warehouse_odds, novig_market

STATE_KEY = "tickets.sim_rows"
CORE = ("H", "D", "A", "O15", "O25", "O35", "BY")


def build_sim_rows(conn: sqlite3.Connection, config: Optional[Dict[str, Any]] = None, log=print,
                   warehouse_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    from betpredict.model.v2 import DEFAULT_CONFIG, WAREHOUSE, fit_artifact, load_champion, market_combine

    warehouse_dir = warehouse_dir or WAREHOUSE
    champ = load_champion(conn)
    cfg = (champ or {}).get("config") or DEFAULT_CONFIG
    t0 = time.time()
    art = fit_artifact(conn, cfg, cutoff=ODDS_CLEAN_FROM, holdout_days=400, keep_holdout=True, log=log,
                       warehouse_dir=warehouse_dir)
    ho = art.get("_holdout")
    if not ho:
        return []
    hist, idx, S = ho["hist"], ho["idx"], ho["S"]
    pos = {int(hist.ids[j]): k for k, j in enumerate(idx)}
    odds: Dict[int, Dict[str, float]] = {}
    if Path(warehouse_dir).is_dir():
        for mid, o in load_warehouse_odds(warehouse_dir).items():
            if mid in pos and plausible_prematch(o):
                odds[mid] = o
    for mid, d in load_snapshot_odds(conn).items():
        if mid in pos and d["close"]:
            odds[mid] = d["close"]
    pm = np.zeros((7, 3))
    for j in range(3):
        pm[j, j], pm[3 + j, j] = 0.35, 0.65
    prior_market = {"1x2": pm.tolist(), **{k: [0.35, 0.35, 0.65, 0.65, 0.0] for k in ("O15", "O25", "O35", "BY")}}
    rows: List[Dict[str, Any]] = []
    t_clean = day_of(ODDS_CLEAN_FROM)
    for mid, o in odds.items():
        k = pos[mid]
        j = int(idx[k])
        if hist.t[j] < t_clean:
            continue
        nv = novig_market(o)
        s_model = {c: float(S[c][k]) for c in CORE}
        if all(c in nv for c in CORE):
            comb = market_combine({c: np.array([s_model[c]]) for c in CORE}, {c: np.array([nv[c]]) for c in CORE},
                                  prior_market)  # coeficienți prior → fără scurgeri
            p = {c: float(comb[c][0]) for c in CORE}
        else:
            p = s_model
        rows.append({"id": mid, "ko": str(hist.ko[j]), "league": int(hist.league[j]), "gh": int(hist.gh[j]), "ga": int(hist.ga[j]),
                     "p": {c: round(v, 5) for c, v in p.items()}, "p_model": {c: round(v, 5) for c, v in s_model.items()},
                     "mk": {c: round(v, 5) for c, v in nv.items()}, "odds": o})
    log(f"  sim_rows: {len(rows)} meciuri cu cote curate ({time.time() - t0:.0f}s)")
    return rows


def save_sim_rows(conn: sqlite3.Connection, rows: List[Dict[str, Any]]) -> None:
    from betpredict.store import repo

    with conn:
        repo.set_state(conn, STATE_KEY, json.dumps(rows))


def load_sim_rows(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    r = conn.execute("SELECT value FROM ingest_state WHERE key=?", (STATE_KEY,)).fetchone()
    return json.loads(r[0]) if r else []
