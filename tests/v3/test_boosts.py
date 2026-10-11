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


def test_core_rule():
    f = BO.core_rule("GG & peste 3.5 goluri", "A", "B")
    assert f(2, 2) and not f(4, 0)
    assert BO.core_rule("Lazio peste 5.5 șuturi pe poartă", "Lazio", "Monza") is None
