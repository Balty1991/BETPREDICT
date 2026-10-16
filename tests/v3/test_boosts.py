import sqlite3
from datetime import date, datetime, timezone

from betpredict.ingest import boosts as BO
from betpredict.store import db as DB, repo
from betpredict.settle import settle_tickets

EV = {"odds": [
    {"uuid": "u1", "marketName": "Final - Super Cota", "name": "SC-1", "price": 2.42, "tags": "superKvota,v2", "extra": {}},
    {"uuid": "u2", "marketName": "Cote Mărite", "name": "Rapid câștigă & peste 2.5 goluri", "price": 3.4, "tags": "price_boost,boost_core_market,v2",
     "extra": {"boostLevel": "normal", "originalPrice": "9480:3.000000"}},
    {"uuid": "u3", "marketName": "X; Y", "name": "Ion va avea peste 0.5 șuturi pe poartă", "price": 2.3, "tags": "price_boost,boost_non_core_market,price_boost_combo,v2",
     "extra": {"originalPrice": "220:2.050000"}},
    {"uuid": "u4", "marketName": "Final", "name": "1", "price": 2.37, "tags": "v2", "extra": {}}]}


def _db():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (1,'2026-10-11T18:00:00Z','Rapid','Dinamo','scheduled')")
    obs = "2026-10-11T08:00:00Z"
    rows = [{"match_id": 1, "market": "1x2", "line": 0.0, "period": "FT", "outcome": o, "decimal": d, "source": "bsd_consensus", "observed_at": obs}
            for o, d in (("HOME", 2.2), ("DRAW", 3.4), ("AWAY", 3.4))]
    rows += [{"match_id": 1, "market": "over_under", "line": 2.5, "period": "FT", "outcome": o, "decimal": d, "source": "bsd_consensus", "observed_at": obs}
             for o, d in (("OVER", 1.9), ("UNDER", 1.9))]
    repo.insert_odds(c, rows)
    return c


def test_parse_kinds():
    b = {x["uid"]: x for x in BO.parse_boosts(EV)}
    assert set(b) == {"u1", "u2", "u3"} and b["u1"]["kind"] == "super_cota" and b["u2"]["kind"] == "core" and b["u3"]["kind"] == "combo"
    assert b["u2"]["orig_price"] == 3.0


def test_evaluate_settle_ticket():
    c = _db()
    BO.store(c, 1, EV, "2026-10-11T08:00:00Z")
    BO.evaluate(c)
    r = {x["uid"]: x for x in c.execute("SELECT * FROM sb_boost")}
    assert r["u1"]["method"].startswith("piață") and 0.4 < r["u1"]["p_fair"] < 0.47
    assert r["u2"]["method"].startswith("model") and 0.15 < r["u2"]["p_fair"] < 0.4
    assert r["u3"]["method"].startswith("incert") and abs(r["u3"]["p_fair"] - 1 / (2.05 * 1.10)) < 1e-3
    doc = BO.today_doc(c, datetime(2026, 10, 11, 9, tzinfo=timezone.utc))
    assert doc["count"] == 3 and doc["boosts"][0]["ev"] >= doc["boosts"][-1]["ev"]
    rep = BO.build_ticket(c, date(2026, 10, 11), datetime(2026, 10, 11, 9, tzinfo=timezone.utc))
    c.execute("UPDATE match SET status='finished', ft_home=3, ft_away=1, ht_home=1, ht_away=0")
    settle_tickets(c)
    r = {x["uid"]: x["result"] for x in c.execute("SELECT uid, result FROM sb_boost")}
    assert r == {"u1": "won", "u2": "won", "u3": "unsettleable"}
    if rep.get("tickets"):
        assert c.execute("SELECT status FROM ticket WHERE variant='cote_marite'").fetchone()[0] == "won"
    s = BO.stats(c)
    assert s["toate"]["n"] == 2 and s["toate"]["hit_rate"] == 1.0
    h = BO.history_doc(c)
    assert h["groups"]["super_cota"]["won"] == 1 and h["groups"]["estimat"]["unsettleable"] == 1 and len(h["recent"]) == 3
    assert h["groups"]["toate"]["roi"] == round((2.42 + 3.4) / 2 - 1, 3)


def test_core_rule():
    f = BO.core_rule("GG & peste 3.5 goluri", "A", "B")
    assert f(2, 2) and not f(4, 0)
    assert BO.core_rule("Lazio peste 5.5 șuturi pe poartă", "Lazio", "Monza") is None


def test_htft_boost_settles_from_halftime_score_and_unsettleable_leg_is_void():
    c = _db()
    ev = {"odds": [{"uuid": "h1", "marketName": "Cote Mărite", "name": "Rapid câștigă la pauză și la final", "price": 4.2,
                    "tags": "price_boost,boost_core_market,v2", "extra": {"originalPrice": "1:3.500000"}},
                   {"uuid": "x1", "marketName": "X; Y", "name": "Ion va avea peste 0.5 șuturi pe poartă", "price": 2.3,
                    "tags": "price_boost,boost_non_core_market,price_boost_combo,v2", "extra": {"originalPrice": "2:2.050000"}}]}
    BO.store(c, 1, ev, "2026-10-11T08:00:00Z")
    BO.evaluate(c)
    cur = c.execute("INSERT INTO ticket (kind, variant, created_by, stake, status, created_at, day, total_odds) VALUES ('acca_boost','cote_marite','robot',0.1,'pending','x','2026-10-11',9.66)")
    for name in ("Rapid câștigă la pauză și la final", "Ion va avea peste 0.5 șuturi pe poartă"):
        c.execute("INSERT INTO ticket_leg (ticket_id, match_id, market, selection, odds) VALUES (?,1,'boost|0',?,2)", (cur.lastrowid, name))
    c.execute("UPDATE match SET status='finished', ft_home=2, ft_away=1, ht_home=1, ht_away=0")
    settle_tickets(c)
    r = {x["uid"]: x["result"] for x in c.execute("SELECT uid, result FROM sb_boost")}
    assert r["h1"] == "won" and r["x1"] == "unsettleable"
    legs = {x["selection"]: x["result"] for x in c.execute("SELECT selection, result FROM ticket_leg")}
    assert legs["Rapid câștigă la pauză și la final"] == "won" and legs["Ion va avea peste 0.5 șuturi pe poartă"] == "void"
    assert c.execute("SELECT status FROM ticket WHERE id=?", (cur.lastrowid,)).fetchone()[0] != "pending"


def test_boost_tickets_are_singles_and_doubles_and_idempotent():
    c = _db()
    c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (2,'2026-10-11T19:00:00Z','Steaua','CFR','scheduled')")
    BO.store(c, 1, EV, "2026-10-11T08:00:00Z")
    BO.store(c, 2, {"odds": [{"uuid": "v2", "marketName": "Final - Super Cota", "name": "SC-2", "price": 2.6, "tags": "superKvota,v2", "extra": {}}]},
             "2026-10-11T08:00:00Z")
    c.execute("INSERT INTO odds_snapshot (match_id, market, line, period, outcome, decimal, source, observed_at) "
              "SELECT 2, market, line, period, outcome, decimal, source, observed_at FROM odds_snapshot WHERE match_id=1")
    BO.evaluate(c)
    c.execute("UPDATE sb_boost SET ev=0.05, p_fair=0.45, method='piață x'")
    now = datetime(2026, 10, 11, 9, tzinfo=timezone.utc)
    rep = BO.build_ticket(c, date(2026, 10, 11), now)
    kinds = sorted(m["type"] for m in rep["made"])
    assert kinds.count("dublu") >= 1 and "simplu" not in kinds
    legs = [r[0] for r in c.execute("SELECT COUNT(*) FROM ticket_leg GROUP BY ticket_id")]
    assert min(legs) == 2
    assert BO.build_ticket(c, date(2026, 10, 11), now)["tickets"] == 0
