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
    assert run["current_step"] == 1 and run["current_bank"] == 120.0 and run["withdrawn_total"] == 20.0
    conn.execute("INSERT INTO pyramid140_step (run_id, step_no, date, ticket_id, bank_before) VALUES (1, 2, '2026-10-12', 2, 120)")
    P.advance_pyramid_140(conn)
    assert conn.execute("SELECT status FROM pyramid140_run").fetchone()[0] == "lost"
    assert conn.execute("SELECT COUNT(*) FROM pyramid_run").fetchone()[0] == 0  # piramida 2.00 neatinsă
