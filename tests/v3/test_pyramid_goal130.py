import math

from betpredict.builder import pyramid_auto, pyramid_mix as M
from betpredict.builder.pool import Cand


def _c(i, odds, p, market="1x2", selection="HOME", line=0.0, league=1, *, p_market=None, source="superbet",
       drift=None, kickoff="2026-11-01T16:00:00Z", extra=None):
    fair = p_market if p_market is not None else min(0.97, (1.0 / odds) / 1.05)
    return Cand(
        i, i, league, None, kickoff, "Gazde", "Oaspeți",
        market, line, selection, odds, p, p * odds - 1, "A", 85, True,
        p_market=fair, odds_source=source, drift=drift, extra=extra or {},
    )


def test_goal130_maximizes_demargined_joint_probability_inside_the_band():
    # 1.68 are șansă mai mică decât 1.52; regula ține capătul de jos când crește șansa.
    short = _c(1, 1.52, 0.64, p_market=0.64)
    long = _c(2, 1.68, 0.70, p_market=0.55)
    pair = [_c(3, 1.22, 0.80, p_market=0.78), _c(4, 1.28, 0.76, p_market=0.74)]
    result = M.pick_goal130([short, long, *pair])
    assert result["status"] == "pick"
    legs, p = result["main"]
    odds = math.prod(c.odds for c in legs)
    assert 1.50 <= odds <= 1.70
    assert legs == [short]
    assert abs(p - 0.64) < 1e-9
    assert len({c.match_id for c in legs}) == len(legs)


def test_goal130_prefers_fewer_legs_when_joint_probability_ties():
    single = _c(1, 1.55, 0.60, p_market=0.60)
    a = _c(2, 1.22, 0.80, p_market=math.sqrt(0.60))
    b = _c(3, 1.27, 0.78, p_market=math.sqrt(0.60))
    result = M.pick_goal130([single, a, b])
    assert result["status"] == "pick"
    assert result["main"][0] == [single]


def test_goal130_prefers_the_low_end_of_the_band_at_equal_probability():
    low = _c(1, 1.51, 0.62, p_market=0.62)
    high = _c(2, 1.69, 0.62, p_market=0.62)
    result = M.pick_goal130([high, low])
    assert result["main"][0] == [low]


def test_goal130_uses_two_or_three_legs_when_no_single_is_in_band():
    legs = [_c(i, 1.16, 0.85, p_market=0.82) for i in range(1, 4)]
    result = M.pick_goal130(legs)
    assert result["status"] == "pick"
    chosen, _p = result["main"]
    assert len(chosen) == 3
    assert 1.50 <= math.prod(c.odds for c in chosen) <= 1.70


def test_goal130_model_only_vetoes_and_keeps_one_leg_per_match():
    vetoed = _c(1, 1.55, 0.40, p_market=0.62)  # modelul e cu >12 pp sub piață
    same_match = Cand(
        99, 1, 1, None, "2026-11-01T16:00:00Z", "Gazde", "Oaspeți",
        "btts", 0.0, "NO", 1.58, 0.58, 0.58 * 1.58 - 1, "A", 80, True,
        p_market=0.60, odds_source="superbet",
    )
    other = _c(2, 1.60, 0.58, p_market=0.59)
    result = M.pick_goal130([vetoed, same_match, other])
    assert result["status"] == "pick"
    legs = result["main"][0]
    assert vetoed not in legs
    assert same_match in legs
    assert len({c.match_id for c in legs}) == len(legs)
    assert result["diagnostics"]["veto"] == 1


def test_goal130_skips_drift_late_kickoff_and_unsupported_variance():
    drifted = _c(1, 1.55, 0.62, p_market=0.62, drift=0.04)
    late = _c(2, 1.55, 0.62, p_market=0.62, kickoff="2026-11-01T20:30:00Z")  # 22:30 RO
    cards = _c(3, 1.55, 0.62, market="ss", selection="YCU55", p_market=0.62)
    corners = _c(4, 1.55, 0.70, market="ss", selection="C85", p_market=0.62,
                 extra={"ss_n": 40, "ss_lift": 1.2})
    result = M.pick_goal130([drifted, late, cards, corners])
    assert result["status"] == "no_bet"
    assert result["main"] is None
    assert result["reason"].startswith("Nicio selecție azi")
    assert "Următoarea verificare" in result["reason"]


def test_goal130_allows_well_supported_cards_when_nothing_else_fits():
    cards = _c(1, 1.55, 0.62, market="ss", selection="YCU55", p_market=0.62,
               extra={"ss_n": 120, "ss_lift": 1.05})
    result = M.pick_goal130([cards])
    assert result["status"] == "pick"
    assert result["main"][0] == [cards]


def test_goal130_prefers_a_top_league_when_the_price_is_the_same():
    top = _c(1, 1.55, 0.62, league=1, p_market=0.62)
    other = _c(2, 1.55, 0.62, league=999, p_market=0.62)
    result = M.pick_goal130([other, top])
    assert result["main"][0] == [top]


def test_streak_backtest_counts_consecutive_wins():
    def day(i, won):
        c = _c(i, 1.55, 0.62, p_market=0.62)
        return [c], {c.prediction_id: "won" if won else "lost"}

    # 3 câștiguri, pierdere, 1 câștig → serii 3 și 1
    doc = M.streak_backtest([day(1, True), day(2, True), day(3, True), day(4, False), day(5, True)])
    assert doc["days"] == 5
    assert doc["max_steps"] == 3
    assert doc["runs"] == 2
    assert {d["steps"]: d["runs"] for d in doc["distribution"]} == {3: 1, 1: 1}
    assert doc["reach_probability"]["1"] == 1.0
    assert doc["reach_probability"].get("4") is None  # nici o serie nu ajunge la încasarea de la pasul 4


def test_goal130_rules_are_the_streak_band():
    rules = M.RULES_GOAL130
    assert rules["band"] == [1.50, 1.70]
    assert (rules["min_legs"], rules["max_legs"]) == (1, 3)
    assert rules["variant"] == "pgoal130"
    assert pyramid_auto.TRACKS["goal130"]["prefix"] == "pyramidgoal130"
    assert pyramid_auto.TRACKS["goal130"]["name"] == "Piramida 1.50–1.70"
