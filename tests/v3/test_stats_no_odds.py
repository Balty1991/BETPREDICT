from betpredict.stats import _agg


def row(res, odds, profit, p=0.6):
    return {"result": res, "odds_shown": odds, "profit_1u": profit, "p_calibrated": p, "clv": None}


def test_no_odds_excluded_from_roi_and_avg_odds():
    a = _agg([row("won", 2.0, 1.0), row("lost", 1.5, -1.0), row("won", None, 0.0), row("lost", None, 0.0), row(None, None, None)])
    assert a["won"] == 2 and a["lost"] == 2 and a["pending"] == 1
    assert a["played"] == 2 and a["played_won"] == 1
    assert a["avg_odds"] == 1.75
    assert a["roi_pct"] == 0.0
    assert a["win_rate"] == 0.5


def test_all_without_odds():
    a = _agg([row("won", None, None), row("lost", 0, None)])
    assert a["played"] == 0 and a["roi_pct"] is None and a["avg_odds"] is None
