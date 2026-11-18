import sqlite3
from datetime import datetime, timezone

from betpredict.builder import rec_monitor as RM
from betpredict.store import db as DB


def test_settle_recommended_markets():
    assert RM.settle("A doua repriză - Interval goluri", "1-3", 2, 1, 1, 0) is True
    assert RM.settle("A doua repriză - Interval goluri", "1-3", 1, 0, 1, 0) is False
    assert RM.settle("Prima repriză - Total goluri", "Sub 1.5", 3, 0, 1, 0) is True
    assert RM.settle("Ambele echipe marchează (GG)", "Da", 1, 1, 0, 0) is True
    assert RM.settle("Final", "2", 0, 1, 0, 0) is True
    assert RM.settle("Peste 0.5 goluri; Peste 7.5 cornere", "x", 1, 0, 0, 0, 5, 3) is True
    assert RM.settle("Peste 0.5 goluri; Peste 7.5 cornere", "x", 0, 0, 0, 0, 5, 5) is False


def test_losing_market_is_switched_off():
    c = sqlite3.connect(":memory:"); DB.init_db(c)
    c.execute("CREATE TABLE IF NOT EXISTS sb_offer_close (match_id INTEGER, market_name TEXT, outcome TEXT, line TEXT, price REAL, observed_at TEXT)")
    rec = {("Ambele echipe marchează (GG)", "Da"): ("btts", "YES", 1.5, 2.1, 0.0)}
    for i in range(1, 201):  # GG la 1.80, intră doar 40%: ROI −28%
        gg = i % 5 < 2
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, ft_home, ft_away, ht_home, ht_away) "
                  "VALUES (?, '2026-11-15T18:00:00Z', 'h', 'a', 'finished', ?, ?, 0, 0)", (i, 1, 1 if gg else 0))
        c.execute("INSERT INTO sb_offer_close (match_id, market_name, outcome, line, price, observed_at) VALUES (?,?,?,?,?,?)",
                  (i, "Ambele echipe marchează (GG)", "Da", None, 1.8, "2026-11-15T17:59:00Z"))
    st = RM.market_stats(c, rec, (1.4, 1.6), datetime(2026, 11, 18, tzinfo=timezone.utc))
    b = st[("Ambele echipe marchează (GG)", "Da")]
    assert b["n"] == 200 and b["off"] and b["roi"] < -0.2
