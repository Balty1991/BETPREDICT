"""Optimizatorul de acumulatoare + auto-învățarea biletelor."""
import copy

from betpredict.builder import optimizer as opt
from betpredict.builder.pool import Cand
from betpredict import learn_tickets as lt


def _c(pid, mid, league, p, odds, market="1x2", line=0.0, sel="HOME", ko="2026-10-09T18:00:00Z", src="bsd_consensus"):
    return Cand(pid, mid, league, None, ko, None, None, market, line, sel, odds, p, p * odds - 1, "A", 75, True,
                p_market=None, odds_source=src)


def setup_function(_):
    opt.use_strategy(copy.deepcopy(opt.DEFAULT_STRATEGY))


def test_mc_probability_below_naive_and_correlation_hurts():
    s = copy.deepcopy(opt.DEFAULT_STRATEGY)
    legs = [_c(i, i, 100 + i, 0.8, 1.3, ko=f"2026-10-09T{10 + i}:00:00Z") for i in range(5)]
    e = opt.ticket_eval(legs, s=s)
    assert e["p"] < e["p_naive"] and e["p_lo"] <= e["p"] <= e["p_hi"]
    same = [_c(i, i, 7, 0.8, 1.3) for i in range(5)]  # aceeași ligă + aceeași oră
    e2 = opt.ticket_eval(same, s=s)
    assert e2["p"] < e["p"] + 0.01  # penalizare de corelație (aceeași ligă/oră)
    assert e2["sd"] > 0 and abs(e["odds"] - 1.3 ** 5) < 1e-6


def test_safety_levels_need_both_high():
    assert opt.safety(0.75, 80)["level"] == "ridicată"
    assert opt.safety(0.75, 40)["level"] != "ridicată"
    assert opt.safety(0.45, 90)["level"] == "scăzută"
    assert opt.safety(None, 90)["level"] is None


def test_leg_filters_block_and_min_p():
    s = copy.deepcopy(opt.DEFAULT_STRATEGY)
    c = _c(1, 1, 1, 0.6, 1.7)
    assert opt.leg_ok(c, 50, s)
    s["blocked_leg_types"] = [opt.leg_type("1x2", 0.0, 1.7)]
    assert not opt.leg_ok(c, 50, s)
    s["blocked_leg_types"] = []
    s["min_leg_p"]["50"] = 0.9
    assert not opt.leg_ok(c, 50, s)


def test_real_odds_bonus_and_reuse_cap():
    s = copy.deepcopy(opt.DEFAULT_STRATEGY)
    assert opt.leg_bonus(_c(1, 1, 1, 0.6, 1.7), s) > 0
    assert opt.leg_bonus(_c(1, 1, 1, 0.6, 1.7, src="legacy"), s) == 0
    pool = [_c(1, 1, 1, 0.6, 1.7), _c(2, 2, 1, 0.6, 1.7)]
    assert [c.prediction_id for c in opt.available(pool, {1: 2}, s)] == [2]


def test_portfolio_respects_exposure():
    a, b = _c(1, 1, 1, 0.6, 1.7), _c(2, 2, 2, 0.6, 1.7)
    ts = [{"legs": [a, b], "ev": 0.2, "sd": 1.0, "stake": 0.5},
          {"legs": [a], "ev": 0.1, "sd": 1.0, "stake": 0.5},
          {"legs": [b], "ev": 0.05, "sd": 1.0, "stake": 0.05}]
    out = opt.portfolio_select(ts, max_uses=2, max_match_stake=0.6)
    assert len(out) == 2 and out[0]["ev"] == 0.2 and out[1]["ev"] == 0.05


def test_variant_order_keeps_two_for_exploration():
    s = copy.deepcopy(opt.DEFAULT_STRATEGY)
    s["variant_weights"] = {"50": {"a": 0.9, "b": 0.01, "c": 0.01}}
    assert opt.variant_order(50, ["a", "b", "c"], s) == ["a", "b"]


def test_propose_learns_bias_and_blocks_bad_leg_type():
    base = copy.deepcopy(opt.DEFAULT_STRATEGY)
    lt_bad = opt.leg_type("btts", 0.0, 1.9)
    legs = []
    for i in range(300):  # promise 60%, deliver ~35%
        legs.append(("btts", lt_bad, 0.6, 0.58, 1.9, 1.0 if i % 20 < 7 else 0.0, 1))
    chal, changes = lt.propose(base, legs, {}, None)
    kinds = {c["type"] for c in changes}
    assert "leg_bias" in kinds or "leg_block" in kinds
    assert chal["leg_bias"].get(lt_bad, 0) < 0 or lt_bad in chal["blocked_leg_types"]
    assert all(c.get("why") for c in changes)


def test_intercept_recovers_bias():
    import numpy as np
    rng = np.random.default_rng(0)
    p = rng.uniform(0.3, 0.8, 4000)
    z = np.log(p / (1 - p)) + 0.4
    y = (rng.uniform(size=p.size) < 1 / (1 + np.exp(-z))).astype(float)
    assert abs(lt._intercept(p, y) - 0.4) < 0.1
