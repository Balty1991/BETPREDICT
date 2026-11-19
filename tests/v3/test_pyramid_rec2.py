"""Cota 2 a zilei din predicțiile recomandate: 2 selecții 1,30–1,55 (rezervă 3 de 1,22–1,32), doar azi 10–24,
pauză la calibrare ruptă, retrageri automate la pașii 2, 4, 6."""
import sqlite3
from datetime import date, datetime, timezone

from betpredict.builder.pyramid import (RULES_CORNER2, advance_pyramid, build_pyramid_120_day, calibration_pause,
                                        ensure_track_tables, pick_rec_2)
from betpredict.store import db as DB

DAY = date(2026, 11, 20)
NOW = datetime(2026, 11, 20, 7, 0, tzinfo=timezone.utc)  # 09:00 ora României


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    DB.init_db(c)
    return c


def _match(c, mid, kick, league):
    c.execute("INSERT OR IGNORE INTO league (id, name) VALUES (?, ?)", (league, f"Liga {league}"))
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, league_id, status) VALUES (?,?,?,?,?,?)",
              (mid, kick, f"H{mid}", f"A{mid}", league, "notstarted"))


def _offer(c, mid, market, outcome, price):
    c.execute("INSERT INTO sb_offer (match_id, market_name, outcome, price, observed_at) VALUES (?,?,?,?,?)",
              (mid, market, outcome, price, "2026-11-20T06:00:00Z"))


H2 = "A doua repriză - Interval goluri"


def test_two_legs_from_different_leagues_today_only():
    c = _db()
    _match(c, 1, "2026-11-20T15:00:00Z", 1)
    _match(c, 2, "2026-11-20T17:30:00Z", 2)
    _match(c, 3, "2026-11-20T18:00:00Z", 1)   # aceeași ligă ca meciul 1
    _match(c, 4, "2026-11-21T15:00:00Z", 4)   # mâine: nu intră
    _match(c, 5, "2026-11-20T06:30:00Z", 5)   # 08:30 ora României: înainte de 10, nu intră
    _offer(c, 1, H2, "1-3", 1.38)
    _offer(c, 2, H2, "1-3", 1.40)
    _offer(c, 3, H2, "1-3", 1.36)
    _offer(c, 4, H2, "1-3", 1.37)
    _offer(c, 5, H2, "1-3", 1.37)
    res = pick_rec_2(c, NOW, RULES_CORNER2, DAY)
    assert res["status"] == "pick"
    legs, p = res["main"]
    assert len(legs) == 2
    ids = {x.match_id for x in legs}
    assert 4 not in ids and 5 not in ids
    assert len({x.league_id for x in legs}) == 2
    assert 1.85 <= legs[0].odds * legs[1].odds <= 2.20
    assert 0.44 <= p <= 0.60
    assert "o dată din două" in res["reason"] and "pașii 2, 4 și 6" in res["reason"]


def test_three_small_legs_are_the_fallback():
    c = _db()
    for mid, lg in ((1, 1), (2, 2), (3, 3)):
        _match(c, mid, f"2026-11-20T1{mid + 4}:00:00Z", lg)
        _offer(c, mid, H2, "1-3", 1.27)
    res = pick_rec_2(c, NOW, RULES_CORNER2, DAY)
    assert res["status"] == "pick"
    assert len(res["main"][0]) == 3


def test_no_bet_reason_is_romanian_and_honest():
    c = _db()
    _match(c, 1, "2026-11-20T15:00:00Z", 1)
    _offer(c, 1, H2, "1-3", 1.38)
    res = pick_rec_2(c, NOW, RULES_CORNER2, DAY)
    assert res["status"] == "no_bet"
    assert "Nu forțăm biletul" in res["reason"]


def test_no_corner_reserve_any_more():
    c = _db()
    _match(c, 1, "2026-11-20T15:00:00Z", 1)
    _match(c, 2, "2026-11-20T17:00:00Z", 2)
    for mid in (1, 2):
        c.execute("""INSERT INTO bb_suggestion (match_id, day, legs_json, label, p_joint, fair_odds, min_odds, sb_price, ev, source, created_at)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                  (mid, "2026-11-20", '{"superbet": {"market": "Bet Builder", "outcome": "Peste 0.5 goluri; Peste 7.5 cornere"}}',
                   "Peste 0.5 goluri; Peste 7.5 cornere", 0.7, 1.43, 1.2, 1.40, -0.02, "superbet", "2026-11-20T06:00:00Z"))
    out = build_pyramid_120_day(c, DAY, NOW, replace=True)
    assert out["status"] == "no_bet"


def _settled(c, day, status, p=0.5):
    c.execute("INSERT INTO ticket (kind, variant, created_by, status, created_at, day, total_odds, p_ticket) "
              "VALUES ('pyramid','p120','robot',?,?,?,1.95,?)", (status, day + "T08:00:00Z", day, p))


def test_calibration_pause_only_when_hits_are_far_below_estimate():
    c = _db()
    for i in range(12):
        _settled(c, f"2026-12-{i + 1:02d}", "won" if i < 2 else "lost")
    assert calibration_pause(c, RULES_CORNER2, date(2026, 12, 20)) is not None
    c2 = _db()
    for i in range(12):
        _settled(c2, f"2026-12-{i + 1:02d}", "won" if i < 5 else "lost")
    assert calibration_pause(c2, RULES_CORNER2, date(2026, 12, 20)) is None
    c3 = _db()
    for i in range(6):
        _settled(c3, f"2026-12-{i + 1:02d}", "lost")
    assert calibration_pause(c3, RULES_CORNER2, date(2026, 12, 20)) is None  # prea puține bilete: nu decidem


def test_half_stake_and_automatic_withdrawal_at_step_2():
    c = _db()
    ensure_track_tables(c, "pyramid120")
    c.execute("INSERT INTO pyramid120_run (start_date, start_bank, status, current_step, current_bank) VALUES ('2026-11-20',100,'active',0,100)")
    for i, (d, bank) in enumerate((("2026-11-20", 100.0), ("2026-11-21", 150.0)), 1):
        c.execute("INSERT INTO ticket (id, kind, variant, created_by, status, payout, created_at, day, total_odds) "
                  "VALUES (?, 'pyramid','p120','robot','won',2.0,?,?,2.0)", (i, d + "T08:00:00Z", d))
        c.execute("INSERT INTO pyramid120_step (run_id, step_no, date, ticket_id, stake, odds, bank_before) VALUES (1,?,?,?,?,2.0,?)",
                  (i, d, i, bank / 2, bank))
        advance_pyramid(c, RULES_CORNER2, "pyramid120_run", "pyramid120_step")
    run = c.execute("SELECT * FROM pyramid120_run WHERE id=1").fetchone()
    step2 = c.execute("SELECT * FROM pyramid120_step WHERE step_no=2").fetchone()
    assert run["current_step"] == 2 and run["status"] == "active"
    assert step2["withdrawn"] == 112.5 and run["current_bank"] == 112.5  # 100 → 150 → 225, jumătate retrasă
