"""v4: Shin, calibrare pe grup + ECE debiased, blend pe ligă, bilete (valoare/dublu/loterie/sistem), piramidă."""
import math
from datetime import date

import numpy as np

from betpredict.builder.pool import Cand
from betpredict.builder.system import system_variant, system_variants
from betpredict.builder import v4tickets as V
from betpredict.model.calib import (blend, ece, ece_debiased, fit_group_calibration, fit_league_weights, league_group,
                                    league_w, proportional, shin)


def test_shin_vs_proportional():
    o = [1.5, 4.2, 7.0]
    s, p = shin(o), proportional(o)
    assert abs(sum(s) - 1) < 1e-9 and abs(sum(p) - 1) < 1e-9
    assert s[0] > p[0] and s[2] < p[2]  # Shin scade outsiderul (bias favorit–outsider)
    assert shin([1.0, 2.0]) is None


def test_ece_debiased_zero_for_perfect():
    rng = np.random.default_rng(1)
    p = rng.uniform(0.2, 0.8, 2000)
    y = (rng.random(2000) < p).astype(float)
    assert ece_debiased(p, y) < 0.01
    assert ece_debiased(np.clip(p + 0.1, 0, 1), y) > 0.05


def test_group_calibration_keeps_only_if_better_and_blocks():
    rng = np.random.default_rng(2)
    n = 6000
    t = np.sort(rng.uniform(0, 200, n))
    league = rng.choice([1, 12, 999], n)
    true = rng.uniform(0.2, 0.8, n)
    y = (rng.random(n) < true).astype(float)
    P = {"O25": np.clip(true + 0.12, 0.01, 0.99)}  # model prost calibrat (+12 pp)
    r = fit_group_calibration(P, {"O25": y}, t, league, np.ones(n, bool), 200.0, ["O25"])
    assert any(x["kept"] for x in r["report"])
    assert all(x["ll_cal"] <= x["ll_raw"] for x in r["report"] if x["kept"])
    assert league_group(1) == "top" and league_group(12) == "second" and league_group(None) == "other"


def test_league_weights_shrink():
    rng = np.random.default_rng(3)
    n = 3000
    league = rng.choice([1, 2, 3], n)
    true = rng.uniform(0.2, 0.8, n)
    y = (rng.random(n) < true).astype(float)
    mk = np.clip(true + rng.normal(0, 0.03, n), 0.02, 0.98)
    mod = np.clip(true + rng.normal(0, 0.15, n), 0.02, 0.98)
    W = fit_league_weights({"BY": mod}, {"BY": mk}, {"BY": y}, league, np.ones(n, bool), ["BY"])
    assert W["BY"]["global"] > 0.6  # piața e mai bună → w mare
    assert 0 <= league_w(W, "BY", 1) <= 1
    assert blend(np.array([0.5]), np.array([0.5]), np.array([0.7]))[0] == 0.5


def test_system_variant_math():
    v = system_variant([2.0, 2.0, 2.0], [0.5, 0.5, 0.5], 2, 3.0)
    assert v["combos"] == 3 and abs(v["stake_per_combo"] - 1.0) < 1e-9
    assert abs(v["ev"]) < 1e-9  # p·c = 1 pe fiecare selecție → EV 0
    assert v["table"][0]["payout_avg"] == 12.0 and v["table"][1]["payout_avg"] == 4.0
    assert abs(v["table"][0]["prob"] - 0.125) < 1e-6
    assert [s["system"] for s in system_variants([1.2] * 10, [0.85] * 10, 1)] == ["9/10", "8/10", "7/10"]


def _c(i, odds, p, pm=None, src="superbet", league=None):
    return Cand(i, 1000 + i, league if league is not None else i, "L", "2026-10-10T18:00:00Z", "A", "B", "1x2", 0.0, "HOME",
                odds, p, p * odds - 1, "A", 80, True, p_market=pm, odds_source=src)


def test_value_tickets_rules():
    pool = [_c(i, 1.9, 0.6, 0.5) for i in range(1, 8)] + [_c(20, 3.0, 0.5, 0.3)]  # cota 3.0 e în afara 1.5–2.5
    t = V.build_value_tickets(pool, {})
    assert t and all(2 <= len(x) <= 4 for x in t)
    assert all(1.5 <= c.odds <= 2.5 and V.edge(c) >= 0.04 for x in t for c in x)
    total, p, ev = V.ticket_stats(t[0])
    assert V.kelly_units(p, total, V.KELLY_TICKET, V.TICKET_CAP_U) <= 1.0


def test_value_double_and_lottery():
    pool = [_c(i, 1.3, 0.85, 0.75) for i in range(1, 6)] + [_c(10 + i, 2.6, 0.5, 0.36) for i in range(12)]
    d = V.build_value_double(pool, {})
    assert d and 1.6 <= d[0].odds * d[1].odds <= 1.8
    lot = V.build_lottery(pool, 100, {})
    assert lot and 80 <= math.prod(c.odds for c in lot) <= 135
    assert sum(1 for c in lot if c.odds < V.LOW_ODDS) <= V.MAX_LOW_LEGS
    assert V.build_lottery([_c(i, 2.6, 0.5, 0.36, src="bsd_consensus") for i in range(12)], 100, {}) is None


def test_pyramid_prefers_single_and_edge():
    from betpredict.builder.pyramid import pick_pyramid

    pool = [_c(1, 2.0, 0.62, 0.56), _c(2, 1.4, 0.745, 0.7), _c(3, 1.45, 0.745, 0.68)]
    for c in pool:
        c.grade = "A"
    r = pick_pyramid(pool)
    assert r["status"] == "pick" and len(r["main"][0]) == 1
    weak = [_c(1, 2.0, 0.505, 0.5)]
    weak[0].grade = "A"
    assert pick_pyramid(weak)["status"] == "no_bet"
