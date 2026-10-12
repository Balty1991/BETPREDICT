"""Cote premeci vs live și profilul selectabil. Nu promovează un model nou."""

from types import SimpleNamespace

from betpredict.builder.profiles import PREFERINTE, select_profile
from betpredict.model.odds_time import odds_time_status, prematch_eval_ok


def test_prematch_live_and_missing_timestamp():
    ko = "2026-06-01T18:00:00Z"
    assert odds_time_status("2026-06-01T17:59:00Z", ko) == "prematch"
    assert odds_time_status("2026-06-01T18:00:00Z", ko) == "prematch"
    assert odds_time_status("2026-06-01T18:00:01Z", ko) == "live"
    assert odds_time_status(None, ko) == "unknown"
    assert odds_time_status("2026-06-01T12:00:00Z", None) == "unknown"
    assert odds_time_status("nu-e-o-data", ko) == "unknown"
    assert prematch_eval_ok("2026-06-01T12:00:00Z", ko, True) is True
    assert prematch_eval_ok("2026-06-01T19:00:00Z", ko, True) is False
    assert prematch_eval_ok(None, ko, True) is False  # depozitul fără timestamp nu e premeci
    assert prematch_eval_ok("2026-06-01T12:00:00Z", ko, False) is False


def _c(**kw):
    base = dict(match_id=1, market="over_under", odds=1.5, p=0.7, p_honest=0.62, ev_honest=0.62 * 1.5 - 1,
                healthy=True, sport="football", league_id=1)
    base.update(kw)
    if "ev_honest" not in kw and "p_honest" in kw:
        base["ev_honest"] = kw["p_honest"] * base["odds"] - 1
    return SimpleNamespace(**base)


def test_profile_keeps_rules_and_refuses_to_relax():
    assert PREFERINTE["min_leg_odds"] == 1.40
    assert PREFERINTE["max_legs"] == 4
    assert PREFERINTE["pyramid"]["max_steps"] == 5
    assert PREFERINTE["pyramid"]["start_bank_units"] == 10
    empty = select_profile([
        _c(market="1x2", odds=1.8, ev_honest=0.05),
        _c(match_id=2, odds=1.2, ev_honest=0.04),
        _c(match_id=3, odds=1.6, ev_honest=-0.02),
    ])
    assert empty["status"] == "no_bet" and empty["legs"] == []
    assert "nu se relaxează" in empty["reason"]


def test_default_leg_blend_is_logit_not_a_new_champion():
    """Paritate cu optimizer.leg_p la ponderea implicită 0.5, fără leg_bias. Nu schimbă campionul."""
    import math
    from betpredict.builder import optimizer

    prev = optimizer._CACHE["strategy"]
    optimizer.use_strategy({"shrink_w": {"default": 0.5}, "leg_bias": {}})
    try:
        got = optimizer.leg_p(0.62, 0.55, 1.80, "over_under", 2.5)
    finally:
        optimizer._CACHE["strategy"] = prev

    def logit(p: float) -> float:
        p = min(1 - 1e-6, max(1e-6, p))
        return math.log(p / (1 - p))

    z = 0.5 * logit(0.62) + 0.5 * logit(0.55)
    expect = min(0.995, max(0.005, 1 / (1 + math.exp(-z))))
    assert abs(got - expect) < 1e-12
    linear = 0.5 * 0.62 + 0.5 * 0.55
    assert abs(got - linear) > 1e-4


def test_profile_one_per_match_ou_dc_positive_ev_max_four():
    pool = [
        _c(match_id=1, market="over_under", odds=1.7, p_honest=0.64),
        _c(match_id=1, market="double_chance", odds=1.45, p_honest=0.8),  # același meci, EV mai bun
        _c(match_id=2, market="double_chance", odds=1.55, p_honest=0.7),
        _c(match_id=3, market="over_under", odds=1.9, p_honest=0.58),
        _c(match_id=4, market="over_under", odds=1.6, p_honest=0.66),
        _c(match_id=5, market="over_under", odds=1.5, p_honest=0.7),
        _c(match_id=6, market="1x2", odds=2.0, p_honest=0.6),
    ]
    got = select_profile(pool)
    assert got["status"] == "pick"
    assert len(got["legs"]) <= 4
    assert len({c.match_id for c in got["legs"]}) == len(got["legs"])
    assert all(c.market in ("over_under", "double_chance") for c in got["legs"])
    assert all(c.odds >= 1.40 for c in got["legs"])
    assert got["ev"] > 0
    assert got["same_match_dropped"] >= 1
    assert got["pyramid"]["target_odds"] == 2.0
