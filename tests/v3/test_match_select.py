"""Settlement status, calibration shrinkage, and one market per match."""
import sqlite3

from betpredict.lab.patterns import _probs, _won
from betpredict.model.match_select import (EV_MARGIN, choose_pool, fit_rows, probability_for_leg, select_fixture)
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


def test_market_shrinkage_and_overconfident_bucket():
    rows = [{"p": 0.72, "y": 1 if i < 40 else 0, "odds": 1.40, "market": "m", "league": "L"} for i in range(100)]
    cal = fit_rows(rows)
    # promised 0.72, hit 0.40, implied 1/1.40 — adjusted probability has to come down
    assert cal.adjust(0.72, "m", "L", 1.40) < 0.60
    # a different market with no sample is shrunk toward that global ratio, not left at face value
    assert cal.adjust(0.72, "btts:NO", "Other", 1.40) < 0.72
    # tiny sample does not override the parent: 2 wins out of 2 cannot erase the global penalty
    thin = fit_rows(rows + [{"p": 0.9, "y": 1, "odds": 1.2, "market": "C85", "league": "G"} for _ in range(2)])
    assert thin.ratio("C85", "G") < thin.ratio("m", "L") + 0.5


def test_per_match_pick_is_best_positive_ev_or_no_bet():
    offers = [
        {"market": "btts:NO", "selection": "NO", "label": "NG", "p": 0.70, "odds": 1.40, "league": "L"},
        {"market": "C85", "selection": "C85", "label": "Cornere 8.5", "p": 0.62, "odds": 1.80, "league": "L"},
    ]
    pick = select_fixture(offers)
    assert pick["decision"] == "value"
    assert pick["best_value"]["market"] == "C85"
    assert pick["best_value"]["ev"] > EV_MARGIN
    assert pick["safest"]["market"] == "btts:NO"
    assert pick["safest"]["ev"] < pick["best_value"]["ev"]
    assert "p ajustat" in pick["reason"]
    dead = [{"market": "btts:NO", "selection": "NO", "label": "NG", "p": 0.55, "odds": 1.50, "league": "L"}]
    no = select_fixture(dead)
    assert no["decision"] == "no_bet" and no["best_value"] is None and no["safest"]["label"] == "NG"


def test_pool_keeps_one_market_per_match():
    def c(i, mid, market, sel, odds, p):
        return Cand(i, mid, 1, "Liga", "2026-10-11T18:00:00Z", "H", "A", market, 0.0, sel, odds, p, p * odds - 1, "A", 80,
                    p_market=1 / odds, odds_source="superbet")
    pool = [c(1, 10, "btts", "NO", 1.40, 0.70), c(2, 10, "over_under", "OVER", 1.90, 0.62),
            c(3, 11, "btts", "NO", 1.50, 0.50)]
    chosen = choose_pool(pool)
    assert len(chosen) == 1 and chosen[0].match_id == 10 and chosen[0].selection == "OVER"
    assert chosen[0].extra["p_adj"] == probability_for_leg(chosen[0])


def test_exact_three_or_four_goals_from_poisson():
    p = _probs(1.35, 1.25, 0.45, None)["G34"]
    assert 0.30 < p < 0.46
    base = {"hthg": 1, "htag": 1, "hc": 0, "ac": 0}
    assert _won("G34", {**base, "fthg": 2, "ftag": 1})
    assert not _won("G34", {**base, "fthg": 2, "ftag": 0})
    assert not _won("G34", {**base, "fthg": 3, "ftag": 2})
