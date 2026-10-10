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
    assert math.isclose(p, math.prod(c.p_honest for c in legs))
    assert p < math.prod(c.p for c in legs) * 0.4
    assert ev <= V.TICKET_EV_CAP and ev_raw <= V.TICKET_EV_CAP
    assert not V.LOTTERY_VALIDATED


def test_honest_probability_close_to_market():
    c = _c(1, 2.0, 0.65)  # model 65%, piața ~47.6%
    assert 0.47 < c.p_honest < 0.52
    assert c.ev_honest < 0.05


def test_suspect_price_excluded():
    c = _c(1, 4.0, 0.44)
    c.p_market = 0.44  # consens corect ~2.27, Superbet 4.0
    assert c.price_suspect and V.edge(c) == -1.0
