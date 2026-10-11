import json
import sqlite3
from datetime import date, datetime, timezone

from betpredict.store import db as DB
from betpredict.experimental import supersocial as SS
from betpredict.settle import settle_tickets


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    DB.init_db(c)
    return c


def _seed(c, n=14):
    for i in range(1, n + 1):
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?,?,?,?,?)",
                  (i, "2026-10-11T18:00:00Z", f"Home{i}", f"Away{i}", "scheduled"))
        c.execute("INSERT INTO match_model (match_id, model_version, lambda_home, lambda_away) VALUES (?,?,?,?)", (i, "robot-v1", 1.5, 1.2))
        for (mn, out), price in {("Interval goluri", "2-4"): 1.62, ("Interval goluri", "2-5"): 1.42, ("Interval goluri", "1-3"): 1.70,
                                 ("Gol marcat în ambele reprize", "Da"): 1.60,
                                 ("Total goluri prima repriză & Total goluri", "Peste 0.5 & Peste 1.5"): 1.45}.items():
            c.execute("INSERT INTO sb_offer (match_id, market_name, outcome, price, observed_at) VALUES (?,?,?,?,?)",
                      (i, mn, out, price, "2026-10-11T08:00:00Z"))


def test_build_tickets_overlap_and_snapshot():
    c = _db(); _seed(c)
    now = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)
    rep = SS.build(c, date(2026, 10, 11), now)
    assert rep["snapshot_rows"] == 70 and len(rep["tickets"]) >= 2
    t = c.execute("SELECT * FROM ticket WHERE variant=?", (SS.VARIANT,)).fetchall()
    assert all(SS.MIN_LEGS <= len(c.execute("SELECT * FROM ticket_leg WHERE ticket_id=?", (x["id"],)).fetchall()) <= SS.MAX_LEGS for x in t)
    per_match = c.execute("SELECT match_id, COUNT(*) n FROM ticket_leg GROUP BY match_id").fetchall()
    assert max(r["n"] for r in per_match) <= SS.MAX_TICKETS_PER_MATCH
    dup = c.execute("SELECT COUNT(*) FROM (SELECT match_id, selection FROM ticket_leg GROUP BY 1,2 HAVING COUNT(*)>1)").fetchone()[0]
    assert dup == 0
    first = c.execute("SELECT selection FROM ticket_leg WHERE ticket_id=?", (t[0]["id"],)).fetchall()
    assert {r["selection"] for r in first} <= {"G24", "G25"}
    assert json.loads(t[0]["notes"])["paper"] is True
    again = SS.build(c, date(2026, 10, 11), now)
    assert again.get("skipped_existing") or not again.get("tickets")  # biletele existente nu se dublează


def test_real_settlement_with_halftime():
    c = _db(); _seed(c)
    SS.build(c, date(2026, 10, 11), datetime(2026, 10, 11, 9, tzinfo=timezone.utc))
    c.execute("UPDATE match SET status='finished', ft_home=2, ft_away=1, ht_home=1, ht_away=0")
    settle_tickets(c)
    legs = c.execute("SELECT selection, result FROM ticket_leg").fetchall()
    assert all(l["result"] == "won" for l in legs)  # 3 goluri, gol în ambele reprize → toate tiparele intră
    assert c.execute("SELECT COUNT(*) FROM ticket WHERE variant=? AND status='won'", (SS.VARIANT,)).fetchone()[0] >= 2
    c.execute("UPDATE ticket_leg SET result=NULL"); c.execute("UPDATE ticket SET status='pending'")
    c.execute("UPDATE match SET ft_home=1, ft_away=0, ht_home=1, ht_away=0")
    settle_tickets(c)
    res = {(l["selection"], l["result"]) for l in c.execute("SELECT selection, result FROM ticket_leg")}
    assert ("G24", "lost") in res or ("G25", "lost") in res
    assert SS.live_stats(c)["legs"]


def test_labels():
    from betpredict.robot.markets import label_ro
    assert label_ro("ss", 0.0, "G24") == "Interval goluri 2-4"


def test_mix_key_cap():
    c = _db(); _seed(c, 20)
    SS.build(c, date(2026, 10, 11), datetime(2026, 10, 11, 9, tzinfo=timezone.utc))
    for t in c.execute("SELECT id, notes FROM ticket").fetchall():
        if json.loads(t["notes"])["stil"] != "Goluri 2–4 / 2–5":
            n = c.execute("SELECT selection, COUNT(*) k FROM ticket_leg WHERE ticket_id=? GROUP BY 1", (t["id"],)).fetchall()
            assert max(r["k"] for r in n) <= SS.MAX_PER_KEY
