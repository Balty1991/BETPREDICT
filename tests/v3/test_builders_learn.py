import math

from betpredict.builder.pool import Cand
from betpredict.builder.pyramid import pick_pyramid
from betpredict.builder.tickets import build_variant, knapsack
from betpredict.learn import fit_blend, fit_platt


def cand(i, odds, p, league=None, market="1x2", grade="A"):
    return Cand(i, i, league if league is not None else i, f"L{i}", f"2026-10-09T{10 + i % 10:02d}:00:00Z", "H", "A",
                market, 0.0, "HOME", odds, p, p * odds - 1, grade, 80)


def test_knapsack_hits_target_band():
    cs = [cand(i, 1.3 + 0.05 * (i % 10), 0.7 - 0.01 * (i % 10)) for i in range(40)]
    lo, hi = math.log(50 * 0.85), math.log(50 * 1.25)
    idx = knapsack(cs, [c.logp for c in cs], lo, hi, 5, 12)
    assert idx
    tot = math.prod(cs[i].odds for i in idx)
    assert 50 * 0.85 * 0.97 <= tot <= 50 * 1.25 * 1.03


def test_variant_one_per_match_and_league_cap():
    pool = [cand(i, 1.5 + 0.04 * (i % 7), 0.74, league=i % 5) for i in range(30)]
    res = build_variant(pool, 50, "echilibrat", {})
    assert res
    legs, _ = res
    assert len({c.match_id for c in legs}) == len(legs)
    leagues = [c.league_id for c in legs]
    assert max(leagues.count(l) for l in set(leagues)) <= 2


def test_pyramid_pick_and_no_bet():
    good = [cand(i, 1.4, 0.8) for i in range(6)]
    res = pick_pyramid(good)
    assert res["status"] == "pick"
    legs, p = res["main"]
    assert 1.85 <= math.prod(c.odds for c in legs) <= 2.2
    weak = [cand(i, 1.45, 0.56, grade="B") for i in range(4)]
    assert pick_pyramid(weak)["status"] == "no_bet"
    assert pick_pyramid([])["status"] == "no_bet"


def test_fit_blend_prefers_informative_source():
    import random

    rng = random.Random(1)
    samples = []
    for _ in range(400):
        p = rng.uniform(0.2, 0.8)
        y = 1.0 if rng.random() < p else 0.0
        samples.append((0.5, 0.5, p, y))  # doar „piața” are informație
    w, _ = fit_blend(samples)
    assert w["market"] >= 0.8


def test_platt_corrects_overconfidence():
    import random

    rng = random.Random(2)
    ps, ys = [], []
    for _ in range(2000):
        true = rng.uniform(0.3, 0.7)
        shown = min(0.99, max(0.01, 0.5 + (true - 0.5) * 2))  # supraîncredere ×2
        ps.append(shown)
        ys.append(1.0 if rng.random() < true else 0.0)
    a, b = fit_platt(ps, ys)
    assert 0.3 <= a < 0.8
