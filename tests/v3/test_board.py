"""Acumulatorul scurt: filtre, fără meciuri comune, plafon, ștergerea jurnalului vechi."""

from datetime import date

from betpredict.builder.board import best_per_match, plan, purge_legacy_once, qualifies
from betpredict.builder.pool import Cand
from betpredict.store.db import connect, init_db


def C(i, **kw):
    base = dict(
        prediction_id=i, match_id=i, league_id=i, league=f"L{i}", kickoff_utc=f"2026-11-09T{12 + (i % 8):02d}:00:00Z",
        home=f"H{i}", away=f"A{i}", market="1x2", line=0.0, selection="HOME", odds=2.10, p=0.49, ev=0.03,
        grade="B", confidence=1, p_market=0.495, odds_source="superbet", drift=0.0,
    )
    base.update(kw)
    return Cand(**base)


def test_qualifies_only_the_calibrated_band():
    assert qualifies(C(1))
    assert not qualifies(C(2, odds=1.40))
    assert not qualifies(C(3, selection="DRAW"))
    assert not qualifies(C(4, market="btts", selection="NO"))
    assert qualifies(C(5, market="btts", selection="YES"))
    assert not qualifies(C(6, odds_source="bsd_consensus"))
    assert not qualifies(C(7, p=0.70))  # modelul se desparte de piață
    assert not qualifies(C(8, p_market=0.40))  # edge uriaș = cotă suspectă
    assert not qualifies(C(9, odds=3.20, p_market=0.33, p=0.34))


def test_plan_no_shared_matches_and_cap():
    cands = best_per_match([C(i, odds=2.05 + (i % 5) * 0.05, p_market=0.50, p=0.50) for i in range(1, 40)])
    # 2.05*0.50=1.025 edge 2.5%; 2.25*0.50=1.125 edge 12.5%. Toate în bandă.
    tickets = plan(cands)
    assert 1 <= len(tickets) <= 15
    seen = []
    for _variant, legs in tickets:
        assert 2 <= len(legs) <= 8
        seen += [c.match_id for c in legs]
        assert len({c.league_id for c in legs}) == len(legs)
    assert len(seen) == len(set(seen))
    plays = [t for t in tickets if t[0].startswith("joc_")]
    assert plays
    assert all(4.0 <= __import__("math").prod(c.odds for c in legs) <= 12.0 for _, legs in plays)


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
    first = purge_legacy_once(conn)
    assert first["tickets"] == 1 and first["legs"] == 1 and first["pyramid_runs"] == 1
    assert conn.execute("SELECT COUNT(*) FROM ticket").fetchone()[0] == 0
    second = purge_legacy_once(conn)
    assert second["skipped"] is True
    conn.close()
    _ = date.today()
