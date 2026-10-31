import math

from betpredict.builder.pool import Cand
from betpredict.builder import pyramid as P
from betpredict.store.db import connect, init_db


def _c(i, odds, p, drift=None, src="superbet", match=None):
    return Cand(i, match or 1000 + i, i, "L", "2026-10-10T18:00:00Z", "A", "B", "1x2", 0.0, "HOME",
                odds, p, p * odds - 1, "A", 80, True, p_market=p, drift=drift, odds_source=src)


def test_pick_maximizes_joint_chance_in_band():
    # un singur meci la ~1.40 are prioritate; fără el, rezerva de 2 selecții (fiecare ≤ 1.40)
    pool = [_c(1, 1.38, 0.74), _c(2, 1.18, 0.86), _c(3, 1.19, 0.85), _c(4, 1.10, 0.92), _c(5, 1.27, 0.80)]
    r = P.pick_pyramid_140(pool)
    legs, p = r["main"]
    assert r["status"] == "pick" and len(legs) == 1 and legs[0].odds == 1.38
    r = P.pick_pyramid_140(pool[1:] + [_c(6, 1.40, 0.60), _c(7, 1.45, 0.80)])   # 60% e prea puțin, 1.45 e peste 1.40
    legs, p = r["main"]
    assert r["status"] == "pick" and len(legs) == 2 and 1.35 <= math.prod(c.odds for c in legs) <= 1.45
    assert all(c.odds <= 1.40 and c.p_honest >= 0.65 for c in legs)


def test_safe_pyramid_gates_on_ticket_monte_carlo_probability(monkeypatch):
    monkeypatch.setattr(P, "q_ticket", lambda legs, rel=None: 0.75)
    rules = {**P.RULES_140, "band": [1.40, 1.45], "max_legs": 2, "fallback_legs": None,
             "min_p": 0.70, "min_ev": 0.0, "leg_odds": [1.15, 1.30]}
    result = P.pick_pyramid_140([_c(1, 1.20, 0.90), _c(2, 1.20, 0.90)], rules)
    assert result["status"] == "pick"
    assert result["main"][1] == 0.75  # nu produsul naiv 0.90 × 0.90


def test_several_selections_per_match_and_reliability():
    """Din același meci poate intra o selecție cu cotă mai mare decât cea mai sigură; corecția pe piață schimbă ordinea."""
    a = Cand(1, 7, 1, "L", "2026-10-10T18:00:00Z", "A", "B", "double_chance", 0.0, "1X", 1.08, 0.93, 0.0, "A", 80, True, p_market=0.93, odds_source="superbet")
    b = Cand(2, 7, 1, "L", "2026-10-10T18:00:00Z", "A", "B", "over_under", 1.5, "OVER", 1.40, 0.76, 0.0, "A", 80, True, p_market=0.76, odds_source="superbet")
    r = P.pick_pyramid_140([a, b])
    assert r["status"] == "pick" and r["main"][0][0].selection == "OVER"   # înainte: doar 1X (cota 1.08) din meci → fără bilet
    c1 = _c(3, 1.20, 0.84, match=8)
    c2 = Cand(4, 9, 4, "L", "2026-10-10T18:00:00Z", "A", "B", "btts", 0.0, "NO", 1.20, 0.84, 0.0, "A", 80, True, p_market=0.84, odds_source="superbet")
    r2 = P.pick_pyramid_140([c1, c2], P.RULES_120, rel={("btts", 0.0, "NO"): 0.04, ("1x2", 0.0, "HOME"): -0.04})
    assert r2["main"][0][0].market == "btts"


def test_drift_and_weak_excluded():
    assert P.pick_pyramid_140([_c(1, 1.40, 0.60)])["status"] == "no_bet"
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
    pool = [_m(1, 1.40, 0.70), _m(2, 1.38, 0.69, "League Two", "AWAY"), _m(3, 1.40, 0.72, "Premier League"),
            _m(4, 1.39, 0.71, "Conference League")]
    r = P.pick_pyramid_mici(pool)
    legs, _ = r["main"]
    assert r["status"] == "pick" and {c.match_id for c in legs} == {2001, 2002}
    assert P.pick_pyramid_mici([_m(1, 1.40, 0.70), _m(2, 1.45, 0.69, "League Two", "AWAY")])["status"] == "no_bet"  # 1.45 > 1.40
    assert P.pick_pyramid_mici([_m(1, 1.95, 0.5)])["status"] == "no_bet"  # o singură selecție nu e destul


def test_mici_cashout_after_9():
    conn = connect(":memory:")
    init_db(conn)
    P.ensure_track_tables(conn, "pyramidmici")
    conn.execute("INSERT INTO pyramidmici_run (start_date, start_bank, current_bank) VALUES ('2026-10-01', 100, 100)")
    bank = 100.0
    for i in range(1, 10):
        conn.execute("INSERT INTO ticket (id, kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, payout, created_at, day) "
                     "VALUES (?, 'pyramid', 'pmici', 'robot', 2, 2, 0.5, 0, 1, 'won', 2, 'x', ?)", (i, f"2026-10-{i:02d}"))
        conn.execute("INSERT INTO pyramidmici_step (run_id, step_no, date, ticket_id, bank_before) VALUES (1, ?, ?, ?, ?)", (i, f"2026-10-{i:02d}", i, bank))
        P.advance_pyramid_mici(conn)
        bank *= 2
    run = conn.execute("SELECT * FROM pyramidmici_run").fetchone()
    assert run["status"] == "completed" and run["withdrawn_total"] == 51200.0 and run["current_step"] == 9


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
    a = A.action(conn, "1.40", None)  # 4 câștiguri → doar propunere de încasare (decizia e a ta), piramida continuă
    assert a["kind"] == "suggest" and "384,16" in a["text"] and a["cashout"] == 384.16
    assert conn.execute("SELECT status FROM pyramid140_run").fetchone()[0] != "completed"
    r = A.review(conn)
    assert r["1.40"]["changed"] is False and r["1.40"]["steps"] == 4  # gardă: prea puțini pași
    assert repo.get_state(conn, A.STATE_KEY + "1.40") is None


def test_ev_gate_does_not_empty_pyramids():
    """Pragul de EV pe piață (healthy=False peste tot când învățarea nu găsește profit) nu mai golește piramidele."""
    def gated(i, odds, p, match=None):
        c = _c(i, odds, p, match=match)
        c.healthy = False
        return c
    r = P.pick_pyramid_140([gated(2, 1.18, 0.86), gated(3, 1.19, 0.85)])
    assert r["status"] == "pick"
    r2 = P.pick_pyramid([gated(7, 1.39, 0.76), gated(8, 1.40, 0.75, match=1108)])
    assert r2["status"] == "pick"
    # cota care fuge de selecție tot oprește
    assert P.pick_pyramid_140([_c(4, 1.18, 0.86, drift=0.08), gated(5, 1.19, 0.85)])["status"] == "no_bet"


def test_120_prefers_steamed_price():
    """1.20: un meci cu cota în scădere (≥ 2%) bate unul puțin mai sigur cu cota pe loc; fără el, regula de bază."""
    a = _c(1, 1.20, 0.86, drift=0.0)
    b = _c(2, 1.21, 0.84, drift=-0.03)
    r = P.pick_pyramid_140([a, b], P.RULES_120)
    assert r["main"][0][0].match_id == b.match_id and "scăzut" in r["reason"]
    r2 = P.pick_pyramid_140([a, _c(3, 1.21, 0.84, drift=0.01)], P.RULES_120)
    assert r2["main"][0][0].match_id == a.match_id


def test_boost_pyramid_and_boost_first_in_safe_pyramids():
    """Cotele mărite obișnuite cu EV > 0: piramida lor și prioritate în piramidele sigure; Super Cota nu intră."""
    from datetime import date, datetime, timezone
    from betpredict.ingest import boosts as BO

    conn = connect(":memory:")
    init_db(conn)
    BO.ensure(conn)
    for mid, ko in ((1, "2026-10-22T17:00:00Z"), (2, "2026-10-22T18:00:00Z"), (3, "2026-10-22T19:00:00Z")):
        conn.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, league_id) VALUES (?,?,?,?,?,?)",
                     (mid, ko, f"H{mid}", f"A{mid}", "notstarted", mid))
    seen = "2026-10-22T06:00:00Z"
    rows = [(1, "u1", "core", "Gazdele câștigă", 2.4, 0.48, 0.15), (2, "u2", "super_cota", "SC-1", 1.9, 0.6, 0.14),
            (3, "u3", "core", "Peste 1.5", 1.38, 0.76, 0.05), (3, "u4", "core", "Ambele marchează", 2.1, 0.45, -0.05)]
    for mid, uid, kind, name, price, p, ev in rows:
        conn.execute("INSERT INTO sb_boost (match_id, uid, kind, name, price, first_seen, last_seen, p_fair, method, ev) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (mid, uid, kind, name, price, seen, seen, p, "model (λ din piață)", ev))
    now = datetime(2026, 10, 22, 7, tzinfo=timezone.utc)
    bc = P.boost_cands(conn, date(2026, 10, 22), now)
    assert {c.selection for c in bc} == {"Gazdele câștigă", "Peste 1.5"}          # fără Super Cota, fără EV negativ
    r = P.pick_pyramid_boost(bc)
    assert r["status"] == "pick" and r["main"][0][0].selection == "Peste 1.5"   # cea mai mare șansă (1.38 intră: minim 1.25)
    pick = P._safe_picker(conn, date(2026, 10, 22), now)
    r140 = pick([_c(9, 1.38, 0.80)], P.RULES_140)
    assert r140["main"][0][0].market == "boost" and "Cotă mărită" in r140["reason"]


def test_boost_pyramid_falls_back_to_positive_super_cota():
    from datetime import date, datetime, timezone
    from betpredict.ingest import boosts as BO

    conn = connect(":memory:")
    init_db(conn)
    BO.ensure(conn)
    conn.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, league_id) VALUES (1,'2026-10-22T19:00:00Z','H','A','notstarted',1)")
    for uid, name, price, p, ev in (("s1", "SC-1", 1.95, 0.52, 0.02), ("s2", "SC-X", 3.6, 0.27, 0.01), ("s3", "SC-2", 2.2, 0.55, -0.02)):
        conn.execute("INSERT INTO sb_boost (match_id, uid, kind, name, price, first_seen, last_seen, p_fair, method, ev) VALUES (1,?,?,?,?,?,?,?,?,?)",
                     (uid, "super_cota", name, price, "2026-10-22T06:00:00Z", "2026-10-22T06:00:00Z", p, "piață (Pinnacle + consens)", ev))
    st = P.build_pyramid_boost_day(conn, date(2026, 10, 22), datetime(2026, 10, 22, 7, tzinfo=timezone.utc))
    assert st["status"] == "pick" and "rezervă" in st["reason"]
    leg = conn.execute("SELECT market, selection, odds FROM ticket_leg").fetchone()
    assert tuple(leg) == ("boost|0", "Super Cota 1", 1.95)


def test_reset_tracks_moves_today_to_step_1_once():
    from datetime import date
    conn = connect(":memory:")
    init_db(conn)
    P.ensure_track_tables(conn, "pyramid140")
    conn.execute("INSERT INTO pyramid140_run (start_date, start_bank, current_step, current_bank) VALUES ('2026-10-15', 100, 3, 255.24)")
    conn.execute("INSERT INTO ticket (id, kind, variant, created_by, target_odds, total_odds, p_ticket, ev, stake, status, created_at, day) "
                 "VALUES (7, 'pyramid', 'p140', 'robot', 1.4, 1.36, 0.7, 0, 1, 'pending', 'x', '2026-10-22')")
    conn.execute("INSERT INTO pyramid140_step (run_id, step_no, date, ticket_id, bank_before, odds) VALUES (1, 4, '2026-10-22', 7, 255.24, 1.36)")
    r = P.reset_tracks(conn, date(2026, 10, 22), {"pyramid140": P.RULES_140})
    assert r["pyramid140"] == {"closed_runs": 1, "today_is_step_1": True}
    runs = conn.execute("SELECT status, current_step, current_bank FROM pyramid140_run ORDER BY id").fetchall()
    assert [x[0] for x in runs] == ["reset", "active"] and runs[1][2] == 100
    st = conn.execute("SELECT run_id, step_no, ticket_id, bank_before FROM pyramid140_step").fetchall()
    assert [tuple(x) for x in st] == [(2, 1, 7, 100.0)]
    assert P.reset_tracks(conn, date(2026, 10, 23), {"pyramid140": P.RULES_140}) == {}   # o singură dată
    conn.execute("UPDATE ticket SET status='won', payout=1.36 WHERE id=7")
    P.advance_pyramid(conn, rules=P.RULES_140, run_t="pyramid140_run", step_t="pyramid140_step")
    assert tuple(conn.execute("SELECT current_step, current_bank FROM pyramid140_run WHERE id=2").fetchone()) == (1, 136.0)
