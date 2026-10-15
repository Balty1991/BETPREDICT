import sqlite3
from datetime import datetime, timezone

from betpredict.ingest import sb_catalog as C


def test_catalog_counts_each_match_once_and_flags_tracked():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    ev = {"odds": [{"marketName": "A doua repriză - Interval goluri", "name": "1-3", "price": 1.33, "marketId": 7},
                   {"marketName": "Total cornere echipa gazdă", "name": "Peste 4.5", "price": 1.80},
                   {"marketName": "Total cornere echipa gazdă", "name": "Peste 4.5", "price": 1.80},
                   {"marketName": "X", "name": "Y", "price": 1.0},
                   {"marketName": "Rapid Viena câștigă; Peste 1.5 goluri", "name": "Da", "price": 2.1}]}
    stamp = "2026-10-15T08:00:00Z"
    assert C.record(c, 1, ev, stamp) == 2
    C.record(c, 1, ev, stamp)                       # același meci recitit: nu se numără din nou
    ev2 = {"odds": [{"marketName": "A doua repriză - Interval goluri", "name": "1-3", "price": 1.41}]}
    C.record(c, 2, ev2, stamp)
    d = C.doc(c, now=datetime(2026, 10, 15, 9, tzinfo=timezone.utc), min_matches=1)
    m = {g["market"]: g for g in d["markets"]}
    o = m["A doua repriză - Interval goluri"]["outcomes"][0]
    assert o["n"] == 2 and o["avg"] == 1.37 and o["min"] == 1.33 and o["max"] == 1.41 and o["tracked"]
    assert not m["Total cornere echipa gazdă"]["tracked"] and d["markets"][0]["market"] == "A doua repriză - Interval goluri"
    assert C.doc(c, now=datetime(2026, 10, 15, 9, tzinfo=timezone.utc))["count"] == 0   # sub 3 meciuri: nu se publică
