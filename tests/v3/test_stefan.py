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


def test_share_link_ingest_and_bb_goals():
    import base64

    from betpredict.experimental import stefan_links as L

    c = _db()
    c.execute("ALTER TABLE match ADD COLUMN ht_home INT")
    c.execute("ALTER TABLE match ADD COLUMN ht_away INT")
    c.execute("UPDATE match SET ht_home=1, ht_away=0 WHERE id=1")  # 1-3, gol în R1 → câștigat
    c.execute("UPDATE match SET ht_home=0, ht_away=0 WHERE id=2")  # 0-0 la pauză → pierdut
    sub = base64.b64encode(json.dumps({"ticket_id": "8939-BBNST0", "user_name": "Stefan M."}).encode()).decode()
    html = '<a href="x?deep_link_sub1\\u003D' + sub.replace("=", "%3D") + '\\u0026pid=a">'
    t = {"ticket": {"status": 1, "coefficient": 3.1, "number_of_selections": 3, "win_count": 1, "lost_count": 1, "active_count": 1,
                    "selections": [{"team1_name": "Randers", "team2_name": "Brondby", "market_name": "Bet Builder", "odd_name": "Peste 0.5;Peste 1.5", "odd_coefficient": 1.4},
                                   {"team1_name": "Servette", "team2_name": "Vaduz", "market_name": "Bet Builder", "odd_name": "Peste 0.5;Peste 1.5", "odd_coefficient": 1.45},
                                   {"team1_name": "Liverpool", "team2_name": "Brighton", "market_name": "Bet Builder", "odd_name": "Peste 0.5;Peste 1.5", "odd_coefficient": 1.5}]},
         "user": {"username": "Stefan M."}}
    calls = []

    def fetch(url):
        calls.append(url)
        return html.encode() if "onelink" in url else json.dumps(t).encode()

    from datetime import datetime, timezone
    now = datetime(2026, 10, 24, 9, tzinfo=timezone.utc)
    link = "https://superbet.onelink.me/8IRb/abc"
    assert L.sync(c, [link], fetch, now) == {"calls": 2, "new": 1, "updated": 1}
    assert L.sync(c, [link], fetch, now)["calls"] == 1  # linkul nu se mai rezolvă; doar biletul activ
    t["ticket"]["status"] = 3
    L.sync(c, [link], fetch, now)
    assert L.sync(c, [link], fetch, now)["calls"] == 0  # decontat: nu mai cerem nimic
    r = stefan.report(c, {"tickets": []})
    tk = r["tickets"][0]
    assert tk["id"] == "sb-8939-BBNST0" and tk["status"] == "lost" and tk["sb"]["lost_count"] == 1
    res = [l["result"] for l in tk["legs"]]
    assert res == ["won", "lost", "pending"] and tk["legs"][0]["label"] == "Gol R1 + Peste 1.5 (BB)"
    p = tk["legs"][2]["model_p"]  # λ=3.0 → R1 1.35: 1−e^−1.35 − 1.35·e^−3
    assert abs(p - (1 - 2.718281828 ** -1.35 - 1.35 * 2.718281828 ** -3.0)) < 2e-3
