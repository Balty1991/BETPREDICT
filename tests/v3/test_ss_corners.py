import sqlite3
from datetime import datetime, timezone

from betpredict.experimental import supersocial as S
from betpredict.experimental.corners import CornerModel, nb_cdf, p_between
from betpredict.ingest import corners as C
from betpredict.store import db as DB


def _db():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c); C.ensure(c)
    return c


def test_parse_stats():
    js = {"stats": {"home": {"corner_kicks": 6}, "away": {"corner_kicks": 3},
                    "first_half": {"home": {"corner_kicks": 4}, "away": {"corner_kicks": 1}}}}
    assert C.parse(js) == (6, 3, 4, 1)
    assert C.parse({"stats": {"home": {}, "away": {}}}) is None


def test_nb_and_model():
    assert abs(nb_cdf(60, 9.8, 60) - 1) < 1e-9
    assert 0.80 < p_between(7, None, 9.8, 60) < 0.86  # O6.5 la media 9.8 ≈ 83%
    c = _db()
    for i in range(30):
        c.execute("INSERT INTO match (id, league_id, home_id, away_id, kickoff_utc, status, corners_home, corners_away, corners_ht_home, corners_ht_away) "
                  "VALUES (?,1,?,?,?, 'finished', 6, 4, 3, 2)", (i + 1, 10 + i % 4, 20 + i % 3, f"2026-09-{1 + i % 28:02d}T12:00:00Z"))
    m = CornerModel(c)
    mean, src = m.mean(1, 10, 20)
    assert src == "liga+echipe" and 9.0 < mean < 11.0
    p = m.probs(mean)
    assert p["C65"] > p["C75"] > p["C85"] and p["H1C25"] > p["H1C35"] and p["BB_C65_U145"] < p["C65"]


def test_won_and_corner_settlement():
    r = {"fthg": 2, "ftag": 1, "hthg": 1, "htag": 0, "hc": 5, "ac": 3, "hc1": 2, "ac1": 1}
    assert S.won("C75", r) and not S.won("C85", r) and S.won("H1C25", r) and not S.won("H1C35", r) and S.won("H13x2", r)
    c = _db()
    c.execute("INSERT INTO match (id, kickoff_utc, status, ft_home, ft_away, ht_home, ht_away, corners_home, corners_away, corners_ht_home, corners_ht_away) "
              "VALUES (1,'2026-10-11T12:00:00Z','finished',2,1,1,0,5,3,2,1)")
    c.execute("INSERT INTO match (id, kickoff_utc, status, ft_home, ft_away, ht_home, ht_away) VALUES (2,'2026-01-01T12:00:00Z','finished',1,1,0,1)")
    c.execute("INSERT INTO ticket (id, kind, variant, created_by, total_odds, stake, status, created_at, day) VALUES (1,'acca_stil','stil_supersocial','robot',2,0.05,'pending','x','2026-10-11')")
    for mid, sel in ((1, "C75"), (1, "H1C35"), (2, "C65")):
        c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds) VALUES (1,?, 'ss|0', ?, 1.25)", (mid, sel))
    S.settle_legs(c)
    res = {r[0]: r[1] for r in c.execute("SELECT selection, result FROM ticket_leg")}
    assert res == {"C75": "won", "H1C35": "lost", "C65": "void"}
    r2 = {"fthg": 2, "ftag": 1, "hthg": 1, "htag": 0, "hc": 10, "ac": 6, "hc1": 5, "ac1": 2}
    assert S.won("BB_C65_U145", r) and not S.won("BB_C65_U145", r2)
    assert S.won("BB_H1C25_U65", r) and not S.won("BB_H1C25_U65", r2)
    assert S.won("BB_H13x2_O15", r)
    assert S._bb_price("BB_C65_U145", {"C65": 0.80, "BB_C65_U145": 0.74}, {"C65": 1.26}) == 1.36


def test_h1_share_global_corners_and_real_interval_names():
    c = _db()
    assert abs(S.h1_shares(c)[None] - 0.446) < 1e-9
    mean, src = CornerModel(c).mean(1, 10, 20)
    assert src == "global" and mean == 9.8
    assert S.MARKETS[("Prima repriză - Interval cornere", "<5")] == "H1CLT5"
    assert S.MARKETS[("Prima repriză - Interval cornere", "5-6")] == "H1C56"
    assert S.MARKETS[("Prima repriză - Interval cornere", "7+")] == "H1C7P"
    assert S.MARKETS[("Prima repriză - Total cornere", "Sub 6.5")] == "H1U65"
    assert "H1CLT5" in S.GROUP and S.GROUP["H1C56"] == "r1_cornere"
