import sqlite3
from datetime import datetime, timedelta, timezone

from betpredict.publish import late_value as LV
from betpredict.store import db as DB, repo

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _odds(c, mid, src, at, market, line, book):
    repo.insert_odds(c, [{"match_id": mid, "market": market, "line": line, "period": "FT", "outcome": o, "decimal": d,
                          "source": src, "observed_at": _iso(at)} for o, d in book.items()])


def _db():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    for mid, ko in ((1, NOW + timedelta(hours=2)), (2, NOW + timedelta(hours=5))):
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status) VALUES (?,?,?,?,'notstarted')",
                  (mid, _iso(ko), f"Gazde{mid}", f"Oaspeti{mid}"))
        c.execute("INSERT INTO ext_event (match_id, source, ext_id, ext_name, checked_at) VALUES (?, 'superbet', ?, ?, ?)",
                  (mid, f"99{mid}", f"Gazde{mid}·Oaspeti{mid}", _iso(NOW - timedelta(minutes=10))))
        # Pinnacle: gazdele ~50% corect; Superbet 2.25 pe gazde = +12%, iar oaspeții la 4.0 (cotă mare, exclusă)
        _odds(c, mid, "bsd:pinnacle", NOW - timedelta(minutes=30), "1x2", 0.0, {"HOME": 1.96, "DRAW": 3.6, "AWAY": 4.3})
        _odds(c, mid, "superbet", NOW - timedelta(minutes=20), "1x2", 0.0, {"HOME": 2.25, "DRAW": 3.3, "AWAY": 4.9})
        _odds(c, mid, "bsd:pinnacle", NOW - timedelta(minutes=30), "over_under", 2.5, {"OVER": 1.9, "UNDER": 1.98})
        _odds(c, mid, "superbet", NOW - timedelta(minutes=20), "over_under", 2.5, {"OVER": 1.85, "UNDER": 1.9})
        _odds(c, mid, "superbet", NOW - timedelta(minutes=20), "double_chance", 0.0, {"1X": 1.6})
    return c


def test_rule_window_odds_cap_and_first_trigger_only():
    c = _db()
    found = LV.find(c, NOW)
    assert [(a["match_id"], a["market"], a["outcome"]) for a in found] == [(1, "1x2", "HOME")]  # meciul 2 e peste 3 h
    a = found[0]
    assert 0.08 <= a["edge"] <= 0.30 and a["superbet"] == 2.25 and a["pinnacle"] == 1.96
    assert LV.track(c, NOW)["new"] == 1
    assert LV.track(c, NOW + timedelta(minutes=30))["new"] == 0  # aceeași selecție nu se mai alertează
    row = c.execute("SELECT alerted_at, superbet, pin_price FROM lv_track").fetchone()
    assert row["alerted_at"] == _iso(NOW) and row["superbet"] == 2.25 and row["pin_price"] == 1.96


def test_stale_superbet_offer_is_ignored():
    c = _db()
    c.execute("UPDATE ext_event SET checked_at=?", (_iso(NOW - timedelta(hours=5)),))
    c.execute("UPDATE odds_snapshot SET observed_at=? WHERE source='superbet'", (_iso(NOW - timedelta(hours=5)),))
    assert LV.find(c, NOW) == []


def test_closing_clv_and_settlement():
    c = _db()
    LV.track(c, NOW)
    # Pinnacle scade gazdele la 1.85 înainte de start → CLV pozitiv
    _odds(c, 1, "bsd:pinnacle", NOW + timedelta(minutes=100), "1x2", 0.0, {"HOME": 1.85, "DRAW": 3.8, "AWAY": 4.6})
    c.execute("UPDATE match SET status='finished', ft_home=2, ft_away=0 WHERE id=1")
    LV.track(c, NOW + timedelta(hours=4))
    r = c.execute("SELECT close_pin, clv, result FROM lv_track").fetchone()
    assert r["close_pin"] == 1.85 and r["clv"] > 0.15 and r["result"] == "won"
    rec = LV.record(c)
    assert rec["settled"] == 1 and rec["won"] == 1 and rec["roi"] == 1.25 and rec["clv_n"] == 1
    d = LV.doc(c, NOW + timedelta(hours=4))
    assert d["paper"] and d["alerts"] == [] and d["recent"][0]["result"] == "won" and d["recent"][0]["label"] == "Final 1"


def test_no_clv_without_a_later_pinnacle_price():
    c = _db()
    LV.track(c, NOW)
    c.execute("UPDATE match SET status='finished', ft_home=0, ft_away=1 WHERE id=1")
    LV.track(c, NOW + timedelta(hours=4))
    r = c.execute("SELECT clv, result FROM lv_track").fetchone()
    assert r["clv"] is None and r["result"] == "lost"


def test_doc_lists_active_alert_with_superbet_link():
    c = _db()
    LV.track(c, NOW)
    d = LV.doc(c, NOW + timedelta(minutes=5))
    a = d["alerts"][0]
    assert a["superbet_url"].endswith("-991") and a["fair"] == round(1 / a["p_fair"], 2) and a["stake"] == 1.0
    assert d["record"]["alerts"] == 1 and d["record"]["pending"] == 1
