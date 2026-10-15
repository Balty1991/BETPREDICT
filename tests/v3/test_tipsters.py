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
