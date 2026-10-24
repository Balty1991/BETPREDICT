import sqlite3
from datetime import date, datetime, timezone

from betpredict.builder import mono_tickets as M
from betpredict.store import db as DB


def _db():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    for i in range(1, 21):
        c.execute("INSERT INTO match (id, league_id, kickoff_utc, home_name, away_name, status) VALUES (?,?,?,?,?, 'notstarted')",
                  (i, i % 7, "2026-10-24T18:00:00Z", f"H{i}", f"A{i}"))
    return c


def _rows(key, odds, n=20, p=0.7):
    return [{"match_id": i, "league_id": i % 7, "key": key, "p": p - i * 0.001, "odds": odds, "kickoff_utc": "2026-10-24T18:00:00Z",
             "suspect": False} for i in range(1, n + 1)]


def test_one_market_per_ticket_near_100_and_idempotent():
    c = _db()
    now = datetime(2026, 10, 24, 6, tzinfo=timezone.utc)
    rows = _rows("H2G13", 1.33) + _rows("R1R2", 1.40) + _rows("BB_H1C25_U65", 1.52)
    rep = M.build(c, date(2026, 10, 24), now, rows)
    assert len(rep["tickets"]) == 3
    for t in c.execute("SELECT id, total_odds FROM ticket WHERE kind='acca_mono'"):
        keys = {r[0] for r in c.execute("SELECT selection FROM ticket_leg WHERE ticket_id=?", (t["id"],))}
        n = c.execute("SELECT COUNT(*) FROM ticket_leg WHERE ticket_id=?", (t["id"],)).fetchone()[0]
        assert len(keys) == 1 and M.LEGS[0] <= n <= M.LEGS[1] and t["total_odds"] >= M.MIN_TOTAL
        per_league = c.execute("""SELECT MAX(k) FROM (SELECT COUNT(*) k FROM ticket_leg l JOIN match m ON m.id=l.match_id
                                  WHERE l.ticket_id=? GROUP BY m.league_id)""", (t["id"],)).fetchone()[0]
        assert per_league <= M.MAX_PER_LEAGUE
    assert M.build(c, date(2026, 10, 24), now, rows) == {"skipped_existing": 3}


def test_too_few_matches_no_ticket():
    c = _db()
    rep = M.build(c, date(2026, 10, 24), datetime(2026, 10, 24, 6, tzinfo=timezone.utc), _rows("H2G13", 1.33, n=5))
    assert rep["tickets"] == [] and {s["key"] for s in rep["skipped"]} == {k for k, *_ in M.MARKETS}
