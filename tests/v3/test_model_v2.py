"""Robot v2: feature-uri fără scurgeri, stacking/calibrare, artefact + predicție live, praguri adaptive."""

import json
import math
import random
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from pathlib import Path

from betpredict.model import gbm as G
from betpredict.model.data import History, load_history, novig_market
from betpredict.model.features import FEATURE_NAMES, build_features
from betpredict.model.metrics import ece, roi
from betpredict.model.stack import apply_binary, apply_multi, fit_binary, fit_multi
from betpredict.store import connect, init_db
from betpredict.timeutil import canon_utc

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
SMALL = {"elo": {"k": 20.0, "home_adv": 60.0, "margin": 0.6, "new_team_offset": -40.0, "regress": 0.2},
         "half_life": 180.0, "dc_years": 2.0, "train_years": 2.0, "oos_months": 4,
         "gbm": {"num_rounds": 25, "num_leaves": 8, "min_data_in_leaf": 50}}


def _poisson(rng, lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p < L:
            return k
        k += 1


def synth_db(n_days=900):
    conn = connect(":memory:")
    init_db(conn)
    rng = random.Random(3)
    teams = {lg: list(range(lg, lg + 20)) for lg in (100, 200)}
    strength = {t: rng.uniform(-0.45, 0.45) for lg in teams for t in teams[lg]}
    rows, mid = [], 1
    for d in range(n_days, 0, -2):
        day = NOW - timedelta(days=d)
        for lg, ts in teams.items():
            o = ts[:]
            rng.shuffle(o)
            for i in range(0, 20, 2):
                h, a = o[i], o[i + 1]
                lh = math.exp(0.15 + 0.25 + strength[h] - strength[a])
                la = math.exp(0.15 + strength[a] - strength[h])
                rows.append((mid, lg, 1 + (n_days - d) // 300, canon_utc(day.isoformat()), h, a, "finished",
                             _poisson(rng, lh), _poisson(rng, la)))
                mid += 1
    conn.executemany("INSERT INTO match (id, league_id, season_id, kickoff_utc, home_id, away_id, status, ft_home, ft_away) "
                     "VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn, strength


def test_features_have_no_leakage():
    conn, _ = synth_db(200)
    h = load_history(conn)
    X, _, _ = build_features(h)
    assert X.shape == (len(h), len(FEATURE_NAMES))
    i = len(h) // 2
    h.gh[i] += 5  # rezultatul meciului i nu are voie să-i schimbe propriile feature-uri
    X2, _, _ = build_features(h)
    assert np.allclose(np.nan_to_num(X[: i + 1]), np.nan_to_num(X2[: i + 1]))
    assert not np.allclose(np.nan_to_num(X[i + 1:]), np.nan_to_num(X2[i + 1:]))


def test_beta_stacking_recovers_calibration():
    rng = np.random.default_rng(0)
    p_true = rng.uniform(0.2, 0.8, 20000)
    y = (rng.uniform(size=p_true.size) < p_true).astype(float)
    over = 1 / (1 + np.exp(-2.0 * np.log(p_true / (1 - p_true))))  # prea încrezător
    c = fit_binary([over], y)
    cal = apply_binary(c, [over])
    assert ece(cal, y) < ece(over, y) / 3
    P = np.stack([p_true * 0.5, p_true * 0.3, 1 - p_true * 0.8], 1)
    yy = np.array([rng.choice(3, p=row) for row in P[:3000]])
    B = fit_multi([P[:3000]], yy)
    Q = apply_multi(B, [P[:3000]])
    assert np.allclose(Q.sum(1), 1)


def test_novig_and_roi():
    nv = novig_market({"H": 2.0, "D": 3.4, "A": 4.0, "O25": 1.9, "U25": 1.9})
    assert abs(nv["H"] + nv["D"] + nv["A"] - 1) < 1e-9 and abs(nv["O25"] - 0.5) < 1e-9
    assert abs(nv["1X"] - (nv["H"] + nv["D"])) < 1e-9
    r = roi(np.array([0.6, 0.4]), np.array([2.0, 2.0]), np.array([1, 0]), ev_min=0.0)
    assert r["n"] == 1 and r["roi"] == 1.0


@pytest.mark.skipif(not G.available(), reason="lightgbm lipsește")
def test_artifact_live_prediction_and_storage():
    from betpredict.model.v2 import LivePredictor, fit_artifact, load_champion, save_artifact

    conn, strength = synth_db()
    art = fit_artifact(conn, SMALL, log=lambda *a: None, warehouse_dir=Path("/nonexistent"))
    assert art["gbm"] and set(art["stack"]) >= {"1x2", "O15", "O25", "O35", "BY"}
    oos = art["metrics"]["oos"]["model"]
    assert oos["n"] > 500 and oos["1x2"] < 1.10
    save_artifact(conn, art)
    art2 = load_champion(conn)
    assert art2["train_to"] == art["train_to"]
    conn.executemany("INSERT INTO match (id, league_id, season_id, kickoff_utc, home_id, away_id, status) VALUES (?,?,?,?,?,?,?)",
                     [(999001, 100, 9, canon_utc((NOW + timedelta(days=1)).isoformat()), 100, 101, "notstarted"),
                      (999002, 200, 9, canon_utc((NOW + timedelta(days=1)).isoformat()), 205, 206, "notstarted")])
    ups = conn.execute("SELECT * FROM match WHERE id >= 999001").fetchall()
    lp = LivePredictor(conn, art2, ups, now_t=NOW.timestamp() / 86400)
    for mid in (999001, 999002):
        o = lp.get(mid)
        assert abs(o["p"]["H"] + o["p"]["D"] + o["p"]["A"] - 1) < 1e-6
        assert o["p"]["O15"] >= o["p"]["O25"] >= o["p"]["O35"]
        mk = lp.with_market(mid, {"H": 0.5, "D": 0.27, "A": 0.23, "O25": 0.55, "O15": 0.78, "O35": 0.3, "BY": 0.52})
        assert abs(mk["H"] + mk["D"] + mk["A"] - 1) < 1e-6 and 0 < mk["O25"] < 1
    # cea mai puternică vs cea mai slabă echipă: favorită clară
    best = max(range(100, 120), key=lambda t: strength[t])
    worst = min(range(100, 120), key=lambda t: strength[t])
    conn.execute("INSERT INTO match (id, league_id, season_id, kickoff_utc, home_id, away_id, status) VALUES (?,?,?,?,?,?,?)",
                 (999003, 100, 9, canon_utc((NOW + timedelta(days=1)).isoformat()), best, worst, "notstarted"))
    lp2 = LivePredictor(conn, art2, conn.execute("SELECT * FROM match WHERE id=999003").fetchall(), now_t=NOW.timestamp() / 86400)
    assert lp2.get(999003)["p"]["H"] > 0.6


def test_adaptive_thresholds_block_losing_markets():
    from betpredict.learn import adaptive_thresholds

    rows = []
    for i in range(300):
        rows.append({"market": "over_under", "line": 2.5, "odds_shown": 1.9, "ev": 0.03, "profit_1u": -1.0 if i % 2 else 0.9,
                     "league_id": 1})
        rows.append({"market": "btts", "line": 0.0, "odds_shown": 1.9, "ev": 0.05, "profit_1u": 0.9 if i % 3 else -1.0,
                     "league_id": 2 if i % 5 else 3})
    th = adaptive_thresholds(rows)
    assert th["over_under_2.5"]["min_ev"] == 0.15          # ROI negativ → doar valori foarte mari
    assert th["btts"]["min_ev"] <= 0.04 and th["btts"]["roi_shrunk"] > 0


def test_threshold_ok():
    from betpredict.robot.params import threshold_ok

    p = {"thresholds": {"btts": {"min_ev": 0.04, "blocked_leagues": [7]}}}
    assert threshold_ok(p, "btts", 1, 0.05) and not threshold_ok(p, "btts", 1, 0.01)
    assert not threshold_ok(p, "btts", 7, 0.5) and threshold_ok(p, "unknown_market", 7, -0.2)
    assert not threshold_ok({}, "1x2", 1, 0.01) and threshold_ok({}, "1x2", 1, 0.06)  # prag implicit din backtest
