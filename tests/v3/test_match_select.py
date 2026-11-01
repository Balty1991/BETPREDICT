"""Settlement status, calibration shrinkage, and one market per match."""
import sqlite3

from betpredict.lab.patterns import _probs, _won
from betpredict.model.match_select import (VETO_GAP, choose_pool, fit_rows, probability_for_leg, select_fixture)
from betpredict.settle import classify_payout, reclassify_settled
from betpredict.stats import ticket_odds_bands
from betpredict.builder.pool import Cand


def test_payout_below_stake_is_not_a_win():
    assert classify_payout(0.10, 0.04) == "partial"  # acca_1000, ticket 2039
    assert classify_payout(0.10, 0.05) == "partial"  # system 17/20, ticket 1893
    assert classify_payout(0.10, 0.0) == "lost"
    assert classify_payout(0.10, 0.28) == "won"
    assert classify_payout(1.0, 1.0, all_void=True) == "void"


def test_historical_rows_and_odds_band_roi_use_cash_not_nominal_odds():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE ticket (id INT, kind TEXT, variant TEXT, stake REAL, payout REAL, status TEXT,
                 day TEXT, total_odds REAL, clv REAL, notes TEXT)""")
    c.execute("CREATE TABLE ticket_leg (ticket_id INT, result TEXT, odds REAL)")
    # previously labelled won: payout under the stake, nominal odds under 3
    c.execute("INSERT INTO ticket VALUES (2039,'acca_1000','loterie',0.10,0.04,'won','2026-10-20',2.40,NULL,'{}')")
    c.execute("INSERT INTO ticket_leg VALUES (2039,'won',1.2)")
    # a real win at odds 2
    c.execute("INSERT INTO ticket VALUES (1,'acca_value','x',1.0,2.0,'won','2026-10-20',2.0,NULL,'{}')")
    c.execute("INSERT INTO ticket_leg VALUES (1,'won',2.0)")
    assert reclassify_settled(c) == 1
    assert c.execute("SELECT status FROM ticket WHERE id=2039").fetchone()[0] == "partial"
    band = next(b for b in ticket_odds_bands(c) if b["key"] == "<3")
    # cash ROI: (2.00+0.04 - 1.00-0.10) / 1.10, not both tickets paid at their nominal price
    assert band["partial"] == 1 and band["won"] == 1
    assert abs(band["roi_pct"] - 100 * (2.04 - 1.10) / 1.10) < 0.2
    assert band["roi_pct"] < 100  # the bogus +162% counted the partial as a full-price win


def test_market_shrinkage_uses_model_probability_not_the_price():
    rows = [{"p": 0.72, "y": 1 if i < 40 else 0, "odds": 1.40, "market": "m", "league": "L"} for i in range(100)]
    cal = fit_rows(rows)
    # hit 0.40 against a model that said 0.72. The ratio is not hit/(1/odds), which would count the margin again.
    assert abs(cal.ratio("m", "L") - 0.40 / 0.72) < 0.08
    assert cal.adjust(0.72, "m", "L", 1.40) < 0.60
    thin = fit_rows(rows + [{"p": 0.9, "y": 1, "odds": 1.2, "market": "C85", "league": "G"} for _ in range(2)])
    # two league rows cannot pull the ratio away from the market-level one (k = 200)
    assert abs(thin.ratio("C85", "G") - thin.ratio("C85", "")) < 0.05


def test_safest_pick_follows_the_market_and_the_model_only_vetoes():
    offers = [
        {"market": "btts:NO", "selection": "NO", "label": "NG", "p": 0.70, "p_market": 0.74, "odds": 1.30, "league": "L"},
        {"market": "1x2:HOME", "selection": "HOME", "label": "1", "p": 0.80, "p_market": 0.55, "odds": 1.80, "league": "L"},
    ]
    pick = select_fixture(offers)
    assert pick["decision"] == "safest" and pick["best_value"] is None
    assert pick["safest"]["market"] == "btts:NO"  # higher market probability, even though the model prefers 1
    assert abs(pick["safest"]["p_adj"] - 0.74) < 1e-9
    vetoed = [{**offers[0], "p": 0.74 - VETO_GAP - 0.02}, offers[1]]
    no = select_fixture(vetoed)
    assert no["decision"] == "no_bet" and no["safest"]["market"] == "btts:NO"
    one_sided = [{"market": "C85", "selection": "C85", "label": "Cornere 8.5", "p": 0.70, "odds": 1.40, "league": "L"}]
    corner = select_fixture(one_sided)
    assert corner["decision"] == "safest" and corner["safest"]["market"] == "C85"


def test_pool_keeps_the_safest_side_per_match():
    def c(i, mid, market, sel, odds, p, pm):
        return Cand(i, mid, 1, "Liga", "2026-10-11T18:00:00Z", "H", "A", market, 0.0, sel, odds, p, p * odds - 1, "A", 80,
                    p_market=pm, odds_source="superbet")
    pool = [c(1, 10, "btts", "NO", 1.30, 0.80, 0.74), c(2, 10, "over_under", "OVER", 1.90, 0.90, 0.52),
            c(3, 11, "btts", "NO", 1.40, 0.40, 0.70)]
    chosen = choose_pool(pool)
    assert [x.match_id for x in chosen] == [10]
    assert chosen[0].selection == "NO"
    assert abs(chosen[0].extra["p_adj"] - 0.74) < 1e-9
    assert probability_for_leg(chosen[0]) == chosen[0].extra["p_adj"]


def test_orphan_leg_settles_from_the_score_and_extra_time_uses_ninety_minutes():
    from betpredict.settle import leg_result_from_match, regulation_score, settle_orphan_legs

    assert regulation_score(3, 2, "aet", '{"home_score_et": 1, "away_score_et": 0}') == (2, 2)
    assert regulation_score(1, 0, "finished", "{}") == (1, 0)
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE match (id INT, status TEXT, ft_home INT, ft_away INT, ht_home INT, ht_away INT,
                 corners_home INT, corners_away INT, corners_ht_home INT, corners_ht_away INT,
                 cards_home INT, cards_away INT, raw_json TEXT, kickoff_utc TEXT)""")
    c.execute("""CREATE TABLE ticket_leg (market TEXT, selection TEXT, result TEXT, prediction_id INT, match_id INT)""")
    c.execute("INSERT INTO match VALUES (1,'finished',2,0,1,0,NULL,NULL,NULL,NULL,NULL,NULL,'{}','2026-10-25T18:00:00Z')")
    c.execute("INSERT INTO ticket_leg VALUES ('1x2|0','HOME',NULL,NULL,1)")
    assert settle_orphan_legs(c) == 1
    assert c.execute("SELECT result FROM ticket_leg").fetchone()[0] == "won"
    cup = {"status": "aet", "ft_home": 2, "ft_away": 1, "raw_json": '{"home_score_90": 1, "away_score_90": 1}',
           "ht_home": 0, "ht_away": 0, "corners_home": None, "corners_away": None, "corners_ht_home": None,
           "corners_ht_away": None, "cards_home": None, "cards_away": None, "kickoff_utc": "2026-10-01"}
    assert leg_result_from_match("over_under|2.5", "OVER", cup) == "lost"


def test_injury_rows_reach_the_absence_nudge():
    from betpredict.robot.engine import _overlay_af_injuries, absence_edge
    import json
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE af_injury (match_id INT, players_json TEXT)")
    players = [{"side": "home", "name": "A", "type": "Missing", "reason": "Knee"},
               {"side": "home", "name": "B", "type": "Missing", "reason": "Suspended"}]
    c.execute("INSERT INTO af_injury VALUES (7, ?)", (json.dumps(players),))
    ctx = {}
    _overlay_af_injuries(c, [7], ctx)
    assert absence_edge(ctx[7]) == 2


def test_exact_three_or_four_goals_from_poisson():
    p = _probs(1.35, 1.25, 0.45, None)["G34"]
    assert 0.30 < p < 0.46
    base = {"hthg": 1, "htag": 1, "hc": 0, "ac": 0}
    assert _won("G34", {**base, "fthg": 2, "ftag": 1})
    assert not _won("G34", {**base, "fthg": 2, "ftag": 0})
    assert not _won("G34", {**base, "fthg": 3, "ftag": 2})
