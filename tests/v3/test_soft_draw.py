import sqlite3
from datetime import date, datetime, timezone

from betpredict.settle import settle_tickets
from betpredict.store import db as DB
from betpredict.store import repo
from betpredict.builder import soft_draw as SD


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    DB.init_db(c)
    return c


def _odd(mid, source, outcome, price):
    return {"match_id": mid, "market": "1x2", "line": 0, "period": "FT", "outcome": outcome,
            "decimal": price, "opening_decimal": None, "previous_decimal": None, "movement": None,
            "source": source, "observed_at": "2026-10-12T18:00:00Z"}


def _seed(c):
    # 1 și 2 intră (3.10 și 3.40, +4% / +6%). 3 e sub 2%. 4 e în afara benzii.
    kicks = {1: "2026-10-13T16:00:00Z", 2: "2026-10-13T19:00:00Z", 3: "2026-10-13T20:00:00Z", 4: "2026-10-14T16:00:00Z"}
    prices = {1: (3.10, 2.98), 2: (3.40, 3.20), 3: (3.05, 3.02), 4: (2.40, 2.20)}
    for i, kick in kicks.items():
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?,?,?,?,?)",
                  (i, kick, f"Home{i}", f"Away{i}", "scheduled"))
        sb, med = prices[i]
        repo.insert_odds(c, [_odd(i, "superbet", "DRAW", sb), _odd(i, "bsd_consensus", "DRAW", med)])


def test_pair_same_day_and_skip_the_rest():
    c = _db(); _seed(c)
    now = datetime(2026, 10, 12, 20, tzinfo=timezone.utc)
    found = SD.candidates(c, now)
    assert [e["match_id"] for e in found] == [2, 1]
    rep = SD.build(c, date(2026, 10, 13), now)
    assert rep["events"] == 2 and len(rep["tickets"]) == 1
    t = c.execute("SELECT total_odds, day, status FROM ticket WHERE kind=?", (SD.KIND,)).fetchone()
    assert t["day"] == "2026-10-13" and t["status"] == "pending"
    assert abs(t["total_odds"] - round(3.10 * 3.40, 2)) < 0.02
    legs = c.execute("SELECT match_id, selection, odds_source FROM ticket_leg ORDER BY match_id").fetchall()
    assert [r["match_id"] for r in legs] == [1, 2]
    assert all(r["selection"] == "DRAW" and r["odds_source"] == "superbet" for r in legs)


def test_rebuild_replaces_pending_and_settles_draw():
    c = _db(); _seed(c)
    now = datetime(2026, 10, 12, 20, tzinfo=timezone.utc)
    SD.build(c, date(2026, 10, 13), now)
    SD.build(c, date(2026, 10, 13), now)
    assert c.execute("SELECT COUNT(*) FROM ticket WHERE kind=? AND status='replaced'", (SD.KIND,)).fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM ticket WHERE kind=? AND status='pending'", (SD.KIND,)).fetchone()[0] == 1
    c.execute("UPDATE match SET status='finished', ft_home=1, ft_away=1 WHERE id=1")
    c.execute("UPDATE match SET status='finished', ft_home=2, ft_away=0 WHERE id=2")
    settle_tickets(c)
    res = {r["match_id"]: r["result"] for r in c.execute("SELECT match_id, result FROM ticket_leg")}
    assert res[1] == "won" and res[2] == "lost"
    assert c.execute("SELECT status FROM ticket WHERE status!='replaced'").fetchone()["status"] == "lost"
