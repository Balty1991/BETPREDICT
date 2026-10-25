from betpredict.builder.pyramid_risk import RULES_R100, pick_r100
from betpredict.builder.pool import Cand


def _c(mid, key, o, league="Premier League"):
    return Cand(prediction_id=0, match_id=mid, league_id=None, league=league, kickoff_utc="2026-10-25T14:00:00Z", home="A", away="B",
                market="ss", line=0.0, selection=key, odds=o, p=0.8, ev=0.0, grade="B", confidence=50)


def test_r100_lowest_first_until_target():
    pool = [_c(1, "H2G13", 1.30), _c(2, "YCU55", 1.25), _c(3, "YCU45", 1.15), _c(4, "H2G13", 1.35),
            _c(5, "G25", 1.10), _c(6, "YCU55", 1.20, "Bad"), _c(2, "H2G13", 1.40)]
    r = pick_r100(pool, RULES_R100, {"Bad"})
    legs, _ = r["main"]
    assert [l.match_id for l in legs] == [3, 2, 1, 4]
    o = 1.0
    for l in legs:
        o *= l.odds
    assert 2.5 <= o <= 3.125 and all(l.selection in ("H2G13", "YCU45", "YCU55") for l in legs)


def test_r100_no_bet_when_short():
    r = pick_r100([_c(1, "H2G13", 1.30)], RULES_R100, set())
    assert r["status"] == "no_bet"
