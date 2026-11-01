import math
import sqlite3
from datetime import datetime, timezone

from betpredict.builder.bb_corr import correlated_chance, fair_odds, joint_p, log_vs_superbet, pair_lift
from betpredict.settle import settle_tickets
from betpredict.builder.calea100 import superbonus
from betpredict.builder.high_odds import (build_lung, build_short, build_superbonus, market_ev, near_fair,
                                          shrunk_roi, ticket_view)
from betpredict.builder.pool import Cand
from betpredict.publish.outputs import ticket_fingerprint
from betpredict.settle import flag_stale_tickets, leg_result_from_match


def _c(i, odds, p, market="1x2", selection="HOME", *, drift=None, p_market=None):
    fair = p_market if p_market is not None else min(0.97, (1 / odds) / 1.05)
    return Cand(i, 1000 + i, i, "L", "2026-11-01T16:00:00Z", "A", "B", market, 0.0, selection,
                odds, p, p * odds - 1, "A", 70, True, p_market=fair, odds_source="superbet", drift=drift)


def test_superbonus_grid_matches_superbet():
    assert [superbonus(n) for n in range(3, 11)] == [0.03, 0.04, 0.06, 0.08, 0.10, 0.15, 0.20, 0.25]
    assert superbonus(11) == 0.30
    assert superbonus(25) == 1.0
    assert superbonus(2) == 0.0


def test_near_fair_keeps_the_research_markets_and_drops_the_avoid_list():
    assert near_fair("R1R2") and near_fair("BB_HG14_U45") and near_fair("YCU45") and near_fair("YCU55")
    assert not near_fair("AO15") and not near_fair("H1O15") and not near_fair("H1C56") and not near_fair("H1C7P")
    assert not near_fair("HTFT_1X")
    assert shrunk_roi(0.021, 400) >= -0.025
    assert shrunk_roi(-0.20, 20) < -0.025


def test_short_50_uses_four_or_five_legs_between_2_and_2_9_and_skips_drift():
    pool = [_c(i, 2.2, 0.42) for i in range(6)] + [_c(20, 2.4, 0.40, drift=0.05)]
    legs = build_short(pool, 50)
    assert legs and 4 <= len(legs) <= 5
    odds = math.prod(c.odds for c in legs)
    assert 50 <= odds < 100
    assert all(c.drift is None for c in legs)
    assert len({c.match_id for c in legs}) == len(legs)


def test_market_ev_includes_superbonus_not_a_model_edge():
    legs = [_c(i, 1.45, 0.9, market="ss", selection="R1R2") for i in range(1, 11)]
    for c in legs:
        c.p_market = 0.66
    view = ticket_view(legs)
    bonus = superbonus(10)
    assert bonus == 0.25
    assert abs(view["ev"] - market_ev(view["p_market"], view["total"], bonus)) < 1e-3
    assert view["one_in_n"] >= 1
    assert view["weakest"]["match_id"]


def test_lung_needs_twenty_near_fair_legs():
    pool = [_c(i, 1.22, 0.78, market="ss", selection="H2G13") for i in range(24)]
    for c in pool:
        c.p_market = 0.78
    legs = build_lung(pool, 100)
    assert legs and 20 <= len(legs) <= 30
    assert math.prod(c.odds for c in legs) >= 100


def test_fingerprint_is_stable_for_the_same_legs():
    a = {"kind": "acca_50", "variant": "scurt", "legs": [
        {"match_id": 2, "market": "1x2", "line": 0, "selection": "HOME"},
        {"match_id": 1, "market": "btts", "line": None, "selection": "NO"},
    ]}
    b = {"kind": "acca_50", "variant": "scurt", "status": "pending", "legs": list(reversed(a["legs"]))}
    assert ticket_fingerprint(a) == ticket_fingerprint(b)


def test_score_settles_a_leg_without_prediction_when_the_kickoff_is_old():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT 'scheduled' AS status, 3 AS ft_home, 1 AS ft_away, NULL AS ht_home, NULL AS ht_away, "
                       "NULL AS raw_json, '2026-10-27T19:45:00Z' AS kickoff_utc").fetchone()
    assert leg_result_from_match("over_under|2.5", "UNDER", row) == "lost"
    assert leg_result_from_match("btts|0", "NO", row) == "lost"


def test_stale_pending_ticket_is_flagged_with_a_reason():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE ticket (id INTEGER PRIMARY KEY, status TEXT, notes TEXT);
        CREATE TABLE ticket_leg (ticket_id INTEGER, market TEXT, selection TEXT, result TEXT, prediction_id INTEGER, match_id INTEGER);
        CREATE TABLE match (id INTEGER PRIMARY KEY, status TEXT, ft_home INTEGER, kickoff_utc TEXT);
        INSERT INTO ticket VALUES (2291, 'pending', '{}');
        INSERT INTO match VALUES (1, 'finished', 3, '2026-10-27T19:45:00Z');
        INSERT INTO ticket_leg VALUES (2291, 'over_under|2.5', 'UNDER', NULL, NULL, 1);
    """)
    n = flag_stale_tickets(conn, hours=4)
    assert n == 1
    notes = conn.execute("SELECT notes FROM ticket WHERE id=2291").fetchone()[0]
    assert "scor prezent" in notes or "over_under" in notes


def test_same_match_legs_use_lift_or_refuse_independence():
    home = {"match_id": 1, "market": "1x2", "selection": "HOME", "line": 0, "p": 0.6}
    over = {"match_id": 1, "market": "team_total_home", "selection": "OVER", "line": 1.5, "p": 0.7}
    assert pair_lift(home, over) == 1.66
    got = correlated_chance([home, over])
    assert got["unknown"] is False and abs(got["p"] - min(0.99, 0.6 * 0.7 * 1.66)) < 1e-6
    cards = {"match_id": 1, "market": "ss", "selection": "YCU55", "line": 0, "p": 0.8}
    unknown = correlated_chance([home, cards])
    assert unknown["unknown"] is True and unknown["p"] is None and unknown["correlated"] is True
    other = {"match_id": 2, "market": "btts", "selection": "NO", "line": 0, "p": 0.5}
    indep = correlated_chance([home, other])
    assert indep["unknown"] is False and abs(indep["p"] - 0.3) < 1e-9


def test_two_legs_on_one_match_settle_on_their_own():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE prediction (id INTEGER PRIMARY KEY, result TEXT);
        CREATE TABLE ticket (id INTEGER PRIMARY KEY, kind TEXT, total_odds REAL, stake REAL, notes TEXT, status TEXT, payout REAL, settled_at TEXT);
        CREATE TABLE ticket_leg (ticket_id INTEGER, market TEXT, selection TEXT, odds REAL, result TEXT, prediction_id INTEGER, match_id INTEGER);
        CREATE TABLE match (id INTEGER PRIMARY KEY, status TEXT, ft_home INTEGER, ft_away INTEGER, ht_home INTEGER, ht_away INTEGER,
                            home_name TEXT, away_name TEXT,
                            corners_home INTEGER, corners_away INTEGER, corners_ht_home INTEGER, corners_ht_away INTEGER,
                            cards_home INTEGER, cards_away INTEGER, raw_json TEXT, kickoff_utc TEXT);
        INSERT INTO ticket VALUES (1, 'manual', 2.5, 10, '{}', 'pending', NULL, NULL);
        INSERT INTO match VALUES (9, 'finished', 2, 1, 1, 0, 'A', 'B', NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-10-27T16:00:00Z');
        INSERT INTO ticket_leg VALUES (1, 'btts|0', 'NO', 1.8, NULL, NULL, 9);
        INSERT INTO ticket_leg VALUES (1, 'over_under|1.5', 'OVER', 1.4, NULL, NULL, 9);
    """)
    settle_tickets(conn)
    rows = conn.execute("SELECT market, result FROM ticket_leg ORDER BY market").fetchall()
    assert [tuple(r) for r in rows] == [("btts|0", "lost"), ("over_under|1.5", "won")]
    assert conn.execute("SELECT status FROM ticket").fetchone()[0] == "lost"


def test_short_ticket_keeps_one_leg_per_match():
    a = _c(1, 2.2, 0.42)
    b = Cand(99, a.match_id, 1, "L", a.kickoff_utc, "A", "B", "btts", 0.0, "YES", 2.3, 0.4, -0.08, "A", 70, True,
             p_market=0.4, odds_source="superbet")
    rest = [_c(i, 2.2, 0.42) for i in range(2, 6)]
    legs = build_short([a, b, *rest], 50)
    assert legs and len({c.match_id for c in legs}) == len(legs)


def test_correlated_builder_price_is_marginals_times_lift():
    p = joint_p(0.50, 0.55, 1.66)
    assert abs(p - 0.50 * 0.55 * 1.66) < 1e-9
    fair = fair_odds(0.50, 0.55, 1.66)
    row = log_vs_superbet(0.50, 0.55, "fav_win_fav_o15", fair)
    assert row["paper"] is True and row["gap"] == 0
    assert log_vs_superbet(0.45, 0.48, "over25_gg", 3.2)["lift"] == 1.53
