import sqlite3

from betpredict.builder import market_settle as MS
from betpredict.store import db as DB

M = {"fh": 2, "fa": 1, "hh": 1, "ha": 0, "ch": 6, "ca": 3, "chh": 2, "cha": 1, "kh": None, "ka": None}


def test_general_markets_settle_from_score_and_corners():
    assert MS.result("Total goluri", "Peste 2.5", M) == "won"
    assert MS.result("A doua repriză - Marchează {H}", "Da", M) == "won"
    assert MS.result("Total goluri {A}", "Sub 1.5", M) == "won"
    assert MS.result("Handicap asiatic", "{H} (-1)", M) == "void"
    assert MS.result("Total cornere", "Peste 9.5", M) == "lost"
    assert MS.result("Piață necunoscută", "x", M) is None


def test_teams_canon_and_key_roundtrip():
    prices = {("Final", "1"): 1.6, ("Final", "2"): 5.0, (MS.DNB, "Steaua"): 1.25, (MS.DNB, "Dinamo"): 3.8}
    t = MS.teams(prices)
    assert t == ("Steaua", "Dinamo")
    key = MS.key_of(MS.canon("Total goluri Steaua", t), "Peste 1.5")
    assert key == "SB:Total goluri {H}|Peste 1.5"
    assert MS.label(key) == "Total goluri Gazde: Peste 1.5"


def test_sb_ticket_legs_settle():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, ft_home, ft_away, ht_home, ht_away) "
              "VALUES (1,'2026-11-20T18:00:00Z','a','b','finished',2,1,1,0)")
    c.execute("INSERT INTO ticket (id, kind, variant, created_by, status, created_at, day) VALUES (1,'acca_super','s10','robot','pending','x','2026-11-20')")
    c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds) VALUES (1,1,'sb|0','SB:A doua repriză - Marchează {H}|Da',1.5)")
    assert MS.settle_sb_legs(c) == 1
    assert c.execute("SELECT result FROM ticket_leg").fetchone()[0] == "won"
