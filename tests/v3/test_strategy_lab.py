import math

import numpy as np

from betpredict.lab import engine as E
from betpredict.lab import superbilete as S
from betpredict.builder.pool import Cand


def test_lambdas_roundtrip():
    lh, la = np.array([1.6]), np.array([1.0])
    P = E.market_probs(lh, la)
    h, a = E.lambdas_from_market(P["H"], P["A"], P["O25"])
    assert abs(h[0] - 1.6) < 0.02 and abs(a[0] - 1.0) < 0.02


def test_system_payout_matches_bruteforce():
    import itertools
    legs = [E.Leg(i, "H", 0.5, o, w, 0, True) for i, (o, w) in enumerate([(2.0, True), (1.5, True), (3.0, False), (1.2, True)])]
    k = 3
    brute = sum(math.prod(l.odds for l in c) for c in itertools.combinations(legs, k) if all(l.win for l in c)) / math.comb(4, k)
    assert abs(E.ticket_return(legs, 1) - brute) < 1e-9
    assert E.ticket_return(legs, 0) == 0.0


def test_metrics_and_summary():
    m = E.metrics([0, 0, 5.0, 0])
    assert m["n"] == 4 and m["hit_rate"] == 0.25 and m["longest_losing_streak"] == 2 and abs(m["roi"] - 0.25) < 1e-9


def _c(i, sel, odds, p):
    mk = {"O05": ("over_under", 0.5, "OVER"), "H": ("1x2", 0.0, "HOME")}[sel]
    return Cand(i, 100 + i, i, "L", "2026-10-11T18:00:00Z", "A", "B", mk[0], mk[1], mk[2], odds, p, p * odds - 1, "A", 80, True,
                p_market=p, odds_source="superbet")


def test_pick_legs_reaches_target_and_respects_band():
    st = {"market_set": "favoriti_1x2", "band": [1.25, 1.6], "key": "p", "drift_filter": True, "league": "all", "tier": 50, "system": 0}
    pool = [_c(i, "H", 1.5, 0.64) for i in range(1, 15)] + [_c(50, "O05", 1.05, 0.95)]
    legs = S.pick_legs(pool, st, {})
    assert legs and math.prod(c.odds for c in legs) >= 50 and all(1.25 <= c.odds <= 1.6 for c in legs)
    used = {c.prediction_id: 2 for c in legs}
    assert S.pick_legs(pool, st, used) is None  # controlul suprapunerii
