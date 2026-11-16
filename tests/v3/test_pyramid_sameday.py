"""Piramida de cotă 2 ia doar meciuri din ziua biletului, ora României."""
import json
import sqlite3
from datetime import date, datetime, timezone

from betpredict.builder.pyramid import RULES_CORNER2, ensure_track_tables, pick_corners_2, replace_offday_corner_ticket
from betpredict.store import db as DB


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    DB.init_db(c)
    return c


def _bb(c, mid, kick, price, p, league):
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, league_id, status) VALUES (?,?,?,?,?,?)",
              (mid, kick, f"H{mid}", f"A{mid}", league, "notstarted"))
    c.execute(
        """INSERT INTO bb_suggestion (match_id, day, legs_json, label, p_joint, fair_odds, min_odds, sb_price, ev, source, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (mid, "2026-11-15", json.dumps({"superbet": {"market": "Bet Builder", "outcome": "Peste 0.5 goluri; Peste 7.5 cornere"}}),
         "Peste 0.5 goluri; Peste 7.5 cornere", p, round(1 / p, 2), 1.2, price, p * price - 1, "superbet", "2026-11-15T10:00:00Z"))


def test_pyramid_ignores_tomorrow_even_if_the_pair_is_better():
    c = _db()
    _bb(c, 1, "2026-11-15T16:30:00Z", 1.40, 0.70, 1)
    _bb(c, 2, "2026-11-15T17:30:00Z", 1.40, 0.68, 2)
    _bb(c, 3, "2026-11-16T19:45:00Z", 1.45, 0.90, 3)
    _bb(c, 4, "2026-11-16T20:15:00Z", 1.45, 0.90, 4)
    now = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc)
    res = pick_corners_2(c, now, RULES_CORNER2, date(2026, 11, 15))
    assert res["status"] == "pick"
    legs, p = res["main"]
    assert {x.match_id for x in legs} == {1, 2}
    assert "de azi" in res["reason"]
    assert round(legs[0].odds * legs[1].odds, 2) == 1.96


def test_pyramid_says_no_bet_when_only_tomorrow_fits():
    c = _db()
    _bb(c, 3, "2026-11-16T19:45:00Z", 1.45, 0.70, 3)
    _bb(c, 4, "2026-11-16T20:15:00Z", 1.45, 0.70, 4)
    now = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc)
    res = pick_corners_2(c, now, RULES_CORNER2, date(2026, 11, 15))
    assert res["status"] == "no_bet"
    assert res["main"] is None


def test_offday_ticket_is_replaced_once_and_the_step_is_removed():
    c = _db()
    ensure_track_tables(c, "pyramid120")
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (9, '2026-11-16T19:45:00Z', 'Perugia', 'Torres', 'notstarted')")
    c.execute("INSERT INTO ticket (kind, variant, created_by, status, created_at, day, total_odds) VALUES ('pyramid','p120','robot','pending','2026-11-15T13:00:00Z','2026-11-15',2.03)")
    tid = c.execute("SELECT id FROM ticket").fetchone()[0]
    c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds) VALUES (?,?,?,?,?)",
              (tid, 9, "bb", "Bet Builder|Peste 0.5 goluri; Peste 7.5 cornere", 1.40))
    c.execute("INSERT INTO pyramid120_run (start_date, start_bank, status, current_step, current_bank) VALUES ('2026-11-15',100,'active',0,100)")
    rid = c.execute("SELECT id FROM pyramid120_run").fetchone()[0]
    c.execute("INSERT INTO pyramid120_step (run_id, step_no, date, ticket_id, stake, odds, bank_before) VALUES (?,?,?,?,?,?,?)",
              (rid, 1, "2026-11-15", tid, 50, 2.03, 100))
    c.execute("INSERT INTO ingest_state (key, value) VALUES ('pyramid120.day.2026-11-15', '{}')")
    assert replace_offday_corner_ticket(c) is True
    assert c.execute("SELECT status FROM ticket WHERE id=?", (tid,)).fetchone()[0] == "replaced"
    assert c.execute("SELECT COUNT(*) FROM pyramid120_step").fetchone()[0] == 0
    assert c.execute("SELECT value FROM ingest_state WHERE key='pyramid120.day.2026-11-15'").fetchone() is None
    assert c.execute("SELECT current_bank FROM pyramid120_run WHERE id=?", (rid,)).fetchone()[0] == 100
    assert replace_offday_corner_ticket(c) is False


def test_today_waits_while_yesterday_is_unsettled():
    from betpredict.builder.pyramid import CORNER2_RESET_ID, CORNER2_SAMEDAY_ID, build_pyramid_120_day
    from betpredict.store import repo

    c = _db()
    ensure_track_tables(c, "pyramid120")
    repo.set_state(c, f"pyramid.reset.pyramid120.{CORNER2_RESET_ID}", "1")
    repo.set_state(c, f"pyramid.sameday.pyramid120.{CORNER2_SAMEDAY_ID}", "1")
    c.execute("INSERT INTO ticket (kind, variant, created_by, status, created_at, day, total_odds) VALUES ('pyramid','p120','robot','pending','2026-11-15T13:00:00Z','2026-11-15',1.96)")
    yid = c.execute("SELECT id FROM ticket").fetchone()[0]
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (1,'2026-11-15T17:30:00Z','Eibar','Cadiz','finished')")
    c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds) VALUES (?,?,?,?,?)",
              (yid, 1, "bb", "Bet Builder|Peste 0.5 goluri; Peste 7.5 cornere", 1.40))
    c.execute("INSERT INTO pyramid120_run (start_date, start_bank, status, current_step, current_bank) VALUES ('2026-11-15',100,'active',0,100)")
    rid = c.execute("SELECT id FROM pyramid120_run").fetchone()[0]
    c.execute("INSERT INTO pyramid120_step (run_id, step_no, date, ticket_id, stake, odds, bank_before) VALUES (?,?,?,?,?,?,?)",
              (rid, 1, "2026-11-15", yid, 50, 1.96, 100))
    c.execute("INSERT INTO ticket (kind, variant, created_by, status, created_at, day, total_odds) VALUES ('pyramid','p120','robot','pending','2026-11-16T04:00:00Z','2026-11-16',1.96)")
    tid = c.execute("SELECT id FROM ticket WHERE day='2026-11-16'").fetchone()[0]
    c.execute("INSERT INTO pyramid120_step (run_id, step_no, date, ticket_id, stake, odds, bank_before) VALUES (?,?,?,?,?,?,?)",
              (rid, 2, "2026-11-16", tid, 50, 1.96, 100))
    _bb(c, 3, "2026-11-16T19:45:00Z", 1.40, 0.70, 3)
    _bb(c, 4, "2026-11-16T20:15:00Z", 1.40, 0.68, 4)
    now = datetime(2026, 11, 16, 4, 0, tzinfo=timezone.utc)
    out = build_pyramid_120_day(c, date(2026, 11, 16), now, replace=True)
    assert out["status"] == "pause"
    assert "15.11" in out["reason"]
    assert c.execute("SELECT status FROM ticket WHERE id=?", (tid,)).fetchone()[0] == "replaced"
    assert c.execute("SELECT status FROM ticket WHERE id=?", (yid,)).fetchone()[0] == "pending"
    assert c.execute("SELECT COUNT(*) FROM pyramid120_step WHERE date='2026-11-16'").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM pyramid120_step WHERE date='2026-11-15'").fetchone()[0] == 1
