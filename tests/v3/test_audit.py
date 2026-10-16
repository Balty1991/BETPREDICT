import sqlite3

from betpredict.publish.audit import audit_doc
from betpredict.store import db as DB


def test_audit_doc_lists_markets_with_status_and_timing():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row; DB.init_db(c)
    c.execute("""CREATE TABLE IF NOT EXISTS ss_track (match_id INTEGER, mkey TEXT, kickoff_utc TEXT, p REAL, odds REAL,
                 updated_at TEXT, result TEXT, odds_first REAL, PRIMARY KEY (match_id, mkey))""")
    for i in range(40):
        c.execute("INSERT INTO ss_track VALUES (?, 'G25', '2026-10-1%dT12:00:00Z', 0.7, 1.40, 'x', ?, 1.38)" % (i % 5), (i, "won" if i % 4 else "lost"))
    d = audit_doc(c)
    g = next(x for x in d["stil"] if x["key"] == "G25")
    assert g["n"] == 40 and g["roi"] == round(30 * 1.40 / 40 - 1, 4) and g["status"]
    assert d["timing"] and d["robot"] == [] and isinstance(d["boosts"], list)
