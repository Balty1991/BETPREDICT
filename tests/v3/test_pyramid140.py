import math

from betpredict.builder.pool import Cand
from betpredict.builder import pyramid as P
from betpredict.store.db import connect, init_db


def _c(i, odds, p, drift=None, src="superbet", match=None):
    return Cand(i, match or 1000 + i, i, "L", "2026-10-10T18:00:00Z", "A", "B", "1x2", 0.0, "HOME",
                odds, p, p * odds - 1, "A", 80, True, p_market=p, drift=drift, odds_source=src)


def test_pick_maximizes_joint_chance_in_band():
    pool = [_c(1, 1.40, 0.70), _c(2, 1.18, 0.86), _c(3, 1.19, 0.85), _c(4, 1.10, 0.92), _c(5, 1.27, 0.80)]
    r = P.pick_pyramid_140(pool)
    legs, p = r["main"]
    assert r["status"] == "pick" and 1.35 <= math.prod(c.odds for c in legs) <= 1.45
    assert len({c.match_id for c in legs}) == len(legs) <= 4
    assert all(c.p_honest >= 0.80 for c in legs)  # selecția de 70% nu intră


def test_drift_and_weak_excluded():
    assert P.pick_pyramid_140([_c(1, 1.40, 0.75)])["status"] == "no_bet"
    pool = [_c(1, 1.18, 0.86, drift=0.08), _c(2, 1.19, 0.85)]
    assert P.pick_pyramid_140(pool)["status"] == "no_bet"


def test_advance_separate_state():
    conn = connect(":memory:")
    init_db(conn)
    P.ensure_140_tables(conn)
    conn.execute("INSERT INTO pyramid140_run (start_date, start_bank, current_bank) VALUES ('2026-10-10', 100, 100)")
    for i, (st, pay) in enumerate((("won", 1.4), ("lost", 0.0)), start=1):
        conn.execute("INSERT INTO ticket (id, kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, payout, created_at, day) "
                     "VALUES (?, 'pyramid', 'p140', 'robot', 1.4, 1.4, 0.7, 0, 1, ?, ?, 'x', ?)", (i, st, pay, f"2026-10-1{i}"))
    conn.execute("INSERT INTO pyramid140_step (run_id, step_no, date, ticket_id, bank_before) VALUES (1, 1, '2026-10-11', 1, 100)")
    P.advance_pyramid_140(conn)
    run = conn.execute("SELECT * FROM pyramid140_run").fetchone()
    assert run["current_step"] == 1 and run["current_bank"] == 140.0 and run["withdrawn_total"] == 0.0
    conn.execute("INSERT INTO pyramid140_step (run_id, step_no, date, ticket_id, bank_before) VALUES (1, 2, '2026-10-12', 2, 140)")
    P.advance_pyramid_140(conn)
    assert conn.execute("SELECT status FROM pyramid140_run").fetchone()[0] == "lost"
    assert conn.execute("SELECT COUNT(*) FROM pyramid_run").fetchone()[0] == 0  # piramida 2.00 neatinsă


def _m(i, odds, p, league="League One", sel="HOME", src="superbet"):
    lid = {"League One": 1, "League Two": 2, "National League": 3}.get(league, 9)
    return Cand(i, 2000 + i, lid, league, "2026-10-10T18:00:00Z", "A", "B", "1x2", 0.0, sel,
                odds, p, p * odds - 1, "A", 80, True, p_market=p, odds_source=src)


def test_mici_picks_small_league_favourites():
    pool = [_m(1, 1.40, 0.70), _m(2, 1.42, 0.69, "League Two", "AWAY"), _m(3, 1.40, 0.72, "Premier League"),
            _m(4, 1.41, 0.71, "Conference League")]
    r = P.pick_pyramid_mici(pool)
    legs, _ = r["main"]
    assert r["status"] == "pick" and {c.match_id for c in legs} == {2001, 2002}
    assert P.pick_pyramid_mici([_m(1, 1.95, 0.5)])["status"] == "no_bet"  # o singură selecție nu e destul


def test_mici_cashout_after_7():
    conn = connect(":memory:")
    init_db(conn)
    P.ensure_track_tables(conn, "pyramidmici")
    conn.execute("INSERT INTO pyramidmici_run (start_date, start_bank, current_bank) VALUES ('2026-10-01', 100, 100)")
    bank = 100.0
    for i in range(1, 8):
        conn.execute("INSERT INTO ticket (id, kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, payout, created_at, day) "
                     "VALUES (?, 'pyramid', 'pmici', 'robot', 2, 2, 0.5, 0, 1, 'won', 2, 'x', ?)", (i, f"2026-10-{i:02d}"))
        conn.execute("INSERT INTO pyramidmici_step (run_id, step_no, date, ticket_id, bank_before) VALUES (1, ?, ?, ?, ?)", (i, f"2026-10-{i:02d}", i, bank))
        P.advance_pyramid_mici(conn)
        bank *= 2
    run = conn.execute("SELECT * FROM pyramidmici_run").fetchone()
    assert run["status"] == "completed" and run["withdrawn_total"] == 12800.0 and run["current_step"] == 7


def test_action_and_review_guard():
    from betpredict.builder import pyramid_auto as A
    from betpredict.store import repo

    conn = connect(":memory:")
    init_db(conn)
    P.ensure_track_tables(conn, "pyramid140")
    assert A.action(conn, "1.40", None)["kind"] == "start"
    conn.execute("INSERT INTO pyramid140_run (start_date, start_bank, current_bank) VALUES ('2026-10-01', 100, 100)")
    for i in range(1, 5):
        conn.execute("INSERT INTO ticket (id, kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, payout, created_at, day) "
                     "VALUES (?, 'pyramid', 'p140', 'robot', 1.4, 1.4, 0.7, 0, 1, 'won', 1.4, 'x', ?)", (i, f"2026-10-0{i}"))
        conn.execute("INSERT INTO pyramid140_step (run_id, step_no, date, ticket_id, bank_before, odds) VALUES (1, ?, ?, ?, 0, 1.4)", (i, f"2026-10-0{i}", i))
        A.advance_all(conn)
        if i == 1:
            assert A.action(conn, "1.40", None)["kind"] == "reinvest"
    a = A.action(conn, "1.40", None)  # 4 câștiguri → ia tot
    assert a["kind"] == "take_all" and "384,16" in a["text"]
    r = A.review(conn)
    assert r["1.40"]["changed"] is False and r["1.40"]["steps"] == 4  # gardă: prea puțini pași
    assert repo.get_state(conn, A.STATE_KEY + "1.40") is None
