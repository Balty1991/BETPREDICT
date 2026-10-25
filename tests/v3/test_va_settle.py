import sqlite3
from datetime import datetime, timezone

from betpredict.publish import value_alerts as VA


def test_va_settles_only_finished_and_resettles():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE match (id INTEGER, ft_home INTEGER, ft_away INTEGER, status TEXT)")
    c.execute("INSERT INTO match VALUES (1, 0, 0, 'live')")
    now = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
    a = {"match_id": 1, "market": "over_under_2.5", "outcome": "OVER", "superbet": 2.0, "p_fair": 0.5, "value": 0.05}
    VA.track_and_settle(c, [a], now)
    assert c.execute("SELECT result FROM va_track").fetchone()[0] is None  # live 0-0: nu se decontează
    c.execute("UPDATE va_track SET result='lost'")  # decont vechi greșit
    c.execute("UPDATE match SET ft_home=2, ft_away=1, status='finished'")
    VA.track_and_settle(c, [], now)
    assert c.execute("SELECT result FROM va_track").fetchone()[0] == "won"
