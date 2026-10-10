import sqlite3
from datetime import date

from betpredict.builder.tickets import _count


def test_replaced_tickets_do_not_count_as_existing():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE ticket (id INTEGER PRIMARY KEY, day TEXT, kind TEXT, created_by TEXT, status TEXT, variant TEXT)")
    c.execute("INSERT INTO ticket (day, kind, created_by, status, variant) VALUES ('2026-10-10','acca_50','robot','replaced','valoare')")
    assert _count(c, date(2026, 10, 10), "1=1") == 0
    c.execute("INSERT INTO ticket (day, kind, created_by, status, variant) VALUES ('2026-10-10','acca_50','robot','pending','valoare')")
    assert _count(c, date(2026, 10, 10), "1=1") == 1
