import sqlite3

from betpredict.experimental import track


def test_superbet_price_requires_exact_market_selection_and_fresh_timestamp():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sb_offer (match_id INTEGER, market_name TEXT, outcome TEXT, price REAL, observed_at TEXT)")
    conn.execute("INSERT INTO sb_offer VALUES (1, 'Prima repriză - Total goluri', 'Peste 0.5', 1.55, '2026-11-02T10:00:00Z')")
    now = "2026-11-02T12:00:00Z"

    assert track._superbet_price(conn, 1, "h1", 0.5, "OVER", now) == (1.55, "2026-11-02T10:00:00Z")
    assert track._superbet_price(conn, 1, "h1", 1.5, "OVER", now) == (None, None)
    assert track._superbet_price(conn, 1, "h1", 0.5, "UNDER", now) == (None, None)
    assert track._superbet_price(conn, 1, "cards", 0.5, "OVER", now) == (None, None)
    assert track._superbet_price(conn, 1, "h1", 0.5, "OVER", "2026-11-02T17:00:01Z") == (None, None)


def test_paper_stats_use_only_settled_rows_with_saved_superbet_odds():
    conn = sqlite3.connect(":memory:")
    track.ensure(conn)
    conn.executemany(
        "INSERT INTO exp_prediction (match_id, market, line, selection, p, created_at, result, odds) VALUES (?,?,?,?,?,?,?,?)",
        [
            (1, "corners", 8.5, "OVER", 0.6, "2026-11-01T00:00:00Z", "won", 2.0),
            (2, "corners", 8.5, "OVER", 0.6, "2026-11-01T00:00:00Z", "lost", 2.0),
            (3, "corners", 8.5, "OVER", 0.6, "2026-11-01T00:00:00Z", "won", None),
            (4, "corners", 8.5, "OVER", 0.6, "2026-11-01T00:00:00Z", None, 2.0),
        ],
    )
    conn.row_factory = sqlite3.Row

    s = track.stats(conn)["corners_8.5_over"]
    assert s["n"] == 3
    assert s["won"] == 2
    assert s["lost"] == 1
    assert s["n_with_superbet_odds"] == 2
    # (2.0 - 1) + (-1) = 0 profit across two equal paper stakes.
    assert s["paper_roi"] == 0.0
    assert s["ticket_eligible"] is False


def test_new_goal_markets_are_probabilities_and_half_outcomes_sum_to_one():
    p = track.match_probs(1.35, 0.95, 0.44, {}, {}, None, 10.0, 4.0)
    assert p[("team_home", 2.5, "OVER")][0] > 0
    assert p[("goals_range", 2.0, "RANGE:4")][0] > 0
    for market in ("h1_result", "h2_result", "half_most_goals"):
        assert abs(sum(v[0] for (m, _, _), v in p.items() if m == market) - 1) < 1e-9


def test_corner_ht_and_interval_markets_are_generated_and_settle_only_from_ht_data():
    team = {"nc": 12, "cf": 5.4, "ca": 4.8}
    p = track.match_probs(1.2, 0.9, 0.44, team, team, None, 10.0, 4.0)
    assert ("ht_corners", 3.5, "OVER") in p
    assert ("corners_range", 9.0, "RANGE:11") in p
    assert ("ht_corners_range", 5.0, "RANGE:6") in p


def test_superbet_price_matches_dynamic_teams_and_interval_outcomes_exactly():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sb_offer (match_id INTEGER, market_name TEXT, outcome TEXT, price REAL, observed_at TEXT)")
    ts = "2026-11-02T10:00:00Z"
    conn.executemany("INSERT INTO sb_offer VALUES (1,?,?,?,?)", [
        ("Total goluri Gazdele FC", "Peste 2.5", 2.1, ts),
        ("Prima repriză - Interval cornere", "5-6", 3.3, ts),
        ("Prima repriză - 1X2", "Oaspeții United", 2.8, ts),
        ("Interval goluri", "2-4", 1.8, ts),
    ])
    now = "2026-11-02T12:00:00Z"
    assert track._superbet_price(conn, 1, "team_home", 2.5, "OVER", now, "Gazdele FC", "Oaspeții United")[0] == 2.1
    assert track._superbet_price(conn, 1, "ht_corners_range", 5, "RANGE:6", now)[0] == 3.3
    assert track._superbet_price(conn, 1, "h1_result", 0, "AWAY", now, "Gazdele FC", "Oaspeții United")[0] == 2.8
    assert track._superbet_price(conn, 1, "goals_range", 2, "RANGE:4", now)[0] == 1.8


def test_offer_identity_matches_interval_and_corners():
    assert track._offer_identity("goals_range", 1, "RANGE:2") == ("Interval goluri", "1-2")
    assert track._offer_identity("goals_range", 1, "RANGE:3") == ("Interval goluri", "1-3")
    assert track._offer_identity("corners", 7.5, "OVER") == ("Total cornere", "Peste 7.5")
    assert track._offer_identity("cards", 3.5, "OVER") == (None, None)


def test_publish_attaches_superbet_pick_without_making_it_a_ticket():
    import json
    import tempfile
    from datetime import date
    from pathlib import Path

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    track.ensure(conn)
    conn.execute("CREATE TABLE match (id INTEGER PRIMARY KEY, home_name TEXT, away_name TEXT, kickoff_utc TEXT)")
    conn.execute("INSERT INTO match VALUES (7, 'Belarus', 'Albania', '2026-11-15T17:00:00Z')")
    conn.execute("CREATE TABLE ext_event (match_id INTEGER, source TEXT, ext_id TEXT)")
    conn.execute("INSERT INTO ext_event VALUES (7, 'superbet', '9988')")
    conn.execute("CREATE TABLE sb_offer (match_id INTEGER, market_name TEXT, outcome TEXT, price REAL, observed_at TEXT, ref TEXT)")
    conn.execute("INSERT INTO sb_offer VALUES (7, 'Interval goluri', '1-2', 1.83, '2026-11-15T12:00:00Z', '11,1.5,abc')")
    conn.execute(
        "INSERT INTO exp_prediction (match_id, market, line, selection, p, day, created_at, odds, odds_observed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (7, "goals_range", 1, "RANGE:2", 0.57, "2026-11-15", "2026-11-15T10:00:00Z", 1.83, "2026-11-15T12:00:00Z"))
    conn.execute(
        "INSERT INTO exp_prediction (match_id, market, line, selection, p, day, created_at, odds) VALUES (?,?,?,?,?,?,?,?)",
        (7, "corners", 7.5, "OVER", 0.5, "2026-11-15", "2026-11-15T10:00:00Z", None))
    with tempfile.TemporaryDirectory() as td:
        track.publish(conn, Path(td), [date(2026, 11, 15)])
        doc = json.loads((Path(td) / "api" / "experimental" / "2026-11-15.json").read_text())
    assert doc["recommended"] is False
    assert "nu sunt recomandări" in doc["note"]
    m = doc["matches"][0]
    assert m["superbet_event_id"] == "9988"
    assert m["superbet_url"].endswith("-9988")
    priced = next(x for x in m["markets"] if x["market"] == "goals_range")
    assert priced["sb_pick"] == {"market": "Interval goluri", "outcome": "1-2", "ref": "11,1.5,abc"}
    bare = next(x for x in m["markets"] if x["market"] == "corners")
    assert "sb_pick" not in bare


def test_settle_categorical_and_interval_markets_from_final_match_data():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE match (
        id INTEGER PRIMARY KEY, status TEXT, ft_home INTEGER, ft_away INTEGER, ht_home INTEGER, ht_away INTEGER,
        corners_home INTEGER, corners_away INTEGER, corners_ht_home INTEGER, corners_ht_away INTEGER,
        cards_home INTEGER, cards_away INTEGER)""")
    track.ensure(conn)
    conn.execute("INSERT INTO match VALUES (1,'finished',1,1,0,0,5,4,2,4,1,2)")
    conn.executemany(
        "INSERT INTO exp_prediction (match_id,market,line,selection,p,created_at) VALUES (1,?,?,?,?,?)",
        [("h1_result", 0, "DRAW", 0.4, "2026-11-01T00:00:00Z"),
         ("goals_range", 1, "RANGE:2", 0.4, "2026-11-01T00:00:00Z"),
         ("ht_corners_range", 5, "RANGE:6", 0.4, "2026-11-01T00:00:00Z"),
         ("corners_range", 9, "RANGE:11", 0.4, "2026-11-01T00:00:00Z")],
    )

    assert track.settle(conn)["settled"] == 4
    got = {r["market"]: r["result"] for r in conn.execute("SELECT market,result FROM exp_prediction")}
    assert got == {"h1_result": "won", "goals_range": "won", "ht_corners_range": "won", "corners_range": "won"}
