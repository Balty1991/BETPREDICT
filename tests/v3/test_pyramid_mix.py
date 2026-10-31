import math

from betpredict.builder import pyramid_mix as M
from betpredict.builder.pool import Cand


def _c(i, odds, p, market, league=None):
    return Cand(i, i, league if league is not None else i, None, "2026-10-31T12:00:00Z", None, None,
                market, 0.0, "OVER", odds, p, p * odds - 1, "A", 80,
                p_market=(1.0 / odds) / 1.05, odds_source="superbet")


def test_mix25_requires_positive_ev_and_diverse_families():
    pool = [
        _c(1, 1.50, 0.86, "over_under"),
        _c(2, 1.40, 0.86, "btts"),
        _c(3, 1.30, 0.86, "draw_no_bet"),
        _c(4, 1.45, 0.86, "1x2"),
        _c(5, 1.70, 0.86, "ss", league=5),
    ]
    # Simulate genuinely validated positive lift by market; don't smuggle in an
    # impossible market probability that would mark the bookmaker price suspect.
    rel = {(c.market, 0.0, c.selection): 0.30 for c in pool}
    result = M.pick_mix25(pool, M.RULES_MIX25, rel)

    assert result["status"] == "pick"
    legs, probability = result["main"]
    odds = math.prod(c.odds for c in legs)
    assert 2.50 <= odds <= 3.125
    assert 0.42 <= probability <= 1
    assert probability * odds - 1 >= 0.02
    assert len(legs) <= 4
    assert len({c.match_id for c in legs}) == len(legs)
    assert len({M._market_family(c) for c in legs}) == len(legs)
    assert any(c.market == "ss" for c in legs)
    assert any(c.market != "ss" for c in legs)


def test_mix25_returns_no_bet_instead_of_forcing_weak_candidates():
    pool = [
        _c(1, 1.50, 0.40, "over_under"),
        _c(2, 1.50, 0.40, "btts"),
        _c(3, 1.50, 0.40, "draw_no_bet"),
        _c(4, 1.50, 0.40, "1x2"),
    ]
    result = M.pick_mix25(pool, M.RULES_MIX25, {})
    assert result["status"] == "no_bet"
    assert result["main"] is None

    # A valid high-EV Robot-only slip still isn't labelled a mixed recommendation.
    robot_only = [
        _c(10, 1.50, 0.95, "over_under"),
        _c(11, 1.70, 0.95, "btts"),
    ]
    rel = {(c.market, 0.0, c.selection): 0.30 for c in robot_only}
    assert M.pick_mix25(robot_only, M.RULES_MIX25, rel)["status"] == "no_bet"


def test_mix_tracks_are_separate_playable_variants_with_nonnegative_mix140_ev():
    assert M.RULES_MIX140["variant"] == "pmix140"
    assert M.RULES_MIX140["min_ev"] >= 0
    assert M.RULES_MIX25["variant"] == "pmix25"
    assert M.RULES_MIX25["min_ev"] >= 0.02
    assert M.RULES_MIX140["start_bank"] == M.RULES_MIX25["start_bank"] == 2.0
