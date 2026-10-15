import sqlite3
from datetime import datetime, timezone

from betpredict.store import db as DB
from betpredict.experimental import supersocial as SS
from betpredict.experimental import tipsters as T
from betpredict.ingest.corners import ensure


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    DB.init_db(c)
    ensure(c)
    return c


def test_csv_in_repo_loads():
    legs = T.load()
    assert len(legs) >= 22 and all(l["key"] in SS.LABELS for l in legs)
    assert legs[0]["kickoff"] == datetime(2026, 10, 11, 10, 15, tzinfo=timezone.utc)   # 13:15 ora României


def test_report_matches_robot_and_checks_corners():
    c = _db()
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, corners_home, corners_away) VALUES "
              "(1,'2026-10-11T10:15:00Z','FC Utrecht','Willem II Tilburg','finished',6,3)")
    SS.track(c, [{"match_id": 1, "key": "C75", "kickoff_utc": "2026-10-11T10:15:00Z", "p": 0.81, "odds": 1.27}],
             datetime(2026, 10, 11, 8, tzinfo=timezone.utc))
    k = datetime(2026, 10, 11, 10, 15, tzinfo=timezone.utc)
    legs = [{"ticket": "t1", "tipster": "x", "kickoff": k, "home": "Utrecht", "away": "Willem II", "key": "C75",
             "odds": 1.26, "result": "won", "corners": 10},
            {"ticket": "t1", "tipster": "x", "kickoff": k, "home": "Como", "away": "AS Roma", "key": "C65",
             "odds": 1.25, "result": "won", "corners": 8}]
    doc = T.report(c, legs)
    t = doc["tickets"][0]
    assert t["status"] == "won" and t["matched"] == 1 and t["robot_seen"] == 1 and t["p_robot"] is None
    assert t["legs"][0]["robot_p"] == 0.81 and t["legs"][1]["match_id"] is None
    assert doc["data_check"] == {"compared": 1, "mismatches": [{"home": "Utrecht", "away": "Willem II", "their": 10, "ours": 9}]}
    mk = {m["key"]: m for m in doc["markets"]}
    assert mk["C75"]["hit"] == 1.0 and mk["C75"]["robot_n"] == 1 and doc["summary"]["only_wins"]


def test_new_markets_and_stat_kinds():
    from betpredict.lab.patterns import _probs
    p = _probs(1.5, 1.2, 0.45, None)
    assert 0 < p["H2G13"] < 1 and abs(p["H1O05"] - (1 - __import__("math").exp(-2.7 * 0.45))) < 1e-9
    r = {"fthg": 2, "ftag": 1, "hthg": 0, "htag": 0, "hc": None, "ac": None}
    assert SS.won("H2G13", r) and not SS.won("H1O05", r) and SS.won("GGO25", r)
    assert SS.MARKETS[("A doua repriză - Interval goluri", "1-3")] == "H2G13"
    assert {"GGO25", "H1O05", "H2G13"} <= set(SS.model_p(1.5, 1.2))
    assert T.stat_kind("C65") == "cornere" and T.stat_kind("SHOTS") == "șuturi" and T.stat_kind("R1R2") is None
    doc = T.report(_db())
    assert doc["summary"]["tickets"] == 22 and doc["data_check"]["compared"] == 0
    v5 = next(t for t in doc["tickets"] if t["id"] == "2026-08-16-v5")
    assert v5["odds"] == 173.75 and v5["status"] == "won"


def test_gg_and_x2_over15_markets():
    import math
    from betpredict.lab.patterns import _probs
    lh, la = 1.4, 1.1
    p = _probs(lh, la, 0.45, None)
    pois = lambda l, k: math.exp(-l) * l ** k / math.factorial(k)
    brute = sum(pois(lh, i) * pois(la, j) for i in range(15) for j in range(15) if j >= i and i + j >= 2)
    assert abs(p["DCX2_O15"] - brute) < 1e-6
    assert abs(p["GG"] - (1 - math.exp(-lh)) * (1 - math.exp(-la))) < 1e-9
    r = {"fthg": 1, "ftag": 1, "hthg": 0, "htag": 0, "hc": None, "ac": None}
    assert SS.won("GG", r) and SS.won("DCX2_O15", r) and not SS.won("DCX2_O15", {**r, "fthg": 2})
    assert {"GG", "DCX2_O15"} <= set(SS.model_p(1.4, 1.1))
    assert SS.MARKETS[("Ambele echipe marchează (GG)", "Da")] == "GG"
    assert SS.MARKETS[("Șansă dublă & Total goluri (1.5)", "X2 & Peste 1.5")] == "DCX2_O15"
