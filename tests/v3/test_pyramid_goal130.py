import math

from betpredict.builder import pyramid_auto, pyramid_mix as M
from betpredict.builder.pool import Cand


def _c(i, odds, p, market, selection, line=0.0, league=None, *, p_market=0.95, source="superbet", drift=None):
    return Cand(
        i, i, league if league is not None else i, None, "2026-10-31T12:00:00Z", "Gazde", "Oaspeți",
        market, line, selection, odds, p, p * odds - 1, "A", 85, True,
        p_market=p_market, odds_source=source, drift=drift,
    )


def test_goal130_picks_only_goal_markets_in_target_band_with_one_leg_per_match():
    pool = [
        _c(1, 1.10, 0.98, "team_total_home", "OVER", 0.5),
        _c(2, 1.10, 0.98, "ss", "HO05"),
        _c(3, 1.06, 0.97, "ss", "HG13"),
        # A second outcome from match 1 must not be combined with its team total.
        _c(1, 1.25, 0.99, "btts", "YES"),
        # Neither unrelated results nor non-goal Supersocial markets may be used.
        _c(4, 1.10, 0.99, "1x2", "HOME"),
        _c(5, 1.10, 0.99, "ss", "YC35"),
    ]

    result = M.pick_goal130(pool)

    assert result["status"] == "pick"
    legs, p = result["main"]
    odds = math.prod(c.odds for c in legs)
    assert 1 <= len(legs) <= 4
    assert 1.20 <= odds <= 1.30
    assert p >= M.RULES_GOAL130["min_p"]
    assert p * odds - 1 >= M.RULES_GOAL130["min_ev"]
    assert len({c.match_id for c in legs}) == len(legs)
    assert all(c.market == "ss" or M._robot_goal_market(c) for c in legs)
    assert all(c.market != "ss" or c.selection in M.GOAL_SS_KEYS for c in legs)


def test_goal130_does_not_force_a_bet_from_weak_or_unplayable_prices():
    weak = _c(1, 1.25, 0.40, "ss", "HO05", p_market=0.76)
    stale = _c(2, 1.25, 0.99, "ss", "HG13", drift=0.08)
    estimated = _c(3, 1.25, 0.99, "ss", "AO05", source="estimated")

    result = M.pick_goal130([weak, stale, estimated])

    assert result["status"] == "no_bet"
    assert result["main"] is None
    assert "Nu completăm" in result["reason"]


def test_goal130_rules_and_auto_track_are_independent_and_playable():
    rules = M.RULES_GOAL130
    assert rules["band"] == [1.20, 1.30]
    assert (rules["min_legs"], rules["max_legs"]) == (1, 4)
    assert rules["min_p"] >= 0.80
    assert rules["min_ev"] >= -0.02
    assert rules["variant"] == "pgoal130"
    assert pyramid_auto.TRACKS["goal130"]["prefix"] == "pyramidgoal130"
    assert pyramid_auto.TRACKS["goal130"]["key"] == M.KEY_GOAL130
