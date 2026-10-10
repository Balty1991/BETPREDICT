import math

from betpredict.builder import v4tickets as V
from betpredict.builder.pool import Cand


def _c(i, odds, p):
    return Cand(i, i, i, "L", "2026-10-11T18:00:00Z", "A", "B", "1x2", 0.0, "HOME", odds, p, p * odds - 1, "A", 80,
                p_market=1 / odds / 1.05, odds_source="superbet")


def test_lottery_ticket_probability_shrunk_and_ev_capped():
    legs = [_c(i, 2.2, 0.6) for i in range(1, 8)]
    total, p_raw, ev_raw = V.ticket_stats(legs)
    total2, p, ev = V.ticket_stats(legs, shrink=True)
    assert math.isclose(p, math.prod(min(0.97, V.LEG_SHRINK * V.p_prudent(c)) for c in legs))
    assert p < p_raw * 0.4  # 0.86^7 ≈ 0.35
    assert ev <= V.TICKET_EV_CAP and ev_raw <= V.TICKET_EV_CAP
    assert not V.LOTTERY_VALIDATED
