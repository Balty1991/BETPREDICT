import json
import sqlite3
from pathlib import Path

from betpredict.experimental import stefan


def _db():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE match (id INTEGER PRIMARY KEY, kickoff_utc TEXT, home_name TEXT, away_name TEXT, ft_home INT, ft_away INT,
                 corners_home INT, corners_away INT, corners_ht_home INT, corners_ht_away INT)""")
    c.execute("CREATE TABLE ss_track (match_id INT, mkey TEXT, p REAL, odds REAL, result TEXT)")
    c.execute("CREATE TABLE match_model (match_id INT, lambda_home REAL, lambda_away REAL, updated_at TEXT)")
    c.executemany("INSERT INTO match VALUES (?,?,?,?,?,?,?,?,?,?)", [
        (1, "2026-10-23T17:00:00Z", "Randers FC", "Brøndby IF", 1, 3, 6, 6, 2, 3),
        (2, "2026-10-24T16:00:00Z", "Servette FC", "FC Vaduz", 2, 1, 6, 2, 0, 1),
        (3, "2026-10-25T14:00:00Z", "Liverpool FC", "Brighton & Hove Albion", None, None, None, None, None, None),
    ])
    c.executemany("INSERT INTO ss_track VALUES (?,?,?,?,?)", [(1, "H1C25", 0.84, 1.14, "won"), (1, "H1U65", 0.77, 1.25, "won")])
    c.execute("INSERT INTO match_model VALUES (3, 1.6, 1.4, '2026-10-25')")
    return c


DOC = {"tickets": [
    {"id": "a", "posted": "2026-10-24", "status_shown": "won", "total_odds": 67.86,
     "legs": [{"home": "Randers FC", "away": "Brondby", "market": "H1C_3_6", "odds": 1.55, "kickoff": None, "result_shown": "won"},
              {"home": "Hajduk Split", "away": "Ajax", "market": "NEXT10_C05", "odds": 1.68, "kickoff": None, "result_shown": "won"}]},
    {"id": "b", "posted": "2026-10-24", "status_shown": "pending", "total_odds": 150.0,
     "legs": [{"home": "Servette", "away": "Vaduz", "market": "EACH_C3", "odds": 1.30, "kickoff": None, "result_shown": "won"},
              {"home": "Liverpool", "away": "Brighton", "market": "G14", "odds": 1.30, "kickoff": None, "result_shown": None}]},
]}


def test_settle_and_compare():
    r = stefan.report(_db(), DOC)
    legs = {l["market"]: l for t in r["tickets"] for l in t["legs"]}
    assert legs["H1C_3_6"]["result"] == "won" and legs["H1C_3_6"]["match_id"] == 1
    assert abs(legs["H1C_3_6"]["model_p"] - 0.61) < 1e-6
    assert legs["NEXT10_C05"]["result"] == "nesettlabil"
    assert legs["EACH_C3"]["result"] == "lost"  # Vaduz doar 2 cornere
    assert legs["G14"]["result"] == "pending" and legs["G14"]["model_p"] is not None
    s = r["summary"]
    assert (s["legs"], s["legs_settled"], s["legs_won"], s["unsettlable"]) == (4, 2, 1, 1)
    assert r["tickets"][1]["status"] == "lost"  # o selecție vizibilă pierdută
    assert r["data_check"]["mismatches"][0]["market"] == "EACH_C3"


def test_committed_file_is_valid():
    d = json.loads((Path(stefan.__file__).resolve().parents[2] / "data" / "stefan_tickets.json").read_text(encoding="utf-8"))
    for t in d["tickets"]:
        for l in t["legs"]:
            assert l["market"] in stefan.LABELS and l["home"] and l["away"]
            assert l["odds"] is None or l["odds"] > 1
