import json
import sqlite3
from datetime import date, datetime, timezone

from betpredict.builder import corner_tickets as C
from betpredict.store import db as DB


def _db(n=120, ko='2026-11-26T18:00:00Z'):
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    for i in range(1, n + 1):
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?, ?, 'h', 'a', 'notstarted')", (i, ko))
        price = 1.36 + (i % 8) * 0.04
        c.execute("INSERT INTO bb_suggestion (match_id, day, legs_json, label, p_joint, fair_odds, min_odds, sb_price, source, created_at) VALUES (?,?,?,?,?,1.43,1.43,?,?,?)",
                  (i, "2026-11-26", json.dumps({"superbet": {"market": "Total goluri & Total cornere", "outcome": "Peste 0.5 & Peste 7.5"}}),
                   "Peste 0.5 goluri; Peste 7.5 cornere", 0.7, price, "superbet", "2026-11-25T00:00:00Z"))
    return c


def test_corners_keep_five_active_tiers_and_replace_finished(monkeypatch):
    monkeypatch.setattr(C, "RICH_POOL", 10**6)
    c = _db()
    now = datetime(2026, 11, 25, 8, tzinfo=timezone.utc)
    rep = C.build(c, date(2026, 11, 25), now)  # miercuri, ofertă obișnuită: 5 bilete, câte unul pe prag
    assert rep["inserted"] == C.ACTIVE
    rows = c.execute("SELECT id, variant, total_odds, target_odds FROM ticket WHERE kind=? AND status='pending'", (C.KIND,)).fetchall()
    assert sorted(r["variant"] for r in rows) == sorted(C.CYCLE)
    for r in rows:
        assert r["target_odds"] <= r["total_odds"] <= r["target_odds"] * C.SPAN_C
    use = [r[0] for r in c.execute("SELECT COUNT(*) FROM ticket_leg GROUP BY match_id")]
    assert max(use) <= C.USE_CAP
    assert C.build(c, date(2026, 11, 25), now).get("inserted", 0) == 0  # nimic nou cât sunt 5 în joc
    c.execute("UPDATE ticket SET status='lost' WHERE id=(SELECT MIN(id) FROM ticket)")
    assert C.build(c, date(2026, 11, 25), now)["inserted"] == 1
    s = C.stats_doc(c, now)
    assert s["all"]["n"] == 1 and s["all"]["pending"] == C.ACTIVE


def test_corners_rich_day_goes_up_to_seven():
    c = _db(200, '2026-11-29T18:00:00Z')
    now = datetime(2026, 11, 28, 8, tzinfo=timezone.utc)
    C.build(c, date(2026, 11, 28), now)  # sâmbătă
    n = c.execute("SELECT COUNT(*) FROM ticket WHERE kind=? AND status='pending'", (C.KIND,)).fetchone()[0]
    assert C.ACTIVE < n <= C.ACTIVE_MAX


def test_lost_paper_ticket_without_stake_is_not_reclassified_as_won():
    from betpredict.settle import classify_payout, reclassify_settled

    c = _db(3)
    c.execute("INSERT INTO ticket (id, kind, variant, created_by, total_odds, status, payout, created_at) "
              "VALUES (1, 'acca_corners', '5000', 'robot', 5152.7, 'lost', 0.0, '2026-11-21T04:11:00Z')")
    c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds, result) VALUES (1, 1, 'bb', 'x', 1.4, 'lost')")
    reclassify_settled(c)
    assert c.execute("SELECT status FROM ticket WHERE id=1").fetchone()[0] == "lost"
    assert classify_payout(0.0, 0.0) == "lost"
