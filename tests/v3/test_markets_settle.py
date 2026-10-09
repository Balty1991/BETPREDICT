import pytest

from betpredict.robot.markets import leg_factor, probs_from_matrix, profit_1u, settle_selection
from analytics_core import football_score_matrix


@pytest.mark.parametrize("market,line,sel,score,expected", [
    ("1x2", 0, "HOME", (2, 1), "won"),
    ("1x2", 0, "DRAW", (2, 1), "lost"),
    ("double_chance", 0, "X2", (1, 1), "won"),
    ("double_chance", 0, "12", (1, 1), "lost"),
    ("draw_no_bet", 0, "AWAY", (0, 0), "void"),
    ("draw_no_bet", 0, "AWAY", (0, 1), "won"),
    ("over_under", 2.5, "OVER", (2, 1), "won"),
    ("over_under", 2.5, "UNDER", (2, 1), "lost"),
    ("over_under", 2.0, "OVER", (1, 1), "void"),
    ("btts", 0, "NO", (3, 0), "won"),
    ("btts", 0, "YES", (3, 0), "lost"),
])
def test_settle_selection(market, line, sel, score, expected):
    assert settle_selection(market, line, sel, *score) == expected


def test_settle_unknown_or_missing_score_is_none():
    assert settle_selection("1x2", 0, "HOME", None, 1) is None
    assert settle_selection("total_corners", 9.5, "OVER", 1, 1) is None  # niciodată „lost” din oficiu


def test_profit_and_leg_factor():
    assert profit_1u("won", 1.8) == pytest.approx(0.8)
    assert profit_1u("lost", 1.8) == -1.0
    assert profit_1u("void", 1.8) == 0.0
    assert leg_factor("void", 3.0) == 1.0
    assert leg_factor("lost", 3.0) == 0.0


def test_matrix_probabilities_consistent():
    pr = probs_from_matrix(football_score_matrix(1.6, 1.1, max_goals=10))
    assert pr[("1x2", 0.0, "HOME")] + pr[("1x2", 0.0, "DRAW")] + pr[("1x2", 0.0, "AWAY")] == pytest.approx(1, abs=1e-6)
    assert pr[("double_chance", 0.0, "1X")] == pytest.approx(pr[("1x2", 0.0, "HOME")] + pr[("1x2", 0.0, "DRAW")])
    assert pr[("over_under", 2.5, "OVER")] + pr[("over_under", 2.5, "UNDER")] == pytest.approx(1)
    assert pr[("over_under", 1.5, "OVER")] > pr[("over_under", 2.5, "OVER")] > pr[("over_under", 3.5, "OVER")]
    assert pr[("1x2", 0.0, "HOME")] > pr[("1x2", 0.0, "AWAY")]
