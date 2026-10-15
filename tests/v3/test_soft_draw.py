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


def _odd(mid, source, outcome, price, market="1x2", line=0):
    return {"match_id": mid, "market": market, "line": line, "period": "FT", "outcome": outcome,
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
        repo.insert_odds(c, [_odd(i, "superbet", "DRAW", sb), _odd(i, "bsd_consensus", "DRAW", med),
                             _odd(i, "bsd_consensus", "HOME", 2.50), _odd(i, "bsd_consensus", "AWAY", 2.90),
                             _odd(i, "bsd_consensus", "OVER", 2.10, "over_under", 2.5)])


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


def test_rebuild_keeps_good_tickets_and_settles_draw():
    c = _db(); _seed(c)
    now = datetime(2026, 10, 12, 20, tzinfo=timezone.utc)
    SD.build(c, date(2026, 10, 13), now)
    SD.build(c, date(2026, 10, 13), now)  # nimic nou: biletul rămâne, nu se dublează
    assert c.execute("SELECT COUNT(*) FROM ticket WHERE kind=? AND status='replaced'", (SD.KIND,)).fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM ticket WHERE kind=? AND status='pending'", (SD.KIND,)).fetchone()[0] == 1
    c.execute("UPDATE match SET status='finished', ft_home=1, ft_away=1 WHERE id=1")
    c.execute("UPDATE match SET status='finished', ft_home=2, ft_away=0 WHERE id=2")
    settle_tickets(c)
    res = {r["match_id"]: r["result"] for r in c.execute("SELECT match_id, result FROM ticket_leg")}
    assert res[1] == "won" and res[2] == "lost"
    assert c.execute("SELECT status FROM ticket WHERE status!='replaced'").fetchone()["status"] == "lost"
    live = SD.live_record(c)
    assert live["singles"]["A"]["n"] == 2 and live["singles"]["A"]["won"] == 1 and live["tickets"]["n"] == 1


def test_tiers_and_replacing_only_unstarted_tickets_whose_match_left_the_rule():
    c = _db(); _seed(c)
    now = datetime(2026, 10, 12, 20, tzinfo=timezone.utc)
    SD.build(c, date(2026, 10, 13), now)
    # meciul 2 nu mai e „strâns”: rămâne în banda de bază (B), iese din A → biletul neînceput se reface
    repo.insert_odds(c, [{**_odd(2, "bsd_consensus", "HOME", 1.60), "observed_at": "2026-10-12T19:00:00Z"},
                         {**_odd(2, "bsd_consensus", "AWAY", 5.50), "observed_at": "2026-10-12T19:00:00Z"}])
    tiers = {e["match_id"]: e["tier"] for e in SD.candidates(c, now)}
    assert tiers == {1: "A", 2: "B"}
    rep = SD.build(c, date(2026, 10, 13), now)
    assert rep["replaced"] == 1 and not rep["tickets"]  # un singur egal A rămas: nu se face bilet
    # un bilet în joc nu se atinge niciodată
    SD.build(c, date(2026, 10, 13), datetime(2026, 10, 13, 17, tzinfo=timezone.utc))


def test_league_tags_from_history():
    from betpredict.ingest import footballdata as FD

    c = _db(); _seed(c)
    c.executescript(FD.SCHEMA)
    c.execute("UPDATE match SET league_id=10 WHERE id=1")
    c.execute("UPDATE match SET league_id=20 WHERE id=2")
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, league_id) VALUES (91,'2025-01-01T15:00:00Z','x','y','finished',10)")
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, league_id) VALUES (92,'2025-01-01T15:00:00Z','x','y','finished',20)")
    c.execute("INSERT INTO fd_match (div, season, day, home, away, match_id) VALUES ('I2','2425','2025-01-01','x','y',91)")
    c.execute("INSERT INTO fd_match (div, season, day, home, away, match_id) VALUES ('E1','2425','2025-01-01','x','y',92)")
    ev = {e["match_id"]: e for e in SD.candidates(c, datetime(2026, 10, 12, 20, tzinfo=timezone.utc))}
    assert ev[1]["league_tag"] == "bună" and ev[1]["tier"] == "A"
    assert ev[2]["league_tag"] == "slabă" and ev[2]["tier"] == "B"  # Championship: egalul A rămâne doar de urmărit
