import math

from betpredict.builder.pool import Cand, ticket_probability
from betpredict.builder.tickets import build_variant, suggested_stake, STAKE_CAP


def cand(i, odds, p, p_market=None, grade="A", league=None):
    return Cand(i, i, league if league is not None else i, f"L{i}", f"2026-10-09T{10 + i % 10:02d}:00:00Z", "H", "A",
                "1x2", 0.0, "HOME", odds, p, p * odds - 1, grade, 80, p_market=p_market)


def test_shrink_toward_market_reduces_optimism():
    c = cand(1, 2.0, 0.60, p_market=0.48)
    assert abs(c.p_adj - 0.54) < 0.01  # blend în spațiul logit (optimizer.leg_p)
    assert c.ev_adj < c.ev
    # fără piață: folosim cota implicită minus marjă
    d = cand(2, 2.0, 0.60)
    assert d.p_adj < 0.60


def test_only_positive_adjusted_ev_ab_legs():
    good = [cand(i, 1.6 + 0.05 * (i % 5), 0.72, p_market=0.62) for i in range(30)]
    bad = [cand(100 + i, 1.9, 0.60, p_market=0.48, grade="C") for i in range(10)]  # grad C
    neg = [cand(200 + i, 1.8, 0.56, p_market=0.50) for i in range(10)]  # EV ajustat < 0
    res = build_variant(good + bad + neg, 50, "echilibrat", {})
    assert res
    legs, _ = res
    assert all(c.ev_adj > 0 and c.grade in ("A", "B") for c in legs)


def test_skip_tier_when_no_positive_ev():
    pool = [cand(i, 1.8, 0.55, p_market=0.52) for i in range(40)]  # EV ajustat negativ
    assert build_variant(pool, 50, "echilibrat", {}) is None
    assert build_variant(pool, 500, "valoare", {}) is None


def test_low_probability_legs_are_capped():
    pool = [cand(i, 3.4, 0.36, p_market=0.30) for i in range(40)]  # p_adj 0.33 < 0.42 pentru ~50
    assert build_variant(pool, 50, "valoare", {}) is None


def test_suggested_stake_fractional_kelly():
    assert suggested_stake(0.03, 45.0, STAKE_CAP[50]) > 0
    assert suggested_stake(0.03, 45.0, STAKE_CAP[50]) <= STAKE_CAP[50]
    assert suggested_stake(0.02, 45.0, 0.5) == 0.0  # EV negativ → fără miză
    assert suggested_stake(0.6, 2.0, 2.0) == round(min(2.0, 0.25 * (0.2 / 1.0) * 100), 2)


def test_adjusted_ticket_probability_is_lower():
    legs = [cand(i, 1.7, 0.7, p_market=0.6) for i in range(5)]
    assert ticket_probability(legs, adjusted=True) < ticket_probability(legs)
    assert abs(legs[0].p_adj - 0.65) < 0.01
