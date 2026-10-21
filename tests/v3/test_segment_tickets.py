import sqlite3
from datetime import date, datetime, timezone

from betpredict.builder import segment_tickets as T
from betpredict.store.db import init_db


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    return c


def _row(i, odds, p, lg, market="over_under"):
    return {"match_id": i, "market": market, "line": 1.5 if market == "over_under" else 0.0, "selection": "OVER" if market == "over_under" else "C85",
            "prediction_id": None, "odds": odds, "p": p, "league_id": lg, "kickoff_utc": "2026-10-21T18:00:00Z", "profile": "cota 1.25–1.5", "rank": 0.02}


def test_two_tickets_low_odds_distinct_matches_and_once_per_day():
    c = _db()
    for i in range(1, 40):
        c.execute("INSERT INTO match (id, kickoff_utc, home_name, away_name, status, league_id) VALUES (?,?,?,?,?,?)",
                  (i, "2026-10-21T18:00:00Z", f"H{i}", f"A{i}", "notstarted", i % 15))
    rows = [_row(i, 1.28 + (i % 4) * 0.03, 0.8 - i * 0.002, i % 15, "ss" if i % 3 == 0 else "over_under") for i in range(1, 40)]
    rows.append(_row(99, 3.2, 0.9, 1))  # cotă mare: nu intră
    now = datetime(2026, 10, 21, 8, tzinfo=timezone.utc)
    r = T.build(c, date(2026, 10, 21), now, rows=rows)
    assert [t["target"] for t in r["tickets"]] == [5.0, 20.0]
    legs = c.execute("SELECT ticket_id, match_id, market, odds FROM ticket_leg").fetchall()
    assert len({l["match_id"] for l in legs}) == len(legs)          # meciuri diferite pe cele două bilete
    assert max(l["odds"] for l in legs) <= 1.9 and 99 not in {l["match_id"] for l in legs}
    assert {l["market"] for l in legs} >= {"ss|0", "over_under|1.5"}
    assert T.build(c, date(2026, 10, 21), now, rows=rows) == {"skipped_existing": 2}
