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
