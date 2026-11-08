"""Acumulatori 100 / 1.000 / 10.000: piețe, bet builder, fără meci comun, resetul jurnalului."""

from datetime import date

from betpredict.builder.board import best_per_match, plan, purge_legacy_once, qualifies
from betpredict.builder.pool import Cand
from betpredict.store.db import connect, init_db


def C(i, **kw):
    base = dict(
        prediction_id=i, match_id=i, league_id=i, league=f"L{i}", kickoff_utc=f"2026-11-09T{12 + (i % 8):02d}:00:00Z",
        home=f"H{i}", away=f"A{i}", market="1x2", line=0.0, selection="HOME", odds=2.20, p=0.45, ev=0.0,
        grade="B", confidence=1, p_market=0.45, odds_source="superbet", drift=0.0,
    )
    base.update(kw)
    return Cand(**base)


def test_qualifies_uses_the_journal_markets():
    assert qualifies(C(1))
    assert qualifies(C(2, market="btts", selection="NO", odds=2.35))
    assert qualifies(C(3, market="btts", selection="YES", odds=1.95))
    assert qualifies(C(4, market="1x2", selection="AWAY", odds=2.10))
    assert not qualifies(C(5, market="btts", selection="NO", odds=2.20))
    assert not qualifies(C(6, market="over_under", selection="OVER", line=2.5))
    assert not qualifies(C(7, selection="DRAW"))
    assert not qualifies(C(8, odds_source="bsd_consensus"))
    assert not qualifies(C(9, odds=1.40))
    assert not qualifies(C(10, p=0.70))
    assert not qualifies(C(11, odds=3.20, p=0.30, p_market=0.30))


def test_betbuilder_settles_from_the_score():
    from betpredict.builder.bb_legs import hits, joint_p

    assert hits("1X2 & GG", "1 & Nu", 2, 0) is True
    assert hits("1X2 & GG", "1 & Nu", 2, 1) is False
    assert hits("Șansă dublă & Interval goluri", "1X & 2-3", 1, 1) is True
    assert hits("Șansă dublă & Interval goluri", "1X & 2-3", 0, 2) is False
    p = joint_p(1.4, 1.1, "1X2 & Total goluri (2.5)", "1 & Peste 2.5")
    assert p is not None and 0.05 < p < 0.6
    assert qualifies(C(20, market="bb", selection="1X2 & GG|1 & Nu", odds=3.2, p=0.30, p_market=None))
    assert not qualifies(C(21, market="bb", selection="scorer", odds=8.0, p=0.2, p_market=None))


def test_plan_hits_targets_without_shared_matches():
    import math
    singles = [C(i) for i in range(1, 40)]
    builders = [C(100 + i, market="bb", selection="1X2 & GG|1 & Nu", odds=3.20, p=0.30, p_market=None) for i in range(1, 50)]
    cands = best_per_match(singles + builders)
    tickets = plan(cands)
    assert 1 <= len(tickets) <= 15
    seen = []
    kinds = {v for v, _ in tickets}
    assert "t100" in kinds and "t1000" in kinds and "t10000" in kinds
    for variant, legs in tickets:
        seen += [c.match_id for c in legs]
        total = math.prod(c.odds for c in legs)
        if variant == "t100":
            assert 100 <= total <= 180 and 6 <= len(legs) <= 8
        elif variant == "t1000":
            assert 1000 <= total <= 2800 and 5 <= len(legs) <= 8
        else:
            assert 10000 <= total <= 28000 and 6 <= len(legs) <= 10
    assert len(seen) == len(set(seen))


def test_purge_once():
    conn = connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO ticket (kind, variant, created_by, total_odds, p_ticket, ev, stake, status, created_at, day) "
        "VALUES ('acca_100','loterie','robot',100,0.01,-0.5,0.25,'pending','2026-11-01T00:00:00Z','2026-11-01')")
    tid = conn.execute("SELECT id FROM ticket").fetchone()[0]
    conn.execute(
        "INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds) VALUES (?,?,?,?,?)",
        (tid, 1, "1x2|0", "HOME", 2.1))
    conn.execute(
        "INSERT INTO pyramid_run (start_date, start_bank, status, current_step, current_bank) "
        "VALUES ('2026-11-01',100,'active',1,100)")
    conn.execute(
        """CREATE TABLE pyramid140_step (
             run_id INTEGER, step_no INTEGER, date TEXT, ticket_id INTEGER REFERENCES ticket(id),
             PRIMARY KEY (run_id, step_no))""")
    conn.execute("INSERT INTO pyramid140_step (run_id, step_no, date, ticket_id) VALUES (1,1,'2026-11-01',?)", (tid,))
    first = purge_legacy_once(conn)
    assert first["tickets"] == 1 and first["legs"] == 1 and first["pyramid_runs"] >= 1
    assert conn.execute("SELECT COUNT(*) FROM ticket").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM pyramid140_step").fetchone()[0] == 0
    second = purge_legacy_once(conn)
    assert second["skipped"] is True
    conn.close()
    _ = date.today()
