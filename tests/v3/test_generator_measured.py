"""Generatorul publică combinația măsurată (peste 0,5 goluri + peste 7,5 cornere), nu alte Bet Builder-e."""
import json
import sqlite3
from datetime import datetime, timezone

from betpredict.experimental import supersocial as SS
from betpredict.store import db as DB


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    DB.init_db(c)
    return c


def _bb(c, mid, label, price, p, kickoff):
    c.execute(
        "INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?,?,?,?,?)",
        (mid, kickoff, f"H{mid}", f"A{mid}", "notstarted"))
    legs = json.dumps({"superbet": {"market": "Bet Builder", "outcome": label}, "legs": ["ft_over_0.5", "corners_over_7.5"]})
    c.execute(
        """INSERT INTO bb_suggestion (match_id, day, legs_json, label, p_joint, fair_odds, min_odds, sb_price, ev, source, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (mid, "2026-11-16", legs, label, p, round(1 / p, 2), round(1.07 / p, 2), price, p * price - 1, "superbet", "2026-11-15T10:00:00Z"))


def test_generator_doc_keeps_only_the_measured_builder():
    c = _db()
    kick = "2026-11-16T18:00:00Z"
    _bb(c, 1, "Peste 0.5 goluri; Peste 7.5 cornere", 1.45, 0.62, kick)
    _bb(c, 2, "Peste 0.5 goluri; Peste 8.5 cornere", 1.80, 0.70, kick)
    _bb(c, 3, "Peste 1.5 goluri; Peste 7.5 cornere", 1.90, 0.55, kick)
    now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    rows = SS.measured_builder_rows(c, now)
    assert [r["m"] for r in rows] == [1]
    assert rows[0]["o"] == 1.45 and rows[0]["p"] == 0.62
    assert rows[0]["k"] == SS.MEASURED_KEY
    assert rows[0]["pk"]["market"] == "Bet Builder"
    assert "7.5 cornere" in rows[0]["pk"]["outcome"]
    assert SS.label(SS.MEASURED_KEY).startswith("Peste 0,5")
    assert SS.short_bb_label("Peste 0.5 goluri; Peste 7.5 cornere", "Peste 0.5 goluri; Peste 7.5 cornere") == "Peste 0,5 goluri + Peste 7,5 cornere"
    assert SS.short_bb_label("Total goluri", "Peste 1.5") == "Total goluri: Peste 1.5"
    assert SS._is_measured_combo("Peste 0,5 goluri; Peste 7,5 cornere")
    assert not SS._is_measured_combo("Peste 1.5 goluri; Peste 7.5 cornere")
    assert not SS._is_measured_combo("Peste 0.5 goluri; Peste 17.5 cornere")


def test_measured_board_is_the_small_feed():
    c = _db()
    kick = "2026-11-16T18:00:00Z"
    _bb(c, 1, "Peste 0.5 goluri; Peste 7.5 cornere", 1.45, 0.62, kick)
    _bb(c, 2, "Peste 0.5 goluri; Peste 8.5 cornere", 1.80, 0.70, kick)
    c.execute("INSERT INTO ext_event (match_id, source, ext_id) VALUES (1, 'superbet', '99')")
    now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    doc = SS.measured_board(c, now)
    assert [r["match_id"] for r in doc["rows"]] == [1]
    assert doc["rows"][0]["home"] == "H1" and doc["rows"][0]["odds"] == 1.45
    assert doc["rows"][0]["superbet_event_id"] == "99"
    assert doc["rows"][0]["superbet_url"].endswith("-99")
    assert "7.5" in doc["rows"][0]["pk"]["outcome"]


def _offer(c, mid, name, price, kick):
    c.execute(
        "INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?,?,?,?,?)",
        (mid, kick, f"H{mid}", f"A{mid}", "notstarted"))
    c.execute(
        "INSERT INTO sb_offer (match_id, market_name, outcome, price, observed_at) VALUES (?,?,?,?,?)",
        (mid, name, name, price, "2026-11-15T10:00:00Z"))


def test_corner_goal_rows_keep_65_and_85_only():
    c = _db()
    kick = "2026-11-16T18:00:00Z"
    _offer(c, 1, "Peste 0.5 goluri; Peste 6.5 cornere", 1.33, kick)
    _offer(c, 2, "Peste 0.5 goluri; Peste 8.5 cornere", 1.55, kick)
    _offer(c, 3, "Peste 0.5 goluri; Peste 7.5 cornere", 1.45, kick)
    _offer(c, 4, "Peste 0.5 goluri; Peste 6.5 cornere; Peste 3.5 cartonașe", 1.90, kick)
    _offer(c, 5, "Peste 1.5 goluri; Peste 6.5 cornere", 1.48, kick)
    _offer(c, 6, "Peste 1.5 goluri; Peste 7.5 cornere", 1.68, kick)
    _offer(c, 7, "Peste 1.5 goluri; Peste 8.5 cornere", 1.96, kick)
    _offer(c, 8, "Fiecare echipă va avea peste 2.5 cornere; Peste 1.5 goluri", 2.10, kick)
    now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    rows = {(r["k"], r["m"]): r for r in SS.corner_goal_rows(c, now)}
    assert set(rows) == {
        ("BB_G05_C65", 1), ("BB_G05_C85", 2),
        ("BB_G15_C65", 5), ("BB_G15_C75", 6), ("BB_G15_C85", 7),
    }
    assert rows[("BB_G05_C65", 1)]["o"] == 1.33
    assert rows[("BB_G05_C65", 1)]["p"] == round(1 / 1.33, 4)
    assert rows[("BB_G15_C75", 6)]["o"] == 1.68
    assert SS.label("BB_G05_C65").endswith("6,5 cornere")
    assert SS.label("BB_G05_C85").endswith("8,5 cornere")
    assert SS.label("BB_G15_C65").startswith("Peste 1,5")
    assert SS.label("BB_G15_C85").endswith("8,5 cornere")


def test_corner_ticket_settles_from_the_score_when_the_builder_row_is_missing():
    from betpredict.builder.corner_tickets import settle_legs

    c = _db()
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, ft_home, ft_away, corners_home, corners_away) VALUES (1,'2026-11-15T16:30:00Z','Ravenna','Forli','finished',2,0,8,7)")
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, ft_home, ft_away, corners_home, corners_away) VALUES (2,'2026-11-15T17:30:00Z','Eibar','Cadiz','finished',1,1,3,3)")
    c.execute("INSERT INTO ticket (id, kind, variant, created_by, total_odds, stake, status, created_at, day) VALUES (9,'pyramid','p120','robot',1.96,50,'pending','x','2026-11-15')")
    sel = "Peste 0.5 goluri; Peste 7.5 cornere|Peste 0.5 goluri; Peste 7.5 cornere"
    c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds) VALUES (9,1,'bb',?,1.40)", (sel,))
    c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds) VALUES (9,2,'bb',?,1.40)", (sel,))
    assert settle_legs(c) == 2
    got = {r[0]: r[1] for r in c.execute("SELECT match_id, result FROM ticket_leg WHERE ticket_id=9")}
    assert got == {1: "won", 2: "lost"}
